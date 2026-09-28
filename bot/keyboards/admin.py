"""کیبوردهای پنل مدیریت."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Order, Plan, Server, ServerKind, Subscription, Ticket, User
from bot.keyboards.callbacks import (
    ABackupCB,
    ABroadcastCB,
    AConfigCB,
    AdminCB,
    AOrderCB,
    APlanCB,
    ASettingCB,
    AServerCB,
    ATicketCB,
    AUserCB,
    CancelCB,
)
from bot.utils.formatting import fmt_price


def back_kb(section: str = "home", text: str = "🔙 بازگشت") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=AdminCB(section=section))
    return builder.as_markup()


def admin_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    return builder.as_markup()


def skip_cancel_kb(skip_callback: str) -> InlineKeyboardMarkup:
    """دکمه «رد کردن» (برای فیلدهای اختیاری) + انصراف."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ رد کردن", callback_data=skip_callback)
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(2)
    return builder.as_markup()


def admin_menu(waiting_orders: int = 0, open_tickets: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    orders_label = f"🧾 سفارش‌ها ({waiting_orders})" if waiting_orders else "🧾 سفارش‌ها"
    tickets_label = f"🎫 تیکت‌ها ({open_tickets})" if open_tickets else "🎫 تیکت‌ها"
    buttons = [
        ("📦 پلن‌ها", "plans"),
        ("🖥 سرورها و کانفیگ‌ها", "servers"),
        ("👥 کاربران", "users"),
        (orders_label, "orders"),
        (tickets_label, "tickets"),
        ("📊 آمار", "stats"),
        ("📣 پیام همگانی", "broadcast"),
        ("💳 تنظیمات پرداخت", "payment"),
        ("⚙️ تنظیمات ربات", "settings"),
        ("💾 بکاپ و ریستور", "backup"),
    ]
    for text, section in buttons:
        builder.button(text=text, callback_data=AdminCB(section=section))
    builder.adjust(2)
    return builder.as_markup()


# ----------------------------------------------------------------------
# پلن‌ها
# ----------------------------------------------------------------------
def plans_list_kb(plans: list[Plan], servers: dict[int, Server]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        server = servers.get(plan.server_id)
        state = "🟢" if plan.is_active else "🔴"
        builder.button(
            text=f"{state} {plan.name} | {fmt_price(plan.price)} | {server.name if server else '?'}",
            callback_data=APlanCB(action="view", plan_id=plan.id),
        )
    builder.button(text="➕ افزودن پلن", callback_data=APlanCB(action="new"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def plan_servers_kb(servers: list[Server]) -> InlineKeyboardMarkup:
    """انتخاب سرور برای پلن جدید."""
    builder = InlineKeyboardBuilder()
    for server in servers:
        builder.button(text=f"🌍 {server.name}", callback_data=APlanCB(action="new_server", server_id=server.id))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(1)
    return builder.as_markup()


def plan_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ذخیره پلن", callback_data=APlanCB(action="save"))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(2)
    return builder.as_markup()


def plan_detail_kb(plan: Plan, is_manual: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, label in (
        ("name", "✏️ نام"),
        ("price", "✏️ قیمت"),
        ("days", "✏️ مدت"),
        ("traffic_gb", "✏️ حجم"),
        ("description", "✏️ توضیحات"),
        ("sort_order", "✏️ ترتیب نمایش"),
    ):
        builder.button(text=label, callback_data=APlanCB(action="edit", plan_id=plan.id, field=field))
    builder.button(
        text="🔴 غیرفعال کردن" if plan.is_active else "🟢 فعال کردن",
        callback_data=APlanCB(action="toggle", plan_id=plan.id),
    )
    builder.button(text="🗑 حذف", callback_data=APlanCB(action="del", plan_id=plan.id))
    sizes = [2, 2, 2, 2]
    if is_manual:
        builder.button(text="📦 انبار کانفیگ این پلن", callback_data=AConfigCB(action="view", plan_id=plan.id))
        sizes.append(1)
    builder.button(text="🔙 لیست پلن‌ها", callback_data=AdminCB(section="plans"))
    sizes.append(1)
    builder.adjust(*sizes)
    return builder.as_markup()


def confirm_kb(yes: str, no: str, yes_text: str = "✅ بله", no_text: str = "❌ خیر") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=yes_text, callback_data=yes)
    builder.button(text=no_text, callback_data=no)
    builder.adjust(2)
    return builder.as_markup()


# ----------------------------------------------------------------------
# سرورها و انبار کانفیگ
# ----------------------------------------------------------------------
def servers_list_kb(servers: list[Server]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for server in servers:
        state = "🟢" if server.is_active else "🔴"
        kind = {"manual": "دستی", "xui": "3x-ui", "marzban": "Marzban"}.get(server.kind, server.kind)
        builder.button(
            text=f"{state} {server.name} ({kind})", callback_data=AServerCB(action="view", server_id=server.id)
        )
    builder.button(text="➕ افزودن سرور", callback_data=AServerCB(action="new"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def server_kind_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kind in ServerKind.ALL:
        builder.button(text=ServerKind.LABELS[kind], callback_data=AServerCB(action="kind", kind=kind))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(1)
    return builder.as_markup()


SERVER_FIELDS: dict[str, tuple[str, str]] = {
    # فیلد: (برچسب دکمه، توضیح درخواست مقدار)
    "name": ("✏️ نام", "نام جدید سرور/لوکیشن را بفرستید (مثال: 🇩🇪 آلمان):"),
    "api_url": ("🌐 آدرس پنل", "آدرس پنل را بفرستید:"),
    "api_user": ("👤 نام کاربری", "نام کاربری پنل را بفرستید:"),
    "api_pass": ("🔑 رمز عبور", "رمز عبور پنل را بفرستید:"),
    "api_token": ("🎟 توکن API", "توکن API پنل را بفرستید (برای حذف: -):"),
    "inbound_ids": ("🔌 اینباندها", "آیدی اینباندها را با کاما بفرستید (مثال: 1,3):"),
    "sub_url": ("🔗 آدرس ساب", "آدرس پایه ساب‌اسکریپشن را بفرستید (برای حذف: -):"),
    "address": ("📍 آدرس عمومی", "آدرس عمومی سرور برای لینک‌ها را بفرستید (برای حذف: -):"),
}


def server_detail_kb(server: Server) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not server.is_manual:
        builder.button(text="🧪 تست اتصال", callback_data=AServerCB(action="test", server_id=server.id))
    builder.button(
        text="🔴 غیرفعال کردن" if server.is_active else "🟢 فعال کردن",
        callback_data=AServerCB(action="toggle", server_id=server.id),
    )
    fields = ["name"] if server.is_manual else list(SERVER_FIELDS)
    for field in fields:
        builder.button(
            text=SERVER_FIELDS[field][0], callback_data=AServerCB(action="field", server_id=server.id, field=field)
        )
    builder.button(text="📦 پلن‌ها و موجودی", callback_data=AServerCB(action="plans", server_id=server.id))
    builder.button(text="🗑 حذف سرور", callback_data=AServerCB(action="del", server_id=server.id))
    builder.button(text="🔙 لیست سرورها", callback_data=AdminCB(section="servers"))
    builder.adjust(2)
    return builder.as_markup()


def server_plans_kb(plans: list[Plan], stock: dict[int, int], server: Server) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        suffix = f" | 📦 {stock.get(plan.id, 0)}" if server.is_manual else ""
        target = AConfigCB(action="view", plan_id=plan.id) if server.is_manual else APlanCB(action="view", plan_id=plan.id)
        builder.button(text=f"{plan.name}{suffix}", callback_data=target)
    builder.button(text="➕ افزودن پلن", callback_data=APlanCB(action="new"))
    builder.button(text="🔙 بازگشت", callback_data=AServerCB(action="view", server_id=server.id))
    builder.adjust(1)
    return builder.as_markup()


def configs_kb(plan_id: int, has_available: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 افزودن کانفیگ", callback_data=AConfigCB(action="add", plan_id=plan_id))
    if has_available:
        builder.button(text="📄 دریافت لیست آزادها", callback_data=AConfigCB(action="export", plan_id=plan_id))
        builder.button(text="🗑 حذف کانفیگ‌های آزاد", callback_data=AConfigCB(action="clear", plan_id=plan_id))
    builder.button(text="🔙 مشخصات پلن", callback_data=APlanCB(action="view", plan_id=plan_id))
    builder.adjust(1)
    return builder.as_markup()


# ----------------------------------------------------------------------
# کاربران
# ----------------------------------------------------------------------
def users_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 جستجوی کاربر", callback_data=AUserCB(action="search"))
    builder.button(text="📋 کاربران اخیر", callback_data=AUserCB(action="list"))
    builder.button(text="⛔️ کاربران مسدود", callback_data=AUserCB(action="banned"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def users_list_kb(users: list[User], *, action: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        state = "⛔️ " if user.is_banned else ""
        builder.button(
            text=f"{state}{user.full_name or user.id} ({user.display_username})",
            callback_data=AUserCB(action="view", user_id=user.id),
        )
    nav = 0
    if page > 0:
        builder.button(text="⬅️ قبلی", callback_data=AUserCB(action=action, page=page - 1))
        nav += 1
    if has_next:
        builder.button(text="بعدی ➡️", callback_data=AUserCB(action=action, page=page + 1))
        nav += 1
    builder.button(text="🔙 بازگشت", callback_data=AdminCB(section="users"))
    builder.adjust(*([1] * len(users)), *([nav] if nav else []), 1)
    return builder.as_markup()


def user_card_kb(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if user.is_banned:
        builder.button(text="✅ رفع مسدودیت", callback_data=AUserCB(action="unban", user_id=user.id))
    else:
        builder.button(text="⛔️ مسدود کردن", callback_data=AUserCB(action="ban", user_id=user.id))
    builder.button(text="📦 سرویس‌ها", callback_data=AUserCB(action="subs", user_id=user.id))
    builder.button(text="🧾 سفارش‌ها", callback_data=AUserCB(action="orders", user_id=user.id))
    builder.button(text="🎁 افزودن سرویس هدیه", callback_data=AUserCB(action="gift", user_id=user.id))
    builder.button(text="✉️ ارسال پیام", callback_data=AUserCB(action="msg", user_id=user.id))
    builder.button(text="🔙 مدیریت کاربران", callback_data=AdminCB(section="users"))
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def user_subs_kb(subs: list[Subscription], user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sub in subs:
        icon = "🟢" if sub.is_active else ("⚫️" if sub.status == "disabled" else "🔴")
        builder.button(
            text=f"{icon} #{sub.id} | {sub.title}", callback_data=AUserCB(action="sub", user_id=user_id, sub_id=sub.id)
        )
    builder.button(text="🔙 کارت کاربر", callback_data=AUserCB(action="view", user_id=user_id))
    builder.adjust(1)
    return builder.as_markup()


def admin_sub_kb(sub: Subscription) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if sub.status != "disabled":
        builder.button(text="➕ افزایش/کاهش روز", callback_data=AUserCB(action="days", user_id=sub.user_id, sub_id=sub.id))
        builder.button(text="❌ لغو سرویس", callback_data=AUserCB(action="cancel_sub", user_id=sub.user_id, sub_id=sub.id))
    builder.button(text="🔙 سرویس‌های کاربر", callback_data=AUserCB(action="subs", user_id=sub.user_id))
    builder.adjust(2, 1)
    return builder.as_markup()


def gift_plans_kb(plans: list[Plan], user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=f"🎁 {plan.name} ({plan.days} روز)",
            callback_data=AUserCB(action="gift_plan", user_id=user_id, plan_id=plan.id),
        )
    builder.button(text="🔙 کارت کاربر", callback_data=AUserCB(action="view", user_id=user_id))
    builder.adjust(1)
    return builder.as_markup()


# ----------------------------------------------------------------------
# سفارش‌ها و تیکت‌ها
# ----------------------------------------------------------------------
def order_review_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ تایید و تحویل", callback_data=AOrderCB(action="approve", order_id=order_id))
    builder.button(text="❌ رد سفارش", callback_data=AOrderCB(action="reject", order_id=order_id))
    builder.adjust(2)
    return builder.as_markup()


def order_failed_kb(order_id: int, is_renew: bool) -> InlineKeyboardMarkup:
    """گزینه‌های ادمین وقتی تحویل خودکار ناموفق بود."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 تلاش مجدد", callback_data=AOrderCB(action="retry", order_id=order_id))
    builder.button(text="✍️ ارسال دستی کانفیگ", callback_data=AOrderCB(action="manual", order_id=order_id))
    if is_renew:
        builder.button(text="📅 فقط تمدید تاریخ", callback_data=AOrderCB(action="dateonly", order_id=order_id))
    builder.adjust(1)
    return builder.as_markup()


def reject_reason_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="رد بدون توضیح", callback_data=AOrderCB(action="reject_now", order_id=order_id))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(1)
    return builder.as_markup()


def orders_list_kb(orders: list[Order]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        icon = "🕓" if order.status == "waiting" else "⚠️"
        builder.button(
            text=f"{icon} #{order.id} | {order.plan_title} | {fmt_price(order.amount)}",
            callback_data=AOrderCB(action="view", order_id=order.id),
        )
    builder.button(text="🔃 بروزرسانی", callback_data=AdminCB(section="orders"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def admin_tickets_kb(tickets: list[Ticket]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ticket in tickets:
        builder.button(
            text=f"🟡 #{ticket.id} | {ticket.subject[:35]}", callback_data=ATicketCB(action="view", ticket_id=ticket.id)
        )
    builder.button(text="🔃 بروزرسانی", callback_data=AdminCB(section="tickets"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def admin_ticket_kb(ticket: Ticket) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ticket.status != "closed":
        builder.button(text="↩️ پاسخ", callback_data=ATicketCB(action="reply", ticket_id=ticket.id))
        builder.button(text="🔒 بستن", callback_data=ATicketCB(action="close", ticket_id=ticket.id))
    builder.button(text="👤 کارت کاربر", callback_data=AUserCB(action="view", user_id=ticket.user_id))
    builder.button(text="🔙 تیکت‌ها", callback_data=AdminCB(section="tickets"))
    builder.adjust(2, 2)
    return builder.as_markup()


# ----------------------------------------------------------------------
# پیام همگانی، تنظیمات، بکاپ
# ----------------------------------------------------------------------
def broadcast_target_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 همه کاربران", callback_data=ABroadcastCB(action="target", target="all"))
    builder.button(text="✅ فقط دارندگان سرویس فعال", callback_data=ABroadcastCB(action="target", target="active"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ارسال شود", callback_data=ABroadcastCB(action="send"))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(2)
    return builder.as_markup()


def payment_settings_kb(card_enabled: bool, link_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{'🟢' if card_enabled else '🔴'} کارت به کارت", callback_data=ASettingCB(action="toggle", key="card_enabled")
    )
    builder.button(
        text=f"{'🟢' if link_enabled else '🔴'} پرداخت با لینک", callback_data=ASettingCB(action="toggle", key="link_enabled")
    )
    builder.button(text="💳 شماره کارت", callback_data=ASettingCB(action="edit", key="card_number"))
    builder.button(text="👤 نام صاحب کارت", callback_data=ASettingCB(action="edit", key="card_holder"))
    builder.button(text="🏦 نام بانک", callback_data=ASettingCB(action="edit", key="bank_name"))
    builder.button(text="🔗 لینک پرداخت", callback_data=ASettingCB(action="edit", key="payment_link"))
    builder.button(text="📝 توضیحات پرداخت", callback_data=ASettingCB(action="edit", key="payment_note"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def bot_settings_kb(sales_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{'🟢 فروش فعال است' if sales_enabled else '🔴 فروش غیرفعال است'}",
        callback_data=ASettingCB(action="toggle", key="sales_enabled"),
    )
    builder.button(text="👋 متن خوش‌آمد", callback_data=ASettingCB(action="edit", key="welcome_text"))
    builder.button(text="🎧 متن پشتیبانی", callback_data=ASettingCB(action="edit", key="support_text"))
    builder.button(text="📚 متن راهنما", callback_data=ASettingCB(action="edit", key="guide_text"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def backup_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💾 دریافت بکاپ فوری", callback_data=ABackupCB(action="now"))
    builder.button(text="♻️ ریستور از فایل بکاپ", callback_data=ABackupCB(action="restore"))
    builder.button(text="🔙 پنل مدیریت", callback_data=AdminCB(section="home"))
    builder.adjust(1)
    return builder.as_markup()


def restore_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ بله، ریستور شود", callback_data=ABackupCB(action="confirm"))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(1)
    return builder.as_markup()
