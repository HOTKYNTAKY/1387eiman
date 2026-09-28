"""
خرید و تمدید سرویس (سمت کاربر)

مراحل:
    ۱. انتخاب لوکیشن (اگر بیش از یک سرور فعال باشد)
    ۲. انتخاب پلن
    ۳. پیش‌فاکتور و انتخاب روش پرداخت (کارت به کارت / لینک پرداخت)
    ۴. ساخت سفارش و نمایش اطلاعات پرداخت
    ۵. دریافت رسید (عکس، فایل یا کد پیگیری) و ارسال برای تایید ادمین

تمدید هم از همین مسیر استفاده می‌کند؛ با این تفاوت که sub_id در داده دکمه‌ها
مقدار دارد و فقط پلن‌های همان سرور نمایش داده می‌شوند.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import Config
from bot.database import Database
from bot.database.models import OrderKind, OrderStatus, Plan, Server, SubStatus, User
from bot.handlers.admin.orders import send_order_to_admins
from bot.keyboards.callbacks import BuyCB, OrderCB
from bot.keyboards.user import invoice_kb, main_menu, payment_kb, plans_kb, servers_kb
from bot.states import BuyStates
from bot.utils.formatting import fmt_price, fmt_traffic, h
from bot.utils.telegram import callback_message, safe_edit

log = logging.getLogger(__name__)
router = Router(name="user_buy")


# ----------------------------------------------------------------------
# نمایش لوکیشن‌ها و پلن‌ها
# ----------------------------------------------------------------------
async def show_servers(message: Message, db: Database, *, edit: bool = False) -> None:
    """ورود به بخش خرید. اگر فقط یک سرور فعال باشد مستقیم پلن‌ها نمایش داده می‌شود."""
    if not await db.settings.get_bool("sales_enabled"):
        await message.answer(texts.SALES_DISABLED)
        return
    servers = await db.servers.list_for_sale()
    if not servers:
        await message.answer("😔 در حال حاضر پلنی برای فروش موجود نیست. لطفاً بعداً مراجعه کنید.")
        return
    if len(servers) == 1:
        await show_plans(message, db, servers[0], edit=edit)
        return
    text = "🌍 <b>لوکیشن سرور را انتخاب کنید:</b>"
    if edit:
        await safe_edit(message, text, servers_kb(servers))
    else:
        await message.answer(text, reply_markup=servers_kb(servers))


async def show_plans(
    message: Message,
    db: Database,
    server: Server,
    *,
    edit: bool = True,
    sub_id: int = 0,
    back_to_servers: bool = False,
) -> None:
    plans = await db.plans.list_for_server(server.id)
    stock = await db.configs.available_by_plan() if server.is_manual else None

    title = f"🔄 <b>تمدید سرویس #{sub_id}</b>" if sub_id else f"📦 <b>پلن‌های {h(server.name)}</b>"
    lines = [title, ""]
    for plan in plans:
        lines.append(f"🔹 <b>{h(plan.name)}</b>")
        lines.append(f"      ⏳ {plan.days} روز  |  📊 {fmt_traffic(plan.traffic_gb)}  |  💰 {fmt_price(plan.price)}")
        if stock is not None and stock.get(plan.id, 0) <= 0:
            lines.append("      ❌ ناموجود")
    if not plans:
        lines.append("در حال حاضر پلنی برای این سرور موجود نیست.")
    else:
        lines.append("\n👇 پلن موردنظر را انتخاب کنید:")
    markup = plans_kb(plans, stock=stock, sub_id=sub_id, back_to_servers=back_to_servers)
    if edit:
        await safe_edit(message, "\n".join(lines), markup)
    else:
        await message.answer("\n".join(lines), reply_markup=markup)


async def _payment_methods(db: Database) -> tuple[bool, bool]:
    """(کارت به کارت فعال و تنظیم‌شده؟، لینک پرداخت فعال و تنظیم‌شده؟)"""
    card = await db.settings.get_bool("card_enabled") and bool((await db.settings.get("card_number")).strip())
    link = await db.settings.get_bool("link_enabled") and bool((await db.settings.get("payment_link")).strip())
    return card, link


async def _validate_purchase(
    db: Database, user: User, plan_id: int, sub_id: int
) -> tuple[Plan, Server] | str:
    """بررسی امکان خرید/تمدید؛ در صورت مشکل متن خطا برمی‌گرداند."""
    if not await db.settings.get_bool("sales_enabled"):
        return texts.SALES_DISABLED
    plan = await db.plans.get(plan_id)
    if plan is None or not plan.is_active:
        return "❗️ این پلن دیگر موجود نیست."
    server = await db.servers.get(plan.server_id)
    if server is None or not server.is_active:
        return "❗️ سرور این پلن در حال حاضر فعال نیست."
    if sub_id:
        sub = await db.subscriptions.get(sub_id)
        if sub is None or sub.user_id != user.id:
            return texts.NOT_FOUND
        if sub.status == SubStatus.DISABLED:
            return "⛔️ این سرویس توسط مدیریت لغو شده است."
        if sub.server_id != plan.server_id:
            return "❗️ این پلن برای تمدید این سرویس قابل استفاده نیست."
    if server.is_manual and await db.configs.count_available(plan.id) <= 0:
        return "❌ موجودی این پلن تمام شده است. لطفاً پلن دیگری انتخاب کنید یا بعداً مراجعه کنید."
    return plan, server


@router.callback_query(BuyCB.filter(F.action == "servers"))
async def cb_servers(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    message = callback_message(callback)
    if message:
        await show_servers(message, db, edit=True)


@router.callback_query(BuyCB.filter(F.action == "server"))
async def cb_server(callback: CallbackQuery, callback_data: BuyCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    server = await db.servers.get(callback_data.server_id)
    if server is None or not server.is_active:
        await callback.answer("❗️ این سرور در حال حاضر فعال نیست.", show_alert=True)
        return
    await callback.answer()
    many = len(await db.servers.list_for_sale()) > 1
    message = callback_message(callback)
    if message:
        await show_plans(message, db, server, back_to_servers=many)


# ----------------------------------------------------------------------
# پیش‌فاکتور
# ----------------------------------------------------------------------
@router.callback_query(BuyCB.filter(F.action == "plan"))
async def cb_plan(callback: CallbackQuery, callback_data: BuyCB, db: Database, user: User) -> None:
    result = await _validate_purchase(db, user, callback_data.plan_id, callback_data.sub_id)
    if isinstance(result, str):
        await callback.answer(result, show_alert=True)
        return
    plan, server = result
    await callback.answer()

    card, link = await _payment_methods(db)
    header = f"🔄 <b>پیش‌فاکتور تمدید سرویس #{callback_data.sub_id}</b>" if callback_data.sub_id else "🧾 <b>پیش‌فاکتور</b>"
    lines = [
        header,
        "",
        f"📦 پلن: <b>{h(plan.name)}</b>",
        f"🌍 سرور: {h(server.name)}",
        f"⏳ مدت: {plan.days} روز",
        f"📊 حجم: {fmt_traffic(plan.traffic_gb)}",
        f"💰 مبلغ قابل پرداخت: <b>{fmt_price(plan.price)}</b>",
    ]
    if plan.description:
        lines += ["", f"📝 {h(plan.description)}"]
    if card or link:
        lines += ["", "💳 روش پرداخت را انتخاب کنید:"]
    else:
        lines += ["", "⚠️ درگاه پرداخت هنوز توسط مدیریت تنظیم نشده است. لطفاً بعداً تلاش کنید یا با پشتیبانی تماس بگیرید."]
    await safe_edit(
        callback_message(callback), "\n".join(lines), invoice_kb(plan, sub_id=callback_data.sub_id, card=card, link=link)
    )


# ----------------------------------------------------------------------
# ساخت سفارش و نمایش اطلاعات پرداخت
# ----------------------------------------------------------------------
async def payment_instructions(db: Database, order_id: int, amount: int, method: str, user_id: int) -> tuple[str, str | None]:
    """متن راهنمای پرداخت و (در صورت وجود) آدرس لینک پرداخت."""
    note = (await db.settings.get("payment_note")).strip()
    if method == "card":
        card_number = await db.settings.get("card_number")
        holder = await db.settings.get("card_holder")
        bank = await db.settings.get("bank_name")
        lines = [
            "💳 <b>پرداخت کارت به کارت</b>",
            "",
            f"مبلغ <b>{fmt_price(amount)}</b> را به کارت زیر واریز کنید:",
            "",
            f"💳 <code>{h(card_number)}</code>",
        ]
        if holder:
            lines.append(f"👤 به نام: {h(holder)}")
        if bank:
            lines.append(f"🏦 بانک: {h(bank)}")
        url = None
    else:
        raw_link = (await db.settings.get("payment_link")).strip()
        # جایگذاری متغیرهای اختیاری در لینک پرداخت
        url = (
            raw_link.replace("{amount}", str(amount)).replace("{order_id}", str(order_id)).replace("{user_id}", str(user_id))
        )
        lines = [
            "🔗 <b>پرداخت آنلاین</b>",
            "",
            f"مبلغ <b>{fmt_price(amount)}</b> را از طریق دکمه زیر پرداخت کنید.",
        ]
        if not url.startswith(("http://", "https://")):
            lines += ["", f"🔗 {h(url)}"]
            url = None
    if note:
        lines += ["", note]
    lines += [
        "",
        "📸 پس از پرداخت، <b>تصویر رسید</b> یا <b>کد پیگیری</b> را همین‌جا ارسال کنید.",
        f"🆔 شماره سفارش: <code>#{order_id}</code>",
    ]
    return "\n".join(lines), url


@router.callback_query(BuyCB.filter(F.action == "pay"))
async def cb_pay(
    callback: CallbackQuery, callback_data: BuyCB, state: FSMContext, db: Database, user: User
) -> None:
    result = await _validate_purchase(db, user, callback_data.plan_id, callback_data.sub_id)
    if isinstance(result, str):
        await callback.answer(result, show_alert=True)
        return
    plan, _server = result
    card, link = await _payment_methods(db)
    if (callback_data.method == "card" and not card) or (callback_data.method == "link" and not link):
        await callback.answer("❗️ این روش پرداخت در حال حاضر فعال نیست.", show_alert=True)
        return
    await callback.answer()

    # هر کاربر در هر لحظه فقط یک سفارش پرداخت‌نشده دارد (سفارش‌های قبلی لغو می‌شوند)
    for old in await db.orders.pending_for_user(user.id):
        await db.orders.transition(old.id, [OrderStatus.PENDING], OrderStatus.CANCELED)

    order_id = await db.orders.create(
        user_id=user.id,
        plan_id=plan.id,
        kind=OrderKind.RENEW if callback_data.sub_id else OrderKind.NEW,
        amount=plan.price,
        plan_title=plan.name,
        method=callback_data.method,
        subscription_id=callback_data.sub_id or None,
    )
    log.info("Order #%s created by user %s (plan %s)", order_id, user.id, plan.id)
    await state.set_state(BuyStates.receipt)
    await state.update_data(order_id=order_id)

    text, url = await payment_instructions(db, order_id, plan.price, callback_data.method, user.id)
    await safe_edit(callback_message(callback), text, payment_kb(order_id, url))


@router.callback_query(OrderCB.filter(F.action == "receipt"))
async def cb_order_receipt(
    callback: CallbackQuery, callback_data: OrderCB, state: FSMContext, db: Database, user: User
) -> None:
    """ارسال رسید برای سفارشی که قبلاً ساخته شده (از بخش سفارش‌های من)."""
    order = await db.orders.get(callback_data.order_id)
    if order is None or order.user_id != user.id or order.status != OrderStatus.PENDING:
        await callback.answer("❗️ این سفارش قابل پرداخت نیست.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BuyStates.receipt)
    await state.update_data(order_id=order.id)
    text, url = await payment_instructions(db, order.id, order.amount, order.method, user.id)
    await safe_edit(callback_message(callback), text, payment_kb(order.id, url))


@router.callback_query(OrderCB.filter(F.action == "cancel"))
async def cb_order_cancel(
    callback: CallbackQuery, callback_data: OrderCB, state: FSMContext, db: Database, user: User
) -> None:
    order = await db.orders.get(callback_data.order_id)
    if order is None or order.user_id != user.id:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    if not await db.orders.transition(order.id, [OrderStatus.PENDING], OrderStatus.CANCELED):
        await callback.answer("❗️ این سفارش دیگر قابل لغو نیست.", show_alert=True)
        return
    data = await state.get_data()
    if data.get("order_id") == order.id:
        await state.clear()
    await callback.answer("سفارش لغو شد")
    await safe_edit(callback_message(callback), f"🚫 سفارش #{order.id} لغو شد.")


# ----------------------------------------------------------------------
# دریافت رسید پرداخت
# ----------------------------------------------------------------------
@router.message(BuyStates.receipt, F.photo | F.document | F.text)
async def receipt_received(
    message: Message,
    state: FSMContext,
    db: Database,
    user: User,
    bot: Bot,
    config: Config,
    is_admin: bool,
) -> None:
    data = await state.get_data()
    order = await db.orders.get(int(data.get("order_id") or 0))
    if order is None or order.user_id != user.id or order.status != OrderStatus.PENDING:
        await state.clear()
        await message.answer("❗️ سفارش معتبری برای این رسید پیدا نشد.", reply_markup=main_menu(is_admin))
        return

    if message.photo:
        kind, file_id, text = "photo", message.photo[-1].file_id, message.caption
    elif message.document:
        kind, file_id, text = "document", message.document.file_id, message.caption
    else:
        kind, file_id, text = "text", None, (message.text or "").strip()
        if len(text) < 4 or text.startswith("/"):
            await message.answer("⚠️ لطفاً تصویر رسید یا کد پیگیری معتبر (حداقل ۴ کاراکتر) ارسال کنید.")
            return

    changed = await db.orders.transition(
        order.id,
        [OrderStatus.PENDING],
        OrderStatus.WAITING,
        receipt_kind=kind,
        receipt_file_id=file_id,
        receipt_text=(text or "")[:1000] or None,
    )
    await state.clear()
    if not changed:
        await message.answer("❗️ وضعیت این سفارش تغییر کرده است.", reply_markup=main_menu(is_admin))
        return

    await message.answer(
        "✅ <b>رسید شما دریافت شد.</b>\n\n"
        f"⏳ سفارش <code>#{order.id}</code> پس از بررسی توسط مدیریت تایید می‌شود و سرویس "
        "به‌صورت خودکار برای شما ارسال خواهد شد. از صبر شما سپاسگزاریم 🌹",
        reply_markup=main_menu(is_admin),
    )
    updated = await db.orders.get(order.id)
    if updated is not None:
        await send_order_to_admins(bot, db, config, updated)


@router.message(BuyStates.receipt)
async def receipt_invalid(message: Message) -> None:
    await message.answer("⚠️ لطفاً <b>تصویر رسید</b> یا <b>کد پیگیری</b> پرداخت را ارسال کنید. برای لغو: /cancel")
