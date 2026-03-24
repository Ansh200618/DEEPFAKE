"""
DeepGuard – Deepfake & Fake-News Detection API
===============================================
Endpoints
---------
GET  /                   → Serve web UI
POST /api/detect/image   → Upload image file
POST /api/detect/audio   → Upload audio file
POST /api/detect/video   → Upload video file
POST /api/detect/text    → JSON body {"text": "..."}
GET  /api/health         → Health-check
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.detectors import AudioDetector, ImageDetector, TextDetector, VideoDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger("deepguard")

# ── Initialise detectors (once at startup) ────────────────────────────────────
_image   = ImageDetector()
_audio   = AudioDetector()
_video   = VideoDetector()
_text    = TextDetector()

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="DeepGuard",
    description="Multimodal deepfake & fake-news detection platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ── Middleware: request timing ────────────────────────────────────────────────
@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
    return response


# ── File-size guard (50 MB) ───────────────────────────────────────────────────
_MAX_BYTES = 50 * 1024 * 1024

async def _read_upload(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "File exceeds 50 MB limit")
    return data


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(_static_dir / "index.html"))


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/detect/image")
async def detect_image(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {"image/jpeg", "image/png",
                                            "image/webp", "image/gif",
                                            "image/bmp", "image/tiff"})
    data   = await _read_upload(file)
    result = _image.analyze(data)
    return JSONResponse(result.to_dict())


@app.post("/api/detect/audio")
async def detect_audio(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {"audio/mpeg", "audio/wav",
                                            "audio/ogg", "audio/flac",
                                            "audio/x-wav", "audio/mp3",
                                            "audio/x-m4a", "audio/aac",
                                            "application/octet-stream"})
    data   = await _read_upload(file)
    result = _audio.analyze(data)
    return JSONResponse(result.to_dict())


@app.post("/api/detect/video")
async def detect_video(file: UploadFile = File(...)):
    _check_content_type(file.content_type, {"video/mp4", "video/mpeg",
                                            "video/webm", "video/ogg",
                                            "video/quicktime", "video/x-msvideo",
                                            "application/octet-stream"})
    data   = await _read_upload(file)
    result = _video.analyze(data)
    return JSONResponse(result.to_dict())


class TextBody(BaseModel):
    text: str


@app.post("/api/detect/text")
async def detect_text(body: TextBody):
    if not body.text or not body.text.strip():
        raise HTTPException(400, "text field must not be empty")
    result = _text.analyze(body.text)
    return JSONResponse(result.to_dict())


# ── helpers ───────────────────────────────────────────────────────────────────
def _check_content_type(ct: str | None, allowed: set[str]):
    if ct and ct.split(";")[0].strip() not in allowed:
        raise HTTPException(415, f"Unsupported media type: {ct}")
