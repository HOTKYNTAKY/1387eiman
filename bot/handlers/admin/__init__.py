"""
هندلرهای پنل مدیریت

فیلتر IsAdmin روی کل این روتر اعمال شده است؛ بنابراین هیچ‌کدام از این
هندلرها برای کاربرانی که آیدی عددی‌شان در ADMIN_ID نیست اجرا نمی‌شوند.
"""

from aiogram import Router

from bot.filters import IsAdmin
from bot.handlers.admin import backup, broadcast, menu, orders, plans, servers, settings, tickets, users


def get_admin_router() -> Router:
    router = Router(name="admin")
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())
    router.include_routers(
        menu.router,
        orders.router,
        plans.router,
        servers.router,
        users.router,
        tickets.router,
        broadcast.router,
        settings.router,
        backup.router,
    )
    return router
