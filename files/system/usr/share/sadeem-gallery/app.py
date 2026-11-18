#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Gallery — معرض سديم
GTK 4 / Libadwaita chronological photo gallery, fast RAW/image viewer,
and full built-in image editor (Crop & Transform, Cairo Markup, Adjustments & Filters).
Visual Identity: Sadeem Burgundy (#7a1c33), Dark Teal (#0f4c5c), Silver (#e2e8f0).
"""

import concurrent.futures
import copy
import os
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import canvas as canvas_mod
import editor
import i18n
import media

t = i18n.t
APP_ID = "org.sadeem.Gallery"

MARKUP_COLORS = [
    ("#7a1c33", "Burgundy"),
    ("#0f4c5c", "Teal"),
    ("#ef4444", "Red"),
    ("#facc15", "Yellow"),
    ("#22c55e", "Green"),
    ("#ffffff", "White"),
    ("#111827", "Black"),
]

SADEEM_CSS = """
.sadeem-burgundy-btn, button.suggested-action {
    background-color: #7a1c33;
    background-image: none;
    color: #ffffff;
}
.sadeem-burgundy-btn:hover, button.suggested-action:hover {
    background-color: #5c1426;
}
.sadeem-teal-btn {
    background-color: #0f4c5c;
    background-image: none;
    color: #ffffff;
}
.sadeem-teal-btn:hover {
    background-color: #0b3945;
}
.filter-pill-active {
    background-color: #7a1c33;
    color: #ffffff;
    border: 1px solid #be123c;
}
.filter-pill-active label {
    color: #ffffff;
}
.date-section-title {
    font-size: 16px;
    font-weight: 700;
    margin-top: 6px;
    margin-bottom: 4px;
}
.date-count-pill {
    background-color: #0f4c5c;
    color: #e2e8f0;
    border: 1px solid #14b8a6;
    border-radius: 9999px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
}
.thumb-tile {
    padding: 0;
    border-radius: 12px;
    border: 2px solid transparent;
    background-color: alpha(currentColor, 0.06);
}
.thumb-tile:hover {
    border-color: #be123c;
}
.thumb-badge-raw {
    background-color: #7a1c33;
    color: #ffffff;
    border: 1px solid #be123c;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 800;
}
.thumb-badge-anim {
    background-color: #0f4c5c;
    color: #99f6e4;
    border: 1px solid #14b8a6;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 800;
}
.editor-sidebar {
    border-left: 1px solid alpha(currentColor, 0.14);
    border-right: 1px solid alpha(currentColor, 0.14);
}
.editor-section-hdr {
    font-weight: 700;
    font-size: 13px;
    color: #e2e8f0;
    background-color: #0f4c5c;
    border-radius: 8px;
    padding: 5px 10px;
}
.tool-btn-active {
    background-color: #7a1c33;
    color: #ffffff;
    border: 1px solid #be123c;
}
.tool-btn-active label, .tool-btn-active image {
    color: #ffffff;
}
.swatch-btn {
    min-width: 28px;
    min-height: 28px;
    padding: 0;
    border-radius: 9999px;
    border: 2px solid rgba(226, 232, 240, 0.45);
}
.swatch-btn-active {
    border: 3px solid #ffffff;
    box-shadow: 0 0 0 2px #7a1c33;
}
.zoom-readout {
    min-width: 52px;
    font-size: 12px;
    font-weight: 700;
}
.viewer-bottom-bar {
    background-color: alpha(currentColor, 0.04);
    border-top: 1px solid alpha(currentColor, 0.10);
    padding: 6px 12px;
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
        self.set_default_size(1180, 780)
        self.set_size_request(820, 600)

        self.settings = media.load_settings()

        # Gallery state
        self.all_gallery_items = []
        self.active_filter = "all"  # "all", "raw", "animated"
        self.thumb_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._scan_generation = 0

        # Viewer state
        self.viewer_items = []
        self.viewer_index = 0
        self.current_path = None
        self.current_is_raw = False
        self.slideshow_timer = None
        self._load_generation = 0

        # Editor state
        self.edit_mode = False
        self.base_image = None       # Current committed PIL RGBA image
        self.preview_image = None    # Base + adjustments + blur + straighten
        self.adjustments = editor.default_adjustments()
        self.strokes = []
        self.straighten_angle = 0.0
        self.history = editor.EditorHistory(max_steps=25)
        self._adj_debounce_id = None
        self._syncing_resize_spins = False
        self._syncing_adj_widgets = False

        self._install_css()
        self._build_ui()
        self._setup_shortcuts()
        self.connect("close-request", self._on_close_request)

    def _install_css(self):
        # Dynamically add color swatch background rules
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
    # MAIN LAYOUT & HEADER BARS
    # =========================================================================
    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.root_stack = Gtk.Stack()
        self.root_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.root_stack.set_transition_duration(180)
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
        if self.root_stack.get_visible_child_name() != "viewer":
            return False

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
                self._set_edit_mode(False)
                return True
        return False

    # =========================================================================
    # MODE 1: CHRONOLOGICAL GALLERY
    # =========================================================================
    def _build_gallery_view(self):
        tv = Adw.ToolbarView()

        hb = Adw.HeaderBar()
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ico = Gtk.Image.new_from_icon_name("sadeem-gallery")
        ico.set_pixel_size(22)
        title_box.append(ico)
        lbl_t = Gtk.Label(label=t("app_title"))
        lbl_t.add_css_class("heading")
        title_box.append(lbl_t)
        hb.set_title_widget(title_box)

        # Quick filter pills on start side
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.filter_buttons = {}
        for fid, fkey in (("all", "filter_all"), ("raw", "filter_raw"), ("animated", "filter_anim")):
            btn = Gtk.Button(label=t(fkey))
            btn.add_css_class("pill")
            btn.connect("clicked", lambda _b, f=fid: self._set_gallery_filter(f))
            filter_box.append(btn)
            self.filter_buttons[fid] = btn
        hb.pack_start(filter_box)

        # Right/end buttons: Choose Folder + Refresh
        btn_folder = Gtk.Button()
        fb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fb.append(Gtk.Image.new_from_icon_name(safe_icon(["folder-open-symbolic", "folder-symbolic"])))
        fb.append(Gtk.Label(label=t("btn_choose_folder")))
        btn_folder.set_child(fb)
        btn_folder.add_css_class("pill")
        btn_folder.connect("clicked", lambda _b: self._open_folders_dialog())
        hb.pack_end(btn_folder)

        btn_ref = Gtk.Button()
        btn_ref.set_icon_name(safe_icon(["view-refresh-symbolic"]))
        btn_ref.set_tooltip_text(t("btn_refresh"))
        btn_ref.connect("clicked", lambda _b: self.refresh_gallery())
        hb.pack_end(btn_ref)

        tv.add_top_bar(hb)

        # Gallery content stack: loading / empty / timeline
        self.gallery_stack = Gtk.Stack()
        self.gallery_stack.set_vexpand(True)
        tv.set_content(self.gallery_stack)

        # Loading page
        load_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        load_box.set_valign(Gtk.Align.CENTER)
        load_box.set_halign(Gtk.Align.CENTER)
        sp = Gtk.Spinner()
        sp.set_size_request(42, 42)
        sp.set_spinning(True)
        load_box.append(sp)
        l_lbl = Gtk.Label(label=t("gallery_scanning"))
        l_lbl.add_css_class("dim-label")
        load_box.append(l_lbl)
        self.gallery_stack.add_named(load_box, "loading")

        # Empty state page
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        e_ico = Gtk.Image.new_from_icon_name("sadeem-gallery")
        e_ico.set_pixel_size(72)
        empty_box.append(e_ico)
        e_t = Gtk.Label(label=t("gallery_empty_title"))
        e_t.add_css_class("title-2")
        empty_box.append(e_t)
        e_d = Gtk.Label(label=t("gallery_empty_desc"))
        e_d.add_css_class("dim-label")
        e_d.set_wrap(True)
        e_d.set_justify(Gtk.Justification.CENTER)
        empty_box.append(e_d)
        e_btn = Gtk.Button(label=t("btn_choose_folder"))
        e_btn.add_css_class("suggested-action")
        e_btn.add_css_class("pill")
        e_btn.connect("clicked", lambda _b: self._open_folders_dialog())
        empty_box.append(e_btn)
        self.gallery_stack.add_named(empty_box, "empty")

        # Timeline ScrolledWindow
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.timeline_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.timeline_box.set_margin_top(16)
        self.timeline_box.set_margin_bottom(28)
        self.timeline_box.set_margin_start(20)
        self.timeline_box.set_margin_end(20)
        scroll.set_child(self.timeline_box)
        self.gallery_stack.add_named(scroll, "timeline")

        self._update_filter_styles()
        return tv

    def open_gallery_mode(self):
        self._stop_slideshow()
        self.canvas.stop_animation()
        self._set_edit_mode(False)
        self.root_stack.set_visible_child_name("gallery")
        if not self.all_gallery_items:
            self.refresh_gallery()

    def _update_filter_styles(self):
        for fid, btn in self.filter_buttons.items():
            if fid == self.active_filter:
                btn.add_css_class("filter-pill-active")
            else:
                btn.remove_css_class("filter-pill-active")

    def _set_gallery_filter(self, fid):
        self.active_filter = fid
        self._update_filter_styles()
        self._render_gallery_timeline()

    def refresh_gallery(self):
        self._scan_generation += 1
        gen = self._scan_generation
        self.gallery_stack.set_visible_child_name("loading")
        dirs = media.get_scan_directories(self.settings)

        def _worker():
            items = media.scan_directories(dirs)
            GLib.idle_add(self._on_gallery_scanned, gen, items)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_gallery_scanned(self, gen, items):
        if gen != self._scan_generation:
            return False
        self.all_gallery_items = items
        self._render_gallery_timeline()
        return False

    def _get_filtered_items(self):
        if self.active_filter == "raw":
            return [it for it in self.all_gallery_items if it["is_raw"]]
        if self.active_filter == "animated":
            return [it for it in self.all_gallery_items if it["is_animated"]]
        return list(self.all_gallery_items)

    def _render_gallery_timeline(self):
        self._clear_box(self.timeline_box)
        filtered = self._get_filtered_items()
        if not filtered:
            self.gallery_stack.set_visible_child_name("empty")
            return

        groups = media.group_items_by_date(filtered)
        gen = self._scan_generation

        for label, group_items in groups:
            sec = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.timeline_box.append(sec)

            hdr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            lbl = Gtk.Label(label=label)
            lbl.add_css_class("date-section-title")
            lbl.set_halign(Gtk.Align.START)
            hdr_row.append(lbl)

            cnt = Gtk.Label(label=t("gallery_count", count=len(group_items)))
            cnt.add_css_class("date-count-pill")
            cnt.set_valign(Gtk.Align.CENTER)
            hdr_row.append(cnt)
            sec.append(hdr_row)

            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            flow.set_column_spacing(10)
            flow.set_row_spacing(10)
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

        if item["is_raw"]:
            b = Gtk.Label(label=item["ext"].lstrip(".").upper())
            b.add_css_class("thumb-badge-raw")
            b.set_halign(Gtk.Align.END)
            b.set_valign(Gtk.Align.START)
            b.set_margin_top(6)
            b.set_margin_end(6)
            ov.add_overlay(b)
        elif item["is_animated"]:
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

    def _open_folders_dialog(self):
        dlg = Adw.Window(transient_for=self, modal=True)
        dlg.set_title(t("folders_dialog_title"))
        dlg.set_default_size(500, 380)

        tv = Adw.ToolbarView()
        dlg.set_content(tv)
        hb = Adw.HeaderBar()
        hb.set_show_start_title_buttons(False)
        hb.set_show_end_title_buttons(True)
        tv.add_top_bar(hb)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        body.set_margin_top(16)
        body.set_margin_bottom(18)
        body.set_margin_start(18)
        body.set_margin_end(18)
        tv.set_content(body)

        desc = Gtk.Label(label=t("folders_dialog_desc"))
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.START)
        desc.add_css_class("dim-label")
        body.append(desc)

        lb = Gtk.ListBox()
        lb.add_css_class("boxed-list")
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        body.append(lb)

        def _populate():
            child = lb.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                lb.remove(child)
                child = nxt

            def_row = Adw.ActionRow()
            def_row.set_use_markup(False)
            def_row.set_title(t("folders_default_label"))
            def_row.set_subtitle(media.get_default_pictures_dir())
            def_row.add_prefix(Gtk.Image.new_from_icon_name(safe_icon(["folder-pictures-symbolic", "folder-symbolic"])))
            lb.append(def_row)

            for folder in list(self.settings.get("extra_folders", [])):
                row = Adw.ActionRow()
                row.set_use_markup(False)
                row.set_title(os.path.basename(folder.rstrip("/")) or folder)
                row.set_subtitle(folder)
                row.add_prefix(Gtk.Image.new_from_icon_name(safe_icon(["folder-symbolic"])))
                rm = Gtk.Button()
                rm.set_icon_name(safe_icon(["user-trash-symbolic", "list-remove-symbolic"]))
                rm.add_css_class("flat")
                rm.set_valign(Gtk.Align.CENTER)
                rm.set_tooltip_text(t("folders_remove_tip"))

                def _remove(_b, fpath=folder):
                    extras = [x for x in self.settings.get("extra_folders", []) if x != fpath]
                    self.settings["extra_folders"] = extras
                    media.save_settings(self.settings)
                    _populate()
                    self.refresh_gallery()

                rm.connect("clicked", _remove)
                row.add_suffix(rm)
                lb.append(row)

        _populate()

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions.set_halign(Gtk.Align.END)
        actions.set_margin_top(6)
        body.append(actions)

        btn_add = Gtk.Button(label=t("folders_add_btn"))
        btn_add.add_css_class("suggested-action")
        btn_add.add_css_class("pill")

        def _on_add(_b):
            fd = Gtk.FileDialog()
            fd.set_title(t("btn_choose_folder"))

            def _picked(dialog, res):
                try:
                    gfile = dialog.select_folder_finish(res)
                    if gfile:
                        path = gfile.get_path()
                        if path:
                            extras = list(self.settings.get("extra_folders", []))
                            if path not in extras and os.path.abspath(path) != os.path.abspath(media.get_default_pictures_dir()):
                                extras.append(path)
                                self.settings["extra_folders"] = extras
                                media.save_settings(self.settings)
                                _populate()
                                self.refresh_gallery()
                except GLib.Error:
                    pass

            fd.select_folder(dlg, None, _picked)

        btn_add.connect("clicked", _on_add)
        actions.append(btn_add)

        btn_close = Gtk.Button(label=t("folders_close"))
        btn_close.add_css_class("pill")
        btn_close.connect("clicked", lambda _b: dlg.close())
        actions.append(btn_close)

        dlg.present()

    # =========================================================================
    # MODE 2 & 3: FAST VIEWER + INTEGRATED FULL IMAGE EDITOR
    # =========================================================================
    def _build_viewer_and_editor_view(self):
        tv = Adw.ToolbarView()

        # Viewer HeaderBar
        hb = Adw.HeaderBar()

        # Back to Chronological Gallery
        btn_back = Gtk.Button()
        bb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bb.append(Gtk.Image.new_from_icon_name(safe_icon(["view-grid-symbolic", "go-previous-symbolic"])))
        bb.append(Gtk.Label(label=t("btn_back_gallery")))
        btn_back.set_child(bb)
        btn_back.connect("clicked", lambda _b: self.open_gallery_mode())
        hb.pack_start(btn_back)

        # Prev / Next navigation
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        nav_box.add_css_class("linked")
        self.btn_prev_img = Gtk.Button()
        self.btn_prev_img.set_icon_name(safe_icon(["go-previous-symbolic"]))
        self.btn_prev_img.set_tooltip_text(t("btn_prev_img"))
        self.btn_prev_img.connect("clicked", lambda _b: self._navigate_viewer(-1))
        nav_box.append(self.btn_prev_img)

        self.btn_next_img = Gtk.Button()
        self.btn_next_img.set_icon_name(safe_icon(["go-next-symbolic"]))
        self.btn_next_img.set_tooltip_text(t("btn_next_img"))
        self.btn_next_img.connect("clicked", lambda _b: self._navigate_viewer(1))
        nav_box.append(self.btn_next_img)
        hb.pack_start(nav_box)

        # Center title (filename + counter)
        self.viewer_title = Adw.WindowTitle()
        self.viewer_title.set_title(t("app_title"))
        hb.set_title_widget(self.viewer_title)

        # End buttons: Edit Image, EXIF, Wallpaper, Slideshow
        self.btn_edit_toggle = Gtk.Button(label=t("btn_edit"))
        self.btn_edit_toggle.add_css_class("suggested-action")
        self.btn_edit_toggle.add_css_class("pill")
        self.btn_edit_toggle.connect("clicked", lambda _b: self._set_edit_mode(not self.edit_mode))
        hb.pack_end(self.btn_edit_toggle)

        # EXIF Info Popover button
        self.btn_exif = Gtk.MenuButton()
        self.btn_exif.set_icon_name(safe_icon(["dialog-information-symbolic", "help-about-symbolic"]))
        self.btn_exif.set_tooltip_text(t("btn_exif"))
        self.exif_popover = Gtk.Popover()
        self.exif_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.exif_box.set_margin_top(12)
        self.exif_box.set_margin_bottom(12)
        self.exif_box.set_margin_start(14)
        self.exif_box.set_margin_end(14)
        self.exif_box.set_size_request(300, -1)
        self.exif_popover.set_child(self.exif_box)
        self.btn_exif.set_popover(self.exif_popover)
        hb.pack_end(self.btn_exif)

        # Set as Wallpaper button
        btn_wall = Gtk.Button()
        btn_wall.set_icon_name(safe_icon(["preferences-desktop-wallpaper-symbolic", "video-display-symbolic"]))
        btn_wall.set_tooltip_text(t("btn_wallpaper"))
        btn_wall.connect("clicked", lambda _b: self._set_as_wallpaper())
        hb.pack_end(btn_wall)

        # Slideshow button
        self.btn_slideshow = Gtk.Button()
        self.btn_slideshow.set_icon_name(safe_icon(["media-playback-start-symbolic"]))
        self.btn_slideshow.set_tooltip_text(t("btn_slideshow"))
        self.btn_slideshow.connect("clicked", lambda _b: self._toggle_slideshow())
        hb.pack_end(self.btn_slideshow)

        tv.add_top_bar(hb)

        # Main workspace: Canvas (left/main) + Editor Sidebar (right/end, hidden unless edit_mode)
        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_row.set_vexpand(True)
        main_row.set_hexpand(True)
        tv.set_content(main_row)

        # Canvas + Loading Overlay
        canvas_overlay = Gtk.Overlay()
        canvas_overlay.set_hexpand(True)
        canvas_overlay.set_vexpand(True)
        main_row.append(canvas_overlay)

        self.canvas = canvas_mod.ImageCanvas(
            on_zoom_changed=self._on_canvas_zoom_changed,
            on_stroke_finished=self._on_canvas_stroke_finished,
            on_text_click=self._on_canvas_text_click,
        )
        canvas_overlay.set_child(self.canvas)

        self.viewer_spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.viewer_spinner_box.set_halign(Gtk.Align.CENTER)
        self.viewer_spinner_box.set_valign(Gtk.Align.CENTER)
        self.viewer_spinner_box.set_visible(False)
        vsp = Gtk.Spinner()
        vsp.set_size_request(40, 40)
        vsp.set_spinning(True)
        self.viewer_spinner_box.append(vsp)
        vlbl = Gtk.Label(label=t("viewer_loading"))
        vlbl.add_css_class("sadeem-tier-pill")
        self.viewer_spinner_box.append(vlbl)
        canvas_overlay.add_overlay(self.viewer_spinner_box)

        # Integrated Editor Side Panel
        self.editor_panel = self._build_editor_sidebar()
        self.editor_panel.set_visible(False)
        main_row.append(self.editor_panel)

        # Bottom zoom & quick status bar
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom_bar.add_css_class("viewer-bottom-bar")

        self.lbl_viewer_meta = Gtk.Label(label="")
        self.lbl_viewer_meta.add_css_class("caption")
        self.lbl_viewer_meta.add_css_class("dim-label")
        self.lbl_viewer_meta.set_hexpand(True)
        self.lbl_viewer_meta.set_halign(Gtk.Align.START)
        bottom_bar.append(self.lbl_viewer_meta)

        btn_zout = Gtk.Button()
        btn_zout.set_icon_name(safe_icon(["zoom-out-symbolic"]))
        btn_zout.set_tooltip_text(t("btn_zoom_out"))
        btn_zout.add_css_class("flat")
        btn_zout.connect("clicked", lambda _b: self.canvas.zoom_by(1.0 / 1.25))
        bottom_bar.append(btn_zout)

        self.lbl_zoom = Gtk.Label(label="100%")
        self.lbl_zoom.add_css_class("zoom-readout")
        bottom_bar.append(self.lbl_zoom)

        btn_zin = Gtk.Button()
        btn_zin.set_icon_name(safe_icon(["zoom-in-symbolic"]))
        btn_zin.set_tooltip_text(t("btn_zoom_in"))
        btn_zin.add_css_class("flat")
        btn_zin.connect("clicked", lambda _b: self.canvas.zoom_by(1.25))
        bottom_bar.append(btn_zin)

        btn_fit = Gtk.Button(label=t("btn_zoom_fit"))
        btn_fit.add_css_class("pill")
        btn_fit.connect("clicked", lambda _b: self.canvas.zoom_fit())
        bottom_bar.append(btn_fit)

        btn_100 = Gtk.Button(label=t("btn_zoom_100"))
        btn_100.add_css_class("pill")
        btn_100.connect("clicked", lambda _b: self.canvas.zoom_100())
        bottom_bar.append(btn_100)

        tv.add_bottom_bar(bottom_bar)
        return tv

    def _build_editor_sidebar(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.set_size_request(350, -1)
        panel.add_css_class("editor-sidebar")

        # 3-tab switcher bar at top of editor panel
        tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_bar.set_margin_top(10)
        tab_bar.set_margin_bottom(8)
        tab_bar.set_margin_start(10)
        tab_bar.set_margin_end(10)
        tab_bar.set_homogeneous(True)
        panel.append(tab_bar)

        self.editor_stack = Gtk.Stack()
        self.editor_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.editor_stack.set_transition_duration(180)
        self.editor_stack.set_vexpand(True)

        self.editor_tab_buttons = {}
        for tid, key in (("crop", "tab_crop"), ("markup", "tab_markup"), ("adjust", "tab_adjust")):
            b = Gtk.Button(label=t(key))
            b.add_css_class("pill")
            b.connect("clicked", lambda _btn, name=tid: self._select_editor_tab(name))
            tab_bar.append(b)
            self.editor_tab_buttons[tid] = b

        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Scrollable tab contents
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.editor_stack)
        panel.append(scroll)

        self.editor_stack.add_named(self._build_tab_crop(), "crop")
        self.editor_stack.add_named(self._build_tab_markup(), "markup")
        self.editor_stack.add_named(self._build_tab_adjust(), "adjust")

        panel.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Persistent Save / Copy Action Bar
        save_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        save_box.set_margin_top(10)
        save_box.set_margin_bottom(12)
        save_box.set_margin_start(12)
        save_box.set_margin_end(12)
        panel.append(save_box)

        btn_save_copy = Gtk.Button(label=t("btn_save_copy"))
        btn_save_copy.add_css_class("suggested-action")
        btn_save_copy.add_css_class("pill")
        btn_save_copy.connect("clicked", lambda _b: self._open_save_copy_dialog())
        save_box.append(btn_save_copy)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row2.set_homogeneous(True)
        save_box.append(row2)

        btn_over = Gtk.Button(label=t("btn_overwrite"))
        btn_over.add_css_class("destructive-action")
        btn_over.add_css_class("pill")
        btn_over.connect("clicked", lambda _b: self._confirm_overwrite_original())
        row2.append(btn_over)

        btn_clip = Gtk.Button(label=t("btn_copy_clip"))
        btn_clip.add_css_class("sadeem-teal-btn")
        btn_clip.add_css_class("pill")
        btn_clip.connect("clicked", lambda _b: self._copy_current_to_clipboard())
        row2.append(btn_clip)

        self._select_editor_tab("crop")
        return panel

    # --- Editor Tab 1: Crop & Transform ---
    def _build_tab_crop(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(14)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # Interactive Crop Section
        h1 = Gtk.Label(label=t("sec_crop"))
        h1.add_css_class("editor-section-hdr")
        h1.set_xalign(0.0)
        box.append(h1)

        self.btn_crop_toggle = Gtk.ToggleButton(label=t("crop_toggle"))
        self.btn_crop_toggle.add_css_class("pill")
        self.btn_crop_toggle.connect("toggled", self._on_crop_toggled)
        box.append(self.btn_crop_toggle)

        ratio_flow = Gtk.FlowBox()
        ratio_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        ratio_flow.set_row_spacing(6)
        ratio_flow.set_column_spacing(6)
        ratio_flow.set_max_children_per_line(3)
        box.append(ratio_flow)

        self.ratio_buttons = {}
        ratios = [
            ("free", None, "ratio_free"),
            ("1:1", 1.0, "ratio_1_1"),
            ("16:9", 16.0 / 9.0, "ratio_16_9"),
            ("4:3", 4.0 / 3.0, "ratio_4_3"),
            ("9:16", 9.0 / 16.0, "ratio_9_16"),
        ]
        for rid, val, key in ratios:
            rb = Gtk.Button(label=t(key))
            rb.add_css_class("pill")
            rb.connect("clicked", lambda _b, r=rid, v=val: self._set_crop_ratio(r, v))
            ratio_flow.append(rb)
            self.ratio_buttons[rid] = rb
        self._highlight_ratio_btn("free")

        btn_apply_crop = Gtk.Button(label=t("btn_apply_crop"))
        btn_apply_crop.add_css_class("sadeem-teal-btn")
        btn_apply_crop.add_css_class("pill")
        btn_apply_crop.connect("clicked", lambda _b: self._apply_crop())
        box.append(btn_apply_crop)

        # Rotate & Flip Section
        h2 = Gtk.Label(label=t("sec_transform"))
        h2.add_css_class("editor-section-hdr")
        h2.set_xalign(0.0)
        box.append(h2)

        rot_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rot_row.set_homogeneous(True)
        b_rl = Gtk.Button(label=t("btn_rot_left"))
        b_rl.add_css_class("pill")
        b_rl.connect("clicked", lambda _b: self._apply_rotate_90(False))
        rot_row.append(b_rl)
        b_rr = Gtk.Button(label=t("btn_rot_right"))
        b_rr.add_css_class("pill")
        b_rr.connect("clicked", lambda _b: self._apply_rotate_90(True))
        rot_row.append(b_rr)
        box.append(rot_row)

        flip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        flip_row.set_homogeneous(True)
        b_fh = Gtk.Button(label=t("btn_flip_h"))
        b_fh.add_css_class("pill")
        b_fh.connect("clicked", lambda _b: self._apply_flip(True))
        flip_row.append(b_fh)
        b_fv = Gtk.Button(label=t("btn_flip_v"))
        b_fv.add_css_class("pill")
        b_fv.connect("clicked", lambda _b: self._apply_flip(False))
        flip_row.append(b_fv)
        box.append(flip_row)

        # Straighten slider (-45 to +45)
        st_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        st_lbl = Gtk.Label(label=t("lbl_straighten"))
        st_lbl.set_hexpand(True)
        st_lbl.set_halign(Gtk.Align.START)
        st_hdr.append(st_lbl)
        self.lbl_straighten_val = Gtk.Label(label="0°")
        self.lbl_straighten_val.add_css_class("caption")
        st_hdr.append(self.lbl_straighten_val)
        box.append(st_hdr)

        self.scale_straighten = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -45.0, 45.0, 0.5)
        self.scale_straighten.set_value(0.0)
        self.scale_straighten.set_draw_value(False)
        self.scale_straighten.connect("value-changed", self._on_straighten_changed)
        box.append(self.scale_straighten)

        btn_apply_rot = Gtk.Button(label=t("btn_apply_straighten"))
        btn_apply_rot.add_css_class("pill")
        btn_apply_rot.connect("clicked", lambda _b: self._commit_straighten())
        box.append(btn_apply_rot)

        # Resize Section
        h3 = Gtk.Label(label=t("sec_resize"))
        h3.add_css_class("editor-section-hdr")
        h3.set_xalign(0.0)
        box.append(h3)

        sz_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        lw = Gtk.Label(label=t("lbl_width"))
        lw.set_halign(Gtk.Align.START)
        self.spin_w = Gtk.SpinButton.new_with_range(16, 16384, 10)
        self.spin_w.set_hexpand(True)
        self.spin_w.connect("value-changed", self._on_resize_w_changed)
        sz_grid.attach(lw, 0, 0, 1, 1)
        sz_grid.attach(self.spin_w, 1, 0, 1, 1)

        lh = Gtk.Label(label=t("lbl_height"))
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

        btn_resize = Gtk.Button(label=t("btn_apply_resize"))
        btn_resize.add_css_class("pill")
        btn_resize.connect("clicked", lambda _b: self._apply_resize())
        box.append(btn_resize)

        return box

    # --- Editor Tab 2: Markup via Cairo ---
    def _build_tab_markup(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(14)
        box.set_margin_start(12)
        box.set_margin_end(12)

        h1 = Gtk.Label(label=t("sec_tools"))
        h1.add_css_class("editor-section-hdr")
        h1.set_xalign(0.0)
        box.append(h1)

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
            btn.add_css_class("pill")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            inner.set_halign(Gtk.Align.CENTER)
            inner.append(Gtk.Image.new_from_icon_name(safe_icon(icons)))
            inner.append(Gtk.Label(label=t(key)))
            btn.set_child(inner)
            btn.connect("clicked", lambda _b, tool_id=tid: self._select_markup_tool(tool_id))
            tools_grid.attach(btn, idx % 2, idx // 2, 1, 1)
            self.tool_buttons[tid] = btn

        h2 = Gtk.Label(label=t("sec_color"))
        h2.add_css_class("editor-section-hdr")
        h2.set_xalign(0.0)
        box.append(h2)

        swatch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        swatch_row.set_halign(Gtk.Align.CENTER)
        self.swatch_buttons = {}
        for idx, (hx, _nm) in enumerate(MARKUP_COLORS):
            sb = Gtk.Button()
            sb.add_css_class("swatch-btn")
            sb.add_css_class(f"swatch-color-{idx}")
            sb.connect("clicked", lambda _b, c=hx: self._select_markup_color(c))
            swatch_row.append(sb)
            self.swatch_buttons[hx] = sb
        box.append(swatch_row)

        th_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        th_lbl = Gtk.Label(label=t("lbl_thickness"))
        th_lbl.set_hexpand(True)
        th_lbl.set_halign(Gtk.Align.START)
        th_hdr.append(th_lbl)
        self.lbl_thick_val = Gtk.Label(label="6 px")
        self.lbl_thick_val.add_css_class("caption")
        th_hdr.append(self.lbl_thick_val)
        box.append(th_hdr)

        self.scale_thick = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2.0, 40.0, 1.0)
        self.scale_thick.set_value(6.0)
        self.scale_thick.set_draw_value(False)
        self.scale_thick.connect("value-changed", self._on_thickness_changed)
        box.append(self.scale_thick)

        # Undo / Redo / Clear
        ur_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ur_row.set_homogeneous(True)
        self.btn_undo = Gtk.Button(label=t("btn_undo"))
        self.btn_undo.add_css_class("pill")
        self.btn_undo.connect("clicked", lambda _b: self._do_undo())
        ur_row.append(self.btn_undo)

        self.btn_redo = Gtk.Button(label=t("btn_redo"))
        self.btn_redo.add_css_class("pill")
        self.btn_redo.connect("clicked", lambda _b: self._do_redo())
        ur_row.append(self.btn_redo)
        box.append(ur_row)

        btn_clr = Gtk.Button(label=t("btn_clear_markup"))
        btn_clr.add_css_class("pill")
        btn_clr.connect("clicked", lambda _b: self._clear_markup())
        box.append(btn_clr)

        self._select_markup_tool("freehand")
        self._select_markup_color("#7a1c33")
        return box

    # --- Editor Tab 3: Adjustments & Filters ---
    def _build_tab_adjust(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(14)
        box.set_margin_start(12)
        box.set_margin_end(12)

        h1 = Gtk.Label(label=t("sec_adjustments"))
        h1.add_css_class("editor-section-hdr")
        h1.set_xalign(0.0)
        box.append(h1)

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
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            lbl = Gtk.Label(label=t(str_key))
            lbl.set_hexpand(True)
            lbl.set_halign(Gtk.Align.START)
            row.append(lbl)
            vlbl = Gtk.Label(label="0" if key == "warmth" else "100%")
            vlbl.add_css_class("caption")
            row.append(vlbl)
            box.append(row)

            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, vmin, vmax, step)
            sc.set_value(vdef)
            sc.set_draw_value(False)
            sc.connect("value-changed", lambda s, k=key: self._on_adj_slider_changed(k, s.get_value()))
            box.append(sc)
            self.adj_scales[key] = sc
            self.adj_labels[key] = vlbl

        btn_rst = Gtk.Button(label=t("btn_reset_adj"))
        btn_rst.add_css_class("pill")
        btn_rst.connect("clicked", lambda _b: self._reset_adjustments())
        box.append(btn_rst)

        h2 = Gtk.Label(label=t("sec_filters"))
        h2.add_css_class("editor-section-hdr")
        h2.set_xalign(0.0)
        box.append(h2)

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
            b.add_css_class("pill")
            b.connect("clicked", lambda _b, f=pid: self._select_preset_filter(f))
            flt_grid.attach(b, idx % 2, idx // 2, 1, 1)
            self.filter_preset_btns[pid] = b
        self._highlight_preset_btn("original")

        return box

    # =========================================================================
    # VIEWER LOADING & NAVIGATION
    # =========================================================================
    def open_file_directly(self, file_path):
        items, idx = media.list_sibling_images(file_path)
        self.viewer_items = items
        self.viewer_index = idx
        self.root_stack.set_visible_child_name("viewer")
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
        self._load_viewer_index(idx)

    def _navigate_viewer(self, delta):
        if not self.viewer_items or self.edit_mode:
            return
        self.viewer_index = (self.viewer_index + delta) % len(self.viewer_items)
        self._load_viewer_index(self.viewer_index)

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
        self.viewer_title.set_subtitle(f"{idx + 1} / {len(self.viewer_items)}")
        self.btn_prev_img.set_sensitive(len(self.viewer_items) > 1)
        self.btn_next_img.set_sensitive(len(self.viewer_items) > 1)

        # Reset editor state for newly loaded image
        self._set_edit_mode(False)
        self.history.clear()
        self.strokes = []
        self.adjustments = editor.default_adjustments()
        self.straighten_angle = 0.0
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
        self.canvas.set_strokes(self.strokes)
        if anim_frames:
            self.canvas.set_animated_frames(anim_frames)
        else:
            self.canvas.set_pil_image(self.preview_image, reset_view=True)

        self._sync_resize_spins()
        self._populate_exif_popover(exif)
        meta_parts = [exif.get("dimensions", ""), exif.get("filesize", ""), exif.get("format", "")]
        self.lbl_viewer_meta.set_text("  •  ".join([p for p in meta_parts if p]))
        return False

    def _populate_exif_popover(self, info):
        self._clear_box(self.exif_box)
        hdr = Gtk.Label(label=t("exif_title"))
        hdr.add_css_class("heading")
        hdr.set_halign(Gtk.Align.START)
        self.exif_box.append(hdr)
        self.exif_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        rows = [
            ("exif_file", info.get("filename")),
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
            ("exif_folder", info.get("folder")),
        ]
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        self.exif_box.append(grid)
        for r_idx, (k_str, val) in enumerate(rows):
            kl = Gtk.Label(label=t(k_str) + ":")
            kl.set_halign(Gtk.Align.START)
            kl.add_css_class("caption")
            kl.add_css_class("dim-label")
            vl = Gtk.Label(label=str(val or t("exif_unknown")))
            vl.set_halign(Gtk.Align.START)
            vl.set_wrap(True)
            vl.set_max_width_chars(28)
            vl.set_selectable(True)
            vl.add_css_class("caption")
            grid.attach(kl, 0, r_idx, 1, 1)
            grid.attach(vl, 1, r_idx, 1, 1)

    def _on_canvas_zoom_changed(self, pct):
        self.lbl_zoom.set_text(f"{pct}%")

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
    # EDITOR MODE LOGIC
    # =========================================================================
    def _set_edit_mode(self, enabled):
        if enabled and self.base_image is None:
            return
        self.edit_mode = bool(enabled)
        self.editor_panel.set_visible(self.edit_mode)
        self.btn_edit_toggle.set_label(t("btn_done_edit") if self.edit_mode else t("btn_edit"))

        if self.edit_mode:
            self._stop_slideshow()
            self.canvas.stop_animation()
            self._refresh_editor_preview()
            self._sync_resize_spins()
            self._update_undo_redo_buttons()
            self._select_editor_tab("crop")
        else:
            self.canvas.set_crop_active(False)
            self.btn_crop_toggle.set_active(False)
            self.canvas.markup_tool = "none"

    def _select_editor_tab(self, tab_id):
        self.editor_stack.set_visible_child_name(tab_id)
        for tid, btn in self.editor_tab_buttons.items():
            if tid == tab_id:
                btn.add_css_class("filter-pill-active")
            else:
                btn.remove_css_class("filter-pill-active")

        if tab_id == "crop":
            self.canvas.markup_tool = "none"
        elif tab_id == "markup":
            self.canvas.set_crop_active(False)
            self.btn_crop_toggle.set_active(False)
            self.canvas.markup_tool = getattr(self, "_selected_markup_tool", "freehand")
        else:
            self.canvas.set_crop_active(False)
            self.btn_crop_toggle.set_active(False)
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

    # --- Crop & Transform Handlers ---
    def _on_crop_toggled(self, btn):
        self.canvas.set_crop_active(btn.get_active())

    def _highlight_ratio_btn(self, active_id):
        for rid, b in self.ratio_buttons.items():
            if rid == active_id:
                b.add_css_class("tool-btn-active")
            else:
                b.remove_css_class("tool-btn-active")

    def _set_crop_ratio(self, rid, val):
        self._highlight_ratio_btn(rid)
        if not self.btn_crop_toggle.get_active():
            self.btn_crop_toggle.set_active(True)
        self.canvas.set_crop_aspect(val)

    def _apply_crop(self):
        if self.base_image is None or not self.canvas.crop_active or not self.canvas.crop_rect:
            return
        rect = tuple(self.canvas.crop_rect)
        self._push_history()
        # Bake current markup & blur before cropping so coordinates stay exact
        baked = editor.composite_full_image(self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle)
        self.base_image = editor.crop_image(baked, rect)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self.btn_crop_toggle.set_active(False)
        self.canvas.set_crop_active(False)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self.canvas.zoom_fit()
        self._toast(t("toast_crop_applied"))

    def _apply_rotate_90(self, clockwise):
        if self.base_image is None:
            return
        self._push_history()
        baked = editor.composite_full_image(self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle)
        self.base_image = editor.rotate_90(baked, clockwise=clockwise)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self.canvas.zoom_fit()

    def _apply_flip(self, horizontal):
        if self.base_image is None:
            return
        self._push_history()
        baked = editor.composite_full_image(self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle)
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
        baked = editor.composite_full_image(self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle)
        self.base_image = baked
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()

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
        baked = editor.composite_full_image(self.base_image, editor.default_adjustments(), self.strokes, self.straighten_angle)
        self.base_image = editor.resize_image(baked, nw, nh)
        self.strokes = []
        self.straighten_angle = 0.0
        self.scale_straighten.set_value(0.0)
        self._sync_resize_spins()
        self._refresh_editor_preview()
        self.canvas.zoom_fit()
        self._toast(t("toast_resize_applied", w=nw, h=nh))

    # --- Markup Handlers ---
    def _select_markup_tool(self, tool_id):
        self._selected_markup_tool = tool_id
        if self.edit_mode and self.editor_stack.get_visible_child_name() == "markup":
            self.canvas.markup_tool = tool_id
        for tid, b in self.tool_buttons.items():
            if tid == tool_id:
                b.add_css_class("tool-btn-active")
            else:
                b.remove_css_class("tool-btn-active")
        if tool_id == "text" and self.edit_mode:
            self._toast(t("toast_text_hint"))

    def _select_markup_color(self, hex_color):
        self.canvas.markup_color = hex_color
        for hx, sb in self.swatch_buttons.items():
            if hx == hex_color:
                sb.add_css_class("swatch-btn-active")
            else:
                sb.remove_css_class("swatch-btn-active")

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
        dlg.set_default_size(400, -1)
        dlg.set_resizable(False)

        tv = Adw.ToolbarView()
        dlg.set_content(tv)
        hb = Adw.HeaderBar()
        hb.set_show_start_title_buttons(False)
        hb.set_show_end_title_buttons(True)
        tv.add_top_bar(hb)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
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
        b_cancel.add_css_class("pill")
        b_cancel.connect("clicked", lambda _b: dlg.close())
        btns.append(b_cancel)

        b_ok = Gtk.Button(label=t("text_dialog_add"))
        b_ok.add_css_class("suggested-action")
        b_ok.add_css_class("pill")

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

    # --- Adjustments & Filters Handlers ---
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
                b.add_css_class("tool-btn-active")
            else:
                b.remove_css_class("tool-btn-active")

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

    def _open_save_copy_dialog(self):
        final_img = self._build_final_edited_image()
        if final_img is None or not self.current_path:
            return

        folder = os.path.dirname(os.path.abspath(self.current_path))
        stem, orig_ext = os.path.splitext(os.path.basename(self.current_path))
        default_fmt_idx = 0  # PNG
        if orig_ext.lower() in (".jpg", ".jpeg"):
            default_fmt_idx = 1
        elif orig_ext.lower() == ".webp":
            default_fmt_idx = 2

        formats = [("PNG", ".png"), ("JPEG", ".jpg"), ("WebP", ".webp")]

        dlg = Adw.Window(transient_for=self, modal=True)
        dlg.set_title(t("save_dialog_title"))
        dlg.set_default_size(440, -1)
        dlg.set_resizable(False)

        tv = Adw.ToolbarView()
        dlg.set_content(tv)
        hb = Adw.HeaderBar()
        hb.set_show_start_title_buttons(False)
        hb.set_show_end_title_buttons(True)
        tv.add_top_bar(hb)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        tv.set_content(box)

        lbl_name = Gtk.Label(label=t("save_dialog_name"))
        lbl_name.set_halign(Gtk.Align.START)
        box.append(lbl_name)

        entry = Gtk.Entry()
        entry.set_text(f"{stem}_edited{formats[default_fmt_idx][1]}")
        box.append(entry)

        lbl_fmt = Gtk.Label(label=t("save_dialog_fmt"))
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
        b_cancel.add_css_class("pill")
        b_cancel.connect("clicked", lambda _b: dlg.close())
        btns.append(b_cancel)

        b_save = Gtk.Button(label=t("save_dialog_save"))
        b_save.add_css_class("suggested-action")
        b_save.add_css_class("pill")

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
                self._toast(t("toast_saved", name=os.path.basename(dest)))
                self.all_gallery_items = []  # mark gallery for refresh on return
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
                self.base_image = final_img
                self.strokes = []
                self.adjustments = editor.default_adjustments()
                self.straighten_angle = 0.0
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
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.window = None

    def _ensure_window(self):
        if i18n.LANG == "ar":
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        else:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
        if not self.window:
            self.window = SadeemGalleryWindow(self)
        return self.window

    def do_activate(self):
        win = self._ensure_window()
        win.open_gallery_mode()
        win.present()

    def do_open(self, files, n_files, _hint):
        win = self._ensure_window()
        target = None
        for gfile in files:
            p = gfile.get_path()
            if p and os.path.isfile(p):
                target = p
                break
        if target:
            win.open_file_directly(target)
        else:
            win.open_gallery_mode()
        win.present()


def main():
    GLib.set_prgname(APP_ID)
    app = SadeemGalleryApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
