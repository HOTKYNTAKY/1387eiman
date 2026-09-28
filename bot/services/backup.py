"""
بکاپ و ریستور دیتابیس

بکاپ:
    - با backup API رسمی SQLite یک کپی سالم از دیتابیس (حتی حین کار ربات) گرفته
      و در یک فایل zip فشرده می‌شود: backups/backup_YYYY-MM-DD_HH-MM-SS.zip
    - فایل برای همه ادمین‌ها ارسال و فقط N بکاپ آخر روی سرور نگه داشته می‌شود.

ریستور:
    - فایل ارسالی ادمین (zip / db / gz) بررسی می‌شود: سالم بودن ساختار SQLite
      (integrity_check) و وجود جدول‌های اصلی ربات.
    - قبل از جایگزینی، یک بکاپ ایمنی (pre_restore_*.zip) از وضعیت فعلی گرفته می‌شود.
    - جایگزینی بدون نیاز به ری‌استارت انجام و در پایان مهاجرت‌های ساختار اجرا می‌شود.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile

from bot.database.schema import REQUIRED_TABLES
from bot.utils.formatting import fmt_date, h
from bot.utils.telegram import notify_admins

if TYPE_CHECKING:
    from bot.config import Config
    from bot.database import Database

log = logging.getLogger(__name__)

# محدودیت دانلود فایل توسط ربات در API تلگرام
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
# محدودیت ارسال فایل توسط ربات
MAX_SEND_SIZE = 49 * 1024 * 1024
# حداکثر حجم دیتابیس بعد از استخراج (محافظت در برابر فایل‌های مخرب)
MAX_EXTRACTED_SIZE = 1024 * 1024 * 1024

SQLITE_MAGIC = b"SQLite format 3\x00"
ZIP_MAGIC = b"PK\x03\x04"
GZIP_MAGIC = b"\x1f\x8b"

DB_NAME_IN_ZIP = "bot.db"


class BackupError(Exception):
    """فایل بکاپ نامعتبر است یا عملیات بکاپ/ریستور ناموفق بود."""


# ----------------------------------------------------------------------
# ساخت بکاپ
# ----------------------------------------------------------------------
async def create_backup(db: Database, config: Config, *, prefix: str = "backup") -> Path:
    """ساخت فایل zip بکاپ و برگرداندن مسیر آن."""
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(config.timezone).strftime("%Y-%m-%d_%H-%M-%S")
    zip_path = config.backup_dir / f"{prefix}_{stamp}.zip"
    tmp_db = config.backup_dir / f".{prefix}_{stamp}.db.tmp"
    try:
        await db.backup_to(tmp_db)
        await asyncio.to_thread(_zip_single_file, tmp_db, zip_path, DB_NAME_IN_ZIP)
    finally:
        tmp_db.unlink(missing_ok=True)
    try:
        zip_path.chmod(0o600)
    except OSError:
        pass
    log.info("Backup created: %s (%d bytes)", zip_path.name, zip_path.stat().st_size)
    return zip_path


def _zip_single_file(source: Path, destination: Path, arcname: str) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.write(source, arcname=arcname)


def cleanup_old_backups(backup_dir: Path, keep: int) -> int:
    """حذف بکاپ‌های قدیمی؛ فقط `keep` فایل آخر هر نوع (عادی/ایمنی) نگه داشته می‌شود."""
    removed = 0
    for prefix in ("backup_", "pre_restore_"):
        files = sorted(
            (p for p in backup_dir.glob(f"{prefix}*.zip") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in files[keep:]:
            try:
                old.unlink()
                removed += 1
            except OSError as exc:
                log.warning("Cannot delete old backup %s: %s", old, exc)
    return removed


async def backup_caption(db: Database, config: Config, path: Path, title: str) -> str:
    users = await db.users.count()
    active = await db.subscriptions.count_active()
    orders = await db.fetchval("SELECT COUNT(*) FROM orders", default=0)
    size_kb = path.stat().st_size / 1024
    return (
        f"💾 <b>{h(title)}</b>\n\n"
        f"🕒 زمان: {fmt_date(int(path.stat().st_mtime), config.timezone)}\n"
        f"👥 کاربران: {users}\n"
        f"📦 سرویس‌های فعال: {active}\n"
        f"🧾 سفارش‌ها: {orders}\n"
        f"📁 حجم فایل: {size_kb:.1f} KB\n\n"
        "♻️ برای ریستور، دستور /restore را بزنید و همین فایل را ارسال کنید."
    )


async def send_backup_to_admins(bot: Bot, db: Database, config: Config, *, title: str) -> Path:
    """ساخت بکاپ، ارسال برای همه ادمین‌ها و پاکسازی بکاپ‌های قدیمی."""
    path = await create_backup(db, config)
    removed = cleanup_old_backups(config.backup_dir, config.backup_keep)
    if path.stat().st_size > MAX_SEND_SIZE:
        size_mb = path.stat().st_size / 1024 / 1024
        await notify_admins(
            bot,
            config,
            f"⚠️ حجم بکاپ ({size_mb:.1f} MB) بیشتر از محدودیت ارسال فایل تلگرام است؛ "
            f"فایل فقط روی سرور ذخیره شد:\n<code>{h(path)}</code>",
        )
        return path
    caption = await backup_caption(db, config, path, title)
    delivered = 0
    for admin_id in config.admin_ids:
        try:
            await bot.send_document(admin_id, FSInputFile(path, filename=path.name), caption=caption)
            delivered += 1
        except TelegramAPIError as exc:
            log.error("Cannot send backup to admin %s: %s", admin_id, exc)
    log.info("Backup sent to %d/%d admins, %d old backups removed", delivered, len(config.admin_ids), removed)
    return path


# ----------------------------------------------------------------------
# ریستور
# ----------------------------------------------------------------------
def extract_database(source: Path, work_dir: Path) -> Path:
    """
    فایل بکاپ را براساس محتوا (نه پسوند) تشخیص و فایل دیتابیس را استخراج می‌کند.
    پشتیبانی: zip (خروجی همین ربات)، gz، فایل خام SQLite
    """
    with source.open("rb") as handle:
        header = handle.read(16)

    target = work_dir / "restore_candidate.db"
    if header.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(source) as archive:
                members = [m for m in archive.infolist() if not m.is_dir()]
                preferred = [m for m in members if m.filename.lower().endswith((".db", ".sqlite", ".sqlite3"))]
                member = (preferred or members or [None])[0]
                if member is None:
                    raise BackupError("فایل zip خالی است.")
                if member.file_size > MAX_EXTRACTED_SIZE:
                    raise BackupError("حجم دیتابیس داخل فایل بیش از حد مجاز است.")
                with archive.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as exc:
            raise BackupError("فایل zip خراب است.") from exc
    elif header.startswith(GZIP_MAGIC):
        try:
            with gzip.open(source, "rb") as src, target.open("wb") as dst:
                copied = 0
                while chunk := src.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > MAX_EXTRACTED_SIZE:
                        raise BackupError("حجم دیتابیس داخل فایل بیش از حد مجاز است.")
                    dst.write(chunk)
        except (OSError, EOFError) as exc:
            raise BackupError("فایل gz خراب است.") from exc
    elif header.startswith(SQLITE_MAGIC):
        shutil.copyfile(source, target)
    else:
        raise BackupError("فرمت فایل پشتیبانی نمی‌شود. فایل بکاپ zip یا db همین ربات را ارسال کنید.")

    with target.open("rb") as handle:
        if handle.read(16) != SQLITE_MAGIC:
            raise BackupError("فایل ارسالی دیتابیس SQLite نیست.")
    return target


def validate_database(path: Path) -> dict[str, int]:
    """
    بررسی سلامت و سازگاری دیتابیس بکاپ.
    :return: آمار مختصر (تعداد کاربران، سرویس‌ها، سفارش‌ها)
    """
    try:
        con = sqlite3.connect(str(path))
    except sqlite3.Error as exc:
        raise BackupError(f"باز کردن دیتابیس ممکن نیست: {exc}") from exc
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise BackupError("دیتابیس بکاپ آسیب دیده است (integrity_check ناموفق).")
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise BackupError("این فایل بکاپ مربوط به این ربات نیست (جدول‌های اصلی وجود ندارند).")
        return {
            "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "subscriptions": con.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0],
            "orders": con.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        }
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"فایل دیتابیس معتبر نیست: {exc}") from exc
    finally:
        con.close()


async def inspect_backup(source: Path, work_dir: Path) -> tuple[Path, dict[str, int]]:
    """استخراج و اعتبارسنجی فایل بکاپ (بدون اعمال)."""
    candidate = await asyncio.to_thread(extract_database, source, work_dir)
    stats = await asyncio.to_thread(validate_database, candidate)
    return candidate, stats


async def restore_backup(db: Database, config: Config, source: Path) -> tuple[dict[str, int], Path]:
    """
    ریستور کامل از فایل بکاپ.
    :return: (آمار بکاپ ریستورشده، مسیر بکاپ ایمنی از وضعیت قبلی)
    """
    with tempfile.TemporaryDirectory(prefix="vpnbot_restore_") as tmp:
        candidate, stats = await inspect_backup(source, Path(tmp))
        safety = await create_backup(db, config, prefix="pre_restore")
        await db.restore_from(candidate)
    log.warning("Database restored from %s (safety backup: %s)", source.name, safety.name)
    return stats, safety
