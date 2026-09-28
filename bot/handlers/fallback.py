"""
هندلرهای پیش‌فرض: پیام‌ها و دکمه‌هایی که هیچ هندلر دیگری آن‌ها را پردازش نکرده است.
این روتر باید آخرین روتر ثبت‌شده باشد.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.keyboards.user import main_menu

router = Router(name="fallback")


@router.message(StateFilter(None))
async def unknown_message(message: Message, is_admin: bool) -> None:
    await message.answer(texts.USE_MENU, reply_markup=main_menu(is_admin))


@router.message()
async def unexpected_input(message: Message) -> None:
    """کاربر در یک مرحله (مثلاً فرم) است ولی نوع پیام مورد انتظار نیست."""
    await message.answer("⚠️ ورودی نامعتبر است. لطفاً طبق راهنمای پیام قبل ارسال کنید یا /cancel را بزنید.")


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer(texts.EXPIRED_BUTTON, show_alert=True)
