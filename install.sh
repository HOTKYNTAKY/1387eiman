#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  AETHER® — one-click installer for Linux servers
#  Supported: Ubuntu / Debian (apt) · RHEL / Rocky / Alma (dnf)
#
#  Usage:
#    sudo bash install.sh                          # Nginx on port 80, any host
#    sudo bash install.sh --domain example.com     # + virtual host
#    sudo bash install.sh --domain example.com --ssl you@mail.com   # + HTTPS (Let's Encrypt)
#    bash install.sh --docker [--port 8080]        # Docker Compose instead
#
#  Re-running the script safely redeploys the latest build.
# ════════════════════════════════════════════════════════════════════
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

APP_NAME="aether"
WEB_ROOT="/var/www/${APP_NAME}"
DOMAIN="_"
SSL_EMAIL=""
MODE="nginx"
PORT="8080"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── pretty logging ──────────────────────────────────────────────────
c_reset=$'\033[0m'; c_gold=$'\033[38;5;179m'; c_cyan=$'\033[38;5;81m'; c_red=$'\033[38;5;203m'; c_dim=$'\033[2m'
log()  { printf "%s▸%s %s\n" "$c_cyan" "$c_reset" "$*"; }
ok()   { printf "%s✓%s %s\n" "$c_gold" "$c_reset" "$*"; }
warn() { printf "%s!%s %s\n" "$c_gold" "$c_reset" "$*"; }
die()  { printf "%s✗ %s%s\n" "$c_red" "$*" "$c_reset" >&2; exit 1; }

usage() {
  cat <<EOF
AETHER installer
  sudo bash install.sh [--domain example.com] [--ssl you@mail.com]
  bash install.sh --docker [--port 8080]
Options:
  --domain NAME   Server name for the Nginx vhost (default: _ = any)
  --ssl EMAIL     Obtain a free Let's Encrypt certificate via Certbot
  --docker        Deploy with Docker Compose instead of bare-metal Nginx
  --port N        Host port for Docker mode (default: 8080)
  -h, --help      Show this help
EOF
}

# ── args ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:?--domain needs a value}"; shift 2 ;;
    --ssl)    SSL_EMAIL="${2:?--ssl needs an email}"; shift 2 ;;
    --docker) MODE="docker"; shift ;;
    --port)   PORT="${2:?--port needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1  (try --help)" ;;
  esac
done

# ── privilege helper ────────────────────────────────────────────────
SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || die "Run as root or install sudo."
  SUDO="sudo"
fi

# ── package manager detection ───────────────────────────────────────
PKG=""
if command -v apt-get >/dev/null 2>&1; then PKG="apt";
elif command -v dnf >/dev/null 2>&1; then PKG="dnf";
elif command -v yum >/dev/null 2>&1; then PKG="yum";
fi

pkg_install() {
  case "$PKG" in
    apt) $SUDO apt-get update -qq && $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" ;;
    dnf) $SUDO dnf install -y -q "$@" ;;
    yum) $SUDO yum install -y -q "$@" ;;
    *) die "Unsupported distro (no apt/dnf/yum). Use --docker mode instead." ;;
  esac
}

ensure_node() {
  if command -v node >/dev/null 2>&1; then
    local major; major="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
    if [[ "$major" -ge 18 ]]; then ok "Node.js $(node -v) found"; return; fi
    warn "Node.js $(node -v) is too old — upgrading to 22 LTS…"
  fi
  log "Installing Node.js 22 LTS (NodeSource)…"
  case "$PKG" in
    apt)
      pkg_install ca-certificates curl gnupg
      $SUDO install -d -m 0755 /etc/apt/keyrings
      curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | $SUDO gpg --batch --yes --dearmor -o /etc/apt/keyrings/nodesource.gpg
      echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
        | $SUDO tee /etc/apt/sources.list.d/nodesource.list >/dev/null
      pkg_install nodejs
      ;;
    dnf|yum)
      curl -fsSL https://rpm.nodesource.com/setup_22.x | $SUDO bash -
      pkg_install nodejs
      ;;
    *) die "Cannot auto-install Node.js on this distro. Install Node ≥18 or use --docker." ;;
  esac
  ok "Node.js $(node -v) installed"
}

# ════════════════════════════════════════════════════════════════════
#  DOCKER MODE
# ════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "docker" ]]; then
  command -v docker >/dev/null 2>&1 || die "Docker is not installed. Get it: https://get.docker.com"
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 plugin is required."
  cd "$SCRIPT_DIR"
  log "Building image and starting container on port ${PORT}…"
  PORT="$PORT" docker compose up -d --build
  ok "AETHER is live →  http://localhost:${PORT}"
  echo "${c_dim}Logs:  docker compose logs -f   ·   Stop:  docker compose down${c_reset}"
  exit 0
fi

# ════════════════════════════════════════════════════════════════════
#  BARE-METAL MODE  (build → /var/www/aether → Nginx)
# ════════════════════════════════════════════════════════════════════
[[ -n "$PKG" ]] || die "Unsupported distro (no apt/dnf/yum). Use --docker mode instead."
cd "$SCRIPT_DIR"

