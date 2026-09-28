"""
ثبت روترها به ترتیب اولویت:

    1. errors   : مدیریت سراسری خطاها
    2. common   : /start، /cancel و دکمه‌های منوی اصلی (در هر حالتی کار می‌کنند)
    3. admin    : پنل مدیریت (فقط برای ادمین‌ها)
    4. user     : خرید، سرویس‌ها، پشتیبانی و حساب کاربری
    5. fallback : پیام‌ها و دکمه‌های ناشناخته
"""

from aiogram import Router

from bot.handlers import common, errors, fallback
from bot.handlers.admin import get_admin_router
from bot.handlers.user import get_user_router


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_routers(
        errors.router,
        common.router,
        get_admin_router(),
        get_user_router(),
        fallback.router,
    )
    return root
