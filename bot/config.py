"""
بارگذاری تنظیمات برنامه از فایل .env

روند کار:
    1. فایل .env خوانده می‌شود (متغیرهای محیطی سیستم در صورت وجود اولویت دارند).
    2. اگر توکن ربات یا آیدی ادمین تنظیم نشده باشد و برنامه در ترمینال (حالت
       تعاملی) اجرا شده باشد، ویزارد راه‌اندازی اولیه اجرا می‌شود تا این مقادیر
       از کاربر گرفته و در .env ذخیره شوند.
    3. در حالت غیرتعاملی (مثلاً اجرا توسط systemd) خطای واضحی نمایش داده می‌شود.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

# پوشه اصلی پروژه (یک سطح بالاتر از پکیج bot)
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"

# الگوی توکن ربات تلگرام؛ مثال: 123456789:AAH-abcdefghijklmnopqrstuvwxyz12345
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")

# کلیدهایی که از .env یا متغیرهای محیطی خوانده می‌شوند
KNOWN_KEYS = (
    "BOT_TOKEN",
    "ADMIN_ID",
    "TIMEZONE",
    "BACKUP_TIME",
    "BACKUP_KEEP",
    "DB_PATH",
    "BACKUP_DIR",
    "LOG_DIR",
    "LOG_LEVEL",
    "PROXY_URL",
    "PANEL_VERIFY_SSL",
)


class ConfigError(Exception):
    """خطای مربوط به تنظیمات نامعتبر یا ناقص."""


@dataclass(frozen=True)
class Config:
    """تمام تنظیمات موردنیاز برنامه (فقط‌خواندنی)."""

    bot_token: str
    admin_ids: tuple[int, ...]
    timezone: ZoneInfo
    backup_time: time
    backup_keep: int
    db_path: Path
    backup_dir: Path
    log_dir: Path
    log_level: str
    proxy_url: str | None
    panel_verify_ssl: bool

    @property
    def owner_id(self) -> int:
        """آیدی مالک اصلی ربات (اولین آیدی در ADMIN_ID)."""
        return self.admin_ids[0]

    def is_admin(self, user_id: int | None) -> bool:
        """بررسی می‌کند که کاربر جزو ادمین‌ها باشد."""
        return user_id is not None and user_id in self.admin_ids


# ----------------------------------------------------------------------
# توابع کمکی اعتبارسنجی و تبدیل مقادیر
# ----------------------------------------------------------------------


def is_valid_token(token: str | None) -> bool:
    """فرمت توکن ربات را بررسی می‌کند (بدون تماس با تلگرام)."""
    return bool(token) and bool(TOKEN_RE.match(token.strip()))


def parse_admin_ids(raw: str | None) -> tuple[int, ...]:
    """
    رشته آیدی‌ها را به تاپل اعداد تبدیل می‌کند.
    ورودی نامعتبر یک تاپل خالی برمی‌گرداند.
        "123, 456" -> (123, 456)
    """
    if not raw:
        return ()
    ids: list[int] = []
    for part in re.split(r"[,\s]+", raw.strip()):
        if not part:
            continue
        if not part.isdigit() or int(part) <= 0:
            return ()
        value = int(part)
        if value not in ids:
            ids.append(value)
    return tuple(ids)


def _resolve_path(value: str | None, default: str) -> Path:
    """مسیرهای نسبی را نسبت به پوشه پروژه تبدیل به مسیر مطلق می‌کند."""
    path = Path((value or "").strip() or default).expanduser()
    return path if path.is_absolute() else (BASE_DIR / path)


def _parse_time(value: str | None) -> time:
    """رشته HH:MM را به time تبدیل می‌کند؛ پیش‌فرض ۰۰:۰۰."""
    raw = (value or "").strip() or "00:00"
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        raise ConfigError(f"BACKUP_TIME نامعتبر است: {raw!r} (فرمت صحیح: HH:MM)")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ConfigError(f"BACKUP_TIME نامعتبر است: {raw!r}")
    return time(hour=hour, minute=minute)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _parse_int(value: str | None, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int((value or "").strip() or default))
    except ValueError:
        return default


def read_env(env_path: Path = ENV_PATH) -> dict[str, str]:
    """
    مقادیر .env را می‌خواند. متغیرهای محیطی سیستم (مثلاً تعریف‌شده در systemd)
    مقادیر فایل را بازنویسی می‌کنند.
    """
    values: dict[str, str] = {}
    if env_path.exists():
        for key, value in dotenv_values(env_path).items():
            if value is not None:
                values[key] = value
    for key in KNOWN_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def _credentials_ok(values: dict[str, str]) -> bool:
    return is_valid_token(values.get("BOT_TOKEN")) and bool(parse_admin_ids(values.get("ADMIN_ID")))


def load_config(env_path: Path = ENV_PATH, *, allow_wizard: bool = True) -> Config:
    """
    تنظیمات را بارگذاری می‌کند و در صورت نیاز ویزارد راه‌اندازی را اجرا می‌کند.

    :param allow_wizard: اگر True باشد و ترمینال تعاملی در دسترس باشد،
                         برای مقادیر ناقص از کاربر سؤال می‌پرسد.
    :raises ConfigError: وقتی تنظیمات ناقص/نامعتبر است و امکان پرسیدن وجود ندارد.
    """
    values = read_env(env_path)

    if not _credentials_ok(values):
        if allow_wizard and sys.stdin is not None and sys.stdin.isatty():
            # اجرای اولیه: گرفتن توکن و آیدی ادمین از کاربر و ذخیره در .env
            from bot.setup_wizard import run_wizard

            run_wizard(env_path)
            values = read_env(env_path)

        if not _credentials_ok(values):
            raise ConfigError(
                "توکن ربات (BOT_TOKEN) یا آیدی عددی ادمین (ADMIN_ID) تنظیم نشده یا نامعتبر است.\n"
                "برای تنظیم، این دستور را در پوشه پروژه اجرا کنید:\n"
                "    .venv/bin/python -m bot --setup\n"
                "BOT_TOKEN or ADMIN_ID is missing. Run: .venv/bin/python -m bot --setup"
            )

    tz_name = (values.get("TIMEZONE") or "Asia/Tehran").strip()
    try:
        timezone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"منطقه زمانی نامعتبر است: {tz_name!r} (مثال صحیح: Asia/Tehran)") from exc

    log_level = (values.get("LOG_LEVEL") or "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "INFO"

    return Config(
        bot_token=values["BOT_TOKEN"].strip(),
        admin_ids=parse_admin_ids(values["ADMIN_ID"]),
        timezone=timezone,
        backup_time=_parse_time(values.get("BACKUP_TIME")),
        backup_keep=_parse_int(values.get("BACKUP_KEEP"), default=14, minimum=1),
        db_path=_resolve_path(values.get("DB_PATH"), "data/bot.db"),
        backup_dir=_resolve_path(values.get("BACKUP_DIR"), "backups"),
        log_dir=_resolve_path(values.get("LOG_DIR"), "logs"),
        log_level=log_level,
        proxy_url=(values.get("PROXY_URL") or "").strip() or None,
        panel_verify_ssl=_parse_bool(values.get("PANEL_VERIFY_SSL"), default=False),
    )
