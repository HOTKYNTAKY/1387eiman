"""
سرویس‌های من (سمت کاربر): مشاهده وضعیت، دریافت کانفیگ و تمدید
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import Config
from bot.database import Database
from bot.database.models import SubStatus, Subscription, User
from bot.handlers.user.buy import show_plans
from bot.keyboards.callbacks import SubCB
from bot.keyboards.user import sub_detail_kb, subs_list_kb
from bot.services.delivery import send_subscription, subscription_status_text
from bot.services.provisioning import Provisioner
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="user_services")


async def _own_subscription(db: Database, user: User, sub_id: int) -> Subscription | None:
    """سرویس فقط اگر متعلق به همین کاربر باشد برگردانده می‌شود (جلوگیری از دسترسی غیرمجاز)."""
    sub = await db.subscriptions.get(sub_id)
    return sub if sub is not None and sub.user_id == user.id else None


async def show_services(message: Message, db: Database, user: User, *, edit: bool = False) -> None:
    subs = await db.subscriptions.list_for_user(user.id)
    if not subs:
        text = "📭 شما هنوز سرویسی ندارید.\nبرای خرید از دکمه «🛒 خرید سرویس» استفاده کنید."
        markup = None
    else:
        text = "📦 <b>سرویس‌های شما</b>\n\n🟢 فعال   🔴 منقضی   ⚫️ لغو شده\n\nبرای مشاهده جزئیات روی سرویس بزنید:"
        markup = subs_list_kb(subs)
    if edit:
        await safe_edit(message, text, markup)
    else:
        await message.answer(text, reply_markup=markup)


async def show_renew_list(message: Message, db: Database, user: User) -> None:
    subs = [s for s in await db.subscriptions.list_for_user(user.id) if s.status != SubStatus.DISABLED]
    if not subs:
        await message.answer("📭 شما سرویسی برای تمدید ندارید. برای خرید از «🛒 خرید سرویس» استفاده کنید.")
        return
    await message.answer("🔄 <b>کدام سرویس را می‌خواهید تمدید کنید؟</b>", reply_markup=subs_list_kb(subs, "renew"))


@router.callback_query(SubCB.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery, state: FSMContext, db: Database, user: User) -> None:
    await state.clear()
    await callback.answer()
    message = callback_message(callback)
    if message:
        await show_services(message, db, user, edit=True)


@router.callback_query(SubCB.filter(F.action == "view"))
async def cb_view(
    callback: CallbackQuery,
    callback_data: SubCB,
    state: FSMContext,
    db: Database,
    user: User,
    config: Config,
    provisioner: Provisioner,
) -> None:
    await state.clear()
    sub = await _own_subscription(db, user, callback_data.sub_id)
    if sub is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    await callback.answer("⏳ در حال دریافت اطلاعات...")
    usage = await provisioner.usage(sub) if sub.status != SubStatus.DISABLED else None
    server = await db.servers.get_any(sub.server_id) if sub.server_id else None
    await safe_edit(callback_message(callback), subscription_status_text(sub, server, usage, config), sub_detail_kb(sub))


@router.callback_query(SubCB.filter(F.action == "config"))
async def cb_config(
    callback: CallbackQuery, callback_data: SubCB, db: Database, user: User, bot: Bot, config: Config
) -> None:
    sub = await _own_subscription(db, user, callback_data.sub_id)
    if sub is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    if sub.status == SubStatus.DISABLED:
        await callback.answer("⛔️ این سرویس لغو شده است.", show_alert=True)
        return
    await callback.answer()
    await send_subscription(bot, db, config, sub, header="🔗 <b>اطلاعات اتصال سرویس</b>", chat_id=user.id)


@router.callback_query(SubCB.filter(F.action == "renew"))
async def cb_renew(
    callback: CallbackQuery, callback_data: SubCB, state: FSMContext, db: Database, user: User
) -> None:
    await state.clear()
    sub = await _own_subscription(db, user, callback_data.sub_id)
    if sub is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    if sub.status == SubStatus.DISABLED:
        await callback.answer("⛔️ این سرویس توسط مدیریت لغو شده و قابل تمدید نیست.", show_alert=True)
        return
    if not await db.settings.get_bool("sales_enabled"):
        await callback.answer(texts.SALES_DISABLED, show_alert=True)
        return
    server = await db.servers.get(sub.server_id) if sub.server_id else None
    if server is None or not server.is_active:
        await callback.answer("❗️ سرور این سرویس دیگر فعال نیست؛ لطفاً یک سرویس جدید خریداری کنید.", show_alert=True)
        return
    if not await db.plans.list_for_server(server.id):
        await callback.answer("❗️ در حال حاضر پلنی برای تمدید این سرویس موجود نیست.", show_alert=True)
        return
    await callback.answer()
    message = callback_message(callback)
    if message:
        await show_plans(message, db, server, sub_id=sub.id)
