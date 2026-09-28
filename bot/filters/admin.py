"""فیلتر دسترسی ادمین: فقط آیدی‌های عددی تعریف‌شده در ADMIN_ID عبور می‌کنند."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject, User

from bot.config import Config


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, config: Config, event_from_user: User | None = None) -> bool:
        return event_from_user is not None and config.is_admin(event_from_user.id)
