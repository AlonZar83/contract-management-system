from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database.database import authenticate_user, init_db, insert_contract

BASE_DIR = Path(__file__).resolve().parents[1]
SHARED_ENV_FILE = BASE_DIR / "shared" / ".env"

# Load variables from shared/.env if present. keep default load for shell-injected vars too.
load_dotenv(dotenv_path=SHARED_ENV_FILE)
load_dotenv()


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title=os.getenv("APP_NAME", "Contract Management System"))
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class ContractCreateRequest(BaseModel):
    tenant_id: int
    user_id: int | None = None
    title: str = Field(min_length=1)
    start_date: date | None = None
    end_date: date
    alert_days: int = Field(default=30, ge=0, le=365)
    file_link: str | None = None
    telegram_chat_id: int | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": os.getenv("APP_NAME", "Contract Management System"),
        "env": os.getenv("APP_ENV", "development"),
    }


@app.post("/api/login")
def login(payload: LoginRequest) -> dict[str, object]:
    user = authenticate_user(email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "success": True,
        "user": user,
    }


@app.post("/api/contracts")
def create_contract(payload: ContractCreateRequest) -> dict[str, object]:
    contract_id = insert_contract(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        title=payload.title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        alert_days=payload.alert_days,
        file_link=payload.file_link,
        telegram_chat_id=payload.telegram_chat_id,
        status="active",
    )
    return {"success": True, "contract_id": contract_id}
