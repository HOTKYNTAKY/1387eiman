"""
تست‌های سناریوی کامل: پیام‌ها از ابتدا تا انتها از Dispatcher واقعی عبور می‌کنند.
"""

from __future__ import annotations

from bot.database.models import OrderStatus, SubStatus, TicketStatus
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
    BuyCB,
    SubCB,
    TicketCB,
)
from bot.services.backup import create_backup
from bot.texts import Btn

from .conftest import ADMIN_ID, Env, buttons, method_text

USER = 2001
OTHER = 2002


async def setup_manual_shop(env: Env, stock: int = 3) -> tuple[int, int]:
    """یک سرور دستی + پلن + موجودی + شماره کارت."""
    server_id = await env.db.servers.create(name="🇩🇪 آلمان", kind="manual")
    plan_id = await env.db.plans.create(server_id=server_id, name="یک ماهه", days=30, traffic_gb=50, price=150000)
    await env.db.configs.add_many(plan_id, [f"vless://uuid-{i}@1.2.3.4:443?security=reality#c{i}" for i in range(stock)])
    await env.db.settings.set("card_number", "6037-9975-1234-5678")
    await env.db.settings.set("card_holder", "علی رضایی")
    return server_id, plan_id


async def buy_until_receipt(env: Env, plan_id: int, sub_id: int = 0) -> int:
    """کاربر پلن را انتخاب، روش کارت به کارت را انتخاب و رسید (عکس) ارسال می‌کند."""
    await env.click(USER, BuyCB(action="plan", plan_id=plan_id, sub_id=sub_id))
    replies = await env.click(USER, BuyCB(action="pay", plan_id=plan_id, sub_id=sub_id, method="card"))
    assert "6037-9975-1234-5678" in method_text(env.session.of("EditMessageText", "SendMessage")[-1])
    assert replies
    replies = await env.send(USER, photo="receipt-photo-1", caption="پرداخت شد")
    assert "رسید شما دریافت شد" in method_text(replies[0])
    order = (await env.db.orders.list_for_user(USER, 1))[0]
    assert order.status == OrderStatus.WAITING
    return order.id


# ----------------------------------------------------------------------
async def test_start_registers_user_and_shows_menu(env: Env) -> None:
    replies = await env.send(USER, "/start")
    assert len(replies) == 1
    assert "User2001" in method_text(replies[0])  # {name} جایگزین شده
    keyboard = [b.text for row in replies[0].reply_markup.keyboard for b in row]
    assert Btn.BUY in keyboard and Btn.ADMIN not in keyboard
    assert (await env.db.users.get(USER)) is not None

    admin_replies = await env.send(ADMIN_ID, "/start")
    keyboard = [b.text for row in admin_replies[0].reply_markup.keyboard for b in row]
    assert Btn.ADMIN in keyboard


async def test_non_admin_cannot_access_admin_panel(env: Env) -> None:
    replies = await env.send(USER, "/admin")
    assert "پنل مدیریت" not in method_text(replies[0])
    replies = await env.click(USER, AdminCB(section="stats"))
    assert type(replies[0]).__name__ == "AnswerCallbackQuery"
    assert "منقضی" in replies[0].text  # هندلر fallback؛ هیچ داده مدیریتی نمایش داده نشد
    replies = await env.send(USER, "/backup")
    assert not env.session.of("SendDocument")


