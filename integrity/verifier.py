import json
import os
import time
import sqlite3
from integrity.hasher   import sha256_file, compute_phash, phash_distance, PHASH_THRESHOLD
from integrity.watermark import extract_watermark

def verify_file(tmp_path: str, kind: str, db: sqlite3.Connection) -> dict:
    """
    3-layer verification. Called after the file has been downloaded.

    Layer 1: Exact SHA-256
    Layer 2: Perceptual hash (Hamming distance)
    Layer 3: Invisible watermark extraction

    Returns a verdict dict.
    """

    # Layer 1 -- exact SHA-256
    current_sha = sha256_file(tmp_path)
    row = db.execute(
        "SELECT * FROM artifacts WHERE sha256 = ? LIMIT 1", (current_sha,)
    ).fetchone()
    if row:
        return _result("AUTHENTIC", "sha256", row, detail="Exact byte-for-byte match.")

    # Layer 2 -- perceptual hash
    current_phash = compute_phash(tmp_path, kind)
    if current_phash:
        rows = db.execute(
            "SELECT * FROM artifacts WHERE phash IS NOT NULL"
        ).fetchall()
        best, best_d = None, 999
        for r in rows:
            d = phash_distance(current_phash, r["phash"])
            if d < best_d:
                best_d, best = d, r
        if best and best_d <= PHASH_THRESHOLD:
            return _result(
                "AUTHENTIC_REENCODED", "phash", best,
                hamming=best_d,
                detail=f"Perceptual fingerprint matched ({best_d}/64 bits differ). Content is authentic but was re-encoded by a platform."
            )

    # Layer 3 -- watermark
    wm_id = extract_watermark(tmp_path, kind)
    if wm_id:
        row = db.execute(
            "SELECT * FROM artifacts WHERE wm_id = ? LIMIT 1", (wm_id,)
        ).fetchone()
        if row:
            return _result(
                "AUTHENTIC_PLATFORM_COPY", "watermark", row,
                wm_id=wm_id,
                detail="Invisible watermark extracted and matched a registered artifact."
            )

    return {
        "verdict":      "UNVERIFIED",
        "method":       None,
        "artifact_id":  None,
        "detail":       "No matching artifact found by exact hash, perceptual fingerprint, or embedded watermark.",
        "artifact":     None,
    }


def _result(verdict, method, row, *, detail="", hamming=None, wm_id=None) -> dict:
    r = {
        "verdict":      verdict,
        "method":       method,
        "artifact_id":  row["id"],
        "detail":       detail,
        "artifact": {
            "id":           row["id"],
            "sha256":       row["sha256"],
            "phash":        row["phash"],
            "wm_id":        row["wm_id"],
            "filename":     row["filename"],
            "content_type": row["content_type"],
            "size_bytes":   row["size_bytes"],
            "registered_at":row["registered_at"],
            "ledger_tx":    row["ledger_tx"],
            "merkle_root":  row["merkle_root"],
        },
    }
    if hamming is not None:
        r["hamming"] = hamming
    if wm_id is not None:
        r["wm_id_found"] = wm_id
    return r
