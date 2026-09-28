"""منوی اصلی پنل مدیریت و آمار."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Config
from bot.database import Database
from bot.database.models import OrderStatus, TicketStatus
from bot.keyboards.admin import admin_menu, back_kb
from bot.keyboards.callbacks import AdminCB
from bot.texts import Btn
from bot.utils.formatting import fmt_price, h, start_of_day
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="admin_menu")


async def admin_home(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    waiting = await db.orders.count_by_status(OrderStatus.WAITING, OrderStatus.PAID)
    open_tickets = await db.tickets.count_by_status(TicketStatus.OPEN)
    notices = []
    if waiting:
        notices.append(f"🧾 {waiting} سفارش منتظر بررسی است.")
    if open_tickets:
        notices.append(f"🎫 {open_tickets} تیکت منتظر پاسخ است.")
    if not await db.servers.list():
        notices.append("💡 برای شروع، از بخش «🖥 سرورها» یک سرور اضافه کنید، سپس پلن بسازید.")
    lines = ["⚙️ <b>پنل مدیریت</b>", "", *notices]
    if notices:
        lines.append("")
    lines.append("یک بخش را انتخاب کنید:")
    return "\n".join(lines), admin_menu(waiting, open_tickets)


@router.message(Command("admin"))
@router.message(F.text == Btn.ADMIN)
async def admin_entry(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, markup = await admin_home(db)
    await message.answer(text, reply_markup=markup)


@router.callback_query(AdminCB.filter(F.section == "home"))
async def cb_home(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await admin_home(db)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(AdminCB.filter(F.section == "stats"))
async def cb_stats(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    tz = config.timezone
    today, week, month = start_of_day(tz), start_of_day(tz, 6), start_of_day(tz, 29)

    sales = {}
    for label, since in (("امروز", today), ("۷ روز اخیر", week), ("۳۰ روز اخیر", month), ("کل", 0)):
        sales[label] = await db.orders.sales_since(since)

    lines = [
        "📊 <b>آمار ربات</b>",
        "",
        "👥 <b>کاربران</b>",
        f"  • کل کاربران: {await db.users.count()}",
        f"  • عضو جدید امروز: {await db.users.count_since(today)}",
        f"  • ۷ روز اخیر: {await db.users.count_since(week)}  |  ۳۰ روز: {await db.users.count_since(month)}",
        f"  • مسدودشده: {await db.users.count_banned()}",
        f"  • ربات را بلاک کرده‌اند: {await db.users.count_bot_blocked()}",
        "",
        "📦 <b>سرویس‌ها</b>",
        f"  • فعال: {await db.subscriptions.count_active()}",
        f"  • کل سرویس‌های فروخته‌شده: {await db.subscriptions.count_total()}",
        "",
        "💰 <b>فروش</b> (تعداد — مبلغ)",
    ]
    for label, (count, total) in sales.items():
        lines.append(f"  • {label}: {count} — {fmt_price(total)}")
    lines += [
        "",
        f"🧾 سفارش‌های منتظر بررسی: {await db.orders.count_by_status(OrderStatus.WAITING, OrderStatus.PAID)}",
        f"🎫 تیکت‌های منتظر پاسخ: {await db.tickets.count_by_status(TicketStatus.OPEN)}",
    ]
    top = await db.orders.top_plans(5)
    if top:
        lines += ["", "🏆 <b>پرفروش‌ترین پلن‌ها</b>"]
        for index, (title, count, total) in enumerate(top, 1):
            lines.append(f"  {index}. {h(title)} — {count} فروش ({fmt_price(total)})")
    await safe_edit(callback_message(callback), "\n".join(lines), back_kb())
