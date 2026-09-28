"""عملیات جدول سرویس‌ها (اشتراک‌ها)."""

from __future__ import annotations

import json
from typing import Any

from bot.database.models import SubStatus, Subscription, now_ts
from bot.database.repos.base import BaseRepo


class SubscriptionRepo(BaseRepo):
    table = "subscriptions"
    updatable = frozenset(
        {
            "plan_id",
            "server_id",
            "title",
            "config",
            "sub_link",
            "meta",
            "traffic_gb",
            "started_at",
            "expires_at",
            "status",
            "warned",
        }
    )

    async def create(
        self,
        *,
        user_id: int,
        plan_id: int | None,
        server_id: int | None,
        title: str,
        config: str,
        sub_link: str,
        meta: dict[str, Any],
        traffic_gb: float,
        started_at: int,
        expires_at: int,
    ) -> int:
        row_id, _ = await self.db.execute(
            """
            INSERT INTO subscriptions (user_id, plan_id, server_id, title, config, sub_link, meta,
                                       traffic_gb, started_at, expires_at, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                plan_id,
                server_id,
                title,
                config,
                sub_link,
                json.dumps(meta, ensure_ascii=False),
                traffic_gb,
                started_at,
                expires_at,
                SubStatus.ACTIVE,
                now_ts(),
            ),
        )
        return row_id

    async def update(self, row_id: int, **values: Any) -> bool:
        # فیلد meta به صورت JSON ذخیره می‌شود
        if "meta" in values and not isinstance(values["meta"], str):
            values["meta"] = json.dumps(values["meta"], ensure_ascii=False)
        return await super().update(row_id, **values)

    async def get(self, sub_id: int) -> Subscription | None:
        row = await self.db.fetchone("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        return Subscription.from_row(row) if row else None

    async def list_for_user(self, user_id: int, limit: int = 30) -> list[Subscription]:
        """سرویس‌های کاربر؛ ابتدا فعال‌ها، سپس جدیدترها."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM subscriptions WHERE user_id = ?
            ORDER BY (status = 'active') DESC, expires_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [Subscription.from_row(r) for r in rows]

    async def count_active(self) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM subscriptions WHERE status = ? AND expires_at > ?",
                (SubStatus.ACTIVE, now_ts()),
                default=0,
            )
        )

    async def count_total(self) -> int:
        return int(await self.db.fetchval("SELECT COUNT(*) FROM subscriptions", default=0))

    async def count_active_for_user(self, user_id: int) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM subscriptions WHERE user_id = ? AND status = ? AND expires_at > ?",
                (user_id, SubStatus.ACTIVE, now_ts()),
                default=0,
            )
        )

    # ------------------------------------------------------------------
    # بررسی‌های زمان‌بندی‌شده
    # ------------------------------------------------------------------
    async def due_for_warning(self, within_seconds: int) -> list[Subscription]:
        """سرویس‌های فعالی که کمتر از بازه مشخص به انقضایشان مانده و هشدار نگرفته‌اند."""
        now = now_ts()
        rows = await self.db.fetchall(
            """
            SELECT * FROM subscriptions
            WHERE status = ? AND warned = 0 AND expires_at > ? AND expires_at <= ?
            """,
            (SubStatus.ACTIVE, now, now + within_seconds),
        )
        return [Subscription.from_row(r) for r in rows]

    async def newly_expired(self) -> list[Subscription]:
        """سرویس‌هایی که هنوز «فعال» ثبت شده‌اند ولی زمانشان تمام شده است."""
        rows = await self.db.fetchall(
            "SELECT * FROM subscriptions WHERE status = ? AND expires_at <= ?",
            (SubStatus.ACTIVE, now_ts()),
        )
        return [Subscription.from_row(r) for r in rows]
