import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
PHASH_THRESHOLD = 10

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def phash_distance(hex1: str, hex2: str) -> int:
    try:
        return bin(int(hex1, 16) ^ int(hex2, 16)).count("1")
    except (ValueError, TypeError):
        return 64

def compute_video_phash(path: str) -> str | None:
    try:
        from videohash import VideoHash
        return VideoHash(path=path).hash_hex
    except ImportError:
        logger.warning("videohash not installed: pip install videohash")
        return None
    except Exception as e:
        logger.warning("compute_video_phash failed: %s", e)
        return None

def compute_image_phash(path: str) -> str | None:
    try:
        import imagehash
        from PIL import Image
        img = Image.open(path).convert("RGB")
        h = imagehash.phash(img)
        return format(int(str(h), 16), "016x")
    except ImportError:
        logger.warning("imagehash/Pillow not installed")
        return None
    except Exception as e:
        logger.warning("compute_image_phash failed: %s", e)
        return None

def compute_phash(path: str, kind: str) -> str | None:
    if kind == "video":
        return compute_video_phash(path)
    if kind == "image":
        return compute_image_phash(path)
    return None  # PDF: SHA-256 only
