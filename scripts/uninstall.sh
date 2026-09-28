#!/usr/bin/env bash
# =====================================================================
#  حذف سرویس systemd ربات
#  اجرا:   sudo bash scripts/uninstall.sh
#
#  فایل‌های پروژه، دیتابیس و بکاپ‌ها حذف نمی‌شوند.
# =====================================================================
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-vpn-bot}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "با sudo اجرا کنید:  sudo bash scripts/uninstall.sh" >&2; exit 1; }

systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
rm -f "$UNIT_FILE"
systemctl daemon-reload

echo "✅ سرویس $SERVICE_NAME حذف شد."
echo "ℹ️  دیتابیس و بکاپ‌ها در $PROJECT_DIR/data و $PROJECT_DIR/backups باقی مانده‌اند."
echo "   برای حذف کامل (پس از کپی گرفتن از بکاپ‌ها):  sudo rm -rf $PROJECT_DIR"
