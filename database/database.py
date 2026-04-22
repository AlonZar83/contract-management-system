from __future__ import annotations

import sqlite3
from datetime import date
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "contracts.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if not _table_has_column(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS Tenants (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                password TEXT,
                telegram_chat_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES Tenants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS Contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER,
                title TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT NOT NULL,
                alert_days INTEGER NOT NULL DEFAULT 30,
                file_link TEXT,
                telegram_chat_id INTEGER,
                manager_group_chat_id INTEGER,
                alert_target TEXT NOT NULL DEFAULT 'direct',
                extra_chat_ids TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES Tenants(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_contracts_tenant_id ON Contracts (tenant_id);
            CREATE INDEX IF NOT EXISTS idx_contracts_end_date ON Contracts (end_date);
            """
        )

        # Backward-compatible migration for databases created before new columns were added.
        _ensure_column(conn, "Users", "email", "email TEXT")
        _ensure_column(conn, "Users", "password", "password TEXT")
        _ensure_column(conn, "Contracts", "user_id", "user_id INTEGER")
        _ensure_column(conn, "Contracts", "start_date", "start_date TEXT")
        _ensure_column(conn, "Contracts", "alert_days", "alert_days INTEGER NOT NULL DEFAULT 30")
        _ensure_column(conn, "Contracts", "file_link", "file_link TEXT")
        _ensure_column(conn, "Contracts", "telegram_chat_id", "telegram_chat_id INTEGER")
        _ensure_column(conn, "Contracts", "manager_group_chat_id", "manager_group_chat_id INTEGER")
        _ensure_column(conn, "Contracts", "alert_target", "alert_target TEXT NOT NULL DEFAULT 'direct'")
        _ensure_column(conn, "Contracts", "extra_chat_ids", "extra_chat_ids TEXT")

        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_email ON Users (tenant_id, email)")


def get_expiring_contracts(days_ahead: int = 30, tenant_id: int | None = None) -> list[sqlite3.Row]:
    sql = (
        """
        SELECT
            c.id,
            c.tenant_id,
            t.name AS tenant_name,
            c.title,
            c.end_date,
            CAST(julianday(c.end_date) - julianday('now') AS INTEGER) AS days_remaining
        FROM Contracts c
        JOIN Tenants t ON t.id = c.tenant_id
        WHERE c.status = 'active'
          AND date(c.end_date) <= date('now', '+' || ? || ' day')
          AND date(c.end_date) >= date('now')
        """
    )
    params: list[object] = [days_ahead]
    if tenant_id is not None:
        sql += " AND c.tenant_id = ?"
        params.append(tenant_id)

    sql += " ORDER BY date(c.end_date) ASC"

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return rows


def upsert_tenant(tenant_id: int, name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO Tenants (id, name)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name
            """,
            (tenant_id, name),
        )


def upsert_user(
    tenant_id: int,
    full_name: str,
    email: str,
    password: str,
    telegram_chat_id: int | None = None,
) -> int:
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM Users
            WHERE tenant_id = ? AND email = ?
            """,
            (tenant_id, email),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE Users
                SET full_name = ?, password = ?, telegram_chat_id = COALESCE(?, telegram_chat_id)
                WHERE id = ?
                """,
                (full_name, password, telegram_chat_id, existing["id"]),
            )
            return int(existing["id"])

        cursor = conn.execute(
            """
            INSERT INTO Users (tenant_id, full_name, email, password, telegram_chat_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tenant_id, full_name, email, password, telegram_chat_id),
        )
        return int(cursor.lastrowid)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, tenant_id, full_name, email, telegram_chat_id
            FROM Users
            WHERE email = ? AND password = ?
            LIMIT 1
            """,
            (email, password),
        ).fetchone()
        return dict(row) if row else None


def insert_contract(
    tenant_id: int,
    title: str,
    end_date: date,
    status: str = "active",
    user_id: int | None = None,
    start_date: date | None = None,
    alert_days: int = 30,
    file_link: str | None = None,
    telegram_chat_id: int | None = None,
    manager_group_chat_id: int | None = None,
    alert_target: str = "direct",
    extra_chat_ids: list[int] | None = None,
) -> int:
    if telegram_chat_id is None:
        raise ValueError("telegram_chat_id is required for contract notifications")

    normalized_target = alert_target if alert_target in {"direct", "managers", "both"} else "direct"
    serialized_extra = json.dumps(extra_chat_ids or [])
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Contracts (
                tenant_id,
                user_id,
                title,
                start_date,
                end_date,
                alert_days,
                file_link,
                telegram_chat_id,
                manager_group_chat_id,
                alert_target,
                extra_chat_ids,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                user_id,
                title,
                start_date.isoformat() if start_date else None,
                end_date.isoformat(),
                alert_days,
                file_link,
                int(telegram_chat_id),
                manager_group_chat_id,
                normalized_target,
                serialized_extra,
                status,
            ),
        )
        return int(cursor.lastrowid)


