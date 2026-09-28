"""
لایه دسترسی به دیتابیس SQLite

یک اتصال (connection) مشترک برای کل برنامه باز می‌شود. چون چند هندلر ممکن است
همزمان اجرا شوند، تمام دستورات با یک قفل asyncio سریال می‌شوند تا تراکنش‌ها
با هم تداخل نداشته باشند.

نمونه استفاده:
    db = Database(Path("data/bot.db"))
    await db.connect()
    user = await db.users.get(123)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from bot.database.schema import DEFAULT_SETTINGS, MIGRATIONS

log = logging.getLogger(__name__)

Params = Sequence[Any] | dict[str, Any]


class Database:
    """مدیریت اتصال، مهاجرت، تراکنش و بکاپ/ریستور دیتابیس."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

        # ریپازیتوری‌ها (هر کدام مسئول یک جدول/بخش)
        from bot.database.repos import (
            ConfigRepo,
            OrderRepo,
            PlanRepo,
            ServerRepo,
            SettingsRepo,
            SubscriptionRepo,
            TicketRepo,
            UserRepo,
        )

        self.users = UserRepo(self)
        self.servers = ServerRepo(self)
        self.plans = PlanRepo(self)
        self.configs = ConfigRepo(self)
        self.subscriptions = SubscriptionRepo(self)
        self.orders = OrderRepo(self)
        self.tickets = TicketRepo(self)
        self.settings = SettingsRepo(self)

    # ------------------------------------------------------------------
    # اتصال و مهاجرت
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """اتصال به دیتابیس، تنظیم PRAGMAها و اجرای مهاجرت‌ها."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None یعنی حالت autocommit؛ تراکنش‌ها را خودمان مدیریت می‌کنیم
        self._conn = await aiosqlite.connect(self.path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=10000")
        await self.migrate()
        try:
            os.chmod(self.path, 0o600)  # دیتابیس شامل اطلاعات حساس است
        except OSError:
            pass
        log.info("Database connected: %s", self.path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def migrate(self) -> None:
        """اجرای مهاجرت‌های باقی‌مانده و درج تنظیمات پیش‌فرض."""
        async with self._lock:
            async with self.conn.execute("PRAGMA user_version") as cur:
                row = await cur.fetchone()
            version = int(row[0]) if row else 0
            for index in range(version, len(MIGRATIONS)):
                log.info("Applying database migration v%d", index + 1)
                await self.conn.executescript(MIGRATIONS[index])
                await self.conn.execute(f"PRAGMA user_version = {index + 1}")
            for key, value in DEFAULT_SETTINGS.items():
                await self.conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
                )

    # ------------------------------------------------------------------
    # اجرای دستورات
    # ------------------------------------------------------------------
    async def execute(self, sql: str, params: Params = ()) -> tuple[int, int]:
        """
        اجرای یک دستور تغییر (INSERT/UPDATE/DELETE).
        :return: (lastrowid, rowcount)
        """
        async with self._lock:
            async with self.conn.execute(sql, params) as cur:
                return cur.lastrowid or 0, cur.rowcount

    async def executemany(self, sql: str, seq: Sequence[Params]) -> int:
        async with self._lock:
            async with self.conn.executemany(sql, seq) as cur:
                return cur.rowcount

    async def fetchone(self, sql: str, params: Params = ()) -> aiosqlite.Row | None:
        async with self._lock:
            async with self.conn.execute(sql, params) as cur:
                return await cur.fetchone()

    async def fetchall(self, sql: str, params: Params = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            async with self.conn.execute(sql, params) as cur:
                return list(await cur.fetchall())

    async def fetchval(self, sql: str, params: Params = (), default: Any = None) -> Any:
        """مقدار ستون اول از ردیف اول (مثلاً برای COUNT)."""
        row = await self.fetchone(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """
        تراکنش اتمی. داخل بلوک باید مستقیماً از اتصال برگردانده‌شده استفاده شود
        (نه متدهای execute/fetch که خودشان قفل را می‌گیرند).

            async with db.transaction() as conn:
                await conn.execute(...)
        """
        async with self._lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            else:
                await self.conn.execute("COMMIT")

    # ------------------------------------------------------------------
    # بکاپ و ریستور (با API رسمی بکاپ SQLite برای کپی سازگار و امن)
    # ------------------------------------------------------------------
    async def backup_to(self, destination: Path) -> None:
        """یک کپی سازگار (consistent) و تک‌فایلی از دیتابیس در مسیر مقصد می‌سازد."""
        await asyncio.to_thread(sqlite_copy, self.path, destination, standalone=True)

    async def restore_from(self, source: Path) -> None:
        """
        محتوای دیتابیس فعلی را با فایل منبع جایگزین می‌کند (بدون نیاز به ری‌استارت).
        فایل منبع باید قبلاً اعتبارسنجی شده باشد.
        """
        async with self._lock:
            await asyncio.to_thread(sqlite_copy, source, self.path, standalone=False)
        # اگر بکاپ مربوط به نسخه قدیمی‌تر باشد، ساختار به‌روز می‌شود
        await self.migrate()


def sqlite_copy(source: Path, destination: Path, *, standalone: bool) -> None:
    """
    کپی کامل یک دیتابیس SQLite به دیگری با backup API.
    این روش حتی وقتی دیتابیس در حال استفاده است، خروجی سالم تولید می‌کند.

    :param standalone: اگر True باشد (ساخت فایل بکاپ)، فایل مقصد به حالت
        journal معمولی تبدیل می‌شود تا یک فایل مستقل و قابل انتقال باشد.
        برای ریستور روی دیتابیس اصلی False است تا حالت WAL آن حفظ شود.
    """
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(destination))
    try:
        dst.execute("PRAGMA busy_timeout=10000")
        src.backup(dst)
        if standalone:
            dst.execute("PRAGMA journal_mode=DELETE")
        else:
            mode = dst.execute("PRAGMA journal_mode").fetchone()[0]
            if str(mode).lower() == "wal":
                # انتقال تغییرات از فایل WAL به فایل اصلی دیتابیس
                dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        src.close()
        dst.close()
