#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Capture — أداة لقطة وتسجيل سديم الموحدة
Clean, fast GTK 4 / Libadwaita screen capture & recording utility
following GNOME Screenshot UI / HIG geometry and proportions.
"""

import math
import os
import shutil
import subprocess
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
import cairo
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, PangoCairo

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from capture_client import (
    CaptureClient,
    copy_file_to_clipboard,
    generate_screenshot_path,
    launch_gallery_editor,
)
import i18n

t = i18n.t
APP_ID = "org.sadeem.Capture"

CAPTURE_CSS = """
window.sadeem-capture-window {
    background-color: transparent;
}

.sadeem-top-pill {
    background-color: rgba(28, 28, 33, 0.90);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 9999px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.42);
    padding: 7px 16px;
}

.sadeem-top-pill-label {
    color: #f1f5f9;
    font-size: 13px;
    font-weight: 500;
}

.sadeem-panel {
    background-color: rgba(36, 36, 40, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 20px;
    padding: 14px 16px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55);
}

.sadeem-close-btn {
    background-color: #35353b;
    background-image: none;
    border-radius: 9999px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    color: #cbd5e1;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
}

.sadeem-close-btn:hover {
    background-color: rgba(224, 27, 36, 0.85);
    border-color: rgba(255, 255, 255, 0.25);
    color: #ffffff;
}

.sadeem-mode-btn {
    background-color: transparent;
    background-image: none;
    border-radius: 12px;
    border: none;
    color: #d4d4d8;
    min-width: 86px;
    min-height: 54px;
    padding: 8px 10px;
    transition: background-color 140ms ease;
}

.sadeem-mode-btn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}

.sadeem-mode-btn.active {
    background-color: rgba(255, 255, 255, 0.14);
    color: #ffffff;
}

.sadeem-mode-btn.active:hover {
    background-color: rgba(255, 255, 255, 0.20);
}

.sadeem-mode-label {
    font-size: 12px;
    font-weight: 600;
}

.sadeem-pill-group {
    background-color: rgba(255, 255, 255, 0.08);
    border-radius: 9999px;
    padding: 3px;
}

.sadeem-pill-btn {
    background-color: transparent;
    background-image: none;
    border: none;
    border-radius: 9999px;
    color: #cbd5e1;
    min-width: 40px;
    min-height: 32px;
    padding: 0;
    transition: background-color 140ms ease;
}

.sadeem-pill-btn:hover {
    color: #ffffff;
    background-color: rgba(255, 255, 255, 0.08);
}

.sadeem-pill-btn.active {
    background-color: rgba(255, 255, 255, 0.20);
    color: #ffffff;
}

.sadeem-pill-btn:disabled {
    opacity: 0.35;
}

.sadeem-shutter-ring {
    background-color: transparent;
    background-image: none;
    border-radius: 9999px;
    border: 2.5px solid rgba(255, 255, 255, 0.92);
    padding: 4px;
    min-width: 44px;
    min-height: 44px;
    transition: border-color 140ms ease;
}

.sadeem-shutter-ring:hover {
    border-color: #ffffff;
}

.sadeem-shutter-core {
    border-radius: 9999px;
    background-color: #7a1c33;
    color: #ffffff;
    box-shadow: 0 2px 10px rgba(122, 28, 51, 0.55);
    transition: background-color 140ms ease;
}

.sadeem-shutter-core:hover {
    background-color: #91243f;
}

.sadeem-shutter-core.record-mode {
    background-color: #e01b24;
    box-shadow: 0 2px 10px rgba(224, 27, 36, 0.60);
}

.sadeem-shutter-core.record-mode:hover {
    background-color: #f63b44;
}

.sadeem-video-bar {
    border-top: 1px solid rgba(255, 255, 255, 0.09);
    padding-top: 10px;
    margin-top: 2px;
}

.sadeem-chip-btn {
    background-color: rgba(255, 255, 255, 0.07);
    background-image: none;
    border-radius: 9999px;
    border: none;
    color: #cbd5e1;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
}

.sadeem-chip-btn:hover {
    background-color: rgba(255, 255, 255, 0.14);
    color: #ffffff;
}

.sadeem-chip-btn.active {
    background-color: rgba(255, 255, 255, 0.20);
    color: #ffffff;
}

