from __future__ import annotations

import logging
from typing import Dict

from core.bitmask import FLAG_FACE, FLAG_NSFW, FLAG_TAGS, FLAG_VECTOR

logger = logging.getLogger(__name__)


class ModelManager:
    _instance: "ModelManager | None" = None

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.loaded_models = {}
        return cls._instance

    def load_models_for_flags(self, flags: int) -> None:
        if flags & FLAG_NSFW:
            self._load_model("nsfw", "Loading NSFW Model...")
        if flags & FLAG_TAGS:
            self._load_model("tags", "Loading Tagging Model...")
        if flags & FLAG_FACE:
            self._load_model("face", "Loading Face Detection Model...")
        if flags & FLAG_VECTOR:
            self._load_model("vector", "Loading Vector Embedding Model...")

    def _load_model(self, key: str, message: str) -> None:
        if key in self.loaded_models:
            return
        logger.info(message)
        self.loaded_models[key] = {"status": "loaded"}


model_manager = ModelManager()
