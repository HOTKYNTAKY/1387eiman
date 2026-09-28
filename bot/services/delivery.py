"""
ارسال اطلاعات سرویس (کانفیگ‌ها، لینک ساب و QR کد) به کاربر
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import BufferedInputFile

from bot.database.models import Server, Subscription, now_ts
from bot.database.models import SubStatus
from bot.services.panels import ClientUsage
from bot.utils.formatting import (
    fmt_bytes,
    fmt_date,
    fmt_duration,
    fmt_traffic,
    h,
    progress_bar,
    split_text,
)
from bot.utils.qrcode import make_qr_png

if TYPE_CHECKING:
    from bot.config import Config
    from bot.database import Database

log = logging.getLogger(__name__)


def subscription_text(sub: Subscription, server: Server | None, config: Config, *, header: str) -> str:
    """متن کامل تحویل سرویس."""
    lines = [
        header,
        "",
        f"🆔 شماره سرویس: <code>#{sub.id}</code>",
        f"📦 پلن: {h(sub.title)}",
    ]
    if server is not None:
        lines.append(f"🌍 سرور: {h(server.name)}")
    lines += [
        f"📅 تاریخ انقضا: {fmt_date(sub.expires_at, config.timezone)}",
        f"⌛️ زمان باقی‌مانده: {fmt_duration(sub.expires_at - now_ts())}",
        f"📊 حجم: {fmt_traffic(sub.traffic_gb)}",
    ]
    if sub.sub_link:
        lines += ["", "🔗 <b>لینک اشتراک (Subscription):</b>", f"<code>{h(sub.sub_link)}</code>"]
    configs = sub.config_lines()
    if configs:
        lines += ["", "📋 <b>کانفیگ‌ها</b> (برای کپی، روی متن بزنید):"]
        lines += [f"<code>{h(item)}</code>" for item in configs]
    lines += ["", "📚 آموزش اتصال: دکمه «📚 راهنمای اتصال» در منوی اصلی"]
    return "\n".join(lines)


def subscription_status_text(
    sub: Subscription, server: Server | None, usage: ClientUsage | None, config: Config
) -> str:
    """متن وضعیت سرویس (زمان باقی‌مانده، مصرف و ...)."""
    now = now_ts()
    status = SubStatus.LABELS.get(sub.status, sub.status)
    if sub.status == SubStatus.ACTIVE and sub.expires_at <= now:
        status = SubStatus.LABELS[SubStatus.EXPIRED]
    lines = [
        f"📦 <b>سرویس #{sub.id}</b>",
        "━━━━━━━━━━━━━━",
        f"🔰 وضعیت: {status}",
        f"📦 پلن: {h(sub.title)}",
    ]
    if server is not None:
        lines.append(f"🌍 سرور: {h(server.name)}")
    lines += [
        f"🗓 تاریخ خرید: {fmt_date(sub.started_at, config.timezone)}",
        f"📅 تاریخ انقضا: {fmt_date(sub.expires_at, config.timezone)}",
        f"⌛️ زمان باقی‌مانده: {fmt_duration(sub.expires_at - now)}",
        f"📊 حجم کل: {fmt_traffic(sub.traffic_gb)}",
    ]
    if usage is not None:
        lines.append(f"📉 مصرف‌شده: {fmt_bytes(usage.used_bytes)}")
        if usage.total_bytes > 0:
            left = max(0, usage.total_bytes - usage.used_bytes)
            lines.append(f"📈 باقی‌مانده: {fmt_bytes(left)}")
            lines.append(progress_bar(usage.used_bytes, usage.total_bytes))
        if not usage.enabled and sub.status == SubStatus.ACTIVE:
            lines.append("\n⚠️ این سرویس روی سرور غیرفعال است (احتمالاً حجم آن تمام شده). برای فعال‌سازی تمدید کنید.")
    return "\n".join(lines)


async def send_subscription(
    bot: Bot,
    db: Database,
    config: Config,
    sub: Subscription,
    *,
    header: str = "🎉 <b>سرویس شما آماده است!</b>",
    chat_id: int | None = None,
) -> bool:
    """
    ارسال سرویس برای کاربر (یا چت مشخص‌شده) همراه با QR کد.
    :return: True اگر ارسال موفق بود
    """
    target = chat_id or sub.user_id
    server = await db.servers.get_any(sub.server_id) if sub.server_id else None
    try:
        for chunk in split_text(subscription_text(sub, server, config, header=header)):
            await bot.send_message(target, chunk, disable_web_page_preview=True)

        qr_source = sub.sub_link or (sub.config_lines()[0] if sub.config_lines() else "")
        png = make_qr_png(qr_source) if qr_source else None
        if png:
            caption = "📷 QR کد لینک اشتراک" if sub.sub_link else "📷 QR کد کانفیگ"
            await bot.send_photo(target, BufferedInputFile(png, filename=f"sub_{sub.id}.png"), caption=caption)
        return True
    except TelegramForbiddenError:
        if target == sub.user_id:
            await db.users.set_bot_blocked(sub.user_id, True)
        log.info("User %s has blocked the bot; subscription #%s not delivered", target, sub.id)
        return False
    except TelegramAPIError as exc:
        log.warning("Cannot send subscription #%s to %s: %s", sub.id, target, exc)
        return False
