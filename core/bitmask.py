from __future__ import annotations

from typing import Iterable

FLAG_BASIC = 1
FLAG_NSFW = 2
FLAG_TAGS = 4
FLAG_FACE = 8
FLAG_VECTOR = 16

_MODULE_FLAG_MAP = {
    "basic": FLAG_BASIC,
    "statistics": FLAG_BASIC,
    "nsfw": FLAG_NSFW,
    "tags": FLAG_TAGS,
    "face": FLAG_FACE,
    "vector": FLAG_VECTOR,
}


def map_modules_to_flags(modules: Iterable[str]) -> int:
    selected_modules = list(modules)
    if not selected_modules:
        return FLAG_BASIC

    flags = 0
    for module in selected_modules:
        normalized = module.strip().lower()
        flags |= _MODULE_FLAG_MAP.get(normalized, 0)

    return flags or FLAG_BASIC
