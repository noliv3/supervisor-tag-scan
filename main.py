from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from core.database import ScannerDB
from routers import auth, legacy_api, legacy_http_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


db = ScannerDB()

app = FastAPI(title="SuperVisor-tag-scan")
app.include_router(legacy_api.router)
app.include_router(legacy_http_api.router)
app.include_router(auth.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    logger.info("Starting SuperVisor-tag-scan service")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
