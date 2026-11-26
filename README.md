<p align="center">
  <img src="files/system/usr/share/icons/hicolor/scalable/apps/sadeem-logo.svg" width="96" height="96" alt="Sadeem 45 Logo" />
</p>

<p align="center">
  <a href="https://github.com/saifdiv432/sadeem/actions/workflows/build.yml"><img src="https://github.com/saifdiv432/sadeem/actions/workflows/build.yml/badge.svg" alt="BlueBuild Image Build" /></a>
  <a href="https://github.com/saifdiv432/sadeem/actions/workflows/sync-external-apps.yml"><img src="https://github.com/saifdiv432/sadeem/actions/workflows/sync-external-apps.yml/badge.svg" alt="Sync External Apps" /></a>
</p>

<p align="center">
  <a href="#sadeem-45"><strong>English</strong></a> •
  <a href="#سديم-45-sadeem-45"><strong>العربية</strong></a>
</p>

---

# Sadeem 45

<p>
  <a href="#download-install--rebase">Download & Install</a> •
  <a href="#the-sadeem-suite-gtk4--libadwaita">Sadeem Suite</a> •
  <a href="#tailored-desktop--extensions">Desktop Experience</a> •
  <a href="#app-ecosystem-containers--automated-ci">Ecosystem & CI</a> •
  <a href="#codecs--hardware-acceleration">Hardware & Codecs</a>
</p>

