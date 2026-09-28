"""عملیات جدول پلن‌ها."""

from __future__ import annotations

from bot.database.models import Plan, now_ts
from bot.database.repos.base import BaseRepo


class PlanRepo(BaseRepo):
    table = "plans"
    updatable = frozenset(
        {"server_id", "name", "days", "traffic_gb", "price", "description", "is_active", "is_deleted", "sort_order"}
    )

    async def create(
        self,
        *,
        server_id: int,
        name: str,
        days: int,
        traffic_gb: float,
        price: int,
        description: str = "",
    ) -> int:
        row_id, _ = await self.db.execute(
            """
            INSERT INTO plans (server_id, name, days, traffic_gb, price, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (server_id, name, days, traffic_gb, price, description, now_ts()),
        )
        return row_id

    async def get(self, plan_id: int) -> Plan | None:
        row = await self.db.fetchone("SELECT * FROM plans WHERE id = ? AND is_deleted = 0", (plan_id,))
        return Plan.from_row(row) if row else None

    async def get_any(self, plan_id: int) -> Plan | None:
        """دریافت پلن حتی اگر حذف شده باشد (برای تحویل سفارش‌های قبلی)."""
        row = await self.db.fetchone("SELECT * FROM plans WHERE id = ?", (plan_id,))
        return Plan.from_row(row) if row else None

    async def list_all(self) -> list[Plan]:
        """همه پلن‌های حذف‌نشده (برای پنل ادمین)."""
        rows = await self.db.fetchall(
            """
            SELECT p.* FROM plans p
            JOIN servers s ON s.id = p.server_id
            WHERE p.is_deleted = 0 AND s.is_deleted = 0
            ORDER BY p.server_id, p.sort_order, p.days, p.price
            """
        )
        return [Plan.from_row(r) for r in rows]

    async def list_for_server(self, server_id: int, *, only_active: bool = True) -> list[Plan]:
        query = "SELECT * FROM plans WHERE server_id = ? AND is_deleted = 0"
        if only_active:
            query += " AND is_active = 1"
        query += " ORDER BY sort_order, days, price"
        rows = await self.db.fetchall(query, (server_id,))
        return [Plan.from_row(r) for r in rows]

    async def list_for_sale(self) -> list[Plan]:
        """پلن‌های فعال روی سرورهای فعال (برای هدیه دادن سرویس توسط ادمین)."""
        rows = await self.db.fetchall(
            """
            SELECT p.* FROM plans p
            JOIN servers s ON s.id = p.server_id
            WHERE p.is_deleted = 0 AND p.is_active = 1 AND s.is_deleted = 0 AND s.is_active = 1
            ORDER BY p.server_id, p.sort_order, p.days, p.price
            """
        )
        return [Plan.from_row(r) for r in rows]

    async def soft_delete(self, plan_id: int) -> bool:
        return await self.update(plan_id, is_deleted=1, is_active=0)
