"""
سرورهای ساختگی پنل‌ها برای تست (بر اساس سورس و مستندات رسمی هر پنل)

- 3x-ui نسخه ۳ : ورود با CSRF، API کلاینت‌ها، توکن Bearer، پاسخ 404 برای درخواست بدون احراز هویت
- 3x-ui نسخه ۲ : ورود ساده، API قدیمی inbounds/addClient (settings به صورت رشته JSON)
- Marzban       : /api/admin/token، proxies/inbounds
- PasarGuard    : group_ids، expire به صورت تاریخ ISO، بدون فیلد links
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

REALITY_STREAM = {
    "network": "tcp",
    "security": "reality",
    "tcpSettings": {"header": {"type": "none"}},
    "realitySettings": {
        "serverNames": ["www.speedtest.net"],
        "shortIds": ["ab12cd"],
        "settings": {"publicKey": "PUBKEY123", "fingerprint": "chrome", "spiderX": "/"},
    },
}
WS_TLS_STREAM = {
    "network": "ws",
    "security": "tls",
    "wsSettings": {"path": "/ws", "headers": {"Host": "cdn.example.com"}},
    "tlsSettings": {"serverName": "cdn.example.com", "alpn": ["h2", "http/1.1"], "settings": {"fingerprint": "chrome"}},
}


def _ok(obj: Any = None, msg: str = "") -> web.Response:
    return web.json_response({"success": True, "msg": msg, "obj": obj})


def _fail(msg: str) -> web.Response:
    return web.json_response({"success": False, "msg": msg, "obj": None})


# ======================================================================
# 3x-ui v3
# ======================================================================
def xui_v3_app(state: dict[str, Any]) -> web.Application:
    state.setdefault("csrf", "csrf-" + secrets.token_hex(4))
    state.setdefault("sessions", set())
    state.setdefault("clients", {})
    state.setdefault("token", "api-token-xyz")
    state.setdefault("inbounds", {1: {"id": 1, "remark": "reality", "protocol": "vless", "port": 443,
                                      "settings": {"clients": [], "decryption": "none"}, "streamSettings": REALITY_STREAM}})
    base = state.get("base", "")

    def bearer(request: web.Request) -> bool:
        return request.headers.get("Authorization") == f"Bearer {state['token']}"

    @web.middleware
    async def auth(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.path.startswith(f"{base}/panel/api"):
            if not (bearer(request) or request.cookies.get("3x-ui") in state["sessions"]):
                return web.Response(status=404)
            if request.method == "POST" and not bearer(request) and request.headers.get("X-CSRF-Token") != state["csrf"]:
                return web.json_response({"success": False, "msg": "invalid csrf"}, status=403)
        return await handler(request)

    async def csrf_token(request: web.Request) -> web.Response:
        response = _ok(state["csrf"])
        response.set_cookie("3x-ui", request.cookies.get("3x-ui") or "sess-" + secrets.token_hex(4))
        return response

    async def login(request: web.Request) -> web.Response:
        if request.headers.get("X-CSRF-Token") != state["csrf"]:
            return web.json_response({"success": False, "msg": "invalid csrf"}, status=403)
        form = await request.post()
        if form.get("username") == "admin" and form.get("password") == "secret":
            state["sessions"].add(request.cookies.get("3x-ui"))
            return _ok(msg="Login Successfully")
        return _fail("Invalid username or password")

    async def list_paged(request: web.Request) -> web.Response:
        return _ok({"items": [], "total": len(state["clients"])})

    async def inbound_list(request: web.Request) -> web.Response:
        return _ok(list(state["inbounds"].values()))

    async def inbound_get(request: web.Request) -> web.Response:
        inbound = state["inbounds"].get(int(request.match_info["id"]))
        return _ok(inbound) if inbound else _fail("record not found")

    async def options(request: web.Request) -> web.Response:
        return _ok([{"id": i["id"], "remark": i["remark"], "protocol": i["protocol"], "port": i["port"]}
                    for i in state["inbounds"].values()])

    async def add(request: web.Request) -> web.Response:
        body = await request.json()
        client, inbound_ids = body["client"], body["inboundIds"]
        if client["email"] in state["clients"]:
            return _fail("email already exists")
        if not inbound_ids or any(i not in state["inbounds"] for i in inbound_ids):
            return _fail("inbound not found")
        record = {
            "id": len(state["clients"]) + 1, "email": client["email"], "subId": client.get("subId", ""),
            "uuid": client.get("id") or secrets.token_hex(16), "password": "", "flow": client.get("flow", ""),
            "totalGB": client["totalGB"], "expiryTime": client["expiryTime"], "enable": client["enable"],
            "limitIp": client.get("limitIp", 0), "tgId": 0, "comment": client.get("comment", ""),
            "reverse": "", "allowedIPs": "", "up": 0, "down": 0,
        }
        state["clients"][client["email"]] = {"record": record, "inboundIds": inbound_ids}
        return _ok(msg="Client added")

    async def get_client(request: web.Request) -> web.Response:
        item = state["clients"].get(request.match_info["email"])
        if not item:
            return _fail("record not found")
        return _ok({"client": item["record"], "inboundIds": item["inboundIds"], "usedTraffic": 0})

    async def update(request: web.Request) -> web.Response:
        item = state["clients"].get(request.match_info["email"])
        if not item:
            return _fail("record not found")
        body = await request.json()
        if not isinstance(body.get("id", ""), str):  # مثل Go: id باید رشته (uuid) باشد
            return _fail("json: cannot unmarshal number into Go struct field Client.id of type string")
        state.setdefault("updates", []).append(body)
        item["record"].update({k: body[k] for k in ("totalGB", "expiryTime", "enable", "flow") if k in body})
        return _ok(msg="Client updated")

    async def reset(request: web.Request) -> web.Response:
        item = state["clients"].get(request.match_info["email"])
        if not item:
            return _fail("record not found")
        item["record"]["up"] = item["record"]["down"] = 0
        state.setdefault("resets", []).append(request.match_info["email"])
        return _ok()

    async def traffic(request: web.Request) -> web.Response:
        item = state["clients"].get(request.match_info["email"])
        if not item:
            return _fail("record not found")
        r = item["record"]
        return _ok({"email": r["email"], "up": 1024**3, "down": 2 * 1024**3, "total": r["totalGB"],
                    "expiryTime": r["expiryTime"], "enable": r["enable"]})

    async def links(request: web.Request) -> web.Response:
        item = state["clients"].get(request.match_info["email"])
        if not item:
            return _fail("record not found")
        if state.get("links_empty"):
            return _ok([])
        host = request.host.split(":")[0]
        r = item["record"]
        return _ok([f"vless://{r['uuid']}@{host}:443?type=tcp&security=reality&pbk=PUBKEY123#{r['email']}"])

    async def delete(request: web.Request) -> web.Response:
        state["clients"].pop(request.match_info["email"], None)
        return _ok()

    app = web.Application(middlewares=[auth])
    app.router.add_get(f"{base}/csrf-token", csrf_token)
    app.router.add_post(f"{base}/login", login)
    api = f"{base}/panel/api"
    app.router.add_get(f"{api}/clients/list/paged", list_paged)
    app.router.add_get(f"{api}/inbounds/list", inbound_list)
    app.router.add_get(f"{api}/inbounds/get/{{id}}", inbound_get)
    app.router.add_get(f"{api}/inbounds/options", options)
    app.router.add_post(f"{api}/clients/add", add)
    app.router.add_get(f"{api}/clients/get/{{email}}", get_client)
    app.router.add_post(f"{api}/clients/update/{{email}}", update)
    app.router.add_post(f"{api}/clients/resetTraffic/{{email}}", reset)
    app.router.add_get(f"{api}/clients/traffic/{{email}}", traffic)
    app.router.add_get(f"{api}/clients/links/{{email}}", links)
    app.router.add_post(f"{api}/clients/del/{{email}}", delete)
    return app


# ======================================================================
# 3x-ui v2 (API قدیمی)
# ======================================================================
def xui_v2_app(state: dict[str, Any]) -> web.Application:
    state.setdefault("sessions", set())
    state.setdefault("traffics", {})
    state.setdefault("inbounds", {
        1: {"id": 1, "remark": "reality", "protocol": "vless", "port": 443, "listen": "",
            "settings": json.dumps({"clients": [], "decryption": "none", "encryption": "none"}),
            "streamSettings": json.dumps(REALITY_STREAM)},
        2: {"id": 2, "remark": "ws", "protocol": "vmess", "port": 8443, "listen": "",
            "settings": json.dumps({"clients": []}), "streamSettings": json.dumps(WS_TLS_STREAM)},
    })

    @web.middleware
    async def auth(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.path.startswith("/panel/api") and request.cookies.get("3x-ui") not in state["sessions"]:
            return web.Response(status=404)
        return await handler(request)

    async def login(request: web.Request) -> web.Response:
        form = await request.post()
        if form.get("username") == "admin" and form.get("password") == "secret":
            sid = "sess-" + secrets.token_hex(4)
            state["sessions"].add(sid)
            response = _ok(msg="Login Successfully")
            response.set_cookie("3x-ui", sid)
            return response
        return _fail("Invalid username or password")

    def clients_of(inbound: dict[str, Any]) -> list[dict[str, Any]]:
        return json.loads(inbound["settings"])["clients"]

    def save_clients(inbound: dict[str, Any], clients: list[dict[str, Any]]) -> None:
        settings = json.loads(inbound["settings"])
        settings["clients"] = clients
        inbound["settings"] = json.dumps(settings)

    async def inbound_list(request: web.Request) -> web.Response:
        return _ok(list(state["inbounds"].values()))

    async def inbound_get(request: web.Request) -> web.Response:
        inbound = state["inbounds"].get(int(request.match_info["id"]))
        return _ok(inbound) if inbound else _fail("record not found")

    async def add_client(request: web.Request) -> web.Response:
        body = await request.json()
        if int(body["id"]) == state.get("fail_inbound"):
            return _fail("xray config error")
        inbound = state["inbounds"][int(body["id"])]
        new_clients = json.loads(body["settings"])["clients"]
        emails = {t for t in state["traffics"]}
        for client in new_clients:
            if client["email"] in emails:
                return _fail("Duplicate email")
            state["traffics"][client["email"]] = {"email": client["email"], "up": 5, "down": 10,
                                                  "total": client["totalGB"], "expiryTime": client["expiryTime"],
                                                  "enable": True, "inboundId": inbound["id"]}
        save_clients(inbound, clients_of(inbound) + new_clients)
        return web.Response(status=200) if state.get("empty_add_response") else _ok()

    async def update_client(request: web.Request) -> web.Response:
        body = await request.json()
        inbound = state["inbounds"][int(body["id"])]
        new = json.loads(body["settings"])["clients"][0]
        key = request.match_info["client_id"]
        clients = clients_of(inbound)
        for index, client in enumerate(clients):
            if client.get("id") == key or client.get("password") == key:
                clients[index] = new
                save_clients(inbound, clients)
                state["traffics"][new["email"]].update(total=new["totalGB"], expiryTime=new["expiryTime"], enable=new["enable"])
                return _ok()
        return _fail("client not found")

    async def reset(request: web.Request) -> web.Response:
        traffic = state["traffics"].get(request.match_info["email"])
        if traffic:
            traffic["up"] = traffic["down"] = 0
        state.setdefault("resets", []).append(request.match_info["email"])
        return _ok()

    async def traffics(request: web.Request) -> web.Response:
        return _ok(state["traffics"].get(request.match_info["email"]))

    async def delete(request: web.Request) -> web.Response:
        inbound = state["inbounds"][int(request.match_info["id"])]
        key = request.match_info["client_id"]
        clients = [c for c in clients_of(inbound) if c.get("id") != key and c.get("password") != key]
        save_clients(inbound, clients)
        return _ok()

    app = web.Application(middlewares=[auth])
    app.router.add_post("/login", login)
    app.router.add_get("/panel/api/inbounds/list", inbound_list)
    app.router.add_get("/panel/api/inbounds/get/{id}", inbound_get)
    app.router.add_post("/panel/api/inbounds/addClient", add_client)
    app.router.add_post("/panel/api/inbounds/updateClient/{client_id}", update_client)
    app.router.add_post("/panel/api/inbounds/{id}/resetClientTraffic/{email}", reset)
    app.router.add_get("/panel/api/inbounds/getClientTraffics/{email}", traffics)
    app.router.add_post("/panel/api/inbounds/{id}/delClient/{client_id}", delete)
    return app


# ======================================================================
# Marzban / PasarGuard
# ======================================================================
def marzban_app(state: dict[str, Any], *, pasarguard: bool = False) -> web.Application:
    state.setdefault("users", {})
    token = "jwt-" + secrets.token_hex(4)

    def authed(request: web.Request) -> bool:
        return request.headers.get("Authorization") == f"Bearer {token}"

    async def admin_token(request: web.Request) -> web.Response:
        form = await request.post()
        if form.get("username") == "admin" and form.get("password") == "secret":
            return web.json_response({"access_token": token, "token_type": "bearer"})
        return web.json_response({"detail": "Incorrect username or password"}, status=401)

    async def groups(request: web.Request) -> web.Response:
        if not authed(request):
            return web.json_response({"detail": "Not authenticated"}, status=401)
        return web.json_response({"groups": [
            {"id": 1, "name": "main", "inbound_tags": ["VLESS"], "is_disabled": False, "total_users": 3},
            {"id": 2, "name": "old", "inbound_tags": ["VMESS"], "is_disabled": True, "total_users": 0},
        ], "total": 2})

    async def inbounds(request: web.Request) -> web.Response:
        if not authed(request):
            return web.json_response({"detail": "Not authenticated"}, status=401)
        return web.json_response({"vless": [{"tag": "VLESS TCP REALITY", "protocol": "vless"}],
                                  "vmess": [{"tag": "VMESS WS", "protocol": "vmess"}]})

    def render(user: dict[str, Any]) -> dict[str, Any]:
        data = dict(user)
        if pasarguard:
            data["expire"] = datetime.fromtimestamp(user["expire"], timezone.utc).isoformat() if user["expire"] else None
            data.pop("links", None)
        return data

    async def create(request: web.Request) -> web.Response:
        if not authed(request):
            return web.json_response({"detail": "Not authenticated"}, status=401)
        body = await request.json()
        if body["username"] in state["users"]:
            return web.json_response({"detail": "User already exists"}, status=409)
        if pasarguard:
            if not body.get("group_ids"):
                return web.json_response({"detail": [{"msg": "group list cannot be empty"}]}, status=422)
        elif not body.get("proxies"):
            return web.json_response({"detail": [{"msg": "Each user needs at least one proxy"}]}, status=422)
        sub_token = secrets.token_hex(6)
        user = {
            "username": body["username"], "status": body.get("status", "active"), "expire": body.get("expire"),
            "data_limit": body.get("data_limit"), "used_traffic": 0, "subscription_url": f"/sub/{sub_token}",
            "links": [f"vless://uuid-{body['username']}@panel.example.com:443?security=reality#{body['username']}"],
            "proxies": body.get("proxies"), "inbounds": body.get("inbounds"), "group_ids": body.get("group_ids"),
            "note": body.get("note"),
        }
        state["users"][body["username"]] = user
        state.setdefault("subs", {})[sub_token] = user["links"]
        state["last_create"] = body
        return web.json_response(render(user))

    async def get_user(request: web.Request) -> web.Response:
        user = state["users"].get(request.match_info["username"])
        if not user:
            return web.json_response({"detail": "User not found"}, status=404)
        return web.json_response(render({**user, "used_traffic": 3 * 1024**3}))

    async def modify(request: web.Request) -> web.Response:
        user = state["users"].get(request.match_info["username"])
        if not user:
            return web.json_response({"detail": "User not found"}, status=404)
        user.update(await request.json())
        return web.json_response(render(user))

    async def reset(request: web.Request) -> web.Response:
        user = state["users"].get(request.match_info["username"])
        if not user:
            return web.json_response({"detail": "User not found"}, status=404)
        user["used_traffic"] = 0
        state.setdefault("resets", []).append(user["username"])
        return web.json_response(render(user))

    async def delete(request: web.Request) -> web.Response:
        if state["users"].pop(request.match_info["username"], None) is None:
            return web.json_response({"detail": "User not found"}, status=404)
        return web.json_response({"detail": "User successfully deleted"})

    async def subscription(request: web.Request) -> web.Response:
        links = state.get("subs", {}).get(request.match_info["token"])
        if links is None:
            return web.Response(status=404)
        return web.Response(text=base64.b64encode("\n".join(links).encode()).decode())

    app = web.Application()
    app.router.add_post("/api/admin/token", admin_token)
    if pasarguard:
        app.router.add_get("/api/groups", groups)
    app.router.add_get("/api/inbounds", inbounds)
    app.router.add_post("/api/user", create)
    app.router.add_get("/api/user/{username}", get_user)
    app.router.add_put("/api/user/{username}", modify)
    app.router.add_delete("/api/user/{username}", delete)
    app.router.add_post("/api/user/{username}/reset", reset)
    app.router.add_get("/sub/{token}", subscription)
    return app


def now_plus(days: int) -> int:
    return int(time.time()) + days * 86400
