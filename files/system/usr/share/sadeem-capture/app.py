#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Capture — أداة لقطة سديم الموحدة
GTK 4 / Libadwaita screen capture tool replacing GNOME 51 built-in screenshot.
Supports Selection, Screen, and Window modes with Wayland D-Bus integration,
cursor/halo toggles, clipboard copy, and seamless sadeem-gallery editing handoff.
"""

import math
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
import cairo
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

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
.sadeem-toolbar-card {
    background-color: rgba(28, 28, 35, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 9999px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
    padding: 6px 14px;
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
    border-radius: 9999px;
    border: 1px solid transparent;
    color: #cbd5e1;
    padding: 5px 14px;
    font-size: 13px;
    font-weight: 500;
}
.sadeem-mode-btn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}
.sadeem-mode-btn.active {
    background-color: #7a1c33;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.22);
}
.sadeem-mode-btn.active:hover {
    background-color: #8c223c;
}
.sadeem-tool-btn {
    background-color: rgba(255, 255, 255, 0.06);
    background-image: none;
    border-radius: 9999px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #cbd5e1;
    min-width: 38px;
    min-height: 38px;
    padding: 0;
}
.sadeem-tool-btn:hover {
    background-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
}
.sadeem-tool-btn.active {
    background-color: #7a1c33;
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.25);
}
.sadeem-tool-btn.active:hover {
    background-color: #8c223c;
}
.sadeem-tool-btn:disabled {
    opacity: 0.35;
}
.sadeem-shutter-btn {
    background-color: #7a1c33;
    background-image: none;
    border-radius: 9999px;
    border: 2.5px solid #ffffff;
    min-width: 48px;
    min-height: 48px;
    color: #ffffff;
    box-shadow: 0 0 14px rgba(122, 28, 51, 0.7);
    padding: 0;
}
.sadeem-shutter-btn:hover {
    background-color: #8c223c;
}
.sadeem-shutter-btn:active {
    background-color: #631528;
}
.sadeem-close-btn {
    background-color: rgba(255, 255, 255, 0.06);
    background-image: none;
    border-radius: 9999px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #cbd5e1;
    min-width: 38px;
    min-height: 38px;
    padding: 0;
}
.sadeem-close-btn:hover {
    background-color: rgba(239, 68, 68, 0.75);
    color: #ffffff;
    border-color: rgba(239, 68, 68, 0.9);
}
.sadeem-media-toggle {
    background-color: rgba(0, 0, 0, 0.4);
    border-radius: 9999px;
    padding: 2px;
    border: 1px solid rgba(255, 255, 255, 0.08);
}
.sadeem-media-btn {
    background-color: transparent;
    background-image: none;
    border-radius: 9999px;
    border: 1px solid transparent;
    color: #cbd5e1;
    padding: 4px 10px;
    font-size: 12px;
}
.sadeem-media-btn.active {
    background-color: #2e2e38;
    color: #ffffff;
}
"""


