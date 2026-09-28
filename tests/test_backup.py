"""تست بکاپ و ریستور دیتابیس."""

from __future__ import annotations

import gzip
import sqlite3
import zipfile
from pathlib import Path

import pytest

from bot.database import Database
from bot.services.backup import (
    BackupError,
    cleanup_old_backups,
    create_backup,
    inspect_backup,
    restore_backup,
)

from .conftest import make_config


async def test_backup_is_standalone_and_restorable(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    db = Database(config.db_path)
    await db.connect()
    try:
        await db.users.upsert(1, "ali", "Ali")
        path = await create_backup(db, config)
        assert path.name.startswith("backup_") and path.suffix == ".zip"
        with zipfile.ZipFile(path) as archive:
            assert archive.namelist() == ["bot.db"]
            raw = archive.read("bot.db")
        assert raw.startswith(b"SQLite format 3\x00")
        # فایل داخل بکاپ در حالت WAL نیست (بایت‌های ۱۸ و ۱۹ = 1)
        assert raw[18] == 1 and raw[19] == 1

        # تغییر و سپس ریستور (با اتصال باز)
        await db.users.upsert(2, "reza", "Reza")
        await db.settings.set("card_number", "1111")
        stats, safety = await restore_backup(db, config, path)
        assert stats["users"] == 1 and safety.exists()
        assert await db.users.get(2) is None
        assert await db.users.get(1) is not None
        assert await db.settings.get("card_number") == ""
        # دیتابیس اصلی همچنان WAL و قابل نوشتن است
        assert await db.fetchval("PRAGMA journal_mode") == "wal"
        await db.users.upsert(3, "sara", "Sara")
        assert await db.users.count() == 2
    finally:
        await db.close()


async def test_restore_accepts_raw_db_and_gzip(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    db = Database(config.db_path)
    await db.connect()
    try:
        await db.users.upsert(10, "x", "X")
        backup = await create_backup(db, config)
        with zipfile.ZipFile(backup) as archive:
            raw = archive.read("bot.db")
        raw_path = tmp_path / "plain.sqlite"
        raw_path.write_bytes(raw)
        gz_path = tmp_path / "file.db.gz"
        gz_path.write_bytes(gzip.compress(raw))
        for source in (raw_path, gz_path):
            _candidate, stats = await inspect_backup(source, tmp_path)
            assert stats["users"] == 1
    finally:
        await db.close()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"hello world, not a database", "فرمت فایل"),
        (b"SQLite format 3\x00" + b"\x00" * 100, "معتبر"),
    ],
)
async def test_invalid_files_are_rejected(tmp_path: Path, content: bytes, message: str) -> None:
    bad = tmp_path / "bad.bin"
    bad.write_bytes(content)
    with pytest.raises(BackupError, match=message):
        await inspect_backup(bad, tmp_path)


async def test_foreign_sqlite_database_is_rejected(tmp_path: Path) -> None:
    foreign = tmp_path / "other.db"
    con = sqlite3.connect(foreign)
    con.execute("CREATE TABLE notes (id INTEGER)")
    con.commit()
    con.close()
    archive_path = tmp_path / "other.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(foreign, "other.db")
    with pytest.raises(BackupError, match="مربوط به این ربات نیست"):
        await inspect_backup(archive_path, tmp_path)


def test_cleanup_keeps_latest(tmp_path: Path) -> None:
    import os
    import time

    for index in range(6):
        path = tmp_path / f"backup_2026-01-0{index}.zip"
        path.write_bytes(b"x")
        os.utime(path, (time.time() - 1000 + index, time.time() - 1000 + index))
    (tmp_path / "pre_restore_1.zip").write_bytes(b"x")
    removed = cleanup_old_backups(tmp_path, keep=3)
    assert removed == 3
    remaining = sorted(p.name for p in tmp_path.glob("backup_*.zip"))
    assert remaining == ["backup_2026-01-03.zip", "backup_2026-01-04.zip", "backup_2026-01-05.zip"]
    assert (tmp_path / "pre_restore_1.zip").exists()


async def test_migrations_run_after_restoring_old_schema(tmp_path: Path) -> None:
    """بکاپ نسخه‌های قدیمی‌تر پس از ریستور به ساختار جدید ارتقا پیدا می‌کند."""
    config = make_config(tmp_path)
    db = Database(config.db_path)
    await db.connect()
    try:
        path = await create_backup(db, config)
        # شبیه‌سازی بکاپ قدیمی: حذف یک تنظیم پیش‌فرض و صفر کردن نسخه
        work = tmp_path / "old"
        work.mkdir()
        with zipfile.ZipFile(path) as archive:
            archive.extract("bot.db", work)
        con = sqlite3.connect(work / "bot.db")
        con.execute("DELETE FROM settings WHERE key = 'guide_text'")
        con.execute("PRAGMA user_version = 0")
        con.commit()
        con.close()
        await restore_backup(db, config, work / "bot.db")
        assert await db.fetchval("PRAGMA user_version") == 1
        assert "راهنمای اتصال" in await db.settings.get("guide_text")
    finally:
        await db.close()
