/* فونت‌های لوکال (سلف‌هاست) — بدون وابستگی به گوگل‌فونت، سریع در ایران */
import '@fontsource/vazirmatn/400.css';
import '@fontsource/vazirmatn/500.css';
import '@fontsource/vazirmatn/700.css';
import '@fontsource/vazirmatn/800.css';
import '@fontsource/vazirmatn/900.css';
import '@fontsource/space-grotesk/600.css';
import '@fontsource/space-grotesk/700.css';
import './style.css';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
/* صحنه three به‌صورت تنبل لود می‌شود تا اولین رندر سریع بماند */

gsap.registerPlugin(ScrollTrigger);
document.documentElement.classList.add('js');
window.__nkBooted = true; // فلگ فیل‌سیف پری‌لودر (اسکریپت اینلاین در index.html)

/* ═══════════════ تنظیمات فروشگاه (از سرور خوانده می‌شود؛ این‌ها پیش‌فرض) ═══════════════ */
const cfg = {
  pricePerGB: 4000,          // تومان
  planDays: 30,
  minGB: 10,
  cardNumber: '6219861495616921',
  cardName: 'ایمان دهقانی',
  panels: [],               // پنل‌های قابل خرید [{id, name, pricePerGB}]
};

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const finePointer = window.matchMedia('(pointer: fine)').matches;
const $ = (s, c = document) => c.querySelector(s);
const $$ = (s, c = document) => [...c.querySelectorAll(s)];
const toFa = (n) => Math.round(Number(n)).toLocaleString('fa-IR');
const padFa = (n) => String(n).padStart(2, '0').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]);
const groupCard = (digits) => String(digits).replace(/[^\d]/g, '').replace(/(\d{4})(?=\d)/g, '$1 ');
const faDigitsToEn = (s) => String(s ?? '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));

$('#year').textContent = new Date().getFullYear().toLocaleString('fa-IR', { useGrouping: false });

async function copyText(text, btn, doneLabel = 'کپی شد ✓') {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove();
  }
  if (btn) {
    const label = btn.querySelector('.btn-label') || btn;
    const old = label.textContent;
    label.textContent = doneLabel;
    setTimeout(() => { label.textContent = old; }, 2200);
  }
}

/* هلپرهای API فروش و قالب‌بندی */
async function api(path, { method = 'GET', body } = {}) {
  const r = await fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(d.error || `خطای ${r.status}`); e.status = r.status; e.data = d; throw e; }
  return d;
}
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const faNum = (n, f = 0) => Number(n || 0).toLocaleString('fa-IR', { maximumFractionDigits: f });
const fmtGB = (bytes) => (bytes == null ? '—' : faNum(bytes / 1024 ** 3, bytes / 1024 ** 3 >= 100 ? 0 : 2));

/* ════════════════ WebGL (لود تنبل؛ جایگزین CSS در صورت نبود) ════════════════ */
/* صحنهٔ سه‌بعدی سنگین‌ترین بخش است (~۱۲۰KB gzip)؛ برای اینکه روی اینترنت‌های
   کند/محدود (مثل مسیر ایران↔خارج) باز شدن اولیهٔ سایت معطل نماند، آن را
   در زمان بیکاری مرورگر لود می‌کنیم و روی اتصال‌های خیلی کند اصلاً رد می‌شویم. */
let aether = null;
const netConn = navigator.connection || {};
const slowNet = netConn.saveData === true || /^(slow-)?2g$/.test(netConn.effectiveType || '');
if (!reducedMotion && !slowNet) {
  const startScene = () => {
    import('./three/scene.js')
      .then(({ createAetherScene }) => {
        aether = createAetherScene($('#webgl'), { reducedMotion });
        if (aether) initScrollJourney(aether);
        else document.body.classList.add('no-webgl');
      })
      .catch(() => document.body.classList.add('no-webgl'));
  };
  if ('requestIdleCallback' in window) requestIdleCallback(startScene, { timeout: 2800 });
  else setTimeout(startScene, 1400);
} else {
  document.body.classList.add('no-webgl');
}

/* ════════════════ اسکرول نرم (Lenis) ════════════════ */
let lenis = null;
if (!reducedMotion) {
  lenis = new Lenis({ lerp: 0.09, wheelMultiplier: 1, smoothWheel: true });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);
}
const jumpToEl = (el, immediate = false) => {
  if (!el) return;
  if (lenis) lenis.scrollTo(el, { immediate, offset: 0, duration: immediate ? 0 : 1.4 });
  else el.scrollIntoView({ behavior: immediate || reducedMotion ? 'auto' : 'smooth' });
};
const getScrollY = () => window.scrollY || 0;
const setScrollY = (y) => {
  if (lenis) lenis.scrollTo(y, { immediate: true, force: true });
  else window.scrollTo(0, y);
};
/* اعمال موقعیت بازیابی‌شده + یک تلاش مجدد کوتاه اگر لیمیت/چیدمان هنوز جا نیفتاده باشد؛ با اسکرول کاربر لغو می‌شود */
let pgRestoreToken = 0;
['wheel', 'touchmove'].forEach((ev) => window.addEventListener(ev, () => { pgRestoreToken++; }, { passive: true }));
const applyRestore = (y) => {
  const tok = ++pgRestoreToken;
  setScrollY(y);
  const again = () => {
    if (tok === pgRestoreToken && Math.abs(getScrollY() - y) > 2) setScrollY(y);
  };
  requestAnimationFrame(again);
  setTimeout(again, 140);
};
const scrollToTarget = (target, immediate = false, restoreY = null) => {
  const el = typeof target === 'string' ? $(target) : target;
  if (!el) return;
  const prevY = getScrollY();
  const pg = el.closest ? el.closest('[data-page]') : null;
  if (pg && pg.dataset.page !== currentPage) {
    if (!showPage(pg.dataset.page)) return;
    if (restoreY != null) applyRestore(restoreY); else jumpToEl(el, true);
  } else if (restoreY != null) {
    applyRestore(restoreY);
  } else {
    jumpToEl(el, immediate);
  }
  if (!pgNavLock && el.id && location.hash !== `#${el.id}`) {
    try { history.replaceState({ pgY: prevY }, ''); } catch { /* ignore */ }
    history.pushState(null, '', `#${el.id}`);
  }
};

/* ════════════════ صفحه‌بندی اپلیکیشنی (روتر) ════════════════ */
let currentPage = 'home';
let pgAuthKnown = false;
let pgLoggedIn = false;
let pgNavLock = false;
const HOME_TITLE = document.title;
const PAGE_TITLES = {
  home: HOME_TITLE,
  shop: 'خرید کانفیگ | ورتکس‌نت',
  account: 'حساب کاربری | ورتکس‌نت',
  track: 'پیگیری سفارش | ورتکس‌نت',
  news: 'اطلاعیه‌ها | ورتکس‌نت',
  reviews: 'نظرات مشتریان | ورتکس‌نت',
  guide: 'راهنمای خرید | ورتکس‌نت',
};
function showPage(name, instant = false) {
  if (!PAGE_TITLES[name]) name = 'home';
  if (name === 'account' && pgAuthKnown && !pgLoggedIn) {
    afterAuthGo = 'orders';
    openAuth('login');
    return false;
  }
  const changed = name !== currentPage;
  currentPage = name;
  $$('[data-page]').forEach((el) => { el.hidden = el.dataset.page !== name; });
  const acc = $('#account');
  if (acc) acc.hidden = !(name === 'account' && pgLoggedIn);
  if (lenis) lenis.resize();
  document.title = PAGE_TITLES[name];
  const main = $('#main');
  if (main && changed && !instant && !reducedMotion) {
    main.classList.remove('page-switch');
    void main.offsetWidth;
    main.classList.add('page-switch');
  }
  if (name === 'home') setBnavActive('home');
  else if (name !== 'account') setBnavActive('');
  ScrollTrigger.refresh();
  $$('.nav-links a[href^="#"]').forEach((a) => {
    const t = $(a.getAttribute('href'));
    const tp = t && t.closest ? t.closest('[data-page]') : null;
    if (tp && tp.dataset.page !== name) a.classList.remove('is-active');
  });
  return true;
}
function routeOnAuth() {
  pgAuthKnown = true;
  pgLoggedIn = !!me;
  if (!me && currentPage === 'account') showPage('home', true);
  const acc = $('#account');
  if (acc) acc.hidden = !(currentPage === 'account' && !!me);
}
window.addEventListener('popstate', (e) => {
  pgNavLock = true;
  pgRestoreGuard = Date.now() + 500;
  const y = e.state && typeof e.state.pgY === 'number' ? e.state.pgY : null;
  scrollToTarget(location.hash && location.hash.length > 1 ? location.hash : '#hero', true, y);
  pgNavLock = false;
});
$('#qa-service')?.addEventListener('click', () => goAccount('service'));
$('#qa-support')?.addEventListener('click', () => toggleChat(true));
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
let pgSaveTick = false;
let pgRestoreGuard = 0;
window.addEventListener('scroll', () => {
  if (pgSaveTick) return;
  pgSaveTick = true;
  requestAnimationFrame(() => {
    pgSaveTick = false;
    if (Date.now() < pgRestoreGuard) return;
    const y = getScrollY();
    if (!history.state || history.state.pgY !== y) {
      try { history.replaceState({ pgY: y }, ''); } catch { /* ignore */ }
    }
  });
}, { passive: true });

