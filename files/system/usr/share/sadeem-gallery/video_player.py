#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video playback widget for Sadeem Gallery using GTK 4 Gtk.Video and Gtk.MediaFile
with custom Libadwaita playback controls, seeking, volume, and shortcut handling.
"""

import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

import i18n
import video_utils

t = i18n.t


def safe_icon(names, fallback="media-playback-start-symbolic"):
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        for name in names:
            if theme.has_icon(name):
                return name
    return fallback


class VideoPlayerWidget(Gtk.Overlay):
    """
    Overlay-based video player widget with video viewport and sleek
    floating bottom control bar.
    """

    def __init__(self, on_edit_requested=None, on_fullscreen_toggle=None):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.add_css_class("video-player-overlay")

        self.on_edit_requested = on_edit_requested
        self.on_fullscreen_toggle = on_fullscreen_toggle

        self.current_path = None
        self.media_file = None
        self.media_stream = None
        self.duration_sec = 0.0
        self.is_seeking = False
        self._syncing_slider = False
        self._update_timer_id = None
        self._sig_ids = []

        self._build_ui()
        self._setup_events()

    def _build_ui(self):
        # 1. Video display widget (Gtk.Picture + Gtk.MediaFile)
        self.picture = Gtk.Picture()
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_can_shrink(True)
        self.picture.set_hexpand(True)
        self.picture.set_vexpand(True)
        self.set_child(self.picture)

        # 2. Bottom Floating Control Bar with Adw.Clamp
        self.ctrl_clamp = Adw.Clamp()
        self.ctrl_clamp.set_maximum_size(680)
        self.ctrl_clamp.set_tightening_threshold(500)
        self.ctrl_clamp.set_halign(Gtk.Align.FILL)
        self.ctrl_clamp.set_valign(Gtk.Align.END)
        self.ctrl_clamp.set_margin_bottom(18)
        self.ctrl_clamp.set_margin_start(24)
        self.ctrl_clamp.set_margin_end(24)

        self.ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.ctrl_box.add_css_class("video-ctrl-bar")
        self.ctrl_clamp.set_child(self.ctrl_box)

        # Play / Pause button
        self.btn_play = Gtk.Button()
        self.btn_play.add_css_class("video-btn-play")
        self.btn_play.set_icon_name(safe_icon(["media-playback-start-symbolic"]))
        self.btn_play.set_tooltip_text(t("video_play"))
        self.btn_play.connect("clicked", lambda _b: self.toggle_play())
        self.ctrl_box.append(self.btn_play)

        # Current time label
        self.lbl_cur_time = Gtk.Label(label="00:00")
        self.lbl_cur_time.add_css_class("video-time-lbl")
        self.ctrl_box.append(self.lbl_cur_time)

        # Seekbar (Gtk.Scale) - Always LTR text direction so time advances L -> R
        self.seek_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=100.0, step_increment=1.0, page_increment=5.0)
        self.seek_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.seek_adj)
        self.seek_scale.set_direction(Gtk.TextDirection.LTR)
        self.seek_scale.set_hexpand(True)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.add_css_class("video-seek-scale")

        self.seek_scale.connect("change-value", self._on_seek_change_value)
        self.ctrl_box.append(self.seek_scale)

        # Duration label
        self.lbl_duration = Gtk.Label(label="00:00")
        self.lbl_duration.add_css_class("video-time-lbl")
        self.ctrl_box.append(self.lbl_duration)

        # Volume / Mute button
        self.btn_mute = Gtk.Button()
        self.btn_mute.add_css_class("sadeem-header-btn")
        self.btn_mute.set_icon_name(safe_icon(["audio-volume-high-symbolic"]))
        self.btn_mute.set_tooltip_text(t("video_mute_toggle"))
        self.btn_mute.connect("clicked", lambda _b: self.toggle_mute())
        self.ctrl_box.append(self.btn_mute)

        # Loop button
        self.btn_loop = Gtk.ToggleButton()
        self.btn_loop.add_css_class("sadeem-header-btn")
        self.btn_loop.set_icon_name(safe_icon(["media-playlist-repeat-symbolic"]))
        self.btn_loop.set_tooltip_text(t("video_loop"))
        self.btn_loop.connect("toggled", self._on_loop_toggled)
        self.ctrl_box.append(self.btn_loop)

        # Fullscreen button (if callback provided)
        if self.on_fullscreen_toggle:
            self.btn_fs = Gtk.Button()
            self.btn_fs.add_css_class("sadeem-header-btn")
            self.btn_fs.set_icon_name(safe_icon(["view-fullscreen-symbolic"]))
            self.btn_fs.set_tooltip_text(t("video_fullscreen"))
            self.btn_fs.connect("clicked", lambda _b: self.on_fullscreen_toggle())
            self.ctrl_box.append(self.btn_fs)

        # Edit button (if callback provided)
        if self.on_edit_requested:
            self.btn_edit = Gtk.Button()
            self.btn_edit.add_css_class("sadeem-btn-compact")
            eb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            eb_box.append(Gtk.Image.new_from_icon_name(safe_icon(["document-edit-symbolic"])))
            eb_box.append(Gtk.Label(label=t("video_edit_btn")))
            self.btn_edit.set_child(eb_box)
            self.btn_edit.set_tooltip_text(t("video_edit_tooltip"))
            self.btn_edit.connect("clicked", lambda _b: self.on_edit_requested(self.current_path))
            self.ctrl_box.append(self.btn_edit)

        self.add_overlay(self.ctrl_clamp)

    def _setup_events(self):
        # Click on video viewport picture to toggle play/pause
        click = Gtk.GestureClick()
        click.connect("released", self._on_viewport_clicked)
        self.picture.add_controller(click)

    def _on_viewport_clicked(self, gesture, n_press, x, y):
        if n_press == 1:
            self.toggle_play()
        elif n_press == 2 and self.on_fullscreen_toggle:
            self.on_fullscreen_toggle()

    def load_video(self, video_path):
        """Load and prepare video file for playback via Gtk.MediaFile."""
        self.stop()
        self.current_path = video_path

        if not os.path.isfile(video_path):
            return False

        # Fast metadata probe to initialize duration
        meta = video_utils.get_video_metadata(video_path)
        self.duration_sec = meta.get("duration", 0.0)
        self.lbl_duration.set_text(meta.get("duration_str", "00:00"))
        self.lbl_cur_time.set_text("00:00")

        self.seek_adj.set_upper(max(1.0, self.duration_sec))
        self.seek_adj.set_value(0.0)

        # Load into Gtk.MediaFile
        try:
            self.media_file = Gtk.MediaFile.new_for_filename(video_path)
            self.picture.set_paintable(self.media_file)
            self.media_stream = self.media_file

            sig1 = self.media_file.connect("notify::playing", self._on_notify_playing)
            sig2 = self.media_file.connect("notify::ended", self._on_notify_ended)
            sig3 = self.media_file.connect("notify::duration", self._on_notify_duration)
            sig4 = self.media_file.connect("notify::prepared", self._on_notify_prepared)
            sig5 = self.media_file.connect("notify::error", self._on_notify_error)
            self._sig_ids = [sig1, sig2, sig3, sig4, sig5]

            # Apply loop preference
            self.media_file.set_loop(self.btn_loop.get_active())

            if hasattr(self.media_file, "is_prepared") and self.media_file.is_prepared():
                self._on_notify_prepared(self.media_file, None)
        except Exception as e:
            print(f"[VideoPlayer] Failed to load media file: {e}")
            return False

        self._update_play_icon(False)
        self._start_periodic_timer()
        return True

    def _start_periodic_timer(self):
        self._stop_periodic_timer()
        self._update_timer_id = GLib.timeout_add(100, self._on_poll_timestamp)

    def _stop_periodic_timer(self):
        if self._update_timer_id is not None:
            GLib.source_remove(self._update_timer_id)
            self._update_timer_id = None

    def _on_poll_timestamp(self):
        if not self.media_stream or self.is_seeking:
            return True

        ts_us = self.media_stream.get_timestamp()
        cur_sec = max(0.0, ts_us / 1_000_000.0)
        self.lbl_cur_time.set_text(video_utils.format_duration(cur_sec))

        if not self._syncing_slider and not self.is_seeking:
            self._syncing_slider = True
            self.seek_adj.set_value(cur_sec)
            self._syncing_slider = False

        return True

    def _on_notify_prepared(self, mf, _pspec):
        is_prep = mf.is_prepared() if hasattr(mf, "is_prepared") else mf.props.prepared
        if not is_prep:
            return
        dur_us = mf.get_duration()
        if dur_us > 0:
            self.duration_sec = dur_us / 1_000_000.0
            self.seek_adj.set_upper(self.duration_sec)
            self.lbl_duration.set_text(video_utils.format_duration(self.duration_sec))
        # Fetch first frame immediately to prevent black screen
        try:
            mf.seek(0)
        except Exception:
            pass

    def _on_notify_error(self, mf, _pspec):
        err = mf.get_error()
        if err:
            print(f"[VideoPlayer] Playback error: {err}")

    def _on_notify_playing(self, stream, _pspec):
        is_playing = stream.get_playing()
        self._update_play_icon(is_playing)

    def _on_notify_ended(self, stream, _pspec):
        if stream.get_ended():
            self._update_play_icon(False)
            if self.media_file and self.media_file.get_loop():
                self.seek_to_sec(0.0)
                self.play()

    def _on_notify_duration(self, stream, _pspec):
        dur_us = stream.get_duration()
        if dur_us > 0:
            dur_sec = dur_us / 1_000_000.0
            if dur_sec > self.duration_sec:
                self.duration_sec = dur_sec
                self.seek_adj.set_upper(dur_sec)
                self.lbl_duration.set_text(video_utils.format_duration(dur_sec))

    def _update_play_icon(self, is_playing):
        icon = "media-playback-pause-symbolic" if is_playing else "media-playback-start-symbolic"
        self.btn_play.set_icon_name(safe_icon([icon]))
        self.btn_play.set_tooltip_text(t("video_pause") if is_playing else t("video_play"))

    def toggle_play(self):
        if not self.media_stream:
            return
        if self.media_stream.get_ended():
            self.seek_to_sec(0.0)
            self.play()
            return
        if self.media_stream.get_playing():
            self.pause()
        else:
            self.play()

    def play(self):
        if self.media_stream:
            self.media_stream.play()
            self._update_play_icon(True)

    def pause(self):
        if self.media_stream:
            self.media_stream.pause()
            self._update_play_icon(False)

    def toggle_mute(self):
        if not self.media_stream:
            return
        muted = not self.media_stream.get_muted()
        self.media_stream.set_muted(muted)
        icon = "audio-volume-muted-symbolic" if muted else "audio-volume-high-symbolic"
        self.btn_mute.set_icon_name(safe_icon([icon]))

    def _on_loop_toggled(self, btn):
        looping = btn.get_active()
        if self.media_file:
            self.media_file.set_loop(looping)

    def _on_seek_change_value(self, scale, scroll_type, value):
        self.is_seeking = True
        clamped = max(0.0, min(self.duration_sec, value))
        self.lbl_cur_time.set_text(video_utils.format_duration(clamped))
        self.seek_to_sec(clamped)
        GLib.timeout_add(150, self._finish_seeking)
        return False

    def _finish_seeking(self):
        self.is_seeking = False
        return GLib.SOURCE_REMOVE

    def seek_to_sec(self, seconds):
        if not self.media_stream:
            return
        target_us = int(max(0.0, seconds) * 1_000_000)
        try:
            self.media_stream.seek(target_us)
        except Exception:
            pass

    def seek_relative(self, delta_seconds):
        if not self.media_stream:
            return
        cur_sec = self.media_stream.get_timestamp() / 1_000_000.0
        target = max(0.0, min(self.duration_sec, cur_sec + delta_seconds))
        self.seek_to_sec(target)
        self.lbl_cur_time.set_text(video_utils.format_duration(target))
        if not self._syncing_slider:
            self._syncing_slider = True
            self.seek_adj.set_value(target)
            self._syncing_slider = False

    def stop(self):
        """Stop playback, disconnect signals, and release media resources."""
        self._stop_periodic_timer()
        if hasattr(self, "picture") and self.picture:
            try:
                self.picture.set_paintable(None)
            except Exception:
                pass

        if self.media_file:
            try:
                self.media_file.pause()
            except Exception:
                pass
            for sid in self._sig_ids:
                try:
                    self.media_file.disconnect(sid)
                except Exception:
                    pass
            self._sig_ids.clear()
            self.media_file = None
            self.media_stream = None

        self.current_path = None
        self.duration_sec = 0.0
        self.is_seeking = False
        self._update_play_icon(False)
