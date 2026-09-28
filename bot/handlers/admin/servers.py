"""
مدیریت سرورها و انبار کانفیگ

انواع سرور:
    - دستی (manual): فقط نام می‌خواهد؛ کانفیگ‌ها برای هر پلن در انبار وارد می‌شوند.
    - 3x-ui: آدرس پنل + نام کاربری/رمز + آیدی اینباند(ها) + آدرس ساب (اختیاری)
    - Marzban / PasarGuard: آدرس پنل + نام کاربری/رمز ادمین (+ تگ اینباند یا آیدی گروه، اختیاری)

هنگام افزودن سرور پنلی، اتصال به صورت خودکار تست و لیست اینباندها نمایش داده می‌شود.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.database import Database
from bot.database.models import Server, ServerKind, now_ts
from bot.keyboards.admin import (
    SERVER_FIELDS,
    admin_cancel_kb,
    configs_kb,
    confirm_kb,
    server_detail_kb,
    server_kind_kb,
    server_plans_kb,
    servers_list_kb,
    skip_cancel_kb,
)
from bot.keyboards.callbacks import AConfigCB, AdminCB, AServerCB, CancelCB
from bot.services.panels import PanelError, get_panel
from bot.states import ConfigAdd, ServerEdit, ServerForm
from bot.utils.formatting import h
from bot.utils.telegram import callback_message, safe_edit

log = logging.getLogger(__name__)
router = Router(name="admin_servers")

MAX_CONFIG_FILE = 2 * 1024 * 1024  # حداکثر حجم فایل txt کانفیگ‌ها


def _mask(secret: str) -> str:
    if not secret:
        return "—"
    return secret[:2] + "•" * min(8, max(len(secret) - 2, 3))


# ----------------------------------------------------------------------
# نمایش
# ----------------------------------------------------------------------
async def server_detail(db: Database, server: Server) -> tuple[str, InlineKeyboardMarkup]:
    plans = await db.plans.list_for_server(server.id, only_active=False)
    lines = [
        f"🖥 <b>{h(server.name)}</b>  (#{server.id})",
        "",
        f"🔧 نوع: {server.kind_label}",
        f"🔰 وضعیت: {'🟢 فعال' if server.is_active else '🔴 غیرفعال'}",
    ]
    if not server.is_manual:
        inbound_label = "گروه‌ها/اینباندها" if server.kind == ServerKind.MARZBAN else "اینباندها"
        lines += [
            f"🌐 آدرس پنل: <code>{h(server.api_url)}</code>",
            f"👤 نام کاربری: <code>{h(server.api_user or '—')}</code>",
            f"🔑 رمز عبور: {_mask(server.api_pass)}",
        ]
        if server.kind == ServerKind.XUI:
            lines.append(f"🎟 توکن API: {'تنظیم شده ✅' if server.api_token else '—'}")
        lines.append(f"🔌 {inbound_label}: {h(server.inbound_ids or ('همه' if server.kind == ServerKind.MARZBAN else '—'))}")
        if server.kind == ServerKind.XUI:
            lines.append(f"🔗 آدرس ساب: {h(server.sub_url or '—')}")
            lines.append(f"📍 آدرس عمومی لینک‌ها: {h(server.address or '(همان آدرس پنل)')}")
    lines += [
        "",
        f"📦 پلن‌ها: {len(plans)}",
        f"👥 سرویس‌های فعال: {await db.servers.count_active_subscriptions(server.id)}",
    ]
    return "\n".join(lines), server_detail_kb(server)


@router.callback_query(AdminCB.filter(F.section == "servers"))
async def cb_servers(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    servers = await db.servers.list()
    text = "🖥 <b>سرورها</b>\n\n"
    text += "برای مدیریت روی سرور بزنید:" if servers else "هنوز سروری اضافه نشده است. با «➕ افزودن سرور» شروع کنید."
    await safe_edit(callback_message(callback), text, servers_list_kb(servers))


@router.callback_query(AServerCB.filter(F.action == "view"))
async def cb_view(callback: CallbackQuery, callback_data: AServerCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    server = await db.servers.get(callback_data.server_id)
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    await callback.answer()
    text, markup = await server_detail(db, server)
    await safe_edit(callback_message(callback), text, markup)


# ----------------------------------------------------------------------
# افزودن سرور
# ----------------------------------------------------------------------
@router.callback_query(AServerCB.filter(F.action == "new"))
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        "➕ <b>سرور جدید</b>\n\nنحوه ساخت کانفیگ برای این سرور را انتخاب کنید:\n\n"
        "📝 <b>دستی</b>: کانفیگ‌های آماده را خودتان در ربات وارد می‌کنید و ربات آن‌ها را می‌فروشد.\n"
        "🟦 <b>3x-ui</b>: ربات به صورت خودکار روی پنل سنایی کاربر می‌سازد (نسخه ۲ و ۳).\n"
        "🟪 <b>Marzban / PasarGuard</b>: ساخت خودکار کاربر روی پنل مرزبان یا پاسارگارد.",
        server_kind_kb(),
    )


@router.callback_query(AServerCB.filter(F.action == "kind"))
async def cb_kind(callback: CallbackQuery, callback_data: AServerCB, state: FSMContext) -> None:
    if callback_data.kind not in ServerKind.ALL:
        await callback.answer()
        return
    await callback.answer()
    await state.set_state(ServerForm.name)
    await state.update_data(kind=callback_data.kind)
    await safe_edit(
        callback_message(callback),
        "✏️ نام سرور/لوکیشن را بفرستید (به کاربران نمایش داده می‌شود):\n(مثال: 🇩🇪 آلمان)",
        admin_cancel_kb(),
    )


@router.message(ServerForm.name, F.text)
async def form_name(message: Message, state: FSMContext, db: Database) -> None:
    name = (message.text or "").strip()
    if not 1 <= len(name) <= 48:
        await message.answer("⚠️ نام باید بین ۱ تا ۴۸ کاراکتر باشد.")
        return
    data = await state.get_data()
    if data["kind"] == ServerKind.MANUAL:
        await state.clear()
        server_id = await db.servers.create(name=name, kind=ServerKind.MANUAL)
        server = await db.servers.get(server_id)
        assert server is not None
        text, markup = await server_detail(db, server)
        await message.answer(
            "✅ <b>سرور دستی ساخته شد.</b>\n\n💡 قدم بعد: از «📦 پلن‌ها» یک پلن برای این سرور بسازید و "
            "سپس کانفیگ‌ها را در انبار آن پلن وارد کنید.\n\n" + text,
            reply_markup=markup,
        )
        return
    await state.update_data(name=name)
    await state.set_state(ServerForm.url)
    if data["kind"] == ServerKind.XUI:
        example = (
            "🌐 آدرس پنل 3x-ui را همراه با مسیر مخفی (web base path) بفرستید.\n"
            "می‌توانید آدرس را مستقیماً از نوار مرورگر کپی کنید.\n\n"
            "مثال:\n<code>https://panel.example.com:2053/AbCdEf12</code>\n<code>http://1.2.3.4:2053/xyz</code>"
        )
    else:
        example = "🌐 آدرس پنل Marzban / PasarGuard را بفرستید.\n\nمثال:\n<code>https://panel.example.com:8000</code>"
    await message.answer(example, reply_markup=admin_cancel_kb())


@router.message(ServerForm.url, F.text)
async def form_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if " " in url or ("." not in url and "localhost" not in url):
        await message.answer("⚠️ آدرس نامعتبر است. مثال: https://panel.example.com:2053/path")
        return
    if "://" not in url:
        url = "http://" + url
    await state.update_data(api_url=url)
    await state.set_state(ServerForm.username)
    await message.answer("👤 نام کاربری ادمین پنل را بفرستید:", reply_markup=admin_cancel_kb())


@router.message(ServerForm.username, F.text)
async def form_username(message: Message, state: FSMContext) -> None:
    await state.update_data(api_user=(message.text or "").strip())
    await state.set_state(ServerForm.password)
    await message.answer("🔑 رمز عبور پنل را بفرستید:\n(پیام شما پس از دریافت حذف می‌شود)", reply_markup=admin_cancel_kb())


def _temp_server(data: dict[str, Any]) -> Server:
    """ساخت شیء موقت سرور برای تست اتصال قبل از ذخیره."""
    return Server(
        id=0,
        name=data.get("name", ""),
        kind=data["kind"],
        api_url=data.get("api_url", ""),
        api_user=data.get("api_user", ""),
        api_pass=data.get("api_pass", ""),
        api_token="",
        inbound_ids="",
        sub_url="",
        address="",
        is_active=1,
        is_deleted=0,
        created_at=now_ts(),
    )


def _retry_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔁 ورود مجدد اطلاعات", callback_data=AServerCB(action="reenter"))
    builder.button(text="💾 ادامه بدون تست", callback_data=AServerCB(action="skip_test"))
    builder.button(text="❌ انصراف", callback_data=CancelCB(to="admin"))
    builder.adjust(1)
    return builder.as_markup()


async def _ask_inbounds(message: Message, state: FSMContext, kind: str, report: str) -> None:
    await state.set_state(ServerForm.inbounds)
    if kind == ServerKind.XUI:
        await message.answer(
            f"{report}\n\n🔌 آیدی اینباند(هایی) که کاربران روی آن ساخته شوند را بفرستید.\n"
            "برای چند اینباند با کاما جدا کنید (مثال: <code>1</code> یا <code>1,3</code>).\n"
            "ℹ️ پروتکل‌های پشتیبانی‌شده: VLESS، VMess، Trojan",
            reply_markup=admin_cancel_kb(),
        )
    else:
        await message.answer(
            f"{report}\n\n🔌 (اختیاری) در Marzban تگ اینباندها و در PasarGuard آیدی گروه‌ها را با کاما بفرستید.\n"
            "برای استفاده از همه اینباندها/گروه‌ها «⏭ رد کردن» را بزنید.",
            reply_markup=skip_cancel_kb(AServerCB(action="skip_inbounds").pack()),
        )


@router.message(ServerForm.password, F.text)
async def form_password(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    await state.update_data(api_pass=(message.text or "").strip())
    try:
        await message.delete()  # حذف رمز از تاریخچه چت
    except Exception:  # noqa: BLE001
        pass
    data = await state.get_data()
    status = await message.answer("⏳ در حال تست اتصال به پنل...")
    server = _temp_server(data)
    try:
        report = await get_panel(server, db, verify_ssl=config.panel_verify_ssl).test()
    except PanelError as exc:
        await safe_edit(status, f"❌ <b>اتصال به پنل ناموفق بود</b>\n\n{h(exc)}", _retry_kb())
        return
    await status.delete()
    await _ask_inbounds(message, state, data["kind"], h(report))


@router.callback_query(AServerCB.filter(F.action == "reenter"), ServerForm.password)
async def cb_reenter(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(ServerForm.url)
    await safe_edit(callback_message(callback), "🌐 آدرس پنل را دوباره بفرستید:", admin_cancel_kb())


@router.callback_query(AServerCB.filter(F.action == "skip_test"), ServerForm.password)
async def cb_skip_test(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    message = callback_message(callback)
    if message:
        await _ask_inbounds(message, state, data["kind"], "⚠️ اتصال تست نشد.")


@router.message(ServerForm.inbounds, F.text)
async def form_inbounds(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").replace("،", ",").replace(" ", "")
    parts = [p for p in raw.split(",") if p]
    data = await state.get_data()
    if data["kind"] == ServerKind.XUI and (not parts or not all(p.isdigit() for p in parts)):
        await message.answer("⚠️ آیدی اینباند باید عدد باشد (مثال: 1 یا 1,3).")
        return
    await state.update_data(inbound_ids=",".join(parts))
    if data["kind"] == ServerKind.XUI:
        await state.set_state(ServerForm.sub_url)
        await message.answer(
            "🔗 (اختیاری) آدرس پایه ساب‌اسکریپشن پنل را بفرستید تا لینک اشتراک هم به کاربر داده شود.\n"
            "این آدرس را در تنظیمات پنل (Subscription) پیدا می‌کنید؛ شناسه ساب به انتهای آن اضافه می‌شود.\n\n"
            "مثال: <code>https://sub.example.com:2096/sub</code>",
            reply_markup=skip_cancel_kb(AServerCB(action="skip_sub").pack()),
        )
    else:
        await _save_server(message, state, db, edit=False)


@router.callback_query(AServerCB.filter(F.action == "skip_inbounds"), ServerForm.inbounds)
async def cb_skip_inbounds(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    await state.update_data(inbound_ids="")
    message = callback_message(callback)
    if message:
        await _save_server(message, state, db, edit=True)


@router.message(ServerForm.sub_url, F.text)
async def form_sub_url(message: Message, state: FSMContext, db: Database) -> None:
    url = (message.text or "").strip()
    if not url.startswith(("http://", "https://")):
        await message.answer("⚠️ آدرس باید با http:// یا https:// شروع شود.")
        return
    await state.update_data(sub_url=url)
    await _save_server(message, state, db, edit=False)


@router.callback_query(AServerCB.filter(F.action == "skip_sub"), ServerForm.sub_url)
async def cb_skip_sub(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    message = callback_message(callback)
    if message:
        await _save_server(message, state, db, edit=True)


async def _save_server(message: Message, state: FSMContext, db: Database, *, edit: bool) -> None:
    data = await state.get_data()
    await state.clear()
    server_id = await db.servers.create(
        name=data["name"],
        kind=data["kind"],
        api_url=data.get("api_url", ""),
        api_user=data.get("api_user", ""),
        api_pass=data.get("api_pass", ""),
        inbound_ids=data.get("inbound_ids", ""),
        sub_url=data.get("sub_url", ""),
    )
    server = await db.servers.get(server_id)
    assert server is not None
    text, markup = await server_detail(db, server)
    text = "✅ <b>سرور ذخیره شد.</b>\n💡 قدم بعد: از «📦 پلن‌ها» برای این سرور پلن بسازید.\n\n" + text
    if edit:
        await safe_edit(message, text, markup)
    else:
        await message.answer(text, reply_markup=markup)


# ----------------------------------------------------------------------
# عملیات روی سرور
# ----------------------------------------------------------------------
@router.callback_query(AServerCB.filter(F.action == "test"))
async def cb_test(callback: CallbackQuery, callback_data: AServerCB, db: Database, config: Config) -> None:
    server = await db.servers.get(callback_data.server_id)
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    await callback.answer("⏳ در حال تست اتصال...")
    try:
        report = await get_panel(server, db, verify_ssl=config.panel_verify_ssl).test()
    except PanelError as exc:
        report = f"❌ اتصال ناموفق بود:\n{exc}"
    message = callback_message(callback)
    if message:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 مشخصات سرور", callback_data=AServerCB(action="view", server_id=server.id))
        await message.answer(f"🧪 <b>تست سرور {h(server.name)}</b>\n\n{h(report)}"[:4000], reply_markup=builder.as_markup())


@router.callback_query(AServerCB.filter(F.action == "toggle"))
async def cb_toggle(callback: CallbackQuery, callback_data: AServerCB, db: Database) -> None:
    server = await db.servers.get(callback_data.server_id)
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    await db.servers.update(server.id, is_active=0 if server.is_active else 1)
    await callback.answer("🔴 غیرفعال شد" if server.is_active else "🟢 فعال شد")
    server = await db.servers.get(server.id)
    assert server is not None
    text, markup = await server_detail(db, server)
    await safe_edit(callback_message(callback), text, markup)


@router.callback_query(AServerCB.filter(F.action == "field"))
async def cb_field(callback: CallbackQuery, callback_data: AServerCB, state: FSMContext) -> None:
    if callback_data.field not in SERVER_FIELDS:
        await callback.answer()
        return
    await callback.answer()
    await state.set_state(ServerEdit.value)
    await state.update_data(server_id=callback_data.server_id, field=callback_data.field)
    prompt = SERVER_FIELDS[callback_data.field][1]
    if callback_data.field == "address":
        prompt += "\n\nℹ️ فقط وقتی لازم است که ربات با آدرس داخلی (مثل 127.0.0.1) به پنل وصل می‌شود ولی کاربران باید دامنه/IP عمومی را ببینند."
    if callback_data.field == "api_token":
        prompt += "\n\nℹ️ در 3x-ui نسخه ۳ از Settings ← Security ← API Token دریافت می‌شود و جایگزین نام کاربری/رمز می‌شود (مناسب وقتی ورود دومرحله‌ای فعال است)."
    message = callback_message(callback)
    if message:
        await message.answer(prompt, reply_markup=admin_cancel_kb())


@router.message(ServerEdit.value, F.text)
async def edit_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    field, raw = data.get("field"), (message.text or "").strip()
    optional = {"api_token", "sub_url", "address"}
    if field not in SERVER_FIELDS:
        await state.clear()
        return
    if field in optional and raw == "-":
        raw = ""
    if field == "api_url":
        if not raw or " " in raw:
            await message.answer("⚠️ آدرس نامعتبر است.")
            return
        if "://" not in raw:
            raw = "http://" + raw
    if field == "sub_url" and raw and not raw.startswith(("http://", "https://")):
        await message.answer("⚠️ آدرس باید با http:// یا https:// شروع شود.")
        return
    if field == "inbound_ids":
        raw = ",".join(p for p in raw.replace("،", ",").replace(" ", "").split(",") if p)
    if field == "name" and not 1 <= len(raw) <= 48:
        await message.answer("⚠️ نام باید بین ۱ تا ۴۸ کاراکتر باشد.")
        return
    if field in ("api_pass", "api_token"):
        try:
            await message.delete()
        except Exception:  # noqa: BLE001
            pass
    await state.clear()
    server_id = int(data["server_id"])
    await db.servers.update(server_id, **{field: raw})
    server = await db.servers.get(server_id)
    if server is None:
        await message.answer("سرور پیدا نشد.")
        return
    if server.kind == ServerKind.XUI and field == "inbound_ids":
        if not raw or not all(p.isdigit() for p in raw.split(",")):
            await message.answer("⚠️ برای 3x-ui آیدی اینباندها باید عدد باشد؛ لطفاً دوباره ویرایش کنید.")
    text, markup = await server_detail(db, server)
    await message.answer("✅ ذخیره شد.\n\n" + text, reply_markup=markup)


@router.callback_query(AServerCB.filter(F.action == "plans"))
async def cb_plans(callback: CallbackQuery, callback_data: AServerCB, db: Database) -> None:
    server = await db.servers.get(callback_data.server_id)
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    await callback.answer()
    plans = await db.plans.list_for_server(server.id, only_active=False)
    stock = await db.configs.available_by_plan()
    text = f"📦 <b>پلن‌های {h(server.name)}</b>"
    if server.is_manual:
        text += "\n\nعدد کنار هر پلن = تعداد کانفیگ آزاد در انبار. برای مدیریت انبار روی پلن بزنید."
    if not plans:
        text += "\n\nهنوز پلنی برای این سرور ساخته نشده است."
    await safe_edit(callback_message(callback), text, server_plans_kb(plans, stock, server))


@router.callback_query(AServerCB.filter(F.action == "del"))
async def cb_delete(callback: CallbackQuery, callback_data: AServerCB, db: Database) -> None:
    server = await db.servers.get(callback_data.server_id)
    if server is None:
        await callback.answer("سرور پیدا نشد", show_alert=True)
        return
    await callback.answer()
    active = await db.servers.count_active_subscriptions(server.id)
    warning = f"\n\n⚠️ این سرور {active} سرویس فعال دارد؛ سرویس‌ها حذف نمی‌شوند ولی تمدید آن‌ها ممکن نخواهد بود." if active else ""
    await safe_edit(
        callback_message(callback),
        f"🗑 آیا از حذف سرور «{h(server.name)}» و همه پلن‌های آن مطمئن هستید؟{warning}",
        confirm_kb(
            AServerCB(action="del_ok", server_id=server.id).pack(),
            AServerCB(action="view", server_id=server.id).pack(),
            yes_text="🗑 بله، حذف شود",
            no_text="🔙 انصراف",
        ),
    )


@router.callback_query(AServerCB.filter(F.action == "del_ok"))
async def cb_delete_ok(callback: CallbackQuery, callback_data: AServerCB, db: Database) -> None:
    await db.servers.soft_delete(callback_data.server_id)
    await callback.answer("🗑 سرور حذف شد")
    servers = await db.servers.list()
    await safe_edit(callback_message(callback), "🖥 <b>سرورها</b>", servers_list_kb(servers))


# ----------------------------------------------------------------------
# انبار کانفیگ (سرورهای دستی)
# ----------------------------------------------------------------------
async def stock_view(db: Database, plan_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    plan = await db.plans.get(plan_id)
    if plan is None:
        return None
    available = await db.configs.count_available(plan.id)
    used = await db.configs.count_used(plan.id)
    text = (
        f"📦 <b>انبار کانفیگ «{h(plan.name)}»</b>\n\n"
        f"🟢 آزاد (آماده فروش): {available}\n"
        f"🔴 فروخته‌شده: {used}\n\n"
        "ℹ️ هر کانفیگ فقط به یک کاربر تحویل داده می‌شود."
    )
    return text, configs_kb(plan.id, available > 0)


@router.callback_query(AConfigCB.filter(F.action == "view"))
async def cb_stock(callback: CallbackQuery, callback_data: AConfigCB, state: FSMContext, db: Database) -> None:
    await state.clear()
    result = await stock_view(db, callback_data.plan_id)
    if result is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await callback.answer()
    await safe_edit(callback_message(callback), *result)


def _done_kb(plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ پایان", callback_data=AConfigCB(action="view", plan_id=plan_id))
    return builder.as_markup()


@router.callback_query(AConfigCB.filter(F.action == "add"))
async def cb_add(callback: CallbackQuery, callback_data: AConfigCB, state: FSMContext, db: Database) -> None:
    plan = await db.plans.get(callback_data.plan_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await callback.answer()
    await state.set_state(ConfigAdd.content)
    await state.update_data(plan_id=plan.id)
    await safe_edit(
        callback_message(callback),
        f"📥 <b>افزودن کانفیگ به «{h(plan.name)}»</b>\n\n"
        "کانفیگ‌ها را بفرستید؛ <b>هر خط یک کانفیگ</b> (vless://، vmess://، لینک ساب و ...).\n"
        "می‌توانید چند پیام پشت سر هم یا یک فایل <code>.txt</code> بفرستید.\n"
        "در پایان دکمه «✅ پایان» را بزنید.",
        _done_kb(plan.id),
    )


async def _add_configs(message: Message, db: Database, plan_id: int, content: str) -> None:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        await message.answer("⚠️ کانفیگی پیدا نشد.")
        return
    added, duplicates = await db.configs.add_many(plan_id, lines)
    available = await db.configs.count_available(plan_id)
    text = f"✅ {added} کانفیگ اضافه شد."
    if duplicates:
        text += f"\n♻️ {duplicates} مورد تکراری نادیده گرفته شد."
    text += f"\n📦 موجودی آزاد: {available}\n\nمی‌توانید ادامه دهید یا «✅ پایان» را بزنید."
    await message.answer(text, reply_markup=_done_kb(plan_id))


@router.message(ConfigAdd.content, F.text)
async def configs_text(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await _add_configs(message, db, int(data["plan_id"]), message.text or "")


@router.message(ConfigAdd.content, F.document)
async def configs_file(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    document = message.document
    assert document is not None
    if (document.file_size or 0) > MAX_CONFIG_FILE:
        await message.answer("⚠️ حجم فایل زیاد است (حداکثر ۲ مگابایت).")
        return
    buffer = io.BytesIO()
    await bot.download(document, destination=buffer)
    try:
        content = buffer.getvalue().decode("utf-8-sig")
    except UnicodeDecodeError:
        await message.answer("⚠️ فایل باید متنی (UTF-8) باشد.")
        return
    data = await state.get_data()
    await _add_configs(message, db, int(data["plan_id"]), content)


@router.callback_query(AConfigCB.filter(F.action == "export"))
async def cb_export(callback: CallbackQuery, callback_data: AConfigCB, db: Database) -> None:
    items = await db.configs.list_available(callback_data.plan_id)
    if not items:
        await callback.answer("انبار خالی است", show_alert=True)
        return
    await callback.answer()
    content = "\n".join(item.content for item in items).encode()
    message = callback_message(callback)
    if message:
        await message.answer_document(
            BufferedInputFile(content, filename=f"plan_{callback_data.plan_id}_configs.txt"),
            caption=f"📄 {len(items)} کانفیگ آزاد",
        )


@router.callback_query(AConfigCB.filter(F.action == "clear"))
async def cb_clear(callback: CallbackQuery, callback_data: AConfigCB) -> None:
    await callback.answer()
    await safe_edit(
        callback_message(callback),
        "🗑 همه کانفیگ‌های <b>آزاد</b> این پلن حذف شوند؟ (کانفیگ‌های فروخته‌شده حفظ می‌شوند)",
        confirm_kb(
            AConfigCB(action="clear_ok", plan_id=callback_data.plan_id).pack(),
            AConfigCB(action="view", plan_id=callback_data.plan_id).pack(),
        ),
    )


@router.callback_query(AConfigCB.filter(F.action == "clear_ok"))
async def cb_clear_ok(callback: CallbackQuery, callback_data: AConfigCB, db: Database) -> None:
    removed = await db.configs.delete_available(callback_data.plan_id)
    await callback.answer(f"🗑 {removed} کانفیگ حذف شد")
    result = await stock_view(db, callback_data.plan_id)
    if result:
        await safe_edit(callback_message(callback), *result)
