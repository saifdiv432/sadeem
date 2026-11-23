#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Capture — أداة لقطة وتسجيل سديم الموحدة
GTK 4 / Libadwaita screen capture & video recording tool for Sadeem OS.
Integrates ScreenCast Portal + PipeWire + GStreamer with hardware acceleration,
cursor halo highlights, top panel live recording status, and sadeem-gallery handoff.
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
    background-color: rgba(28, 28, 35, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 9999px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.55);
    padding: 8px 18px;
    margin-top: 36px;
}
.sadeem-top-pill-label {
    color: #f1f5f9;
    font-size: 13px;
    font-weight: 500;
}
.sadeem-toolbar-card {
    background-color: rgba(30, 30, 35, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 24px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.60);
    padding: 14px 18px;
    margin-bottom: 32px;
}
.sadeem-pill-group {
    background-color: rgba(0, 0, 0, 0.4);
    border-radius: 9999px;
    padding: 3px;
    border: 1px solid rgba(255, 255, 255, 0.08);
}
.sadeem-mode-btn {
    background-color: transparent;
    background-image: none;
    border-radius: 14px;
    border: 1px solid transparent;
    color: #94a3b8;
    padding: 8px 18px;
    font-size: 12px;
    font-weight: 500;
}
.sadeem-mode-btn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}
.sadeem-mode-btn.active {
    background-color: rgba(255, 255, 255, 0.16);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.12);
}
.sadeem-mode-btn.active:hover {
    background-color: rgba(255, 255, 255, 0.20);
}
.sadeem-tool-btn {
    background-color: rgba(255, 255, 255, 0.08);
    background-image: none;
    border-radius: 9999px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: #cbd5e1;
    min-width: 36px;
    min-height: 36px;
    padding: 0;
    margin: 0;
}
.sadeem-tool-btn:hover {
    background-color: rgba(255, 255, 255, 0.15);
    color: #ffffff;
}
.sadeem-tool-btn.active {
    background-color: rgba(255, 255, 255, 0.22);
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.25);
}
.sadeem-tool-btn.active:hover {
    background-color: rgba(255, 255, 255, 0.28);
}
.sadeem-tool-btn.active-blue {
    background-color: #0284c7;
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.3);
}
.sadeem-tool-btn:disabled {
    opacity: 0.3;
}
.sadeem-shutter-btn {
    background-color: #7a1c33;
    background-image: none;
    border-radius: 9999px;
    border: 3px solid #ffffff;
    min-width: 52px;
    min-height: 52px;
    color: #ffffff;
    box-shadow: 0 0 14px rgba(122, 28, 51, 0.6);
    padding: 0;
    margin: 0;
}
.sadeem-shutter-btn:hover {
    background-color: #8c223c;
}
.sadeem-shutter-btn:active {
    background-color: #631528;
}
.sadeem-shutter-btn-record {
    background-color: #e01b24;
    background-image: none;
    border-radius: 9999px;
    border: 3px solid #ffffff;
    min-width: 52px;
    min-height: 52px;
    color: #ffffff;
    box-shadow: 0 0 16px rgba(224, 27, 36, 0.7);
    padding: 0;
    margin: 0;
}
.sadeem-shutter-btn-record:hover {
    background-color: #ef4444;
}
.sadeem-shutter-btn-record:active {
    background-color: #b91c1c;
}
.sadeem-close-btn {
    background-color: rgba(255, 255, 255, 0.08);
    background-image: none;
    border-radius: 9999px;
    border: none;
    color: #cbd5e1;
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    margin: 0;
}
.sadeem-close-btn:hover {
    background-color: rgba(255, 255, 255, 0.16);
    color: #ffffff;
}
.sadeem-warning-banner {
    background-color: rgba(180, 83, 9, 0.95);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 9999px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    padding: 8px 18px;
}
.sadeem-warning-label {
    color: #fef3c7;
    font-size: 13px;
    font-weight: 500;
}
.sadeem-media-toggle {
    background-color: rgba(255, 255, 255, 0.07);
    border-radius: 9999px;
    padding: 3px;
}
.sadeem-media-btn {
    background-color: transparent;
    background-image: none;
    border-radius: 9999px;
    border: none;
    color: #cbd5e1;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
}
.sadeem-media-btn:hover {
    color: #ffffff;
}
.sadeem-media-btn.active {
    background-color: rgba(255, 255, 255, 0.18);
    color: #ffffff;
}
.sadeem-popover-box {
    background-color: #1e1e24;
    padding: 12px;
    border-radius: 12px;
    color: #f1f5f9;
}
"""


def format_file_size(num_bytes: int) -> str:
    """Formats file size into human-readable string."""
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


class SadeemCaptureWindow(Gtk.Window):
    def __init__(self, app, initial_mode="selection", bg_path=None):
        super().__init__(application=app)
        self.app = app
        self.client = app.client
        self.mode = initial_mode  # "selection", "screen", "window"
        self.cursor_enabled = True
        self.halo_enabled = False
        self.media_type = "photo"  # "photo" or "video"

        # Background snapshot for frozen desktop presentation on Wayland
        self.bg_path = bg_path

        self.connect("destroy", lambda _w: self._cleanup_bg())

        # Video recording settings
        self.video_resolution = "native"  # "native", "1080p", "720p"
        self.video_framerate = 30  # 30 or 60
        self.video_codec = "h264"  # "h264" or "h265"
        self.audio_system_enabled = True
        self.audio_mic_enabled = False

        # Lazy microphone initialization
        self.available_mics = []
        self.selected_mic_id = "@DEFAULT_SOURCE@"
        self._mics_loaded = False

        # Active recorder instance
        self.recorder = None
        self.is_recording = False
        self._stop_sig_id = None
        self._silent_sig_id = None

        # Coordinates for selection box
        self.sel_x = 0
        self.sel_y = 0
        self.sel_w = 0
        self.sel_h = 0
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0

        # Window list for window mode
        self.windows = []
        self.hovered_window = None

        # Pointer position
        self.pointer_x = 0
        self.pointer_y = 0

        self.set_title(t("app_name"))
        self.add_css_class("sadeem-capture-window")
        self.set_decorated(False)

        self._build_ui()
        self._setup_events()

    def _build_ui(self):
        self.overlay = Gtk.Overlay()

        # 1. Background Picture layer (GPU-accelerated via Gdk.Texture)
        self.bg_picture = Gtk.Picture()
        self.bg_picture.set_content_fit(Gtk.ContentFit.FILL)
        self.bg_picture.set_can_target(False)
        if self.bg_path and os.path.exists(self.bg_path):
            try:
                texture = Gdk.Texture.new_from_filename(self.bg_path)
                self.bg_picture.set_paintable(texture)
            except Exception as e:
                print(f"[sadeem-capture] Error loading background texture: {e}", file=sys.stderr)
        self.overlay.set_child(self.bg_picture)

        # 2. Canvas drawing area overlay layer
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_vexpand(True)
        self.drawing_area.set_draw_func(self._on_draw)
        self.overlay.add_overlay(self.drawing_area)

        # 3. Toast overlay wraps overlay from the outside (never blocks child clicks)
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.overlay)
        self.set_child(self.toast_overlay)

        # Top Floating Instruction Pill
        self.top_pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.top_pill.set_halign(Gtk.Align.CENTER)
        self.top_pill.set_valign(Gtk.Align.START)
        self.top_pill.set_margin_top(42)
        self.top_pill.set_can_target(False)
        self.top_pill.add_css_class("sadeem-top-pill")

        self.top_pill_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        self.top_pill.append(self.top_pill_icon)

        self.top_pill_label = Gtk.Label()
        self.top_pill_label.add_css_class("sadeem-top-pill-label")
        self.top_pill.append(self.top_pill_label)

        self.overlay.add_overlay(self.top_pill)

        # Prominent warning banner if background capture failed / extension disabled
        if not self.bg_path or not os.path.exists(self.bg_path):
            self.warning_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            self.warning_banner.set_halign(Gtk.Align.CENTER)
            self.warning_banner.set_valign(Gtk.Align.START)
            self.warning_banner.set_margin_top(92)
            self.warning_banner.set_can_target(False)
            self.warning_banner.add_css_class("sadeem-warning-banner")

            warn_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            self.warning_banner.append(warn_icon)

            warn_lbl = Gtk.Label(label=t("helper_disabled_warning"))
            warn_lbl.add_css_class("sadeem-warning-label")
            self.warning_banner.append(warn_lbl)

            self.overlay.add_overlay(self.warning_banner)

        # 4. Floating Bottom Toolbar Card
        self.toolbar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toolbar_box.set_halign(Gtk.Align.CENTER)
        self.toolbar_box.set_valign(Gtk.Align.END)
        self.toolbar_box.set_margin_bottom(32)
        self.toolbar_box.add_css_class("sadeem-toolbar-card")

        # Card Overlay to place close button in corner
        self.card_overlay = Gtk.Overlay()

        # Vertical content container
        card_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Row 1: Mode Switcher (Selection, Screen, Window)
        row_modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_modes.set_homogeneous(True)
        row_modes.set_halign(Gtk.Align.CENTER)
        row_modes.set_margin_start(28)
        row_modes.set_margin_end(28)

        def make_mode_btn(icon_name, text_label, mode_id):
            btn = Gtk.Button()
            btn.add_css_class("sadeem-mode-btn")
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            vbox.set_halign(Gtk.Align.CENTER)
            vbox.set_valign(Gtk.Align.CENTER)
            img = Gtk.Image.new_from_icon_name(icon_name)
            img.set_pixel_size(20)
            lbl = Gtk.Label(label=text_label)
            vbox.append(img)
            vbox.append(lbl)
            btn.set_child(vbox)
            btn.connect("clicked", lambda _b: self._set_mode(mode_id))
            return btn

        self.btn_mode_sel = make_mode_btn("edit-select-all-symbolic", t("mode_selection"), "selection")
        self.btn_mode_screen = make_mode_btn("video-display-symbolic", t("mode_screen"), "screen")
        self.btn_mode_win = make_mode_btn("preferences-system-windows-symbolic", t("mode_window"), "window")

        row_modes.append(self.btn_mode_sel)
        row_modes.append(self.btn_mode_screen)
        row_modes.append(self.btn_mode_win)
        card_content.append(row_modes)

        # Row 2: Controls with mathematically centered shutter button
        row_controls = Gtk.CenterBox()
        row_controls.set_halign(Gtk.Align.FILL)
        row_controls.set_valign(Gtk.Align.CENTER)

        # Start widget: Photo / Video pill switch
        media_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        media_box.add_css_class("sadeem-media-toggle")
        media_box.set_halign(Gtk.Align.START)
        media_box.set_valign(Gtk.Align.CENTER)

        def make_media_btn(icon_name, text_label):
            btn = Gtk.Button()
            btn.add_css_class("sadeem-media-btn")
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hbox.set_halign(Gtk.Align.CENTER)
            hbox.set_valign(Gtk.Align.CENTER)
            img = Gtk.Image.new_from_icon_name(icon_name)
            img.set_pixel_size(16)
            lbl = Gtk.Label(label=text_label)
            hbox.append(img)
            hbox.append(lbl)
            btn.set_child(hbox)
            return btn

        self.btn_photo = make_media_btn("camera-photo-symbolic", t("tab_photo"))
        self.btn_photo.add_css_class("active")
        self.btn_photo.connect("clicked", lambda _b: self._set_media_type("photo"))

        self.btn_video = make_media_btn("media-record-symbolic", t("tab_video"))
        self.btn_video.connect("clicked", lambda _b: self._set_media_type("video"))

        media_box.append(self.btn_photo)
        media_box.append(self.btn_video)
        row_controls.set_start_widget(media_box)

        # Center widget: Circular Shutter Button
        self.btn_shutter = Gtk.Button()
        self.btn_shutter.set_icon_name("camera-photo-symbolic")
        self.btn_shutter.set_tooltip_text(t("btn_capture"))
        self.btn_shutter.add_css_class("sadeem-shutter-btn")
        self.btn_shutter.set_size_request(52, 52)
        self.btn_shutter.set_halign(Gtk.Align.CENTER)
        self.btn_shutter.set_valign(Gtk.Align.CENTER)
        self.btn_shutter.set_hexpand(False)
        self.btn_shutter.set_vexpand(False)
        self.btn_shutter.connect("clicked", lambda _b: self._trigger_action())
        row_controls.set_center_widget(self.btn_shutter)

        # End widget: Secondary Tool Buttons
        tools_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tools_box.set_halign(Gtk.Align.END)
        tools_box.set_valign(Gtk.Align.CENTER)

        # Cursor Toggle
        self.btn_cursor = Gtk.Button()
        self.btn_cursor.set_icon_name("input-mouse-symbolic")
        self.btn_cursor.set_tooltip_text(t("tooltip_cursor"))
        self.btn_cursor.add_css_class("sadeem-tool-btn")
        self.btn_cursor.add_css_class("active")
        self.btn_cursor.set_size_request(36, 36)
        self.btn_cursor.set_halign(Gtk.Align.CENTER)
        self.btn_cursor.set_valign(Gtk.Align.CENTER)
        self.btn_cursor.connect("clicked", self._toggle_cursor)
        tools_box.append(self.btn_cursor)

        # Cursor Halo Toggle
        self.btn_halo = Gtk.Button()
        self.btn_halo.set_icon_name("find-location-symbolic")
        self.btn_halo.set_tooltip_text(t("tooltip_halo"))
        self.btn_halo.add_css_class("sadeem-tool-btn")
        self.btn_halo.set_size_request(36, 36)
        self.btn_halo.set_halign(Gtk.Align.CENTER)
        self.btn_halo.set_valign(Gtk.Align.CENTER)
        self.btn_halo.connect("clicked", self._toggle_halo)
        tools_box.append(self.btn_halo)

        # Video-specific quick toggles (Mic, System Audio, Settings popover)
        self.btn_quick_sys_audio = Gtk.Button()
        self.btn_quick_sys_audio.set_icon_name("audio-volume-high-symbolic")
        self.btn_quick_sys_audio.set_tooltip_text(t("audio_system"))
        self.btn_quick_sys_audio.add_css_class("sadeem-tool-btn")
        self.btn_quick_sys_audio.add_css_class("active-blue")
        self.btn_quick_sys_audio.set_size_request(36, 36)
        self.btn_quick_sys_audio.set_halign(Gtk.Align.CENTER)
        self.btn_quick_sys_audio.set_valign(Gtk.Align.CENTER)
        self.btn_quick_sys_audio.set_visible(False)
        self.btn_quick_sys_audio.connect("clicked", self._toggle_quick_sys_audio)
        tools_box.append(self.btn_quick_sys_audio)

        self.btn_quick_mic = Gtk.Button()
        self.btn_quick_mic.set_icon_name("audio-input-microphone-symbolic")
        self.btn_quick_mic.set_tooltip_text(t("audio_mic"))
        self.btn_quick_mic.add_css_class("sadeem-tool-btn")
        self.btn_quick_mic.set_size_request(36, 36)
        self.btn_quick_mic.set_halign(Gtk.Align.CENTER)
        self.btn_quick_mic.set_valign(Gtk.Align.CENTER)
        self.btn_quick_mic.set_visible(False)
        self.btn_quick_mic.connect("clicked", self._toggle_quick_mic)
        tools_box.append(self.btn_quick_mic)

        self.btn_video_settings = Gtk.MenuButton()
        self.btn_video_settings.set_icon_name("emblem-system-symbolic")
        self.btn_video_settings.add_css_class("sadeem-tool-btn")
        self.btn_video_settings.set_size_request(36, 36)
        self.btn_video_settings.set_halign(Gtk.Align.CENTER)
        self.btn_video_settings.set_valign(Gtk.Align.CENTER)
        self.btn_video_settings.set_visible(False)
        self._build_video_settings_popover()
        tools_box.append(self.btn_video_settings)

        row_controls.set_end_widget(tools_box)
        card_content.append(row_controls)

        self.card_overlay.set_child(card_content)

        # Close button in top-end corner
        self.btn_close = Gtk.Button()
        self.btn_close.set_icon_name("window-close-symbolic")
        self.btn_close.set_tooltip_text(t("tooltip_close"))
        self.btn_close.add_css_class("sadeem-close-btn")
        self.btn_close.set_size_request(28, 28)
        self.btn_close.set_halign(Gtk.Align.END)
        self.btn_close.set_valign(Gtk.Align.START)
        self.btn_close.set_margin_top(2)
        self.btn_close.set_margin_end(2)
        self.btn_close.connect("clicked", lambda _b: self._close_or_quit())
        self.card_overlay.add_overlay(self.btn_close)

        self.toolbar_box.append(self.card_overlay)
        self.overlay.add_overlay(self.toolbar_box)

        self._update_mode_ui()

    def _build_video_settings_popover(self):
        """Constructs compact video recording settings popover."""
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("sadeem-popover-box")

        # 1. Resolution row
        lbl_res = Gtk.Label(label=t("res_native"), halign=Gtk.Align.START)
        lbl_res.add_css_class("caption-heading")
        box.append(lbl_res)

        res_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        res_box.add_css_class("sadeem-pill-group")

        self.btn_res_native = Gtk.Button(label=t("res_native"))
        self.btn_res_native.add_css_class("sadeem-mode-btn")
        self.btn_res_native.add_css_class("active")
        self.btn_res_native.connect("clicked", lambda _b: self._set_resolution("native"))

        self.btn_res_1080p = Gtk.Button(label="1080p")
        self.btn_res_1080p.add_css_class("sadeem-mode-btn")
        self.btn_res_1080p.connect("clicked", lambda _b: self._set_resolution("1080p"))

        self.btn_res_720p = Gtk.Button(label="720p")
        self.btn_res_720p.add_css_class("sadeem-mode-btn")
        self.btn_res_720p.connect("clicked", lambda _b: self._set_resolution("720p"))

        res_box.append(self.btn_res_native)
        res_box.append(self.btn_res_1080p)
        res_box.append(self.btn_res_720p)
        box.append(res_box)

        # 2. Framerate & Codec row
        row_fc = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Framerate
        fps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        fps_box.add_css_class("sadeem-pill-group")

        self.btn_fps_30 = Gtk.Button(label=t("fps_30"))
        self.btn_fps_30.add_css_class("sadeem-mode-btn")
        self.btn_fps_30.add_css_class("active")
        self.btn_fps_30.connect("clicked", lambda _b: self._set_fps(30))

        self.btn_fps_60 = Gtk.Button(label=t("fps_60"))
        self.btn_fps_60.add_css_class("sadeem-mode-btn")
        self.btn_fps_60.connect("clicked", lambda _b: self._set_fps(60))

        fps_box.append(self.btn_fps_30)
        fps_box.append(self.btn_fps_60)
        row_fc.append(fps_box)

        # Codec
        codec_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        codec_box.add_css_class("sadeem-pill-group")

        self.btn_codec_h264 = Gtk.Button(label="H.264")
        self.btn_codec_h264.add_css_class("sadeem-mode-btn")
        self.btn_codec_h264.add_css_class("active")
        self.btn_codec_h264.connect("clicked", lambda _b: self._set_codec("h264"))

        self.btn_codec_h265 = Gtk.Button(label="H.265")
        self.btn_codec_h265.add_css_class("sadeem-mode-btn")
        self.btn_codec_h265.connect("clicked", lambda _b: self._set_codec("h265"))

        codec_box.append(self.btn_codec_h264)
        codec_box.append(self.btn_codec_h265)
        row_fc.append(codec_box)

        box.append(row_fc)

        # 3. Audio Device Dropdown container
        self.mic_dropdown_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(self.mic_dropdown_box)
        self._update_mic_dropdown()

        # 4. Keyboard Shortcuts Hint
        lbl_hint = Gtk.Label(label=t("hint_recording_shortcuts"), halign=Gtk.Align.CENTER)
        lbl_hint.set_wrap(True)
        lbl_hint.set_justify(Gtk.Justification.CENTER)
        lbl_hint.add_css_class("caption")
        lbl_hint.add_css_class("dim-label")
        lbl_hint.set_margin_top(6)
        box.append(lbl_hint)

        popover.set_child(box)
        self.btn_video_settings.set_popover(popover)

    def _async_load_microphones(self):
        """Asynchronously probes connected microphones in background thread."""
        threading.Thread(target=self._probe_mics_thread, daemon=True).start()

    def _probe_mics_thread(self):
        try:
            from capture.media_probe import get_connected_microphones
            mics = get_connected_microphones()
            GLib.idle_add(self._on_microphones_loaded, mics)
        except Exception as e:
            print(f"[sadeem-capture] Failed to probe microphones: {e}", file=sys.stderr)

    def _on_microphones_loaded(self, mics):
        self.available_mics = mics or []
        if self.available_mics and (not self.selected_mic_id or self.selected_mic_id == "@DEFAULT_SOURCE@"):
            self.selected_mic_id = self.available_mics[0]["id"]
        self._update_mic_dropdown()
        return GLib.SOURCE_REMOVE

    def _update_mic_dropdown(self):
        if not hasattr(self, "mic_dropdown_box"):
            return
        child = self.mic_dropdown_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.mic_dropdown_box.remove(child)
            child = next_child

        if self.available_mics:
            lbl_mic_dev = Gtk.Label(label=t("audio_device"), halign=Gtk.Align.START)
            lbl_mic_dev.add_css_class("caption-heading")
            self.mic_dropdown_box.append(lbl_mic_dev)

            names = [m["name"] for m in self.available_mics]
            str_list = Gtk.StringList.new(names)
            drop_mic = Gtk.DropDown.new(str_list, None)
            drop_mic.connect("notify::selected", self._on_mic_selected)
            self.mic_dropdown_box.append(drop_mic)

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

        self.drag_gesture = Gtk.GestureDrag()
        self.drag_gesture.connect("drag-begin", self._on_drag_begin)
        self.drag_gesture.connect("drag-update", self._on_drag_update)
        self.drag_gesture.connect("drag-end", self._on_drag_end)
        self.drawing_area.add_controller(self.drag_gesture)

        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", self._on_click_released)
        self.drawing_area.add_controller(click_gesture)

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self.is_recording:
                self._stop_video_recording()
            else:
                self._close_or_quit()
            return True
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._trigger_action()
            return True
        elif keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
            self._set_mode("selection")
            return True
        elif keyval in (Gdk.KEY_2, Gdk.KEY_KP_2):
            self._set_mode("screen")
            return True
        elif keyval in (Gdk.KEY_3, Gdk.KEY_KP_3):
            self._set_mode("window")
            return True
        elif keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self._toggle_cursor()
            return True
        elif keyval in (Gdk.KEY_h, Gdk.KEY_H):
            if self.btn_halo.get_sensitive():
                self._toggle_halo()
            return True
        return False

    def _set_mode(self, new_mode):
        self.mode = new_mode
        self._update_mode_ui()
        if self.mode == "window":
            self.windows = self.client.list_windows()
        self.drawing_area.queue_draw()

    def _cleanup_bg(self):
        if hasattr(self, "bg_picture") and self.bg_picture:
            self.bg_picture.set_paintable(None)
        if self.bg_path and os.path.exists(self.bg_path):
            try:
                os.remove(self.bg_path)
            except Exception:
                pass
        self.bg_path = None

    def _close_or_quit(self):
        self.set_visible(False)
        self._cleanup_bg()
        self.close()
        self.app.window = None
        if not getattr(self.app, "is_daemon", False):
            self.app.quit()

    def _send_error_notification(self, title, msg):
        try:
            notif = Gio.Notification.new(title)
            notif.set_body(msg)
            notif.set_icon(Gio.ThemedIcon.new("dialog-error-symbolic"))
            self.app.send_notification("sadeem-capture-error", notif)
        except Exception:
            pass
        if shutil.which("notify-send"):
            try:
                subprocess.run(
                    ["notify-send", "-a", "Sadeem Capture", "-i", "dialog-error-symbolic", title, msg],
                    check=False,
                )
            except Exception:
                pass

    def _update_top_pill(self):
        if not hasattr(self, "top_pill") or not self.top_pill:
            return
        if self.mode == "selection":
            if self.sel_w > 4 and self.sel_h > 4:
                self.top_pill_label.set_text(f"{t('mode_selection')} — {int(self.sel_w)} × {int(self.sel_h)} px")
                self.top_pill_icon.set_from_icon_name("edit-select-all-symbolic")
            else:
                self.top_pill_label.set_text(t("select_hint"))
                self.top_pill_icon.set_from_icon_name("edit-select-all-symbolic")
        elif self.mode == "screen":
            screen_txt = t("screen_hint") if "screen_hint" in i18n.STRINGS.get(i18n.LANG, {}) else t("mode_screen")
            self.top_pill_label.set_text(screen_txt)
            self.top_pill_icon.set_from_icon_name("video-display-symbolic")
        elif self.mode == "window":
            if self.hovered_window:
                title = self.hovered_window.get("title") or self.hovered_window.get("appName") or ""
                self.top_pill_label.set_text(title if len(title) <= 50 else title[:47] + "...")
            else:
                self.top_pill_label.set_text(t("window_hint"))
            self.top_pill_icon.set_from_icon_name("preferences-system-windows-symbolic")

    def _update_mode_ui(self):
        self.btn_mode_sel.remove_css_class("active")
        self.btn_mode_screen.remove_css_class("active")
        self.btn_mode_win.remove_css_class("active")

        if self.mode == "selection":
            self.btn_mode_sel.add_css_class("active")
        elif self.mode == "screen":
            self.btn_mode_screen.add_css_class("active")
        elif self.mode == "window":
            self.btn_mode_win.add_css_class("active")

        # Halo rule: disabled in window mode or if cursor is disabled
        if self.mode == "window" or not self.cursor_enabled:
            self.btn_halo.set_sensitive(False)
            self.halo_enabled = False
            self.btn_halo.remove_css_class("active")
        else:
            self.btn_halo.set_sensitive(True)

        self._update_top_pill()

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
            self.btn_quick_mic.add_css_class("active-blue")
        else:
            self.btn_quick_mic.remove_css_class("active-blue")

    def _toggle_quick_sys_audio(self, *_a):
        self.audio_system_enabled = not self.audio_system_enabled
        if self.audio_system_enabled:
            self.btn_quick_sys_audio.add_css_class("active-blue")
        else:
            self.btn_quick_sys_audio.remove_css_class("active-blue")

    def _set_resolution(self, res):
        self.video_resolution = res
        self.btn_res_native.remove_css_class("active")
        self.btn_res_1080p.remove_css_class("active")
        self.btn_res_720p.remove_css_class("active")
        if res == "native":
            self.btn_res_native.add_css_class("active")
        elif res == "1080p":
            self.btn_res_1080p.add_css_class("active")
        elif res == "720p":
            self.btn_res_720p.add_css_class("active")

    def _set_fps(self, fps):
        self.video_framerate = fps
        self.btn_fps_30.remove_css_class("active")
        self.btn_fps_60.remove_css_class("active")
        if fps == 30:
            self.btn_fps_30.add_css_class("active")
        else:
            self.btn_fps_60.add_css_class("active")

    def _set_codec(self, codec):
        self.video_codec = codec
        self.btn_codec_h264.remove_css_class("active")
        self.btn_codec_h265.remove_css_class("active")
        if codec == "h264":
            self.btn_codec_h264.add_css_class("active")
        else:
            self.btn_codec_h265.add_css_class("active")

    def _set_media_type(self, mtype):
        self.media_type = mtype
        if mtype == "video":
            self.btn_photo.remove_css_class("active")
            self.btn_video.add_css_class("active")
            self.btn_quick_mic.set_visible(True)
            self.btn_quick_sys_audio.set_visible(True)
            self.btn_video_settings.set_visible(True)

            self.btn_shutter.remove_css_class("sadeem-shutter-btn")
            self.btn_shutter.add_css_class("sadeem-shutter-btn-record")
            self.btn_shutter.set_icon_name("media-record-symbolic")
            self.btn_shutter.set_tooltip_text(t("btn_record"))

            # Lazy load microphones on first switch to video mode
            if not self._mics_loaded:
                self._mics_loaded = True
                self._async_load_microphones()
        else:
            self.btn_photo.add_css_class("active")
            self.btn_video.remove_css_class("active")
            self.btn_quick_mic.set_visible(False)
            self.btn_quick_sys_audio.set_visible(False)
            self.btn_video_settings.set_visible(False)

            self.btn_shutter.remove_css_class("sadeem-shutter-btn-record")
            self.btn_shutter.add_css_class("sadeem-shutter-btn")
            self.btn_shutter.set_icon_name("camera-photo-symbolic")
            self.btn_shutter.set_tooltip_text(t("btn_capture"))

        self.drawing_area.queue_draw()

    # --- Mouse & Gestures Handling ---
    def _on_motion(self, _ctrl, x, y):
        self.pointer_x = x
        self.pointer_y = y
        if self.mode == "window":
            found = None
            for w in self.windows:
                wx = w.get("x", 0)
                wy = w.get("y", 0)
                ww = w.get("width", 0)
                wh = w.get("height", 0)
                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    found = w
                    break
            if found != self.hovered_window:
                self.hovered_window = found
                self._update_top_pill()
                self.drawing_area.queue_draw()

    def _on_drag_begin(self, _gesture, start_x, start_y):
        if self.mode != "selection":
            return
        self.is_dragging = True
        self.drag_start_x = start_x
        self.drag_start_y = start_y
        self.sel_x = start_x
        self.sel_y = start_y
        self.sel_w = 0
        self.sel_h = 0
        self._update_top_pill()
        self.drawing_area.queue_draw()

    def _on_drag_update(self, _gesture, offset_x, offset_y):
        if self.mode != "selection" or not self.is_dragging:
            return
        cur_x = self.drag_start_x + offset_x
        cur_y = self.drag_start_y + offset_y
        self.sel_x = min(self.drag_start_x, cur_x)
        self.sel_y = min(self.drag_start_y, cur_y)
        self.sel_w = abs(offset_x)
        self.sel_h = abs(offset_y)
        self._update_top_pill()
        self.drawing_area.queue_draw()

    def _on_drag_end(self, _gesture, _offset_x, _offset_y):
        if self.mode != "selection":
            return
        self.is_dragging = False
        self._update_top_pill()
        self.drawing_area.queue_draw()

    def _on_click_released(self, _gesture, n_press, x, y):
        tb_alloc = self.toolbar_box.get_allocation()
        if (
            tb_alloc.x <= x <= tb_alloc.x + tb_alloc.width
            and tb_alloc.y <= y <= tb_alloc.y + tb_alloc.height
        ):
            return

        if self.mode == "window" and self.hovered_window:
            self._trigger_action(target_win=self.hovered_window)
        elif self.mode == "screen":
            self._trigger_action()

    # --- Cairo Canvas Drawing (Zero Full-Screen CPU Blit) ---
    def _on_draw(self, _area, cr, width, height):
        # 1. Base translucent dimming layer
        if self.bg_path:
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.42)
        else:
            cr.set_source_rgba(0.08, 0.08, 0.12, 0.70)
        cr.paint()

        # 2. Cutouts & highlights according to active mode
        if self.mode == "selection":
            self._draw_selection(cr, width, height)
        elif self.mode == "screen":
            self._draw_screen_highlight(cr, width, height)
        elif self.mode == "window":
            self._draw_window_highlight(cr, width, height)

    def _draw_selection(self, cr, width, height):
        if self.sel_w > 4 and self.sel_h > 4:
            # Cut out selection rectangle to reveal crystal-clear bg_picture beneath
            cr.save()
            cr.rectangle(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.fill()
            cr.restore()

            accent_color = (0.88, 0.11, 0.14, 0.95) if self.media_type == "video" else (1.0, 1.0, 1.0, 0.90)
            cr.set_source_rgba(*accent_color)
            cr.set_line_width(2.0)
            cr.rectangle(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            cr.stroke()

            handles = [
                (self.sel_x, self.sel_y),
                (self.sel_x + self.sel_w / 2, self.sel_y),
                (self.sel_x + self.sel_w, self.sel_y),
                (self.sel_x, self.sel_y + self.sel_h / 2),
                (self.sel_x + self.sel_w, self.sel_y + self.sel_h / 2),
                (self.sel_x, self.sel_y + self.sel_h),
                (self.sel_x + self.sel_w / 2, self.sel_y + self.sel_h),
                (self.sel_x + self.sel_w, self.sel_y + self.sel_h),
            ]
            cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            for hx, hy in handles:
                cr.rectangle(hx - 3.5, hy - 3.5, 7.0, 7.0)
                cr.fill_preserve()
                cr.set_source_rgba(0.1, 0.1, 0.14, 0.9)
                cr.set_line_width(1.0)
                cr.stroke()
                cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)

            dim_str = f"{int(self.sel_w)} × {int(self.sel_h)}"
            layout = self.create_pango_layout(dim_str)
            layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 10"))
            _, log_rect = layout.get_pixel_extents()

            badge_w = log_rect.width + 16
            badge_h = 24
            badge_x = self.sel_x + 8
            badge_y = self.sel_y - 30 if self.sel_y > 36 else self.sel_y + self.sel_h + 8

            cr.set_source_rgba(0.09, 0.09, 0.12, 0.90)
            self._draw_rounded_rect(cr, badge_x, badge_y, badge_w, badge_h, 6)
            cr.fill_preserve()
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.20)
            cr.set_line_width(1.0)
            cr.stroke()

            cr.set_source_rgba(0.95, 0.96, 0.98, 1.0)
            cr.move_to(badge_x + 8, badge_y + (badge_h - log_rect.height) / 2)
            PangoCairo.show_layout(cr, layout)

    def _draw_screen_highlight(self, cr, width, height):
        cr.save()
        cr.rectangle(0, 0, width, height)
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.fill()
        cr.restore()

        accent = (0.88, 0.11, 0.14, 0.85) if self.media_type == "video" else (1.0, 1.0, 1.0, 0.85)
        cr.set_source_rgba(*accent)
        cr.set_line_width(3.0)
        cr.rectangle(3, 3, width - 6, height - 6)
        cr.stroke()

    def _draw_window_highlight(self, cr, width, height):
        if self.hovered_window:
            wx = self.hovered_window.get("x", 0)
            wy = self.hovered_window.get("y", 0)
            ww = self.hovered_window.get("width", 0)
            wh = self.hovered_window.get("height", 0)
            title = self.hovered_window.get("title") or self.hovered_window.get("appName") or ""

            cr.save()
            self._draw_rounded_rect(cr, wx, wy, ww, wh, 8)
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.fill()
            cr.restore()

            accent = (0.88, 0.11, 0.14, 0.95) if self.media_type == "video" else (1.0, 1.0, 1.0, 0.95)
            cr.set_source_rgba(*accent)
            cr.set_line_width(2.5)
            self._draw_rounded_rect(cr, wx, wy, ww, wh, 8)
            cr.stroke()

            if title:
                display_title = title if len(title) <= 45 else title[:42] + "..."
                layout = self.create_pango_layout(display_title)
                layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 10"))
                _, log_rect = layout.get_pixel_extents()

                badge_w = log_rect.width + 18
                badge_h = 26
                badge_x = wx + 12
                badge_y = wy + 12

                cr.set_source_rgba(0.09, 0.09, 0.12, 0.92)
                self._draw_rounded_rect(cr, badge_x, badge_y, badge_w, badge_h, 6)
                cr.fill_preserve()
                cr.set_source_rgba(*accent)
                cr.set_line_width(1.0)
                cr.stroke()

                cr.set_source_rgba(0.95, 0.96, 0.98, 1.0)
                cr.move_to(badge_x + 9, badge_y + (badge_h - log_rect.height) / 2)
                PangoCairo.show_layout(cr, layout)

    def _draw_rounded_rect(self, cr, x, y, w, h, r):
        deg = math.pi / 180.0
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -90 * deg, 0 * deg)
        cr.arc(x + w - r, y + h - r, r, 0 * deg, 90 * deg)
        cr.arc(x + r, y + h - r, r, 90 * deg, 180 * deg)
        cr.arc(x + r, y + r, r, 180 * deg, 270 * deg)
        cr.close_path()

    # --- Trigger Action: Photo vs Video ---
    def _trigger_action(self, target_win=None):
        if self.media_type == "video":
            if self.is_recording:
                self._stop_video_recording()
            else:
                self._start_video_recording(target_win)
        else:
            self._trigger_photo_capture(target_win)

    # --- Photo Pipeline ---
    def _trigger_photo_capture(self, target_win=None):
        self.set_visible(False)
        GLib.timeout_add(80, self._do_execute_photo_capture, target_win)

    def _do_execute_photo_capture(self, target_win=None):
        dest_path = generate_screenshot_path()

        if self.halo_enabled:
            try:
                self.client.set_halo_active(True)
            except Exception:
                pass

        success = False
        try:
            if target_win:
                win_id = target_win.get("id", 0)
                success = self.client.capture_window(win_id, True, self.cursor_enabled, dest_path)
            elif self.mode == "selection":
                if self.sel_w > 4 and self.sel_h > 4:
                    success = self.client.capture_area(
                        int(self.sel_x),
                        int(self.sel_y),
                        int(self.sel_w),
                        int(self.sel_h),
                        self.cursor_enabled,
                        dest_path,
                    )
                else:
                    success = self.client.capture_screen(self.cursor_enabled, dest_path)
            elif self.mode == "screen":
                success = self.client.capture_screen(self.cursor_enabled, dest_path)
            elif self.mode == "window":
                if self.hovered_window:
                    win_id = self.hovered_window.get("id", 0)
                    success = self.client.capture_window(win_id, True, self.cursor_enabled, dest_path)
                else:
                    success = self.client.capture_screen(self.cursor_enabled, dest_path)
        except Exception as e:
            print(f"[sadeem-capture] Photo capture error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            self._send_error_notification(t("error_capture_failed"), str(e))
        finally:
            if self.halo_enabled:
                try:
                    self.client.set_halo_active(False)
                except Exception:
                    pass

        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            copy_file_to_clipboard(dest_path)
            launch_gallery_editor(dest_path)
        elif not success:
            self._send_error_notification(t("error_capture_failed"), "Failed to save screenshot file")

        self._close_or_quit()
        return GLib.SOURCE_REMOVE

    # --- Video Recording Pipeline ---
    def _start_video_recording(self, target_win=None):
        self.set_visible(False)
        GLib.timeout_add(80, self._do_start_video, target_win)

    def _do_start_video(self, target_win=None):
        try:
            # Determine audio mode
            if self.audio_system_enabled and self.audio_mic_enabled:
                a_mode = "both"
            elif self.audio_system_enabled:
                a_mode = "system"
            elif self.audio_mic_enabled:
                a_mode = "mic"
            else:
                a_mode = "none"

            # Determine crop box and window rect
            crop_box = None
            if self.mode == "selection" and self.sel_w > 4 and self.sel_h > 4:
                crop_box = (self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            elif self.mode == "window":
                win = target_win or self.hovered_window
                if win:
                    crop_box = (win.get("x", 0), win.get("y", 0), win.get("width", 1280), win.get("height", 720))

            scale = self.get_scale_factor() or 1.0
            width = self.get_width() or 1920
            height = self.get_height() or 1080

            from capture.video_recorder import VideoRecorder

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
            )

            success = self.recorder.start()
            if not success:
                print("[sadeem-capture] Failed to start recorder.", file=sys.stderr)
                self._send_error_notification(t("error_rec_start_failed"), "Recorder start returned false")
                self._close_or_quit()
                return GLib.SOURCE_REMOVE

            self.is_recording = True

            # Subscribe to StopRecordingRequested and SilentScreenshotRequested from panel indicator
            self._stop_sig_id = self.client.subscribe_stop_recording(self._on_stop_signal)
            self._silent_sig_id = self.client.subscribe_silent_screenshot(self._on_silent_screenshot_signal)
        except Exception as e:
            print(f"[sadeem-capture] Video recording start error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            self._send_error_notification(t("error_rec_start_failed"), str(e))
            self._close_or_quit()
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_REMOVE

    def _on_silent_screenshot_signal(self):
        GLib.idle_add(self._take_silent_screenshot)

    def _take_silent_screenshot(self):
        """Takes an instant silent screenshot without interrupting the active video recording."""
        if not self.is_recording:
            return

        dest_path = generate_screenshot_path()
        success = False

        if self.mode == "selection" and self.sel_w > 4 and self.sel_h > 4:
            success = self.client.capture_area(
                int(self.sel_x),
                int(self.sel_y),
                int(self.sel_w),
                int(self.sel_h),
                self.cursor_enabled,
                dest_path,
            )
        else:
            success = self.client.capture_screen(self.cursor_enabled, dest_path)

        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            copy_file_to_clipboard(dest_path)
            self.client.flash_camera_indicator()
            try:
                subprocess.run(
                    ["canberra-gtk-play", "-i", "camera-shutter"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def _on_stop_signal(self):
        GLib.idle_add(self._stop_video_recording)

    def _stop_video_recording(self):
        if not self.is_recording or not self.recorder:
            self._close_or_quit()
            return

        success, path, size, duration = self.recorder.stop()
        self.is_recording = False

        if success and os.path.isfile(path) and size > 0:
            formatted_size = format_file_size(size)
            # 1. Desktop Notification
            title = t("notif_recorded_title")
            body = t("notif_recorded_body", size=formatted_size, path=path)

            try:
                notif = Gio.Notification.new(title)
                notif.set_body(body)
                notif.set_icon(Gio.ThemedIcon.new("video-x-generic"))
                self.app.send_notification("sadeem-video-saved", notif)
            except Exception:
                pass

            if shutil.which("notify-send"):
                try:
                    subprocess.run(
                        ["notify-send", "-a", "Sadeem Capture", "-i", "video-x-generic", title, body],
                        check=False,
                    )
                except Exception:
                    pass

            # 2. Handoff to Sadeem Gallery video editor
            launch_gallery_editor(path)
        else:
            self._send_error_notification(t("error_rec_start_failed"), "Video recording failed or output file is empty")

        self._close_or_quit()


class SadeemCaptureApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.client = CaptureClient()
        self.window = None
        self.is_daemon = False
        self._css_loaded = False

    def _take_background_snapshot(self):
        # If helper proxy is not active, attempt to enable the extension and wait up to 1 second
        if not self.client._helper_proxy or not self.client._helper_proxy.get_name_owner():
            try:
                subprocess.run(
                    ["gnome-extensions", "enable", "sadeem-desktop-helper@sadeem.os"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                pass

            import time
            start = time.time()
            while time.time() - start < 1.0:
                self.client._init_proxies()
                if self.client._helper_proxy and self.client._helper_proxy.get_name_owner():
                    break
                time.sleep(0.08)

        tmp_dir = GLib.get_user_runtime_dir()
        bg_path = os.path.join(tmp_dir, f"sadeem_capture_bg_{os.getpid()}_{int(GLib.get_real_time())}.png")
        try:
            if self.client.capture_screen(False, bg_path):
                return bg_path
        except Exception as e:
            print(f"[sadeem-capture] Background snapshot failed: {e}", file=sys.stderr)
        return None

    def _load_styles(self):
        if self._css_loaded:
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
            self._css_loaded = True

    def do_activate(self):
        # If active recording is running, take a silent screenshot instead of opening UI
        if self.window is not None:
            if getattr(self.window, "is_recording", False):
                self.window._take_silent_screenshot()
            else:
                self.window.present()
            return

        self._load_styles()
        bg_path = self._take_background_snapshot()
        self.window = SadeemCaptureWindow(self, bg_path=bg_path)
        self.window.fullscreen()
        self.window.present()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]

        # Resident pre-warmed daemon mode
        if "--daemon" in args:
            self.is_daemon = True
            self.hold()
            print("[sadeem-capture] Resident pre-warmed daemon initialized and holding in RAM.", file=sys.stderr)
            return 0

        # Dedicated stop recording argument
        if "--stop-recording" in args:
            if self.window and getattr(self.window, "is_recording", False):
                self.window._stop_video_recording()
            return 0

        # If active recording is running and no --stop-recording was passed, take silent screenshot
        if self.window and getattr(self.window, "is_recording", False):
            self.window._take_silent_screenshot()
            return 0

        # Instant window capture flag
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
                    print(f"[sadeem-capture] Error in --window-id capture: {e}", file=sys.stderr)
                    return 1

        if self.window is not None:
            self.window.present()
            return 0

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

        self._load_styles()
        bg_path = self._take_background_snapshot()
        self.window = SadeemCaptureWindow(self, initial_mode=initial_mode, bg_path=bg_path)
        if initial_media == "video":
            self.window._set_media_type("video")
        self.window.fullscreen()
        self.window.present()
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
                    sys.exit(0)
                else:
                    sys.exit(1)
        except Exception as exc:
            print(f"[sadeem-capture] CLI capture error: {exc}", file=sys.stderr)
            sys.exit(1)

    GLib.set_prgname(APP_ID)
    app = SadeemCaptureApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
