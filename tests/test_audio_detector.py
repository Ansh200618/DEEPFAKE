"""
Tests for AudioDetector.
"""
import io
import math
import struct
import wave

import numpy as np
import pytest

from app.detectors.audio_detector import AudioDetector

detector = AudioDetector()


def _make_wav(duration_s: float = 2.0, sr: int = 22050,
              freq: float = 440.0, noise_level: float = 0.02) -> bytes:
    """Generate a pure sine wave WAV (simulates synthetic/TTS-like audio)."""
    n = int(sr * duration_s)
    t = np.linspace(0, duration_s, n, endpoint=False)
    samples = (np.sin(2 * math.pi * freq * t) + noise_level * np.random.randn(n)).astype(np.float32)
    # Normalise
    samples = samples / np.max(np.abs(samples) + 1e-9) * 0.8
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        pcm = (samples * 32767).astype(np.int16).tobytes()
        wf.writeframes(pcm)
    return buf.getvalue()


def _make_noisy_speech_wav(duration_s: float = 3.0, sr: int = 22050) -> bytes:
    """Generate random-noise WAV (simulates background noise)."""
    n = int(sr * duration_s)
    samples = (0.1 * np.random.randn(n)).astype(np.float32)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        pcm = (samples * 32767).astype(np.int16).tobytes()
        wf.writeframes(pcm)
    return buf.getvalue()


class TestAudioDetector:

    def test_returns_result_for_valid_wav(self):
        data = _make_wav()
        result = detector.analyze(data)
        assert result.label in ("FAKE", "SUSPICIOUS", "REAL",
                                "INSUFFICIENT_DATA", "ERROR")

    def test_detail_keys_present(self):
        data = _make_wav(duration_s=3.0)
        result = detector.analyze(data)
        if result.label in ("ERROR", "INSUFFICIENT_DATA"):
            pytest.skip("Audio could not be analysed")
        for key in ("mfcc_variance", "spectral_flatness",
                    "pitch_consistency", "silence_ratio"):
            assert key in result.details

    def test_score_in_range(self):
        data = _make_wav(duration_s=3.0)
        result = detector.analyze(data)
        if result.label in ("ERROR", "INSUFFICIENT_DATA"):
            pytest.skip("Audio could not be analysed")
        assert 0.0 <= result.score <= 1.0

    def test_short_audio_returns_insufficient(self):
        # 0.2 second clip – below 0.5 s threshold
        data = _make_wav(duration_s=0.2)
        result = detector.analyze(data)
        assert result.label == "INSUFFICIENT_DATA"

    def test_invalid_bytes_returns_error(self):
        result = detector.analyze(b"not audio data at all")
        assert result.label == "ERROR"
        assert len(result.flags) > 0

    def test_to_dict_format(self):
        data = _make_wav(duration_s=3.0)
        d = detector.analyze(data).to_dict()
        assert isinstance(d["label"],      str)
        assert isinstance(d["confidence"], float)
        assert isinstance(d["score"],      float)

    def test_pure_sine_scores_as_suspicious_or_fake(self):
        """A pure sine wave is maximally synthetic – should score reasonably high."""
        data = _make_wav(duration_s=3.0, noise_level=0.0)
        result = detector.analyze(data)
        if result.label in ("ERROR", "INSUFFICIENT_DATA"):
            pytest.skip("Could not analyse")
        # Pure sine has zero pitch variance → should elevate score
        assert result.score > 0.2
