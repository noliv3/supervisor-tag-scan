from __future__ import annotations

import io
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from tensorflow.keras.applications import mobilenet_v2

from core.bitmask import FLAG_NSFW, FLAG_TAGS
from core.database import ScannerDB
from core.model_manager import model_manager

logger = logging.getLogger(__name__)

_TAGGING_MODEL: Any | None = None


def _get_tagging_model() -> Any:
    global _TAGGING_MODEL
    if _TAGGING_MODEL is None:
        _TAGGING_MODEL = mobilenet_v2.MobileNetV2(weights="imagenet")
    return _TAGGING_MODEL


def _run_tagging(image_path: str) -> dict:
    model = _get_tagging_model()
    with Image.open(image_path) as image:
        image = image.convert("RGB").resize((224, 224), Image.BICUBIC)
        image_array = np.asarray(image, dtype=np.float32)
    image_batch = np.expand_dims(image_array, axis=0)
    image_batch = mobilenet_v2.preprocess_input(image_batch)
    preds = model.predict(image_batch, verbose=0)
    decoded = mobilenet_v2.decode_predictions(preds, top=3)[0]
    tags = [{"label": label, "score": float(score)} for (_, label, score) in decoded]
    return {"tags": tags}


def _run_nsfw(image_path: str) -> dict:
    model_manager.load_models_for_flags(FLAG_NSFW)
    if "nsfw" not in model_manager.models:
        return {"error": "NSFW model not loaded"}
    score = model_manager.predict_nsfw(image_path)
    score = max(0.0, min(1.0, float(score)))
    return {
        "drawings": 0.0,
        "hentai": score,
        "neutral": max(0.0, 1.0 - score),
        "porn": score,
        "sexy": score,
    }


def _run_deepdanbooru(image_path: str, threshold: float = 0.2) -> dict:
    model_manager.load_models_for_flags(FLAG_TAGS)
    tags = model_manager.predict_deepdanbooru_tags_with_scores(image_path, threshold=threshold)
    return {"tags": tags}


def run_tagging_from_path(image_path: str) -> dict:
    return _run_tagging(image_path)


def run_nsfw_from_path(image_path: str) -> dict:
    return _run_nsfw(image_path)


def run_deepdanbooru_from_path(image_path: str) -> dict:
    return _run_deepdanbooru(image_path)


def _extract_labels(tag_result: dict, key: str) -> list[str]:
    items = tag_result.get(key, []) if isinstance(tag_result, dict) else []
    labels: list[str] = []
    for item in items:
        label = item.get("label") if isinstance(item, dict) else None
        if label:
            labels.append(str(label))
    return labels


def _run_statistics(result: dict, db: ScannerDB) -> dict:
    tagging_labels = _extract_labels(result.get("modules.tagging", {}), "tags")
    ddb_labels = _extract_labels(result.get("modules.deepdanbooru_tags", {}), "tags")
    all_labels = tagging_labels + ddb_labels
    db.update_tag_trends(all_labels)
    db.record_legacy_tags(all_labels)
    return {"recorded": len(all_labels)}


def _run_image_storage(image_bytes: bytes, result: dict) -> dict:
    tag_module = result.get("modules.tagging", {})
    ddb_module = result.get("modules.deepdanbooru_tags", {})
    tags_raw = tag_module.get("tags") if isinstance(tag_module, dict) else None
    ddb_raw = ddb_module.get("tags") if isinstance(ddb_module, dict) else None
    nsfw_meta = result.get("modules.nsfw_scanner", {})

    output_dir = Path("scanned") / time.strftime("%Y_%m")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{time.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}.jpg"
    output_path = output_dir / filename

    with Image.open(io.BytesIO(image_bytes)) as image:
        image = image.convert("RGB")
        image.thumbnail((1280, 720), Image.BICUBIC)
        image.save(output_path, format="JPEG")
        width, height = image.width, image.height

    metadata = {
        "width": int(width),
        "height": int(height),
        "tags": tags_raw,
        "danbooru_tags": ddb_raw,
    }
    if isinstance(nsfw_meta, dict):
        metadata.update(nsfw_meta)

    return {"path": str(output_path), "metadata": metadata}


async def process_image_bytes(image_bytes: bytes, db: ScannerDB) -> dict:
    result: dict[str, Any] = {}
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            temp_file.write(image_bytes)
            temp_file.flush()
            temp_path = temp_file.name

        try:
            result["modules.nsfw_scanner"] = run_nsfw_from_path(temp_path)
        except Exception as exc:
            logger.exception("[LEGACY_PIPELINE] [NSFW] [ERROR]")
            result["modules.nsfw_scanner"] = {"error": str(exc)}

        try:
            result["modules.tagging"] = run_tagging_from_path(temp_path)
        except Exception as exc:
            logger.exception("[LEGACY_PIPELINE] [TAGGING] [ERROR]")
            result["modules.tagging"] = {"error": str(exc)}

        try:
            result["modules.deepdanbooru_tags"] = run_deepdanbooru_from_path(temp_path)
        except Exception as exc:
            logger.exception("[LEGACY_PIPELINE] [DDB] [ERROR]")
            result["modules.deepdanbooru_tags"] = {"error": str(exc)}

        try:
            result["modules.statistics"] = _run_statistics(result, db)
        except Exception as exc:
            logger.exception("[LEGACY_PIPELINE] [STATISTICS] [ERROR]")
            result["modules.statistics"] = {"error": str(exc)}

        try:
            result["modules.image_storage"] = _run_image_storage(image_bytes, result)
        except Exception as exc:
            logger.exception("[LEGACY_PIPELINE] [IMAGE_STORAGE] [ERROR]")
            result["modules.image_storage"] = {"error": str(exc)}
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    return result