**An atomic Linux desktop distribution built on Fedora Silverblue 45 using the [BlueBuild](https://blue-build.org/) framework and GNOME 51.**

**Sadeem 45** is engineered to be ready for daily work, creativity, and gaming out of the box with zero manual setup. It pairs the reliability of an immutable ostree base with a custom **Burgundy** visual identity (`#7a1c33`), native **RTL/LTR** ergonomics, **10-language** custom GTK4/Libadwaita applications (`12` system langpacks), hardware-accelerated screen capture and video editing, offline local AI tooling, and graphical driver and container management.

---

## Download, Install & Rebase

Download the single complete installation ISO (`sadeem-45.iso`) or switch directly from any Fedora Atomic desktop:

- **Direct ISO Download (Hugging Face):** **[Download sadeem-45.iso](https://huggingface.co/datasets/saifeldin432/sadeem-iso/resolve/main/sadeem-45.iso)**
- **Official Releases:** **[GitHub Releases (Latest)](https://github.com/saifdiv432/sadeem/releases/latest)**

### System Requirements
- **Storage:** At least **40 GB** free space (SSD strongly recommended) for atomic deployments and container storage.
- **Memory (RAM):** 4 GB minimum (8 GB+ recommended for containers, gaming, and local AI models).
- **USB Drive:** 8 GB or larger for installation media.

### Flashing to USB
Write `sadeem-45.iso` to a USB drive using one of the following tools:
1. **Fedora Media Writer** (Recommended on Linux, Windows, and macOS).
2. **BalenaEtcher** (Cross-platform).
3. **Rufus** (On Windows: choose **DD Image mode** when prompted after clicking Start).
4. **Ventoy** (Copy `sadeem-45.iso` directly onto your Ventoy partition).

### Direct Rebase for Existing Fedora Atomic Users
If you already run **Fedora Silverblue 45** (or another Fedora Atomic variant), switch to **Sadeem 45** while preserving your personal data and Flatpaks:

```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifdiv432/sadeem:latest
systemctl reboot
```

---

## The Sadeem Suite (GTK4 / Libadwaita)

Sadeem's native applications are built with **GTK 4** and **Libadwaita**, following GNOME 51 HIG standards and automatically translating across **10 languages** (`ar`, `en`, `fr`, `es`, `de`, `tr`, `ru`, `pt`, `it`, `zh`):

### Core Applications
* **Sadeem System (`sadeem-system`):** Unified 5-page system control center (`Adw.NavigationSplitView`):
  * **Updates:** Graphical on-demand checker & updater for `rpm-ostree` system images, Flathub apps, and `sadeem-box` container packages, displaying download counts/sizes before applying, morphing into **Install & Restart** when staged, and triggering cleanup afterward.
  * **Colors & Theme:** Live accent color switcher with presets and a full color wheel syncing `GNOME Shell`, `Libadwaita (GTK4)`, and `GTK3`, plus one-click reset to signature Burgundy (`#7a1c33`).
  * **Sadeem Menu:** Live configuration for `sadeem-menu@sadeem.os` via `org.sadeem.menu` (`Super` key binding, live background opacity `10%–100%`, tile icon size, All Apps sidebar, footer power buttons, separate **Most Used** and **Recently Installed** limits `1–4`, per-group automatic smart-group toggles for `Sadeem Apps / Office / Games / Social`, and independent Appearance / Layout resets).
  * **Drivers & Hardware:** Full hardware scanner (`pciutils`, `usbutils`, kernel modules, `fwupd` firmware updates, and `mokutil` Secure Boot MOK enrollment) supporting **NVIDIA** proprietary drivers & **CUDA** (`akmod`), **Intel** hardware video acceleration (`intel-media-driver`), **AMD** Freeworld codecs, **Broadcom Wi-Fi** (`akmod-wl`), **Intel IPU6/MIPI** webcams, **Sound Open Firmware (SOF)**, **fprintd** fingerprint readers, and automatic repository modalias matching.
  * **Containers & Packages:** Quick management of the `sadeem-box` container, **BoxBuddy**, and runtime cache cleanup.
* **Sadeem Gallery (`sadeem-gallery`):** Chronological photo and video gallery with fast image & **RAW / HEIF / WebP / animated GIF** viewing, EXIF inspection, wallpaper setter, integrated `Gtk.Video` playback, and a clean 5-section vertical-rail photo editor (**Crop, Rotate, Draw** with PangoCairo Arabic/English text & blur, **Light**, **Filters**).
* **Sadeem Video Editor (`sadeem-video-editor`):** Fast, single-page FFmpeg-backed editor (`org.sadeem.VideoEditor`) with multi-window support, timeline splitting, lossless stream-copy trimming for single segments, per-segment playback speed (`0.5x–4.0x`), aspect-ratio presets (`Free, 16:9, 9:16, 1:1, 4:3`), timed Cairo vector annotations (freehand, arrow, rectangle, ellipse, text), temporal blur regions (`Pixelate`, `Frosted Glass`, `Solid Fill`), external audio mixing/replacement with fade-in/out and mute ranges, plus video and animated `GIF` export.
* **Sadeem AI Manager (`sadeem-ai-manager`):** Local offline AI model hub powered by `llama.cpp` (`llama-server` auto-installed in CUDA or CPU builds). Profiles RAM, CPU, and GPU/VRAM (`nvidia-smi` / DRM) to score compatibility across a curated 7-model catalog (`gemma-4-e2b`, `gemma-4-e4b`, `qwen-3.5-2b`, `qwen-3.5-9b`, `qwen-3-14b`, `phi-4-mini`, `deepseek-r1-14b`), downloads Hugging Face `GGUF` / `mmproj` weights with live speed & cancel controls, and provides built-in offline streaming chat.
* **Rumman (`rumman`):** *"Drag. Drop. Done."* Hold `Shift` while dragging any file in Files (via `rumman-helper@rumman.app` on GNOME Wayland) or launch directly to open a radial format wheel under the cursor with format-aware compression, scaling, rotation, audio normalization/silence trim, and archive options.
* **Welcome to Sadeem (`sadeem-welcome`):** Interactive 10-language onboarding tour highlighting desktop customization, bundled tools, and quick app launching.

### Built-in System Handlers & Background Services
* **Sadeem Package Installer (`sadeem-pkg-installer`):** Double-click external **`.rpm`** and **`.deb`** packages in Files to provision isolated `Distrobox` sandboxes automatically, resolve dependencies, export icons to the app menu, and clean temporary caches (`dnf` / `apt-get`).
* **Windows App Runner (`sadeem-windows-exe-handler`):** Double-click **`.exe`** and **`.msi`** files to set up the `Sadeem-Windows` container in **Bottles** automatically and sync installed Windows app shortcuts and extracted PE/ICO icons cleanly into the GNOME app menu (`shortcut_sync.py`).
* **Sadeem Uninstaller (`sadeem-uninstaller`):** Unified uninstaller handling **Flatpak** apps, **Distrobox / user desktop / AppImage** apps, and layered `rpm-ostree` packages (while protecting core system components).
* **Automatic Housekeeping (`sadeem-housekeeping`):** Silent systemd user timer and post-update hook pruning unused Flatpak runtimes (`flatpak uninstall --unused`) and `sadeem-box` caches, paired with `sadeem-updater-check.timer`.

---

## Tailored Desktop & Extensions

Sadeem 45 runs **GNOME 51** configured out of the box with custom Sadeem extensions and cohesive extensions tuned for both RTL and LTR workflows:

* **Sadeem Menu (`sadeem-menu@sadeem.os`):** Custom-built GNOME 51 launcher featuring a unified 2D free-placement tile board, inline collapsible foldable groups resizeable cleanly (`2×2`–`4×4`), full 2D drag-and-drop & edge-handle menu resizing, live `10%–100%` background opacity, individually toggleable automatic smart groups (**Sadeem Apps**, **Office**, **Games**, **Social**), instant search, optional `Super`-key binding, collapsible All Apps sidebar with jump grid, footer power actions, and per-app **Uninstall** right-click integration.
* **Sadeem Capture (`sadeem-capture` & `captureUI.js` / `recorder.py`):** Instant screen-freeze capture overlay (`Print` key) for **Selection, Screen, and Window** modes:
  * **Photo:** Zero-latency capture directly from the frozen Wayland compositor frame (`Shell.Screenshot.composite_to_stream`) with cursor/halo toggles, collision-safe filenames, clipboard copy, and notification actions to open/edit immediately in **Sadeem Gallery**.
  * **Video:** Hardware-accelerated PipeWire/Portal recording (`VA-API` zero-copy DMA-BUF on screen mode / `vapostproc` + `NVENC` / software `x264`/`x265` fallback) supporting `H.264` & `H.265`, `Native / 1080p / 720p`, `30 / 60 FPS`, synchronized `System Audio / Microphone / Both` stereo mixing (`48 kHz` AAC), silent `Print` screenshots during active recordings, `Shift+Print` stop shortcut, and direct notification handoff to **Sadeem Video Editor**.
* **Sadeem Desktop Helper (`sadeem-desktop-helper@sadeem.os`):** Automatically flips **Dash to Panel** layout orientation between `RTL` and `LTR`, opens **Clipboard Indicator** (`Super+V`) and **Emoji Copy** (`Super+.`) directly at the mouse cursor, injects localized **Take Screenshot** actions into GNOME window menus, and adds localized **Uninstall** actions to GNOME app context menus.
* **Adwaita 24H Lockscreen Clock & Weather (`adwaita-lock-clock@saifeldin.osama`):** Custom Libadwaita lock-screen interface with a **sticky real-time preview** (`15` UI languages) and extensive customization:
  * **Hybrid 24H / 12H Clock & Positioning:** Sculpted analog-digital hands with orbiting digits, circular halo clipping, toggleable seconds hand (power-saving mode), adjustable UI scale (`75%–135%`), card opacity (`0%–100%`), and vertical screen position (`30%–70%`).
  * **Weather & Metrics Card (`Open-Meteo`):** Live temperature with high/low and yesterday comparison, **3-day forecast**, 4 toggleable metrics (**Humidity, Wind Speed, Feels Like, UV Index**), auto/manual regional units (`°C/°F`, `km/h / m/s / mph`), and auto geolocation or searchable city/country/timezone picker.
  * **Calendars, Numerals & Accent Sync:** Gregorian + local secondary calendars (**Hijri Umm al-Qura**, Persian, Chinese, Japanese, Buddhist, Indian, Ethiopic, or **ISO Week**), single weekday or **7-day strip** with configurable week start (`Auto / Sat / Sun / Mon`), **22 numeral systems**, and automatic **system accent color** & theme (`System / Dark / Light`) synchronization.
* **Pre-enabled Companion Extensions:**
  * `dash-to-panel@jderose9.github.com` (unified bottom panel & taskbar)
  * `clipboard-indicator@tudmotu.com` (`Super+V` clipboard history at cursor)
  * `emoji-copy@felipeftn` (`Super+.` emoji picker at cursor)
  * `rumman-helper@rumman.app` (GNOME Wayland `Shift`+drag bridge for Rumman)
  * `user-theme@gnome-shell-extensions.gcampax.github.com` & `light-style@gnome-shell-extensions.gcampax.github.com`
* **Typography & Localization:** Bundled Arabic and global fonts (`Vazirmatn` as default UI font, `Noto Sans Arabic` as default document font, `Amiri`, `Carlito`, `Caladea`, `Liberation`, `Noto Nastaliq Urdu`, `Noto Sans Devanagari`, `Noto Sans CJK`) plus **12 Fedora language packs** (`en, ar, ru, es, tr, fr, it, hi, zh_CN, ur, ms, id`).

---

## App Ecosystem, Containers & Automated CI

* **Unfiltered Flathub Enabled by Default:** Fedora's filtered Flatpak remotes are removed at build time, full **Flathub** (`dl.flathub.org`) is configured system-wide, and `flatpak-configure-languages.service` keeps installed Flatpak locales synchronized.
* **Pre-installed Flathub Apps (`recipe.yml`):** `Firefox`, `GNOME Text Editor`, `LibreOffice`, `VLC`, `Extension Manager`, `Refine`, `Flatseal`, `Bottles`, `ProtonUp-Qt`, `BoxBuddy`, and `Gear Lever` (AppImage integration).
* **Ready-to-Use Isolated Containers (`Distrobox` + `BoxBuddy`):** Background initialization of the `sadeem-box` container (`sadeem-init-sandbox.service`) for external software and CLI workflows without modifying the immutable base image.
* **Bundled Daily External Apps (Auto-Synced):**
  * **ZapFast (`crmne/zapfast`):** Fast native Rust desktop WhatsApp client (`v0.21.3`).
  * **Mister Download Manager (`anefzaoui/misterdownloadmanager`):** High-speed multi-connection download and torrent manager (`v0.5.2`) pre-integrated with both Firefox and Chromium native-messaging hosts.
* **GitHub Actions CI & Daily App Sync:**
  * [`.github/workflows/build.yml`](.github/workflows/build.yml) builds and signs fresh OCI images automatically via BlueBuild twice weekly (`06:00 UTC` Mondays & Thursdays) and on repository pushes.
  * [`.github/workflows/sync-external-apps.yml`](.github/workflows/sync-external-apps.yml) checks upstream GitHub releases for **ZapFast** and **Mister Download Manager** daily at `03:00 UTC`, validates downloaded archives, updates bundled companion extensions/assets cleanly, commits version updates, and dispatches a fresh image build automatically.

---

## Codecs & Hardware Acceleration

* **RPM Fusion (Free & Nonfree)** repositories enabled out of the box.
* Hardware-accelerated video pipelines and full multimedia codecs (`intel-media-driver`, `mesa-va-drivers-freeworld`, `libavcodec-freeworld`, `gstreamer1-plugins-bad-freeworld`, `gstreamer1-plugins-ugly`, `gstreamer1-plugin-libav`, `pipewire-gstreamer`).
* Out-of-the-box image/thumbnail loaders and archive support: `HEIF/HEIC` (`libheif-freeworld`, `heif-pixbuf-loader`), `WebP` (`webp-pixbuf-loader`), `ffmpegthumbnailer`, `unrar`, and `p7zip` / `p7zip-plugins`.

---

<div dir="rtl">

# سديم 45 (Sadeem 45)

<p>
  <a href="#التنزيل-والتثبيت-والتحويل-المباشر">التنزيل والتثبيت</a> •
  <a href="#حزمة-تطبيقات-سديم-gtk4--libadwaita">تطبيقات سديم</a> •
  <a href="#تجربة-سطح-المكتب-والإضافات">سطح المكتب والإضافات</a> •
  <a href="#بيئة-التطبيقات-والحاويات-والتحديث-الآلي-ci">الحاويات والتحديث الآلي</a> •
  <a href="#الترميز-وتسريع-العتاد-الكامل">الترميز والعتاد</a>
</p>

**توزيعة لينكس ذرية (Atomic) مبنية على Fedora Silverblue 45 باستخدام إطار عمل [BlueBuild](https://blue-build.org/) وبيئة GNOME 51.**

صُمّمت **سديم 45** لتكون جاهزة تماماً للعمل والإبداع والألعاب منذ الإقلاع الأول دون إعدادات ما بعد التثبيت؛ فهي تجمع بين متانة النظام الذري غير القابل للكسر، وهوية **سديم الخمرية** (`#7a1c33`) المصمّمة لاتجاهَي `RTL/LTR`، وتطبيقات **GTK4 / Libadwaita** أصلية مترجمة تلقائياً إلى **10 لغات** (مع 12 حزمة لغة على مستوى النظام)، وأدوات متكاملة لالتقاط الشاشة ومونتاج الفيديو والذكاء الاصطناعي المحلي وإدارة التعريفات والحاويات.

---

## التنزيل والتثبيت والتحويل المباشر

يمكنك تنزيل ملف التثبيت المكتمل بنقرة واحدة (`sadeem-45.iso`) أو التحويل الفوري من أي توزيعة Fedora Atomic:

- **تنزيل مباشر لملف `sadeem-45.iso` (Hugging Face):** **[اضغط هنا للتنزيل](https://huggingface.co/datasets/saifeldin432/sadeem-iso/resolve/main/sadeem-45.iso)**
- **صفحة الإصدارات الرسمية:** **[GitHub Releases (أحدث إصدار)](https://github.com/saifdiv432/sadeem/releases/latest)**

### متطلبات النظام
- **المساحة التخزينية:** لا تقل عن **40 جيجابايت** (يُوصى بقرص SSD) لاستيعاب التحديثات الذرية والحاويات.
- **الذاكرة العشوائية (RAM):** 4 جيجابايت كحد أدنى (يُوصى بـ 8 جيجابايت فأكثر للحاويات والألعاب والذكاء الاصطناعي المحلي).
- **ذاكرة USB:** بسعة 8 جيجابايت أو أكبر لوسيط التثبيت.

### حرق ملف الـ ISO على ذاكرة فلاشية
اكتب `sadeem-45.iso` مباشرة على ذاكرة USB باستخدام إحدى الأدوات التالية:
1. **Fedora Media Writer** (موصى به على Linux وWindows وmacOS).
2. **BalenaEtcher** (متوفر لجميع الأنظمة).
3. **Rufus** (على Windows: اختر **DD Image mode** عند ظهور نافذة التأكيد بعد الضغط على Start).
4. **Ventoy** (انسخ ملف `sadeem-45.iso` مباشرة إلى قسم Ventoy).

### التحويل المباشر لمستخدمي فيدورا الذرية
إذا كنت تستخدم **Fedora Silverblue 45** (أو أي توزيعة Fedora Atomic أخرى)، يمكنك التبديل إلى **سديم 45** مع الاحتفاظ الكامل بملفاتك وتطبيقات Flatpak بأمر واحد:

```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/saifdiv432/sadeem:latest
systemctl reboot
```

---

## حزمة تطبيقات سديم (GTK4 / Libadwaita)

طُوّرت تطبيقات سديم بلغة تصميم **GTK 4** و**Libadwaita** المتوافقة مع GNOME 51، وتدعم تلقائياً **10 لغات** (`العربية، الإنجليزية، الفرنسية، الإسبانية، الألمانية، التركية، الروسية، البرتغالية، الإيطالية، الصينية`):

### التطبيقات الستة الأساسية
* **نظام سديم (`sadeem-system`):** مركز تحكم موحّد من **5 صفحات** (`Adw.NavigationSplitView`):
  * **التحديثات:** فحص وتحديث عند الطلب لصورة النظام (`rpm-ostree`)، وتطبيقات `Flathub`، وحزم حاوية `sadeem-box` مع عرض عدد الحزم وأحجام التنزيل، وتحوّل الزر تلقائياً إلى **«تثبيت وإعادة التشغيل»** عند الجهوزية، مع تنظيف تلقائي بعد التحديث.
  * **الألوان والمظهر:** تخصيص اللون الأساسي عبر 8 ألوان جاهزة أو دائرة ألوان كاملة مع مزامنة فورية لـ `GNOME Shell` و`Libadwaita (GTK4)` و`GTK3`، وزر لاستعادة الخمري الأصيل (`#7a1c33`).
  * **قائمة سديم:** تخصيص حي ومباشر لإضافة `sadeem-menu@sadeem.os` عبر `org.sadeem.menu` (ربط مفتاح `Super`، شفافية الخلفية `10%–100%`، حجم الأيقونات، شريط «كل التطبيقات»، أزرار الطاقة السفلية، عدّادَي «الأكثر استخداماً» و«الأحدث تثبيتاً» من `1` إلى `4` لكل منهما، تفعيل/تعطيل كل مجموعة ذكية على حدة: **تطبيقات سديم / المكتب / الألعاب / التواصل**، وأزرار استعادة المظهر والتخطيط).
  * **التعريفات والعتاد:** فاحص شامل للعتاد (`pciutils`، `usbutils`، وحدات النواة، تحديثات البرامج الثابتة `fwupd`، وتوقيع Secure Boot عبر `mokutil`) يشمل تعريفات **NVIDIA** وحزم **CUDA** (`akmod`)، وتسريع فيديو **Intel** (`intel-media-driver`)، وترميزات **AMD Freeworld**، وبطاقات **Broadcom Wi-Fi** (`akmod-wl`)، وكاميرات **Intel IPU6/MIPI**، وصوت **SOF**، وقارئ البصمة **fprintd**، ومطابقة تلقائية لمعرّفات `modalias`.
  * **الحاويات والحزم:** إدارة سريعة لحاوية `sadeem-box` وفتح **BoxBuddy** وتنظيف الذاكرة المؤقتة.
* **معرض سديم (`sadeem-gallery`):** معرض زمني ومستعرض سريع للصور وملفات **RAW / HEIF / WebP / GIF المتحركة** مع قراءة بيانات EXIF وتعيين الخلفية، ومشغّل فيديو مدمج (`Gtk.Video`)، ومحرّر صور جانبي من **5 أقسام** (**القص، التدوير، الرسم والشرح** بنصوص عربية/إنجليزية وطمس، **الإضاءة، الفلاتر**).
* **محرّر فيديو سديم (`sadeem-video-editor`):** محرّر عملي سريع يعتمد على `FFmpeg` (`org.sadeem.VideoEditor`) يدعم تعدّد النوافذ، وقصّ المسار الزمني بتقنية النسخ السريع دون إعادة ترميز للمقاطع المنفردة، وتغيير السرعة لكل مقطع (`0.5x–4.0x`)، وقصّ الأبعاد بنِسَب جاهزة (`حر، 16:9، 9:16، 1:1، 4:3`)، ورسومات وتوضيحات زمنية (`Cairo`)، وتغطية/طمس مؤقت بـ 3 أنماط (**بيكسلات، زجاج ضبابي، تعبئة صلبة**)، ودمج أو استبدال الصوت الخارجي مع تدرّج وكتم مؤقت، والتصدير إلى فيديو أو `GIF` متحرك.
* **مدير سديم للذكاء الاصطناعي (`sadeem-ai-manager`):** مركز محلي لتشغيل النماذج بدون إنترنت عبر `llama.cpp` (`llama-server` بإصدارَي CPU وCUDA). يفحص الذاكرة والمعالج وكرت الشاشة (`nvidia-smi` / DRM) ويقيّم توافق العتاد مع كتالوج من 7 نماذج مختارة (`gemma-4-e2b`, `gemma-4-e4b`, `qwen-3.5-2b`, `qwen-3.5-9b`, `qwen-3-14b`, `phi-4-mini`, `deepseek-r1-14b`)، وينزّل ملفات `GGUF` / `mmproj` من Hugging Face مع مؤشر سرعة وإلغاء، ومحادثة متدفقة محلية.
* **رُمّان (`rumman`):** *«اسحب. أسقط. انتهى.»* اسحب أي ملف في «الملفات» مع ضغط مفتاح `Shift` (عبر `rumman-helper@rumman.app` على GNOME Wayland) أو مرّر الملفات مباشرة لتنبثق عجلة الصيغ المناسبة تحت المؤشر مع خيارات دقيقة للضغط والأبعاد والتدوير والصوت والأرشفة.
* **ترحيب سديم (`sadeem-welcome`):** جولة تفاعلية بـ 10 لغات عند أول تسجيل دخول لاستكشاف التوزيعة وإطلاق الأدوات الأساسية.

### الأدوات النظامية ومعالجات الملفات المدمجة
* **مثبّت حزم سديم (`sadeem-pkg-installer`):** تثبيت حزم **`.rpm`** و**`.deb`** بالنقر المزدوج تلقائياً داخل حاويات `Distrobox` معزولة وتصدير اختصاراتها للقائمة وتنظيف مخلفات `dnf` / `apt-get`.
* **مشغّل برامج ويندوز (`sadeem-windows-exe-handler`):** تشغيل ملفات **`.exe`** و**`.msi`** بالنقر المزدوج عبر حاوية `Sadeem-Windows` في **Bottles** مع مزامنة اختصارات التطبيقات المثبّتة وأيقوناتها تلقائياً إلى قائمة جنوم (`shortcut_sync.py`).
* **مزيل تطبيقات سديم (`sadeem-uninstaller`):** أداة موحّدة لإزالة تطبيقات **Flatpak** وتطبيقات المستخدم/**Distrobox**/**AppImage** وحزم `rpm-ostree` المضافة، مع حماية التطبيقات النظامية الأساسية.
* **الصيانة التلقائية (`sadeem-housekeeping`) ومؤقّت التحديث:** خدمة مستخدم صامتة تنظّف مكتبات Flatpak غير المستخدمة (`flatpak uninstall --unused`) وذاكرة `sadeem-box` دورياً وبعد كل تحديث، مع مؤقت `sadeem-updater-check.timer`.

---

## تجربة سطح المكتب والإضافات

تعمل **سديم 45** على **GNOME 51** مهيأةً مسبقاً بإضافات طُوّرت خصيصاً لها مع دعم متكامل لاتجاهَي `RTL` و`LTR`:

* **قائمة سديم (`sadeem-menu@sadeem.os`):** قائمة تطبيقات أصلية مصمّمة لـ GNOME 51 تضم لوحة بلاطات حرة ثنائية الأبعاد، ومجموعات مدمجة قابلة للطي وتغيير الحجم، وسحباً وإفلاتاً حراً في المحورين، وتحجيماً سلساً من الحواف، وشفافية حية من `10%` إلى `100%`، ومجموعات ذكية تلقائية قابلة للتخصيص فردياً (**تطبيقات سديم، المكتب، الألعاب، التواصل**)، وبحثاً فورياً، وفتحاً بمفتاح `Super`، وشريطاً جانبياً قابلاً للطي مع شبكة قفز أبجدية، وأزرار الطاقة، وتكاملاً مع «إلغاء التثبيت» بالكلك يمين عبر **10 لغات**.
* **لقطة سديم (`sadeem-capture` و`captureUI.js` و`recorder.py`):** تجميد فوري للشاشة عند ضغط `Print` مع 3 أوضاع (**تحديد، شاشة، نافذة**):
  * **الصور:** التقاط مباشر وفوري من الإطار المجمّد عبر `Shell.Screenshot.composite_to_stream` مع خيارات المؤشر وهالته، وحفظ دون تعارض أسماء، ونسخ للحافظة، وفتح/تحرير مباشر في **معرض سديم** من الإشعار.
  * **تسجيل الفيديو:** تسجيل مسرّع بالعتاد عبر PipeWire (`VA-API` بنقل `DMA-BUF` الصفري أو `vapostproc`، و`NVENC`، وارتداد برمجي `x264`/`x265`) بدعم `H.264` و`H.265` ودقّات `الأصلي / 1080p / 720p` و`30 / 60 FPS` ومزج صوت النظام والميكروفون (`48 kHz` AAC)، والتقاط صور صامتة بـ `Print` أثناء التسجيل، وإيقاف التسجيل بـ `Shift+Print`، ثم الفتح المباشر في **محرّر فيديو سديم**.
* **مساعد سطح مكتب سديم (`sadeem-desktop-helper@sadeem.os`):** يعيد ترتيب شريط المهام (`Dash to Panel`) تلقائياً وفق اتجاه اللغة `RTL/LTR`، ويفتح قوائم **الحافظة** (`Super+V`) و**الرموز التعبيرية** (`Super+.`) عند موضع مؤشر الفأرة مباشرة، ويضيف خيار **«التقاط لقطة شاشة»** لقوائم النوافذ، وخيار **«إلغاء التثبيت»** المترجم داخل قوائم تطبيقات جنوم (مربوطاً بأداة `sadeem-uninstaller`).
* **ساعة وطقس شاشة القفل (`adwaita-lock-clock@saifeldin.osama`):** واجهة شاشة قفل مخصّصة بنمط Libadwaita مع **معاينة حية مثبتة** في الإعدادات (`15` لغة) وإمكانات تخصيص شاملة:
  * **الساعة الهجينة والتموضع:** ساعة هجينة **24 / 12 ساعة** بأرقام مدارية وعقارب منحوتة وتوهج دائري، مع زر لإخفاء/إظهار عقرب الثواني لتوفير الطاقة، والتحكم بالمقياس (`75%–135%`)، وشفافية البطاقة (`0%–100%`)، والموقع الرأسي على الشاشة (`30%–70%`).
  * **بطاقة الطقس التفصيلية (`Open-Meteo`):** الحرارة الحالية والصغرى/العظمى ومقارنتها بالأمس، و**توقعات 3 أيام**، و4 مؤشرات مستقلة (**الرطوبة، سرعة الرياح، الحرارة المحسوسة، الأشعة فوق البنفسجية**)، ووحدات تلقائية أو يدوية (`°C/°F` و`km/h / m/s / mph`)، مع تحديد الموقع تلقائياً أو البحث في قاعدة مدن ودول ومناطق زمنية مدمجة.
  * **التقاويم والأرقام والألوان:** التاريخ الميلادي مع تقويم ثانوي محلي (**الهجري أم القرى**، الفارسي، الصيني، الياباني، البوذي، الهندي، الإثيوبي، أو **رقم الأسبوع ISO**)، وعرض اليوم منفرداً أو **شريط الأسبوع الكامل (7 أيام)** مع تخصيص بداية الأسبوع (`تلقائي / السبت / الأحد / الإثنين`)، و**22 نظام أرقام عالمياً**، ومزامنة تلقائية مع **اللون الأساسي للنظام** والسمة (`النظام / داكن / فاتح`).
* **الإضافات المصاحبة المفعّلة تلقائياً:**
  * `dash-to-panel@jderose9.github.com` (شريط مهام سفلي متكامل)
  * `clipboard-indicator@tudmotu.com` (سجل الحافظة عبر `Super+V` عند المؤشر)
  * `emoji-copy@felipeftn` (منتقي الرموز التعبيرية عبر `Super+.` عند المؤشر)
  * `rumman-helper@rumman.app` (جسر السحب بمفتاح `Shift` لتطبيق رُمّان على GNOME Wayland)
  * `user-theme@gnome-shell-extensions.gcampax.github.com` و`light-style@gnome-shell-extensions.gcampax.github.com`
* **الخطوط واللغات:** خطوط عربية ومكتبية مدمجة افتراضياً (`Vazirmatn` للواجهة، و`Noto Sans Arabic` للمستندات، و`Amiri` و`Carlito` و`Caladea` و`Liberation` و`Noto Nastaliq Urdu` و`Noto Sans Devanagari` و`Noto Sans CJK`) مع **12 حزمة لغة** لنظام فيدورا (`en, ar, ru, es, tr, fr, it, hi, zh_CN, ur, ms, id`).

---

## بيئة التطبيقات والحاويات والتحديث الآلي (CI)

* **متجر Flathub الكامل مفعّل افتراضياً:** مع إزالة مستودع فيدورا المقيّد أثناء البناء، ومزامنة لغات تطبيقات Flatpak تلقائياً عبر `flatpak-configure-languages.service`.
* **حزمة Flatpak المثبتة مسبقاً (`recipe.yml`):** `Firefox`، و`GNOME Text Editor`، و`LibreOffice`، و`VLC`، و`Extension Manager`، و`Refine`، و`Flatseal`، و`Bottles`، و`ProtonUp-Qt`، و`BoxBuddy`، و`Gear Lever` (لإدارة ملفات `AppImage`).
* **حاويات معزولة جاهزة (`Distrobox` + `BoxBuddy`):** تهيئة صامتة في الخلفية لحاوية `sadeem-box` (`sadeem-init-sandbox.service`) لتشغيل الحزم والأدوات الخارجية دون المساس بجذر النظام الذري.
* **برامج خارجية مدمجة ومحدّثة آلياً:**
  * **ZapFast (`crmne/zapfast`):** عميل واتساب مكتبي أصيل وخفيف مبني بلغة Rust (`v0.21.3`).
  * **Mister Download Manager (`anefzaoui/misterdownloadmanager`):** مدير تنزيلات سريع متعدد الاتصالات والتورنت (`v0.5.2`) مدمج مسبقاً مع إضافات `Firefox` و`Chromium`.
* **البناء والمزامنة الآلية على GitHub Actions:**
  * يقوم ملف [`.github/workflows/build.yml`](.github/workflows/build.yml) ببناء وتوقيع صور التوزيعة آلياً مرتين أسبوعياً (الإثنين والخميس `06:00 UTC`) وعند كل تحديث.
  * يفحص ملف [`.github/workflows/sync-external-apps.yml`](.github/workflows/sync-external-apps.yml) يومياً (`03:00 UTC`) أحدث إصدارات **ZapFast** و**Mister Download Manager** على GitHub، ويتحقق من سلامة الأرشيفات، ويحدّث الإضافات والروابط الاحتياطية في المستودع تلقائياً ثم يطلق بناء صورة جديدة فور صدور أي تحديث.

---

## الترميز وتسريع العتاد الكامل

* مستودعات **RPM Fusion** (الحرة وغير الحرة) مفعّلة افتراضياً.
* تسريع الفيديو بالعتاد وحزمة الترميزات الكاملة (`intel-media-driver`، `mesa-va-drivers-freeworld`، `libavcodec-freeworld`، `gstreamer1-plugins-bad-freeworld`، `gstreamer1-plugins-ugly`، `gstreamer1-plugin-libav`، `pipewire-gstreamer`).
* دعم معاينة الصور والمصغّرات وفك الأرشيفات مباشرة: `HEIF/HEIC` (`libheif-freeworld`، `heif-pixbuf-loader`)، و`WebP` (`webp-pixbuf-loader`)، ومصغّرات الفيديو (`ffmpegthumbnailer`)، وفك ضغط `RAR` (`unrar`) و`7z` (`p7zip` / `p7zip-plugins`).

</div>
