from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.bitmask import map_modules_to_flags
from core.model_manager import model_manager
from routers.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()


class LegacyRequest(BaseModel):
    file_path: str
    modules: List[str] = []
    token: str


@router.post("/scan_image")
def scan_image(request: LegacyRequest) -> dict:
    if not verify_token(request.token):
        raise HTTPException(status_code=401, detail="Invalid token")

    flags = map_modules_to_flags(request.modules)
    model_manager.load_models_for_flags(flags)

    logger.info("Scanning file %s with flags %s", request.file_path, flags)

    return {
        "tags": [],
        "nsfw_scores": {},
        "statistics": {},
    }
