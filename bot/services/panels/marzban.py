"""
اتصال به پنل Marzban و فورک آن PasarGuard

هر دو پنل API مشابهی دارند:
    POST /api/admin/token            ← دریافت توکن با نام کاربری/رمز ادمین
    POST /api/user                   ← ساخت کاربر
    GET/PUT/DELETE /api/user/{name}  ← مشاهده/ویرایش/حذف
    POST /api/user/{name}/reset      ← صفر کردن مصرف

تفاوت اصلی در ساخت کاربر است:
    - Marzban   : فیلدهای proxies و inbounds (براساس پروتکل و تگ اینباند)
    - PasarGuard: فیلد group_ids (کاربر عضو گروه‌ها می‌شود)
نوع پنل با وجود مسیر GET /api/groups به صورت خودکار تشخیص داده می‌شود.

فیلد «اینباندها» در تنظیمات سرور:
    - Marzban   : تگ اینباندها با کاما (خالی = همه اینباندها)
    - PasarGuard: آیدی گروه‌ها با کاما (خالی = همه گروه‌های فعال)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

from bot.database.models import Plan, Server, Subscription
from bot.services.panels.base import (
    BasePanel,
    ClientResult,
    ClientUsage,
    PanelError,
    gb_to_bytes,
    random_string,
)
from bot.services.panels.http import HttpClient, fetch_subscription_links, normalize_base_url

log = logging.getLogger(__name__)

_URL_SUFFIXES = ("/dashboard", "/docs", "/api")

MARZBAN = "marzban"
PASARGUARD = "pasarguard"


def _parse_expire(value: Any) -> int | None:
    """expire در Marzban عدد (ثانیه) و در PasarGuard رشته تاریخ ISO است."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def _error_detail(data: Any) -> str:
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, list):  # خطاهای اعتبارسنجی FastAPI
            return "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
        if detail:
            return str(detail)
    return ""


class _MarzbanSession:
    def __init__(self, http: HttpClient, server: Server) -> None:
        self.http = http
        self.server = server
        self.flavor = MARZBAN

    async def login(self) -> None:
        if not self.server.api_user:
            raise PanelError("نام کاربری ادمین پنل تنظیم نشده است.")
        status, data = await self.http.request(
            "POST",
            "/api/admin/token",
            data={"username": self.server.api_user, "password": self.server.api_pass, "grant_type": "password"},
        )
        if status == 404:
            raise PanelError("مسیر API پنل پیدا نشد. آدرس را به شکل https://domain.com:8000 وارد کنید.")
        if status in (401, 403) or not isinstance(data, dict) or not data.get("access_token"):
            detail = _error_detail(data)
            raise PanelError("ورود به پنل ناموفق بود؛ نام کاربری/رمز ادمین را بررسی کنید." + (f"\n{detail}" if detail else ""))
        self.http.headers["Authorization"] = f"Bearer {data['access_token']}"

        # تشخیص PasarGuard
        status, data = await self.http.request("GET", "/api/groups")
        if status == 200 and isinstance(data, dict) and "groups" in data:
            self.flavor = PASARGUARD

    async def call(self, method: str, path: str, *, json_body: Any = None, ok: tuple[int, ...] = (200,)) -> Any:
        status, data = await self.http.request(method, path, json_body=json_body)
        if status in ok:
            return data
        if status == 404:
            raise PanelError(f"یافت نشد (404): {_error_detail(data) or path}")
        if status in (401, 403):
            raise PanelError("دسترسی رد شد؛ اطلاعات ادمین پنل را بررسی کنید.")
        if status == 409:
            raise PanelError("کاربری با این نام از قبل در پنل وجود دارد.")
        raise PanelError(f"خطای پنل (HTTP {status}): {_error_detail(data) or 'unknown'}")


