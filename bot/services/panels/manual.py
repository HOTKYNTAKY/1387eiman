"""
سرور «دستی»: تحویل کانفیگ از انبار

ادمین کانفیگ‌های آماده (هر خط یک کانفیگ یا لینک ساب) را برای هر پلن در ربات
وارد می‌کند و ربات پس از تایید پرداخت، یکی از آن‌ها را به صورت خودکار تحویل
می‌دهد. برای تمدید، یک کانفیگ جدید از انبار پلن تمدید تحویل داده می‌شود.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.database.models import Plan, Server, Subscription
from bot.services.panels.base import BasePanel, ClientResult, PanelError

if TYPE_CHECKING:
    from bot.database import Database


class ManualPanel(BasePanel):
    def __init__(self, server: Server, db: Database) -> None:
        super().__init__(server)
        self.db = db

    async def test(self) -> str:
        plans = await self.db.plans.list_for_server(self.server.id, only_active=False)
        lines = ["✅ سرور دستی (بدون نیاز به اتصال)", "\nموجودی انبار پلن‌ها:"]
        for plan in plans:
            available = await self.db.configs.count_available(plan.id)
            lines.append(f"▫️ {plan.name}: {available} کانفیگ آزاد")
        if not plans:
            lines.append("هنوز پلنی برای این سرور تعریف نشده است.")
        return "\n".join(lines)

    async def _pop(self, plan: Plan) -> ClientResult:
        item = await self.db.configs.pop(plan.id)
        if item is None:
            raise PanelError(f"موجودی کانفیگ پلن «{plan.name}» تمام شده است.")
        return ClientResult(links=[item.content], meta={"config_id": item.id})

    async def create_client(
        self, *, remark: str, expires_at: int, traffic_gb: float, plan: Plan, user_id: int
    ) -> ClientResult:
        return await self._pop(plan)

    async def renew_client(
        self, sub: Subscription, *, expires_at: int, traffic_gb: float, plan: Plan
    ) -> ClientResult | None:
        return await self._pop(plan)
