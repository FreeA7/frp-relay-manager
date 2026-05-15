from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .security import hash_password, utc_iso


class Repository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_db(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS enrollment_tokens (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    label TEXT,
                    expires_at TEXT,
                    used_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    client_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    os TEXT NOT NULL,
                    arch TEXT,
                    ips_json TEXT NOT NULL DEFAULT '[]',
                    agent_version TEXT,
                    frpc_status TEXT NOT NULL DEFAULT 'unknown',
                    status TEXT NOT NULL DEFAULT 'offline',
                    last_seen_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS port_check_tasks (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS forwards (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    local_ip TEXT NOT NULL,
                    local_port INTEGER NOT NULL,
                    remote_port INTEGER,
                    subdomain TEXT,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def ensure_admin(self, user_id: str, email: str, password: str, reset_password: bool = False) -> None:
        existing = self.fetchone("SELECT id FROM users WHERE email = ?", (email,))
        if existing and not reset_password:
            return

        password_hash = hash_password(password)
        now = utc_iso()
        if existing:
            self.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email))
        else:
            self.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, email, password_hash, now),
            )

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> None:
        with self.connect() as db:
            db.execute(sql, params)

    def fetchone(self, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        with self.connect() as db:
            row = db.execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def executemany(self, sql: str, rows: Iterable[Tuple[Any, ...]]) -> None:
        with self.connect() as db:
            db.executemany(sql, rows)

