"""
اتصال به پنل 3x-ui (MHSanaei/3x-ui)

سه نسل API پشتیبانی و به صورت خودکار تشخیص داده می‌شود:
    - نسخه ۲.x           : API قدیمی (/panel/api/inbounds/addClient و ...)
    - نسخه ۳.۰.x          : همان API قدیمی + محافظت CSRF در صفحه ورود
    - نسخه ۳.۱ به بعد     : API جدید کلاینت‌ها (/panel/api/clients/*)

روش ورود:
    - اگر «توکن API» تنظیم شده باشد (Settings → Security → API Token در نسخه ۳)
      از هدر Authorization: Bearer استفاده می‌شود (مناسب وقتی ورود دومرحله‌ای فعال است).
    - در غیر این صورت با نام کاربری/رمز عبور لاگین می‌شود؛ ابتدا توکن CSRF از
      /csrf-token گرفته می‌شود (در نسخه ۲ این مسیر وجود ندارد و نادیده گرفته می‌شود).

آدرس پنل باید همراه با مسیر مخفی (web base path) وارد شود، مثلاً:
    https://panel.example.com:2053/AbCdEf12
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote, urlsplit

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
from bot.services.panels.xui_links import as_dict, build_links, replace_link_host

log = logging.getLogger(__name__)

# مسیرهای صفحات پنل که اگر ادمین آدرس را از مرورگر کپی کند، حذف می‌شوند
_URL_SUFFIXES = ("/login", "/inbounds", "/settings", "/xray", "/clients", "/panel")

VISION_FLOW = "xtls-rprx-vision"
SUPPORTED_PROTOCOLS = ("vless", "vmess", "trojan")


class _NotFound(PanelError):
    """مسیر API روی پنل وجود ندارد (HTTP 404)."""


class _ApiFailure(PanelError):
    """پنل پاسخ داد ولی عملیات را انجام نداد (success=false)."""


class ClientNotFound(PanelError):
    """کاربر موردنظر روی پنل وجود ندارد (مثلاً دستی حذف شده است)."""


class _XUISession:
    """یک نشست لاگین‌شده روی پنل 3x-ui."""

    def __init__(self, http: HttpClient, server: Server) -> None:
        self.http = http
        self.server = server

    async def login(self) -> None:
        token = self.server.api_token.strip()
        if token:
            self.http.headers["Authorization"] = f"Bearer {token}"
            return
        if not self.server.api_user:
            raise PanelError("نام کاربری پنل تنظیم نشده است.")

        # نسخه ۳: ورود نیازمند توکن CSRF است (نسخه ۲ این مسیر را ندارد)
        csrf: str | None = None
        status, data = await self.http.request("GET", "/csrf-token")
        if status == 200 and isinstance(data, dict) and data.get("success") and data.get("obj"):
            csrf = str(data["obj"])
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        status, data = await self.http.request(
            "POST",
            "/login",
            data={"username": self.server.api_user, "password": self.server.api_pass},
            headers=headers,
        )
        if status == 404 or not isinstance(data, dict):
            raise PanelError(
                f"صفحه ورود پنل پیدا نشد (HTTP {status}). آدرس پنل را همراه با مسیر مخفی "
                "(web base path) وارد کنید؛ مثال: https://domain.com:2053/AbCd12"
            )
        if not data.get("success"):
            message = str(data.get("msg") or "").strip()
            raise PanelError(
                "ورود به پنل ناموفق بود؛ نام کاربری و رمز عبور را بررسی کنید. "
                "اگر ورود دومرحله‌ای فعال است از «توکن API» استفاده کنید."
                + (f"\nپیام پنل: {message}" if message else "")
            )
        if csrf:
            # درخواست‌های بعدی (POST) هم باید همین توکن را داشته باشند
            self.http.headers["X-CSRF-Token"] = csrf

    async def api(self, method: str, path: str, *, json_body: Any = None, allow_empty: bool = False) -> Any:
        """فراخوانی API پنل و برگرداندن فیلد obj پاسخ."""
        status, data = await self.http.request(method, path, json_body=json_body)
        if status == 404:
            raise _NotFound(f"مسیر API در پنل پیدا نشد: {path}")
        if status in (401, 403):
            raise PanelError("پنل درخواست را رد کرد (دسترسی غیرمجاز). اطلاعات ورود یا توکن API را بررسی کنید.")
        if status >= 500:
            raise PanelError(f"خطای داخلی پنل (HTTP {status}).")
        if data is None:
            # برخی نسخه‌ها (مثل 2.6.0) پس از افزودن کلاینت پاسخ خالی برمی‌گردانند
            if allow_empty and status == 200:
                return None
            raise PanelError(f"پاسخ نامعتبر از پنل (HTTP {status}).")
        if not isinstance(data, dict) or not data.get("success"):
            message = data.get("msg") if isinstance(data, dict) else ""
            raise _ApiFailure(f"پنل خطا برگرداند: {message or 'unknown error'}")
        return data.get("obj")

    async def has_clients_api(self) -> bool:
        """تشخیص API جدید کلاینت‌ها (نسخه ۳.۱ به بعد)."""
        status, data = await self.http.request("GET", "/panel/api/clients/list/paged?page=1&pageSize=1")
        return status != 404 and isinstance(data, dict)

    async def inbound(self, inbound_id: int) -> dict[str, Any]:
        obj = await self.api("GET", f"/panel/api/inbounds/get/{inbound_id}")
        if not isinstance(obj, dict):
            raise PanelError(f"اینباند #{inbound_id} در پنل پیدا نشد.")
        return obj


def _client_flow(inbounds: list[dict[str, Any]]) -> str:
    """
    تعیین flow برای کلاینت جدید:
      - فقط اگر همه اینباندها VLESS روی TCP با امنیت TLS/Reality باشند
      - اگر کلاینت‌های موجود flow خاصی دارند همان تکرار می‌شود (تنظیم ادمین حفظ شود)
      - اگر اینباند هنوز کلاینتی ندارد، xtls-rprx-vision (پیشنهاد رسمی Xray)
    """
    has_clients = False
    for inbound in inbounds:
        stream = as_dict(inbound.get("streamSettings"))
        if (
            inbound.get("protocol") != "vless"
            or (stream.get("network") or "tcp") != "tcp"
            or stream.get("security") not in ("tls", "reality")
        ):
            return ""
        for client in as_dict(inbound.get("settings")).get("clients") or []:
            has_clients = True
            if isinstance(client, dict) and client.get("flow"):
                return str(client["flow"])
    return "" if has_clients else VISION_FLOW


class XUIPanel(BasePanel):
    """پیاده‌سازی رابط پنل برای 3x-ui."""

    def __init__(self, server: Server, *, verify_ssl: bool = False, timeout: float = 20.0) -> None:
        super().__init__(server, verify_ssl=verify_ssl, timeout=timeout)
        self.base_url = normalize_base_url(server.api_url, _URL_SUFFIXES)

    # ------------------------------------------------------------------
    # ابزارهای داخلی
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def _session(self) -> AsyncIterator[_XUISession]:
        if not self.base_url:
            raise PanelError("آدرس پنل تنظیم نشده است.")
        async with HttpClient(self.base_url, verify_ssl=self.verify_ssl, timeout=self.timeout) as http:
            session = _XUISession(http, self.server)
            await session.login()
            yield session

    def _inbound_ids(self) -> list[int]:
        ids: list[int] = []
        for part in self.server.inbound_list():
            if not part.isdigit():
                raise PanelError(f"آیدی اینباند نامعتبر است: {part}")
            ids.append(int(part))
        if not ids:
            raise PanelError("هیچ اینباندی برای این سرور انتخاب نشده است.")
        return ids

    def _public_host(self) -> str:
        """آدرسی که در لینک‌ها قرار می‌گیرد."""
        return self.server.address.strip() or (urlsplit(self.base_url).hostname or "")

    def _sub_link(self, sub_id: str) -> str:
        base = self.server.sub_url.strip()
        if not base or not sub_id:
            return ""
        if "{sub_id}" in base:
            return base.replace("{sub_id}", sub_id)
        return f"{base.rstrip('/')}/{sub_id}"

    async def _v3_links(self, session: _XUISession, email: str) -> list[str]:
        """لینک‌ها را مستقیماً از پنل (نسخه ۳) می‌گیرد."""
        try:
            obj = await session.api("GET", f"/panel/api/clients/links/{quote(email, safe='')}")
        except PanelError as exc:
            log.warning("Cannot fetch client links from panel: %s", exc)
            return []
        links = [str(x).strip() for x in obj or [] if str(x).strip()] if isinstance(obj, list) else []
        if self.server.address.strip():
            links = [replace_link_host(link, self.server.address.strip()) for link in links]
        return links

    # ------------------------------------------------------------------
    # رابط عمومی
    # ------------------------------------------------------------------
    async def list_inbounds(self) -> list[dict[str, Any]]:
        """لیست اینباندهای پنل (برای انتخاب توسط ادمین)."""
        async with self._session() as session:
            obj = await session.api("GET", "/panel/api/inbounds/list")
        return [i for i in obj or [] if isinstance(i, dict)]

    async def test(self) -> str:
        async with self._session() as session:
            v3 = await session.has_clients_api()
            inbounds = await session.api("GET", "/panel/api/inbounds/list") or []
        lines = [f"✅ اتصال به پنل 3x-ui موفق بود ({'API جدید نسخه ۳' if v3 else 'API نسخه ۲'})"]
        configured = set(self.server.inbound_list())
        found: set[str] = set()
        lines.append("\nاینباندهای پنل:")
        for inbound in inbounds:
            inbound_id = str(inbound.get("id"))
            mark = "☑️" if inbound_id in configured else "▫️"
            if inbound_id in configured:
                found.add(inbound_id)
            lines.append(
                f"{mark} #{inbound_id} | {inbound.get('remark') or '-'} | "
                f"{inbound.get('protocol')} | پورت {inbound.get('port')}"
            )
        missing = configured - found
        if missing:
            lines.append(f"\n⚠️ این اینباندها در پنل پیدا نشدند: {', '.join(sorted(missing))}")
        return "\n".join(lines)

    async def create_client(
        self, *, remark: str, expires_at: int, traffic_gb: float, plan: Plan, user_id: int
    ) -> ClientResult:
        inbound_ids = self._inbound_ids()
        sub_id = random_string(16)
        total = gb_to_bytes(traffic_gb)
        expiry_ms = int(expires_at) * 1000
        comment = f"tg:{user_id}"

        async with self._session() as session:
            inbounds = [await session.inbound(i) for i in inbound_ids]
            for inbound in inbounds:
                if inbound.get("protocol") not in SUPPORTED_PROTOCOLS:
                    raise PanelError(
                        f"پروتکل اینباند #{inbound.get('id')} ({inbound.get('protocol')}) پشتیبانی نمی‌شود. "
                        "پروتکل‌های قابل استفاده: VLESS، VMess، Trojan"
                    )
            if await session.has_clients_api():
                # ---------------- نسخه ۳.۱+ ----------------
                client_uuid = str(uuid.uuid4())
                client = {
                    "id": client_uuid,
                    "email": remark,
                    "subId": sub_id,
                    # در نسخه ۳ یک کلاینت مشترک برای همه اینباندهاست
                    "flow": _client_flow(inbounds),
                    "totalGB": total,
                    "expiryTime": expiry_ms,
                    "limitIp": 0,
                    "enable": True,
                    "comment": comment,
                }
                await session.api(
                    "POST", "/panel/api/clients/add", json_body={"client": client, "inboundIds": inbound_ids}
                )
                meta: dict[str, Any] = {"api": "v3", "email": remark, "sub_id": sub_id, "inbound_ids": inbound_ids}
                links = await self._v3_links(session, remark)
                if not links:
                    # پنل لینکی برنگرداند؛ ساخت لینک از روی تنظیمات اینباند
                    links = await self._v3_build_links(session, remark, inbounds)
            else:
                # ---------------- نسخه ۲.x / ۳.۰ ----------------
                clients_meta: list[dict[str, Any]] = []
                links = []
                meta = {"api": "v2", "email": remark, "sub_id": sub_id, "clients": clients_meta}
                for inbound in inbounds:
                    inbound_id = int(inbound["id"])
                    email = remark if len(inbounds) == 1 else f"{remark}-{inbound_id}"
                    # در نسخه ۲ هر اینباند کلاینت جداگانه دارد؛ flow برای هر اینباند جدا تعیین می‌شود
                    client = self._legacy_client(
                        str(inbound["protocol"]), email, sub_id, total, expiry_ms, _client_flow([inbound]), comment
                    )
                    try:
                        await session.api(
                            "POST",
                            "/panel/api/inbounds/addClient",
                            json_body={"id": inbound_id, "settings": json.dumps({"clients": [client]})},
                            allow_empty=True,
                        )
                    except PanelError:
                        # کلاینت‌های ساخته‌شده روی اینباندهای قبلی حذف شوند (جلوگیری از کاربر یتیم)
                        await self._cleanup(session, meta)
                        raise
                    clients_meta.append(
                        {
                            "inbound_id": inbound_id,
                            "email": email,
                            "protocol": inbound["protocol"],
                            "key": client.get("id") or client.get("password"),
                        }
                    )
                    link_remark = f"{self.server.name}-{email}"
                    links.extend(build_links(inbound, client, self._public_host(), link_remark))

        sub_link = self._sub_link(sub_id)
        if sub_link and meta["api"] == "v2":
            # اگر ساب‌اسکریپشن تنظیم شده، لینک‌های دقیق را از خود پنل بگیر
            panel_links = await fetch_subscription_links(sub_link, verify_ssl=self.verify_ssl)
            if panel_links:
                links = panel_links
        if not links and not sub_link:
            async with self._session() as session:
                await self._cleanup(session, meta)
            raise PanelError("ساخت لینک کانفیگ ممکن نبود. «آدرس ساب» را در تنظیمات سرور وارد کنید و دوباره تلاش کنید.")
        return ClientResult(links=links, sub_link=sub_link, meta=meta)

    async def _v3_build_links(self, session: _XUISession, email: str, inbounds: list[dict[str, Any]]) -> list[str]:
        """ساخت لینک با اطلاعات کلاینت (uuid/password تولیدشده توسط پنل) — روش جایگزین در نسخه ۳."""
        try:
            obj = await session.api("GET", f"/panel/api/clients/get/{quote(email, safe='')}")
        except PanelError:
            return []
        record = obj.get("client") if isinstance(obj, dict) else None
        if not isinstance(record, dict):
            return []
        client = {
            "id": record.get("uuid") or "",
            "password": record.get("password") or "",
            "flow": record.get("flow") or "",
            "security": record.get("security") or "auto",
        }
        links: list[str] = []
        for inbound in inbounds:
            links.extend(build_links(inbound, client, self._public_host(), f"{self.server.name}-{email}"))
        return links

    async def _cleanup(self, session: _XUISession, meta: dict[str, Any]) -> None:
        """حذف بهترین‌تلاش کلاینت ساخته‌شده وقتی ادامه عملیات ناموفق است."""
        try:
            if meta.get("api") == "v3":
                await session.api("POST", f"/panel/api/clients/del/{quote(str(meta['email']), safe='')}")
            for item in meta.get("clients") or []:
                await session.api(
                    "POST",
                    f"/panel/api/inbounds/{int(item['inbound_id'])}/delClient/{quote(str(item['key']), safe='')}",
                    allow_empty=True,
                )
        except PanelError as exc:
            log.warning("Cleanup of half-created client failed: %s", exc)

    @staticmethod
    def _legacy_client(
        protocol: str, email: str, sub_id: str, total: int, expiry_ms: int, flow: str, comment: str
    ) -> dict[str, Any]:
        client: dict[str, Any] = {
            "email": email,
            "limitIp": 0,
            "totalGB": total,
            "expiryTime": expiry_ms,
            "enable": True,
            "subId": sub_id,
            "comment": comment,
            "reset": 0,
        }
        if protocol == "vless":
            client.update({"id": str(uuid.uuid4()), "flow": flow})
        elif protocol == "vmess":
            client.update({"id": str(uuid.uuid4()), "security": "auto"})
        elif protocol == "trojan":
            client["password"] = random_string(16)
        return client

    # ------------------------------------------------------------------
    # به‌روزرسانی کلاینت (تمدید / تغییر تاریخ)
    # ------------------------------------------------------------------
    async def _update(
        self, sub: Subscription, *, expiry_ms: int, total: int | None, reset_traffic: bool
    ) -> None:
        meta = sub.meta
        async with self._session() as session:
            if meta.get("api") == "v3":
                email = str(meta["email"])
                quoted = quote(email, safe="")
                try:
                    obj = await session.api("GET", f"/panel/api/clients/get/{quoted}")
                except _ApiFailure as exc:
                    raise ClientNotFound(f"کاربر {email} در پنل پیدا نشد.") from exc
                record = obj.get("client") if isinstance(obj, dict) else None
                if not isinstance(record, dict):
                    raise ClientNotFound(f"کاربر {email} در پنل پیدا نشد.")
                body = {
                    # در رکورد دیتابیس پنل، uuid جدا از id (شماره ردیف) است
                    "id": record.get("uuid") or "",
                    "email": email,
                    "subId": record.get("subId") or meta.get("sub_id") or "",
                    "password": record.get("password") or "",
                    "auth": record.get("auth") or "",
                    "flow": record.get("flow") or "",
                    "security": record.get("security") or "",
                    "limitIp": int(record.get("limitIp") or 0),
                    "limitHwid": int(record.get("limitHwid") or 0),
                    "totalGB": int(record.get("totalGB") or 0) if total is None else total,
                    "expiryTime": expiry_ms,
                    "enable": True,
                    "tgId": int(record.get("tgId") or 0),
                    "comment": record.get("comment") or "",
                    "group": record.get("group") or "",
                    "reset": int(record.get("reset") or 0),
                }
                await session.api("POST", f"/panel/api/clients/update/{quoted}", json_body=body)
                if reset_traffic:
                    await session.api("POST", f"/panel/api/clients/resetTraffic/{quoted}")
                return

            for item in meta.get("clients") or []:
                inbound_id = int(item["inbound_id"])
                email = str(item["email"])
                inbound = await session.inbound(inbound_id)
                clients = as_dict(inbound.get("settings")).get("clients") or []
                client = next((c for c in clients if isinstance(c, dict) and c.get("email") == email), None)
                if client is None:
                    raise ClientNotFound(f"کاربر {email} در اینباند #{inbound_id} پیدا نشد.")
                client["expiryTime"] = expiry_ms
                client["enable"] = True
                if total is not None:
                    client["totalGB"] = total
                key = client.get("password") if inbound.get("protocol") == "trojan" else client.get("id")
                if not key:
                    raise PanelError("شناسه کاربر در پنل پیدا نشد.")
                await session.api(
                    "POST",
                    f"/panel/api/inbounds/updateClient/{quote(str(key), safe='')}",
                    json_body={"id": inbound_id, "settings": json.dumps({"clients": [client]})},
                    allow_empty=True,
                )
                if reset_traffic:
                    await session.api(
                        "POST",
                        f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{quote(email, safe='')}",
                        allow_empty=True,
                    )

    async def renew_client(
        self, sub: Subscription, *, expires_at: int, traffic_gb: float, plan: Plan
    ) -> ClientResult | None:
        try:
            await self._update(
                sub, expiry_ms=int(expires_at) * 1000, total=gb_to_bytes(traffic_gb), reset_traffic=True
            )
            return None
        except ClientNotFound as exc:
            # کاربر از پنل حذف شده (مثلاً با پاکسازی کاربران منقضی) → ساخت کاربر جدید
            log.warning("Client of subscription #%s not found on panel, recreating: %s", sub.id, exc)
            return await self.create_client(
                remark=f"u{sub.user_id}_{random_string(5)}",
                expires_at=expires_at,
                traffic_gb=traffic_gb,
                plan=plan,
                user_id=sub.user_id,
            )

    async def set_expiry(self, sub: Subscription, expires_at: int) -> None:
        await self._update(sub, expiry_ms=int(expires_at) * 1000, total=None, reset_traffic=False)

    async def get_usage(self, sub: Subscription) -> ClientUsage | None:
        meta = sub.meta
        async with self._session() as session:
            if meta.get("api") == "v3":
                emails = [str(meta["email"])]
                path = "/panel/api/clients/traffic/{}"
            else:
                emails = [str(c["email"]) for c in meta.get("clients") or []]
                path = "/panel/api/inbounds/getClientTraffics/{}"
            used = total = 0
            expiry = 0
            enabled = False
            found = False
            for email in emails:
                obj = await session.api("GET", path.format(quote(email, safe="")))
                if not isinstance(obj, dict):
                    continue
                found = True
                used += int(obj.get("up") or 0) + int(obj.get("down") or 0)
                total = max(total, int(obj.get("total") or 0))
                expiry = max(expiry, int(obj.get("expiryTime") or 0))
                enabled = enabled or bool(obj.get("enable", True))
        if not found:
            return None
        return ClientUsage(
            used_bytes=used,
            total_bytes=total,
            expires_at=expiry // 1000 if expiry > 0 else None,
            enabled=enabled,
        )

    async def delete_client(self, sub: Subscription) -> None:
        meta = sub.meta
        async with self._session() as session:
            if meta.get("api") == "v3":
                await session.api("POST", f"/panel/api/clients/del/{quote(str(meta['email']), safe='')}")
                return
            for item in meta.get("clients") or []:
                await session.api(
                    "POST",
                    f"/panel/api/inbounds/{int(item['inbound_id'])}/delClient/{quote(str(item['key']), safe='')}",
                    allow_empty=True,
                )