class MarzbanPanel(BasePanel):
    """پیاده‌سازی رابط پنل برای Marzban / PasarGuard."""

    def __init__(self, server: Server, *, verify_ssl: bool = False, timeout: float = 20.0) -> None:
        super().__init__(server, verify_ssl=verify_ssl, timeout=timeout)
        self.base_url = normalize_base_url(server.api_url, _URL_SUFFIXES)

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[_MarzbanSession]:
        if not self.base_url:
            raise PanelError("آدرس پنل تنظیم نشده است.")
        async with HttpClient(self.base_url, verify_ssl=self.verify_ssl, timeout=self.timeout) as http:
            session = _MarzbanSession(http, self.server)
            await session.login()
            yield session

    def _absolute(self, url: str | None) -> str:
        """subscription_url ممکن است نسبی باشد (مثلاً /sub/xxxx)."""
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return urljoin(self.base_url + "/", url.lstrip("/"))

    async def _groups(self, session: _MarzbanSession) -> list[dict[str, Any]]:
        data = await session.call("GET", "/api/groups")
        groups = data.get("groups") if isinstance(data, dict) else None
        return [g for g in groups or [] if isinstance(g, dict)]

    # ------------------------------------------------------------------
    async def test(self) -> str:
        async with self._session() as session:
            if session.flavor == PASARGUARD:
                groups = await self._groups(session)
                lines = ["✅ اتصال به پنل PasarGuard موفق بود", "\nگروه‌ها (آیدی را در فیلد اینباندها وارد کنید):"]
                for group in groups:
                    state = "🔴" if group.get("is_disabled") else "🟢"
                    lines.append(f"{state} #{group.get('id')} | {group.get('name')} | کاربران: {group.get('total_users', 0)}")
                return "\n".join(lines)
            inbounds = await session.call("GET", "/api/inbounds") or {}
        lines = ["✅ اتصال به پنل Marzban موفق بود", "\nاینباندها (تگ را در فیلد اینباندها وارد کنید؛ خالی = همه):"]
        for protocol, items in (inbounds or {}).items():
            for item in items or []:
                lines.append(f"▫️ {protocol} | {item.get('tag')}")
        return "\n".join(lines)

    async def create_client(
        self, *, remark: str, expires_at: int, traffic_gb: float, plan: Plan, user_id: int
    ) -> ClientResult:
        body: dict[str, Any] = {
            "username": remark,
            "expire": int(expires_at),
            "data_limit": gb_to_bytes(traffic_gb),
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
            "note": f"Telegram: {user_id}",
        }
        selected = self.server.inbound_list()
        async with self._session() as session:
            if session.flavor == PASARGUARD:
                if selected:
                    try:
                        group_ids = [int(x) for x in selected]
                    except ValueError as exc:
                        raise PanelError("در PasarGuard فیلد اینباندها باید آیدی عددی گروه‌ها باشد.") from exc
                else:
                    group_ids = [int(g["id"]) for g in await self._groups(session) if not g.get("is_disabled")]
                if not group_ids:
                    raise PanelError("هیچ گروه فعالی در پنل PasarGuard پیدا نشد.")
                body["group_ids"] = group_ids
            else:
                inbounds = await session.call("GET", "/api/inbounds") or {}
                proxies: dict[str, dict[str, Any]] = {}
                inbound_map: dict[str, list[str]] = {}
                for protocol, items in inbounds.items():
                    tags = [str(i.get("tag")) for i in items or [] if isinstance(i, dict)]
                    if selected:
                        tags = [t for t in tags if t in selected]
                    if tags:
                        proxies[protocol] = {}
                        inbound_map[protocol] = tags
                if not proxies:
                    raise PanelError("هیچ اینباند معتبری در پنل Marzban پیدا نشد (تگ‌ها را بررسی کنید).")
                body["proxies"] = proxies
                body["inbounds"] = inbound_map

            user = await session.call("POST", "/api/user", json_body=body)
            flavor = session.flavor

        if not isinstance(user, dict):
            raise PanelError("پاسخ نامعتبر از پنل هنگام ساخت کاربر.")
        sub_link = self._absolute(user.get("subscription_url"))
        links = [str(x) for x in user.get("links") or [] if x]
        if not links and sub_link:
            links = await fetch_subscription_links(sub_link, verify_ssl=self.verify_ssl)
        return ClientResult(links=links, sub_link=sub_link, meta={"username": remark, "flavor": flavor})

    async def renew_client(
        self, sub: Subscription, *, expires_at: int, traffic_gb: float, plan: Plan
    ) -> ClientResult | None:
        username = quote(str(sub.meta.get("username")), safe="")
        async with self._session() as session:
            status, _ = await session.http.request("GET", f"/api/user/{username}")
            if status == 404:
                missing = True
            else:
                missing = False
                await session.call(
                    "PUT",
                    f"/api/user/{username}",
                    json_body={"expire": int(expires_at), "data_limit": gb_to_bytes(traffic_gb), "status": "active"},
                )
                await session.call("POST", f"/api/user/{username}/reset")
        if missing:
            # کاربر از پنل حذف شده → ساخت کاربر جدید
            log.warning("User of subscription #%s not found on panel, recreating", sub.id)
            return await self.create_client(
                remark=f"u{sub.user_id}_{random_string(5)}",
                expires_at=expires_at,
                traffic_gb=traffic_gb,
                plan=plan,
                user_id=sub.user_id,
            )
        return None

    async def set_expiry(self, sub: Subscription, expires_at: int) -> None:
        username = quote(str(sub.meta.get("username")), safe="")
        async with self._session() as session:
            await session.call("PUT", f"/api/user/{username}", json_body={"expire": int(expires_at)})

    async def get_usage(self, sub: Subscription) -> ClientUsage | None:
        username = quote(str(sub.meta.get("username")), safe="")
        async with self._session() as session:
            user = await session.call("GET", f"/api/user/{username}")
        if not isinstance(user, dict):
            return None
        return ClientUsage(
            used_bytes=int(user.get("used_traffic") or 0),
            total_bytes=int(user.get("data_limit") or 0),
            expires_at=_parse_expire(user.get("expire")),
            enabled=str(user.get("status")) in ("active", "on_hold"),
        )

    async def delete_client(self, sub: Subscription) -> None:
        username = quote(str(sub.meta.get("username")), safe="")
        async with self._session() as session:
            await session.call("DELETE", f"/api/user/{username}", ok=(200, 204, 404))
