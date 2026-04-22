from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parents[1]
SHARED_ENV_FILE = BASE_DIR / "shared" / ".env"

# Load variables from shared/.env if present. keep default load for shell-injected vars too.
load_dotenv(dotenv_path=SHARED_ENV_FILE)
load_dotenv()


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title=os.getenv("APP_NAME", "Contract Management System"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": os.getenv("APP_NAME", "Contract Management System"),
        "env": os.getenv("APP_ENV", "development"),
    }
