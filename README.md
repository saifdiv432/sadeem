<div dir="rtl">

# 🚀 Sadeem 45 (سديم 45)

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
* **بيئة حاويات معزولة جاهزة (Distrobox + BoxBuddy):** تهيئة صامتة لحاوية `sadeem-box` في الخلفية عند أول اتصال بالإنترنت، مع تطبيق **BoxBuddy** لإدارة الحاويات رسومياً.
* **برامج يومية مدمجة مسبقاً:**
  * **Mister Download Manager (MDM):** مدير تنزيلات سريع متكامل تلقائياً مع متصفح Firefox.
  * **ZapFast:** عميل واتساب مكتبي خفيف وسريع مبني بلغة Rust.
  * **Rumman (رمان):** محول وسائط وملفات يدعم السحب والإفلات.
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

## 🌐 English Overview

**Sadeem 45** is an atomic Linux desktop distribution built on **Fedora Silverblue 45** (GNOME 51) using **BlueBuild**, designed to deliver an out-of-the-box workstation experience with zero post-install setup.

### Key Highlights
* **Custom GTK4/Libadwaita Suite (10 Languages Supported):**
  * **Sadeem Colors:** Instant system-wide accent color customizer (presets + full color wheel) syncing GNOME Shell, Libadwaita, and GTK3, with one-click reset to signature Burgundy (`#7a1c33`).
  * **Sadeem Package Installer:** Double-click GUI installer for external **`.rpm`** and **`.deb`** files—automatically provisioning isolated `Distrobox` containers and exporting desktop icons to the app grid without terminal commands.
  * **Sadeem NVIDIA & CUDA Manager:** GUI utility for installing official NVIDIA drivers and CUDA with Secure Boot support.
  * **Welcome to Sadeem:** Multilingual interactive onboarding tour.
* **Pre-configured Desktop & Apps:** Full Flathub integration, silent `Distrobox` background setup + `BoxBuddy`, `Firefox`, `Mister Download Manager (MDM)`, `ZapFast`, `Rumman`, `VLC`, `Extension Manager`, `Refine`, `Flatseal`, `Bottles`, and `ProtonUp-Qt`, alongside pre-tuned `ArcMenu` and `Dash to Dock`.
* **Complete Codecs & Multilingual Typography:** Pre-enabled RPM Fusion, VA-API/VDPAU hardware acceleration, HEIF/WebP thumbnails, archive utilities, and crisp Arabic/Latin font rendering (`Vazirmatn`, `Noto Sans Arabic`, `Amiri`, `Carlito`).

### Rebase from Existing Fedora Silverblue 45
```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifeldinosama9677-ctrl/sadeem:latest && systemctl reboot
```
After rebooting, switch to the signed image for verified daily updates:
```bash
rpm-ostree rebase ostree-image-signed:docker://ghcr.io/saifeldinosama9677-ctrl/sadeem:latest && systemctl reboot
```
