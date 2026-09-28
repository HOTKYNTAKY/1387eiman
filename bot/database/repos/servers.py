"""عملیات جدول سرورها."""

from __future__ import annotations

from bot.database.models import Server, SubStatus, now_ts
from bot.database.repos.base import BaseRepo


class ServerRepo(BaseRepo):
    table = "servers"
    updatable = frozenset(
        {
            "name",
            "kind",
            "api_url",
            "api_user",
            "api_pass",
            "api_token",
            "inbound_ids",
            "sub_url",
            "address",
            "is_active",
            "is_deleted",
        }
    )

    async def create(
        self,
        *,
        name: str,
        kind: str,
        api_url: str = "",
        api_user: str = "",
        api_pass: str = "",
        api_token: str = "",
        inbound_ids: str = "",
        sub_url: str = "",
        address: str = "",
    ) -> int:
        row_id, _ = await self.db.execute(
            """
            INSERT INTO servers (name, kind, api_url, api_user, api_pass, api_token,
                                 inbound_ids, sub_url, address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, kind, api_url, api_user, api_pass, api_token, inbound_ids, sub_url, address, now_ts()),
        )
        return row_id

    async def get(self, server_id: int) -> Server | None:
        row = await self.db.fetchone(
            "SELECT * FROM servers WHERE id = ? AND is_deleted = 0", (server_id,)
        )
        return Server.from_row(row) if row else None

    async def get_any(self, server_id: int) -> Server | None:
        """دریافت سرور حتی اگر حذف شده باشد (برای نمایش سوابق)."""
        row = await self.db.fetchone("SELECT * FROM servers WHERE id = ?", (server_id,))
        return Server.from_row(row) if row else None

    async def list(self) -> list[Server]:
        rows = await self.db.fetchall("SELECT * FROM servers WHERE is_deleted = 0 ORDER BY id")
        return [Server.from_row(r) for r in rows]

    async def list_for_sale(self) -> list[Server]:
        """سرورهای فعالی که حداقل یک پلن فعال دارند (برای نمایش در بخش خرید)."""
        rows = await self.db.fetchall(
            """
            SELECT s.* FROM servers s
            WHERE s.is_deleted = 0 AND s.is_active = 1
              AND EXISTS (SELECT 1 FROM plans p
                          WHERE p.server_id = s.id AND p.is_active = 1 AND p.is_deleted = 0)
            ORDER BY s.id
            """
        )
        return [Server.from_row(r) for r in rows]

    async def soft_delete(self, server_id: int) -> None:
        """حذف نرم سرور و پلن‌های آن (سوابق سفارش‌ها حفظ می‌شود)."""
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE servers SET is_deleted = 1, is_active = 0 WHERE id = ?", (server_id,)
            )
            await conn.execute(
                "UPDATE plans SET is_deleted = 1, is_active = 0 WHERE server_id = ?", (server_id,)
            )

    async def count_active_subscriptions(self, server_id: int) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM subscriptions WHERE server_id = ? AND status = ? AND expires_at > ?",
                (server_id, SubStatus.ACTIVE, now_ts()),
                default=0,
            )
        )
