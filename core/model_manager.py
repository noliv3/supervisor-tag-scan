from __future__ import annotations

import gc
import logging
import os
import time
from typing import Dict, List, Set

from tensorflow.keras.models import load_model

from core.bitmask import FLAG_NSFW, FLAG_TAGS
from core.image_utils import prepare_image

logger = logging.getLogger(__name__)


class ModelManager:
    _instance: "ModelManager | None" = None

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.models: Dict[str, object] = {}
        self.model_last_used: Dict[str, float] = {}
        self.unload_timeout_seconds = 600
        self.nsfw_model_path = os.path.join("models", "nsfw", "model.h5")
        self.tags_model_path = os.path.join("models", "deepdanbooru", "model.h5")
        self.tags_path = os.path.join("models", "deepdanbooru", "tags.txt")
        self.character_tags_path = os.path.join("models", "deepdanbooru", "tags-character.txt")
        self.tags = self._load_tags()
        self.character_tags = self._load_character_tags()

    def _load_tags(self) -> List[str]:
        if not os.path.exists(self.tags_path):
            logger.warning("tags.txt not found at %s", self.tags_path)
            return []
        with open(self.tags_path, "r", encoding="utf-8") as tags_file:
            tags = [line.strip() for line in tags_file.read().splitlines()]
        return [tag for tag in tags if tag]

    def _load_character_tags(self) -> Set[str]:
        if not os.path.exists(self.character_tags_path):
            logger.warning("tags-character.txt not found at %s", self.character_tags_path)
            return set()
        with open(self.character_tags_path, "r", encoding="utf-8") as tags_file:
            tags = [line.strip() for line in tags_file.read().splitlines()]
        return {tag for tag in tags if tag}

    def load_models_for_flags(self, flags: int) -> None:
        self._unload_inactive_models()
        if flags & FLAG_NSFW and "nsfw" not in self.models:
            self._load_nsfw_model()
        if flags & FLAG_TAGS and "tags" not in self.models:
            self._load_tags_model()

    def _load_nsfw_model(self) -> None:
        if not os.path.exists(self.nsfw_model_path):
            logger.error("[MODEL_MANAGER] [LOAD_NSFW] [NOT_FOUND] %s", self.nsfw_model_path)
            return
        logger.info("[MODEL_MANAGER] [LOAD_NSFW] [START] %s", self.nsfw_model_path)
        try:
            self.models["nsfw"] = load_model(self.nsfw_model_path, compile=False)
            self.model_last_used["nsfw"] = time.time()
            logger.info("[MODEL_MANAGER] [LOAD_NSFW] [OK]")
        except OSError:
            logger.exception("[MODEL_MANAGER] [LOAD_NSFW] [ERROR] %s", self.nsfw_model_path)

    def _load_tags_model(self) -> None:
        if not os.path.exists(self.tags_model_path):
            logger.error("[MODEL_MANAGER] [LOAD_TAGS] [NOT_FOUND] %s", self.tags_model_path)
            return
        logger.info("[MODEL_MANAGER] [LOAD_TAGS] [START] %s", self.tags_model_path)
        try:
            self.models["tags"] = load_model(self.tags_model_path, compile=False)
            self.model_last_used["tags"] = time.time()
            logger.info("[MODEL_MANAGER] [LOAD_TAGS] [OK]")
        except OSError:
            logger.exception("[MODEL_MANAGER] [LOAD_TAGS] [ERROR] %s", self.tags_model_path)

    def _touch_model(self, name: str) -> None:
        self.model_last_used[name] = time.time()

    def _unload_inactive_models(self) -> None:
        now = time.time()
        inactive = [
            name
            for name, last_used in self.model_last_used.items()
            if now - last_used > self.unload_timeout_seconds
        ]
        for name in inactive:
            try:
                del self.models[name]
                logger.info("[MODEL_MANAGER] [UNLOAD] [OK] %s", name)
            except KeyError:
                logger.warning("[MODEL_MANAGER] [UNLOAD] [SKIP] %s", name)
            self.model_last_used.pop(name, None)
        if inactive:
            gc.collect()

    def predict_nsfw(self, image_path: str) -> float:
        if "nsfw" not in self.models:
            logger.error("[MODEL_MANAGER] [PREDICT_NSFW] [NOT_LOADED] returning 0.0")
            return 0.0
        logger.info("[MODEL_MANAGER] [PREDICT_NSFW] [START] %s", image_path)
        try:
            image_batch = prepare_image(image_path, target_size=(224, 224))
            prediction = self.models["nsfw"].predict(image_batch, verbose=0)[0]
            score = float(prediction[1]) if len(prediction) > 1 else float(prediction[0])
            self._touch_model("nsfw")
            if score >= 0.7:
                logger.warning("[MODEL_MANAGER] [PREDICT_NSFW] [HIGH_RISK] score=%.4f", score)
            elif score >= 0.3:
                logger.warning("[MODEL_MANAGER] [PREDICT_NSFW] [WARN] score=%.4f", score)
            else:
                logger.info("[MODEL_MANAGER] [PREDICT_NSFW] [OK] score=%.4f", score)
            return score
        except Exception:
            logger.exception("[MODEL_MANAGER] [PREDICT_NSFW] [ERROR] %s", image_path)
            return 0.0

    def predict_tags(self, image_path: str, threshold: float = 0.5) -> Dict[str, List[str]]:
        if "tags" not in self.models:
            logger.error("[MODEL_MANAGER] [PREDICT_TAGS] [NOT_LOADED] returning empty tags")
            return {"tags": [], "characters": []}
        if not self.tags:
            logger.error("[MODEL_MANAGER] [PREDICT_TAGS] [NO_TAGS] returning empty tags")
            return {"tags": [], "characters": []}

        logger.info("[MODEL_MANAGER] [PREDICT_TAGS] [START] %s", image_path)
        try:
            image_batch = prepare_image(image_path, target_size=(512, 512))
            probs = self.models["tags"].predict(image_batch, verbose=0)[0]
            self._touch_model("tags")
        except Exception:
            logger.exception("[MODEL_MANAGER] [PREDICT_TAGS] [ERROR] %s", image_path)
            return {"tags": [], "characters": []}

        tag_count = min(len(self.tags), len(probs))
        selected_tags = [
            self.tags[index]
            for index in range(tag_count)
            if float(probs[index]) >= threshold
        ]
        character_tags = [tag for tag in selected_tags if tag in self.character_tags]
        general_tags = [tag for tag in selected_tags if tag not in self.character_tags]

        logger.info(
            "[MODEL_MANAGER] [PREDICT_TAGS] [OK] general=%d character=%d",
            len(general_tags),
            len(character_tags),
        )
        return {"tags": general_tags, "characters": character_tags}


model_manager = ModelManager()