(() => {
  const h = location.hash;
  const el = /^#[A-Za-z][\w-]*$/.test(h) ? $(h) : null;
  const pg = el && el.closest ? el.closest('[data-page]') : null;
  showPage(pg ? pg.dataset.page : 'home', true);
  const sy = history.state && typeof history.state.pgY === 'number' ? history.state.pgY : null;
  if (sy != null) applyRestore(sy);
  else if (el && pg) jumpToEl(el, true);
})();

/* ════════════════ پری‌لودر + ورود هیرو ════════════════ */
document.body.classList.add('is-loading');
if (lenis) lenis.stop();

const heroIntro = () => {
  const tl = gsap.timeline({ defaults: { ease: 'power4.out' } });
  tl.to('#preloader .loader-inner', { yPercent: -30, opacity: 0, duration: 0.55, ease: 'power3.in' })
    .to('#preloader', { yPercent: -100, duration: 0.9, ease: 'power4.inOut' }, '-=0.1')
    .set('#preloader', { display: 'none' })
    .add(() => { document.body.classList.remove('is-loading'); if (lenis) lenis.start(); }, '-=0.55')
    .from('.hero-title .ht-inner', { yPercent: 118, duration: 1.05, stagger: 0.11 }, '-=0.55')
    .to('.hero .hero-anim', { opacity: 1, y: 0, duration: 0.9, stagger: 0.09 }, '-=0.65');
  return tl;
};

if (reducedMotion) {
  gsap.set('#preloader', { display: 'none' });
  gsap.set('.hero-anim, [data-reveal]', { opacity: 1 });
  document.body.classList.remove('is-loading');
} else {
  gsap.set('.hero .hero-anim', { y: 30 });
  const counter = { v: 0 };
  const countEl = $('#loader-count');
  const barEl = $('#loader-bar-fill');
  gsap.to(counter, {
    v: 100, duration: 1.5, ease: 'power2.inOut',
    onUpdate() {
      const n = Math.round(counter.v);
      countEl.textContent = padFa(n);
      barEl.style.width = `${n}%`;
    },
    onComplete: heroIntro,
  });
}

/* ════════════════ ناوبری ════════════════ */
const nav = $('#site-nav');
const onScrollNav = () => nav.classList.toggle('is-scrolled', window.scrollY > 40);
window.addEventListener('scroll', onScrollNav, { passive: true });
onScrollNav();

gsap.to('#scroll-progress', {
  scaleX: 1, ease: 'none',
  scrollTrigger: { trigger: document.body, start: 'top top', end: 'bottom bottom', scrub: 0.3 },
});

['features', 'plans', 'steps', 'faq', 'track'].forEach((id) => {
  ScrollTrigger.create({
    trigger: `#${id}`, start: 'top 45%', end: 'bottom 45%',
    onToggle(self) {
      $$(`.nav-links a[href="#${id}"]`).forEach((a) => a.classList.toggle('is-active', self.isActive));
    },
  });
});

/* ════════════════ منوی موبایل ════════════════ */
const menuBtn = $('#menu-btn');
const mobileMenu = $('#mobile-menu');
let menuOpen = false;
const menuTl = gsap.timeline({ paused: true })
  .set(mobileMenu, { visibility: 'visible' })
  .to(mobileMenu, { clipPath: 'inset(0 0 0% 0)', duration: 0.65, ease: 'power4.inOut' })
  .from('#mobile-menu .mm-fade', { y: 26, opacity: 0, duration: 0.5, stagger: 0.055, ease: 'power3.out', clearProps: 'transform,opacity' }, '-=0.25');

const setMenu = (open) => {
  menuOpen = open;
  document.body.classList.toggle('menu-open', open);
  menuBtn.classList.toggle('is-open', open);
  menuBtn.setAttribute('aria-expanded', String(open));
  menuBtn.setAttribute('aria-label', open ? 'بستن منو' : 'باز کردن منو');
  mobileMenu.setAttribute('aria-hidden', String(!open));
  if (open) { menuTl.timeScale(1).play(); lenis && lenis.stop(); $('#mm-close')?.focus({ preventScroll: true }); }
  else { menuTl.timeScale(1.5).reverse(); lenis && lenis.start(); }
};
menuBtn.addEventListener('click', () => setMenu(!menuOpen));
$('#mm-close')?.addEventListener('click', () => setMenu(false));

/* ════════════════ ترنزیشن وایپ برای لینک‌های داخلی ════════════════ */
const wipe = $('#page-wipe');
let wiping = false;
$$('a.nav-link[href^="#"]').forEach((a) => {
  a.addEventListener('click', (e) => {
    const id = a.getAttribute('href');
    const el = $(id);
    if (!el || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    if (menuOpen) setMenu(false);
    if (a.dataset.buyGb) setSelectedGB(Number(a.dataset.buyGb));
    if (a.id === 'calc-buy') setSelectedGB(calcGB);
    const pg = el.closest ? el.closest('[data-page]') : null;
    const pageChange = !!(pg && pg.dataset.page !== currentPage);
    if (!pageChange) { scrollToTarget(id); return; }
    if (reducedMotion || wiping) { scrollToTarget(id, true); return; }
    wiping = true;
    gsap.timeline({ onComplete: () => { wiping = false; } })
      .set(wipe, { yPercent: -101 })
      .to(wipe, { yPercent: 0, duration: 0.5, ease: 'power4.inOut' })
      .add(() => scrollToTarget(id, true))
      .to(wipe, { yPercent: 101, duration: 0.55, ease: 'power4.inOut', delay: 0.08 })
      .set(wipe, { yPercent: -101 });
  });
});

/* ════════════════ انیمیشن‌های اسکرولی ════════════════ */
if (!reducedMotion) {
  $$('[data-reveal]').forEach((el) => {
    gsap.fromTo(el,
      { y: 44, opacity: 0 },
      {
        y: 0, opacity: 1, duration: 1, ease: 'power3.out',
        scrollTrigger: { trigger: el, start: 'top 88%', once: true },
      });
  });

  const wordsEl = $('[data-words]');
  if (wordsEl) {
    const raw = wordsEl.textContent.trim().replace(/\s+/g, ' ');
    wordsEl.setAttribute('aria-label', raw);
    wordsEl.innerHTML = raw.split(' ').map((w) => `<span class="word" aria-hidden="true">${w}</span>`).join(' ');
    gsap.fromTo('[data-words] .word', { opacity: 0.13 }, {
      opacity: 1, stagger: 0.05, ease: 'none',
      scrollTrigger: { trigger: wordsEl, start: 'top 78%', end: 'bottom 42%', scrub: 0.6 },
    });
  }

  $$('[data-parallax]').forEach((el) => {
    gsap.to(el, {
      yPercent: parseFloat(el.dataset.parallax) || -12, ease: 'none',
      scrollTrigger: { trigger: el.parentElement, start: 'top bottom', end: 'bottom top', scrub: 0.8 },
    });
  });
}

/* شمارنده‌ها با اعداد فارسی (مقدار بعضی‌ها از تنظیمات زنده خوانده می‌شود) */
$$('[data-count]').forEach((el) => {
  const getEnd = () => (el.dataset.countKey ? Number(cfg[el.dataset.countKey]) || 0 : parseInt(el.dataset.count, 10) || 0);
  if (reducedMotion) { el.textContent = toFa(getEnd()); return; }
  ScrollTrigger.create({
    trigger: el, start: 'top 92%', once: true,
    onEnter: () => {
      const obj = { v: 0 };
      const end = getEnd();
      gsap.to(obj, {
        v: end, duration: 1.7, ease: 'power3.out',
        onUpdate: () => { el.textContent = toFa(obj.v); },
      });
    },
  });
});

/* ════════════════ قیمت‌گذاری: پلن‌ها + ماشین‌حساب + بخش خرید ════════════════ */
const rangeEl = $('#gb-range');
const inputEl = $('#gb-input');
const priceEl = $('#calc-price');
const perdayEl = $('#calc-perday');
const gbLabelEl = $('#calc-gb-label');
const ckInput = $('#ck-gb-input');
const ckPriceEl = $('#ck-price');
const ckPerdayEl = $('#ck-perday');

let calcGB = 50;
let selectedGB = 50;

/* ── انتخاب پنل (سرور): قیمت همه‌چیز از پنل انتخابی مشتری حساب می‌شود ── */
let selectedPanelId = '';
const salePanels = () => (Array.isArray(cfg.panels) ? cfg.panels : []);
const selectedPanel = () => salePanels().find((p) => p.id === selectedPanelId) || salePanels()[0] || null;
const pricePerGBNow = () => selectedPanel()?.pricePerGB || cfg.pricePerGB;
const priceOf = (gb) => gb * pricePerGBNow();
function renderPanelPicker() {
  const list = salePanels();
  const cur = selectedPanel();
  if (cur) selectedPanelId = cur.id;
  const wrap = $('#panel-picker');
  const opts = $('#panel-opts');
  if (wrap && opts) {
    wrap.hidden = list.length < 2;
    opts.innerHTML = list.map((p) => `<button type="button" class="panel-opt ${p.id === selectedPanelId ? 'on' : ''}" data-panel-opt="${esc(p.id)}" role="radio" aria-checked="${p.id === selectedPanelId}" data-hover><b>${esc(p.name)}</b><span>هر گیگ ${toFa(p.pricePerGB)} تومان</span></button>`).join('');
  }
  const ckName = $('#ck-panel-name');
  if (ckName) {
    ckName.hidden = !cur || list.length < 2;
    if (cur) ckName.innerHTML = `پنل انتخابی: <b>${esc(cur.name)}</b> — هر گیگ ${toFa(cur.pricePerGB)} تومان`;
  }
}
function selectPanel(id) {
  if (!salePanels().some((p) => p.id === id) || id === selectedPanelId) return;
  selectedPanelId = id;
  if (appliedDiscount) {
    clearDiscount();
    setStatus($('#discount-msg'), 'پنل عوض شد؛ برای قیمت جدید، کد تخفیف رو دوباره اعمال کن');
  }
  renderPanelPicker();
  renderStaticPrices();
  updateCalc(calcGB, null);
  setSelectedGB(selectedGB, null);
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-panel-opt]');
  if (b) selectPanel(b.dataset.panelOpt);
});
const fmtPrice = (gb) => `${toFa(priceOf(gb))} تومان`;
const fmtPerDay = (gb) => `روزی حدود ${toFa(priceOf(gb) / cfg.planDays)} تومان`;