# ── shop API port: env > server/.env > ./.env > 9273 ────────────────
if [[ -z "${API_PORT:-}" && -f server/.env ]]; then
  API_PORT="$(grep -E '^API_PORT=' server/.env | tail -1 | cut -d= -f2 | tr -d ' "'"'"'\r' || true)"
fi
if [[ -z "${API_PORT:-}" && -f .env ]]; then
  API_PORT="$(grep -E '^API_PORT=' .env | tail -1 | cut -d= -f2 | tr -d ' "'"'"'\r' || true)"
fi
API_PORT="${API_PORT:-9273}"

# ── remember the chosen domain across updates (server/.env) ─────────
if [[ "$DOMAIN" == "_" && -f server/.env ]]; then
  SAVED_DOMAIN="$(grep -E '^SITE_DOMAIN=' server/.env | tail -1 | cut -d= -f2 | tr -d ' "'"'"'\r' || true)"
  if [[ -n "${SAVED_DOMAIN:-}" ]]; then DOMAIN="$SAVED_DOMAIN"; log "Using saved domain: ${DOMAIN}"; fi
fi
SCHEME="http"

ensure_node
command -v npm >/dev/null 2>&1 || die "npm missing after Node install."

log "Installing dependencies…"
if [[ -f package-lock.json ]]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

log "Building production bundle…"
npm run build
[[ -f dist/index.html ]] || die "Build failed: dist/index.html not found."
ok "Build complete ($(du -sh dist | cut -f1))"

log "Deploying to ${WEB_ROOT}…"
$SUDO mkdir -p "$WEB_ROOT"
if command -v rsync >/dev/null 2>&1; then
  $SUDO rsync -a --delete dist/ "$WEB_ROOT/"
else
  $SUDO rm -rf "${WEB_ROOT:?}"/* && $SUDO cp -a dist/. "$WEB_ROOT/"
fi
$SUDO chown -R www-data:www-data "$WEB_ROOT" 2>/dev/null || $SUDO chown -R nginx:nginx "$WEB_ROOT" 2>/dev/null || true
$SUDO find "$WEB_ROOT" -type d -exec chmod 755 {} + 2>/dev/null || true
$SUDO find "$WEB_ROOT" -type f -exec chmod 644 {} + 2>/dev/null || true

# ── shop API backend (orders, admin panel, Pasarguard provisioning) ──
NODE_BIN="$(command -v node)"
$SUDO mkdir -p "$SCRIPT_DIR/server/data"
$SUDO chmod 700 "$SCRIPT_DIR/server/data" 2>/dev/null || true
if [[ ! -f "$SCRIPT_DIR/server/.env" && -f "$SCRIPT_DIR/server/.env.example" ]]; then
  $SUDO cp "$SCRIPT_DIR/server/.env.example" "$SCRIPT_DIR/server/.env"
  $SUDO sed -i "s/^API_PORT=.*/API_PORT=${API_PORT}/" "$SCRIPT_DIR/server/.env"
  $SUDO chmod 600 "$SCRIPT_DIR/server/.env" 2>/dev/null || true
  log "Created server/.env (API_PORT=${API_PORT})"
fi
if command -v systemctl >/dev/null 2>&1 && [[ -f deploy/norkhiz-api.service ]]; then
  TMPUNIT="$(mktemp)"
  sed -e "s#__APPDIR__#${SCRIPT_DIR}#g" -e "s#__NODE__#${NODE_BIN}#g" \
    deploy/norkhiz-api.service > "$TMPUNIT"
  $SUDO install -m 644 "$TMPUNIT" /etc/systemd/system/norkhiz-api.service
  rm -f "$TMPUNIT"
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable norkhiz-api >/dev/null 2>&1 || true
  $SUDO systemctl restart norkhiz-api
  ok "Shop API service started on port ${API_PORT}"
else
  warn "systemctl unavailable — start the shop API manually:  cd server && node server.mjs"
fi

if ! command -v nginx >/dev/null 2>&1; then
  log "Installing Nginx…"
  pkg_install nginx
fi

log "Writing Nginx vhost (server_name: ${DOMAIN})…"
TMPCONF="$(mktemp)"
sed -e "s#__DOMAIN__#${DOMAIN}#g" -e "s#__ROOT__#${WEB_ROOT}#g" -e "s#__APIPORT__#${API_PORT}#g" \
  deploy/nginx-site.conf > "$TMPCONF"

if [[ -d /etc/nginx/sites-available ]]; then
  $SUDO install -m 644 "$TMPCONF" "/etc/nginx/sites-available/${APP_NAME}"
  $SUDO ln -sf "/etc/nginx/sites-available/${APP_NAME}" "/etc/nginx/sites-enabled/${APP_NAME}"
  # keep the distro default site only if we are not the catch-all
  if [[ "$DOMAIN" == "_" && -e /etc/nginx/sites-enabled/default ]]; then
    $SUDO rm -f /etc/nginx/sites-enabled/default
  fi
else
  $SUDO install -m 644 "$TMPCONF" "/etc/nginx/conf.d/${APP_NAME}.conf"
fi
rm -f "$TMPCONF"

