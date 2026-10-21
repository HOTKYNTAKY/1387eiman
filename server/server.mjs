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
const REPORTS_FILE = path.join(DATA_DIR, 'reports.json');

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
  panels: null,              // پنل‌های پاسارگارد (از روی تنظیمات قدیمی خودکار ساخته می‌شود)
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
let serviceReports = loadJson(REPORTS_FILE, []);     // [{id, code, userId, username, panelId, panelName, text, status:'open'|'done', createdAt, resolvedAt}]
if (!fs.existsSync(CONFIG_FILE)) saveJson(CONFIG_FILE, config, 0o600);
const saveConfig = () => saveJson(CONFIG_FILE, config, 0o600);
const saveOrders = () => saveJson(ORDERS_FILE, orders, 0o600);
const saveUsers = () => saveJson(USERS_FILE, users, 0o600);
const saveChats = () => saveJson(CHATS_FILE, chats, 0o600);
const saveDiscounts = () => saveJson(DISCOUNTS_FILE, discounts, 0o600);
const saveAnnouncements = () => saveJson(ANN_FILE, announcements, 0o600);
const saveComments = () => saveJson(COMMENTS_FILE, comments, 0o600);
const saveReports = () => saveJson(REPORTS_FILE, serviceReports, 0o600);
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
/* ───────────────── پنل‌های پاسارگارد (چندپنلی) ─────────────────
   هر پنل: {id, name(اسمی که مشتری موقع خرید می‌بیند), pricePerGB, enabled(قابل خرید),
   baseUrl, publicBaseUrl, apiKey, username, password, groupIds}
   سفارش روی پنلی ساخته می‌شود که مشتری موقع خرید انتخاب کرده (order.panelId).
   تنظیمات قدیمیِ تک‌پنله (pgBaseUrl و…) خودکار به «پنل اصلی» تبدیل و برای سازگاری
   با بکاپ‌های قدیمی با پنل اول همگام نگه داشته می‌شوند. */
