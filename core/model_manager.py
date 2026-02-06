from __future__ import annotations

import gc
import importlib
import importlib.util
import logging
import os
import time
from typing import Dict, List, Set

import numpy as np
from tensorflow.keras.models import load_model

from core.bitmask import FLAG_FACE, FLAG_NSFW, FLAG_TAGS, FLAG_VECTOR
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
        self.nsfw_model_path = os.path.join("models", "nsfw", "model.h5")
        self.tags_model_path = os.path.join("models", "deepdanbooru", "model.h5")
        self.tags_path = os.path.join("models", "deepdanbooru", "tags.txt")
        self.character_tags_path = os.path.join("models", "deepdanbooru", "tags-character.txt")
        self.face_model_path = os.path.join("models", "yolo", "yolov8n-face.pt")
        self.clip_model_name = os.environ.get("CLIP_MODEL_NAME", "ViT-B-32")
        self.clip_pretrained = os.environ.get("CLIP_PRETRAINED", "openai")
        self.clip_preprocess = None
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
        self._ensure_vram_capacity(flags)
        if flags & FLAG_NSFW and "nsfw" not in self.models:
            self._load_nsfw_model()
        if flags & FLAG_TAGS and "tags" not in self.models:
            self._load_tags_model()
        if flags & FLAG_FACE and "face" not in self.models:
            self._load_face_model()
        if flags & FLAG_VECTOR and "clip" not in self.models:
            self._load_clip_model()

    def can_run_flags(self, flags: int) -> bool:
        free_pct = self._get_free_vram_percent()
        if free_pct is None:
            return True
        if free_pct >= 15.0:
            return True
        heavy_flags = FLAG_TAGS | FLAG_FACE | FLAG_VECTOR
        if flags & heavy_flags:
            logger.warning(
                "[MODEL_MANAGER] [VRAM] [LOW] free_pct=%.2f%% flags=%s",
                free_pct,
                flags,
            )
            return False
        return True

    def _optional_import(self, module_name: str) -> object | None:
        if importlib.util.find_spec(module_name) is None:
            return None
        return importlib.import_module(module_name)

    def _get_free_vram_percent(self) -> float | None:
        torch_module = self._optional_import("torch")
        if torch_module is None:
            return None
        if not torch_module.cuda.is_available():
            return None
        free_bytes, total_bytes = torch_module.cuda.mem_get_info()
        if total_bytes == 0:
            return None
        return float(free_bytes) / float(total_bytes) * 100.0

    def _ensure_vram_capacity(self, flags: int) -> None:
        free_pct = self._get_free_vram_percent()
        if free_pct is None or free_pct >= 15.0:
            return
        requires_nsfw = bool(flags & FLAG_NSFW)
        unload_targets = self._unload_priority_targets(flags)
        if unload_targets:
            logger.info(
                "[MODEL_MANAGER] [VRAM] [PRESSURE] free_pct=%.2f%% unloading=%s",
                free_pct,
                ", ".join(unload_targets),
            )
        self._unload_models(unload_targets)
        free_pct = self._get_free_vram_percent()
        if free_pct is not None and free_pct < 15.0 and requires_nsfw:
            logger.warning(
                "[MODEL_MANAGER] [VRAM] [LOW_AFTER_UNLOAD] free_pct=%.2f%%",
                free_pct,
            )

    def _unload_priority_targets(self, flags: int) -> List[str]:
        required = set()
        if flags & FLAG_NSFW:
            required.add("nsfw")
        if flags & FLAG_TAGS:
            required.add("tags")
        if flags & FLAG_FACE:
            required.add("face")
        if flags & FLAG_VECTOR:
            required.add("clip")
        unload_order = ["tags", "clip", "face"]
        return [name for name in unload_order if name in self.models and name not in required]

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

    def _load_face_model(self) -> None:
        if not os.path.exists(self.face_model_path):
            logger.error("[MODEL_MANAGER] [LOAD_FACE] [NOT_FOUND] %s", self.face_model_path)
            return
        ultralytics = self._optional_import("ultralytics")
        if ultralytics is None:
            logger.error("[MODEL_MANAGER] [LOAD_FACE] [MISSING_DEPS] ultralytics")
            return
        logger.info("[MODEL_MANAGER] [LOAD_FACE] [START] %s", self.face_model_path)
        self.models["face"] = ultralytics.YOLO(self.face_model_path)
        self.model_last_used["face"] = time.time()
        logger.info("[MODEL_MANAGER] [LOAD_FACE] [OK]")

    def _load_clip_model(self) -> None:
        torch_module = self._optional_import("torch")
        open_clip = self._optional_import("open_clip")
        if torch_module is None or open_clip is None:
            logger.error("[MODEL_MANAGER] [LOAD_CLIP] [MISSING_DEPS] torch/open_clip")
            return
        logger.info("[MODEL_MANAGER] [LOAD_CLIP] [START] %s", self.clip_model_name)
        model, _, preprocess = open_clip.create_model_and_transforms(
            self.clip_model_name,
            pretrained=self.clip_pretrained,
        )
        model.eval()
        self.models["clip"] = model
        self.clip_preprocess = preprocess
        self.model_last_used["clip"] = time.time()
        logger.info("[MODEL_MANAGER] [LOAD_CLIP] [OK]")

    def _touch_model(self, name: str) -> None:
        self.model_last_used[name] = time.time()

    def _unload_models(self, model_names: List[str]) -> None:
        if not model_names:
            return
        for name in model_names:
            if name == "nsfw":
                continue
            try:
                del self.models[name]
                logger.info("[MODEL_MANAGER] [UNLOAD] [OK] %s", name)
            except KeyError:
                logger.warning("[MODEL_MANAGER] [UNLOAD] [SKIP] %s", name)
            self.model_last_used.pop(name, None)
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

    def predict_face_bboxes(self, image_path: str) -> List[dict]:
        if "face" not in self.models:
            logger.error("[MODEL_MANAGER] [PREDICT_FACE] [NOT_LOADED] returning empty")
            return []
        logger.info("[MODEL_MANAGER] [PREDICT_FACE] [START] %s", image_path)
        results = self.models["face"](image_path)
        self._touch_model("face")
        bboxes: List[dict] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                coords = box.xyxy[0].tolist()
                confidence = float(box.conf[0]) if getattr(box, "conf", None) is not None else None
                bboxes.append(
                    {
                        "x1": float(coords[0]),
                        "y1": float(coords[1]),
                        "x2": float(coords[2]),
                        "y2": float(coords[3]),
                        "confidence": confidence,
                    }
                )
        logger.info("[MODEL_MANAGER] [PREDICT_FACE] [OK] count=%d", len(bboxes))
        return bboxes

    def predict_clip_embedding(self, image_path: str) -> bytes | None:
        if "clip" not in self.models:
            logger.error("[MODEL_MANAGER] [PREDICT_CLIP] [NOT_LOADED] returning empty")
            return None
        torch_module = self._optional_import("torch")
        if torch_module is None:
            logger.error("[MODEL_MANAGER] [PREDICT_CLIP] [MISSING_DEPS] torch")
            return None
        if self.clip_preprocess is None:
            logger.error("[MODEL_MANAGER] [PREDICT_CLIP] [NO_PREPROCESS]")
            return None
        from PIL import Image

        logger.info("[MODEL_MANAGER] [PREDICT_CLIP] [START] %s", image_path)
        image = Image.open(image_path).convert("RGB")
        image_tensor = self.clip_preprocess(image).unsqueeze(0)
        with torch_module.no_grad():
            embedding = self.models["clip"].encode_image(image_tensor)
        embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        self._touch_model("clip")
        vector = embedding.squeeze(0).cpu().numpy().astype(np.float32)
        logger.info("[MODEL_MANAGER] [PREDICT_CLIP] [OK] dims=%d", vector.shape[0])
        return vector.tobytes()


model_manager = ModelManager()
