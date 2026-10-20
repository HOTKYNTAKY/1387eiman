#!/usr/bin/env node
/**
 * ═══════════════════════════════════════════════════════════════
 *  ورتکس‌نت — سرور فروش و پنل ادمین (Node بدون هیچ وابستگی)
 *  - فروش کانفیگ با کارت‌به‌کارت + تأیید دستی ادمین
 *  - ساخت خودکار کانفیگ روی پنل پاسارگارد (PasarGuard API) بعد از تأیید
 *  - پنل ادمین روی همین پورت (پیش‌فرض 9273) — راه‌اندازی اولیه از مرورگر
 *  هیچ رازی داخل کد نیست؛ رمز ادمین و کلید API فقط در data/config.json
 *  روی خود سرور (با دسترسی 600) ذخیره می‌شود.
 * ═══════════════════════════════════════════════════════════════
 */
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.API_PORT || 9273);
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const CONFIG_FILE = path.join(DATA_DIR, 'config.json');
const ORDERS_FILE = path.join(DATA_DIR, 'orders.json');
const USERS_FILE = path.join(DATA_DIR, 'users.json');
const CHATS_FILE = path.join(DATA_DIR, 'chats.json');
const DISCOUNTS_FILE = path.join(DATA_DIR, 'discounts.json');
const ANN_FILE = path.join(DATA_DIR, 'announcements.json');
const COMMENTS_FILE = path.join(DATA_DIR, 'comments.json');
const SESSIONS_FILE = path.join(DATA_DIR, 'sessions.json');

const DEFAULT_CONFIG = {
  pricePerGB: 4000,          // تومان
  planDays: 30,              // مدت هر پلن (روز)
  minGB: 10,                 // حداقل حجم قابل خرید
  cardNumber: '6219861495616921',
  cardName: 'ایمان دهقانی',
  pgBaseUrl: '',             // مثال: https://alman.norkhizstudio.com:8000
  pgPublicBaseUrl: '',       // آدرس عمومی لینک اشتراک مشتری؛ خالی = همان آدرس پنل
  pgApiKey: '',              // کلید pg_key_... از تنظیمات پنل پاسارگارد
  pgUsername: '',            // جایگزین کلید API: نام کاربری پنل (حساب نمایندگی)
  pgPassword: '',            // رمز همان حساب — ورود خودکار و دریافت توکن JWT
  pgGroupIds: [],            // خالی = همه گروه‌ها
  adminPassHash: null,       // null یعنی هنوز راه‌اندازی نشده
};

/* ───────────────────────── ذخیره‌سازی ───────────────────────── */
fs.mkdirSync(DATA_DIR, { recursive: true });

function loadJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch { return structuredClone(fallback); }
}
function saveJson(file, data, mode = 0o644) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), { mode });
  fs.renameSync(tmp, file);
}
let config = { ...DEFAULT_CONFIG, ...loadJson(CONFIG_FILE, {}) };
let orders = loadJson(ORDERS_FILE, []);
let users = loadJson(USERS_FILE, []);            // [{id, username, usernameKey, name, email, passHash, createdAt}]
let chats = loadJson(CHATS_FILE, {});            // userId -> {userId, username, updatedAt, messages:[{id,from,text,at,read}]}
let discounts = loadJson(DISCOUNTS_FILE, []);      // [{id, code, codeKey, type, value, maxUses, oncePerUser, expiresAt, active, note, createdAt}]
let announcements = loadJson(ANN_FILE, []);         // [{id, title, body, level, pinned, active, createdAt, updatedAt}]
let comments = loadJson(COMMENTS_FILE, []);         // [{id, userId, username, text, status:'pending'|'approved', createdAt}]
if (!fs.existsSync(CONFIG_FILE)) saveJson(CONFIG_FILE, config, 0o600);
const saveConfig = () => saveJson(CONFIG_FILE, config, 0o600);
const saveOrders = () => saveJson(ORDERS_FILE, orders, 0o600);
const saveUsers = () => saveJson(USERS_FILE, users, 0o600);
const saveChats = () => saveJson(CHATS_FILE, chats, 0o600);
const saveDiscounts = () => saveJson(DISCOUNTS_FILE, discounts, 0o600);
const saveAnnouncements = () => saveJson(ANN_FILE, announcements, 0o600);
const saveComments = () => saveJson(COMMENTS_FILE, comments, 0o600);
const persistedSessions = loadJson(SESSIONS_FILE, { admin: {}, user: {} });
function saveSessions() {
  try { saveJson(SESSIONS_FILE, { admin: Object.fromEntries(sessions), user: Object.fromEntries(userSessions) }, 0o600); } catch { /* ignore */ }
}

/* ───────────────────────── ابزارها ───────────────────────── */
const nowISO = () => new Date().toISOString();
const CODE_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
function newOrderCode() {
  let code;
  do {
    code = 'VX-' + Array.from({ length: 6 }, () => CODE_CHARS[crypto.randomInt(CODE_CHARS.length)]).join('');
  } while (orders.some((o) => o.code === code));
  return code;
}
function normalizeDigits(s = '') {
  return String(s).replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
                  .replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
}
const cleanStr = (s, max = 120) => String(s ?? '').trim().slice(0, max);

/* هش رمز ادمین با scrypt */
function hashPassword(pw) {
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(pw, salt, 64);
  return `scrypt:${salt.toString('base64')}:${hash.toString('base64')}`;
}
function verifyPassword(pw, stored) {
  try {
    const [, saltB64, hashB64] = String(stored).split(':');
    const expected = Buffer.from(hashB64, 'base64');
    const actual = crypto.scryptSync(pw, Buffer.from(saltB64, 'base64'), expected.length);
    return crypto.timingSafeEqual(expected, actual);
  } catch { return false; }
}

/* ───────────────────────── نشست ادمین ───────────────────────── */
const sessions = new Map(Object.entries(persistedSessions.admin || {}).filter(([, exp]) => exp > Date.now())); // token -> expiresAt
function newSession(res) {
  const token = crypto.randomBytes(32).toString('hex');
  sessions.set(token, Date.now() + 7 * 86400_000);
  saveSessions();
  res.setHeader('Set-Cookie', `nk_admin=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${7 * 86400}`);
}
function getSession(req) {
  const m = /(?:^|;\s*)nk_admin=([a-f0-9]{64})/.exec(req.headers.cookie || '');
  if (!m) return null;
  const exp = sessions.get(m[1]);
  if (!exp || exp < Date.now()) { sessions.delete(m[1]); return null; }
  return m[1];
}

/* ───────────────────────── حساب کاربری مشتری ───────────────────────── */
const RESERVED_USERNAMES = new Set(['admin', 'administrator', 'norkhiz', 'support', 'root', 'moderator', 'system']);
const usernameKeyOf = (u) => String(u || '').normalize('NFC').trim().toLowerCase();
function validateUsername(raw) {
  const u = String(raw || '').normalize('NFC').trim();
  if (!/^[\p{L}\p{N}_.]{3,24}$/u.test(u)) return null;   // حروف/عدد/آندرلاین — فارسی و انگلیسی
  if (RESERVED_USERNAMES.has(usernameKeyOf(u))) return null;
  return u;
}
const findUserByKey = (key) => users.find((u) => u.usernameKey === key);
const findUserById = (id) => users.find((u) => u.id === id);
const publicUser = (u) => (u ? { id: u.id, username: u.username, name: u.name || '', email: u.email || '', createdAt: u.createdAt } : null);

/* نام واقعی و ایمیل (برای بازیابی حساب) */
const emailKeyOf = (e) => String(e || '').normalize('NFC').trim().toLowerCase();
function validateEmail(raw) {
  const e = emailKeyOf(raw);
  if (!e || e.length > 120) return null;
  if (!/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(e)) return null;
  return e;
}
function validateName(raw) {
  const n = String(raw || '').normalize('NFC').trim().replace(/\s+/g, ' ');
  if (n.length < 2 || n.length > 60 || !/\p{L}/u.test(n)) return null;
  return n;
}
/* کلید مقایسهٔ نام برای بازیابی — تفاوت ی/ي و ک/ك و نیم‌فاصله و اعراب را نادیده می‌گیرد */
const nameKeyOf = (n) => String(n || '')
  .normalize('NFC')
  .replace(/\u064A/g, '\u06CC').replace(/\u0643/g, '\u06A9').replace(/\u0629/g, '\u0647')
  .replace(/[\u064B-\u065F\u0670]/g, '')
  .replace(/\u0640/g, '').replace(/[\u200C\u00A0]/g, ' ')
  .replace(/\s+/g, ' ').trim().toLowerCase();
const findUserByEmail = (key) => users.find((u) => u.email && emailKeyOf(u.email) === key);

const userSessions = new Map(Object.entries(persistedSessions.user || {}).filter(([, s]) => s && s.exp > Date.now())); // token -> {userId, exp}
function newUserSession(res, userId) {
  const token = crypto.randomBytes(32).toString('hex');
  userSessions.set(token, { userId, exp: Date.now() + 30 * 86400_000 });
  saveSessions();
  res.setHeader('Set-Cookie', `nk_user=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${30 * 86400}`);
}
function getUserToken(req) {
  const m = /(?:^|;\s*)nk_user=([a-f0-9]{64})/.exec(req.headers.cookie || '');
  return m ? m[1] : null;
}
function getUser(req) {
  const t = getUserToken(req);
  if (!t) return null;
  const s = userSessions.get(t);
  if (!s || s.exp < Date.now()) { userSessions.delete(t); return null; }
  return findUserById(s.userId) || null;
}

