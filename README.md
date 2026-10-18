# ✦ AETHER® — وب‌سایت لوکس و آینده‌نگر با WebGL

یک وب‌سایت **فوق‌لوکس و سینمایی** در سطح Awwwards: صحنه سه‌بعدی زنده با **Three.js** و شیدر اختصاصی GLSL، انیمیشن‌های **GSAP + ScrollTrigger**، اسکرول نرم **Lenis**، کرسر سفارشی و دکمه‌های مغناطیسی، گالری افقی اسکرولی، افکت شیشه‌ای (Glassmorphism) و مورفینگ کامل صحنه 3D با اسکرول — با خروجی استاتیک سبک (~۱.۲ مگابایت) و آماده نصب روی **سرور لینوکس**.

---

## 🚀 نصب روی سرور لینوکس — سه روش

### روش ۱: نصب خودکار با یک دستور (پیشنهادی) — Ubuntu/Debian/Rocky

اسکریپت `install.sh` همه‌چیز را خودش انجام می‌دهد: نصب Node.js 22 (اگر نباشد)، بیلد پروژه، نصب و کانفیگ Nginx (کش، Gzip، هدرهای امنیتی)، باز کردن فایروال و (اختیاری) گرفتن SSL رایگان.

```bash
git clone https://github.com/HOTKYNTAKY/1387eiman.git
cd 1387eiman

# ساده‌ترین حالت — روی IP سرور، پورت 80:
sudo bash install.sh

# با دامنه اختصاصی:
sudo bash install.sh --domain example.com

# با دامنه + HTTPS رایگان (Let's Encrypt):
sudo bash install.sh --domain example.com --ssl you@mail.com
```

آپدیت‌های بعدی فقط با یک دستور:

```bash
sudo bash update.sh        # git pull + build + deploy + reload nginx
```

### روش ۲: Docker (سریع‌ترین روش — روی هر لینوکسی)

```bash
git clone https://github.com/HOTKYNTAKY/1387eiman.git
cd 1387eiman

docker compose up -d --build
# سایت روی http://SERVER-IP:8080 بالا می‌آید
# پورت را در فایل .env عوض کنید (cp .env.example .env)
```

یا بدون Compose:

```bash
docker build -t aether .
docker run -d --restart unless-stopped -p 8080:80 --name aether aether
```

### روش ۳: دستی (Nginx / Apache / هاست اشتراکی)

خروجی پروژه کاملاً استاتیک است؛ کافی است فولدر `dist` را روی سرور بگذارید:

```bash
npm ci && npm run build     # ساخت فولدر dist
# محتویات dist را در روت وب‌سرور کپی کنید، مثلاً /var/www/html
```

کانفیگ آماده Nginx در `deploy/nginx-site.conf` هست (با کش immutable برای assetها، Gzip و SPA fallback).
گزینه جایگزین systemd هم در `deploy/aether.service` موجود است.

---

## 🛠 اجرای لوکال (توسعه)

```bash
npm install
npm run dev        # http://localhost:5173  (هات‌ریلود)
npm run build      # بیلد production در dist/
npm run preview    # پیش‌نمایش بیلد نهایی
```

نیازمندی: Node.js نسخه ۱۸ به بالا.

---

## ✨ قابلیت‌ها

| بخش | توضیح |
|---|---|
| 🎬 صحنه WebGL | هسته مورفینگ با شیدر نویز Simplex اختصاصی، دو حلقه مداری فلزی با نورپردازی دینامیک (نور دنبال‌کننده موس)، ~۳۰۰۰ ذره ستاره‌ای |
| 🖱 تعامل با کرسر | پارالاکس دوربین، کرسر سفارشی دو‌لایه، دکمه‌های مغناطیسی با برگشت الاستیک، تیلت سه‌بعدی کارت‌ها با نور نقطه‌ای |
| 📜 اسکرول سینمایی | اسکرول نرم Lenis، تغییر رنگ/فرم/موقعیت صحنه 3D در طول صفحه، روشن‌شدن کلمه‌به‌کلمه مانیفست، گالری افقی پین‌شده، شمارنده آمار |
| 🎞 ترنزیشن صفحه | وایپ سینمایی هنگام ناوبری + پری‌لودر با شمارنده درصد |
| ⚡ پرفورمنس | لود تنبل Three.js، کداسپلیتینگ، کیفیت تطبیقی WebGL (کاهش خودکار DPR در FPS پایین)، توقف رندر در تب مخفی |
| ♿ دسترس‌پذیری | احترام به `prefers-reduced-motion` (جایگزین CSS به‌جای WebGL)، فوکوس واضح، Skip-Link، HTML معنایی و ARIA |
| 📱 ریسپانسیو | منوی موبایل تمام‌صفحه، گالری سوایپی در موبایل، بودجه ذرات کمتر در گوشی |

## 📁 ساختار پروژه

```
├── index.html              # اسکلت صفحه و سئو
├── src/
│   ├── main.js             # GSAP، Lenis، کرسر، منو، فرم…
│   ├── style.css           # سیستم طراحی لوکس
│   └── three/scene.js      # صحنه WebGL و شیدرها
├── public/images/          # تصاویر نمونه‌کارها
├── deploy/
│   ├── nginx-site.conf     # کانفیگ Nginx برای نصب مستقیم
│   ├── nginx-docker.conf   # کانفیگ Nginx داخل ایمیج داکر
│   └── aether.service      # یونیت systemd (جایگزین)
├── Dockerfile              # بیلد چندمرحله‌ای (Node → Nginx Alpine)
├── docker-compose.yml
├── install.sh              # ★ نصب خودکار روی لینوکس
├── update.sh               # آپدیت یک‌دستوره
└── Makefile                # میانبرها: make install / docker-up / build
```

---

## English — Quick Start

**AETHER®** is an ultra-premium, Awwwards-grade futuristic website: a living Three.js/WebGL scene (custom GLSL morphing core, dynamic lights, particles), GSAP scroll choreography, Lenis smooth scrolling, magnetic UI, glassmorphism and a pinned horizontal gallery — shipped as a fast static build, installable on any Linux server.

```bash
# 1) One-click bare-metal install (Ubuntu/Debian/RHEL) — Node + build + Nginx (+optional SSL)
sudo bash install.sh --domain example.com --ssl you@mail.com

# 2) Or Docker
docker compose up -d --build        # → http://SERVER-IP:8080

# 3) Or local development
npm install && npm run dev          # → http://localhost:5173
```

Updates: `sudo bash update.sh` · Make shortcuts: `make help`

---

© 2026 AETHER Studio — Crafted beyond gravity.
