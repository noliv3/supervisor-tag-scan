from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from core.database import ScannerDB

logger = logging.getLogger(__name__)

router = APIRouter()
db = ScannerDB()

TOKENS_PATH = Path("tokens.json")
SERVER_SECRET = os.getenv("SERVER_SECRET", "change-me")
EXPIRY_SECONDS = 3600 * 24 * 30


class TokenRequest(BaseModel):
    mail: Optional[str] = None
    webseite: Optional[str] = None


class TokenResponse(BaseModel):
    token: str
    status: str


async def _load_tokens() -> Dict[str, Any]:
    if not TOKENS_PATH.exists():
        return {}
    async with aiofiles.open(TOKENS_PATH, "r", encoding="utf-8") as handle:
        content = await handle.read()
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    return {}


def _is_new_token_entry(value: Any) -> bool:
    return isinstance(value, dict) and (
        "mail" in value
        or "webseite" in value
        or "status" in value
        or "timestamp" in value
    )


def _is_legacy_entry(value: Any) -> bool:
    if isinstance(value, dict):
        return "token" in value or "ts" in value
    return isinstance(value, str)


def _cleanup_legacy_tokens(tokens: Dict[str, Any]) -> bool:
    now = int(time.time())
    changed = False
    for key, value in list(tokens.items()):
        if not _is_legacy_entry(value):
            continue
        if isinstance(value, dict):
            ts_value = value.get("ts")
            if ts_value is None:
                continue
            try:
                ts_int = int(ts_value)
            except (TypeError, ValueError):
                continue
            if now - ts_int > EXPIRY_SECONDS:
                tokens.pop(key, None)
                changed = True
    return changed


async def _save_tokens(tokens: Dict[str, Any]) -> None:
    tmp_path = TOKENS_PATH.with_suffix(TOKENS_PATH.suffix + ".tmp")
    async with aiofiles.open(tmp_path, "w", encoding="utf-8") as handle:
        payload = json.dumps(tokens, indent=2, sort_keys=True)
        await handle.write(payload)
    os.replace(tmp_path, TOKENS_PATH)


async def verify_token(token: str) -> bool:
    tokens = await _load_tokens()
    changed = _cleanup_legacy_tokens(tokens)

    if token in tokens:
        token_info = tokens.get(token, {})
        if isinstance(token_info, dict):
            db.record_token_use(token, token_info.get("mail"), token_info.get("webseite"))
        else:
            db.record_token_use(token, None, None)
        if changed:
            await _save_tokens(tokens)
        return True

    for email, value in tokens.items():
        if _is_new_token_entry(value):
            continue
        if isinstance(value, dict) and value.get("token") == token:
            db.record_token_use(token, mail=email, webseite=None)
            if changed:
                await _save_tokens(tokens)
            return True
        if isinstance(value, str) and value == token:
            db.record_token_use(token, mail=email, webseite=None)
            if changed:
                await _save_tokens(tokens)
            return True

    if changed:
        await _save_tokens(tokens)
    return False


def _build_token(mail: str, webseite: str) -> str:
    payload = f"{mail}:{webseite}:{SERVER_SECRET}".encode()
    return hashlib.sha256(payload).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def legacy_get_token(email: str, renew: bool) -> str:
    tokens = await _load_tokens()
    changed = _cleanup_legacy_tokens(tokens)
    entry = tokens.get(email)
    token: str | None = None
    if not renew and entry is not None:
        if isinstance(entry, dict) and entry.get("token"):
            token = str(entry.get("token"))
        elif isinstance(entry, str):
            token = entry

    if token is None:
        token = secrets.token_hex(16)
        tokens[email] = {"token": token, "ts": int(time.time())}
        changed = True

    if changed:
        await _save_tokens(tokens)
    return token


@router.get("/token")
async def get_token(
    request: Request,
    mail: Optional[str] = Query(default=None),
    webseite: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
) -> TokenResponse | PlainTextResponse | JSONResponse:
    if "email" in request.query_params:
        if not email:
            return JSONResponse(status_code=400, content={"error": "missing email"})
        renew = "renew" in request.query_params
        token = await legacy_get_token(email, renew)
        return PlainTextResponse(token, status_code=200, media_type="text/plain; charset=utf-8")

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
