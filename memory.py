from __future__ import annotations

import aiosqlite

SCHEMA = '''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
'''


class MemoryStore:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
            await db.commit()

    async def get_recent_messages(self, user_id: int, limit: int = 8) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                '''
                SELECT role, content
                FROM messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    async def clear_history(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
            await db.commit()

    async def set_setting(self, user_id: int, key: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO settings (user_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
                ''',
                (user_id, key, value),
            )
            await db.commit()

    async def get_setting(self, user_id: int, key: str, default: str | None = None) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE user_id = ? AND key = ?",
                (user_id, key),
            )
            row = await cursor.fetchone()
        if row is None:
            return default
        return row[0]

    async def delete_setting(self, user_id: int, key: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM settings WHERE user_id = ? AND key = ?",
                (user_id, key),
            )
            await db.commit()