/* ── کد تخفیف (نمایش مبلغ نهایی؛ اعتبار نهایی را سرور موقع ثبت سفارش چک می‌کند) ── */
let appliedDiscount = null; // {code, type, value}
const discountAmountFor = (gb) => {
  if (!appliedDiscount) return 0;
  const orig = priceOf(gb);
  return appliedDiscount.type === 'percent' ? Math.floor(orig * appliedDiscount.value / 100) : Math.min(appliedDiscount.value, orig);
};
const displayPrice = (gb) => Math.max(0, priceOf(gb) - discountAmountFor(gb));
function updateDiscountLine() {
  const line = $('#discount-line');
  if (!line) return;
  if (!appliedDiscount) { line.hidden = true; line.textContent = ''; return; }
  line.hidden = false;
  line.textContent = `🎟 تخفیف «${appliedDiscount.code}»: ‏−${toFa(discountAmountFor(selectedGB))} تومان — مبلغ اصلی ${toFa(priceOf(selectedGB))} تومان بود`;
}
function clearDiscount(silent) {
  appliedDiscount = null;
  const f = $('#f-discount'); if (f) f.disabled = false;
  const a = $('#discount-apply'); if (a) a.disabled = false;
  const r = $('#discount-remove'); if (r) r.hidden = true;
  if (!silent) setStatus($('#discount-msg'), '');
  updateDiscountLine();
}
const clampGB = (gb) => Math.max(cfg.minGB, Math.min(5000, Math.round(Number(gb) || cfg.minGB)));

function renderStaticPrices() {
  $$('[data-price-per-gb]').forEach((el) => { el.textContent = toFa(pricePerGBNow()); });
  $$('[data-plan-days]').forEach((el) => { el.textContent = toFa(cfg.planDays); });
  $$('[data-min-gb]').forEach((el) => { el.textContent = toFa(cfg.minGB); });
  $$('[data-price-gb]').forEach((el) => { el.textContent = toFa(priceOf(parseFloat(el.dataset.priceGb) || 0)); });
  const cn = $('#card-number'); if (cn) cn.textContent = groupCard(cfg.cardNumber);
  const cname = $('#card-name'); if (cname) cname.textContent = cfg.cardName;
  if (rangeEl) { rangeEl.min = cfg.minGB; }
  if (inputEl) { inputEl.min = cfg.minGB; }
  if (ckInput) { ckInput.min = cfg.minGB; }
}
function pop(el) { if (el && !reducedMotion) gsap.fromTo(el, { scale: 1.04 }, { scale: 1, duration: 0.35, ease: 'power2.out' }); }

function updateCalc(gb, source) {
  calcGB = clampGB(gb);
  if (gbLabelEl) gbLabelEl.textContent = `${toFa(calcGB)} گیگ`;
  if (priceEl) { priceEl.textContent = fmtPrice(calcGB); pop(priceEl); }
  if (perdayEl) perdayEl.textContent = `یعنی ${fmtPerDay(calcGB)}`;
  if (rangeEl && source !== rangeEl) rangeEl.value = Math.min(500, Math.max(cfg.minGB, calcGB));
  if (inputEl && source !== inputEl) inputEl.value = calcGB;
}
function setSelectedGB(gb, source) {
  selectedGB = clampGB(gb);
  if (ckInput && source !== ckInput) ckInput.value = selectedGB;
  if (ckPriceEl) { ckPriceEl.textContent = `${toFa(displayPrice(selectedGB))} تومان`; pop(ckPriceEl); }
  if (ckPerdayEl) ckPerdayEl.textContent = `روزی حدود ${toFa(displayPrice(selectedGB) / cfg.planDays)} تومان`;
  updateDiscountLine();
  $$('[data-ck-gb]').forEach((b) => b.classList.toggle('on', Number(b.dataset.ckGb) === selectedGB));
  $$('.plan-card').forEach((c) => c.classList.toggle('is-selected', Number(c.dataset.planGb) === selectedGB));
}
if (rangeEl && inputEl) {
  rangeEl.addEventListener('input', () => updateCalc(rangeEl.value, rangeEl));
  inputEl.addEventListener('input', () => updateCalc(inputEl.value, inputEl));
  inputEl.addEventListener('blur', () => updateCalc(inputEl.value, inputEl));
}
if (ckInput) {
  ckInput.addEventListener('input', () => setSelectedGB(ckInput.value, ckInput));
  ckInput.addEventListener('blur', () => setSelectedGB(ckInput.value, ckInput));
  $('#ck-minus')?.addEventListener('click', () => setSelectedGB(selectedGB - 5));
  $('#ck-plus')?.addEventListener('click', () => setSelectedGB(selectedGB + 5));
  $$('[data-ck-gb]').forEach((b) => b.addEventListener('click', () => setSelectedGB(Number(b.dataset.ckGb))));
}
renderStaticPrices();
updateCalc(50, null);
setSelectedGB(50, null);

/* تنظیمات زنده از سرور فروش */
fetch('/api/config')
  .then((r) => (r.ok ? r.json() : Promise.reject()))
  .then((remote) => {
    Object.assign(cfg, remote);
    renderPanelPicker();
    renderStaticPrices();
    updateCalc(calcGB, null);
    setSelectedGB(selectedGB, null);
  })
  .catch(() => { /* پیش‌فرض‌ها کافی‌اند (مثلاً در پیش‌نمایش بدون بک‌اند) */ });

/* کپی شماره کارت */
$('#copy-card')?.addEventListener('click', (e) => copyText(cfg.cardNumber, e.currentTarget));

/* ════════════════ ثبت سفارش ════════════════ */
const orderForm = $('#order-form');
const orderStatus = $('#order-status');
function setStatus(el, text, ok) { if (!el) return; el.textContent = text || ''; el.classList.toggle('ok', !!ok); }

/* فقط عدد در ورودی ۴ رقم آخر کارت */
$('#f-last4')?.addEventListener('input', (e) => {
  e.target.value = faDigitsToEn(e.target.value).replace(/[^\d]/g, '').slice(0, 4);
});

/* اعمال کد تخفیف */
$('#discount-apply')?.addEventListener('click', async () => {
  const msgEl = $('#discount-msg');
  const code = $('#f-discount').value.trim();
  if (!code) return setStatus(msgEl, 'کد تخفیف رو وارد کن');
  if (!me) { setStatus(msgEl, 'برای استفاده از کد تخفیف اول وارد حسابت شو'); openAuth('login'); return; }
  const btn = $('#discount-apply');
  btn.disabled = true;
  setStatus(msgEl, 'در حال بررسی کد…', true);
  try {
    const d = await api('/api/discounts/validate', { method: 'POST', body: { code, gb: selectedGB, panelId: selectedPanel()?.id || '' } });
    appliedDiscount = { code: d.code, type: d.type, value: d.value };
    $('#f-discount').value = d.code;
    $('#f-discount').disabled = true;
    $('#discount-remove').hidden = false;
    setStatus(msgEl, `کد اعمال شد 🎉 فقط ${toFa(d.finalPrice)} تومان کارت‌به‌کارت کن`, true);
    setSelectedGB(selectedGB);
  } catch (err) {
    clearDiscount(true);
    setStatus(msgEl, err.message || 'کد تخفیف معتبر نیست');
    setSelectedGB(selectedGB);
    btn.disabled = false;
  }
});
$('#discount-remove')?.addEventListener('click', () => {
  clearDiscount();
  $('#f-discount').value = '';
  setSelectedGB(selectedGB);
  $('#f-discount')?.focus();
});

orderForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  setStatus(orderStatus, '');
  if (!me) { openAuth('login'); return; }
  const digits = faDigitsToEn($('#f-last4').value).replace(/[^\d]/g, '');
  const last4 = digits.length >= 4 ? digits.slice(-4) : '';
  if (!/^\d{4}$/.test(last4))
    return setStatus(orderStatus, '۴ رقم آخر کارتی که باهاش پرداخت کردی رو وارد کن');

  const btn = $('#order-submit');
  btn.disabled = true;
  setStatus(orderStatus, 'در حال ثبت سفارش…', true);
  try {
    const data = await api('/api/orders', { method: 'POST', body: { gb: selectedGB, last4, panelId: selectedPanel()?.id || '', ...(appliedDiscount ? { discountCode: appliedDiscount.code } : {}) } });
    localStorage.setItem('nk_last_order', JSON.stringify({ code: data.code, last4 }));
    clearDiscount();
    $('#success-code').textContent = data.code;
    orderForm.hidden = true;
    document.querySelector('.ck-pay').hidden = true;
    const okBox = $('#order-success');
    okBox.hidden = false;
    if (!reducedMotion) gsap.fromTo(okBox, { y: 24, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, ease: 'power3.out' });
    setStatus(orderStatus, '');
    loadMyOrders(true);
    ScrollTrigger.refresh();
  } catch (err) {
    if (err.status === 401) { me = null; renderAuthState(); openAuth('login'); }
    setStatus(orderStatus, err.message || 'خطای شبکه؛ دوباره تلاش کن');
  } finally {
    btn.disabled = false;
  }
});
$('#copy-code')?.addEventListener('click', (e) => copyText($('#success-code').textContent, e.currentTarget, 'کپی شد ✓'));
$('#success-to-orders')?.addEventListener('click', () => {
  setAccTab('orders');
  scrollToTarget('#account');
  loadMyOrders(true);
});
$('#order-again')?.addEventListener('click', () => {
  $('#order-success').hidden = true;
  document.querySelector('.ck-pay').hidden = false;
  orderForm.reset();
  renderAuthState();
});

/* ════════════════ پیگیری سفارش ════════════════ */
const trackForm = $('#track-form');
const trackStatus = $('#track-status');
const trackResult = $('#track-result');

try {
  const last = JSON.parse(localStorage.getItem('nk_last_order') || 'null');
  if (last?.code) { $('#t-code').value = last.code; $('#t-secret').value = last.last4 || ''; }
} catch { /* ignore */ }

const STATUS_FA = { pending: '⏳ در انتظار بررسی پرداخت', approved: '✅ تأیید شده — کانفیگ آماده است', rejected: '❌ رد شده' };
const faDateTime = (iso) => (iso ? new Date(iso).toLocaleString('fa-IR', { dateStyle: 'medium', timeStyle: 'short' }) : '—');

async function renderQrInto(el, text) {
  try {
    const { default: qrcode } = await import('qrcode-generator');
    const qr = qrcode(0, 'M');
    qr.addData(text, 'Byte');
    qr.make();
    el.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
    el.parentElement.hidden = false;
  } catch { el.parentElement.hidden = true; }
}

function renderTrackResult(o) {
  let html = `
    <div class="st-head">
      <span class="st-chip ${o.status}">${STATUS_FA[o.status] || o.status}</span>
      <span class="st-msg">سفارش <b dir="ltr">${o.code}</b> — ${toFa(o.gb)} گیگ / ${toFa(o.days)} روز — ${toFa(o.price)} تومان</span>
    </div>
    <div class="result-meta">
      <span>زمان ثبت: <b>${faDateTime(o.createdAt)}</b></span>
      ${o.decidedAt ? `<span>زمان بررسی: <b>${faDateTime(o.decidedAt)}</b></span>` : ''}
      ${o.expireAt ? `<span>انقضای اشتراک: <b>${faDateTime(o.expireAt)}</b></span>` : ''}
      ${o.discountAmount ? `<span>تخفیف: <b>‏−${toFa(o.discountAmount)} تومان</b> (کد ${o.discountCode || ''})</span>` : ''}
      ${o.username ? `<span>نام کاربری اشتراک: <b dir="ltr">${o.username}</b></span>` : ''}
    </div>`;
  if (o.status === 'pending') {
    html += `<p class="st-msg">پرداختت در حال بررسی است؛ معمولاً چند دقیقه طول می‌کشد. این صفحه را چند دقیقه دیگر دوباره استعلام کن — به‌محض تأیید، لینک اشتراکت همین‌جا نمایش داده می‌شود.</p>`;
  } else if (o.status === 'rejected') {
    html += `<p class="st-msg">متأسفانه پرداخت این سفارش تأیید نشد.${o.rejectReason ? ` علت: <b>${o.rejectReason}</b>` : ''}<br/>اگر اشتباهی شده، یک سفارش جدید با کد پیگیری صحیح ثبت کن.</p>`;
  } else if (o.status === 'approved' && o.subscriptionUrl) {
    html += `
      <p class="st-msg">اشتراکت آماده است 🎉 این لینک را در اپلیکیشن‌ت (v2rayNG، Streisand، Nekoray و…) به‌عنوان اشتراک (Subscription) وارد کن:</p>
      <div class="result-sub">
        <input readonly dir="ltr" value="${o.subscriptionUrl}" aria-label="لینک اشتراک" />
        <button type="button" class="btn btn-primary" data-copy-sub data-hover><span class="btn-label">کپی لینک اشتراک</span></button>
      </div>
      <div class="qr-wrap" hidden>
        <div class="qr-box" id="qr-box"></div>
        <p class="qr-note">با دوربین گوشی یا از داخل اپلیکیشن، این QR را اسکن کن تا اشتراک خودکار اضافه شود. این لینک شخصی است؛ با دیگران به اشتراک نگذار.</p>
      </div>`;
  }
  trackResult.innerHTML = html;
  trackResult.hidden = false;
  if (!reducedMotion) gsap.fromTo(trackResult, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out' });
  ScrollTrigger.refresh();
  const qrBox = $('#qr-box');
  if (qrBox && o.subscriptionUrl) renderQrInto(qrBox, o.subscriptionUrl);
  trackResult.querySelector('[data-copy-sub]')?.addEventListener('click', (e) => copyText(o.subscriptionUrl, e.currentTarget));
}

trackForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  setStatus(trackStatus, '');
  trackResult.hidden = true;
  const code = $('#t-code').value.trim();
  const secret = $('#t-secret').value.trim();
  if (!code || !secret) return setStatus(trackStatus, 'کد پیگیری و ۴ رقم آخر کارت پرداخت (یا کد رسید بانکی) را وارد کن');
  const btn = $('#track-submit');
  btn.disabled = true;
  setStatus(trackStatus, 'در حال استعلام…', true);
  try {
    const res = await fetch('/api/orders/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, secret }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'خطا در استعلام');
    setStatus(trackStatus, '');
    renderTrackResult(data);
  } catch (err) {
    setStatus(trackStatus, err.message || 'خطای شبکه؛ دوباره تلاش کن');
  } finally {
    btn.disabled = false;
  }
});

/* ════════════════ حساب کاربری: ورود/ثبت‌نام ════════════════ */
let me = null;
let recoveryToken = null;
let myTimers = [];
const authModal = $('#auth-modal');

function resetRecoverForm() {
  recoveryToken = null;
  const s2 = $('#recover-step2'); if (s2) s2.hidden = true;
  const em = $('#rc-email'); if (em) em.disabled = false;
  const nm = $('#rc-name'); if (nm) nm.disabled = false;
  const lbl = $('#recover-submit-label'); if (lbl) lbl.textContent = 'پیدا کردن حسابم';
  ['#rc-password', '#rc-password2'].forEach((s) => { const i = $(s); if (i) i.value = ''; });
}
function setAuthTab(tab) {
  $$('[data-auth-tab]').forEach((b) => b.classList.toggle('on', b.dataset.authTab === tab));
  $('#register-form').hidden = tab !== 'register';
  $('#login-form').hidden = tab !== 'login';
  const rf = $('#recover-form'); if (rf) rf.hidden = true;
  resetRecoverForm();
  setStatus($('#auth-status'), '');
}
function showRecover() {
  $$('[data-auth-tab]').forEach((b) => b.classList.remove('on'));
  $('#register-form').hidden = true;
  $('#login-form').hidden = true;
  $('#recover-form').hidden = false;
  resetRecoverForm();
  setStatus($('#auth-status'), '');
  setTimeout(() => $('#rc-email')?.focus(), 60);
}
function openAuth(tab = 'register') {
  if (!authModal) return;
  setAuthTab(tab);
  authModal.hidden = false;
  document.body.style.overflow = 'hidden';
  if (lenis) lenis.stop();
  setTimeout(() => (tab === 'login' ? $('#l-username') : $('#r-name'))?.focus(), 70);
}
function closeAuth() {
  if (!authModal) return;
  authModal.hidden = true;
  document.body.style.overflow = '';
  if (lenis) lenis.start();
}
document.addEventListener('click', (e) => {
  const o = e.target.closest('[data-auth-open]');
  if (o) { e.preventDefault(); openAuth(o.dataset.authOpen || 'register'); }
  if (e.target.closest('[data-auth-close]')) closeAuth();
  const t = e.target.closest('[data-auth-tab]');
  if (t) setAuthTab(t.dataset.authTab);
  const cs = e.target.closest('[data-copy-sub]');
  if (cs && cs.dataset.copySub) copyText(cs.dataset.copySub, cs);
  if (e.target.closest('[data-goto-service]')) { setAccTab('service'); loadMyServices(true); }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeAuth(); if (chatOpen) toggleChat(false); if (menuOpen) setMenu(false); }
});
$('#nav-account')?.addEventListener('click', () => {
  if (me) { setAccTab('service'); scrollToTarget('#account'); }
  else openAuth('login');
});
$('#mm-account')?.addEventListener('click', (e) => {
  e.preventDefault();
  if (menuOpen) setMenu(false);
  if (me) { setAccTab('service'); scrollToTarget('#account'); }
  else openAuth('login');
});
$('#mm-support')?.addEventListener('click', () => {
  if (menuOpen) setMenu(false);
  toggleChat(true);
});

