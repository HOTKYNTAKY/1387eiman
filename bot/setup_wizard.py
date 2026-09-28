"""
ویزارد راه‌اندازی اولیه (در ترمینال اجرا می‌شود)

- توکن ربات تلگرام و آیدی عددی مالک را از کاربر می‌گیرد
- در صورت دسترسی به اینترنت، اعتبار توکن را با متد getMe تلگرام بررسی می‌کند
- مقادیر را در فایل .env ذخیره می‌کند (سایر تنظیمات موجود دست‌نخورده می‌مانند)

اجرای دستی:   python -m bot --setup
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import dotenv_values, set_key

from bot.config import ENV_EXAMPLE_PATH, ENV_PATH, is_valid_token, parse_admin_ids

BANNER = r"""
==============================================================
      🤖  VPN Shop Bot - First-time Setup
      ربات فروش فیلترشکن - راه‌اندازی اولیه
==============================================================
"""


def _ask(prompt: str) -> str:
    """یک خط از کاربر می‌خواند؛ در صورت بسته بودن ورودی، برنامه متوقف می‌شود."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n❌ Setup cancelled / راه‌اندازی لغو شد.")
        raise SystemExit(1) from None


def verify_token_online(token: str) -> tuple[bool | None, str]:
    """
    توکن را با متد getMe تلگرام بررسی می‌کند.

    :return: (True, username) اگر معتبر باشد،
             (False, reason) اگر تلگرام توکن را رد کند،
             (None, reason) اگر بررسی ممکن نباشد (مثلاً نبود اینترنت).
    """
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # آدرس ثابت API تلگرام
            data = json.load(response)
        if data.get("ok"):
            return True, data.get("result", {}).get("username", "")
        return False, str(data.get("description", "unknown error"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 404):
            return False, "Unauthorized - token is invalid / توکن نامعتبر است"
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # خطای شبکه، DNS، تایم‌اوت و ...
        return None, str(exc)


def _ensure_env_file(env_path: Path) -> None:
    """اگر .env وجود ندارد، از روی .env.example ساخته می‌شود."""
    if env_path.exists():
        return
    if ENV_EXAMPLE_PATH.exists():
        shutil.copyfile(ENV_EXAMPLE_PATH, env_path)
    else:
        env_path.touch()


def run_wizard(env_path: Path = ENV_PATH) -> None:
    """ویزارد تعاملی گرفتن توکن و آیدی ادمین و ذخیره در .env."""
    print(BANNER)
    existing = dotenv_values(env_path) if env_path.exists() else {}
    current_token = (existing.get("BOT_TOKEN") or "").strip()
    current_admins = (existing.get("ADMIN_ID") or "").strip()

    # ------------------------------------------------------------------
    # مرحله ۱: توکن ربات
    # ------------------------------------------------------------------
    print("1) Bot token from @BotFather  |  توکن ربات را از @BotFather بگیرید")
    if is_valid_token(current_token):
        print(f"   Current token: {current_token[:10]}...  (Enter = keep / برای حفظ، Enter بزنید)")

    while True:
        token = _ask("🔑 BOT_TOKEN: ") or (current_token if is_valid_token(current_token) else "")
        if not is_valid_token(token):
            print("   ❌ Invalid token format / فرمت توکن نامعتبر است. مثال: 123456789:AAH...")
            continue

        ok, info = verify_token_online(token)
        if ok is True:
            print(f"   ✅ Token is valid / توکن معتبر است  →  @{info}")
            break
        if ok is False:
            print(f"   ❌ Telegram rejected this token / تلگرام توکن را رد کرد: {info}")
            continue
        # بررسی آنلاین ممکن نبود (مثلاً سرور به تلگرام دسترسی ندارد)
        print(f"   ⚠️  Could not verify token online ({info}).")
        print("       امکان بررسی آنلاین توکن نبود؛ توکن ذخیره می‌شود.")
        break

    # ------------------------------------------------------------------
    # مرحله ۲: آیدی عددی ادمین
    # ------------------------------------------------------------------
    print("\n2) Your numeric Telegram ID (get it from @userinfobot)")
    print("   آیدی عددی تلگرام خود را از ربات @userinfobot بگیرید (برای چند ادمین با کاما جدا کنید)")
    if parse_admin_ids(current_admins):
        print(f"   Current: {current_admins}  (Enter = keep / برای حفظ، Enter بزنید)")

    while True:
        raw = _ask("👤 ADMIN_ID: ") or current_admins
        admin_ids = parse_admin_ids(raw)
        if admin_ids:
            break
        print("   ❌ Admin ID must be a positive number / آیدی باید یک عدد مثبت باشد (مثال: 123456789)")

    # ------------------------------------------------------------------
    # مرحله ۳: ذخیره در .env
    # ------------------------------------------------------------------
    _ensure_env_file(env_path)
    set_key(str(env_path), "BOT_TOKEN", token, quote_mode="never")
    set_key(str(env_path), "ADMIN_ID", ",".join(str(i) for i in admin_ids), quote_mode="never")
    try:
        os.chmod(env_path, 0o600)  # فقط مالک فایل اجازه خواندن توکن را داشته باشد
    except OSError:
        pass

    print(f"\n✅ Settings saved to {env_path}")
    print("   تنظیمات با موفقیت در فایل .env ذخیره شد.\n")
