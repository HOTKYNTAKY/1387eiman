"""هندلرهای بخش کاربر."""

from aiogram import Router

from bot.handlers.user import account, buy, services, support


def get_user_router() -> Router:
    router = Router(name="user")
    router.include_routers(buy.router, services.router, support.router, account.router)
    return router