$SUDO nginx -t
if command -v systemctl >/dev/null 2>&1; then
  $SUDO systemctl enable nginx >/dev/null 2>&1 || true
  $SUDO systemctl reload nginx 2>/dev/null || $SUDO systemctl restart nginx
else
  $SUDO nginx -s reload 2>/dev/null || $SUDO nginx
fi
ok "Nginx configured and (re)loaded"

# firewall (best-effort)
if command -v ufw >/dev/null 2>&1 && $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
  $SUDO ufw allow 'Nginx Full' >/dev/null 2>&1 || $SUDO ufw allow 80,443/tcp >/dev/null 2>&1 || true
  $SUDO ufw allow "${API_PORT}/tcp" >/dev/null 2>&1 || true
  log "UFW: allowed HTTP/HTTPS + shop API (${API_PORT})"
fi
if command -v firewall-cmd >/dev/null 2>&1 && $SUDO firewall-cmd --state >/dev/null 2>&1; then
  $SUDO firewall-cmd --permanent --add-service=http --add-service=https >/dev/null 2>&1 || true
  $SUDO firewall-cmd --permanent --add-port="${API_PORT}/tcp" >/dev/null 2>&1 || true
  $SUDO firewall-cmd --reload >/dev/null 2>&1 || true
  log "firewalld: allowed HTTP/HTTPS + shop API (${API_PORT})"
fi

# ── HTTPS via Certbot (obtain, or re-apply after vhost rewrite) ─────
if [[ "$DOMAIN" != "_" ]]; then
  # persist domain so future updates keep this vhost + its certificate
  mkdir -p server
  if [[ -f server/.env ]]; then
    grep -v '^SITE_DOMAIN=' server/.env > server/.env.tmp || true
    mv server/.env.tmp server/.env
  fi
  echo "SITE_DOMAIN=${DOMAIN}" >> server/.env
  chmod 600 server/.env 2>/dev/null || true

  if [[ -n "$SSL_EMAIL" ]]; then
    log "Requesting Let's Encrypt certificate for ${DOMAIN}…"
    CERT_READY=1
    CERT_OK=0
    if [[ "$PKG" == "apt" ]]; then
      pkg_install certbot python3-certbot-nginx || CERT_READY=0
    else
      pkg_install certbot python3-certbot-nginx || pkg_install certbot || CERT_READY=0
    fi
    if [[ "$CERT_READY" == "1" ]]; then
      if [[ "$SSL_EMAIL" == "none" ]]; then
        if $SUDO certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect; then
          CERT_OK=1
        fi
      else
        if $SUDO certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$SSL_EMAIL" --redirect; then
          CERT_OK=1
        fi
      fi
    fi
    if [[ "$CERT_OK" == "1" ]]; then
      SCHEME="https"
      ok "HTTPS enabled → https://${DOMAIN}"
    else
      warn "HTTPS could not be enabled yet; the site and API were installed with HTTP."
      warn "After DNS for ${DOMAIN} points to this server and ports 80/443 are open, retry:"
      if [[ "$SSL_EMAIL" == "none" ]]; then
        warn "  sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos --register-unsafely-without-email --redirect"
      else
        warn "  sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m ${SSL_EMAIL} --redirect"
      fi
    fi
  elif [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]] && command -v certbot >/dev/null 2>&1; then
    log "Existing certificate found for ${DOMAIN} — re-applying after vhost update…"
    if $SUDO certbot install --nginx --cert-name "$DOMAIN" --non-interactive --redirect; then
      SCHEME="https"
      ok "HTTPS restored → https://${DOMAIN}"
      $SUDO systemctl reload nginx 2>/dev/null || $SUDO nginx -s reload 2>/dev/null || true
    else
      warn "Could not re-apply certificate automatically. Run:  sudo certbot install --nginx --cert-name ${DOMAIN} --redirect"
    fi
  else
    warn "Domain vhost ready, but HTTPS is off. To enable: run with --ssl you@mail.com (after DNS points here)."
  fi
fi

# ── health check ────────────────────────────────────────────────────
sleep 1
if curl -fsS "http://127.0.0.1:${API_PORT}/api/config" >/dev/null 2>&1; then
  ok "Shop API health check passed"
else
  warn "Shop API not responding yet on :${API_PORT} — check:  systemctl status norkhiz-api  /  journalctl -u norkhiz-api -n 50"
fi
PUBLIC_IP="$(curl -fsS --max-time 4 https://api.ipify.org 2>/dev/null || echo '<SERVER-IP>')"

echo
if [[ "$DOMAIN" == "_" ]]; then
  ok "AETHER is live →  http://<SERVER-IP>/"
else
  ok "AETHER is live →  ${SCHEME}://${DOMAIN}/"
fi
ok "Admin panel →  http://${PUBLIC_IP}:${API_PORT}   (first visit: choose your password + enter Pasarguard URL & API key)"
echo "${c_dim}Update later with:  sudo bash update.sh        ·        Files: ${WEB_ROOT}${c_reset}"
echo "${c_dim}Nginx logs:  /var/log/nginx/aether.access.log${c_reset}"
