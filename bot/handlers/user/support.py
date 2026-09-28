"""
پشتیبانی و تیکت (سمت کاربر)

کاربر تیکت ثبت می‌کند، پیام برای همه ادمین‌ها ارسال می‌شود و پاسخ ادمین در همین
ربات به کاربر می‌رسد. کاربر می‌تواند تاریخچه تیکت را ببیند، پاسخ دهد یا آن را ببندد.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.config import Config
from bot.database import Database
from bot.database.models import Ticket, TicketStatus, User
from bot.handlers.admin.tickets import send_ticket_to_admins, ticket_history_text
from bot.keyboards.callbacks import TicketCB
from bot.keyboards.user import cancel_kb, main_menu, support_kb, ticket_view_kb, tickets_kb
from bot.states import TicketStates
from bot.utils.telegram import callback_message, safe_edit

router = Router(name="user_support")

MAX_OPEN_TICKETS = 3


async def show_support(message: Message, db: Database, *, edit: bool = False) -> None:
    text = await db.settings.get("support_text")
    if edit:
        await safe_edit(message, text, support_kb())
    else:
        await message.answer(text, reply_markup=support_kb())


def _extract_content(message: Message) -> tuple[str, str | None, str | None]:
    """(متن، file_id، نوع فایل) از پیام کاربر."""
    if message.photo:
        return (message.caption or "").strip(), message.photo[-1].file_id, "photo"
    if message.document:
        return (message.caption or "").strip(), message.document.file_id, "document"
    return (message.text or "").strip(), None, None


@router.callback_query(TicketCB.filter(F.action == "menu"))
async def cb_menu(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await callback.answer()
    message = callback_message(callback)
    if message:
        await show_support(message, db, edit=True)


@router.callback_query(TicketCB.filter(F.action == "new"))
async def cb_new(callback: CallbackQuery, state: FSMContext, db: Database, user: User) -> None:
    if await db.tickets.count_unclosed_for_user(user.id) >= MAX_OPEN_TICKETS:
        await callback.answer(
            f"❗️ شما {MAX_OPEN_TICKETS} تیکت باز دارید. لطفاً منتظر پاسخ بمانید یا از بخش «تیکت‌های من» ادامه دهید.",
            show_alert=True,
        )
        return
    await callback.answer()
    await state.set_state(TicketStates.new)
    await safe_edit(
        callback_message(callback),
        "✍️ <b>پیام خود را بنویسید</b>\n\nمی‌توانید متن، عکس یا فایل (همراه با توضیح) ارسال کنید.",
        cancel_kb(),
    )


@router.message(TicketStates.new, F.text | F.photo | F.document)
async def ticket_new_message(
    message: Message, state: FSMContext, db: Database, user: User, bot: Bot, config: Config, is_admin: bool
) -> None:
    text, file_id, file_kind = _extract_content(message)
    if not text and not file_id:
        await message.answer("⚠️ پیام خالی است. لطفاً متن یا تصویر ارسال کنید.")
        return
    subject = (text.splitlines()[0] if text else "📎 فایل پیوست")[:50]
    ticket_id = await db.tickets.create(user.id, subject)
    await db.tickets.add_message(ticket_id, "user", text, file_id, file_kind)
    await state.clear()
    await message.answer(
        f"✅ تیکت <code>#{ticket_id}</code> ثبت شد.\nپاسخ پشتیبانی در همین ربات برای شما ارسال می‌شود 🙏",
        reply_markup=main_menu(is_admin),
    )
    ticket = await db.tickets.get(ticket_id)
    if ticket is not None:
        await send_ticket_to_admins(bot, config, ticket, user, text, file_id, file_kind, is_new=True)


@router.callback_query(TicketCB.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery, state: FSMContext, db: Database, user: User) -> None:
    await state.clear()
    tickets = await db.tickets.list_for_user(user.id)
    await callback.answer()
    if not tickets:
        await safe_edit(callback_message(callback), "📭 شما هنوز تیکتی ثبت نکرده‌اید.", support_kb())
        return
    await safe_edit(callback_message(callback), "📂 <b>تیکت‌های شما</b>", tickets_kb(tickets))


async def _own_ticket(db: Database, user: User, ticket_id: int) -> Ticket | None:
    ticket = await db.tickets.get(ticket_id)
    return ticket if ticket is not None and ticket.user_id == user.id else None


@router.callback_query(TicketCB.filter(F.action == "view"))
async def cb_view(
    callback: CallbackQuery, callback_data: TicketCB, state: FSMContext, db: Database, user: User, config: Config
) -> None:
    await state.clear()
    ticket = await _own_ticket(db, user, callback_data.ticket_id)
    if ticket is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    await callback.answer()
    messages = await db.tickets.messages(ticket.id)
    await safe_edit(
        callback_message(callback), ticket_history_text(ticket, messages, config, for_admin=False), ticket_view_kb(ticket)
    )


@router.callback_query(TicketCB.filter(F.action == "reply"))
async def cb_reply(callback: CallbackQuery, callback_data: TicketCB, state: FSMContext, db: Database, user: User) -> None:
    ticket = await _own_ticket(db, user, callback_data.ticket_id)
    if ticket is None or ticket.status == TicketStatus.CLOSED:
        await callback.answer("❗️ این تیکت بسته شده است.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(TicketStates.reply)
    await state.update_data(ticket_id=ticket.id)
    message = callback_message(callback)
    if message:
        await message.answer(f"✍️ پاسخ خود را برای تیکت #{ticket.id} بنویسید:", reply_markup=cancel_kb())


@router.message(TicketStates.reply, F.text | F.photo | F.document)
async def ticket_reply_message(
    message: Message, state: FSMContext, db: Database, user: User, bot: Bot, config: Config, is_admin: bool
) -> None:
    data = await state.get_data()
    ticket = await _own_ticket(db, user, int(data.get("ticket_id") or 0))
    await state.clear()
    if ticket is None or ticket.status == TicketStatus.CLOSED:
        await message.answer("❗️ این تیکت بسته شده است.", reply_markup=main_menu(is_admin))
        return
    text, file_id, file_kind = _extract_content(message)
    await db.tickets.add_message(ticket.id, "user", text, file_id, file_kind)
    await message.answer(f"✅ پیام شما در تیکت #{ticket.id} ثبت شد.", reply_markup=main_menu(is_admin))
    await send_ticket_to_admins(bot, config, ticket, user, text, file_id, file_kind, is_new=False)


@router.callback_query(TicketCB.filter(F.action == "close"))
async def cb_close(callback: CallbackQuery, callback_data: TicketCB, db: Database, user: User) -> None:
    ticket = await _own_ticket(db, user, callback_data.ticket_id)
    if ticket is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    await db.tickets.set_status(ticket.id, TicketStatus.CLOSED)
    await callback.answer("تیکت بسته شد")
    await safe_edit(callback_message(callback), f"🔒 تیکت #{ticket.id} بسته شد.", support_kb())


@router.message(TicketStates.new)
@router.message(TicketStates.reply)
async def ticket_invalid(message: Message) -> None:
    await message.answer("⚠️ لطفاً متن، عکس یا فایل ارسال کنید. برای لغو: /cancel")
