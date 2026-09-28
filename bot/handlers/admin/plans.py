"""
مدیریت پلن‌ها: افزودن (فرم مرحله‌ای)، ویرایش، فعال/غیرفعال و حذف
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.database import Database
from bot.database.models import Plan
from bot.keyboards.admin import (
    admin_cancel_kb,
    confirm_kb,
    plan_confirm_kb,
    plan_detail_kb,
    plan_servers_kb,
    plans_list_kb,
    skip_cancel_kb,
)
from bot.keyboards.callbacks import AdminCB, APlanCB
from bot.states import PlanEdit, PlanForm
from bot.utils.formatting import fmt_price, fmt_traffic, h, parse_float, parse_int
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="admin_plans")


# ----------------------------------------------------------------------
# نمایش
# ----------------------------------------------------------------------
async def plans_list(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    plans = await db.plans.list_all()
    servers = {s.id: s for s in await db.servers.list()}
    if not plans:
        text = "📦 <b>پلن‌ها</b>\n\nهنوز پلنی تعریف نشده است. با دکمه «➕ افزودن پلن» اولین پلن را بسازید."
    else:
        text = f"📦 <b>پلن‌ها</b> ({len(plans)} پلن)\n\n🟢 فعال   🔴 غیرفعال\nبرای مدیریت روی پلن بزنید:"
    return text, plans_list_kb(plans, servers)


async def plan_detail(db: Database, plan: Plan) -> tuple[str, InlineKeyboardMarkup]:
    server = await db.servers.get_any(plan.server_id)
    is_manual = bool(server and server.is_manual)
    lines = [
        f"📦 <b>{h(plan.name)}</b>  (#{plan.id})",
        "",
        f"🌍 سرور: {h(server.name) if server else '—'}",
        f"⏳ مدت: {plan.days} روز",
        f"📊 حجم: {fmt_traffic(plan.traffic_gb)}",
        f"💰 قیمت: {fmt_price(plan.price)}",
        f"🔢 ترتیب نمایش: {plan.sort_order}",
        f"🔰 وضعیت: {'🟢 فعال' if plan.is_active else '🔴 غیرفعال'}",
    ]
    if plan.description:
        lines.append(f"📝 توضیحات: {h(plan.description)}")
    if is_manual:
        available = await db.configs.count_available(plan.id)
        used = await db.configs.count_used(plan.id)
        lines.append(f"\n📦 انبار کانفیگ: {available} آزاد | {used} فروخته‌شده")
        if available == 0:
            lines.append("⚠️ موجودی این پلن صفر است و برای کاربران «ناموجود» نمایش داده می‌شود.")
    return "\n".join(lines), plan_detail_kb(plan, is_manual)


@router.callback_query(AdminCB.filter(F.section == "plans"))
async def cb_plans(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await plans_list(db)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(APlanCB.filter(F.action == "view"))
async def cb_view(callback: CallbackQuery, callback_data: APlanCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    plan = await db.plans.get(callback_data.plan_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await callback.answer()
    text, markup = await plan_detail(db, plan)
    await safe_edit(callback_message(callback), text, markup)


# ----------------------------------------------------------------------
# افزودن پلن (فرم مرحله‌ای)
# ----------------------------------------------------------------------
async def _ask_name(message: Message, state: FSMContext, server_id: int, *, edit: bool) -> None:
    await state.set_state(PlanForm.name)
    await state.update_data(server_id=server_id)
    text = "➕ <b>پلن جدید</b> — مرحله ۱ از ۵\n\n✏️ نام پلن را بفرستید:\n(مثال: یک ماهه ۵۰ گیگ)"
    if edit:
        await safe_edit(message, text, admin_cancel_kb())
    else:
        await message.answer(text, reply_markup=admin_cancel_kb())


@router.callback_query(APlanCB.filter(F.action == "new"))
async def cb_new(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    servers = await db.servers.list()
    if not servers:
        await callback.answer("❗️ ابتدا از بخش «🖥 سرورها» یک سرور اضافه کنید.", show_alert=True)
        return
    await callback.answer()
    message = callback_message(callback)
    if message is None:
        return
    if len(servers) == 1:
        await _ask_name(message, state, servers[0].id, edit=True)
    else:
        await safe_edit(message, "➕ <b>پلن جدید</b>\n\n🌍 این پلن برای کدام سرور است؟", plan_servers_kb(servers))


@router.callback_query(APlanCB.filter(F.action == "new_server"))
async def cb_new_server(callback: CallbackQuery, callback_data: APlanCB, state: FSMContext, db: Database) -> None:
    server = await db.servers.get(callback_data.server_id)
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    await callback.answer()
    message = callback_message(callback)
    if message:
        await _ask_name(message, state, server.id, edit=True)


@router.message(PlanForm.name, F.text)
async def form_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 1 <= len(name) <= 64:
        await message.answer("⚠️ نام پلن باید بین ۱ تا ۶۴ کاراکتر باشد.")
        return
    await state.update_data(name=name)
    await state.set_state(PlanForm.days)
    await message.answer("مرحله ۲ از ۵\n\n⏳ مدت پلن را به <b>روز</b> بفرستید:\n(مثال: 30)", reply_markup=admin_cancel_kb())


@router.message(PlanForm.days, F.text)
async def form_days(message: Message, state: FSMContext) -> None:
    days = parse_int(message.text or "")
    if days is None or not 1 <= days <= 3650:
        await message.answer("⚠️ یک عدد بین ۱ تا ۳۶۵۰ بفرستید.")
        return
    await state.update_data(days=days)
    await state.set_state(PlanForm.traffic)
    await message.answer(
        "مرحله ۳ از ۵\n\n📊 حجم پلن را به <b>گیگابایت</b> بفرستید:\n(برای نامحدود عدد 0 را بفرستید)",
        reply_markup=admin_cancel_kb(),
    )


@router.message(PlanForm.traffic, F.text)
async def form_traffic(message: Message, state: FSMContext) -> None:
    traffic = parse_float(message.text or "")
    if traffic is None or not 0 <= traffic <= 100000:
        await message.answer("⚠️ یک عدد معتبر بفرستید (0 = نامحدود).")
        return
    await state.update_data(traffic_gb=traffic)
    await state.set_state(PlanForm.price)
    await message.answer("مرحله ۴ از ۵\n\n💰 قیمت پلن را به <b>تومان</b> بفرستید:\n(مثال: 150000)", reply_markup=admin_cancel_kb())


@router.message(PlanForm.price, F.text)
async def form_price(message: Message, state: FSMContext) -> None:
    price = parse_int(message.text or "")
    if price is None or not 0 <= price <= 10**12:
        await message.answer("⚠️ یک عدد معتبر (به تومان) بفرستید.")
        return
    await state.update_data(price=price)
    await state.set_state(PlanForm.description)
    await message.answer(
        "مرحله ۵ از ۵\n\n📝 توضیحات پلن را بفرستید (اختیاری):\nمثلاً: مناسب اینستاگرام و یوتیوب، ۲ کاربره",
        reply_markup=skip_cancel_kb(APlanCB(action="skip_desc").pack()),
    )


async def _show_confirm(message: Message, state: FSMContext, db: Database, *, edit: bool) -> None:
    data = await state.get_data()
    server = await db.servers.get(int(data["server_id"]))
    await state.set_state(PlanForm.confirm)
    text = (
        "✅ <b>تایید اطلاعات پلن</b>\n\n"
        f"🌍 سرور: {h(server.name) if server else '—'}\n"
        f"📦 نام: {h(data['name'])}\n"
        f"⏳ مدت: {data['days']} روز\n"
        f"📊 حجم: {fmt_traffic(data['traffic_gb'])}\n"
        f"💰 قیمت: {fmt_price(data['price'])}\n"
        f"📝 توضیحات: {h(data.get('description') or '—')}"
    )
    if edit:
        await safe_edit(message, text, plan_confirm_kb())
    else:
        await message.answer(text, reply_markup=plan_confirm_kb())


@router.message(PlanForm.description, F.text)
async def form_description(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(description=(message.text or "").strip()[:500])
    await _show_confirm(message, state, db, edit=False)


@router.callback_query(APlanCB.filter(F.action == "skip_desc"), PlanForm.description)
async def cb_skip_description(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    await state.update_data(description="")
    message = callback_message(callback)
    if message:
        await _show_confirm(message, state, db, edit=True)


@router.callback_query(APlanCB.filter(F.action == "save"), PlanForm.confirm)
async def cb_save(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await state.clear()
    server = await db.servers.get(int(data["server_id"]))
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    plan_id = await db.plans.create(
        server_id=server.id,
        name=data["name"],
        days=int(data["days"]),
        traffic_gb=float(data["traffic_gb"]),
        price=int(data["price"]),
        description=data.get("description", ""),
    )
    await callback.answer("✅ پلن ذخیره شد")
    plan = await db.plans.get(plan_id)
    assert plan is not None
    text, markup = await plan_detail(db, plan)
    if server.is_manual:
        text += "\n\n💡 این سرور «دستی» است؛ برای فروش، از دکمه «📦 انبار کانفیگ این پلن» کانفیگ‌ها را اضافه کنید."
    await safe_edit(callback_message(callback), "✅ <b>پلن با موفقیت ساخته شد.</b>\n\n" + text, markup)


# ----------------------------------------------------------------------
# ویرایش
# ----------------------------------------------------------------------
EDIT_PROMPTS = {
    "name": "✏️ نام جدید پلن را بفرستید:",
    "price": "💰 قیمت جدید (تومان) را بفرستید:",
    "days": "⏳ مدت جدید (روز) را بفرستید:",
    "traffic_gb": "📊 حجم جدید (گیگابایت، 0 = نامحدود) را بفرستید:",
    "description": "📝 توضیحات جدید را بفرستید (برای حذف: -):",
    "sort_order": "🔢 ترتیب نمایش را بفرستید (عدد کوچک‌تر = بالاتر):",
}


@router.callback_query(APlanCB.filter(F.action == "edit"))
async def cb_edit(callback: CallbackQuery, callback_data: APlanCB, state: FSMContext) -> None:
    if callback_data.field not in EDIT_PROMPTS:
        await callback.answer()
        return
    await callback.answer()
    await state.set_state(PlanEdit.value)
    await state.update_data(plan_id=callback_data.plan_id, field=callback_data.field)
    message = callback_message(callback)
    if message:
        await message.answer(EDIT_PROMPTS[callback_data.field], reply_markup=admin_cancel_kb())


@router.message(PlanEdit.value, F.text)
async def edit_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    field, raw = data.get("field"), (message.text or "").strip()
    value: object
    if field == "name":
        if not 1 <= len(raw) <= 64:
            await message.answer("⚠️ نام باید بین ۱ تا ۶۴ کاراکتر باشد.")
            return
        value = raw
    elif field in ("price", "days", "sort_order"):
        number = parse_int(raw)
        limits = {"price": (0, 10**12), "days": (1, 3650), "sort_order": (-1000, 1000)}[field]
        if number is None or not limits[0] <= number <= limits[1]:
            await message.answer("⚠️ عدد وارد شده معتبر نیست.")
            return
        value = number
    elif field == "traffic_gb":
        traffic = parse_float(raw)
        if traffic is None or traffic < 0:
            await message.answer("⚠️ عدد وارد شده معتبر نیست.")
            return
        value = traffic
    elif field == "description":
        value = "" if raw == "-" else raw[:500]
    else:
        await state.clear()
        return

    await state.clear()
    plan_id = int(data["plan_id"])
    await db.plans.update(plan_id, **{field: value})
    plan = await db.plans.get(plan_id)
    if plan is None:
        await message.answer("پلن پیدا نشد.")
        return
    text, markup = await plan_detail(db, plan)
    await message.answer("✅ ذخیره شد.\n\n" + text, reply_markup=markup)


@router.callback_query(APlanCB.filter(F.action == "toggle"))
async def cb_toggle(callback: CallbackQuery, callback_data: APlanCB, db: Database) -> None:
    plan = await db.plans.get(callback_data.plan_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await db.plans.update(plan.id, is_active=0 if plan.is_active else 1)
    await callback.answer("🔴 غیرفعال شد" if plan.is_active else "🟢 فعال شد")
    plan = await db.plans.get(plan.id)
    assert plan is not None
    text, markup = await plan_detail(db, plan)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(APlanCB.filter(F.action == "del"))
async def cb_delete(callback: CallbackQuery, callback_data: APlanCB, db: Database) -> None:
    plan = await db.plans.get(callback_data.plan_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        f"🗑 آیا از حذف پلن «{h(plan.name)}» مطمئن هستید؟\n\n"
        "ℹ️ سرویس‌های فعلی کاربران و سوابق سفارش‌ها حفظ می‌شوند؛ فقط پلن از فروش حذف می‌شود.",
        confirm_kb(
            APlanCB(action="del_ok", plan_id=plan.id).pack(),
            APlanCB(action="view", plan_id=plan.id).pack(),
            yes_text="🗑 بله، حذف شود",
            no_text="🔙 انصراف",
        ),
    )


@router.callback_query(APlanCB.filter(F.action == "del_ok"))
async def cb_delete_ok(callback: CallbackQuery, callback_data: APlanCB, db: Database) -> None:
    await db.plans.soft_delete(callback_data.plan_id)
    await callback.answer("🗑 پلن حذف شد")
    text, markup = await plans_list(db)
    await safe_edit(callback_message(callback), text, markup)
