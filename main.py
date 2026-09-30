import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes.register import router as register_router
from routes.verify   import router as verify_router

app = FastAPI(
    title="Fade Artifact Verification Server",
    description=(
        "Public verification server for Fade-exported content.\n\n"
        "Verifies videos, images, and PDFs via 3-layer hash comparison:\n"
        "1. SHA-256 exact match\n"
        "2. Perceptual hash (survives platform re-encode)\n"
        "3. Invisible DWT-DCT watermark extraction"
    ),
    version="1.0.0",
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


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "Fade Verification Server"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
