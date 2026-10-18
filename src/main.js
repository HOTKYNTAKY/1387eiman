import './style.css';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
/* three/scene.js is dynamically imported below so first paint stays fast */

gsap.registerPlugin(ScrollTrigger);
document.documentElement.classList.add('js');

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const finePointer = window.matchMedia('(pointer: fine)').matches;
const $ = (s, c = document) => c.querySelector(s);
const $$ = (s, c = document) => [...c.querySelectorAll(s)];

$('#year').textContent = new Date().getFullYear();

/* ════════════════ WebGL (lazy-loaded; CSS fallback if unavailable) ════════════════ */
let aether = null;
if (!reducedMotion) {
  import('./three/scene.js')
    .then(({ createAetherScene }) => {
      aether = createAetherScene($('#webgl'), { reducedMotion });
      if (aether) initScrollJourney(aether);
      else document.body.classList.add('no-webgl');
    })
    .catch(() => document.body.classList.add('no-webgl'));
} else {
  document.body.classList.add('no-webgl');
}

/* ════════════════ Smooth scroll (Lenis + GSAP ticker) ════════════════ */
let lenis = null;
if (!reducedMotion) {
  lenis = new Lenis({ lerp: 0.09, wheelMultiplier: 1, smoothWheel: true });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);
}
const scrollToTarget = (target, immediate = false) => {
  const el = typeof target === 'string' ? $(target) : target;
  if (!el) return;
  if (lenis) lenis.scrollTo(el, { immediate, offset: 0, duration: immediate ? 0 : 1.4 });
  else el.scrollIntoView({ behavior: immediate || reducedMotion ? 'auto' : 'smooth' });
};

/* ════════════════ Split hero title into chars (plain lines only) ════════════════ */
$$('[data-split]').forEach((el) => {
  if (el.tagName === 'EM') return; // gradient serif line animates as one piece
  const text = el.textContent;
  el.setAttribute('aria-hidden', 'true');
  el.textContent = '';
  [...text].forEach((ch) => {
    const s = document.createElement('span');
    s.className = 'char';
    s.textContent = ch === ' ' ? ' ' : ch;
    el.appendChild(s);
  });
});

/* ════════════════ Preloader ════════════════ */
document.body.classList.add('is-loading');
if (lenis) lenis.stop();

const heroIntro = () => {
  const tl = gsap.timeline({ defaults: { ease: 'power4.out' } });
  tl.to('#preloader .loader-inner', { yPercent: -30, opacity: 0, duration: 0.55, ease: 'power3.in' })
    .to('#preloader', { yPercent: -100, duration: 0.9, ease: 'power4.inOut' }, '-=0.1')
    .set('#preloader', { display: 'none' })
    .add(() => { document.body.classList.remove('is-loading'); if (lenis) lenis.start(); }, '-=0.55')
    .from('.hero-title .char', { yPercent: 120, rotate: 5, duration: 1.05, stagger: 0.028 }, '-=0.55')
    .from('.hero-title em', { yPercent: 115, duration: 1.15 }, '<0.12')
    .to('.hero .hero-anim:not(.hero-side)', { opacity: 1, y: 0, duration: 0.9, stagger: 0.09 }, '-=0.7')
    .to('.hero-side', { opacity: 1, duration: 1 }, '<0.2');
  return tl;
};

if (reducedMotion) {
  gsap.set('#preloader', { display: 'none' });
  gsap.set('.hero-anim, [data-reveal]', { opacity: 1 });
  document.body.classList.remove('is-loading');
} else {
  gsap.set('.hero .hero-anim:not(.hero-side)', { y: 34 });
  const counter = { v: 0 };
  const countEl = $('#loader-count');
  const barEl = $('#loader-bar-fill');
  gsap.to(counter, {
    v: 100, duration: 1.6, ease: 'power2.inOut',
    onUpdate() {
      const n = Math.round(counter.v);
      countEl.textContent = String(n).padStart(2, '0');
      barEl.style.width = `${n}%`;
    },
    onComplete: heroIntro,
  });
}

/* ════════════════ Nav behaviour ════════════════ */
const nav = $('#site-nav');
const onScrollNav = () => nav.classList.toggle('is-scrolled', window.scrollY > 40);
window.addEventListener('scroll', onScrollNav, { passive: true });
onScrollNav();

