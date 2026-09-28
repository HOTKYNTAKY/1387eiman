"""
توابع قالب‌بندی متن‌ها: قیمت، حجم، تاریخ شمسی، مدت زمان و ...

توجه: چون پیام‌ها با parse_mode=HTML ارسال می‌شوند، هر متنی که از کاربر یا
پنل می‌آید باید با h() اسکیپ شود تا کاراکترهایی مثل < و & پیام را خراب نکنند.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import jdatetime

DAY = 86400
GB = 1024**3


def h(value: object) -> str:
    """اسکیپ HTML برای نمایش امن متن در پیام‌ها."""
    return html.escape(str(value if value is not None else ""), quote=False)


def fmt_price(amount: int | float) -> str:
    """150000 -> '150,000 تومان'"""
    return f"{int(amount):,} تومان"


def fmt_traffic(gb: float) -> str:
    """حجم پلن؛ صفر یعنی نامحدود."""
    if not gb or gb <= 0:
        return "نامحدود ♾"
    return f"{gb:g} گیگابایت"


def fmt_bytes(size: int | float | None) -> str:
    """نمایش خوانای حجم (بایت)."""
    if size is None:
        return "—"
    size = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def fmt_date(timestamp: int | None, tz: ZoneInfo, *, with_time: bool = True) -> str:
    """تبدیل timestamp به تاریخ شمسی در منطقه زمانی تنظیم‌شده."""
    if not timestamp:
        return "—"
    moment = datetime.fromtimestamp(int(timestamp), tz)
    jalali = jdatetime.datetime.fromgregorian(datetime=moment)
    return jalali.strftime("%Y/%m/%d - %H:%M" if with_time else "%Y/%m/%d")


def fmt_duration(seconds: int) -> str:
    """مدت زمان باقی‌مانده به صورت «۱۲ روز و ۵ ساعت»."""
    if seconds <= 0:
        return "تمام شده"
    days, remainder = divmod(int(seconds), DAY)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} روز")
    if hours:
        parts.append(f"{hours} ساعت")
    if not days and minutes:
        parts.append(f"{minutes} دقیقه")
    return " و ".join(parts) or "کمتر از یک دقیقه"


def start_of_day(tz: ZoneInfo, days_ago: int = 0) -> int:
    """timestamp ساعت ۰۰:۰۰ امروز (یا چند روز قبل) در منطقه زمانی مشخص."""
    now = datetime.now(tz)
    midnight = datetime.combine(now.date() - timedelta(days=days_ago), datetime.min.time(), tzinfo=tz)
    return int(midnight.timestamp())


def user_link(user_id: int, name: str | None) -> str:
    """لینک قابل کلیک به پروفایل کاربر."""
    return f'<a href="tg://user?id={user_id}">{h(name or user_id)}</a>'


def split_text(text: str, limit: int = 4000) -> list[str]:
    """
    تقسیم متن طولانی به چند بخش (محدودیت تلگرام ۴۰۹۶ کاراکتر است).
    تقسیم در محل خطوط انجام می‌شود تا تگ‌های HTML یک خط نصف نشوند.
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:  # خط خیلی بلند
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def progress_bar(used: float, total: float, width: int = 10) -> str:
    """نوار پیشرفت متنی برای نمایش مصرف حجم."""
    if total <= 0:
        return ""
    ratio = max(0.0, min(1.0, used / total))
    filled = round(ratio * width)
    return "▰" * filled + "▱" * (width - filled) + f" {ratio * 100:.0f}%"


# ----------------------------------------------------------------------
# تبدیل ورودی عددی کاربر (پشتیبانی از ارقام فارسی/عربی و جداکننده هزارگان)
# ----------------------------------------------------------------------
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")


def normalize_digits(text: str) -> str:
    """۱۲۳ → 123"""
    return text.translate(_DIGIT_MAP)


def _clean_number(text: str) -> str:
    cleaned = normalize_digits(text or "").strip()
    for token in (",", "٬", "،", " ", "_", "تومان", "toman", "روز", "گیگ", "GB", "gb"):
        cleaned = cleaned.replace(token, "")
    return cleaned


def parse_int(text: str) -> int | None:
    """'۱۵۰,۰۰۰ تومان' → 150000 ؛ ورودی نامعتبر → None"""
    cleaned = _clean_number(text)
    if cleaned.lstrip("+-").isdigit():
        return int(cleaned)
    return None


def parse_float(text: str) -> float | None:
    """'۲.۵' → 2.5 ؛ ورودی نامعتبر → None"""
    cleaned = _clean_number(text).replace("/", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None