const newPanelId = () => 'pn_' + crypto.randomBytes(4).toString('hex');
const cleanGroupIds = (v) => (Array.isArray(v) ? v.map(Number).filter((n) => Number.isFinite(n) && n > 0) : []);
const cleanPrice = (v, fallback) => {
  const n = Math.round(Number(v));
  return Number.isFinite(n) && n >= 0 && n <= 10_000_000 ? n : fallback;
};
function sanitizePanel(raw, cur = null) {
  const b = raw && typeof raw === 'object' ? raw : {};
  return {
    id: cur?.id || newPanelId(),
    name: cleanStr(b.name !== undefined ? b.name : cur?.name, 60),
    pricePerGB: cleanPrice(b.pricePerGB, cur?.pricePerGB ?? config.pricePerGB ?? 4000),
    enabled: b.enabled !== undefined ? !!b.enabled : cur ? !!cur.enabled : true,
    baseUrl: normalizePgBase(cleanStr(b.baseUrl !== undefined ? b.baseUrl : cur?.baseUrl, 200)),
    publicBaseUrl: normalizePgBase(cleanStr(b.publicBaseUrl !== undefined ? b.publicBaseUrl : cur?.publicBaseUrl, 200)),
    apiKey: b.apiKey ? cleanStr(b.apiKey, 300) : cur?.apiKey || '',
    username: cleanStr(b.username !== undefined ? b.username : cur?.username, 120),
    password: b.password ? String(b.password).slice(0, 300) : cur?.password || '',
    groupIds: b.groupIds !== undefined ? cleanGroupIds(b.groupIds) : cleanGroupIds(cur?.groupIds),
  };
}
const panelsOf = () => (Array.isArray(config.panels) ? config.panels : []);
const panelById = (id) => panelsOf().find((p) => p.id === id) || null;
const defaultPanel = () => panelsOf().find((p) => p.enabled) || panelsOf()[0] || null;
const panelPrice = (p) => (p && Number(p.pricePerGB) > 0 ? Number(p.pricePerGB) : config.pricePerGB || 4000);
/* پنل‌هایی که به مشتری برای خرید پیشنهاد می‌شوند (فعال + دارای آدرس) */
const salePanels = () => {
  const list = panelsOf().filter((p) => p.enabled && normalizePgBase(p.baseUrl));
  return list.length ? list : panelsOf().filter((p) => p.enabled);
};
/* پنل مربوط به یک سفارش؛ سفارش‌های قدیمی (بدون panelId) روی پنل اول‌اند */
const panelForOrder = (o) => panelById(o?.panelId) || panelById(o?.pg?.panelId) || panelsOf()[0] || null;
const panelNameOf = (o) => panelForOrder(o)?.name || o?.panelName || '';
/* همگام‌سازی دوسویه با فیلدهای قدیمی تک‌پنله (برای بکاپ/راه‌اندازی قدیمی) */
function syncLegacyFromFirstPanel() {
  const p0 = panelsOf()[0];
  if (!p0) return;
  config.pgBaseUrl = p0.baseUrl; config.pgPublicBaseUrl = p0.publicBaseUrl;
  config.pgApiKey = p0.apiKey; config.pgUsername = p0.username;
  config.pgPassword = p0.password; config.pgGroupIds = p0.groupIds;
}
function syncFirstPanelFromLegacy() {
  const p0 = panelsOf()[0];
  if (!p0) return;
  p0.baseUrl = config.pgBaseUrl || ''; p0.publicBaseUrl = config.pgPublicBaseUrl || '';
  p0.apiKey = config.pgApiKey || ''; p0.username = config.pgUsername || '';
  p0.password = config.pgPassword || ''; p0.groupIds = cleanGroupIds(config.pgGroupIds);
}
function ensurePanels() {
  if (!Array.isArray(config.panels) || !config.panels.length) {
    config.panels = [sanitizePanel({
      name: 'پنل اصلی', pricePerGB: config.pricePerGB, enabled: true,
      baseUrl: config.pgBaseUrl, publicBaseUrl: config.pgPublicBaseUrl,
      apiKey: config.pgApiKey, username: config.pgUsername,
      password: config.pgPassword, groupIds: config.pgGroupIds,
    })];
    config.panels[0].id = 'pn_main';
    saveConfig();
  } else {
    config.panels = config.panels.map((p) => sanitizePanel(p, p));
  }
}
const publicPanel = (p) => ({ id: p.id, name: p.name, pricePerGB: panelPrice(p) });
const adminPanelView = (p) => ({
  id: p.id, name: p.name, pricePerGB: panelPrice(p), enabled: !!p.enabled,
  baseUrl: p.baseUrl || '', publicBaseUrl: p.publicBaseUrl || '',
  username: p.username || '', groupIds: cleanGroupIds(p.groupIds),
  hasApiKey: !!p.apiKey, apiKeyMasked: p.apiKey ? `••••••••${String(p.apiKey).slice(-4)}` : '',
  hasPassword: !!p.password,
  ordersCount: orders.filter((o) => (o.panelId || o.pg?.panelId) === p.id).length,
});
function pgBase(panel) {
  return normalizePgBase(panel?.baseUrl || '');
}
ensurePanels();
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
const pgInsecureHosts = new Set(); // مبدأهایی با گواهی self-signed (جدا برای هر پنل)
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
      out = await pgHttpOnce(target, { method: m, headers, payload: pl, insecure: pgInsecureHosts.has(target.origin) });
    } catch (e) {
      const code = e.code || e.cause?.code || '';
      if (target.protocol === 'https:' && !pgInsecureHosts.has(target.origin) && PG_CERT_ERR_CODES.has(code)) {
        pgInsecureHosts.add(target.origin);
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
const pgJwtCaches = new Map(); // panelId -> {key, token, exp}
const pgUseJwt = (panel) => !!panel && !panel.apiKey && !!(panel.username && panel.password);
async function pgGetJwt(panel, force = false) {
  const ck = pgBase(panel) + '|' + panel.username + '|' +
    crypto.createHash('sha256').update(String(panel.password || '')).digest('hex').slice(0, 16);
  const cache = pgJwtCaches.get(panel.id) || { key: '', token: '', exp: 0 };
  if (!force && cache.token && cache.key === ck && Date.now() < cache.exp) return cache.token;
  const payload = new URLSearchParams({ username: String(panel.username), password: String(panel.password) }).toString();
  const res = await pgRequest(new URL(pgBase(panel) + '/api/admin/token'), {
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
  pgJwtCaches.set(panel.id, { key: ck, token: data.access_token, exp });
  return data.access_token;
}
async function pgFetch(panel, pathname, { method = 'GET', body, query } = {}) {
  const base = pgBase(panel);
  const useJwt = pgUseJwt(panel);
  if (!panel || !base || (!panel.apiKey && !useJwt))
    throw new Error(`اتصال پاسارگارد${panel?.name ? ` (${panel.name})` : ''} تنظیم نشده است (آدرس پنل و کلید API — یا نام کاربری/رمز پنل — لازم است)`);
  const url = new URL(base + pathname);
  if (query) for (const [k, v] of Object.entries(query)) if (v !== undefined) url.searchParams.set(k, String(v));
  const payload = body ? JSON.stringify(body) : undefined;
  const call = (token) => pgRequest(url, {
    method,
    payload,
    headers: {
      ...(panel.apiKey ? { 'X-API-Key': panel.apiKey } : { 'Authorization': `Bearer ${token}` }),
      'Accept': 'application/json',
      ...(payload ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } : {}),
    },
  });
  let res;
  try {
    res = await call(useJwt ? await pgGetJwt(panel) : null);
    if (useJwt && res.status === 401) res = await call(await pgGetJwt(panel, true)); // توکن منقضی شده؛ ورود تازه و یک تلاش دیگر
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
const absolutize = (panel, u) => {
  if (!u) return '';
  try {
    const base = pgBase(panel);
    const abs = new URL(u, base + '/');
    const pub = normalizePgBase(panel?.publicBaseUrl);
    if (pub && abs.hostname === new URL(base + '/').hostname)
      return new URL(abs.pathname + abs.search + abs.hash, pub + '/').toString();
    return abs.toString();
  } catch { return u; }
};
async function pgAllGroupIds(panel) {
  const data = await pgFetch(panel, '/api/groups/simple', { query: { all: true } });
  return (data?.groups || []).map((g) => g.id);
}
const pgUsernameFor = (order) => 'vx_' + order.code.replace(/^(NK|VX)-/, '').toLowerCase();
/* ساخت کاربر اشتراک روی یک پنل مشخص؛ opts برای انتقال بین پنل‌ها (حجم/روز دلخواه) است */
async function pgCreateUser(panel, order, opts = {}) {
  if (!panel) throw new Error('هیچ پنل پاسارگاردی تنظیم نشده است');
  const groupIds = Array.isArray(panel.groupIds) && panel.groupIds.length
    ? panel.groupIds
    : await pgAllGroupIds(panel);
  const username = pgUsernameFor(order);
  const gb = Number(opts.gb ?? order.gb);
  const days = Number(opts.days ?? order.days ?? config.planDays);
  const payload = {
    username,
    data_limit: Math.round(gb * 1024 ** 3),
    expire: Math.floor(Date.now() / 1000) + Math.round(days) * 86400,
    status: 'active',
    group_ids: groupIds,
    note: `VortexNet | ${order.code} | ${gb}GB | ${order.username ? '@' + order.username : order.name || ''}${order.last4 ? ' | card..' + order.last4 : ''}${opts.noteSuffix || ''}`,
  };
  const pack = (user) => ({
    userId: user.id, username: user.username || username,
    subUrl: absolutize(panel, user.subscription_url),
    expire: user.expire ?? payload.expire,
    panelId: panel.id, dataLimit: payload.data_limit, disabledByUser: false, lastUsage: null,
  });
  try {
    return pack(await pgFetch(panel, '/api/user', { method: 'POST', body: payload }));
  } catch (e) {
    if (e.status === 409) {
      // نام کاربری روی این پنل هست (تأیید دوباره یا انتقال نیمه‌کارهٔ قبلی)
      const cur = await pgFetch(panel, `/api/user/${encodeURIComponent(username)}`);
      if (opts.relimit) {
        // موقع انتقال: حجم/انقضای موجود را دقیقاً به مقادیر انتقال تنظیم کن
        return pack(await pgModifyUser(panel, username, { data_limit: payload.data_limit, expire: payload.expire, status: 'active' }, cur));
      }
      return pack(cur);
    }
    throw e;
  }
}

/* وضعیت زندهٔ اشتراک (مصرف/انقضا) از پاسارگارد — با کش کوتاه */
const pgUserCache = new Map(); // panelId:username -> {at, data}
async function pgGetUserCached(panel, username) {
  const key = `${panel?.id || ''}:${username}`;
  const hit = pgUserCache.get(key);
  if (hit && Date.now() - hit.at < 15_000) return hit.data;
  const data = await pgFetch(panel, `/api/user/${encodeURIComponent(username)}`);
  pgUserCache.set(key, { at: Date.now(), data });
  return data;
}
const pgUserCacheDel = (panel, username) => pgUserCache.delete(`${panel?.id || ''}:${username}`);
/* تغییر کاربر پنل با حفظ بقیهٔ مشخصات فعلی (امن در برابر PUT جایگزینی کامل).
   اول مسیر نام کاربری؛ اگر پنل نداشت (404/405) مسیر by-id امتحان می‌شود. */
async function pgModifyUser(panel, username, patch, known) {
  const cur = known || await pgFetch(panel, `/api/user/${encodeURIComponent(username)}`);
  const body = {
    data_limit: patch.data_limit ?? cur.data_limit,
    expire: patch.expire ?? toEpochSec(cur.expire) ?? cur.expire,
    status: patch.status ?? cur.status,
    note: cur.note ?? '',
  };
  if (Array.isArray(cur.group_ids)) body.group_ids = cur.group_ids;
  let updated = null;
  try {
    updated = await pgFetch(panel, `/api/user/${encodeURIComponent(username)}`, { method: 'PUT', body });
  } catch (e) {
    if ((e.status === 404 || e.status === 405) && cur.id)
      updated = await pgFetch(panel, `/api/user/by-id/${encodeURIComponent(cur.id)}`, { method: 'PUT', body });
    else throw e;
  }
  pgUserCacheDel(panel, username);
  if (!updated || typeof updated !== 'object' || !updated.username)
    updated = await pgFetch(panel, `/api/user/${encodeURIComponent(username)}`);
  return updated;
}
/* تغییر لینک اشتراک: لینک قبلی باطل و لینک تازه ساخته می‌شود؛ کاربر تازه برگردانده می‌شود */
async function pgRevokeSub(panel, username, userId) {
  try {
    await pgFetch(panel, `/api/user/${encodeURIComponent(username)}/revoke_sub`, { method: 'POST' });
  } catch (e) {
    if ((e.status === 404 || e.status === 405) && userId)
      await pgFetch(panel, `/api/user/by-id/${encodeURIComponent(userId)}/revoke_sub`, { method: 'POST' });
    else throw e;
  }
  pgUserCacheDel(panel, username);
  return pgFetch(panel, `/api/user/${encodeURIComponent(username)}`);
}
async function serviceOf(order) {
  const panel = panelForOrder(order);
  const base = {
    code: order.code, gb: order.gb, days: order.days,
    panelId: panel?.id || order.panelId || '', panelName: panel?.name || order.panelName || '',
    username: order.pg?.username || '',
    subUrl: order.pg?.subUrl || '',
    status: order.pg?.disabledByUser ? 'disabled' : 'active', live: false,
    disabledByUser: !!order.pg?.disabledByUser,
    usedTraffic: order.pg?.lastUsage?.usedTraffic ?? null,
    dataLimit: order.pg?.lastUsage?.dataLimit || order.pg?.dataLimit || Math.round(order.gb) * 1024 ** 3,
    expire: toEpochSec(order.pg?.lastUsage?.expire) ?? toEpochSec(order.pg?.expire),
    fetchedAt: order.pg?.lastUsage?.at || null,
  };
  if (!base.username || !panel) return base;
  try {
    const u = await pgGetUserCached(panel, base.username);
    const live = {
      ...base, live: true, fetchedAt: nowISO(),
      status: u.status || base.status,
      usedTraffic: Number.isFinite(Number(u.used_traffic)) ? Number(u.used_traffic) : null,
      dataLimit: Number.isFinite(Number(u.data_limit)) && Number(u.data_limit) > 0 ? Number(u.data_limit) : base.dataLimit,
      expire: toEpochSec(u.expire) ?? base.expire,
      subUrl: absolutize(panel, u.subscription_url) || base.subUrl,
    };
    /* آخرین مصرف را روی سفارش ذخیره کن تا اگر روزی پنل قطع شد، «انتقال به پنل دیگر»
       بتواند حجم و زمان باقی‌مانده را از همین آخرین اطلاعات حساب کند */
    const prev = order.pg.lastUsage;
    if (!prev || prev.usedTraffic !== live.usedTraffic || prev.dataLimit !== live.dataLimit ||
        prev.expire !== live.expire || Date.now() - Date.parse(prev.at || 0) > 120_000) {
      order.pg.lastUsage = {
        usedTraffic: live.usedTraffic, dataLimit: live.dataLimit,
        expire: live.expire, status: live.status, at: live.fetchedAt,
      };
      if (live.expire) order.pg.expire = live.expire;
      if (live.dataLimit) order.pg.dataLimit = live.dataLimit;
      saveOrders();
    }
    return live;
  } catch { return base; }
}
/* حجم/زمان باقی‌ماندهٔ یک اشتراک: اول زنده از پنل؛ نشد از آخرین مصرف ذخیره‌شده؛ نشد حجم اصلی خرید.
   مبنای پیش‌فرض «انتقال به پنل دیگر» است (ادمین قبل از تأیید می‌تواند عوضش کند). */
async function computeRemaining(order) {
  const panel = panelForOrder(order);
  const GIB = 1024 ** 3;
  const now = Math.floor(Date.now() / 1000);
  let used = null, limit = null, expire = null, source = 'original';
  const lu = order.pg?.lastUsage;
  if (panel && order.pg?.username) {
    try {
      const u = await pgFetch(panel, `/api/user/${encodeURIComponent(order.pg.username)}`);
      if (Number.isFinite(Number(u.used_traffic))) used = Number(u.used_traffic);
      if (Number.isFinite(Number(u.data_limit)) && Number(u.data_limit) > 0) limit = Number(u.data_limit);
      expire = toEpochSec(u.expire);
      source = 'live';
    } catch { /* پنل در دسترس نیست؛ از آخرین اطلاعات ذخیره‌شده استفاده می‌شود */ }
  }
  if ((used == null || limit == null || expire == null) && lu) {
    if (used == null && Number.isFinite(Number(lu.usedTraffic))) used = Number(lu.usedTraffic);
    if (limit == null && Number.isFinite(Number(lu.dataLimit)) && Number(lu.dataLimit) > 0) limit = Number(lu.dataLimit);
    if (expire == null) expire = toEpochSec(lu.expire);
    if (source === 'original' && (used != null || limit != null)) source = 'cached';
  }
  if (limit == null) limit = order.pg?.dataLimit || Math.round(order.gb) * GIB;
  if (expire == null) expire = toEpochSec(order.pg?.expire);
  const remainBytes = used == null ? limit : Math.max(0, limit - used);
  return {
    fromPanelId: panel?.id || '', fromPanelName: panel?.name || order.panelName || '',
    usedGB: used == null ? null : Math.round((used / GIB) * 100) / 100,
    totalGB: Math.round((limit / GIB) * 100) / 100,
    remainGB: Math.round((remainBytes / GIB) * 10) / 10,
    remainDays: expire ? Math.max(1, Math.ceil((expire - now) / 86400)) : (order.days || config.planDays),
    expire: expire || null, source, lastUsageAt: lu?.at || null,
  };
}
/* ───────────────── گزارش روزانهٔ فروشگاه (به وقت ایران) ───────────────── */
let _tzFmt = null;
try { _tzFmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' }); } catch { _tzFmt = null; }
const tzDay = (iso) => {
  const t = Date.parse(iso || '');
  if (!Number.isFinite(t)) return '';
  if (_tzFmt) return _tzFmt.format(new Date(t));
  return new Date(t + 3.5 * 3600_000).toISOString().slice(0, 10); // پشتیبان: ایران UTC+3:30
};
const shiftDay = (dayStr, delta) => {
  const d = new Date(`${dayStr}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
};
const isDayStr = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && shiftDay(s, 0) === s;
function dayStats(day) {
  const sum = (arr, f) => arr.reduce((s, x) => s + (Number(f(x)) || 0), 0);
  const created = orders.filter((o) => tzDay(o.createdAt) === day);
  const createdOk = created.filter((o) => o.status !== 'rejected');
  const approved = orders.filter((o) => o.status === 'approved' && tzDay(o.decidedAt) === day);
  const rejected = orders.filter((o) => o.status === 'rejected' && tzDay(o.decidedAt) === day);
  const filedReports = serviceReports.filter((r) => tzDay(r.createdAt) === day);
  const chatMsgs = Object.values(chats).flatMap((t) => t.messages).filter((m) => tzDay(m.at) === day);
  const migrations = [];
  for (const o of orders) if (Array.isArray(o.migrations)) for (const m of o.migrations) if (tzDay(m.at) === day) migrations.push({ code: o.code, ...m });
  const discMap = new Map();
  for (const o of createdOk) if (o.discountCode) {
    const cur = discMap.get(o.discountCode) || { code: o.discountCode, count: 0, amount: 0 };
    cur.count++; cur.amount += Number(o.discountAmount) || 0;
    discMap.set(o.discountCode, cur);
  }
  return {
    ordersCreated: created.length,
    createdGB: sum(createdOk, (o) => o.gb),
    createdValue: sum(createdOk, (o) => o.price),
    approvedCount: approved.length,
    approvedGB: sum(approved, (o) => o.gb),
    revenue: sum(approved, (o) => o.price),
    rejectedCount: rejected.length,
    pendingFromDay: created.filter((o) => o.status === 'pending').length,
    discountGiven: sum(createdOk, (o) => o.discountAmount || 0),
    topDiscounts: [...discMap.values()].sort((a, b) => b.amount - a.amount).slice(0, 5),
    newUsers: users.filter((u) => tzDay(u.createdAt) === day).length,
    reportsFiled: filedReports.length,
    reportsResolved: serviceReports.filter((r) => r.resolvedAt && tzDay(r.resolvedAt) === day).length,
    commentsNew: comments.filter((c) => tzDay(c.createdAt) === day).length,
    chatMessages: chatMsgs.length,
    chatUserMessages: chatMsgs.filter((m) => m.from === 'user').length,
    chatAdminMessages: chatMsgs.filter((m) => m.from === 'admin').length,
    migrationsCount: migrations.length,
    announcementsNew: announcements.filter((a) => tzDay(a.createdAt) === day).length,
    panels: panelsOf().map((p) => {
      const c = createdOk.filter((o) => panelForOrder(o)?.id === p.id);
      const a = approved.filter((o) => panelForOrder(o)?.id === p.id);
      return { id: p.id, name: p.name, created: c.length, approved: a.length, gb: sum(a, (o) => o.gb), revenue: sum(a, (o) => o.price) };
    }),
    lists: {
      orders: created.slice(0, 60).map((o) => ({ code: o.code, username: o.username || '', gb: o.gb, price: o.price, status: o.status, panelName: panelNameOf(o), createdAt: o.createdAt })),
      newUsers: users.filter((u) => tzDay(u.createdAt) === day).slice(0, 60).map((u) => ({ username: u.username, name: u.name || '', createdAt: u.createdAt })),
      reports: filedReports.slice(0, 30).map((r) => ({ code: r.code, username: r.username, panelName: r.panelName, text: r.text, status: r.status, createdAt: r.createdAt })),
      migrations: migrations.slice(0, 30),
    },
  };
}
function shopSnapshot() {
  const now = Math.floor(Date.now() / 1000);
  const actives = orders.filter((o) => o.status === 'approved' && o.pg);
  const expOf = (o) => toEpochSec(o.pg?.lastUsage?.expire) ?? toEpochSec(o.pg?.expire);
  return {
    totalUsers: users.length,
    totalOrders: orders.length,
    revenueAllTime: orders.filter((o) => o.status === 'approved').reduce((s, o) => s + (Number(o.price) || 0), 0),
    activeServices: actives.length,
    expiringSoon: actives.filter((o) => { const e = expOf(o); return e && e > now && e - now <= 3 * 86400; }).length,
    expiredServices: actives.filter((o) => { const e = expOf(o); return e && e <= now; }).length,
    pendingOrders: orders.filter((o) => o.status === 'pending').length,
    provisionErrors: orders.filter((o) => o.provisionError).length,
    openReports: serviceReports.filter((r) => r.status === 'open').length,
    pendingComments: comments.filter((c) => c.status === 'pending').length,
    unreadChats: Object.values(chats).reduce((s, t) => s + unreadFor(t, 'admin'), 0),
  };
}

const publicOrder = (o) => ({
  code: o.code, gb: o.gb, days: o.days, price: o.price, status: o.status,
  panelName: panelNameOf(o),
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
  pricePerGB: panelPrice(defaultPanel()),
  planDays: config.planDays,
  minGB: config.minGB,
  cardNumber: config.cardNumber,
  cardName: config.cardName,
  panels: salePanels().map(publicPanel),
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
const BACKUP_FILES = ['config.json', 'orders.json', 'users.json', 'chats.json', 'sessions.json', 'discounts.json', 'announcements.json', 'comments.json', 'reports.json'];
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
      'reports.json': serviceReports,
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
    'reports.json': (v) => Array.isArray(v),
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
  ensurePanels();
  if (files['orders.json']) orders = files['orders.json'];
  if (files['users.json']) users = files['users.json'];
  if (files['chats.json']) chats = files['chats.json'];
  if (files['discounts.json']) discounts = files['discounts.json'];
  if (files['announcements.json']) announcements = files['announcements.json'];
  if (files['comments.json']) comments = files['comments.json'];
  if (files['reports.json']) serviceReports = files['reports.json'];
  if (files['sessions.json']) {
    sessions.clear(); userSessions.clear();
    for (const [tok, exp] of Object.entries(files['sessions.json'].admin || {})) if (exp > Date.now()) sessions.set(tok, exp);
    for (const [tok, s] of Object.entries(files['sessions.json'].user || {})) if (s && s.exp > Date.now()) userSessions.set(tok, s);
  }
  if (keepAdminToken) sessions.set(keepAdminToken, keepAdminExp || Date.now() + 7 * 86400_000);
  saveSessions();
  pgJwtCaches.clear();
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
      const panel = b.panelId ? panelById(b.panelId) : defaultPanel();
      if (b.panelId && (!panel || !panel.enabled))
        return sendJson(res, 400, { error: 'این پنل الان قابل خرید نیست؛ یک پنل دیگر انتخاب کن' });
      const originalPrice = gb * panelPrice(panel);
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
      const panel = b.panelId ? panelById(b.panelId) : defaultPanel();
      if (!panel)
        return sendJson(res, 400, { error: 'الان هیچ پنلی برای خرید فعال نیست؛ کمی بعد دوباره امتحان کن یا به پشتیبانی پیام بده' });
      if (b.panelId && !panel.enabled)
        return sendJson(res, 400, { error: 'این پنل الان قابل خرید نیست؛ یک پنل دیگر انتخاب کن' });
      const originalPrice = gb * panelPrice(panel);
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
        panelId: panel.id, panelName: panel.name, pricePerGB: panelPrice(panel),
        discountCode, discountId, discountAmount,
        ...fields,
        status: 'pending',
        createdAt: nowISO(), decidedAt: null,
        rejectReason: '',
        pg: null, provisionError: null,
      };
      orders.unshift(order);
      saveOrders();
      return sendJson(res, 201, { code: order.code, gb: order.gb, price: order.price, days: order.days, panelName: order.panelName, discountCode: order.discountCode, discountAmount: order.discountAmount });
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
        const services = await Promise.all(mine.map(serviceOf));
        for (const s of services) s.reportOpen = serviceReports.some((r) => r.code === s.code && r.status === 'open');
        return sendJson(res, 200, { services });
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
        const panel = panelForOrder(order);
        try {
          if (svcMatch[2] === 'extend-time') {
            const days = Math.floor(Number(b.days));
            if (!Number.isFinite(days) || days < 1 || days > 365)
              return sendJson(res, 400, { error: 'عدد روزهای تمدید بین ۱ تا ۳۶۵ باشد' });
            const cur = await pgFetch(panel, `/api/user/${encodeURIComponent(username)}`);
            const curExp = toEpochSec(cur.expire);
            if (!curExp) return sendJson(res, 400, { error: 'این اشتراک انقضای زمانی ندارد' });
            const newExp = Math.max(curExp, Math.floor(Date.now() / 1000)) + days * 86400;
            await pgModifyUser(panel, username, { expire: newExp }, cur);
            order.pg.expire = newExp;
            saveOrders();
          } else if (svcMatch[2] === 'toggle') {
            const on = b.on === true;
            await pgModifyUser(panel, username, { status: on ? 'active' : 'disabled' });
            order.pg.disabledByUser = !on;
            saveOrders();
          } else { // revoke-sub
            if (rateLimited(`svc-revoke:${user.id}`, 5, 3600_000))
              return sendJson(res, 429, { error: 'تغییر لینک را زیاد انجام دادی؛ یک ساعت دیگر امتحان کن' });
            const fresh = await pgRevokeSub(panel, username, order.pg.userId);
            if (fresh?.subscription_url) order.pg.subUrl = absolutize(panel, fresh.subscription_url);
            saveOrders();
          }
        } catch (e) {
          return sendJson(res, 502, { error: 'در ارتباط با سرور اشتراک مشکلی پیش آمد؛ چند دقیقه دیگر دوباره تلاش کن یا به پشتیبانی پیام بده' });
        }
        return sendJson(res, 200, { ok: true, service: await serviceOf(order) });
      }

      /* ── گزارش مشکل سرویس: در بخش «گزارش‌های سرویس» پنل مدیریت دیده می‌شود ── */
      const repMatch = /^\/api\/my\/services\/([A-Za-z0-9-]+)\/report$/.exec(p);
      if (req.method === 'POST' && repMatch) {
        if (rateLimited(`svcreport:${user.id}`, 5, 3600_000))
          return sendJson(res, 429, { error: 'چند گزارش فرستادی؛ کمی صبر کن تا بررسی بشن' });
        const order = orders.find((o) => o.code === repMatch[1].toUpperCase() && o.userId === user.id && o.status === 'approved' && o.pg?.username);
        if (!order) return sendJson(res, 404, { error: 'اشتراک پیدا نشد' });
        const b = await readBody(req);
        const text = cleanStr(b.text, 1000);
        if (text.length < 5) return sendJson(res, 400, { error: 'مشکل رو یکم کامل‌تر بنویس (حداقل چند کلمه)' });
        if (serviceReports.some((r) => r.code === order.code && r.status === 'open'))
          return sendJson(res, 409, { error: 'برای این سرویس یک گزارش باز داری که در حال بررسی است 🙏' });
        const panel = panelForOrder(order);
        const r = {
          id: 'r_' + crypto.randomBytes(6).toString('hex'),
          code: order.code, userId: user.id, username: user.username,
          panelId: panel?.id || '', panelName: panel?.name || order.panelName || '',
          text, status: 'open', createdAt: nowISO(), resolvedAt: null,
        };
        serviceReports.unshift(r);
        saveReports();
        return sendJson(res, 201, { ok: true, report: { id: r.id, status: r.status, createdAt: r.createdAt } });
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
        panelName: panelNameOf(order),
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
      ensurePanels();
      syncFirstPanelFromLegacy();
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
          reportsOpen: serviceReports.filter((r) => r.status === 'open').length,
        };
        return sendJson(res, 200, { orders: list.slice(0, 300).map((o) => ({ ...o, panelName: panelNameOf(o) })), counts });
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
          const panel = panelForOrder(order) || defaultPanel();
          if (panel && !order.panelId) { order.panelId = panel.id; order.panelName = panel.name; }
          const pg = await pgCreateUser(panel, order);
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

      /* ── پنل‌های پاسارگارد (چندپنلی) ── */
      if (req.method === 'GET' && p === '/api/admin/panels') {
        return sendJson(res, 200, { panels: panelsOf().map(adminPanelView) });
      }
      if (req.method === 'POST' && p === '/api/admin/panels') {
        const b = await readBody(req);
        const panel = sanitizePanel(b);
        if (!panel.name) return sendJson(res, 400, { error: 'برای پنل یک اسم بگذار (همان اسمی که مشتری موقع خرید می‌بیند)' });
        config.panels = [...panelsOf(), panel];
        syncLegacyFromFirstPanel();
        saveConfig();
        return sendJson(res, 201, { ok: true, panel: adminPanelView(panel) });
      }
      const panelMatch = /^\/api\/admin\/panels\/([A-Za-z0-9_-]+)\/(edit|toggle|delete)$/.exec(p);
      if (req.method === 'POST' && panelMatch) {
        const idx = panelsOf().findIndex((x) => x.id === panelMatch[1]);
        if (idx < 0) return sendJson(res, 404, { error: 'پنل پیدا نشد' });
        const act = panelMatch[2];
        if (act === 'delete') {
          if (panelsOf().length <= 1)
            return sendJson(res, 409, { error: 'نمی‌توان تنها پنل فروشگاه را حذف کرد' });
          const used = orders.some((o) => (o.panelId || o.pg?.panelId) === panelMatch[1] || (idx === 0 && !o.panelId && !o.pg?.panelId));
          if (used)
            return sendJson(res, 409, { error: 'این پنل سفارش/اشتراک دارد و حذف نمی‌شود؛ به‌جای حذف «غیرفعال»اش کن تا از خرید برداشته شود و سرویس‌هایش قابل انتقال بمانند' });
          config.panels.splice(idx, 1);
        } else if (act === 'toggle') {
          config.panels[idx].enabled = !config.panels[idx].enabled;
        } else { // edit
          const b = await readBody(req);
          const panel = sanitizePanel(b, config.panels[idx]);
          if (!panel.name) return sendJson(res, 400, { error: 'اسم پنل نباید خالی باشد' });
          config.panels[idx] = panel;
        }
        syncLegacyFromFirstPanel();
        saveConfig();
        return sendJson(res, 200, { ok: true, panels: panelsOf().map(adminPanelView) });
      }

      /* ── انتقال اشتراک بین پنل‌ها ── */
      const migPrevMatch = /^\/api\/admin\/orders\/([A-Za-z0-9-]+)\/migrate-preview$/.exec(p);
      if (req.method === 'GET' && migPrevMatch) {
        const order = findOrder(migPrevMatch[1]);
        if (!order || order.status !== 'approved' || !order.pg?.username)
          return sendJson(res, 404, { error: 'اشتراک فعالی برای این سفارش پیدا نشد' });
        const info = await computeRemaining(order);
        return sendJson(res, 200, {
          ok: true, ...info,
          targets: panelsOf().filter((x) => x.id !== info.fromPanelId)
            .map((x) => ({ id: x.id, name: x.name, enabled: !!x.enabled, hasUrl: !!normalizePgBase(x.baseUrl) })),
        });
      }
      const migMatch = /^\/api\/admin\/orders\/([A-Za-z0-9-]+)\/migrate$/.exec(p);
      if (req.method === 'POST' && migMatch) {
        const order = findOrder(migMatch[1]);
        if (!order || order.status !== 'approved' || !order.pg?.username)
          return sendJson(res, 404, { error: 'اشتراک فعالی برای این سفارش پیدا نشد' });
        const b = await readBody(req);
        const target = panelById(b.toPanelId);
        if (!target) return sendJson(res, 400, { error: 'پنل مقصد را انتخاب کن' });
        const sourcePanel = panelForOrder(order);
        if (sourcePanel && target.id === sourcePanel.id)
          return sendJson(res, 400, { error: 'پنل مقصد همان پنل فعلی است؛ یک پنل دیگر انتخاب کن' });
        if (!normalizePgBase(target.baseUrl))
          return sendJson(res, 400, { error: 'آدرس پنل مقصد تنظیم نشده است' });
        let gb = Number(b.gb), days = Math.floor(Number(b.days));
        if (!Number.isFinite(gb) || !Number.isFinite(days)) {
          const info = await computeRemaining(order);
          if (!Number.isFinite(gb)) gb = info.remainGB;
          if (!Number.isFinite(days)) days = info.remainDays;
        }
        if (!(gb > 0) || gb > 5000)
          return sendJson(res, 400, { error: 'حجم انتقال باید بیشتر از صفر و حداکثر ۵۰۰۰ گیگ باشد (اگر حجم تمام شده، یک حجم دستی وارد کن)' });
        if (!(days >= 1) || days > 3650)
          return sendJson(res, 400, { error: 'روزهای انتقال باید بین ۱ تا ۳۶۵۰ باشد' });
        gb = Math.round(gb * 10) / 10;
        try {
          const pg = await pgCreateUser(target, order, { gb, days, relimit: true, noteSuffix: ' | انتقال از پنل قبلی' });
          const fromPanelId = sourcePanel?.id || '';
          const fromPanelName = sourcePanel?.name || order.panelName || '';
          const oldUsername = order.pg.username;
          order.pg = pg;
          order.panelId = target.id;
          order.panelName = target.name;
          order.provisionError = null;
          /* کانفیگ روی پنل قبلی را (اگر در دسترس بود) خاموش کن تا دوبار مصرف نشود */
          let sourceDisabled = false;
          if (sourcePanel && normalizePgBase(sourcePanel.baseUrl)) {
            try { await pgModifyUser(sourcePanel, oldUsername, { status: 'disabled' }); sourceDisabled = true; }
            catch { /* پنل قبلی در دسترس نیست (همان دلیلی که داریم منتقل می‌کنیم) */ }
          }
          order.migrations = [...(Array.isArray(order.migrations) ? order.migrations : []), {
            at: nowISO(), fromPanelId, fromPanelName, toPanelId: target.id, toPanelName: target.name,
            gb, days, sourceDisabled,
          }];
          saveOrders();
          /* گزارش باز این سرویس را «انجام‌شده» کن و به مشتری در چت خبر بده */
          let reportsClosed = 0;
          for (const r of serviceReports) if (r.code === order.code && r.status === 'open') { r.status = 'done'; r.resolvedAt = nowISO(); reportsClosed++; }
          if (reportsClosed) saveReports();
          const owner = order.userId ? findUserById(order.userId) : null;
          if (owner) {
            const thread = getThread(owner);
            pushMessage(thread, 'admin', `سلام 🙏 اشتراکت (سفارش ${order.code}) به پنل «${target.name}» منتقل شد و لینک اشتراک جدید ساخته شد ✅\nحجم منتقل‌شده: ${gb} گیگ برای ${days} روز.\nلینک جدید رو از بخش «سرویس من» بردار و جایگزین لینک قبلی کن (لینک قبلی دیگر کار نمی‌کند):\n${pg.subUrl}`);
            saveChats();
          }
          return sendJson(res, 200, { ok: true, order: { ...order, panelName: target.name }, sourceDisabled, reportsClosed });
        } catch (e) {
          return sendJson(res, 502, { error: `خطا در انتقال: ${e.message}` });
        }
      }

      /* ── گزارش‌های مشکل سرویس ── */
      if (req.method === 'GET' && p === '/api/admin/reports') {
        const list = serviceReports.slice().sort((x, y) =>
          ((x.status === 'open' ? 0 : 1) - (y.status === 'open' ? 0 : 1)) ||
          String(y.createdAt).localeCompare(String(x.createdAt)));
        return sendJson(res, 200, { reports: list.slice(0, 300), open: serviceReports.filter((r) => r.status === 'open').length });
      }
      const repAdminMatch = /^\/api\/admin\/reports\/([A-Za-z0-9_-]+)\/(resolve|reopen|delete)$/.exec(p);
      if (req.method === 'POST' && repAdminMatch) {
        const idx = serviceReports.findIndex((x) => x.id === repAdminMatch[1]);
        if (idx < 0) return sendJson(res, 404, { error: 'گزارش پیدا نشد' });
        if (repAdminMatch[2] === 'delete') serviceReports.splice(idx, 1);
        else if (repAdminMatch[2] === 'resolve') { serviceReports[idx].status = 'done'; serviceReports[idx].resolvedAt = nowISO(); }
        else { serviceReports[idx].status = 'open'; serviceReports[idx].resolvedAt = null; }
        saveReports();
        return sendJson(res, 200, { ok: true });
      }

      /* ── گزارش روزانهٔ فروشگاه: یک روز به وقت ایران + مقایسه با روز قبل + کارهای باز ── */
      if (req.method === 'GET' && p === '/api/admin/daily-report') {
        const today = tzDay(nowISO());
        let day = url.searchParams.get('date') || today;
        if (!isDayStr(day) || day > today) day = today;
        const prevDay = shiftDay(day, -1);
        const prevStats = dayStats(prevDay);
        delete prevStats.lists;
        return sendJson(res, 200, {
          ok: true, date: day, prevDate: prevDay, isToday: day === today,
          stats: dayStats(day), prev: prevStats, snapshot: shopSnapshot(),
        });
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
        const { pgApiKey, pgPassword, adminPassHash, panels, ...rest } = config;
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
        syncFirstPanelFromLegacy();
        saveConfig();
        return sendJson(res, 200, { ok: true, settings: publicConfig() });
      }
      if (req.method === 'POST' && p === '/api/admin/test-pg') {
        const b = await readBody(req);
        // پنل آزمایشی موقت از روی فرم (اگر panelId آمد روی همان پنل ذخیره‌شده) — بدون دست‌زدن به تنظیمات
        const base = b.panelId ? panelById(b.panelId) : null;
        const panel = sanitizePanel({
          name: base?.name || 'تست اتصال',
          baseUrl: b.pgBaseUrl ?? b.baseUrl ?? base?.baseUrl,
          publicBaseUrl: b.pgPublicBaseUrl ?? b.publicBaseUrl ?? base?.publicBaseUrl,
          apiKey: b.pgApiKey ?? b.apiKey ?? '',
          username: b.pgUsername ?? b.username ?? base?.username,
          password: b.pgPassword ?? b.password ?? '',
          groupIds: base?.groupIds,
        }, base);
        panel.id = base?.id || 'pn_test';
        try {
          const data = await pgFetch(panel, '/api/groups/simple', { query: { all: true } });
          return sendJson(res, 200, { ok: true, groups: data?.groups || [] });
        } catch (e) {
          return sendJson(res, 502, { error: e.message });
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