.sadeem-popover-box {
    padding: 12px;
}
"""


def format_file_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def _send_notification(app, notif_id: str, title: str, body: str, icon_name: str):
    try:
        notif = Gio.Notification.new(title)
        notif.set_body(body)
        notif.set_icon(Gio.ThemedIcon.new(icon_name))
        app.send_notification(notif_id, notif)
    except Exception:
        pass
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "-a", t("app_name"), "-i", icon_name, title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass


def _make_mode_button(icon_name: str, label_text: str) -> Gtk.Button:
    btn = Gtk.Button()
    btn.add_css_class("flat")
    btn.add_css_class("sadeem-mode-btn")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_pixel_size(20)
    lbl = Gtk.Label(label=label_text)
    lbl.add_css_class("sadeem-mode-label")
    box.append(img)
    box.append(lbl)
    btn.set_child(box)
    return btn


def _make_pill_button(icon_name: str, tooltip: str) -> Gtk.Button:
    btn = Gtk.Button()
    btn.add_css_class("flat")
    btn.add_css_class("sadeem-pill-btn")
    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_pixel_size(18)
    btn.set_child(img)
    btn.set_size_request(40, 32)
    btn.set_halign(Gtk.Align.CENTER)
    btn.set_valign(Gtk.Align.CENTER)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn


def _make_inline_button(icon_name: str, label_text: str, css_class: str) -> Gtk.Button:
    btn = Gtk.Button()
    btn.add_css_class("flat")
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_pixel_size(15)
    lbl = Gtk.Label(label=label_text)
    box.append(img)
    box.append(lbl)
    btn.set_child(box)
    btn.add_css_class(css_class)
    return btn


def _make_circle_button(icon_name: str, tooltip: str, css_class: str, size: int = 36, icon_size: int = 16) -> Gtk.Button:
    btn = Gtk.Button()
    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_pixel_size(icon_size)
    btn.set_child(img)
    btn.set_size_request(size, size)
    btn.set_halign(Gtk.Align.CENTER)
    btn.set_valign(Gtk.Align.CENTER)
    btn.set_hexpand(False)
    btn.set_vexpand(False)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    btn.add_css_class(css_class)
    return btn


class SadeemCaptureWindow(Gtk.Window):
    def __init__(self, app, initial_mode="selection", initial_media="photo", bg_path=None):
        super().__init__(application=app)
        self.app = app
        self.client = app.client
        self.mode = initial_mode
        self.media_type = initial_media
        self.cursor_enabled = True
        self.halo_enabled = False

        self.bg_path = bg_path
        self.bg_texture = None
        if self.bg_path and os.path.isfile(self.bg_path):
            try:
                self.bg_texture = Gdk.Texture.new_from_filename(self.bg_path)
            except Exception as e:
                print(f"[sadeem-capture] Failed to load bg texture: {e}", file=sys.stderr)

        # Video settings (lazy-loaded microphones on demand)
        self.video_resolution = "native"
        self.video_framerate = 30
        self.video_codec = "h264"
        self.audio_system_enabled = True
        self.audio_mic_enabled = False
        self.available_mics = []
        self.selected_mic_id = "@DEFAULT_SOURCE@"
        self._mics_loaded = False

        self.recorder = None
        self.is_recording = False
        self._stop_sig_id = None
        self._silent_sig_id = None

        # Selection state
        self.sel_x = 0.0
        self.sel_y = 0.0
        self.sel_w = 0.0
        self.sel_h = 0.0
        self._drag_action = None  # "new", "move", "tl", "tr", "bl", "br"
        self._drag_origin_x = 0.0
        self._drag_origin_y = 0.0
        self._drag_init_rect = (0.0, 0.0, 0.0, 0.0)

        self.windows = []
        self.hovered_window = None
        self._action_in_progress = False

        self.set_title(t("app_name"))
        self.add_css_class("sadeem-capture-window")
        self.set_decorated(False)
        self.connect("destroy", self._on_destroy)

        self._build_ui()
        self._setup_events()

        if self.mode == "window":
            self.windows = self.client.list_windows()
        if self.media_type == "video":
            self._set_media_type("video")
        if not self.bg_texture and not self.client.is_helper_available():
            self.toast_overlay.add_toast(Adw.Toast.new(t("helper_disabled_warning")))

    def _on_destroy(self, _w):
        if not self.is_recording:
            self._cleanup_bg()

    def _cleanup_bg(self):
        self.bg_texture = None
        if self.bg_path and os.path.exists(self.bg_path):
            try:
                os.remove(self.bg_path)
            except Exception:
                pass
        self.bg_path = None

    def _finish_session(self):
        self.app.close_capture_session(self)

    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.overlay = Gtk.Overlay()
        self.toast_overlay.set_child(self.overlay)
        self.set_child(self.toast_overlay)

        # Layer 0: GPU-accelerated frozen desktop snapshot
        self.bg_picture = Gtk.Picture()
        self.bg_picture.set_hexpand(True)
        self.bg_picture.set_vexpand(True)
        self.bg_picture.set_content_fit(Gtk.ContentFit.FILL)
        self.bg_picture.set_can_target(False)
        if self.bg_texture:
            self.bg_picture.set_paintable(self.bg_texture)
        self.overlay.set_child(self.bg_picture)

        # Layer 1: Interactive Cairo canvas for dimming, selection & window highlight
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_vexpand(True)
        self.drawing_area.set_draw_func(self._on_draw)
        self.overlay.add_overlay(self.drawing_area)

        # Layer 2: Top floating hint pill (non-interactive so it never steals drags)
        self.top_pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.top_pill.set_halign(Gtk.Align.CENTER)
        self.top_pill.set_valign(Gtk.Align.START)
        self.top_pill.set_margin_top(28)
        self.top_pill.set_can_target(False)
        self.top_pill.add_css_class("sadeem-top-pill")

        self.top_pill_icon = Gtk.Image.new_from_icon_name("edit-select-all-symbolic")
        self.top_pill_icon.set_pixel_size(15)
        self.top_pill.append(self.top_pill_icon)

        self.top_pill_label = Gtk.Label()
        self.top_pill_label.add_css_class("sadeem-top-pill-label")
        self.top_pill.append(self.top_pill_label)
        self.overlay.add_overlay(self.top_pill)

        # Layer 3: GNOME-HIG Bottom Floating Control Panel
        self.panel_wrapper = Gtk.Overlay()
        self.panel_wrapper.set_halign(Gtk.Align.CENTER)
        self.panel_wrapper.set_valign(Gtk.Align.END)
        self.panel_wrapper.set_margin_bottom(32)

        self.toolbar_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.toolbar_card.add_css_class("sadeem-panel")
        self.toolbar_card.set_margin_top(12)
        self.toolbar_card.set_margin_start(12)
        self.toolbar_card.set_margin_end(12)
        self.toolbar_card.set_margin_bottom(0)

        # Row 1: Mode switcher (Selection / Screen / Window)
        row_modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row_modes.set_homogeneous(True)
        row_modes.set_halign(Gtk.Align.CENTER)

        self.btn_mode_sel = _make_mode_button("edit-select-all-symbolic", t("mode_selection"))
        self.btn_mode_sel.connect("clicked", lambda _b: self._set_mode("selection"))

        self.btn_mode_screen = _make_mode_button("video-display-symbolic", t("mode_screen"))
        self.btn_mode_screen.connect("clicked", lambda _b: self._set_mode("screen"))

        self.btn_mode_win = _make_mode_button("preferences-system-windows-symbolic", t("mode_window"))
        self.btn_mode_win.connect("clicked", lambda _b: self._set_mode("window"))

        row_modes.append(self.btn_mode_sel)
        row_modes.append(self.btn_mode_screen)
        row_modes.append(self.btn_mode_win)
        self.toolbar_card.append(row_modes)

        # Row 2: Balanced CenterBox (Photo/Video | Centered Shutter | Cursor & Halo)
        row_actions = Gtk.CenterBox()
        row_actions.set_margin_top(2)

        # Start: Photo / Video pill capsule
        media_capsule = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        media_capsule.set_valign(Gtk.Align.CENTER)
        media_capsule.add_css_class("sadeem-pill-group")

        self.btn_photo = _make_pill_button("camera-photo-symbolic", t("tab_photo"))
        self.btn_photo.add_css_class("active")
        self.btn_photo.connect("clicked", lambda _b: self._set_media_type("photo"))

        self.btn_video = _make_pill_button("camera-video-symbolic", t("tab_video"))
        self.btn_video.connect("clicked", lambda _b: self._set_media_type("video"))

        media_capsule.append(self.btn_photo)
        media_capsule.append(self.btn_video)
        row_actions.set_start_widget(media_capsule)

        # Center: GNOME double-ring shutter button
        self.btn_shutter = Gtk.Button()
        self.btn_shutter.add_css_class("flat")
        self.btn_shutter.add_css_class("sadeem-shutter-ring")
        self.btn_shutter.set_size_request(56, 56)
        self.btn_shutter.set_margin_start(18)
        self.btn_shutter.set_margin_end(18)
        self.btn_shutter.set_halign(Gtk.Align.CENTER)
        self.btn_shutter.set_valign(Gtk.Align.CENTER)
        self.btn_shutter.set_tooltip_text(t("btn_capture"))

        self.shutter_core = Gtk.Box()
        self.shutter_core.add_css_class("sadeem-shutter-core")
        self.shutter_core.set_hexpand(True)
        self.shutter_core.set_vexpand(True)
        self.shutter_core.set_halign(Gtk.Align.FILL)
        self.shutter_core.set_valign(Gtk.Align.FILL)

        self.shutter_image = Gtk.Image.new_from_icon_name("camera-photo-symbolic")
        self.shutter_image.set_pixel_size(18)
        self.shutter_image.set_halign(Gtk.Align.CENTER)
        self.shutter_image.set_valign(Gtk.Align.CENTER)
        self.shutter_image.set_hexpand(True)
        self.shutter_image.set_vexpand(True)
        self.shutter_core.append(self.shutter_image)
        self.btn_shutter.set_child(self.shutter_core)
        self.btn_shutter.connect("clicked", lambda _b: self._trigger_action())
        row_actions.set_center_widget(self.btn_shutter)

        # End: Cursor & Halo pill capsule
        util_capsule = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        util_capsule.set_valign(Gtk.Align.CENTER)
        util_capsule.add_css_class("sadeem-pill-group")

        self.btn_cursor = _make_pill_button("input-mouse-symbolic", t("tooltip_cursor"))
        self.btn_cursor.add_css_class("active")
        self.btn_cursor.connect("clicked", self._toggle_cursor)

        self.btn_halo = _make_pill_button("find-location-symbolic", t("tooltip_halo"))
        self.btn_halo.connect("clicked", self._toggle_halo)

        util_capsule.append(self.btn_cursor)
        util_capsule.append(self.btn_halo)
        row_actions.set_end_widget(util_capsule)

        # Equalize width of both wings for strict geometric symmetry
        wings_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        wings_group.add_widget(media_capsule)
        wings_group.add_widget(util_capsule)

        self.toolbar_card.append(row_actions)

        # Row 3 (Revealed smoothly in Video mode only): Audio & Video Settings
        self.video_revealer = Gtk.Revealer()
        self.video_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.video_revealer.set_transition_duration(180)
        self.video_revealer.set_reveal_child(False)

        video_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        video_bar.set_halign(Gtk.Align.CENTER)
        video_bar.add_css_class("sadeem-video-bar")

        self.btn_quick_sys_audio = _make_inline_button(
            "audio-volume-high-symbolic", t("audio_system"), "sadeem-chip-btn"
        )
        self.btn_quick_sys_audio.add_css_class("active")
        self.btn_quick_sys_audio.connect("clicked", self._toggle_quick_sys_audio)
        video_bar.append(self.btn_quick_sys_audio)

        self.btn_quick_mic = _make_inline_button(
            "audio-input-microphone-symbolic", t("audio_mic"), "sadeem-chip-btn"
        )
        self.btn_quick_mic.connect("clicked", self._toggle_quick_mic)
        video_bar.append(self.btn_quick_mic)

        self.btn_video_settings = Gtk.MenuButton()
        self.btn_video_settings.add_css_class("flat")
        self.btn_video_settings.add_css_class("sadeem-chip-btn")
        settings_img = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        settings_img.set_pixel_size(16)
        self.btn_video_settings.set_child(settings_img)
        self.btn_video_settings.set_size_request(34, 34)
        self.btn_video_settings.set_valign(Gtk.Align.CENTER)
        self._build_video_settings_popover()
        video_bar.append(self.btn_video_settings)

        self.video_revealer.set_child(video_bar)
        self.toolbar_card.append(self.video_revealer)

        self.panel_wrapper.set_child(self.toolbar_card)

        # Corner close button (top-left in RTL, top-right in LTR)
        self.btn_close = Gtk.Button()
        self.btn_close.add_css_class("flat")
        self.btn_close.add_css_class("sadeem-close-btn")
        img_close = Gtk.Image.new_from_icon_name("window-close-symbolic")
        img_close.set_pixel_size(14)
        self.btn_close.set_child(img_close)
        self.btn_close.set_size_request(28, 28)
        self.btn_close.set_halign(Gtk.Align.END)
        self.btn_close.set_valign(Gtk.Align.START)
        self.btn_close.set_margin_top(0)
        self.btn_close.set_margin_end(0)
        self.btn_close.set_margin_start(0)
        self.btn_close.set_margin_bottom(0)
        self.btn_close.set_tooltip_text(t("tooltip_close"))
        self.btn_close.connect("clicked", lambda _b: self._finish_session())
        self.panel_wrapper.add_overlay(self.btn_close)

        self.overlay.add_overlay(self.panel_wrapper)
        self._update_mode_ui()

    def _build_video_settings_popover(self):
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("sadeem-popover-box")

        # Resolution
        res_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        res_box.add_css_class("sadeem-segmented")
        self.btn_res_native = Gtk.Button(label=t("res_native"))
        self.btn_res_native.add_css_class("sadeem-seg-btn")
        self.btn_res_native.add_css_class("active")
        self.btn_res_native.connect("clicked", lambda _b: self._set_resolution("native"))

        self.btn_res_1080p = Gtk.Button(label=t("res_1080p"))
        self.btn_res_1080p.add_css_class("sadeem-seg-btn")
        self.btn_res_1080p.connect("clicked", lambda _b: self._set_resolution("1080p"))

        self.btn_res_720p = Gtk.Button(label=t("res_720p"))
        self.btn_res_720p.add_css_class("sadeem-seg-btn")
        self.btn_res_720p.connect("clicked", lambda _b: self._set_resolution("720p"))

        res_box.append(self.btn_res_native)
        res_box.append(self.btn_res_1080p)
        res_box.append(self.btn_res_720p)
        box.append(res_box)

        # FPS & Codec
        row_fc = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_fc.set_halign(Gtk.Align.CENTER)

        fps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        fps_box.add_css_class("sadeem-segmented")
        self.btn_fps_30 = Gtk.Button(label=t("fps_30"))
        self.btn_fps_30.add_css_class("sadeem-seg-btn")
        self.btn_fps_30.add_css_class("active")
        self.btn_fps_30.connect("clicked", lambda _b: self._set_fps(30))

        self.btn_fps_60 = Gtk.Button(label=t("fps_60"))
        self.btn_fps_60.add_css_class("sadeem-seg-btn")
        self.btn_fps_60.connect("clicked", lambda _b: self._set_fps(60))

        fps_box.append(self.btn_fps_30)
        fps_box.append(self.btn_fps_60)
        row_fc.append(fps_box)

        codec_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        codec_box.add_css_class("sadeem-segmented")
        self.btn_codec_h264 = Gtk.Button(label="H.264")
        self.btn_codec_h264.add_css_class("sadeem-seg-btn")
        self.btn_codec_h264.add_css_class("active")
        self.btn_codec_h264.connect("clicked", lambda _b: self._set_codec("h264"))

        self.btn_codec_h265 = Gtk.Button(label="H.265")
        self.btn_codec_h265.add_css_class("sadeem-seg-btn")
        self.btn_codec_h265.connect("clicked", lambda _b: self._set_codec("h265"))

        codec_box.append(self.btn_codec_h264)
        codec_box.append(self.btn_codec_h265)
        row_fc.append(codec_box)
        box.append(row_fc)

        # Dynamic microphone container (populated lazily in background thread)
        self.mic_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.mic_box.set_visible(False)
        lbl_mic = Gtk.Label(label=t("audio_device"), halign=Gtk.Align.START)
        lbl_mic.add_css_class("caption-heading")
        self.mic_box.append(lbl_mic)
        self.mic_dropdown_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.mic_box.append(self.mic_dropdown_slot)
        box.append(self.mic_box)

        lbl_hint = Gtk.Label(label=t("hint_recording_shortcuts"), halign=Gtk.Align.CENTER)
        lbl_hint.set_wrap(True)
        lbl_hint.set_max_width_chars(38)
        lbl_hint.set_justify(Gtk.Justification.CENTER)
        lbl_hint.add_css_class("caption")
        lbl_hint.add_css_class("dim-label")
        box.append(lbl_hint)

        popover.set_child(box)
        self.btn_video_settings.set_popover(popover)

    def _load_mics_async(self):
        if self._mics_loaded:
            return
        self._mics_loaded = True

        def _worker():
            try:
                from capture.media_probe import get_connected_microphones
                mics = get_connected_microphones()
            except Exception:
                mics = []
            GLib.idle_add(self._apply_loaded_mics, mics)

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_loaded_mics(self, mics):
        self.available_mics = mics or []
        if not self.available_mics:
            return False
        self.selected_mic_id = self.available_mics[0]["id"]
        child = self.mic_dropdown_slot.get_first_child()
        while child:
            self.mic_dropdown_slot.remove(child)
            child = self.mic_dropdown_slot.get_first_child()
        names = [m["name"] for m in self.available_mics]
        dropdown = Gtk.DropDown.new(Gtk.StringList.new(names), None)
        dropdown.connect("notify::selected", self._on_mic_selected)
        self.mic_dropdown_slot.append(dropdown)
        self.mic_box.set_visible(True)
        return False

    def _on_mic_selected(self, dropdown, _param):
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.available_mics):
            self.selected_mic_id = self.available_mics[idx]["id"]

    def _setup_events(self):
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        motion_ctrl = Gtk.EventControllerMotion()
        motion_ctrl.connect("motion", self._on_motion)
        self.drawing_area.add_controller(motion_ctrl)

        drag_gesture = Gtk.GestureDrag()
        drag_gesture.connect("drag-begin", self._on_drag_begin)
        drag_gesture.connect("drag-update", self._on_drag_update)
        drag_gesture.connect("drag-end", self._on_drag_end)
        self.drawing_area.add_controller(drag_gesture)

        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", self._on_click_released)
        self.drawing_area.add_controller(click_gesture)

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self.is_recording:
                self._stop_video_recording()
            else:
                self._finish_session()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._trigger_action()
            return True
        if keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
            self._set_mode("selection")
            return True
        if keyval in (Gdk.KEY_2, Gdk.KEY_KP_2):
            self._set_mode("screen")
            return True
        if keyval in (Gdk.KEY_3, Gdk.KEY_KP_3):
            self._set_mode("window")
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self._toggle_cursor()
            return True
        if keyval in (Gdk.KEY_h, Gdk.KEY_H) and self.btn_halo.get_sensitive():
            self._toggle_halo()
            return True
        if keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self._set_media_type("video" if self.media_type == "photo" else "photo")
            return True
        return False

    def _set_mode(self, new_mode: str):
        self.mode = new_mode
        self._update_mode_ui()
        if self.mode == "window":
            self.windows = self.client.list_windows()
        self.drawing_area.queue_draw()

    def _update_top_pill(self):
        if self.mode == "selection":
            if self.sel_w > 4 and self.sel_h > 4:
                self.top_pill_label.set_text(f"{t('mode_selection')} — {int(round(self.sel_w))} × {int(round(self.sel_h))} px")
            else:
                self.top_pill_label.set_text(t("select_hint"))
            self.top_pill_icon.set_from_icon_name("edit-select-all-symbolic")
        elif self.mode == "screen":
            self.top_pill_label.set_text(t("screen_hint"))
            self.top_pill_icon.set_from_icon_name("video-display-symbolic")
        elif self.mode == "window":
            if self.hovered_window:
                title = self.hovered_window.get("title") or self.hovered_window.get("appName") or ""
                self.top_pill_label.set_text(title if len(title) <= 50 else title[:47] + "...")
            else:
                self.top_pill_label.set_text(t("window_hint"))
            self.top_pill_icon.set_from_icon_name("preferences-system-windows-symbolic")

    def _update_mode_ui(self):
        for btn, key in (
            (self.btn_mode_sel, "selection"),
            (self.btn_mode_screen, "screen"),
            (self.btn_mode_win, "window"),
        ):
            if self.mode == key:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

        if self.mode == "window" or not self.cursor_enabled:
            self.btn_halo.set_sensitive(False)
            self.halo_enabled = False
            self.btn_halo.remove_css_class("active")
        else:
            self.btn_halo.set_sensitive(True)

        self._update_top_pill()

    def _set_media_type(self, mtype: str):
        self.media_type = mtype
        if mtype == "video":
            self.btn_photo.remove_css_class("active")
            self.btn_video.add_css_class("active")
            if hasattr(self, "shutter_core"):
                self.shutter_core.add_css_class("record-mode")
            if hasattr(self, "shutter_image"):
                self.shutter_image.set_from_icon_name("media-record-symbolic")
            self.btn_shutter.set_tooltip_text(t("btn_record"))
            self.video_revealer.set_reveal_child(True)
            self._load_mics_async()
        else:
            self.btn_photo.add_css_class("active")
            self.btn_video.remove_css_class("active")
            if hasattr(self, "shutter_core"):
                self.shutter_core.remove_css_class("record-mode")
            if hasattr(self, "shutter_image"):
                self.shutter_image.set_from_icon_name("camera-photo-symbolic")
            self.btn_shutter.set_tooltip_text(t("btn_capture"))
            self.video_revealer.set_reveal_child(False)
        self.drawing_area.queue_draw()

    def _toggle_cursor(self, *_a):
        self.cursor_enabled = not self.cursor_enabled
        if self.cursor_enabled:
            self.btn_cursor.add_css_class("active")
        else:
            self.btn_cursor.remove_css_class("active")
        self._update_mode_ui()

    def _toggle_halo(self, *_a):
        if not self.cursor_enabled or self.mode == "window":
            return
        self.halo_enabled = not self.halo_enabled
        if self.halo_enabled:
            self.btn_halo.add_css_class("active")
        else:
            self.btn_halo.remove_css_class("active")

    def _toggle_quick_mic(self, *_a):
        self.audio_mic_enabled = not self.audio_mic_enabled
        if self.audio_mic_enabled:
            self.btn_quick_mic.add_css_class("active")
        else:
            self.btn_quick_mic.remove_css_class("active")

    def _toggle_quick_sys_audio(self, *_a):
        self.audio_system_enabled = not self.audio_system_enabled
        if self.audio_system_enabled:
            self.btn_quick_sys_audio.add_css_class("active")
        else:
            self.btn_quick_sys_audio.remove_css_class("active")

    def _set_resolution(self, res: str):
        self.video_resolution = res
        for btn, key in (
            (self.btn_res_native, "native"),
            (self.btn_res_1080p, "1080p"),
            (self.btn_res_720p, "720p"),
        ):
            if res == key:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

    def _set_fps(self, fps: int):
        self.video_framerate = fps
        if fps == 30:
            self.btn_fps_30.add_css_class("active")
            self.btn_fps_60.remove_css_class("active")
        else:
            self.btn_fps_30.remove_css_class("active")
            self.btn_fps_60.add_css_class("active")

    def _set_codec(self, codec: str):
        self.video_codec = codec
        if codec == "h264":
            self.btn_codec_h264.add_css_class("active")
            self.btn_codec_h265.remove_css_class("active")
        else:
            self.btn_codec_h264.remove_css_class("active")
            self.btn_codec_h265.add_css_class("active")

    # --- Pointer & Selection Interaction ---
    def _point_in_panel(self, x: float, y: float) -> bool:
        try:
            ok, rect = self.panel_wrapper.compute_bounds(self.overlay)
            if ok:
                return (
                    rect.origin.x <= x <= rect.origin.x + rect.size.width
                    and rect.origin.y <= y <= rect.origin.y + rect.size.height
                )
        except Exception:
            pass
        return False

    def _hit_test_selection(self, x: float, y: float) -> str:
        if self.sel_w <= 8 or self.sel_h <= 8:
            return "new"
        r = 16.0
        corners = (
            ("tl", self.sel_x, self.sel_y),
            ("tr", self.sel_x + self.sel_w, self.sel_y),
            ("bl", self.sel_x, self.sel_y + self.sel_h),
            ("br", self.sel_x + self.sel_w, self.sel_y + self.sel_h),
        )
        for name, cx, cy in corners:
            if math.hypot(x - cx, y - cy) <= r:
                return name
        if self.sel_x <= x <= self.sel_x + self.sel_w and self.sel_y <= y <= self.sel_y + self.sel_h:
            return "move"
        return "new"

    def _on_motion(self, _ctrl, x, y):
        if self.mode == "window":
            found = None
            for w in self.windows:
                wx, wy = w.get("x", 0), w.get("y", 0)
                ww, wh = w.get("width", 0), w.get("height", 0)
                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    found = w
                    break
            if found != self.hovered_window:
                self.hovered_window = found
                self._update_top_pill()
                self.drawing_area.queue_draw()

    def _on_drag_begin(self, _gesture, start_x, start_y):
        if self.mode != "selection" or self._point_in_panel(start_x, start_y):
            self._drag_action = None
            return
        self._drag_origin_x = start_x
        self._drag_origin_y = start_y
        self._drag_init_rect = (self.sel_x, self.sel_y, self.sel_w, self.sel_h)
        self._drag_action = self._hit_test_selection(start_x, start_y)
        if self._drag_action == "new":
            self.sel_x = start_x
            self.sel_y = start_y
            self.sel_w = 0.0
            self.sel_h = 0.0
            self._update_top_pill()
            self.drawing_area.queue_draw()

    def _on_drag_update(self, _gesture, offset_x, offset_y):
        if self.mode != "selection" or not self._drag_action:
            return
        win_w = float(self.drawing_area.get_width() or 1920)
        win_h = float(self.drawing_area.get_height() or 1080)
        ix, iy, iw, ih = self._drag_init_rect

        if self._drag_action == "new":
            cur_x = max(0.0, min(win_w, self._drag_origin_x + offset_x))
            cur_y = max(0.0, min(win_h, self._drag_origin_y + offset_y))
            self.sel_x = min(self._drag_origin_x, cur_x)
            self.sel_y = min(self._drag_origin_y, cur_y)
            self.sel_w = abs(cur_x - self._drag_origin_x)
            self.sel_h = abs(cur_y - self._drag_origin_y)
        elif self._drag_action == "move":
            self.sel_x = max(0.0, min(win_w - iw, ix + offset_x))
            self.sel_y = max(0.0, min(win_h - ih, iy + offset_y))
        else:
            x1, y1, x2, y2 = ix, iy, ix + iw, iy + ih
            if "l" in self._drag_action:
                x1 = max(0.0, min(win_w, ix + offset_x))
            if "r" in self._drag_action:
                x2 = max(0.0, min(win_w, ix + iw + offset_x))
            if "t" in self._drag_action:
                y1 = max(0.0, min(win_h, iy + offset_y))
            if "b" in self._drag_action:
                y2 = max(0.0, min(win_h, iy + ih + offset_y))
            self.sel_x = min(x1, x2)
            self.sel_y = min(y1, y2)
            self.sel_w = abs(x2 - x1)
            self.sel_h = abs(y2 - y1)

        self._update_top_pill()
        self.drawing_area.queue_draw()

    def _on_drag_end(self, _gesture, _ox, _oy):
        self._drag_action = None
        self._update_top_pill()
        self.drawing_area.queue_draw()

    def _on_click_released(self, _gesture, n_press, x, y):
        if self._point_in_panel(x, y):
            return
        if self.mode == "window" and self.hovered_window:
            self._trigger_action(target_win=self.hovered_window)
        elif self.mode == "screen":
            self._trigger_action()
        elif self.mode == "selection" and n_press == 2 and self.sel_w > 8 and self.sel_h > 8:
            if self.sel_x <= x <= self.sel_x + self.sel_w and self.sel_y <= y <= self.sel_y + self.sel_h:
                self._trigger_action()

    # --- Drawing (4-rect dimming around focus area — zero OPERATOR_CLEAR artifacts) ---
    def _dim_around(self, cr, width, height, rx, ry, rw, rh):
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.45)
        if ry > 0:
            cr.rectangle(0, 0, width, ry)
            cr.fill()
        bottom_y = ry + rh
        if bottom_y < height:
            cr.rectangle(0, bottom_y, width, height - bottom_y)
            cr.fill()
        if rx > 0:
            cr.rectangle(0, ry, rx, rh)
            cr.fill()
        right_x = rx + rw
        if right_x < width:
            cr.rectangle(right_x, ry, width - right_x, rh)
            cr.fill()

    def _on_draw(self, _area, cr, width, height):
        if not self.bg_texture:
            cr.set_source_rgba(0.08, 0.08, 0.11, 0.85)
            cr.paint()

        accent = (0.88, 0.11, 0.14, 0.95) if self.media_type == "video" else (1.0, 1.0, 1.0, 0.92)

        if self.mode == "selection":
            if self.sel_w > 4 and self.sel_h > 4:
                self._dim_around(cr, width, height, self.sel_x, self.sel_y, self.sel_w, self.sel_h)

                # Crisp dashed/solid border like GNOME Screenshot UI
                cr.set_source_rgba(*accent)
                cr.set_line_width(2.0)
                cr.rectangle(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
                cr.stroke()

                # Clean circular corner handles
                for hx, hy in (
                    (self.sel_x, self.sel_y),
                    (self.sel_x + self.sel_w, self.sel_y),
                    (self.sel_x, self.sel_y + self.sel_h),
                    (self.sel_x + self.sel_w, self.sel_y + self.sel_h),
                ):
                    cr.arc(hx, hy, 6.0, 0, 2 * math.pi)
                    cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
                    cr.fill_preserve()
                    cr.set_source_rgba(0.12, 0.12, 0.16, 0.85)
                    cr.set_line_width(1.5)
                    cr.stroke()

                # Dimensions badge via PangoCairo
                self._draw_badge(
                    cr,
                    f"{int(round(self.sel_w))} × {int(round(self.sel_h))}",
                    self.sel_x + 8,
                    self.sel_y - 32 if self.sel_y > 40 else self.sel_y + 8,
                )
            else:
                cr.set_source_rgba(0.0, 0.0, 0.0, 0.36)
                cr.paint()

        elif self.mode == "screen":
            cr.set_source_rgba(*accent)
            cr.set_line_width(3.0)
            cr.rectangle(2, 2, width - 4, height - 4)
            cr.stroke()

        elif self.mode == "window":
            if self.hovered_window:
                wx = float(self.hovered_window.get("x", 0))
                wy = float(self.hovered_window.get("y", 0))
                ww = float(self.hovered_window.get("width", 0))
                wh = float(self.hovered_window.get("height", 0))
                self._dim_around(cr, width, height, wx, wy, ww, wh)

                cr.set_source_rgba(*accent)
                cr.set_line_width(2.5)
                self._rounded_rect(cr, wx, wy, ww, wh, 10)
                cr.stroke()

                title = self.hovered_window.get("title") or self.hovered_window.get("appName") or ""
                if title:
                    display = title if len(title) <= 45 else title[:42] + "..."
                    self._draw_badge(cr, display, wx + 12, wy + 12)
            else:
                cr.set_source_rgba(0.0, 0.0, 0.0, 0.36)
                cr.paint()

    def _draw_badge(self, cr, text: str, x: float, y: float):
        layout = self.create_pango_layout(text)
        layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 10"))
        _, log_rect = layout.get_pixel_extents()
        bw = log_rect.width + 18
        bh = 26
        cr.set_source_rgba(0.11, 0.11, 0.14, 0.90)
        self._rounded_rect(cr, x, y, bw, bh, 8)
        cr.fill_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.16)
        cr.set_line_width(1.0)
        cr.stroke()

        cr.set_source_rgba(0.96, 0.97, 0.99, 1.0)
        cr.move_to(x + 9, y + (bh - log_rect.height) / 2.0)
        PangoCairo.show_layout(cr, layout)

    def _rounded_rect(self, cr, x, y, w, h, r):
        r = min(r, w / 2.0, h / 2.0)
        deg = math.pi / 180.0
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -90 * deg, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 90 * deg)
        cr.arc(x + r, y + h - r, r, 90 * deg, 180 * deg)
        cr.arc(x + r, y + r, r, 180 * deg, 270 * deg)
        cr.close_path()

    # --- Actions ---
    def _trigger_action(self, target_win=None):
        if self._action_in_progress:
            return
        self._action_in_progress = True
        if self.media_type == "video":
            if self.is_recording:
                self._stop_video_recording()
            else:
                self._start_video_recording(target_win)
        else:
            self._trigger_photo_capture(target_win)

    def _crop_from_bg(self, rect, dest_path: str) -> bool:
        if not self.bg_path or not os.path.isfile(self.bg_path):
            return False
        try:
            src = cairo.ImageSurface.create_from_png(self.bg_path)
            img_w, img_h = src.get_width(), src.get_height()
            if rect is None:
                shutil.copyfile(self.bg_path, dest_path)
                return os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0

            win_w = float(self.get_width() or img_w)
            win_h = float(self.get_height() or img_h)
            sx = img_w / win_w
            sy = img_h / win_h
            rx, ry, rw, rh = rect
            ix = max(0, min(img_w - 1, int(round(rx * sx))))
            iy = max(0, min(img_h - 1, int(round(ry * sy))))
            iw = max(1, min(img_w - ix, int(round(rw * sx))))
            ih = max(1, min(img_h - iy, int(round(rh * sy))))

            out = cairo.ImageSurface(cairo.FORMAT_ARGB32, iw, ih)
            ctx = cairo.Context(out)
            ctx.set_source_surface(src, -ix, -iy)
            ctx.paint()
            out.write_to_png(dest_path)
            return os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0
        except Exception as e:
            print(f"[sadeem-capture] Background crop fallback failed: {e}", file=sys.stderr)
            return False

    def _trigger_photo_capture(self, target_win=None):
        # Fast path: when cursor & halo are disabled and we already froze the screen
        if (
            not self.cursor_enabled
            and not self.halo_enabled
            and self.bg_path
            and os.path.isfile(self.bg_path)
            and self.mode in ("selection", "screen")
            and target_win is None
        ):
            dest_path = generate_screenshot_path()
            rect = (self.sel_x, self.sel_y, self.sel_w, self.sel_h) if (self.mode == "selection" and self.sel_w > 4 and self.sel_h > 4) else None
            self.set_visible(False)
            if self._crop_from_bg(rect, dest_path):
                copy_file_to_clipboard(dest_path)
                launch_gallery_editor(dest_path)
                self._finish_session()
                return

        self.set_visible(False)
        GLib.timeout_add(80, self._execute_photo_capture, target_win)

    def _execute_photo_capture(self, target_win=None):
        dest_path = generate_screenshot_path()
        success = False
        try:
            if self.halo_enabled:
                self.client.set_halo_active(True)

            if target_win:
                wid = target_win.get("id", 0)
                success = self.client.capture_window(wid, True, self.cursor_enabled, dest_path)
                if not success:
                    rect = (
                        target_win.get("x", 0),
                        target_win.get("y", 0),
                        target_win.get("width", 0),
                        target_win.get("height", 0),
                    )
                    success = self._crop_from_bg(rect, dest_path)
            elif self.mode == "selection" and self.sel_w > 4 and self.sel_h > 4:
                success = self.client.capture_area(
                    int(round(self.sel_x)),
                    int(round(self.sel_y)),
                    int(round(self.sel_w)),
                    int(round(self.sel_h)),
                    self.cursor_enabled,
                    dest_path,
                )
                if not success:
                    success = self._crop_from_bg((self.sel_x, self.sel_y, self.sel_w, self.sel_h), dest_path)
            elif self.mode == "window" and self.hovered_window:
                wid = self.hovered_window.get("id", 0)
                success = self.client.capture_window(wid, True, self.cursor_enabled, dest_path)
                if not success:
                    rect = (
                        self.hovered_window.get("x", 0),
                        self.hovered_window.get("y", 0),
                        self.hovered_window.get("width", 0),
                        self.hovered_window.get("height", 0),
                    )
                    success = self._crop_from_bg(rect, dest_path)
            else:
                success = self.client.capture_screen(self.cursor_enabled, dest_path)
                if not success:
                    success = self._crop_from_bg(None, dest_path)
        except Exception as e:
            print(f"[sadeem-capture] Photo capture error: {e}", file=sys.stderr)
        finally:
            if self.halo_enabled:
                self.client.set_halo_active(False)

        if success and os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
            copy_file_to_clipboard(dest_path)
            launch_gallery_editor(dest_path)
        else:
            _send_notification(self.app, "sadeem-capture-err", t("app_name"), t("error_capture_failed"), "dialog-error-symbolic")

        self._finish_session()
        return GLib.SOURCE_REMOVE

    # --- Video Pipeline (Lazy-loaded GStreamer) ---
    def _start_video_recording(self, target_win=None):
        self.set_visible(False)
        GLib.timeout_add(90, self._do_start_video, target_win)

    def _do_start_video(self, target_win=None):
        try:
            from capture.video_recorder import VideoRecorder

            if self.audio_system_enabled and self.audio_mic_enabled:
                a_mode = "both"
            elif self.audio_system_enabled:
                a_mode = "system"
            elif self.audio_mic_enabled:
                a_mode = "mic"
            else:
                a_mode = "none"

            crop_box = None
            if self.mode == "selection" and self.sel_w > 4 and self.sel_h > 4:
                crop_box = (self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            elif self.mode == "window":
                win = target_win or self.hovered_window
                if win:
                    crop_box = (
                        win.get("x", 0),
                        win.get("y", 0),
                        win.get("width", 1280),
                        win.get("height", 720),
                    )

            scale = self.get_scale_factor() or 1.0
            width = self.get_width() or 1920
            height = self.get_height() or 1080

            self.recorder = VideoRecorder(
                mode=self.mode,
                crop_box=crop_box,
                screen_size=(width, height),
                scale_factor=scale,
                resolution=self.video_resolution,
                framerate=self.video_framerate,
                codec=self.video_codec,
                audio_mode=a_mode,
                microphone_id=self.selected_mic_id,
                cursor_enabled=self.cursor_enabled,
                halo_enabled=self.halo_enabled,
                capture_client=self.client,
                on_stream_ended=self._on_recorder_stream_ended,
            )
            if not self.recorder.start():
                _send_notification(self.app, "sadeem-rec-err", t("app_name"), t("error_rec_start_failed"), "dialog-error-symbolic")
                self._finish_session()
                return GLib.SOURCE_REMOVE

            self._cleanup_bg()
            self.is_recording = True
            self._action_in_progress = False
            self._stop_sig_id = self.client.subscribe_stop_recording(lambda: GLib.idle_add(self._stop_video_recording))
            self._silent_sig_id = self.client.subscribe_silent_screenshot(lambda: GLib.idle_add(self._take_silent_screenshot))
        except Exception as e:
            print(f"[sadeem-capture] Video start error: {e}", file=sys.stderr)
            _send_notification(self.app, "sadeem-rec-err", t("app_name"), t("error_rec_start_failed"), "dialog-error-symbolic")
            self._finish_session()
        return GLib.SOURCE_REMOVE

    def _on_recorder_stream_ended(self, err=None):
        if self.is_recording:
            GLib.idle_add(self._stop_video_recording)

    def _take_silent_screenshot(self):
        if not self.is_recording:
            return False
        dest_path = generate_screenshot_path()
        if self.mode == "selection" and self.sel_w > 4 and self.sel_h > 4:
            ok = self.client.capture_area(
                int(round(self.sel_x)),
                int(round(self.sel_y)),
                int(round(self.sel_w)),
                int(round(self.sel_h)),
                self.cursor_enabled,
                dest_path,
            )
        else:
            ok = self.client.capture_screen(self.cursor_enabled, dest_path)

        if ok and os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
            copy_file_to_clipboard(dest_path)
            self.client.flash_camera_indicator()
            if shutil.which("canberra-gtk-play"):
                try:
                    subprocess.Popen(
                        ["canberra-gtk-play", "-i", "camera-shutter"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except Exception:
                    pass
        return False

    def _stop_video_recording(self):
        if not self.is_recording or not self.recorder:
            self._finish_session()
            return False

        self.client.unsubscribe(self._stop_sig_id)
        self.client.unsubscribe(self._silent_sig_id)
        self._stop_sig_id = None
        self._silent_sig_id = None

        success, path, size, _duration = self.recorder.stop()
        self.recorder = None
        self.is_recording = False

        if success and os.path.isfile(path) and size > 0:
            body = t("notif_recorded_body", size=format_file_size(size), path=path)
            _send_notification(self.app, "sadeem-video-saved", t("notif_recorded_title"), body, "video-x-generic")
            launch_gallery_editor(path)

        self._finish_session()
        return False


class SadeemCaptureApp(Adw.Application):
    def __init__(self, daemon_mode=False, standalone=False):
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if standalone:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        self._daemon_mode = daemon_mode
        self._styles_loaded = False
        self.client = CaptureClient()
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_styles()
        if self._daemon_mode:
            self.hold()

    def _load_styles(self):
        if self._styles_loaded:
            return
        if i18n.is_rtl():
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        else:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)

        display = Gdk.Display.get_default()
        if display:
            provider = Gtk.CssProvider()
            provider.load_from_string(CAPTURE_CSS)
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self._styles_loaded = True

    def _take_background_snapshot(self):
        runtime_dir = GLib.get_user_runtime_dir() or GLib.get_user_cache_dir()
        bg_path = os.path.join(runtime_dir, f"sadeem_capture_bg_{os.getpid()}.png")
        try:
            if self.client.capture_screen(False, bg_path):
                return bg_path
        except Exception as e:
            print(f"[sadeem-capture] Background snapshot failed: {e}", file=sys.stderr)
        return None

    def close_capture_session(self, win):
        if win is not None:
            win._cleanup_bg()
            try:
                win.close()
            except Exception:
                pass
        if self.window is win:
            self.window = None
        if not self._daemon_mode:
            self.quit()

    def _open_window(self, initial_mode="selection", initial_media="photo"):
        if self.window and getattr(self.window, "is_recording", False):
            self.window._take_silent_screenshot()
            return

        if self.window is not None:
            self.close_capture_session(self.window)

        self._load_styles()
        bg_path = self._take_background_snapshot()
        self.window = SadeemCaptureWindow(
            self,
            initial_mode=initial_mode,
            initial_media=initial_media,
            bg_path=bg_path,
        )
        self.window.fullscreen()
        self.window.present()

    def do_activate(self):
        self._open_window()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]

        if "--daemon" in args:
            return 0

        if "--stop-recording" in args:
            if self.window and getattr(self.window, "is_recording", False):
                self.window._stop_video_recording()
            return 0

        if self.window and getattr(self.window, "is_recording", False):
            self.window._take_silent_screenshot()
            return 0

        if "--window-id" in args:
            idx = args.index("--window-id")
            if idx + 1 < len(args):
                try:
                    wid = int(args[idx + 1])
                    dest = generate_screenshot_path()
                    if self.client.capture_window(wid, True, False, dest):
                        copy_file_to_clipboard(dest)
                        launch_gallery_editor(dest)
                        return 0
                except Exception as e:
                    print(f"[sadeem-capture] --window-id error: {e}", file=sys.stderr)
                    return 1

        initial_mode = "selection"
        initial_media = "photo"
        if "--video" in args:
            initial_media = "video"
        if "--screen" in args:
            initial_mode = "screen"
        elif "--window" in args:
            initial_mode = "window"
        elif "--area" in args or "--selection" in args:
            initial_mode = "selection"

        self._open_window(initial_mode=initial_mode, initial_media=initial_media)
        return 0


def main():
    if "--window-id" in sys.argv:
        try:
            idx = sys.argv.index("--window-id")
            if idx + 1 < len(sys.argv):
                wid = int(sys.argv[idx + 1])
                client = CaptureClient()
                dest = generate_screenshot_path()
                if client.capture_window(wid, True, False, dest):
                    copy_file_to_clipboard(dest)
                    launch_gallery_editor(dest)
                    return 0
                return 1
        except Exception as exc:
            print(f"[sadeem-capture] CLI error: {exc}", file=sys.stderr)
            return 1

    daemon_mode = "--daemon" in sys.argv
    standalone = "--standalone" in sys.argv or "--test" in sys.argv

    # Never claim the D-Bus name in daemon mode if the graphical display isn't ready yet
    if daemon_mode and not Gtk.init_check():
        print("[sadeem-capture] Graphical display not ready; exiting daemon for retry.", file=sys.stderr)
        return 1

    GLib.set_prgname(APP_ID)
    app = SadeemCaptureApp(daemon_mode=daemon_mode, standalone=standalone)
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
