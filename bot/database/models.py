"""
مدل‌های داده (dataclass) متناظر با جداول دیتابیس

هر مدل با متد from_row از یک ردیف SQLite ساخته می‌شود تا در کد به جای
row["field"] از model.field استفاده شود (خواناتر و قابل تکمیل خودکار در IDE).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, fields
from typing import Any, TypeVar

T = TypeVar("T")


def now_ts() -> int:
    """زمان فعلی به صورت Unix timestamp (ثانیه)."""
    return int(time.time())


def _from_row(cls: type[T], row: Any) -> T:
    """ساخت dataclass از ردیف دیتابیس (ستون‌های اضافه نادیده گرفته می‌شوند)."""
    keys = set(row.keys())
    kwargs = {f.name: row[f.name] for f in fields(cls) if f.name in keys}  # type: ignore[arg-type]
    return cls(**kwargs)


# ----------------------------------------------------------------------
# ثابت‌ها
# ----------------------------------------------------------------------
class ServerKind:
    MANUAL = "manual"  # تحویل از انبار کانفیگ
    XUI = "xui"  # پنل 3x-ui (سنایی)
    MARZBAN = "marzban"  # پنل Marzban / PasarGuard

    ALL = (MANUAL, XUI, MARZBAN)
    LABELS = {
        MANUAL: "📝 دستی (انبار کانفیگ)",
        XUI: "🟦 پنل 3x-ui (سنایی)",
        MARZBAN: "🟪 پنل Marzban / PasarGuard",
    }


class OrderStatus:
    PENDING = "pending"  # سفارش ساخته شده، منتظر پرداخت/رسید
    WAITING = "waiting"  # رسید ارسال شده، منتظر تایید ادمین
    PAID = "paid"  # تایید شده ولی تحویل با خطا مواجه شده
    COMPLETED = "completed"  # سرویس تحویل داده شده
    REJECTED = "rejected"
    CANCELED = "canceled"

    # سفارش‌هایی که پول آن‌ها دریافت شده (برای آمار فروش)
    REVENUE = (PAID, COMPLETED)

    LABELS = {
        PENDING: "⏳ در انتظار پرداخت",
        WAITING: "🕓 در انتظار تایید",
        PAID: "💰 تایید شده (در حال تحویل)",
        COMPLETED: "✅ تکمیل شده",
        REJECTED: "❌ رد شده",
        CANCELED: "🚫 لغو شده",
    }


class OrderKind:
    NEW = "new"
    RENEW = "renew"
    GIFT = "gift"

    LABELS = {NEW: "🛒 خرید جدید", RENEW: "🔄 تمدید", GIFT: "🎁 هدیه ادمین"}


class SubStatus:
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"

    LABELS = {ACTIVE: "🟢 فعال", EXPIRED: "🔴 منقضی شده", DISABLED: "⚫️ غیرفعال"}


class TicketStatus:
    OPEN = "open"  # منتظر پاسخ پشتیبانی
    ANSWERED = "answered"  # پاسخ داده شده
    CLOSED = "closed"

    LABELS = {OPEN: "🟡 در انتظار پاسخ", ANSWERED: "🟢 پاسخ داده شده", CLOSED: "⚪️ بسته شده"}


# ----------------------------------------------------------------------
# مدل‌ها
# ----------------------------------------------------------------------
@dataclass
class User:
    id: int
    username: str | None
    full_name: str
    is_banned: int
    bot_blocked: int
    created_at: int
    last_seen_at: int

    @classmethod
    def from_row(cls, row: Any) -> User:
        return _from_row(cls, row)

    @property
    def display_username(self) -> str:
        return f"@{self.username}" if self.username else "—"


@dataclass
class Server:
    id: int
    name: str
    kind: str
    api_url: str
    api_user: str
    api_pass: str
    api_token: str
    inbound_ids: str
    sub_url: str
    address: str
    is_active: int
    is_deleted: int
    created_at: int

    @classmethod
    def from_row(cls, row: Any) -> Server:
        return _from_row(cls, row)

    @property
    def is_manual(self) -> bool:
        return self.kind == ServerKind.MANUAL

    @property
    def kind_label(self) -> str:
        return ServerKind.LABELS.get(self.kind, self.kind)

    def inbound_list(self) -> list[str]:
        """لیست آیدی/تگ اینباندها (جداشده با کاما)."""
        return [part.strip() for part in self.inbound_ids.split(",") if part.strip()]


@dataclass
class Plan:
    id: int
    server_id: int
    name: str
    days: int
    traffic_gb: float
    price: int
    description: str
    is_active: int
    is_deleted: int
    sort_order: int
    created_at: int

    @classmethod
    def from_row(cls, row: Any) -> Plan:
        return _from_row(cls, row)


@dataclass
class Subscription:
    id: int
    user_id: int
    plan_id: int | None
    server_id: int | None
    title: str
    config: str
    sub_link: str
    traffic_gb: float
    started_at: int
    expires_at: int
    status: str
    warned: int
    created_at: int
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> Subscription:
        obj = _from_row(cls, row)
        raw = row["meta"] if "meta" in row.keys() else "{}"  # noqa: SIM118 (sqlite3.Row)
        try:
            obj.meta = json.loads(raw or "{}")
        except (TypeError, ValueError):
            obj.meta = {}
        return obj

    @property
    def is_active(self) -> bool:
        return self.status == SubStatus.ACTIVE and self.expires_at > now_ts()

    def config_lines(self) -> list[str]:
        return [line.strip() for line in self.config.splitlines() if line.strip()]


@dataclass
class ConfigItem:
    id: int
    plan_id: int
    content: str
    subscription_id: int | None
    is_used: int
    created_at: int
    used_at: int | None

    @classmethod
    def from_row(cls, row: Any) -> ConfigItem:
        return _from_row(cls, row)


@dataclass
class Order:
    id: int
    user_id: int
    plan_id: int | None
    subscription_id: int | None
    kind: str
    amount: int
    plan_title: str
    method: str
    status: str
    receipt_kind: str | None
    receipt_file_id: str | None
    receipt_text: str | None
    note: str | None
    created_at: int
    updated_at: int
    paid_at: int | None

    @classmethod
    def from_row(cls, row: Any) -> Order:
        return _from_row(cls, row)

    @property
    def status_label(self) -> str:
        return OrderStatus.LABELS.get(self.status, self.status)

    @property
    def kind_label(self) -> str:
        return OrderKind.LABELS.get(self.kind, self.kind)


@dataclass
class Ticket:
    id: int
    user_id: int
    subject: str
    status: str
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, row: Any) -> Ticket:
        return _from_row(cls, row)

    @property
    def status_label(self) -> str:
        return TicketStatus.LABELS.get(self.status, self.status)


@dataclass
class TicketMessage:
    id: int
    ticket_id: int
    sender: str
    text: str
    file_id: str | None
    file_kind: str | None
    created_at: int

    @classmethod
    def from_row(cls, row: Any) -> TicketMessage:
        return _from_row(cls, row)
