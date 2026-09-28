"""
پنل‌های ساخت سرویس

get_panel() براساس نوع سرور، کلاس مناسب را برمی‌گرداند:
    manual  → ManualPanel  (انبار کانفیگ)
    xui     → XUIPanel     (3x-ui نسخه ۲ و ۳)
    marzban → MarzbanPanel (Marzban و PasarGuard)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.database.models import Server, ServerKind
from bot.services.panels.base import BasePanel, ClientResult, ClientUsage, PanelError
from bot.services.panels.manual import ManualPanel
from bot.services.panels.marzban import MarzbanPanel
from bot.services.panels.xui import XUIPanel

if TYPE_CHECKING:
    from bot.database import Database


def get_panel(server: Server, db: Database, *, verify_ssl: bool = False) -> BasePanel:
    """ساخت شیء پنل مناسب برای یک سرور."""
    if server.kind == ServerKind.MANUAL:
        return ManualPanel(server, db)
    if server.kind == ServerKind.XUI:
        return XUIPanel(server, verify_ssl=verify_ssl)
    if server.kind == ServerKind.MARZBAN:
        return MarzbanPanel(server, verify_ssl=verify_ssl)
    raise PanelError(f"نوع سرور ناشناخته است: {server.kind}")


__all__ = [
    "BasePanel",
    "ClientResult",
    "ClientUsage",
    "ManualPanel",
    "MarzbanPanel",
    "PanelError",
    "XUIPanel",
    "get_panel",
]
