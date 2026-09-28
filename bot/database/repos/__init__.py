"""ریپازیتوری‌ها: هر کلاس عملیات مربوط به یک جدول را کپسوله می‌کند."""

from bot.database.repos.configs import ConfigRepo
from bot.database.repos.orders import OrderRepo
from bot.database.repos.plans import PlanRepo
from bot.database.repos.servers import ServerRepo
from bot.database.repos.settings import SettingsRepo
from bot.database.repos.subscriptions import SubscriptionRepo
from bot.database.repos.tickets import TicketRepo
from bot.database.repos.users import UserRepo

__all__ = [
    "ConfigRepo",
    "OrderRepo",
    "PlanRepo",
    "ServerRepo",
    "SettingsRepo",
    "SubscriptionRepo",
    "TicketRepo",
    "UserRepo",
]
