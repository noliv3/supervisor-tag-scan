from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image


def calculate_hash(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_image_metadata(path: str) -> Dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
        return {
            "width": int(width),
            "height": int(height),
            "size": int(os.path.getsize(path)),
            "format": image.format,
        }


def load_image_for_model(path: str, target_size: Tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert("RGB").resize(target_size)
        image_array = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(image_array, axis=0)
