"""عملیات تیکت‌های پشتیبانی."""

from __future__ import annotations

from bot.database.models import Ticket, TicketMessage, TicketStatus, now_ts
from bot.database.repos.base import BaseRepo


class TicketRepo(BaseRepo):
    table = "tickets"
    updatable = frozenset({"subject", "status", "updated_at"})

    async def create(self, user_id: int, subject: str) -> int:
        now = now_ts()
        row_id, _ = await self.db.execute(
            "INSERT INTO tickets (user_id, subject, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, subject[:60], TicketStatus.OPEN, now, now),
        )
        return row_id

    async def add_message(
        self,
        ticket_id: int,
        sender: str,
        text: str,
        file_id: str | None = None,
        file_kind: str | None = None,
    ) -> int:
        """افزودن پیام و به‌روزرسانی وضعیت تیکت براساس فرستنده."""
        now = now_ts()
        status = TicketStatus.ANSWERED if sender == "admin" else TicketStatus.OPEN
        async with self.db.transaction() as conn:
            cur = await conn.execute(
                """
                INSERT INTO ticket_messages (ticket_id, sender, text, file_id, file_kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticket_id, sender, text, file_id, file_kind, now),
            )
            message_id = cur.lastrowid or 0
            await cur.close()
            await conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, now, ticket_id)
            )
        return message_id

    async def get(self, ticket_id: int) -> Ticket | None:
        row = await self.db.fetchone("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return Ticket.from_row(row) if row else None

    async def messages(self, ticket_id: int, limit: int = 30) -> list[TicketMessage]:
        """آخرین پیام‌های تیکت به ترتیب زمانی."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM (
                SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY id DESC LIMIT ?
            ) ORDER BY id
            """,
            (ticket_id, limit),
        )
        return [TicketMessage.from_row(r) for r in rows]

    async def list_for_user(self, user_id: int, limit: int = 10) -> list[Ticket]:
        rows = await self.db.fetchall(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?", (user_id, limit)
        )
        return [Ticket.from_row(r) for r in rows]

    async def list_by_status(self, status: str, limit: int = 20, offset: int = 0) -> list[Ticket]:
        rows = await self.db.fetchall(
            "SELECT * FROM tickets WHERE status = ? ORDER BY updated_at LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        return [Ticket.from_row(r) for r in rows]

    async def count_by_status(self, status: str) -> int:
        return int(
            await self.db.fetchval("SELECT COUNT(*) FROM tickets WHERE status = ?", (status,), default=0)
        )

    async def count_unclosed_for_user(self, user_id: int) -> int:
        return int(
            await self.db.fetchval(
                "SELECT COUNT(*) FROM tickets WHERE user_id = ? AND status != ?",
                (user_id, TicketStatus.CLOSED),
                default=0,
            )
        )

    async def set_status(self, ticket_id: int, status: str) -> bool:
        return await self.update(ticket_id, status=status, updated_at=now_ts())
