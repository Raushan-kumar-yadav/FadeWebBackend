import hashlib
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

CHUNK = 1024 * 1024  # 1 MB
MAX_BYTES = 500 * 1024 * 1024  # 500 MB safety cap

VIDEO_EXTS  = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".ts"}
IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
PDF_EXTS    = {".pdf"}

SOCIAL_DOMAINS = {
    "youtube.com", "youtu.be", "instagram.com", "twitter.com", "x.com", 
    "tiktok.com", "facebook.com", "vimeo.com", "twitch.tv", "reddit.com"
}

def _is_social_media(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain == d or domain.endswith("." + d) for d in SOCIAL_DOMAINS)
    except Exception:
        return False

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

def _download_with_ytdlp(url: str) -> tuple[str, str]:
    import yt_dlp
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tmp.close()

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': tmp.name,
        'max_filesize': MAX_BYTES,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    
    try:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if os.path.exists(tmp.name):
            return tmp.name, "video"
            
        # In case yt-dlp appended an extension to our tmp.name
        dirname = os.path.dirname(tmp.name)
        basename = os.path.basename(tmp.name)
        for f in os.listdir(dirname):
            if f.startswith(basename) and f != basename:
                found = os.path.join(dirname, f)
                shutil.move(found, tmp.name)
                return tmp.name, "video"
                
        raise FileNotFoundError("yt-dlp output file not found")
        
    except Exception as e:
        if os.path.exists(tmp.name):
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        raise ValueError(f"Failed to extract media from social URL: {e}")

def download_to_temp(url: str) -> tuple[str, str]:
    """
    Download file from URL to a temp file.
    Uses yt-dlp for social media URLs, and httpx for direct links.
    Returns (tmp_path, content_type).
    Caller is responsible for deleting the temp file.
    """
    if _is_social_media(url):
        try:
            return _download_with_ytdlp(url)
        except Exception as e:
            print(f"[Warning] yt-dlp failed, falling back to direct download: {e}")
            # Fall through to httpx if yt-dlp fails
            pass

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
