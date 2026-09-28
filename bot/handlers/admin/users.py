"""
مدیریت کاربران: جستجو، مشاهده اطلاعات، مسدودسازی، افزایش روز سرویس،
لغو سرویس، سرویس هدیه و ارسال پیام خصوصی
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, MessageOriginUser

from bot.config import Config
from bot.database import Database
from bot.database.models import OrderKind, OrderStatus, SubStatus, User, now_ts
from bot.handlers.admin.orders import deliver_and_report
from bot.keyboards.admin import (
    admin_cancel_kb,
    admin_sub_kb,
    back_kb,
    confirm_kb,
    gift_plans_kb,
    user_card_kb,
    user_subs_kb,
    users_list_kb,
    users_menu_kb,
)
from bot.keyboards.callbacks import AdminCB, AUserCB
from bot.services.delivery import subscription_status_text
from bot.services.panels import PanelError
from bot.services.provisioning import Provisioner
from bot.states import UserAdmin
from bot.utils.formatting import fmt_date, fmt_price, h, parse_int, user_link
from bot.utils.telegram import callback_message, safe_edit, safe_send

log = logging.getLogger(__name__)
router = Router(name="admin_users")

PAGE_SIZE = 10


async def user_card(db: Database, config: Config, user: User) -> tuple[str, InlineKeyboardMarkup]:
    active = await db.subscriptions.count_active_for_user(user.id)
    subs = await db.subscriptions.list_for_user(user.id)
    purchases, total = await db.orders.user_summary(user.id)
    flags = []
    if user.is_banned:
        flags.append("⛔️ مسدود")
    if user.bot_blocked:
        flags.append("🚫 ربات را بلاک کرده")
    if config.is_admin(user.id):
        flags.append("👑 ادمین")
    lines = [
        f"👤 <b>{user_link(user.id, user.full_name)}</b>",
        "",
        f"🆔 آیدی عددی: <code>{user.id}</code>",
        f"📛 یوزرنیم: {h(user.display_username)}",
        f"📅 عضویت: {fmt_date(user.created_at, config.timezone)}",
        f"👁 آخرین فعالیت: {fmt_date(user.last_seen_at, config.timezone)}",
        f"📦 سرویس‌ها: {active} فعال از {len(subs)}",
        f"🧾 خریدها: {purchases} — {fmt_price(total)}",
    ]
    if flags:
        lines.append(f"🏷 وضعیت: {' | '.join(flags)}")
    return "\n".join(lines), user_card_kb(user)


@router.callback_query(AdminCB.filter(F.section == "users"))
async def cb_users(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        f"👥 <b>مدیریت کاربران</b>\n\nکل کاربران: {await db.users.count()}\nمسدود: {await db.users.count_banned()}",
        users_menu_kb(),
    )


# ----------------------------------------------------------------------
# جستجو و لیست
# ----------------------------------------------------------------------
@router.callback_query(AUserCB.filter(F.action == "search"))
async def cb_search(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(UserAdmin.search)
    await safe_edit(
        callback_message(callback),
        "🔍 آیدی عددی یا یوزرنیم کاربر را بفرستید.\nهمچنین می‌توانید یک پیام از کاربر را فوروارد کنید.",
        admin_cancel_kb(),
    )


@router.message(UserAdmin.search)
async def search_query(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    query = ""
    if isinstance(message.forward_origin, MessageOriginUser):
        query = str(message.forward_origin.sender_user.id)
    elif message.text:
        query = message.text.strip()
    user = await db.users.find(query) if query else None
    if user is None:
        await message.answer(
            "❌ کاربری پیدا نشد (کاربر باید حداقل یک بار ربات را استارت کرده باشد). دوباره تلاش کنید:",
            reply_markup=admin_cancel_kb(),
        )
        return
    await state.clear()
    text, markup = await user_card(db, config, user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(AUserCB.filter(F.action.in_({"list", "banned"})))
async def cb_list(callback: CallbackQuery, callback_data: AUserCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    page = max(0, callback_data.page)
    fetch = db.users.list_banned if callback_data.action == "banned" else db.users.list_recent
    users = await fetch(PAGE_SIZE + 1, page * PAGE_SIZE)
    has_next = len(users) > PAGE_SIZE
    users = users[:PAGE_SIZE]
    title = "⛔️ <b>کاربران مسدود</b>" if callback_data.action == "banned" else "📋 <b>کاربران اخیر</b>"
    text = f"{title} — صفحه {page + 1}" if users else f"{title}\n\nکاربری وجود ندارد."
    await safe_edit(
        callback_message(callback),
        text,
        users_list_kb(users, action=callback_data.action, page=page, has_next=has_next),
    )


@router.callback_query(AUserCB.filter(F.action == "view"))
async def cb_view(callback: CallbackQuery, callback_data: AUserCB, state: FSMContext, db: Database, config: Config) -> None:
    await state.clear()
    user = await db.users.get(callback_data.user_id)
    if user is None:
        await callback.answer("کاربر پیدا نشد", show_alert=True)
        return
    await callback.answer()
    text, markup = await user_card(db, config, user)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(AUserCB.filter(F.action.in_({"ban", "unban"})))
async def cb_ban(callback: CallbackQuery, callback_data: AUserCB, db: Database, config: Config) -> None:
    if config.is_admin(callback_data.user_id):
        await callback.answer("❗️ ادمین را نمی‌توان مسدود کرد.", show_alert=True)
        return
    banned = callback_data.action == "ban"
    await db.users.set_banned(callback_data.user_id, banned)
    log.info("User %s %s by admin %s", callback_data.user_id, "banned" if banned else "unbanned", callback.from_user.id)
    await callback.answer("⛔️ کاربر مسدود شد" if banned else "✅ مسدودیت برداشته شد")
    user = await db.users.get(callback_data.user_id)
    if user:
        text, markup = await user_card(db, config, user)
        await safe_edit(callback_message(callback), text, markup)


@router.callback_query(AUserCB.filter(F.action == "orders"))
async def cb_orders(callback: CallbackQuery, callback_data: AUserCB, db: Database, config: Config) -> None:
    await callback.answer()
    orders = await db.orders.list_for_user(callback_data.user_id, limit=15)
    lines = [f"🧾 <b>سفارش‌های کاربر</b> <code>{callback_data.user_id}</code>", ""]
    for order in orders:
        lines.append(
            f"#{order.id} | {h(order.plan_title)} | {fmt_price(order.amount)} | {order.status_label}\n"
            f"      {order.kind_label} — {fmt_date(order.created_at, config.timezone)}"
        )
    if not orders:
        lines.append("سفارشی ثبت نشده است.")
    markup = confirm_kb(
        AUserCB(action="view", user_id=callback_data.user_id).pack(),
        AdminCB(section="users").pack(),
        yes_text="🔙 کارت کاربر",
        no_text="👥 مدیریت کاربران",
    )
    await safe_edit(callback_message(callback), "\n".join(lines), markup)


# ----------------------------------------------------------------------
# سرویس‌های کاربر
# ----------------------------------------------------------------------
@router.callback_query(AUserCB.filter(F.action == "subs"))
async def cb_subs(callback: CallbackQuery, callback_data: AUserCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    subs = await db.subscriptions.list_for_user(callback_data.user_id)
    text = f"📦 <b>سرویس‌های کاربر</b> <code>{callback_data.user_id}</code>"
    if not subs:
        text += "\n\nاین کاربر سرویسی ندارد."
    await safe_edit(callback_message(callback), text, user_subs_kb(subs, callback_data.user_id))


@router.callback_query(AUserCB.filter(F.action == "sub"))
async def cb_sub(
    callback: CallbackQuery, callback_data: AUserCB, db: Database, config: Config, provisioner: Provisioner
) -> None:
    sub = await db.subscriptions.get(callback_data.sub_id)
    if sub is None:
        await callback.answer("سرویس پیدا نشد", show_alert=True)
        return
    await callback.answer("⏳ ...")
    usage = await provisioner.usage(sub) if sub.status != SubStatus.DISABLED else None
    server = await db.servers.get_any(sub.server_id) if sub.server_id else None
    text = subscription_status_text(sub, server, usage, config)
    if sub.meta.get("email") or sub.meta.get("username"):
        text += f"\n🔖 نام کاربر در پنل: <code>{h(sub.meta.get('email') or sub.meta.get('username'))}</code>"
    configs = sub.config_lines()
    if configs:
        text += "\n\n📋 کانفیگ:\n" + "\n".join(f"<code>{h(c)}</code>" for c in configs[:3])
    if sub.sub_link:
        text += f"\n🔗 ساب: <code>{h(sub.sub_link)}</code>"
    await safe_edit(callback_message(callback), text[:4000], admin_sub_kb(sub))


@router.callback_query(AUserCB.filter(F.action == "days"))
async def cb_days(callback: CallbackQuery, callback_data: AUserCB, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(UserAdmin.add_days)
    await state.update_data(sub_id=callback_data.sub_id)
    message = callback_message(callback)
    if message:
        await message.answer(
            "➕ تعداد روز را بفرستید.\nبرای کاهش، عدد منفی بفرستید (مثال: <code>10</code> یا <code>-5</code>):",
            reply_markup=admin_cancel_kb(),
        )


@router.message(UserAdmin.add_days, F.text)
async def add_days_value(
    message: Message, state: FSMContext, db: Database, bot: Bot, config: Config, provisioner: Provisioner
) -> None:
    days = parse_int(message.text or "")
    if days is None or days == 0 or abs(days) > 3650:
        await message.answer("⚠️ یک عدد غیر صفر بین ۳۶۵۰- و ۳۶۵۰ بفرستید.")
        return
    data = await state.get_data()
    await state.clear()
    sub = await db.subscriptions.get(int(data.get("sub_id") or 0))
    if sub is None:
        await message.answer("سرویس پیدا نشد.")
        return
    try:
        sub = await provisioner.add_days(sub, days)
    except PanelError as exc:
        await message.answer(f"❌ تغییر روی پنل ناموفق بود:\n<code>{h(exc)}</code>")
        return
    log.info("Admin %s changed subscription #%s by %s days", message.chat.id, sub.id, days)
    action = f"{days} روز به" if days > 0 else f"{-days} روز از"
    await message.answer(
        f"✅ {action} سرویس #{sub.id} {'اضافه' if days > 0 else 'کم'} شد.\n"
        f"📅 انقضای جدید: {fmt_date(sub.expires_at, config.timezone)}",
        reply_markup=back_kb("users", "🔙 مدیریت کاربران"),
    )
    if days > 0:
        await safe_send(
            bot,
            sub.user_id,
            f"🎁 {days} روز به سرویس #{sub.id} شما اضافه شد.\n📅 تاریخ انقضای جدید: {fmt_date(sub.expires_at, config.timezone)}",
            db=db,
        )


@router.callback_query(AUserCB.filter(F.action == "cancel_sub"))
async def cb_cancel_sub(callback: CallbackQuery, callback_data: AUserCB) -> None:
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        f"❌ سرویس #{callback_data.sub_id} لغو شود؟\nکاربر روی پنل حذف و سرویس در ربات غیرفعال می‌شود.",
        confirm_kb(
            AUserCB(action="cancel_ok", user_id=callback_data.user_id, sub_id=callback_data.sub_id).pack(),
            AUserCB(action="sub", user_id=callback_data.user_id, sub_id=callback_data.sub_id).pack(),
            yes_text="❌ بله، لغو شود",
            no_text="🔙 انصراف",
        ),
    )


@router.callback_query(AUserCB.filter(F.action == "cancel_ok"))
async def cb_cancel_ok(
    callback: CallbackQuery, callback_data: AUserCB, db: Database, bot: Bot, provisioner: Provisioner
) -> None:
    sub = await db.subscriptions.get(callback_data.sub_id)
    if sub is None or sub.status == SubStatus.DISABLED:
        await callback.answer("سرویس پیدا نشد یا قبلاً لغو شده است.", show_alert=True)
        return
    await callback.answer("⏳ ...")
    warning = await provisioner.cancel_subscription(sub)
    text = f"✅ سرویس #{sub.id} لغو شد."
    if warning:
        text += f"\n⚠️ حذف از پنل ناموفق بود؛ لطفاً دستی حذف کنید:\n<code>{h(warning)}</code>"
    await safe_edit(callback_message(callback), text, user_subs_kb(await db.subscriptions.list_for_user(sub.user_id), sub.user_id))
    await safe_send(bot, sub.user_id, f"⛔️ سرویس #{sub.id} توسط مدیریت لغو شد.", db=db)


# ----------------------------------------------------------------------
# سرویس هدیه
# ----------------------------------------------------------------------
@router.callback_query(AUserCB.filter(F.action == "gift"))
async def cb_gift(callback: CallbackQuery, callback_data: AUserCB, db: Database) -> None:
    plans = await db.plans.list_for_sale()
    if not plans:
        await callback.answer("❗️ هیچ پلن فعالی وجود ندارد.", show_alert=True)
        return
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        "🎁 کدام پلن به صورت رایگان برای این کاربر فعال شود؟",
        gift_plans_kb(plans, callback_data.user_id),
    )


@router.callback_query(AUserCB.filter(F.action == "gift_plan"))
async def cb_gift_plan(callback: CallbackQuery, callback_data: AUserCB, db: Database) -> None:
    plan = await db.plans.get(callback_data.plan_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        f"🎁 پلن «{h(plan.name)}» ({plan.days} روز) برای کاربر <code>{callback_data.user_id}</code> فعال شود؟",
        confirm_kb(
            AUserCB(action="gift_ok", user_id=callback_data.user_id, plan_id=plan.id).pack(),
            AUserCB(action="view", user_id=callback_data.user_id).pack(),
        ),
    )


@router.callback_query(AUserCB.filter(F.action == "gift_ok"))
async def cb_gift_ok(
    callback: CallbackQuery, callback_data: AUserCB, db: Database, bot: Bot, config: Config, provisioner: Provisioner
) -> None:
    plan = await db.plans.get(callback_data.plan_id)
    user = await db.users.get(callback_data.user_id)
    if plan is None or user is None:
        await callback.answer("پلن یا کاربر پیدا نشد", show_alert=True)
        return
    await callback.answer("⏳ در حال ساخت سرویس...")
    order_id = await db.orders.create(
        user_id=user.id,
        plan_id=plan.id,
        kind=OrderKind.GIFT,
        amount=0,
        plan_title=plan.name,
        method="admin",
        status=OrderStatus.PAID,
    )
    await db.orders.update(order_id, paid_at=now_ts())
    await safe_edit(callback_message(callback), f"🎁 سفارش هدیه #{order_id} ثبت شد.")
    await deliver_and_report(callback.from_user.id, bot, db, config, provisioner, order_id, notify_user_on_failure=False)


# ----------------------------------------------------------------------
# ارسال پیام خصوصی
# ----------------------------------------------------------------------
@router.callback_query(AUserCB.filter(F.action == "msg"))
async def cb_message(callback: CallbackQuery, callback_data: AUserCB, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(UserAdmin.message)
    await state.update_data(user_id=callback_data.user_id)
    message = callback_message(callback)
    if message:
        await message.answer("✉️ پیام خود را بفرستید (متن، عکس، فایل و ...):", reply_markup=admin_cancel_kb())


@router.message(UserAdmin.message)
async def message_to_user(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    user_id = int(data.get("user_id") or 0)
    try:
        await bot.send_message(user_id, "📩 <b>پیام از طرف مدیریت:</b>")
        await message.copy_to(user_id)
        result = "✅ پیام ارسال شد."
    except TelegramAPIError as exc:
        result = f"❌ ارسال ناموفق بود: {h(exc)}"
        if "blocked" in str(exc).lower():
            await db.users.set_bot_blocked(user_id, True)
    await message.answer(result, reply_markup=back_kb("users", "🔙 مدیریت کاربران"))
