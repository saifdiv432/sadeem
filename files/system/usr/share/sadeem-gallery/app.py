#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Gallery — معرض سديم
GTK 4 / Libadwaita chronological photo gallery, fast RAW/image viewer,
and calm GNOME/Adwaita 6-section vertical rail image editor.
"""

import concurrent.futures
import os
import shutil
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import canvas as canvas_mod
import editor
import i18n
import media

t = i18n.t
APP_ID = "org.sadeem.Gallery"


def launch_video_editor(video_path):
    """Launches sadeem-video-editor for a given video file."""
    editor_bin = shutil.which("sadeem-video-editor")
    if not editor_bin:
        repo_bin = os.path.normpath(os.path.join(APP_DIR, "..", "..", "..", "bin", "sadeem-video-editor"))
        sys_bin = "/usr/bin/sadeem-video-editor"
        for candidate in [repo_bin, sys_bin]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                editor_bin = candidate
                break
    if not editor_bin:
        editor_bin = "sadeem-video-editor"

    try:
        res = subprocess.run(
            ["systemd-run", "--user", "--scope", "--quiet", editor_bin, video_path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return True
    except Exception:
        pass

    try:
        subprocess.Popen([editor_bin, video_path], start_new_session=True, close_fds=True)
        return True
    except Exception as e:
        sys.stderr.write(f"Failed to launch video editor: {e}\n")
        return False

MARKUP_COLORS = [
    ("#7a1c33", "Burgundy"),
    ("#0f4c5c", "Teal"),
    ("#ef4444", "Red"),
    ("#facc15", "Yellow"),
    ("#22c55e", "Green"),
    ("#ffffff", "White"),
    ("#111827", "Black"),
]

FORMAT_FILTER_OPTIONS = [
    ("all", "fmt_all", "fmt_short_all", ["view-grid-symbolic"]),
    ("video", "fmt_video", "fmt_short_video", ["video-x-generic-symbolic"]),
    ("jpeg", "fmt_jpeg", "fmt_short_jpeg", ["image-x-generic-symbolic"]),
    ("png", "fmt_png", "fmt_short_png", ["image-x-generic-symbolic"]),
    ("webp", "fmt_webp", "fmt_short_webp", ["image-x-generic-symbolic"]),
    ("heic_avif", "fmt_heic_avif", "fmt_short_heic_avif", ["camera-photo-symbolic"]),
    ("animated", "fmt_animated", "fmt_short_animated", ["media-playback-start-symbolic"]),
    ("raw", "fmt_raw", "fmt_short_raw", ["applications-photography-symbolic"]),
    ("vector", "fmt_vector", "fmt_short_vector", ["applications-graphics-symbolic"]),
    ("other", "fmt_other", "fmt_short_other", ["document-open-symbolic"]),
]

DIMENSION_FILTER_OPTIONS = [
    ("all", "dim_all", "dim_short_all", ["view-grid-symbolic"]),
    ("landscape", "dim_landscape", "dim_short_landscape", ["object-flip-horizontal-symbolic"]),
    ("portrait", "dim_portrait", "dim_short_portrait", ["object-flip-vertical-symbolic"]),
    ("square", "dim_square", "dim_short_square", ["view-grid-symbolic"]),
    ("ultrawide", "dim_ultrawide", "dim_short_ultrawide", ["view-fullscreen-symbolic"]),
    ("standard", "dim_standard", "dim_short_standard", ["zoom-fit-best-symbolic"]),
]

RESOLUTION_FILTER_OPTIONS = [
    ("all", "res_all", "res_short_all", ["view-grid-symbolic"]),
    ("low", "res_low", "res_short_low", ["image-x-generic-symbolic"]),
    ("hd", "res_hd", "res_short_hd", ["video-display-symbolic"]),
    ("fhd", "res_fhd", "res_short_fhd", ["zoom-fit-best-symbolic"]),
    ("2k", "res_2k", "res_short_2k", ["view-fullscreen-symbolic"]),
    ("4k", "res_4k", "res_short_4k", ["starred-symbolic"]),
]

# Legacy alias
GALLERY_CATEGORIES = [
    ("all", "cat_all", ["view-grid-symbolic"]),
    ("camera", "cat_camera", ["camera-photo-symbolic"]),
    ("screenshots", "cat_screenshots", ["applets-screenshooter-symbolic"]),
    ("hd", "cat_hd", ["zoom-fit-best-symbolic"]),
    ("portrait", "cat_portrait", ["object-flip-vertical-symbolic"]),
    ("landscape", "cat_landscape", ["object-flip-horizontal-symbolic"]),
    ("animated", "cat_animated", ["media-playback-start-symbolic"]),
    ("raw", "cat_raw", ["camera-photo-symbolic"]),
    ("vector", "cat_vector", ["applications-graphics-symbolic"]),
]

SADEEM_CSS = """
.sadeem-canvas-bg {
    background-color: #18181c;
}
.sadeem-btn {
    background-color: #2e2e35;
    background-image: none;
    color: #f1f5f9;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    min-height: 30px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 500;
}
.sadeem-btn:hover {
    background-color: #393943;
}
.sadeem-btn:active {
    background-color: #444450;
}
.sadeem-btn-compact {
    background-color: #2e2e35;
    background-image: none;
    color: #f1f5f9;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    min-height: 30px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: 500;
}
.sadeem-btn-compact:hover {
    background-color: #393943;
}
.sadeem-btn-active {
    background-color: #7a1c33;
    background-image: none;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.14);
}
.sadeem-btn-active:hover {
    background-color: #8c223c;
}
.sadeem-btn-active label, .sadeem-btn-active image {
    color: #ffffff;
}
.sadeem-btn-danger {
    background-color: #2e2e35;
    background-image: none;
    color: #fca5a5;
    border-radius: 6px;
    border: 1px solid rgba(239, 68, 68, 0.28);
    min-height: 30px;
    padding: 4px 10px;
    font-size: 12px;
}
.sadeem-btn-danger:hover {
    background-color: rgba(127, 29, 29, 0.65);
    color: #fecaca;
}
.sadeem-header-btn {
    border-radius: 6px;
    min-height: 30px;
    padding: 3px 10px;
    font-size: 12px;
}
.sadeem-sidebar-shell {
    background-color: #222227;
    border-left: 1px solid rgba(255, 255, 255, 0.08);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}
.sadeem-drawer {
    background-color: #222227;
}
.sadeem-rail {
    background-color: #1c1c21;
    border-left: 1px solid rgba(255, 255, 255, 0.08);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}
.rail-btn {
    background-color: transparent;
    background-image: none;
    color: #cbd5e1;
    border: 1px solid transparent;
    border-radius: 6px;
    min-height: 50px;
    padding: 6px 4px;
    font-size: 11px;
    font-weight: 500;
}
.rail-btn:hover {
    background-color: #2e2e35;
    color: #f8fafc;
}
.rail-btn-active {
    background-color: #7a1c33;
    background-image: none;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.14);
}
.rail-btn-active:hover {
    background-color: #8c223c;
}
.rail-btn-active label, .rail-btn-active image {
    color: #ffffff;
}
.sadeem-scale trough {
    min-height: 4px;
    border-radius: 3px;
    background-color: rgba(255, 255, 255, 0.14);
}
.sadeem-scale highlight {
    background-color: #7a1c33;
    border-radius: 3px;
}
.sadeem-scale slider {
    min-width: 14px;
    min-height: 14px;
    border-radius: 9999px;
    background-color: #f1f5f9;
    border: 2px solid #7a1c33;
}
.swatch-dot {
    min-width: 22px;
    min-height: 22px;
    padding: 0;
    border-radius: 9999px;
    border: 2px solid rgba(255, 255, 255, 0.25);
}
.swatch-dot-active {
    border: 2px solid #ffffff;
    box-shadow: 0 0 0 2px #7a1c33;
}
.date-section-title {
    font-size: 15px;
    font-weight: 700;
    margin-top: 6px;
    margin-bottom: 2px;
}
.date-count-lbl {
    background-color: rgba(255, 255, 255, 0.07);
    color: #cbd5e1;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
.thumb-tile {
    padding: 0;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background-color: #222227;
}
.thumb-tile:hover {
    border-color: #7a1c33;
}
.thumb-badge-raw {
    background-color: rgba(24, 24, 28, 0.86);
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    font-weight: 700;
}
.thumb-badge-anim {
    background-color: rgba(24, 24, 28, 0.86);
    color: #cbd5e1;
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    font-weight: 700;
}
.thumb-badge-video {
    background-color: rgba(15, 23, 42, 0.88);
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}
.video-ctrl-bar {
    background-color: rgba(24, 24, 28, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 24px;
    padding: 4px 14px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.5);
}
.video-time-lbl {
    font-size: 12px;
    font-weight: 600;
    color: #cbd5e1;
}
.video-btn-play {
    background-color: #7a1c33;
    color: #ffffff;
    border-radius: 9999px;
    min-width: 34px;
    min-height: 34px;
    padding: 0;
    border: none;
}
.video-btn-play:hover {
    background-color: #92223e;
}
.video-seek-scale trough {
    min-height: 6px;
    border-radius: 3px;
    background-color: rgba(255, 255, 255, 0.18);
}
.video-seek-scale highlight {
    background-color: #7a1c33;
    border-radius: 3px;
}
.video-seek-scale slider {
    min-width: 14px;
    min-height: 14px;
    border-radius: 9999px;
    background-color: #f1f5f9;
    border: 2px solid #7a1c33;
}
.viewer-bottom-bar {
    background-color: #1e1e23;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding: 5px 12px;
}
.zoom-group button {
    background-color: #2e2e35;
    background-image: none;
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.07);
    min-height: 28px;
    padding: 2px 8px;
    font-size: 12px;
}
.zoom-group button:hover {
    background-color: #393943;
}
.zoom-readout-btn {
    min-width: 52px;
    font-weight: 600;
}
.save-menu-btn {
    border-radius: 6px;
    min-height: 30px;
    padding: 4px 10px;
    font-size: 12px;
}
.editor-drawer {
    background-color: #222227;
    border-left: 1px solid rgba(255, 255, 255, 0.08);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}
