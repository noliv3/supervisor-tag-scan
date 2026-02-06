from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

import aiofiles
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

TOKENS_PATH = Path("tokens.json")


class TokenRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    token: str
    status: str


async def _load_tokens() -> Dict[str, str]:
    if not TOKENS_PATH.exists():
        return {}
    async with aiofiles.open(TOKENS_PATH, "r", encoding="utf-8") as handle:
        content = await handle.read()
        data = json.loads(content)
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items()}
    return {}


async def _save_tokens(tokens: Dict[str, str]) -> None:
    async with aiofiles.open(TOKENS_PATH, "w", encoding="utf-8") as handle:
        payload = json.dumps(tokens, indent=2, sort_keys=True)
        await handle.write(payload)


async def verify_token(token: str) -> bool:
    tokens = await _load_tokens()
    return token in tokens


@router.post("/token/generate", response_model=TokenResponse)
async def generate_token(request: TokenRequest) -> TokenResponse:
    tokens = await _load_tokens()
    tokens[request.token] = "active"
    await _save_tokens(tokens)
    logger.info("Generated token")
    return TokenResponse(token=request.token, status="generated")


@router.post("/token/refresh", response_model=TokenResponse)
async def refresh_token(request: TokenRequest) -> TokenResponse:
    tokens = await _load_tokens()
    tokens[request.token] = "refreshed"
    await _save_tokens(tokens)
    logger.info("Refreshed token")
    return TokenResponse(token=request.token, status="refreshed")
