#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D-Bus Capture Client for Sadeem OS.
Connects lazily to org.sadeem.CaptureHelper with non-blocking clipboard copy
and sadeem-gallery handoff.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import threading

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

import i18n


class CaptureClient:
    def __init__(self):
        self._bus = None
        self._helper_proxy = None
        self._gnome_proxy = None
        self._connect_bus()

    def _connect_bus(self):
        if self._bus is not None:
            return
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            print(f"[CaptureClient] Session bus error: {e}", file=sys.stderr)

    def ensure_helper_proxy(self):
        self._connect_bus()
        if self._bus is None:
            return None

        if self._helper_proxy is not None:
            try:
                if self._helper_proxy.get_name_owner():
                    return self._helper_proxy
            except Exception:
                pass
            self._helper_proxy = None

        try:
            proxy = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.DO_NOT_AUTO_START,
                None,
                "org.sadeem.CaptureHelper",
                "/org/sadeem/CaptureHelper",
                "org.sadeem.CaptureHelper",
                None,
            )
            if proxy.get_name_owner():
                self._helper_proxy = proxy
                return self._helper_proxy
        except Exception as e:
            print(f"[CaptureClient] CaptureHelper proxy error: {e}", file=sys.stderr)
        return None

    def _ensure_gnome_proxy(self):
        self._connect_bus()
        if self._bus is None:
            return None
        if self._gnome_proxy is None:
            try:
                self._gnome_proxy = Gio.DBusProxy.new_sync(
                    self._bus,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    "org.gnome.Shell.Screenshot",
                    "/org/gnome/Shell/Screenshot",
                    "org.gnome.Shell.Screenshot",
                    None,
                )
            except Exception:
                self._gnome_proxy = None
        return self._gnome_proxy

    def is_helper_available(self) -> bool:
        return self.ensure_helper_proxy() is not None

    def set_halo_active(self, active: bool) -> bool:
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "SetHaloActive",
                    GLib.Variant("(b)", (bool(active),)),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception:
                pass
        return False

    def set_recording_state(self, active: bool) -> bool:
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "SetRecordingState",
                    GLib.Variant("(b)", (bool(active),)),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception:
                pass
        return False

    def set_gnome_indicator_suppressed(self, active: bool) -> bool:
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "SetGnomeIndicatorSuppressed",
                    GLib.Variant("(b)", (bool(active),)),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception:
                pass
        return False

    def flash_camera_indicator(self) -> bool:
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "FlashCameraIndicator",
                    None,
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception:
                pass
        return False

    def subscribe_stop_recording(self, callback):
        self._connect_bus()
        if self._bus:
            try:
                return self._bus.signal_subscribe(
                    None,
                    "org.sadeem.CaptureHelper",
                    "StopRecordingRequested",
                    "/org/sadeem/CaptureHelper",
                    None,
                    Gio.DBusSignalFlags.NONE,
                    lambda *args: callback(),
                )
            except Exception as e:
                print(f"[CaptureClient] Subscribe stop error: {e}", file=sys.stderr)
        return None

    def subscribe_silent_screenshot(self, callback):
        self._connect_bus()
        if self._bus:
            try:
                return self._bus.signal_subscribe(
                    None,
                    "org.sadeem.CaptureHelper",
                    "SilentScreenshotRequested",
                    "/org/sadeem/CaptureHelper",
                    None,
                    Gio.DBusSignalFlags.NONE,
                    lambda *args: callback(),
                )
            except Exception as e:
                print(f"[CaptureClient] Subscribe silent error: {e}", file=sys.stderr)
        return None

    def unsubscribe(self, sub_id):
        if self._bus and sub_id:
            try:
                self._bus.signal_unsubscribe(sub_id)
            except Exception:
                pass

    def list_windows(self):
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "ListWindows",
                    None,
                    Gio.DBusCallFlags.NONE,
                    2000,
                    None,
                )
                return json.loads(res.unpack()[0])
            except Exception as e:
                print(f"[CaptureClient] ListWindows error: {e}", file=sys.stderr)
        return []

    def capture_screen(self, include_cursor: bool, file_path: str) -> bool:
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "CaptureScreen",
                    GLib.Variant("(bs)", (bool(include_cursor), file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                if res.unpack()[0] and os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return True
            except Exception as e:
                print(f"[CaptureClient] CaptureHelper.CaptureScreen failed: {e}", file=sys.stderr)

        gproxy = self._ensure_gnome_proxy()
        if gproxy:
            try:
                res = gproxy.call_sync(
                    "Screenshot",
                    GLib.Variant("(bbs)", (bool(include_cursor), False, file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                success, _used = res.unpack()
                if success and os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return True
            except Exception as e:
                print(f"[CaptureClient] GnomeScreenshot.Screenshot failed: {e}", file=sys.stderr)

        return False

    def capture_area(self, x: int, y: int, width: int, height: int, include_cursor: bool, file_path: str) -> bool:
        if width <= 0 or height <= 0:
            return False

        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "CaptureArea",
                    GLib.Variant("(iiiibs)", (int(x), int(y), int(width), int(height), bool(include_cursor), file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                if res.unpack()[0] and os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return True
            except Exception as e:
                print(f"[CaptureClient] CaptureHelper.CaptureArea failed: {e}", file=sys.stderr)

        gproxy = self._ensure_gnome_proxy()
        if gproxy:
            try:
                res = gproxy.call_sync(
                    "ScreenshotArea",
                    GLib.Variant("(iiiibs)", (int(x), int(y), int(width), int(height), False, file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                success, _used = res.unpack()
                if success and os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return True
            except Exception as e:
                print(f"[CaptureClient] GnomeScreenshot.ScreenshotArea failed: {e}", file=sys.stderr)

        return False

    def capture_window(self, window_id: int, include_frame: bool, include_cursor: bool, file_path: str) -> bool:
        proxy = self.ensure_helper_proxy()
        if proxy:
            try:
                res = proxy.call_sync(
                    "CaptureWindow",
                    GLib.Variant("(ubbs)", (int(window_id), bool(include_frame), bool(include_cursor), file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                if res.unpack()[0] and os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return True
            except Exception as e:
                print(f"[CaptureClient] CaptureHelper.CaptureWindow failed: {e}", file=sys.stderr)

        gproxy = self._ensure_gnome_proxy()
        if gproxy:
            try:
                res = gproxy.call_sync(
                    "ScreenshotWindow",
                    GLib.Variant("(bbbs)", (bool(include_frame), bool(include_cursor), False, file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                success, _used = res.unpack()
                if success and os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                    return True
            except Exception as e:
                print(f"[CaptureClient] GnomeScreenshot.ScreenshotWindow failed: {e}", file=sys.stderr)

        return False


def generate_screenshot_path() -> str:
    pics_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    if not pics_dir:
        pics_dir = os.path.expanduser("~/Pictures")
    folder_name = i18n.t("folder_screenshots") or "Screenshots"
    screenshots_dir = os.path.join(pics_dir, folder_name)
    os.makedirs(screenshots_dir, exist_ok=True)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    prefix = i18n.t("filename_prefix")
    return os.path.join(screenshots_dir, f"{prefix}_{now_str}.png")


def _copy_worker(file_path: str):
    try:
        with open(file_path, "rb") as f:
            proc = subprocess.Popen(
                ["wl-copy", "--type", "image/png"],
                stdin=f,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            proc.wait(timeout=3.0)
    except Exception as e:
        print(f"[CaptureClient] Async clipboard copy error: {e}", file=sys.stderr)


def copy_file_to_clipboard(file_path: str) -> bool:
    """Non-blocking clipboard copy running in background thread."""
    if not os.path.isfile(file_path) or not shutil.which("wl-copy"):
        return False
    t = threading.Thread(target=_copy_worker, args=(file_path,), daemon=True)
    t.start()
    return True


def launch_gallery_editor(file_path: str):
    if not os.path.isfile(file_path):
        return
    try:
        if shutil.which("systemd-run"):
            cmd = ["systemd-run", "--user", "--scope", "--quiet", "sadeem-gallery", "--edit", file_path]
        else:
            cmd = ["sadeem-gallery", "--edit", file_path]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception as e:
        print(f"[CaptureClient] Failed to spawn sadeem-gallery: {e}", file=sys.stderr)
