"""
بکاپ و ریستور از داخل ربات

    /backup  یا دکمه «💾 دریافت بکاپ فوری»   → ساخت و ارسال فوری فایل بکاپ
    /restore یا دکمه «♻️ ریستور از فایل بکاپ» → ارسال فایل بکاپ و تایید برای جایگزینی دیتابیس
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from bot.config import Config
from bot.database import Database
from bot.keyboards.admin import admin_cancel_kb, back_kb, backup_kb, restore_confirm_kb
from bot.keyboards.callbacks import ABackupCB, AdminCB
from bot.services.backup import (
    MAX_UPLOAD_SIZE,
    BackupError,
    backup_caption,
    cleanup_old_backups,
    create_backup,
    inspect_backup,
    restore_backup,
)
from bot.services.scheduler import Scheduler
from bot.states import RestoreStates
from bot.utils.formatting import fmt_date, h
from bot.utils.telegram import callback_message, safe_edit

log = logging.getLogger(__name__)
router = Router(name="admin_backup")

RESTORE_UPLOAD_NAME = ".restore_upload.tmp"


def upload_path(config: Config) -> Path:
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    return config.backup_dir / RESTORE_UPLOAD_NAME


async def backup_page(config: Config, scheduler: Scheduler | None) -> tuple[str, InlineKeyboardMarkup]:
    files = sorted(config.backup_dir.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if config.backup_dir.exists() else []
    lines = [
        "💾 <b>بکاپ و ریستور</b>",
        "",
        f"⏰ بکاپ خودکار: هر روز ساعت <b>{config.backup_time.strftime('%H:%M')}</b> ({config.timezone.key})",
    ]
    if scheduler is not None and "daily_backup" in scheduler.next_runs:
        lines.append(f"⏭ بکاپ بعدی: {fmt_date(int(scheduler.next_runs['daily_backup'].timestamp()), config.timezone)}")
    lines.append(f"🗂 بکاپ‌های روی سرور: {len(files)} (حداکثر {config.backup_keep})")
    if files:
        lines.append(f"🕒 آخرین بکاپ: {fmt_date(int(files[0].stat().st_mtime), config.timezone)}")
    lines += ["", "فایل‌های بکاپ برای همه ادمین‌ها ارسال می‌شوند.", "دستورات سریع: /backup و /restore"]
    return "\n".join(lines), backup_kb()


@router.callback_query(AdminCB.filter(F.section == "backup"))
async def cb_backup_page(
    callback: CallbackQuery, state: FSMContext, config: Config, scheduler: Scheduler | None = None
) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await backup_page(config, scheduler)
    await safe_edit(callback_message(callback), text, markup)


async def _send_backup(message: Message, bot: Bot, db: Database, config: Config) -> None:
    status = await message.answer("⏳ در حال ساخت بکاپ...")
    try:
        path = await create_backup(db, config)
        caption = await backup_caption(db, config, path, "بکاپ دستی")
        await bot.send_document(message.chat.id, FSInputFile(path, filename=path.name), caption=caption)
        cleanup_old_backups(config.backup_dir, config.backup_keep)
        await status.delete()
    except Exception as exc:
        log.exception("Manual backup failed")
        await safe_edit(status, f"❌ ساخت بکاپ ناموفق بود:\n<code>{h(exc)}</code>")


@router.message(Command("backup"))
async def cmd_backup(message: Message, state: FSMContext, bot: Bot, db: Database, config: Config) -> None:
    await state.clear()
    await _send_backup(message, bot, db, config)


@router.callback_query(ABackupCB.filter(F.action == "now"))
async def cb_backup_now(callback: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    await callback.answer()
    message = callback_message(callback)
    if message:
        await _send_backup(message, bot, db, config)


# ----------------------------------------------------------------------
# ریستور
# ----------------------------------------------------------------------
RESTORE_PROMPT = (
    "♻️ <b>ریستور دیتابیس</b>\n\n"
    "فایل بکاپ (<code>.zip</code> ساخته‌شده توسط همین ربات) را به صورت <b>فایل</b> ارسال کنید.\n"
    "⚠️ پس از تایید، تمام اطلاعات فعلی ربات با اطلاعات بکاپ جایگزین می‌شود "
    "(قبل از آن یک بکاپ ایمنی از وضعیت فعلی گرفته می‌شود)."
)


@router.message(Command("restore"))
async def cmd_restore(message: Message, state: FSMContext) -> None:
    await state.set_state(RestoreStates.file)
    await message.answer(RESTORE_PROMPT, reply_markup=admin_cancel_kb())


@router.callback_query(ABackupCB.filter(F.action == "restore"))
async def cb_restore(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(RestoreStates.file)
    await safe_edit(callback_message(callback), RESTORE_PROMPT, admin_cancel_kb())


@router.message(RestoreStates.file, F.document)
async def restore_file(message: Message, state: FSMContext, bot: Bot, config: Config) -> None:
    document = message.document
    assert document is not None
    if (document.file_size or 0) > MAX_UPLOAD_SIZE:
        await message.answer(
            "⚠️ حجم فایل بیش از ۲۰ مگابایت است و ربات نمی‌تواند آن را دانلود کند.\n"
            "برای فایل‌های بزرگ از ریستور در سرور استفاده کنید:\n"
            "<code>.venv/bin/python -m bot --restore backups/FILE.zip</code>"
        )
        return
    status = await message.answer("⏳ در حال دریافت و بررسی فایل...")
    target = upload_path(config)
    try:
        await bot.download(document, destination=target)
        with tempfile.TemporaryDirectory(prefix="vpnbot_check_") as tmp:
            _candidate, stats = await inspect_backup(target, Path(tmp))
    except BackupError as exc:
        target.unlink(missing_ok=True)
        await safe_edit(status, f"❌ فایل بکاپ معتبر نیست:\n{h(exc)}\n\nفایل دیگری بفرستید یا /cancel بزنید.")
        return
    except Exception as exc:
        target.unlink(missing_ok=True)
        log.exception("Cannot process uploaded backup")
        await safe_edit(status, f"❌ خطا در پردازش فایل: <code>{h(exc)}</code>")
        return

    await state.set_state(RestoreStates.confirm)
    await safe_edit(
        status,
        "📋 <b>فایل بکاپ معتبر است</b>\n\n"
        f"📄 نام فایل: <code>{h(document.file_name or '-')}</code>\n"
        f"👥 کاربران: {stats['users']}\n"
        f"📦 سرویس‌ها: {stats['subscriptions']}\n"
        f"🧾 سفارش‌ها: {stats['orders']}\n\n"
        "⚠️ <b>با تایید، تمام اطلاعات فعلی جایگزین می‌شود.</b> ادامه می‌دهید؟",
        restore_confirm_kb(),
    )


@router.message(RestoreStates.file)
async def restore_not_file(message: Message) -> None:
    await message.answer("⚠️ لطفاً فایل بکاپ را به صورت «فایل» (Document) ارسال کنید. برای لغو: /cancel")


@router.callback_query(ABackupCB.filter(F.action == "confirm"), RestoreStates.confirm)
async def cb_restore_confirm(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    await state.clear()
    target = upload_path(config)
    if not target.exists():
        await callback.answer("فایل بکاپ پیدا نشد؛ دوباره ارسال کنید.", show_alert=True)
        return
    await callback.answer("⏳ در حال ریستور...")
    message = callback_message(callback)
    try:
        stats, safety = await restore_backup(db, config, target)
    except Exception as exc:
        log.exception("Restore failed")
        await safe_edit(message, f"❌ ریستور ناموفق بود؛ اطلاعات فعلی دست‌نخورده باقی ماند.\n<code>{h(exc)}</code>", back_kb())
        return
    finally:
        target.unlink(missing_ok=True)
    log.warning("Database restored by admin %s", callback.from_user.id)
    await safe_edit(
        message,
        "✅ <b>ریستور با موفقیت انجام شد.</b>\n\n"
        f"👥 کاربران: {stats['users']}\n📦 سرویس‌ها: {stats['subscriptions']}\n🧾 سفارش‌ها: {stats['orders']}\n\n"
        f"🛟 بکاپ ایمنی از وضعیت قبلی: <code>{h(safety.name)}</code>\n"
        "ℹ️ توکن ربات و آیدی ادمین‌ها در فایل .env هستند و با ریستور تغییر نمی‌کنند.",
        back_kb(),
    )