class SadeemCaptureWindow(Gtk.Window):
    def __init__(self, app, initial_mode="selection"):
        super().__init__(application=app)
        self.app = app
        self.client = app.client
        self.mode = initial_mode  # "selection", "screen", "window"
        self.cursor_enabled = True
        self.halo_enabled = False
        self.media_type = "photo"  # "photo" or "video"

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
        self.set_child(self.overlay)

        # 1. Canvas drawing area
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_vexpand(True)
        self.drawing_area.set_draw_func(self._on_draw)
        self.overlay.set_child(self.drawing_area)

        # 2. Toast overlay for user feedback (Phase 2 note, etc.)
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_hexpand(True)
        self.toast_overlay.set_vexpand(True)
        self.toast_overlay.set_child(Gtk.Box())  # Empty container

        # 3. Floating Bottom Toolbar
        self.toolbar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.toolbar_box.set_halign(Gtk.Align.CENTER)
        self.toolbar_box.set_valign(Gtk.Align.END)
        self.toolbar_box.set_margin_bottom(36)
        self.toolbar_box.add_css_class("sadeem-toolbar-card")

        # Row 1: Mode Switcher (Selection, Screen, Window)
        row_modes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_modes.set_halign(Gtk.Align.CENTER)
        row_modes.add_css_class("sadeem-pill-group")

        self.btn_mode_sel = Gtk.Button(label=f" {t('mode_selection')}")
        self.btn_mode_sel.set_icon_name("edit-select-all-symbolic")
        self.btn_mode_sel.add_css_class("sadeem-mode-btn")
        self.btn_mode_sel.connect("clicked", lambda _b: self._set_mode("selection"))

        self.btn_mode_screen = Gtk.Button(label=f" {t('mode_screen')}")
        self.btn_mode_screen.set_icon_name("video-display-symbolic")
        self.btn_mode_screen.add_css_class("sadeem-mode-btn")
        self.btn_mode_screen.connect("clicked", lambda _b: self._set_mode("screen"))

        self.btn_mode_win = Gtk.Button(label=f" {t('mode_window')}")
        self.btn_mode_win.set_icon_name("preferences-system-windows-symbolic")
        self.btn_mode_win.add_css_class("sadeem-mode-btn")
        self.btn_mode_win.connect("clicked", lambda _b: self._set_mode("window"))

        row_modes.append(self.btn_mode_sel)
        row_modes.append(self.btn_mode_screen)
        row_modes.append(self.btn_mode_win)
        self.toolbar_box.append(row_modes)

        # Row 2: Controls (Cursor, Halo, Shutter, Media Pill, Close)
        row_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_controls.set_halign(Gtk.Align.CENTER)

        # Cursor Toggle
        self.btn_cursor = Gtk.Button()
        self.btn_cursor.set_icon_name("input-mouse-symbolic")
        self.btn_cursor.set_tooltip_text(t("tooltip_cursor"))
        self.btn_cursor.add_css_class("sadeem-tool-btn")
        self.btn_cursor.add_css_class("active")
        self.btn_cursor.connect("clicked", self._toggle_cursor)
        row_controls.append(self.btn_cursor)

        # Cursor Halo Toggle
        self.btn_halo = Gtk.Button()
        self.btn_halo.set_icon_name("weather-clear-symbolic")
        self.btn_halo.set_tooltip_text(t("tooltip_halo"))
        self.btn_halo.add_css_class("sadeem-tool-btn")
        self.btn_halo.connect("clicked", self._toggle_halo)
        row_controls.append(self.btn_halo)

        # Shutter Capture Button (Center highlight)
        self.btn_shutter = Gtk.Button()
        self.btn_shutter.set_icon_name("camera-photo-symbolic")
        self.btn_shutter.set_tooltip_text(t("btn_capture"))
        self.btn_shutter.add_css_class("sadeem-shutter-btn")
        self.btn_shutter.connect("clicked", lambda _b: self._trigger_capture())
        row_controls.append(self.btn_shutter)

        # Photo / Video segmented switch
        media_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        media_box.add_css_class("sadeem-media-toggle")

        self.btn_photo = Gtk.Button(label=t("tab_photo"))
        self.btn_photo.add_css_class("sadeem-media-btn")
        self.btn_photo.add_css_class("active")
        self.btn_photo.connect("clicked", lambda _b: self._set_media_type("photo"))

        self.btn_video = Gtk.Button(label=t("tab_video"))
        self.btn_video.add_css_class("sadeem-media-btn")
        self.btn_video.connect("clicked", lambda _b: self._set_media_type("video"))

        media_box.append(self.btn_photo)
        media_box.append(self.btn_video)
        row_controls.append(media_box)

        # Cancel / Close Button
        self.btn_close = Gtk.Button()
        self.btn_close.set_icon_name("window-close-symbolic")
        self.btn_close.set_tooltip_text(t("tooltip_close"))
        self.btn_close.add_css_class("sadeem-close-btn")
        self.btn_close.connect("clicked", lambda _b: self.app.quit())
        row_controls.append(self.btn_close)

        self.toolbar_box.append(row_controls)

        # Add toolbar to overlay
        self.overlay.add_overlay(self.toolbar_box)
        self.overlay.add_overlay(self.toast_overlay)

        self._update_mode_ui()

    def _setup_events(self):
        # Keyboard shortcuts
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        # Motion tracking
        motion_ctrl = Gtk.EventControllerMotion()
        motion_ctrl.connect("motion", self._on_motion)
        self.drawing_area.add_controller(motion_ctrl)

        # Drag gesture for area selection
        self.drag_gesture = Gtk.GestureDrag()
        self.drag_gesture.connect("drag-begin", self._on_drag_begin)
        self.drag_gesture.connect("drag-update", self._on_drag_update)
        self.drag_gesture.connect("drag-end", self._on_drag_end)
        self.drawing_area.add_controller(self.drag_gesture)

        # Click gesture for window / screen capture
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", self._on_click_released)
        self.drawing_area.add_controller(click_gesture)

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.app.quit()
            return True
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._trigger_capture()
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
            # Fetch active window list via D-Bus
            self.windows = self.client.list_windows()
        self.drawing_area.queue_draw()

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

        # Halo is disabled in window mode or when cursor is disabled
        if self.mode == "window" or not self.cursor_enabled:
            self.btn_halo.set_sensitive(False)
            self.halo_enabled = False
            self.btn_halo.remove_css_class("active")
        else:
            self.btn_halo.set_sensitive(True)

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

    def _set_media_type(self, mtype):
        if mtype == "video":
            # Video recording notification for Phase 2
            toast = Adw.Toast.new(t("video_phase2_note"))
            toast.set_timeout(3)
            self.toast_overlay.add_toast(toast)
            return
        self.media_type = "photo"
        self.btn_photo.add_css_class("active")
        self.btn_video.remove_css_class("active")

    # --- Mouse & Gestures Handling ---
    def _on_motion(self, _ctrl, x, y):
        self.pointer_x = x
        self.pointer_y = y
        if self.mode == "window":
            # Check which window contains pointer
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
        self.drawing_area.queue_draw()

    def _on_drag_end(self, _gesture, _offset_x, _offset_y):
        if self.mode != "selection":
            return
        self.is_dragging = False
        self.drawing_area.queue_draw()

    def _on_click_released(self, _gesture, n_press, x, y):
        # Ignore clicks inside toolbar
        tb_alloc = self.toolbar_box.get_allocation()
        if (
            tb_alloc.x <= x <= tb_alloc.x + tb_alloc.width
            and tb_alloc.y <= y <= tb_alloc.y + tb_alloc.height
        ):
            return

        if self.mode == "window" and self.hovered_window:
            self._trigger_capture(target_win=self.hovered_window)
        elif self.mode == "screen":
            self._trigger_capture()

    # --- Cairo Canvas Drawing ---
    def _on_draw(self, _area, cr, width, height):
        # 1. Base translucent scrim
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.35)
        cr.paint()

        if self.mode == "selection":
            self._draw_selection(cr, width, height)
        elif self.mode == "screen":
            self._draw_screen_highlight(cr, width, height)
        elif self.mode == "window":
            self._draw_window_highlight(cr, width, height)

    def _draw_selection(self, cr, width, height):
        if self.sel_w > 4 and self.sel_h > 4:
            # Cut-out transparent hole in scrim
            cr.save()
            cr.rectangle(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.fill()
            cr.restore()

            # Selection bounding border (Sadeem Turquoise #06b6d4)
            cr.set_source_rgba(0.024, 0.714, 0.831, 0.95)
            cr.set_line_width(2.0)
            cr.rectangle(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            cr.stroke()

            # Corner and edge resize handles
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

            # Dimension badge pill e.g. "1920 × 1080"
            dim_str = f"{int(self.sel_w)} × {int(self.sel_h)}"
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(12.0)
            extents = cr.text_extents(dim_str)

            badge_w = extents.width + 16
            badge_h = 24
            badge_x = self.sel_x + 8
            badge_y = self.sel_y - 30 if self.sel_y > 36 else self.sel_y + self.sel_h + 8

            # Draw badge background
            cr.set_source_rgba(0.09, 0.09, 0.12, 0.9)
            self._draw_rounded_rect(cr, badge_x, badge_y, badge_w, badge_h, 6)
            cr.fill_preserve()
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.2)
            cr.set_line_width(1.0)
            cr.stroke()

            # Draw dimension text
            cr.set_source_rgba(0.95, 0.96, 0.98, 1.0)
            cr.move_to(badge_x + 8, badge_y + 16)
            cr.show_text(dim_str)
        else:
            # Hint text when no selection yet
            hint = t("select_hint")
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(14.0)
            extents = cr.text_extents(hint)
            cr.set_source_rgba(0.9, 0.92, 0.96, 0.85)
            cr.move_to((width - extents.width) / 2, 80)
            cr.show_text(hint)

    def _draw_screen_highlight(self, cr, width, height):
        # Subtle inset highlight border around entire screen
        cr.set_source_rgba(0.024, 0.714, 0.831, 0.85)
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

            # Clear hole
            cr.save()
            cr.rectangle(wx, wy, ww, wh)
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.fill()
            cr.restore()

            # Highlight border
            cr.set_source_rgba(0.024, 0.714, 0.831, 0.95)
            cr.set_line_width(2.5)
            self._draw_rounded_rect(cr, wx, wy, ww, wh, 8)
            cr.stroke()

            # Window Title Badge
            if title:
                cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(12.0)
                display_title = title if len(title) <= 45 else title[:42] + "..."
                extents = cr.text_extents(display_title)

                badge_w = extents.width + 18
                badge_h = 26
                badge_x = wx + 12
                badge_y = wy + 12

                cr.set_source_rgba(0.09, 0.09, 0.12, 0.92)
                self._draw_rounded_rect(cr, badge_x, badge_y, badge_w, badge_h, 6)
                cr.fill_preserve()
                cr.set_source_rgba(0.024, 0.714, 0.831, 0.8)
                cr.set_line_width(1.0)
                cr.stroke()

                cr.set_source_rgba(0.95, 0.96, 0.98, 1.0)
                cr.move_to(badge_x + 9, badge_y + 17)
                cr.show_text(display_title)
        else:
            hint = t("window_hint")
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(14.0)
            extents = cr.text_extents(hint)
            cr.set_source_rgba(0.9, 0.92, 0.96, 0.85)
            cr.move_to((width - extents.width) / 2, 80)
            cr.show_text(hint)

    def _draw_rounded_rect(self, cr, x, y, w, h, r):
        deg = math.pi / 180.0
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -90 * deg, 0 * deg)
        cr.arc(x + w - r, y + h - r, r, 0 * deg, 90 * deg)
        cr.arc(x + r, y + h - r, r, 90 * deg, 180 * deg)
        cr.arc(x + r, y + r, r, 180 * deg, 270 * deg)
        cr.close_path()

    # --- Execution & Handoff Pipeline ---
    def _trigger_capture(self, target_win=None):
        # 1. Hide the overlay window completely before grabbing pixels
        self.set_visible(False)

        # 2. Wait 80ms for compositor flush, then execute capture
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 80, self._do_execute_capture, target_win)

    def _do_execute_capture(self, target_win=None):
        dest_path = generate_screenshot_path()

        # Turn on halo if requested
        if self.halo_enabled:
            self.client.set_halo_active(True)

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
                    # Fallback to full screen if no area selected
                    success = self.client.capture_screen(self.cursor_enabled, dest_path)
            elif self.mode == "screen":
                success = self.client.capture_screen(self.cursor_enabled, dest_path)
            elif self.mode == "window":
                if self.hovered_window:
                    win_id = self.hovered_window.get("id", 0)
                    success = self.client.capture_window(win_id, True, self.cursor_enabled, dest_path)
                else:
                    success = self.client.capture_screen(self.cursor_enabled, dest_path)
        finally:
            if self.halo_enabled:
                self.client.set_halo_active(False)

        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            copy_file_to_clipboard(dest_path)
            launch_gallery_editor(dest_path)

        self.app.quit()
        return GLib.SOURCE_REMOVE


class SadeemCaptureApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.client = CaptureClient()
        self.window = None

    def _load_styles(self):
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

    def do_activate(self):
        self._load_styles()
        if not self.window:
            self.window = SadeemCaptureWindow(self)
        self.window.fullscreen()
        self.window.present()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]

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

        initial_mode = "selection"
        if "--screen" in args:
            initial_mode = "screen"
        elif "--window" in args:
            initial_mode = "window"
        elif "--area" in args or "--selection" in args:
            initial_mode = "selection"

        self._load_styles()
        self.window = SadeemCaptureWindow(self, initial_mode=initial_mode)
        self.window.fullscreen()
        self.window.present()
        return 0


def main():
    # Handle instant --window-id outside of GUI loop for instantaneous response
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
