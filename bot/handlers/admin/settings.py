"""
تنظیمات پرداخت و تنظیمات عمومی ربات (قابل ویرایش از داخل ربات)
"""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.database import Database
from bot.keyboards.admin import admin_cancel_kb, bot_settings_kb, payment_settings_kb
from bot.keyboards.callbacks import AdminCB, ASettingCB
from bot.states import SettingEdit
from bot.utils.formatting import h, normalize_digits
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="admin_settings")

TOGGLE_KEYS = {"card_enabled": "payment", "link_enabled": "payment", "sales_enabled": "settings"}

# کلید: (صفحه، راهنمای ویرایش، قالب HTML دارد؟)
EDITABLE: dict[str, tuple[str, str, bool]] = {
    "card_number": ("payment", "💳 شماره کارت (۱۶ رقم) را بفرستید:", False),
    "card_holder": ("payment", "👤 نام صاحب کارت را بفرستید:", False),
    "bank_name": ("payment", "🏦 نام بانک را بفرستید (برای حذف: -):", False),
    "payment_link": (
        "payment",
        "🔗 لینک پرداخت را بفرستید (باید با https:// شروع شود؛ برای حذف: -)\n\n"
        "می‌توانید از این متغیرها در لینک استفاده کنید:\n"
        "<code>{amount}</code> مبلغ  |  <code>{order_id}</code> شماره سفارش  |  <code>{user_id}</code> آیدی کاربر",
        False,
    ),
    "payment_note": ("payment", "📝 توضیحات پرداخت را بفرستید (زیر اطلاعات پرداخت نمایش داده می‌شود؛ برای حذف: -):", True),
    "welcome_text": (
        "settings",
        "👋 متن خوش‌آمدگویی را بفرستید.\n<code>{name}</code> با نام کاربر جایگزین می‌شود. قالب‌بندی (بولد و ...) حفظ می‌شود.",
        True,
    ),
    "support_text": ("settings", "🎧 متن بخش پشتیبانی را بفرستید:", True),
    "guide_text": ("settings", "📚 متن راهنمای اتصال را بفرستید:", True),
}


async def payment_page(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    s = await db.settings.get_many(
        "card_enabled", "card_number", "card_holder", "bank_name", "link_enabled", "payment_link", "payment_note"
    )
    card_on, link_on = s["card_enabled"] == "1", s["link_enabled"] == "1"
    lines = [
        "💳 <b>تنظیمات پرداخت</b>",
        "",
        f"کارت به کارت: {'🟢 فعال' if card_on else '🔴 غیرفعال'}",
        f"  💳 شماره کارت: <code>{h(s['card_number'] or '—')}</code>",
        f"  👤 صاحب کارت: {h(s['card_holder'] or '—')}",
        f"  🏦 بانک: {h(s['bank_name'] or '—')}",
        "",
        f"پرداخت با لینک: {'🟢 فعال' if link_on else '🔴 غیرفعال'}",
        f"  🔗 لینک: {h(s['payment_link'] or '—')}",
        "",
        f"📝 توضیحات: {'تنظیم شده' if s['payment_note'] else '—'}",
    ]
    if card_on and not s["card_number"]:
        lines.append("\n⚠️ کارت به کارت فعال است ولی شماره کارت ثبت نشده؛ این روش به کاربران نمایش داده نمی‌شود.")
    if link_on and not s["payment_link"]:
        lines.append("\n⚠️ پرداخت با لینک فعال است ولی لینکی ثبت نشده است.")
    return "\n".join(lines), payment_settings_kb(card_on, link_on)


async def settings_page(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    sales = await db.settings.get_bool("sales_enabled")
    text = (
        "⚙️ <b>تنظیمات ربات</b>\n\n"
        f"🛒 فروش: {'🟢 فعال' if sales else '🔴 غیرفعال (کاربران نمی‌توانند خرید یا تمدید کنند)'}\n\n"
        "متن‌های قابل ویرایش را از دکمه‌های زیر تغییر دهید."
    )
    return text, bot_settings_kb(sales)


async def _page(db: Database, name: str) -> tuple[str, InlineKeyboardMarkup]:
    return await (payment_page(db) if name == "payment" else settings_page(db))


@router.callback_query(AdminCB.filter(F.section.in_({"payment", "settings"})))
async def cb_page(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await _page(db, callback_data.section)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(ASettingCB.filter(F.action == "toggle"))
async def cb_toggle(callback: CallbackQuery, callback_data: ASettingCB, db: Database) -> None:
    page = TOGGLE_KEYS.get(callback_data.key)
    if page is None:
        await callback.answer()
        return
    value = await db.settings.toggle(callback_data.key)
    await callback.answer("🟢 فعال شد" if value else "🔴 غیرفعال شد")
    text, markup = await _page(db, page)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(ASettingCB.filter(F.action == "edit"))
async def cb_edit(callback: CallbackQuery, callback_data: ASettingCB, state: FSMContext, db: Database) -> None:
    if callback_data.key not in EDITABLE:
        await callback.answer()
        return
    await callback.answer()
    await state.set_state(SettingEdit.value)
    await state.update_data(key=callback_data.key)
    _page_name, prompt, _html = EDITABLE[callback_data.key]
    current = await db.settings.get(callback_data.key)
    preview = f"\n\n📄 مقدار فعلی:\n{current if _html else h(current)}" if current else ""
    message = callback_message(callback)
    if message:
        await message.answer((prompt + preview)[:4000], reply_markup=admin_cancel_kb())


@router.message(SettingEdit.value, F.text)
async def edit_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    key = data.get("key", "")
    if key not in EDITABLE:
        await state.clear()
        return
    page, _prompt, is_html = EDITABLE[key]
    raw = (message.text or "").strip()
    value = message.html_text.strip() if is_html else raw

    if raw == "-" and key in ("bank_name", "payment_link", "payment_note"):
        value = ""
    elif key == "card_number":
        digits = re.sub(r"[\s\-]", "", normalize_digits(raw))
        if not digits.isdigit() or not 16 <= len(digits) <= 19:
            await message.answer("⚠️ شماره کارت باید ۱۶ رقم باشد.")
            return
        # نمایش خوانا: 6037-9975-1234-5678
        value = "-".join(digits[i : i + 4] for i in range(0, len(digits), 4))
    elif key == "payment_link" and not raw.startswith(("http://", "https://")):
        await message.answer("⚠️ لینک باید با https:// شروع شود.")
        return
    if len(value) > 3500:
        await message.answer("⚠️ متن خیلی طولانی است (حداکثر ۳۵۰۰ کاراکتر).")
        return

    await state.clear()
    await db.settings.set(key, value)
    text, markup = await _page(db, page)
    await message.answer("✅ ذخیره شد.\n\n" + text, reply_markup=markup)
