from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from core.legacy_pipeline import (
    run_deepdanbooru_from_path,
    run_nsfw_from_path,
    run_tagging_from_path,
)

GIF_STEP = 5
VIDEO_STEP = 20
MAX_OUT_FRAMES = 60


def _resolve_ffmpeg_bin() -> str:
    env_bin = os.getenv("FFMPEG_BIN")
    if env_bin:
        return env_bin
    repo_root = Path(__file__).resolve().parent.parent
    local_bin = repo_root / "ffmpeg" / "bin" / "ffmpeg"
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
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-vframes",
        str(MAX_OUT_FRAMES),
        output_pattern,
    ]
    subprocess.run(command, check=True)
    return sorted(Path(output_dir).glob("frame_*.png"))


async def scan_batch(buf: bytes, mime: str = "") -> dict:
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

            max_risk = 0.0
            tag_union: set[str] = set()

            for index in indices:
                frame_path = str(frames[index])
                nsfw_res = run_nsfw_from_path(frame_path)
                tag_res = run_tagging_from_path(frame_path)
                ddb_res = run_deepdanbooru_from_path(frame_path)
                base = max(
                    float(nsfw_res.get("hentai", 0)),
                    float(nsfw_res.get("porn", 0)),
                    float(nsfw_res.get("sexy", 0)),
                )
                max_risk = max(max_risk, base)
                for item in tag_res.get("tags", []) if isinstance(tag_res, dict) else []:
                    label = item.get("label") if isinstance(item, dict) else None
                    if label:
                        tag_union.add(str(label))
                for item in ddb_res.get("tags", []) if isinstance(ddb_res, dict) else []:
                    label = item.get("label") if isinstance(item, dict) else None
                    if label:
                        tag_union.add(str(label))
                if max_risk >= 1.0:
                    break

            return {
                "risk": round(max_risk, 3),
                "tags": sorted(tag_union)[:200],
                "frameCount": total,
            }
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
