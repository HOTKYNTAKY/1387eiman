"""
رابط مشترک پنل‌ها

هر نوع سرور (دستی، 3x-ui، Marzban) یک کلاس «پنل» دارد که عملیات زیر را
پیاده‌سازی می‌کند. بقیه برنامه فقط با همین رابط کار می‌کند و از جزئیات API هر
پنل بی‌خبر است؛ بنابراین افزودن پنل جدید فقط نیاز به یک کلاس جدید دارد.
"""

from __future__ import annotations

import secrets
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from bot.database.models import Plan, Server, Subscription

GB = 1024**3


class PanelError(Exception):
    """خطای ارتباط با پنل یا انجام عملیات روی آن (پیام آن برای ادمین نمایش داده می‌شود)."""


@dataclass
class ClientResult:
    """نتیجه ساخت/تمدید کاربر روی پنل."""

    links: list[str]  # کانفیگ‌ها (vless://, vmess://, ...)
    sub_link: str = ""  # لینک ساب‌اسکریپشن
    meta: dict[str, Any] = field(default_factory=dict)  # شناسه‌های فنی برای عملیات بعدی


@dataclass
class ClientUsage:
    """وضعیت مصرف کاربر روی پنل."""

    used_bytes: int
    total_bytes: int  # صفر = نامحدود
    expires_at: int | None  # timestamp ثانیه؛ None = نامحدود
    enabled: bool


def gb_to_bytes(gb: float) -> int:
    return round((gb or 0) * GB)


def random_string(length: int = 16, alphabet: str = string.ascii_lowercase + string.digits) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))


class BasePanel(ABC):
    """کلاس پایه همه پنل‌ها."""

    def __init__(self, server: Server, *, verify_ssl: bool = False, timeout: float = 20.0) -> None:
        self.server = server
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    @abstractmethod
    async def test(self) -> str:
        """تست اتصال؛ متن گزارش برای ادمین برمی‌گرداند یا PanelError می‌دهد."""

    @abstractmethod
    async def create_client(
        self, *, remark: str, expires_at: int, traffic_gb: float, plan: Plan, user_id: int
    ) -> ClientResult:
        """ساخت کاربر/کانفیگ جدید."""

    @abstractmethod
    async def renew_client(
        self, sub: Subscription, *, expires_at: int, traffic_gb: float, plan: Plan
    ) -> ClientResult | None:
        """
        تمدید کاربر: تنظیم تاریخ انقضای جدید، حجم جدید و صفر کردن مصرف.
        اگر لینک‌ها تغییر کنند ClientResult جدید برمی‌گرداند، وگرنه None.
        """

    async def set_expiry(self, sub: Subscription, expires_at: int) -> None:
        """تغییر تاریخ انقضا (برای افزایش/کاهش روز توسط ادمین)."""
        return None

    async def get_usage(self, sub: Subscription) -> ClientUsage | None:
        """دریافت میزان مصرف؛ اگر پنل پشتیبانی نکند None."""
        return None

    async def delete_client(self, sub: Subscription) -> None:
        """حذف کاربر از پنل (هنگام لغو سرویس توسط ادمین)."""
        return None