$('#register-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#register-submit');
  btn.disabled = true;
  setStatus($('#auth-status'), 'در حال ساخت حساب…', true);
  try {
    const d = await api('/api/auth/register', {
      method: 'POST',
      body: { name: $('#r-name').value.trim(), username: $('#r-username').value.trim(), password: $('#r-password').value, email: $('#r-email').value.trim() },
    });
    me = d.user;
    closeAuth();
    renderAuthState();
  } catch (err) { setStatus($('#auth-status'), err.message || 'خطا در ثبت‌نام'); }
  finally { btn.disabled = false; }
});
$('#login-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#login-submit');
  btn.disabled = true;
  setStatus($('#auth-status'), 'در حال ورود…', true);
  try {
    const d = await api('/api/auth/login', {
      method: 'POST',
      body: { username: $('#l-username').value.trim(), password: $('#l-password').value },
    });
    me = d.user;
    closeAuth();
    renderAuthState();
  } catch (err) { setStatus($('#auth-status'), err.message || 'خطا در ورود'); }
  finally { btn.disabled = false; }
});
$('#forgot-open')?.addEventListener('click', showRecover);
$('#recover-back')?.addEventListener('click', () => setAuthTab('login'));
$('#recover-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#recover-submit');
  btn.disabled = true;
  try {
    if (!recoveryToken) {
      setStatus($('#auth-status'), 'در حال بررسی…', true);
      const d = await api('/api/auth/recover/start', {
        method: 'POST',
        body: { email: $('#rc-email').value.trim(), name: $('#rc-name').value.trim() },
      });
      recoveryToken = d.token;
      $('#rc-username').textContent = d.username;
      $('#recover-step2').hidden = false;
      $('#rc-email').disabled = true;
      $('#rc-name').disabled = true;
      $('#recover-submit-label').textContent = 'ذخیره رمز جدید و ورود';
      setStatus($('#auth-status'), 'حسابت پیدا شد ✅ رمز جدیدت رو بساز', true);
      setTimeout(() => $('#rc-password')?.focus(), 50);
    } else {
      const p1 = $('#rc-password').value;
      const p2 = $('#rc-password2').value;
      if (p1.length < 6) { setStatus($('#auth-status'), 'رمز جدید باید حداقل ۶ کاراکتر باشه'); return; }
      if (p1 !== p2) { setStatus($('#auth-status'), 'رمز جدید و تکرارش یکی نیستن'); return; }
      setStatus($('#auth-status'), 'در حال ذخیره رمز جدید…', true);
      const d = await api('/api/auth/recover/finish', {
        method: 'POST',
        body: { token: recoveryToken, password: p1 },
      });
      me = d.user;
      resetRecoverForm();
      closeAuth();
      renderAuthState();
    }
  } catch (err) { setStatus($('#auth-status'), err.message || 'خطا در بازیابی حساب'); }
  finally { btn.disabled = false; }
});
$('#profile-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#profile-submit');
  btn.disabled = true;
  setStatus($('#profile-status'), 'در حال ذخیره…', true);
  try {
    const d = await api('/api/auth/profile', {
      method: 'POST',
      body: { name: $('#pf-name').value.trim(), email: $('#pf-email').value.trim() },
    });
    me = d.user;
    setStatus($('#profile-status'), 'ذخیره شد ✅ از این به بعد بازیابی حسابت فعاله', true);
    setTimeout(renderAuthState, 1400);
  } catch (err) { setStatus($('#profile-status'), err.message || 'خطا در ذخیره اطلاعات'); }
  finally { btn.disabled = false; }
});
$('#acc-logout')?.addEventListener('click', async () => {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
  me = null;
  $('#order-success').hidden = true;
  document.querySelector('.ck-pay').hidden = false;
  renderAuthState();
  scrollToTarget('#hero');
});

function startMyPollers() {
  if (myTimers.length) return;
  myTimers = [
    setInterval(() => { if (!document.hidden && me) loadMyOrders(true); }, 20000),
    setInterval(() => { if (!document.hidden && me) loadMyServices(true); }, 30000),
    setInterval(() => { if (!document.hidden && me && !chatOpen) updateChatBadge(); }, 25000),
  ];
}
function stopMyPollers() { myTimers.forEach(clearInterval); myTimers = []; }

function renderAuthState() {
  const label = $('#nav-account-label');
  if (label) label.textContent = me ? me.username : 'ورود / ثبت‌نام';
  const mmLabel = $('#mm-account-label');
  if (mmLabel) mmLabel.textContent = me ? 'حساب من' : 'ورود / ثبت‌نام';
  const mmSub = $('#mm-account-sub');
  if (mmSub) mmSub.textContent = me ? me.username : 'برای خرید و مشاهده سرویس خود وارد شوید';
  const gate = $('#ck-need-login');
  if (gate) gate.hidden = !!me;
  if (orderForm) orderForm.hidden = !me || !$('#order-success').hidden;
  const acc = $('#account');
  if (acc) acc.hidden = !me || currentPage !== 'account';
  refreshChatAuthUI();
  loadReviews();
  routeOnAuth();
  if (me) {
    $('#acc-username').textContent = me.name || me.username;
    const pf = $('#profile-form');
    if (pf) {
      const incomplete = !me.name || !me.email;
      pf.hidden = !incomplete;
      if (incomplete && !pf.contains(document.activeElement)) {
        $('#pf-name').value = me.name || '';
        $('#pf-email').value = me.email || '';
      }
    }
    loadMyOrders(true);
    loadMyServices(true);
    startMyPollers();
    updateChatBadge();
    if (afterAuthGo) { const t = afterAuthGo; afterAuthGo = null; setTimeout(() => goAccount(t), 150); }
  } else {
    clearDiscount(true);
    if (typeof setSelectedGB === 'function') setSelectedGB(selectedGB);
    stopMyPollers();
    setChatBadge(0);
    const bb = $('#bnav-orders-badge'); if (bb) bb.hidden = true;
    setBnavActive('home');
  }
  ScrollTrigger.refresh();
}

/* ════════════════ پنل کاربری: سفارشات + سرویس من ════════════════ */
function setAccTab(name) {
  $$('.acc-tab').forEach((b) => b.classList.toggle('on', b.dataset.accTab === name));
  $('#acc-service').hidden = name !== 'service';
  $('#acc-orders').hidden = name !== 'orders';
  setBnavActive(name);
  ScrollTrigger.refresh();
}
$$('.acc-tab').forEach((b) => b.addEventListener('click', () => {
  setAccTab(b.dataset.accTab);
  if (b.dataset.accTab === 'service') loadMyServices(true);
  else loadMyOrders(true);
}));
$('#svc-refresh')?.addEventListener('click', () => loadMyServices());

async function loadMyOrders(silent) {
  if (!me) return;
  try {
    const { orders } = await api('/api/my/orders');
    renderMyOrders(orders);
  } catch (e) {
    if (!silent) $('#my-orders-list').innerHTML = `<p class="acc-empty">خطا: ${esc(e.message)}</p>`;
  }
}
function renderMyOrders(list) {
  const badge = $('#orders-badge');
  const pend = list.filter((o) => o.status === 'pending').length;
  if (badge) { badge.hidden = !pend; badge.textContent = faNum(pend); }
  const bb = $('#bnav-orders-badge');
  if (bb) { bb.hidden = !pend; bb.textContent = faNum(pend); }
  $('#my-orders-list').innerHTML = list.length ? list.map((o) => `
    <article class="my-order">
      <div class="mo-head"><b dir="ltr">${esc(o.code)}</b><span class="st-chip ${o.status}">${STATUS_FA[o.status] || o.status}</span></div>
      <div class="mo-meta">
        <span>حجم: <b>${faNum(o.gb)} گیگ / ${faNum(o.days)} روز</b></span>
        <span>مبلغ: <b>${faNum(o.price)} تومان</b></span>
        ${o.panelName ? `<span>پنل: <b>${esc(o.panelName)}</b></span>` : ''}
        ${o.discountAmount ? `<span>🎟 تخفیف: <b>‏−${faNum(o.discountAmount)} تومان</b> (کد ${esc(o.discountCode || '')})</span>` : ''}
        ${o.last4 ? `<span>کارت پرداخت: <b dir="ltr">•••• ${esc(o.last4)}</b></span>` : ''}
        <span>ثبت: <b>${faDateTime(o.createdAt)}</b></span>
        ${o.status === 'rejected' && o.rejectReason ? `<span>علت رد: <b>${esc(o.rejectReason)}</b></span>` : ''}
      </div>
      ${o.status === 'pending' ? '<p class="st-msg" style="margin-top:8px">پرداختت در حال بررسیه ⏳ به‌محض تأیید، اشتراکت توی تب «سرویس من» فعال میشه.</p>' : ''}
      ${o.status === 'rejected' ? '<p class="st-msg" style="margin-top:8px">اگه فکر می‌کنی اشتباهی شده، از چت پشتیبانی پیام بده یا یه سفارش جدید ثبت کن.</p>' : ''}
      ${o.status === 'approved' ? '<button type="button" class="btn btn-primary btn-sm" data-goto-service data-hover style="margin-top:10px"><span class="btn-label">🚀 مشاهده اشتراک در سرویس من</span></button>' : ''}
    </article>`).join('')
    : '<p class="acc-empty">هنوز سفارشی نداری 🌙<br>از بخش خرید، اولین کانفیگت رو بگیر.</p>';
}

