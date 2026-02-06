from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image


def calculate_hash(file_path: str, algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    file_path_obj = Path(file_path)
    with file_path_obj.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_image_metadata(file_path: str) -> Dict[str, Any]:
    with Image.open(file_path) as image:
        width, height = image.size
        return {
            "width": width,
            "height": height,
            "format": image.format,
            "mode": image.mode,
        }


def load_image_for_model(file_path: str, target_size: Tuple[int, int] = (512, 512)) -> np.ndarray:
    with Image.open(file_path) as image:
        image = image.convert("RGB").resize(target_size)
        image_array = np.asarray(image, dtype=np.float32) / 255.0
    return image_array
