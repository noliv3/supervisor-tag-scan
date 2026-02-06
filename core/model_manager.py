from __future__ import annotations

import logging
import os
from typing import Dict, List, Set

import numpy as np
import tensorflow as tf

from core.bitmask import FLAG_TAGS
from core.image_utils import load_image_for_model

logger = logging.getLogger(__name__)


class ModelManager:
    _instance: "ModelManager | None" = None

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.models = {}
            cls._instance.base_model_dir = os.path.join("models", "deepdanbooru")
            cls._instance.tags = cls._instance._load_tags()
            cls._instance.character_tags = cls._instance._load_character_tags()
        return cls._instance

    def _tags_path(self) -> str:
        return os.path.join(self.base_model_dir, "tags.txt")

    def _character_tags_path(self) -> str:
        return os.path.join(self.base_model_dir, "tags-character.txt")

    def _model_path(self) -> str | None:
        if not os.path.isdir(self.base_model_dir):
            return None
        model_files = sorted(
            file_name
            for file_name in os.listdir(self.base_model_dir)
            if file_name.lower().endswith(".h5")
        )
        if not model_files:
            return None
        return os.path.join(self.base_model_dir, model_files[0])

    def _load_tags(self) -> List[str]:
        tags_path = self._tags_path()
        if not os.path.exists(tags_path):
            logger.warning("tags.txt not found at %s", tags_path)
            return []
        with open(tags_path, "r", encoding="utf-8") as tags_file:
            tags = [line.strip() for line in tags_file.read().splitlines()]
        return [tag for tag in tags if tag]

    def _load_character_tags(self) -> Set[str]:
        character_tags_path = self._character_tags_path()
        if not os.path.exists(character_tags_path):
            logger.warning("tags-character.txt not found at %s", character_tags_path)
            return set()
        with open(character_tags_path, "r", encoding="utf-8") as tags_file:
            tags = [line.strip() for line in tags_file.read().splitlines()]
        return {tag for tag in tags if tag}

    def load_models_for_flags(self, flags: int) -> None:
        if flags & FLAG_TAGS:
            self._load_tags_model()

    def _load_tags_model(self) -> None:
        if "tags" in self.models:
            return
        model_path = self._model_path()
        if not model_path:
            logger.warning("Tag model not found in %s", self.base_model_dir)
            return
        logger.info("Loading Tagging Model from %s", model_path)
        self.models["tags"] = tf.keras.models.load_model(model_path)

    def predict_tags(self, image_path: str, threshold: float = 0.5) -> Dict[str, List[str]]:
        if "tags" not in self.models:
            logger.warning("Tag model not loaded; returning empty tag list")
            return {"tags": [], "characters": []}
        if not self.tags:
            logger.warning("No tags loaded; returning empty tag list")
            return {"tags": [], "characters": []}

        image_array = load_image_for_model(image_path)
        image_batch = np.expand_dims(image_array, axis=0)
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
