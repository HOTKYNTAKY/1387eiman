"""
میدل‌ور ضد اسپم (Throttling)

اگر کاربری در فاصله کمتر از `rate` ثانیه چند پیام/کلیک پشت سر هم بفرستد،
درخواست‌های اضافه نادیده گرفته می‌شوند. ادمین‌ها محدودیتی ندارند.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.5, admin_ids: tuple[int, ...] = ()) -> None:
        self.rate = rate
        self.admin_ids = set(admin_ids)
        self._last_seen: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id in self.admin_ids:
            return await handler(event, data)

        key = (user.id, type(event).__name__)
        now = time.monotonic()
        last = self._last_seen.get(key, 0.0)
        self._last_seen[key] = now
        if now - last < self.rate:
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ لطفاً کمی آهسته‌تر...", show_alert=False)
            return None

        # جلوگیری از بزرگ شدن بی‌رویه حافظه
        if len(self._last_seen) > 50_000:
            cutoff = now - 60
            self._last_seen = {k: v for k, v in self._last_seen.items() if v > cutoff}
        return await handler(event, data)
