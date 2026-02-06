from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.database import ScannerDB

logger = logging.getLogger(__name__)

router = APIRouter()
db = ScannerDB()

TOKENS_PATH = Path("tokens.json")
SERVER_SECRET = os.getenv("SERVER_SECRET", "change-me")


class TokenRequest(BaseModel):
    mail: Optional[str] = None
    webseite: Optional[str] = None


class TokenResponse(BaseModel):
    token: str
    status: str


async def _load_tokens() -> Dict[str, Dict[str, Any]]:
    if not TOKENS_PATH.exists():
        return {}
    async with aiofiles.open(TOKENS_PATH, "r", encoding="utf-8") as handle:
        content = await handle.read()
        data = json.loads(content)
        if isinstance(data, dict):
            normalized: Dict[str, Dict[str, Any]] = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    normalized[str(key)] = value
                else:
                    normalized[str(key)] = {"status": str(value)}
            return normalized
    return {}


async def _save_tokens(tokens: Dict[str, Dict[str, Any]]) -> None:
    async with aiofiles.open(TOKENS_PATH, "w", encoding="utf-8") as handle:
        payload = json.dumps(tokens, indent=2, sort_keys=True)
        await handle.write(payload)


async def verify_token(token: str) -> bool:
    tokens = await _load_tokens()
    if token in tokens:
        token_info = tokens.get(token, {})
        db.record_token_use(token, token_info.get("mail"), token_info.get("webseite"))
        return True
    return False


def _build_token(mail: str, webseite: str) -> str:
    payload = f"{mail}:{webseite}:{SERVER_SECRET}".encode()
    return hashlib.sha256(payload).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/token", response_model=TokenResponse)
async def get_token(
    mail: Optional[str] = Query(default=None),
    webseite: Optional[str] = Query(default=None),
) -> TokenResponse:
    if not mail or not webseite:
        raise HTTPException(status_code=400, detail="Missing credentials")

    token = _build_token(mail, webseite)
    tokens = await _load_tokens()
    tokens[token] = {
        "mail": mail,
        "webseite": webseite,
        "status": "alive",
        "timestamp": _now_iso(),
    }
    await _save_tokens(tokens)
    db.record_token_use(token, mail, webseite)
    logger.info("[AUTH] [TOKEN] [ISSUED] %s", mail)
    return TokenResponse(token=token, status="alive")


@router.post("/token", response_model=TokenResponse)
async def post_token(request: TokenRequest) -> TokenResponse:
    if not request.mail or not request.webseite:
        raise HTTPException(status_code=400, detail="Missing credentials")

    token = _build_token(request.mail, request.webseite)
    tokens = await _load_tokens()
    tokens[token] = {
        "mail": request.mail,
        "webseite": request.webseite,
        "status": "alive",
        "timestamp": _now_iso(),
    }
    await _save_tokens(tokens)
    db.record_token_use(token, request.mail, request.webseite)
    logger.info("[AUTH] [TOKEN] [ISSUED] %s", request.mail)
    return TokenResponse(token=token, status="alive")
