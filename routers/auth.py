from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

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


def _load_tokens() -> Dict[str, str]:
    if not TOKENS_PATH.exists():
        return {}
    with TOKENS_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items()}
    return {}


def _save_tokens(tokens: Dict[str, str]) -> None:
    with TOKENS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(tokens, handle, indent=2, sort_keys=True)


def verify_token(token: str) -> bool:
    tokens = _load_tokens()
    return token in tokens


@router.post("/token/generate", response_model=TokenResponse)
def generate_token(request: TokenRequest) -> TokenResponse:
    tokens = _load_tokens()
    tokens[request.token] = "active"
    _save_tokens(tokens)
    logger.info("Generated token")
    return TokenResponse(token=request.token, status="generated")


@router.post("/token/refresh", response_model=TokenResponse)
def refresh_token(request: TokenRequest) -> TokenResponse:
    tokens = _load_tokens()
    tokens[request.token] = "refreshed"
    _save_tokens(tokens)
    logger.info("Refreshed token")
    return TokenResponse(token=request.token, status="refreshed")
