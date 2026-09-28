"""تست اتصال به پنل‌ها با سرورهای ساختگی (3x-ui v2/v3، Marzban، PasarGuard)."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from aiohttp.test_utils import TestServer

from bot.database import Database
from bot.database.models import Plan, Server, Subscription, now_ts
from bot.services.panels import MarzbanPanel, PanelError, XUIPanel
from bot.services.provisioning import Provisioner

from .conftest import make_config
from .mock_panels import marzban_app, now_plus, xui_v2_app, xui_v3_app


def server(url: str, kind: str = "xui", **extra: Any) -> Server:
    values: dict[str, Any] = {
        "id": 1, "name": "DE", "kind": kind, "api_url": url, "api_user": "admin", "api_pass": "secret",
        "api_token": "", "inbound_ids": "1", "sub_url": "", "address": "", "is_active": 1, "is_deleted": 0,
        "created_at": now_ts(),
    }
    values.update(extra)
    return Server(**values)


PLAN = Plan(id=1, server_id=1, name="1M", days=30, traffic_gb=50, price=1, description="", is_active=1,
            is_deleted=0, sort_order=0, created_at=0)


def sub_from(result_meta: dict[str, Any], expires_at: int) -> Subscription:
    return Subscription(id=1, user_id=42, plan_id=1, server_id=1, title="1M", config="", sub_link="",
                        traffic_gb=50, started_at=now_ts(), expires_at=expires_at, status="active", warned=0,
                        created_at=now_ts(), meta=result_meta)


@pytest.fixture
async def start_server() -> AsyncIterator[Any]:
    servers: list[TestServer] = []

    async def _start(app: Any) -> str:
        test_server = TestServer(app)
        await test_server.start_server()
        servers.append(test_server)
        return str(test_server.make_url("")).rstrip("/")

    yield _start
    for test_server in servers:
        await test_server.close()


# ----------------------------------------------------------------------
# 3x-ui v3
# ----------------------------------------------------------------------
async def test_xui_v3_full_lifecycle_with_csrf_login(start_server: Any) -> None:
    state: dict[str, Any] = {"base": "/secretpath"}
    url = await start_server(xui_v3_app(state))
    # آدرسی که ادمین از مرورگر کپی کرده (با /panel/inbounds)
    panel = XUIPanel(server(url + "/secretpath/panel/inbounds", sub_url="https://sub.example.com:2096/sub"))

    report = await panel.test()
    assert "API جدید نسخه ۳" in report and "#1" in report

    expires = now_plus(30)
    result = await panel.create_client(remark="u42_abcde", expires_at=expires, traffic_gb=50, plan=PLAN, user_id=42)
    assert result.meta["api"] == "v3" and result.meta["email"] == "u42_abcde"
    record = state["clients"]["u42_abcde"]["record"]
    assert record["totalGB"] == 50 * 1024**3 and record["expiryTime"] == expires * 1000
    assert record["flow"] == "xtls-rprx-vision"  # اینباند Reality بدون کلاینت قبلی
    assert result.links and result.links[0].startswith("vless://")
    assert result.sub_link == f"https://sub.example.com:2096/sub/{result.meta['sub_id']}"

    sub = sub_from(result.meta, expires)
    new_expiry = expires + 30 * 86400
    assert await panel.renew_client(sub, expires_at=new_expiry, traffic_gb=100, plan=PLAN) is None
    update = state["updates"][-1]
    assert update["id"] == record["uuid"]  # uuid (نه شماره ردیف) ارسال شده
    assert update["expiryTime"] == new_expiry * 1000 and update["totalGB"] == 100 * 1024**3
    assert state["resets"] == ["u42_abcde"]

    usage = await panel.get_usage(sub)
    assert usage is not None and usage.used_bytes == 3 * 1024**3 and usage.expires_at == new_expiry

    await panel.set_expiry(sub, new_expiry + 86400)
    assert state["clients"]["u42_abcde"]["record"]["totalGB"] == 100 * 1024**3  # حجم دست نخورده

    await panel.delete_client(sub)
    assert "u42_abcde" not in state["clients"]


async def test_xui_v3_recreates_deleted_client_on_renew(start_server: Any) -> None:
    state: dict[str, Any] = {}
    url = await start_server(xui_v3_app(state))
    panel = XUIPanel(server(url))
    result = await panel.create_client(remark="u42_aaaaa", expires_at=now_plus(1), traffic_gb=10, plan=PLAN, user_id=42)
    state["clients"].clear()  # ادمین کاربر را از پنل حذف کرده است
    renewed = await panel.renew_client(sub_from(result.meta, now_plus(1)), expires_at=now_plus(31), traffic_gb=10, plan=PLAN)
    assert renewed is not None and renewed.links and renewed.meta["email"] != "u42_aaaaa"
    assert len(state["clients"]) == 1


async def test_xui_v3_api_token_and_address_override(start_server: Any) -> None:
    state: dict[str, Any] = {}
    url = await start_server(xui_v3_app(state))
    panel = XUIPanel(server(url, api_user="", api_pass="", api_token="api-token-xyz", address="vpn.example.com"))
    result = await panel.create_client(remark="u7_zzzzz", expires_at=now_plus(30), traffic_gb=0, plan=PLAN, user_id=7)
    assert "@vpn.example.com:443" in result.links[0]
    assert state["sessions"] == set()  # بدون لاگین (فقط توکن)


async def test_xui_login_errors_are_readable(start_server: Any) -> None:
    url = await start_server(xui_v3_app({}))
    with pytest.raises(PanelError, match="نام کاربری و رمز"):
        await XUIPanel(server(url, api_pass="wrong")).test()
    with pytest.raises(PanelError, match="اتصال به پنل برقرار نشد"):
        await XUIPanel(server("http://127.0.0.1:1")).test()


async def test_xui_v3_builds_links_when_panel_returns_none(start_server: Any) -> None:
    state: dict[str, Any] = {"links_empty": True}
    url = await start_server(xui_v3_app(state))
    result = await XUIPanel(server(url)).create_client(
        remark="u8_links", expires_at=now_plus(30), traffic_gb=10, plan=PLAN, user_id=8
    )
    record = state["clients"]["u8_links"]["record"]
    assert len(result.links) == 1 and result.links[0].startswith(f"vless://{record['uuid']}@127.0.0.1:443")
    assert "pbk=PUBKEY123" in result.links[0] and "flow=xtls-rprx-vision" in result.links[0]


# ----------------------------------------------------------------------
# 3x-ui v2 (API قدیمی)
# ----------------------------------------------------------------------
async def test_xui_v2_partial_failure_is_cleaned_up(start_server: Any) -> None:
    state: dict[str, Any] = {"fail_inbound": 2}
    url = await start_server(xui_v2_app(state))
    with pytest.raises(PanelError, match="xray config error"):
        await XUIPanel(server(url, inbound_ids="1,2")).create_client(
            remark="u9_part", expires_at=now_plus(30), traffic_gb=1, plan=PLAN, user_id=9
        )
    # کلاینت ساخته‌شده روی اینباند ۱ حذف شده است
    assert json.loads(state["inbounds"][1]["settings"])["clients"] == []


async def test_xui_v2_multi_inbound_links_and_renew(start_server: Any) -> None:
    state: dict[str, Any] = {"empty_add_response": True}  # رفتار نسخه 2.6.0
    url = await start_server(xui_v2_app(state))
    panel = XUIPanel(server(url, inbound_ids="1,2"))

    report = await panel.test()
    assert "API نسخه ۲" in report

    expires = now_plus(30)
    result = await panel.create_client(remark="u9_qwert", expires_at=expires, traffic_gb=20, plan=PLAN, user_id=9)
    assert result.meta["api"] == "v2" and len(result.meta["clients"]) == 2
    emails = {c["email"] for c in result.meta["clients"]}
    assert emails == {"u9_qwert-1", "u9_qwert-2"}  # ایمیل یکتا برای هر اینباند

    vless = next(link for link in result.links if link.startswith("vless://"))
    query = parse_qs(urlsplit(vless).query)
    assert query["security"] == ["reality"] and query["pbk"] == ["PUBKEY123"] and query["sid"] == ["ab12cd"]
    assert query["flow"] == ["xtls-rprx-vision"] and query["sni"] == ["www.speedtest.net"]
    assert urlsplit(vless).hostname == "127.0.0.1"

    vmess = next(link for link in result.links if link.startswith("vmess://"))
    data = json.loads(base64.b64decode(vmess[8:]))
    assert data["net"] == "ws" and data["path"] == "/ws" and data["host"] == "cdn.example.com" and data["tls"] == "tls"

    sub = sub_from(result.meta, expires)
    new_expiry = expires + 86400 * 30
    await panel.renew_client(sub, expires_at=new_expiry, traffic_gb=40, plan=PLAN)
    assert sorted(state["resets"]) == ["u9_qwert-1", "u9_qwert-2"]
    assert state["traffics"]["u9_qwert-1"]["expiryTime"] == new_expiry * 1000
    assert state["traffics"]["u9_qwert-2"]["total"] == 40 * 1024**3

    usage = await panel.get_usage(sub)
    assert usage is not None and usage.total_bytes == 40 * 1024**3

    await panel.delete_client(sub)
    assert all(json.loads(i["settings"])["clients"] == [] for i in state["inbounds"].values())


async def test_xui_v2_rejects_unsupported_protocol(start_server: Any) -> None:
    state: dict[str, Any] = {}
    app = xui_v2_app(state)
    state["inbounds"][1]["protocol"] = "wireguard"
    url = await start_server(app)
    with pytest.raises(PanelError, match="پشتیبانی نمی‌شود"):
        await XUIPanel(server(url)).create_client(remark="x", expires_at=now_plus(1), traffic_gb=1, plan=PLAN, user_id=1)


# ----------------------------------------------------------------------
# Marzban / PasarGuard
# ----------------------------------------------------------------------
async def test_marzban_lifecycle(start_server: Any) -> None:
    state: dict[str, Any] = {}
    url = await start_server(marzban_app(state))
    panel = MarzbanPanel(server(url + "/dashboard/", kind="marzban", inbound_ids=""))
    assert "Marzban" in await panel.test()

    expires = now_plus(30)
    result = await panel.create_client(remark="u5_abcde", expires_at=expires, traffic_gb=25, plan=PLAN, user_id=5)
    body = state["last_create"]
    assert set(body["proxies"]) == {"vless", "vmess"} and body["data_limit"] == 25 * 1024**3 and body["expire"] == expires
    assert result.links and result.sub_link.startswith(url + "/sub/")

    sub = sub_from(result.meta, expires)
    await panel.renew_client(sub, expires_at=expires + 86400, traffic_gb=50, plan=PLAN)
    assert state["users"]["u5_abcde"]["expire"] == expires + 86400 and state["resets"] == ["u5_abcde"]
    usage = await panel.get_usage(sub)
    assert usage is not None and usage.used_bytes == 3 * 1024**3

    state["users"].clear()
    recreated = await panel.renew_client(sub, expires_at=expires + 86400, traffic_gb=50, plan=PLAN)
    assert recreated is not None and recreated.meta["username"] != "u5_abcde"


async def test_marzban_inbound_tag_filter(start_server: Any) -> None:
    state: dict[str, Any] = {}
    url = await start_server(marzban_app(state))
    panel = MarzbanPanel(server(url, kind="marzban", inbound_ids="VLESS TCP REALITY"))
    await panel.create_client(remark="u1_aaaaa", expires_at=now_plus(1), traffic_gb=1, plan=PLAN, user_id=1)
    assert state["last_create"]["proxies"] == {"vless": {}}
    assert state["last_create"]["inbounds"] == {"vless": ["VLESS TCP REALITY"]}


async def test_pasarguard_uses_groups_and_subscription_links(start_server: Any) -> None:
    state: dict[str, Any] = {}
    url = await start_server(marzban_app(state, pasarguard=True))
    panel = MarzbanPanel(server(url, kind="marzban", inbound_ids=""))
    assert "PasarGuard" in await panel.test()

    expires = now_plus(30)
    result = await panel.create_client(remark="u3_abcde", expires_at=expires, traffic_gb=0, plan=PLAN, user_id=3)
    assert state["last_create"]["group_ids"] == [1]  # فقط گروه‌های فعال
    assert result.meta["flavor"] == "pasarguard"
    assert result.links and result.links[0].startswith("vless://")  # از لینک ساب استخراج شد

    usage = await panel.get_usage(sub_from(result.meta, expires))
    assert usage is not None and usage.expires_at == expires  # تاریخ ISO تبدیل شد


# ----------------------------------------------------------------------
# Provisioner + پنل واقعی (ساختگی)
# ----------------------------------------------------------------------
async def test_provisioner_with_xui_panel(start_server: Any, tmp_path: Any) -> None:
    state: dict[str, Any] = {}
    url = await start_server(xui_v3_app(state))
    config = make_config(tmp_path)
    db = Database(config.db_path)
    await db.connect()
    try:
        await db.users.upsert(42, "user42", "User 42")
        server_id = await db.servers.create(name="DE", kind="xui", api_url=url, api_user="admin", api_pass="secret",
                                            inbound_ids="1")
        plan_id = await db.plans.create(server_id=server_id, name="1M", days=30, traffic_gb=50, price=100)
        plan = await db.plans.get(plan_id)
        provisioner = Provisioner(db, config)
        sub = await provisioner.create_subscription(42, plan)
        assert sub.config.startswith("vless://") and sub.meta["api"] == "v3"

        extended = await provisioner.add_days(sub, 5)
        assert extended.expires_at == sub.expires_at + 5 * 86400
        email = sub.meta["email"]
        assert state["clients"][email]["record"]["expiryTime"] == extended.expires_at * 1000

        renewed = await provisioner.renew_subscription(extended, plan)
        assert renewed.expires_at == extended.expires_at + 30 * 86400

        warning = await provisioner.cancel_subscription(renewed)
        assert warning is None and email not in state["clients"]
        assert (await db.subscriptions.get(sub.id)).status == "disabled"
    finally:
        await db.close()
