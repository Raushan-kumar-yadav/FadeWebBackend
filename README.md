# Fade Artifact Verification Server

A standalone FastAPI server that verifies the authenticity of videos, images, and PDFs
exported from **Fade** using 3-layer cryptographic fingerprinting.

> The actual media file is **never stored on this server**.
> Only cryptographic hashes (64-char hex strings) are stored.

---

## How It Works

### Registration (Fade side)

When a user exports content in Fade and ticks "Register for Integrity Verification":

1. **Fade** computes 3 fingerprints locally:
   - `sha256`  — exact byte hash of the exported file
   - `phash`   — perceptual hash (survives platform re-encoding)
   - `wm_id`   — invisible watermark embedded into pixels (video/image only)

2. **Fade** calls `POST /registerContent` on this server, sending only the hashes (never the file).

3. This server stores the proof bundle in SQLite.

### Verification (anyone)

Anyone with the public URL of a video/image/PDF calls:

```
GET /getVerificationContent/{encoded_url}
```

The server:
1. **Downloads** the file from the URL (max 500 MB)
2. **Re-computes** the 3 fingerprints from the downloaded file
3. **Compares** against all registered artifacts:

```
Downloaded file
     │
     ├─ Layer 1: SHA-256 exact match?
     │           YES → AUTHENTIC (exact original)
     │
     ├─ Layer 2: Perceptual hash Hamming distance ≤ 10?
     │           YES → AUTHENTIC_REENCODED (re-encoded by platform)
     │
     └─ Layer 3: Watermark extraction matches wm_id?
                 YES → AUTHENTIC_PLATFORM_COPY
                 NO  → UNVERIFIED
```

### Why 3 Layers?

| Scenario | SHA-256 | Perceptual Hash | Watermark |
|----------|:-------:|:---------------:|:---------:|
| Exact original file | ✅ | ✅ | ✅ |
| Downloaded from YouTube (re-encoded) | ❌ | ✅ | ✅ |
| Downloaded from Instagram (heavy compress) | ❌ | ✅ | ⚠️ |
| File edited/trimmed | ❌ | ❌ | ✅ (if WM frames kept) |
| Screenshot of video | ❌ | ❌ | ❌ |

---

## Project Structure

```
WebHostVerification/
├── main.py                  FastAPI app entry point
├── database.py              SQLite schema + connection
├── requirements.txt
├── .env.example             Environment variable template
│
├── routes/
│   ├── register.py          POST /registerContent
│   └── verify.py            GET  /getVerificationContent/{link}
│                            GET  /artifacts
│                            GET  /verifyLog
│
└── integrity/
    ├── downloader.py        Download video/image/pdf from URL
    ├── hasher.py            SHA-256 + perceptual hash (video & image)
    ├── watermark.py         DWT-DCT watermark extraction
    └── verifier.py          3-layer verification orchestrator
```

---

## SQLite Schema

```sql
-- Registered artifact proof bundles (hashes only, no files)
CREATE TABLE artifacts (
    id              TEXT PRIMARY KEY,        -- artifact_id from Fade
    sha256          TEXT NOT NULL,           -- SHA-256 of original export
    phash           TEXT,                    -- perceptual hash hex (video/image)
    wm_id           TEXT,                    -- watermark ID (8 hex chars)
    merkle_proof    TEXT,                    -- JSON array (Merkle proof path)
    merkle_root     TEXT,                    -- Merkle root (anchored on ledger)
    ledger_tx       TEXT,                    -- Blockchain TX hash (if EVM mode)
    filename        TEXT,                    -- original filename
    content_type    TEXT,                    -- video | image | pdf
    size_bytes      INTEGER,
    registered_at   INTEGER NOT NULL,        -- Unix timestamp
    registered_by   TEXT NOT NULL            -- API key owner
);

-- API keys for registration (verification is public/keyless)
CREATE TABLE api_keys (
    key         TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1
);

-- Verification attempt log
CREATE TABLE verify_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_url     TEXT NOT NULL,           -- URL that was verified
    content_type    TEXT,                    -- detected type
    verdict         TEXT NOT NULL,           -- AUTHENTIC | AUTHENTIC_REENCODED | ...
    artifact_id     TEXT,                    -- matched artifact (if any)
    method          TEXT,                    -- sha256 | phash | watermark | null
    hamming         INTEGER,                 -- Hamming distance (phash only)
    verified_at     INTEGER NOT NULL,
    ip              TEXT
);
```

---

## API Reference

### `POST /registerContent`

Register a Fade artifact proof bundle.

**Authentication:** `X-API-Key: <key>` header required.

**Request body (JSON):**
```json
{
  "artifact_id":  "a1b2c3d4e5f60001",
  "sha256":       "abc123def456...",
  "phash":        "f0e1d2c3b4a59687",
  "wm_id":        "a1b2c3d4",
  "merkle_proof": ["hash1", "hash2", "..."],
  "merkle_root":  "deadbeef...",
  "ledger_tx":    "0xabc123...",
  "filename":     "promo_video.mp4",
  "content_type": "video",
  "size_bytes":   104857600
}
```

**Response (201):**
```json
{
  "ok": true,
  "artifact_id": "a1b2c3d4e5f60001",
  "registered_at": 1727690400
}
```

