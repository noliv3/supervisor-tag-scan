from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

import numpy as np
from PIL import Image


def calculate_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    file_path_obj = Path(file_path)
    with file_path_obj.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_image_metadata(file_path: str) -> Dict[str, Any]:
    file_path_obj = Path(file_path)
    with Image.open(file_path_obj) as image:
        width, height = image.size
        return {
            "width": int(width),
            "height": int(height),
            "format": image.format,
            "size": int(file_path_obj.stat().st_size),
        }


def load_image_for_model(file_path: str) -> np.ndarray:
    with Image.open(file_path) as image:
        image = image.convert("RGB").resize((512, 512))
        image_array = np.asarray(image, dtype=np.float32) / 255.0
    return image_array
