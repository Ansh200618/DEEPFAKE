"""
Video Deepfake Detector
=======================
Techniques used
---------------
1. Per-frame image analysis   – each sampled frame is passed through the
   ImageDetector; a high mean frame score indicates face-swap / GAN generation.
2. Temporal consistency       – authentic video has smooth optical-flow between
   consecutive frames; deepfakes often have micro-jumps in the face region.
3. Eye-blink frequency        – deepfake subjects tend to blink less naturally
   due to training on still images.
4. Face-presence ratio        – sudden face appearance / disappearance is a
   manipulation indicator.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import List, Tuple

import cv2
import numpy as np

from app.detectors.image_detector import ImageDetector
from app.utils.helpers import DetectionResult, clamp, label_from_score

logger = logging.getLogger(__name__)

_SAMPLE_RATE     = 8    # analyse every Nth frame
_FRAME_WEIGHT    = 0.40
_TEMPORAL_WEIGHT = 0.30
_BLINK_WEIGHT    = 0.15
_FACE_RATIO_WT   = 0.15

_image_detector = ImageDetector()


class VideoDetector:
    """Stateless video deepfake analyser."""

    _face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    _eye_cascade  = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_eye.xml"
    )

    def analyze(self, video_bytes: bytes) -> DetectionResult:
        """Write *video_bytes* to a temp file, analyse, and return result."""
        suffix = ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        try:
            return self._analyze_file(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    def _analyze_file(self, path: str) -> DetectionResult:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return DetectionResult(
                label="ERROR", confidence=0.0, score=0.0,
                flags=["Could not open video file"]
            )

        frames: List[np.ndarray] = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % _SAMPLE_RATE == 0:
                frames.append(frame)
            idx += 1
        cap.release()

        if len(frames) < 2:
            return DetectionResult(
                label="INSUFFICIENT_DATA", confidence=0.0, score=0.0,
                flags=["Video too short for analysis"]
            )

        frame_score,    frame_val    = self._per_frame_score(frames)
        temporal_score, temporal_val = self._temporal_score(frames)
        blink_score,    blink_val    = self._blink_score(frames)
        face_ratio_score, face_ratio = self._face_ratio_score(frames)

        composite = clamp(
            frame_score        * _FRAME_WEIGHT
            + temporal_score   * _TEMPORAL_WEIGHT
            + blink_score      * _BLINK_WEIGHT
            + face_ratio_score * _FACE_RATIO_WT
        )

        flags: list[str] = []
        if frame_score > 0.55:
            flags.append("Multiple frames show image-level manipulation artefacts")
        if temporal_score > 0.55:
            flags.append("Optical-flow discontinuity in face region detected")
        if blink_score > 0.55:
            flags.append("Unnatural eye-blink pattern")
        if face_ratio_score > 0.55:
            flags.append("Inconsistent face-presence across frames")

        label = label_from_score(composite)
        confidence = composite if label == "FAKE" else (1.0 - composite)

        return DetectionResult(
            label=label,
            confidence=clamp(confidence),
            score=composite,
            details={
                "frame_score":      frame_val,
                "temporal_score":   temporal_val,
                "blink_rate":       blink_val,
                "face_ratio":       face_ratio,
                "frames_analyzed":  float(len(frames)),
            },
            flags=flags,
        )

    # ------------------------------------------------------------------
    # Feature extractors
    # ------------------------------------------------------------------
    @staticmethod
    def _per_frame_score(frames: List[np.ndarray]) -> Tuple[float, float]:
        """Run ImageDetector on each frame; return mean composite score."""
        scores = []
        for frame in frames:
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            result = _image_detector.analyze(buf.tobytes())
            if result.label != "ERROR":
                scores.append(result.score)
        if not scores:
            return 0.3, 0.3
        mean = float(np.mean(scores))
        return clamp(mean), mean

    def _temporal_score(self, frames: List[np.ndarray]) -> Tuple[float, float]:
        """
        Compute mean optical-flow magnitude between consecutive frames and
        check for sudden spikes (artefact of face-swap boundary).
        """
        flow_mags: List[float] = []
        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        for frame in frames[1:]:
            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            flow_mags.append(float(np.mean(mag)))
            prev_gray = curr_gray

        if not flow_mags:
            return 0.3, 0.0

        mean_flow = float(np.mean(flow_mags))
        std_flow  = float(np.std(flow_mags))
        # High std relative to mean → inconsistent motion → suspicious
        cv_flow = std_flow / (mean_flow + 1e-9)
        score = clamp(cv_flow / 2.0)
        return score, cv_flow

    def _blink_score(self, frames: List[np.ndarray]) -> Tuple[float, float]:
        """
        Count frames where eyes are detected.  A suspiciously low
        eye-detection rate suggests the eyes may have been synthesised open.
        """
        eye_detected = 0
        face_detected = 0
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(
                gray, 1.1, 5, minSize=(40, 40)
            )
            if len(faces) == 0:
                continue
            face_detected += 1
            x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
            roi = gray[y: y + fh, x: x + fw]
            eyes = self._eye_cascade.detectMultiScale(roi, 1.1, 3)
            if len(eyes) > 0:
                eye_detected += 1

        if face_detected == 0:
            return 0.3, 1.0

        eye_rate = eye_detected / face_detected
        # Natural video: eyes visible ~70–90% of face frames
        # Deepfake: often 95–100% (always open) or 30–50% (landmark errors)
        deviation = abs(eye_rate - 0.80)
        score = clamp(deviation / 0.40)
        return score, eye_rate

    def _face_ratio_score(self, frames: List[np.ndarray]) -> Tuple[float, float]:
        """
        Proportion of frames containing a face.  Sudden gaps in face
        presence can indicate stitching artefacts.
        """
        has_face: List[int] = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(
                gray, 1.1, 5, minSize=(40, 40)
            )
            has_face.append(1 if len(faces) > 0 else 0)

        ratio = float(np.mean(has_face))
        # Very high variance in face presence is suspicious
        variance = float(np.var(has_face))
        score = clamp(variance * 3.0)
        return score, ratio
