<p align="center">
  <a href="#-sadeem-45">English</a> •
  <a href="#-سـديـم-45-sadeem-45">العربية</a>
</p>

# 🚀 Sadeem 45

**An atomic Linux desktop distribution built on Fedora Silverblue 45 using the [BlueBuild](https://blue-build.org/) framework and GNOME 51.**

**Sadeem 45** is designed to be ready for daily use and productivity right from the first boot with zero post-install configuration. It combines the reliability of an unbreakable atomic system with a cohesive custom Burgundy visual identity, full support for Arabic and 9 other global languages, and graphical tools that simplify external package installation and hardware driver management.

---

## ✨ Key Features & Additions

### 1. Custom Built-in Sadeem Suite (GTK4 / Libadwaita)
All distribution utilities follow modern GNOME human interface guidelines and automatically adapt to **10 languages** (Arabic, English, French, Spanish, German, Turkish, Russian, Portuguese, Italian, and Chinese):
* **Sadeem Colors:** Customize the system accent color using 8 curated presets or pick any shade from the full color wheel, instantly syncing `GNOME Shell`, `Libadwaita (GTK4)`, and `GTK3`, with a one-click reset to signature Burgundy (`#7a1c33`).
* **Sadeem Package Installer:** Install external **`.rpm`** and **`.deb`** packages via double-click directly from the file manager. It automatically provisions isolated containers in the background, installs the package along with its dependencies, and exports its application icon to the app grid without terminal commands or system reboots.
* **Sadeem NVIDIA & CUDA Manager:** A graphical utility to easily install official NVIDIA drivers and CUDA toolkits with full Secure Boot support.
* **Welcome to Sadeem:** An interactive onboarding tour upon first login to explore system features and quickly configure essential desktop preferences.

### 2. Pre-configured App Ecosystem & Containers
* **Full Flathub Repository Enabled by Default:** With Fedora's filtered Flatpak remote disabled, plus automatic Flatpak locale synchronization (`ar;en`) handled via a dedicated systemd service.
* **Ready-to-Use Isolated Containers (`Distrobox` + `BoxBuddy`):** Silent background initialization of the default `sadeem-box` container upon first internet connection, paired with **BoxBuddy** for graphical container management.
* **Pre-installed Daily Applications:**
  * **Mister Download Manager (MDM):** High-speed download manager pre-integrated with Firefox.
  * **ZapFast:** Lightweight and fast native desktop WhatsApp client built in Rust.
  * **Rumman:** Drag-and-drop media and file converter.
  * **Media, Gaming & Customization Suite:** `VLC`, `Extension Manager`, `Refine`, `Flatseal`, `Bottles`, and `ProtonUp-Qt`.

### 3. Polished & Pre-tuned Desktop Experience
* **Tailored GNOME Desktop Out of the Box:** Top panel centered with **ArcMenu** in a clean layout, pre-tuned **Dash to Dock** bottom bar, **Clipboard Indicator** for clipboard history management, and **Adwaita 24H Lockscreen Clock & Weather**.
* **Comprehensive Typography & Localization:** Full right-to-left (RTL) layout support and bundled Arabic and office-compatible fonts (`Vazirmatn`, `Noto Sans Arabic`, `Amiri`, `Carlito`, `Caladea`, `Liberation`), with `Vazirmatn` configured as the default interface font and `Noto Sans Arabic` as the default document font.

### 4. Complete Codecs & Hardware Acceleration
* **RPM Fusion** (Free and Non-Free) repositories enabled out of the box.
* Hardware-accelerated video decoding (`intel-media-driver`, `mesa-va-drivers-freeworld`, `mesa-vdpau-drivers-freeworld`) and full multimedia codecs (`libavcodec-freeworld`, `gstreamer1-plugins-*`).
* Viewing and thumbnail generation support for `HEIF/HEIC` and `WebP` images, video thumbnails (`ffmpegthumbnailer`), and archive extraction for `RAR` and `7z`.

---

## 💿 Installation & Upgrade

### Fresh Installation (ISO Image)
Download the latest installer image (`sadeem-45.iso`) from the **[Releases](https://github.com/saifeldinosama9677-ctrl/sadeem/releases)** page and flash it to a USB drive using **Fedora Media Writer** or **Ventoy**.

### Rebase from Existing Fedora Silverblue 45
If you are already running Fedora Silverblue 45, you can switch to **Sadeem 45** while keeping all your personal files and Flatpak apps in two steps:

1. Initial rebase to the Sadeem image and reboot:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
systemctl reboot
```

2. Switch to cryptographic signature verification for verified daily updates:
```bash
rpm-ostree rebase ostree-image-signed:docker://ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
systemctl reboot
```

---

<div dir="rtl">

# 🚀 سـديـم 45 (Sadeem 45)

**توزيعة لينكس ذرية (Atomic) مبنية على Fedora Silverblue 45 باستخدام إطار عمل [BlueBuild](https://blue-build.org/) وواجهة GNOME 51.**

صُممت **سديم 45** لتكون جاهزة للاستخدام اليومي والإنتاجية فور الإقلاع الأول دون الحاجة لإعدادات ما بعد التثبيت؛ حيث تجمع بين استقرار الأنظمة الذرية غير القابلة للكسر، وهوية بصرية خمرية متكاملة، ودعم كامل للغة العربية و9 لغات عالمية أخرى، إلى جانب أدوات رسومية تبسّط تثبيت البرامج الخارجية وإدارة تعريفات العتاد.

---

## ✨ أبرز المزايا والإضافات

### 1. تطبيقات وأدوات سديم المدمجة (GTK4 / Libadwaita)
جميع أدوات التوزيعة مصممة بلغة تصميم جنوم الحديثة وتدعم **10 لغات تلقائياً** (العربية، الإنجليزية، الفرنسية، الإسبانية، الألمانية، التركية، الروسية، البرتغالية، الإيطالية، والصينية):
* **ألوان سديم (Sadeem Colors):** أداة لتخصيص اللون الأساسي للنظام عبر 8 ألوان جاهزة أو اختيار أي درجة من دائرة الألوان، مع مزامنة فورية لسمات `GNOME Shell` و `Libadwaita (GTK4)` و `GTK3` وإمكانية استعادة اللون الخمري الأصيل (`#7a1c33`) بضغطة زر.
* **مثبّت حزم سديم (Sadeem Package Installer):** يتيح تثبيت حزم **`.rpm`** و **`.deb`** الخارجية بالنقر المزدوج مباشرة من مدير الملفات؛ حيث يتولى إنشاء حاويات معزولة في الخلفية وتثبيت الحزمة مع اعتمادياتها وتصدير أيقونتها إلى قائمة التطبيقات دون الحاجة لأوامر طرفية أو إعادة تشغيل.
* **مدير تعريفات NVIDIA و CUDA:** أداة رسومية لتثبيت تعريفات NVIDIA الرسمية وحزم CUDA بسهولة مع دعم الإقلاع الآمن (Secure Boot).
* **مرحباً بك في سديم (Welcome to Sadeem):** جولة تعريفية تفاعلية عند أول تسجيل دخول لاستكشاف مزايا النظام وضبط الإعدادات الأساسية بسرعة.

### 2. بيئة التطبيقات والحاويات الجاهزة
* **متجر Flathub الكامل مفعّل افتراضياً:** مع إزالة القيود المفروضة على مستودع فيدورا الافتراضي، ومزامنة لغات التطبيقات (`ar;en`) تلقائياً عبر خدمة نظام مخصصة.
* **بيئة حاويات معزولة جاهزة (`Distrobox` + `BoxBuddy`):** تهيئة صامتة لحاوية `sadeem-box` في الخلفية عند أول اتصال بالإنترنت، مع تطبيق **BoxBuddy** لإدارة الحاويات رسومياً.
* **برامج يومية مدمجة مسبقاً:**
  * **مدير التنزيلات (Mister Download Manager - MDM):** مدير تنزيلات سريع يتكامل تلقائياً مع متصفح Firefox.
  * **زاب فاست (ZapFast):** عميل واتساب مكتبي خفيف وسريع مبني بلغة Rust.
  * **رمان (Rumman):** محول وسائط وملفات يدعم السحب والإفلات.
  * **أدوات الوسائط والألعاب والتخصيص:** `VLC`، `Extension Manager`، `Refine`، `Flatseal`، `Bottles`، و `ProtonUp-Qt`.

### 3. تجربة سطح مكتب مصقولة ومهيأة مسبقاً
* **واجهة جنوم مخصصة دون تعقيد:** شريط تطبيقات علوي يتوسطه **ArcMenu** بتخطيط نظيف، وشريط سفلي **Dash to Dock** مضبوط الشفافية والأبعاد، مع **Clipboard Indicator** لإدارة الحافظة، وساعة شاشة القفل **Adwaita 24H Lockscreen Clock & Weather**.
* **الخطوط والتعريب المتكامل:** دعم كامل للاتجاه من اليمين إلى اليسار (RTL)، وخطوط عربية ومكتبية مدمجة (`Vazirmatn`، `Noto Sans Arabic`، `Amiri`، `Carlito`، `Caladea`، `Liberation`) مع ضبط `Vazirmatn` للواجهة و`Noto Sans Arabic` للمستندات افتراضياً.

### 4. الترميز وتسريع العتاد الكامل
* مستودعات **RPM Fusion** (الحرة وغير الحرة) مفعلة مسبقاً.
* تسريع الفيديو عبر العتاد (`intel-media-driver`، `mesa-va-drivers-freeworld`، `mesa-vdpau-drivers-freeworld`) ومشغلات الوسائط الكاملة (`libavcodec-freeworld`، `gstreamer1-plugins-*`).
* دعم معاينة صور `HEIF/HEIC` و `WebP` ومصغرات الفيديو (`ffmpegthumbnailer`) وفك ضغط أرشيفات `RAR` و `7z`.

---

## 💿 التثبيت والترقية

### التثبيت الجديد (ملف ISO)
يمكنك تنزيل أحدث نسخة تثبيت مباشرة (`sadeem-45.iso`) من صفحة **[Releases](https://github.com/saifeldinosama9677-ctrl/sadeem/releases)** وحرقها على ذاكرة USB باستخدام أداة **Fedora Media Writer** أو **Ventoy**.

### التحويل من Fedora Silverblue 45 الحالي
إذا كنت تستخدم Fedora Silverblue 45 حالياً، يمكنك التحويل إلى **سديم 45** مع الحفاظ على ملفاتك وتطبيقاتك عبر الخطوتين التاليتين:

1. التحويل المبدئي إلى صورة سديم وإعادة التشغيل:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
systemctl reboot
```

2. تفعيل التحقق بالتوقيع الرقمي المشفّر للتحديثات المستقبلية:
```bash
rpm-ostree rebase ostree-image-signed:docker://ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
systemctl reboot
```

</div>

---
