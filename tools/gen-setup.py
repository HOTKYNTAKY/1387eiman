#!/usr/bin/env python3
"""
ژنراتور vortexnet-setup.sh — هر ۱۸ فایل سورس فروشگاه را به‌صورت base64(gzip)
داخل یک اسکریپت نصب خودکفا جاسازی می‌کند.

خروجی: vortexnet-setup.sh در ریشهٔ ریپو.
اجرا: python3 tools/gen-setup.py
تست خشک خروجی: NORKHIZ_ONLY_FILES=1 VORTEXNET_DIR=/tmp/test bash vortexnet-setup.sh
"""
import base64
import gzip
import hashlib
import os
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "vortexnet-setup.sh")

FILES = [
    'index.html',
    'src/main.js',
    'src/style.css',
    'server/server.mjs',
    'server/admin.html',
    'server/.env.example',
    'deploy/nginx-site.conf',
    'deploy/norkhiz-api.service',
    'install.sh',
    'update.sh',
    'vite.config.js',
    'src/three/scene.js',
    'public/images/work-nebula.jpg',
    'public/robots.txt',
    'package.json',
    'package-lock.json',
    'public/favicon.svg',
    '.gitignore',
]

HEADER = '#!/usr/bin/env bash\n# ════════════════════════════════════════════════════════════════════\n#  VORTEXNET / ورتکس\u200cنت — FRESH INSTALL / UPDATE (self-contained, one command)\n#\n#  چه کار می\u200cکند:\n#   • حساب کاربری مشتری (نام کاربری یکتا + رمز)\n#   • پرداخت راحت: کارت\u200cبه\u200cکارت + فقط ۴ رقم آخر کارت\n#   • «سفارشات» و «سرویس من» زنده (حجم/روز باقی\u200cمانده از پاسارگارد)\n#   • چت پشتیبانی داخل سایت ↔ پنل ادمین\n#   • ساخت خودکار کانفیگ ۳۰روزه در پاسارگارد بعد از تأیید پرداخت\n#   • رفع به\u200cهم\u200cریختگی شماره کارت و ایرادهای موبایل\n#\n#  رمز پنل و کلید API پاسارگارد در این فایل نیست؛ روی سرور خودت\n#  در server/data ذخیره شده\u200cاند و دست نخورده می\u200cمانند.\n#\n#  Usage (on YOUR server):\n#    [VORTEXNET_DIR=/opt/vortexnet] [API_PORT=9273] [DOMAIN=example.com] \\\n#    [SSL_EMAIL=you@mail.com|none] bash vortexnet-setup.sh\n#\n#    Moving servers with existing users/orders/settings:\n#      VORTEXNET_DATA_ARCHIVE=/root/vortexnet-data.tar.gz ... bash vortexnet-setup.sh\n#\n#    NORKHIZ_ONLY_FILES=1 VORTEXNET_DIR=/tmp/test bash vortexnet-setup.sh\n#      → dry run: only extracts files (used by the author to verify).\n# ════════════════════════════════════════════════════════════════════\nset -euo pipefail\nexport DEBIAN_FRONTEND=noninteractive\n\nc_reset=$\'\\033[0m\'; c_gold=$\'\\033[38;5;179m\'; c_cyan=$\'\\033[38;5;81m\'; c_red=$\'\\033[38;5;203m\'; c_dim=$\'\\033[2m\'\nlog()  { printf "%s▸%s %s\\n" "$c_cyan" "$c_reset" "$*"; }\nok()   { printf "%s✓%s %s\\n" "$c_gold" "$c_reset" "$*"; }\nwarn() { printf "%s!%s %s\\n" "$c_gold" "$c_reset" "$*"; }\ndie()  { printf "%s✗ %s%s\\n" "$c_red" "$*" "$c_reset" >&2; exit 1; }\n\nSUDO=""; [[ "${EUID:-$(id -u)}" -ne 0 ]] && SUDO="sudo"\nAPI_PORT="${API_PORT:-9273}"\nDOMAIN="${DOMAIN:-}"\nSSL_EMAIL="${SSL_EMAIL:-}"\n\n# ── locate the existing site clone ──────────────────────────────────\nfind_dir() {\n  if [[ -n "${VORTEXNET_DIR:-}" ]]; then echo "$VORTEXNET_DIR"; return; fi\n  if [[ -n "${NORKHIZ_DIR:-}" ]]; then echo "$NORKHIZ_DIR"; return; fi\n  local cand\n  for cand in "$PWD" /root/1387eiman/1387eiman /root/1387eiman "$HOME/1387eiman/1387eiman" "$HOME/1387eiman" /opt/1387eiman; do\n    if [[ -f "$cand/package.json" && -f "$cand/vite.config.js" && -f "$cand/install.sh" ]]; then echo "$cand"; return; fi\n  done\n}\nAPP_DIR="$(find_dir || true)"\nif [[ -z "${APP_DIR:-}" ]]; then\n  APP_DIR="$(find /root "$HOME" /opt /srv -maxdepth 4 -name package.json -path \'*1387eiman*\' 2>/dev/null | head -1 | xargs -r dirname || true)"\nfi\nif [[ -z "${APP_DIR:-}" ]]; then\n  APP_DIR="${VORTEXNET_DIR:-/opt/vortexnet}"\n  log "No existing site found — fresh install into ${APP_DIR}"\nfi\nmkdir -p "$APP_DIR"\ncd "$APP_DIR"\nok "Site directory: $APP_DIR"\n\n# ── decode + verify one embedded file ───────────────────────────────\nwrite_file() {  # write_file <relative-path> <sha256> < <b64-gzip on stdin>\n  local rel="$1" sum="$2" tmp\n  tmp="$(mktemp)"\n  base64 -d | gzip -dc > "$tmp"\n  if command -v sha256sum >/dev/null 2>&1; then\n    echo "${sum}  ${tmp}" | sha256sum -c - >/dev/null 2>&1 \\\n      || { rm -f "$tmp"; die "Checksum mismatch for ${rel} — the download was corrupted. Download again and retry."; }\n  fi\n  mkdir -p "$(dirname "$rel")"\n  mv "$tmp" "$rel"\n  ok "written: $rel"\n}\n\nlog "Extracting VORTEXNET shop files…"\n\n'

