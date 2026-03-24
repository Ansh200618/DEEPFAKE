"""
Image Deepfake Detector
=======================
Techniques used
---------------
1. Error Level Analysis (ELA) – detects JPEG re-compression inconsistencies
   introduced by splicing or GAN post-processing.
2. DCT Frequency Fingerprint – GAN-generated faces exhibit a characteristic
   drop in high-frequency components (the "GAN frequency fingerprint").
3. Median-filter Noise Residual – manipulated regions differ statistically
   from authentic sensor noise.
4. Facial Region Consistency – colour / brightness variance inside the face
   bounding box relative to the surrounding background.
All features are combined into a single composite score in [0, 1].
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

from app.utils.helpers import DetectionResult, clamp, label_from_score

logger = logging.getLogger(__name__)

# ── thresholds / weights ──────────────────────────────────────────────────────
_ELA_HIGH_THRESH = 15.0      # mean ELA intensity → suspicious if > threshold
_ELA_WEIGHT = 0.35
_FREQ_WEIGHT = 0.30
_NOISE_WEIGHT = 0.20
_FACE_WEIGHT = 0.15
_JPEG_QUALITY = 90           # re-save quality for ELA


class ImageDetector:
    """Stateless image deepfake analyser."""

    # Haar cascade bundled with OpenCV – no extra download required.
    _face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze(self, image_bytes: bytes) -> DetectionResult:
        """Analyse *image_bytes* and return a :class:`DetectionResult`."""
        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            logger.error("Cannot open image: %s", exc)
            return DetectionResult(
                label="ERROR", confidence=0.0, score=0.0,
                flags=["Could not decode image"]
            )

        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        ela_score, ela_detail = self._ela_score(pil_img)
        freq_score, freq_detail = self._frequency_score(cv_img)
        noise_score, noise_detail = self._noise_score(cv_img)
        face_score, face_detail = self._face_consistency_score(cv_img)

        composite = clamp(
            ela_score   * _ELA_WEIGHT
            + freq_score  * _FREQ_WEIGHT
            + noise_score * _NOISE_WEIGHT
            + face_score  * _FACE_WEIGHT
        )

        flags: list[str] = []
        if ela_score > 0.6:
            flags.append("High ELA variance – possible splicing or re-encoding")
        if freq_score > 0.6:
            flags.append("Anomalous frequency spectrum – GAN fingerprint detected")
        if noise_score > 0.6:
            flags.append("Inconsistent sensor noise pattern")
        if face_score > 0.6:
            flags.append("Facial region colour/lighting inconsistency")

        label = label_from_score(composite)
        confidence = composite if label == "FAKE" else (1.0 - composite)

        return DetectionResult(
            label=label,
            confidence=clamp(confidence),
            score=composite,
            details={
                "ela": ela_detail,
                "frequency": freq_detail,
                "noise": noise_detail,
                "face_consistency": face_detail,
            },
            flags=flags,
        )

    # ------------------------------------------------------------------
    # Feature extractors
    # ------------------------------------------------------------------
    @staticmethod
    def _ela_score(pil_img: Image.Image) -> Tuple[float, float]:
        """
        Error Level Analysis.
        Re-save the image at *_JPEG_QUALITY* and compute the absolute
        pixel-difference.  Returns (normalised_score, mean_ela_value).
        """
        buffer = io.BytesIO()
        pil_img.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")

        ela = ImageChops.difference(pil_img, recompressed)
        ela_arr = np.array(ImageEnhance.Brightness(ela).enhance(20)).astype(float)
        mean_val = float(np.mean(ela_arr))

        # Typical authentic images → mean ≈ 2–8; manipulated → 10–40+
        score = clamp(mean_val / 40.0)
        return score, mean_val

    @staticmethod
    def _frequency_score(cv_img: np.ndarray) -> Tuple[float, float]:
        """
        GAN fingerprint via DCT energy ratio.
        Real camera images have roughly 1/f² power spectra; GAN images
        show a characteristic dip at high spatial frequencies.
        Returns (normalised_score, high_freq_energy_ratio).
        """
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        dct = cv2.dct(gray)
        total_energy = float(np.sum(dct ** 2)) + 1e-9

        h, w = dct.shape
        # High-frequency region: bottom-right quarter
        hf_energy = float(np.sum(dct[h // 2:, w // 2:] ** 2))
        ratio = hf_energy / total_energy

        # Natural images: ratio ≈ 0.02–0.12; GAN images: < 0.02
        # Lower ratio → more suspicious
        score = clamp(1.0 - (ratio / 0.12))
        return score, ratio

    @staticmethod
    def _noise_score(cv_img: np.ndarray) -> Tuple[float, float]:
        """
        Median-filter residual noise analysis.
        Authentic images have spatially-uniform noise; edited regions show
        discontinuities in the residual map.
        Returns (normalised_score, residual_std).
        """
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        blurred = cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float32)
        residual = np.abs(gray - blurred)

        std_val = float(np.std(residual))
        # High std → inconsistent noise (manipulated)
        score = clamp(std_val / 25.0)
        return score, std_val

    def _face_consistency_score(self, cv_img: np.ndarray) -> Tuple[float, float]:
        """
        Compare mean luminance / colour inside face bounding box vs background.
        Large discrepancy suggests the face was composited onto a different image.
        Returns (normalised_score, luminance_delta).
        """
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )

        if len(faces) == 0:
            # No face detected – neutral score
            return 0.3, 0.0

        # Use the largest detected face
        x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        face_region = cv_img[y: y + fh, x: x + fw]

        mask = np.ones(cv_img.shape[:2], dtype=bool)
        mask[y: y + fh, x: x + fw] = False
        background = cv_img[mask]

        face_lum = float(np.mean(cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)))
        if background.size == 0:
            return 0.3, 0.0
        bg_lum = float(np.mean(cv2.cvtColor(
            background.reshape(-1, 1, 3), cv2.COLOR_BGR2GRAY
        )))

        delta = abs(face_lum - bg_lum)
        score = clamp(delta / 80.0)
        return score, delta
