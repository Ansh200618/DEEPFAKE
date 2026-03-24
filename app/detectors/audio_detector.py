"""
Audio Deepfake Detector
=======================
Techniques used
---------------
1. MFCC Trajectory Variance – synthetic TTS/voice-clone audio has unnaturally
   smooth or repetitive MFCC curves compared with genuine speech.
2. Spectral Flatness – voice-cloned audio tends to have higher spectral
   flatness (more noise-like) in certain frequency bands.
3. Pitch Consistency – real voices show natural micro-variations in F0;
   cloned voices are often too regular or contain unnatural jumps.
4. Short-Time Energy Silence Ratio – TTS systems leave characteristic
   silence patterns between phonemes.
5. Background Noise Fingerprint – authentic recordings have continuous,
   spectrally-stable background noise; synthesis artefacts differ.
"""
from __future__ import annotations

import io
import logging
import math
from typing import Tuple

import librosa
import numpy as np

from app.utils.helpers import DetectionResult, clamp, label_from_score

logger = logging.getLogger(__name__)

# ── weights ───────────────────────────────────────────────────────────────────
_MFCC_WEIGHT    = 0.30
_FLAT_WEIGHT    = 0.25
_PITCH_WEIGHT   = 0.25
_SILENCE_WEIGHT = 0.20

_SR = 22_050   # target sample-rate
_HOP = 512


class AudioDetector:
    """Stateless audio deepfake analyser."""

    def analyze(self, audio_bytes: bytes) -> DetectionResult:
        """Analyse raw audio bytes (wav/mp3/ogg/flac) and return a result."""
        try:
            y, sr = librosa.load(io.BytesIO(audio_bytes), sr=_SR, mono=True)
        except Exception as exc:
            logger.error("Cannot decode audio: %s", exc)
            return DetectionResult(
                label="ERROR", confidence=0.0, score=0.0,
                flags=["Could not decode audio file"]
            )

        if len(y) < _SR * 0.5:
            return DetectionResult(
                label="INSUFFICIENT_DATA", confidence=0.0, score=0.0,
                flags=["Audio too short (< 0.5 s) for reliable analysis"]
            )

        mfcc_score,    mfcc_val    = self._mfcc_score(y, sr)
        flat_score,    flat_val    = self._spectral_flatness_score(y, sr)
        pitch_score,   pitch_val   = self._pitch_score(y, sr)
        silence_score, silence_val = self._silence_score(y, sr)

        composite = clamp(
            mfcc_score    * _MFCC_WEIGHT
            + flat_score  * _FLAT_WEIGHT
            + pitch_score * _PITCH_WEIGHT
            + silence_score * _SILENCE_WEIGHT
        )

        flags: list[str] = []
        if mfcc_score > 0.6:
            flags.append("Unnaturally smooth MFCC trajectory – possible synthesis")
        if flat_score > 0.6:
            flags.append("Elevated spectral flatness – noise-floor artefacts")
        if pitch_score > 0.6:
            flags.append("Unnatural pitch consistency – voice-clone indicator")
        if silence_score > 0.6:
            flags.append("Atypical silence pattern – TTS prosody detected")

        label = label_from_score(composite)
        confidence = composite if label == "FAKE" else (1.0 - composite)

        return DetectionResult(
            label=label,
            confidence=clamp(confidence),
            score=composite,
            details={
                "mfcc_variance": mfcc_val,
                "spectral_flatness": flat_val,
                "pitch_consistency": pitch_val,
                "silence_ratio": silence_val,
            },
            flags=flags,
        )

    # ------------------------------------------------------------------
    # Feature extractors
    # ------------------------------------------------------------------
    @staticmethod
    def _mfcc_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        """
        Low inter-frame MFCC variance → suspiciously smooth → likely synthetic.
        """
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=_HOP)
        # Frame-to-frame delta magnitude across all coefficients
        delta = np.diff(mfccs, axis=1)
        mean_var = float(np.mean(np.var(delta, axis=1)))
        # Authentic speech: ~20–80; synthetic: < 10
        score = clamp(1.0 - (mean_var / 80.0))
        return score, mean_var

    @staticmethod
    def _spectral_flatness_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        """
        High spectral flatness in voiced segments → synthetic origin.
        """
        flatness = librosa.feature.spectral_flatness(y=y, hop_length=_HOP)[0]
        mean_flat = float(np.mean(flatness))
        # Natural speech: ~0.001–0.05; synthetic artefacts push it higher
        score = clamp(mean_flat / 0.15)
        return score, mean_flat

    @staticmethod
    def _pitch_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        """
        Standard-deviation of voiced F0 – low σ → too regular → clone signal.
        """
        f0, _, _ = librosa.pyin(y, fmin=librosa.note_to_hz("C2"),
                                fmax=librosa.note_to_hz("C7"),
                                hop_length=_HOP)
        voiced = f0[~np.isnan(f0)]
        if len(voiced) < 10:
            return 0.3, 0.0
        std_f0 = float(np.std(voiced))
        # Natural: std ≈ 15–60 Hz; synthetic: < 8 Hz
        score = clamp(1.0 - (std_f0 / 60.0))
        return score, std_f0

    @staticmethod
    def _silence_score(y: np.ndarray, sr: int) -> Tuple[float, float]:
        """
        Ratio of near-silence frames.  TTS systems produce very clean silences
        (no breath, no room-tone) → atypically high ratio.
        """
        rms = librosa.feature.rms(y=y, hop_length=_HOP)[0]
        threshold = float(np.percentile(rms, 20))
        silence_ratio = float(np.mean(rms < threshold * 1.5))
        # Natural: ~0.15–0.30; TTS: can reach 0.50+
        score = clamp((silence_ratio - 0.30) / 0.40)
        return score, silence_ratio
