"""
ساختار جداول دیتابیس SQLite و سیستم مهاجرت (Migration)

نسخه ساختار دیتابیس در PRAGMA user_version ذخیره می‌شود. برای تغییر ساختار در
نسخه‌های بعدی، کافی است یک رشته SQL جدید به انتهای لیست MIGRATIONS اضافه کنید؛
هنگام اجرا (و همچنین پس از ریستور یک بکاپ قدیمی) مهاجرت‌های باقی‌مانده خودکار
اجرا می‌شوند.

همه زمان‌ها به صورت Unix timestamp (ثانیه، UTC) ذخیره می‌شوند.
"""

# ----------------------------------------------------------------------
# نسخه ۱: ساختار اولیه
# ----------------------------------------------------------------------
SCHEMA_V1 = """
-- کاربران ربات (کلید اصلی = آیدی عددی تلگرام)
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT,
    full_name     TEXT    NOT NULL DEFAULT '',
    is_banned     INTEGER NOT NULL DEFAULT 0,   -- مسدود شده توسط ادمین
    bot_blocked   INTEGER NOT NULL DEFAULT 0,   -- کاربر ربات را بلاک کرده است
    created_at    INTEGER NOT NULL,
    last_seen_at  INTEGER NOT NULL
);

-- سرورها / لوکیشن‌ها و نحوه ساخت کانفیگ روی آن‌ها
--   kind = manual  : کانفیگ‌ها از انبار (موجودی دستی) تحویل داده می‌شوند
--   kind = xui     : ساخت خودکار کاربر روی پنل 3x-ui (سنایی)
--   kind = marzban : ساخت خودکار کاربر روی پنل Marzban / PasarGuard
CREATE TABLE IF NOT EXISTS servers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    kind         TEXT    NOT NULL DEFAULT 'manual',
    api_url      TEXT    NOT NULL DEFAULT '',
    api_user     TEXT    NOT NULL DEFAULT '',
    api_pass     TEXT    NOT NULL DEFAULT '',
    api_token    TEXT    NOT NULL DEFAULT '',   -- توکن API (اختیاری، 3x-ui نسخه ۳)
    inbound_ids  TEXT    NOT NULL DEFAULT '',   -- 3x-ui: آیدی اینباندها / PasarGuard: آیدی گروه‌ها / Marzban: تگ اینباندها
    sub_url      TEXT    NOT NULL DEFAULT '',   -- آدرس پایه لینک ساب‌اسکریپشن (اختیاری)
    address      TEXT    NOT NULL DEFAULT '',   -- آدرس عمومی سرور برای ساخت لینک‌ها (اختیاری)
    is_active    INTEGER NOT NULL DEFAULT 1,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL
);

-- پلن‌های فروش (هر پلن به یک سرور تعلق دارد)
CREATE TABLE IF NOT EXISTS plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id    INTEGER NOT NULL REFERENCES servers(id),
    name         TEXT    NOT NULL,
    days         INTEGER NOT NULL,
    traffic_gb   REAL    NOT NULL DEFAULT 0,    -- 0 = نامحدود
    price        INTEGER NOT NULL,              -- به تومان
    description  TEXT    NOT NULL DEFAULT '',
    is_active    INTEGER NOT NULL DEFAULT 1,
    is_deleted   INTEGER NOT NULL DEFAULT 0,    -- حذف نرم (برای حفظ سابقه سفارش‌ها)
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL
);

-- سرویس‌ها (اشتراک‌های خریداری‌شده کاربران)
CREATE TABLE IF NOT EXISTS subscriptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    plan_id      INTEGER REFERENCES plans(id),
    server_id    INTEGER REFERENCES servers(id),
    title        TEXT    NOT NULL,              -- نام پلن در زمان خرید
    config       TEXT    NOT NULL DEFAULT '',   -- کانفیگ‌ها (هر خط یک کانفیگ)
    sub_link     TEXT    NOT NULL DEFAULT '',   -- لینک ساب‌اسکریپشن
    meta         TEXT    NOT NULL DEFAULT '{}', -- اطلاعات فنی پنل (JSON)
    traffic_gb   REAL    NOT NULL DEFAULT 0,
    started_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'active',  -- active | expired | disabled
    warned       INTEGER NOT NULL DEFAULT 0,         -- هشدار نزدیک شدن به انقضا ارسال شده؟
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subs_status_exp ON subscriptions(status, expires_at);

-- انبار کانفیگ‌های آماده برای سرورهای «دستی» (هر کانفیگ متعلق به یک پلن)
CREATE TABLE IF NOT EXISTS configs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id          INTEGER NOT NULL REFERENCES plans(id),
    content          TEXT    NOT NULL,
    subscription_id  INTEGER REFERENCES subscriptions(id),
    is_used          INTEGER NOT NULL DEFAULT 0,
    created_at       INTEGER NOT NULL,
    used_at          INTEGER
);
CREATE INDEX IF NOT EXISTS idx_configs_plan ON configs(plan_id, is_used);

-- سفارش‌ها
--   kind   : new (خرید) | renew (تمدید) | gift (سرویس هدیه از طرف ادمین)
--   status : pending (در انتظار پرداخت) | waiting (رسید ارسال شده، منتظر تایید)
--            | paid (تایید شده ولی تحویل ناموفق) | completed (تحویل شده)
--            | rejected (رد شده) | canceled (لغو شده)
CREATE TABLE IF NOT EXISTS orders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    plan_id          INTEGER REFERENCES plans(id),
    subscription_id  INTEGER REFERENCES subscriptions(id),
    kind             TEXT    NOT NULL DEFAULT 'new',
    amount           INTEGER NOT NULL DEFAULT 0,
    plan_title       TEXT    NOT NULL DEFAULT '',
    method           TEXT    NOT NULL DEFAULT '',   -- card | link | admin
    status           TEXT    NOT NULL DEFAULT 'pending',
    receipt_kind     TEXT,                          -- photo | document | text
    receipt_file_id  TEXT,
    receipt_text     TEXT,
    note             TEXT,                          -- دلیل رد یا خطای تحویل
    created_at       INTEGER NOT NULL,
    updated_at       INTEGER NOT NULL,
    paid_at          INTEGER
);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- تیکت‌های پشتیبانی
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    subject     TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'open',   -- open | answered | closed
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender      TEXT    NOT NULL,                  -- user | admin
    text        TEXT    NOT NULL DEFAULT '',
    file_id     TEXT,
    file_kind   TEXT,                              -- photo | document
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket ON ticket_messages(ticket_id);

-- تنظیمات قابل ویرایش از داخل ربات (کلید/مقدار)
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

# لیست مهاجرت‌ها به ترتیب نسخه (اندیس ۰ = نسخه ۱)
MIGRATIONS: list[str] = [
    SCHEMA_V1,
]

# جدول‌هایی که یک فایل بکاپ معتبر باید داشته باشد
REQUIRED_TABLES = {"users", "plans", "orders", "subscriptions", "settings"}


# ----------------------------------------------------------------------
# مقادیر پیش‌فرض تنظیمات (فقط اگر وجود نداشته باشند درج می‌شوند)
# ----------------------------------------------------------------------
DEFAULT_WELCOME = (
    "سلام {name} عزیز 👋\n"
    "به ربات فروش فیلترشکن خوش آمدید 🌹\n\n"
    "🚀 سرویس‌های پرسرعت و پایدار V2Ray (VLESS / VMess / Reality)\n"
    "⚡️ تحویل خودکار پس از تایید پرداخت\n"
    "🎧 پشتیبانی از طریق تیکت\n\n"
    "از منوی زیر یکی از گزینه‌ها را انتخاب کنید 👇"
)

DEFAULT_SUPPORT = (
    "🎧 <b>پشتیبانی</b>\n\n"
    "اگر سؤال یا مشکلی دارید، یک تیکت ثبت کنید.\n"
    "پاسخ پشتیبانی در همین ربات برای شما ارسال می‌شود."
)

DEFAULT_GUIDE = (
    "📚 <b>راهنمای اتصال</b>\n\n"
    "1️⃣ یکی از برنامه‌های زیر را نصب کنید:\n"
    "🤖 اندروید: v2rayNG یا Hiddify\n"
    "🍏 آیفون: Streisand یا V2Box یا Hiddify\n"
    "💻 ویندوز: v2rayN یا Hiddify\n"
    "🍎 مک: V2Box یا Hiddify\n\n"
    "2️⃣ از بخش «📦 سرویس‌های من» کانفیگ یا لینک اشتراک خود را کپی کنید.\n"
    "3️⃣ در برنامه گزینه «Import from clipboard» (افزودن از کلیپ‌بورد) را بزنید.\n"
    "4️⃣ کانفیگ را انتخاب و دکمه اتصال را بزنید ✅"
)

DEFAULT_SETTINGS: dict[str, str] = {
    # عمومی
    "sales_enabled": "1",
    "welcome_text": DEFAULT_WELCOME,
    "support_text": DEFAULT_SUPPORT,
    "guide_text": DEFAULT_GUIDE,
    # پرداخت کارت به کارت
    "card_enabled": "1",
    "card_number": "",
    "card_holder": "",
    "bank_name": "",
    # پرداخت از طریق لینک (درگاه شخصی، زرین‌لینک، کریپتو و ...)
    "link_enabled": "0",
    "payment_link": "",
    # توضیحات اضافه که زیر اطلاعات پرداخت نمایش داده می‌شود
    "payment_note": "",
}
