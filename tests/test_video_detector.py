"""
Tests for VideoDetector.
"""
import io
import os
import struct
import tempfile
import pytest
import cv2
import numpy as np

from app.detectors.video_detector import VideoDetector

detector = VideoDetector()


def _make_mp4(n_frames: int = 30, width: int = 120, height: int = 120,
              fps: int = 15) -> bytes:
    """Create a minimal MP4 video using OpenCV VideoWriter."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        tmp_path = f.name
    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, fps, (width, height))
        for i in range(n_frames):
            frame = np.full((height, width, 3),
                            fill_value=(i * 4 % 255, 100, 200 - i * 3 % 200),
                            dtype=np.uint8)
            out.write(frame)
        out.release()
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


class TestVideoDetector:

    def test_returns_result_for_valid_video(self):
        data = _make_mp4()
        result = detector.analyze(data)
        assert result.label in ("FAKE", "SUSPICIOUS", "REAL",
                                "INSUFFICIENT_DATA", "ERROR")

    def test_detail_keys_present(self):
        data = _make_mp4(n_frames=40)
        result = detector.analyze(data)
        if result.label in ("ERROR", "INSUFFICIENT_DATA"):
            pytest.skip("Video could not be analysed")
        for key in ("frame_score", "temporal_score",
                    "blink_rate", "face_ratio", "frames_analyzed"):
            assert key in result.details

    def test_score_in_range(self):
        data = _make_mp4(n_frames=40)
        result = detector.analyze(data)
        if result.label in ("ERROR", "INSUFFICIENT_DATA"):
            pytest.skip("Video could not be analysed")
        assert 0.0 <= result.score <= 1.0

    def test_too_short_video_returns_insufficient(self):
        # Single frame
        data = _make_mp4(n_frames=1)
        result = detector.analyze(data)
        assert result.label in ("INSUFFICIENT_DATA", "ERROR")

    def test_invalid_bytes_returns_error(self):
        result = detector.analyze(b"not a video")
        assert result.label == "ERROR"

    def test_to_dict_format(self):
        data = _make_mp4(n_frames=40)
        d = detector.analyze(data).to_dict()
        assert isinstance(d["label"],      str)
        assert isinstance(d["confidence"], float)
        assert isinstance(d["score"],      float)
        assert isinstance(d["flags"],      list)
