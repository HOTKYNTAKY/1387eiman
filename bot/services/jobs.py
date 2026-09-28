"""
کارهای زمان‌بندی‌شده ربات

1. بکاپ روزانه (پیش‌فرض ساعت ۰۰:۰۰) و ارسال فایل برای ادمین‌ها
2. بررسی سرویس‌ها (هر ۳۰ دقیقه):
     - هشدار به کاربرانی که کمتر از ۲۴ ساعت به انقضای سرویسشان مانده
     - علامت‌گذاری سرویس‌های منقضی‌شده و اطلاع به کاربر
     - لغو خودکار سفارش‌هایی که بیش از ۲۴ ساعت بدون پرداخت مانده‌اند
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Bot

from bot.database.models import SubStatus, now_ts
from bot.keyboards.user import renew_now_kb
from bot.services.backup import send_backup_to_admins
from bot.utils.formatting import fmt_date, fmt_duration, h
from bot.utils.telegram import notify_admins, safe_send

if TYPE_CHECKING:
    from bot.config import Config
    from bot.database import Database

log = logging.getLogger(__name__)

WARN_BEFORE_SECONDS = 24 * 3600
STALE_ORDER_SECONDS = 24 * 3600


async def daily_backup_job(bot: Bot, db: Database, config: Config) -> None:
    try:
        await send_backup_to_admins(bot, db, config, title="بکاپ خودکار روزانه")
    except Exception as exc:
        log.exception("Daily backup failed")
        await notify_admins(bot, config, f"⚠️ بکاپ خودکار روزانه ناموفق بود:\n<code>{h(exc)}</code>")


async def subscription_check_job(bot: Bot, db: Database, config: Config) -> None:
    # --- هشدار نزدیک شدن به انقضا ---
    for sub in await db.subscriptions.due_for_warning(WARN_BEFORE_SECONDS):
        remaining = sub.expires_at - now_ts()
        await safe_send(
            bot,
            sub.user_id,
            f"⏰ <b>یادآوری تمدید</b>\n\n"
            f"سرویس <b>#{sub.id}</b> ({h(sub.title)}) کمتر از {fmt_duration(int(remaining))} دیگر منقضی می‌شود.\n"
            f"📅 تاریخ انقضا: {fmt_date(sub.expires_at, config.timezone)}\n\n"
            "برای جلوگیری از قطع شدن، همین حالا تمدید کنید 👇",
            db=db,
            reply_markup=renew_now_kb(sub.id),
        )
        await db.subscriptions.update(sub.id, warned=1)

    # --- سرویس‌های منقضی‌شده ---
    for sub in await db.subscriptions.newly_expired():
        await db.subscriptions.update(sub.id, status=SubStatus.EXPIRED)
        await safe_send(
            bot,
            sub.user_id,
            f"🔴 سرویس <b>#{sub.id}</b> ({h(sub.title)}) منقضی شد.\n\n"
            "برای ادامه استفاده، سرویس خود را تمدید کنید 👇",
            db=db,
            reply_markup=renew_now_kb(sub.id),
        )

    # --- لغو سفارش‌های رهاشده ---
    canceled = await db.orders.cancel_stale(STALE_ORDER_SECONDS)
    if canceled:
        log.info("%d stale pending orders canceled", canceled)