const PG_STATUS_FA = { active: '🟢 فعال', limited: '🔴 حجم تمام شده', expired: '⚫ منقضی شده', disabled: '⛔ غیرفعال', on_hold: '⏸ در انتظار فعال‌سازی' };
async function loadMyServices(silent) {
  if (!me) return;
  try {
    const { services } = await api('/api/my/services');
    renderServices(services);
  } catch (e) {
    if (!silent) $('#service-list').innerHTML = `<p class="acc-empty">خطا در دریافت: ${esc(e.message)}</p>`;
  }
}
function renderServices(list) {
  const note = $('#svc-live-note');
  if (!list.length) {
    $('#service-list').innerHTML = '<p class="acc-empty">هنوز اشتراک فعالی نداری 🌙<br>وقتی سفارشت تأیید بشه، اشتراکت همین‌جا با لینک و QR آماده‌ست.</p>';
    if (note) { note.textContent = 'اشتراکی فعال نیست'; note.classList.add('stale'); }
    return;
  }
  const anyLive = list.some((s) => s.live);
  if (note) {
    note.textContent = anyLive ? `🟢 زنده — آخرین به‌روزرسانی ${new Date().toLocaleTimeString('fa-IR')}` : '🟡 نمایش آخرین اطلاعات ذخیره‌شده';
    note.classList.toggle('stale', !anyLive);
  }
  $('#service-list').innerHTML = list.map((s) => {
    const limit = s.dataLimit || 0;
    const used = s.usedTraffic;
    const remain = used == null ? null : Math.max(0, limit - used);
    const pct = used == null || !limit ? 0 : Math.min(100, Math.round((used / limit) * 100));
    const daysLeft = s.expire ? Math.max(0, Math.ceil((s.expire * 1000 - Date.now()) / 86400000)) : null;
    const fillCls = pct >= 90 ? 'danger' : pct >= 70 ? 'warn' : '';
    return `<article class="svc-card" data-svc-card="${esc(s.code)}">
      <div class="svc-head"><b>اشتراک <span dir="ltr">${esc(s.code)}</span></b><span class="st-chip ${s.status === 'active' ? 'approved' : 'pending'}">${PG_STATUS_FA[s.status] || s.status}</span></div>
      <div class="svc-stats">
        <div class="svc-stat"><strong>${remain == null ? '—' : fmtGB(remain)}<em> گیگ</em></strong><span>حجم باقی‌مانده</span></div>
        <div class="svc-stat"><strong>${daysLeft == null ? '—' : faNum(daysLeft)}<em> روز</em></strong><span>زمان باقی‌مانده</span></div>
        <div class="svc-stat"><strong>${used == null ? '—' : fmtGB(used)}<em> گیگ</em></strong><span>مصرف‌شده</span></div>
      </div>
      <div class="usage">
        <div class="usage-top"><span>میزان مصرف</span><span>${used == null ? '—' : faNum(pct) + '٪'} از ${fmtGB(limit)} گیگ</span></div>
        <div class="usage-bar"><div class="usage-fill ${fillCls}" style="width:${pct}%"></div></div>
      </div>
      <div class="svc-meta">
        ${s.panelName ? `<span>پنل: <b>${esc(s.panelName)}</b></span>` : ''}
        ${s.expire ? `<span>انقضا: <b>${faDateTime(new Date(s.expire * 1000).toISOString())}</b></span>` : ''}
        ${s.username ? `<span>نام اشتراک: <b dir="ltr">${esc(s.username)}</b></span>` : ''}
        <span>${s.live ? '🟢 اطلاعات زنده' : '🟡 اطلاعات ذخیره‌شده'}</span>
      </div>
      ${s.subUrl ? `<div class="result-sub">
        <input readonly dir="ltr" value="${esc(s.subUrl)}" aria-label="لینک اشتراک" />
        <button type="button" class="btn btn-primary" data-copy-sub="${esc(s.subUrl)}" data-hover><span class="btn-label">کپی لینک اشتراک</span></button>
      </div>
      <div class="qr-wrap" hidden><div class="qr-box" data-qr="${esc(s.subUrl)}"></div><p class="qr-note">QR را با اپلیکیشن (v2rayNG / Streisand / Nekoray…) اسکن کن تا اشتراک خودکار اضافه شود. این لینک شخصی است؛ به کسی نده.</p></div>` : ''}
      ${s.username ? `<div class="svc-actions">
        <button type="button" class="btn btn-ghost btn-sm" data-svc="extend-open" data-hover><span class="btn-label">📅 تمدید زمان (رایگان)</span></button>
        <button type="button" class="btn btn-ghost btn-sm" data-svc="revoke" data-hover><span class="btn-label">🔄 تغییر لینک اشتراک</span></button>
        <button type="button" class="btn ${s.status === 'disabled' ? 'btn-primary' : 'btn-ghost'} btn-sm" data-svc="toggle" data-on="${s.status === 'disabled' ? '1' : '0'}" data-hover><span class="btn-label">${s.status === 'disabled' ? '▶ روشن کردن اشتراک' : '⏸ توقف اشتراک'}</span></button>
        <button type="button" class="btn btn-ghost btn-sm" data-svc="report-open" data-hover><span class="btn-label">🚨 گزارش مشکل سرویس</span></button>
      </div>
      <div class="svc-extend" data-extend-box hidden>
        <label>چند روز اضافه بشه؟ <input type="number" min="1" max="365" step="1" value="30" data-extend-days inputmode="numeric" dir="ltr" /> روز</label>
        <button type="button" class="btn btn-primary btn-sm" data-svc="extend-go" data-hover><span class="btn-label">تمدید کن</span></button>
        <small>رایگانه — هر بار حداکثر ۳۶۵ روز. حجم اشتراکت تغییری نمی‌کنه.</small>
      </div>
      <div class="svc-report" data-report-box hidden>
        ${s.reportOpen ? '<p class="svc-report-open">📨 یک گزارش برای این سرویس فرستادی و در حال بررسی است؛ به‌زودی رسیدگی می‌کنیم 🙏</p>' : `<label class="svc-report-label" for="report-text-${esc(s.code)}">مشکل سرویس رو بنویس تا سریع رسیدگی کنیم:</label>
        <textarea id="report-text-${esc(s.code)}" data-report-text rows="3" maxlength="1000" placeholder="مثلاً: از امروز صبح وصل نمیشه…"></textarea>
        <button type="button" class="btn btn-primary btn-sm" data-svc="report-go" data-hover><span class="btn-label">ارسال گزارش</span></button>`}
      </div>` : ''}
    </article>`;
  }).join('');
  $$('#service-list [data-qr]').forEach((el) => renderQrInto(el, el.dataset.qr));
  ScrollTrigger.refresh();
}

/* عملیات روی اشتراک: تمدید رایگان زمان، تغییر لینک، توقف/روشن */
$('#service-list')?.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-svc]');
  if (!btn) return;
  const card = btn.closest('[data-svc-card]');
  const code = card?.dataset.svcCard;
  if (!code) return;
  const act = btn.dataset.svc;
  if (act === 'extend-open') {
    const box = card.querySelector('[data-extend-box]');
    if (box) { box.hidden = !box.hidden; if (!box.hidden) box.querySelector('[data-extend-days]')?.focus(); }
    return;
  }
  if (act === 'report-open') {
    const box = card.querySelector('[data-report-box]');
    if (box) { box.hidden = !box.hidden; if (!box.hidden) box.querySelector('[data-report-text]')?.focus(); }
    return;
  }
  if (act === 'report-go') {
    const ta = card.querySelector('[data-report-text]');
    const text = (ta?.value || '').trim();
    if (text.length < 5) return setStatus($('#svc-action-msg'), 'مشکل رو یکم کامل‌تر بنویس تا بتونیم کمک کنیم');
    btn.disabled = true;
    setStatus($('#svc-action-msg'), 'در حال ارسال گزارش…', true);
    try {
      await api(`/api/my/services/${encodeURIComponent(code)}/report`, { method: 'POST', body: { text } });
      setStatus($('#svc-action-msg'), '✅ گزارشت ثبت شد؛ سریع بررسی می‌کنیم و همین‌جا یا از پشتیبانی خبرت می‌کنیم', true);
      loadMyServices(true);
    } catch (err) {
      setStatus($('#svc-action-msg'), err.message || 'خطا در ارسال گزارش');
      btn.disabled = false;
    }
    return;
  }
  let path = '', body = {}, doing = '', done = '';
  if (act === 'extend-go') {
    const days = Math.floor(Number(card.querySelector('[data-extend-days]')?.value));
    if (!days || days < 1 || days > 365) return setStatus($('#svc-action-msg'), 'عدد روزها باید بین ۱ تا ۳۶۵ باشد');
    path = 'extend-time'; body = { days }; doing = 'در حال تمدید زمان…'; done = `✅ ${faNum(days)} روز به اشتراکت اضافه شد`;
  } else if (act === 'revoke') {
    if (!confirm('لینک اشتراک فعلی باطل می‌شود و یک لینک تازه ساخته می‌شود؛ باید لینک جدید را در اپلیکیشنت وارد کنی. ادامه می‌دهی؟')) return;
    path = 'revoke-sub'; doing = 'در حال ساخت لینک تازه…'; done = '✅ لینک اشتراکت عوض شد — لینک و QR جدید را از همین کارت بردار';
  } else if (act === 'toggle') {
    const on = btn.dataset.on === '1';
    if (!on && !confirm('اشتراکت متوقف می‌شود و کانفیگ از کار می‌افتد تا وقتی دوباره روشنش کنی. مطمئنی؟')) return;
    path = 'toggle'; body = { on }; doing = on ? 'در حال روشن‌کردن…' : 'در حال توقف…'; done = on ? '✅ اشتراکت روشن شد' : '⏸ اشتراکت متوقف شد';
  } else return;
  btn.disabled = true;
  setStatus($('#svc-action-msg'), doing, true);
  try {
    await api(`/api/my/services/${encodeURIComponent(code)}/${path}`, { method: 'POST', body });
    setStatus($('#svc-action-msg'), done, true);
    loadMyServices(true);
  } catch (err) {
    setStatus($('#svc-action-msg'), err.message || 'خطا در انجام عملیات');
    btn.disabled = false;
  }
});

