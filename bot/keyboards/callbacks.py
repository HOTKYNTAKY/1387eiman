"""
تعریف ساختار داده دکمه‌های شیشه‌ای (CallbackData)

هر کلاس یک پیشوند یکتا دارد و aiogram داده را به شکل «پیشوند:فیلد۱:فیلد۲» در
دکمه ذخیره می‌کند (حداکثر ۶۴ بایت). در هندلرها با Class.filter() فیلتر می‌شوند.

نکته امنیتی: داده دکمه‌ها قابل دستکاری توسط کاربر است؛ بنابراین هندلرهای کاربر
همیشه مالکیت سرویس/سفارش/تیکت را بررسی می‌کنند.
"""

from aiogram.filters.callback_data import CallbackData


# ======================================================================
# عمومی
# ======================================================================
class CancelCB(CallbackData, prefix="x"):
    """دکمه انصراف از هر فرم در حال پر شدن."""

    to: str = ""  # مقصد پس از لغو (مثلاً admin برای بازگشت به پنل مدیریت)


# ======================================================================
# کاربر
# ======================================================================
class BuyCB(CallbackData, prefix="b"):
    """
    مراحل خرید/تمدید:
      servers → server (لیست پلن‌ها) → plan (پیش‌فاکتور) → pay (ساخت سفارش)
    sub_id > 0 یعنی تمدید آن سرویس.
    """

    action: str
    server_id: int = 0
    plan_id: int = 0
    sub_id: int = 0
    method: str = ""


class OrderCB(CallbackData, prefix="o"):
    action: str  # list | receipt | cancel
    order_id: int = 0


class SubCB(CallbackData, prefix="s"):
    action: str  # list | view | config | renew
    sub_id: int = 0


class TicketCB(CallbackData, prefix="t"):
    action: str  # menu | new | list | view | reply | close
    ticket_id: int = 0


class AccountCB(CallbackData, prefix="a"):
    action: str  # home | orders


# ======================================================================
# ادمین
# ======================================================================
class AdminCB(CallbackData, prefix="ad"):
    """منوی اصلی پنل مدیریت و بخش‌های آن."""

    section: str


class APlanCB(CallbackData, prefix="ap"):
    action: str  # list | view | new | new_server | save | edit | toggle | del | del_ok
    plan_id: int = 0
    server_id: int = 0
    field: str = ""


class AServerCB(CallbackData, prefix="as"):
    action: str  # list | view | new | kind | test | toggle | edit | field | del | del_ok | inbounds
    server_id: int = 0
    kind: str = ""
    field: str = ""


class AConfigCB(CallbackData, prefix="ac"):
    """انبار کانفیگ پلن‌های سرورهای دستی."""

    action: str  # view | add | export | clear | clear_ok
    plan_id: int = 0


class AUserCB(CallbackData, prefix="au"):
    action: str  # menu | search | list | banned | view | ban | unban | subs | sub | days | cancel_sub
    #              cancel_ok | gift | gift_plan | gift_ok | msg | orders
    user_id: int = 0
    sub_id: int = 0
    plan_id: int = 0
    page: int = 0


class AOrderCB(CallbackData, prefix="ao"):
    action: str  # list | view | approve | reject | reject_now | retry | manual | dateonly
    order_id: int = 0


class ATicketCB(CallbackData, prefix="at"):
    action: str  # list | view | reply | close
    ticket_id: int = 0


class ABroadcastCB(CallbackData, prefix="ab"):
    action: str  # target | send
    target: str = ""  # all | active


class ASettingCB(CallbackData, prefix="st"):
    action: str  # edit | toggle
    key: str = ""


class ABackupCB(CallbackData, prefix="bk"):
    action: str  # now | restore | confirm
