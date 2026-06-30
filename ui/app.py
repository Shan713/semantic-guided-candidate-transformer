"""FastAPI application factory for the SGCT visualization layer.

This module creates the FastAPI app, mounts static files, and registers routes.
No business logic lives here — the UI is purely a presentation layer that
invokes the existing PipelineOrchestrator.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ui.routes import router

UI_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Semantic Guided Candidate Transformer",
        description="Deterministic Multi-Source Candidate Fusion — Visualization Layer",
        version="0.1.0",
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)

    return app


app = create_app()