def get_contracts_for_tenant(tenant_id: int, search: str | None = None) -> list[dict[str, Any]]:
    sql = (
        """
        SELECT
            id,
            tenant_id,
            title,
            start_date,
            end_date,
            alert_days,
            file_link,
            telegram_chat_id,
            status,
            created_at,
            CASE
                WHEN date(end_date) >= date('now') THEN 'active'
                ELSE 'expired'
            END AS computed_status
        FROM Contracts
        WHERE tenant_id = ?
        """
    )
    params: list[object] = [tenant_id]

    if search and search.strip():
        sql += " AND title LIKE ?"
        params.append(f"%{search.strip()}%")

    sql += " ORDER BY date(end_date) ASC, id DESC"

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def delete_contract_for_tenant(contract_id: int, tenant_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM Contracts
            WHERE id = ? AND tenant_id = ?
            """,
            (contract_id, tenant_id),
        )
        return cursor.rowcount > 0


def get_contracts_needing_alert_today() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                                c.id,
                                c.tenant_id,
                                t.name AS tenant_name,
                                c.title,
                                c.end_date,
                                c.alert_days,
                                c.telegram_chat_id,
                                CAST(julianday(c.end_date) - julianday('now') AS INTEGER) AS days_remaining
                        FROM Contracts c
                        JOIN Tenants t ON t.id = c.tenant_id
                        WHERE c.status = 'active'
                            AND c.telegram_chat_id IS NOT NULL
                            AND CAST(julianday(c.end_date) - julianday('now') AS INTEGER) = c.alert_days
                        ORDER BY c.end_date ASC
            """
        ).fetchall()


def is_chat_authorized_for_tenant(chat_id: int, tenant_id: int) -> bool:
    with get_connection() as conn:
        contract_match = conn.execute(
            """
            SELECT 1
            FROM Contracts
            WHERE tenant_id = ? AND telegram_chat_id = ?
            LIMIT 1
            """,
            (tenant_id, chat_id),
        ).fetchone()
        if contract_match:
            return True

        user_match = conn.execute(
            """
            SELECT 1
            FROM Users
            WHERE tenant_id = ? AND telegram_chat_id = ?
            LIMIT 1
            """,
            (tenant_id, chat_id),
        ).fetchone()
        return bool(user_match)


def get_contracts_due_for_alerts() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                c.id,
                c.tenant_id,
                c.title,
                c.end_date,
                c.alert_days,
                c.telegram_chat_id,
                c.manager_group_chat_id,
                c.alert_target,
                c.extra_chat_ids,
                t.name AS tenant_name,
                CAST(julianday(c.end_date) - julianday('now') AS INTEGER) AS days_remaining
            FROM Contracts c
            JOIN Tenants t ON t.id = c.tenant_id
            WHERE c.status = 'active'
              AND CAST(julianday(c.end_date) - julianday('now') AS INTEGER) = c.alert_days
            ORDER BY c.end_date ASC
            """
        ).fetchall()


def parse_chat_ids(contract_row: sqlite3.Row) -> list[int]:
    chat_ids: list[int] = []
    target = contract_row["alert_target"] or "direct"

    direct_id = contract_row["telegram_chat_id"]
    manager_group_id = contract_row["manager_group_chat_id"]

    if target in {"direct", "both"} and direct_id is not None:
        chat_ids.append(int(direct_id))
    if target in {"managers", "both"} and manager_group_id is not None:
        chat_ids.append(int(manager_group_id))

    raw_extra = contract_row["extra_chat_ids"]
    if raw_extra:
        try:
            parsed = json.loads(raw_extra)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, int):
                        chat_ids.append(item)
                    elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
                        chat_ids.append(int(item.strip()))
        except json.JSONDecodeError:
            pass

    # Preserve order and remove duplicates.
    unique: list[int] = []
    seen: set[int] = set()
    for chat_id in chat_ids:
        if chat_id not in seen:
            seen.add(chat_id)
            unique.append(chat_id)
    return unique