gsap.to('#scroll-progress', {
  scaleX: 1, ease: 'none',
  scrollTrigger: { trigger: document.body, start: 'top top', end: 'bottom bottom', scrub: 0.3 },
});

/* active section highlight */
['manifesto', 'services', 'works', 'process', 'contact'].forEach((id) => {
  ScrollTrigger.create({
    trigger: `#${id}`, start: 'top 45%', end: 'bottom 45%',
    onToggle(self) {
      $$(`.nav-links a[href="#${id}"]`).forEach((a) => a.classList.toggle('is-active', self.isActive));
    },
  });
});

/* ════════════════ Mobile menu ════════════════ */
const menuBtn = $('#menu-btn');
const mobileMenu = $('#mobile-menu');
let menuOpen = false;
const menuTl = gsap.timeline({ paused: true })
  .set(mobileMenu, { visibility: 'visible' })
  .to(mobileMenu, { clipPath: 'inset(0 0 0% 0)', duration: 0.65, ease: 'power4.inOut' })
  .from('#mobile-menu nav a', { y: 44, opacity: 0, duration: 0.55, stagger: 0.07, ease: 'power3.out' }, '-=0.25');

const setMenu = (open) => {
  menuOpen = open;
  menuBtn.classList.toggle('is-open', open);
  menuBtn.setAttribute('aria-expanded', String(open));
  menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  mobileMenu.setAttribute('aria-hidden', String(!open));
  if (open) { menuTl.timeScale(1).play(); lenis && lenis.stop(); }
  else { menuTl.timeScale(1.5).reverse(); lenis && lenis.start(); }
};
menuBtn.addEventListener('click', () => setMenu(!menuOpen));

