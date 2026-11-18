#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem AI Manager — مدير سديم للذكاء الاصطناعي
GTK 4 / Libadwaita local AI model manager, hardware profiler, comparison matrix, and offline chat.
Identity: Sadeem Burgundy (#7a1c33)
"""

import os
import re
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import engine
import hardware

APP_ID = "org.sadeem.AIManager"


def detect_lang():
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        val = os.environ.get(var, "")
        if val:
            code = val.split(":")[0].split(".")[0].split("_")[0].split("@")[0].lower()
            if code in ("ar", "en"):
                return code
    return "ar"


LANG = detect_lang()

STRINGS = {
    "ar": {
        "app_title": "مدير سديم للذكاء الاصطناعي",
        "app_subtitle": "ذكاء اصطناعي محلي وخاص 100% على جهازك بدون إنترنت أو اشتراكات",
        "tab_catalog": "النماذج والعتاد",
        "tab_compare": "مقارنة النماذج",
        "tab_chat": "المحادثة المحلية",
        "btn_guide": "دليل الاستخدام",
        "btn_rescan": "إعادة الفحص",
        "onb_title": "مرحباً بك في مدير سديم للذكاء الاصطناعي",
        "onb_1_title": "ذكاء اصطناعي خاص 100% على جهازك",
        "onb_1_desc": "يعمل دون اتصال بالإنترنت بعد التنزيل، ودون اشتراكات شهرية أو إرسال أي كلمة من بياناتك وملفاتك إلى خوادم خارجية.",
        "onb_2_title": "فحص ذكي لعتاد حاسوبك",
        "onb_2_desc": "يحلّل الذاكرة العشوائية والمعالج وكرت الشاشة تلقائياً ليقترح النماذج المثالية ويحميك من تحميل نماذج ثقيلة تبطئ النظام.",
        "onb_3_title": "تنزيل وتشغيل مباشر بضغطة زر",
        "onb_3_desc": "اختر النموذج المناسب ليتم تنزيله من مصدره الرسمي وتجهيز محرك التشغيل للمحادثة وقراءة الملفات والصور فوراً.",
        "onb_prev": "السابق",
        "onb_next": "التالي",
        "onb_start": "ابدأ الفحص الآن",
        "hw_card_title": "ملخص فحص العتاد التلقائي",
        "hw_scanning": "جارٍ تحليل عتاد الجهاز (الذاكرة، المعالج، بطاقة الرسوميات)...",
        "hw_ram": "الذاكرة العشوائية (RAM)",
        "hw_ram_val": "{total:.1f} GB كلية — {avail:.1f} GB متاحة الآن",
        "hw_cpu": "المعالج المركزي (CPU)",
        "hw_cpu_val": "{model} ({cores} أنوية{avx})",
        "hw_gpu": "البطاقة الرسومية (GPU)",
        "hw_gpu_vram": "{name} — ذاكرة فيديو {vram:.1f} GB{cuda}",
        "hw_gpu_novram": "{name}",
        "hw_rec_tier": "الفئة الأنسب لجهازك",
        "vision_yes": "يدعم الصور (Vision)",
        "vision_no": "نصوص فقط",
        "ctx_label": "سياق {ctx}",
        "size_label": "الحجم: ~{size:.1f} GB",
        "ram_req_label": "الذاكرة المطلوبة: ~{ram:.1f} GB",
        "btn_download": "تنزيل وتهيئة",
        "btn_download_locked": "تنزيل (تحذير الذاكرة)",
        "btn_cancel": "إلغاء",
        "btn_chat_now": "بدء المحادثة الآن",
        "btn_delete": "حذف النموذج",
        "dl_preparing": "جاري تحضير التنزيل ومحرك التشغيل...",
        "dl_progress": "{label}: {pct}% ({done:.0f} / {total:.0f} MB — {speed:.1f} MB/s)",
        "dl_done": "تم تنزيل وتهيئة {name} بنجاح! يمكنك بدء المحادثة الآن.",
        "dl_cancelled": "تم إلغاء التنزيل.",
        "dl_error": "فشل التنزيل: {err}",
        "warn_heavy_title": "تحذير: النموذج يتطلب ذاكرة أكبر من المتاح",
        "warn_heavy_body": "يحتاج النموذج «{name}» إلى نحو {req:.1f} GB من الذاكرة (أكثر من 85% من الذاكرة المتاحة على جهازك). قد يؤدي تشغيله إلى بطء شديد أو تجمّد النظام.\n\nهل تريد المتابعة وتنزيله رغم ذلك؟",
        "warn_continue": "تنزيل على مسؤوليتي",
        "del_confirm_title": "حذف النموذج المحلي؟",
        "del_confirm_body": "سيتم حذف ملفات النموذج «{name}» من جهازك لتوفير مساحة التخزين.",
        "del_confirm_btn": "حذف نهائياً",
        "deleted_toast": "تم حذف النموذج {name} وتحرير المساحة.",
        "cmp_title": "مقارنة شاملة للنماذج المقترحة",
        "cmp_desc": "قارن بين النماذج المفتوحة من حيث التوافق مع عتادك، البرمجة، الدقة، السياق، فهم الصور، وجودة العربية.",
        "cmp_col_model": "النموذج",
        "cmp_col_compat": "التوافق والسرعة المتوقعة",
        "cmp_col_coding": "البرمجة والمنطق",
        "cmp_col_accuracy": "الدقة ومستوى الهلوسة",
        "cmp_col_files": "تحليل الملفات والسياق",
        "cmp_col_vision": "فهم وتحليل الصور",
        "cmp_col_arabic": "العربية وحجم التنزيل",
        "chat_no_models_title": "لا توجد نماذج مثبّتة بعد",
        "chat_no_models_desc": "انتقل إلى تبويب «النماذج والعتاد» لتنزيل أول نموذج ذكاء اصطناعي محلي بضغطة زر.",
        "chat_go_catalog": "تصفح النماذج المتاحة",
        "chat_model_label": "النموذج:",
        "chat_new": "محادثة جديدة",
        "chat_status_idle": "متوقف",
        "chat_status_loading": "جارٍ تحميل النموذج محلياً...",
        "chat_status_ready": "متصل محلياً (127.0.0.1)",
        "chat_status_err": "خطأ في المحرك المحلي",
        "chat_placeholder": "اكتب رسالتك أو سؤالك هنا... (Enter للإرسال، Shift+Enter لسطر جديد)",
        "chat_send": "إرسال",
        "chat_stop": "إيقاف",
        "chat_attach_file": "إرفاق ملف",
        "chat_attach_image": "إرفاق صورة",
        "chat_vision_only_tip": "هذا النموذج للنصوص فقط — اختر نموذجاً داعماً للصور مثل Gemma 4 أو Qwen 3.5",
        "chat_welcome_msg": "مرحباً! أنا مساعدك المحلي الخاص على نظام سديم 45. تعمل محادثاتنا بالكامل على جهازك دون اتصال بالإنترنت. يمكنك طرح الأسئلة، كتابة الأكواد، إرفاق ملفات PDF/نصوص، أو إرفاق الصور مع النماذج الداعمة لها.",
        "chat_you": "أنت",
        "chat_ai": "المساعد المحلي",
        "chat_file_attached": "ملف مرفق: {name}",
        "chat_image_attached": "صورة مرفقة: {name}",
        "chat_file_err": "تعذر قراءة الملف: {err}",
        "chat_server_err": "تعذر تشغيل النموذج المحلي: {err}",
        "chat_stream_err": "خطأ أثناء توليد الإجابة: {err}",
        "system_prompt": "أنت مساعد ذكي ودقيق يعمل محلياً بالكامل على نظام التشغيل سديم 45 (Sadeem 45). أجب بوضوح واحترافية وباللغة التي يكتب بها المستخدم.",
    },
    "en": {
        "app_title": "Sadeem AI Manager",
        "app_subtitle": "100% private local AI on your computer — offline, no subscriptions",
        "tab_catalog": "Models & Hardware",
        "tab_compare": "Model Comparison",
        "tab_chat": "Local Chat",
        "btn_guide": "User Guide",
        "btn_rescan": "Rescan",
        "onb_title": "Welcome to Sadeem AI Manager",
        "onb_1_title": "100% Private AI on Your Device",
        "onb_1_desc": "Runs completely offline with no subscriptions and never sends your conversations, files, or images to any external server.",
        "onb_2_title": "Smart Hardware Profiling",
        "onb_2_desc": "Automatically analyzes your RAM, CPU, and GPU/VRAM to recommend ideal models and protect your system from heavy downloads.",
        "onb_3_title": "Direct Download & Instant Chat",
        "onb_3_desc": "Pick a model to download directly from official sources and start chatting, analyzing documents, and inspecting images immediately.",
        "onb_prev": "Previous",
        "onb_next": "Next",
        "onb_start": "Start Hardware Scan",
        "hw_card_title": "Automatic Hardware Profile",
        "hw_scanning": "Analyzing system hardware (RAM, CPU, GPU/VRAM)...",
        "hw_ram": "System Memory (RAM)",
        "hw_ram_val": "{total:.1f} GB Total — {avail:.1f} GB Available",
        "hw_cpu": "Processor (CPU)",
        "hw_cpu_val": "{model} ({cores} cores{avx})",
        "hw_gpu": "Graphics Card (GPU)",
        "hw_gpu_vram": "{name} — {vram:.1f} GB VRAM{cuda}",
        "hw_gpu_novram": "{name}",
        "hw_rec_tier": "Recommended Tier for Your PC",
        "vision_yes": "Vision Supported",
        "vision_no": "Text Only",
        "ctx_label": "{ctx} Context",
        "size_label": "Size: ~{size:.1f} GB",
        "ram_req_label": "RAM Required: ~{ram:.1f} GB",
        "btn_download": "Download & Setup",
        "btn_download_locked": "Download (RAM Warning)",
        "btn_cancel": "Cancel",
        "btn_chat_now": "Start Chat Now",
        "btn_delete": "Delete Model",
        "dl_preparing": "Preparing download and inference engine...",
        "dl_progress": "{label}: {pct}% ({done:.0f} / {total:.0f} MB — {speed:.1f} MB/s)",
        "dl_done": "{name} downloaded and ready! You can start chatting now.",
        "dl_cancelled": "Download cancelled.",
        "dl_error": "Download failed: {err}",
        "warn_heavy_title": "Warning: Model Exceeds Available Memory",
        "warn_heavy_body": "'{name}' requires roughly {req:.1f} GB of RAM (over 85% of your usable memory). Running it may cause severe slowdowns or freezes.\n\nDo you still want to download it?",
        "warn_continue": "Download Anyway",
        "del_confirm_title": "Delete Local Model?",
        "del_confirm_body": "This will delete '{name}' files from your disk to free up storage space.",
        "del_confirm_btn": "Delete",
        "deleted_toast": "Deleted {name} and freed storage.",
        "cmp_title": "Model Comparison Matrix",
        "cmp_desc": "Compare open-weights models side by side across hardware fit, coding, accuracy, context window, vision, and Arabic fluency.",
        "cmp_col_model": "Model",
        "cmp_col_compat": "Compatibility & Speed",
        "cmp_col_coding": "Coding & Logic",
        "cmp_col_accuracy": "Accuracy & Hallucination",
        "cmp_col_files": "Files & Context Window",
        "cmp_col_vision": "Image / Vision Support",
        "cmp_col_arabic": "Arabic & Download Size",
        "chat_no_models_title": "No Local Models Installed Yet",
        "chat_no_models_desc": "Switch to 'Models & Hardware' to download your first local AI model with one click.",
        "chat_go_catalog": "Browse Models",
        "chat_model_label": "Model:",
        "chat_new": "New Chat",
        "chat_status_idle": "Stopped",
        "chat_status_loading": "Loading model locally...",
        "chat_status_ready": "Connected Locally (127.0.0.1)",
        "chat_status_err": "Local Engine Error",
        "chat_placeholder": "Type your message here... (Enter to send, Shift+Enter for newline)",
        "chat_send": "Send",
        "chat_stop": "Stop",
        "chat_attach_file": "Attach File",
        "chat_attach_image": "Attach Image",
        "chat_vision_only_tip": "Text-only model — choose a Vision model like Gemma 4 or Qwen 3.5",
        "chat_welcome_msg": "Hello! I am your private local AI assistant on Sadeem 45. Everything runs offline on your computer. Ask questions, write code, attach PDF/text documents, or attach images with Vision models.",
        "chat_you": "You",
        "chat_ai": "Local AI",
        "chat_file_attached": "Attached file: {name}",
        "chat_image_attached": "Attached image: {name}",
        "chat_file_err": "Could not read file: {err}",
        "chat_server_err": "Failed to start local model: {err}",
        "chat_stream_err": "Error while generating reply: {err}",
        "system_prompt": "You are a helpful, accurate AI assistant running 100% locally on Sadeem 45 Linux. Answer clearly in the user's language.",
    },
}


def t(key, **kwargs):
    val = STRINGS.get(LANG, STRINGS["ar"]).get(key) or STRINGS["en"].get(key, key)
    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            return val
    return val


def safe_icon(names, fallback="applications-science-symbolic"):
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        for name in names:
            if theme.has_icon(name):
                return name
    return fallback


SADEEM_CSS = """
.sadeem-ai-badge {
    background: linear-gradient(135deg, #7a1c33 0%, #5c1426 60%, #115e59 100%);
    border-radius: 9999px;
    border: 2px solid rgba(255, 255, 255, 0.25);
    box-shadow: 0 4px 14px rgba(122, 28, 51, 0.35);
}
.sadeem-ai-badge image {
    color: #ffffff;
}
.sadeem-burgundy-btn, button.suggested-action {
    background-color: #7a1c33;
    background-image: none;
    color: #ffffff;
}
.sadeem-burgundy-btn:hover, button.suggested-action:hover {
    background-color: #5c1426;
}
.sadeem-tier-pill {
    background-color: rgba(122, 28, 51, 0.16);
    color: #7a1c33;
    border: 1px solid rgba(122, 28, 51, 0.35);
    border-radius: 9999px;
    padding: 4px 12px;
    font-weight: 700;
    font-size: 12px;
}
.compat-excellent {
    background-color: rgba(38, 162, 105, 0.16);
    color: #1f8a57;
    border: 1px solid rgba(38, 162, 105, 0.4);
    border-radius: 9999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
.compat-acceptable {
    background-color: rgba(229, 165, 10, 0.18);
    color: #a87200;
    border: 1px solid rgba(229, 165, 10, 0.45);
    border-radius: 9999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
.compat-too_heavy {
    background-color: rgba(224, 27, 36, 0.16);
    color: #c01c28;
    border: 1px solid rgba(224, 27, 36, 0.42);
    border-radius: 9999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
.vision-pill {
    background-color: rgba(17, 94, 89, 0.16);
    color: #115e59;
    border: 1px solid rgba(17, 94, 89, 0.35);
    border-radius: 9999px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}
.meta-pill {
    background-color: rgba(128, 128, 128, 0.14);
    border-radius: 9999px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}
.cmp-header {
    background-color: rgba(122, 28, 51, 0.14);
    font-weight: 700;
    padding: 10px 12px;
    border-radius: 8px;
}
.cmp-cell {
    padding: 10px 12px;
}
.chat-bubble-user {
    background-color: #7a1c33;
    color: #ffffff;
    border-radius: 16px;
    padding: 12px 16px;
}
.chat-bubble-ai {
    background-color: alpha(currentColor, 0.06);
    border: 1px solid alpha(currentColor, 0.12);
    border-radius: 16px;
    padding: 12px 16px;
}
.chat-code-block {
    background-color: #1e1e2e;
    color: #f8f8f2;
    border-radius: 10px;
    padding: 10px 14px;
    font-family: monospace;
    font-size: 12px;
}
.chat-status-ready {
    background-color: rgba(38, 162, 105, 0.16);
    color: #1f8a57;
    border-radius: 9999px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 700;
}
.chat-status-busy {
    background-color: rgba(229, 165, 10, 0.18);
    color: #a87200;
    border-radius: 9999px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 700;
}
.chat-chip {
    background-color: rgba(122, 28, 51, 0.14);
    border: 1px solid rgba(122, 28, 51, 0.3);
    border-radius: 9999px;
    padding: 4px 12px;
    font-size: 12px;
}
"""


class OnboardingWindow(Gtk.Window):
    """Interactive 3-card Adw.Carousel onboarding guide."""

    def __init__(self, parent_window, on_finish_cb):
        super().__init__(transient_for=parent_window, modal=True)
        self.on_finish_cb = on_finish_cb
        self.set_title(t("onb_title"))
        self.set_default_size(560, 470)
        self.set_resizable(False)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        hb = Adw.HeaderBar()
        hb.set_show_end_title_buttons(True)
        root.append(hb)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_margin_top(16)
        body.set_margin_bottom(22)
        body.set_margin_start(24)
        body.set_margin_end(24)
        body.set_vexpand(True)
        root.append(body)

        self.carousel = Adw.Carousel()
        self.carousel.set_vexpand(True)
        self.carousel.set_hexpand(True)
        self.carousel.set_allow_mouse_drag(True)
        self.carousel.set_allow_scroll_wheel(True)
        body.append(self.carousel)

        slides = [
            (["security-high-symbolic", "channel-secure-symbolic"], t("onb_1_title"), t("onb_1_desc")),
            (["computer-symbolic", "video-display-symbolic"], t("onb_2_title"), t("onb_2_desc")),
            (["folder-download-symbolic", "system-software-install-symbolic"], t("onb_3_title"), t("onb_3_desc")),
        ]
        for icons, title, desc in slides:
            self.carousel.append(self._build_slide(icons, title, desc))

        dots = Adw.CarouselIndicatorDots()
        dots.set_carousel(self.carousel)
        body.append(dots)

        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav_box.set_margin_top(6)
        body.append(nav_box)

        self.btn_prev = Gtk.Button(label=t("onb_prev"))
        self.btn_prev.add_css_class("pill")
        self.btn_prev.connect("clicked", self._on_prev)
        nav_box.append(self.btn_prev)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        nav_box.append(spacer)

        self.btn_next = Gtk.Button(label=t("onb_next"))
        self.btn_next.add_css_class("pill")
        self.btn_next.connect("clicked", self._on_next)
        nav_box.append(self.btn_next)

        self.btn_start = Gtk.Button(label=t("onb_start"))
        self.btn_start.add_css_class("suggested-action")
        self.btn_start.add_css_class("pill")
        self.btn_start.set_size_request(180, 44)
        self.btn_start.connect("clicked", self._on_finish)
        nav_box.append(self.btn_start)

        self.carousel.connect("page-changed", self._on_page_changed)
        self._on_page_changed(self.carousel, 0)

    def _build_slide(self, icons, title, desc):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_start(16)
        box.set_margin_end(16)

        badge = Gtk.Box()
        badge.set_size_request(84, 84)
        badge.set_halign(Gtk.Align.CENTER)
        badge.set_valign(Gtk.Align.CENTER)
        badge.add_css_class("sadeem-ai-badge")
        img = Gtk.Image.new_from_icon_name(safe_icon(icons))
        img.set_pixel_size(40)
        img.set_hexpand(True)
        img.set_vexpand(True)
        badge.append(img)
        box.append(badge)

        lbl_t = Gtk.Label(label=title)
        lbl_t.set_wrap(True)
        lbl_t.set_justify(Gtk.Justification.CENTER)
        lbl_t.add_css_class("title-2")
        box.append(lbl_t)

        lbl_d = Gtk.Label(label=desc)
        lbl_d.set_wrap(True)
        lbl_d.set_max_width_chars(46)
        lbl_d.set_justify(Gtk.Justification.CENTER)
        lbl_d.add_css_class("dim-label")
        box.append(lbl_d)
        return box

    def _on_page_changed(self, carousel, index):
        total = carousel.get_n_pages()
        self.btn_prev.set_visible(index > 0)
        is_last = index >= total - 1
        self.btn_next.set_visible(not is_last)
        self.btn_start.set_visible(is_last)

    def _on_prev(self, *_a):
        idx = int(round(self.carousel.get_position()))
        if idx > 0:
            self.carousel.scroll_to(self.carousel.get_nth_page(idx - 1), True)

    def _on_next(self, *_a):
        idx = int(round(self.carousel.get_position()))
        if idx + 1 < self.carousel.get_n_pages():
            self.carousel.scroll_to(self.carousel.get_nth_page(idx + 1), True)

    def _on_finish(self, *_a):
        self.close()
        if self.on_finish_cb:
            self.on_finish_cb()


class SadeemAIManagerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title(t("app_title"))
        self.set_default_size(1020, 740)
        self.set_size_request(760, 580)

        self.settings = engine.load_settings()
        self.catalog = engine.load_catalog()
        self.hw = None
        self.server = engine.LlamaServerManager()

        # Download state per model_id -> {cancel_event, progress_box, bar, label, btn_dl, btn_chat, btn_del}
        self.active_downloads = {}
        self.model_widgets = {}

        # Chat state
        self.installed_models = []
        self.current_chat_model = None
        self.chat_history = []
        self.chat_streaming = False
        self.chat_cancel_event = None
        self.attached_file = None   # {"name": ..., "text": ...}
        self.attached_image = None  # {"name": ..., "data_uri": ...}

        self._install_css()
        self._build_ui()

        self.connect("close-request", self._on_close_request)

        # Start hardware profiling + optional remote catalog refresh
        self.start_hardware_profile()
        threading.Thread(target=self._refresh_catalog_worker, daemon=True).start()

        # Show onboarding on first launch
        if not self.settings.get("onboarding_done"):
            GLib.idle_add(self.show_onboarding)

    def _install_css(self):
        prov = Gtk.CssProvider()
        prov.load_from_string(SADEEM_CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _on_close_request(self, *_args):
        for dl in list(self.active_downloads.values()):
            dl["cancel"].set()
        if self.chat_cancel_event:
            self.chat_cancel_event.set()
        self.server.stop()
        return False

    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(self.toolbar_view)
        self.set_content(self.toast_overlay)

        # HeaderBar
        self.header_bar = Adw.HeaderBar()
        self.switcher_title = Adw.ViewSwitcherTitle()
        self.switcher_title.set_title(t("app_title"))

        self.view_stack = Adw.ViewStack()
        if hasattr(self.switcher_title, "set_view_stack"):
            self.switcher_title.set_view_stack(self.view_stack)
        else:
            self.switcher_title.set_stack(self.view_stack)

        self.header_bar.set_title_widget(self.switcher_title)

        # Onboarding / User Guide button in HeaderBar
        btn_guide = Gtk.Button()
        guide_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        guide_box.append(Gtk.Image.new_from_icon_name(safe_icon(["help-about-symbolic", "dialog-information-symbolic"])))
        guide_box.append(Gtk.Label(label=t("btn_guide")))
        btn_guide.set_child(guide_box)
        btn_guide.connect("clicked", lambda b: self.show_onboarding())
        self.header_bar.pack_end(btn_guide)

        self.toolbar_view.add_top_bar(self.header_bar)

        # Adaptive bottom switcher bar
        self.switcher_bar = Adw.ViewSwitcherBar()
        if hasattr(self.switcher_bar, "set_view_stack"):
            self.switcher_bar.set_view_stack(self.view_stack)
        else:
            self.switcher_bar.set_stack(self.view_stack)
        self.toolbar_view.add_bottom_bar(self.switcher_bar)
        self.switcher_title.bind_property(
            "title-visible", self.switcher_bar, "reveal", GObject.BindingFlags.SYNC_CREATE
        )

        # Build the 3 core pages
        self.page_catalog = self._build_catalog_page()
        self.page_compare = self._build_compare_page()
        self.page_chat = self._build_chat_page()

        self.view_stack.add_titled_with_icon(
            self.page_catalog, "catalog", t("tab_catalog"), safe_icon(["computer-symbolic", "system-software-install-symbolic"])
        )
        self.view_stack.add_titled_with_icon(
            self.page_compare, "compare", t("tab_compare"), safe_icon(["view-grid-symbolic", "view-list-symbolic"])
        )
        self.view_stack.add_titled_with_icon(
            self.page_chat, "chat", t("tab_chat"), safe_icon(["mail-send-symbolic", "user-available-symbolic"])
        )

        self.toolbar_view.set_content(self.view_stack)

    def show_onboarding(self):
        def _done():
            self.settings["onboarding_done"] = True
            engine.save_settings(self.settings)
            self.start_hardware_profile()

        win = OnboardingWindow(self, _done)
        win.present()
        return False

    def _clear_box(self, box):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _refresh_catalog_worker(self):
        updated = engine.refresh_catalog_remote(self.catalog)
        if updated:
            def _apply():
                self.catalog = updated
                if self.hw:
                    self._render_catalog()
                    self._render_comparison_matrix()
                return False
            GLib.idle_add(_apply)

    # =========================================================================
    # PAGE 1: HARDWARE PROFILER & MODEL CATALOG
    # =========================================================================
    def _build_catalog_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(860)
        clamp.set_tightening_threshold(620)
        scrolled.set_child(clamp)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(20)
        content.set_margin_bottom(28)
        content.set_margin_start(20)
        content.set_margin_end(20)
        clamp.set_child(content)

        # Page Hero Header
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        hero.set_halign(Gtk.Align.CENTER)
        content.append(hero)

        badge = Gtk.Box()
        badge.set_size_request(64, 64)
        badge.set_halign(Gtk.Align.CENTER)
        badge.add_css_class("sadeem-ai-badge")
        b_img = Gtk.Image.new_from_icon_name(safe_icon(["sadeem-ai-manager", "applications-science-symbolic"]))
        b_img.set_pixel_size(34)
        b_img.set_hexpand(True)
        b_img.set_vexpand(True)
        badge.append(b_img)
        hero.append(badge)

        lbl_title = Gtk.Label(label=t("app_title"))
        lbl_title.add_css_class("title-1")
        hero.append(lbl_title)

        lbl_sub = Gtk.Label(label=t("app_subtitle"))
        lbl_sub.add_css_class("dim-label")
        lbl_sub.set_wrap(True)
        lbl_sub.set_justify(Gtk.Justification.CENTER)
        hero.append(lbl_sub)

        # Hardware Profiler Summary Card
        self.hw_group = Adw.PreferencesGroup(title=t("hw_card_title"))
        rescan_btn = Gtk.Button()
        rb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        rb_box.append(Gtk.Image.new_from_icon_name(safe_icon(["view-refresh-symbolic"])))
        rb_box.append(Gtk.Label(label=t("btn_rescan")))
        rescan_btn.set_child(rb_box)
        rescan_btn.add_css_class("flat")
        rescan_btn.connect("clicked", lambda b: self.start_hardware_profile())
        self.hw_group.set_header_suffix(rescan_btn)
        content.append(self.hw_group)

        self.hw_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.hw_group.add(self.hw_box)

        # Models container
        self.catalog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.append(self.catalog_box)

        return scrolled

    def start_hardware_profile(self):
        self._clear_box(self.hw_box)
        scan_row = Adw.ActionRow()
        scan_row.set_use_markup(False)
        scan_row.set_title(t("hw_scanning"))
        sp = Gtk.Spinner()
        sp.set_spinning(True)
        scan_row.add_prefix(sp)
        lb = Gtk.ListBox()
        lb.add_css_class("boxed-list")
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.append(scan_row)
        self.hw_box.append(lb)

        def _worker():
            hw = hardware.profile_hardware()
            GLib.idle_add(self._on_hardware_ready, hw)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_hardware_ready(self, hw):
        self.hw = hw
        self._render_hw_card()
        self._render_catalog()
        self._render_comparison_matrix()
        self._refresh_chat_model_selector()
        return False

    def _render_hw_card(self):
        self._clear_box(self.hw_box)
        hw = self.hw or {}

        lb = Gtk.ListBox()
        lb.add_css_class("boxed-list")
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        self.hw_box.append(lb)

        # RAM Row
        r_ram = Adw.ActionRow()
        r_ram.set_use_markup(False)
        r_ram.set_title(t("hw_ram"))
        r_ram.set_subtitle(t("hw_ram_val", total=hw.get("ram_total_gb", 0.0), avail=hw.get("ram_avail_gb", 0.0)))
        r_ram.add_prefix(Gtk.Image.new_from_icon_name(safe_icon(["drive-harddisk-symbolic", "computer-symbolic"])))
        lb.append(r_ram)

        # CPU Row
        r_cpu = Adw.ActionRow()
        r_cpu.set_use_markup(False)
        r_cpu.set_title(t("hw_cpu"))
        avx_txt = " — AVX2" if hw.get("has_avx2") else ""
        r_cpu.set_subtitle(t("hw_cpu_val", model=hw.get("cpu_model", ""), cores=hw.get("cpu_cores", 4), avx=avx_txt))
        r_cpu.add_prefix(Gtk.Image.new_from_icon_name(safe_icon(["applications-engineering-symbolic", "computer-symbolic"])))
        lb.append(r_cpu)

        # GPU Row
        r_gpu = Adw.ActionRow()
        r_gpu.set_use_markup(False)
        r_gpu.set_title(t("hw_gpu"))
        vram = hw.get("vram_gb", 0.0)
        if vram > 0:
            cuda_txt = " (CUDA)" if hw.get("has_cuda") else ""
            r_gpu.set_subtitle(t("hw_gpu_vram", name=hw.get("gpu_name", ""), vram=vram, cuda=cuda_txt))
        else:
            r_gpu.set_subtitle(t("hw_gpu_novram", name=hw.get("gpu_name", "")))
        r_gpu.add_prefix(Gtk.Image.new_from_icon_name(safe_icon(["video-display-symbolic"])))
        lb.append(r_gpu)

        # Recommended Tier Row
        r_rec = Adw.ActionRow()
        r_rec.set_use_markup(False)
        r_rec.set_title(t("hw_rec_tier"))
        rec_lbl = hw.get("recommended_range_ar") if LANG == "ar" else hw.get("recommended_range_en")
        r_rec.set_subtitle(rec_lbl or "")
        r_rec.add_prefix(Gtk.Image.new_from_icon_name(safe_icon(["starred-symbolic", "emblem-ok-symbolic"])))
        pill = Gtk.Label(label=rec_lbl or "")
        pill.set_valign(Gtk.Align.CENTER)
        pill.add_css_class("sadeem-tier-pill")
        r_rec.add_suffix(pill)
        lb.append(r_rec)

    def _render_catalog(self):
        self._clear_box(self.catalog_box)
        self.model_widgets = {}
        tiers = self.catalog.get("tiers", [])
        models = self.catalog.get("models", [])

        for tier in tiers:
            tid = tier["id"]
            tier_models = [m for m in models if m.get("tier") == tid]
            if not tier_models:
                continue

            grp = Adw.PreferencesGroup(
                title=tier["name_ar"] if LANG == "ar" else tier["name_en"],
                description=tier["desc_ar"] if LANG == "ar" else tier["desc_en"]
            )
            self.catalog_box.append(grp)

            for model in tier_models:
                grp.add(self._build_model_card(model))

    def _build_model_card(self, model):
        mid = model["id"]
        compat = hardware.evaluate_model_compatibility(model, self.hw or {})
        installed = engine.is_model_installed(model)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.set_margin_bottom(10)
        card.set_margin_top(2)
        card.set_margin_start(2)
        card.set_margin_end(2)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        card.append(inner)

        # Top row: Name + Compatibility Badge
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        inner.append(top)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        top.append(title_box)

        lbl_name = Gtk.Label(label=model["name"])
        lbl_name.set_halign(Gtk.Align.START)
        lbl_name.add_css_class("title-4")
        title_box.append(lbl_name)

        lbl_prov = Gtk.Label(label=f"{model.get('provider', '')}  •  {model.get('hf_repo', '')}")
        lbl_prov.set_halign(Gtk.Align.START)
        lbl_prov.add_css_class("dim-label")
        lbl_prov.add_css_class("caption")
        title_box.append(lbl_prov)

        compat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        compat_box.set_valign(Gtk.Align.CENTER)
        compat_lbl = compat["label_ar"] if LANG == "ar" else compat["label_en"]
        if compat["level"] == "too_heavy":
            lock_ico = Gtk.Image.new_from_icon_name(safe_icon(["changes-prevent-symbolic", "dialog-warning-symbolic"]))
            lock_ico.set_pixel_size(14)
            compat_box.append(lock_ico)
        lbl_compat = Gtk.Label(label=compat_lbl)
        compat_box.append(lbl_compat)
        compat_box.add_css_class(f"compat-{compat['level']}")
        top.append(compat_box)

        # Description
        desc_txt = model.get("desc_ar") if LANG == "ar" else model.get("desc_en")
        lbl_desc = Gtk.Label(label=desc_txt or "")
        lbl_desc.set_halign(Gtk.Align.START)
        lbl_desc.set_wrap(True)
        lbl_desc.set_xalign(0.0)
        lbl_desc.add_css_class("dim-label")
        inner.append(lbl_desc)

        # Metadata pills (size, RAM req, Context, Vision)
        meta_row = Gtk.FlowBox()
        meta_row.set_selection_mode(Gtk.SelectionMode.NONE)
        meta_row.set_row_spacing(6)
        meta_row.set_column_spacing(6)
        inner.append(meta_row)

        total_dl_gb = float(model.get("size_gb", 0)) + float(model.get("mmproj_size_gb", 0))
        for txt, css_cls in [
            (t("size_label", size=total_dl_gb), "meta-pill"),
            (t("ram_req_label", ram=model.get("ram_required_gb", 0)), "meta-pill"),
            (t("ctx_label", ctx=model.get("context_label", "32K")), "meta-pill"),
            (t("vision_yes") if model.get("vision") else t("vision_no"), "vision-pill" if model.get("vision") else "meta-pill"),
        ]:
            pl = Gtk.Label(label=txt)
            pl.add_css_class(css_cls)
            meta_row.append(pl)

        # Download progress box (hidden unless downloading)
        prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prog_box.set_visible(False)
        inner.append(prog_box)

        prog_bar = Gtk.ProgressBar()
        prog_bar.set_show_text(True)
        prog_box.append(prog_bar)

        prog_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        prog_box.append(prog_bottom)

        lbl_prog = Gtk.Label(label=t("dl_preparing"))
        lbl_prog.set_hexpand(True)
        lbl_prog.set_halign(Gtk.Align.START)
        lbl_prog.set_ellipsize(Pango.EllipsizeMode.END)
        lbl_prog.add_css_class("caption")
        lbl_prog.add_css_class("dim-label")
        prog_bottom.append(lbl_prog)

        btn_cancel = Gtk.Button(label=t("btn_cancel"))
        btn_cancel.add_css_class("destructive-action")
        btn_cancel.add_css_class("pill")
        btn_cancel.connect("clicked", lambda b, m_id=mid: self._cancel_download(m_id))
        prog_bottom.append(btn_cancel)

        # Action Buttons Row
        act_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        act_row.set_margin_top(4)
        inner.append(act_row)

        btn_dl = Gtk.Button(label=t("btn_download_locked") if compat["level"] == "too_heavy" else t("btn_download"))
        if compat["level"] != "too_heavy":
            btn_dl.add_css_class("suggested-action")
        btn_dl.add_css_class("pill")
        btn_dl.set_visible(not installed)
        btn_dl.connect("clicked", lambda b, m=model, c=compat: self._on_download_clicked(m, c))
        act_row.append(btn_dl)

        btn_chat = Gtk.Button(label=t("btn_chat_now"))
        btn_chat.add_css_class("suggested-action")
        btn_chat.add_css_class("pill")
        btn_chat.set_visible(installed)
        btn_chat.connect("clicked", lambda b, m=model: self._open_chat_with_model(m))
        act_row.append(btn_chat)

        btn_del = Gtk.Button(label=t("btn_delete"))
        btn_del.add_css_class("destructive-action")
        btn_del.add_css_class("pill")
        btn_del.set_visible(installed)
        btn_del.connect("clicked", lambda b, m=model: self._confirm_delete_model(m))
        act_row.append(btn_del)

        self.model_widgets[mid] = {
            "prog_box": prog_box,
            "prog_bar": prog_bar,
            "lbl_prog": lbl_prog,
            "btn_dl": btn_dl,
            "btn_chat": btn_chat,
            "btn_del": btn_del,
        }

        # Restore visible progress if download already active
        if mid in self.active_downloads:
            prog_box.set_visible(True)
            btn_dl.set_visible(False)

        return card

    def _on_download_clicked(self, model, compat):
        if compat["level"] == "too_heavy":
            self._show_heavy_warning(model, compat)
        else:
            self._start_model_download(model)

    def _show_heavy_warning(self, model, compat):
        dlg = Gtk.Window(transient_for=self, modal=True)
        dlg.set_title(t("warn_heavy_title"))
        dlg.set_default_size(440, -1)
        dlg.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        dlg.set_child(box)

        lbl_t = Gtk.Label(label=t("warn_heavy_title"))
        lbl_t.add_css_class("title-3")
        lbl_t.set_wrap(True)
        lbl_t.set_halign(Gtk.Align.START)
        box.append(lbl_t)

        lbl_b = Gtk.Label(label=t("warn_heavy_body", name=model["name"], req=compat["ram_required_gb"]))
        lbl_b.set_wrap(True)
        lbl_b.set_halign(Gtk.Align.START)
        lbl_b.add_css_class("dim-label")
        box.append(lbl_b)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btns.set_halign(Gtk.Align.END)
        box.append(btns)

        b_cancel = Gtk.Button(label=t("btn_cancel"))
        b_cancel.add_css_class("pill")
        b_cancel.connect("clicked", lambda b: dlg.close())
        btns.append(b_cancel)

        b_ok = Gtk.Button(label=t("warn_continue"))
        b_ok.add_css_class("destructive-action")
        b_ok.add_css_class("pill")

        def _go(*_a):
            dlg.close()
            self._start_model_download(model)

        b_ok.connect("clicked", _go)
        btns.append(b_ok)
        dlg.present()

    def _start_model_download(self, model):
        mid = model["id"]
        if mid in self.active_downloads:
            return
        cancel_ev = threading.Event()
        self.active_downloads[mid] = {"cancel": cancel_ev}

        w = self.model_widgets.get(mid)
        if w:
            w["btn_dl"].set_visible(False)
            w["prog_box"].set_visible(True)
            w["prog_bar"].set_fraction(0.0)
            w["prog_bar"].set_text("0%")
            w["lbl_prog"].set_text(t("dl_preparing"))

        def _on_prog(info):
            def _upd():
                ww = self.model_widgets.get(mid)
                if not ww:
                    return False
                frac = info.get("fraction", 0.0)
                pct = int(round(frac * 100))
                ww["prog_bar"].set_fraction(frac)
                ww["prog_bar"].set_text(f"{pct}%")
                ww["lbl_prog"].set_text(
                    t(
                        "dl_progress",
                        label=info.get("label", model["name"]),
                        pct=pct,
                        done=info.get("downloaded_mb", 0.0),
                        total=info.get("total_mb", 0.0),
                        speed=info.get("speed_mb", 0.0),
                    )
                )
                return False
            GLib.idle_add(_upd)

        def _worker():
            try:
                engine.download_model_and_engine(model, self.hw or {}, progress_cb=_on_prog, cancel_event=cancel_ev)
                GLib.idle_add(self._on_download_finished, model, True, "")
            except engine.DownloadCancelled:
                GLib.idle_add(self._on_download_finished, model, False, "CANCELLED")
            except Exception as exc:
                GLib.idle_add(self._on_download_finished, model, False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _cancel_download(self, model_id):
        dl = self.active_downloads.get(model_id)
        if dl:
            dl["cancel"].set()

    def _on_download_finished(self, model, success, err):
        mid = model["id"]
        self.active_downloads.pop(mid, None)
        w = self.model_widgets.get(mid)
        if w:
            w["prog_box"].set_visible(False)
            if success:
                w["btn_dl"].set_visible(False)
                w["btn_chat"].set_visible(True)
                w["btn_del"].set_visible(True)
            else:
                w["btn_dl"].set_visible(True)

        if success:
            self.toast_overlay.add_toast(Adw.Toast.new(t("dl_done", name=model["name"])))
            self._refresh_chat_model_selector()
            self._render_comparison_matrix()
        elif err == "CANCELLED":
            self.toast_overlay.add_toast(Adw.Toast.new(t("dl_cancelled")))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(t("dl_error", err=err)))
        return False

    def _confirm_delete_model(self, model):
        dlg = Gtk.Window(transient_for=self, modal=True)
        dlg.set_title(t("del_confirm_title"))
        dlg.set_default_size(400, -1)
        dlg.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        dlg.set_child(box)

        lbl_t = Gtk.Label(label=t("del_confirm_title"))
        lbl_t.add_css_class("title-3")
        lbl_t.set_halign(Gtk.Align.START)
        box.append(lbl_t)

        lbl_b = Gtk.Label(label=t("del_confirm_body", name=model["name"]))
        lbl_b.set_wrap(True)
        lbl_b.set_halign(Gtk.Align.START)
        lbl_b.add_css_class("dim-label")
        box.append(lbl_b)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btns.set_halign(Gtk.Align.END)
        box.append(btns)

        b_cancel = Gtk.Button(label=t("btn_cancel"))
        b_cancel.add_css_class("pill")
        b_cancel.connect("clicked", lambda b: dlg.close())
        btns.append(b_cancel)

        b_del = Gtk.Button(label=t("del_confirm_btn"))
        b_del.add_css_class("destructive-action")
        b_del.add_css_class("pill")

        def _do_del(*_a):
            dlg.close()
            if self.server.active_model_id == model["id"]:
                self.server.stop()
            engine.delete_model_files(model)
            self._render_catalog()
            self._render_comparison_matrix()
            self._refresh_chat_model_selector()
            self.toast_overlay.add_toast(Adw.Toast.new(t("deleted_toast", name=model["name"])))

        b_del.connect("clicked", _do_del)
        btns.append(b_del)
        dlg.present()

    # =========================================================================
    # PAGE 2: MODEL COMPARISON MATRIX
    # =========================================================================
    def _build_compare_page(self):
        outer = Gtk.ScrolledWindow()
        outer.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(20)
        box.set_margin_bottom(28)
        box.set_margin_start(20)
        box.set_margin_end(20)
        outer.set_child(box)

        lbl_t = Gtk.Label(label=t("cmp_title"))
        lbl_t.add_css_class("title-2")
        lbl_t.set_halign(Gtk.Align.START)
        box.append(lbl_t)

        lbl_d = Gtk.Label(label=t("cmp_desc"))
        lbl_d.add_css_class("dim-label")
        lbl_d.set_wrap(True)
        lbl_d.set_halign(Gtk.Align.START)
        box.append(lbl_d)

        hscroll = Gtk.ScrolledWindow()
        hscroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        hscroll.set_vexpand(True)
        box.append(hscroll)

        self.cmp_grid_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hscroll.set_child(self.cmp_grid_holder)
        return outer

    def _render_comparison_matrix(self):
        self._clear_box(self.cmp_grid_holder)
        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)
        grid.add_css_class("card")
        grid.set_margin_top(4)
        grid.set_margin_bottom(4)
        self.cmp_grid_holder.append(grid)

        headers = [
            t("cmp_col_model"),
            t("cmp_col_compat"),
            t("cmp_col_coding"),
            t("cmp_col_accuracy"),
            t("cmp_col_files"),
            t("cmp_col_vision"),
            t("cmp_col_arabic"),
        ]
        for col, htext in enumerate(headers):
            hl = Gtk.Label(label=htext)
            hl.add_css_class("cmp-header")
            hl.set_halign(Gtk.Align.FILL)
            hl.set_xalign(0.0)
            grid.attach(hl, col, 0, 1, 1)

        is_ar = LANG == "ar"
        for row_idx, model in enumerate(self.catalog.get("models", []), start=1):
            compat = hardware.evaluate_model_compatibility(model, self.hw or {})
            ratings = model.get("ratings", {})
            installed = engine.is_model_installed(model)
            total_dl_gb = float(model.get("size_gb", 0)) + float(model.get("mmproj_size_gb", 0))

            # Col 0: Model name + quick button
            c0 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            c0.add_css_class("cmp-cell")
            ln = Gtk.Label(label=model["name"])
            ln.set_halign(Gtk.Align.START)
            ln.add_css_class("heading")
            c0.append(ln)
            if installed:
                qb = Gtk.Button(label=t("btn_chat_now"))
                qb.add_css_class("suggested-action")
                qb.add_css_class("pill")
                qb.set_halign(Gtk.Align.START)
                qb.connect("clicked", lambda b, m=model: self._open_chat_with_model(m))
                c0.append(qb)
            grid.attach(c0, 0, row_idx, 1, 1)

            # Col 1: Compatibility + Expected speed
            c1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            c1.add_css_class("cmp-cell")
            badge = Gtk.Label(label=compat["label_ar"] if is_ar else compat["label_en"])
            badge.add_css_class(f"compat-{compat['level']}")
            badge.set_halign(Gtk.Align.START)
            c1.append(badge)
            sp = Gtk.Label(label=ratings.get("speed_ar" if is_ar else "speed_en", ""))
            sp.set_halign(Gtk.Align.START)
            sp.add_css_class("caption")
            sp.add_css_class("dim-label")
            c1.append(sp)
            grid.attach(c1, 1, row_idx, 1, 1)

            # Col 2..5
            cells = [
                ratings.get("coding_ar" if is_ar else "coding_en", ""),
                ratings.get("accuracy_ar" if is_ar else "accuracy_en", ""),
                ratings.get("files_ar" if is_ar else "files_en", ""),
                ratings.get("vision_ar" if is_ar else "vision_en", ""),
                f"{ratings.get('arabic_ar' if is_ar else 'arabic_en', '')}\n(~{total_dl_gb:.1f} GB)",
            ]
            for offset, text in enumerate(cells, start=2):
                lbl = Gtk.Label(label=text)
                lbl.add_css_class("cmp-cell")
                lbl.set_wrap(True)
                lbl.set_max_width_chars(24)
                lbl.set_xalign(0.0)
                if offset == 5 and model.get("vision"):
                    lbl.add_css_class("vision-pill")
                grid.attach(lbl, offset, row_idx, 1, 1)

    # =========================================================================
    # PAGE 3: INTEGRATED LOCAL CHAT VIEW
    # =========================================================================
    def _build_chat_page(self):
        self.chat_stack = Gtk.Stack()
        self.chat_stack.set_vexpand(True)

        # Empty state when no model is installed
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_box.set_margin_start(32)
        empty_box.set_margin_end(32)

        e_ico = Gtk.Image.new_from_icon_name(safe_icon(["folder-download-symbolic", "applications-science-symbolic"]))
        e_ico.set_pixel_size(56)
        e_ico.add_css_class("dim-label")
        empty_box.append(e_ico)

        e_title = Gtk.Label(label=t("chat_no_models_title"))
        e_title.add_css_class("title-2")
        empty_box.append(e_title)

        e_desc = Gtk.Label(label=t("chat_no_models_desc"))
        e_desc.add_css_class("dim-label")
        e_desc.set_wrap(True)
        e_desc.set_justify(Gtk.Justification.CENTER)
        empty_box.append(e_desc)

        btn_go = Gtk.Button(label=t("chat_go_catalog"))
        btn_go.add_css_class("suggested-action")
        btn_go.add_css_class("pill")
        btn_go.set_size_request(200, 44)
        btn_go.connect("clicked", lambda b: self.view_stack.set_visible_child_name("catalog"))
        empty_box.append(btn_go)

        self.chat_stack.add_named(empty_box, "empty")

        # Active Chat Interface
        chat_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Top control bar (Model selector + server status + New Chat)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top_bar.set_margin_top(10)
        top_bar.set_margin_bottom(10)
        top_bar.set_margin_start(16)
        top_bar.set_margin_end(16)
        chat_root.append(top_bar)

        lbl_m = Gtk.Label(label=t("chat_model_label"))
        lbl_m.add_css_class("heading")
        top_bar.append(lbl_m)

        self.chat_model_list = Gtk.StringList()
        self.chat_model_dropdown = Gtk.DropDown(model=self.chat_model_list)
        self.chat_model_dropdown.set_hexpand(True)
        self.chat_model_dropdown.connect("notify::selected", self._on_chat_model_selected)
        top_bar.append(self.chat_model_dropdown)

        self.lbl_server_status = Gtk.Label(label=t("chat_status_idle"))
        self.lbl_server_status.add_css_class("meta-pill")
        top_bar.append(self.lbl_server_status)

        btn_new = Gtk.Button(label=t("chat_new"))
        btn_new.add_css_class("pill")
        btn_new.connect("clicked", lambda b: self._reset_chat_conversation())
        top_bar.append(btn_new)

        chat_root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Messages scroll area
        self.chat_scroll = Gtk.ScrolledWindow()
        self.chat_scroll.set_vexpand(True)
        chat_root.append(self.chat_scroll)

        msg_clamp = Adw.Clamp()
        msg_clamp.set_maximum_size(820)
        self.chat_scroll.set_child(msg_clamp)

        self.chat_messages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.chat_messages_box.set_margin_top(16)
        self.chat_messages_box.set_margin_bottom(16)
        self.chat_messages_box.set_margin_start(16)
        self.chat_messages_box.set_margin_end(16)
        msg_clamp.set_child(self.chat_messages_box)

        # Attachment preview strip
        self.attach_strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.attach_strip.set_margin_start(16)
        self.attach_strip.set_margin_end(16)
        self.attach_strip.set_margin_bottom(6)
        self.attach_strip.set_visible(False)
        chat_root.append(self.attach_strip)

        chat_root.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Bottom Composer Bar
        comp_clamp = Adw.Clamp()
        comp_clamp.set_maximum_size(820)
        chat_root.append(comp_clamp)

        composer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        composer.set_margin_top(10)
        composer.set_margin_bottom(12)
        composer.set_margin_start(16)
        composer.set_margin_end(16)
        comp_clamp.set_child(composer)

        # Attach File button
        self.btn_attach_file = Gtk.Button()
        self.btn_attach_file.set_icon_name(safe_icon(["mail-attachment-symbolic", "document-open-symbolic"]))
        self.btn_attach_file.set_tooltip_text(t("chat_attach_file"))
        self.btn_attach_file.add_css_class("circular")
        self.btn_attach_file.set_valign(Gtk.Align.END)
        self.btn_attach_file.connect("clicked", self._on_attach_file_clicked)
        composer.append(self.btn_attach_file)

        # Attach Image button (Vision models only)
        self.btn_attach_image = Gtk.Button()
        self.btn_attach_image.set_icon_name(safe_icon(["insert-image-symbolic", "camera-photo-symbolic"]))
        self.btn_attach_image.set_tooltip_text(t("chat_attach_image"))
        self.btn_attach_image.add_css_class("circular")
        self.btn_attach_image.set_valign(Gtk.Align.END)
        self.btn_attach_image.connect("clicked", self._on_attach_image_clicked)
        composer.append(self.btn_attach_image)

        # Multi-line message input
        in_scroll = Gtk.ScrolledWindow()
        in_scroll.set_hexpand(True)
        in_scroll.set_min_content_height(44)
        in_scroll.set_max_content_height(130)
        in_scroll.add_css_class("card")
        composer.append(in_scroll)

        self.chat_input_buf = Gtk.TextBuffer()
        self.chat_input_view = Gtk.TextView.new_with_buffer(self.chat_input_buf)
        self.chat_input_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.chat_input_view.set_top_margin(10)
        self.chat_input_view.set_bottom_margin(10)
        self.chat_input_view.set_left_margin(12)
        self.chat_input_view.set_right_margin(12)
        in_scroll.set_child(self.chat_input_view)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_chat_key_pressed)
        self.chat_input_view.add_controller(key_ctrl)

        # Send / Stop button
        self.btn_chat_send = Gtk.Button(label=t("chat_send"))
        self.btn_chat_send.add_css_class("suggested-action")
        self.btn_chat_send.add_css_class("pill")
        self.btn_chat_send.set_valign(Gtk.Align.END)
        self.btn_chat_send.set_size_request(96, 44)
        self.btn_chat_send.connect("clicked", self._on_send_or_stop_clicked)
        composer.append(self.btn_chat_send)

        self.chat_stack.add_named(chat_root, "chat")
        self._reset_chat_conversation()
        return self.chat_stack

    def _refresh_chat_model_selector(self):
        self.installed_models = [m for m in self.catalog.get("models", []) if engine.is_model_installed(m)]
        # Rebuild StringList safely
        n = self.chat_model_list.get_n_items()
        if n > 0:
            self.chat_model_list.splice(0, n, [])
        for m in self.installed_models:
            self.chat_model_list.append(m["name"])

        if not self.installed_models:
            self.current_chat_model = None
            self.chat_stack.set_visible_child_name("empty")
            return

        self.chat_stack.set_visible_child_name("chat")
        target_idx = 0
        last_id = self.settings.get("last_model_id", "")
        if self.current_chat_model:
            last_id = self.current_chat_model["id"]
        for i, m in enumerate(self.installed_models):
            if m["id"] == last_id:
                target_idx = i
                break
        self.chat_model_dropdown.set_selected(target_idx)
        self._select_chat_model(self.installed_models[target_idx])

    def _open_chat_with_model(self, model):
        self._refresh_chat_model_selector()
        for i, m in enumerate(self.installed_models):
            if m["id"] == model["id"]:
                self.chat_model_dropdown.set_selected(i)
                self._select_chat_model(m)
                break
        self.view_stack.set_visible_child_name("chat")

    def _on_chat_model_selected(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.installed_models):
            self._select_chat_model(self.installed_models[idx])

    def _select_chat_model(self, model):
        self.current_chat_model = model
        self.settings["last_model_id"] = model["id"]
        engine.save_settings(self.settings)

        # Toggle Vision button based on model support
        supports_vision = bool(model.get("vision"))
        self.btn_attach_image.set_sensitive(supports_vision)
        self.btn_attach_image.set_tooltip_text(
            t("chat_attach_image") if supports_vision else t("chat_vision_only_tip")
        )
        if not supports_vision and self.attached_image:
            self.attached_image = None
            self._render_attach_strip()

        # Start local llama-server for selected model in background
        self._ensure_server_running_async(model)

    def _set_server_status(self, text, style_class):
        def _upd():
            for cls in ("meta-pill", "chat-status-ready", "chat-status-busy"):
                self.lbl_server_status.remove_css_class(cls)
            self.lbl_server_status.add_css_class(style_class)
            self.lbl_server_status.set_text(text)
            return False
        GLib.idle_add(_upd)

    def _ensure_server_running_async(self, model):
        if self.server.is_running() and self.server.active_model_id == model["id"]:
            self._set_server_status(t("chat_status_ready"), "chat-status-ready")
            return

        self._set_server_status(t("chat_status_loading"), "chat-status-busy")

        def _worker():
            try:
                self.server.start(model, self.hw or {})
                self._set_server_status(t("chat_status_ready"), "chat-status-ready")
            except Exception as exc:
                self._set_server_status(t("chat_status_err"), "compat-too_heavy")
                GLib.idle_add(self.toast_overlay.add_toast, Adw.Toast.new(t("chat_server_err", err=str(exc))))

        threading.Thread(target=_worker, daemon=True).start()

    def _reset_chat_conversation(self):
        self.chat_history = [{"role": "system", "content": t("system_prompt")}]
        self.attached_file = None
        self.attached_image = None
        self._render_attach_strip()
        self._clear_box(self.chat_messages_box)
        self._add_chat_bubble("assistant", t("chat_welcome_msg"))

    def _scroll_chat_bottom(self):
        def _do():
            adj = self.chat_scroll.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            return False
        GLib.idle_add(_do)

    def _populate_rich_text_box(self, container, text):
        """Render message text with crisp fenced monospace code blocks."""
        self._clear_box(container)
        parts = re.split(r"```(?:[a-zA-Z0-9_+-]*)\n?(.*?)```", text, flags=re.DOTALL)
        for idx, part in enumerate(parts):
            chunk = part.strip("\n")
            if not chunk and len(parts) > 1:
                continue
            if idx % 2 == 1:
                # Code block
                code_lbl = Gtk.Label(label=chunk)
                code_lbl.set_selectable(True)
                code_lbl.set_wrap(True)
                code_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                code_lbl.set_xalign(0.0)
                code_lbl.set_direction(Gtk.TextDirection.LTR)
                code_lbl.add_css_class("chat-code-block")
                container.append(code_lbl)
            else:
                lbl = Gtk.Label(label=chunk)
                lbl.set_selectable(True)
                lbl.set_wrap(True)
                lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                lbl.set_xalign(0.0)
                container.append(lbl)

    def _add_chat_bubble(self, role, text, note=""):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.set_hexpand(True)

        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bubble.set_size_request(120, -1)
        if role == "user":
            row.set_halign(Gtk.Align.END)
            bubble.add_css_class("chat-bubble-user")
        else:
            row.set_halign(Gtk.Align.START)
            bubble.add_css_class("chat-bubble-ai")

        hdr = Gtk.Label(label=t("chat_you") if role == "user" else t("chat_ai"))
        hdr.set_halign(Gtk.Align.START)
        hdr.add_css_class("caption")
        hdr.add_css_class("heading")
        bubble.append(hdr)

        if note:
            n_lbl = Gtk.Label(label=note)
            n_lbl.set_halign(Gtk.Align.START)
            n_lbl.add_css_class("caption")
            bubble.append(n_lbl)

        body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._populate_rich_text_box(body_box, text)
        bubble.append(body_box)

        row.append(bubble)
        self.chat_messages_box.append(row)
        self._scroll_chat_bottom()
        return body_box

    def _render_attach_strip(self):
        self._clear_box(self.attach_strip)
        has_any = False
        if self.attached_file:
            has_any = True
            chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            chip.add_css_class("chat-chip")
            chip.append(Gtk.Label(label=t("chat_file_attached", name=self.attached_file["name"])))
            rm = Gtk.Button(label="×")
            rm.add_css_class("flat")
            rm.connect("clicked", self._clear_attached_file)
            chip.append(rm)
            self.attach_strip.append(chip)

        if self.attached_image:
            has_any = True
            chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            chip.add_css_class("chat-chip")
            chip.append(Gtk.Label(label=t("chat_image_attached", name=self.attached_image["name"])))
            rm = Gtk.Button(label="×")
            rm.add_css_class("flat")
            rm.connect("clicked", self._clear_attached_image)
            chip.append(rm)
            self.attach_strip.append(chip)

        self.attach_strip.set_visible(has_any)

    def _clear_attached_file(self, *_a):
        self.attached_file = None
        self._render_attach_strip()

    def _clear_attached_image(self, *_a):
        self.attached_image = None
        self._render_attach_strip()

    def _on_attach_file_clicked(self, *_a):
        dlg = Gtk.FileDialog()
        dlg.set_title(t("chat_attach_file"))
        flt = Gtk.FileFilter()
        flt.set_name("Documents & Code (.pdf, .txt, .md, .py, .json, .csv)")
        for pat in ("*.pdf", "*.txt", "*.md", "*.py", "*.json", "*.csv", "*.log", "*.yml", "*.yaml", "*.sh"):
            flt.add_pattern(pat)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)

        def _on_open(dialog, res):
            try:
                gfile = dialog.open_finish(res)
                if not gfile:
                    return
                fpath = gfile.get_path()
                extracted = engine.extract_document_text(fpath)
                self.attached_file = {"name": os.path.basename(fpath), "text": extracted}
                self._render_attach_strip()
            except GLib.Error:
                pass
            except Exception as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(t("chat_file_err", err=str(exc))))

        dlg.open(self, None, _on_open)

    def _on_attach_image_clicked(self, *_a):
        dlg = Gtk.FileDialog()
        dlg.set_title(t("chat_attach_image"))
        flt = Gtk.FileFilter()
        flt.set_name("Images (.png, .jpg, .jpeg, .webp)")
        for pat in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif"):
            flt.add_pattern(pat)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)

        def _on_open(dialog, res):
            try:
                gfile = dialog.open_finish(res)
                if not gfile:
                    return
                fpath = gfile.get_path()
                uri = engine.encode_image_data_uri(fpath)
                self.attached_image = {"name": os.path.basename(fpath), "data_uri": uri}
                self._render_attach_strip()
            except GLib.Error:
                pass
            except Exception as exc:
                self.toast_overlay.add_toast(Adw.Toast.new(t("chat_file_err", err=str(exc))))

        dlg.open(self, None, _on_open)

    def _on_chat_key_pressed(self, _ctrl, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if not (state & Gdk.ModifierType.SHIFT_MASK):
                self._on_send_or_stop_clicked()
                return True
        return False

    def _on_send_or_stop_clicked(self, *_a):
        if self.chat_streaming:
            if self.chat_cancel_event:
                self.chat_cancel_event.set()
            return

        if not self.current_chat_model:
            return

        start, end = self.chat_input_buf.get_bounds()
        user_text = self.chat_input_buf.get_text(start, end, False).strip()
        if not user_text and not self.attached_file and not self.attached_image:
            return

        self.chat_input_buf.set_text("")

        # Build message payload (handling attached file + optional Vision image)
        notes = []
        prompt_text = user_text
        if self.attached_file:
            notes.append(t("chat_file_attached", name=self.attached_file["name"]))
            file_block = f"\n\n--- [{self.attached_file['name']}] ---\n{self.attached_file['text']}\n---"
            prompt_text = (prompt_text or "قم بتحليل هذا الملف وتلخيصه:") + file_block

        img_data_uri = None
        if self.attached_image and self.current_chat_model.get("vision"):
            notes.append(t("chat_image_attached", name=self.attached_image["name"]))
            img_data_uri = self.attached_image["data_uri"]
            if not prompt_text:
                prompt_text = "صف هذه الصورة وحلّل محتواها بدقة."

        self.attached_file = None
        self.attached_image = None
        self._render_attach_strip()

        self._add_chat_bubble("user", user_text or prompt_text[:120], note="  •  ".join(notes))

        if img_data_uri:
            user_msg = {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": img_data_uri}},
                ],
            }
        else:
            user_msg = {"role": "user", "content": prompt_text}

        self.chat_history.append(user_msg)
        ai_body_box = self._add_chat_bubble("assistant", "…")

        self.chat_streaming = True
        self.chat_cancel_event = threading.Event()
        self.btn_chat_send.set_label(t("chat_stop"))
        self.btn_chat_send.remove_css_class("suggested-action")
        self.btn_chat_send.add_css_class("destructive-action")

        model = self.current_chat_model
        messages_snapshot = list(self.chat_history)
        stream_buf = []
        last_ui_upd = [0.0]

        def _worker():
            try:
                if not (self.server.is_running() and self.server.active_model_id == model["id"]):
                    self._set_server_status(t("chat_status_loading"), "chat-status-busy")
                    self.server.start(model, self.hw or {})
                    self._set_server_status(t("chat_status_ready"), "chat-status-ready")

                import time as _time

                def _on_tok(piece):
                    stream_buf.append(piece)
                    now = _time.monotonic()
                    if now - last_ui_upd[0] >= 0.06:
                        last_ui_upd[0] = now
                        cur_txt = "".join(stream_buf)
                        GLib.idle_add(self._update_streaming_bubble, ai_body_box, cur_txt)

                full_reply = self.server.stream_chat(
                    messages_snapshot, on_token=_on_tok, cancel_event=self.chat_cancel_event
                )
                GLib.idle_add(self._on_chat_stream_done, ai_body_box, full_reply, "")
            except Exception as exc:
                GLib.idle_add(self._on_chat_stream_done, ai_body_box, "".join(stream_buf), str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_streaming_bubble(self, body_box, text):
        self._populate_rich_text_box(body_box, text)
        self._scroll_chat_bottom()
        return False

    def _on_chat_stream_done(self, body_box, reply_text, err):
        self.chat_streaming = False
        self.btn_chat_send.set_label(t("chat_send"))
        self.btn_chat_send.remove_css_class("destructive-action")
        self.btn_chat_send.add_css_class("suggested-action")

        if err:
            final_txt = reply_text or t("chat_stream_err", err=err)
            self._populate_rich_text_box(body_box, final_txt)
            self.toast_overlay.add_toast(Adw.Toast.new(t("chat_stream_err", err=err)))
        else:
            final_txt = reply_text.strip() or "—"
            self._populate_rich_text_box(body_box, final_txt)
            self.chat_history.append({"role": "assistant", "content": final_txt})
        self._scroll_chat_bottom()
        return False


class SadeemAIManagerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.window = None

    def do_activate(self):
        if LANG == "ar":
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        else:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)

        if not self.window:
            self.window = SadeemAIManagerWindow(self)
        self.window.present()


def main():
    GLib.set_prgname(APP_ID)
    app = SadeemAIManagerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
