"""
حالت‌های FSM (ماشین حالت) برای گفتگوهای چندمرحله‌ای

مثلاً وقتی ربات منتظر ارسال رسید پرداخت یا نام پلن جدید است، کاربر در یکی از
این حالت‌ها قرار می‌گیرد. با زدن هر دکمه منوی اصلی یا /cancel حالت پاک می‌شود.
"""

from aiogram.fsm.state import State, StatesGroup


# ----------------------------- کاربر -----------------------------
class BuyStates(StatesGroup):
    receipt = State()  # منتظر تصویر رسید / کد پیگیری


class TicketStates(StatesGroup):
    new = State()  # متن تیکت جدید
    reply = State()  # پاسخ کاربر به تیکت


# ----------------------------- ادمین -----------------------------
class PlanForm(StatesGroup):
    name = State()
    days = State()
    traffic = State()
    price = State()
    description = State()
    confirm = State()


class PlanEdit(StatesGroup):
    value = State()


class ServerForm(StatesGroup):
    name = State()
    url = State()
    username = State()
    password = State()
    inbounds = State()
    sub_url = State()


class ServerEdit(StatesGroup):
    value = State()


class ConfigAdd(StatesGroup):
    content = State()


class UserAdmin(StatesGroup):
    search = State()
    add_days = State()
    message = State()


class OrderAdmin(StatesGroup):
    reject_reason = State()
    manual_config = State()


class AdminTicket(StatesGroup):
    reply = State()


class BroadcastStates(StatesGroup):
    message = State()
    confirm = State()


class SettingEdit(StatesGroup):
    value = State()


class RestoreStates(StatesGroup):
    file = State()
    confirm = State()
