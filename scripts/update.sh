#!/usr/bin/env bash
# =====================================================================
#  به‌روزرسانی ربات به آخرین نسخه مخزن گیت
#  اجرا:   sudo bash scripts/update.sh
#
#  قبل از به‌روزرسانی یک بکاپ از دیتابیس گرفته می‌شود.
# =====================================================================
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-vpn-bot}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

info() { echo -e "\e[36m[•]\e[0m $*"; }
ok()   { echo -e "\e[32m[✓]\e[0m $*"; }
warn() { echo -e "\e[33m[!]\e[0m $*"; }
die()  { echo -e "\e[31m[✗]\e[0m $*" >&2; exit 1; }
trap 'die "خطا در خط $LINENO؛ به‌روزرسانی متوقف شد."' ERR

[[ $EUID -eq 0 ]] || die "با sudo اجرا کنید:  sudo bash scripts/update.sh"
[[ -x "$VENV_DIR/bin/python" ]] || die "ابتدا ربات را نصب کنید:  sudo bash scripts/install.sh"

cd "$PROJECT_DIR"
RUN_USER="$(stat -c %U "$PROJECT_DIR")"
as_user() { runuser -u "$RUN_USER" -- "$@"; }

info "گرفتن بکاپ قبل از به‌روزرسانی..."
as_user "$VENV_DIR/bin/python" -m bot --backup || warn "بکاپ گرفته نشد (ادامه می‌دهیم)."

info "دریافت آخرین نسخه از گیت..."
as_user git pull --ff-only

info "به‌روزرسانی کتابخانه‌ها..."
as_user "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt

info "ری‌استارت ربات..."
systemctl restart "$SERVICE_NAME"
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
  ok "به‌روزرسانی با موفقیت انجام شد."
else
  warn "سرویس اجرا نشد؛ لاگ را بررسی کنید:  journalctl -u $SERVICE_NAME -n 50"
fi
