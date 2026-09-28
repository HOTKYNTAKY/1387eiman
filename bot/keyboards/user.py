"""کیبوردهای بخش کاربر."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.database.models import Order, OrderStatus, Plan, Server, Subscription, Ticket, TicketStatus
from bot.keyboards.callbacks import AccountCB, BuyCB, CancelCB, OrderCB, SubCB, TicketCB
from bot.texts import Btn
from bot.utils.formatting import fmt_price


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """منوی اصلی (کیبورد پایین صفحه)."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=Btn.BUY)
    builder.button(text=Btn.MY_SERVICES)
    builder.button(text=Btn.RENEW)
    builder.button(text=Btn.ACCOUNT)
    builder.button(text=Btn.SUPPORT)
    builder.button(text=Btn.GUIDE)
    sizes = [1, 2, 2, 1]
    if is_admin:
        builder.button(text=Btn.ADMIN)
        sizes.append(1)
    builder.adjust(*sizes)
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="یک گزینه را انتخاب کنید")


def cancel_kb(to: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data=CancelCB(to=to))
    return builder.as_markup()


# ----------------------------------------------------------------------
# خرید و تمدید
# ----------------------------------------------------------------------
def servers_kb(servers: list[Server]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for server in servers:
        builder.button(text=f"🌍 {server.name}", callback_data=BuyCB(action="server", server_id=server.id))
    builder.adjust(1)
    return builder.as_markup()


def plans_kb(
    plans: list[Plan],
    *,
    stock: dict[int, int] | None = None,
    sub_id: int = 0,
    back_to_servers: bool = False,
) -> InlineKeyboardMarkup:
    """
    لیست پلن‌ها. برای سرورهای دستی، پلن‌های بدون موجودی با علامت «ناموجود» نمایش داده می‌شوند.
    """
    builder = InlineKeyboardBuilder()
    for plan in plans:
        label = f"{plan.name} | {fmt_price(plan.price)}"
        if stock is not None and stock.get(plan.id, 0) <= 0:
            label = f"❌ {plan.name} (ناموجود)"
        builder.button(text=label, callback_data=BuyCB(action="plan", plan_id=plan.id, sub_id=sub_id))
    if back_to_servers:
        builder.button(text="🔙 بازگشت به لوکیشن‌ها", callback_data=BuyCB(action="servers"))
    elif sub_id:
        builder.button(text="🔙 بازگشت", callback_data=SubCB(action="view", sub_id=sub_id))
    builder.adjust(1)
    return builder.as_markup()


def invoice_kb(plan: Plan, *, sub_id: int, card: bool, link: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if card:
        builder.button(
            text="💳 کارت به کارت", callback_data=BuyCB(action="pay", plan_id=plan.id, sub_id=sub_id, method="card")
        )
    if link:
        builder.button(
            text="🔗 پرداخت آنلاین", callback_data=BuyCB(action="pay", plan_id=plan.id, sub_id=sub_id, method="link")
        )
    if sub_id:
        builder.button(text="🔙 بازگشت", callback_data=SubCB(action="renew", sub_id=sub_id))
    else:
        builder.button(text="🔙 بازگشت", callback_data=BuyCB(action="server", server_id=plan.server_id))
    builder.adjust(1)
    return builder.as_markup()


def payment_kb(order_id: int, pay_url: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if pay_url:
        builder.button(text="💳 ورود به صفحه پرداخت", url=pay_url)
    builder.button(text="❌ لغو سفارش", callback_data=OrderCB(action="cancel", order_id=order_id))
    builder.adjust(1)
    return builder.as_markup()


# ----------------------------------------------------------------------
# سرویس‌ها
# ----------------------------------------------------------------------
def _sub_icon(sub: Subscription) -> str:
    return "🟢" if sub.is_active else ("⚫️" if sub.status == "disabled" else "🔴")


def subs_list_kb(subs: list[Subscription], action: str = "view") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sub in subs:
        builder.button(
            text=f"{_sub_icon(sub)} #{sub.id} | {sub.title}", callback_data=SubCB(action=action, sub_id=sub.id)
        )
    builder.adjust(1)
    return builder.as_markup()


def sub_detail_kb(sub: Subscription) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if sub.status != "disabled":
        builder.button(text="🔗 دریافت کانفیگ", callback_data=SubCB(action="config", sub_id=sub.id))
        builder.button(text="🔄 تمدید", callback_data=SubCB(action="renew", sub_id=sub.id))
    builder.button(text="🔃 بروزرسانی", callback_data=SubCB(action="view", sub_id=sub.id))
    builder.button(text="🔙 سرویس‌های من", callback_data=SubCB(action="list"))
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def renew_now_kb(sub_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 تمدید سرویس", callback_data=SubCB(action="renew", sub_id=sub_id))
    return builder.as_markup()


# ----------------------------------------------------------------------
# پشتیبانی
# ----------------------------------------------------------------------
def support_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✉️ ثبت تیکت جدید", callback_data=TicketCB(action="new"))
    builder.button(text="📂 تیکت‌های من", callback_data=TicketCB(action="list"))
    builder.adjust(1)
    return builder.as_markup()


def tickets_kb(tickets: list[Ticket]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    icons = {TicketStatus.OPEN: "🟡", TicketStatus.ANSWERED: "🟢", TicketStatus.CLOSED: "⚪️"}
    for ticket in tickets:
        builder.button(
            text=f"{icons.get(ticket.status, '▫️')} #{ticket.id} | {ticket.subject[:30]}",
            callback_data=TicketCB(action="view", ticket_id=ticket.id),
        )
    builder.button(text="🔙 بازگشت", callback_data=TicketCB(action="menu"))
    builder.adjust(1)
    return builder.as_markup()


def ticket_view_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ticket.status != TicketStatus.CLOSED:
        builder.button(text="↩️ ارسال پاسخ", callback_data=TicketCB(action="reply", ticket_id=ticket.id))
        builder.button(text="🔒 بستن تیکت", callback_data=TicketCB(action="close", ticket_id=ticket.id))
    builder.button(text="🔙 تیکت‌های من", callback_data=TicketCB(action="list"))
    builder.adjust(2, 1)
    return builder.as_markup()


# ----------------------------------------------------------------------
# حساب کاربری
# ----------------------------------------------------------------------
def account_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧾 سفارش‌های من", callback_data=AccountCB(action="orders"))
    return builder.as_markup()


def orders_kb(orders: list[Order]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        if order.status == OrderStatus.PENDING:
            builder.button(text=f"📤 ارسال رسید #{order.id}", callback_data=OrderCB(action="receipt", order_id=order.id))
            builder.button(text=f"❌ لغو #{order.id}", callback_data=OrderCB(action="cancel", order_id=order.id))
    builder.button(text="🔙 بازگشت", callback_data=AccountCB(action="home"))
    builder.adjust(2)
    return builder.as_markup()