.drawer-section-title {
    font-size: 11px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.55);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.video-timeline-container {
    background-color: #222227;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 8px 12px;
}
.video-progress-banner {
    background-color: rgba(122, 28, 51, 0.25);
    border-radius: 8px;
    border: 1px solid rgba(122, 28, 51, 0.5);
    padding: 6px 12px;
}
.drawer-subtle-label {
    font-size: 11px;
    color: #94a3b8;
    font-weight: 600;
}
.info-key-lbl {
    font-size: 11px;
    color: #94a3b8;
}
.info-val-lbl {
    font-size: 12px;
    color: #f1f5f9;
}
.loading-chip {
    background-color: rgba(34, 34, 39, 0.92);
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}
"""


def safe_icon(names, fallback="image-x-generic-symbolic"):
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        for name in names:
            if theme.has_icon(name):
                return name
    return fallback


class SadeemGalleryWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title(t("app_title"))
        self.set_default_size(1200, 780)
        self.set_size_request(860, 600)

        self.settings = media.load_settings()

        # Gallery state
        self.all_gallery_items = []
        self.filter_format = "all"
        self.filter_dimensions = "all"
        self.filter_resolution = "all"
        self.active_filter = "all"
        self.thumb_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._scan_generation = 0

        # Viewer state
        self.viewer_items = []
        self.viewer_index = 0
        self.current_path = None
        self.current_is_raw = False
        self.current_exif = {}
        self.slideshow_timer = None
        self._load_generation = 0

        # Video state
        self.video_player_widget = None
        self.video_editor_view = None
        self.is_current_video = False

        # Editor state
        self.edit_mode = False
        self.active_rail_section = "crop"
        self.base_image = None
        self.preview_image = None
        self.adjustments = editor.default_adjustments()
        self.strokes = []
        self.straighten_angle = 0.0
        self.history = editor.EditorHistory(max_steps=25)
        self._selected_markup_tool = "none"
        self._adj_debounce_id = None
        self._syncing_resize_spins = False
        self._syncing_adj_widgets = False

        self._install_css()
        self._build_ui()
        self._setup_shortcuts()
        self.connect("close-request", self._on_close_request)

    def _install_css(self):
        swatch_rules = []
        for idx, (hx, _name) in enumerate(MARKUP_COLORS):
            swatch_rules.append(f".swatch-color-{idx} {{ background-color: {hx}; background-image: none; }}")
        full_css = SADEEM_CSS + "\n" + "\n".join(swatch_rules)

        prov = Gtk.CssProvider()
        prov.load_from_string(full_css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            local_icons = os.path.abspath(os.path.join(APP_DIR, "..", "icons"))
            if os.path.isdir(local_icons):
                Gtk.IconTheme.get_for_display(display).add_search_path(local_icons)

    def _on_close_request(self, *_args):
        self._stop_slideshow()
        self.canvas.stop_animation()
        if self.video_player_widget:
            self.video_player_widget.stop()
        self.thumb_pool.shutdown(wait=False, cancel_futures=True)
        return False

    def _clear_box(self, box):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _toast(self, msg):
        self.toast_overlay.add_toast(Adw.Toast.new(msg))

    def _present_alert(self, heading, body, responses, on_response):
        if hasattr(Adw, "AlertDialog"):
            dlg = Adw.AlertDialog.new(heading, body)
            for rid, lbl, app_style in responses:
                dlg.add_response(rid, lbl)
                if app_style is not None:
                    dlg.set_response_appearance(rid, app_style)
            dlg.set_default_response(responses[0][0])
            dlg.set_close_response("cancel")
            dlg.connect("response", lambda _d, r: on_response(r))
            dlg.present(self)
        else:
            dlg = Adw.MessageDialog(transient_for=self, modal=True, heading=heading, body=body)
            for rid, lbl, app_style in responses:
                dlg.add_response(rid, lbl)
                if app_style is not None:
                    dlg.set_response_appearance(rid, app_style)
            dlg.set_default_response(responses[0][0])
            dlg.set_close_response("cancel")
            dlg.connect("response", lambda _d, r: on_response(r))
            dlg.present()

    # =========================================================================
    # ROOT STACK & KEYBOARD SHORTCUTS
    # =========================================================================
    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.root_stack = Gtk.Stack()
        self.root_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.root_stack.set_transition_duration(160)
        self.toast_overlay.set_child(self.root_stack)

        self.gallery_page = self._build_gallery_view()
        self.viewer_page = self._build_viewer_and_editor_view()

        self.root_stack.add_named(self.gallery_page, "gallery")
        self.root_stack.add_named(self.viewer_page, "viewer")

    def _setup_shortcuts(self):
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, _ctrl, keyval, _keycode, state):
        cur_child = self.root_stack.get_visible_child_name()
        if cur_child != "viewer":
            return False

        if self.is_current_video and self.video_player_widget:
            if keyval == Gdk.KEY_space:
                self.video_player_widget.toggle_play()
                return True
            elif keyval == Gdk.KEY_Left:
                self.video_player_widget.seek_relative(-5.0)
                return True
            elif keyval == Gdk.KEY_Right:
                self.video_player_widget.seek_relative(5.0)
                return True
            elif keyval in (Gdk.KEY_m, Gdk.KEY_M):
                self.video_player_widget.toggle_mute()
                return True
            elif keyval == Gdk.KEY_Escape:
                self.open_gallery_mode()
                return True

        ctrl_down = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl_down:
            if keyval in (Gdk.KEY_c, Gdk.KEY_C):
                self._copy_current_to_clipboard()
                return True
            if self.edit_mode and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
                self._do_undo()
                return True
            if self.edit_mode and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
                self._do_redo()
                return True
            if keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                self.canvas.zoom_by(1.2)
                return True
            if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
                self.canvas.zoom_by(1.0 / 1.2)
                return True
            if keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
                self.canvas.zoom_fit()
                return True
            if keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
                self.canvas.zoom_100()
                return True

        if not self.edit_mode:
            if keyval == Gdk.KEY_Right:
                self._navigate_viewer(-1 if i18n.LANG == "ar" else 1)
                return True
            if keyval == Gdk.KEY_Left:
                self._navigate_viewer(1 if i18n.LANG == "ar" else -1)
                return True
            if keyval in (Gdk.KEY_F5, Gdk.KEY_space):
                self._toggle_slideshow()
                return True
            if keyval == Gdk.KEY_Escape:
                if self.slideshow_timer is not None:
                    self._stop_slideshow()
                else:
                    self.open_gallery_mode()
                return True
        else:
            if keyval == Gdk.KEY_Escape:
                self._handle_escape_in_editor()
                return True
        return False

    def _handle_escape_in_editor(self):
        has_changes = (self.history and self.history.can_undo()) or bool(self.strokes)
        if has_changes:
            responses = [
                ("discard", t("btn_discard"), Adw.ResponseAppearance.DESTRUCTIVE),
                ("cancel", t("btn_cancel"), Adw.ResponseAppearance.DEFAULT),
            ]

            def _on_resp(rid):
                if rid == "discard":
                    if self.history:
                        self.history.clear()
                    self.strokes = []
                    if getattr(self, "opened_in_edit_mode", False):
                        self.close()
                    else:
                        self._set_edit_mode(False)

            self._present_alert(
                t("discard_title"),
                t("discard_body"),
                responses,
                _on_resp,
            )
        else:
            if getattr(self, "opened_in_edit_mode", False):
                self.close()
            else:
                self._set_edit_mode(False)

    # =========================================================================
    # MODE 1: CHRONOLOGICAL GALLERY
    # =========================================================================
    def _build_gallery_view(self):
        tv = Adw.ToolbarView()

        hb = Adw.HeaderBar()
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ico = Gtk.Image.new_from_icon_name("sadeem-gallery")
        ico.set_pixel_size(20)
        title_box.append(ico)
        lbl_t = Gtk.Label(label=t("app_title"))
        lbl_t.add_css_class("heading")
        title_box.append(lbl_t)
        hb.set_title_widget(title_box)

        # 3 compact orthogonal filter dropdowns + reset button
        filters_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # 1. Format dropdown
        self.btn_fmt_menu, self.lbl_fmt_title, self.pop_fmt, self.fmt_item_btns = self._create_filter_menu(
            FORMAT_FILTER_OPTIONS,
            prefix_key="filter_fmt_prefix",
            on_select=self._on_format_filter_selected,
        )
        filters_box.append(self.btn_fmt_menu)

        # 2. Dimensions dropdown
        self.btn_dim_menu, self.lbl_dim_title, self.pop_dim, self.dim_item_btns = self._create_filter_menu(
            DIMENSION_FILTER_OPTIONS,
            prefix_key="filter_dim_prefix",
            on_select=self._on_dimension_filter_selected,
        )
        filters_box.append(self.btn_dim_menu)

        # 3. Resolution dropdown
        self.btn_res_menu, self.lbl_res_title, self.pop_res, self.res_item_btns = self._create_filter_menu(
            RESOLUTION_FILTER_OPTIONS,
            prefix_key="filter_res_prefix",
            on_select=self._on_resolution_filter_selected,
        )
        filters_box.append(self.btn_res_menu)

        # 4. Clear/Reset filter button
        self.btn_clear_filters = Gtk.Button()
        self.btn_clear_filters.set_icon_name(safe_icon(["edit-clear-symbolic", "user-trash-symbolic"]))
        self.btn_clear_filters.set_tooltip_text(t("filter_clear_tooltip"))
        self.btn_clear_filters.add_css_class("sadeem-header-btn")
        self.btn_clear_filters.set_visible(False)
        self.btn_clear_filters.connect("clicked", lambda _b: self._reset_all_filters())
        filters_box.append(self.btn_clear_filters)

        hb.pack_start(filters_box)

        # End buttons: Direct Choose Folder + Refresh
        btn_folder = Gtk.Button()
        fb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fb.append(Gtk.Image.new_from_icon_name(safe_icon(["folder-open-symbolic", "folder-symbolic"])))
        fb.append(Gtk.Label(label=t("btn_choose_folder")))
        btn_folder.set_child(fb)
        btn_folder.add_css_class("sadeem-btn-compact")
        btn_folder.connect("clicked", lambda _b: self._choose_folder_directly())
        hb.pack_end(btn_folder)

        btn_ref = Gtk.Button()
        btn_ref.set_icon_name(safe_icon(["view-refresh-symbolic"]))
        btn_ref.set_tooltip_text(t("btn_refresh"))
        btn_ref.add_css_class("sadeem-header-btn")
        btn_ref.connect("clicked", lambda _b: self.refresh_gallery())
        hb.pack_end(btn_ref)

        tv.add_top_bar(hb)

        self.gallery_stack = Gtk.Stack()
        self.gallery_stack.set_vexpand(True)
        tv.set_content(self.gallery_stack)

        # Loading page
        load_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        load_box.set_valign(Gtk.Align.CENTER)
        load_box.set_halign(Gtk.Align.CENTER)
        self.gallery_spinner = Gtk.Spinner()
        self.gallery_spinner.set_size_request(36, 36)
        self.gallery_spinner.set_spinning(False)
        load_box.append(self.gallery_spinner)
        l_lbl = Gtk.Label(label=t("gallery_scanning"))
        l_lbl.add_css_class("dim-label")
        load_box.append(l_lbl)
        self.gallery_stack.add_named(load_box, "loading")

        # Empty state
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        e_ico = Gtk.Image.new_from_icon_name("sadeem-gallery")
        e_ico.set_pixel_size(64)
        empty_box.append(e_ico)
        e_t = Gtk.Label(label=t("gallery_empty_title"))
        e_t.add_css_class("title-3")
        empty_box.append(e_t)
        e_d = Gtk.Label(label=t("gallery_empty_desc"))
        e_d.add_css_class("dim-label")
        e_d.set_wrap(True)
        e_d.set_justify(Gtk.Justification.CENTER)
        empty_box.append(e_d)
        e_btn = Gtk.Button(label=t("btn_choose_folder"))
        e_btn.add_css_class("sadeem-btn")
        e_btn.connect("clicked", lambda _b: self._choose_folder_directly())
        empty_box.append(e_btn)
        self.btn_empty_reset = Gtk.Button(label=t("filter_clear_tooltip"))
        self.btn_empty_reset.add_css_class("sadeem-btn")
        self.btn_empty_reset.set_visible(False)
        self.btn_empty_reset.connect("clicked", lambda _b: self._reset_all_filters())
        empty_box.append(self.btn_empty_reset)
        self.gallery_stack.add_named(empty_box, "empty")

        # Timeline scroll area
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.timeline_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.timeline_box.set_margin_top(14)
        self.timeline_box.set_margin_bottom(24)
        self.timeline_box.set_margin_start(18)
        self.timeline_box.set_margin_end(18)
        scroll.set_child(self.timeline_box)
        self.gallery_stack.add_named(scroll, "timeline")

        self._update_filter_styles()
        return tv

    def open_gallery_mode(self):
        self._stop_slideshow()
        self.canvas.stop_animation()
        if self.video_player_widget:
            self.video_player_widget.stop()
        self._set_edit_mode(False)
        self.root_stack.set_visible_child_name("gallery")
        if not self.all_gallery_items:
            self.refresh_gallery()

    def _create_filter_menu(self, options, prefix_key, on_select):
        btn = Gtk.MenuButton()
        btn.add_css_class("sadeem-btn-compact")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        lbl = Gtk.Label(label=f"{t(prefix_key)}: {t('fmt_short_all')}")
        lbl.set_halign(Gtk.Align.CENTER)
        box.append(lbl)

        arr = Gtk.Image.new_from_icon_name(safe_icon(["pan-down-symbolic"]))
        arr.set_pixel_size(12)
        box.append(arr)
        btn.set_child(box)

        popover = Gtk.Popover()
        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pop_box.set_margin_top(6)
        pop_box.set_margin_bottom(6)
        pop_box.set_margin_start(6)
        pop_box.set_margin_end(6)
        pop_box.set_size_request(220, -1)
        popover.set_child(pop_box)

        item_btns = {}
        for fid, fkey, _fshort, ficons in options:
            cb = Gtk.Button()
            cb.add_css_class("flat")
            cb.add_css_class("save-menu-btn")

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            ico = Gtk.Image.new_from_icon_name(safe_icon(ficons))
            ico.set_pixel_size(15)
            row.append(ico)

            item_lbl = Gtk.Label(label=t(fkey))
            item_lbl.set_halign(Gtk.Align.START)
            item_lbl.set_hexpand(True)
            row.append(item_lbl)

            cb.set_child(row)

            def _pick(_b, val=fid, pop=popover):
                pop.popdown()
                on_select(val)

            cb.connect("clicked", _pick)
            pop_box.append(cb)
            item_btns[fid] = cb

        btn.set_popover(popover)
        return btn, lbl, popover, item_btns

    def _on_format_filter_selected(self, fmt_id):
        self.filter_format = fmt_id
        self._update_filter_styles()
        self._render_gallery_timeline()

    def _on_dimension_filter_selected(self, dim_id):
        self.filter_dimensions = dim_id
        self._update_filter_styles()
        self._render_gallery_timeline()

    def _on_resolution_filter_selected(self, res_id):
        self.filter_resolution = res_id
        self._update_filter_styles()
        self._render_gallery_timeline()

    def _reset_all_filters(self):
        self.filter_format = "all"
        self.filter_dimensions = "all"
        self.filter_resolution = "all"
        self._update_filter_styles()
        self._render_gallery_timeline()

    def _update_filter_styles(self):
        # 1. Format label and styles
        fmt_short_key = "fmt_short_all"
        for fid, _fkey, fshort, _icons in FORMAT_FILTER_OPTIONS:
            if fid == self.filter_format:
                fmt_short_key = fshort
                break
        self.lbl_fmt_title.set_text(f"{t('filter_fmt_prefix')}: {t(fmt_short_key)}")
        for fid, btn in self.fmt_item_btns.items():
            if fid == self.filter_format:
                btn.remove_css_class("flat")
                btn.add_css_class("sadeem-btn-active")
            else:
                btn.remove_css_class("sadeem-btn-active")
                btn.add_css_class("flat")
        if self.filter_format != "all":
            self.btn_fmt_menu.add_css_class("sadeem-btn-active")
        else:
            self.btn_fmt_menu.remove_css_class("sadeem-btn-active")

        # 2. Dimensions label and styles
        dim_short_key = "dim_short_all"
        for did, _dkey, dshort, _icons in DIMENSION_FILTER_OPTIONS:
            if did == self.filter_dimensions:
                dim_short_key = dshort
                break
        self.lbl_dim_title.set_text(f"{t('filter_dim_prefix')}: {t(dim_short_key)}")
        for did, btn in self.dim_item_btns.items():
            if did == self.filter_dimensions:
                btn.remove_css_class("flat")
                btn.add_css_class("sadeem-btn-active")
            else:
                btn.remove_css_class("sadeem-btn-active")
                btn.add_css_class("flat")
        if self.filter_dimensions != "all":
            self.btn_dim_menu.add_css_class("sadeem-btn-active")
        else:
            self.btn_dim_menu.remove_css_class("sadeem-btn-active")

        # 3. Resolution label and styles
        res_short_key = "res_short_all"
        for rid, _rkey, rshort, _icons in RESOLUTION_FILTER_OPTIONS:
            if rid == self.filter_resolution:
                res_short_key = rshort
                break
        self.lbl_res_title.set_text(f"{t('filter_res_prefix')}: {t(res_short_key)}")
        for rid, btn in self.res_item_btns.items():
            if rid == self.filter_resolution:
                btn.remove_css_class("flat")
                btn.add_css_class("sadeem-btn-active")
            else:
                btn.remove_css_class("sadeem-btn-active")
                btn.add_css_class("flat")
        if self.filter_resolution != "all":
            self.btn_res_menu.add_css_class("sadeem-btn-active")
        else:
            self.btn_res_menu.remove_css_class("sadeem-btn-active")

        # 4. Clear/Reset filter button visibility
        has_active_filter = (
            self.filter_format != "all"
            or self.filter_dimensions != "all"
            or self.filter_resolution != "all"
        )
        self.btn_clear_filters.set_visible(has_active_filter)
        if hasattr(self, "btn_empty_reset"):
            self.btn_empty_reset.set_visible(has_active_filter)

    def _set_gallery_filter(self, fid):
        self.filter_format = fid
        self._update_filter_styles()
        self._render_gallery_timeline()

    def refresh_gallery(self):
        self._scan_generation += 1
        gen = self._scan_generation
        self.gallery_spinner.set_spinning(True)
        self.gallery_stack.set_visible_child_name("loading")
        dirs = media.get_scan_directories(self.settings)

        def _worker():
            items = []
            try:
                items = media.scan_directories(dirs)
            except Exception:
                items = []
            finally:
                GLib.idle_add(self._on_gallery_scanned, gen, items)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_gallery_scanned(self, gen, items):
        if gen != self._scan_generation:
            return False
        self.gallery_spinner.set_spinning(False)
        self.all_gallery_items = items or []
        self._render_gallery_timeline()
        return False

    def _get_filtered_items(self):
        return [
            it for it in self.all_gallery_items
            if media.matches_filters(
                it,
                self.filter_format,
                self.filter_dimensions,
                self.filter_resolution
            )
        ]

    def _render_gallery_timeline(self):
        self._clear_box(self.timeline_box)
        self.gallery_spinner.set_spinning(False)
        filtered = self._get_filtered_items()
        if not filtered:
            self.gallery_stack.set_visible_child_name("empty")
            return

        groups = media.group_items_by_date(filtered)
        gen = self._scan_generation

        for label, group_items in groups:
            sec = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.timeline_box.append(sec)

            hdr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=label)
            lbl.add_css_class("date-section-title")
            lbl.set_halign(Gtk.Align.START)
            hdr_row.append(lbl)

            cnt = Gtk.Label(label=t("gallery_count", count=len(group_items)))
            cnt.add_css_class("date-count-lbl")
            cnt.set_valign(Gtk.Align.CENTER)
            hdr_row.append(cnt)
            sec.append(hdr_row)

            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            flow.set_column_spacing(8)
            flow.set_row_spacing(8)
            flow.set_min_children_per_line(2)
            flow.set_max_children_per_line(8)
            sec.append(flow)

            for item in group_items:
                tile, pic_widget = self._build_thumb_tile(item, filtered)
                flow.append(tile)
                self._schedule_thumbnail(gen, item, pic_widget)

        self.gallery_stack.set_visible_child_name("timeline")

    def _build_thumb_tile(self, item, context_list):
        btn = Gtk.Button()
        btn.add_css_class("thumb-tile")
        btn.set_size_request(180, 180)
        btn.set_overflow(Gtk.Overflow.HIDDEN)
        btn.set_tooltip_text(item["name"])

        ov = Gtk.Overlay()
        ov.set_size_request(180, 180)
        ov.set_overflow(Gtk.Overflow.HIDDEN)
        btn.set_child(ov)

        pic = Gtk.Picture()
        pic.set_size_request(180, 180)
        pic.set_content_fit(Gtk.ContentFit.COVER)
        pic.set_can_shrink(True)
        ov.set_child(pic)

        if item.get("is_video"):
            v_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            v_box.add_css_class("thumb-badge-video")
            v_box.set_halign(Gtk.Align.END)
            v_box.set_valign(Gtk.Align.END)
            v_box.set_margin_bottom(6)
            v_box.set_margin_end(6)
            ico = Gtk.Image.new_from_icon_name(safe_icon(["media-playback-start-symbolic"]))
            ico.set_pixel_size(10)
            v_box.append(ico)
            v_lbl = Gtk.Label(label=item.get("duration_str", "00:00"))
            v_box.append(v_lbl)
            ov.add_overlay(v_box)
        elif item.get("is_raw"):
            b = Gtk.Label(label=item["ext"].lstrip(".").upper())
            b.add_css_class("thumb-badge-raw")
            b.set_halign(Gtk.Align.END)
            b.set_valign(Gtk.Align.START)
            b.set_margin_top(6)
            b.set_margin_end(6)
            ov.add_overlay(b)
        elif item.get("is_animated"):
            b = Gtk.Label(label="GIF" if item["ext"] == ".gif" else "ANIM")
            b.add_css_class("thumb-badge-anim")
            b.set_halign(Gtk.Align.END)
            b.set_valign(Gtk.Align.START)
            b.set_margin_top(6)
            b.set_margin_end(6)
            ov.add_overlay(b)

        btn.connect("clicked", lambda _b, it=item, lst=context_list: self.open_viewer_from_gallery(it, lst))
        return btn, pic

    def _schedule_thumbnail(self, gen, item, pic_widget):
        def _worker():
            if gen != self._scan_generation:
                return
            thumb_path = media.get_or_create_thumbnail(item)
            if thumb_path and gen == self._scan_generation:
                def _apply():
                    if gen == self._scan_generation and pic_widget.get_parent() is not None:
                        pic_widget.set_filename(thumb_path)
                    return False
                GLib.idle_add(_apply)

        try:
            self.thumb_pool.submit(_worker)
        except Exception:
            pass

    def _choose_folder_directly(self):
        """Open native folder chooser directly and add/scan the selected folder."""
        fd = Gtk.FileDialog()
        fd.set_title(t("btn_choose_folder"))

        def _picked(dialog, res):
            try:
                gfile = dialog.select_folder_finish(res)
                if gfile:
                    path = gfile.get_path()
                    if path and os.path.isdir(path):
                        extras = list(self.settings.get("extra_folders", []))
                        ap = os.path.abspath(path)
                        if ap not in [os.path.abspath(x) for x in extras] and ap != os.path.abspath(media.get_default_pictures_dir()):
                            extras.append(ap)
                            self.settings["extra_folders"] = extras
                            media.save_settings(self.settings)
                        self.refresh_gallery()
            except GLib.Error:
                pass

        fd.select_folder(self, None, _picked)

    # =========================================================================
    # MODE 2 & 3: FAST VIEWER + CALM 6-RAIL INTEGRATED EDITOR
    # =========================================================================
    def _build_viewer_and_editor_view(self):
        tv = Adw.ToolbarView()

        # --- Unified HeaderBar with clean Viewer vs Edit state switching ---
        hb = Adw.HeaderBar()

        # START SIDE: Viewer controls
        self.btn_back_gallery = Gtk.Button()
        bb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bb.append(Gtk.Image.new_from_icon_name(safe_icon(["view-grid-symbolic", "go-previous-symbolic"])))
        bb.append(Gtk.Label(label=t("btn_back_gallery")))
        self.btn_back_gallery.set_child(bb)
        self.btn_back_gallery.add_css_class("sadeem-btn-compact")
        self.btn_back_gallery.connect("clicked", lambda _b: self.open_gallery_mode())
        hb.pack_start(self.btn_back_gallery)

        self.nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.nav_box.add_css_class("linked")
        self.btn_prev_img = Gtk.Button()
        self.btn_prev_img.set_icon_name(safe_icon(["go-previous-symbolic"]))
        self.btn_prev_img.set_tooltip_text(t("btn_prev_img"))
        self.btn_prev_img.connect("clicked", lambda _b: self._navigate_viewer(-1))
        self.nav_box.append(self.btn_prev_img)

        self.btn_next_img = Gtk.Button()
        self.btn_next_img.set_icon_name(safe_icon(["go-next-symbolic"]))
        self.btn_next_img.set_tooltip_text(t("btn_next_img"))
        self.btn_next_img.connect("clicked", lambda _b: self._navigate_viewer(1))
        self.nav_box.append(self.btn_next_img)
        hb.pack_start(self.nav_box)

        # START SIDE: Edit-mode controls (hidden in viewer mode)
        self.edit_start_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.edit_start_box.set_visible(False)

        self.btn_done_edit = Gtk.Button(label=t("btn_done_edit"))
        self.btn_done_edit.add_css_class("sadeem-btn-compact")
        self.btn_done_edit.connect("clicked", lambda _b: self._set_edit_mode(False))
        self.edit_start_box.append(self.btn_done_edit)

        ur_linked = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        ur_linked.add_css_class("linked")
        self.btn_undo = Gtk.Button()
        self.btn_undo.set_icon_name(safe_icon(["edit-undo-symbolic"]))
        self.btn_undo.set_tooltip_text(t("btn_undo"))
        self.btn_undo.connect("clicked", lambda _b: self._do_undo())
        ur_linked.append(self.btn_undo)

        self.btn_redo = Gtk.Button()
        self.btn_redo.set_icon_name(safe_icon(["edit-redo-symbolic"]))
        self.btn_redo.set_tooltip_text(t("btn_redo"))
        self.btn_redo.connect("clicked", lambda _b: self._do_redo())
        ur_linked.append(self.btn_redo)
        self.edit_start_box.append(ur_linked)
        hb.pack_start(self.edit_start_box)

        # CENTER: WindowTitle (filename + properly oriented Arabic counter)
        self.viewer_title = Adw.WindowTitle()
        self.viewer_title.set_title(t("app_title"))
        hb.set_title_widget(self.viewer_title)

        # END SIDE: Edit-mode single "Save Changes" MenuButton + Popover
        self.btn_save_menu = Gtk.MenuButton()
        sm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sm_box.append(Gtk.Image.new_from_icon_name(safe_icon(["document-save-symbolic"])))
        sm_box.append(Gtk.Label(label=t("btn_save_changes")))
        self.btn_save_menu.set_child(sm_box)
        self.btn_save_menu.add_css_class("sadeem-btn-compact")
        self.btn_save_menu.set_visible(False)

        self.save_popover = Gtk.Popover()
        sp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sp_box.set_margin_top(6)
        sp_box.set_margin_bottom(6)
        sp_box.set_margin_start(6)
        sp_box.set_margin_end(6)
        self.save_popover.set_child(sp_box)

        for label_key, icon_names, cb, danger in (
            ("btn_save_copy", ["document-save-as-symbolic", "document-save-symbolic"], self._open_save_copy_dialog, False),
            ("btn_overwrite", ["document-save-symbolic"], self._confirm_overwrite_original, True),
            ("btn_copy_clip", ["edit-copy-symbolic"], self._copy_current_to_clipboard, False),
        ):
            mb = Gtk.Button()
            mb.add_css_class("flat")
            mb.add_css_class("save-menu-btn")
            if danger:
                mb.add_css_class("destructive-action")
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.append(Gtk.Image.new_from_icon_name(safe_icon(icon_names)))
            lbl = Gtk.Label(label=t(label_key))
            lbl.set_halign(Gtk.Align.START)
            r.append(lbl)
            mb.set_child(r)

            def _run(_b, func=cb):
                self.save_popover.popdown()
                func()

            mb.connect("clicked", _run)
            sp_box.append(mb)

        self.btn_save_menu.set_popover(self.save_popover)
        hb.pack_end(self.btn_save_menu)

        # END SIDE: Viewer controls (neutral standard buttons, no pill/loud burgundy)
        self.viewer_end_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.btn_slideshow = Gtk.Button()
        self.btn_slideshow.set_icon_name(safe_icon(["media-playback-start-symbolic"]))
        self.btn_slideshow.set_tooltip_text(t("btn_slideshow"))
        self.btn_slideshow.add_css_class("sadeem-header-btn")
        self.btn_slideshow.connect("clicked", lambda _b: self._toggle_slideshow())
        self.viewer_end_box.append(self.btn_slideshow)

        self.btn_wall = Gtk.Button()
        self.btn_wall.set_icon_name(safe_icon(["preferences-desktop-wallpaper-symbolic", "video-display-symbolic"]))
        self.btn_wall.set_tooltip_text(t("btn_wallpaper"))
        self.btn_wall.add_css_class("sadeem-header-btn")
        self.btn_wall.connect("clicked", lambda _b: self._set_as_wallpaper())
        self.viewer_end_box.append(self.btn_wall)

        self.btn_exif = Gtk.MenuButton()
        self.btn_exif.set_icon_name(safe_icon(["dialog-information-symbolic", "help-about-symbolic"]))
        self.btn_exif.set_tooltip_text(t("btn_exif"))
        self.btn_exif.add_css_class("sadeem-header-btn")
        self.exif_popover = Gtk.Popover()
        self.exif_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.exif_box.set_margin_top(10)
        self.exif_box.set_margin_bottom(10)
        self.exif_box.set_margin_start(12)
        self.exif_box.set_margin_end(12)
        self.exif_box.set_size_request(280, -1)
        self.exif_popover.set_child(self.exif_box)
        self.btn_exif.set_popover(self.exif_popover)
        self.viewer_end_box.append(self.btn_exif)

        self.btn_edit_toggle = Gtk.Button(label=t("btn_edit"))
        self.btn_edit_toggle.add_css_class("sadeem-btn-compact")
        self.btn_edit_toggle.connect("clicked", lambda _b: self._on_edit_toggle_clicked())
        self.viewer_end_box.append(self.btn_edit_toggle)

        hb.pack_end(self.viewer_end_box)
        tv.add_top_bar(hb)

        # --- Main Workspace: 75-80% Canvas + Fixed Slim Sidebar (298px) ---
        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_row.set_vexpand(True)
        main_row.set_hexpand(True)
        tv.set_content(main_row)

        canvas_overlay = Gtk.Overlay()
        canvas_overlay.set_hexpand(True)
        canvas_overlay.set_vexpand(True)
        canvas_overlay.add_css_class("sadeem-canvas-bg")
        main_row.append(canvas_overlay)

        self.viewer_content_stack = Gtk.Stack()
        self.viewer_content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.viewer_content_stack.set_transition_duration(120)

        self.canvas = canvas_mod.ImageCanvas(
            on_zoom_changed=self._on_canvas_zoom_changed,
            on_stroke_finished=self._on_canvas_stroke_finished,
            on_text_click=self._on_canvas_text_click,
        )
        self.viewer_content_stack.add_named(self.canvas, "image")

        self.video_container_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.video_container_box.set_hexpand(True)
        self.video_container_box.set_vexpand(True)
        self.viewer_content_stack.add_named(self.video_container_box, "video")

        canvas_overlay.set_child(self.viewer_content_stack)

        self.viewer_spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.viewer_spinner_box.set_halign(Gtk.Align.CENTER)
        self.viewer_spinner_box.set_valign(Gtk.Align.CENTER)
        self.viewer_spinner_box.set_visible(False)
        vsp = Gtk.Spinner()
        vsp.set_size_request(34, 34)
        vsp.set_spinning(True)
        self.viewer_spinner_box.append(vsp)
        vlbl = Gtk.Label(label=t("viewer_loading"))
        vlbl.add_css_class("loading-chip")
        self.viewer_spinner_box.append(vlbl)
        canvas_overlay.add_overlay(self.viewer_spinner_box)

        # Slim Fixed-Width Editor Sidebar (Drawer 226px + 6-Button Rail 72px = 298px)
        self.editor_panel = self._build_editor_sidebar()
        self.editor_panel.set_visible(False)
        main_row.append(self.editor_panel)

        # --- Bottom Status & Unified Compact Zoom Bar ---
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_bar.add_css_class("viewer-bottom-bar")
        self.viewer_bottom_bar = bottom_bar

        self.lbl_viewer_meta = Gtk.Label(label="")
        self.lbl_viewer_meta.add_css_class("caption")
        self.lbl_viewer_meta.add_css_class("dim-label")
        self.lbl_viewer_meta.set_hexpand(True)
        self.lbl_viewer_meta.set_halign(Gtk.Align.START)
        bottom_bar.append(self.lbl_viewer_meta)

        # Single compact linked zoom group: [ - | 69% (toggle 100%/Fit) | + | Fit ]
        zoom_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        zoom_group.add_css_class("linked")
        zoom_group.add_css_class("zoom-group")

        btn_zout = Gtk.Button()
        btn_zout.set_icon_name(safe_icon(["zoom-out-symbolic"]))
        btn_zout.set_tooltip_text(t("btn_zoom_out"))
        btn_zout.connect("clicked", lambda _b: self.canvas.zoom_by(1.0 / 1.25))
        zoom_group.append(btn_zout)

        self.btn_zoom_pct = Gtk.Button(label="100%")
        self.btn_zoom_pct.add_css_class("zoom-readout-btn")
        self.btn_zoom_pct.set_tooltip_text(t("zoom_toggle_tip"))
        self.btn_zoom_pct.connect("clicked", lambda _b: self.canvas.toggle_fit_or_100())
        zoom_group.append(self.btn_zoom_pct)

        btn_zin = Gtk.Button()
        btn_zin.set_icon_name(safe_icon(["zoom-in-symbolic"]))
        btn_zin.set_tooltip_text(t("btn_zoom_in"))
        btn_zin.connect("clicked", lambda _b: self.canvas.zoom_by(1.25))
        zoom_group.append(btn_zin)

        btn_fit = Gtk.Button(label=t("btn_zoom_fit"))
        btn_fit.connect("clicked", lambda _b: self.canvas.zoom_fit())
        zoom_group.append(btn_fit)

        bottom_bar.append(zoom_group)
        tv.add_bottom_bar(bottom_bar)

        self._sync_viewer_header_state()
        return tv

    def _sync_viewer_header_state(self):
        """Enforce clean button visibility between Viewer Mode and Edit Mode."""
        if not hasattr(self, "btn_back_gallery"):
            return
        in_edit = self.edit_mode
        self.btn_back_gallery.set_visible(not in_edit)
        self.nav_box.set_visible(not in_edit)
        self.viewer_end_box.set_visible(not in_edit)

        self.edit_start_box.set_visible(in_edit)
        self.btn_save_menu.set_visible(in_edit)

    # =========================================================================
    # SLIM 5-BUTTON VERTICAL RAIL & COMPACT TOOL DRAWER (298px TOTAL)
    # =========================================================================
    def _build_editor_sidebar(self):
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        shell.set_hexpand(False)
        shell.set_size_request(298, -1)
        shell.add_css_class("sadeem-sidebar-shell")

        # 1. Compact Tool Drawer (~226px)
        drawer_scroll = Gtk.ScrolledWindow()
        drawer_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        drawer_scroll.set_vexpand(True)
        drawer_scroll.set_hexpand(False)
        drawer_scroll.set_size_request(226, -1)
        drawer_scroll.add_css_class("sadeem-drawer")
        shell.append(drawer_scroll)

        self.drawer_stack = Gtk.Stack()
        self.drawer_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.drawer_stack.set_transition_duration(120)
        self.drawer_stack.set_hexpand(False)
        drawer_scroll.set_child(self.drawer_stack)

        self.drawer_stack.add_named(self._build_drawer_crop(), "crop")
        self.drawer_stack.add_named(self._build_drawer_rotate(), "rotate")
        self.drawer_stack.add_named(self._build_drawer_draw(), "draw")
        self.drawer_stack.add_named(self._build_drawer_light(), "light")
        self.drawer_stack.add_named(self._build_drawer_filters(), "filters")

        # 2. Slim Vertical 5-Button Navigation Rail (~72px) on outer edge
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rail.set_hexpand(False)
        rail.set_vexpand(True)
        rail.set_size_request(72, -1)
        rail.set_margin_top(8)
        rail.set_margin_bottom(8)
        rail.set_margin_start(4)
        rail.set_margin_end(4)
        rail.add_css_class("sadeem-rail")
        shell.append(rail)

        rail_specs = [
            ("crop", "rail_crop", ["edit-cut-symbolic", "view-fullscreen-symbolic"]),
            ("rotate", "rail_rotate", ["object-rotate-right-symbolic", "view-refresh-symbolic"]),
            ("draw", "rail_draw", ["document-edit-symbolic"]),
            ("light", "rail_light", ["display-brightness-symbolic", "weather-clear-symbolic"]),
            ("filters", "rail_filters", ["applications-graphics-symbolic", "color-select-symbolic"]),
        ]
        self.rail_buttons = {}
        for sid, lkey, icons in rail_specs:
            btn = Gtk.Button()
            btn.add_css_class("rail-btn")
            vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            vb.set_halign(Gtk.Align.CENTER)
            vb.set_valign(Gtk.Align.CENTER)
            ico = Gtk.Image.new_from_icon_name(safe_icon(icons))
            ico.set_pixel_size(18)
            vb.append(ico)
            lbl = Gtk.Label(label=t(lkey))
            vb.append(lbl)
            btn.set_child(vb)
            btn.connect("clicked", lambda _b, name=sid: self._select_rail_section(name))
            rail.append(btn)
            self.rail_buttons[sid] = btn

        return shell

    def _make_drawer_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(14)
        box.set_margin_start(10)
        box.set_margin_end(10)
        return box

    # 1. Drawer: Crop (auto-activates crop frame, no redundant toggle or headers)
    def _build_drawer_crop(self):
        box = self._make_drawer_box()

        grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        grid.set_column_homogeneous(True)
        box.append(grid)

        self.ratio_buttons = {}
        ratios = [
            ("free", None, "ratio_free"),
            ("1:1", 1.0, "ratio_1_1"),
            ("16:9", 16.0 / 9.0, "ratio_16_9"),
            ("4:3", 4.0 / 3.0, "ratio_4_3"),
            ("9:16", 9.0 / 16.0, "ratio_9_16"),
        ]
        for idx, (rid, val, key) in enumerate(ratios):
            rb = Gtk.Button(label=t(key))
            rb.add_css_class("sadeem-btn-compact")
            rb.connect("clicked", lambda _b, r=rid, v=val: self._set_crop_ratio(r, v))
            grid.attach(rb, idx % 2, idx // 2, 1, 1)
            self.ratio_buttons[rid] = rb
        self._highlight_ratio_btn("free")

        btn_apply_crop = Gtk.Button(label=t("btn_apply_crop"))
        btn_apply_crop.add_css_class("sadeem-btn")
        btn_apply_crop.add_css_class("sadeem-btn-active")
        btn_apply_crop.set_margin_top(4)
        btn_apply_crop.connect("clicked", lambda _b: self._apply_crop())
        box.append(btn_apply_crop)
        return box

    # 2. Drawer: Rotate, Flip, Straighten & Resize
    def _build_drawer_rotate(self):
        box = self._make_drawer_box()

        # 2x2 grid of compact icon buttons
        tgrid = Gtk.Grid(column_spacing=6, row_spacing=6)
        tgrid.set_column_homogeneous(True)
        box.append(tgrid)

        actions = [
            (t("btn_rot_right"), ["object-rotate-right-symbolic"], lambda _b: self._apply_rotate_90(True)),
            (t("btn_rot_left"), ["object-rotate-left-symbolic"], lambda _b: self._apply_rotate_90(False)),
            (t("btn_flip_h"), ["object-flip-horizontal-symbolic"], lambda _b: self._apply_flip(True)),
            (t("btn_flip_v"), ["object-flip-vertical-symbolic"], lambda _b: self._apply_flip(False)),
        ]
        for idx, (lbl_txt, icons, cb) in enumerate(actions):
            b = Gtk.Button()
            b.add_css_class("sadeem-btn-compact")
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            r.set_halign(Gtk.Align.CENTER)
            ico = Gtk.Image.new_from_icon_name(safe_icon(icons))
            ico.set_pixel_size(14)
            r.append(ico)
            r.append(Gtk.Label(label=lbl_txt))
            b.set_child(r)
            b.connect("clicked", cb)
            tgrid.attach(b, idx % 2, idx // 2, 1, 1)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Fine Straighten slider (-45 to +45)
        st_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        st_lbl = Gtk.Label(label=t("lbl_straighten"))
        st_lbl.add_css_class("drawer-subtle-label")
        st_lbl.set_hexpand(True)
        st_lbl.set_halign(Gtk.Align.START)
        st_hdr.append(st_lbl)
        self.lbl_straighten_val = Gtk.Label(label="0.0°")
        self.lbl_straighten_val.add_css_class("drawer-subtle-label")
        st_hdr.append(self.lbl_straighten_val)
        box.append(st_hdr)

        self.scale_straighten = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -45.0, 45.0, 0.5)
        self.scale_straighten.set_value(0.0)
        self.scale_straighten.set_draw_value(False)
        self.scale_straighten.add_css_class("sadeem-scale")
        self.scale_straighten.connect("value-changed", self._on_straighten_changed)
        box.append(self.scale_straighten)

        btn_apply_rot = Gtk.Button(label=t("btn_apply_straighten"))
        btn_apply_rot.add_css_class("sadeem-btn-compact")
        btn_apply_rot.connect("clicked", lambda _b: self._commit_straighten())
        box.append(btn_apply_rot)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Resize (Width x Height px)
        r_lbl = Gtk.Label(label=t("lbl_resize_dims"))
        r_lbl.add_css_class("drawer-subtle-label")
        r_lbl.set_halign(Gtk.Align.START)
        box.append(r_lbl)

        sz_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        lw = Gtk.Label(label=t("lbl_width"))
        lw.add_css_class("caption")
        lw.set_halign(Gtk.Align.START)
        self.spin_w = Gtk.SpinButton.new_with_range(16, 16384, 10)
        self.spin_w.set_hexpand(True)
        self.spin_w.connect("value-changed", self._on_resize_w_changed)
        sz_grid.attach(lw, 0, 0, 1, 1)
        sz_grid.attach(self.spin_w, 1, 0, 1, 1)

        lh = Gtk.Label(label=t("lbl_height"))
        lh.add_css_class("caption")
        lh.set_halign(Gtk.Align.START)
        self.spin_h = Gtk.SpinButton.new_with_range(16, 16384, 10)
        self.spin_h.set_hexpand(True)
        self.spin_h.connect("value-changed", self._on_resize_h_changed)
        sz_grid.attach(lh, 0, 1, 1, 1)
        sz_grid.attach(self.spin_h, 1, 1, 1, 1)
        box.append(sz_grid)

        self.chk_lock_aspect = Gtk.CheckButton(label=t("chk_lock_aspect"))
        self.chk_lock_aspect.set_active(True)
        box.append(self.chk_lock_aspect)

        btn_resize = Gtk.Button(label=t("btn_apply"))
        btn_resize.add_css_class("sadeem-btn-compact")
        btn_resize.connect("clicked", lambda _b: self._apply_resize())
        box.append(btn_resize)
        return box

    # 3. Drawer: Draw / Markup (Cairo) — compact 2-col tool grid + color dots + thickness
    def _build_drawer_draw(self):
        box = self._make_drawer_box()

        tools_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        tools_grid.set_column_homogeneous(True)
        box.append(tools_grid)

        tools = [
            ("none", "tool_none", ["input-mouse-symbolic", "pan-start-symbolic"]),
            ("freehand", "tool_freehand", ["document-edit-symbolic"]),
            ("highlighter", "tool_highlighter", ["format-text-highlight-symbolic", "edit-select-all-symbolic"]),
            ("arrow", "tool_arrow", ["go-top-symbolic", "mail-forward-symbolic"]),
            ("rect", "tool_rect", ["checkbox-symbolic", "view-grid-symbolic"]),
            ("ellipse", "tool_ellipse", ["radio-symbolic", "media-record-symbolic"]),
            ("text", "tool_text", ["insert-text-symbolic", "font-x-generic-symbolic"]),
            ("blur", "tool_blur", ["view-conceal-symbolic", "security-high-symbolic"]),
        ]
        self.tool_buttons = {}
        for idx, (tid, key, icons) in enumerate(tools):
            btn = Gtk.Button()
            btn.add_css_class("sadeem-btn-compact")
            btn.set_size_request(-1, 32)
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            inner.set_halign(Gtk.Align.CENTER)
            ico = Gtk.Image.new_from_icon_name(safe_icon(icons))
            ico.set_pixel_size(14)
            inner.append(ico)
            inner.append(Gtk.Label(label=t(key)))
            btn.set_child(inner)
            btn.connect("clicked", lambda _b, tool_id=tid: self._select_markup_tool(tool_id))
            tools_grid.attach(btn, idx % 2, idx // 2, 1, 1)
            self.tool_buttons[tid] = btn

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Small circular color dots row
        swatch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        swatch_row.set_halign(Gtk.Align.CENTER)
        self.swatch_buttons = {}
        for idx, (hx, _nm) in enumerate(MARKUP_COLORS):
            sb = Gtk.Button()
            sb.add_css_class("swatch-dot")
            sb.add_css_class(f"swatch-color-{idx}")
            sb.connect("clicked", lambda _b, c=hx: self._select_markup_color(c))
            swatch_row.append(sb)
            self.swatch_buttons[hx] = sb
        box.append(swatch_row)

        # Stroke thickness slider
        th_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        th_lbl = Gtk.Label(label=t("lbl_thickness"))
        th_lbl.add_css_class("drawer-subtle-label")
        th_lbl.set_hexpand(True)
        th_lbl.set_halign(Gtk.Align.START)
        th_hdr.append(th_lbl)
        self.lbl_thick_val = Gtk.Label(label="6 px")
        self.lbl_thick_val.add_css_class("drawer-subtle-label")
        th_hdr.append(self.lbl_thick_val)
        box.append(th_hdr)

        self.scale_thick = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2.0, 40.0, 1.0)
        self.scale_thick.set_value(6.0)
        self.scale_thick.set_draw_value(False)
        self.scale_thick.add_css_class("sadeem-scale")
        self.scale_thick.connect("value-changed", self._on_thickness_changed)
        box.append(self.scale_thick)

        btn_clr = Gtk.Button(label=t("btn_clear_markup"))
        btn_clr.add_css_class("sadeem-btn-danger")
        btn_clr.set_margin_top(4)
        btn_clr.connect("clicked", lambda _b: self._clear_markup())
        box.append(btn_clr)

        # Default tool is "none" (Pan) when not actively drawing
        self._select_markup_tool("none")
        self._select_markup_color("#7a1c33")
        return box

    # 4. Drawer: Light / Adjustments (5 slim sliders + Reset)
    def _build_drawer_light(self):
        box = self._make_drawer_box()

        self.adj_scales = {}
        self.adj_labels = {}
        specs = [
            ("brightness", "adj_brightness", 0.25, 2.0, 1.0, 0.02),
            ("contrast", "adj_contrast", 0.25, 2.0, 1.0, 0.02),
            ("saturation", "adj_saturation", 0.0, 2.2, 1.0, 0.02),
            ("sharpness", "adj_sharpness", 0.0, 3.0, 1.0, 0.05),
            ("warmth", "adj_warmth", -50.0, 50.0, 0.0, 1.0),
        ]
        for key, str_key, vmin, vmax, vdef, step in specs:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            lbl = Gtk.Label(label=t(str_key))
            lbl.add_css_class("drawer-subtle-label")
            lbl.set_hexpand(True)
            lbl.set_halign(Gtk.Align.START)
            row.append(lbl)
            vlbl = Gtk.Label(label="0" if key == "warmth" else "100%")
            vlbl.add_css_class("drawer-subtle-label")
            row.append(vlbl)
            box.append(row)

            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, vmin, vmax, step)
            sc.set_value(vdef)
            sc.set_draw_value(False)
            sc.add_css_class("sadeem-scale")
            sc.connect("value-changed", lambda s, k=key: self._on_adj_slider_changed(k, s.get_value()))
            box.append(sc)
            self.adj_scales[key] = sc
            self.adj_labels[key] = vlbl

        btn_rst = Gtk.Button(label=t("btn_reset_adj"))
        btn_rst.add_css_class("sadeem-btn-compact")
        btn_rst.set_margin_top(6)
        btn_rst.connect("clicked", lambda _b: self._reset_adjustments())
        box.append(btn_rst)
        return box

    # 5. Drawer: Preset Filters (2-col compact grid)
    def _build_drawer_filters(self):
        box = self._make_drawer_box()

        flt_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        flt_grid.set_column_homogeneous(True)
        box.append(flt_grid)

        self.filter_preset_btns = {}
        presets = [
            ("original", "flt_original"),
            ("auto", "flt_auto"),
            ("vivid", "flt_vivid"),
            ("bw", "flt_bw"),
            ("warm", "flt_warm"),
            ("cool", "flt_cool"),
        ]
        for idx, (pid, skey) in enumerate(presets):
            b = Gtk.Button(label=t(skey))
            b.add_css_class("sadeem-btn-compact")
            b.connect("clicked", lambda _b, f=pid: self._select_preset_filter(f))
            flt_grid.attach(b, idx % 2, idx // 2, 1, 1)
            self.filter_preset_btns[pid] = b
        self._highlight_preset_btn("original")
        return box

    # =========================================================================
    # VIEWER LOADING, NAVIGATION & METADATA
    # =========================================================================
    def open_file_directly(self, file_path):
        items, idx = media.list_sibling_images(file_path)
        self.viewer_items = items
        self.viewer_index = idx
        self.root_stack.set_visible_child_name("viewer")
        self._sync_viewer_header_state()
        self._load_viewer_index(idx)

    def open_viewer_from_gallery(self, item, gallery_list):
        self.viewer_items = list(gallery_list)
        idx = 0
        for i, it in enumerate(self.viewer_items):
            if it["path"] == item["path"]:
                idx = i
                break
        self.viewer_index = idx
        self.root_stack.set_visible_child_name("viewer")
        self._sync_viewer_header_state()
        self._load_viewer_index(idx)

    def _navigate_viewer(self, delta):
        if not self.viewer_items or self.edit_mode:
            return
        self.viewer_index = (self.viewer_index + delta) % len(self.viewer_items)
        self._load_viewer_index(self.viewer_index)

    def _ensure_video_player(self):
        if self.video_player_widget is None:
            import video_player
            self.video_player_widget = video_player.VideoPlayerWidget(
                on_edit_requested=lambda p: self._open_video_editor(p)
            )
            self.video_container_box.append(self.video_player_widget)
        return self.video_player_widget

    def _open_video_editor(self, video_path):
        if self.video_player_widget:
            self.video_player_widget.pause()
        launch_video_editor(video_path)

    def open_video_editor_directly(self, video_path):
        self._open_video_editor(video_path)

    def _on_edit_toggle_clicked(self):
        if self.is_current_video:
            self._open_video_editor(self.current_path)
        else:
            self._set_edit_mode(True)

    def _load_viewer_index(self, idx):
        if not self.viewer_items:
            return
        idx = max(0, min(idx, len(self.viewer_items) - 1))
        self.viewer_index = idx
        item = self.viewer_items[idx]
        path = item["path"]
        self.current_path = path
        self.current_is_raw = media.is_raw_file(path)

        self.viewer_title.set_title(item["name"])
        self.viewer_title.set_subtitle(
            t("viewer_counter", cur=idx + 1, total=len(self.viewer_items))
        )
        self.btn_prev_img.set_sensitive(len(self.viewer_items) > 1)
        self.btn_next_img.set_sensitive(len(self.viewer_items) > 1)

        # Video mode branch
        self.is_current_video = item.get("is_video", False) or media.is_video_file(path)
        if self.is_current_video:
            self.viewer_spinner_box.set_visible(False)
            self.canvas.stop_animation()
            self._set_edit_mode(False)
            self._ensure_video_player()
            self.viewer_content_stack.set_visible_child_name("video")
            self.video_player_widget.load_video(path)
            if hasattr(self, "viewer_bottom_bar"):
                self.viewer_bottom_bar.set_visible(False)

            self.btn_slideshow.set_visible(False)
            self.btn_wall.set_visible(False)
            self.btn_exif.set_visible(False)
            self.btn_edit_toggle.set_visible(True)
            self.btn_edit_toggle.set_label(t("video_edit_btn"))
            return

        # Photo mode branch
        if self.video_player_widget:
            self.video_player_widget.stop()
        self.viewer_content_stack.set_visible_child_name("image")
        if hasattr(self, "viewer_bottom_bar"):
            self.viewer_bottom_bar.set_visible(True)
        self.btn_slideshow.set_visible(True)
        self.btn_wall.set_visible(True)
        self.btn_exif.set_visible(True)
        self.btn_edit_toggle.set_visible(True)
        self.btn_edit_toggle.set_label(t("btn_edit"))

        # Reset editor state for newly loaded image
        self._set_edit_mode(False)
        self.history.clear()
        self.strokes = []
        self.adjustments = editor.default_adjustments()
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_adjustment_widgets()

        self._load_generation += 1
        gen = self._load_generation
        self.viewer_spinner_box.set_visible(True)
        self.canvas.stop_animation()

        def _worker():
            try:
                anim_frames = media.load_animated_frames(path)
                if anim_frames:
                    full_img = anim_frames[0][0]
                else:
                    full_img = media.load_full_image(path)
                exif = media.extract_exif_info(path, pil_image=full_img)
                GLib.idle_add(self._on_image_loaded, gen, path, full_img, anim_frames, exif, None)
            except Exception as exc:
                GLib.idle_add(self._on_image_loaded, gen, path, None, None, None, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_image_loaded(self, gen, path, pil_img, anim_frames, exif, err):
        if gen != self._load_generation:
            return False
        self.viewer_spinner_box.set_visible(False)
        if err or pil_img is None:
            self._toast(t("viewer_load_err", err=err or "Unknown"))
            return False

        self.base_image = pil_img
        self.preview_image = pil_img.copy()
        self.current_exif = exif or {}
        self.canvas.set_strokes(self.strokes)
        if anim_frames:
            self.canvas.set_animated_frames(anim_frames)
        else:
            self.canvas.set_pil_image(self.preview_image, reset_view=True)

        self._sync_resize_spins()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()
        return False

    def _update_bottom_meta(self):
        info = dict(self.current_exif)
        if self.base_image is not None:
            info["dimensions"] = f"{self.base_image.width} × {self.base_image.height} px"
        meta_parts = [info.get("dimensions", ""), info.get("filesize", ""), info.get("format", "")]
        self.lbl_viewer_meta.set_text("  •  ".join([p for p in meta_parts if p and p != t("exif_unknown")]))

    def _populate_exif_views(self, info):
        if self.base_image is not None:
            info = dict(info)
            info["dimensions"] = f"{self.base_image.width} × {self.base_image.height} px"

        rows = [
            ("exif_dimensions", info.get("dimensions")),
            ("exif_filesize", info.get("filesize")),
            ("exif_format", info.get("format")),
            ("exif_date", info.get("date")),
            ("exif_camera", info.get("camera")),
            ("exif_lens", info.get("lens")),
            ("exif_aperture", info.get("aperture")),
            ("exif_iso", info.get("iso")),
            ("exif_shutter", info.get("shutter")),
            ("exif_focal", info.get("focal")),
            ("exif_file", info.get("filename")),
        ]

        # Viewer EXIF Popover (Viewer Mode only)
        self._clear_box(self.exif_box)
        hdr = Gtk.Label(label=t("exif_title"))
        hdr.add_css_class("heading")
        hdr.set_halign(Gtk.Align.START)
        self.exif_box.append(hdr)
        self.exif_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        grid = Gtk.Grid(column_spacing=12, row_spacing=5)
        self.exif_box.append(grid)
        for r_idx, (k_str, val) in enumerate(rows):
            kl = Gtk.Label(label=t(k_str))
            kl.set_halign(Gtk.Align.START)
            kl.add_css_class("info-key-lbl")
            vl = Gtk.Label(label=str(val or t("exif_unknown")))
            vl.set_halign(Gtk.Align.START)
            vl.set_wrap(True)
            vl.set_max_width_chars(24)
            vl.set_selectable(True)
            vl.add_css_class("info-val-lbl")
            grid.attach(kl, 0, r_idx, 1, 1)
            grid.attach(vl, 1, r_idx, 1, 1)

    def _on_canvas_zoom_changed(self, pct):
        self.btn_zoom_pct.set_label(f"{pct}%")

    def _toggle_slideshow(self):
        if self.slideshow_timer is not None:
            self._stop_slideshow()
        else:
            if len(self.viewer_items) <= 1 or self.edit_mode:
                return
            self.btn_slideshow.set_icon_name(safe_icon(["media-playback-stop-symbolic"]))
            self.btn_slideshow.set_tooltip_text(t("btn_slideshow_stop"))

            def _advance():
                if self.root_stack.get_visible_child_name() != "viewer" or self.edit_mode:
                    self._stop_slideshow()
                    return False
                self._navigate_viewer(1)
                return True

            self.slideshow_timer = GLib.timeout_add(3500, _advance)

    def _stop_slideshow(self):
        if self.slideshow_timer is not None:
            try:
                GLib.source_remove(self.slideshow_timer)
            except Exception:
                pass
            self.slideshow_timer = None
        self.btn_slideshow.set_icon_name(safe_icon(["media-playback-start-symbolic"]))
        self.btn_slideshow.set_tooltip_text(t("btn_slideshow"))

    def _set_as_wallpaper(self):
        if not self.current_path:
            return
        path = self.current_path
        img_copy = self.base_image.copy() if self.base_image is not None else None

        def _worker():
            try:
                media.set_desktop_wallpaper(path, pil_image=img_copy)
                GLib.idle_add(self._toast, t("wallpaper_set_ok"))
            except Exception as exc:
                GLib.idle_add(self._toast, t("wallpaper_set_err", err=str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # EDITOR MODE & 6-BUTTON RAIL STATE MANAGEMENT
    # =========================================================================
    def _set_edit_mode(self, enabled):
        if enabled and self.base_image is None:
            return
        self.edit_mode = bool(enabled)
        self.editor_panel.set_visible(self.edit_mode)
        self._sync_viewer_header_state()

        if self.edit_mode:
            self._stop_slideshow()
            self.canvas.stop_animation()
            self._refresh_editor_preview()
            self._sync_resize_spins()
            self._update_undo_redo_buttons()
            self._select_rail_section("crop")
        else:
            self.canvas.set_crop_active(False)
            self.canvas.markup_tool = "none"

    def _select_rail_section(self, section_id):
        self.active_rail_section = section_id
        self.drawer_stack.set_visible_child_name(section_id)
        for sid, btn in self.rail_buttons.items():
            if sid == section_id:
                btn.add_css_class("rail-btn-active")
            else:
                btn.remove_css_class("rail-btn-active")

        if section_id == "crop":
            # Auto-enable interactive crop frame upon selecting Crop rail button
            self.canvas.markup_tool = "none"
            self.canvas.set_crop_active(True)
        elif section_id == "draw":
            self.canvas.set_crop_active(False)
            self.canvas.markup_tool = self._selected_markup_tool
        else:
            self.canvas.set_crop_active(False)
            self.canvas.markup_tool = "none"

    def _push_history(self):
        self.history.push(self.base_image, self.strokes, self.adjustments)
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        self.btn_undo.set_sensitive(self.history.can_undo())
        self.btn_redo.set_sensitive(self.history.can_redo())

    def _do_undo(self):
        snap = self.history.undo(self.base_image, self.strokes, self.adjustments)
        if snap is None:
            return
        self.base_image, self.strokes, self.adjustments = snap
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_adjustment_widgets()
        self._sync_resize_spins()
        self.canvas.set_strokes(self.strokes)
        self._refresh_editor_preview()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()
        self._update_undo_redo_buttons()

    def _do_redo(self):
        snap = self.history.redo(self.base_image, self.strokes, self.adjustments)
        if snap is None:
            return
        self.base_image, self.strokes, self.adjustments = snap
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_adjustment_widgets()
        self._sync_resize_spins()
        self.canvas.set_strokes(self.strokes)
        self._refresh_editor_preview()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()
        self._update_undo_redo_buttons()

    def _refresh_editor_preview(self):
        if self.base_image is None:
            return
        img = editor.apply_adjustments_and_filter(self.base_image, self.adjustments)
        for st in self.strokes:
            if st.get("tool") == "blur":
                img = editor.apply_blur_stroke_to_pil(img, st)
        if abs(self.straighten_angle) >= 0.05:
            img = editor.straighten_image(img, self.straighten_angle)
        self.preview_image = img
        self.canvas.set_strokes(self.strokes)
        self.canvas.set_pil_image(self.preview_image, reset_view=False)

    # --- 1. Crop Handlers ---
    def _highlight_ratio_btn(self, active_id):
        for rid, b in self.ratio_buttons.items():
            if rid == active_id:
                b.add_css_class("sadeem-btn-active")
            else:
                b.remove_css_class("sadeem-btn-active")

    def _set_crop_ratio(self, rid, val):
        self._highlight_ratio_btn(rid)
        if not self.canvas.crop_active:
            self.canvas.set_crop_active(True)
        self.canvas.set_crop_aspect(val)

    def _apply_crop(self):
        if self.base_image is None or not self.canvas.crop_active or not self.canvas.crop_rect:
            return
        rect = tuple(self.canvas.crop_rect)
        self._push_history()
        baked = editor.composite_full_image(
            self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle
        )
        self.base_image = editor.crop_image(baked, rect)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self.canvas.reset_crop_rect()
        self.canvas.zoom_fit()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()
        self._toast(t("toast_crop_applied"))

    # --- 2. Rotate, Flip, Straighten & Resize Handlers ---
    def _apply_rotate_90(self, clockwise):
        if self.base_image is None:
            return
        self._push_history()
        baked = editor.composite_full_image(
            self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle
        )
        self.base_image = editor.rotate_90(baked, clockwise=clockwise)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self.canvas.zoom_fit()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()

    def _apply_flip(self, horizontal):
        if self.base_image is None:
            return
        self._push_history()
        baked = editor.composite_full_image(
            self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle
        )
        self.base_image = editor.flip_image(baked, horizontal=horizontal)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._refresh_editor_preview()

    def _on_straighten_changed(self, scale):
        val = scale.get_value()
        self.straighten_angle = val
        self.lbl_straighten_val.set_text(f"{val:+.1f}°")
        self._schedule_debounced_preview()

    def _commit_straighten(self):
        if self.base_image is None or abs(self.straighten_angle) < 0.05:
            return
        self._push_history()
        baked = editor.composite_full_image(
            self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle
        )
        self.base_image = baked
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()

    def _sync_resize_spins(self):
        if self.base_image is None:
            return
        self._syncing_resize_spins = True
        self.spin_w.set_value(self.base_image.width)
        self.spin_h.set_value(self.base_image.height)
        self._syncing_resize_spins = False

    def _on_resize_w_changed(self, spin):
        if self._syncing_resize_spins or self.base_image is None or not self.chk_lock_aspect.get_active():
            return
        aspect = self.base_image.height / max(self.base_image.width, 1)
        self._syncing_resize_spins = True
        self.spin_h.set_value(max(16, int(round(spin.get_value() * aspect))))
        self._syncing_resize_spins = False

    def _on_resize_h_changed(self, spin):
        if self._syncing_resize_spins or self.base_image is None or not self.chk_lock_aspect.get_active():
            return
        aspect = self.base_image.width / max(self.base_image.height, 1)
        self._syncing_resize_spins = True
        self.spin_w.set_value(max(16, int(round(spin.get_value() * aspect))))
        self._syncing_resize_spins = False

    def _apply_resize(self):
        if self.base_image is None:
            return
        nw = int(self.spin_w.get_value())
        nh = int(self.spin_h.get_value())
        self._push_history()
        baked = editor.composite_full_image(
            self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle
        )
        self.base_image = editor.resize_image(baked, nw, nh)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self.canvas.zoom_fit()
        self._populate_exif_views(self.current_exif)
        self._update_bottom_meta()
        self._toast(t("toast_resize_applied", w=nw, h=nh))

    # --- 3. Draw / Markup Handlers ---
    def _select_markup_tool(self, tool_id):
        self._selected_markup_tool = tool_id
        if self.edit_mode and self.active_rail_section == "draw":
            self.canvas.markup_tool = tool_id
        for tid, b in self.tool_buttons.items():
            if tid == tool_id:
                b.add_css_class("sadeem-btn-active")
            else:
                b.remove_css_class("sadeem-btn-active")
        if tool_id == "text" and self.edit_mode:
            self._toast(t("toast_text_hint"))

    def _select_markup_color(self, hex_color):
        self.canvas.markup_color = hex_color
        for hx, sb in self.swatch_buttons.items():
            if hx == hex_color:
                sb.add_css_class("swatch-dot-active")
            else:
                sb.remove_css_class("swatch-dot-active")

    def _on_thickness_changed(self, scale):
        val = int(round(scale.get_value()))
        self.canvas.markup_width = float(val)
        self.lbl_thick_val.set_text(f"{val} px")

    def _on_canvas_stroke_finished(self, stroke):
        self._push_history()
        self.strokes.append(stroke)
        if stroke.get("tool") == "blur":
            self._refresh_editor_preview()
        else:
            self.canvas.set_strokes(self.strokes)
        self._update_undo_redo_buttons()

    def _on_canvas_text_click(self, ix, iy):
        dlg = Adw.Window(transient_for=self, modal=True)
        dlg.set_title(t("text_dialog_title"))
        dlg.set_default_size(380, -1)
        dlg.set_resizable(False)

        tv = Adw.ToolbarView()
        dlg.set_content(tv)
        hb = Adw.HeaderBar()
        hb.set_show_start_title_buttons(False)
        hb.set_show_end_title_buttons(True)
        tv.add_top_bar(hb)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(14)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        tv.set_content(box)

        entry = Gtk.Entry()
        entry.set_placeholder_text(t("text_dialog_placeholder"))
        box.append(entry)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btns.set_halign(Gtk.Align.END)
        box.append(btns)

        b_cancel = Gtk.Button(label=t("btn_cancel"))
        b_cancel.add_css_class("sadeem-btn")
        b_cancel.connect("clicked", lambda _b: dlg.close())
        btns.append(b_cancel)

        b_ok = Gtk.Button(label=t("text_dialog_add"))
        b_ok.add_css_class("sadeem-btn")
        b_ok.add_css_class("sadeem-btn-active")

        def _commit(*_a):
            txt = entry.get_text().strip()
            dlg.close()
            if txt:
                self._push_history()
                self.strokes.append({
                    "tool": "text",
                    "text": txt,
                    "color": self.canvas.markup_color,
                    "width": self.canvas.markup_width,
                    "x1": ix,
                    "y1": iy,
                })
                self.canvas.set_strokes(self.strokes)
                self._update_undo_redo_buttons()

        entry.connect("activate", _commit)
        b_ok.connect("clicked", _commit)
        btns.append(b_ok)
        dlg.present()
        entry.grab_focus()

    def _clear_markup(self):
        if not self.strokes:
            return
        self._push_history()
        self.strokes = []
        self.canvas.set_strokes(self.strokes)
        self._refresh_editor_preview()

    # --- 4 & 5. Light & Filters Handlers ---
    def _schedule_debounced_preview(self):
        if self._adj_debounce_id is not None:
            try:
                GLib.source_remove(self._adj_debounce_id)
            except Exception:
                pass
        self._adj_debounce_id = GLib.timeout_add(45, self._run_debounced_preview)

    def _run_debounced_preview(self):
        self._adj_debounce_id = None
        self._refresh_editor_preview()
        return False

    def _on_adj_slider_changed(self, key, val):
        if self._syncing_adj_widgets:
            return
        self.adjustments[key] = val
        if key == "warmth":
            self.adj_labels[key].set_text(f"{int(round(val)):+d}")
        else:
            self.adj_labels[key].set_text(f"{int(round(val * 100))}%")
        self._schedule_debounced_preview()

    def _sync_adjustment_widgets(self):
        self._syncing_adj_widgets = True
        for key, sc in self.adj_scales.items():
            val = self.adjustments.get(key, 0.0 if key == "warmth" else 1.0)
            sc.set_value(val)
            if key == "warmth":
                self.adj_labels[key].set_text(f"{int(round(val)):+d}")
            else:
                self.adj_labels[key].set_text(f"{int(round(val * 100))}%")
        self._highlight_preset_btn(self.adjustments.get("filter", "original"))
        self._syncing_adj_widgets = False

    def _highlight_preset_btn(self, active_id):
        for pid, b in self.filter_preset_btns.items():
            if pid == active_id:
                b.add_css_class("sadeem-btn-active")
            else:
                b.remove_css_class("sadeem-btn-active")

    def _select_preset_filter(self, preset_id):
        self._push_history()
        self.adjustments["filter"] = preset_id
        self._highlight_preset_btn(preset_id)
        self._refresh_editor_preview()

    def _reset_adjustments(self):
        self._push_history()
        self.adjustments = editor.default_adjustments()
        self._sync_adjustment_widgets()
        self._refresh_editor_preview()

    # =========================================================================
    # SAVE / OVERWRITE / CLIPBOARD
    # =========================================================================
    def _build_final_edited_image(self):
        if self.base_image is None:
            return None
        return editor.composite_full_image(
            self.base_image, self.adjustments, self.strokes, self.straighten_angle
        )

    def _copy_current_to_clipboard(self):
        img = self._build_final_edited_image()
        if img is None:
            return
        try:
            editor.copy_pil_to_clipboard(img, Gdk.Display.get_default())
            self._toast(t("toast_copied"))
        except Exception as exc:
            self._toast(t("toast_copy_err", err=str(exc)))

    def _copy_image_to_clipboard(self, file_path, pil_img=None):
        if pil_img is not None:
            try:
                editor.copy_pil_to_clipboard(pil_img, Gdk.Display.get_default())
            except Exception:
                pass
        if file_path and os.path.isfile(file_path):
            try:
                import shutil, subprocess
                if shutil.which("wl-copy"):
                    with open(file_path, "rb") as f:
                        subprocess.run(["wl-copy", "--type", "image/png"], input=f.read(), check=False)
            except Exception:
                pass

    def _open_save_copy_dialog(self):
        final_img = self._build_final_edited_image()
        if final_img is None or not self.current_path:
            return

        folder = os.path.dirname(os.path.abspath(self.current_path))
        stem, orig_ext = os.path.splitext(os.path.basename(self.current_path))
        default_fmt_idx = 0
        if orig_ext.lower() in (".jpg", ".jpeg"):
            default_fmt_idx = 1
        elif orig_ext.lower() == ".webp":
            default_fmt_idx = 2

        formats = [("PNG", ".png"), ("JPEG", ".jpg"), ("WebP", ".webp")]

        dlg = Adw.Window(transient_for=self, modal=True)
        dlg.set_title(t("save_dialog_title"))
        dlg.set_default_size(420, -1)
        dlg.set_resizable(False)

        tv = Adw.ToolbarView()
        dlg.set_content(tv)
        hb = Adw.HeaderBar()
        hb.set_show_start_title_buttons(False)
        hb.set_show_end_title_buttons(True)
        tv.add_top_bar(hb)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        tv.set_content(box)

        lbl_name = Gtk.Label(label=t("save_dialog_name"))
        lbl_name.add_css_class("drawer-subtle-label")
        lbl_name.set_halign(Gtk.Align.START)
        box.append(lbl_name)

        entry = Gtk.Entry()
        entry.set_text(f"{stem}_edited{formats[default_fmt_idx][1]}")
        box.append(entry)

        lbl_fmt = Gtk.Label(label=t("save_dialog_fmt"))
        lbl_fmt.add_css_class("drawer-subtle-label")
        lbl_fmt.set_halign(Gtk.Align.START)
        box.append(lbl_fmt)

        fmt_list = Gtk.StringList.new([f[0] for f in formats])
        dd_fmt = Gtk.DropDown(model=fmt_list)
        dd_fmt.set_selected(default_fmt_idx)

        def _on_fmt_changed(dd, _ps):
            idx = dd.get_selected()
            if 0 <= idx < len(formats):
                cur_stem = os.path.splitext(entry.get_text().strip())[0] or f"{stem}_edited"
                entry.set_text(cur_stem + formats[idx][1])

        dd_fmt.connect("notify::selected", _on_fmt_changed)
        box.append(dd_fmt)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btns.set_halign(Gtk.Align.END)
        btns.set_margin_top(6)
        box.append(btns)

        b_cancel = Gtk.Button(label=t("btn_cancel"))
        b_cancel.add_css_class("sadeem-btn")
        b_cancel.connect("clicked", lambda _b: dlg.close())
        btns.append(b_cancel)

        b_save = Gtk.Button(label=t("save_dialog_save"))
        b_save.add_css_class("sadeem-btn")
        b_save.add_css_class("sadeem-btn-active")

        def _do_save(*_a):
            idx = dd_fmt.get_selected()
            fmt_name, ext = formats[idx] if 0 <= idx < len(formats) else formats[0]
            fname = entry.get_text().strip() or f"{stem}_edited{ext}"
            if not os.path.splitext(fname)[1]:
                fname += ext
            dest = os.path.join(folder, fname)
            dlg.close()
            try:
                editor.save_pil_image(final_img, dest, fmt=fmt_name)
                self._copy_image_to_clipboard(dest, final_img)
                self._toast(t("toast_saved", name=os.path.basename(dest)))
                self.all_gallery_items = []
            except Exception as exc:
                self._toast(t("toast_save_err", err=str(exc)))

        entry.connect("activate", _do_save)
        b_save.connect("clicked", _do_save)
        btns.append(b_save)
        dlg.present()

    def _confirm_overwrite_original(self):
        if not self.current_path or self.base_image is None:
            return
        if self.current_is_raw:
            self._toast(t("overwrite_raw_note"))
            self._open_save_copy_dialog()
            return

        fname = os.path.basename(self.current_path)
        responses = [
            ("overwrite", t("overwrite_confirm"), Adw.ResponseAppearance.DESTRUCTIVE),
            ("cancel", t("btn_cancel"), Adw.ResponseAppearance.DEFAULT),
        ]

        def _on_resp(rid):
            if rid != "overwrite":
                return
            final_img = self._build_final_edited_image()
            if final_img is None:
                return
            try:
                editor.save_pil_image(final_img, self.current_path)
                self._copy_image_to_clipboard(self.current_path, final_img)
                self.base_image = final_img
                self.strokes = []
                self.adjustments = editor.default_adjustments()
                self.straighten_angle = 0.0
                self.scale_straighten.set_value(0.0)
                self._sync_adjustment_widgets()
                self.history.clear()
                self._update_undo_redo_buttons()
                self._refresh_editor_preview()
                self.all_gallery_items = []
                self._toast(t("toast_saved", name=fname))
            except Exception as exc:
                self._toast(t("toast_save_err", err=str(exc)))

        self._present_alert(t("overwrite_title"), t("overwrite_body", name=fname), responses, _on_resp)


class SadeemGalleryApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )

    def do_startup(self):
        Adw.Application.do_startup(self)
        if i18n.LANG == "ar":
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        else:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
        self._install_css()

    def _install_css(self):
        swatch_rules = []
        for idx, (hx, _name) in enumerate(MARKUP_COLORS):
            swatch_rules.append(f".swatch-color-{idx} {{ background-color: {hx}; background-image: none; }}")
        full_css = SADEEM_CSS + "\n" + "\n".join(swatch_rules)

        prov = Gtk.CssProvider()
        prov.load_from_string(full_css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            local_icons = os.path.abspath(os.path.join(APP_DIR, "..", "icons"))
            if os.path.isdir(local_icons):
                Gtk.IconTheme.get_for_display(display).add_search_path(local_icons)

    def do_activate(self):
        for win in self.get_windows():
            if isinstance(win, SadeemGalleryWindow) and win.root_stack.get_visible_child_name() == "gallery":
                win.present()
                return
        win = SadeemGalleryWindow(self)
        win.open_gallery_mode()
        win.present()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]

        edit_path = None
        open_path = None

        if "--edit" in args:
            idx = args.index("--edit")
            if idx + 1 < len(args):
                edit_path = args[idx + 1]
        else:
            for a in args:
                if a.startswith("--edit="):
                    edit_path = a.split("=", 1)[1]
                    break

        if not edit_path:
            for a in args:
                if not a.startswith("-") and os.path.isfile(a):
                    open_path = a
                    break

        target_path = edit_path or open_path
        is_edit = bool(edit_path)

        if target_path and os.path.isfile(target_path):
            if is_edit and media.is_video_file(target_path):
                launch_video_editor(target_path)
                return 0

            target_real = os.path.realpath(target_path)
            # Focus matching window if already open
            for win in self.get_windows():
                if isinstance(win, SadeemGalleryWindow) and win.current_path:
                    if os.path.realpath(win.current_path) == target_real:
                        if is_edit:
                            win._set_edit_mode(True)
                        win.present()
                        return 0

            # Create new window for distinct file
            win = SadeemGalleryWindow(self)
            if is_edit:
                win.opened_in_edit_mode = True
                win.open_file_directly(target_path)
                win._set_edit_mode(True)
            else:
                win.opened_in_edit_mode = False
                win.open_file_directly(target_path)
            win.present()
            return 0

        # No file specified: focus existing gallery window or open a new one
        for win in self.get_windows():
            if isinstance(win, SadeemGalleryWindow) and win.root_stack.get_visible_child_name() == "gallery":
                win.present()
                return 0

        win = SadeemGalleryWindow(self)
        win.open_gallery_mode()
        win.present()
        return 0


def main():
    GLib.set_prgname(APP_ID)
    app = SadeemGalleryApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