FOOTER = '# ── dry run? ────────────────────────────────────────────────────────\nif [[ "${NORKHIZ_ONLY_FILES:-0}" == "1" ]]; then\n  ok "Files extracted (NORKHIZ_ONLY_FILES=1 — install skipped)."\n  exit 0\nfi\n\n# ── optional: import runtime data when moving to a new server ───────\n# Create the archive on the OLD server from its app directory:\n#   tar -czf /root/vortexnet-data.tar.gz server/data server/.env\n# Copy it directly to the NEW server (never through chat/public links),\n# then run this setup with VORTEXNET_DATA_ARCHIVE=/root/vortexnet-data.tar.gz.\nDATA_ARCHIVE="${VORTEXNET_DATA_ARCHIVE:-${NORKHIZ_DATA_ARCHIVE:-}}"\nif [[ -n "$DATA_ARCHIVE" ]]; then\n  [[ -f "$DATA_ARCHIVE" ]] || die "Data archive not found: $DATA_ARCHIVE"\n  log "Importing existing shop data from ${DATA_ARCHIVE}…"\n  mkdir -p server/data\n  if ! tar -xzf "$DATA_ARCHIVE" -C "$APP_DIR" --no-same-owner --no-same-permissions server/data server/.env 2>/dev/null; then\n    tar -xzf "$DATA_ARCHIVE" -C "$APP_DIR" --no-same-owner --no-same-permissions server/data \\\n      || die "Could not import server/data from: $DATA_ARCHIVE"\n  fi\n  chmod 700 server/data 2>/dev/null || true\n  find server/data -type f -exec chmod 600 {} + 2>/dev/null || true\n  [[ -f server/.env ]] && chmod 600 server/.env 2>/dev/null || true\n  ok "Existing shop data imported (users, orders, chats, sessions and settings preserved)"\nfi\n\n# ── make sure the frontend deps are declared ────────────────────────\nHAVE_NODE=0; command -v node >/dev/null 2>&1 && HAVE_NODE=1\n[[ "$HAVE_NODE" == "1" ]] || log "Node.js not found yet — the installer will set it up."\nif [[ "$HAVE_NODE" == "1" ]] && ! grep -q \'"@fontsource/vazirmatn"\' package.json; then\n  log "Adding local Persian fonts (Vazirmatn, Space Grotesk)…"\n  npm i -S @fontsource/vazirmatn @fontsource/space-grotesk\nfi\nif [[ "$HAVE_NODE" == "1" ]] && ! grep -q \'"qrcode-generator"\' package.json; then\n  log "Adding QR library for subscription links…"\n  npm i -S qrcode-generator@1.4.4\nfi\n\n# ── don\'t let env files leak dev settings into the production build ─\nfor f in .env .env.local; do\n  if [[ -f "$f" ]] && grep -Eq \'^(VITE_BASE|BASE_PATH)=\' "$f"; then\n    sed -i.bak -E \'/^(VITE_BASE|BASE_PATH)=/d\' "$f"\n    warn "Removed VITE_BASE/BASE_PATH from $f (production must use /). Backup: $f.bak"\n  fi\ndone\nunset VITE_BASE BASE_PATH\n\nchmod +x install.sh update.sh\n\n# ── run the full installer (build → /var/www/aether → Nginx /api proxy\n#    → shop API systemd service → firewall → health check) ──────────\nARGS=()\n[[ -n "$DOMAIN" ]] && ARGS+=(--domain "$DOMAIN")\n[[ -n "$SSL_EMAIL" ]] && ARGS+=(--ssl "$SSL_EMAIL")\nlog "Running installer (این مرحله ممکن است ۱ تا ۳ دقیقه طول بکشد)…"\nAPI_PORT="$API_PORT" bash install.sh "${ARGS[@]}"\n\nPUBLIC_IP="$(curl -fsS --max-time 4 https://api.ipify.org 2>/dev/null || echo \'<SERVER-IP>\')"\nDISPLAY_DOMAIN="$DOMAIN"\nif [[ -z "$DISPLAY_DOMAIN" && -f server/.env ]]; then\n  DISPLAY_DOMAIN="$(grep -E \'^SITE_DOMAIN=\' server/.env | tail -1 | cut -d= -f2 | tr -d \' \\"\'\\\'\'\\r\' || true)"\nfi\nif [[ -n "$DISPLAY_DOMAIN" && -d "/etc/letsencrypt/live/${DISPLAY_DOMAIN}" ]]; then\n  SITE_URL="https://${DISPLAY_DOMAIN}/"\nelif [[ -n "$DISPLAY_DOMAIN" ]]; then\n  SITE_URL="http://${DISPLAY_DOMAIN}/"\nelse\n  SITE_URL="http://${PUBLIC_IP}/"\nfi\necho\nok "ورتکس\u200cنت نصب/به\u200cروز شد 🎉 (حساب کاربری + سفارشات + سرویس من + چت پشتیبانی)"\necho "${c_dim}سایت:        ${SITE_URL}${c_reset}"\necho "${c_dim}پنل مدیریت:  http://${PUBLIC_IP}:${API_PORT}  — بخش «💬 چت\u200cها» برای گفت\u200cوگو با مشتری${c_reset}"\n'


def main():
    parts = [HEADER]
    raw_total = 0
    for rel in FILES:
        with open(os.path.join(ROOT, rel), "rb") as fh:
            raw = fh.read()
        raw_total += len(raw)
        sha = hashlib.sha256(raw).hexdigest()
        gz = gzip.compress(raw, 9, mtime=0)
        b64 = base64.b64encode(gz).decode("ascii")
        delim = "NK4EOF_" + hashlib.sha256(gz).hexdigest()[:10]
        parts.append(f'write_file "{rel}" "{sha}" <<\'{delim}\'\n')
        parts.append("\n".join(textwrap.wrap(b64, 76)) + "\n")
        parts.append(delim + "\n\n")
    parts.append(FOOTER)
    data = "".join(parts)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(data)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    print(f"files={len(FILES)} raw={raw_total} setup_bytes={len(data.encode('utf-8'))} sha256={digest}")


if __name__ == "__main__":
    main()
