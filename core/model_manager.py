from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

import numpy as np
import tensorflow as tf
from PIL import Image

from core.bitmask import FLAG_FACE, FLAG_NSFW, FLAG_TAGS, FLAG_VECTOR

logger = logging.getLogger(__name__)


class ModelManager:
    _instance: "ModelManager | None" = None

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.models = {}
            cls._instance.tags = cls._instance._load_tags()
            cls._instance.tag_model_path = Path(
                os.getenv("DEEPDANBOORU_MODEL_PATH", "deepdanbooru-v3-20211112-sgd-e28.h5")
            )
        return cls._instance

    def load_models_for_flags(self, flags: int) -> None:
        if flags & FLAG_NSFW:
            self._load_model("nsfw", "Loading NSFW Model...")
        if flags & FLAG_TAGS:
            self._load_tags_model()
        if flags & FLAG_FACE:
            self._load_model("face", "Loading Face Detection Model...")
        if flags & FLAG_VECTOR:
            self._load_model("vector", "Loading Vector Embedding Model...")

    def _load_model(self, key: str, message: str) -> None:
        if key in self.models:
            return
        logger.info(message)
        self.models[key] = {"status": "loaded"}

    def _load_tags(self) -> List[str]:
        tags_path = Path(os.getenv("DEEPDANBOORU_TAGS_PATH", "tags.txt"))
        if not tags_path.exists():
            logger.warning("tags.txt not found at %s", tags_path)
            return []
        tags = [line.strip() for line in tags_path.read_text(encoding="utf-8").splitlines()]
        return [tag for tag in tags if tag]

    def _load_tags_model(self) -> None:
        if "tags" in self.models:
            return
        if not self.tag_model_path.exists():
            logger.warning("Tag model not found at %s", self.tag_model_path)
            return
        logger.info("Loading Tagging Model from %s", self.tag_model_path)
        self.models["tags"] = tf.keras.models.load_model(self.tag_model_path)

    def predict_tags(self, image_path: str, threshold: float = 0.5) -> List[str]:
        if "tags" not in self.models:
            logger.warning("Tag model not loaded; returning empty tag list")
            return []
        if not self.tags:
            logger.warning("No tags loaded; returning empty tag list")
            return []

        image = Image.open(image_path).convert("RGB").resize((512, 512))
        image_array = np.asarray(image, dtype=np.float32) / 255.0
        image_batch = np.expand_dims(image_array, axis=0)
        probs = self.models["tags"].predict(image_batch, verbose=0)[0]

        tag_count = min(len(self.tags), len(probs))
        return [
            self.tags[index]
            for index in range(tag_count)
            if float(probs[index]) >= threshold
        ]


model_manager = ModelManager()
