#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Libadwaita / GTK 4 Video Editor UI for Sadeem Gallery.
Features:
- Fast multi-track timeline (trim in/out handles, audio mute intervals, annotation timing).
- Real-time video preview with crop handles and vector markup overlay (pen, arrow, rect, text).
- 4 focused editing tabs: Trim, Crop, Audio (full/partial mute), Markup annotations.
- Stream-copy fast export with live progress bar and atomic save/overwrite.
"""

import copy
import math
import os
import tempfile
import threading

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango, PangoCairo
from PIL import Image

import editor
import i18n
import video_editor_engine
import video_utils

t = i18n.t

MARKUP_COLORS = [
    ("#7a1c33", "Burgundy"),
    ("#06b6d4", "Cyan"),
    ("#ef4444", "Red"),
    ("#facc15", "Yellow"),
    ("#22c55e", "Green"),
    ("#ffffff", "White"),
    ("#111827", "Black"),
]


def safe_icon(names, fallback="document-edit-symbolic"):
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        for name in names:
            if theme.has_icon(name):
                return name
    return fallback


class VideoEditorView(Adw.ToolbarView):
    """
    Integrated video editing view with full preview, multi-rail controls,
    and responsive interactive timeline.
    """

    def __init__(self, window, video_path, on_close=None, on_saved=None):
        super().__init__()
        self.window = window
        self.video_path = video_path
        self.on_close_cb = on_close
        self.on_saved_cb = on_saved

        # Probe metadata
        self.meta = video_utils.get_video_metadata(video_path)
        self.duration_sec = max(0.1, self.meta.get("duration", 0.0))
        self.video_w = max(1, self.meta.get("width", 1280))
        self.video_h = max(1, self.meta.get("height", 720))

        # Editor State
        self.active_tab = "trim"  # "trim", "crop", "audio", "markup"
        self.trim_start = 0.0
        self.trim_end = self.duration_sec
        self.crop_box = None  # (x, y, w, h) in video coordinates
        self.mute_all = False
        self.mute_ranges = []  # list of (s, e)
        self.strokes = []
        self.overlay_start = 0.0
        self.overlay_end = self.duration_sec

        # Markup tool state
        self.markup_tool = "pen"  # "pen", "arrow", "rect", "text"
        self.markup_color = "#7a1c33"
        self.markup_width = 4.0
        self.current_stroke = None

        # Crop interaction state
        self.crop_active_handle = None
        self.crop_drag_start = None

        # Playback & timeline state
        self.media_stream = None
        self.is_playing = False
        self.current_time = 0.0
        self.poll_timer_id = None
        self.timeline_drag_mode = None  # "in", "out", "playhead"

        # Undo / Redo history
        self.history = []
        self.redo_stack = []
        self.has_unsaved_changes = False

        self._build_ui()
        self._load_video()
        self._push_history()

    def _build_ui(self):
        # 1. HeaderBar
        hb = Adw.HeaderBar()

        # START: Back / Done button
        btn_back = Gtk.Button()
        b_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        b_box.append(Gtk.Image.new_from_icon_name(safe_icon(["go-previous-symbolic"])))
        b_box.append(Gtk.Label(label=t("btn_back_gallery")))
        btn_back.set_child(b_box)
        btn_back.add_css_class("sadeem-btn-compact")
        btn_back.connect("clicked", lambda _b: self._request_close())
        hb.pack_start(btn_back)

        # Undo / Redo buttons
        ur_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        ur_box.add_css_class("linked")
        self.btn_undo = Gtk.Button()
        self.btn_undo.set_icon_name(safe_icon(["edit-undo-symbolic"]))
        self.btn_undo.set_tooltip_text(t("btn_undo"))
        self.btn_undo.connect("clicked", lambda _b: self._undo())
        ur_box.append(self.btn_undo)

        self.btn_redo = Gtk.Button()
        self.btn_redo.set_icon_name(safe_icon(["edit-redo-symbolic"]))
        self.btn_redo.set_tooltip_text(t("btn_redo"))
        self.btn_redo.connect("clicked", lambda _b: self._redo())
        ur_box.append(self.btn_redo)
        hb.pack_start(ur_box)

        # TITLE: Filename + Editor subtitle
        title = Adw.WindowTitle()
        title.set_title(os.path.basename(self.video_path))
        title.set_subtitle(t("video_editor_title"))
        hb.set_title_widget(title)

        # END: Save MenuButton
        btn_save_menu = Gtk.MenuButton()
        sm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sm_box.append(Gtk.Image.new_from_icon_name(safe_icon(["document-save-symbolic"])))
        sm_box.append(Gtk.Label(label=t("btn_save_changes")))
        btn_save_menu.set_child(sm_box)
        btn_save_menu.add_css_class("sadeem-btn-compact")
        btn_save_menu.add_css_class("sadeem-btn-active")

        pop = Gtk.Popover()
        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pop_box.set_margin_top(6)
        pop_box.set_margin_bottom(6)
        pop_box.set_margin_start(6)
        pop_box.set_margin_end(6)
        pop.set_child(pop_box)

        for label_k, icon_n, cb, danger in (
            ("btn_save_copy", ["document-save-as-symbolic"], self._on_save_copy_clicked, False),
            ("btn_overwrite", ["document-save-symbolic"], self._on_overwrite_clicked, True),
        ):
            b = Gtk.Button()
            b.add_css_class("flat")
            if danger:
                b.add_css_class("destructive-action")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.append(Gtk.Image.new_from_icon_name(safe_icon(icon_n)))
            lbl = Gtk.Label(label=t(label_k))
            lbl.set_halign(Gtk.Align.START)
            row.append(lbl)
            b.set_child(row)

            def _act(_btn, func=cb):
                pop.popdown()
                func()

            b.connect("clicked", _act)
            pop_box.append(b)

        btn_save_menu.set_popover(pop)
        hb.pack_end(btn_save_menu)
        self.add_top_bar(hb)

        # 2. Main Horizontal Workspace
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main_box.set_vexpand(True)
        main_box.set_hexpand(True)
        self.set_content(main_box)

        # LEFT WORKSPACE: Preview + Timeline (75%)
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left_box.set_hexpand(True)
        left_box.set_vexpand(True)
        main_box.append(left_box)

        # Video Preview Overlay
        self.preview_overlay = Gtk.Overlay()
        self.preview_overlay.set_hexpand(True)
        self.preview_overlay.set_vexpand(True)
        self.preview_overlay.add_css_class("sadeem-canvas-bg")
        left_box.append(self.preview_overlay)

        self.video_widget = Gtk.Video()
        self.video_widget.set_hexpand(True)
        self.video_widget.set_vexpand(True)
        self.preview_overlay.set_child(self.video_widget)

        # Canvas overlay for Crop & Markup
        self.overlay_canvas = Gtk.DrawingArea()
        self.overlay_canvas.set_can_target(True)
        self.overlay_canvas.set_draw_func(self._draw_overlay_canvas)

        drag_gesture = Gtk.GestureDrag()
        drag_gesture.connect("drag-begin", self._on_canvas_drag_begin)
        drag_gesture.connect("drag-update", self._on_canvas_drag_update)
        drag_gesture.connect("drag-end", self._on_canvas_drag_end)
        self.overlay_canvas.add_controller(drag_gesture)

        click_gesture = Gtk.GestureClick()
        click_gesture.connect("released", self._on_canvas_clicked)
        self.overlay_canvas.add_controller(click_gesture)

        self.preview_overlay.add_overlay(self.overlay_canvas)

        # TIMELINE & CONTROLS CONTAINER
        timeline_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        timeline_container.add_css_class("video-timeline-container")
        timeline_container.set_margin_start(16)
        timeline_container.set_margin_end(16)
        timeline_container.set_margin_bottom(12)
        timeline_container.set_margin_top(6)
        left_box.append(timeline_container)

        # Playback Row: Play/Pause, Time readout, Quick Jump
        pb_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        pb_row.set_halign(Gtk.Align.CENTER)

        self.btn_pb_play = Gtk.Button()
        self.btn_pb_play.add_css_class("video-btn-play")
        self.btn_pb_play.set_icon_name(safe_icon(["media-playback-start-symbolic"]))
        self.btn_pb_play.connect("clicked", lambda _b: self.toggle_play())
        pb_row.append(self.btn_pb_play)

        self.lbl_pb_time = Gtk.Label(label="00:00 / 00:00")
        self.lbl_pb_time.add_css_class("video-time-lbl")
        pb_row.append(self.lbl_pb_time)

        btn_jump_start = Gtk.Button()
        btn_jump_start.add_css_class("sadeem-header-btn")
        btn_jump_start.set_icon_name(safe_icon(["go-first-symbolic", "go-previous-symbolic"]))
        btn_jump_start.set_tooltip_text(t("video_jump_in"))
        btn_jump_start.connect("clicked", lambda _b: self.seek_to(self.trim_start))
        pb_row.append(btn_jump_start)

        btn_jump_end = Gtk.Button()
        btn_jump_end.add_css_class("sadeem-header-btn")
        btn_jump_end.set_icon_name(safe_icon(["go-last-symbolic", "go-next-symbolic"]))
        btn_jump_end.set_tooltip_text(t("video_jump_out"))
        btn_jump_end.connect("clicked", lambda _b: self.seek_to(self.trim_end))
        pb_row.append(btn_jump_end)

        timeline_container.append(pb_row)

        # Multi-Track Visual Timeline (DrawingArea)
        self.timeline_area = Gtk.DrawingArea()
        self.timeline_area.set_size_request(-1, 52)
        self.timeline_area.set_draw_func(self._draw_timeline)
        self.timeline_area.set_can_target(True)

        tl_drag = Gtk.GestureDrag()
        tl_drag.connect("drag-begin", self._on_timeline_drag_begin)
        tl_drag.connect("drag-update", self._on_timeline_drag_update)
        tl_drag.connect("drag-end", self._on_timeline_drag_end)
        self.timeline_area.add_controller(tl_drag)

        tl_click = Gtk.GestureClick()
        tl_click.connect("pressed", self._on_timeline_click)
        self.timeline_area.add_controller(tl_click)

        timeline_container.append(self.timeline_area)

        # RIGHT WORKSPACE: Tool Sidebar (300px)
        self.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.sidebar_box.set_size_request(298, -1)
        self.sidebar_box.add_css_class("editor-drawer")
        main_box.append(self.sidebar_box)

        # Mode Tab Bar (Trim, Crop, Audio, Markup)
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_box.set_margin_top(10)
        tab_box.set_margin_bottom(10)
        tab_box.set_margin_start(10)
        tab_box.set_margin_end(10)
        tab_box.add_css_class("linked")
        self.sidebar_box.append(tab_box)

        self.tab_btns = {}
        for mode_id, lbl_key, icon_name in (
            ("trim", "vtab_trim", "edit-cut-symbolic"),
            ("crop", "vtab_crop", "zoom-fit-best-symbolic"),
            ("audio", "vtab_audio", "audio-volume-high-symbolic"),
            ("markup", "vtab_markup", "document-edit-symbolic"),
        ):
            b = Gtk.Button()
            b.add_css_class("sadeem-btn-compact")
            b.set_hexpand(True)
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            r.set_halign(Gtk.Align.CENTER)
            r.append(Gtk.Image.new_from_icon_name(safe_icon([icon_name])))
            lbl = Gtk.Label(label=t(lbl_key))
            r.append(lbl)
            b.set_child(r)
            b.connect("clicked", lambda _btn, m=mode_id: self._select_tab(m))
            tab_box.append(b)
            self.tab_btns[mode_id] = b

        # Tab Stack Content
        self.tab_stack = Gtk.Stack()
        self.tab_stack.set_vexpand(True)
        self.sidebar_box.append(self.tab_stack)

        self.tab_stack.add_named(self._build_trim_panel(), "trim")
        self.tab_stack.add_named(self._build_crop_panel(), "crop")
        self.tab_stack.add_named(self._build_audio_panel(), "audio")
        self.tab_stack.add_named(self._build_markup_panel(), "markup")

        self._select_tab("trim")

        # 3. Export Progress Banner (Hidden by default)
        self.progress_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.progress_banner.add_css_class("video-progress-banner")
        self.progress_banner.set_margin_start(16)
        self.progress_banner.set_margin_end(16)
        self.progress_banner.set_margin_bottom(12)
        self.progress_banner.set_visible(False)

        self.export_progress_bar = Gtk.ProgressBar()
        self.export_progress_bar.set_hexpand(True)
        self.export_progress_bar.set_show_text(True)
        self.progress_banner.append(self.export_progress_bar)

        self.btn_cancel_export = Gtk.Button(label=t("btn_cancel"))
        self.btn_cancel_export.add_css_class("sadeem-btn-compact")
        self.progress_banner.append(self.btn_cancel_export)
        left_box.append(self.progress_banner)

    # -------------------------------------------------------------------------
    # TAB PANELS
    # -------------------------------------------------------------------------
    def _build_trim_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_start(14)
        box.set_margin_end(14)

        lbl = Gtk.Label(label=t("vtrim_heading"))
        lbl.add_css_class("drawer-section-title")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        # In Point
        r_in = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_in = Gtk.Label(label=t("vtrim_start"))
        lbl_in.set_hexpand(True)
        lbl_in.set_halign(Gtk.Align.START)
        r_in.append(lbl_in)
        self.lbl_in_val = Gtk.Label(label="00:00.0")
        self.lbl_in_val.add_css_class("dim-label")
        r_in.append(self.lbl_in_val)
        btn_set_in = Gtk.Button(label=t("vtrim_set_cur"))
        btn_set_in.add_css_class("sadeem-btn-compact")
        btn_set_in.connect("clicked", lambda _b: self._set_trim_in_current())
        r_in.append(btn_set_in)
        box.append(r_in)

        # Out Point
        r_out = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_out = Gtk.Label(label=t("vtrim_end"))
        lbl_out.set_hexpand(True)
        lbl_out.set_halign(Gtk.Align.START)
        r_out.append(lbl_out)
        self.lbl_out_val = Gtk.Label(label=video_utils.format_duration(self.duration_sec))
        self.lbl_out_val.add_css_class("dim-label")
        r_out.append(self.lbl_out_val)
        btn_set_out = Gtk.Button(label=t("vtrim_set_cur"))
        btn_set_out.add_css_class("sadeem-btn-compact")
        btn_set_out.connect("clicked", lambda _b: self._set_trim_out_current())
        r_out.append(btn_set_out)
        box.append(r_out)

        # Reset button
        btn_reset = Gtk.Button(label=t("vtrim_reset"))
        btn_reset.add_css_class("sadeem-btn")
        btn_reset.connect("clicked", lambda _b: self._reset_trim())
        box.append(btn_reset)

        return box

    def _build_crop_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_start(14)
        box.set_margin_end(14)

        lbl = Gtk.Label(label=t("vcrop_heading"))
        lbl.add_css_class("drawer-section-title")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)
        box.append(grid)

        ratios = [
            ("free", t("crop_free")),
            ("16_9", "16:9"),
            ("4_3", "4:3"),
            ("1_1", "1:1"),
            ("9_16", "9:16"),
        ]
        for idx, (cid, clbl) in enumerate(ratios):
            b = Gtk.Button(label=clbl)
            b.add_css_class("sadeem-btn-compact")
            b.connect("clicked", lambda _b, r=cid: self._apply_crop_preset(r))
            grid.attach(b, idx % 2, idx // 2, 1, 1)

        btn_reset = Gtk.Button(label=t("crop_reset"))
        btn_reset.add_css_class("sadeem-btn")
        btn_reset.connect("clicked", lambda _b: self._reset_crop())
        box.append(btn_reset)

        return box

    def _build_audio_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_start(14)
        box.set_margin_end(14)

        lbl = Gtk.Label(label=t("vaudio_heading"))
        lbl.add_css_class("drawer-section-title")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        # Mute All Switch
        mute_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        m_lbl = Gtk.Label(label=t("vaudio_mute_all"))
        m_lbl.set_hexpand(True)
        m_lbl.set_halign(Gtk.Align.START)
        mute_row.append(m_lbl)
        self.sw_mute_all = Gtk.Switch()
        self.sw_mute_all.set_active(False)
        self.sw_mute_all.connect("notify::active", self._on_mute_all_toggled)
        mute_row.append(self.sw_mute_all)
        box.append(mute_row)

        sep = Gtk.Separator()
        box.append(sep)

        # Partial Mute Section
        p_lbl = Gtk.Label(label=t("vaudio_partial_mute"))
        p_lbl.add_css_class("drawer-subtle-label")
        p_lbl.set_halign(Gtk.Align.START)
        box.append(p_lbl)

        btn_add_mute = Gtk.Button(label=t("vaudio_add_mute_range"))
        btn_add_mute.add_css_class("sadeem-btn-compact")
        btn_add_mute.connect("clicked", lambda _b: self._add_mute_range())
        box.append(btn_add_mute)

        self.mute_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.mute_list_box)

        return box

    def _build_markup_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_start(14)
        box.set_margin_end(14)

        lbl = Gtk.Label(label=t("vmarkup_heading"))
        lbl.add_css_class("drawer-section-title")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        # Tools row (pen, arrow, rect, text)
        tools_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tools_row.add_css_class("linked")
        box.append(tools_row)

        self.markup_tool_btns = {}
        for tid, ico, tooltip in (
            ("pen", "document-edit-symbolic", t("markup_pen")),
            ("arrow", "go-next-symbolic", t("markup_arrow")),
            ("rect", "edit-select-symbolic", t("markup_rect")),
            ("text", "font-x-generic-symbolic", t("markup_text")),
        ):
            b = Gtk.Button()
            b.set_icon_name(safe_icon([ico]))
            b.set_tooltip_text(tooltip)
            b.add_css_class("sadeem-btn-compact")
            b.connect("clicked", lambda _btn, t_id=tid: self._select_markup_tool(t_id))
            tools_row.append(b)
            self.markup_tool_btns[tid] = b

        # Color Palette
        col_lbl = Gtk.Label(label=t("markup_color"))
        col_lbl.add_css_class("drawer-subtle-label")
        col_lbl.set_halign(Gtk.Align.START)
        box.append(col_lbl)

        swatches_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.append(swatches_row)
        for idx, (hx, _name) in enumerate(MARKUP_COLORS):
            sb = Gtk.Button()
            sb.add_css_class("swatch-dot")
            sb.add_css_class(f"swatch-color-{idx}")
            sb.connect("clicked", lambda _b, col=hx: self._set_markup_color(col))
            swatches_row.append(sb)

        # Timing Section (when overlay appears)
        t_lbl = Gtk.Label(label=t("vmarkup_timing"))
        t_lbl.add_css_class("drawer-subtle-label")
        t_lbl.set_halign(Gtk.Align.START)
        box.append(t_lbl)

        btn_set_ov_in = Gtk.Button(label=t("vtrim_set_cur"))
        btn_set_ov_in.add_css_class("sadeem-btn-compact")
        btn_set_ov_in.connect("clicked", lambda _b: self._set_overlay_start_current())
        box.append(btn_set_ov_in)

        btn_clear_markup = Gtk.Button(label=t("markup_clear"))
        btn_clear_markup.add_css_class("sadeem-btn")
        btn_clear_markup.connect("clicked", lambda _b: self._clear_markup())
        box.append(btn_clear_markup)

        return box

    def _select_tab(self, tab_id):
        self.active_tab = tab_id
        for tid, b in self.tab_btns.items():
            if tid == tab_id:
                b.add_css_class("sadeem-btn-active")
            else:
                b.remove_css_class("sadeem-btn-active")
        self.tab_stack.set_visible_child_name(tab_id)
        self.overlay_canvas.queue_draw()

    # -------------------------------------------------------------------------
    # VIDEO PLAYBACK & TIMELINE
    # -------------------------------------------------------------------------
    def _load_video(self):
        self.video_widget.set_filename(self.video_path)
        self.media_stream = self.video_widget.get_media_stream()
        if self.media_stream:
            self.media_stream.connect("notify::playing", self._on_stream_playing)
            self.media_stream.connect("notify::ended", self._on_stream_ended)

        self._start_poll_timer()
        self._update_time_display()

    def _start_poll_timer(self):
        self._stop_poll_timer()
        self.poll_timer_id = GLib.timeout_add(80, self._on_poll_tick)

    def _stop_poll_timer(self):
        if self.poll_timer_id is not None:
            GLib.source_remove(self.poll_timer_id)
            self.poll_timer_id = None

    def _on_poll_tick(self):
        if not self.media_stream or self.timeline_drag_mode:
            return True
        ts = self.media_stream.get_timestamp() / 1_000_000.0
        if abs(ts - self.current_time) > 0.05:
            self.current_time = ts
            self._update_time_display()
            self.timeline_area.queue_draw()
            self.overlay_canvas.queue_draw()
        return True

    def _on_stream_playing(self, stream, _p):
        self.is_playing = stream.get_playing()
        icon = "media-playback-pause-symbolic" if self.is_playing else "media-playback-start-symbolic"
        self.btn_pb_play.set_icon_name(safe_icon([icon]))

    def _on_stream_ended(self, stream, _p):
        if stream.get_ended():
            self.seek_to(self.trim_start)
            self.pause()

    def toggle_play(self):
        if not self.media_stream:
            return
        if self.media_stream.get_playing():
            self.pause()
        else:
            self.play()

    def play(self):
        if self.media_stream:
            self.media_stream.play()

    def pause(self):
        if self.media_stream:
            self.media_stream.pause()

    def seek_to(self, sec):
        if not self.media_stream:
            return
        sec = max(0.0, min(self.duration_sec, float(sec)))
        self.current_time = sec
        self._update_time_display()
        self.timeline_area.queue_draw()
        self.overlay_canvas.queue_draw()
        try:
            self.media_stream.seek(int(sec * 1_000_000))
        except Exception:
            pass

    def _update_time_display(self):
        cur_str = video_utils.format_duration(self.current_time)
        dur_str = video_utils.format_duration(self.duration_sec)
        self.lbl_pb_time.set_text(f"{cur_str} / {dur_str}")

    # -------------------------------------------------------------------------
    # TIMELINE DRAWING & INTERACTION
    # -------------------------------------------------------------------------
    def _draw_timeline(self, area, cr, width, height):
        # Background track
        cr.set_source_rgb(0.12, 0.12, 0.15)
        cr.paint()

        dur = max(0.1, self.duration_sec)

        # Draw audio mute intervals
        for ms, me in self.mute_ranges:
            x1 = (ms / dur) * width
            x2 = (me / dur) * width
            cr.set_source_rgba(0.94, 0.27, 0.27, 0.35)
            cr.rectangle(x1, 0, max(2, x2 - x1), height)
            cr.fill()

        # Draw overlay annotation segment
        if self.strokes:
            ox1 = (self.overlay_start / dur) * width
            ox2 = (self.overlay_end / dur) * width
            cr.set_source_rgba(0.02, 0.71, 0.83, 0.30)
            cr.rectangle(ox1, height - 10, max(2, ox2 - ox1), 8)
            cr.fill()

        # Dim areas outside trim
        x_in = (self.trim_start / dur) * width
        x_out = (self.trim_end / dur) * width

        cr.set_source_rgba(0.0, 0.0, 0.0, 0.65)
        if x_in > 0:
            cr.rectangle(0, 0, x_in, height)
            cr.fill()
        if x_out < width:
            cr.rectangle(x_out, 0, width - x_out, height)
            cr.fill()

        # Trim active bar
        cr.set_source_rgb(0.48, 0.11, 0.20)
        cr.set_line_width(2.0)
        cr.rectangle(x_in, 0, x_out - x_in, height)
        cr.stroke()

        # In handle (left)
        cr.set_source_rgb(0.95, 0.96, 0.98)
        cr.rectangle(x_in - 4, 0, 8, height)
        cr.fill()
        cr.set_source_rgb(0.48, 0.11, 0.20)
        cr.rectangle(x_in - 1, 8, 2, height - 16)
        cr.fill()

        # Out handle (right)
        cr.set_source_rgb(0.95, 0.96, 0.98)
        cr.rectangle(x_out - 4, 0, 8, height)
        cr.fill()
        cr.set_source_rgb(0.48, 0.11, 0.20)
        cr.rectangle(x_out - 1, 8, 2, height - 16)
        cr.fill()

        # Playhead (cursor)
        x_cur = (self.current_time / dur) * width
        cr.set_source_rgb(0.06, 0.72, 0.85)
        cr.set_line_width(2.0)
        cr.move_to(x_cur, 0)
        cr.line_to(x_cur, height)
        cr.stroke()

        # Playhead top triangle
        cr.move_to(x_cur - 5, 0)
        cr.line_to(x_cur + 5, 0)
        cr.line_to(x_cur, 7)
        cr.close_path()
        cr.fill()

    def _on_timeline_click(self, gesture, _n, x, _y):
        width = self.timeline_area.get_width()
        if width <= 0:
            return
        dur = max(0.1, self.duration_sec)
        target_t = max(0.0, min(self.duration_sec, (x / width) * dur))
        self.seek_to(target_t)

    def _on_timeline_drag_begin(self, gesture, start_x, _start_y):
        width = self.timeline_area.get_width()
        if width <= 0:
            return
        dur = max(0.1, self.duration_sec)
        x_in = (self.trim_start / dur) * width
        x_out = (self.trim_end / dur) * width

        if abs(start_x - x_in) < 12:
            self.timeline_drag_mode = "in"
        elif abs(start_x - x_out) < 12:
            self.timeline_drag_mode = "out"
        else:
            self.timeline_drag_mode = "playhead"
            self.seek_to((start_x / width) * dur)

    def _on_timeline_drag_update(self, gesture, offset_x, _offset_y):
        start_x, _ = gesture.get_start_point()
        cur_x = start_x + offset_x
        width = self.timeline_area.get_width()
        if width <= 0:
            return
        dur = max(0.1, self.duration_sec)
        t_sec = max(0.0, min(self.duration_sec, (cur_x / width) * dur))

        if self.timeline_drag_mode == "in":
            self.trim_start = min(t_sec, self.trim_end - 0.2)
            self.lbl_in_val.set_text(video_utils.format_duration(self.trim_start))
        elif self.timeline_drag_mode == "out":
            self.trim_end = max(t_sec, self.trim_start + 0.2)
            self.lbl_out_val.set_text(video_utils.format_duration(self.trim_end))
        elif self.timeline_drag_mode == "playhead":
            self.seek_to(t_sec)

        self.timeline_area.queue_draw()

    def _on_timeline_drag_end(self, gesture, _offset_x, _offset_y):
        self.timeline_drag_mode = None
        self._push_history()

    # -------------------------------------------------------------------------
    # OVERLAY CANVAS (CROP & MARKUP DRAWING)
    # -------------------------------------------------------------------------
    def _get_video_viewport_rect(self):
        w = self.overlay_canvas.get_width()
        h = self.overlay_canvas.get_height()
        if w <= 0 or h <= 0 or self.video_w <= 0 or self.video_h <= 0:
            return 0, 0, w, h, 1.0

        scale = min(w / self.video_w, h / self.video_h)
        vw = self.video_w * scale
        vh = self.video_h * scale
        vx = (w - vw) / 2.0
        vy = (h - vh) / 2.0
        return vx, vy, vw, vh, scale

    def _draw_overlay_canvas(self, area, cr, width, height):
        vx, vy, vw, vh, scale = self._get_video_viewport_rect()

        # 1. Draw Crop Rect & Handles if active
        if self.crop_box:
            cx, cy, cw, ch = self.crop_box
            rcx = vx + cx * scale
            rcy = vy + cy * scale
            rcw = cw * scale
            rch = ch * scale

            # Dim outside crop
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.rectangle(0, 0, width, rcy)
            cr.rectangle(0, rcy + rch, width, height - (rcy + rch))
            cr.rectangle(0, rcy, rcx, rch)
            cr.rectangle(rcx + rcw, rcy, width - (rcx + rcw), rch)
            cr.fill()

            # Crop border & rule of thirds
            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.set_line_width(2.0)
            cr.rectangle(rcx, rcy, rcw, rch)
            cr.stroke()

            # Corner handles
            handle_size = 10.0
            cr.set_source_rgb(0.48, 0.11, 0.20)
            for hx, hy in (
                (rcx, rcy),
                (rcx + rcw, rcy),
                (rcx, rcy + rch),
                (rcx + rcw, rcy + rch),
            ):
                cr.rectangle(hx - handle_size / 2, hy - handle_size / 2, handle_size, handle_size)
                cr.fill()

        # 2. Draw Markup Vector Overlay if within timing window
        if self.strokes and (self.overlay_start <= self.current_time <= self.overlay_end):
            cr.save()
            cr.translate(vx, vy)
            for s in self.strokes:
                editor.draw_stroke_on_cairo(cr, s, scale_factor=scale)
            cr.restore()

        # 3. Draw live stroke in progress
        if self.current_stroke:
            cr.save()
            cr.translate(vx, vy)
            editor.draw_stroke_on_cairo(cr, self.current_stroke, scale_factor=scale)
            cr.restore()

    def _on_canvas_drag_begin(self, gesture, start_x, start_y):
        vx, vy, vw, vh, scale = self._get_video_viewport_rect()
        if scale <= 0:
            return

        img_x = (start_x - vx) / scale
        img_y = (start_y - vy) / scale

        if self.active_tab == "crop":
            if not self.crop_box:
                self.crop_box = [0, 0, self.video_w, self.video_h]
            self.crop_drag_start = (img_x, img_y, copy.deepcopy(self.crop_box))
        elif self.active_tab == "markup":
            self.current_stroke = {
                "tool": self.markup_tool,
                "color": self.markup_color,
                "width": self.markup_width,
                "x1": img_x,
                "y1": img_y,
                "x2": img_x,
                "y2": img_y,
                "points": [(img_x, img_y)],
            }

    def _on_canvas_drag_update(self, gesture, offset_x, offset_y):
        vx, vy, vw, vh, scale = self._get_video_viewport_rect()
        if scale <= 0:
            return

        start_x, start_y = gesture.get_start_point()
        cur_x = (start_x + offset_x - vx) / scale
        cur_y = (start_y + offset_y - vy) / scale

        if self.active_tab == "crop" and self.crop_drag_start:
            _, _, init_box = self.crop_drag_start
            x1 = min(init_box[0], cur_x)
            y1 = min(init_box[1], cur_y)
            x2 = max(init_box[0] + init_box[2], cur_x)
            y2 = max(init_box[1] + init_box[3], cur_y)
            self.crop_box = [max(0, x1), max(0, y1), min(self.video_w - x1, x2 - x1), min(self.video_h - y1, y2 - y1)]
            self.overlay_canvas.queue_draw()

        elif self.active_tab == "markup" and self.current_stroke:
            if self.markup_tool in ("pen", "freehand"):
                self.current_stroke["points"].append((cur_x, cur_y))
            else:
                self.current_stroke["x2"] = cur_x
                self.current_stroke["y2"] = cur_y
            self.overlay_canvas.queue_draw()

    def _on_canvas_drag_end(self, gesture, _offset_x, _offset_y):
        if self.active_tab == "crop":
            self.crop_drag_start = None
            self._push_history()
        elif self.active_tab == "markup" and self.current_stroke:
            self.strokes.append(self.current_stroke)
            self.current_stroke = None
            self.overlay_canvas.queue_draw()
            self._push_history()

    def _on_canvas_clicked(self, gesture, n_press, x, y):
        if n_press == 1 and self.active_tab not in ("crop", "markup"):
            self.toggle_play()

    # -------------------------------------------------------------------------
    # ACTIONS & PRESETS
    # -------------------------------------------------------------------------
    def _set_trim_in_current(self):
        self.trim_start = min(self.current_time, self.trim_end - 0.2)
        self.lbl_in_val.set_text(video_utils.format_duration(self.trim_start))
        self.timeline_area.queue_draw()
        self._push_history()

    def _set_trim_out_current(self):
        self.trim_end = max(self.current_time, self.trim_start + 0.2)
        self.lbl_out_val.set_text(video_utils.format_duration(self.trim_end))
        self.timeline_area.queue_draw()
        self._push_history()

    def _reset_trim(self):
        self.trim_start = 0.0
        self.trim_end = self.duration_sec
        self.lbl_in_val.set_text("00:00.0")
        self.lbl_out_val.set_text(video_utils.format_duration(self.duration_sec))
        self.timeline_area.queue_draw()
        self._push_history()

    def _apply_crop_preset(self, ratio_id):
        vw, vh = self.video_w, self.video_h
        if ratio_id == "free":
            self.crop_box = [0, 0, vw, vh]
        elif ratio_id == "16_9":
            target_r = 16.0 / 9.0
            if vw / vh > target_r:
                cw = int(vh * target_r)
                self.crop_box = [(vw - cw) // 2, 0, cw, vh]
            else:
                ch = int(vw / target_r)
                self.crop_box = [0, (vh - ch) // 2, vw, ch]
        elif ratio_id == "4_3":
            target_r = 4.0 / 3.0
            if vw / vh > target_r:
                cw = int(vh * target_r)
                self.crop_box = [(vw - cw) // 2, 0, cw, vh]
            else:
                ch = int(vw / target_r)
                self.crop_box = [0, (vh - ch) // 2, vw, ch]
        elif ratio_id == "1_1":
            side = min(vw, vh)
            self.crop_box = [(vw - side) // 2, (vh - side) // 2, side, side]
        elif ratio_id == "9_16":
            target_r = 9.0 / 16.0
            cw = min(vw, int(vh * target_r))
            ch = int(cw / target_r)
            self.crop_box = [(vw - cw) // 2, (vh - ch) // 2, cw, ch]

        self.overlay_canvas.queue_draw()
        self._push_history()

    def _reset_crop(self):
        self.crop_box = None
        self.overlay_canvas.queue_draw()
        self._push_history()

    def _on_mute_all_toggled(self, sw, _p):
        self.mute_all = sw.get_active()
        self.timeline_area.queue_draw()
        self._push_history()

    def _add_mute_range(self):
        # Default mute interval: 2 seconds from current position
        s = self.current_time
        e = min(self.duration_sec, s + 2.0)
        self.mute_ranges.append((s, e))
        self._refresh_mute_list()
        self.timeline_area.queue_draw()
        self._push_history()

    def _refresh_mute_list(self):
        child = self.mute_list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.mute_list_box.remove(child)
            child = nxt

        for idx, (ms, me) in enumerate(self.mute_ranges):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            s_str = video_utils.format_duration(ms)
            e_str = video_utils.format_duration(me)
            lbl = Gtk.Label(label=f"{s_str} ➔ {e_str}")
            lbl.set_hexpand(True)
            lbl.set_halign(Gtk.Align.START)
            row.append(lbl)

            btn_del = Gtk.Button()
            btn_del.set_icon_name(safe_icon(["user-trash-symbolic"]))
            btn_del.add_css_class("flat")
            btn_del.connect("clicked", lambda _b, i=idx: self._remove_mute_range(i))
            row.append(btn_del)
            self.mute_list_box.append(row)

    def _remove_mute_range(self, idx):
        if 0 <= idx < len(self.mute_ranges):
            self.mute_ranges.pop(idx)
            self._refresh_mute_list()
            self.timeline_area.queue_draw()
            self._push_history()

    def _select_markup_tool(self, tid):
        self.markup_tool = tid
        for k, b in self.markup_tool_btns.items():
            if k == tid:
                b.add_css_class("sadeem-btn-active")
            else:
                b.remove_css_class("sadeem-btn-active")

    def _set_markup_color(self, hex_col):
        self.markup_color = hex_col

    def _set_overlay_start_current(self):
        self.overlay_start = self.current_time
        self.overlay_end = min(self.duration_sec, self.overlay_start + 4.0)
        self.timeline_area.queue_draw()
        self._push_history()

    def _clear_markup(self):
        self.strokes.clear()
        self.overlay_canvas.queue_draw()
        self._push_history()

    # -------------------------------------------------------------------------
    # HISTORY (UNDO / REDO)
    # -------------------------------------------------------------------------
    def _push_history(self):
        state = {
            "trim_start": self.trim_start,
            "trim_end": self.trim_end,
            "crop_box": copy.deepcopy(self.crop_box),
            "mute_all": self.mute_all,
            "mute_ranges": list(self.mute_ranges),
            "strokes": copy.deepcopy(self.strokes),
            "overlay_start": self.overlay_start,
            "overlay_end": self.overlay_end,
        }
        self.history.append(state)
        self.redo_stack.clear()
        self.has_unsaved_changes = len(self.history) > 1
        self._sync_undo_redo_buttons()

    def _undo(self):
        if len(self.history) <= 1:
            return
        cur = self.history.pop()
        self.redo_stack.append(cur)
        self._restore_state(self.history[-1])

    def _redo(self):
        if not self.redo_stack:
            return
        nxt = self.redo_stack.pop()
        self.history.append(nxt)
        self._restore_state(nxt)

    def _restore_state(self, st):
        self.trim_start = st["trim_start"]
        self.trim_end = st["trim_end"]
        self.crop_box = copy.deepcopy(st["crop_box"])
        self.mute_all = st["mute_all"]
        self.mute_ranges = list(st["mute_ranges"])
        self.strokes = copy.deepcopy(st["strokes"])
        self.overlay_start = st["overlay_start"]
        self.overlay_end = st["overlay_end"]

        self.sw_mute_all.set_active(self.mute_all)
        self.lbl_in_val.set_text(video_utils.format_duration(self.trim_start))
        self.lbl_out_val.set_text(video_utils.format_duration(self.trim_end))
        self._refresh_mute_list()
        self.timeline_area.queue_draw()
        self.overlay_canvas.queue_draw()
        self._sync_undo_redo_buttons()

    def _sync_undo_redo_buttons(self):
        self.btn_undo.set_sensitive(len(self.history) > 1)
        self.btn_redo.set_sensitive(len(self.redo_stack) > 0)

    # -------------------------------------------------------------------------
    # EXPORT & SAVE PIPELINES
    # -------------------------------------------------------------------------
    def _create_overlay_png(self):
        if not self.strokes:
            return None
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.video_w, self.video_h)
        cr = cairo.Context(surf)
        for s in self.strokes:
            editor.draw_stroke_on_cairo(cr, s, scale_factor=1.0)
        pil_img = editor.cairo_surface_to_pil(surf)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        pil_img.save(tmp.name, format="PNG")
        return tmp.name

    def _on_save_copy_clicked(self):
        folder = os.path.dirname(self.video_path)
        base = os.path.splitext(os.path.basename(self.video_path))[0]
        ext = os.path.splitext(self.video_path)[1]
        out_name = f"{base}_edited{ext}"
        out_path = os.path.join(folder, out_name)

        dlg = Adw.MessageDialog(
            transient_for=self.window,
            heading=t("btn_save_copy"),
            body=f"{t('save_dialog_dest')}: {out_name}",
        )
        dlg.add_response("cancel", t("btn_cancel"))
        dlg.add_response("save", t("save_dialog_save"))
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def _on_resp(_d, rid):
            if rid == "save":
                self._run_export(out_path)

        dlg.connect("response", _on_resp)
        dlg.present()

    def _on_overwrite_clicked(self):
        dlg = Adw.MessageDialog(
            transient_for=self.window,
            heading=t("overwrite_title"),
            body=t("overwrite_body", name=os.path.basename(self.video_path)),
        )
        dlg.add_response("cancel", t("btn_cancel"))
        dlg.add_response("overwrite", t("overwrite_confirm"))
        dlg.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)

        def _on_resp(_d, rid):
            if rid == "overwrite":
                self._run_export(self.video_path)

        dlg.connect("response", _on_resp)
        dlg.present()

    def _run_export(self, target_dest):
        self.pause()
        self.progress_banner.set_visible(True)
        self.export_progress_bar.set_fraction(0.0)
        self.export_progress_bar.set_text(t("exporting_video"))

        cancel_ev = threading.Event()
        self.btn_cancel_export.connect("clicked", lambda _b: cancel_ev.set())

        ov_png = self._create_overlay_png()

        def _on_progress(fraction, time_sec):
            def _ui():
                self.export_progress_bar.set_fraction(fraction)
                pct = int(fraction * 100)
                self.export_progress_bar.set_text(f"{t('exporting_video')} {pct}%")
                return False
            GLib.idle_add(_ui)

        def _worker():
            ok, err = video_editor_engine.export_video(
                input_path=self.video_path,
                output_path=target_dest,
                trim_start=self.trim_start if self.trim_start > 0.05 else None,
                trim_end=self.trim_end if self.trim_end < self.duration_sec - 0.05 else None,
                mute_all=self.mute_all,
                mute_ranges=self.mute_ranges if self.mute_ranges else None,
                crop_box=tuple(self.crop_box) if self.crop_box else None,
                overlay_png_path=ov_png,
                overlay_start=self.overlay_start,
                overlay_end=self.overlay_end,
                progress_callback=_on_progress,
                cancel_event=cancel_ev,
            )

            if ov_png and os.path.isfile(ov_png):
                try:
                    os.remove(ov_png)
                except OSError:
                    pass

            def _finish():
                self.progress_banner.set_visible(False)
                if ok:
                    self.has_unsaved_changes = False
                    if self.window and hasattr(self.window, "_toast"):
                        self.window._toast(t("toast_saved", name=os.path.basename(target_dest)))
                    if self.on_saved_cb:
                        self.on_saved_cb(target_dest)
                    self._close_view()
                else:
                    if self.window and hasattr(self.window, "_toast"):
                        self.window._toast(t("toast_save_err", err=err or "Export failed"))
                return False

            GLib.idle_add(_finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _request_close(self):
        if self.has_unsaved_changes:
            dlg = Adw.MessageDialog(
                transient_for=self.window,
                heading=t("discard_title"),
                body=t("discard_body"),
            )
            dlg.add_response("cancel", t("btn_cancel"))
            dlg.add_response("discard", t("discard_confirm"))
            dlg.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)

            def _on_resp(_d, rid):
                if rid == "discard":
                    self._close_view()

            dlg.connect("response", _on_resp)
            dlg.present()
        else:
            self._close_view()

    def _close_view(self):
        self._stop_poll_timer()
        if self.media_stream:
            try:
                self.media_stream.pause()
            except Exception:
                pass
        if self.video_widget:
            self.video_widget.set_media_stream(None)
        if self.on_close_cb:
            self.on_close_cb()
