#!/usr/bin/env bash
# =====================================================================
#  نصب خودکار ربات فروش فیلترشکن روی Ubuntu / Debian
#
#  اجرا (داخل پوشه پروژه):
#      sudo bash scripts/install.sh
#
#  این اسکریپت:
#    1. پیش‌نیازها (Python 3.10+، venv، git) را نصب می‌کند
#    2. محیط مجازی .venv را می‌سازد و کتابخانه‌ها را نصب می‌کند
#    3. اگر تنظیم نشده باشد، توکن ربات و آیدی ادمین را می‌پرسد (.env)
#    4. سرویس systemd را می‌سازد، فعال می‌کند و ربات را اجرا می‌کند
#
#  متغیرهای اختیاری:
#      SERVICE_NAME=my-bot  sudo -E bash scripts/install.sh   (نام دلخواه سرویس، برای چند ربات)
#      RUN_USER=someuser    sudo -E bash scripts/install.sh   (کاربر اجرای ربات)
# =====================================================================
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-vpn-bot}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
MIN_MINOR=10

info() { echo -e "\e[36m[•]\e[0m $*"; }
ok()   { echo -e "\e[32m[✓]\e[0m $*"; }
warn() { echo -e "\e[33m[!]\e[0m $*"; }
die()  { echo -e "\e[31m[✗]\e[0m $*" >&2; exit 1; }
trap 'die "خطا در خط $LINENO؛ نصب متوقف شد. (Installation failed at line $LINENO)"' ERR

[[ $EUID -eq 0 ]] || die "این اسکریپت را با sudo اجرا کنید:  sudo bash scripts/install.sh"
command -v apt-get >/dev/null 2>&1 || die "فقط Ubuntu و Debian پشتیبانی می‌شوند."
command -v systemctl >/dev/null 2>&1 || die "systemd پیدا نشد."

cd "$PROJECT_DIR"
RUN_USER="${RUN_USER:-$(stat -c %U "$PROJECT_DIR")}"
id "$RUN_USER" >/dev/null 2>&1 || die "کاربر $RUN_USER وجود ندارد."
as_user() { runuser -u "$RUN_USER" -- "$@"; }

echo
echo "=============================================="
echo "   🤖  VPN Shop Bot installer / نصب ربات"
echo "=============================================="
info "پوشه پروژه: $PROJECT_DIR"
info "کاربر اجرای ربات: $RUN_USER"
info "نام سرویس: $SERVICE_NAME"
echo

# ---------------------------------------------------------------------
# 1) پیش‌نیازها
# ---------------------------------------------------------------------
info "نصب پیش‌نیازهای سیستم..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -qq
apt-get install -y -qq python3 python3-venv python3-pip ca-certificates tzdata git >/dev/null

find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)" 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  # مثلاً Ubuntu 20.04 که Python 3.8 دارد
  . /etc/os-release
  if [[ "${ID:-}" == "ubuntu" ]]; then
    warn "Python 3.10+ پیدا نشد؛ نصب Python 3.11 از مخزن deadsnakes..."
    apt-get install -y -qq software-properties-common >/dev/null
    add-apt-repository -y ppa:deadsnakes/ppa >/dev/null
    apt-get update -y -qq
    apt-get install -y -qq python3.11 python3.11-venv >/dev/null
    PYTHON_BIN="$(command -v python3.11)"
  else
    die "Python 3.10 یا بالاتر لازم است. لطفاً سیستم‌عامل را به Ubuntu 22.04/24.04 یا Debian 12 ارتقا دهید."
  fi
fi

# ماژول venv/ensurepip برای نسخه انتخاب‌شده (بسته python3.X-venv)
if ! "$PYTHON_BIN" -c "import ensurepip, venv" >/dev/null 2>&1; then
  PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  apt-get install -y -qq "python${PY_VER}-venv" >/dev/null
fi
ok "Python: $("$PYTHON_BIN" --version)"

# ---------------------------------------------------------------------
# 2) محیط مجازی و کتابخانه‌ها
# ---------------------------------------------------------------------
info "ساخت محیط مجازی و نصب کتابخانه‌ها (ممکن است چند دقیقه طول بکشد)..."
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  as_user "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
as_user "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
as_user "$VENV_DIR/bin/python" -m pip install --quiet -r "$PROJECT_DIR/requirements.txt"
ok "کتابخانه‌ها نصب شدند."

# پوشه‌های داده
for dir in data backups logs; do
  mkdir -p "$PROJECT_DIR/$dir"
  chown "$RUN_USER": "$PROJECT_DIR/$dir"
done

# ---------------------------------------------------------------------
# 3) تنظیمات ربات (.env)
# ---------------------------------------------------------------------
if ! as_user "$VENV_DIR/bin/python" -m bot --check >/dev/null 2>&1; then
  if [[ -t 0 ]]; then
    echo
    info "اکنون توکن ربات (از @BotFather) و آیدی عددی ادمین (از @userinfobot) را وارد کنید:"
    as_user "$VENV_DIR/bin/python" -m bot --setup
  else
    die "ترمینال تعاملی در دسترس نیست. ابتدا اجرا کنید:  $VENV_DIR/bin/python -m bot --setup"
  fi
fi
as_user "$VENV_DIR/bin/python" -m bot --check || die "تنظیمات .env نامعتبر است."
chmod 600 "$PROJECT_DIR/.env"

# ---------------------------------------------------------------------
# 4) سرویس systemd
# ---------------------------------------------------------------------
info "ساخت سرویس systemd: $UNIT_FILE"
sed -e "s#/opt/vpn-bot#${PROJECT_DIR}#g" \
    -e "s#^User=.*#User=${RUN_USER}#" \
    "$PROJECT_DIR/deploy/vpn-bot.service" > "$UNIT_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"

sleep 4
if systemctl is-active --quiet "$SERVICE_NAME"; then
  ok "ربات با موفقیت اجرا شد 🎉  در تلگرام به ربات /start بدهید."
else
  warn "سرویس اجرا نشد. لاگ‌ها را بررسی کنید:"
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
fi

cat <<EOF

----------------------------------------------
 دستورات مدیریت ربات:
   وضعیت:          sudo systemctl status $SERVICE_NAME
   مشاهده لاگ:     sudo journalctl -u $SERVICE_NAME -f
   ری‌استارت:       sudo systemctl restart $SERVICE_NAME
   توقف:           sudo systemctl stop $SERVICE_NAME
   تغییر توکن:     sudo -u $RUN_USER $VENV_DIR/bin/python -m bot --setup
   به‌روزرسانی:     sudo bash $PROJECT_DIR/scripts/update.sh
----------------------------------------------
EOF