/* ════════════════ چت پشتیبانی ════════════════ */
const chatPanel = $('#chat-panel');
const chatMsgs = $('#chat-msgs');
let chatOpen = false, chatPollId = null, lastChatSig = '', chatMsgsCache = [], chatReplyTo = null;

function setChatBadge(n) {
  const b = $('#bnav-chat-badge');
  if (!b) return;
  b.hidden = !n;
  b.textContent = faNum(n);
}
function refreshChatAuthUI() {
  const nl = $('#chat-need-login');
  const cf = $('#chat-form');
  if (nl) nl.hidden = !!me;
  if (cf) cf.hidden = !me;
  if (!me && chatMsgs) chatMsgs.innerHTML = '<p class="chat-p-empty">سلام! 👋<br>برای گفت‌وگو با پشتیبانی اول وارد شو.</p>';
}
async function updateChatBadge() {
  if (!me) return setChatBadge(0);
  try { const d = await api('/api/my/chat?peek=1'); if (!chatOpen) setChatBadge(d.unread || 0); } catch { /* ignore */ }
}
function renderChat(msgs, forceScroll) {
  const sig = `${msgs.length}:${msgs[msgs.length - 1]?.id || ''}:${msgs.filter((m) => m.read).length}`;
  if (sig === lastChatSig && !forceScroll) return;
  lastChatSig = sig;
  chatMsgsCache = msgs;
  const nearBottom = chatMsgs.scrollHeight - chatMsgs.scrollTop - chatMsgs.clientHeight < 170;
  chatMsgs.innerHTML = msgs.length
    ? msgs.map((m) => `<div class="cmsg ${m.from === 'user' ? 'me' : 'them'}" data-mid="${esc(m.id)}">${m.replyTo ? `<span class="cmsg-q"><b>${m.replyTo.from === 'user' ? 'شما' : 'پشتیبانی ورتکس‌نت'}</b>${esc(m.replyTo.text)}</span>` : ''}${esc(m.text)}<small>${faDateTime(m.at)}${m.from === 'user' && m.read ? ' · خوانده شد ✓✓' : ''}</small></div>`).join('')
    : '<p class="chat-p-empty">سلام! 👋<br>سؤالت رو بپرس، زود جواب میدیم.</p>';
  if (forceScroll || nearBottom) chatMsgs.scrollTop = chatMsgs.scrollHeight;
}
async function loadChat(forceScroll) {
  if (!me) return;
  try {
    const d = await api('/api/my/chat');
    renderChat(d.messages || [], forceScroll);
    setChatBadge(0);
  } catch { /* ignore */ }
}
function toggleChat(open) {
  chatOpen = open;
  if (chatPanel) chatPanel.hidden = !open;
  clearInterval(chatPollId);
  if (open) {
    setBnavActive('chat');
    refreshChatAuthUI();
    lastChatSig = '';
    loadChat(true);
    chatPollId = setInterval(() => { if (!document.hidden) loadChat(false); }, 4000);
    if (me) setTimeout(() => $('#chat-input')?.focus(), 90);
  } else {
    updateChatBadge();
    spyBnav();
  }
}

/* ════════════════ ناوبری پایین صفحه ════════════════ */
let afterAuthGo = null;
function setBnavActive(name) {
  $$('.bnav-item').forEach((b) => b.classList.toggle('on', b.dataset.bnav === name));
}
function goAccount(tab) {
  if (!me) { afterAuthGo = tab; openAuth('login'); return; }
  setAccTab(tab);
  scrollToTarget('#account');
  if (tab === 'orders') loadMyOrders(true); else loadMyServices(true);
}
$$('.bnav-item').forEach((b) => b.addEventListener('click', () => {
  const k = b.dataset.bnav;
  if (k === 'home') { setBnavActive('home'); scrollToTarget('#hero'); }
  else if (k === 'chat') toggleChat(!chatOpen);
  else goAccount(k);
}));
function spyBnav() {
  if (chatOpen) return;
  if (currentPage === 'account') setBnavActive($('#acc-orders').hidden ? 'service' : 'orders');
  else if (currentPage === 'home') setBnavActive('home');
}
let spyTick = false;
window.addEventListener('scroll', () => {
  if (spyTick) return;
  spyTick = true;
  requestAnimationFrame(() => { spyBnav(); spyTick = false; });
}, { passive: true });
$('#chat-close')?.addEventListener('click', () => toggleChat(false));
$('#acc-chat-open')?.addEventListener('click', () => toggleChat(true));
$('#chat-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const inp = $('#chat-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  try {
    await api('/api/my/chat', { method: 'POST', body: { text, replyToId: chatReplyTo ? chatReplyTo.id : undefined } });
    clearChatReply();
    lastChatSig = '';
    loadChat(true);
  } catch { inp.value = text; }
});

/* ════════════════ ریپلای با سوایپ در چت ════════════════ */
const chatReplyBar = $('#chat-reply-bar');
const chatSwipeHint = $('#chat-swipe-hint');
function setChatReply(id) {
  const src = chatMsgsCache.find((m) => m.id === id);
  if (!src) return;
  chatReplyTo = { id: src.id };
  const who = $('#chat-reply-who');
  if (who) who.textContent = src.from === 'user' ? 'پاسخ به پیام شما' : 'پاسخ به پشتیبانی';
  const txt = $('#chat-reply-text');
  if (txt) txt.textContent = String(src.text || '').slice(0, 90);
  if (chatReplyBar) chatReplyBar.hidden = false;
  $('#chat-input')?.focus();
}
function clearChatReply() {
  chatReplyTo = null;
  if (chatReplyBar) chatReplyBar.hidden = true;
}
$('#chat-reply-x')?.addEventListener('click', clearChatReply);

