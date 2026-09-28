"""عملیات انبار کانفیگ‌ها (برای سرورهای دستی)."""

from __future__ import annotations

from bot.database.models import ConfigItem, now_ts
from bot.database.repos.base import BaseRepo


class ConfigRepo(BaseRepo):
    table = "configs"
    updatable = frozenset({"subscription_id", "is_used", "used_at", "content"})

    async def add_many(self, plan_id: int, contents: list[str]) -> tuple[int, int]:
        """
        افزودن چند کانفیگ به انبار یک پلن.
        کانفیگ‌های تکراری (موجود در همان پلن یا تکراری در ورودی) نادیده گرفته می‌شوند.
        :return: (تعداد اضافه‌شده، تعداد تکراری)
        """
        existing_rows = await self.db.fetchall(
            "SELECT content FROM configs WHERE plan_id = ?", (plan_id,)
        )
        existing = {r[0] for r in existing_rows}
        fresh: list[str] = []
        for item in contents:
            item = item.strip()
            if item and item not in existing:
                existing.add(item)
                fresh.append(item)
        if fresh:
            now = now_ts()
            await self.db.executemany(
                "INSERT INTO configs (plan_id, content, created_at) VALUES (?, ?, ?)",
                [(plan_id, item, now) for item in fresh],
            )
        return len(fresh), len([c for c in contents if c.strip()]) - len(fresh)

    async def pop(self, plan_id: int) -> ConfigItem | None:
        """
        برداشتن یک کانفیگ آزاد از انبار به صورت اتمی
        (دو خرید همزمان هرگز یک کانفیگ مشترک دریافت نمی‌کنند).
        """
        async with self.db.transaction() as conn:
            async with conn.execute(
                "SELECT * FROM configs WHERE plan_id = ? AND is_used = 0 ORDER BY id LIMIT 1",
                (plan_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            await conn.execute(
                "UPDATE configs SET is_used = 1, used_at = ? WHERE id = ?", (now_ts(), row["id"])
            )
        item = ConfigItem.from_row(row)
        item.is_used = 1
        return item

    async def attach(self, config_id: int, subscription_id: int) -> None:
        await self.update(config_id, subscription_id=subscription_id)

    async def release(self, config_id: int) -> None:
        """برگرداندن کانفیگ به انبار (وقتی تحویل سرویس ناموفق بود)."""
        await self.update(config_id, is_used=0, used_at=None, subscription_id=None)

    async def count_available(self, plan_id: int) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM configs WHERE plan_id = ? AND is_used = 0", (plan_id,), default=0
            )
        )

    async def count_used(self, plan_id: int) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM configs WHERE plan_id = ? AND is_used = 1", (plan_id,), default=0
            )
        )

    async def available_by_plan(self) -> dict[int, int]:
        """تعداد کانفیگ‌های آزاد به تفکیک پلن."""
        rows = await self.db.fetchall(
            "SELECT plan_id, COUNT(*) FROM configs WHERE is_used = 0 GROUP BY plan_id"
        )
        return {int(r[0]): int(r[1]) for r in rows}

    async def list_available(self, plan_id: int) -> list[ConfigItem]:
        rows = await self.db.fetchall(
            "SELECT * FROM configs WHERE plan_id = ? AND is_used = 0 ORDER BY id", (plan_id,)
        )
        return [ConfigItem.from_row(r) for r in rows]

    async def delete_available(self, plan_id: int) -> int:
        _, count = await self.db.execute(
            "DELETE FROM configs WHERE plan_id = ? AND is_used = 0", (plan_id,)
        )
        return count
