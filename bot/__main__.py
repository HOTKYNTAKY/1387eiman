"""
نقطه ورود برنامه

    python -m bot                   اجرای ربات (در اولین اجرا ویزارد تنظیمات اجرا می‌شود)
    python -m bot --setup           تنظیم/تغییر توکن ربات و آیدی ادمین
    python -m bot --backup          ساخت فایل بکاپ در پوشه backups
    python -m bot --restore FILE    ریستور دیتابیس از فایل بکاپ (ربات باید متوقف باشد)
    python -m bot --check           فقط بررسی کامل بودن تنظیمات .env (کد خروج 0 = سالم)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

from bot import __version__
from bot.config import ENV_PATH, ConfigError, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m bot", description="VPN Shop Telegram Bot / ربات فروش فیلترشکن")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--setup", action="store_true", help="set bot token and admin id / تنظیم توکن و آیدی ادمین")
    group.add_argument("--backup", action="store_true", help="create a local backup file / ساخت بکاپ")
    group.add_argument("--restore", metavar="FILE", help="restore database from a backup file / ریستور از فایل بکاپ")
    group.add_argument("--check", action="store_true", help="validate .env and exit / فقط بررسی تنظیمات")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


async def _cli_backup() -> Path:
    from bot.database import Database
    from bot.services.backup import cleanup_old_backups, create_backup

    config = load_config(allow_wizard=False)
    db = Database(config.db_path)
    await db.connect()
    try:
        path = await create_backup(db, config)
        cleanup_old_backups(config.backup_dir, config.backup_keep)
        return path
    finally:
        await db.close()


async def _cli_restore(source: Path) -> None:
    from bot.database import Database
    from bot.services.backup import inspect_backup, restore_backup

    config = load_config(allow_wizard=False)
    with tempfile.TemporaryDirectory() as tmp:
        _candidate, stats = await inspect_backup(source, Path(tmp))
    print(f"Backup OK: users={stats['users']} subscriptions={stats['subscriptions']} orders={stats['orders']}")
    db = Database(config.db_path)
    await db.connect()
    try:
        _stats, safety = await restore_backup(db, config, source)
        print(f"✅ Restored. Safety backup of the previous data: {safety}")
    finally:
        await db.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # فایل‌هایی که ربات می‌سازد (دیتابیس، بکاپ، لاگ، .env) فقط برای مالک قابل خواندن باشند
    os.umask(0o077)

    if args.setup:
        from bot.setup_wizard import run_wizard

        run_wizard(ENV_PATH)
        print("If the bot runs as a service, restart it:  sudo systemctl restart vpn-bot")
        return 0

    try:
        config = load_config(allow_wizard=not (args.backup or args.restore or args.check))
    except ConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if args.check:
        print(f"✅ Config OK — admins: {', '.join(map(str, config.admin_ids))}, backup at {config.backup_time:%H:%M} {config.timezone.key}")
        return 0

    from bot.app import StartupError, run_bot
    from bot.logger import setup_logging
    from bot.services.backup import BackupError

    setup_logging(config.log_level, config.log_dir, config.timezone)
    log = logging.getLogger("bot")

    try:
        if args.backup:
            path = asyncio.run(_cli_backup())
            print(f"✅ Backup created: {path}")
            return 0
        if args.restore:
            asyncio.run(_cli_restore(Path(args.restore).expanduser().resolve()))
            return 0
        asyncio.run(run_bot(config))
        return 0
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        return 0
    except StartupError as exc:
        log.error("%s", exc)
        return exc.exit_code
    except BackupError as exc:
        log.error("Backup error: %s", exc)
        return 1
    except Exception:  # هر خطای پیش‌بینی‌نشده در راه‌اندازی
        log.exception("Fatal error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
