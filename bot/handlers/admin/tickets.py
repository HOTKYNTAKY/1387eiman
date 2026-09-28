"""مدیریت تیکت‌های پشتیبانی (سمت ادمین)."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.database import Database
from bot.database.models import Ticket, TicketMessage, TicketStatus, User
from bot.keyboards.admin import admin_cancel_kb, admin_ticket_kb, admin_tickets_kb, back_kb
from bot.keyboards.callbacks import AdminCB, ATicketCB, TicketCB
from bot.states import AdminTicket
from bot.utils.formatting import fmt_date, h, user_link
from bot.utils.telegram import callback_message, safe_edit, safe_send

log = logging.getLogger(__name__)
router = Router(name="admin_tickets")


def ticket_history_text(ticket: Ticket, messages: list[TicketMessage], config: Config, *, for_admin: bool) -> str:
    """تاریخچه پیام‌های تیکت (در صورت طولانی بودن، پیام‌های قدیمی حذف می‌شوند)."""
    header = [
        f"🎫 <b>تیکت #{ticket.id}</b> — {ticket.status_label}",
        f"📌 موضوع: {h(ticket.subject)}",
        "━━━━━━━━━━━━━━",
    ]
    blocks: list[str] = []
    for item in messages:
        if item.sender == "admin":
            who = "🎧 پشتیبانی"
        else:
            who = "👤 کاربر" if for_admin else "👤 شما"
        attachment = " 📎" if item.file_id else ""
        body = h(item.text) if item.text else "<i>(فایل پیوست)</i>"
        blocks.append(f"<b>{who}</b>{attachment} | {fmt_date(item.created_at, config.timezone)}\n{body}")
    # محدودیت طول پیام تلگرام
    while blocks and len("\n\n".join(header + blocks)) > 3900:
        blocks.pop(0)
    return "\n".join(header) + "\n\n" + "\n\n".join(blocks)


async def send_ticket_to_admins(
    bot: Bot,
    config: Config,
    ticket: Ticket,
    user: User,
    text: str,
    file_id: str | None,
    file_kind: str | None,
    *,
    is_new: bool,
) -> None:
    """ارسال پیام تیکت کاربر برای همه ادمین‌ها."""
    title = "🎫 <b>تیکت جدید</b>" if is_new else "💬 <b>پیام جدید در تیکت</b>"
    body = (
        f"{title} #{ticket.id}\n"
        f"👤 {user_link(user.id, user.full_name)} | <code>{user.id}</code>\n"
        f"📌 {h(ticket.subject)}\n"
        "━━━━━━━━━━━━━━\n"
        f"{h(text) if text else '<i>(فایل پیوست)</i>'}"
    )
    markup = admin_ticket_kb(ticket)
    for admin_id in config.admin_ids:
        try:
            if file_kind == "photo" and file_id:
                await bot.send_photo(admin_id, file_id, caption=body[:1024], reply_markup=markup)
            elif file_kind == "document" and file_id:
                await bot.send_document(admin_id, file_id, caption=body[:1024], reply_markup=markup)
            else:
                await bot.send_message(admin_id, body[:4096], reply_markup=markup)
        except TelegramAPIError as exc:
            log.warning("Cannot send ticket #%s to admin %s: %s", ticket.id, admin_id, exc)


@router.callback_query(AdminCB.filter(F.section == "tickets"))
async def cb_tickets(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    tickets = await db.tickets.list_by_status(TicketStatus.OPEN, limit=30)
    if not tickets:
        await safe_edit(callback_message(callback), "✅ هیچ تیکتی منتظر پاسخ نیست.", back_kb())
        return
    await safe_edit(callback_message(callback), "🎫 <b>تیکت‌های منتظر پاسخ</b>", admin_tickets_kb(tickets))


@router.callback_query(ATicketCB.filter(F.action == "view"))
async def cb_view(callback: CallbackQuery, callback_data: ATicketCB, db: Database, config: Config) -> None:
    ticket = await db.tickets.get(callback_data.ticket_id)
    if ticket is None:
        await callback.answer("تیکت پیدا نشد", show_alert=True)
        return
    await callback.answer()
    user = await db.users.get(ticket.user_id)
    messages = await db.tickets.messages(ticket.id)
    text = ticket_history_text(ticket, messages, config, for_admin=True)
    if user:
        text = f"👤 {user_link(user.id, user.full_name)} | <code>{user.id}</code>\n" + text
    message = callback_message(callback)
    if message:
        # همیشه پیام جدید (پیام قبلی ممکن است عکس باشد)
        await message.answer(text, reply_markup=admin_ticket_kb(ticket))


@router.callback_query(ATicketCB.filter(F.action == "reply"))
async def cb_reply(callback: CallbackQuery, callback_data: ATicketCB, state: FSMContext, db: Database) -> None:
    ticket = await db.tickets.get(callback_data.ticket_id)
    if ticket is None or ticket.status == TicketStatus.CLOSED:
        await callback.answer("❗️ این تیکت بسته شده است.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminTicket.reply)
    await state.update_data(ticket_id=ticket.id)
    message = callback_message(callback)
    if message:
        await message.answer(f"✍️ پاسخ تیکت #{ticket.id} را بنویسید (متن، عکس یا فایل):", reply_markup=admin_cancel_kb())


@router.message(AdminTicket.reply, F.text | F.photo | F.document)
async def reply_received(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    ticket = await db.tickets.get(int(data.get("ticket_id") or 0))
    await state.clear()
    if ticket is None:
        await message.answer("❗️ تیکت پیدا نشد.")
        return

    if message.photo:
        text, file_id, file_kind = (message.caption or "").strip(), message.photo[-1].file_id, "photo"
    elif message.document:
        text, file_id, file_kind = (message.caption or "").strip(), message.document.file_id, "document"
    else:
        text, file_id, file_kind = (message.text or "").strip(), None, None
    await db.tickets.add_message(ticket.id, "admin", text, file_id, file_kind)

    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ پاسخ", callback_data=TicketCB(action="reply", ticket_id=ticket.id))
    builder.button(text="🔒 بستن تیکت", callback_data=TicketCB(action="close", ticket_id=ticket.id))
    markup = builder.as_markup()
    header = f"📩 <b>پاسخ پشتیبانی — تیکت #{ticket.id}</b>\n\n"

    delivered = True
    try:
        if file_kind == "photo" and file_id:
            await bot.send_photo(ticket.user_id, file_id, caption=(header + h(text))[:1024], reply_markup=markup)
        elif file_kind == "document" and file_id:
            await bot.send_document(ticket.user_id, file_id, caption=(header + h(text))[:1024], reply_markup=markup)
        else:
            delivered = await safe_send(bot, ticket.user_id, header + h(text), db=db, reply_markup=markup) is not None
    except TelegramAPIError as exc:
        log.warning("Cannot deliver ticket reply to %s: %s", ticket.user_id, exc)
        delivered = False
    await message.answer(
        f"✅ پاسخ تیکت #{ticket.id} ثبت شد." + ("" if delivered else "\n⚠️ ارسال برای کاربر ناموفق بود."),
        reply_markup=back_kb("tickets", "🔙 تیکت‌ها"),
    )


@router.callback_query(ATicketCB.filter(F.action == "close"))
async def cb_close(callback: CallbackQuery, callback_data: ATicketCB, db: Database, bot: Bot) -> None:
    ticket = await db.tickets.get(callback_data.ticket_id)
    if ticket is None:
        await callback.answer("تیکت پیدا نشد", show_alert=True)
        return
    await db.tickets.set_status(ticket.id, TicketStatus.CLOSED)
    await callback.answer("تیکت بسته شد")
    await safe_send(bot, ticket.user_id, f"🔒 تیکت #{ticket.id} توسط پشتیبانی بسته شد.", db=db)
    message = callback_message(callback)
    if message:
        await message.answer(f"🔒 تیکت #{ticket.id} بسته شد.", reply_markup=back_kb("tickets", "🔙 تیکت‌ها"))
