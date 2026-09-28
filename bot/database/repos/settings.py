"""تنظیمات قابل ویرایش از داخل ربات (جدول کلید/مقدار)."""

from __future__ import annotations

from bot.database.repos.base import BaseRepo
from bot.database.schema import DEFAULT_SETTINGS


class SettingsRepo(BaseRepo):
    table = "settings"

    async def get(self, key: str, default: str | None = None) -> str:
        value = await self.db.fetchval("SELECT value FROM settings WHERE key = ?", (key,))
        if value is None:
            return default if default is not None else DEFAULT_SETTINGS.get(key, "")
        return str(value)

    async def set(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    async def get_bool(self, key: str) -> bool:
        return (await self.get(key)).strip() in {"1", "true", "yes", "on"}

    async def toggle(self, key: str) -> bool:
        """مقدار بولی را برعکس می‌کند و مقدار جدید را برمی‌گرداند."""
        new_value = not await self.get_bool(key)
        await self.set(key, "1" if new_value else "0")
        return new_value

    async def get_many(self, *keys: str) -> dict[str, str]:
        return {key: await self.get(key) for key in keys}
