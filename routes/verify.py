import os
import time
from urllib.parse import unquote
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from integrity.downloader import download_to_temp
from integrity.verifier   import verify_file

router = APIRouter()


@router.get(
    "/getVerificationContent/{content_link:path}",
    summary="Verify any content by its public URL"
)
def get_verification_content(content_link: str, request: Request):
    """
    Downloads the content at `content_link` and runs 3-layer verification:

      Layer 1 — SHA-256 exact match
                Works when: the exact original file is available (no re-encoding)

      Layer 2 — Perceptual hash (Hamming distance ≤ 10)
                Works when: video/image was re-encoded by YouTube, TikTok, etc.
                NOT applicable for PDF (returns to SHA-256 only)

      Layer 3 — Invisible watermark extraction (DWT-DCT)
                Works when: video/image was uploaded to a social platform
                The watermark survives H.264/H.265 re-encoding
                NOT applicable for PDF

    Path parameter:
        content_link — full URL-encoded link to the content
                       e.g. /getVerificationContent/https://youtu.be/abc123

    Returns:
        {
          verdict:     AUTHENTIC | AUTHENTIC_REENCODED | AUTHENTIC_PLATFORM_COPY | UNVERIFIED
          method:      sha256 | phash | watermark | null
          artifact_id: string | null
          detail:      human-readable explanation
          artifact:    full artifact record (if matched)
          verified_at: unix timestamp
        }

    Verdicts explained:
        AUTHENTIC              — Exact byte match. The file was not modified at all.
        AUTHENTIC_REENCODED    — Re-encoded (e.g. YouTube/TikTok), but content is authentic.
        AUTHENTIC_PLATFORM_COPY— Platform copy detected via invisible watermark.
        UNVERIFIED             — Cannot be matched to any registered Fade artifact.
    """
    url = unquote(content_link)
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "content_link must be a full http/https URL")

    tmp_path = None
    kind = "unknown"
    try:
        tmp_path, kind = download_to_temp(url)
        db   = get_db()
        result = verify_file(tmp_path, kind, db)
        db.close()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Failed to download or process content: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    now = int(time.time())
    result["verified_at"] = now
    result["content_url"] = url
    result["content_type_detected"] = kind

    # Log to DB
    try:
        db2 = get_db()
        db2.execute(
            """INSERT INTO verify_log
               (content_url, content_type, verdict, artifact_id, method, hamming, verified_at, ip)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                url, kind, result["verdict"],
                result.get("artifact_id"),
                result.get("method"),
                result.get("hamming"),
                now,
                request.client.host if request.client else None,
            ),
        )
        db2.commit()
        db2.close()
    except Exception:
        pass

    return result


@router.get("/artifacts", summary="List all registered artifacts (admin)")
def list_artifacts(x_api_key: str = None):
    db = get_db()
    rows = db.execute(
        "SELECT id, filename, content_type, sha256, registered_at, registered_by, ledger_tx "
        "FROM artifacts ORDER BY registered_at DESC"
    ).fetchall()
    db.close()
    return {"artifacts": [dict(r) for r in rows]}


@router.get("/verifyLog", summary="Recent verification attempts")
def verify_log(limit: int = 50):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM verify_log ORDER BY verified_at DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return {"log": [dict(r) for r in rows]}
