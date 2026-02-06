from __future__ import annotations

import logging
import mimetypes
from io import BytesIO

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

try:
    from PIL import ImageFile
except Exception:
    ImageFile = None

from core import legacy_batch, legacy_pipeline
from core.database import ScannerDB
from routers.auth import verify_token

router = APIRouter()
db = ScannerDB()

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_BATCH_SIZE = 25 * 1024 * 1024

Image.MAX_IMAGE_PIXELS = 50_000_000
if ImageFile is not None:
    ImageFile.LOAD_TRUNCATED_IMAGES = False

logger = logging.getLogger("legacy_http")
if not logger.handlers:
    handler = logging.FileHandler("scanner.log")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _log_raw(request: Request, note: str) -> None:
    client = request.client.host if request.client else "unknown"
    headers_dump = "\n".join(f"{key}: {value}" for key, value in request.headers.items())
    payload = (
        f"[Fehlversuch] {client} -> {note}\n"
        f"{request.method} {request.url}\n"
        f"{headers_dump}\n"
    )
    with open("raw_connections.log", "a", encoding="utf-8") as handle:
        handle.write(payload)


@router.get("/stats")
async def get_stats(request: Request) -> JSONResponse:
    logger.info("[LEGACY_HTTP] [STATS] [START]")
    token = request.headers.get("authorization", "")
    if not token or not await verify_token(token):
        _log_raw(request, "forbidden")
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    stats = db.get_legacy_stats()
    logger.info("[LEGACY_HTTP] [STATS] [DONE]")
    return JSONResponse(status_code=200, content=stats)


@router.post("/check")
async def check_image(request: Request) -> JSONResponse:
    logger.info("[LEGACY_HTTP] [CHECK] [START]")
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        _log_raw(request, "invalid content-type")
        return JSONResponse(status_code=403, content={"error": "invalid content-type"})

    token = request.headers.get("authorization", "")
    if not token or not await verify_token(token):
        _log_raw(request, "forbidden")
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    form = await request.form()
    upload = form.get("image")
    if upload is None or not isinstance(upload, UploadFile):
        return JSONResponse(status_code=400, content={"error": "image missing"})

    image_bytes = await upload.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return JSONResponse(status_code=413, content={"error": "payload too large"})

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid image"})

    result = await legacy_pipeline.process_image_bytes(image_bytes, db)
    logger.info("[LEGACY_HTTP] [CHECK] [DONE]")
    return JSONResponse(status_code=200, content=result)


@router.post("/batch")
async def batch_scan(request: Request) -> JSONResponse:
    logger.info("[LEGACY_HTTP] [BATCH] [START]")
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        _log_raw(request, "invalid content-type")
        return JSONResponse(status_code=403, content={"error": "invalid content-type"})

    token = request.headers.get("authorization", "")
    if not token or not await verify_token(token):
        _log_raw(request, "forbidden")
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    form = await request.form()
    upload = form.get("file")
    if upload is None or not isinstance(upload, UploadFile):
        return JSONResponse(status_code=400, content={"error": "file missing"})

    file_bytes = await upload.read()
    if len(file_bytes) > MAX_BATCH_SIZE:
        return JSONResponse(status_code=413, content={"error": "payload too large"})

    mime = upload.content_type
    if not mime and upload.filename:
        mime, _ = mimetypes.guess_type(upload.filename)
    mime = mime or ""

    try:
        result = await legacy_batch.scan_batch(file_bytes, mime)
        logger.info("[LEGACY_HTTP] [BATCH] [DONE]")
        return JSONResponse(status_code=200, content=result)
    except Exception as exc:
        logger.exception("[LEGACY_HTTP] [BATCH] [ERROR]")
        return JSONResponse(status_code=500, content={"error": str(exc)})
