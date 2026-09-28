"""
تحویل سرویس به کاربران

این ماژول پل بین «سفارش‌ها» و «پنل‌ها» است:
    - ساخت سرویس جدید پس از تایید پرداخت
    - تمدید سرویس (افزودن روز از تاریخ انقضای فعلی + صفر کردن مصرف)
    - افزایش/کاهش روز توسط ادمین
    - لغو سرویس و حذف کاربر از پنل
    - دریافت میزان مصرف از پنل
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.database.models import (
    Order,
    OrderKind,
    OrderStatus,
    Plan,
    Server,
    SubStatus,
    Subscription,
    now_ts,
)
from bot.services.panels import BasePanel, ClientResult, ClientUsage, PanelError, get_panel
from bot.services.panels.base import random_string

if TYPE_CHECKING:
    from bot.config import Config
    from bot.database import Database

log = logging.getLogger(__name__)

DAY = 86400


class DeliveryError(Exception):
    """خطای منطقی در تحویل سرویس (مثلاً پلن یا سرور پیدا نشد)."""


def make_remark(user_id: int) -> str:
    """نام یکتای کاربر روی پنل؛ مثال: u123456789_k3x9q (سازگار با همه پنل‌ها)."""
    return f"u{user_id}_{random_string(5)}"


class Provisioner:
    def __init__(self, db: Database, config: Config) -> None:
        self.db = db
        self.config = config

    def panel_for(self, server: Server) -> BasePanel:
        return get_panel(server, self.db, verify_ssl=self.config.panel_verify_ssl)

    async def _server_of(self, server_id: int | None) -> Server:
        server = await self.db.servers.get_any(server_id) if server_id else None
        if server is None:
            raise DeliveryError("سرور مربوط به این سرویس پیدا نشد.")
        return server

    # ------------------------------------------------------------------
    # سفارش‌ها
    # ------------------------------------------------------------------
    async def fulfill_order(
        self, order: Order, *, manual_links: list[str] | None = None, date_only: bool = False
    ) -> Subscription:
        """
        تحویل سفارش پرداخت‌شده (وضعیت paid). در صورت موفقیت، سفارش «تکمیل‌شده» می‌شود.
        :param manual_links: کانفیگی که ادمین دستی فرستاده (به جای ساخت خودکار)
        :param date_only: فقط تمدید تاریخ در ربات، بدون تغییر در پنل/انبار
        """
        plan = await self.db.plans.get_any(order.plan_id) if order.plan_id else None
        if plan is None:
            raise DeliveryError("پلن این سفارش پیدا نشد.")

        if order.kind == OrderKind.RENEW:
            sub = await self.db.subscriptions.get(order.subscription_id or 0)
            if sub is None:
                raise DeliveryError("سرویس موردنظر برای تمدید پیدا نشد.")
            sub = await self.renew_subscription(sub, plan, manual_links=manual_links, date_only=date_only)
        else:
            sub = await self.create_subscription(order.user_id, plan, manual_links=manual_links)

        await self.db.orders.transition(
            order.id, [OrderStatus.PAID], OrderStatus.COMPLETED, subscription_id=sub.id, note=None
        )
        log.info("Order #%s fulfilled -> subscription #%s", order.id, sub.id)
        return sub

    # ------------------------------------------------------------------
    # ساخت و تمدید
    # ------------------------------------------------------------------
    async def create_subscription(
        self, user_id: int, plan: Plan, *, manual_links: list[str] | None = None
    ) -> Subscription:
        server = await self._server_of(plan.server_id)
        now = now_ts()
        expires_at = now + plan.days * DAY

        if manual_links:
            result = ClientResult(links=manual_links)
        else:
            result = await self.panel_for(server).create_client(
                remark=make_remark(user_id),
                expires_at=expires_at,
                traffic_gb=plan.traffic_gb,
                plan=plan,
                user_id=user_id,
            )

        config_id = result.meta.get("config_id")
        try:
            sub_id = await self.db.subscriptions.create(
                user_id=user_id,
                plan_id=plan.id,
                server_id=server.id,
                title=plan.name,
                config="\n".join(result.links),
                sub_link=result.sub_link,
                meta=result.meta,
                traffic_gb=plan.traffic_gb,
                started_at=now,
                expires_at=expires_at,
            )
        except Exception:
            # کانفیگ انبار به موجودی برگردد؛ کاربر ساخته‌شده روی پنل در لاگ ثبت می‌شود
            if config_id:
                await self.db.configs.release(int(config_id))
            log.exception("DB error after creating panel client %s", result.meta)
            raise
        if config_id:
            await self.db.configs.attach(int(config_id), sub_id)

        sub = await self.db.subscriptions.get(sub_id)
        assert sub is not None
        return sub

    async def renew_subscription(
        self,
        sub: Subscription,
        plan: Plan,
        *,
        manual_links: list[str] | None = None,
        date_only: bool = False,
    ) -> Subscription:
        """
        تمدید سرویس: اگر هنوز فعال است روزها به تاریخ انقضای فعلی اضافه می‌شود،
        وگرنه از همین لحظه محاسبه می‌شود. حجم مصرفی روی پنل صفر می‌شود.
        """
        now = now_ts()
        base = sub.expires_at if (sub.status == SubStatus.ACTIVE and sub.expires_at > now) else now
        expires_at = base + plan.days * DAY
        updates: dict[str, object] = {
            "expires_at": expires_at,
            "traffic_gb": plan.traffic_gb,
            "status": SubStatus.ACTIVE,
            "warned": 0,
            "plan_id": plan.id,
            "title": plan.name,
        }

        result: ClientResult | None = None
        if manual_links:
            updates["config"] = "\n".join(manual_links)
        elif not date_only:
            server = await self._server_of(sub.server_id or plan.server_id)
            result = await self.panel_for(server).renew_client(
                sub, expires_at=expires_at, traffic_gb=plan.traffic_gb, plan=plan
            )
            if result is not None:
                # لینک‌ها تغییر کرده‌اند (کانفیگ جدید از انبار یا ساخت مجدد کاربر روی پنل)
                if result.links:
                    updates["config"] = "\n".join(result.links)
                updates["sub_link"] = result.sub_link
                if result.meta:
                    updates["meta"] = result.meta

        await self.db.subscriptions.update(sub.id, **updates)
        if result is not None and result.meta.get("config_id"):
            await self.db.configs.attach(int(result.meta["config_id"]), sub.id)

        renewed = await self.db.subscriptions.get(sub.id)
        assert renewed is not None
        return renewed

    # ------------------------------------------------------------------
    # عملیات ادمین
    # ------------------------------------------------------------------
    async def add_days(self, sub: Subscription, days: int) -> Subscription:
        """افزایش (یا با عدد منفی کاهش) روزهای سرویس."""
        now = now_ts()
        base = now if (days > 0 and sub.expires_at < now) else sub.expires_at
        expires_at = base + days * DAY

        server = await self.db.servers.get_any(sub.server_id) if sub.server_id else None
        if server is not None and not server.is_manual:
            await self.panel_for(server).set_expiry(sub, expires_at)

        status = SubStatus.ACTIVE if expires_at > now else SubStatus.EXPIRED
        await self.db.subscriptions.update(sub.id, expires_at=expires_at, status=status, warned=0)
        updated = await self.db.subscriptions.get(sub.id)
        assert updated is not None
        return updated

    async def cancel_subscription(self, sub: Subscription) -> str | None:
        """
        لغو سرویس: حذف کاربر از پنل و غیرفعال کردن در ربات.
        :return: متن هشدار اگر حذف از پنل ناموفق بود، وگرنه None
        """
        warning = None
        server = await self.db.servers.get_any(sub.server_id) if sub.server_id else None
        if server is not None and not server.is_manual:
            try:
                await self.panel_for(server).delete_client(sub)
            except PanelError as exc:
                warning = str(exc)
                log.warning("Cannot delete client of subscription #%s from panel: %s", sub.id, exc)
        await self.db.subscriptions.update(sub.id, status=SubStatus.DISABLED)
        return warning

    async def usage(self, sub: Subscription) -> ClientUsage | None:
        """میزان مصرف از پنل؛ در صورت خطا یا سرور دستی None."""
        server = await self.db.servers.get_any(sub.server_id) if sub.server_id else None
        if server is None or server.is_manual:
            return None
        try:
            return await self.panel_for(server).get_usage(sub)
        except PanelError as exc:
            log.info("Cannot get usage of subscription #%s: %s", sub.id, exc)
            return None
