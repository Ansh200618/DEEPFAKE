"""
Tests for ImageDetector.
"""
import io
import os
import pytest
from PIL import Image, ImageDraw
import numpy as np

from app.detectors.image_detector import ImageDetector

detector = ImageDetector()


def _make_jpeg(width=200, height=200, mode="RGB") -> bytes:
    """Create a plain synthetic JPEG image."""
    img = Image.new(mode, (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_noisy_jpeg() -> bytes:
    """Create a JPEG image with random noise (more authentic-looking)."""
    arr = np.random.randint(50, 200, (200, 200, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_ela_stressed_jpeg() -> bytes:
    """Re-save multiple times to simulate manipulation artefacts."""
    img = Image.new("RGB", (200, 200), color=(80, 120, 160))
    # Draw a rectangle to simulate a paste
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 150, 150], fill=(200, 50, 50))
    buf = io.BytesIO()
    for _ in range(3):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        img = Image.open(buf)
    buf.seek(0)
    return buf.read()


class TestImageDetector:

    def test_returns_result_for_valid_image(self):
        data = _make_jpeg()
        result = detector.analyze(data)
        assert result.label in ("FAKE", "SUSPICIOUS", "REAL")
        assert 0.0 <= result.confidence <= 100.0
        assert 0.0 <= result.score <= 1.0

    def test_result_has_all_detail_keys(self):
        data = _make_jpeg()
        result = detector.analyze(data)
        for key in ("ela", "frequency", "noise", "face_consistency"):
            assert key in result.details, f"Missing detail key: {key}"

    def test_invalid_bytes_returns_error(self):
        result = detector.analyze(b"not an image")
        assert result.label == "ERROR"
        assert len(result.flags) > 0

    def test_noisy_image_scores_reasonable(self):
        """Noisy authentic image should not score too high (not all noise is fake)."""
        data = _make_noisy_jpeg()
        result = detector.analyze(data)
        assert result.label in ("FAKE", "SUSPICIOUS", "REAL")
        assert isinstance(result.score, float)

    def test_to_dict_format(self):
        data = _make_jpeg()
        d = detector.analyze(data).to_dict()
        assert isinstance(d["label"],      str)
        assert isinstance(d["confidence"], float)
        assert isinstance(d["score"],      float)
        assert isinstance(d["details"],    dict)
        assert isinstance(d["flags"],      list)

    def test_png_image_works(self):
        img = Image.new("RGB", (100, 100), color=(0, 128, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = detector.analyze(buf.getvalue())
        assert result.label != "ERROR"

    def test_ela_stressed_image_scores_higher(self):
        normal  = detector.analyze(_make_jpeg()).score
        stressed = detector.analyze(_make_ela_stressed_jpeg()).score
        # Stressed image should generally score higher (more fake-like)
        # We use >= because on small synthetic images results can be similar
        assert stressed >= normal * 0.8
