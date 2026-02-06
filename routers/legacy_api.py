from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import image_utils
from core.bitmask import FLAG_BASIC, FLAG_NSFW, FLAG_TAGS, map_modules_to_flags
from core.database import ScannerDB
from core.model_manager import model_manager
from routers.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()
db = ScannerDB()


class LegacyRequest(BaseModel):
    file_path: str
    modules: List[str] = Field(default_factory=list)
    token: str


@router.post("/scan_image")
async def scan_image(request: LegacyRequest) -> dict:
    if not await verify_token(request.token):
        raise HTTPException(status_code=401, detail="Invalid token")

    path = request.file_path
    file_hash = image_utils.calculate_hash(path)
    flags = map_modules_to_flags(request.modules)

    logger.info("Scanning file %s with flags %s", path, flags)
    model_manager.load_models_for_flags(flags)

    result: dict = {"file_path": path, "modules": request.modules}
    meta = None
    nsfw_score = None
    tags_data = {"tags": [], "characters": []}

    if flags & FLAG_BASIC:
        logger.info("Collecting basic metadata for %s", path)
        meta = image_utils.get_image_metadata(path)
        result["statistics"] = meta

    if flags & FLAG_NSFW:
        logger.info("Running NSFW prediction for %s", path)
        nsfw_score = model_manager.predict_nsfw(path)
        result["nsfw_score"] = nsfw_score

    if flags & FLAG_TAGS:
        logger.info("Running tag prediction for %s", path)
        tags_data = model_manager.predict_tags(path)
        result["tags"] = tags_data.get("tags", [])
        characters = tags_data.get("characters", [])
        if characters:
            logger.info("Detected character tags: %s", ", ".join(characters))

    db.save_scan_result(file_hash, path, flags, meta=meta, nsfw_score=nsfw_score)
    if tags_data.get("tags") or tags_data.get("characters"):
        db.save_tags(file_hash, tags_data.get("tags", []), tags_data.get("characters", []))

    return result
