"""کلاینت HTTP ساده برای ارتباط با API پنل‌ها (بر پایه aiohttp)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from bot import __version__
from bot.services.panels.base import PanelError

log = logging.getLogger(__name__)


def normalize_base_url(url: str, strip_suffixes: tuple[str, ...] = ()) -> str:
    """
    آدرس پنل را یکدست می‌کند:
      - افزودن http:// اگر پروتکل ذکر نشده باشد
      - حذف / انتهایی، کوئری و مسیرهای صفحات پنل (مثل /panel/inbounds یا /login)
        تا ادمین بتواند آدرس را مستقیماً از نوار مرورگر کپی کند.
    هر پسوند حداکثر یک بار (به ترتیب لیست) حذف می‌شود تا مسیر مخفی پنل آسیب نبیند.
    """
    url = url.strip()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    for suffix in strip_suffixes:
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class HttpClient:
    """
    یک نشست HTTP با کوکی (برای لاگین پنل) و تایم‌اوت.
    CookieJar(unsafe=True) لازم است تا کوکی‌ها برای آدرس‌های IP هم ذخیره شوند.
    """

    def __init__(self, base_url: str, *, verify_ssl: bool = False, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.headers: dict[str, str] = {}
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> HttpClient:
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.verify_ssl),
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            headers={"User-Agent": f"VPNShopBot/{__version__}", "Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session is not None:
            await self._session.close()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        data: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """
        ارسال درخواست و برگرداندن (کد وضعیت، بدنه JSON یا None).
        خطاهای شبکه به PanelError با پیام فارسی تبدیل می‌شوند.
        """
        assert self._session is not None, "use 'async with HttpClient(...)'"
        url = path if path.startswith("http") else self.base_url + path
        try:
            async with self._session.request(
                method,
                url,
                json=json_body,
                data=data,
                params=params,
                headers={**self.headers, **(headers or {})},
            ) as response:
                text = await response.text()
                status = response.status
        except asyncio.TimeoutError as exc:
            raise PanelError("پنل در زمان مقرر پاسخ نداد (Timeout).") from exc
        except aiohttp.ClientSSLError as exc:
            raise PanelError(
                "خطای SSL در اتصال به پنل. اگر گواهی پنل self-signed است، "
                "PANEL_VERIFY_SSL=false را در .env تنظیم کنید."
            ) from exc
        except aiohttp.ClientError as exc:
            raise PanelError(f"اتصال به پنل برقرار نشد: {exc.__class__.__name__}") from exc

        if not text:
            return status, None
        try:
            return status, json.loads(text)
        except ValueError:
            log.debug("Non-JSON response from %s (%s): %.200s", url, status, text)
            return status, None


async def fetch_subscription_links(url: str, *, verify_ssl: bool = False, timeout: float = 15.0) -> list[str]:
    """
    دریافت محتوای لینک ساب‌اسکریپشن و استخراج کانفیگ‌ها.
    خروجی ساب معمولاً لیست کانفیگ‌ها به صورت base64 است.
    در صورت هر خطایی لیست خالی برمی‌گرداند (این مرحله اختیاری است).
    """
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=verify_ssl),
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": "v2rayNG/1.9.0", "Accept": "*/*"},
        ) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                body = (await response.text()).strip()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.info("Cannot fetch subscription %s: %s", url, exc)
        return []
    return parse_subscription_body(body)


def parse_subscription_body(body: str) -> list[str]:
    """تبدیل متن ساب (base64 یا متن ساده) به لیست کانفیگ‌ها."""
    text = body.strip()
    if "://" not in text:
        try:
            padded = text + "=" * (-len(text) % 4)
            text = base64.b64decode(padded, altchars=b"-_" if "-" in text or "_" in text else None).decode(
                "utf-8", "ignore"
            )
        except (binascii.Error, ValueError):
            return []
    return [line.strip() for line in text.splitlines() if "://" in line]
