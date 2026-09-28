"""
میدل‌ور کاربر

قبل از هر پیام/دکمه:
    1. کاربر در دیتابیس ثبت یا به‌روزرسانی می‌شود و شیء User در اختیار هندلر قرار می‌گیرد.
    2. اگر کاربر مسدود باشد (و ادمین نباشد)، درخواست او پردازش نمی‌شود.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser

from bot import texts
from bot.config import Config
from bot.database import Database

log = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        chat = data.get("event_chat")
        # فقط چت خصوصی پردازش می‌شود (ربات فروش در گروه کاربردی ندارد)
        if tg_user is None or tg_user.is_bot or (chat is not None and chat.type != "private"):
            return None

        db: Database = data["db"]
        config: Config = data["config"]
        user = await db.users.upsert(tg_user.id, tg_user.username, tg_user.full_name)
        data["user"] = user
        data["is_admin"] = config.is_admin(tg_user.id)

        if user.is_banned and not data["is_admin"]:
            if isinstance(event, CallbackQuery):
                await event.answer(texts.BANNED, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(texts.BANNED)
            return None

        return await handler(event, data)
