"""
بررسی سفارش‌ها توسط ادمین

- پس از ارسال رسید توسط کاربر، سفارش همراه با رسید برای همه ادمین‌ها ارسال می‌شود.
- تایید: وضعیت به صورت اتمی از waiting به paid تغییر می‌کند (کلیک دوباره یا
  تایید همزمان دو ادمین باعث تحویل دوباره نمی‌شود)، سپس سرویس ساخته و تحویل می‌شود.
- اگر تحویل خودکار ناموفق باشد (مثلاً پنل در دسترس نیست)، سفارش در وضعیت paid
  می‌ماند و ادمین می‌تواند دوباره تلاش کند یا کانفیگ را دستی بفرستد.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.database import Database
from bot.database.models import Order, OrderKind, OrderStatus, now_ts
from bot.keyboards.admin import (
    admin_cancel_kb,
    back_kb,
    order_failed_kb,
    order_review_kb,
    orders_list_kb,
    reject_reason_kb,
)
from bot.keyboards.callbacks import AdminCB, AOrderCB
from bot.services.delivery import send_subscription
from bot.services.panels import PanelError
from bot.services.provisioning import DeliveryError, Provisioner
from bot.states import OrderAdmin
from bot.utils.formatting import fmt_date, fmt_price, h, user_link
from bot.utils.telegram import callback_message, safe_edit, safe_send

log = logging.getLogger(__name__)
router = Router(name="admin_orders")

METHOD_LABELS = {"card": "💳 کارت به کارت", "link": "🔗 لینک پرداخت", "admin": "👤 ادمین"}


async def order_admin_text(db: Database, config: Config, order: Order) -> str:
    """متن خلاصه سفارش برای ادمین (زیر ۱۰۲۴ کاراکتر تا در کپشن عکس جا شود)."""
    user = await db.users.get(order.user_id)
    plan = await db.plans.get_any(order.plan_id) if order.plan_id else None
    server = await db.servers.get_any(plan.server_id) if plan else None
    lines = [
        f"🧾 <b>سفارش #{order.id}</b> — {order.kind_label}",
        "",
        f"👤 کاربر: {user_link(order.user_id, user.full_name if user else None)}",
        f"🆔 آیدی: <code>{order.user_id}</code>" + (f" | @{h(user.username)}" if user and user.username else ""),
        f"📦 پلن: {h(order.plan_title)}",
    ]
    if server:
        lines.append(f"🌍 سرور: {h(server.name)}")
    if order.kind == OrderKind.RENEW and order.subscription_id:
        lines.append(f"🔄 تمدید سرویس: #{order.subscription_id}")
    lines += [
        f"💰 مبلغ: <b>{fmt_price(order.amount)}</b>",
        f"💳 روش: {METHOD_LABELS.get(order.method, order.method)}",
        f"🕒 زمان: {fmt_date(order.updated_at, config.timezone)}",
        f"📍 وضعیت: {order.status_label}",
    ]
    if order.receipt_text:
        lines.append(f"📝 توضیح/کد پیگیری: <code>{h(order.receipt_text[:200])}</code>")
    if order.note and order.status == OrderStatus.PAID:
        lines.append(f"⚠️ خطای تحویل: {h(order.note[:200])}")
    return "\n".join(lines)


async def send_order_to_admins(bot: Bot, db: Database, config: Config, order: Order) -> None:
    """ارسال سفارش جدید (همراه با تصویر/فایل رسید) برای همه ادمین‌ها."""
    text = await order_admin_text(db, config, order)
    markup = order_review_kb(order.id)
    for admin_id in config.admin_ids:
        try:
            await _send_order_message(bot, admin_id, order, text, markup)
        except TelegramAPIError as exc:
            log.warning("Cannot send order #%s to admin %s: %s", order.id, admin_id, exc)


async def _send_order_message(bot: Bot, chat_id: int, order: Order, text: str, markup) -> None:  # type: ignore[no-untyped-def]
    if order.receipt_kind == "photo" and order.receipt_file_id:
        await bot.send_photo(chat_id, order.receipt_file_id, caption=text, reply_markup=markup)
    elif order.receipt_kind == "document" and order.receipt_file_id:
        await bot.send_document(chat_id, order.receipt_file_id, caption=text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup)


async def _append_status(message: Message | None, status_line: str) -> None:
    """افزودن نتیجه بررسی به پیام سفارش و حذف دکمه‌ها."""
    if message is None:
        return
    try:
        if message.caption is not None or message.photo or message.document:
            caption = (message.html_text or "")[:900]
            await message.edit_caption(caption=f"{caption}\n\n{status_line}", reply_markup=None)
        else:
            await message.edit_text(f"{message.html_text}\n\n{status_line}", reply_markup=None)
    except TelegramAPIError as exc:
        log.debug("Cannot update order message: %s", exc)


async def deliver_and_report(
    report_chat_id: int,
    bot: Bot,
    db: Database,
    config: Config,
    provisioner: Provisioner,
    order_id: int,
    *,
    manual_links: list[str] | None = None,
    date_only: bool = False,
    notify_user_on_failure: bool = True,
) -> bool:
    """
    تحویل سفارش پرداخت‌شده و گزارش نتیجه به ادمین (در چت report_chat_id).
    :return: True در صورت موفقیت
    """
    order = await db.orders.get(order_id)
    if order is None or order.status != OrderStatus.PAID:
        await safe_send(bot, report_chat_id, "❗️ این سفارش در وضعیت قابل تحویل نیست.")
        return False

    old_sub = await db.subscriptions.get(order.subscription_id) if order.kind == OrderKind.RENEW and order.subscription_id else None
    try:
        sub = await provisioner.fulfill_order(order, manual_links=manual_links, date_only=date_only)
    except Exception as exc:
        known = isinstance(exc, (PanelError, DeliveryError))
        if not known:
            log.exception("Unexpected error while delivering order #%s", order_id)
        error_text = str(exc) if known else f"{exc.__class__.__name__}: {exc}"
        await db.orders.update(order_id, note=error_text[:500])
        await safe_send(
            bot,
            report_chat_id,
            f"⚠️ <b>تحویل خودکار سفارش #{order_id} ناموفق بود</b>\n\n<code>{h(error_text[:800])}</code>\n\n"
            "پس از رفع مشکل «تلاش مجدد» را بزنید یا کانفیگ را دستی ارسال کنید:",
            reply_markup=order_failed_kb(order_id, order.kind == OrderKind.RENEW),
        )
        if notify_user_on_failure:
            await safe_send(
                bot,
                order.user_id,
                f"✅ پرداخت سفارش #{order_id} تایید شد.\n⏳ سرویس شما به‌زودی توسط پشتیبانی تحویل داده می‌شود 🙏",
                db=db,
            )
        return False

    # اطلاع به کاربر
    if order.kind == OrderKind.RENEW and old_sub is not None and sub.config == old_sub.config and sub.sub_link == old_sub.sub_link:
        # کانفیگ تغییری نکرده؛ فقط اطلاعات تمدید ارسال می‌شود
        delivered = (
            await safe_send(
                bot,
                sub.user_id,
                f"✅ <b>سرویس #{sub.id} با موفقیت تمدید شد!</b>\n\n"
                f"📅 تاریخ انقضای جدید: {fmt_date(sub.expires_at, config.timezone)}\n"
                "🔗 کانفیگ شما تغییری نکرده و می‌توانید همچنان از آن استفاده کنید.",
                db=db,
            )
            is not None
        )
    else:
        header = {
            OrderKind.NEW: "🎉 <b>پرداخت شما تایید شد و سرویس آماده است!</b>",
            OrderKind.RENEW: "✅ <b>سرویس شما تمدید شد!</b> (کانفیگ جدید)",
            OrderKind.GIFT: "🎁 <b>یک سرویس هدیه برای شما فعال شد!</b>",
        }.get(order.kind, "🎉 <b>سرویس شما آماده است!</b>")
        delivered = await send_subscription(bot, db, config, sub, header=header)

    await safe_send(
        bot,
        report_chat_id,
        f"✅ سفارش #{order_id} تحویل شد ← سرویس #{sub.id}"
        + ("" if delivered else "\n⚠️ ارسال پیام به کاربر ناموفق بود (احتمالاً ربات را بلاک کرده است).")
    )
    return True


# ----------------------------------------------------------------------
# لیست سفارش‌های منتظر
# ----------------------------------------------------------------------
@router.callback_query(AdminCB.filter(F.section == "orders"))
async def cb_orders(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    orders = await db.orders.list_by_status([OrderStatus.WAITING, OrderStatus.PAID], limit=30)
    if not orders:
        await safe_edit(callback_message(callback), "✅ هیچ سفارشی منتظر بررسی نیست.", back_kb())
        return
    await safe_edit(
        callback_message(callback),
        "🧾 <b>سفارش‌های منتظر بررسی</b>\n\n🕓 منتظر تایید پرداخت   ⚠️ تایید شده ولی تحویل ناموفق",
        orders_list_kb(orders),
    )


@router.callback_query(AOrderCB.filter(F.action == "view"))
async def cb_view(callback: CallbackQuery, callback_data: AOrderCB, db: Database, bot: Bot, config: Config) -> None:
    order = await db.orders.get(callback_data.order_id)
    if order is None:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    await callback.answer()
    text = await order_admin_text(db, config, order)
    if order.status == OrderStatus.WAITING:
        markup = order_review_kb(order.id)
    elif order.status == OrderStatus.PAID:
        markup = order_failed_kb(order.id, order.kind == OrderKind.RENEW)
    else:
        markup = None
    message = callback_message(callback)
    if message:
        await _send_order_message(bot, message.chat.id, order, text, markup)


# ----------------------------------------------------------------------
# تایید
# ----------------------------------------------------------------------
@router.callback_query(AOrderCB.filter(F.action == "approve"))
async def cb_approve(
    callback: CallbackQuery,
    callback_data: AOrderCB,
    db: Database,
    bot: Bot,
    config: Config,
    provisioner: Provisioner,
) -> None:
    order_id = callback_data.order_id
    if not await db.orders.transition(order_id, [OrderStatus.WAITING], OrderStatus.PAID, paid_at=now_ts()):
        order = await db.orders.get(order_id)
        await callback.answer(
            f"این سفارش قبلاً بررسی شده است ({order.status_label if order else 'نامشخص'}).", show_alert=True
        )
        await _append_status(callback_message(callback), f"ℹ️ وضعیت: {order.status_label if order else '-'}")
        return
    await callback.answer("⏳ در حال ساخت و تحویل سرویس...")
    admin_name = h(callback.from_user.full_name)
    message = callback_message(callback)
    await _append_status(message, f"✅ تایید شد توسط {admin_name}")
    log.info("Order #%s approved by admin %s", order_id, callback.from_user.id)
    await deliver_and_report(callback.from_user.id, bot, db, config, provisioner, order_id)


@router.callback_query(AOrderCB.filter(F.action == "retry"))
async def cb_retry(
    callback: CallbackQuery,
    callback_data: AOrderCB,
    db: Database,
    bot: Bot,
    config: Config,
    provisioner: Provisioner,
) -> None:
    await callback.answer("⏳ تلاش مجدد...")
    await _append_status(callback_message(callback), "🔄 تلاش مجدد...")
    await deliver_and_report(
        callback.from_user.id, bot, db, config, provisioner, callback_data.order_id, notify_user_on_failure=False
    )


@router.callback_query(AOrderCB.filter(F.action == "dateonly"))
async def cb_date_only(
    callback: CallbackQuery,
    callback_data: AOrderCB,
    db: Database,
    bot: Bot,
    config: Config,
    provisioner: Provisioner,
) -> None:
    """فقط تمدید تاریخ در ربات (ادمین کانفیگ را خودش روی سرور تمدید می‌کند)."""
    await callback.answer()
    await _append_status(callback_message(callback), "📅 تمدید تاریخ بدون تغییر کانفیگ")
    await deliver_and_report(
        callback.from_user.id, bot, db, config, provisioner, callback_data.order_id,
        date_only=True, notify_user_on_failure=False,
    )


@router.callback_query(AOrderCB.filter(F.action == "manual"))
async def cb_manual(callback: CallbackQuery, callback_data: AOrderCB, state: FSMContext, db: Database) -> None:
    order = await db.orders.get(callback_data.order_id)
    if order is None or order.status != OrderStatus.PAID:
        await callback.answer("❗️ این سفارش در وضعیت قابل تحویل نیست.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(OrderAdmin.manual_config)
    await state.update_data(order_id=order.id)
    message = callback_message(callback)
    if message:
        await message.answer(
            f"✍️ کانفیگ(های) سفارش #{order.id} را بفرستید (هر خط یک کانفیگ یا لینک ساب):",
            reply_markup=admin_cancel_kb(),
        )


@router.message(OrderAdmin.manual_config, F.text)
async def manual_config_received(
    message: Message, state: FSMContext, db: Database, bot: Bot, config: Config, provisioner: Provisioner
) -> None:
    lines = [line.strip() for line in (message.text or "").splitlines() if line.strip()]
    if not lines:
        await message.answer("⚠️ متن خالی است. کانفیگ را ارسال کنید.")
        return
    data = await state.get_data()
    await state.clear()
    await deliver_and_report(
        message.chat.id, bot, db, config, provisioner, int(data.get("order_id") or 0), manual_links=lines,
        notify_user_on_failure=False,
    )


# ----------------------------------------------------------------------
# رد سفارش
# ----------------------------------------------------------------------
async def _reject(bot: Bot, db: Database, order_id: int, reason: str | None) -> Order | None:
    if not await db.orders.transition(order_id, [OrderStatus.WAITING], OrderStatus.REJECTED, note=reason):
        return None
    order = await db.orders.get(order_id)
    if order is not None:
        text = f"❌ <b>سفارش #{order.id} رد شد.</b>"
        if reason:
            text += f"\n\n📝 دلیل: {h(reason)}"
        text += "\n\nدر صورت نیاز از بخش «🎧 پشتیبانی» با ما در ارتباط باشید."
        await safe_send(bot, order.user_id, text, db=db)
    log.info("Order #%s rejected (%s)", order_id, reason or "no reason")
    return order


@router.callback_query(AOrderCB.filter(F.action == "reject"))
async def cb_reject(callback: CallbackQuery, callback_data: AOrderCB, state: FSMContext, db: Database) -> None:
    order = await db.orders.get(callback_data.order_id)
    if order is None or order.status != OrderStatus.WAITING:
        await callback.answer("این سفارش قبلاً بررسی شده است.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(OrderAdmin.reject_reason)
    await state.update_data(order_id=order.id)
    message = callback_message(callback)
    if message:
        await message.answer(
            f"✍️ دلیل رد سفارش #{order.id} را بنویسید (برای کاربر ارسال می‌شود):",
            reply_markup=reject_reason_kb(order.id),
        )


@router.callback_query(AOrderCB.filter(F.action == "reject_now"))
async def cb_reject_now(callback: CallbackQuery, callback_data: AOrderCB, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    order = await _reject(bot, db, callback_data.order_id, None)
    if order is None:
        await callback.answer("این سفارش قبلاً بررسی شده است.", show_alert=True)
        return
    await callback.answer("سفارش رد شد")
    await safe_edit(callback_message(callback), f"❌ سفارش #{order.id} رد شد و به کاربر اطلاع داده شد.")


@router.message(OrderAdmin.reject_reason, F.text)
async def reject_reason_received(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    order = await _reject(bot, db, int(data.get("order_id") or 0), (message.text or "").strip()[:500])
    if order is None:
        await message.answer("❗️ این سفارش قبلاً بررسی شده است.")
        return
    await message.answer(f"❌ سفارش #{order.id} رد شد و دلیل آن برای کاربر ارسال شد.")
