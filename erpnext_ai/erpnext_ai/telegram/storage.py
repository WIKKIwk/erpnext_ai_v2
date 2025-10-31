from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from cryptography.fernet import Fernet


def _utcnow() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class BotStorage:
    """Lightweight SQLite-backed storage for Telegram bot state."""

    def __init__(self, db_path: Path, encryption_key: bytes):
        self.db_path = Path(db_path)
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._fernet = Fernet(encryption_key)
        self._initialise_schema()

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialise_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sales_master_managers (
                    telegram_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    added_by INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    sales_master_manager_id INTEGER,
                    sales_manager_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY (sales_master_manager_id) REFERENCES sales_master_managers(telegram_id),
                    FOREIGN KEY (sales_manager_id) REFERENCES sales_managers(telegram_id)
                );

                CREATE TABLE IF NOT EXISTS group_members (
                    chat_id INTEGER NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    last_message TEXT,
                    PRIMARY KEY (chat_id, telegram_id)
                );

                CREATE TABLE IF NOT EXISTS sales_managers (
                    telegram_id INTEGER PRIMARY KEY,
                    group_chat_id INTEGER UNIQUE,
                    username TEXT,
                    full_name TEXT,
                    status TEXT NOT NULL,
                    encrypted_api_key TEXT,
                    encrypted_api_secret TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    requester_id INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    sales_manager_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")

    # Master manager operations -------------------------------------------------
    def add_master_manager(
        self,
        telegram_id: int,
        *,
        full_name: Optional[str],
        username: Optional[str],
        added_by: Optional[int] = None,
    ) -> bool:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT telegram_id FROM sales_master_managers WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE sales_master_managers
                    SET full_name = ?, username = ?
                    WHERE telegram_id = ?
                    """,
                    (full_name, username, telegram_id),
                )
                return False
            conn.execute(
                """
                INSERT INTO sales_master_managers (telegram_id, full_name, username, added_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (telegram_id, full_name, username, added_by, _utcnow()),
            )
            return True

    def remove_master_manager(self, telegram_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM sales_master_managers WHERE telegram_id = ?", (telegram_id,))
            conn.execute(
                """
                UPDATE groups
                SET sales_master_manager_id = NULL
                WHERE sales_master_manager_id = ?
                """,
                (telegram_id,),
            )

    def is_master_manager(self, telegram_id: int) -> bool:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM sales_master_managers WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            return bool(row)

    def list_master_managers(self) -> List[sqlite3.Row]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                "SELECT telegram_id, full_name, username, created_at FROM sales_master_managers ORDER BY created_at"
            ).fetchall()
            return list(rows)

    # Group operations ----------------------------------------------------------
    def touch_group(self, chat_id: int, title: Optional[str]) -> None:
        now = _utcnow()
        with self._lock, self._connection() as conn:
            existing = conn.execute("SELECT chat_id FROM groups WHERE chat_id = ?", (chat_id,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE groups SET title = COALESCE(?, title), updated_at = ? WHERE chat_id = ?",
                    (title, now, chat_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO groups (chat_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chat_id, title, now, now),
                )

    def assign_group_to_master(self, chat_id: int, master_manager_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                UPDATE groups
                SET sales_master_manager_id = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (master_manager_id, _utcnow(), chat_id),
            )

    def get_group(self, chat_id: int) -> Optional[sqlite3.Row]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT chat_id, title, sales_master_manager_id, sales_manager_id
                FROM groups
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            return row

    # Group member tracking -----------------------------------------------------
    def upsert_group_member(
        self,
        chat_id: int,
        *,
        telegram_id: int,
        username: Optional[str],
        full_name: Optional[str],
        message_preview: Optional[str] = None,
    ) -> None:
        now = _utcnow()
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT telegram_id FROM group_members WHERE chat_id = ? AND telegram_id = ?
                """,
                (chat_id, telegram_id),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE group_members
                    SET username = ?, full_name = ?, last_seen = ?, last_message = ?
                    WHERE chat_id = ? AND telegram_id = ?
                    """,
                    (username, full_name, now, message_preview, chat_id, telegram_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO group_members (
                        chat_id,
                        telegram_id,
                        username,
                        full_name,
                        first_seen,
                        last_seen,
                        last_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chat_id, telegram_id, username, full_name, now, now, message_preview),
                )

    def list_group_members(self, chat_id: int) -> List[Dict[str, Optional[str]]]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT telegram_id, username, full_name, last_seen
                FROM group_members
                WHERE chat_id = ?
                ORDER BY full_name COLLATE NOCASE
                """,
                (chat_id,),
            ).fetchall()
            return [
                {
                    "telegram_id": row["telegram_id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "last_seen": row["last_seen"],
                }
                for row in rows
            ]

    # Sales manager operations --------------------------------------------------
    def assign_sales_manager(
        self,
        *,
        telegram_id: int,
        group_chat_id: int,
        username: Optional[str],
        full_name: Optional[str],
    ) -> None:
        now = _utcnow()
        with self._lock, self._connection() as conn:
            existing = conn.execute(
                "SELECT group_chat_id FROM sales_managers WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if existing and existing["group_chat_id"] != group_chat_id:
                raise ValueError("User is already a sales manager in a different group.")

            conn.execute(
                """
                INSERT INTO sales_managers (
                    telegram_id,
                    group_chat_id,
                    username,
                    full_name,
                    status,
                    encrypted_api_key,
                    encrypted_api_secret,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, 'awaiting_api', NULL, NULL, ?, ?)
                ON CONFLICT(telegram_id)
                DO UPDATE SET
                    group_chat_id=excluded.group_chat_id,
                    username=excluded.username,
                    full_name=excluded.full_name,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (telegram_id, group_chat_id, username, full_name, now, now),
            )

            conn.execute(
                "UPDATE groups SET sales_manager_id = ?, updated_at = ? WHERE chat_id = ?",
                (telegram_id, now, group_chat_id),
            )

    def clear_sales_manager(self, telegram_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE groups SET sales_manager_id = NULL WHERE sales_manager_id = ?",
                (telegram_id,),
            )
            conn.execute("DELETE FROM sales_managers WHERE telegram_id = ?", (telegram_id,))

    def get_sales_manager(self, telegram_id: int) -> Optional[sqlite3.Row]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT telegram_id, group_chat_id, status, username, full_name,
                       encrypted_api_key, encrypted_api_secret, updated_at
                FROM sales_managers
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            return row

    def get_sales_manager_for_group(self, chat_id: int) -> Optional[sqlite3.Row]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT sm.telegram_id,
                       sm.username,
                       sm.full_name,
                       sm.status,
                       sm.encrypted_api_key,
                       sm.encrypted_api_secret,
                       sm.updated_at
                FROM sales_managers AS sm
                JOIN groups AS g ON g.sales_manager_id = sm.telegram_id
                WHERE g.chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            return row

    def store_sales_manager_credentials(
        self,
        *,
        telegram_id: int,
        api_key: str,
        api_secret: str,
        status: str,
    ) -> None:
        encrypted_key = self._encrypt(api_key)
        encrypted_secret = self._encrypt(api_secret)
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                UPDATE sales_managers
                SET encrypted_api_key = ?, encrypted_api_secret = ?, status = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (encrypted_key, encrypted_secret, status, _utcnow(), telegram_id),
            )

    def get_decrypted_credentials(self, telegram_id: int) -> Optional[Tuple[str, str]]:
        manager = self.get_sales_manager(telegram_id)
        if not manager:
            return None
        if not manager["encrypted_api_key"] or not manager["encrypted_api_secret"]:
            return None
        return (
            self._decrypt(manager["encrypted_api_key"]),
            self._decrypt(manager["encrypted_api_secret"]),
        )

    def get_group_credentials(self, chat_id: int) -> Optional[Tuple[int, str, str, str]]:
        manager = self.get_sales_manager_for_group(chat_id)
        if not manager:
            return None
        if not manager["encrypted_api_key"] or not manager["encrypted_api_secret"]:
            return None
        return (
            manager["telegram_id"],
            self._decrypt(manager["encrypted_api_key"]),
            self._decrypt(manager["encrypted_api_secret"]),
            manager["status"],
        )

    # Order logging -------------------------------------------------------------
    def log_order_request(
        self,
        *,
        chat_id: int,
        requester_id: int,
        payload: Dict[str, object],
        sales_manager_id: Optional[int],
        status: str = "pending",
    ) -> int:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO order_requests (
                    chat_id,
                    requester_id,
                    payload,
                    sales_manager_id,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    requester_id,
                    json.dumps(payload, ensure_ascii=True),
                    sales_manager_id,
                    status,
                    _utcnow(),
                    _utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def update_order_status(self, order_id: int, status: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE order_requests SET status = ?, updated_at = ? WHERE id = ?",
                (status, _utcnow(), order_id),
            )

    def list_orders(self, *, status: Optional[str] = None, limit: int = 20) -> List[Dict[str, object]]:
        query = "SELECT id, chat_id, requester_id, payload, sales_manager_id, status, created_at FROM order_requests"
        params: List[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._lock, self._connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            results: List[Dict[str, object]] = []
            for row in rows:
                payload = json.loads(row["payload"])
                results.append(
                    {
                        "id": row["id"],
                        "chat_id": row["chat_id"],
                        "requester_id": row["requester_id"],
                        "payload": payload,
                        "sales_manager_id": row["sales_manager_id"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                    }
                )
            return results

