"""
زمان‌بند ساده و سبک مبتنی بر asyncio (بدون وابستگی خارجی)

- daily(at, job):     اجرای روزانه در ساعت دقیق (مثلاً ۰۰:۰۰ به وقت تهران)
- interval(sec, job): اجرای دوره‌ای (مثلاً هر ۳۰ دقیقه)

برای دقت در زمان اجرا، خواب طولانی به تکه‌های حداکثر ۶۰ ثانیه‌ای تقسیم می‌شود؛
به این ترتیب تغییر ساعت سیستم یا تعلیق موقت سرور باعث جابه‌جایی زمان اجرا نمی‌شود.
خطای هر کار لاگ می‌شود و زمان‌بند را متوقف نمی‌کند.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

Job = Callable[[], Awaitable[None]]


def next_daily_run(now: datetime, at: time) -> datetime:
    """زمان اجرای بعدی یک کار روزانه (امروز اگر هنوز نرسیده، وگرنه فردا)."""
    tz = now.tzinfo
    candidate = datetime.combine(now.date(), at, tzinfo=tz)
    if candidate <= now:
        candidate = datetime.combine(now.date() + timedelta(days=1), at, tzinfo=tz)
    return candidate


class Scheduler:
    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz
        self._specs: list[tuple[str, Callable[[], Awaitable[None]]]] = []
        self._tasks: list[asyncio.Task[None]] = []
        self.next_runs: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    def daily(self, at: time, job: Job, name: str) -> None:
        async def loop() -> None:
            while True:
                target = next_daily_run(datetime.now(self.tz), at)
                self.next_runs[name] = target
                log.info("Job %r scheduled at %s", name, target.strftime("%Y-%m-%d %H:%M %Z"))
                while (remaining := (target - datetime.now(self.tz)).total_seconds()) > 0:
                    await asyncio.sleep(min(remaining, 60))
                await self._run(job, name)
                await asyncio.sleep(1)  # جلوگیری از اجرای دوباره در همان ثانیه

        self._specs.append((name, loop))

    def interval(self, seconds: int, job: Job, name: str, first_delay: int = 60) -> None:
        async def loop() -> None:
            await asyncio.sleep(first_delay)
            while True:
                await self._run(job, name)
                self.next_runs[name] = datetime.now(self.tz) + timedelta(seconds=seconds)
                await asyncio.sleep(seconds)

        self._specs.append((name, loop))

    # ------------------------------------------------------------------
    async def _run(self, job: Job, name: str) -> None:
        log.info("Running job %r", name)
        try:
            await job()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Job %r failed", name)

    def start(self) -> None:
        for name, loop in self._specs:
            self._tasks.append(asyncio.create_task(loop(), name=f"job:{name}"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
