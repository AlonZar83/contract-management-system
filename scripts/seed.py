from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from database.database import insert_contract, init_db, upsert_tenant, upsert_user


def seed() -> None:
    init_db()

    tenant_id = 101
    upsert_tenant(tenant_id=tenant_id, name="בדיקה 1")
    user_id = upsert_user(
        tenant_id=tenant_id,
        full_name="משתמש בדיקה",
        email="test@contract.local",
        password="123456",
    )

    seed_chat_id = int(os.getenv("SEED_TELEGRAM_CHAT_ID", "123456789"))

    insert_contract(
        tenant_id=tenant_id,
        user_id=user_id,
        title="דירת הדגמה",
        end_date=date.today() + timedelta(days=3),
        alert_days=30,
        telegram_chat_id=seed_chat_id,
        status="active",
    )

    print("Seeding completed.")
    print("Tenant: בדיקה 1 (ID: 101)")
    print("User: test@contract.local / 123456")
    print("Contract: דירת הדגמה (expires in 3 days)")


if __name__ == "__main__":
    seed()
