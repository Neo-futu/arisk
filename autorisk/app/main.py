from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router as risk_router
from .config import settings

app = FastAPI(
    title="AutoRisk",
    description="Independent automated risk evaluation service for fund management.",
    version="1.0.0",
)

allow_origins = ["*"] if settings.cors_origins == ["*"] else settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk_router, prefix=settings.api_prefix)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/demo")


@app.get("/demo", include_in_schema=False)
async def demo():
    return FileResponse(static_dir / "demo.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.service_name,
        "workflow_mode": settings.workflow_mode.value,
        "ai_provider": settings.ai_provider,
        "rules_config": settings.rules_path.name,
    }