/* توکن‌های بازیابی حساب — حافظه‌ای، یکبارمصرف، ۱۰ دقیقه‌ای (فقط هش توکن نگه داشته می‌شود) */
const recoveryTokens = new Map(); // sha256(token) -> { userId, exp }
function newRecoveryToken(userId) {
  for (const [k, v] of recoveryTokens) if (v.userId === userId || v.exp < Date.now()) recoveryTokens.delete(k);
  const token = crypto.randomBytes(32).toString('hex');
  recoveryTokens.set(crypto.createHash('sha256').update(token).digest('hex'), { userId, exp: Date.now() + 600_000 });
  return token;
}
function takeRecoveryToken(token) {
  if (!/^[a-f0-9]{64}$/.test(String(token || ''))) return null;
  const k = crypto.createHash('sha256').update(String(token)).digest('hex');
  const v = recoveryTokens.get(k);
  recoveryTokens.delete(k);
  return v && v.exp > Date.now() ? v : null;
}
/* ابطال همهٔ نشست‌های یک کاربر (مثلاً بعد از تغییر رمز با بازیابی) */
function revokeUserSessions(userId) {
  let changed = false;
  for (const [t, s] of userSessions) if (s.userId === userId) { userSessions.delete(t); changed = true; }
  if (changed) saveSessions();
}

/* ───────────────────────── چت پشتیبانی ───────────────────────── */
function getThread(user) {
  if (!chats[user.id]) {
    chats[user.id] = { userId: user.id, username: user.username, createdAt: nowISO(), updatedAt: nowISO(), messages: [] };
  }
  chats[user.id].username = user.username;
  return chats[user.id];
}
/* اسنپ‌شات پیام ریپلای‌شده (نمایش نقل‌قول داخل حباب) */
function replySnapshot(thread, replyToId) {
  if (!replyToId) return null;
  const src = (thread.messages || []).find((x) => x.id === String(replyToId));
  if (!src) return null;
  return { id: src.id, from: src.from, text: String(src.text || '').slice(0, 140) };
}
function pushMessage(thread, from, text, replyTo) {
  const m = { id: crypto.randomBytes(6).toString('hex'), from, text, at: nowISO(), read: false };
  if (replyTo) m.replyTo = replyTo;
  thread.messages.push(m);
  if (thread.messages.length > 500) thread.messages = thread.messages.slice(-500);
  thread.updatedAt = m.at;
  return m;
}
const unreadFor = (thread, who) =>
  (thread?.messages || []).filter((m) => !m.read && m.from !== who).length;
function markReadFor(thread, who) {
  let changed = false;
  for (const m of thread.messages) if (!m.read && m.from !== who) { m.read = true; changed = true; }
  return changed;
}

/* انقضای پاسارگارد ممکن است epoch ثانیه/میلی‌ثانیه یا رشتهٔ ISO باشد */
function toEpochSec(v) {
  if (typeof v === 'number' && Number.isFinite(v)) return v > 1e12 ? Math.floor(v / 1000) : Math.floor(v);
  if (typeof v === 'string' && v) {
    const n = Number(v);
    if (Number.isFinite(n) && n > 0) return toEpochSec(n);
    const d = Date.parse(v);
    if (Number.isFinite(d)) return Math.floor(d / 1000);
  }
  return null;
}

/* محدودیت تلاش ورود و ثبت سفارش (حافظه‌ای، ساده) */
const buckets = new Map();
function rateLimited(key, limit, windowMs) {
  const now = Date.now();
  const arr = (buckets.get(key) || []).filter((t) => now - t < windowMs);
  arr.push(now);
  buckets.set(key, arr);
  return arr.length > limit;
}
/* IP واقعی کاربر — پشت پراکسی کلودفلر، IP لبهٔ کلودفلر بین همه مشترک است؛
   پس وقتی درخواست از Nginx لوکال رسیده، هدر CF-Connecting-IP مبناست.
   (فقط برای درخواست‌های عبوری از Nginx به هدرها اعتماد می‌شود تا روی پورت
   مستقیم ادمین قابل جعل نباشد.) */
const clientIp = (req) => {
  const sock = (req.socket.remoteAddress || '').toString();
  const viaLocalProxy = sock === '127.0.0.1' || sock === '::1' || sock === '::ffff:127.0.0.1';
  if (viaLocalProxy) {
    const cf = req.headers['cf-connecting-ip'];
    if (cf) return cf.toString().trim();
    const xff = req.headers['x-forwarded-for'];
    if (xff) return xff.toString().split(',')[0].trim();
    const xr = req.headers['x-real-ip'];
    if (xr) return xr.toString().trim();
  }
  return sock || 'unknown';
};

/* ───────────────────────── پاسارگارد ───────────────────────── */
/* آدرس پنل را نرمال می‌کند: API پاسارگارد در ریشهٔ دامنه است (/api/...)،
   ولی کاربران معمولاً آدرس داشبورد (…/dashboard) را وارد می‌کنند.
   پسوندهای /dashboard و /api و اسلش انتهایی حذف می‌شوند. */
