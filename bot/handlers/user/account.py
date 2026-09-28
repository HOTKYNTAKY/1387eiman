"""حساب کاربری، سفارش‌های من و راهنمای اتصال (سمت کاربر)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.database import Database
from bot.database.models import User
from bot.keyboards.callbacks import AccountCB
from bot.keyboards.user import account_kb, orders_kb
from bot.utils.formatting import fmt_date, fmt_price, h
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="user_account")


async def account_text(db: Database, user: User, config: Config) -> str:
    active = await db.subscriptions.count_active_for_user(user.id)
    purchases, total = await db.orders.user_summary(user.id)
    return (
        "👤 <b>حساب کاربری</b>\n\n"
        f"🆔 آیدی عددی: <code>{user.id}</code>\n"
        f"👤 نام: {h(user.full_name)}\n"
        f"📅 تاریخ عضویت: {fmt_date(user.created_at, config.timezone, with_time=False)}\n"
        f"📦 سرویس‌های فعال: {active}\n"
        f"🧾 تعداد خریدها: {purchases}\n"
        f"💰 مجموع پرداختی: {fmt_price(total)}"
    )


async def show_account(message: Message, db: Database, user: User, config: Config, *, edit: bool = False) -> None:
    text = await account_text(db, user, config)
    if edit:
        await safe_edit(message, text, account_kb())
    else:
        await message.answer(text, reply_markup=account_kb())


async def show_guide(message: Message, db: Database) -> None:
    await message.answer(await db.settings.get("guide_text"), disable_web_page_preview=True)


@router.callback_query(AccountCB.filter(F.action == "home"))
async def cb_home(callback: CallbackQuery, state: FSMContext, db: Database, user: User, config: Config) -> None:
    await state.clear()
    await callback.answer()
    message = callback_message(callback)
    if message:
        await show_account(message, db, user, config, edit=True)


@router.callback_query(AccountCB.filter(F.action == "orders"))
async def cb_orders(callback: CallbackQuery, db: Database, user: User, config: Config) -> None:
    orders = await db.orders.list_for_user(user.id, limit=10)
    await callback.answer()
    if not orders:
        await safe_edit(callback_message(callback), "📭 شما هنوز سفارشی ثبت نکرده‌اید.", account_kb())
        return
    lines = ["🧾 <b>۱۰ سفارش آخر شما</b>", ""]
    for order in orders:
        lines.append(
            f"<b>#{order.id}</b> | {h(order.plan_title)} | {fmt_price(order.amount)}\n"
            f"      {order.kind_label} — {order.status_label} — {fmt_date(order.created_at, config.timezone)}"
        )
    if any(o.status == "pending" for o in orders):
        lines.append("\n💡 برای سفارش‌های پرداخت‌نشده می‌توانید رسید ارسال کنید یا آن‌ها را لغو کنید.")
    await safe_edit(callback_message(callback), "\n".join(lines), orders_kb(orders))
