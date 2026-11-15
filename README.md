# Sadeem 45 (سديم) 🚀

توزيعة مخصصة مبنية على **Fedora Atomic (Silverblue 45)** باستخدام إطار عمل **[BlueBuild](https://blue-build.org/)**.

مستودع المشروع: [https://github.com/saifeldinosama9677-ctrl/sadeem](https://github.com/saifeldinosama9677-ctrl/sadeem)

تتضمن هذه النسخة حزم وبرامج إضافية مدمجة مسبقاً لتوفير تجربة متكاملة وجاهزة للاستخدام اليومي والإنتاجية، مع دعم ممتاز للغة العربية واللغات المتعددة، وتسريع كامل للوسائط المتعددة والعتاد، وتطبيقات إنتاجية وتخصيص أصيلة مدمجة.

---

## ✨ المميزات الرئيسية

- **الترميز وتسريع العتاد:**
  - مستودعات **RPM Fusion** (الحرة وغير الحرة) مفعلة مسبقاً.
  - تعريفات تسريع العتاد للبطاقات الرسومية: `mesa-va-drivers-freeworld`، `mesa-vdpau-drivers-freeworld`، `intel-media-driver`.
  - مشغلات وتراميز الوسائط: `libavcodec-freeworld`، `gstreamer1-plugins-*`، `gstreamer1-plugin-libav`.
  - أداة متخصصة لإدارة وتثبيت تعريفات NVIDIA الرسمية و CUDA مع دعم الإقلاع الآمن.
- **دعم صيغ الصور والمصغرات:**
  - `libheif-freeworld`، `heif-pixbuf-loader`، `webp-pixbuf-loader`، `ffmpegthumbnailer`.
- **الضغط والأرشفة:**
  - `unrar`، `p7zip`، `p7zip-plugins`.
- **الخطوط والتعريب المتكامل:**
  - دعم 10 لغات عالمية مع دعم كامل للاتجاه من اليمين إلى اليسار (RTL).
  - حزم اللغات: `langpacks-ar`، `glibc-langpack-ar`.
  - خطوط عربية ومكتبية مدمجة: `google-noto-sans-arabic-fonts`، `vazirmatn-fonts`، `amiri-fonts`، `google-carlito-fonts`، `google-caladea-fonts`، `liberation-fonts`.
  - إعدادات `dconf` افتراضية: خط الواجهة `Vazirmatn 11`، وخط المستندات `Noto Sans Arabic 11`.
- **إدارة الحزم وتطبيقات Flatpak:**
  - مستودع **Flathub** الكامل مفعل افتراضياً للنظام.
  - تعطيل مستودع Fedora Flatpak المحدود تلقائياً.
  - ضبط لغات Flatpak على `"ar;en"` عند الإقلاع عبر خدمة systemd مخصصة.
  - تطبيقات مثبتة مسبقاً: **Extension Manager**, **Refine**, **Flatseal**, **VLC**.
- **تطبيقات مدمجة خاصة بنظام سديم:**
  - **ألوان سديم (Sadeem Colors):** تطبيق GTK4/Libadwaita لتخصيص اللون الأساسي للنظام والواجهة بدائرة ألوان كاملة وألوان جاهزة مع إمكانية استعادة اللون الخمري الأصيل.
  - **مرحباً بك في سديم (Sadeem Welcome):** جولة تعريفية تفاعلية بـ 5 شرائح تدعم 10 لغات مع كشف بطاقات NVIDIA وإمكانية تشغيل البرامج الأساسية مباشرة.
  - **رمان (Rumman):** محول ملفات سريع ومدمج بنظام السحب والإفلات.
  - **مدير التنزيلات (MDM - Mister Download Manager):** مدير تنزيلات فائق السرعة متكامل تلقائياً مع متصفح فايرفوكس.
  - **زاب فاست (ZapFast):** عميل واتساب مكتبي سريع مبني بلغة Rust.
- **واجهة جنوم وإضافات سطح المكتب:**
  - إضافات مفعلة ومهيأة مسبقاً: قائمة التطبيقات **ArcMenu**، شريط المهام **Dash to Dock**، سجل الحافظة **Clipboard Indicator**، وساعة شاشة القفل.
  - ثيم خمري أصيل للنظام وقائمة جنوم متناسق مع تطبيقات GTK4 و Libadwaita و GTK3.

---

## 🛠️ التثبيت والتبديل (Rebase)

### التبديل إلى الصورة السحابية عبر rpm-ostree:

للانتقال من أي نظام Fedora Silverblue حالي إلى صورة سديم (Sadeem):

```bash
sudo rpm-ostree rebase ostree-image-signed:docker://ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
```

أو لتثبيت إصدار محدد (مثل إصدار 45):

```bash
sudo rpm-ostree rebase ostree-image-signed:docker://ghcr.io/saifeldinosama9677-ctrl/sadeem:45
```

### تثبيت النظام عبر ملف ISO:

يمكن تشغيل سير عمل بناء ملف الـ ISO يدوياً عبر تبويب **Actions** في مستودع GitHub (`build-iso`)، أو تنزيل ملف الـ ISO المتولد مع كل إصدار رسمي (Release)، وحرقه على ذاكرة فلاشية باستخدام **Fedora Media Writer** أو **Etcher**.

---

## 🔐 التوقيع الرقمي (Image Signing)

يتم توقيع الصورة الناتجة تلقائياً بواسطة أداة **Sigstore/Cosign**. يمكن التحقق من سلامة الصورة باستخدام المفتاح العام المتوفر في جذر المستودع `cosign.pub`:

```bash
cosign verify --key cosign.pub ghcr.io/saifeldinosama9677-ctrl/sadeem:latest
```
