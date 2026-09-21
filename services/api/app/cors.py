"""Explicit CORS configuration for the deployed buyer frontend."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.operational import configured_origins


def configure_cors(app: FastAPI) -> list[str]:
    """Attach CORS using the comma-separated CORS_ORIGINS allow-list."""
    origins = configured_origins(os.getenv("CORS_ORIGINS"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Admin-Token", "X-Actor"],
    )
    return origins
