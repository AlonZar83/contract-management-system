from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database.database import (
    authenticate_user,
    delete_contract_for_tenant,
    get_contracts_for_tenant,
    init_db,
    insert_contract,
)

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

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


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
    telegram_chat_id: int
    manager_group_chat_id: int | None = None
    alert_target: str = Field(default="direct")
    extra_chat_ids: list[int] = Field(default_factory=list)


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
async def create_contract(
    tenant_id: int = Form(...),
    user_id: int | None = Form(None),
    title: str = Form(...),
    start_date: str | None = Form(None),
    end_date: str = Form(...),
    alert_days: int = Form(30),
    telegram_chat_id: int = Form(...),
    manager_group_chat_id: int | None = Form(None),
    alert_target: str = Form("direct"),
    contract_file: Optional[UploadFile] = None,
) -> dict[str, object]:
    if alert_target not in {"direct", "managers", "both"}:
        raise HTTPException(status_code=400, detail="alert_target must be one of: direct, managers, both")

    try:
        parsed_end_date = date.fromisoformat(end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="end_date must be ISO format YYYY-MM-DD") from exc

    parsed_start_date: date | None = None
    if start_date:
        try:
            parsed_start_date = date.fromisoformat(start_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="start_date must be ISO format YYYY-MM-DD") from exc

    file_link: str | None = None
    if contract_file and contract_file.filename:
        extension = Path(contract_file.filename).suffix.lower()
        allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
        if extension not in allowed_extensions:
            raise HTTPException(status_code=400, detail="Only PDF/JPG/JPEG/PNG files are allowed")

        unique_filename = f"{uuid4().hex}{extension}"
        destination = UPLOADS_DIR / unique_filename
        content = await contract_file.read()
        destination.write_bytes(content)
        file_link = f"/uploads/{unique_filename}"

    contract_id = insert_contract(
        tenant_id=tenant_id,
        user_id=user_id,
        title=title,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        alert_days=alert_days,
        file_link=file_link,
        telegram_chat_id=telegram_chat_id,
        manager_group_chat_id=manager_group_chat_id,
        alert_target=alert_target,
        extra_chat_ids=[],
        status="active",
    )
    return {"success": True, "contract_id": contract_id}


@app.get("/api/contracts")
def list_contracts(tenant_id: int, search: str | None = None) -> dict[str, object]:
    contracts = get_contracts_for_tenant(tenant_id=tenant_id, search=search)
    return {"success": True, "contracts": contracts}


@app.delete("/api/contracts/{contract_id}")
def delete_contract(contract_id: int, tenant_id: int) -> dict[str, object]:
    deleted = delete_contract_for_tenant(contract_id=contract_id, tenant_id=tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contract not found for this tenant")
    return {"success": True}
