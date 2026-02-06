from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image, ImageFile, UnidentifiedImageError
from PIL.ExifTags import TAGS


def calculate_hash(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_image_corrupt(path: str) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return True
    return False


def compute_dhash(path: str, hash_size: int = 8) -> str:
    with Image.open(path) as image:
        image = image.convert("L").resize((hash_size + 1, hash_size), Image.BICUBIC)
        pixels = np.asarray(image, dtype=np.int16)
    diff = pixels[:, 1:] > pixels[:, :-1]
    bit_string = "".join("1" if value else "0" for value in diff.flatten())
    return f"{int(bit_string, 2):016x}"


def get_image_metadata(path: str) -> Dict[str, Any]:
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    with Image.open(path) as image:
        width, height = image.size
        exif_data = {}
        raw_exif = image.getexif()
        if raw_exif:
            for key, value in raw_exif.items():
                tag_name = TAGS.get(key, str(key))
                exif_data[tag_name] = value
        return {
            "width": int(width),
            "height": int(height),
            "filesize": int(os.path.getsize(path)),
            "format": image.format,
            "colorspace": image.mode,
            "exif": exif_data,
            "dhash": compute_dhash(path),
        }


def prepare_image(path: str, target_size: Tuple[int, int]) -> np.ndarray:
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    with Image.open(path) as image:
        image.load()
        image = image.convert("RGB").resize(target_size, Image.BICUBIC)
        image_array = np.asarray(image, dtype=np.float32) / 255.0
    return np.expand_dims(image_array, axis=0)
