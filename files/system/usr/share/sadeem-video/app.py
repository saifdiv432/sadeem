#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Video (فيديو سديم) — Standalone GTK4 + Libadwaita Video Player
built directly on libmpv.so.2 via ctypes and Gtk.GLArea.
"""

import locale
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import i18n
import mpris
import mpv_engine
import playlist
import popovers
import thumbnails

t = i18n.t

APP_ID = "org.sadeem.Video"
OSD_HIDE_DELAY_MS = 2500
OSD_PILL_MS = 1400
RESUME_BANNER_MS = 8000
POLL_INTERVAL_MS = 67
CLICK_DISAMBIGUATION_MS = 220

SADEEM_VIDEO_PLAYER_CSS = popovers.SADEEM_VIDEO_PLAYER_CSS
format_isolated_filename = popovers.format_isolated
format_time = popovers.format_time


def get_screenshots_dir() -> str:
    """Return Pictures/<localized_screenshots_folder> matching system language."""
    try:
        pic_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    except Exception:
        pic_dir = None
    if not pic_dir:
        pic_dir = os.path.join(os.path.expanduser("~"), "Pictures")
    folder = i18n.t("folder_screenshots") or "Screenshots"
    return os.path.join(pic_dir, folder)


def find_exec_binary(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    repo_bin = os.path.normpath(os.path.join(APP_DIR, "..", "..", "..", "bin", name))
    sys_bin = os.path.join("/usr/bin", name)
    for candidate in (repo_bin, sys_bin):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def launch_video_editor(video_path: Optional[str]) -> bool:
    """Open sadeem-video-editor asynchronously via Popen without blocking the player."""
    editor_bin = find_exec_binary("sadeem-video-editor") or "sadeem-video-editor"
    args = [editor_bin]
    if video_path:
        args.append(video_path)
    try:
        subprocess.Popen(args, start_new_session=True, close_fds=True)
        return True
    except Exception as exc:
        sys.stderr.write(f"Failed to launch sadeem-video-editor: {exc}\n")
        return False


class SadeemVideoWindow(Adw.ApplicationWindow):
    """Main cinema window with floating overlays, GLArea mpv viewport, popovers & playlist."""

    def __init__(
        self,
        app: Adw.Application,
        initial_files: Optional[List[str]] = None,
        engine: Optional[mpv_engine.MpvEngine] = None,
        state_store: Optional[playlist.StateStore] = None,
    ) -> None:
        super().__init__(application=app, title=t("app_title"))
        # Isolate outer window shell to LTR so GTK4 Wayland+RTL unfullscreen/drag
        # geometry never drifts, while restoring system UI direction inside toast_overlay.
        self._ui_direction = Gtk.Widget.get_default_direction()
        self.set_direction(Gtk.TextDirection.LTR)
        self.set_icon_name("sadeem-video")
        self.set_default_size(1120, 680)
        self.set_size_request(520, 340)

        self.playlist_mgr = playlist.PlaylistManager()
        self.state_store = state_store or playlist.StateStore()
        self.engine = engine or mpv_engine.MpvEngine()
        self.engine_error: Optional[str] = None

        self._poll_id: int = 0
        self._hide_hud_id: int = 0
        self._osd_hide_id: int = 0
        self._resume_timer_id: int = 0
        self._click_timer_id: int = 0
        self._seeking_from_ui: bool = False
        self._updating_ui: bool = False
        self._is_fullscreen: bool = False
        self._is_mini_mode: bool = False
        self._pre_mini_size: Optional[tuple] = None
        self._is_playing: bool = False
        self._pointer_over_hud: bool = False
        self._active_popovers: int = 0
        self._last_motion_x: float = -1.0
        self._last_motion_y: float = -1.0

        self._ab_point_a: Optional[float] = None
        self._ab_point_b: Optional[float] = None
        self._last_sid: int = 1
        self._audio_delay_val: float = 0.0
        self._sub_delay_val: float = 0.0
        self._sub_scale_val: float = 1.0
        self._current_speed: float = float(self.state_store.get_setting("speed", 1.0))
        self._loop_mode: str = str(self.state_store.get_setting("loop_mode", "off"))
        self._resume_mode: str = str(self.state_store.get_setting("resume_mode", "ask"))
        self._pause_on_minimize: bool = bool(self.state_store.get_setting("pause_on_minimize", True))
        self._paused_by_minimize: bool = False
        self._inhibit_cookie: int = 0
        self._tracked_surface = None
        self._surface_state_handler_id: int = 0
        self._cached_chapters: list = []
        self._thumb_hover_ts: float = -1.0
        self._audio_eq_preset: str = str(self.state_store.get_setting("audio_eq_preset", "normal"))
        self._sub_pos_val: int = int(self.state_store.get_setting("sub_pos", 100))
        self._sub_color_val: str = str(self.state_store.get_setting("sub_color", "#FFFFFF"))
        self._sub_font_val: str = str(self.state_store.get_setting("sub_font", ""))
        self._current_aspect: str = "auto"
        self._current_rotation: int = 0
        self._video_zoom: float = 0.0
        self._panscan_enabled: bool = False
        self._pending_resume_seek: float = 0.0
        self._last_saved_save_tick: float = 0.0
        self._pending_load_path: Optional[str] = None
        self._destroyed: bool = False
        self._gl_redraw_lock = threading.Lock()
        self._gl_redraw_pending: bool = False
        self._gl_needs_initial_draw: bool = True

        self.thumb_extractor = thumbnails.ThumbnailExtractor(dispatcher=GLib.idle_add)
        self.mpris_service = mpris.MprisService(self, identity=t("app_title"))

        self._init_engine()
        self._build_ui()
        self._setup_controllers()
        self._apply_saved_settings()
        self.mpris_service.start()

        self.connect("close-request", self._on_close_request)
        self.connect("notify::fullscreened", self._on_fullscreen_changed)
        self.connect("realize", self._on_window_realize_surface)

        if initial_files:
            self.open_paths(initial_files)

        self._poll_id = GLib.timeout_add(POLL_INTERVAL_MS, self._on_poll_tick)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def _init_engine(self) -> None:
        try:
            if not self.engine.is_initialized:
                self.engine.initialize()
        except Exception as exc:
            self.engine_error = str(exc)

    def _apply_saved_settings(self) -> None:
        vol = float(self.state_store.get_setting("volume", 100.0))
        muted = bool(self.state_store.get_setting("muted", False))
        speed = float(self.state_store.get_setting("speed", 1.0))
        sub_bidi = bool(self.state_store.get_setting("sub_bidi_compat", False))
        night_mode = bool(self.state_store.get_setting("audio_night_mode", False))
        sub_back_box = bool(self.state_store.get_setting("sub_back_box", False))
        self._current_speed = speed

        self._updating_ui = True
        try:
            self.volume_scale.set_value(max(0.0, min(200.0, vol)))
            self._update_mute_icon(muted, vol)
            self.sub_bidi_switch.set_active(sub_bidi)
            self.night_mode_switch.set_active(night_mode)
            self.sub_back_box_switch.set_active(sub_back_box)
            self.pause_on_min_switch.set_active(self._pause_on_minimize)
        finally:
            self._updating_ui = False

        if self.engine.is_initialized:
            self.engine.set_volume(vol)
            self.engine.set_mute(muted)
            self.engine.set_speed(speed)
            self.engine.set_loop_file(self._loop_mode == "file")
            self.engine.set_sub_bidi_compat(sub_bidi)
            if night_mode:
                self.engine.set_night_mode(True)
            if self._audio_eq_preset != "normal":
                self.engine.set_audio_eq_preset(self._audio_eq_preset)
            self.engine.set_sub_pos(self._sub_pos_val)
            self.engine.set_sub_color(self._sub_color_val)
            if sub_back_box:
                self.engine.set_sub_back_box(True)
            if self._sub_font_val:
                self.engine.set_sub_font(self._sub_font_val)

        popovers.sync_settings_active_states(self)
        popovers.sync_tracks_active_states(self)

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_direction(self._ui_direction)
        self.set_content(self.toast_overlay)

        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_sidebar_position(Gtk.PackType.END)
        self.split_view.set_show_sidebar(False)
        self.split_view.set_min_sidebar_width(260)
        self.split_view.set_max_sidebar_width(360)
        self.toast_overlay.set_child(self.split_view)

        self.playlist_sidebar = self._build_playlist_sidebar()
        self.split_view.set_sidebar(self.playlist_sidebar)

        self.video_overlay = Gtk.Overlay()
        self.video_overlay.add_css_class("sadeem-video-stage")
        self.video_overlay.set_hexpand(True)
        self.video_overlay.set_vexpand(True)
        self.split_view.set_content(self.video_overlay)

        # GLArea base canvas
        self.gl_area = Gtk.GLArea()
        self.gl_area.set_auto_render(True)
        self.gl_area.set_hexpand(True)
        self.gl_area.set_vexpand(True)
        self.gl_area.connect("realize", self._on_gl_realize)
        self.gl_area.connect("render", self._on_gl_render)
        self.gl_area.connect("unrealize", self._on_gl_unrealize)
        self.video_overlay.set_child(self.gl_area)

        # Welcome / Empty Overlay
        self.welcome_box = self._build_welcome_overlay()
        self.video_overlay.add_overlay(self.welcome_box)

        # Transient OSD badge
        self.osd_revealer = Gtk.Revealer()
        self.osd_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.osd_revealer.set_transition_duration(180)
        self.osd_revealer.set_halign(Gtk.Align.CENTER)
        self.osd_revealer.set_valign(Gtk.Align.CENTER)
        self.osd_revealer.set_can_target(False)
        self.osd_label = Gtk.Label()
        self.osd_label.add_css_class("sadeem-osd-badge")
        self.osd_revealer.set_child(self.osd_label)
        self.video_overlay.add_overlay(self.osd_revealer)

        # Smart Resume Banner Overlay (inside Gtk.Revealer)
        self.resume_revealer = Gtk.Revealer()
        self.resume_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.resume_revealer.set_transition_duration(200)
        self.resume_revealer.set_halign(Gtk.Align.CENTER)
        self.resume_revealer.set_valign(Gtk.Align.END)
        self.resume_revealer.set_reveal_child(False)
        self.resume_revealer.set_can_target(False)

        resume_pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        resume_pill.add_css_class("sadeem-resume-banner")
        self.resume_msg_lbl = Gtk.Label(label="")
        resume_pill.append(self.resume_msg_lbl)

        self.resume_action_btn = Gtk.Button(label=t("resume_btn"))
        self.resume_action_btn.add_css_class("flat")
        self.resume_action_btn.add_css_class("sadeem-resume-btn")
        self.resume_action_btn.connect("clicked", self._on_resume_action_clicked)
        resume_pill.append(self.resume_action_btn)

        resume_close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        resume_close_btn.add_css_class("flat")
        resume_close_btn.add_css_class("sadeem-hud-btn")
        resume_close_btn.connect("clicked", lambda *_: self.dismiss_resume_banner())
        resume_pill.append(resume_close_btn)
        self.resume_revealer.set_child(resume_pill)
        self.video_overlay.add_overlay(self.resume_revealer)

        # Top floating overlay bar wrapped cleanly in CROSSFADE Revealer
        self.top_revealer = Gtk.Revealer()
        self.top_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.top_revealer.set_transition_duration(220)
        self.top_revealer.set_halign(Gtk.Align.FILL)
        self.top_revealer.set_valign(Gtk.Align.START)
        self.top_revealer.set_reveal_child(True)
        self.top_bar_widget = self._build_top_bar()
        self.top_revealer.set_child(self.top_bar_widget)
        self.video_overlay.add_overlay(self.top_revealer)

        # Bottom floating OSD capsule inside Adw.Clamp + CROSSFADE Revealer
        self.bottom_revealer = Gtk.Revealer()
        self.bottom_revealer.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.bottom_revealer.set_transition_duration(220)
        self.bottom_revealer.set_halign(Gtk.Align.FILL)
        self.bottom_revealer.set_valign(Gtk.Align.END)
        self.bottom_revealer.set_reveal_child(True)
        self.bottom_clamp = Adw.Clamp()
        self.bottom_clamp.set_maximum_size(760)
        self.bottom_clamp.set_tightening_threshold(560)
        self.bottom_dock_widget = self._build_bottom_dock()
        self.bottom_clamp.set_child(self.bottom_dock_widget)
        self.bottom_revealer.set_child(self.bottom_clamp)
        self.video_overlay.add_overlay(self.bottom_revealer)

    def _build_welcome_overlay(self) -> Gtk.Widget:
        return popovers.build_welcome_overlay(self)

    def _refresh_welcome_recent(self) -> None:
        popovers.refresh_welcome_recent(self)

    def _on_clear_recent_clicked(self, *_args) -> None:
        self.state_store.clear_recent_files()
        self._refresh_welcome_recent()

    def _build_top_bar(self) -> Gtk.Widget:
        handle = Gtk.WindowHandle()
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("sadeem-hud-top")
        handle.set_child(bar)

        self.open_btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
        self.open_btn.add_css_class("osd")
        self.open_btn.add_css_class("sadeem-osd-btn")
        self.open_btn.set_tooltip_text(t("open_file"))
        self.open_btn.connect("clicked", lambda *_: self.prompt_open_file())
        bar.append(self.open_btn)

        self.playlist_toggle_btn = Gtk.ToggleButton()
        self.playlist_toggle_btn.set_icon_name("view-list-symbolic")
        self.playlist_toggle_btn.add_css_class("osd")
        self.playlist_toggle_btn.add_css_class("sadeem-osd-btn")
        self.playlist_toggle_btn.set_tooltip_text(f"{t('playlist')} (P)")
        self.playlist_toggle_btn.connect("toggled", self._on_playlist_toggled)
        bar.append(self.playlist_toggle_btn)

        self.title_label = Gtk.Label(label=format_isolated_filename(t("app_title")))
        self.title_label.add_css_class("sadeem-video-title")
        self.title_label.set_hexpand(True)
        self.title_label.set_halign(Gtk.Align.CENTER)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.title_label.set_single_line_mode(True)
        bar.append(self.title_label)

        self.edit_btn = Gtk.Button()
        edit_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        edit_box.append(Gtk.Image.new_from_icon_name("document-edit-symbolic"))
        edit_box.append(Gtk.Label(label=t("edit_video")))
        self.edit_btn.set_child(edit_box)
        self.edit_btn.add_css_class("osd")
        self.edit_btn.add_css_class("sadeem-osd-btn")
        self.edit_btn.set_tooltip_text(t("edit_video"))
        self.edit_btn.set_sensitive(False)
        self.edit_btn.connect("clicked", self._on_edit_video_clicked)
        bar.append(self.edit_btn)

        self.info_btn = Gtk.Button.new_from_icon_name("info-outline-symbolic")
        self.info_btn.add_css_class("osd")
        self.info_btn.add_css_class("sadeem-osd-btn")
        self.info_btn.set_tooltip_text(f"{t('media_info')} (I)")
        self.info_btn.connect("clicked", lambda *_: self.show_media_info_dialog())
        bar.append(self.info_btn)

        win_controls = Gtk.WindowControls.new(Gtk.PackType.END)
        bar.append(win_controls)

        self._attach_hud_motion(bar)
        return handle

    def _build_bottom_dock(self) -> Gtk.Widget:
        capsule = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        capsule.add_css_class("sadeem-hud-capsule")

        # Top row inside capsule: strictly LTR [current_time] [Seek Scale] [duration]
        self.progress_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.progress_row.set_direction(Gtk.TextDirection.LTR)

        self.time_pos_label = Gtk.Label(label="00:00")
        self.time_pos_label.set_direction(Gtk.TextDirection.LTR)
        self.time_pos_label.add_css_class("sadeem-time-label")
        self.progress_row.append(self.time_pos_label)

        self.seek_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=1.0, page_increment=10.0)
        self.seek_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.seek_adj)
        self.seek_scale.set_direction(Gtk.TextDirection.LTR)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.set_hexpand(True)
        self.seek_scale.add_css_class("sadeem-seek-scale")
        self.seek_scale.connect("change-value", self._on_seek_change_value)
        self._build_seek_thumbnail_popover()
        self.progress_row.append(self.seek_scale)

        self.time_dur_label = Gtk.Label(label="00:00")
        self.time_dur_label.set_direction(Gtk.TextDirection.LTR)
        self.time_dur_label.add_css_class("sadeem-time-label")
        self.progress_row.append(self.time_dur_label)

        capsule.append(self.progress_row)

        # Bottom balanced 3-part Gtk.CenterBox (Volume 200% | LTR Transport | Tools)
        controls = Gtk.CenterBox()

        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vol_box.set_direction(Gtk.TextDirection.LTR)
        self.mute_btn = Gtk.Button.new_from_icon_name("audio-volume-high-symbolic")
        self.mute_btn.add_css_class("flat")
        self.mute_btn.add_css_class("sadeem-hud-btn")
        self.mute_btn.set_tooltip_text(f"{t('mute')} (M)")
        self.mute_btn.connect("clicked", lambda *_: self.toggle_mute())
        vol_box.append(self.mute_btn)

        self.vol_adj = Gtk.Adjustment(value=100.0, lower=0.0, upper=200.0, step_increment=5.0, page_increment=15.0)
        self.volume_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.vol_adj)
        self.volume_scale.set_direction(Gtk.TextDirection.LTR)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_size_request(95, -1)
        self.volume_scale.add_css_class("sadeem-vol-scale")
        self.volume_scale.connect("value-changed", self._on_volume_slider_changed)
        vol_box.append(self.volume_scale)
        controls.set_start_widget(vol_box)

        # Center widget: Fixed-LTR Transport ([Prev] [-10s] [Play/Pause] [+10s] [Next])
        self.transport_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.transport_box.set_direction(Gtk.TextDirection.LTR)

        self.prev_btn = Gtk.Button.new_from_icon_name("media-skip-backward-symbolic")
        self.prev_btn.add_css_class("flat")
        self.prev_btn.add_css_class("sadeem-hud-btn")
        self.prev_btn.set_tooltip_text(f"{t('previous')} (PageUp)")
        self.prev_btn.connect("clicked", lambda *_: self.play_previous())
        self.transport_box.append(self.prev_btn)

        self.skip_back_btn = Gtk.Button.new_from_icon_name("media-seek-backward-symbolic")
        self.skip_back_btn.add_css_class("flat")
        self.skip_back_btn.add_css_class("sadeem-hud-btn")
        self.skip_back_btn.set_tooltip_text(t("osd_seek_back", s=10))
        self.skip_back_btn.connect("clicked", lambda *_: self.seek_relative(-10.0))
        self.transport_box.append(self.skip_back_btn)

        self.play_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.play_btn.add_css_class("sadeem-play-btn")
        self.play_btn.set_tooltip_text(f"{t('play')} / {t('pause')} (Space)")
        self.play_btn.connect("clicked", lambda *_: self.toggle_play_pause())
        self.transport_box.append(self.play_btn)

        self.skip_fwd_btn = Gtk.Button.new_from_icon_name("media-seek-forward-symbolic")
        self.skip_fwd_btn.add_css_class("flat")
        self.skip_fwd_btn.add_css_class("sadeem-hud-btn")
        self.skip_fwd_btn.set_tooltip_text(t("osd_seek_fwd", s=10))
        self.skip_fwd_btn.connect("clicked", lambda *_: self.seek_relative(10.0))
        self.transport_box.append(self.skip_fwd_btn)

        self.next_btn = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic")
        self.next_btn.add_css_class("flat")
        self.next_btn.add_css_class("sadeem-hud-btn")
        self.next_btn.set_tooltip_text(f"{t('next')} (PageDown)")
        self.next_btn.connect("clicked", lambda *_: self.play_next())
        self.transport_box.append(self.next_btn)

        controls.set_center_widget(self.transport_box)

        # End widget: Tracks Popover + Settings Popover + Fullscreen
        tools_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self.tracks_btn = Gtk.MenuButton()
        self.tracks_btn.set_has_frame(False)
        self.tracks_btn.set_icon_name("media-view-subtitles-symbolic")
        self.tracks_btn.add_css_class("flat")
        self.tracks_btn.add_css_class("sadeem-hud-btn")
        self.tracks_btn.set_tooltip_text(t("tracks_btn"))
        self.tracks_popover = popovers.build_tracks_popover(self)
        self.tracks_btn.set_popover(self.tracks_popover)
        tools_box.append(self.tracks_btn)

        self.settings_btn = Gtk.MenuButton()
        self.settings_btn.set_has_frame(False)
        self.settings_btn.set_icon_name("emblem-system-symbolic")
        self.settings_btn.add_css_class("flat")
        self.settings_btn.add_css_class("sadeem-hud-btn")
        self.settings_btn.set_tooltip_text(t("settings"))
        self.settings_popover = popovers.build_settings_popover(self)
        self.settings_btn.set_popover(self.settings_popover)
        tools_box.append(self.settings_btn)

        self.fs_btn = Gtk.Button.new_from_icon_name("view-fullscreen-symbolic")
        self.fs_btn.add_css_class("flat")
        self.fs_btn.add_css_class("sadeem-hud-btn")
        self.fs_btn.set_tooltip_text(f"{t('fullscreen')} (F / F11)")
        self.fs_btn.connect("clicked", lambda *_: self.toggle_fullscreen())
        tools_box.append(self.fs_btn)

        controls.set_end_widget(tools_box)

        capsule.append(controls)
        self._attach_hud_motion(capsule)
        return capsule

    def _register_popover_tracking(self, popover: Gtk.Popover) -> None:
        def _on_show(*_):
            self._active_popovers += 1
            self._reveal_hud(auto_hide=False)

        def _on_closed(*_):
            self._active_popovers = max(0, self._active_popovers - 1)
            self._schedule_hud_hide()

        popover.connect("show", _on_show)
        popover.connect("closed", _on_closed)

    def _build_playlist_sidebar(self) -> Gtk.Widget:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)
        hdr.set_show_start_title_buttons(False)
        hdr_title = Adw.WindowTitle(title=t("playlist"), subtitle="")
        self.playlist_header_title = hdr_title
        hdr.set_title_widget(hdr_title)

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.set_tooltip_text(t("add_files"))
        add_btn.connect("clicked", lambda *_: self.prompt_open_file(add_to_playlist=True))
        hdr.pack_start(add_btn)

        clr_btn = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic")
        clr_btn.set_tooltip_text(t("clear_playlist"))
        clr_btn.connect("clicked", lambda *_: self._clear_playlist())
        hdr.pack_end(clr_btn)
        panel.append(hdr)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.playlist_listbox = Gtk.ListBox()
        self.playlist_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.playlist_listbox.add_css_class("navigation-sidebar")
        self.playlist_listbox.connect("row-activated", self._on_playlist_row_activated)
        scroll.set_child(self.playlist_listbox)
        panel.append(scroll)
        return panel

    # -----------------------------------------------------------------------
    # Controllers (Keyboard, Pointer HUD reveal, Scroll Volume, Clicks, D&D)
    # -----------------------------------------------------------------------
    def _attach_hud_motion(self, widget: Gtk.Widget) -> None:
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._set_pointer_over_hud(True))
        motion.connect("leave", lambda *_: self._set_pointer_over_hud(False))
        widget.add_controller(motion)

    def _setup_controllers(self) -> None:
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_stage_pointer_motion)
        self.video_overlay.add_controller(motion)

        click = Gtk.GestureClick()
        click.set_button(Gdk.BUTTON_PRIMARY)
        click.connect("released", self._on_video_clicked)
        self.gl_area.add_controller(click)

        scroll_ctrl = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_ctrl.connect("scroll", self._on_video_scroll)
        self.gl_area.add_controller(scroll_ctrl)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_files_dropped)
        self.add_controller(drop)

    def _on_stage_pointer_motion(self, _ctrl, x: float, y: float) -> None:
        if self._last_motion_x >= 0.0 and self._last_motion_y >= 0.0:
            if abs(x - self._last_motion_x) <= 2.0 and abs(y - self._last_motion_y) <= 2.0:
                return
        self._last_motion_x = float(x)
        self._last_motion_y = float(y)
        self._reveal_hud(auto_hide=True)

    # -----------------------------------------------------------------------
    # GL Render Lifecycle
    # -----------------------------------------------------------------------
    def _build_seek_thumbnail_popover(self) -> None:
        self.thumb_popover = Gtk.Popover()
        self.thumb_popover.set_parent(self.seek_scale)
        self.thumb_popover.set_autohide(False)
        self.thumb_popover.set_can_target(False)
        self.thumb_popover.set_has_arrow(False)
        self.thumb_popover.set_position(Gtk.PositionType.TOP)
        self.thumb_popover.set_offset(0, -8)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("sadeem-thumb-preview")

        self.thumb_picture = Gtk.Picture()
        self.thumb_picture.set_size_request(160, 90)
        self.thumb_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.thumb_picture.set_visible(False)
        card.append(self.thumb_picture)

        self.thumb_time_lbl = Gtk.Label(label="00:00")
        self.thumb_time_lbl.add_css_class("sadeem-tabular-val")
        card.append(self.thumb_time_lbl)

        self.thumb_chapter_lbl = Gtk.Label(label="")
        self.thumb_chapter_lbl.add_css_class("caption")
        self.thumb_chapter_lbl.add_css_class("dim-label")
        self.thumb_chapter_lbl.set_max_width_chars(24)
        self.thumb_chapter_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.thumb_chapter_lbl.set_visible(False)
        card.append(self.thumb_chapter_lbl)

        self.thumb_popover.set_child(card)

        seek_motion = Gtk.EventControllerMotion()
        seek_motion.connect("motion", self._on_seek_hover_motion)
        seek_motion.connect("leave", self._on_seek_hover_leave)
        self.seek_scale.add_controller(seek_motion)

    def _on_seek_hover_motion(self, _ctrl, x: float, _y: float) -> None:
        cur = self.playlist_mgr.current_path
        dur = float(self.seek_adj.get_upper())
        if not cur or dur <= 1.0:
            return
        w = max(1.0, float(self.seek_scale.get_width()))
        frac = max(0.0, min(1.0, float(x) / w))
        hover_sec = frac * dur
        self._thumb_hover_ts = hover_sec

        self.thumb_time_lbl.set_text(format_time(hover_sec))

        chap_title = ""
        for ch in self._cached_chapters:
            if float(ch.get("time", 0.0)) <= hover_sec:
                chap_title = str(ch.get("title") or "")
        if chap_title:
            self.thumb_chapter_lbl.set_text(format_isolated_filename(chap_title))
            self.thumb_chapter_lbl.set_visible(True)
        else:
            self.thumb_chapter_lbl.set_visible(False)

        rect = Gdk.Rectangle()
        rect.x = int(max(0, min(w - 1, x)))
        rect.y = 0
        rect.width = 1
        rect.height = 1
        self.thumb_popover.set_pointing_to(rect)
        if not self.thumb_popover.get_visible():
            self.thumb_popover.popup()

        if self.thumb_extractor.is_available and self.thumb_extractor.can_extract_for(cur):
            cached = self.thumb_extractor.get_cached(cur, hover_sec, dur)
            if cached:
                self._apply_thumb_bytes(cached)
            else:
                self.thumb_extractor.request_thumbnail(cur, hover_sec, dur, self._on_thumbnail_ready)
        else:
            self.thumb_picture.set_visible(False)

    def _on_seek_hover_leave(self, *_args) -> None:
        self._thumb_hover_ts = -1.0
        self.thumb_popover.popdown()

    def _on_thumbnail_ready(self, video_path: str, _q_ts: float, png_bytes: Optional[bytes]) -> None:
        if (
            self._destroyed
            or video_path != self.playlist_mgr.current_path
            or self._thumb_hover_ts < 0.0
            or not png_bytes
        ):
            return
        self._apply_thumb_bytes(png_bytes)

    def _apply_thumb_bytes(self, png_bytes: bytes) -> None:
        try:
            tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(png_bytes))
            self.thumb_picture.set_paintable(tex)
            self.thumb_picture.set_visible(True)
        except Exception:
            self.thumb_picture.set_visible(False)

    def _on_gl_realize(self, area: Gtk.GLArea) -> None:
        if not self.engine.is_initialized or self._destroyed:
            return
        with self._gl_redraw_lock:
            self._gl_needs_initial_draw = True
        try:
            self.engine.setup_gl_render(area, on_update=self._queue_gl_redraw)
        except Exception as exc:
            self.engine_error = str(exc)
            sys.stderr.write(f"GL render context setup failed: {exc}\n")

        if self._pending_load_path:
            pending = self._pending_load_path
            self._pending_load_path = None
            self._start_playback(pending)

    def _queue_gl_redraw(self) -> None:
        if self._destroyed:
            return
        with self._gl_redraw_lock:
            if self._gl_redraw_pending:
                return
            self._gl_redraw_pending = True

        def _idle_redraw():
            with self._gl_redraw_lock:
                self._gl_redraw_pending = False
                initial = self._gl_needs_initial_draw
                self._gl_needs_initial_draw = False
            if self._destroyed or not self.gl_area.get_realized():
                return False
            flags = self.engine.update_render_context()
            if (flags & mpv_engine.MPV_RENDER_UPDATE_FRAME) or initial:
                self.gl_area.queue_render()
            return False

        GLib.idle_add(_idle_redraw)

    def _on_gl_render(self, area: Gtk.GLArea, _gl_ctx) -> bool:
        if not self.engine.has_render_context:
            return False
        scale = max(1, area.get_scale_factor())
        w = max(1, int(area.get_width() * scale))
        h = max(1, int(area.get_height() * scale))
        return self.engine.render_frame(w, h)

    def _on_gl_unrealize(self, area: Gtk.GLArea) -> None:
        self.engine.destroy_gl_render(area)

    # -----------------------------------------------------------------------
    # Polling, Events & Chapters
    # -----------------------------------------------------------------------
    def _on_poll_tick(self) -> bool:
        if self._destroyed:
            return False
        if self.engine.is_initialized:
            self.engine.drain_events(self._handle_mpv_event)
            self._sync_playback_ui()
        return True

    def _refresh_chapter_marks(self) -> None:
        if hasattr(self.seek_scale, "clear_marks"):
            self.seek_scale.clear_marks()
        if not self.engine.is_initialized:
            self._cached_chapters = []
            return
        chapters = self.engine.get_chapters()
        self._cached_chapters = chapters
        for ch in chapters:
            ts = float(ch.get("time", 0.0))
            if ts > 0.0 and hasattr(self.seek_scale, "add_mark"):
                self.seek_scale.add_mark(ts, Gtk.PositionType.TOP, None)

    def _handle_mpv_event(self, ev: dict) -> None:
        ev_id = ev.get("event_id")
        if ev_id == mpv_engine.MPV_EVENT_FILE_LOADED:
            self._refresh_playlist_ui()
            if self.engine.is_initialized:
                dur = self.engine.get_duration()
                self.time_dur_label.set_text(format_time(dur))
                self.seek_adj.set_upper(max(1.0, dur))
                self._refresh_chapter_marks()
                cur = self.playlist_mgr.current_path
                if cur and dur > 0.0:
                    self.state_store.record_recent(cur, self.engine.get_time_pos(), dur)
                paused = self.engine.is_paused()
                self._sync_play_pause_state(paused, trigger_hud=True)
                self.mpris_service.emit_properties_changed(("Metadata", "PlaybackStatus", "CanSeek"))
        elif ev_id == mpv_engine.MPV_EVENT_END_FILE:
            reason = ev.get("reason")
            if reason == mpv_engine.MPV_END_FILE_REASON_EOF:
                cur = self.playlist_mgr.current_path
                if cur:
                    dur = self.engine.get_duration()
                    self.state_store.set_position(cur, dur, dur)
                    self.state_store.save()
                if self._loop_mode == "file":
                    self.engine.seek_absolute(0.0)
                    self.engine.set_paused(False)
                    self._sync_play_pause_state(False, trigger_hud=True)
                elif self._loop_mode == "playlist":
                    self.play_next(wrap=True)
                elif self.playlist_mgr.has_next(wrap=False):
                    self.play_next(wrap=False)
                else:
                    self._sync_play_pause_state(True, trigger_hud=True)
            elif reason == mpv_engine.MPV_END_FILE_REASON_ERROR:
                self._show_osd(t("err_open_file"))
                self._sync_play_pause_state(True, trigger_hud=True)
        elif ev_id in (mpv_engine.MPV_EVENT_PLAYBACK_RESTART, mpv_engine.MPV_EVENT_SEEK):
            if self.engine.is_initialized:
                self._sync_play_pause_state(self.engine.is_paused(), trigger_hud=True)
                if ev_id == mpv_engine.MPV_EVENT_SEEK:
                    self.mpris_service.emit_seeked(self.engine.get_time_pos())

    def _sync_playback_ui(self) -> None:
        cur = self.playlist_mgr.current_path
        if not cur or not self.engine.is_initialized:
            return

        dur = self.engine.get_duration()
        pos = self.engine.get_time_pos()
        paused = self.engine.is_paused()

        self._updating_ui = True
        try:
            self.time_pos_label.set_text(format_time(pos))
            self.time_dur_label.set_text(format_time(dur))
            if dur > 0.1:
                self.seek_adj.set_upper(dur)
            if not self._seeking_from_ui:
                self.seek_adj.set_value(min(max(0.0, pos), max(1.0, dur)))
            self._sync_play_pause_state(paused, trigger_hud=False)
        finally:
            self._updating_ui = False

        now = time.monotonic()
        if now - self._last_saved_save_tick >= 3.0 and dur > 0.0:
            self._last_saved_save_tick = now
            self.state_store.set_position(cur, pos, dur)

    def _update_idle_inhibit(self, should_inhibit: bool) -> None:
        app = self.get_application()
        if should_inhibit:
            if not self._inhibit_cookie and app is not None and hasattr(app, "inhibit"):
                try:
                    cookie = app.inhibit(self, Gtk.ApplicationInhibitFlags.IDLE, t("app_title"))
                    self._inhibit_cookie = int(cookie or 0)
                except Exception:
                    self._inhibit_cookie = 0
        else:
            if self._inhibit_cookie and app is not None and hasattr(app, "uninhibit"):
                try:
                    app.uninhibit(self._inhibit_cookie)
                except Exception:
                    pass
                finally:
                    self._inhibit_cookie = 0

    def _sync_play_pause_state(self, paused: bool, trigger_hud: bool = False) -> None:
        new_playing = bool(self.playlist_mgr.current_path) and not paused
        state_changed = (new_playing != self._is_playing)
        self._is_playing = new_playing
        self._update_idle_inhibit(self._is_playing)
        self.play_btn.set_icon_name(
            "media-playback-pause-symbolic" if self._is_playing else "media-playback-start-symbolic"
        )
        if state_changed:
            self.mpris_service.emit_properties_changed(
                ("PlaybackStatus", "CanPlay", "CanPause", "CanSeek", "CanGoNext", "CanGoPrevious")
            )
        if state_changed or trigger_hud:
            if not self._is_playing:
                self._reveal_hud(auto_hide=False)
            else:
                self._schedule_hud_hide()

    # -----------------------------------------------------------------------
    # Opening Files, Smart Resume & Playlist Control
    # -----------------------------------------------------------------------
    def open_paths(self, paths: List[str]) -> None:
        video_paths = []
        sub_paths = []
        urls = []
        for p in paths:
            if not p:
                continue
            if playlist.is_network_url(p):
                urls.append(p.strip())
                continue
            abs_p = os.path.abspath(p)
            if playlist.is_subtitle_file(abs_p) and self.playlist_mgr.current_path:
                sub_paths.append(abs_p)
            elif os.path.isfile(abs_p):
                video_paths.append(abs_p)

        if len(video_paths) == 1:
            selected = self.playlist_mgr.load_with_siblings(video_paths[0])
            self._refresh_playlist_ui()
            if selected:
                self.play_path(selected)
        elif len(video_paths) > 1:
            self.playlist_mgr.clear()
            self.playlist_mgr.add_files(video_paths, select_first_added=True)
            self._refresh_playlist_ui()
            if self.playlist_mgr.current_path:
                self.play_path(self.playlist_mgr.current_path)
        elif urls:
            self.open_url(urls[0])

        for sp in sub_paths:
            if self.engine.is_initialized:
                self.engine.add_subtitle(sp)
                self._show_osd(t("sub_added"))

    def play_path(self, path: str) -> None:
        if playlist.is_network_url(path):
            self.open_url(path)
            return
        if not path or not os.path.isfile(path):
            self._show_osd(t("err_open_file"))
            return
        self.dismiss_resume_banner()
        self.thumb_popover.popdown()
        self.thumb_picture.set_visible(False)
        self.thumb_extractor.set_video(path)

        prev_path = self.playlist_mgr.current_path
        if prev_path and prev_path != os.path.abspath(path) and self.engine.is_initialized:
            dur = self.engine.get_duration()
            if dur > 0.0:
                self.state_store.set_position(prev_path, self.engine.get_time_pos(), dur)

        self.playlist_mgr.select_path(path)
        self._ab_point_a = None
        self._ab_point_b = None
        self.welcome_box.set_visible(False)
        self.edit_btn.set_sensitive(True)
        self.state_store.record_recent(path)

        base = os.path.basename(path)
        iso = format_isolated_filename(base)
        self.title_label.set_text(iso)
        self.set_title(f"{iso} — {t('app_title')}")
        self._refresh_playlist_ui()

        if self.gl_area.get_realized() or not self.engine.is_initialized:
            self._start_playback(path)
        else:
            self._pending_load_path = path

    def open_url(self, url: str) -> bool:
        clean = (url or "").strip()
        if not re.match(r"^(https?|rtsps?|mmsh?|rtp|rtmp|udp)://\S+$", clean, re.IGNORECASE):
            self._show_osd(t("open_url_invalid"))
            return False

        self.dismiss_resume_banner()
        self.thumb_popover.popdown()
        self.thumb_picture.set_visible(False)
        self.thumb_extractor.set_video(None)

        prev_path = self.playlist_mgr.current_path
        if prev_path and prev_path != clean and self.engine.is_initialized:
            dur = self.engine.get_duration()
            if dur > 0.0:
                self.state_store.set_position(prev_path, self.engine.get_time_pos(), dur)

        self.playlist_mgr.select_path(clean)
        self._ab_point_a = None
        self._ab_point_b = None
        self.welcome_box.set_visible(False)
        self.edit_btn.set_sensitive(False)
        self.state_store.record_recent(clean)

        iso = format_isolated_filename(clean)
        self.title_label.set_text(iso)
        self.set_title(f"{iso} — {t('app_title')}")
        self._refresh_playlist_ui()

        if self.gl_area.get_realized() or not self.engine.is_initialized:
            self._start_playback(clean)
        else:
            self._pending_load_path = clean
        return True

    def stop_playback(self) -> None:
        self.dismiss_resume_banner()
        self.thumb_popover.popdown()
        self.thumb_picture.set_visible(False)
        self.thumb_extractor.set_video(None)
        cur = self.playlist_mgr.current_path
        if cur and self.engine.is_initialized:
            dur = self.engine.get_duration()
            if dur > 0.0:
                self.state_store.set_position(cur, self.engine.get_time_pos(), dur)
            self.engine.stop()
        self.state_store.save()
        self.playlist_mgr.current_index = -1
        self._cached_chapters = []
        self._sync_play_pause_state(True, trigger_hud=False)
        self.edit_btn.set_sensitive(False)
        self.title_label.set_text(format_isolated_filename(t("app_title")))
        self.set_title(t("app_title"))
        self._refresh_welcome_recent()
        self.welcome_box.set_visible(True)
        self.mpris_service.emit_properties_changed(("PlaybackStatus", "Metadata", "CanPlay", "CanPause", "CanSeek"))

    def _start_playback(self, path: str) -> None:
        if not self.engine.is_initialized:
            self._show_osd(t("err_mpv_missing"))
            return
        mode, immediate_pos, ask_pos = self.state_store.get_resume_action(path)
        self.engine.load_file(path, start_seconds=immediate_pos)
        self._sync_play_pause_state(False, trigger_hud=True)
        self._reveal_hud(auto_hide=True)

        if mode == "ask" and ask_pos > 0.0:
            self._show_resume_banner(ask_pos, is_auto_restart=False)
        elif mode == "auto" and immediate_pos > 0.0:
            self._show_resume_banner(immediate_pos, is_auto_restart=True)
        else:
            self.dismiss_resume_banner()

    def _show_resume_banner(self, pos_seconds: float, is_auto_restart: bool = False) -> None:
        self._pending_resume_seek = 0.0 if is_auto_restart else float(pos_seconds)
        if is_auto_restart:
            self.resume_msg_lbl.set_text(t("osd_resumed_at", t=format_time(pos_seconds)))
            self.resume_action_btn.set_label(t("start_beginning_btn"))
        else:
            self.resume_msg_lbl.set_text(t("resume_banner_msg", t=format_time(pos_seconds)))
            self.resume_action_btn.set_label(t("resume_btn"))
        self.resume_revealer.set_reveal_child(True)
        self.resume_revealer.set_can_target(True)
        if self._resume_timer_id:
            GLib.source_remove(self._resume_timer_id)
        self._resume_timer_id = GLib.timeout_add(RESUME_BANNER_MS, self.dismiss_resume_banner)

    def dismiss_resume_banner(self) -> bool:
        if self._resume_timer_id:
            GLib.source_remove(self._resume_timer_id)
            self._resume_timer_id = 0
        self.resume_revealer.set_reveal_child(False)
        self.resume_revealer.set_can_target(False)
        return False

    def _on_resume_action_clicked(self, _btn) -> None:
        target = self._pending_resume_seek
        self.dismiss_resume_banner()
        if self.engine.is_initialized:
            self.engine.seek_absolute(target)

    def set_resume_mode(self, mode: str) -> None:
        if mode in playlist.StateStore.RESUME_MODES:
            self._resume_mode = mode
            self.state_store.set_setting("resume_mode", mode)
            popovers.sync_settings_active_states(self)

    def play_next(self, wrap: bool = False) -> None:
        nxt = self.playlist_mgr.next(wrap=wrap)
        if nxt:
            self.play_path(nxt)

    def play_previous(self, wrap: bool = False) -> None:
        prev = self.playlist_mgr.previous(wrap=wrap)
        if prev:
            self.play_path(prev)

    def _clear_playlist(self) -> None:
        self.playlist_mgr.clear()
        self._refresh_playlist_ui()

    def _refresh_playlist_ui(self) -> None:
        while True:
            row = self.playlist_listbox.get_row_at_index(0)
            if row is None:
                break
            self.playlist_listbox.remove(row)

        count = len(self.playlist_mgr.items)
        self.playlist_header_title.set_subtitle(
            t("playlist_count", n=count) if count else t("playlist_empty")
        )
        self.prev_btn.set_sensitive(self.playlist_mgr.has_previous(wrap=(self._loop_mode == "playlist")))
        self.next_btn.set_sensitive(self.playlist_mgr.has_next(wrap=(self._loop_mode == "playlist")))

        for idx, item_path in enumerate(self.playlist_mgr.items):
            row = Gtk.ListBoxRow()
            row._playlist_index = idx
            disp = item_path if playlist.is_network_url(item_path) else os.path.basename(item_path)
            lbl = Gtk.Label(label=format_isolated_filename(disp), xalign=0)
            lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)
            lbl.set_margin_start(8)
            lbl.set_margin_end(8)
            row.set_child(lbl)
            if idx == self.playlist_mgr.current_index:
                row.add_css_class("sadeem-playlist-active")
                self.playlist_listbox.select_row(row)
            self.playlist_listbox.append(row)

    def _on_playlist_row_activated(self, _listbox, row) -> None:
        idx = getattr(row, "_playlist_index", -1)
        path = self.playlist_mgr.set_current(idx)
        if path:
            self.play_path(path)

    def _on_playlist_toggled(self, btn: Gtk.ToggleButton) -> None:
        self.split_view.set_show_sidebar(btn.get_active())

    def toggle_playlist(self) -> None:
        active = not self.split_view.get_show_sidebar()
        self.split_view.set_show_sidebar(active)
        self.playlist_toggle_btn.set_active(active)

    # -----------------------------------------------------------------------
    # Playback, Audio & Video Actions
    # -----------------------------------------------------------------------
    def toggle_play_pause(self) -> None:
        if not self.engine.is_initialized or not self.playlist_mgr.current_path:
            return
        paused = self.engine.toggle_pause()
        self._sync_play_pause_state(paused, trigger_hud=True)
        self._show_osd(t("pause") if paused else t("play"))

    def seek_relative(self, delta: float) -> None:
        if not self.engine.is_initialized or not self.playlist_mgr.current_path:
            return
        self.engine.seek(delta)
        sec_abs = int(abs(delta))
        self._show_osd(t("osd_seek_fwd", s=sec_abs) if delta >= 0 else t("osd_seek_back", s=sec_abs))
        self._reveal_hud(auto_hide=True)

    def skip_intro(self, seconds: float = 85.0) -> None:
        if not self.engine.is_initialized or not self.playlist_mgr.current_path:
            return
        self.engine.seek(seconds)
        self._show_osd(t("osd_skip_intro") if seconds >= 0 else t("osd_seek_back", s=int(abs(seconds))))
        self._reveal_hud(auto_hide=True)

    def adjust_volume(self, delta: float) -> None:
        if not self.engine.is_initialized:
            return
        cur = self.engine.get_volume()
        new_vol = max(0.0, min(200.0, round(cur + delta)))
        self.engine.set_volume(new_vol)
        if new_vol > 0 and self.engine.get_mute():
            self.engine.set_mute(False)
        self.state_store.set_setting("volume", new_vol)
        self.state_store.set_setting("muted", False)
        self._updating_ui = True
        try:
            self.volume_scale.set_value(new_vol)
            self._update_mute_icon(False, new_vol)
        finally:
            self._updating_ui = False
        self.mpris_service.emit_properties_changed(("Volume",))
        self._show_osd(t("osd_volume", v=int(round(new_vol))))

    def toggle_mute(self) -> None:
        if not self.engine.is_initialized:
            return
        muted = not self.engine.get_mute()
        self.engine.set_mute(muted)
        vol = self.engine.get_volume()
        self.state_store.set_setting("muted", muted)
        self._update_mute_icon(muted, vol)
        self.mpris_service.emit_properties_changed(("Volume",))
        self._show_osd(t("osd_muted") if muted else t("osd_unmuted", v=int(round(vol))))

    def _update_mute_icon(self, muted: bool, vol: float) -> None:
        if muted or vol <= 0:
            icon = "audio-volume-muted-symbolic"
        elif vol < 35:
            icon = "audio-volume-low-symbolic"
        elif vol < 85:
            icon = "audio-volume-medium-symbolic"
        else:
            icon = "audio-volume-high-symbolic"
        self.mute_btn.set_icon_name(icon)
        if not muted and vol > 100.0:
            self.mute_btn.add_css_class("sadeem-vol-boost")
        else:
            self.mute_btn.remove_css_class("sadeem-vol-boost")

    def _adjust_audio_delay(self, delta: float) -> None:
        self._set_audio_delay(self._audio_delay_val + delta)

    def _set_audio_delay(self, value: float) -> None:
        self._audio_delay_val = max(-30.0, min(30.0, round(value, 1)))
        self.audio_delay_lbl.set_text(f"{self._audio_delay_val:+.1f}s" if self._audio_delay_val else "0.0s")
        if self.engine.is_initialized:
            self.engine.set_audio_delay(self._audio_delay_val)

    def _on_night_mode_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self._updating_ui:
            return
        enabled = bool(switch.get_active())
        self.state_store.set_setting("audio_night_mode", enabled)
        if self.engine.is_initialized:
            self.engine.set_night_mode(enabled)

    def set_audio_eq_preset(self, preset: str) -> None:
        self._audio_eq_preset = preset
        self.state_store.set_setting("audio_eq_preset", preset)
        if self.engine.is_initialized:
            self.engine.set_audio_eq_preset(preset)
        popovers.sync_tracks_active_states(self)

    def set_speed(self, speed: float) -> None:
        clamped = max(0.25, min(4.0, round(speed, 2)))
        self._current_speed = clamped
        if self.engine.is_initialized:
            self.engine.set_speed(clamped)
        self.state_store.set_setting("speed", clamped)
        popovers.sync_settings_active_states(self)
        self.mpris_service.emit_properties_changed(("Rate",))
        self._show_osd(t("osd_speed", v=clamped))

    def _on_pause_on_minimize_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self._updating_ui:
            return
        self._pause_on_minimize = bool(switch.get_active())
        self.state_store.set_setting("pause_on_minimize", self._pause_on_minimize)

    def _on_window_realize_surface(self, *_args) -> None:
        surf = self.get_surface()
        if surf is None or not hasattr(surf, "connect"):
            return
        if self._tracked_surface is surf and self._surface_state_handler_id:
            return
        self._tracked_surface = surf
        self._surface_state_handler_id = surf.connect("notify::state", self._on_surface_state_changed)

    def _on_surface_state_changed(self, surface, _pspec) -> None:
        if not hasattr(surface, "get_state"):
            return
        minimized = bool(surface.get_state() & Gdk.ToplevelState.MINIMIZED)
        self._handle_window_minimized(minimized)

    def _handle_window_minimized(self, minimized: bool) -> None:
        if minimized:
            if self._pause_on_minimize and self._is_playing and self.engine.is_initialized:
                self._paused_by_minimize = True
                self.engine.set_paused(True)
                self._sync_play_pause_state(True, trigger_hud=False)
        else:
            self._paused_by_minimize = False

    def step_speed(self, delta: float) -> None:
        cur = self.engine.get_speed() if self.engine.is_initialized else self._current_speed
        self.set_speed(cur + delta)

    def set_loop_mode(self, mode: str) -> None:
        self._loop_mode = mode
        self.state_store.set_setting("loop_mode", mode)
        if self.engine.is_initialized:
            self.engine.set_loop_file(mode == "file")
        self._refresh_playlist_ui()
        popovers.sync_settings_active_states(self)
        if mode == "file":
            self._show_osd(t("osd_loop_file"))
        elif mode == "playlist":
            self._show_osd(t("osd_loop_playlist"))
        else:
            self._show_osd(t("osd_loop_off"))

    def _on_ab_action(self, action: str) -> None:
        if not self.engine.is_initialized:
            return
        if action == "a":
            self._ab_point_a = self.engine.get_time_pos()
            self.engine.set_ab_loop(self._ab_point_a, self._ab_point_b)
            self._show_osd(t("osd_ab_a", t=format_time(self._ab_point_a)))
        elif action == "b":
            self._ab_point_b = self.engine.get_time_pos()
            self.engine.set_ab_loop(self._ab_point_a, self._ab_point_b)
            self._show_osd(t("osd_ab_b"))
        else:
            self._ab_point_a = None
            self._ab_point_b = None
            self.engine.set_ab_loop(None, None)
            self._show_osd(t("osd_ab_off"))
        popovers.sync_settings_active_states(self)

    def cycle_ab_loop(self) -> None:
        if self._ab_point_a is None:
            self._on_ab_action("a")
        elif self._ab_point_b is None:
            self._on_ab_action("b")
        else:
            self._on_ab_action("clear")

    def toggle_subtitles(self) -> None:
        if not self.engine.is_initialized:
            return
        tracks = self.engine.get_tracks()["sub"]
        if not tracks:
            self._show_osd(t("osd_sub_off"))
            return
        selected = next((s for s in tracks if s.get("selected")), None)
        if selected:
            self._last_sid = selected["id"]
            self.engine.set_subtitle_track(None)
            self._show_osd(t("osd_sub_off"))
        else:
            target = next((s["id"] for s in tracks if s["id"] == self._last_sid), tracks[0]["id"])
            self.engine.set_subtitle_track(target)
            self._show_osd(t("osd_sub_on"))

    def cycle_audio_track(self) -> None:
        if not self.engine.is_initialized:
            return
        tracks = self.engine.get_tracks()["audio"]
        if len(tracks) <= 1:
            return
        cur_idx = next((i for i, a in enumerate(tracks) if a.get("selected")), 0)
        nxt = tracks[(cur_idx + 1) % len(tracks)]
        self.engine.set_audio_track(nxt["id"])
        label = nxt.get("title") or nxt.get("lang") or t("track_untitled", id=nxt["id"])
        self._show_osd(t("osd_audio_next", name=label))

    def take_screenshot(self) -> None:
        if not self.engine.is_initialized or not self.playlist_mgr.current_path:
            return
        folder = get_screenshots_dir()
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        prefix = i18n.t("filename_screenshot_prefix") or "video_snapshot"
        out_path = os.path.join(folder, f"{prefix}_{stamp}.png")
        rc = self.engine.take_screenshot(out_path)
        if rc >= 0:
            self._show_osd(t("osd_screenshot_saved", name=os.path.basename(out_path)))

    # -----------------------------------------------------------------------
    # Fullscreen (strictly zero size/maximize geometry mutations) & Mini Player
    # -----------------------------------------------------------------------
    def toggle_fullscreen(self) -> None:
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_fullscreen_changed(self, *_args) -> None:
        self._is_fullscreen = self.is_fullscreen()
        self.fs_btn.set_icon_name(
            "view-restore-symbolic" if self._is_fullscreen else "view-fullscreen-symbolic"
        )
        if not self._is_fullscreen:
            self._set_cursor_hidden(False)
        else:
            self._schedule_hud_hide()

    def toggle_mini_mode(self) -> None:
        """Toggle compact mini player (~480x270) without affecting fullscreen state."""
        if self.is_fullscreen():
            self.unfullscreen()
        entering = not self._is_mini_mode
        self._is_mini_mode = entering
        if entering:
            w = self.get_width() or 1120
            h = self.get_height() or 680
            self._pre_mini_size = (w, h)
            if self.split_view.get_show_sidebar():
                self.toggle_playlist()
            self.set_size_request(360, 210)
            self.set_default_size(480, 270)
        else:
            rw, rh = self._pre_mini_size or (1120, 680)
            self.set_size_request(520, 340)
            self.set_default_size(rw, rh)

        for wgt in (
            self.edit_btn,
            self.info_btn,
            self.playlist_toggle_btn,
            self.prev_btn,
            self.skip_back_btn,
            self.skip_fwd_btn,
            self.next_btn,
        ):
            wgt.set_visible(not entering)
        popovers.sync_settings_active_states(self)

    # -----------------------------------------------------------------------
    # Zoom, Panscan, Subtitle Sync / Style
    # -----------------------------------------------------------------------
    def _set_aspect(self, mode: str) -> None:
        self._current_aspect = mode
        if self.engine.is_initialized:
            self.engine.set_aspect_ratio(mode)
        popovers.sync_settings_active_states(self)
        label = t("aspect_auto") if mode == "auto" else (t("aspect_fill") if mode == "fill" else mode)
        self._show_osd(f"{t('aspect_ratio')}: {label}")

    def _set_rotation(self, degrees: int) -> None:
        self._current_rotation = degrees
        if self.engine.is_initialized:
            self.engine.set_rotation(degrees)
        popovers.sync_settings_active_states(self)
        self._show_osd(f"{t('rotation')}: {degrees}°")

    def _adjust_video_zoom(self, delta: float) -> None:
        self.set_video_zoom(self._video_zoom + delta)

    def set_video_zoom(self, zoom: float) -> None:
        self._video_zoom = max(-0.5, min(2.0, round(float(zoom), 2)))
        if self.engine.is_initialized:
            self.engine.set_video_zoom(self._video_zoom)
        popovers.sync_settings_active_states(self)

    def _on_panscan_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self._updating_ui:
            return
        self._panscan_enabled = bool(switch.get_active())
        if self.engine.is_initialized:
            self.engine.set_panscan(1.0 if self._panscan_enabled else 0.0)

    def reset_video_view(self, reset_speed: bool = False) -> None:
        self._video_zoom = 0.0
        self._panscan_enabled = False
        self._current_aspect = "auto"
        self._current_rotation = 0
        self._updating_ui = True
        try:
            self.panscan_switch.set_active(False)
        finally:
            self._updating_ui = False
        if self.engine.is_initialized:
            self.engine.set_video_zoom(0.0)
            self.engine.set_panscan(0.0)
            self.engine.set_aspect_ratio("auto")
            self.engine.set_rotation(0)
        if reset_speed:
            self.set_speed(1.0)
        popovers.sync_settings_active_states(self)
        self._show_osd(t("osd_view_reset"))

    def _on_eq_changed(self, scale: Gtk.Scale, prop_key: str) -> None:
        val = int(round(scale.get_value()))
        if prop_key in self._eq_value_labels:
            self._eq_value_labels[prop_key].set_text(str(val))
        if self._updating_ui or not self.engine.is_initialized:
            return
        self.engine.set_equalizer(**{prop_key: float(val)})

    def _reset_equalizer(self) -> None:
        self._updating_ui = True
        try:
            for k, sc in self.eq_scales.items():
                sc.set_value(0.0)
                if k in self._eq_value_labels:
                    self._eq_value_labels[k].set_text("0")
        finally:
            self._updating_ui = False
        if self.engine.is_initialized:
            self.engine.reset_equalizer()
        self._show_osd(t("eq_reset"))

    def _adjust_sub_delay(self, delta: float) -> None:
        self._set_sub_delay(self._sub_delay_val + delta)

    def _set_sub_delay(self, value: float) -> None:
        self._sub_delay_val = max(-30.0, min(30.0, round(value, 1)))
        self.sub_delay_lbl.set_text(f"{self._sub_delay_val:+.1f}s" if self._sub_delay_val else "0.0s")
        if self.engine.is_initialized:
            self.engine.set_sub_delay(self._sub_delay_val)

    def _adjust_sub_scale(self, delta: float) -> None:
        self._set_sub_scale(self._sub_scale_val + delta)

    def _set_sub_scale(self, value: float) -> None:
        self._sub_scale_val = max(0.4, min(2.5, round(value, 1)))
        self.sub_scale_lbl.set_text(f"{self._sub_scale_val:.1f}x")
        if self.engine.is_initialized:
            self.engine.set_sub_scale(self._sub_scale_val)

    def _on_sub_bidi_compat_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self._updating_ui:
            return
        enabled = bool(switch.get_active())
        self.state_store.set_setting("sub_bidi_compat", enabled)
        if self.engine.is_initialized:
            self.engine.set_sub_bidi_compat(enabled)

    def _adjust_sub_pos(self, delta: int) -> None:
        self.set_sub_pos(self._sub_pos_val + delta)

    def set_sub_pos(self, pos: int) -> None:
        self._sub_pos_val = max(70, min(100, int(pos)))
        self.state_store.set_setting("sub_pos", self._sub_pos_val)
        if self.engine.is_initialized:
            self.engine.set_sub_pos(self._sub_pos_val)
        popovers.sync_tracks_active_states(self)

    def set_sub_color(self, color: str) -> None:
        self._sub_color_val = str(color)
        self.state_store.set_setting("sub_color", self._sub_color_val)
        if self.engine.is_initialized:
            self.engine.set_sub_color(self._sub_color_val)
        popovers.sync_tracks_active_states(self)

    def _on_sub_back_box_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self._updating_ui:
            return
        enabled = bool(switch.get_active())
        self.state_store.set_setting("sub_back_box", enabled)
        if self.engine.is_initialized:
            self.engine.set_sub_back_box(enabled)

    def set_sub_font(self, font_name: str) -> None:
        self._sub_font_val = str(font_name or "")
        self.state_store.set_setting("sub_font", self._sub_font_val)
        if self.engine.is_initialized:
            self.engine.set_sub_font(self._sub_font_val)
        popovers.sync_tracks_active_states(self)

    # -----------------------------------------------------------------------
    # HUD Auto-hide (2.5s), Cursor Hiding, Manual Toggle (H) & Transient OSD
    # -----------------------------------------------------------------------
    def _set_cursor_hidden(self, hidden: bool) -> None:
        cursor = Gdk.Cursor.new_from_name("none", None) if hidden else None
        self.video_overlay.set_cursor(cursor)
        self.gl_area.set_cursor(cursor)

    def _set_hud_visible(self, visible: bool) -> None:
        self.top_revealer.set_reveal_child(visible)
        self.top_revealer.set_can_target(visible)
        self.bottom_revealer.set_reveal_child(visible)
        self.bottom_revealer.set_can_target(visible)
        if visible:
            self._set_cursor_hidden(False)
        elif self.is_fullscreen():
            self._set_cursor_hidden(True)

    def _set_pointer_over_hud(self, over: bool) -> None:
        self._pointer_over_hud = over
        if over:
            self._reveal_hud(auto_hide=False)
        else:
            self._schedule_hud_hide()

    def _reveal_hud(self, auto_hide: bool = True) -> None:
        self._set_hud_visible(True)
        if self._hide_hud_id:
            GLib.source_remove(self._hide_hud_id)
            self._hide_hud_id = 0
        if auto_hide:
            self._schedule_hud_hide()

    def _schedule_hud_hide(self) -> None:
        if self._hide_hud_id:
            GLib.source_remove(self._hide_hud_id)
            self._hide_hud_id = 0
        if (
            self._destroyed
            or not self.playlist_mgr.current_path
            or self._pointer_over_hud
            or self._active_popovers > 0
            or not self._is_playing
        ):
            return
        self._hide_hud_id = GLib.timeout_add(OSD_HIDE_DELAY_MS, self._on_hud_hide_timeout)

    def _on_hud_hide_timeout(self) -> bool:
        self._hide_hud_id = 0
        if (
            self._destroyed
            or self._pointer_over_hud
            or self._active_popovers > 0
            or not self.playlist_mgr.current_path
            or not self._is_playing
        ):
            return False
        self._set_hud_visible(False)
        return False

    def toggle_hud(self) -> None:
        if self._hide_hud_id:
            GLib.source_remove(self._hide_hud_id)
            self._hide_hud_id = 0
        if self.top_revealer.get_reveal_child() or self.bottom_revealer.get_reveal_child():
            self._set_hud_visible(False)
        else:
            self._reveal_hud(auto_hide=True)

    def _show_osd(self, text: str) -> None:
        self.osd_label.set_text(text)
        self.osd_revealer.set_reveal_child(True)
        if self._osd_hide_id:
            GLib.source_remove(self._osd_hide_id)
            self._osd_hide_id = 0
        self._osd_hide_id = GLib.timeout_add(OSD_PILL_MS, self._hide_osd_pill)

    def _hide_osd_pill(self) -> bool:
        self._osd_hide_id = 0
        self.osd_revealer.set_reveal_child(False)
        return False

    # -----------------------------------------------------------------------
    # UI Signal Callbacks & File Dialogs
    # -----------------------------------------------------------------------
    def _on_seek_change_value(self, _scale, _scroll_type, value: float) -> bool:
        if self._updating_ui or not self.engine.is_initialized:
            return False
        self.dismiss_resume_banner()
        self._seeking_from_ui = True
        try:
            self.engine.seek_absolute(value)
            self.time_pos_label.set_text(format_time(value))
        finally:
            self._seeking_from_ui = False
        self._reveal_hud(auto_hide=True)
        return False

    def _on_volume_slider_changed(self, scale: Gtk.Scale) -> None:
        if self._updating_ui:
            return
        val = float(scale.get_value())
        if self.engine.is_initialized:
            self.engine.set_volume(val)
            if val > 0 and self.engine.get_mute():
                self.engine.set_mute(False)
        self.state_store.set_setting("volume", val)
        self.state_store.set_setting("muted", False)
        self._update_mute_icon(False, val)
        self.mpris_service.emit_properties_changed(("Volume",))
        self._show_osd(t("osd_volume", v=int(round(val))))

    def _on_video_clicked(self, _gesture, n_press: int, _x: float, _y: float) -> None:
        self._reveal_hud(auto_hide=True)
        if n_press == 2:
            if self._click_timer_id:
                GLib.source_remove(self._click_timer_id)
                self._click_timer_id = 0
            self.toggle_fullscreen()
        elif n_press == 1 and self.playlist_mgr.current_path:
            if self._click_timer_id:
                GLib.source_remove(self._click_timer_id)
            self._click_timer_id = GLib.timeout_add(CLICK_DISAMBIGUATION_MS, self._on_single_click_fire)

    def _on_single_click_fire(self) -> bool:
        self._click_timer_id = 0
        if not self._destroyed and self.playlist_mgr.current_path:
            self.toggle_play_pause()
        return False

    def _on_video_scroll(self, _ctrl, _dx: float, dy: float) -> bool:
        self.adjust_volume(-5.0 if dy > 0 else 5.0)
        return True

    def _on_files_dropped(self, _drop, value, _x: float, _y: float) -> bool:
        paths: List[str] = []
        if isinstance(value, Gdk.FileList):
            for f in value.get_files():
                p = f.get_path()
                if p:
                    paths.append(p)
        elif isinstance(value, Gio.File):
            p = value.get_path()
            if p:
                paths.append(p)
        if paths:
            self.open_paths(paths)
            return True
        return False

    def _on_edit_video_clicked(self, _btn) -> None:
        if self.playlist_mgr.current_path:
            if self.engine.is_initialized and not self.engine.is_paused():
                self.engine.set_paused(True)
                self._sync_play_pause_state(True, trigger_hud=True)
            launch_video_editor(self.playlist_mgr.current_path)

    def prompt_open_file(self, add_to_playlist: bool = False) -> None:
        flt = Gtk.FileFilter()
        flt.set_name(t("filter_videos"))
        for ext in sorted(playlist.VIDEO_EXTENSIONS):
            flt.add_suffix(ext.lstrip("."))

        if hasattr(Gtk, "FileDialog"):
            dlg = Gtk.FileDialog(title=t("add_files") if add_to_playlist else t("open_file"))
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(flt)
            dlg.set_filters(filters)

            def _on_done(d, res):
                try:
                    files = d.open_multiple_finish(res)
                except Exception:
                    return
                paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
                paths = [p for p in paths if p]
                if not paths:
                    return
                if add_to_playlist and self.playlist_mgr.current_path:
                    self.playlist_mgr.add_files(paths)
                    self._refresh_playlist_ui()
                else:
                    self.open_paths(paths)

            dlg.open_multiple(self, None, _on_done)

    def _on_load_sub_clicked(self, _btn) -> None:
        self.tracks_popover.popdown()
        flt = Gtk.FileFilter()
        flt.set_name(t("filter_subtitles"))
        for ext in sorted(playlist.SUBTITLE_EXTENSIONS):
            flt.add_suffix(ext.lstrip("."))

        if hasattr(Gtk, "FileDialog"):
            dlg = Gtk.FileDialog(title=t("load_subtitle"))
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(flt)
            dlg.set_filters(filters)

            def _on_done(d, res):
                try:
                    f = d.open_finish(res)
                except Exception:
                    return
                path = f.get_path() if f else None
                if path and self.engine.is_initialized:
                    self.engine.add_subtitle(path)
                    self._show_osd(t("sub_added"))

            dlg.open(self, None, _on_done)

    def prompt_open_url(self):
        return popovers.prompt_open_url(self)

    def build_media_info_page(self) -> Gtk.Widget:
        return popovers.build_media_info_page(self)

    def show_media_info_dialog(self):
        return popovers.present_adw_dialog(self, t("media_info"), self.build_media_info_page(), width=440, height=520)

    def build_shortcuts_page(self) -> Gtk.Widget:
        return popovers.build_shortcuts_page()

    def show_shortcuts_dialog(self):
        return popovers.present_adw_dialog(self, t("shortcuts_title"), self.build_shortcuts_page(), width=500, height=560)

    # -----------------------------------------------------------------------
    # Keyboard Shortcut Router
    # -----------------------------------------------------------------------
    def _on_key_pressed(self, _ctrl, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)

        focus = self.get_focus()
        if isinstance(focus, Gtk.Text) or isinstance(focus, Gtk.Editable):
            if keyval != Gdk.KEY_Escape:
                return False

        if keyval in (Gdk.KEY_space, Gdk.KEY_k, Gdk.KEY_K):
            self.toggle_play_pause()
            return True
        if keyval in (Gdk.KEY_o, Gdk.KEY_O) and ctrl:
            self.prompt_open_file()
            return True
        if keyval in (Gdk.KEY_u, Gdk.KEY_U) and ctrl:
            self.prompt_open_url()
            return True
        if keyval in (Gdk.KEY_question, Gdk.KEY_F1):
            self.show_shortcuts_dialog()
            return True
        if keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self.toggle_hud()
            return True
        if keyval == Gdk.KEY_Right:
            if shift:
                self.skip_intro(85.0)
            else:
                self.seek_relative(30.0 if ctrl else 5.0)
            return True
        if keyval == Gdk.KEY_Left:
            if shift:
                self.skip_intro(-85.0)
            else:
                self.seek_relative(-30.0 if ctrl else -5.0)
            return True
        if keyval == Gdk.KEY_Up:
            self.adjust_volume(5.0)
            return True
        if keyval == Gdk.KEY_Down:
            self.adjust_volume(-5.0)
            return True
        if keyval in (Gdk.KEY_m, Gdk.KEY_M):
            if alt:
                self.toggle_mini_mode()
            else:
                self.toggle_mute()
            return True
        if keyval in (Gdk.KEY_f, Gdk.KEY_F, Gdk.KEY_F11):
            self.toggle_fullscreen()
            return True
        if keyval == Gdk.KEY_Escape:
            if self.is_fullscreen():
                self.unfullscreen()
                return True
            return False
        if keyval == Gdk.KEY_bracketleft:
            self.step_speed(-0.25)
            return True
        if keyval == Gdk.KEY_bracketright:
            self.step_speed(0.25)
            return True
        if keyval == Gdk.KEY_BackSpace:
            self.reset_video_view(reset_speed=True)
            return True
        if keyval in (Gdk.KEY_period, Gdk.KEY_greater):
            if self.engine.is_initialized:
                self.engine.frame_step()
                self._show_osd(t("osd_frame_next"))
            return True
        if keyval in (Gdk.KEY_comma, Gdk.KEY_less):
            if self.engine.is_initialized:
                self.engine.frame_back_step()
                self._show_osd(t("osd_frame_prev"))
            return True
        if keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.take_screenshot()
            return True
        if keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self.toggle_subtitles()
            return True
        if keyval in (Gdk.KEY_a, Gdk.KEY_A):
            self.cycle_audio_track()
            return True
        if keyval in (Gdk.KEY_l, Gdk.KEY_L):
            self.cycle_ab_loop()
            return True
        if keyval in (Gdk.KEY_p, Gdk.KEY_P):
            self.toggle_playlist()
            return True
        if keyval in (Gdk.KEY_i, Gdk.KEY_I):
            self.show_media_info_dialog()
            return True
        if keyval == Gdk.KEY_Page_Up:
            self.play_previous()
            return True
        if keyval == Gdk.KEY_Page_Down:
            self.play_next()
            return True
        return False

    # -----------------------------------------------------------------------
    # Safe Teardown
    # -----------------------------------------------------------------------
    def shutdown(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True

        self._update_idle_inhibit(False)
        self.thumb_extractor.shutdown()
        self.mpris_service.shutdown()
        if getattr(self, "_tracked_surface", None) is not None and self._surface_state_handler_id:
            try:
                self._tracked_surface.disconnect(self._surface_state_handler_id)
            except Exception:
                pass
            self._surface_state_handler_id = 0
            self._tracked_surface = None
        if hasattr(self, "thumb_popover") and self.thumb_popover is not None:
            try:
                self.thumb_popover.popdown()
                self.thumb_popover.unparent()
            except Exception:
                pass

        for attr in ("_poll_id", "_hide_hud_id", "_osd_hide_id", "_resume_timer_id", "_click_timer_id"):
            sid = getattr(self, attr, 0)
            if sid:
                try:
                    GLib.source_remove(sid)
                except Exception:
                    pass
                setattr(self, attr, 0)

        cur = self.playlist_mgr.current_path
        if cur and self.engine.is_initialized:
            dur = self.engine.get_duration()
            if dur > 0.0:
                self.state_store.set_position(cur, self.engine.get_time_pos(), dur)
        self.state_store.save()

        self.engine.destroy(gl_area=self.gl_area)

    def _on_close_request(self, *_args) -> bool:
        self.shutdown()
        return False


class SadeemVideoApp(Adw.Application):
    """Standalone Libadwaita application for Sadeem Video."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
            **kwargs,
        )
        self._css_loaded = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        # Mandatory after gtk_init/Adw startup so libmpv receives LC_NUMERIC=C
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except locale.Error:
            pass

        if not self._css_loaded:
            provider = Gtk.CssProvider()
            provider.load_from_string(SADEEM_VIDEO_PLAYER_CSS)
            disp = Gdk.Display.get_default()
            if disp is not None:
                Gtk.StyleContext.add_provider_for_display(
                    disp, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            self._css_loaded = True

    def do_activate(self) -> None:
        win = self.get_active_window()
        if win is None:
            win = SadeemVideoWindow(app=self)
        win.present()

    def do_open(self, files, n_files: int, _hint: str) -> None:
        paths = []
        urls = []
        for f in files[:n_files]:
            p = f.get_path()
            if p:
                paths.append(p)
            else:
                uri = f.get_uri()
                if uri and playlist.is_network_url(uri):
                    urls.append(uri)
        win = self.get_active_window()
        if win is None:
            win = SadeemVideoWindow(app=self, initial_files=paths)
            if not paths and urls:
                win.open_url(urls[0])
        else:
            if paths:
                win.open_paths(paths)
            elif urls:
                win.open_url(urls[0])
        win.present()


def main(argv: Optional[List[str]] = None) -> int:
    app = SadeemVideoApp()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
