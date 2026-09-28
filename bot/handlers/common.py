"""
هندلرهای عمومی: /start، /cancel، /id، /help و دکمه‌های منوی اصلی

این روتر قبل از بقیه ثبت می‌شود؛ بنابراین دکمه‌های منوی اصلی در هر حالتی (حتی
وسط پر کردن یک فرم) کار می‌کنند و حالت قبلی را پاک می‌کنند.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import Config
from bot.database import Database
from bot.database.models import User
from bot.handlers.user.account import show_account, show_guide
from bot.handlers.user.buy import show_servers
from bot.handlers.user.services import show_renew_list, show_services
from bot.handlers.user.support import show_support
from bot.keyboards.callbacks import CancelCB
from bot.keyboards.user import main_menu
from bot.texts import Btn
from bot.utils.formatting import h
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, is_admin: bool) -> None:
    await state.clear()
    welcome = await db.settings.get("welcome_text")
    first_name = message.from_user.first_name if message.from_user else ""
    await message.answer(welcome.replace("{name}", h(first_name)), reply_markup=main_menu(is_admin))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, is_admin: bool) -> None:
    await state.clear()
    await message.answer(texts.CANCELED, reply_markup=main_menu(is_admin))


@router.callback_query(CancelCB.filter())
async def cb_cancel(
    callback: CallbackQuery, callback_data: CancelCB, state: FSMContext, db: Database, is_admin: bool
) -> None:
    await state.clear()
    await callback.answer("لغو شد")
    if callback_data.to == "admin" and is_admin:
        # بازگشت به پنل مدیریت
        from bot.handlers.admin.menu import admin_home

        text, markup = await admin_home(db)
        await safe_edit(callback_message(callback), text, markup)
    else:
        await safe_edit(callback_message(callback), texts.CANCELED)


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    await message.answer(f"🆔 آیدی عددی شما: <code>{user_id}</code>")


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await show_guide(message, db)


# ----------------------------------------------------------------------
# دکمه‌های منوی اصلی (در هر حالتی فعال هستند)
# ----------------------------------------------------------------------
@router.message(F.text == Btn.BUY)
async def menu_buy(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await show_servers(message, db)


@router.message(F.text == Btn.MY_SERVICES)
async def menu_services(message: Message, state: FSMContext, db: Database, user: User) -> None:
    await state.clear()
    await show_services(message, db, user)


@router.message(F.text == Btn.RENEW)
async def menu_renew(message: Message, state: FSMContext, db: Database, user: User) -> None:
    await state.clear()
    await show_renew_list(message, db, user)


@router.message(F.text == Btn.ACCOUNT)
async def menu_account(message: Message, state: FSMContext, db: Database, user: User, config: Config) -> None:
    await state.clear()
    await show_account(message, db, user, config)


@router.message(F.text == Btn.SUPPORT)
async def menu_support(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await show_support(message, db)


@router.message(F.text == Btn.GUIDE)
async def menu_guide(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await show_guide(message, db)
