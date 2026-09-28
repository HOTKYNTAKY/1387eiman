"""کلاس پایه ریپازیتوری‌ها."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.database.db import Database


class BaseRepo:
    # ستون‌هایی که اجازه به‌روزرسانی از طریق update() را دارند (در هر زیرکلاس تعریف می‌شود)
    table: str = ""
    updatable: frozenset[str] = frozenset()

    def __init__(self, db: Database) -> None:
        self.db = db

    async def update(self, row_id: int, **values: Any) -> bool:
        """
        به‌روزرسانی ستون‌های مجاز یک ردیف.
        نام ستون‌ها با لیست سفید بررسی می‌شود تا از تزریق SQL جلوگیری شود.
        """
        if not values:
            return False
        invalid = set(values) - self.updatable
        if invalid:
            raise ValueError(f"Columns not updatable on {self.table}: {sorted(invalid)}")
        assignments = ", ".join(f"{column} = ?" for column in values)
        _, count = await self.db.execute(
            f"UPDATE {self.table} SET {assignments} WHERE id = ?",  # noqa: S608 (ستون‌ها از لیست سفید)
            (*values.values(), row_id),
        )
        return count > 0
