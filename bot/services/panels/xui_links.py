"""
ساخت لینک کانفیگ (vless:// و vmess:// و trojan://) از تنظیمات اینباند 3x-ui

پنل 3x-ui نسخه ۳ خودش لینک‌ها را از طریق API می‌دهد؛ اما نسخه‌های ۲.x چنین
API‌ای ندارند. این ماژول همان منطق فایل sub/subService.go پنل را پیاده‌سازی
می‌کند تا برای رایج‌ترین حالت‌ها لینک صحیح ساخته شود:
    شبکه: tcp (با/بدون هدر http)، ws، grpc، httpupgrade، xhttp، kcp
    امنیت: none، tls، reality
    externalProxy (پروکسی خارجی / CDN)

برای تنظیمات خیلی خاص (fallback و ...) بهتر است آدرس ساب‌اسکریپشن پنل را در
تنظیمات سرور وارد کنید تا لینک‌ها مستقیماً از خود پنل گرفته شوند.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


def as_dict(value: Any) -> dict[str, Any]:
    """تنظیمات اینباند در نسخه ۲ رشته JSON و در نسخه ۳ آبجکت است؛ هر دو پشتیبانی می‌شود."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _search_host(headers: Any) -> str:
    """پیدا کردن هدر Host (مقدار ممکن است رشته یا لیست باشد)."""
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if key.lower() == "host":
            if isinstance(value, list):
                return str(value[0]) if value else ""
            return str(value)
    return ""


