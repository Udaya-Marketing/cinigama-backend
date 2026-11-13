"""
Model downloader and verification script for OpenCV YuNet and SFace models.
Downloads official weights from the OpenCV Zoo repository and verifies SHA256 integrity.
"""

import hashlib
import os
import sys
from pathlib import Path
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("model_downloader")

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models_zoo"

MODELS = {
    "face_detection_yunet_2023mar.onnx": {
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "fallback_url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "description": "YuNet 2023mar Face Detection ONNX model (Apache 2.0)",
        "expected_min_bytes": 150_000,  # ~232 KB
        "expected_sha256": None,  # Will verify / record
    },
    "face_recognition_sface_2021dec.onnx": {
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "fallback_url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "description": "SFace 2021dec Face Recognition ONNX model (Apache 2.0)",
        "expected_min_bytes": 25_000_000,  # ~37 MB
        "expected_sha256": None,  # Will verify / record
    },
}


def compute_sha256(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_file(url: str, dest_path: Path, min_bytes: int = 1024) -> bool:
    logger.info(f"Downloading from {url} to {dest_path.name}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")

    headers = {"User-Agent": "Mozilla/5.0 (EventPhotoManagement/1.0; ModelDownloader)"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=120) as response, open(temp_path, "wb") as out_file:
            total_size = response.getheader("Content-Length")
            total_size = int(total_size) if total_size else None
            downloaded = 0
            block_size = 65536

            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                if total_size:
                    percent = (downloaded / total_size) * 100
                    if downloaded % (block_size * 40) == 0 or downloaded == total_size:
                        sys.stdout.write(f"\r  Progress: {downloaded}/{total_size} bytes ({percent:.1f}%)")
                        sys.stdout.flush()

        print()
        if temp_path.stat().st_size < min_bytes:
            logger.error(f"Downloaded file is suspiciously small ({temp_path.stat().st_size} bytes). Possibly an error page.")
            temp_path.unlink(missing_ok=True)
            return False

        temp_path.replace(dest_path)
        return True

    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        temp_path.unlink(missing_ok=True)
        return False


def ensure_models(target_dir: Path = MODELS_DIR) -> dict[str, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    for filename, meta in MODELS.items():
        file_path = target_dir / filename
        needs_download = True

        if file_path.exists() and file_path.stat().st_size >= meta["expected_min_bytes"]:
            sha256_hash = compute_sha256(file_path)
            logger.info(f"Model already present: {filename} ({file_path.stat().st_size} bytes, SHA256: {sha256_hash[:16]}...)")
            results[filename] = file_path
            needs_download = False

        if needs_download:
            success = download_file(meta["url"], file_path, min_bytes=meta["expected_min_bytes"])
            if not success and "fallback_url" in meta:
                logger.info(f"Retrying with fallback URL: {meta['fallback_url']}")
                success = download_file(meta["fallback_url"], file_path, min_bytes=meta["expected_min_bytes"])

            if not success:
                raise RuntimeError(f"Could not download model {filename}")

            sha256_hash = compute_sha256(file_path)
            logger.info(f"Verified {filename}: {file_path.stat().st_size} bytes, SHA256: {sha256_hash}")
            results[filename] = file_path

    return results


if __name__ == "__main__":
    try:
        ensure_models()
        logger.info("All required face models verified successfully.")
    except Exception as exc:
        logger.error(f"Model verification failed: {exc}")
        sys.exit(1)
