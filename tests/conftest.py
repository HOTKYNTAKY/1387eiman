"""
ابزارهای مشترک تست‌ها

FakeSession به جای ارتباط واقعی با تلگرام، درخواست‌های ربات را ثبت و پاسخ ساختگی
برمی‌گرداند. به این ترتیب کل مسیر پردازش (میدل‌ورها، فیلترها، FSM، هندلرها و
دیتابیس) بدون اینترنت و توکن واقعی تست می‌شود.
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.filters.callback_data import CallbackData  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import Chat, File, Message, MessageId, PhotoSize, Update, User  # noqa: E402

from bot.app import create_dispatcher  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.database import Database  # noqa: E402
from bot.services.provisioning import Provisioner  # noqa: E402

TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ"
ADMIN_ID = 1000
BOT_USER = User(id=123456789, is_bot=True, first_name="VPN Bot", username="vpn_test_bot")

MESSAGE_METHODS = {
    "SendMessage",
    "SendPhoto",
    "SendDocument",
    "EditMessageText",
    "EditMessageCaption",
    "EditMessageReplyMarkup",
}


class FakeSession(BaseSession):
    """جایگزین شبکه تلگرام در تست‌ها."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.files: dict[str, bytes] = {}
        self._ids = itertools.count(5000)

    async def close(self) -> None:
        return None

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.requests.append(method)
        name = type(method).__name__
        if name in MESSAGE_METHODS:
            chat_id = getattr(method, "chat_id", None) or 0
            kwargs: dict[str, Any] = {
                "message_id": getattr(method, "message_id", None) or next(self._ids),
                "date": datetime.now(),
                "chat": Chat(id=int(chat_id), type="private"),
                "from_user": BOT_USER,
            }
            if name == "SendPhoto":
                kwargs["photo"] = [PhotoSize(file_id="photo-id", file_unique_id="p", width=100, height=100)]
                kwargs["caption"] = method.caption
            elif name in ("SendDocument", "EditMessageCaption"):
                kwargs["caption"] = method.caption
            else:
                kwargs["text"] = getattr(method, "text", None) or "."
            return Message(**kwargs).as_(bot)
        if name == "CopyMessage":
            return MessageId(message_id=next(self._ids))
        if name == "GetMe":
            return BOT_USER
        if name == "GetFile":
            return File(file_id=method.file_id, file_unique_id="u", file_path=f"files/{method.file_id}",
                        file_size=len(self.files.get(method.file_id, b"")))
        return True

    async def stream_content(
        self, url: str, headers: dict[str, Any] | None = None, timeout: int = 30, chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        file_id = url.rsplit("/files/", 1)[-1]
        yield self.files[file_id]

    # ------------------------------------------------------------------
    def of(self, *names: str, since: int = 0) -> list[TelegramMethod[Any]]:
        return [r for r in self.requests[since:] if type(r).__name__ in names]


def method_text(method: TelegramMethod[Any]) -> str:
    return str(getattr(method, "text", None) or getattr(method, "caption", None) or "")


def buttons(method: TelegramMethod[Any]) -> list[tuple[str, str]]:
    """(متن، callback_data یا url) دکمه‌های شیشه‌ای یک پیام."""
    markup = getattr(method, "reply_markup", None)
    rows = getattr(markup, "inline_keyboard", None) or []
    return [(b.text, b.callback_data or b.url or "") for row in rows for b in row]


@dataclass
class Env:
    dp: Dispatcher
    bot: Bot
    session: FakeSession
    db: Database
    config: Config
    _update_ids: Any = field(default_factory=lambda: itertools.count(1))
    _message_ids: Any = field(default_factory=lambda: itertools.count(1))

    def _user(self, user_id: int) -> dict[str, Any]:
        return {"id": user_id, "is_bot": False, "first_name": f"User{user_id}", "username": f"user{user_id}"}

    async def send(
        self,
        user_id: int,
        text: str | None = None,
        *,
        photo: str | None = None,
        document: tuple[str, str] | None = None,
        caption: str | None = None,
        forward_from: int | None = None,
    ) -> list[TelegramMethod[Any]]:
        """ارسال پیام از طرف کاربر و برگرداندن درخواست‌هایی که ربات در پاسخ فرستاد."""
        start = len(self.session.requests)
        message: dict[str, Any] = {
            "message_id": next(self._message_ids),
            "date": int(datetime.now().timestamp()),
            "chat": {"id": user_id, "type": "private"},
            "from": self._user(user_id),
        }
        if text is not None:
            message["text"] = text
            if text.startswith("/"):
                message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        if photo:
            message["photo"] = [{"file_id": photo, "file_unique_id": photo, "width": 800, "height": 600}]
        if document:
            file_id, name = document
            message["document"] = {"file_id": file_id, "file_unique_id": file_id, "file_name": name,
                                   "file_size": len(self.session.files.get(file_id, b""))}
        if caption:
            message["caption"] = caption
        if forward_from:
            message["forward_origin"] = {"type": "user", "date": 1, "sender_user": self._user(forward_from)}
        update = Update.model_validate({"update_id": next(self._update_ids), "message": message}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)
        return self.session.requests[start:]

    async def click(self, user_id: int, data: CallbackData | str, *, photo_message: bool = False) -> list[TelegramMethod[Any]]:
        """کلیک روی دکمه شیشه‌ای از طرف کاربر."""
        start = len(self.session.requests)
        message: dict[str, Any] = {
            "message_id": next(self._message_ids),
            "date": int(datetime.now().timestamp()),
            "chat": {"id": user_id, "type": "private"},
            "from": BOT_USER.model_dump(),
        }
        if photo_message:
            message["photo"] = [{"file_id": "x", "file_unique_id": "x", "width": 1, "height": 1}]
            message["caption"] = "order"
        else:
            message["text"] = "menu"
        payload = {
            "id": str(next(self._update_ids)),
            "from": self._user(user_id),
            "chat_instance": "ci",
            "data": data.pack() if isinstance(data, CallbackData) else data,
            "message": message,
        }
        update = Update.model_validate(
            {"update_id": next(self._update_ids), "callback_query": payload}, context={"bot": self.bot}
        )
        await self.dp.feed_update(self.bot, update)
        return self.session.requests[start:]


def make_config(tmp_path: Path, admin_ids: tuple[int, ...] = (ADMIN_ID,)) -> Config:
    return Config(
        bot_token=TOKEN,
        admin_ids=admin_ids,
        timezone=ZoneInfo("Asia/Tehran"),
        backup_time=time(0, 0),
        backup_keep=5,
        db_path=tmp_path / "data" / "bot.db",
        backup_dir=tmp_path / "backups",
        log_dir=tmp_path / "logs",
        log_level="INFO",
        proxy_url=None,
        panel_verify_ssl=False,
    )


@pytest.fixture(scope="session")
def dispatcher(tmp_path_factory: pytest.TempPathFactory) -> Dispatcher:
    """
    روترهای ماژول‌ها فقط یک بار قابل اتصال هستند؛ بنابراین Dispatcher یک بار ساخته
    می‌شود و در هر تست وابستگی‌ها (config/db/storage) با نمونه تازه جایگزین می‌شوند.
    """
    base = tmp_path_factory.mktemp("dispatcher")
    config = make_config(base)
    return create_dispatcher(config, Database(config.db_path), throttle_rate=0)


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def env(tmp_path: Path, dispatcher: Dispatcher) -> AsyncIterator[Env]:
    config = make_config(tmp_path)
    database = Database(config.db_path)
    await database.connect()
    dispatcher["config"] = config
    dispatcher["db"] = database
    dispatcher["provisioner"] = Provisioner(database, config)
    dispatcher.fsm.storage = MemoryStorage()
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    yield Env(dp=dispatcher, bot=bot, session=session, db=database, config=config)
    await database.close()
