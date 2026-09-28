"""
پیکربندی سیستم لاگ

- لاگ‌ها هم در خروجی استاندارد (قابل مشاهده با journalctl) و هم در فایل
  logs/bot.log نوشته می‌شوند.
- فایل لاگ به صورت چرخشی است (حداکثر ۵ فایل ۵ مگابایتی) تا دیسک پر نشود.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO", log_dir: Path | None = None, tz: ZoneInfo | None = None) -> None:
    """
    لاگر اصلی برنامه را تنظیم می‌کند.
    :param tz: منطقه زمانی زمان‌های لاگ (مثلاً Asia/Tehran)؛ پیش‌فرض ساعت سیستم
    """
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    if tz is not None:
        formatter.converter = lambda timestamp: datetime.fromtimestamp(timestamp, tz).timetuple()  # type: ignore[method-assign,assignment]
    root = logging.getLogger()
    root.setLevel(level)

    # حذف هندلرهای قبلی (در صورت فراخوانی مجدد)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "bot.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as exc:  # مثلاً نبود دسترسی نوشتن
            root.warning("Cannot create log file in %s: %s", log_dir, exc)

    # کاهش لاگ‌های پرحجم کتابخانه‌ها
    # (aiogram هر آپدیت را در سطح INFO لاگ می‌کند که خیلی شلوغ است)
    if level != "DEBUG":
        logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
