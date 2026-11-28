#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Video (فيديو سديم) — Standalone GTK4 + Libadwaita Video Player
built directly on libmpv.so.2 via ctypes and Gtk.GLArea.
"""

import locale
import os
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional

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
import mpv_engine
import playlist

t = i18n.t

APP_ID = "org.sadeem.Video"
OSD_HIDE_DELAY_MS = 2500
OSD_PILL_MS = 1400
POLL_INTERVAL_MS = 67
CLICK_DISAMBIGUATION_MS = 220

SADEEM_VIDEO_PLAYER_CSS = """
.sadeem-video-stage {
    background-color: #000000;
}

.sadeem-hud-top {
    background-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.72), transparent);
    background-color: transparent;
    color: #ffffff;
    border: none;
    border-radius: 0px;
    padding: 10px 16px 20px 16px;
}

.sadeem-osd-btn {
    color: #f8fafc;
    background-color: rgba(20, 20, 26, 0.52);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 999px;
    min-width: 34px;
    min-height: 34px;
    padding: 4px 10px;
}
.sadeem-osd-btn:hover {
    background-color: rgba(255, 255, 255, 0.18);
    color: #ffffff;
}
.sadeem-osd-btn:disabled {
    opacity: 0.45;
}

.sadeem-hud-capsule {
    background-color: rgba(20, 20, 24, 0.88);
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 18px;
    padding: 10px 16px;
    margin: 0 16px 18px 16px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
}

.sadeem-hud-btn {
    color: #f8fafc;
    background-color: transparent;
    border-radius: 999px;
    min-width: 34px;
    min-height: 34px;
    padding: 4px 8px;
}
.sadeem-hud-btn:hover {
    background-color: rgba(255, 255, 255, 0.14);
}
.sadeem-hud-btn:disabled {
    color: rgba(248, 250, 252, 0.35);
}

.sadeem-play-btn {
    background-color: #7a1c33;
    color: #ffffff;
    border-radius: 999px;
    min-width: 38px;
    min-height: 38px;
    padding: 0;
}
.sadeem-play-btn:hover {
    background-color: #93233e;
}

.sadeem-video-title {
    font-weight: 600;
    font-size: 13px;
    color: #ffffff;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.85);
}

.sadeem-time-label {
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    font-weight: 600;
    color: rgba(248, 250, 252, 0.94);
    min-width: 48px;
}

.sadeem-seek-scale trough {
    min-height: 6px;
    border-radius: 999px;
    background-color: rgba(255, 255, 255, 0.22);
}
.sadeem-seek-scale highlight {
    border-radius: 999px;
    background-color: #7a1c33;
}
.sadeem-seek-scale slider {
    min-width: 14px;
    min-height: 14px;
    margin: -4px;
    border-radius: 999px;
    background-color: #ffffff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.55);
}

.sadeem-vol-scale trough {
    min-height: 5px;
    border-radius: 999px;
    background-color: rgba(255, 255, 255, 0.22);
}
.sadeem-vol-scale highlight {
    border-radius: 999px;
    background-color: rgba(248, 250, 252, 0.85);
}
.sadeem-vol-scale slider {
    min-width: 12px;
    min-height: 12px;
    margin: -3px;
    border-radius: 999px;
    background-color: #ffffff;
}

.sadeem-osd-badge {
    background-color: rgba(15, 16, 20, 0.86);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 999px;
    padding: 8px 18px;
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.48);
}

.sadeem-welcome-card {
    background-color: rgba(20, 20, 26, 0.88);
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    padding: 28px 34px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55);
}

.sadeem-playlist-active {
    background-color: alpha(currentColor, 0.10);
    font-weight: 600;
}

.sadeem-section-heading {
    font-size: 12px;
    font-weight: 700;
    opacity: 0.78;
}

.sadeem-menu-row {
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 34px;
}

.sadeem-menu-subhdr {
    font-weight: 700;
    font-size: 13px;
}

.sadeem-tabular-val {
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    font-weight: 600;
    min-width: 44px;
}

