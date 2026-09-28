"""
راه‌اندازی و اجرای ربات

ساخت Bot و Dispatcher، اتصال دیتابیس، ثبت میدل‌ورها و روترها، زمان‌بندی کارها
(بکاپ روزانه و بررسی سرویس‌ها) و شروع دریافت پیام‌ها (long polling).
"""

from __future__ import annotations

import logging
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot import __version__
from bot.config import Config
from bot.database import Database
from bot.handlers import setup_routers
from bot.middlewares import ThrottlingMiddleware, UserMiddleware
from bot.services.jobs import daily_backup_job, subscription_check_job
from bot.services.provisioning import Provisioner
from bot.services.scheduler import Scheduler

log = logging.getLogger(__name__)

# کد خروج برای خطاهای تنظیمات (systemd با این کد ربات را دوباره اجرا نمی‌کند)
EXIT_CONFIG_ERROR = 2

USER_COMMANDS = [
    BotCommand(command="start", description="🏠 منوی اصلی"),
    BotCommand(command="id", description="🆔 نمایش آیدی عددی من"),
    BotCommand(command="cancel", description="❌ لغو عملیات جاری"),
]
ADMIN_COMMANDS = [
    *USER_COMMANDS,
    BotCommand(command="admin", description="⚙️ پنل مدیریت"),
    BotCommand(command="backup", description="💾 دریافت بکاپ فوری"),
    BotCommand(command="restore", description="♻️ ریستور از فایل بکاپ"),
]


class StartupError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def create_bot(config: Config) -> Bot:
    session = AiohttpSession(proxy=config.proxy_url) if config.proxy_url else AiohttpSession()
    return Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


def create_dispatcher(config: Config, db: Database, *, throttle_rate: float = 0.4) -> Dispatcher:
    """ساخت Dispatcher به همراه وابستگی‌ها، میدل‌ورها و روترها."""
    dp = Dispatcher(storage=MemoryStorage())
    # این مقادیر به صورت خودکار به پارامترهای هم‌نام هندلرها تزریق می‌شوند
    dp["config"] = config
    dp["db"] = db
    dp["provisioner"] = Provisioner(db, config)

    throttling = ThrottlingMiddleware(rate=throttle_rate, admin_ids=config.admin_ids)
    user_middleware = UserMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttling)
        observer.outer_middleware(user_middleware)

    dp.include_router(setup_routers())
    return dp


async def _set_commands(bot: Bot, config: Config) -> None:
    try:
        await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    except TelegramAPIError as exc:
        log.warning("Cannot set default commands: %s", exc)
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as exc:
            # معمولاً یعنی ادمین هنوز ربات را استارت نکرده است
            log.warning("Cannot set admin commands for %s (has the admin started the bot?): %s", admin_id, exc)


async def run_bot(config: Config) -> None:
    db = Database(config.db_path)
    await db.connect()
    bot = create_bot(config)
    dp = create_dispatcher(config, db)

    scheduler = Scheduler(config.timezone)
    scheduler.daily(config.backup_time, partial(daily_backup_job, bot, db, config), "daily_backup")
    scheduler.interval(1800, partial(subscription_check_job, bot, db, config), "subscription_check", first_delay=20)
    dp["scheduler"] = scheduler

    try:
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError as exc:
            raise StartupError(
                "توکن ربات نامعتبر است. با دستور `python -m bot --setup` توکن صحیح را وارد کنید. "
                "(Invalid bot token)",
                EXIT_CONFIG_ERROR,
            ) from exc
        except TelegramNetworkError as exc:
            raise StartupError(
                "اتصال به سرورهای تلگرام برقرار نشد. اگر سرور شما به تلگرام دسترسی ندارد، "
                "PROXY_URL را در فایل .env تنظیم کنید. (Cannot reach api.telegram.org)"
            ) from exc

        log.info("Bot @%s (id=%s) started — version %s", me.username, me.id, __version__)
        await _set_commands(bot, config)
        await bot.delete_webhook(drop_pending_updates=False)
        scheduler.start()

        for admin_id in config.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"✅ ربات روشن شد (نسخه {__version__})\n"
                    f"⏰ بکاپ خودکار: هر روز ساعت {config.backup_time.strftime('%H:%M')} ({config.timezone.key})",
                )
            except TelegramAPIError:
                log.warning("Admin %s has not started the bot yet; send /start to the bot.", admin_id)

        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=True)
    finally:
        await scheduler.stop()
        await bot.session.close()
        await db.close()
        log.info("Bot stopped")
