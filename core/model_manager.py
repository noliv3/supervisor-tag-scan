from __future__ import annotations

import logging
import os
from typing import Dict, List, Set

import numpy as np
import tensorflow as tf

from core.bitmask import FLAG_NSFW, FLAG_TAGS
from core.image_utils import load_image_for_model

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
        self.models: Dict[str, tf.keras.Model] = {}
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
        if flags & FLAG_NSFW and "nsfw" not in self.models:
            self._load_nsfw_model()
        if flags & FLAG_TAGS and "tags" not in self.models:
            self._load_tags_model()

    def _load_nsfw_model(self) -> None:
        if not os.path.exists(self.nsfw_model_path):
            logger.warning("NSFW model not found at %s", self.nsfw_model_path)
            return
        logger.info("Loading NSFW model from %s", self.nsfw_model_path)
        self.models["nsfw"] = tf.keras.models.load_model(self.nsfw_model_path, compile=False)

    def _load_tags_model(self) -> None:
        if not os.path.exists(self.tags_model_path):
            logger.warning("Tag model not found at %s", self.tags_model_path)
            return
        logger.info("Loading Tagging Model from %s", self.tags_model_path)
        self.models["tags"] = tf.keras.models.load_model(self.tags_model_path, compile=False)

    def predict_nsfw(self, image_path: str) -> float | None:
        if "nsfw" not in self.models:
            logger.warning("NSFW model not loaded; returning None")
            return None
        logger.info("Predicting NSFW score for %s", image_path)
        image_batch = load_image_for_model(image_path, target_size=(224, 224))
        prediction = self.models["nsfw"].predict(image_batch, verbose=0)[0]
        score = float(prediction[1]) if len(prediction) > 1 else float(prediction[0])
        return score

    def predict_tags(self, image_path: str, threshold: float = 0.5) -> Dict[str, List[str]]:
        if "tags" not in self.models:
            logger.warning("Tag model not loaded; returning empty tag list")
            return {"tags": [], "characters": []}
        if not self.tags:
            logger.warning("No tags loaded; returning empty tag list")
            return {"tags": [], "characters": []}

        logger.info("Predicting tags for %s", image_path)
        image_batch = load_image_for_model(image_path, target_size=(512, 512))
        probs = self.models["tags"].predict(image_batch, verbose=0)[0]

        tag_count = min(len(self.tags), len(probs))
        selected_tags = [
            self.tags[index]
            for index in range(tag_count)
            if float(probs[index]) >= threshold
        ]
        character_tags = [tag for tag in selected_tags if tag in self.character_tags]
        general_tags = [tag for tag in selected_tags if tag not in self.character_tags]

        return {"tags": general_tags, "characters": character_tags}


model_manager = ModelManager()
