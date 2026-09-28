"""عملیات جدول سفارش‌ها و آمار فروش."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bot.database.models import Order, OrderStatus, now_ts
from bot.database.repos.base import BaseRepo


class OrderRepo(BaseRepo):
    table = "orders"
    updatable = frozenset(
        {
            "plan_id",
            "subscription_id",
            "amount",
            "method",
            "status",
            "receipt_kind",
            "receipt_file_id",
            "receipt_text",
            "note",
            "updated_at",
            "paid_at",
        }
    )

    async def create(
        self,
        *,
        user_id: int,
        plan_id: int | None,
        kind: str,
        amount: int,
        plan_title: str,
        method: str,
        subscription_id: int | None = None,
        status: str = OrderStatus.PENDING,
    ) -> int:
        now = now_ts()
        row_id, _ = await self.db.execute(
            """
            INSERT INTO orders (user_id, plan_id, subscription_id, kind, amount, plan_title,
                                method, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, plan_id, subscription_id, kind, amount, plan_title, method, status, now, now),
        )
        return row_id

    async def get(self, order_id: int) -> Order | None:
        row = await self.db.fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
        return Order.from_row(row) if row else None

    async def transition(
        self, order_id: int, from_statuses: Iterable[str], to_status: str, **extra: Any
    ) -> bool:
        """
        تغییر وضعیت سفارش به صورت اتمی و فقط اگر وضعیت فعلی در لیست مجاز باشد.
        این کار از تایید دوباره یک سفارش (مثلاً دوبار کلیک ادمین) جلوگیری می‌کند.
        :return: True اگر وضعیت تغییر کرد.
        """
        invalid = set(extra) - self.updatable
        if invalid:
            raise ValueError(f"Invalid order columns: {sorted(invalid)}")
        statuses = list(from_statuses)
        placeholders = ", ".join("?" for _ in statuses)
        assignments = ", ".join(["status = ?", "updated_at = ?", *[f"{k} = ?" for k in extra]])
        _, count = await self.db.execute(
            f"UPDATE orders SET {assignments} WHERE id = ? AND status IN ({placeholders})",  # noqa: S608
            (to_status, now_ts(), *extra.values(), order_id, *statuses),
        )
        return count > 0

    async def list_for_user(self, user_id: int, limit: int = 10) -> list[Order]:
        rows = await self.db.fetchall(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
        )
        return [Order.from_row(r) for r in rows]

    async def list_by_status(self, statuses: Iterable[str], limit: int = 20, offset: int = 0) -> list[Order]:
        statuses = list(statuses)
        placeholders = ", ".join("?" for _ in statuses)
        rows = await self.db.fetchall(
            f"SELECT * FROM orders WHERE status IN ({placeholders}) ORDER BY id LIMIT ? OFFSET ?",  # noqa: S608
            (*statuses, limit, offset),
        )
        return [Order.from_row(r) for r in rows]

    async def count_by_status(self, *statuses: str) -> int:
        placeholders = ", ".join("?" for _ in statuses)
        return int(
            await self.db.fetchval(
                f"SELECT COUNT(*) FROM orders WHERE status IN ({placeholders})",  # noqa: S608
                statuses,
                default=0,
            )
        )

    async def pending_for_user(self, user_id: int) -> list[Order]:
        """سفارش‌های پرداخت‌نشده کاربر."""
        rows = await self.db.fetchall(
            "SELECT * FROM orders WHERE user_id = ? AND status = ? ORDER BY id DESC",
            (user_id, OrderStatus.PENDING),
        )
        return [Order.from_row(r) for r in rows]

    async def cancel_stale(self, older_than_seconds: int) -> int:
        """لغو خودکار سفارش‌هایی که مدت زیادی بدون پرداخت مانده‌اند."""
        cutoff = now_ts() - older_than_seconds
        _, count = await self.db.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE status = ? AND created_at < ?",
            (OrderStatus.CANCELED, now_ts(), OrderStatus.PENDING, cutoff),
        )
        return count

    # ------------------------------------------------------------------
    # آمار
    # ------------------------------------------------------------------
    async def sales_since(self, timestamp: int) -> tuple[int, int]:
        """(تعداد، مجموع مبلغ) فروش‌های موفق از زمان مشخص (براساس زمان پرداخت)."""
        row = await self.db.fetchone(
            f"""
            SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM orders
            WHERE status IN ({", ".join("?" for _ in OrderStatus.REVENUE)})
              AND amount > 0 AND COALESCE(paid_at, created_at) >= ?
            """,  # noqa: S608
            (*OrderStatus.REVENUE, timestamp),
        )
        return (int(row[0]), int(row[1])) if row else (0, 0)

    async def top_plans(self, limit: int = 5) -> list[tuple[str, int, int]]:
        """پرفروش‌ترین پلن‌ها: (نام پلن، تعداد، مجموع مبلغ)."""
        rows = await self.db.fetchall(
            f"""
            SELECT plan_title, COUNT(*) AS cnt, COALESCE(SUM(amount), 0) FROM orders
            WHERE status IN ({", ".join("?" for _ in OrderStatus.REVENUE)}) AND amount > 0
            GROUP BY plan_title ORDER BY cnt DESC LIMIT ?
            """,  # noqa: S608
            (*OrderStatus.REVENUE, limit),
        )
        return [(str(r[0]), int(r[1]), int(r[2])) for r in rows]

    async def user_summary(self, user_id: int) -> tuple[int, int]:
        """(تعداد خریدهای موفق، مجموع پرداختی) یک کاربر."""
        row = await self.db.fetchone(
            f"""
            SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM orders
            WHERE user_id = ? AND status IN ({", ".join("?" for _ in OrderStatus.REVENUE)})
            """,  # noqa: S608
            (user_id, *OrderStatus.REVENUE),
        )
        return (int(row[0]), int(row[1])) if row else (0, 0)