/* کشیدن پیام به سمت چپ = پاسخ (انگشت و موس، با Pointer Events) */
(() => {
  if (!chatMsgs) return;
  let sw = null;
  const THRESH = 54;
  const pullOf = (dx) => (dx >= 0 ? 0 : dx < -70 ? -70 + (dx + 70) * 0.22 : dx);
  const reset = (el, snap) => {
    if (chatSwipeHint) chatSwipeHint.style.opacity = '0';
    if (!el) return;
    el.classList.toggle('snap', !!snap);
    el.style.transform = '';
    if (snap) setTimeout(() => el.classList.remove('snap'), 280);
  };
  chatMsgs.addEventListener('pointerdown', (e) => {
    const el = e.target.closest('.cmsg[data-mid]');
    if (!el || (e.pointerType === 'mouse' && e.button !== 0)) return;
    sw = { el, id: el.dataset.mid, x0: e.clientX, y0: e.clientY, pid: e.pointerId, on: false, pull: 0 };
  });
  chatMsgs.addEventListener('pointermove', (e) => {
    if (!sw || e.pointerId !== sw.pid) return;
    const dx = e.clientX - sw.x0;
    const dy = e.clientY - sw.y0;
    if (!sw.on) {
      if (Math.abs(dx) < 9 || Math.abs(dy) > Math.abs(dx) * 1.15) return;
      sw.on = true;
      try { sw.el.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      sw.el.classList.remove('snap');
    }
    sw.pull = pullOf(dx);
    sw.el.style.transform = `translateX(${sw.pull}px)`;
    if (chatSwipeHint && chatPanel) {
      const pr = chatPanel.getBoundingClientRect();
      const br = sw.el.getBoundingClientRect();
      chatSwipeHint.style.top = `${br.top - pr.top + br.height / 2}px`;
      const k = Math.min(1, -sw.pull / THRESH);
      chatSwipeHint.style.opacity = String(k);
      chatSwipeHint.style.transform = `translateY(-50%) scale(${0.7 + 0.3 * k})`;
      chatSwipeHint.classList.toggle('go', -sw.pull >= THRESH);
    }
  });
  const finish = (e) => {
    if (!sw || e.pointerId !== sw.pid) return;
    const { el, id, on, pull } = sw;
    sw = null;
    if (on && -pull >= THRESH) setChatReply(id);
    reset(el, true);
  };
  chatMsgs.addEventListener('pointerup', finish);
  chatMsgs.addEventListener('pointercancel', finish);
  window.addEventListener('pointerup', () => { if (sw) { const el = sw.el; sw = null; reset(el, true); } }, { passive: true });
})();

/* ════════════════ اطلاعیه‌های همگانی ════════════════ */
function annCardHtml(a) {
  return `<article class="news-card${a.level === 'important' ? ' hot' : ''}">
    <header class="news-head">
      <h3>${esc(a.title)}</h3>
      ${a.pinned ? '<span class="news-tag pin">سنجاق شده</span>' : ''}${a.level === 'important' ? '<span class="news-tag imp">مهم</span>' : ''}
    </header>
    <p class="news-body">${esc(a.body)}</p>
    <small class="news-date">${faDateTime(a.createdAt)}</small>
  </article>`;
}
async function loadAnnouncements() {
  try {
    const d = await api('/api/announcements');
    const list = d.announcements || [];
    const box = $('#news-list');
    if (box) box.innerHTML = list.length ? list.map(annCardHtml).join('') : '<p class="news-empty">فعلاً اطلاعیه‌ای منتشر نشده است.</p>';
    const pill = $('#ann-pill');
    if (pill) {
      const top = list[0];
      let dismissed = '';
      try { dismissed = localStorage.getItem('vx_ann_off') || ''; } catch { /* ignore */ }
      pill.hidden = !top || dismissed === top.id;
      if (top) {
        pill.dataset.annId = top.id;
        const t = $('#ann-pill-text');
        if (t) t.textContent = top.title;
      }
    }
  } catch { /* ignore */ }
}
$('#ann-pill')?.addEventListener('click', (e) => {
  const pill = $('#ann-pill');
  if (!pill) return;
  if (e.target.closest('#ann-pill-x')) {
    try { localStorage.setItem('vx_ann_off', pill.dataset.annId || ''); } catch { /* ignore */ }
    pill.hidden = true;
    return;
  }
  scrollToTarget('#news');
});
loadAnnouncements();

/* ════════════════ نظرات مشتریان (ناشناس) ════════════════ */
function revCardHtml(c) {
  return `<article class="rev-card">
    <header class="rev-head">
      <span class="rev-ava" aria-hidden="true"><svg><use href="#ic-user"/></svg></span>
      <b>مشتری ورتکس‌نت</b>
      <span class="rev-anon">ناشناس</span>
      <small>${faDateTime(c.createdAt)}</small>
    </header>
    <p class="rev-text">${esc(c.text)}</p>
  </article>`;
}
async function loadReviews() {
  const listEl = $('#reviews-list');
  if (listEl) {
    try {
      const d = await api('/api/comments');
      const list = d.comments || [];
      listEl.innerHTML = list.length ? list.map(revCardHtml).join('') : '<p class="news-empty">هنوز نظری منتشر نشده؛ اولین نفر باش که تجربه‌اش را می‌گوید!</p>';
    } catch { /* ignore */ }
  }
  const form = $('#rev-form');
  const need = $('#rev-need-login');
  const mineBox = $('#rev-mine');
  if (form) form.hidden = !me;
  if (need) need.hidden = !!me;
  if (mineBox) {
    if (!me) { mineBox.hidden = true; mineBox.innerHTML = ''; }
    else {
      try {
        const md = await api('/api/my/comments');
        const mine = (md.comments || []).filter((c) => c.status === 'pending');
        mineBox.hidden = !mine.length;
        mineBox.innerHTML = mine.length
          ? '<p class="rev-mine-t">نظرهای شما در انتظار تأیید مدیریت:</p>' + mine.map((c) => `
            <div class="rev-mine-row">
              <p>${esc(c.text)}</p>
              <button type="button" class="btn btn-ghost btn-sm" data-rev-del="${esc(c.id)}" data-hover><span class="btn-label">حذف</span></button>
            </div>`).join('')
          : '';
      } catch { mineBox.hidden = true; }
    }
  }
}
$('#rev-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const ta = $('#rev-text');
  const msgEl = $('#rev-msg');
  const text = (ta?.value || '').trim();
  if (text.length < 3) {
    if (msgEl) { msgEl.textContent = 'نظرت خیلی کوتاهه؛ چند کلمه بیشتر بنویس 🙂'; msgEl.className = 'err'; }
    return;
  }
  const btn = $('#rev-submit');
  if (btn) btn.disabled = true;
  try {
    await api('/api/comments', { method: 'POST', body: { text } });
    if (ta) ta.value = '';
    if (msgEl) { msgEl.textContent = 'نظرت ثبت شد ✓ بعد از تأیید مدیریت، به‌صورت ناشناس همین‌جا نمایش داده می‌شه.'; msgEl.className = 'ok'; }
    loadReviews();
  } catch (err) {
    if (msgEl) { msgEl.textContent = err.message; msgEl.className = 'err'; }
  } finally { if (btn) btn.disabled = false; }
});
$('#rev-mine')?.addEventListener('click', async (e) => {
  const del = e.target.closest('[data-rev-del]');
  if (!del) return;
  try {
    await api(`/api/my/comments/${encodeURIComponent(del.dataset.revDel)}/delete`, { method: 'POST' });
    loadReviews();
  } catch { /* ignore */ }
});

/* راه‌اندازی وضعیت ورود */
(async () => {
  try { me = (await api('/api/auth/me')).user; }
  catch { me = null; }
  renderAuthState();
})();

/* ════════════════ آکاردئون سوالات متداول ════════════════ */
$$('.faq-item').forEach((item) => {
  const btn = item.querySelector('.faq-q');
  const panel = item.querySelector('.faq-a');
  btn.addEventListener('click', () => {
    const isOpen = item.classList.contains('open');
    $$('.faq-item.open').forEach((other) => {
      other.classList.remove('open');
      other.querySelector('.faq-q').setAttribute('aria-expanded', 'false');
      other.querySelector('.faq-a').style.maxHeight = '0px';
    });
    if (!isOpen) {
      item.classList.add('open');
      btn.setAttribute('aria-expanded', 'true');
      panel.style.maxHeight = `${panel.scrollHeight}px`;
    }
    setTimeout(() => ScrollTrigger.refresh(), 600);
  });
});

/* ════════════════ سفر مورفینگ سه‌بعدی با اسکرول ════════════════ */
function initScrollJourney(sceneApi) {
  const st = sceneApi.state;
  const isSmallScreen = window.innerWidth < 981;
  const side = isSmallScreen ? 0 : 1.9;

  gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: { trigger: document.body, start: 'top top', end: 'bottom bottom', scrub: 1.1 },
  })
    .to(st, { posX: side, posY: -0.2, distort: 0.3, palette: 0.35, scale: 0.92, camZ: 8.8, duration: 1 })
    .to(st, { posX: -side, posY: 0.25, distort: 0.62, freq: 0.7, palette: 1.05, scale: 1.0, duration: 1 })
    .to(st, { posX: 0, posY: 0.9, distort: 0.95, freq: 1.15, palette: 2.0, scale: 0.8, camZ: 10.5, spin: 1.7, duration: 1 })
    .to(st, { posX: side, posY: 0, distort: 0.55, freq: 0.9, palette: 2.9, scale: 0.95, camZ: 8.6, spin: 1.1, duration: 1 })
    .to(st, { posX: 0, posY: -0.3, distort: 0.48, palette: 3.0, scale: 1.22, camZ: 6.4, spin: 0.6, duration: 1 });
}

/* ════════════════ مغناطیس + تیلت کارت + کرسر (فقط دسکتاپ) ════════════════ */
if (finePointer && !reducedMotion) {
  $$('.magnetic').forEach((el) => {
    const xTo = gsap.quickTo(el, 'x', { duration: 0.45, ease: 'power3.out' });
    const yTo = gsap.quickTo(el, 'y', { duration: 0.45, ease: 'power3.out' });
    el.addEventListener('pointermove', (e) => {
      const r = el.getBoundingClientRect();
      xTo((e.clientX - (r.left + r.width / 2)) * 0.34);
      yTo((e.clientY - (r.top + r.height / 2)) * 0.34);
    });
    el.addEventListener('pointerleave', () => {
      gsap.to(el, { x: 0, y: 0, duration: 0.85, ease: 'elastic.out(1, 0.4)' });
    });
  });

  $$('.tilt').forEach((card) => {
    const rx = gsap.quickTo(card, 'rotationX', { duration: 0.6, ease: 'power3.out' });
    const ry = gsap.quickTo(card, 'rotationY', { duration: 0.6, ease: 'power3.out' });
    gsap.set(card, { transformPerspective: 900 });
    card.addEventListener('pointermove', (e) => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      ry((px - 0.5) * 9); rx((0.5 - py) * 9);
      card.style.setProperty('--mx', `${px * 100}%`);
      card.style.setProperty('--my', `${py * 100}%`);
    });
    card.addEventListener('pointerleave', () => { rx(0); ry(0); });
  });

  document.body.classList.add('has-cursor');
  const dot = $('#cursor-dot'), ring = $('#cursor-ring');
  gsap.set([dot, ring], { xPercent: -50, yPercent: -50, x: -100, y: -100 });
  const dx = gsap.quickTo(dot, 'x', { duration: 0.12, ease: 'power3.out' });
  const dy = gsap.quickTo(dot, 'y', { duration: 0.12, ease: 'power3.out' });
  const rxq = gsap.quickTo(ring, 'x', { duration: 0.42, ease: 'power3.out' });
  const ryq = gsap.quickTo(ring, 'y', { duration: 0.42, ease: 'power3.out' });
  let cursorShown = false;
  window.addEventListener('pointermove', (e) => {
    if (!cursorShown) { gsap.to([dot, ring], { opacity: 1, duration: 0.4 }); cursorShown = true; }
    dx(e.clientX); dy(e.clientY); rxq(e.clientX); ryq(e.clientY);
  }, { passive: true });
  const hoverSel = 'a, button, [data-hover], input';
  document.addEventListener('pointerover', (e) => ring.classList.toggle('is-hover', !!e.target.closest(hoverSel)));
}

window.addEventListener('load', () => ScrollTrigger.refresh());
