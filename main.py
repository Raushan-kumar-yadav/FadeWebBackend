import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes.register import router as register_router
from routes.verify import router as verify_router
from routes.blockchain import router as blockchain_router
from routes.blockchain import set_anchor_service
from blockchain.anchor import AnchorService
from blockchain.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Fade Artifact Verification Server",
    description=(
        "Public verification server for Fade-exported content.\n\n"
        "Verifies videos, images, and PDFs via 3-layer hash comparison:\n"
        "1. SHA-256 exact match\n"
        "2. Perceptual hash (survives platform re-encode)\n"
        "3. Invisible DWT-DCT watermark extraction\n\n"
        "**Blockchain:** Artifact hashes are batched into a Merkle tree and "
        "anchored to Polygon Amoy Testnet every 60 seconds."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(register_router)
app.include_router(verify_router)
app.include_router(blockchain_router)


@app.on_event("startup")
def startup():
    # Add bundled FFmpeg to PATH so videohash/cv2 works on Render
    try:
        import imageio_ffmpeg
        import os
        os.environ["PATH"] += os.pathsep + os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as e:
        print("Failed to add imageio_ffmpeg to PATH:", e)
        
    init_db()

    # Initialise blockchain anchor service  
    anchor_svc = AnchorService()
    set_anchor_service(anchor_svc)
    start_scheduler(anchor_svc)


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "Fade Verification Server", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