.sadeem-popover-active {
    background-color: alpha(currentColor, 0.10);
    font-weight: 600;
}
"""


def format_isolated_filename(name: str) -> str:
    """Wrap filename in Unicode FSI/PDI directional isolates so RTL never reverses extensions."""
    if not name:
        return ""
    return f"\u2066{name}\u2069"


def format_time(seconds: float) -> str:
    sec = max(0, int(round(seconds))) if seconds and seconds > 0 else 0
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


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
        self._click_timer_id: int = 0
        self._seeking_from_ui: bool = False
        self._updating_ui: bool = False
        self._is_fullscreen: bool = False
        self._is_playing: bool = False
        self._pointer_over_hud: bool = False
        self._active_popovers: int = 0
        self._last_motion_x: float = -1.0
        self._last_motion_y: float = -1.0

        self._ab_point_a: Optional[float] = None
        self._ab_point_b: Optional[float] = None
        self._last_sid: int = 1
        self._sub_delay_val: float = 0.0
        self._sub_scale_val: float = 1.0
        self._current_speed: float = float(self.state_store.get_setting("speed", 1.0))
        self._loop_mode: str = str(self.state_store.get_setting("loop_mode", "off"))
        self._current_aspect: str = "auto"
        self._current_rotation: int = 0
        self._last_saved_save_tick: float = 0.0
        self._pending_load_path: Optional[str] = None
        self._destroyed: bool = False

        # Popover control button registries for active highlighting
        self._speed_buttons: Dict[float, Gtk.Button] = {}
        self._loop_buttons: Dict[str, Gtk.Button] = {}
        self._ab_buttons: Dict[str, Gtk.Button] = {}
        self._aspect_buttons: Dict[str, Gtk.Button] = {}
        self._rotation_buttons: Dict[int, Gtk.Button] = {}
        self._eq_value_labels: Dict[str, Gtk.Label] = {}

        self._init_engine()
        self._build_ui()
        self._setup_controllers()
        self._apply_saved_settings()

        self.connect("close-request", self._on_close_request)
        self.connect("notify::fullscreened", self._on_fullscreen_changed)

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
        self._current_speed = speed

        self._updating_ui = True
        try:
            self.volume_scale.set_value(max(0.0, min(150.0, vol)))
            self._update_mute_icon(muted, vol)
            self.sub_bidi_switch.set_active(sub_bidi)
        finally:
            self._updating_ui = False

        if self.engine.is_initialized:
            self.engine.set_volume(vol)
            self.engine.set_mute(muted)
            self.engine.set_speed(speed)
            self.engine.set_loop_file(self._loop_mode == "file")
            self.engine.set_sub_bidi_compat(sub_bidi)
        self._sync_settings_active_states()

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_sidebar_position(Gtk.PackType.END)
        self.split_view.set_show_sidebar(False)
        self.split_view.set_min_sidebar_width(260)
        self.split_view.set_max_sidebar_width(360)
        self.toast_overlay.set_child(self.split_view)

        # Sidebar: Playlist Panel
        self.playlist_sidebar = self._build_playlist_sidebar()
        self.split_view.set_sidebar(self.playlist_sidebar)

        # Main video viewport overlay
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
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.add_css_class("sadeem-welcome-card")

        icon = Gtk.Image.new_from_icon_name("sadeem-video")
        icon.set_pixel_size(72)
        box.append(icon)

        title = Gtk.Label(label=t("app_title"))
        title.add_css_class("title-1")
        box.append(title)

        sub = Gtk.Label(label=t("open_prompt"))
        sub.add_css_class("dim-label")
        sub.set_wrap(True)
        sub.set_justify(Gtk.Justification.CENTER)
        box.append(sub)

        if self.engine_error:
            err_lbl = Gtk.Label(label=f"{t('err_mpv_missing')}\n({self.engine_error})")
            err_lbl.add_css_class("error")
            err_lbl.set_wrap(True)
            err_lbl.set_justify(Gtk.Justification.CENTER)
            box.append(err_lbl)

        open_btn = Gtk.Button(label=t("open_file"))
        open_btn.add_css_class("suggested-action")
        open_btn.add_css_class("pill")
        open_btn.set_halign(Gtk.Align.CENTER)
        open_btn.connect("clicked", lambda *_: self.prompt_open_file())
        box.append(open_btn)

        hint = Gtk.Label(label=t("drop_hint"))
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        box.append(hint)
        return box

    def _build_top_bar(self) -> Gtk.Widget:
        handle = Gtk.WindowHandle()
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("sadeem-hud-top")
        handle.set_child(bar)

        open_btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
        open_btn.add_css_class("osd")
        open_btn.add_css_class("sadeem-osd-btn")
        open_btn.set_tooltip_text(t("open_file"))
        open_btn.connect("clicked", lambda *_: self.prompt_open_file())
        bar.append(open_btn)

        self.playlist_toggle_btn = Gtk.ToggleButton()
        self.playlist_toggle_btn.set_icon_name("view-list-symbolic")
        self.playlist_toggle_btn.add_css_class("osd")
        self.playlist_toggle_btn.add_css_class("sadeem-osd-btn")
        self.playlist_toggle_btn.set_tooltip_text(f"{t('playlist')} (P)")
        self.playlist_toggle_btn.connect("toggled", self._on_playlist_toggled)
        bar.append(self.playlist_toggle_btn)

        # Filename title (strictly isolated with FSI/PDI)
        self.title_label = Gtk.Label(label=format_isolated_filename(t("app_title")))
        self.title_label.add_css_class("sadeem-video-title")
        self.title_label.set_hexpand(True)
        self.title_label.set_halign(Gtk.Align.CENTER)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.title_label.set_single_line_mode(True)
        bar.append(self.title_label)

        # Launch sadeem-video-editor non-blockingly
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

        # Media Info Button (uses clear info-outline-symbolic matching sadeem-gallery)
        self.info_btn = Gtk.Button.new_from_icon_name("info-outline-symbolic")
        self.info_btn.add_css_class("osd")
        self.info_btn.add_css_class("sadeem-osd-btn")
        self.info_btn.set_tooltip_text(f"{t('media_info')} (I)")
        self.info_btn.connect("clicked", lambda *_: self.show_media_info_dialog())
        bar.append(self.info_btn)

        # Window Controls (minimize / maximize / close)
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
        self.progress_row.append(self.seek_scale)

        self.time_dur_label = Gtk.Label(label="00:00")
        self.time_dur_label.set_direction(Gtk.TextDirection.LTR)
        self.time_dur_label.add_css_class("sadeem-time-label")
        self.progress_row.append(self.time_dur_label)

        capsule.append(self.progress_row)

        # Bottom balanced 3-part Gtk.CenterBox (Volume | LTR Transport | Tools)
        controls = Gtk.CenterBox()

        # Start widget: Volume cluster
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vol_box.set_direction(Gtk.TextDirection.LTR)
        self.mute_btn = Gtk.Button.new_from_icon_name("audio-volume-high-symbolic")
        self.mute_btn.add_css_class("flat")
        self.mute_btn.add_css_class("sadeem-hud-btn")
        self.mute_btn.set_tooltip_text(f"{t('mute')} (M)")
        self.mute_btn.connect("clicked", lambda *_: self.toggle_mute())
        vol_box.append(self.mute_btn)

        self.vol_adj = Gtk.Adjustment(value=100.0, lower=0.0, upper=150.0, step_increment=5.0, page_increment=15.0)
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
        self.tracks_btn.set_icon_name("media-view-subtitles-symbolic")
        self.tracks_btn.add_css_class("flat")
        self.tracks_btn.add_css_class("sadeem-hud-btn")
        self.tracks_btn.set_tooltip_text(t("tracks_btn"))
        self.tracks_popover = self._build_tracks_popover()
        self.tracks_btn.set_popover(self.tracks_popover)
        tools_box.append(self.tracks_btn)

        self.settings_btn = Gtk.MenuButton()
        self.settings_btn.set_icon_name("emblem-system-symbolic")
        self.settings_btn.add_css_class("flat")
        self.settings_btn.add_css_class("sadeem-hud-btn")
        self.settings_btn.set_tooltip_text(t("settings"))
        self.settings_popover = self._build_settings_popover()
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

    def _make_section_label(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class("caption-heading")
        lbl.add_css_class("sadeem-section-heading")
        lbl.set_margin_start(6)
        lbl.set_margin_top(2)
        return lbl

    def _make_stepper_row(
        self,
        title: str,
        initial_text: str,
        on_dec,
        on_inc,
        on_reset,
    ):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_start(6)
        row.set_margin_end(4)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        lbl = Gtk.Label(label=title, xalign=0)
        lbl.set_hexpand(True)
        row.append(lbl)

        ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        ctrl_box.set_direction(Gtk.TextDirection.LTR)

        dec_btn = Gtk.Button(label="−")
        dec_btn.add_css_class("flat")
        dec_btn.connect("clicked", lambda *_: on_dec())
        val_lbl = Gtk.Label(label=initial_text)
        val_lbl.add_css_class("sadeem-tabular-val")
        val_lbl.set_size_request(48, -1)
        val_lbl.set_halign(Gtk.Align.CENTER)
        inc_btn = Gtk.Button(label="+")
        inc_btn.add_css_class("flat")
        inc_btn.connect("clicked", lambda *_: on_inc())
        rst_btn = Gtk.Button(label=t("reset"))
        rst_btn.add_css_class("flat")
        rst_btn.connect("clicked", lambda *_: on_reset())

        ctrl_box.append(dec_btn)
        ctrl_box.append(val_lbl)
        ctrl_box.append(inc_btn)
        ctrl_box.append(rst_btn)
        row.append(ctrl_box)
        return row, val_lbl

    def _build_check_row(
        self,
        label: str,
        selected: bool,
        on_click,
        isolate_bidi: bool = False,
    ):
        b = Gtk.Button()
        b.add_css_class("flat")
        b.add_css_class("sadeem-menu-row")
        if selected:
            b.add_css_class("sadeem-popover-active")
        b.set_halign(Gtk.Align.FILL)

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(
            label=format_isolated_filename(label) if isolate_bidi else label,
            xalign=0,
        )
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.FILL)
        lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        row_box.append(lbl)

        # Fixed-width check slot prevents RTL layout jumps next to English filenames
        chk_slot = Gtk.Box()
        chk_slot.set_size_request(18, 18)
        chk_slot.set_halign(Gtk.Align.END)
        chk_slot.set_valign(Gtk.Align.CENTER)
        chk = Gtk.Image.new_from_icon_name("object-select-symbolic")
        chk.set_opacity(1.0 if selected else 0.0)
        chk_slot.append(chk)
        row_box.append(chk_slot)

        b.set_child(row_box)
        b.connect("clicked", lambda *_: on_click())
        return b, chk

    def _build_nav_row(self, icon_name: str, title: str, target_page: str):
        b = Gtk.Button()
        b.add_css_class("flat")
        b.add_css_class("sadeem-menu-row")
        b.set_halign(Gtk.Align.FILL)

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row_box.append(Gtk.Image.new_from_icon_name(icon_name))

        title_lbl = Gtk.Label(label=title, xalign=0)
        title_lbl.set_hexpand(True)
        title_lbl.set_halign(Gtk.Align.FILL)
        row_box.append(title_lbl)

        val_lbl = Gtk.Label(label="")
        val_lbl.add_css_class("dim-label")
        val_lbl.add_css_class("caption")
        row_box.append(val_lbl)

        row_box.append(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        b.set_child(row_box)
        b.connect("clicked", lambda *_: self.settings_stack.set_visible_child_name(target_page))
        return b, val_lbl

    def _make_subpage_header(self, title: str) -> Gtk.Box:
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        back_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", lambda *_: self.settings_stack.set_visible_child_name("main"))
        hdr.append(back_btn)

        lbl = Gtk.Label(label=title, xalign=0)
        lbl.add_css_class("sadeem-menu-subhdr")
        lbl.set_hexpand(True)
        hdr.append(lbl)

        wrap.append(hdr)
        wrap.append(Gtk.Separator())
        return wrap

    def _build_tracks_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        self._register_popover_tracking(pop)
        pop.connect("show", lambda *_: self._refresh_tracks_popover())

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(430)
        scroll.set_propagate_natural_height(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_size_request(310, -1)
        scroll.set_child(box)
        pop.set_child(scroll)

        # Audio Tracks
        box.append(self._make_section_label(t("audio_track")))
        self.audio_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(self.audio_list_box)

        box.append(Gtk.Separator())

        # Subtitle Tracks
        box.append(self._make_section_label(t("subtitle_track")))
        self.sub_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(self.sub_list_box)

        # Load External Subtitle row
        add_sub_btn = Gtk.Button()
        add_sub_btn.add_css_class("flat")
        add_sub_btn.add_css_class("sadeem-menu-row")
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        add_box.append(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
        add_lbl = Gtk.Label(label=t("load_subtitle"), xalign=0)
        add_lbl.set_hexpand(True)
        add_box.append(add_lbl)
        add_sub_btn.set_child(add_box)
        add_sub_btn.connect("clicked", self._on_load_sub_clicked)
        box.append(add_sub_btn)

        box.append(Gtk.Separator())

        # Subtitle Delay & Font Scale (clean flat steppers)
        delay_row, self.sub_delay_lbl = self._make_stepper_row(
            t("sub_delay"),
            "0.0s",
            lambda: self._adjust_sub_delay(-0.2),
            lambda: self._adjust_sub_delay(0.2),
            lambda: self._set_sub_delay(0.0),
        )
        box.append(delay_row)

        scale_row, self.sub_scale_lbl = self._make_stepper_row(
            t("sub_scale"),
            "1.0x",
            lambda: self._adjust_sub_scale(-0.1),
            lambda: self._adjust_sub_scale(0.1),
            lambda: self._set_sub_scale(1.0),
        )
        box.append(scale_row)

        bidi_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bidi_row.set_margin_start(6)
        bidi_row.set_margin_end(6)
        bidi_row.set_margin_top(4)
        bidi_row.set_margin_bottom(2)
        bidi_lbl = Gtk.Label(label=t("sub_bidi_compat"), xalign=0)
        bidi_lbl.set_hexpand(True)
        bidi_lbl.set_wrap(True)
        self.sub_bidi_switch = Gtk.Switch()
        self.sub_bidi_switch.set_valign(Gtk.Align.CENTER)
        self.sub_bidi_switch.connect("notify::active", self._on_sub_bidi_compat_toggled)
        bidi_row.append(bidi_lbl)
        bidi_row.append(self.sub_bidi_switch)
        box.append(bidi_row)

        return pop

    def _build_settings_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        self._register_popover_tracking(pop)
        pop.connect("show", lambda *_: (self._sync_settings_active_states(), self._refresh_chapters_section()))
        pop.connect("closed", lambda *_: self.settings_stack.set_visible_child_name("main"))

        self.settings_stack = Gtk.Stack()
        self.settings_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.settings_stack.set_transition_duration(180)
        self.settings_stack.set_vhomogeneous(False)
        self.settings_stack.set_size_request(280, -1)
        pop.set_child(self.settings_stack)

        # ---- Main Page ----
        main_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("top", "bottom", "start", "end"):
            getattr(main_page, f"set_margin_{margin}")(8)

        spd_nav, self.nav_speed_val = self._build_nav_row("media-seek-forward-symbolic", t("speed"), "speed")
        rep_nav, self.nav_repeat_val = self._build_nav_row("media-playlist-repeat-symbolic", t("loop_mode"), "repeat")
        vid_nav, self.nav_video_val = self._build_nav_row("video-display-symbolic", t("aspect_ratio"), "video")
        eq_nav, _eq_val = self._build_nav_row("applications-graphics-symbolic", t("eq_title"), "eq")
        self.chapters_nav_btn, self.nav_chapters_val = self._build_nav_row("view-list-symbolic", t("chapters"), "chapters")
        self.chapters_nav_btn.set_visible(False)

        main_page.append(spd_nav)
        main_page.append(rep_nav)
        main_page.append(vid_nav)
        main_page.append(eq_nav)
        main_page.append(self.chapters_nav_btn)

        sep = Gtk.Separator()
        sep.set_margin_top(2)
        sep.set_margin_bottom(2)
        main_page.append(sep)

        ss_btn = Gtk.Button()
        ss_btn.add_css_class("flat")
        ss_btn.add_css_class("sadeem-menu-row")
        ss_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ss_box.append(Gtk.Image.new_from_icon_name("camera-photo-symbolic"))
        ss_lbl = Gtk.Label(label=t("screenshot"), xalign=0)
        ss_lbl.set_hexpand(True)
        ss_box.append(ss_lbl)
        ss_btn.set_child(ss_box)
        ss_btn.connect("clicked", lambda *_: (self.settings_popover.popdown(), self.take_screenshot()))
        main_page.append(ss_btn)

        self.settings_stack.add_named(main_page, "main")

        # ---- Speed Subpage ----
        spd_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("top", "bottom", "start", "end"):
            getattr(spd_page, f"set_margin_{margin}")(8)
        spd_page.append(self._make_subpage_header(t("speed")))
        for s in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
            b, chk = self._build_check_row(f"{s:g}x", False, lambda val=s: self.set_speed(val))
            self._speed_buttons[float(s)] = (b, chk)
            spd_page.append(b)
        self.settings_stack.add_named(spd_page, "speed")

        # ---- Repeat & A-B Subpage ----
        rep_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("top", "bottom", "start", "end"):
            getattr(rep_page, f"set_margin_{margin}")(8)
        rep_page.append(self._make_subpage_header(t("loop_mode")))
        for mode_id, lbl_key in (("off", "loop_off"), ("file", "loop_file"), ("playlist", "loop_playlist")):
            b, chk = self._build_check_row(t(lbl_key), False, lambda m=mode_id: self.set_loop_mode(m))
            self._loop_buttons[mode_id] = (b, chk)
            rep_page.append(b)

        rep_sep = Gtk.Separator()
        rep_sep.set_margin_top(4)
        rep_sep.set_margin_bottom(4)
        rep_page.append(rep_sep)
        rep_page.append(self._make_section_label(t("ab_loop")))
        for action, lbl_key in (("a", "ab_set_a"), ("b", "ab_set_b"), ("clear", "ab_clear")):
            b, chk = self._build_check_row(t(lbl_key), False, lambda act=action: self._on_ab_action(act))
            self._ab_buttons[action] = (b, chk)
            rep_page.append(b)
        self.settings_stack.add_named(rep_page, "repeat")

        # ---- Aspect Ratio & Rotation Subpage ----
        vid_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("top", "bottom", "start", "end"):
            getattr(vid_page, f"set_margin_{margin}")(8)
        vid_page.append(self._make_subpage_header(t("aspect_ratio")))
        for mode, label in (
            ("auto", t("aspect_auto")),
            ("16:9", "16:9"),
            ("4:3", "4:3"),
            ("21:9", "21:9"),
            ("fill", t("aspect_fill")),
        ):
            b, chk = self._build_check_row(label, False, lambda m=mode: self._set_aspect(m))
            self._aspect_buttons[mode] = (b, chk)
            vid_page.append(b)

        vid_sep = Gtk.Separator()
        vid_sep.set_margin_top(4)
        vid_sep.set_margin_bottom(4)
        vid_page.append(vid_sep)
        vid_page.append(self._make_section_label(t("rotation")))
        for deg in (0, 90, 180, 270):
            b, chk = self._build_check_row(f"{deg}°", False, lambda d=deg: self._set_rotation(d))
            self._rotation_buttons[deg] = (b, chk)
            vid_page.append(b)
        self.settings_stack.add_named(vid_page, "video")

        # ---- Equalizer Subpage ----
        eq_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for margin in ("top", "bottom", "start", "end"):
            getattr(eq_page, f"set_margin_{margin}")(8)
        eq_page.append(self._make_subpage_header(t("eq_title")))

        self.eq_scales: Dict[str, Gtk.Scale] = {}
        for prop_key, label_key in (
            ("brightness", "eq_brightness"),
            ("contrast", "eq_contrast"),
            ("saturation", "eq_saturation"),
            ("gamma", "eq_gamma"),
        ):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(4)
            row.set_margin_end(4)
            lbl = Gtk.Label(label=t(label_key), xalign=0)
            lbl.set_size_request(72, -1)
            adj = Gtk.Adjustment(value=0.0, lower=-100.0, upper=100.0, step_increment=2.0, page_increment=10.0)
            sc = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            sc.set_direction(Gtk.TextDirection.LTR)
            sc.set_draw_value(False)
            sc.set_hexpand(True)
            val_lbl = Gtk.Label(label="0")
            val_lbl.add_css_class("sadeem-tabular-val")
            val_lbl.set_size_request(32, -1)
            sc.connect("value-changed", self._on_eq_changed, prop_key)
            self.eq_scales[prop_key] = sc
            self._eq_value_labels[prop_key] = val_lbl
            row.append(lbl)
            row.append(sc)
            row.append(val_lbl)
            eq_page.append(row)

        eq_reset_btn = Gtk.Button(label=t("eq_reset"))
        eq_reset_btn.add_css_class("flat")
        eq_reset_btn.add_css_class("sadeem-menu-row")
        eq_reset_btn.set_halign(Gtk.Align.END)
        eq_reset_btn.connect("clicked", lambda *_: self._reset_equalizer())
        eq_page.append(eq_reset_btn)
        self.settings_stack.add_named(eq_page, "eq")

        # ---- Chapters Subpage ----
        ch_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("top", "bottom", "start", "end"):
            getattr(ch_page, f"set_margin_{margin}")(8)
        ch_page.append(self._make_subpage_header(t("chapters")))
        ch_scroll = Gtk.ScrolledWindow()
        ch_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        ch_scroll.set_max_content_height(300)
        ch_scroll.set_propagate_natural_height(True)
        self.chapters_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        ch_scroll.set_child(self.chapters_section)
        ch_page.append(ch_scroll)
        self.settings_stack.add_named(ch_page, "chapters")

        return pop

    def _set_check_row_state(self, btn: Gtk.Button, chk: Gtk.Image, active: bool) -> None:
        if active:
            btn.add_css_class("sadeem-popover-active")
            chk.set_opacity(1.0)
        else:
            btn.remove_css_class("sadeem-popover-active")
            chk.set_opacity(0.0)

    def _sync_settings_active_states(self) -> None:
        self.nav_speed_val.set_text(f"{self._current_speed:g}x")
        loop_key = "loop_file" if self._loop_mode == "file" else ("loop_playlist" if self._loop_mode == "playlist" else "loop_off")
        self.nav_repeat_val.set_text(t(loop_key))
        asp_lbl = t("aspect_auto") if self._current_aspect == "auto" else (t("aspect_fill") if self._current_aspect == "fill" else self._current_aspect)
        if self._current_rotation:
            self.nav_video_val.set_text(f"{asp_lbl} · {self._current_rotation}°")
        else:
            self.nav_video_val.set_text(asp_lbl)

        for spd, (btn, chk) in self._speed_buttons.items():
            self._set_check_row_state(btn, chk, abs(spd - self._current_speed) < 0.01)

        for mode_id, (btn, chk) in self._loop_buttons.items():
            self._set_check_row_state(btn, chk, mode_id == self._loop_mode)

        if "a" in self._ab_buttons:
            self._set_check_row_state(*self._ab_buttons["a"], self._ab_point_a is not None)
        if "b" in self._ab_buttons:
            self._set_check_row_state(*self._ab_buttons["b"], self._ab_point_b is not None)
        if "clear" in self._ab_buttons:
            self._set_check_row_state(*self._ab_buttons["clear"], False)

        for mode, (btn, chk) in self._aspect_buttons.items():
            self._set_check_row_state(btn, chk, mode == self._current_aspect)

        for deg, (btn, chk) in self._rotation_buttons.items():
            self._set_check_row_state(btn, chk, deg == self._current_rotation)

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
        # Keyboard shortcuts on window
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        # Pointer motion over video stage reveals HUD ONLY on real movement (> 2px)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_stage_pointer_motion)
        self.video_overlay.add_controller(motion)

        # Click / Double-click on GLArea: single=play/pause, double=fullscreen
        click = Gtk.GestureClick()
        click.set_button(Gdk.BUTTON_PRIMARY)
        click.connect("released", self._on_video_clicked)
        self.gl_area.add_controller(click)

        # Mouse wheel controls volume over video area
        scroll_ctrl = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_ctrl.connect("scroll", self._on_video_scroll)
        self.gl_area.add_controller(scroll_ctrl)

        # Drag and drop files (Gdk.FileList) onto window
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
    def _on_gl_realize(self, area: Gtk.GLArea) -> None:
        if not self.engine.is_initialized or self._destroyed:
            return
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

        def _idle_redraw():
            if not self._destroyed and self.gl_area.get_realized():
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
    # Polling, Events & State Persistence
    # -----------------------------------------------------------------------
    def _on_poll_tick(self) -> bool:
        if self._destroyed:
            return False
        if self.engine.is_initialized:
            self.engine.drain_events(self._handle_mpv_event)
            self._sync_playback_ui()
        return True

    def _handle_mpv_event(self, ev: dict) -> None:
        ev_id = ev.get("event_id")
        if ev_id == mpv_engine.MPV_EVENT_FILE_LOADED:
            self._refresh_playlist_ui()
            if self.engine.is_initialized:
                dur = self.engine.get_duration()
                self.time_dur_label.set_text(format_time(dur))
                self.seek_adj.set_upper(max(1.0, dur))
                paused = self.engine.is_paused()
                self._sync_play_pause_state(paused, trigger_hud=True)
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
            # Only act on HUD timer when play/pause state actually transitions
            self._sync_play_pause_state(paused, trigger_hud=False)
        finally:
            self._updating_ui = False

        now = time.monotonic()
        if now - self._last_saved_save_tick >= 3.0 and dur > 0.0:
            self._last_saved_save_tick = now
            self.state_store.set_position(cur, pos, dur)

    def _sync_play_pause_state(self, paused: bool, trigger_hud: bool = False) -> None:
        new_playing = bool(self.playlist_mgr.current_path) and not paused
        state_changed = (new_playing != self._is_playing)
        self._is_playing = new_playing
        self.play_btn.set_icon_name(
            "media-playback-pause-symbolic" if self._is_playing else "media-playback-start-symbolic"
        )
        if state_changed or trigger_hud:
            if not self._is_playing:
                self._reveal_hud(auto_hide=False)
            else:
                self._schedule_hud_hide()

    # -----------------------------------------------------------------------
    # Opening Files & Playlist Control
    # -----------------------------------------------------------------------
    def open_paths(self, paths: List[str]) -> None:
        video_paths = []
        sub_paths = []
        for p in paths:
            if not p:
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

        for sp in sub_paths:
            if self.engine.is_initialized:
                self.engine.add_subtitle(sp)
                self._show_osd(t("sub_added"))

    def play_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            self._show_osd(t("err_open_file"))
            return
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

        base = os.path.basename(path)
        iso = format_isolated_filename(base)
        self.title_label.set_text(iso)
        self.set_title(f"{iso} — {t('app_title')}")
        self._refresh_playlist_ui()

        if self.gl_area.get_realized() or not self.engine.is_initialized:
            self._start_playback(path)
        else:
            self._pending_load_path = path

    def _start_playback(self, path: str) -> None:
        if not self.engine.is_initialized:
            self._show_osd(t("err_mpv_missing"))
            return
        resume = self.state_store.get_resume_position(path)
        self.engine.load_file(path, start_seconds=resume)
        self._sync_play_pause_state(False, trigger_hud=True)
        self._reveal_hud(auto_hide=True)

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
            lbl = Gtk.Label(label=format_isolated_filename(os.path.basename(item_path)), xalign=0)
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
    # Playback Actions
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

    def adjust_volume(self, delta: float) -> None:
        if not self.engine.is_initialized:
            return
        cur = self.engine.get_volume()
        new_vol = max(0.0, min(150.0, round(cur + delta)))
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
        self._show_osd(t("osd_volume", v=int(round(new_vol))))

    def toggle_mute(self) -> None:
        if not self.engine.is_initialized:
            return
        muted = not self.engine.get_mute()
        self.engine.set_mute(muted)
        vol = self.engine.get_volume()
        self.state_store.set_setting("muted", muted)
        self._update_mute_icon(muted, vol)
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

    def set_speed(self, speed: float) -> None:
        clamped = max(0.25, min(4.0, round(speed, 2)))
        self._current_speed = clamped
        if self.engine.is_initialized:
            self.engine.set_speed(clamped)
        self.state_store.set_setting("speed", clamped)
        self._sync_settings_active_states()
        self._show_osd(t("osd_speed", v=clamped))

    def step_speed(self, delta: float) -> None:
        cur = self.engine.get_speed() if self.engine.is_initialized else self._current_speed
        self.set_speed(cur + delta)

    def set_loop_mode(self, mode: str) -> None:
        self._loop_mode = mode
        self.state_store.set_setting("loop_mode", mode)
        if self.engine.is_initialized:
            self.engine.set_loop_file(mode == "file")
        self._refresh_playlist_ui()
        self._sync_settings_active_states()
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
        self._sync_settings_active_states()

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

    def toggle_fullscreen(self) -> None:
        if self._is_fullscreen:
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
        elif self._is_fullscreen:
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
        """Manually show or hide top/bottom HUD overlays (shortcut H)."""
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
    # UI Signal Callbacks & Popover Content Builders
    # -----------------------------------------------------------------------
    def _on_seek_change_value(self, _scale, _scroll_type, value: float) -> bool:
        if self._updating_ui or not self.engine.is_initialized:
            return False
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

    def _set_aspect(self, mode: str) -> None:
        self._current_aspect = mode
        if self.engine.is_initialized:
            self.engine.set_aspect_ratio(mode)
        self._sync_settings_active_states()
        label = t("aspect_auto") if mode == "auto" else (t("aspect_fill") if mode == "fill" else mode)
        self._show_osd(f"{t('aspect_ratio')}: {label}")

    def _set_rotation(self, degrees: int) -> None:
        self._current_rotation = degrees
        if self.engine.is_initialized:
            self.engine.set_rotation(degrees)
        self._sync_settings_active_states()
        self._show_osd(f"{t('rotation')}: {degrees}°")

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

    def _refresh_tracks_popover(self) -> None:
        for container in (self.audio_list_box, self.sub_list_box):
            while True:
                child = container.get_first_child()
                if child is None:
                    break
                container.remove(child)

        tracks = self.engine.get_tracks() if self.engine.is_initialized else {"audio": [], "sub": []}
        audio_tracks = tracks["audio"]
        sub_tracks = tracks["sub"]

        if not audio_tracks:
            lbl = Gtk.Label(label=t("info_none"), xalign=0)
            lbl.add_css_class("dim-label")
            lbl.set_margin_start(8)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            self.audio_list_box.append(lbl)
        else:
            for tr in audio_tracks:
                title = tr.get("title") or tr.get("lang") or t("track_untitled", id=tr["id"])
                if tr.get("lang") and tr.get("title"):
                    title = f"{tr['title']} ({tr['lang']})"
                b, _chk = self._build_check_row(
                    title,
                    bool(tr.get("selected")),
                    lambda tid=tr["id"]: (self.engine.set_audio_track(tid), self.tracks_popover.popdown()),
                    isolate_bidi=True,
                )
                self.audio_list_box.append(b)

        any_sub_sel = any(s.get("selected") for s in sub_tracks)
        off_btn, _chk = self._build_check_row(
            t("sub_off"),
            not any_sub_sel,
            lambda: (self.engine.set_subtitle_track(None), self.tracks_popover.popdown()),
        )
        self.sub_list_box.append(off_btn)

        for tr in sub_tracks:
            title = tr.get("title") or tr.get("lang") or t("track_untitled", id=tr["id"])
            if tr.get("lang") and tr.get("title"):
                title = f"{tr['title']} ({tr['lang']})"
            b, _chk = self._build_check_row(
                title,
                bool(tr.get("selected")),
                lambda tid=tr["id"]: (self.engine.set_subtitle_track(tid), self.tracks_popover.popdown()),
                isolate_bidi=True,
            )
            self.sub_list_box.append(b)

    def _refresh_chapters_section(self) -> None:
        while True:
            child = self.chapters_section.get_first_child()
            if child is None:
                break
            self.chapters_section.remove(child)

        if not self.engine.is_initialized:
            self.chapters_nav_btn.set_visible(False)
            return
        chapters = self.engine.get_chapters()
        if not chapters:
            self.chapters_nav_btn.set_visible(False)
            return
        self.chapters_nav_btn.set_visible(True)
        self.nav_chapters_val.set_text(str(len(chapters)))
        for ch in chapters[:25]:
            title = ch["title"] or f"{t('chapters')} {ch['index'] + 1}"
            b, _chk = self._build_check_row(
                f"{format_time(ch['time'])}  {title}",
                False,
                lambda ts=ch["time"]: (self.engine.seek_absolute(ts), self.settings_popover.popdown()),
                isolate_bidi=True,
            )
            self.chapters_section.append(b)

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

    # -----------------------------------------------------------------------
    # File Dialogs & Media Info Dialog
    # -----------------------------------------------------------------------
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

    def show_media_info_dialog(self) -> None:
        info = self.engine.get_media_info() if self.engine.is_initialized else {
            "width": 0, "height": 0, "fps": 0.0, "video_codec": "", "hwdec_current": "no",
            "duration": 0.0, "audio_tracks": [], "sub_tracks": [], "chapters": [],
        }

        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title=t("media_info"), subtitle=""))
        tv.add_top_bar(hb)

        pref_page = Adw.PreferencesPage()
        grp = Adw.PreferencesGroup()
        pref_page.add(grp)

        res_str = f"{info['width']} × {info['height']}" if info["width"] and info["height"] else t("info_none")
        fps_str = f"{info['fps']:.2f} fps" if info["fps"] else t("info_none")
        aud_str = ", ".join(
            (a.get("title") or a.get("lang") or a.get("codec") or str(a.get("id")))
            for a in info.get("audio_tracks", [])
        ) or t("info_none")
        sub_str = ", ".join(
            (s.get("title") or s.get("lang") or str(s.get("id")))
            for s in info.get("sub_tracks", [])
        ) or t("info_none")

        rows = [
            (t("info_resolution"), res_str),
            (t("info_codec"), info.get("video_codec") or t("info_none")),
            (t("info_fps"), fps_str),
            (t("info_hwdec"), info.get("hwdec_current") or "no"),
            (t("info_duration"), format_time(info.get("duration", 0.0))),
            (t("info_audio_tracks"), aud_str),
            (t("info_sub_tracks"), sub_str),
        ]
        for label, val in rows:
            row = Adw.ActionRow(title=label, subtitle=str(val))
            row.set_subtitle_selectable(True)
            grp.add(row)

        tv.set_content(pref_page)

        if hasattr(Adw, "Dialog"):
            dlg = Adw.Dialog()
            dlg.set_title(t("media_info"))
            dlg.set_content_width(420)
            dlg.set_content_height(460)
            dlg.set_child(tv)
            dlg.present(self)
        else:
            dlg = Adw.Window(transient_for=self, modal=True, title=t("media_info"))
            dlg.set_default_size(420, 460)
            dlg.set_content(tv)
            dlg.present()

    # -----------------------------------------------------------------------
    # Keyboard Shortcut Router
    # -----------------------------------------------------------------------
    def _on_key_pressed(self, _ctrl, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)

        focus = self.get_focus()
        if isinstance(focus, Gtk.Text) or isinstance(focus, Gtk.Editable):
            if keyval != Gdk.KEY_Escape:
                return False

        if keyval in (Gdk.KEY_space, Gdk.KEY_k, Gdk.KEY_K):
            self.toggle_play_pause()
            return True
        if keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self.toggle_hud()
            return True
        if keyval == Gdk.KEY_Right:
            delta = 1.0 if shift else (30.0 if ctrl else 5.0)
            self.seek_relative(delta)
            return True
        if keyval == Gdk.KEY_Left:
            delta = -1.0 if shift else (-30.0 if ctrl else -5.0)
            self.seek_relative(delta)
            return True
        if keyval == Gdk.KEY_Up:
            self.adjust_volume(5.0)
            return True
        if keyval == Gdk.KEY_Down:
            self.adjust_volume(-5.0)
            return True
        if keyval in (Gdk.KEY_m, Gdk.KEY_M):
            self.toggle_mute()
            return True
        if keyval in (Gdk.KEY_f, Gdk.KEY_F, Gdk.KEY_F11):
            self.toggle_fullscreen()
            return True
        if keyval == Gdk.KEY_Escape:
            if self._is_fullscreen:
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
            self.set_speed(1.0)
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

        for attr in ("_poll_id", "_hide_hud_id", "_osd_hide_id", "_click_timer_id"):
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
        for f in files[:n_files]:
            p = f.get_path()
            if p:
                paths.append(p)
        win = self.get_active_window()
        if win is None:
            win = SadeemVideoWindow(app=self, initial_files=paths)
        else:
            win.open_paths(paths)
        win.present()


def main(argv: Optional[List[str]] = None) -> int:
    app = SadeemVideoApp()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
