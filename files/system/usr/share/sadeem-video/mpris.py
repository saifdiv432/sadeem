#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Native MPRIS2 D-Bus service for Sadeem Video (فيديو سديم) via Gio.DBusConnection.
Exposes org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player cleanly with zero
external dependencies.
"""

from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.sadeem_video"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_IFACE_ROOT = "org.mpris.MediaPlayer2"
MPRIS_IFACE_PLAYER = "org.mpris.MediaPlayer2.Player"
DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"

SUPPORTED_SCHEMES = ["file", "http", "https", "rtsp", "mms"]
SUPPORTED_MIMES = [
    "video/mp4",
    "video/x-matroska",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-flv",
    "video/mpeg",
    "video/ogg",
    "video/mp2t",
    "video/3gpp",
]

MPRIS_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg name="Offset" type="x" direction="in"/>
    </method>
    <method name="SetPosition">
      <arg name="TrackId" type="o" direction="in"/>
      <arg name="Position" type="x" direction="in"/>
    </method>
    <method name="OpenUri">
      <arg name="Uri" type="s" direction="in"/>
    </method>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""


def seconds_to_us(seconds: float) -> int:
    if not seconds or seconds <= 0.0:
        return 0
    return int(round(float(seconds) * 1_000_000))


def us_to_seconds(microseconds: int) -> float:
    return float(microseconds) / 1_000_000.0


def playback_status_str(has_media: bool, is_playing: bool) -> str:
    if not has_media:
        return "Stopped"
    return "Playing" if is_playing else "Paused"


def path_to_uri(target: str) -> str:
    if not target:
        return ""
    if "://" in target:
        return target
    return "file://" + quote(target)


def build_metadata_variants(
    track_index: int,
    title: str,
    target: str,
    duration_seconds: float,
) -> Dict[str, GLib.Variant]:
    """Build MPRIS2 Metadata dictionary (a{sv}) for current media."""
    idx = max(1, int(track_index) + 1)
    meta: Dict[str, GLib.Variant] = {
        "mpris:trackid": GLib.Variant("o", f"/org/mpris/MediaPlayer2/Track/{idx}"),
    }
    if target:
        meta["xesam:url"] = GLib.Variant("s", path_to_uri(target))
    if title:
        meta["xesam:title"] = GLib.Variant("s", title)
    if duration_seconds and duration_seconds > 0.0:
        meta["mpris:length"] = GLib.Variant("x", seconds_to_us(duration_seconds))
    return meta


class MprisService:
    """Manages MPRIS2 D-Bus registration, method dispatch, and PropertiesChanged emission."""

    def __init__(self, window, identity: str = "Sadeem Video") -> None:
        self._win = window
        self._identity = identity
        self._conn: Optional[Gio.DBusConnection] = None
        self._owner_id: int = 0
        self._reg_ids = []
        self._node_info = Gio.DBusNodeInfo.new_for_xml(MPRIS_XML)
        self._destroyed: bool = False

    @property
    def is_registered(self) -> bool:
        return bool(self._reg_ids) and self._conn is not None and not self._destroyed

    def start(self) -> bool:
        if self._destroyed or self._conn is not None:
            return self.is_registered
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            self._conn = None
            return False

        if self._conn is None:
            return False

        for iface_name in (MPRIS_IFACE_ROOT, MPRIS_IFACE_PLAYER):
            iface_info = self._node_info.lookup_interface(iface_name)
            if iface_info is None:
                continue
            try:
                reg_id = self._conn.register_object(
                    MPRIS_OBJECT_PATH,
                    iface_info,
                    self._on_method_call,
                    self._on_get_property,
                    self._on_set_property,
                )
                if reg_id:
                    self._reg_ids.append(reg_id)
            except Exception:
                pass

        if self._reg_ids:
            try:
                self._owner_id = Gio.bus_own_name_on_connection(
                    self._conn,
                    MPRIS_BUS_NAME,
                    Gio.BusNameOwnerFlags.NONE,
                    None,
                    None,
                )
            except Exception:
                self._owner_id = 0

        return self.is_registered

    def _win_state(self) -> Dict[str, Any]:
        win = self._win
        cur = win.playlist_mgr.current_path
        has_media = bool(cur)
        dur = win.engine.get_duration() if (has_media and win.engine.is_initialized) else 0.0
        pos = win.engine.get_time_pos() if (has_media and win.engine.is_initialized) else 0.0
        vol = win.engine.get_volume() if win.engine.is_initialized else 100.0
        speed = float(getattr(win, "_current_speed", 1.0))
        return {
            "path": cur or "",
            "has_media": has_media,
            "playing": bool(win.is_playing),
            "duration": float(dur or 0.0),
            "position": float(pos or 0.0),
            "volume": max(0.0, float(vol) / 100.0),
            "rate": max(0.25, min(3.0, speed)),
            "can_next": win.playlist_mgr.has_next(wrap=False),
            "can_prev": win.playlist_mgr.has_previous(wrap=False),
            "track_index": win.playlist_mgr.current_index,
        }

    def _build_metadata_dict(self) -> Dict[str, GLib.Variant]:
        st = self._win_state()
        if not st["has_media"]:
            return {"mpris:trackid": GLib.Variant("o", "/org/mpris/MediaPlayer2/TrackList/NoTrack")}
        target = st["path"]
        title = target.rsplit("/", 1)[-1] or target
        return build_metadata_variants(
            track_index=st["track_index"],
            title=title,
            target=target,
            duration_seconds=st["duration"],
        )

    def get_player_properties(self) -> Dict[str, GLib.Variant]:
        st = self._win_state()
        return {
            "PlaybackStatus": GLib.Variant("s", playback_status_str(st["has_media"], st["playing"])),
            "Rate": GLib.Variant("d", st["rate"]),
            "Metadata": GLib.Variant("a{sv}", self._build_metadata_dict()),
            "Volume": GLib.Variant("d", st["volume"]),
            "Position": GLib.Variant("x", seconds_to_us(st["position"])),
            "MinimumRate": GLib.Variant("d", 0.25),
            "MaximumRate": GLib.Variant("d", 3.0),
            "CanGoNext": GLib.Variant("b", st["can_next"]),
            "CanGoPrevious": GLib.Variant("b", st["can_prev"]),
            "CanPlay": GLib.Variant("b", st["has_media"]),
            "CanPause": GLib.Variant("b", st["has_media"]),
            "CanSeek": GLib.Variant("b", st["has_media"]),
            "CanControl": GLib.Variant("b", True),
        }

    def _on_get_property(
        self, _conn, _sender, _path, interface_name: str, property_name: str
    ) -> Optional[GLib.Variant]:
        if interface_name == MPRIS_IFACE_ROOT:
            root_props = {
                "CanQuit": GLib.Variant("b", True),
                "CanRaise": GLib.Variant("b", True),
                "HasTrackList": GLib.Variant("b", False),
                "Identity": GLib.Variant("s", self._identity),
                "DesktopEntry": GLib.Variant("s", "sadeem-video"),
                "SupportedUriSchemes": GLib.Variant("as", SUPPORTED_SCHEMES),
                "SupportedMimeTypes": GLib.Variant("as", SUPPORTED_MIMES),
            }
            return root_props.get(property_name)
        if interface_name == MPRIS_IFACE_PLAYER:
            return self.get_player_properties().get(property_name)
        return None

    def _on_set_property(
        self, _conn, _sender, _path, interface_name: str, property_name: str, value: GLib.Variant
    ) -> bool:
        if interface_name != MPRIS_IFACE_PLAYER:
            return False
        win = self._win
        if property_name == "Volume":
            new_pct = max(0.0, min(200.0, float(value.get_double()) * 100.0))
            if win.engine.is_initialized:
                cur_pct = win.engine.get_volume()
                win.adjust_volume(new_pct - cur_pct)
            return True
        if property_name == "Rate":
            rate = max(0.25, min(3.0, float(value.get_double())))
            win.set_speed(rate)
            return True
        return False

    def _on_method_call(
        self,
        _conn,
        _sender,
        _path,
        interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        win = self._win
        try:
            if interface_name == MPRIS_IFACE_ROOT:
                if method_name == "Raise":
                    win.present()
                elif method_name == "Quit":
                    app = win.get_application()
                    if app is not None:
                        app.quit()
                    else:
                        win.close()
                invocation.return_value(None)
                return

            if interface_name == MPRIS_IFACE_PLAYER:
                if method_name == "PlayPause":
                    win.toggle_play_pause()
                elif method_name == "Play":
                    if win.engine.is_initialized and win.playlist_mgr.current_path and win.engine.is_paused():
                        win.toggle_play_pause()
                elif method_name == "Pause":
                    if win.engine.is_initialized and win.playlist_mgr.current_path and not win.engine.is_paused():
                        win.toggle_play_pause()
                elif method_name == "Stop":
                    if hasattr(win, "stop_playback"):
                        win.stop_playback()
                elif method_name == "Next":
                    win.play_next()
                elif method_name == "Previous":
                    win.play_previous()
                elif method_name == "Seek":
                    (offset_us,) = parameters.unpack()
                    win.seek_relative(us_to_seconds(offset_us))
                elif method_name == "SetPosition":
                    _track_id, pos_us = parameters.unpack()
                    if win.engine.is_initialized and win.playlist_mgr.current_path:
                        sec = max(0.0, us_to_seconds(pos_us))
                        win.engine.seek_absolute(sec)
                        self.emit_seeked(sec)
                elif method_name == "OpenUri":
                    (uri,) = parameters.unpack()
                    if uri:
                        if uri.startswith("file://"):
                            gf = Gio.File.new_for_uri(uri)
                            p = gf.get_path()
                            if p:
                                win.open_paths([p])
                        elif hasattr(win, "open_url"):
                            win.open_url(uri)
                invocation.return_value(None)
                return
        except Exception as exc:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.Failed", str(exc))
            return

        invocation.return_dbus_error(
            "org.freedesktop.DBus.Error.UnknownMethod",
            f"Unknown method {interface_name}.{method_name}",
        )

    def emit_properties_changed(self, prop_names: Optional[tuple] = None) -> None:
        if not self.is_registered:
            return
        all_props = self.get_player_properties()
        if prop_names:
            changed = {k: all_props[k] for k in prop_names if k in all_props}
        else:
            changed = all_props
        if not changed:
            return
        try:
            self._conn.emit_signal(
                None,
                MPRIS_OBJECT_PATH,
                DBUS_PROPS_IFACE,
                "PropertiesChanged",
                GLib.Variant("(sa{sv}as)", (MPRIS_IFACE_PLAYER, changed, [])),
            )
        except Exception:
            pass

    def emit_seeked(self, seconds: float) -> None:
        if not self.is_registered:
            return
        try:
            self._conn.emit_signal(
                None,
                MPRIS_OBJECT_PATH,
                MPRIS_IFACE_PLAYER,
                "Seeked",
                GLib.Variant("(x)", (seconds_to_us(seconds),)),
            )
        except Exception:
            pass

    def shutdown(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._conn is not None:
            for reg_id in self._reg_ids:
                try:
                    self._conn.unregister_object(reg_id)
                except Exception:
                    pass
        self._reg_ids.clear()
        if self._owner_id:
            try:
                Gio.bus_unown_name(self._owner_id)
            except Exception:
                pass
            self._owner_id = 0
        self._conn = None
