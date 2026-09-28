"""
توابع کمکی کار با API تلگرام همراه با مدیریت خطا

- safe_edit: ویرایش پیام و نادیده گرفتن خطای «پیام تغییری نکرده»
- safe_send: ارسال پیام به کاربر و ثبت کاربرانی که ربات را بلاک کرده‌اند
- notify_admins: ارسال پیام به همه ادمین‌ها
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

if TYPE_CHECKING:
    from bot.config import Config
    from bot.database import Database

log = logging.getLogger(__name__)


def callback_message(callback: CallbackQuery) -> Message | None:
    """پیام مربوط به callback (اگر هنوز در دسترس باشد)."""
    return callback.message if isinstance(callback.message, Message) else None


async def safe_edit(
    message: Message | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message | None:
    """
    ویرایش متن پیام؛ اگر ویرایش ممکن نباشد (مثلاً پیام عکس است یا خیلی قدیمی
    شده)، پیام جدید ارسال می‌شود.
    """
    if message is None:
        return None
    try:
        if message.photo or message.document or message.video:
            # پیام‌های رسانه‌ای متن ندارند؛ به جای ویرایش پیام جدید می‌فرستیم
            return await message.answer(text, reply_markup=reply_markup, **kwargs)
        result = await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        return result if isinstance(result, Message) else message
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return message
        log.debug("edit failed (%s), sending a new message", exc)
        return await message.answer(text, reply_markup=reply_markup, **kwargs)


async def safe_send(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    db: Database | None = None,
    **kwargs: Any,
) -> Message | None:
    """
    ارسال پیام بدون ایجاد خطا در برنامه.
    اگر کاربر ربات را بلاک کرده باشد در دیتابیس علامت‌گذاری می‌شود.
    """
    for _ in range(2):
        try:
            return await bot.send_message(chat_id, text, **kwargs)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
        except TelegramForbiddenError:
            if db is not None:
                await db.users.set_bot_blocked(chat_id, True)
            return None
        except TelegramAPIError as exc:
            log.warning("Failed to send message to %s: %s", chat_id, exc)
            return None
    return None


async def notify_admins(bot: Bot, config: Config, text: str, **kwargs: Any) -> list[Message]:
    """ارسال پیام متنی به همه ادمین‌ها؛ خطای هر ادمین جداگانه مدیریت می‌شود."""
    sent: list[Message] = []
    for admin_id in config.admin_ids:
        try:
            sent.append(await bot.send_message(admin_id, text, **kwargs))
        except TelegramAPIError as exc:
            log.warning("Cannot notify admin %s: %s", admin_id, exc)
    return sent