function normalizePgBase(raw) {
  let s = String(raw || '').trim();
  if (!s) return '';
  if (!/^https?:\/\//i.test(s)) s = 'https://' + s;
  s = s.replace(/\/+$/, '');
  let prev;
  do { prev = s; s = s.replace(/\/(dashboard|api)$/i, '').replace(/\/+$/, ''); } while (s !== prev);
  return s;
}
function pgBase() {
  return normalizePgBase(config.pgBaseUrl);
}
/* حمل‌ونقل HTTP(S) اختصاصی پاسارگارد (بدون وابستگی):
   تلاش اول با بررسی کامل گواهی TLS؛ اگر گواهی پنل self-signed باشد
   (در پنل‌های روی پورت ۸۰۰۰ بسیار رایج است) یک بار بدون بررسی گواهی
   دوباره تلاش می‌شود و از آن به بعد همان حالت به خاطر سپرده می‌شود. */
const PG_CERT_ERR_CODES = new Set([
  'DEPTH_ZERO_SELF_SIGNED_CERT', 'SELF_SIGNED_CERT_IN_CHAIN',
  'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
  'UNABLE_TO_GET_ISSUER_CERT', 'CERT_HAS_EXPIRED', 'CERT_UNTRUSTED',
  'ERR_TLS_CERT_ALTNAME_INVALID', 'INVALID_CA',
]);
let pgInsecureTls = false;
function pgHttpOnce(url, { method, headers, payload, insecure }) {
  return new Promise((resolve, reject) => {
    const isHttps = url.protocol === 'https:';
    const req = (isHttps ? https : http).request(url, {
      method,
      headers,
      timeout: 20000,
      ...(isHttps ? { rejectUnauthorized: !insecure } : {}),
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolve({
        status: res.statusCode || 0,
        location: res.headers.location || '',
        text: Buffer.concat(chunks).toString('utf8'),
      }));
    });
    req.on('timeout', () => req.destroy(Object.assign(new Error('timed out'), { code: 'ETIMEDOUT' })));
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}
async function pgRequest(url, { method, headers, payload }) {
  let target = url;
  let m = method;
  let pl = payload;
  for (let hop = 0; hop <= 3; hop++) {
    let out;
    try {
      out = await pgHttpOnce(target, { method: m, headers, payload: pl, insecure: pgInsecureTls });
    } catch (e) {
      const code = e.code || e.cause?.code || '';
      if (target.protocol === 'https:' && !pgInsecureTls && PG_CERT_ERR_CODES.has(code)) {
        pgInsecureTls = true;
        console.warn(`[norkhiz] Pasarguard TLS certificate cannot be verified (${code}) — retrying without verification (self-signed panel certificate).`);
        out = await pgHttpOnce(target, { method: m, headers, payload: pl, insecure: true });
      } else {
        throw e;
      }
    }
    if ([301, 302, 303, 307, 308].includes(out.status) && out.location && hop < 3) {
      const next = new URL(out.location, target);
      if (next.origin !== target.origin) return out; // کلید API را به مبدأ دیگر نفرست
      if (out.status === 303 || ((out.status === 301 || out.status === 302) && m === 'POST')) { m = 'GET'; pl = undefined; }
      target = next;
      continue;
    }
    return out;
  }
  throw new Error('too many redirects');
}
function pgNetErrorFa(e) {
  const code = e.code || e.cause?.code || '';
  let kind = e.message;
  if (code === 'ENOTFOUND' || code === 'EAI_AGAIN') kind = 'دامنه پنل پیدا/resolve نشد (DNS)';
  else if (code === 'ECONNREFUSED') kind = 'پنل اتصال را رد کرد (پورت بسته یا فایروال)';
  else if (code === 'ETIMEDOUT' || e.name === 'AbortError') kind = 'تایم‌اوت — سرور به پنل نمی‌رسد (مسیر شبکه/فایروال)';
  else if (code === 'ECONNRESET') kind = 'اتصال وسط راه قطع شد';
  else if (PG_CERT_ERR_CODES.has(code)) kind = 'گواهی SSL پنل قابل تأیید نیست';
  return `خطای شبکه در اتصال به پاسارگارد: ${kind}${code ? ` [${code}]` : ''}`;
}
/* ── ورود با نام کاربری/رمز پنل (جایگزین کلید API، مناسب پنل نمایندگی) ──
   POST /api/admin/token با فرم یوزر/پسورد → access_token (JWT، معمولاً ۲۴ساعته).
   توکن فقط در حافظه کش می‌شود؛ با خطای 401 یک بار ورود تازه انجام می‌شود. */
let pgJwtCache = { key: '', token: '', exp: 0 };
const pgUseJwt = () => !config.pgApiKey && !!(config.pgUsername && config.pgPassword);
async function pgGetJwt(force = false) {
  const ck = pgBase() + '|' + config.pgUsername + '|' +
    crypto.createHash('sha256').update(String(config.pgPassword || '')).digest('hex').slice(0, 16);
  if (!force && pgJwtCache.token && pgJwtCache.key === ck && Date.now() < pgJwtCache.exp) return pgJwtCache.token;
  const payload = new URLSearchParams({ username: String(config.pgUsername), password: String(config.pgPassword) }).toString();
  const res = await pgRequest(new URL(pgBase() + '/api/admin/token'), {
    method: 'POST',
    payload,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
  });
  let data = null;
  try { data = res.text ? JSON.parse(res.text) : null; } catch { /* ignore */ }
  if (!(res.status >= 200 && res.status < 300) || !data?.access_token) {
    let detail = '';
    if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    const err = new Error(`ورود به پنل پاسارگارد با نام کاربری/رمز ناموفق بود (خطای ${res.status})${detail ? ': ' + detail : ''} — نام کاربری و رمز پنل را بررسی کن`);
    err.pgFinal = true;
    throw err;
  }
  let exp = Date.now() + 3600_000;
  try {
    const p = JSON.parse(Buffer.from(String(data.access_token).split('.')[1] || '', 'base64url').toString('utf8'));
    if (p?.exp) exp = p.exp * 1000 - 60_000;
  } catch { /* ignore */ }
  pgJwtCache = { key: ck, token: data.access_token, exp };
  return data.access_token;
}
async function pgFetch(pathname, { method = 'GET', body, query } = {}) {
  const base = pgBase();
  const useJwt = pgUseJwt();
  if (!base || (!config.pgApiKey && !useJwt))
    throw new Error('اتصال پاسارگارد تنظیم نشده است (آدرس پنل و کلید API — یا نام کاربری/رمز پنل — لازم است)');
  const url = new URL(base + pathname);
  if (query) for (const [k, v] of Object.entries(query)) if (v !== undefined) url.searchParams.set(k, String(v));
  const payload = body ? JSON.stringify(body) : undefined;
  const call = (token) => pgRequest(url, {
    method,
    payload,
    headers: {
      ...(config.pgApiKey ? { 'X-API-Key': config.pgApiKey } : { 'Authorization': `Bearer ${token}` }),
      'Accept': 'application/json',
      ...(payload ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } : {}),
    },
  });
  let res;
  try {
    res = await call(useJwt ? await pgGetJwt() : null);
    if (useJwt && res.status === 401) res = await call(await pgGetJwt(true)); // توکن منقضی شده؛ ورود تازه و یک تلاش دیگر
  } catch (e) {
    if (e.pgFinal) throw e;
    throw new Error(pgNetErrorFa(e));
  }
  const text = res.text;
  const resOk = res.status >= 200 && res.status < 300;
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* ignore */ }
  if (!resOk) {
    let detail = '';
    if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    else if (text && !/^\s*</.test(text)) detail = text.replace(/\s+/g, ' ').trim().slice(0, 200);
    // اگر پاسخ HTML بود (مثل صفحهٔ داشبورد) متن خام را نشان نده؛ راهنما بده
    let hint = '';
    if (res.status === 404) hint = ' — احتمالاً آدرس پنل اشتباه وارد شده؛ آدرس را بدون ‎/dashboard‎ وارد کن (مثال: https://node3.example.com:8000)';
    else if (res.status === 401 || res.status === 403) hint = useJwt ? ' — حساب پنل دسترسی کافی ندارد؛ نقش نمایندگی باید اجازه ساخت کاربر و مشاهده گروه‌ها را داشته باشد' : ' — کلید API اشتباه است یا دسترسی کافی ندارد؛ در پاسارگارد از تنظیمات ← API Keys یک کلید با دسترسی ساخت کاربر بساز';
    else if (res.status === 422) hint = ' — دادهٔ ارسالی از طرف پنل پذیرفته نشد';
    const err = new Error(`پاسارگارد خطای ${res.status} داد${detail ? ': ' + detail : ''}${hint}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}
/* لینک اشتراک را مطلق می‌کند؛ اگر «آدرس عمومی» تنظیم شده باشد (مثلاً API با IP
   صدا زده می‌شود ولی لینک مشتری باید با دامنه باشد) مبدأ لینک با آن جایگزین می‌شود. */
const absolutize = (u) => {
  if (!u) return '';
  try {
    const abs = new URL(u, pgBase() + '/');
    const pub = normalizePgBase(config.pgPublicBaseUrl);
    if (pub && abs.hostname === new URL(pgBase() + '/').hostname)
      return new URL(abs.pathname + abs.search + abs.hash, pub + '/').toString();
    return abs.toString();
  } catch { return u; }
};
async function pgAllGroupIds() {
  const data = await pgFetch('/api/groups/simple', { query: { all: true } });
  return (data?.groups || []).map((g) => g.id);
}
async function pgCreateUser(order) {
  const groupIds = Array.isArray(config.pgGroupIds) && config.pgGroupIds.length
    ? config.pgGroupIds
    : await pgAllGroupIds();
  const username = 'vx_' + order.code.replace(/^(NK|VX)-/, '').toLowerCase();
  const payload = {
    username,
    data_limit: Math.round(order.gb) * 1024 ** 3,
    expire: Math.floor(Date.now() / 1000) + (order.days || config.planDays) * 86400,
    status: 'active',
    group_ids: groupIds,
    note: `VortexNet | ${order.code} | ${order.gb}GB | ${order.username ? '@' + order.username : order.name || ''}${order.last4 ? ' | card..' + order.last4 : ''}`,
  };
  try {
    const user = await pgFetch('/api/user', { method: 'POST', body: payload });
    return { userId: user.id, username: user.username || username, subUrl: absolutize(user.subscription_url), expire: user.expire ?? payload.expire };
  } catch (e) {
    if (e.status === 409) {
      // نام کاربری قبلاً ساخته شده (مثلاً تأیید دوباره) → همان را تحویل بگیر
      const user = await pgFetch(`/api/user/${encodeURIComponent(username)}`);
      return { userId: user.id, username: user.username || username, subUrl: absolutize(user.subscription_url), expire: user.expire ?? payload.expire };
    }
    throw e;
  }
}

/* وضعیت زندهٔ اشتراک (مصرف/انقضا) از پاسارگارد — با کش کوتاه */
const pgUserCache = new Map(); // username -> {at, data}
async function pgGetUserCached(username) {
  const hit = pgUserCache.get(username);
  if (hit && Date.now() - hit.at < 15_000) return hit.data;
  const data = await pgFetch(`/api/user/${encodeURIComponent(username)}`);
  pgUserCache.set(username, { at: Date.now(), data });
  return data;
}
/* تغییر کاربر پنل با حفظ بقیهٔ مشخصات فعلی (امن در برابر PUT جایگزینی کامل).
   اول مسیر نام کاربری؛ اگر پنل نداشت (404/405) مسیر by-id امتحان می‌شود. */
async function pgModifyUser(username, patch, known) {
  const cur = known || await pgFetch(`/api/user/${encodeURIComponent(username)}`);
  const body = {
    data_limit: patch.data_limit ?? cur.data_limit,
    expire: patch.expire ?? toEpochSec(cur.expire) ?? cur.expire,
    status: patch.status ?? cur.status,
    note: cur.note ?? '',
  };
  if (Array.isArray(cur.group_ids)) body.group_ids = cur.group_ids;
  let updated = null;
  try {
    updated = await pgFetch(`/api/user/${encodeURIComponent(username)}`, { method: 'PUT', body });
  } catch (e) {
    if ((e.status === 404 || e.status === 405) && cur.id)
      updated = await pgFetch(`/api/user/by-id/${encodeURIComponent(cur.id)}`, { method: 'PUT', body });
    else throw e;
  }
  pgUserCache.delete(username);
  if (!updated || typeof updated !== 'object' || !updated.username)
    updated = await pgFetch(`/api/user/${encodeURIComponent(username)}`);
  return updated;
}
/* تغییر لینک اشتراک: لینک قبلی باطل و لینک تازه ساخته می‌شود؛ کاربر تازه برگردانده می‌شود */
async function pgRevokeSub(username, userId) {
  try {
    await pgFetch(`/api/user/${encodeURIComponent(username)}/revoke_sub`, { method: 'POST' });
  } catch (e) {
    if ((e.status === 404 || e.status === 405) && userId)
      await pgFetch(`/api/user/by-id/${encodeURIComponent(userId)}/revoke_sub`, { method: 'POST' });
    else throw e;
  }
  pgUserCache.delete(username);
  return pgFetch(`/api/user/${encodeURIComponent(username)}`);
}
async function serviceOf(order) {
  const base = {
    code: order.code, gb: order.gb, days: order.days,
    username: order.pg?.username || '',
    subUrl: order.pg?.subUrl || '',
    status: order.pg?.disabledByUser ? 'disabled' : 'active', live: false,
    disabledByUser: !!order.pg?.disabledByUser,
    usedTraffic: null, dataLimit: Math.round(order.gb) * 1024 ** 3,
    expire: toEpochSec(order.pg?.expire), fetchedAt: null,
  };
  if (!base.username) return base;
  try {
    const u = await pgGetUserCached(base.username);
    return {
      ...base, live: true, fetchedAt: nowISO(),
      status: u.status || base.status,
      usedTraffic: Number.isFinite(Number(u.used_traffic)) ? Number(u.used_traffic) : null,
      dataLimit: Number.isFinite(Number(u.data_limit)) && Number(u.data_limit) > 0 ? Number(u.data_limit) : base.dataLimit,
      expire: toEpochSec(u.expire) ?? base.expire,
      subUrl: absolutize(u.subscription_url) || base.subUrl,
    };
  } catch { return base; }
}
const publicOrder = (o) => ({
  code: o.code, gb: o.gb, days: o.days, price: o.price, status: o.status,
  discountCode: o.discountCode || '', discountAmount: o.discountAmount || 0,
  createdAt: o.createdAt, decidedAt: o.decidedAt,
  rejectReason: o.status === 'rejected' ? o.rejectReason || '' : '',
  last4: o.last4 || '',
  subscriptionUrl: o.status === 'approved' ? o.pg?.subUrl || '' : '',
});

/* ───────────────────────── HTTP helpers ───────────────────────── */
function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(body);
}
async function readBody(req, maxBytes = 64 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > maxBytes) throw new Error('بدنه درخواست خیلی بزرگ است');
    chunks.push(c);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}
const publicConfig = () => ({
  pricePerGB: config.pricePerGB,
  planDays: config.planDays,
  minGB: config.minGB,
  cardNumber: config.cardNumber,
  cardName: config.cardName,
});
const findOrder = (code) => orders.find((o) => o.code === String(code || '').trim().toUpperCase());

/* ───────────────────────── کدهای تخفیف ───────────────────────── */
function validateDiscountCode(raw) {
  const c = String(raw || '').normalize('NFC').trim();
  if (!/^[\p{L}\p{N}_-]{3,30}$/u.test(c)) return null;
  return c;
}
const discountKeyOf = (c) => String(c || '').normalize('NFC').trim().toUpperCase();
/* مصرف کد از روی سفارش‌ها حساب می‌شود (سفارش ردشده مصرف حساب نمی‌شود) */
const discountUsage = (d) => orders.filter((o) => o.discountId === d.id && o.status !== 'rejected').length;
function checkDiscount(raw, user, originalPrice) {
  const d = discounts.find((x) => x.codeKey === discountKeyOf(raw));
  if (!d || !d.active) return { ok: false, error: 'این کد تخفیف معتبر نیست' };
  if (d.expiresAt && Date.parse(d.expiresAt) < Date.now()) return { ok: false, error: 'مهلت استفاده از این کد تموم شده' };
  if (d.maxUses && discountUsage(d) >= d.maxUses) return { ok: false, error: 'ظرفیت این کد تخفیف پر شده' };
  if (d.oncePerUser && user && orders.some((o) => o.discountId === d.id && o.userId === user.id && o.status !== 'rejected'))
    return { ok: false, error: 'این کد رو قبلاً استفاده کردی' };
  const amount = d.type === 'percent' ? Math.floor(originalPrice * d.value / 100) : Math.min(d.value, originalPrice);
  if (!(amount > 0)) return { ok: false, error: 'این کد روی این سفارش تخفیفی نداره' };
  return { ok: true, discount: d, amount };
}
const publicDiscount = (d) => ({ ...d, usedCount: discountUsage(d) });

/* ── اطلاعیه‌های همگانی ── */
const publicAnnouncement = (a) => ({ id: a.id, title: a.title, body: a.body, level: a.level, pinned: !!a.pinned, createdAt: a.createdAt });

/* ── نظرات مشتریان: نمایش عمومیِ کاملاً ناشناس؛ انتشار فقط با تأیید ادمین ── */
function cleanCommentText(s) {
  const t = String(s ?? '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  return t.length >= 3 && t.length <= 600 ? t : '';
}

/* ───────────────────────── بکاپ کامل فروشگاه ───────────────────────── */
const BACKUP_FILES = ['config.json', 'orders.json', 'users.json', 'chats.json', 'sessions.json', 'discounts.json', 'announcements.json', 'comments.json'];
function currentBackupObject() {
  return {
    app: 'vortexnet', kind: 'shop-backup', version: 1, exportedAt: nowISO(),
    files: {
      'config.json': config,
      'orders.json': orders,
      'users.json': users,
      'chats.json': chats,
      'sessions.json': { admin: Object.fromEntries(sessions), user: Object.fromEntries(userSessions) },
      'discounts.json': discounts,
      'announcements.json': announcements,
      'comments.json': comments,
    },
  };
}
function applyBackupObject(b, keepAdminToken, keepAdminExp) {
  const files = (b && typeof b === 'object') ? b.files : null;
  if (!files || typeof files !== 'object' || Array.isArray(files)) return null;
  const shapeOk = {
    'config.json': (v) => v && typeof v === 'object' && !Array.isArray(v),
    'orders.json': (v) => Array.isArray(v),
    'users.json': (v) => Array.isArray(v),
    'chats.json': (v) => v && typeof v === 'object' && !Array.isArray(v),
    'sessions.json': (v) => v && typeof v === 'object' && !Array.isArray(v),
    'discounts.json': (v) => Array.isArray(v),
    'announcements.json': (v) => Array.isArray(v),
    'comments.json': (v) => Array.isArray(v),
  };
  const present = BACKUP_FILES.filter((n) => files[n] !== undefined);
  if (!present.length || !present.every((n) => shapeOk[n](files[n]))) return null;
  /* اول از وضعیت فعلی یک نسخه امن نگه دار */
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const dir = path.join(DATA_DIR, 'backups');
  fs.mkdirSync(dir, { recursive: true });
  const safetyName = `before-import-${stamp}.json`;
  fs.writeFileSync(path.join(dir, safetyName), JSON.stringify(currentBackupObject(), null, 2), { mode: 0o600 });
  /* نوشتن فایل‌های واردشده و بارگذاری دوباره در حافظه */
  for (const n of present) saveJson(path.join(DATA_DIR, n), files[n], 0o600);
  if (files['config.json']) config = { ...DEFAULT_CONFIG, ...files['config.json'] };
  if (files['orders.json']) orders = files['orders.json'];
  if (files['users.json']) users = files['users.json'];
  if (files['chats.json']) chats = files['chats.json'];
  if (files['discounts.json']) discounts = files['discounts.json'];
  if (files['announcements.json']) announcements = files['announcements.json'];
  if (files['comments.json']) comments = files['comments.json'];
  if (files['sessions.json']) {
    sessions.clear(); userSessions.clear();
    for (const [tok, exp] of Object.entries(files['sessions.json'].admin || {})) if (exp > Date.now()) sessions.set(tok, exp);
    for (const [tok, s] of Object.entries(files['sessions.json'].user || {})) if (s && s.exp > Date.now()) userSessions.set(tok, s);
  }
  if (keepAdminToken) sessions.set(keepAdminToken, keepAdminExp || Date.now() + 7 * 86400_000);
  saveSessions();
  pgJwtCache = { key: '', token: '', exp: 0 };
  pgUserCache.clear();
  return { imported: present, safetyBackup: `backups/${safetyName}` };
}
const siteUrl = () => {
  const d = String(process.env.SITE_DOMAIN || '').trim().toLowerCase();
  return /^[a-z0-9.-]+$/.test(d) ? `https://${d}/` : '/';
};

let adminHtml = '';
try { adminHtml = fs.readFileSync(path.join(__dirname, 'admin.html'), 'utf8'); }
catch { adminHtml = '<h1>admin.html missing</h1>'; }

/* ───────────────────────── روتر ───────────────────────── */
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const p = url.pathname;
  res.setHeader('X-Content-Type-Options', 'nosniff');

  try {
    /* صفحه پنل ادمین */
    if (req.method === 'GET' && (p === '/' || p === '/admin' || p === '/admin/')) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' });
      return res.end(adminHtml.split('__SITE_URL__').join(siteUrl()));
    }
    if (req.method === 'GET' && p === '/healthz') return sendJson(res, 200, { ok: true });

    /* ── عمومی (فروشگاه) ── */
    if (req.method === 'GET' && p === '/api/config') return sendJson(res, 200, publicConfig());

    /* اطلاعیه‌های همگانی (عمومی) */
    if (req.method === 'GET' && p === '/api/announcements') {
      const list = announcements.filter((a) => a.active)
        .sort((x, y) => ((y.pinned ? 1 : 0) - (x.pinned ? 1 : 0)) || String(y.createdAt).localeCompare(String(x.createdAt)))
        .slice(0, 20).map(publicAnnouncement);
      return sendJson(res, 200, { announcements: list });
    }
    /* نظرات مشتریان — فقط تأییدشده‌ها و کاملاً ناشناس (بدون هیچ اطلاعاتی از نویسنده) */
    if (req.method === 'GET' && p === '/api/comments') {
      const list = comments.filter((c) => c.status === 'approved')
        .sort((x, y) => String(y.createdAt).localeCompare(String(x.createdAt)))
        .slice(0, 40).map((c) => ({ id: c.id, text: c.text, createdAt: c.createdAt }));
      return sendJson(res, 200, { comments: list });
    }

    /* ── حساب کاربری مشتری ── */
    if (req.method === 'POST' && p === '/api/auth/register') {
      if (rateLimited(`reg:${clientIp(req)}`, 10, 3600_000))
        return sendJson(res, 429, { error: 'تلاش زیاد برای ثبت‌نام؛ کمی بعد دوباره امتحان کن' });
      const b = await readBody(req);
      const name = validateName(b.name);
      if (!name) return sendJson(res, 400, { error: 'نام و نام خانوادگیت رو کامل بنویس (۲ تا ۶۰ حرف)' });
      const username = validateUsername(b.username);
      if (!username)
        return sendJson(res, 400, { error: 'نام کاربری باید ۳ تا ۲۴ حرف/عدد باشد (فارسی یا انگلیسی، بدون فاصله)' });
      const pw = String(b.password || '');
      if (pw.length < 6) return sendJson(res, 400, { error: 'رمز باید حداقل ۶ کاراکتر باشد' });
      const email = validateEmail(b.email);
      if (!email) return sendJson(res, 400, { error: 'ایمیل معتبر نیست؛ یک ایمیل واقعی وارد کن (برای بازیابی حسابت لازمه)' });
      if (findUserByKey(usernameKeyOf(username)))
        return sendJson(res, 409, { error: 'این نام کاربری قبلاً گرفته شده؛ یکی دیگه انتخاب کن' });
      if (findUserByEmail(email))
        return sendJson(res, 409, { error: 'این ایمیل قبلاً برای یک حساب ثبت شده؛ اگه حساب خودته وارد شو، یا توی صفحه ورود روی «فراموش کردم» بزن' });
      const user = {
        id: 'u_' + crypto.randomBytes(8).toString('hex'),
        username, usernameKey: usernameKeyOf(username), name, email,
        passHash: hashPassword(pw), createdAt: nowISO(),
      };
      users.push(user);
      saveUsers();
      newUserSession(res, user.id);
      return sendJson(res, 201, { ok: true, user: publicUser(user) });
    }
    if (req.method === 'POST' && p === '/api/auth/login') {
      if (rateLimited(`ulogin:${clientIp(req)}`, 12, 600_000))
        return sendJson(res, 429, { error: 'تلاش‌های ناموفق زیاد است؛ ۱۰ دقیقه صبر کن' });
      const b = await readBody(req);
      const user = findUserByKey(usernameKeyOf(b.username));
      if (!user || !verifyPassword(String(b.password || ''), user.passHash))
        return sendJson(res, 401, { error: 'نام کاربری یا رمز اشتباه است' });
      newUserSession(res, user.id);
      return sendJson(res, 200, { ok: true, user: publicUser(user) });
    }
    if (req.method === 'POST' && p === '/api/auth/logout') {
      const t = getUserToken(req);
      if (t) { userSessions.delete(t); saveSessions(); }
      res.setHeader('Set-Cookie', 'nk_user=; HttpOnly; Path=/; Max-Age=0');
      return sendJson(res, 200, { ok: true });
    }
    if (req.method === 'GET' && p === '/api/auth/me') {
      return sendJson(res, 200, { user: publicUser(getUser(req)) });
    }
    /* تکمیل/ویرایش نام و ایمیل (برای حساب‌های قبلی که ایمیل ندارن) */
    if (req.method === 'POST' && p === '/api/auth/profile') {
      const user = getUser(req);
      if (!user) return sendJson(res, 401, { error: 'اول وارد حسابت شو' });
      if (rateLimited(`profile:${user.id}`, 20, 3600_000))
        return sendJson(res, 429, { error: 'تلاش زیاد است؛ یکم صبر کن' });
      const b = await readBody(req);
      const name = validateName(b.name);
      if (!name) return sendJson(res, 400, { error: 'نام و نام خانوادگیت رو کامل بنویس (۲ تا ۶۰ حرف)' });
      const email = validateEmail(b.email);
      if (!email) return sendJson(res, 400, { error: 'ایمیل معتبر نیست؛ یک ایمیل واقعی وارد کن' });
      const emailOwner = findUserByEmail(email);
      if (emailOwner && emailOwner.id !== user.id)
        return sendJson(res, 409, { error: 'این ایمیل برای یک حساب دیگه ثبت شده' });
      user.name = name;
      user.email = email;
      delete user.phone;
      saveUsers();
      return sendJson(res, 200, { ok: true, user: publicUser(user) });
    }
    /* بازیابی حساب — مرحله ۱: ایمیل + نام کامل باید هر دو دقیقاً با ثبت‌نام بخونن.
       رمز قبلی قابل نمایش نیست (هش شده)؛ نام کاربری نشون داده می‌شه و رمز جدید ساخته می‌شه. */
    if (req.method === 'POST' && p === '/api/auth/recover/start') {
      if (rateLimited(`recover:${clientIp(req)}`, 6, 3600_000))
        return sendJson(res, 429, { error: 'تلاش برای بازیابی زیاد شده؛ یک ساعت دیگه امتحان کن یا به پشتیبانی پیام بده' });
      const b = await readBody(req);
      const deny = { error: 'حسابی با این ایمیل و نام پیدا نشد. دقیقاً همون ایمیل و نام و نام خانوادگی رو بزن که موقع ثبت‌نام دادی — اگه باز نشد به پشتیبانی پیام بده تا کمکت کنیم.' };
      const email = validateEmail(b.email);
      const name = validateName(b.name);
      if (!email || !name) return sendJson(res, 400, deny);
      if (rateLimited(`recover-mail:${email}`, 3, 3600_000))
        return sendJson(res, 429, { error: 'برای این ایمیل چند بار تلاش شده؛ یک ساعت دیگه امتحان کن یا به پشتیبانی پیام بده' });
      const user = findUserByEmail(email);
      if (!user || !user.name || nameKeyOf(user.name) !== nameKeyOf(name)) return sendJson(res, 404, deny);
      return sendJson(res, 200, { ok: true, username: user.username, token: newRecoveryToken(user.id) });
    }
    /* بازیابی حساب — مرحله ۲: ساخت رمز جدید با توکن یکبارمصرف */
    if (req.method === 'POST' && p === '/api/auth/recover/finish') {
      if (rateLimited(`recover-fin:${clientIp(req)}`, 12, 3600_000))
        return sendJson(res, 429, { error: 'تلاش زیاد شده؛ کمی صبر کن' });
      const b = await readBody(req);
      const pw = String(b.password || '');
      if (pw.length < 6) return sendJson(res, 400, { error: 'رمز جدید باید حداقل ۶ کاراکتر باشد' });
      const v = takeRecoveryToken(b.token);
      if (!v) return sendJson(res, 400, { error: 'مهلت بازیابی تموم شده (۱۰ دقیقه)؛ از اول شروع کن' });
      const user = findUserById(v.userId);
      if (!user) return sendJson(res, 404, { error: 'حساب کاربری پیدا نشد' });
      user.passHash = hashPassword(pw);
      user.lastRecoveryAt = nowISO();
      saveUsers();
      revokeUserSessions(user.id); // همهٔ دستگاه‌های قبلی از حساب خارج می‌شن
      try { // اعلان در چت پشتیبانی مشتری — تا اگه سوءاستفاده‌ای شد معلوم بشه
        const thread = getThread(user);
        pushMessage(thread, 'admin', '🔐 پیام خودکار سیستم: رمز حسابت به‌تازگی از طریق «بازیابی حساب» عوض شد و بقیه دستگاه‌ها از حسابت خارج شدن. اگه این کار تو نبوده، همین‌جا فوراً به پشتیبانی خبر بده.');
        saveChats();
      } catch { /* ignore */ }
      newUserSession(res, user.id); // ورود خودکار با رمز جدید
      return sendJson(res, 200, { ok: true, user: publicUser(user) });
    }

    /* بررسی کد تخفیف (پیش‌نمایش مبلغ نهایی قبل از کارت‌به‌کارت) */
    if (req.method === 'POST' && p === '/api/discounts/validate') {
      const user = getUser(req);
      if (!user) return sendJson(res, 401, { error: 'برای استفاده از کد تخفیف اول وارد حساب شو', needAuth: true });
      if (rateLimited(`disc:${user.id}`, 20, 600_000))
        return sendJson(res, 429, { error: 'زیاد تلاش کردی؛ چند دقیقه صبر کن' });
      const b = await readBody(req);
      const gb = Math.round(Number(b.gb));
      if (!Number.isFinite(gb) || gb < config.minGB || gb > 5000)
        return sendJson(res, 400, { error: `حجم باید حداقل ${config.minGB} گیگ باشد` });
      const originalPrice = gb * config.pricePerGB;
      const v = checkDiscount(b.code, user, originalPrice);
      if (!v.ok) return sendJson(res, 400, { error: v.error });
      return sendJson(res, 200, {
        ok: true, code: v.discount.code, type: v.discount.type, value: v.discount.value,
        discountAmount: v.amount, originalPrice, finalPrice: originalPrice - v.amount,
      });
    }

    /* ثبت نظر مشتری (ورود لازم است؛ پس از تأیید ادمین، ناشناس منتشر می‌شود) */
    if (req.method === 'POST' && p === '/api/comments') {
      const user = getUser(req);
      if (!user) return sendJson(res, 401, { error: 'برای ثبت نظر اول وارد حساب شو', needAuth: true });
      if (rateLimited(`comment:${user.id}`, 6, 3600_000))
        return sendJson(res, 429, { error: 'امروز چند نظر ثبت کردی؛ کمی بعد دوباره امتحان کن' });
      const b = await readBody(req);
      const text = cleanCommentText(b.text);
      if (!text) return sendJson(res, 400, { error: 'متن نظر باید بین ۳ تا ۶۰۰ حرف باشد' });
      const pendingMine = comments.filter((c) => c.userId === user.id && c.status === 'pending').length;
      if (pendingMine >= 3)
        return sendJson(res, 429, { error: 'سه نظرت هنوز در انتظار تأیید است؛ بعد از بررسی مدیریت می‌توانی نظر تازه ثبت کنی' });
      const c = { id: 'c_' + crypto.randomBytes(6).toString('hex'), userId: user.id, username: user.username, text, status: 'pending', createdAt: nowISO() };
      comments.unshift(c);
      saveComments();
      return sendJson(res, 201, { ok: true, status: 'pending', comment: { id: c.id, text: c.text, status: c.status, createdAt: c.createdAt } });
    }

    if (req.method === 'POST' && p === '/api/orders') {
      if (rateLimited(`order:${clientIp(req)}`, 12, 3600_000))
        return sendJson(res, 429, { error: 'تعداد سفارش‌ها زیاد است؛ کمی بعد دوباره تلاش کن' });
      const b = await readBody(req);
      const gb = Math.round(Number(b.gb));
      if (!Number.isFinite(gb) || gb < config.minGB || gb > 5000)
        return sendJson(res, 400, { error: `حجم باید حداقل ${config.minGB} گیگ باشد` });
      const user = getUser(req);
      let fields;
      if (user) {
        /* مسیر اصلی: فقط ۴ رقم آخر کارتی که با آن پرداخت کرده */
        const digits = normalizeDigits(b.last4 || '').replace(/[^\d]/g, '');
        const last4 = digits.length >= 4 ? digits.slice(-4) : '';
        if (!/^\d{4}$/.test(last4))
          return sendJson(res, 400, { error: '۴ رقم آخر کارتی که با آن پرداخت کردی را وارد کن' });
        fields = { userId: user.id, username: user.username, name: user.name || user.username, refCode: '', last4, note: cleanStr(b.note, 300) };
      } else {
        /* خرید فقط با حساب کاربری */
        return sendJson(res, 401, { error: 'برای ثبت خرید اول وارد حساب شو یا ثبت‌نام کن', needAuth: true });
      }
      const originalPrice = gb * config.pricePerGB;
      let discountCode = '', discountAmount = 0, discountId = '';
      if (String(b.discountCode || '').trim()) {
        const v = checkDiscount(b.discountCode, user, originalPrice);
        if (!v.ok) return sendJson(res, 400, { error: v.error });
        discountCode = v.discount.code;
        discountId = v.discount.id;
        discountAmount = v.amount;
      }
      const order = {
        code: newOrderCode(),
        gb, days: config.planDays,
        price: originalPrice - discountAmount,
        discountCode, discountId, discountAmount,
        ...fields,
        status: 'pending',
        createdAt: nowISO(), decidedAt: null,
        rejectReason: '',
        pg: null, provisionError: null,
      };
      orders.unshift(order);
      saveOrders();
      return sendJson(res, 201, { code: order.code, gb: order.gb, price: order.price, days: order.days, discountCode: order.discountCode, discountAmount: order.discountAmount });
    }

    /* ── پنل کاربری: سفارشات + سرویس من + چت ── */
    if (p.startsWith('/api/my/')) {
      const user = getUser(req);
      if (!user) return sendJson(res, 401, { error: 'ابتدا وارد شو', needAuth: true });

      if (req.method === 'GET' && p === '/api/my/orders') {
        return sendJson(res, 200, { orders: orders.filter((o) => o.userId === user.id).slice(0, 100).map(publicOrder) });
      }
      if (req.method === 'GET' && p === '/api/my/services') {
        const mine = orders.filter((o) => o.userId === user.id && o.status === 'approved' && o.pg);
        return sendJson(res, 200, { services: await Promise.all(mine.map(serviceOf)) });
      }
      if (req.method === 'GET' && p === '/api/my/comments') {
        return sendJson(res, 200, { comments: comments.filter((c) => c.userId === user.id).slice(0, 30).map((c) => ({ id: c.id, text: c.text, status: c.status, createdAt: c.createdAt })) });
      }
      const myCmtDel = /^\/api\/my\/comments\/([A-Za-z0-9_-]+)\/delete$/.exec(p);
      if (req.method === 'POST' && myCmtDel) {
        const idx = comments.findIndex((c) => c.id === myCmtDel[1] && c.userId === user.id);
        if (idx < 0) return sendJson(res, 404, { error: 'نظر پیدا نشد' });
        comments.splice(idx, 1);
        saveComments();
        return sendJson(res, 200, { ok: true });
      }
      if (req.method === 'GET' && p === '/api/my/chat') {
        const thread = getThread(user);
        const peek = url.searchParams.get('peek') === '1';
        const unread = unreadFor(thread, 'user');
        if (!peek && markReadFor(thread, 'user')) saveChats();
        return sendJson(res, 200, { messages: thread.messages.slice(-200), unread });
      }
      if (req.method === 'POST' && p === '/api/my/chat') {
        if (rateLimited(`chat:${user.id}`, 60, 600_000))
          return sendJson(res, 429, { error: 'کمی آرام‌تر پیام بده 🙂' });
        const b = await readBody(req);
        const text = cleanStr(b.text, 2000);
        if (!text) return sendJson(res, 400, { error: 'پیام خالی است' });
        const thread = getThread(user);
        const m = pushMessage(thread, 'user', text, replySnapshot(thread, b.replyToId));
        saveChats();
        return sendJson(res, 201, { ok: true, message: m });
      }

      /* ── عملیات روی اشتراک: تمدید رایگان زمان، تغییر لینک، توقف/روشن ── */
      const svcMatch = /^\/api\/my\/services\/([A-Za-z0-9-]+)\/(extend-time|revoke-sub|toggle)$/.exec(p);
      if (req.method === 'POST' && svcMatch) {
        if (rateLimited(`svc:${user.id}`, 30, 3600_000))
          return sendJson(res, 429, { error: 'امروز خیلی دستکاری کردی 🙂 یکم بعد دوباره امتحان کن' });
        const order = orders.find((o) => o.code === svcMatch[1].toUpperCase() && o.userId === user.id && o.status === 'approved' && o.pg?.username);
        if (!order) return sendJson(res, 404, { error: 'اشتراک پیدا نشد' });
        const b = await readBody(req);
        const username = order.pg.username;
        try {
          if (svcMatch[2] === 'extend-time') {
            const days = Math.floor(Number(b.days));
            if (!Number.isFinite(days) || days < 1 || days > 365)
              return sendJson(res, 400, { error: 'عدد روزهای تمدید بین ۱ تا ۳۶۵ باشد' });
            const cur = await pgFetch(`/api/user/${encodeURIComponent(username)}`);
            const curExp = toEpochSec(cur.expire);
            if (!curExp) return sendJson(res, 400, { error: 'این اشتراک انقضای زمانی ندارد' });
            const newExp = Math.max(curExp, Math.floor(Date.now() / 1000)) + days * 86400;
            await pgModifyUser(username, { expire: newExp }, cur);
            order.pg.expire = newExp;
            saveOrders();
          } else if (svcMatch[2] === 'toggle') {
            const on = b.on === true;
            await pgModifyUser(username, { status: on ? 'active' : 'disabled' });
            order.pg.disabledByUser = !on;
            saveOrders();
          } else { // revoke-sub
            if (rateLimited(`svc-revoke:${user.id}`, 5, 3600_000))
              return sendJson(res, 429, { error: 'تغییر لینک را زیاد انجام دادی؛ یک ساعت دیگر امتحان کن' });
            const fresh = await pgRevokeSub(username, order.pg.userId);
            if (fresh?.subscription_url) order.pg.subUrl = absolutize(fresh.subscription_url);
            saveOrders();
          }
        } catch (e) {
          return sendJson(res, 502, { error: 'در ارتباط با سرور اشتراک مشکلی پیش آمد؛ چند دقیقه دیگر دوباره تلاش کن یا به پشتیبانی پیام بده' });
        }
        return sendJson(res, 200, { ok: true, service: await serviceOf(order) });
      }
      return sendJson(res, 404, { error: 'مسیر پیدا نشد' });
    }

    if (req.method === 'POST' && p === '/api/orders/track') {
      if (rateLimited(`track:${clientIp(req)}`, 40, 3600_000))
        return sendJson(res, 429, { error: 'تلاش زیاد؛ کمی بعد دوباره امتحان کن' });
      const b = await readBody(req);
      if (rateLimited(`track-code:${String(b.code || '').trim().toUpperCase()}`, 12, 3600_000))
        return sendJson(res, 429, { error: 'برای این سفارش زیاد استعلام شده؛ یک ساعت دیگه امتحان کن' });
      const order = findOrder(b.code);
      /* احراز: ۴ رقم آخر کارت پرداخت (سفارش‌های حسابی) یا کد پیگیری رسید بانکی (سفارش‌های قدیمی) */
      const secretDigits = normalizeDigits(b.secret || '').replace(/[^\d]/g, '');
      const refDigits = order ? normalizeDigits(order.refCode || '').replace(/[^\d]/g, '') : '';
      const okSecret = !!secretDigits && (
        (order?.last4 && secretDigits.length === 4 && secretDigits === order.last4) ||
        (refDigits.length >= 4 && secretDigits === refDigits)
      );
      if (!order || !okSecret)
        return sendJson(res, 404, { error: 'سفارشی با این مشخصات پیدا نشد؛ کد پیگیری و ۴ رقم آخر کارت پرداخت (یا کد رسید بانکی) را بررسی کن' });
      return sendJson(res, 200, {
        code: order.code, status: order.status, gb: order.gb, days: order.days, price: order.price,
        discountCode: order.discountCode || '', discountAmount: order.discountAmount || 0,
        createdAt: order.createdAt, decidedAt: order.decidedAt,
        rejectReason: order.status === 'rejected' ? order.rejectReason : '',
        subscriptionUrl: order.pg?.subUrl || '',
        username: order.pg?.username || '',
        expireAt: order.pg?.expire ? new Date(order.pg.expire * 1000).toISOString() : null,
      });
    }

    /* ── ادمین: وضعیت/راه‌اندازی/ورود ── */
    if (req.method === 'GET' && p === '/api/admin/state') {
      return sendJson(res, 200, { configured: !!config.adminPassHash, authed: !!getSession(req) });
    }
    if (req.method === 'POST' && p === '/api/admin/setup') {
      if (config.adminPassHash) return sendJson(res, 409, { error: 'راه‌اندازی قبلاً انجام شده است' });
      const b = await readBody(req);
      const pw = String(b.password || '');
      if (pw.length < 10) return sendJson(res, 400, { error: 'رمز ادمین باید حداقل ۱۰ کاراکتر باشد' });
      config.adminPassHash = hashPassword(pw);
      if (b.pgBaseUrl) config.pgBaseUrl = normalizePgBase(cleanStr(b.pgBaseUrl, 200));
      if (b.pgApiKey) config.pgApiKey = cleanStr(b.pgApiKey, 200);
      if (b.pgUsername) config.pgUsername = cleanStr(b.pgUsername, 120);
      if (b.pgPassword) config.pgPassword = String(b.pgPassword).slice(0, 300);
      saveConfig();
      newSession(res);
      return sendJson(res, 200, { ok: true });
    }
    if (req.method === 'POST' && p === '/api/admin/login') {
      if (rateLimited(`login:${clientIp(req)}`, 8, 600_000))
        return sendJson(res, 429, { error: 'تلاش‌های ناموفق زیاد است؛ ۱۰ دقیقه صبر کن' });
      const b = await readBody(req);
      if (!config.adminPassHash) return sendJson(res, 409, { error: 'ابتدا راه‌اندازی اولیه را انجام بده' });
      if (!verifyPassword(String(b.password || ''), config.adminPassHash))
        return sendJson(res, 401, { error: 'رمز اشتباه است' });
      newSession(res);
      return sendJson(res, 200, { ok: true });
    }
    if (req.method === 'POST' && p === '/api/admin/logout') {
      const t = getSession(req);
      if (t) { sessions.delete(t); saveSessions(); }
      res.setHeader('Set-Cookie', 'nk_admin=; HttpOnly; Path=/; Max-Age=0');
      return sendJson(res, 200, { ok: true });
    }

    /* ── ادمین: بخش‌های محافظت‌شده ── */
    if (p.startsWith('/api/admin/')) {
      if (!getSession(req)) return sendJson(res, 401, { error: 'ابتدا وارد شو' });

      if (req.method === 'GET' && p === '/api/admin/orders') {
        const status = url.searchParams.get('status') || '';
        const q = (url.searchParams.get('q') || '').trim().toLowerCase();
        let list = orders;
        if (status) list = list.filter((o) => o.status === status);
        if (q) list = list.filter((o) => o.code.toLowerCase().includes(q) || (o.name || '').toLowerCase().includes(q) || (o.username || '').toLowerCase().includes(q) || (o.last4 || '') === normalizeDigits(q) || (o.refCode || '') === normalizeDigits(q));
        const counts = {
          total: orders.length,
          pending: orders.filter((o) => o.status === 'pending').length,
          approved: orders.filter((o) => o.status === 'approved').length,
          rejected: orders.filter((o) => o.status === 'rejected').length,
          revenueApproved: orders.filter((o) => o.status === 'approved').reduce((s, o) => s + o.price, 0),
          users: users.length,
          chatsUnread: Object.values(chats).reduce((s, t) => s + unreadFor(t, 'admin'), 0),
          commentsPending: comments.filter((c) => c.status === 'pending').length,
        };
        return sendJson(res, 200, { orders: list.slice(0, 300), counts });
      }

      /* ── کدهای تخفیف ── */
      if (req.method === 'GET' && p === '/api/admin/discounts') {
        return sendJson(res, 200, { discounts: discounts.map(publicDiscount) });
      }
      if (req.method === 'POST' && p === '/api/admin/discounts') {
        const b = await readBody(req);
        const code = validateDiscountCode(b.code);
        if (!code) return sendJson(res, 400, { error: 'کد باید ۳ تا ۳۰ حرف/عدد باشد (بدون فاصله)' });
        if (discounts.some((x) => x.codeKey === discountKeyOf(code)))
          return sendJson(res, 409, { error: 'این کد قبلاً ساخته شده' });
        const type = b.type === 'fixed' ? 'fixed' : 'percent';
        const value = Math.floor(Number(b.value));
        if (!Number.isFinite(value) || (type === 'percent' ? value < 1 || value > 100 : value < 1 || value > 100000000))
          return sendJson(res, 400, { error: type === 'percent' ? 'درصد باید بین ۱ تا ۱۰۰ باشد' : 'مبلغ تخفیف معتبر نیست' });
        let maxUses = null;
        if (b.maxUses !== null && b.maxUses !== undefined && String(b.maxUses) !== '') {
          maxUses = Math.floor(Number(b.maxUses));
          if (!Number.isFinite(maxUses) || maxUses < 1 || maxUses > 100000)
            return sendJson(res, 400, { error: 'حداکثر تعداد استفاده معتبر نیست' });
        }
        let expiresAt = null;
        if (b.expiresAt) {
          const t = Date.parse(b.expiresAt);
          if (!Number.isFinite(t)) return sendJson(res, 400, { error: 'تاریخ انقضا معتبر نیست' });
          expiresAt = new Date(t).toISOString();
        }
        const d = {
          id: 'd_' + crypto.randomBytes(6).toString('hex'),
          code, codeKey: discountKeyOf(code), type, value, maxUses,
          oncePerUser: !!b.oncePerUser, expiresAt,
          active: true, note: cleanStr(b.note, 120), createdAt: nowISO(),
        };
        discounts.unshift(d);
        saveDiscounts();
        return sendJson(res, 201, { ok: true, discount: publicDiscount(d) });
      }
      const discMatch = /^\/api\/admin\/discounts\/([A-Za-z0-9_-]+)\/(toggle|delete)$/.exec(p);
      if (req.method === 'POST' && discMatch) {
        const idx = discounts.findIndex((x) => x.id === discMatch[1]);
        if (idx < 0) return sendJson(res, 404, { error: 'کد تخفیف پیدا نشد' });
        if (discMatch[2] === 'delete') discounts.splice(idx, 1);
        else discounts[idx].active = !discounts[idx].active;
        saveDiscounts();
        return sendJson(res, 200, { ok: true });
      }

      /* ── اطلاعیه‌های همگانی (ادمین) ── */
      if (req.method === 'GET' && p === '/api/admin/announcements') {
        return sendJson(res, 200, { announcements });
      }
      if (req.method === 'POST' && p === '/api/admin/announcements') {
        const b = await readBody(req);
        const title = cleanStr(b.title, 120);
        const body = cleanStr(b.body, 2000);
        if (!title) return sendJson(res, 400, { error: 'عنوان اطلاعیه خالی است' });
        if (!body) return sendJson(res, 400, { error: 'متن اطلاعیه خالی است' });
        const a = {
          id: 'a_' + crypto.randomBytes(6).toString('hex'),
          title, body,
          level: b.level === 'important' ? 'important' : 'normal',
          pinned: !!b.pinned, active: true,
          createdAt: nowISO(), updatedAt: nowISO(),
        };
        announcements.unshift(a);
        saveAnnouncements();
        return sendJson(res, 201, { ok: true, announcement: a });
      }
      const annMatch = /^\/api\/admin\/announcements\/([A-Za-z0-9_-]+)\/(toggle|pin|delete|edit)$/.exec(p);
      if (req.method === 'POST' && annMatch) {
        const idx = announcements.findIndex((x) => x.id === annMatch[1]);
        if (idx < 0) return sendJson(res, 404, { error: 'اطلاعیه پیدا نشد' });
        const act = annMatch[2];
        if (act === 'delete') announcements.splice(idx, 1);
        else if (act === 'toggle') announcements[idx].active = !announcements[idx].active;
        else if (act === 'pin') announcements[idx].pinned = !announcements[idx].pinned;
        else { // edit
          const b = await readBody(req);
          const title = cleanStr(b.title, 120);
          const body = cleanStr(b.body, 2000);
          if (!title || !body) return sendJson(res, 400, { error: 'عنوان و متن اطلاعیه نباید خالی باشد' });
          announcements[idx].title = title;
          announcements[idx].body = body;
          announcements[idx].level = b.level === 'important' ? 'important' : 'normal';
          if (b.pinned !== undefined) announcements[idx].pinned = !!b.pinned;
          announcements[idx].updatedAt = nowISO();
        }
        saveAnnouncements();
        return sendJson(res, 200, { ok: true });
      }

      /* ── نظرات مشتریان (ادمین: بررسی و تأیید) ── */
      if (req.method === 'GET' && p === '/api/admin/comments') {
        const list = comments.slice().sort((x, y) =>
          ((x.status === 'pending' ? 0 : 1) - (y.status === 'pending' ? 0 : 1)) ||
          String(y.createdAt).localeCompare(String(x.createdAt)));
        return sendJson(res, 200, { comments: list.slice(0, 300), pending: comments.filter((c) => c.status === 'pending').length });
      }
      const cmtMatch = /^\/api\/admin\/comments\/([A-Za-z0-9_-]+)\/(approve|hide|delete)$/.exec(p);
      if (req.method === 'POST' && cmtMatch) {
        const idx = comments.findIndex((x) => x.id === cmtMatch[1]);
        if (idx < 0) return sendJson(res, 404, { error: 'نظر پیدا نشد' });
        if (cmtMatch[2] === 'delete') comments.splice(idx, 1);
        else if (cmtMatch[2] === 'approve') comments[idx].status = 'approved';
        else comments[idx].status = 'pending';
        saveComments();
        return sendJson(res, 200, { ok: true });
      }

      const actMatch = /^\/api\/admin\/orders\/([A-Za-z0-9-]+)\/(approve|reject)$/.exec(p);
      if (req.method === 'POST' && actMatch) {
        const order = findOrder(actMatch[1]);
        if (!order) return sendJson(res, 404, { error: 'سفارش پیدا نشد' });
        const action = actMatch[2];

        if (action === 'reject') {
          if (order.status === 'approved') return sendJson(res, 409, { error: 'این سفارش قبلاً تأیید و کانفیگ آن ساخته شده است' });
          const b = await readBody(req);
          order.status = 'rejected';
          order.rejectReason = cleanStr(b.reason, 200);
          order.decidedAt = nowISO();
          saveOrders();
          return sendJson(res, 200, { ok: true, order });
        }

        /* approve → ساخت کانفیگ در پاسارگارد */
        if (order.status === 'approved' && order.pg?.subUrl)
          return sendJson(res, 200, { ok: true, order, note: 'قبلاً ساخته شده بود' });
        if (order.status === 'rejected')
          return sendJson(res, 409, { error: 'سفارش رد شده را نمی‌توان تأیید کرد' });
        try {
          const pg = await pgCreateUser(order);
          order.pg = pg;
          order.provisionError = null;
          order.status = 'approved';
          order.decidedAt = nowISO();
          saveOrders();
          return sendJson(res, 200, { ok: true, order });
        } catch (e) {
          order.provisionError = { at: nowISO(), message: e.message };
          saveOrders();
          return sendJson(res, 502, { error: `خطا در ساخت کانفیگ: ${e.message}`, order });
        }
      }

      /* ── ادمین: چت با مشتری‌ها ── */
      if (req.method === 'GET' && p === '/api/admin/chats') {
        const list = Object.values(chats)
          .map((t) => ({
            userId: t.userId, username: t.username, name: findUserById(t.userId)?.name || '', updatedAt: t.updatedAt,
            unread: unreadFor(t, 'admin'),
            last: t.messages.length ? t.messages[t.messages.length - 1] : null,
          }))
          .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
        return sendJson(res, 200, { chats: list, totalUnread: list.reduce((s, c) => s + c.unread, 0) });
      }
      const chatMatch = /^\/api\/admin\/chats\/([A-Za-z0-9_-]+)$/.exec(p);
      if (chatMatch && (req.method === 'GET' || req.method === 'POST')) {
        const target = findUserById(chatMatch[1]);
        if (!target) return sendJson(res, 404, { error: 'کاربر پیدا نشد' });
        const thread = getThread(target);
        if (req.method === 'GET') {
          if (url.searchParams.get('peek') !== '1' && markReadFor(thread, 'admin')) saveChats();
          return sendJson(res, 200, { username: thread.username, messages: thread.messages.slice(-300) });
        }
        const b = await readBody(req);
        const text = cleanStr(b.text, 2000);
        if (!text) return sendJson(res, 400, { error: 'پیام خالی است' });
        const m = pushMessage(thread, 'admin', text, replySnapshot(thread, b.replyToId));
        saveChats();
        return sendJson(res, 201, { ok: true, message: m });
      }

      if (req.method === 'GET' && p === '/api/admin/settings') {
        const { pgApiKey, pgPassword, adminPassHash, ...rest } = config;
        return sendJson(res, 200, {
          ...rest,
          pgApiKeyMasked: pgApiKey ? `••••••••${String(pgApiKey).slice(-4)}` : '',
          hasApiKey: !!pgApiKey,
          hasPgPassword: !!pgPassword,
        });
      }
      if (req.method === 'POST' && p === '/api/admin/settings') {
        const b = await readBody(req);
        const num = (v, min, max, cur) => {
          const n = Math.round(Number(v));
          return Number.isFinite(n) && n >= min && n <= max ? n : cur;
        };
        config.pricePerGB = num(b.pricePerGB, 0, 10_000_000, config.pricePerGB);
        config.planDays = num(b.planDays, 1, 3650, config.planDays);
        config.minGB = num(b.minGB, 1, 5000, config.minGB);
        if (b.cardNumber) config.cardNumber = normalizeDigits(b.cardNumber).replace(/[^\d]/g, '').slice(0, 19);
        if (b.cardName) config.cardName = cleanStr(b.cardName, 80);
        if (b.pgBaseUrl !== undefined) config.pgBaseUrl = normalizePgBase(cleanStr(b.pgBaseUrl, 200));
        if (b.pgPublicBaseUrl !== undefined) config.pgPublicBaseUrl = normalizePgBase(cleanStr(b.pgPublicBaseUrl, 200));
        if (b.pgApiKey) config.pgApiKey = cleanStr(b.pgApiKey, 300);
        if (b.pgUsername !== undefined) config.pgUsername = cleanStr(b.pgUsername, 120);
        if (b.pgPassword) config.pgPassword = String(b.pgPassword).slice(0, 300);
        if (Array.isArray(b.pgGroupIds)) config.pgGroupIds = b.pgGroupIds.map(Number).filter((n) => Number.isFinite(n) && n > 0);
        saveConfig();
        return sendJson(res, 200, { ok: true, settings: publicConfig() });
      }
      if (req.method === 'POST' && p === '/api/admin/test-pg') {
        const b = await readBody(req);
        const backup = { pgBaseUrl: config.pgBaseUrl, pgApiKey: config.pgApiKey, pgUsername: config.pgUsername, pgPassword: config.pgPassword };
        if (b.pgBaseUrl) config.pgBaseUrl = normalizePgBase(cleanStr(b.pgBaseUrl, 200));
        if (b.pgApiKey) config.pgApiKey = cleanStr(b.pgApiKey, 300);
        if (b.pgUsername) config.pgUsername = cleanStr(b.pgUsername, 120);
        if (b.pgPassword) config.pgPassword = String(b.pgPassword).slice(0, 300);
        try {
          const data = await pgFetch('/api/groups/simple', { query: { all: true } });
          return sendJson(res, 200, { ok: true, groups: data?.groups || [] });
        } catch (e) {
          return sendJson(res, 502, { error: e.message });
        } finally {
          // تست اتصال نباید تنظیمات ذخیره‌شده را در حافظه دست‌کاری کند
          config.pgBaseUrl = backup.pgBaseUrl;
          config.pgApiKey = backup.pgApiKey;
          config.pgUsername = backup.pgUsername;
          config.pgPassword = backup.pgPassword;
        }
      }
      if (req.method === 'POST' && p === '/api/admin/change-password') {
        const b = await readBody(req);
        if (!verifyPassword(String(b.oldPassword || ''), config.adminPassHash))
          return sendJson(res, 401, { error: 'رمز فعلی اشتباه است' });
        if (String(b.newPassword || '').length < 10)
          return sendJson(res, 400, { error: 'رمز جدید باید حداقل ۱۰ کاراکتر باشد' });
        config.adminPassHash = hashPassword(String(b.newPassword));
        saveConfig();
        return sendJson(res, 200, { ok: true });
      }
      if (req.method === 'GET' && p === '/api/admin/backup') {
        const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
        res.writeHead(200, {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Disposition': `attachment; filename="vortexnet-backup-${stamp}.json"`,
          'Cache-Control': 'no-store',
        });
        return res.end(JSON.stringify(currentBackupObject(), null, 2));
      }
      if (req.method === 'POST' && p === '/api/admin/backup/import') {
        let b;
        try { b = await readBody(req, 25 * 1024 * 1024); }
        catch { return sendJson(res, 400, { error: 'فایل بکاپ خوانا نیست یا خیلی بزرگ است' }); }
        if (!b || b.kind !== 'shop-backup')
          return sendJson(res, 400, { error: 'این فایل، بکاپ فروشگاه ورتکس‌نت نیست' });
        const curTok = getSession(req);
        const out = applyBackupObject(b, curTok, curTok ? sessions.get(curTok) : 0);
        if (!out) return sendJson(res, 400, { error: 'ساختار فایل بکاپ معتبر نیست' });
        console.log(`[norkhiz] backup imported (${out.imported.join(', ')}); safety copy: ${out.safetyBackup}`);
        return sendJson(res, 200, { ok: true, ...out });
      }
    }

    return sendJson(res, 404, { error: 'مسیر پیدا نشد' });
  } catch (e) {
    console.error('[norkhiz]', e);
    if (!res.headersSent) sendJson(res, 500, { error: `خطای سرور: ${e.message}` });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[norkhiz] shop API + admin listening on :${PORT}  (data: ${DATA_DIR})`);
  if (!config.adminPassHash) console.log('[norkhiz] first run: open the admin panel and complete setup');
});