async def test_full_purchase_with_manual_stock(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env)
    await env.send(USER, "/start")

    # منوی خرید: چون فقط یک سرور هست، مستقیم پلن‌ها نمایش داده می‌شوند
    replies = await env.send(USER, Btn.BUY)
    assert "یک ماهه" in method_text(replies[0])
    assert any("150,000" in text for text, _ in buttons(replies[0]))

    order_id = await buy_until_receipt(env, plan_id)

    # رسید برای ادمین ارسال شده است
    photos = env.session.of("SendPhoto")
    assert photos and photos[-1].chat_id == ADMIN_ID and photos[-1].photo == "receipt-photo-1"
    assert any("approve" in data for _, data in buttons(photos[-1]))

    # تایید ادمین → تحویل خودکار
    start = len(env.session.requests)
    await env.click(ADMIN_ID, AOrderCB(action="approve", order_id=order_id), photo_message=True)
    order = await env.db.orders.get(order_id)
    assert order.status == OrderStatus.COMPLETED and order.subscription_id

    to_user = [m for m in env.session.of("SendMessage", since=start) if m.chat_id == USER]
    assert to_user and "vless://uuid-0" in method_text(to_user[0])
    qr = [m for m in env.session.of("SendPhoto", since=start) if m.chat_id == USER]
    assert qr, "QR code must be sent"
    assert await env.db.configs.count_available(plan_id) == 2

    # تایید دوباره همان سفارش نباید سرویس دوم بسازد
    replies = await env.click(ADMIN_ID, AOrderCB(action="approve", order_id=order_id), photo_message=True)
    assert "قبلاً بررسی" in replies[0].text
    assert await env.db.subscriptions.count_total() == 1

    # کاربر سرویس خود را می‌بیند
    replies = await env.send(USER, Btn.MY_SERVICES)
    assert any(f"#{order.subscription_id}" in text for text, _ in buttons(replies[0]))
    replies = await env.click(USER, SubCB(action="view", sub_id=order.subscription_id))
    assert "فعال" in method_text(env.session.of("EditMessageText")[-1])


async def test_renewal_extends_expiry_and_delivers_new_config(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env)
    await env.send(USER, "/start")
    order_id = await buy_until_receipt(env, plan_id)
    await env.click(ADMIN_ID, AOrderCB(action="approve", order_id=order_id), photo_message=True)
    sub = await env.db.subscriptions.get((await env.db.orders.get(order_id)).subscription_id)

    await env.click(USER, SubCB(action="renew", sub_id=sub.id))
    renew_order = await buy_until_receipt(env, plan_id, sub_id=sub.id)
    await env.click(ADMIN_ID, AOrderCB(action="approve", order_id=renew_order), photo_message=True)

    renewed = await env.db.subscriptions.get(sub.id)
    assert renewed.expires_at == sub.expires_at + 30 * 86400
    assert renewed.config != sub.config  # کانفیگ جدید از انبار
    assert await env.db.subscriptions.count_total() == 1


async def test_out_of_stock_plan_cannot_be_bought(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env, stock=0)
    await env.send(USER, "/start")
    replies = await env.click(USER, BuyCB(action="plan", plan_id=plan_id))
    assert replies[0].show_alert and "موجودی" in replies[0].text


async def test_failed_delivery_can_be_fixed_manually(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env, stock=1)
    await env.send(USER, "/start")
    order_id = await buy_until_receipt(env, plan_id)
    await env.db.configs.pop(plan_id)  # موجودی قبل از تایید تمام می‌شود

    replies = await env.click(ADMIN_ID, AOrderCB(action="approve", order_id=order_id), photo_message=True)
    failure = [m for m in replies if "ناموفق" in method_text(m)]
    assert failure and any("manual" in d for _, d in buttons(failure[0]))
    assert (await env.db.orders.get(order_id)).status == OrderStatus.PAID

    await env.click(ADMIN_ID, AOrderCB(action="manual", order_id=order_id))
    await env.send(ADMIN_ID, "vless://manual-config@5.6.7.8:443#manual")
    order = await env.db.orders.get(order_id)
    assert order.status == OrderStatus.COMPLETED
    sub = await env.db.subscriptions.get(order.subscription_id)
    assert sub.config == "vless://manual-config@5.6.7.8:443#manual"


async def test_admin_rejects_order_with_reason(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env)
    await env.send(USER, "/start")
    order_id = await buy_until_receipt(env, plan_id)
    await env.click(ADMIN_ID, AOrderCB(action="reject", order_id=order_id), photo_message=True)
    start = len(env.session.requests)
    await env.send(ADMIN_ID, "مبلغ واریزی کمتر است")
    assert (await env.db.orders.get(order_id)).status == OrderStatus.REJECTED
    to_user = [m for m in env.session.of("SendMessage", since=start) if m.chat_id == USER]
    assert "مبلغ واریزی کمتر است" in method_text(to_user[0])


