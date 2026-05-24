from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from typing import Any, Optional

from config import SETTINGS

@dataclass
class UserState:
    user_id: int
    username: str
    role: str = "normal"
    mode: str = "chat"
    premium: int = 0
    web_enabled: int = 0

class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    role TEXT NOT NULL DEFAULT 'normal',
                    mode TEXT NOT NULL DEFAULT 'chat',
                    premium INTEGER NOT NULL DEFAULT 0,
                    web_enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def ensure_user(self, user_id: int, username: str | None) -> UserState:
        username = (username or "").lstrip("@")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()

            if row is None:
                role = "admin" if username and username in SETTINGS.admin_usernames else "normal"
                premium = 1 if role in {"premium", "admin"} else 0
                await db.execute(
                    "INSERT INTO users (user_id, username, role, mode, premium, web_enabled) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username, role, "chat", premium, 0),
                )
                await db.commit()
                return UserState(user_id=user_id, username=username, role=role, mode="chat", premium=premium, web_enabled=0)

            if username and row["username"] != username:
                await db.execute(
                    "UPDATE users SET username = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (username, user_id),
                )
                await db.commit()

            return UserState(
                user_id=row["user_id"],
                username=username or (row["username"] or ""),
                role=row["role"],
                mode=row["mode"],
                premium=row["premium"],
                web_enabled=row["web_enabled"],
            )

    async def get_user(self, user_id: int) -> Optional[UserState]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                return None
            return UserState(
                user_id=row["user_id"],
                username=row["username"] or "",
                role=row["role"],
                mode=row["mode"],
                premium=row["premium"],
                web_enabled=row["web_enabled"],
            )

    async def set_role(self, user_id: int, role: str) -> None:
        premium = 1 if role in {"premium", "admin"} else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET role = ?, premium = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (role, premium, user_id),
            )
            await db.commit()

    async def set_mode(self, user_id: int, mode: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET mode = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (mode, user_id),
            )
            await db.commit()

    async def set_premium(self, user_id: int, premium: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET premium = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (1 if premium else 0, user_id),
            )
            await db.commit()

    async def set_web(self, user_id: int, enabled: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET web_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (1 if enabled else 0, user_id),
            )
            await db.commit()

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
            await db.commit()

    async def get_history(self, user_id: int, limit: int = 12) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cur.fetchall()
        rows = list(reversed(rows))
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def clear_history(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
            await db.commit()

    async def list_users(self, limit: int = 20) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT user_id, username, role, mode, premium, web_enabled FROM users ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

MEMORY = MemoryStore(SETTINGS.db_path)
