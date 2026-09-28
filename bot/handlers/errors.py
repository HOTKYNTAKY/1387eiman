"""
مدیریت سراسری خطاها

هر خطای پیش‌بینی‌نشده در هندلرها اینجا لاگ می‌شود (همراه با شماره آپدیت) و به
کاربر پیام کوتاهی نمایش داده می‌شود؛ ربات هرگز به خاطر یک خطا متوقف نمی‌شود.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent

from bot import texts

log = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    exception = event.exception
    update = event.update

    # خطای بی‌خطر: تلاش برای ویرایش پیام با همان محتوا
    if isinstance(exception, TelegramBadRequest) and "message is not modified" in str(exception):
        return True

    user_id = None
    if update.message and update.message.from_user:
        user_id = update.message.from_user.id
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
    log.error(
        "Unhandled error in update %s (user %s): %r", update.update_id, user_id, exception, exc_info=exception
    )

    try:
        if update.callback_query:
            await update.callback_query.answer(texts.ERROR, show_alert=True)
        elif update.message:
            await update.message.answer(texts.ERROR)
    except Exception:  # noqa: BLE001 - ارسال پیام خطا نباید خطای جدید ایجاد کند
        pass
    return True
