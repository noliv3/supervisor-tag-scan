#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

BASE_URL = os.getenv("LEGACY_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}")
        sys.exit(1)


def _assert_json(response: requests.Response, expected: dict, label: str) -> None:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        _assert(False, f"{label} expected JSON, got decode error: {exc}")
        return
    _assert(payload == expected, f"{label} expected {expected}, got {payload}")


def _make_png_bytes() -> bytes:
    image = Image.new("RGB", (64, 64), color=(120, 10, 10))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _make_gif_bytes() -> bytes:
    frames = [
        Image.new("RGB", (64, 64), color=(255, 0, 0)),
        Image.new("RGB", (64, 64), color=(0, 255, 0)),
        Image.new("RGB", (64, 64), color=(0, 0, 255)),
    ]
    buf = BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


def main() -> int:
    print(f"BASE_URL={BASE_URL}")

    print("A) GET /token")
    response = requests.get(f"{BASE_URL}/token", params={"email": "test@example.com"}, timeout=10)
    _assert(response.status_code == 200, f"/token status {response.status_code}")
    content_type = response.headers.get("content-type", "")
    _assert(content_type.startswith("text/plain"), f"/token content-type {content_type}")
    token = response.text.strip()
    _assert(len(token) >= 16, f"/token length {len(token)}")

    print("B) GET /stats without auth")
    response = requests.get(f"{BASE_URL}/stats", timeout=10)
    _assert(response.status_code == 403, f"/stats status {response.status_code}")
    _assert_json(response, {"error": "forbidden"}, "/stats error")

    print("C) POST /check JSON body")
    response = requests.post(f"{BASE_URL}/check", json={"foo": "bar"}, timeout=10)
    _assert(response.status_code == 403, f"/check JSON status {response.status_code}")
    _assert_json(response, {"error": "invalid content-type"}, "/check JSON error")

    print("D) POST /check multipart without image")
    response = requests.post(
        f"{BASE_URL}/check",
        files={"dummy": ("dummy.txt", b"x", "text/plain")},
        headers={"Authorization": token},
        timeout=10,
    )
    _assert(response.status_code == 400, f"/check no image status {response.status_code}")
    _assert_json(response, {"error": "image missing"}, "/check no image error")

    print("E) POST /check valid image")
    png_bytes = _make_png_bytes()
    response = requests.post(
        f"{BASE_URL}/check",
        files={"image": ("t.png", png_bytes, "image/png")},
        headers={"Authorization": token},
        timeout=30,
    )
    _assert(response.status_code == 200, f"/check valid status {response.status_code}")
    payload = response.json()
    modules = payload.get("modules", {})
    for key in (
        "nsfw_scanner",
        "tagging",
        "deepdanbooru_tags",
        "statistics",
        "image_storage",
    ):
        _assert(key in modules and isinstance(modules[key], dict), f"/check modules.{key} missing")
    image_storage = modules.get("image_storage", {})
    _assert(isinstance(image_storage.get("path"), str), "/check image_storage.path missing")
    _assert(isinstance(image_storage.get("metadata"), dict), "/check image_storage.metadata missing")

    print("F) GET /stats with auth")
    response = requests.get(f"{BASE_URL}/stats", headers={"Authorization": token}, timeout=10)
    _assert(response.status_code == 200, f"/stats auth status {response.status_code}")
    payload = response.json()
    _assert(isinstance(payload.get("count"), int), "/stats count missing")
    _assert(isinstance(payload.get("top_tags"), list), "/stats top_tags missing")

    print("G) POST /batch JSON body")
    response = requests.post(f"{BASE_URL}/batch", json={"foo": "bar"}, timeout=10)
    _assert(response.status_code == 403, f"/batch JSON status {response.status_code}")
    _assert_json(response, {"error": "invalid content-type"}, "/batch JSON error")

    print("H) POST /batch multipart without file")
    response = requests.post(
        f"{BASE_URL}/batch",
        files={"dummy": ("dummy.txt", b"x", "text/plain")},
        headers={"Authorization": token},
        timeout=10,
    )
    _assert(response.status_code == 400, f"/batch no file status {response.status_code}")
    _assert_json(response, {"error": "file missing"}, "/batch no file error")

    print("I) POST /batch valid GIF")
    gif_bytes = _make_gif_bytes()
    response = requests.post(
        f"{BASE_URL}/batch",
        files={"file": ("t.gif", gif_bytes, "image/gif")},
        headers={"Authorization": token},
        timeout=60,
    )
    if response.status_code == 500:
        error_text = ""
        try:
            error_text = response.json().get("error", "")
        except json.JSONDecodeError:
            error_text = response.text
        if "ffmpeg" in error_text or "No such file" in error_text or "[Errno 2]" in error_text:
            print("SKIP batch (ffmpeg missing)")
        else:
            _assert(False, f"/batch unexpected 500: {error_text}")
    else:
        _assert(response.status_code == 200, f"/batch status {response.status_code}")
        payload = response.json()
        _assert(isinstance(payload.get("risk"), float), "/batch risk missing")
        _assert(isinstance(payload.get("tags"), list), "/batch tags missing")
        _assert(isinstance(payload.get("frameCount"), int), "/batch frameCount missing")

    host = urlparse(BASE_URL).hostname or ""
    force_scan = os.getenv("FORCE_SCAN_IMAGE_TEST") == "1"
    if force_scan or host in {"127.0.0.1", "localhost"}:
        print("J) POST /scan_image")
        temp_path = None
        try:
            png_bytes = _make_png_bytes()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as handle:
                handle.write(png_bytes)
                handle.flush()
                temp_path = handle.name
            response = requests.post(
                f"{BASE_URL}/scan_image",
                json={
                    "file_path": str(Path(temp_path).resolve()),
                    "modules": ["basic", "nsfw", "tags"],
                    "token": token,
                },
                timeout=60,
            )
            _assert(response.status_code == 200, f"/scan_image status {response.status_code}")
            payload = response.json()
            for key in ("file_path", "statistics", "nsfw_score", "tags"):
                _assert(key in payload, f"/scan_image missing {key}")
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
    else:
        print("SKIP /scan_image (non-local base URL)")

    print("Smoke test completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
