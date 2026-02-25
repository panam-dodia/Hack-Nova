import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.api.inspections import router as inspections_router
from app.api.voice import router as voice_router
from app.api.monitoring import router as monitoring_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SafetyAI — OSHA Inspection Platform",
    description="AI-powered construction site safety inspection using Amazon Nova models.",
    version="1.0.0",
)

# ─── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(inspections_router)
app.include_router(voice_router)
app.include_router(monitoring_router)

# ─── Static file serving for uploaded media ──────────────────────────────────
uploads_dir = Path(settings.upload_dir)
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized")
    logger.info(f"Nova Pro model: {settings.nova_pro_model_id}")
    logger.info(f"Nova Lite model: {settings.nova_lite_model_id}")
    logger.info(f"AWS Region: {settings.aws_region}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "SafetyAI"}
