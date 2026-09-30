import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

CHUNK = 1024 * 1024  # 1 MB
MAX_BYTES = 500 * 1024 * 1024  # 500 MB safety cap

VIDEO_EXTS  = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".ts"}
IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
PDF_EXTS    = {".pdf"}

def _detect_type(url: str, content_type_header: str | None) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    ct = (content_type_header or "").lower()
    if "video" in ct:
        return "video"
    if "image" in ct:
        return "image"
    if "pdf" in ct:
        return "pdf"
    return "unknown"

def _ext_for(kind: str) -> str:
    return {"video": ".mp4", "image": ".png", "pdf": ".pdf"}.get(kind, ".bin")

def download_to_temp(url: str) -> tuple[str, str]:
    """
    Download file from URL to a temp file.
    Returns (tmp_path, content_type).
    Caller is responsible for deleting the temp file.
    """
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            ct_header = resp.headers.get("content-type")
            kind = _detect_type(url, ct_header)
            suffix = _ext_for(kind)

            total = 0
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            try:
                for chunk in resp.iter_bytes(chunk_size=CHUNK):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        tmp.close()
                        os.unlink(tmp.name)
                        raise ValueError(f"File too large (>{MAX_BYTES // 1024 // 1024} MB)")
                    tmp.write(chunk)
                tmp.close()
                return tmp.name, kind
            except Exception:
                try:
                    tmp.close()
                    os.unlink(tmp.name)
                except OSError:
                    pass
                raise