async def test_admin_wizards_create_server_plan_and_stock(env: Env) -> None:
    await env.send(ADMIN_ID, "/start")
    await env.click(ADMIN_ID, AServerCB(action="new"))
    await env.click(ADMIN_ID, AServerCB(action="kind", kind="manual"))
    replies = await env.send(ADMIN_ID, "🇳🇱 هلند")
    assert "سرور دستی ساخته شد" in method_text(replies[0])
    server = (await env.db.servers.list())[0]

    await env.click(ADMIN_ID, APlanCB(action="new"))  # فقط یک سرور → مستقیم نام پلن
    await env.send(ADMIN_ID, "سه ماهه نامحدود")
    await env.send(ADMIN_ID, "۹۰")  # ارقام فارسی
    await env.send(ADMIN_ID, "0")
    await env.send(ADMIN_ID, "390,000")
    await env.click(ADMIN_ID, APlanCB(action="skip_desc"))
    await env.click(ADMIN_ID, APlanCB(action="save"))
    plan = (await env.db.plans.list_for_server(server.id))[0]
    assert (plan.name, plan.days, plan.traffic_gb, plan.price) == ("سه ماهه نامحدود", 90, 0, 390000)

    await env.click(ADMIN_ID, AConfigCB(action="add", plan_id=plan.id))
    replies = await env.send(ADMIN_ID, "vless://a\nvless://b\n\nvless://a")
    assert "2 کانفیگ اضافه شد" in method_text(replies[0])
    assert await env.db.configs.count_available(plan.id) == 2

    # ویرایش قیمت
    await env.click(ADMIN_ID, APlanCB(action="edit", plan_id=plan.id, field="price"))
    await env.send(ADMIN_ID, "۴۰۰۰۰۰")
    assert (await env.db.plans.get(plan.id)).price == 400000


async def test_ticket_conversation(env: Env) -> None:
    await env.send(USER, "/start")
    await env.click(USER, TicketCB(action="new"))
    start = len(env.session.requests)
    await env.send(USER, "کانفیگ وصل نمی‌شود")
    ticket = (await env.db.tickets.list_for_user(USER))[0]
    assert ticket.status == TicketStatus.OPEN
    admin_msgs = [m for m in env.session.of("SendMessage", since=start) if m.chat_id == ADMIN_ID]
    assert "کانفیگ وصل نمی‌شود" in method_text(admin_msgs[0])

    await env.click(ADMIN_ID, ATicketCB(action="reply", ticket_id=ticket.id))
    start = len(env.session.requests)
    await env.send(ADMIN_ID, "لطفاً برنامه را آپدیت کنید")
    to_user = [m for m in env.session.of("SendMessage", since=start) if m.chat_id == USER]
    assert "لطفاً برنامه را آپدیت کنید" in method_text(to_user[0])
    assert (await env.db.tickets.get(ticket.id)).status == TicketStatus.ANSWERED

    await env.click(USER, TicketCB(action="close", ticket_id=ticket.id))
    assert (await env.db.tickets.get(ticket.id)).status == TicketStatus.CLOSED


async def test_user_cannot_access_other_users_data(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env)
    await env.send(USER, "/start")
    await env.send(OTHER, "/start")
    order_id = await buy_until_receipt(env, plan_id)
    await env.click(ADMIN_ID, AOrderCB(action="approve", order_id=order_id), photo_message=True)
    sub_id = (await env.db.orders.get(order_id)).subscription_id

    for data in (SubCB(action="view", sub_id=sub_id), SubCB(action="config", sub_id=sub_id)):
        replies = await env.click(OTHER, data)
        assert replies[0].show_alert
        assert not any("vless://" in method_text(m) for m in replies)


async def test_banned_user_is_ignored(env: Env) -> None:
    await env.send(USER, "/start")
    await env.click(ADMIN_ID, AUserCB(action="ban", user_id=USER))
    assert (await env.db.users.get(USER)).is_banned
    replies = await env.send(USER, Btn.BUY)
    assert "مسدود" in method_text(replies[0])
    await env.click(ADMIN_ID, AUserCB(action="unban", user_id=USER))
    assert not (await env.db.users.get(USER)).is_banned


async def test_admin_adds_days_and_gifts_service(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env)
    await env.send(USER, "/start")
    await env.click(ADMIN_ID, AUserCB(action="gift_ok", user_id=USER, plan_id=plan_id))
    sub = (await env.db.subscriptions.list_for_user(USER))[0]
    assert sub.status == SubStatus.ACTIVE

    await env.click(ADMIN_ID, AUserCB(action="days", user_id=USER, sub_id=sub.id))
    await env.send(ADMIN_ID, "10")
    assert (await env.db.subscriptions.get(sub.id)).expires_at == sub.expires_at + 10 * 86400

    # جستجوی کاربر با فوروارد پیام
    await env.click(ADMIN_ID, AUserCB(action="search"))
    replies = await env.send(ADMIN_ID, "hello", forward_from=USER)
    assert str(USER) in method_text(replies[0])


