from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from telegram import Bot

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "shared" / ".env")

from database.database import get_contracts_needing_alert_today, init_db

logger = logging.getLogger(__name__)


def build_contract_alert_message(contract_row) -> str:
    return (
        f"🔔 התראת חוזה\n"
        f"לקוח: {contract_row['tenant_name']}\n"
        f"חוזה: {contract_row['title']}\n"
        f"תאריך סיום: {contract_row['end_date']}\n"
        f"נותרו: {contract_row['days_remaining']} ימים"
    )


async def run_scan_once() -> dict[str, int]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    init_db()
    bot = Bot(token=token)
    due_contracts = get_contracts_needing_alert_today()

    sent_count = 0
    fail_count = 0

    for contract in due_contracts:
        message = build_contract_alert_message(contract)
        chat_id = contract["telegram_chat_id"]
        if chat_id is None:
            logger.info("Contract %s has no telegram_chat_id configured", contract["id"])
            continue

        try:
            await bot.send_message(chat_id=int(chat_id), text=message)
            sent_count += 1
            logger.info(
                "התראה עבור חוזה %s של לקוח %s נשלחה לצ'אט %s",
                contract["title"],
                contract["tenant_id"],
                chat_id,
            )
        except Exception as exc:
            fail_count += 1
            logger.error(
                "Alert failed: contract=%s tenant=%s chat_id=%s error=%s",
                contract["id"],
                contract["tenant_id"],
                chat_id,
                exc,
            )

    logger.info("Scan completed. sent=%s failed=%s contracts=%s", sent_count, fail_count, len(due_contracts))
    return {"sent": sent_count, "failed": fail_count, "contracts": len(due_contracts)}


def _seconds_until_next_run(hour: int = 8, minute: int = 0) -> float:
    now = datetime.now()
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= next_run:
        next_run = next_run + timedelta(days=1)
    return (next_run - now).total_seconds()


async def run_daily_scheduler(hour: int = 8, minute: int = 0) -> None:
    logger.info("Daily scheduler started. run_time=%02d:%02d", hour, minute)
    while True:
        wait_seconds = _seconds_until_next_run(hour=hour, minute=minute)
        logger.info("Next scan in %.0f seconds", wait_seconds)
        await asyncio.sleep(wait_seconds)
        try:
            await run_scan_once()
        except Exception as exc:
            logger.exception("Daily scan failed: %s", exc)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Contract reminder scheduler")
    parser.add_argument("--once", action="store_true", help="Run one scan immediately and exit")
    parser.add_argument("--hour", type=int, default=8, help="Daily run hour (0-23)")
    parser.add_argument("--minute", type=int, default=0, help="Daily run minute (0-59)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.once:
        result = asyncio.run(run_scan_once())
        print(result)
        return

    asyncio.run(run_daily_scheduler(hour=args.hour, minute=args.minute))


if __name__ == "__main__":
    main()
