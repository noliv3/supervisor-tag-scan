from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.bitmask import FLAG_TAGS, map_modules_to_flags
from core.model_manager import model_manager
from routers.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()


class LegacyRequest(BaseModel):
    file_path: str
    modules: List[str] = Field(default_factory=list)
    token: str


@router.post("/scan_image")
async def scan_image(request: LegacyRequest) -> dict:
    if not await verify_token(request.token):
        raise HTTPException(status_code=401, detail="Invalid token")

    flags = map_modules_to_flags(request.modules)
    model_manager.load_models_for_flags(flags)

    logger.info("Scanning file %s with flags %s", request.file_path, flags)

    tags: List[str] = []
    if flags & FLAG_TAGS:
        tags = await asyncio.to_thread(model_manager.predict_tags, request.file_path)

    return {
        "tags": tags,
        "nsfw_scores": {},
        "statistics": {},
    }
