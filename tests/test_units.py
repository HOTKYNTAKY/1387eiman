"""تست‌های واحد: تنظیمات، ویزارد، زمان‌بند، ساخت لینک، قالب‌بندی و کارهای زمان‌بندی‌شده."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from bot import config as config_module
from bot.config import ConfigError, is_valid_token, load_config, parse_admin_ids
from bot.database.models import SubStatus, now_ts
from bot.services.jobs import subscription_check_job
from bot.services.panels.http import normalize_base_url, parse_subscription_body
from bot.services.panels.xui_links import build_links, replace_link_host
from bot.services.scheduler import Scheduler, next_daily_run
from bot.utils.formatting import fmt_duration, parse_float, parse_int, split_text

from .conftest import TOKEN, Env
from .mock_panels import REALITY_STREAM, WS_TLS_STREAM


# ----------------------------------------------------------------------
# تنظیمات و ویزارد
# ----------------------------------------------------------------------
def test_token_and_admin_parsing() -> None:
    assert is_valid_token(TOKEN)
    assert not is_valid_token("12345")
    assert not is_valid_token("abc:def")
    assert parse_admin_ids("123, 456 123") == (123, 456)
    assert parse_admin_ids("12a") == ()
    assert parse_admin_ids("") == ()


def test_load_config_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in config_module.KNOWN_KEYS:
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(f"BOT_TOKEN={TOKEN}\nADMIN_ID=111,222\nBACKUP_TIME=03:30\nDB_PATH=/tmp/x/bot.db\nTIMEZONE=Asia/Tehran\n")
    config = load_config(env, allow_wizard=False)
    assert config.admin_ids == (111, 222) and config.owner_id == 111
    assert config.backup_time == time(3, 30)
    assert config.db_path == Path("/tmp/x/bot.db")
    assert config.backup_dir == config_module.BASE_DIR / "backups"

    env.write_text("BOT_TOKEN=\nADMIN_ID=\n")
    with pytest.raises(ConfigError, match="--setup"):
        load_config(env, allow_wizard=False)

    env.write_text(f"BOT_TOKEN={TOKEN}\nADMIN_ID=1\nBACKUP_TIME=25:00\n")
    with pytest.raises(ConfigError, match="BACKUP_TIME"):
        load_config(env, allow_wizard=False)


def test_setup_wizard_writes_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bot import setup_wizard

    answers = iter(["bad-token", TOKEN, "abc", "987654321"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(setup_wizard, "verify_token_online", lambda token: (None, "offline"))
    env = tmp_path / ".env"
    setup_wizard.run_wizard(env)
    content = env.read_text()
    assert f"BOT_TOKEN={TOKEN}" in content and "ADMIN_ID=987654321" in content
    assert "TIMEZONE=Asia/Tehran" in content  # از .env.example کپی شده
    assert oct(env.stat().st_mode & 0o777) == "0o600"


# ----------------------------------------------------------------------
# زمان‌بند
# ----------------------------------------------------------------------
def test_next_daily_run() -> None:
    tz = ZoneInfo("Asia/Tehran")
    before = datetime(2026, 9, 28, 23, 59, 30, tzinfo=tz)
    assert next_daily_run(before, time(0, 0)) == datetime(2026, 9, 29, 0, 0, tzinfo=tz)
    exactly = datetime(2026, 9, 29, 0, 0, tzinfo=tz)
    assert next_daily_run(exactly, time(0, 0)) == datetime(2026, 9, 30, 0, 0, tzinfo=tz)
    morning = datetime(2026, 9, 29, 8, 0, tzinfo=tz)
    assert next_daily_run(morning, time(12, 30)) == datetime(2026, 9, 29, 12, 30, tzinfo=tz)
    # ساعت تابستانی (اروپا): نیمه‌شب محلی حفظ می‌شود
    berlin = ZoneInfo("Europe/Berlin")
    target = next_daily_run(datetime(2026, 10, 24, 12, 0, tzinfo=berlin), time(0, 0))
    assert target.hour == 0 and target.utcoffset().total_seconds() == 7200


async def test_scheduler_runs_jobs_and_survives_errors() -> None:
    scheduler = Scheduler(ZoneInfo("UTC"))
    calls: list[str] = []

    async def good() -> None:
        calls.append("ok")

    async def bad() -> None:
        calls.append("bad")
        raise RuntimeError("boom")

    scheduler.interval(3600, good, "good", first_delay=0)
    scheduler.interval(3600, bad, "bad", first_delay=0)
    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()
    assert sorted(calls) == ["bad", "ok"]


# ----------------------------------------------------------------------
# لینک‌ها
# ----------------------------------------------------------------------
def test_vless_reality_link() -> None:
    inbound = {"protocol": "vless", "port": 443, "settings": json.dumps({"clients": []}),
               "streamSettings": json.dumps(REALITY_STREAM)}
    client = {"id": "11111111-2222-3333-4444-555555555555", "flow": "xtls-rprx-vision"}
    link = build_links(inbound, client, "de.example.com", "🇩🇪 Germany-u1")[0]
    parts = urlsplit(link)
    assert parts.scheme == "vless" and parts.hostname == "de.example.com" and parts.port == 443
    assert parts.username == client["id"]
    query = parse_qs(parts.query)
    assert query == {
        "type": ["tcp"], "encryption": ["none"], "security": ["reality"], "sni": ["www.speedtest.net"],
        "pbk": ["PUBKEY123"], "sid": ["ab12cd"], "fp": ["chrome"], "spx": ["/"], "flow": ["xtls-rprx-vision"],
    }
    assert parts.fragment  # نام کانفیگ (URL-encoded)


def test_vmess_ws_tls_and_trojan_grpc_links() -> None:
    vmess = build_links({"protocol": "vmess", "port": 8443, "streamSettings": WS_TLS_STREAM},
                        {"id": "uuid-1", "security": "auto"}, "1.2.3.4", "r")[0]
    data = json.loads(base64.b64decode(vmess[len("vmess://"):]))
    assert data["add"] == "1.2.3.4" and data["port"] == 8443 and data["net"] == "ws"
    assert data["tls"] == "tls" and data["sni"] == "cdn.example.com" and data["alpn"] == "h2,http/1.1"

    grpc_stream = {"network": "grpc", "security": "tls", "grpcSettings": {"serviceName": "svc", "multiMode": True},
                   "tlsSettings": {"serverName": "t.example.com"}}
    trojan = build_links({"protocol": "trojan", "port": 443, "streamSettings": grpc_stream},
                         {"password": "p@ss"}, "t.example.com", "r")[0]
    query = parse_qs(urlsplit(trojan).query)
    assert trojan.startswith("trojan://p%40ss@t.example.com:443")
    assert query["serviceName"] == ["svc"] and query["mode"] == ["multi"] and query["security"] == ["tls"]


def test_external_proxy_links() -> None:
    stream = dict(WS_TLS_STREAM, externalProxy=[
        {"forceTls": "same", "dest": "cdn1.example.com", "port": 443, "remark": "CDN"},
        {"forceTls": "none", "dest": "direct.example.com", "port": 80, "remark": ""},
    ])
    links = build_links({"protocol": "vless", "port": 2083, "streamSettings": stream}, {"id": "u"}, "x", "r")
    assert len(links) == 2
    first, second = (parse_qs(urlsplit(link).query) for link in links)
    assert first["security"] == ["tls"] and "sni" in first
    assert second["security"] == ["none"] and "sni" not in second
    assert urlsplit(links[1]).hostname == "direct.example.com"


def test_replace_host_and_subscription_parsing() -> None:
    assert replace_link_host("vless://id@127.0.0.1:443?a=1#x", "vpn.example.com") == "vless://id@vpn.example.com:443?a=1#x"
    vmess = "vmess://" + base64.b64encode(json.dumps({"add": "127.0.0.1", "port": 1}).encode()).decode()
    replaced = replace_link_host(vmess, "vpn.example.com")
    assert json.loads(base64.b64decode(replaced[8:]))["add"] == "vpn.example.com"

    body = base64.b64encode(b"vless://a@b:1#x\nvmess://abc\n").decode()
    assert parse_subscription_body(body) == ["vless://a@b:1#x", "vmess://abc"]
    assert parse_subscription_body("trojan://p@h:1") == ["trojan://p@h:1"]
    assert parse_subscription_body("<html>not a sub</html>") == []


def test_normalize_base_url() -> None:
    suffixes = ("/login", "/inbounds", "/settings", "/xray", "/clients", "/panel")
    assert normalize_base_url("1.2.3.4:2053/AbC/panel/inbounds/", suffixes) == "http://1.2.3.4:2053/AbC"
    assert normalize_base_url("https://d.com:2053/x/login?next=1", suffixes) == "https://d.com:2053/x"
    assert normalize_base_url("https://d.com/panel/panel/", suffixes) == "https://d.com/panel"


def test_formatting_helpers() -> None:
    assert parse_int("۱۲۳,۴۵۶ تومان") == 123456
    assert parse_int("12.5") is None
    assert parse_float("۲٫۵") == 2.5
    assert fmt_duration(0) == "تمام شده"
    assert fmt_duration(2 * 86400 + 3 * 3600) == "2 روز و 3 ساعت"
    chunks = split_text("\n".join(["x" * 50] * 200), limit=1000)
    assert all(len(c) <= 1000 for c in chunks) and sum(c.count("x") for c in chunks) == 50 * 200


# ----------------------------------------------------------------------
# کار زمان‌بندی‌شده بررسی سرویس‌ها
# ----------------------------------------------------------------------
async def test_subscription_check_job_warns_and_expires(env: Env) -> None:
    await env.db.users.upsert(1, "a", "A")
    common = {"user_id": 1, "plan_id": None, "server_id": None, "config": "vless://x", "sub_link": "", "meta": {},
              "traffic_gb": 0, "started_at": now_ts()}
    soon = await env.db.subscriptions.create(title="soon", expires_at=now_ts() + 3600, **common)
    gone = await env.db.subscriptions.create(title="gone", expires_at=now_ts() - 60, **common)
    later = await env.db.subscriptions.create(title="later", expires_at=now_ts() + 10 * 86400, **common)
    stale = await env.db.orders.create(user_id=1, plan_id=None, kind="new", amount=1, plan_title="p", method="card")
    await env.db.execute("UPDATE orders SET created_at = ? WHERE id = ?", (now_ts() - 2 * 86400, stale))

    await subscription_check_job(env.bot, env.db, env.config)
    assert (await env.db.subscriptions.get(soon)).warned == 1
    assert (await env.db.subscriptions.get(gone)).status == SubStatus.EXPIRED
    assert (await env.db.subscriptions.get(later)).warned == 0
    assert (await env.db.orders.get(stale)).status == "canceled"
    texts = [m.text for m in env.session.of("SendMessage")]
    assert any("یادآوری تمدید" in t for t in texts) and any("منقضی شد" in t for t in texts)

    # اجرای دوباره پیام تکراری نمی‌فرستد
    count = len(env.session.of("SendMessage"))
    await subscription_check_job(env.bot, env.db, env.config)
    assert len(env.session.of("SendMessage")) == count


async def test_daily_backup_job_sends_file_to_admins(env: Env) -> None:
    from bot.services.jobs import daily_backup_job

    await daily_backup_job(env.bot, env.db, env.config)
    documents = env.session.of("SendDocument")
    assert documents and documents[0].chat_id == env.config.owner_id
    assert "بکاپ خودکار روزانه" in documents[0].caption
    assert list(env.config.backup_dir.glob("backup_*.zip"))
