"""
پیام همگانی

پیام ادمین (هر نوعی: متن، عکس، ویدیو، ...) با copy_message برای کاربران کپی
می‌شود. ارسال در پس‌زمینه با سرعت حدود ۲۰ پیام در ثانیه (زیر محدودیت تلگرام)
انجام و پیشرفت آن به صورت دوره‌ای گزارش می‌شود.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import Database
from bot.keyboards.admin import admin_cancel_kb, back_kb, broadcast_confirm_kb, broadcast_target_kb
from bot.keyboards.callbacks import ABroadcastCB, AdminCB
from bot.states import BroadcastStates
from bot.utils.telegram import callback_message, safe_edit

log = logging.getLogger(__name__)
router = Router(name="admin_broadcast")

SEND_DELAY = 0.05  # ~۲۰ پیام در ثانیه
_running: dict[str, asyncio.Task[None]] = {}


@router.callback_query(AdminCB.filter(F.section == "broadcast"))
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if "task" in _running and not _running["task"].done():
        await safe_edit(callback_message(callback), "⏳ یک پیام همگانی در حال ارسال است؛ لطفاً تا پایان آن صبر کنید.", back_kb())
        return
    await safe_edit(callback_message(callback), "📣 <b>پیام همگانی</b>\n\nپیام برای چه کسانی ارسال شود؟", broadcast_target_kb())


@router.callback_query(ABroadcastCB.filter(F.action == "target"))
async def cb_target(callback: CallbackQuery, callback_data: ABroadcastCB, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BroadcastStates.message)
    await state.update_data(target=callback_data.target)
    await safe_edit(
        callback_message(callback),
        "✍️ پیام خود را بفرستید.\nهر نوع پیامی (متن، عکس، ویدیو، فایل) دقیقاً همان‌طور که هست برای کاربران کپی می‌شود.",
        admin_cancel_kb(),
    )


@router.message(BroadcastStates.message)
async def broadcast_message(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    recipients = await db.users.broadcast_ids(only_active_subscribers=data.get("target") == "active")
    if not recipients:
        await state.clear()
        await message.answer("❗️ هیچ کاربری برای ارسال وجود ندارد.", reply_markup=back_kb())
        return
    await state.update_data(from_chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(BroadcastStates.confirm)
    await message.reply(
        f"📣 پیام بالا برای <b>{len(recipients)}</b> کاربر ارسال شود؟",
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(ABroadcastCB.filter(F.action == "send"), BroadcastStates.confirm)
async def cb_send(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    if "task" in _running and not _running["task"].done():
        await callback.answer("یک ارسال دیگر در جریان است", show_alert=True)
        return
    recipients = await db.users.broadcast_ids(only_active_subscribers=data.get("target") == "active")
    await callback.answer("ارسال شروع شد")
    status = await safe_edit(callback_message(callback), f"📣 ارسال به {len(recipients)} کاربر شروع شد...")
    task = asyncio.create_task(
        run_broadcast(bot, db, int(data["from_chat_id"]), int(data["message_id"]), recipients, status),
        name="broadcast",
    )
    _running["task"] = task  # نگه‌داشتن ارجاع تا تسک توسط garbage collector حذف نشود


async def run_broadcast(
    bot: Bot, db: Database, from_chat_id: int, message_id: int, recipients: list[int], status: Message | None
) -> None:
    sent = blocked = failed = 0
    total = len(recipients)
    for index, user_id in enumerate(recipients, 1):
        for _attempt in range(2):
            try:
                await bot.copy_message(user_id, from_chat_id, message_id)
                sent += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                blocked += 1
                await db.users.set_bot_blocked(user_id, True)
                break
            except TelegramAPIError as exc:
                failed += 1
                log.debug("Broadcast to %s failed: %s", user_id, exc)
                break
        await asyncio.sleep(SEND_DELAY)
        if status is not None and index % 200 == 0:
            await safe_edit(status, f"📣 در حال ارسال... {index}/{total}")

    report = (
        "✅ <b>ارسال پیام همگانی تمام شد</b>\n\n"
        f"📨 موفق: {sent}\n🚫 ربات را بلاک کرده‌اند: {blocked}\n⚠️ ناموفق: {failed}\n👥 کل: {total}"
    )
    log.info("Broadcast finished: sent=%s blocked=%s failed=%s", sent, blocked, failed)
    if status is not None:
        await safe_edit(status, report, back_kb())