async def test_payment_settings_validation(env: Env) -> None:
    await env.click(ADMIN_ID, ASettingCB(action="edit", key="card_number"))
    replies = await env.send(ADMIN_ID, "1234")
    assert "۱۶ رقم" in method_text(replies[0])
    await env.send(ADMIN_ID, "۶۰۳۷ ۹۹۷۵ ۱۲۳۴ ۵۶۷۸")
    assert await env.db.settings.get("card_number") == "6037-9975-1234-5678"

    await env.click(ADMIN_ID, ASettingCB(action="toggle", key="sales_enabled"))
    assert not await env.db.settings.get_bool("sales_enabled")
    replies = await env.send(USER, Btn.BUY)
    assert "غیرفعال" in method_text(replies[0])


async def test_broadcast_to_all_users(env: Env) -> None:
    for uid in (USER, OTHER, 2003):
        await env.send(uid, "/start")
    await env.click(ADMIN_ID, ABroadcastCB(action="target", target="all"))
    await env.send(ADMIN_ID, "📢 تخفیف ویژه!")
    await env.click(ADMIN_ID, ABroadcastCB(action="send"))
    from bot.handlers.admin.broadcast import _running

    await _running["task"]
    copied = {m.chat_id for m in env.session.of("CopyMessage")}
    assert {USER, OTHER, 2003} <= copied


async def test_backup_and_restore_through_bot(env: Env) -> None:
    _server_id, plan_id = await setup_manual_shop(env)
    await env.send(USER, "/start")

    replies = await env.send(ADMIN_ID, "/backup")
    documents = [m for m in replies if type(m).__name__ == "SendDocument"]
    assert documents and documents[0].chat_id == ADMIN_ID

    backup_path = await create_backup(env.db, env.config)
    # تغییر داده‌ها بعد از بکاپ
    await env.db.plans.update(plan_id, name="تغییر یافته")
    await env.send(2999, "/start")

    env.session.files["backup-file"] = backup_path.read_bytes()
    await env.send(ADMIN_ID, "/restore")
    replies = await env.send(ADMIN_ID, document=("backup-file", backup_path.name))
    assert "معتبر است" in method_text(env.session.of("EditMessageText", "SendMessage")[-1]), [method_text(r) for r in replies]
    await env.click(ADMIN_ID, ABackupCB(action="confirm"))

    assert (await env.db.plans.get(plan_id)).name == "یک ماهه"
    assert await env.db.users.get(2999) is None
    assert list(env.config.backup_dir.glob("pre_restore_*.zip"))

    # فایل نامعتبر رد می‌شود
    env.session.files["junk"] = b"not a backup at all"
    await env.send(ADMIN_ID, "/restore")
    await env.send(ADMIN_ID, document=("junk", "junk.zip"))
    assert "معتبر نیست" in method_text(env.session.of("EditMessageText")[-1])


async def test_menu_buttons_cancel_any_state(env: Env) -> None:
    await env.send(USER, "/start")
    await env.click(USER, TicketCB(action="new"))
    replies = await env.send(USER, Btn.ACCOUNT)
    assert "حساب کاربری" in method_text(replies[0])
    # حالت تیکت پاک شده؛ پیام بعدی تیکت نمی‌سازد
    await env.send(USER, "سلام")
    assert await env.db.tickets.list_for_user(USER) == []


async def test_unexpected_errors_are_handled_gracefully(env: Env, monkeypatch) -> None:
    async def broken(*_args, **_kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(env.db.settings, "get", broken)
    replies = await env.send(USER, "/start")
    assert "خطایی رخ داد" in method_text(replies[-1])
    replies = await env.click(USER, SubCB(action="renew", sub_id=1))
    # هندلر بدون خطا پاسخ داد (سرویس وجود ندارد) یا پیام خطا نمایش داده شد
    assert type(replies[0]).__name__ == "AnswerCallbackQuery"