def _search_key(data: Any, key: str) -> Any:
    """جستجوی بازگشتی یک کلید در دیکشنری‌های تو در تو."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _search_key(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _search_key(value, key)
            if found is not None:
                return found
    return None


def _path_host(settings: dict[str, Any]) -> tuple[str, str]:
    path = str(settings.get("path") or "/")
    host = str(settings.get("host") or "") or _search_host(settings.get("headers"))
    return path, host


def network_params(stream: dict[str, Any], network: str) -> dict[str, str]:
    """پارامترهای مربوط به نوع شبکه (transport)."""
    params: dict[str, str] = {}
    if network == "tcp":
        header = as_dict(as_dict(stream.get("tcpSettings")).get("header"))
        if header.get("type") == "http":
            request = as_dict(header.get("request"))
            paths = request.get("path") or ["/"]
            params["path"] = str(paths[0] if isinstance(paths, list) and paths else "/")
            params["host"] = _search_host(request.get("headers"))
            params["headerType"] = "http"
    elif network == "kcp":
        kcp = as_dict(stream.get("kcpSettings"))
        params["headerType"] = str(as_dict(kcp.get("header")).get("type") or "none")
        if kcp.get("seed"):
            params["seed"] = str(kcp["seed"])
    elif network == "ws":
        params["path"], params["host"] = _path_host(as_dict(stream.get("wsSettings")))
    elif network == "grpc":
        grpc = as_dict(stream.get("grpcSettings"))
        params["serviceName"] = str(grpc.get("serviceName") or "")
        params["authority"] = str(grpc.get("authority") or "")
        if grpc.get("multiMode"):
            params["mode"] = "multi"
    elif network == "httpupgrade":
        params["path"], params["host"] = _path_host(as_dict(stream.get("httpupgradeSettings")))
    elif network == "xhttp":
        xhttp = as_dict(stream.get("xhttpSettings"))
        params["path"], params["host"] = _path_host(xhttp)
        params["mode"] = str(xhttp.get("mode") or "")
    return params


def tls_params(stream: dict[str, Any]) -> dict[str, str]:
    tls = as_dict(stream.get("tlsSettings"))
    params = {"security": "tls"}
    alpn = tls.get("alpn") or []
    if isinstance(alpn, list) and alpn:
        params["alpn"] = ",".join(str(a) for a in alpn)
    sni = tls.get("serverName") or _search_key(tls, "serverName")
    if sni:
        params["sni"] = str(sni)
    fingerprint = _search_key(as_dict(tls.get("settings")), "fingerprint")
    if fingerprint:
        params["fp"] = str(fingerprint)
    return params


def reality_params(stream: dict[str, Any]) -> dict[str, str]:
    reality = as_dict(stream.get("realitySettings"))
    inner = as_dict(reality.get("settings"))
    params = {"security": "reality"}
    server_names = reality.get("serverNames") or []
    if isinstance(server_names, list) and server_names:
        params["sni"] = str(server_names[0])
    if inner.get("publicKey"):
        params["pbk"] = str(inner["publicKey"])
    short_ids = reality.get("shortIds") or []
    if isinstance(short_ids, list) and short_ids:
        params["sid"] = str(short_ids[0])
    if inner.get("fingerprint"):
        params["fp"] = str(inner["fingerprint"])
    if inner.get("mldsa65Verify"):
        params["pqv"] = str(inner["mldsa65Verify"])
    params["spx"] = str(inner.get("spiderX") or "/")
    return params


def _url(scheme: str, userinfo: str, host: str, port: int, params: dict[str, str], remark: str) -> str:
    """ساخت لینک استاندارد با پارامترهای مرتب‌شده (همانند خروجی پنل)."""
    clean = {k: v for k, v in params.items() if v not in ("", None) or k in ("security", "type")}
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    query = urlencode(sorted(clean.items()), quote_via=quote, safe="")
    return f"{scheme}://{quote(userinfo, safe='')}@{host_part}:{port}?{query}#{quote(remark, safe='')}"


def _external_proxies(stream: dict[str, Any]) -> list[dict[str, Any]]:
    proxies = stream.get("externalProxy") or []
    return [p for p in proxies if isinstance(p, dict) and p.get("dest")] if isinstance(proxies, list) else []


def _apply_force_tls(params: dict[str, str], base_security: str, force: str) -> dict[str, str]:
    """اعمال تنظیم forceTls پروکسی خارجی روی پارامترها."""
    result = dict(params)
    if force in ("", "same"):
        result["security"] = base_security
        return result
    result["security"] = force
    if force == "none":
        for key in ("alpn", "sni", "fp"):
            result.pop(key, None)
    return result


def build_links(inbound: dict[str, Any], client: dict[str, Any], address: str, remark: str) -> list[str]:
    """
    ساخت لینک(های) یک کلاینت روی یک اینباند.
    اگر اینباند externalProxy داشته باشد برای هر پروکسی یک لینک ساخته می‌شود.
    """
    protocol = str(inbound.get("protocol") or "")
    stream = as_dict(inbound.get("streamSettings"))
    settings = as_dict(inbound.get("settings"))
    port = int(inbound.get("port") or 0)
    network = str(stream.get("network") or "tcp")
    security = str(stream.get("security") or "none")

    if protocol == "vmess":
        return _vmess_links(stream, network, security, client, address, port, remark)

    if protocol == "vless":
        userinfo = str(client.get("id") or "")
        scheme = "vless"
    elif protocol == "trojan":
        userinfo = str(client.get("password") or "")
        scheme = "trojan"
    else:
        return []  # سایر پروتکل‌ها از طریق ساب‌اسکریپشن پنل پشتیبانی می‌شوند

    params: dict[str, str] = {"type": network}
    if protocol == "vless":
        params["encryption"] = str(settings.get("encryption") or "none")
    params.update(network_params(stream, network))

    flow = str(client.get("flow") or "")
    if security == "tls":
        params.update(tls_params(stream))
        if protocol == "vless" and network == "tcp" and flow:
            params["flow"] = flow
    elif security == "reality":
        params.update(reality_params(stream))
        if network == "tcp" and flow:
            params["flow"] = flow
    else:
        params["security"] = "none"

    proxies = _external_proxies(stream)
    if proxies:
        links = []
        for proxy in proxies:
            proxy_params = _apply_force_tls(params, params["security"], str(proxy.get("forceTls") or "same"))
            proxy_remark = f"{remark}-{proxy['remark']}" if proxy.get("remark") else remark
            links.append(
                _url(scheme, userinfo, str(proxy["dest"]), int(proxy.get("port") or port), proxy_params, proxy_remark)
            )
        return links
    return [_url(scheme, userinfo, address, port, params, remark)]


def _vmess_links(
    stream: dict[str, Any],
    network: str,
    security: str,
    client: dict[str, Any],
    address: str,
    port: int,
    remark: str,
) -> list[str]:
    """لینک vmess یک JSON کدشده با base64 است."""
    obj: dict[str, Any] = {
        "v": "2",
        "ps": remark,
        "add": address,
        "port": port,
        "id": str(client.get("id") or ""),
        "scy": str(client.get("security") or "auto"),
        "net": network,
        "type": "none",
        "tls": "none",
    }
    params = network_params(stream, network)
    if network in ("tcp", "kcp"):
        obj["type"] = params.get("headerType", "none")
    elif network == "grpc":
        obj["path"] = params.get("serviceName", "")
        obj["authority"] = params.get("authority", "")
        if params.get("mode") == "multi":
            obj["type"] = "multi"
    if "path" in params and network != "grpc":
        obj["path"] = params["path"]
    if params.get("host"):
        obj["host"] = params["host"]
    if network == "xhttp" and params.get("mode"):
        obj["mode"] = params["mode"]

    if security == "tls":
        obj["tls"] = "tls"
        tls = tls_params(stream)
        for key in ("sni", "alpn", "fp"):
            if tls.get(key):
                obj[key] = tls[key]

    proxies = _external_proxies(stream)
    targets = (
        [(str(p["dest"]), int(p.get("port") or port), str(p.get("forceTls") or "same"), p.get("remark")) for p in proxies]
        if proxies
        else [(address, port, "same", None)]
    )
    links = []
    for dest, dest_port, force, extra in targets:
        item = dict(obj)
        item["add"], item["port"] = dest, dest_port
        if extra:
            item["ps"] = f"{remark}-{extra}"
        if force == "none":
            item["tls"] = "none"
            for key in ("sni", "alpn", "fp"):
                item.pop(key, None)
        elif force == "tls":
            item["tls"] = "tls"
        encoded = base64.b64encode(json.dumps(item, ensure_ascii=False).encode()).decode()
        links.append("vmess://" + encoded)
    return links


def replace_link_host(link: str, new_host: str) -> str:
    """
    جایگزینی آدرس سرور در یک لینک (برای وقتی ربات از طریق آدرس داخلی مثل
    127.0.0.1 به پنل وصل است ولی کاربران باید دامنه عمومی را ببینند).
    """
    if not new_host:
        return link
    if link.startswith("vmess://"):
        try:
            payload = link[len("vmess://") :]
            data = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)).decode())
            data["add"] = new_host
            return "vmess://" + base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
        except (ValueError, TypeError):
            return link
    try:
        parts = urlsplit(link)
        if not parts.hostname or "@" not in parts.netloc:
            return link
        userinfo = parts.netloc.rsplit("@", 1)[0]
        host = f"[{new_host}]" if ":" in new_host else new_host
        netloc = f"{userinfo}@{host}:{parts.port}" if parts.port else f"{userinfo}@{host}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return link
