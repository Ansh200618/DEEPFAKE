"""
Integration tests for the FastAPI endpoints.
"""
import io
import math
import struct
import wave

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app


# ── helpers ───────────────────────────────────────────────────────────────────
def _jpeg_bytes(w=120, h=120) -> bytes:
    img = Image.new("RGB", (w, h), color=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _wav_bytes(duration=2.0, sr=22050) -> bytes:
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    samples = (np.sin(2 * math.pi * 440 * t) * 0.5 +
               0.05 * np.random.randn(n)).astype(np.float32)
    samples = np.clip(samples, -1, 1)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((samples * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


@pytest.fixture
def transport():
    return ASGITransport(app=app)


# ── tests ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_detect_image_ok(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/image",
            files={"file": ("test.jpg", _jpeg_bytes(), "image/jpeg")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "label"      in data
    assert "confidence" in data
    assert "score"      in data
    assert "details"    in data
    assert "flags"      in data


@pytest.mark.asyncio
async def test_detect_text_ok(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/text",
            json={"text": "SHOCKING secret exposed – share before deleted!! Corrupt "
                          "elites want you to stay silent about this one weird trick."},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] in ("FAKE", "SUSPICIOUS", "REAL")


@pytest.mark.asyncio
async def test_detect_text_empty(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/detect/text", json={"text": "  "})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_detect_audio_ok(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/detect/audio",
            files={"file": ("test.wav", _wav_bytes(), "audio/wav")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "label" in data


@pytest.mark.asyncio
async def test_index_serves_html(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "DeepGuard" in resp.text
