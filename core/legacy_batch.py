from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from core.bitmask import FLAG_NSFW, FLAG_TAGS
from core.model_manager import model_manager

GIF_STEP = 5
VIDEO_STEP = 20
MAX_OUT_FRAMES = 60


def _resolve_ffmpeg_bin() -> str:
    env_bin = os.getenv("FFMPEG_BIN")
    if env_bin:
        return env_bin
    local_bin = Path("ffmpeg") / "bin" / "ffmpeg"
    if os.name == "nt":
        local_bin = local_bin.with_suffix(".exe")
    return str(local_bin)


def _sample_indices(total: int, step: int) -> list[int]:
    if total <= 0:
        return []
    indices = {0, total - 1}
    indices.update(range(0, total, step))
    return sorted(index for index in indices if 0 <= index < total)


def _extract_frames(input_path: str, output_dir: str) -> list[Path]:
    ffmpeg_bin = _resolve_ffmpeg_bin()
    output_pattern = str(Path(output_dir) / "frame_%05d.png")
    command = [
        ffmpeg_bin,
        "-i",
        input_path,
        "-vf",
        "fps=1",
        "-vframes",
        str(MAX_OUT_FRAMES),
        output_pattern,
    ]
    subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return sorted(Path(output_dir).glob("frame_*.png"))


def _collect_ddb_tags(image_path: str) -> Iterable[str]:
    tags = model_manager.predict_deepdanbooru_tags_with_scores(image_path, threshold=0.2)
    return [tag.get("label") for tag in tags if isinstance(tag, dict) and tag.get("label")]


async def scan_batch(buf: bytes, mime: str = "") -> dict:
    model_manager.load_models_for_flags(FLAG_NSFW | FLAG_TAGS)
    temp_file = None
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as handle:
                handle.write(buf)
                handle.flush()
                temp_file = handle.name

            frames = _extract_frames(temp_file, temp_dir)
            total = len(frames)
            if total == 0:
                return {"risk": 0.0, "tags": [], "frameCount": 0}

            step = VIDEO_STEP if "video" in mime and "gif" not in mime else GIF_STEP
            indices = _sample_indices(total, step)

            risk = 0.0
            tag_union: set[str] = set()

            for index in indices:
                frame_path = str(frames[index])
                nsfw_score = model_manager.predict_nsfw(frame_path)
                risk = max(risk, float(nsfw_score))
                tag_union.update(_collect_ddb_tags(frame_path))
                if risk >= 1.0:
                    break

            return {
                "risk": round(risk, 3),
                "tags": sorted(tag_union)[:200],
                "frameCount": total,
            }
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
