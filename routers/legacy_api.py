from __future__ import annotations

import logging
import json
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.bitmask import FLAG_TAGS, map_modules_to_flags
from core.database import ScannerDB
from core import image_utils
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

    file_hash = image_utils.calculate_hash(request.file_path)
    metadata = image_utils.get_image_metadata(request.file_path)
    db.save_file_scan(file_hash, request.file_path, json.dumps(metadata), flags_done=0)

    flags = map_modules_to_flags(request.modules)
    model_manager.load_models_for_flags(flags)

    logger.info("Scanning file %s with flags %s", request.file_path, flags)

    tags: List[str] = []
    if flags & FLAG_TAGS:
        result = model_manager.predict_tags(request.file_path)
        tags = result.get("tags", [])
        db.save_tags(file_hash, tags, result.get("characters", []))
        db.update_file_flags(file_hash, FLAG_TAGS)

    return {
        "tags": tags,
        "nsfw_scores": {},
        "statistics": {},
    }