/* ════════════════ Fluid anchor transitions (page wipe) ════════════════ */
const wipe = $('#page-wipe');
let wiping = false;
$$('a.nav-link[href^="#"]').forEach((a) => {
  a.addEventListener('click', (e) => {
    const id = a.getAttribute('href');
    if (!$(id) || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    if (menuOpen) setMenu(false);
    if (reducedMotion || wiping) { scrollToTarget(id); return; }
    wiping = true;
    gsap.timeline({ onComplete: () => { wiping = false; } })
      .set(wipe, { yPercent: -101 })
      .to(wipe, { yPercent: 0, duration: 0.5, ease: 'power4.inOut' })
      .add(() => scrollToTarget(id, true))
      .to(wipe, { yPercent: 101, duration: 0.55, ease: 'power4.inOut', delay: 0.08 })
      .set(wipe, { yPercent: -101 });
    history.replaceState(null, '', id);
  });
});

/* ════════════════ Scroll-triggered 2D animation ════════════════ */
if (!reducedMotion) {
  /* generic reveals */
  $$('[data-reveal]').forEach((el) => {
    gsap.fromTo(el,
      { y: 48, opacity: 0 },
      {
        y: 0, opacity: 1, duration: 1.05, ease: 'power3.out',
        scrollTrigger: { trigger: el, start: 'top 88%', once: true },
      });
  });

  /* manifesto word-by-word illumination */
  const wordsEl = $('[data-words]');
  if (wordsEl) {
    const words = wordsEl.textContent.trim().split(/\s+/);
    wordsEl.setAttribute('aria-label', wordsEl.textContent.trim());
    wordsEl.innerHTML = words.map((w) => `<span class="word" aria-hidden="true">${w}</span>`).join(' ');
    gsap.fromTo('#manifesto .word', { opacity: 0.13 }, {
      opacity: 1, stagger: 0.06, ease: 'none',
      scrollTrigger: { trigger: wordsEl, start: 'top 78%', end: 'bottom 42%', scrub: 0.6 },
    });
  }

  /* parallax orbs */
  $$('[data-parallax]').forEach((el) => {
    gsap.to(el, {
      yPercent: parseFloat(el.dataset.parallax) || -12, ease: 'none',
      scrollTrigger: { trigger: el.parentElement, start: 'top bottom', end: 'bottom top', scrub: 0.8 },
    });
  });

  /* horizontal works gallery (desktop) */
  const mm = gsap.matchMedia();
  mm.add('(min-width: 981px)', () => {
    const track = $('#works-track');
    const getAmount = () => Math.max(0, track.scrollWidth - window.innerWidth);
    const tween = gsap.to(track, {
      x: () => -getAmount(), ease: 'none',
      scrollTrigger: {
        trigger: '#works', start: 'top top',
        end: () => `+=${getAmount()}`,
        pin: true, scrub: 0.7, anticipatePin: 1, invalidateOnRefresh: true,
      },
    });
    /* inner-image parallax inside the horizontal travel */
    $$('.work-card img').forEach((img) => {
      gsap.fromTo(img, { xPercent: -4 }, {
        xPercent: 4, ease: 'none',
        scrollTrigger: {
          trigger: img.closest('.work-card'), containerAnimation: tween,
          start: 'left right', end: 'right left', scrub: true,
        },
      });
    });
    return () => {};
  });
}

/* counters (also fine with reduced motion → set instantly) */
$$('[data-count]').forEach((el) => {
  const end = parseInt(el.dataset.count, 10) || 0;
  if (reducedMotion) { el.textContent = end; return; }
  const obj = { v: 0 };
  ScrollTrigger.create({
    trigger: el, start: 'top 92%', once: true,
    onEnter: () => gsap.to(obj, {
      v: end, duration: 1.8, ease: 'power3.out',
      onUpdate: () => { el.textContent = Math.round(obj.v); },
    }),
  });
});

/* ════════════════ Scroll-driven 3D morphing journey ════════════════ */
function initScrollJourney(sceneApi) {
  const st = sceneApi.state;
  const isSmallScreen = window.innerWidth < 981;
  const side = isSmallScreen ? 0 : 1.9;

  gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: { trigger: document.body, start: 'top top', end: 'bottom bottom', scrub: 1.1 },
  })
    /* Hero → Manifesto: drift right, calmer */
    .to(st, { posX: side, posY: -0.2, distort: 0.3, palette: 0.35, scale: 0.92, camZ: 8.8, duration: 1 })
    /* Services: slide left, golden, more liquid */
    .to(st, { posX: -side, posY: 0.25, distort: 0.62, freq: 0.7, palette: 1.05, scale: 1.0, duration: 1 })
    /* Works: centre-back, teal, energetic spikes */
    .to(st, { posX: 0, posY: 0.9, distort: 0.95, freq: 1.15, palette: 2.0, scale: 0.8, camZ: 10.5, spin: 1.7, duration: 1 })
    /* Process: right again, violet-magenta */
    .to(st, { posX: side, posY: 0, distort: 0.55, freq: 0.9, palette: 2.9, scale: 0.95, camZ: 8.6, spin: 1.1, duration: 1 })
    /* Contact: grand finale — close, huge, slow */
    .to(st, { posX: 0, posY: -0.3, distort: 0.48, palette: 3.0, scale: 1.22, camZ: 6.4, spin: 0.6, duration: 1 });
}

/* ════════════════ Magnetic elements + card tilt + cursor ════════════════ */
if (finePointer && !reducedMotion) {
  /* magnetic */
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

  /* tilt + spotlight glow on glass cards */
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

  /* custom cursor */
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
  const hoverSel = 'a, button, [data-hover], input, textarea';
  document.addEventListener('pointerover', (e) => ring.classList.toggle('is-hover', !!e.target.closest(hoverSel)));
}

/* ════════════════ Contact form (front-end demo) ════════════════ */
const form = $('#contact-form');
form.addEventListener('submit', (e) => {
  e.preventDefault();
  const status = $('#form-status');
  if (!form.checkValidity()) {
    status.textContent = 'Please complete all fields with a valid email.';
    status.style.color = '#ff9d7a';
    form.reportValidity();
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  const label = btn.querySelector('.btn-label');
  const original = label.textContent;
  btn.disabled = true;
  label.textContent = 'Transmitting…';
  setTimeout(() => {
    label.textContent = 'Message Received ✓';
    status.style.color = '';
    status.textContent = 'Thank you — your signal reached the studio. We reply within 24 hours.';
    gsap.fromTo(status, { y: 8, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out' });
    form.reset();
    setTimeout(() => { label.textContent = original; btn.disabled = false; }, 3200);
  }, 900);
});

/* keep ScrollTrigger measurements fresh after images/fonts settle */
window.addEventListener('load', () => ScrollTrigger.refresh());
