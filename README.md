<p align="center">
  <a href="#-sadeem-45">English</a> •
  <a href="#-سـديـم-45-sadeem-45">العربية</a>
</p>

# 🚀 Sadeem 45

**An atomic Linux desktop distribution built on Fedora Silverblue 45 using the [BlueBuild](https://blue-build.org/) framework and GNOME 51.**

**Sadeem 45** is designed to be ready for daily use and productivity right from the first boot with zero post-install configuration. It combines the reliability of an unbreakable atomic system with a cohesive custom Burgundy visual identity, full support for Arabic and 9 other global languages, and graphical tools that simplify external package installation and hardware driver management.

---

## 📥 تنزيل التوزيعة وتثبيتها (Download & Install)

يمكنك تنزيل ملف التثبيت المكتمل بنقرة واحدة مباشرة (`sadeem-45.iso`)، أو التحويل المباشر لمستخدمي فيدورا الذرية عبر طرفية النظام:

### 🚀 روابط التنزيل المباشر (Direct Download):
* **[تنزيل مباشر لملف sadeem-45.iso الكامل بنقرة واحدة (Hugging Face)](https://huggingface.co/datasets/saifeldinosama9677-ctrl/sadeem-iso/resolve/main/sadeem-45.iso)**
* **صفحة الإصدارات الرسمية:** **[GitHub Releases](https://github.com/saifeldinosama9677-ctrl/sadeem/releases)**

---

### ⚙️ متطلبات التثبيت على القرص (System Requirements):
* **المساحة التخزينية:** مساحة حرة لا تقل عن **40 جيجابايت** على القرص (SSD موصى به) لتثبيت النظام وتشغيل الحاويات والتطبيقات بسلاسة.
* **الذاكرة العشوائية (RAM):** 4 جيجابايت كحد أدنى (8 جيجابايت موصى بها لتشغيل الحاويات والألعاب).
* **ذاكرة فلاشية (USB):** بسعة 8 جيجابايت أو أكثر.

---

### 💾 حرق ملف الـ ISO على ذاكرة فلاشية (Flashing to USB):
احرق ملف `sadeem-45.iso` الكامل مباشرة على ذاكرة فلاشية باستخدام أحد البرامج التالية:
1. **Fedora Media Writer** (موصى به لجميع المنصات - Linux, Windows, macOS).
2. **BalenaEtcher** (متوفر لجميع الأنظمة).
3. **Rufus** (على Windows: تأكد من اختيار **وضع كتابة صورة DD** أو **DD Image mode** عند ظهور رسالة التأكيد بعد الضغط على Start).
4. **Ventoy** (يمكنك نسخ ملف `sadeem-45.iso` مباشرة إلى فلاشة Ventoy).

---

### 🔄 التحويل المباشر لمستخدمي فيدورا الذرية (Direct Rebase for Fedora Atomic):
إذا كنت تستخدم حالياً نظام **Fedora Silverblue 45** (أو أي توزيعة ذرية مبنية عليه)، يمكنك التحويل مباشرة إلى **سديم 45** مع الاحتفاظ الكامل ببياناتك وملفاتك الشخصية وتطبيقاتك عبر تنفيذ أمر واحد في الطرفية:

```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
systemctl reboot
```

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
Download the complete single installer image (`sadeem-45.iso`) directly with one click:
- **Direct Download (Hugging Face):** [sadeem-45.iso](https://huggingface.co/datasets/saifeldinosama9677-ctrl/sadeem-iso/resolve/main/sadeem-45.iso)
- **Official Releases:** **[GitHub Releases](https://github.com/saifeldinosama9677-ctrl/sadeem/releases)**
- Flash `sadeem-45.iso` directly to a USB drive (8 GB minimum) using **Fedora Media Writer**, **BalenaEtcher**, or **Rufus** (in DD Image mode).
- Recommended storage space: at least **40 GB** free disk space.

### Rebase from Existing Fedora Silverblue 45
If you are already running Fedora Silverblue 45 or any Fedora Atomic system, you can switch to **Sadeem 45** while keeping all your personal files and Flatpak apps:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
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
يمكنك تنزيل ملف التثبيت المكتمل بنقرة واحدة (`sadeem-45.iso`) دون الحاجة لأي دمج أو تجزئة:
- **رابط التنزيل المباشر (Hugging Face):** [sadeem-45.iso](https://huggingface.co/datasets/saifeldinosama9677-ctrl/sadeem-iso/resolve/main/sadeem-45.iso)
- **صفحة الإصدارات:** **[GitHub Releases](https://github.com/saifeldinosama9677-ctrl/sadeem/releases)**
- احرق `sadeem-45.iso` مباشرة على ذاكرة USB (8 جيجابايت كحد أدنى) باستخدام **Fedora Media Writer** أو **BalenaEtcher** أو **Rufus** (بوضع DD Image mode).
- متطلبات التخزين: مساحة حرة لا تقل عن **40 جيجابايت** على القرص.

### التحويل من Fedora Silverblue 45 الحالي
إذا كنت تستخدم Fedora Silverblue 45 حالياً (أو أي توزيعة ذرية مبنية عليه)، يمكنك التحويل إلى **سديم 45** مع الحفاظ على ملفاتك وتطبيقاتك عبر أمر واحد في الطرفية:
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
systemctl reboot
```

</div>

---
