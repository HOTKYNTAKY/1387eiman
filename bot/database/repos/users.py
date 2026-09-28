"""عملیات جدول کاربران."""

from __future__ import annotations

from bot.database.models import SubStatus, User, now_ts
from bot.database.repos.base import BaseRepo


class UserRepo(BaseRepo):
    table = "users"
    updatable = frozenset({"username", "full_name", "is_banned", "bot_blocked"})

    async def upsert(self, user_id: int, username: str | None, full_name: str) -> User:
        """
        ثبت کاربر جدید یا به‌روزرسانی نام و زمان آخرین فعالیت کاربر موجود.
        چون کاربر در حال تعامل با ربات است، پرچم «بلاک کردن ربات» هم پاک می‌شود.
        """
        now = now_ts()
        await self.db.execute(
            """
            INSERT INTO users (id, username, full_name, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username     = excluded.username,
                full_name    = excluded.full_name,
                last_seen_at = excluded.last_seen_at,
                bot_blocked  = 0
            """,
            (user_id, username, full_name or "", now, now),
        )
        user = await self.get(user_id)
        assert user is not None
        return user

    async def get(self, user_id: int) -> User | None:
        row = await self.db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row) if row else None

    async def find(self, query: str) -> User | None:
        """جستجو با آیدی عددی یا یوزرنیم (با یا بدون @)."""
        query = query.strip()
        if query.lstrip("-").isdigit():
            return await self.get(int(query))
        username = query.lstrip("@")
        if not username:
            return None
        row = await self.db.fetchone(
            "SELECT * FROM users WHERE lower(username) = lower(?)", (username,)
        )
        return User.from_row(row) if row else None

    async def set_banned(self, user_id: int, banned: bool) -> bool:
        return await self.update(user_id, is_banned=int(banned))

    async def set_bot_blocked(self, user_id: int, blocked: bool = True) -> None:
        await self.update(user_id, bot_blocked=int(blocked))

    # ------------------------------------------------------------------
    # لیست و آمار
    # ------------------------------------------------------------------
    async def list_recent(self, limit: int, offset: int = 0) -> list[User]:
        rows = await self.db.fetchall(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [User.from_row(r) for r in rows]

    async def list_banned(self, limit: int, offset: int = 0) -> list[User]:
        rows = await self.db.fetchall(
            "SELECT * FROM users WHERE is_banned = 1 ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [User.from_row(r) for r in rows]

    async def count(self) -> int:
        return int(await self.db.fetchval("SELECT COUNT(*) FROM users", default=0))

    async def count_banned(self) -> int:
        return int(await self.db.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = 1", default=0))

    async def count_bot_blocked(self) -> int:
        return int(
            await self.db.fetchval("SELECT COUNT(*) FROM users WHERE bot_blocked = 1", default=0)
        )

    async def count_since(self, timestamp: int) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?", (timestamp,), default=0
            )
        )

    async def broadcast_ids(self, only_active_subscribers: bool = False) -> list[int]:
        """آیدی کاربرانی که پیام همگانی برایشان ارسال می‌شود (بدون مسدودها)."""
        if only_active_subscribers:
            rows = await self.db.fetchall(
                """
                SELECT DISTINCT u.id FROM users u
                JOIN subscriptions s ON s.user_id = u.id
                WHERE u.is_banned = 0 AND u.bot_blocked = 0
                  AND s.status = ? AND s.expires_at > ?
                """,
                (SubStatus.ACTIVE, now_ts()),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT id FROM users WHERE is_banned = 0 AND bot_blocked = 0"
            )
        return [int(r[0]) for r in rows]
