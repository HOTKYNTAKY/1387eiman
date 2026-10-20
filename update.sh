#!/usr/bin/env bash
# AETHER — update an existing bare-metal install in place:
#   git pull → npm ci → build → rsync to /var/www/aether → reload Nginx
# Usage:  sudo bash update.sh
set -euo pipefail

WEB_ROOT="/var/www/aether"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SUDO=""; [[ "${EUID}" -ne 0 ]] && SUDO="sudo"

if [[ -d .git ]]; then
  echo "▸ Pulling latest code…"
  git pull --ff-only
fi

echo "▸ Installing dependencies & building…"
[[ -f package-lock.json ]] && npm ci --no-audit --no-fund || npm install --no-audit --no-fund
npm run build

echo "▸ Deploying to ${WEB_ROOT}…"
$SUDO mkdir -p "$WEB_ROOT"
if command -v rsync >/dev/null 2>&1; then
  $SUDO rsync -a --delete dist/ "$WEB_ROOT/"
else
  $SUDO rm -rf "${WEB_ROOT:?}"/* && $SUDO cp -a dist/. "$WEB_ROOT/"
fi
$SUDO nginx -t && { $SUDO systemctl reload nginx 2>/dev/null || $SUDO nginx -s reload; }
if $SUDO systemctl cat norkhiz-api >/dev/null 2>&1; then
  echo "▸ Restarting shop API…"
  $SUDO systemctl restart norkhiz-api
fi
echo "✓ AETHER updated."
