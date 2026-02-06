from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException
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
async def scan_image(request: LegacyRequest, background_tasks: BackgroundTasks) -> dict:
    if not await verify_token(request.token):
        raise HTTPException(status_code=401, detail="Invalid token")

    path = request.file_path
    flags = map_modules_to_flags(request.modules)

    logger.info("[LEGACY_API] [SCAN] [START] %s flags=%s", path, flags)
    result: dict = {"file_path": path}

    try:
        file_hash = image_utils.calculate_hash(path)
    except OSError:
        logger.exception("[LEGACY_API] [HASH] [ERROR] %s", path)
        result["error"] = "Failed to read file"
        result["statistics"] = {}
        result["nsfw_score"] = 0.0
        result["tags"] = []
        return result

    existing = db.get_file_record(file_hash) or {}
    flags_done = existing.get("flags_done", 0)
    needed_now = flags & ~flags_done

    logger.info(
        "[LEGACY_API] [SMART_SCAN] [EVAL] flags_done=%s needed_now=%s",
        flags_done,
        needed_now,
    )

    meta = existing.get("meta_json")
    nsfw_score = existing.get("nsfw_score")
    tags_data = {
        "tags": existing.get("tags", []),
        "characters": existing.get("characters", []),
    }

    if needed_now and image_utils.is_image_corrupt(path):
        logger.error("[LEGACY_API] [VALIDATE] [CORRUPT] %s", path)
        result["error"] = "Corrupt or unreadable image"
        result["statistics"] = meta or {}
        result["nsfw_score"] = nsfw_score if nsfw_score is not None else 0.0
        result["tags"] = tags_data.get("tags", []) + tags_data.get("characters", [])
        return result

    if needed_now:
        model_manager.load_models_for_flags(needed_now)

    if needed_now & FLAG_BASIC:
        logger.info("[LEGACY_API] [BASIC] [RUN] %s", path)
        try:
            meta = image_utils.get_image_metadata(path)
        except (OSError, ValueError):
            logger.exception("[LEGACY_API] [BASIC] [ERROR] %s", path)

    if needed_now & FLAG_NSFW:
        logger.info("[LEGACY_API] [NSFW] [RUN] %s", path)
        nsfw_score = model_manager.predict_nsfw(path)

    if needed_now & FLAG_TAGS:
        logger.info("[LEGACY_API] [TAGS] [RUN] %s", path)
        tags_data = model_manager.predict_tags(path)
        characters = tags_data.get("characters", [])
        if characters:
            logger.info(
                "[LEGACY_API] [TAGS] [CHARACTERS] %s",
                ", ".join(characters),
            )

    result["statistics"] = meta or {}
    result["nsfw_score"] = nsfw_score if nsfw_score is not None else 0.0
    result["tags"] = tags_data.get("tags", []) + tags_data.get("characters", [])

    if needed_now:
        db.upsert_scan_result(file_hash, path, needed_now, meta=meta, nsfw_score=nsfw_score)
        if tags_data.get("tags") or tags_data.get("characters"):
            db.save_tags(file_hash, tags_data.get("tags", []), tags_data.get("characters", []))
            background_tasks.add_task(
                db.update_tag_trends,
                tags_data.get("tags", []) + tags_data.get("characters", []),
            )

    logger.info("[LEGACY_API] [SCAN] [DONE] %s", path)
    return result