**Error codes:**
- `401` — Invalid or missing API key
- `409` — Artifact already registered

---

### `GET /getVerificationContent/{content_link}`

Verify any publicly accessible video, image, or PDF by its URL.

**Authentication:** None (public endpoint).

**Path parameter:**
```
content_link — full URL to the content (URL-encoded)

Example:
GET /getVerificationContent/https%3A%2F%2Fexample.com%2Fvideo.mp4
```

**What happens internally:**
1. Server downloads the file from the URL (streams up to 500 MB)
2. Detects type: `video` / `image` / `pdf` from extension + Content-Type header
3. Runs 3-layer verification:
   - **SHA-256:** `hashlib.sha256()` streaming read
   - **Perceptual hash:** `videohash.VideoHash` (video) or `imagehash.phash` (image)
   - **Watermark:** `imwatermark.WatermarkDecoder` with majority vote across 12 sampled frames
4. Returns verdict + logs attempt to DB

**Response (200):**
```json
{
  "verdict":               "AUTHENTIC_REENCODED",
  "method":                "phash",
  "artifact_id":           "a1b2c3d4e5f60001",
  "detail":                "Perceptual fingerprint matched (4/64 bits differ). Content is authentic but was re-encoded by a platform.",
  "hamming":               4,
  "content_url":           "https://youtu.be/...",
  "content_type_detected": "video",
  "verified_at":           1727700000,
  "artifact": {
    "id":           "a1b2c3d4e5f60001",
    "sha256":       "abc123...",
    "phash":        "f0e1d2c3b4a59687",
    "wm_id":        "a1b2c3d4",
    "filename":     "promo_video.mp4",
    "content_type": "video",
    "size_bytes":   104857600,
    "registered_at":1727690400,
    "ledger_tx":    "0xabc123...",
    "merkle_root":  "deadbeef..."
  }
}
```

**Verdict meanings:**
| Verdict | Meaning |
|---------|---------|
| `AUTHENTIC` | Exact byte match — file is the unmodified original |
| `AUTHENTIC_REENCODED` | Perceptual match — re-encoded by YouTube/TikTok etc., but content is authentic |
| `AUTHENTIC_PLATFORM_COPY` | Watermark found — invisible ID extracted and matched |
| `UNVERIFIED` | No match in any layer — file not registered or heavily modified |

**Error codes:**
- `400` — Invalid URL or file too large (>500 MB)
- `502` — Could not download the file (network error, 404, etc.)

---

### `GET /artifacts`

List all registered artifacts.

**Response:**
```json
{
  "artifacts": [
    {
      "id": "...",
      "filename": "promo.mp4",
      "content_type": "video",
      "sha256": "abc123...",
      "registered_at": 1727690400,
      "registered_by": "team-fade",
      "ledger_tx": "0x..."
    }
  ]
}
```

---

### `GET /verifyLog?limit=50`

Recent verification attempts log.

---

### `GET /health`

```json
{ "status": "ok", "service": "Fade Verification Server" }
```

---

## Setup and Running

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> FFmpeg must be on PATH for `videohash` to work with video files.
> Install: https://ffmpeg.org/download.html

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env:
# DEFAULT_API_KEY=your-secret-api-key-here
# PORT=8080
```

### 3. Run

```bash
# Development (auto-reload)
python main.py

# Production
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 2
```

### 4. Interactive API docs

Open `http://localhost:8080/docs` for Swagger UI.

---

## Integration with Fade

After Fade registers a content locally, it auto-calls this server:

```python
# Fade backend/integrity/service.py (add this after seal())
import requests, os

server = os.getenv("VERIFICATION_SERVER_URL", "http://localhost:8080")
api_key = os.getenv("VERIFICATION_SERVER_KEY", "fade-dev-key-changeme")

requests.post(f"{server}/registerContent",
    headers={"X-API-Key": api_key},
    json={
        "artifact_id":  artifact_id,
        "sha256":        sha256,
        "phash":         phash,
        "wm_id":         wm_id,
        "merkle_root":   batch["root"],
        "ledger_tx":     batch.get("tx"),
        "filename":      filename,
        "content_type":  "video",
    }
)
```

---

## Deployment

Host this on any server with Python 3.11+:

- **Railway / Render / Fly.io** — free tier works for SIH demo
- **VPS** — `gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker`
- **Docker** — `docker build -t fade-verify . && docker run -p 8080:8080 fade-verify`

---

## Security Notes

- Registration requires an API key (`X-API-Key` header) — only Fade team can register
- Verification is **public** — anyone can verify a URL without authentication
- Files are downloaded to a temp directory and deleted immediately after verification
- No media content is ever stored on this server
- The default API key (`fade-dev-key-changeme`) must be changed before deployment

---

## Built With

| Library | Purpose |
|---------|---------|
| FastAPI | Web framework |
| httpx | Async HTTP client (file download) |
| videohash | Perceptual video hashing |
| imagehash + Pillow | Perceptual image hashing |
| invisible-watermark | DWT-DCT watermark extraction |
| OpenCV | Video frame processing |
| SQLite3 | Artifact + log storage |
