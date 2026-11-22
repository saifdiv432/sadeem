#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D-Bus Capture Client for Sadeem OS.
Communicates with org.sadeem.CaptureHelper (sadeem-desktop-helper extension)
with automatic fallback to org.gnome.Shell.Screenshot.
Handles clipboard copying and gallery handoff.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys

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
        self._init_proxies()

    def _init_proxies(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            print(f"[CaptureClient] Failed to connect to session bus: {e}", file=sys.stderr)
            return

        # Attempt to create proxy for org.sadeem.CaptureHelper
        try:
            self._helper_proxy = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.DO_NOT_AUTO_START,
                None,
                "org.sadeem.CaptureHelper",
                "/org/sadeem/CaptureHelper",
                "org.sadeem.CaptureHelper",
                None,
            )
            # Verify name owner exists
            if not self._helper_proxy.get_name_owner():
                self._helper_proxy = None
        except Exception as e:
            self._helper_proxy = None

        # Create fallback proxy for org.gnome.Shell.Screenshot
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
        except Exception as e:
            self._gnome_proxy = None

    def set_halo_active(self, active: bool) -> bool:
        """Enables or disables the cursor halo overlay via CaptureHelper."""
        if self._helper_proxy:
            try:
                res = self._helper_proxy.call_sync(
                    "SetHaloActive",
                    GLib.Variant("(b)", (bool(active),)),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception as e:
                pass
        return False

    def set_recording_state(self, active: bool) -> bool:
        """Shows or hides the live top panel recording indicator in GNOME Shell."""
        if self._helper_proxy:
            try:
                res = self._helper_proxy.call_sync(
                    "SetRecordingState",
                    GLib.Variant("(b)", (bool(active),)),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception as e:
                pass
        return False

    def subscribe_stop_recording(self, callback):
        """Subscribes to StopRecordingRequested signal from CaptureHelper."""
        if self._bus:
            try:
                return self._bus.signal_subscribe(
                    "org.sadeem.CaptureHelper",
                    "org.sadeem.CaptureHelper",
                    "StopRecordingRequested",
                    "/org/sadeem/CaptureHelper",
                    None,
                    Gio.DBusSignalFlags.NONE,
                    lambda *args: callback(),
                )
            except Exception as e:
                print(f"[CaptureClient] Failed to subscribe StopRecordingRequested: {e}", file=sys.stderr)
        return None

    def list_windows(self):
        """Returns list of open windows [{id, title, appName, iconName, x, y, width, height, monitor}]."""
        if self._helper_proxy:
            try:
                res = self._helper_proxy.call_sync(
                    "ListWindows",
                    None,
                    Gio.DBusCallFlags.NONE,
                    2000,
                    None,
                )
                raw_json = res.unpack()[0]
                return json.loads(raw_json)
            except Exception as e:
                print(f"[CaptureClient] ListWindows error: {e}", file=sys.stderr)
        return []

    def capture_screen(self, include_cursor: bool, file_path: str) -> bool:
        """Captures entire screen to file_path."""
        # 1. Try CaptureHelper
        if self._helper_proxy:
            try:
                res = self._helper_proxy.call_sync(
                    "CaptureScreen",
                    GLib.Variant("(bs)", (bool(include_cursor), file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                if res.unpack()[0]:
                    return True
            except Exception as e:
                print(f"[CaptureClient] CaptureHelper.CaptureScreen failed: {e}", file=sys.stderr)

        # 2. Fallback to org.gnome.Shell.Screenshot
        if self._gnome_proxy:
            try:
                res = self._gnome_proxy.call_sync(
                    "Screenshot",
                    GLib.Variant("(bbs)", (bool(include_cursor), False, file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                success, used = res.unpack()
                if success and os.path.exists(file_path):
                    return True
            except Exception as e:
                print(f"[CaptureClient] GnomeScreenshot.Screenshot failed: {e}", file=sys.stderr)

        return False

    def capture_area(self, x: int, y: int, width: int, height: int, include_cursor: bool, file_path: str) -> bool:
        """Captures specific rectangular area to file_path."""
        if width <= 0 or height <= 0:
            return False

        # 1. Try CaptureHelper
        if self._helper_proxy:
            try:
                res = self._helper_proxy.call_sync(
                    "CaptureArea",
                    GLib.Variant("(iiiibs)", (int(x), int(y), int(width), int(height), bool(include_cursor), file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                if res.unpack()[0]:
                    return True
            except Exception as e:
                print(f"[CaptureClient] CaptureHelper.CaptureArea failed: {e}", file=sys.stderr)

        # 2. Fallback to org.gnome.Shell.Screenshot
        if self._gnome_proxy:
            try:
                res = self._gnome_proxy.call_sync(
                    "ScreenshotArea",
                    GLib.Variant("(iiiibs)", (int(x), int(y), int(width), int(height), False, file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                success, used = res.unpack()
                if success and os.path.exists(file_path):
                    return True
            except Exception as e:
                print(f"[CaptureClient] GnomeScreenshot.ScreenshotArea failed: {e}", file=sys.stderr)

        return False

    def capture_window(self, window_id: int, include_frame: bool, include_cursor: bool, file_path: str) -> bool:
        """Captures specific window by ID to file_path."""
        # 1. Try CaptureHelper
        if self._helper_proxy:
            try:
                res = self._helper_proxy.call_sync(
                    "CaptureWindow",
                    GLib.Variant("(ubbs)", (int(window_id), bool(include_frame), bool(include_cursor), file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                if res.unpack()[0]:
                    return True
            except Exception as e:
                print(f"[CaptureClient] CaptureHelper.CaptureWindow failed: {e}", file=sys.stderr)

        # 2. Fallback to org.gnome.Shell.Screenshot (captures currently active window)
        if self._gnome_proxy:
            try:
                res = self._gnome_proxy.call_sync(
                    "ScreenshotWindow",
                    GLib.Variant("(bbbs)", (bool(include_frame), bool(include_cursor), False, file_path)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
                success, used = res.unpack()
                if success and os.path.exists(file_path):
                    return True
            except Exception as e:
                print(f"[CaptureClient] GnomeScreenshot.ScreenshotWindow failed: {e}", file=sys.stderr)

        return False


def generate_screenshot_path() -> str:
    """Generates standard destination path inside ~/Pictures/Screenshots."""
    pics_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    if not pics_dir:
        pics_dir = os.path.expanduser("~/Pictures")
    screenshots_dir = os.path.join(pics_dir, "Screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    prefix = i18n.t("filename_prefix")
    return os.path.join(screenshots_dir, f"{prefix}_{now_str}.png")


def copy_file_to_clipboard(file_path: str) -> bool:
    """Copies PNG image data to system clipboard using wl-copy."""
    if not os.path.isfile(file_path):
        return False

    try:
        if shutil.which("wl-copy"):
            with open(file_path, "rb") as f:
                p = subprocess.run(
                    ["wl-copy", "--type", "image/png"],
                    input=f.read(),
                    capture_output=True,
                    timeout=5,
                )
                return p.returncode == 0
    except Exception as e:
        print(f"[CaptureClient] Clipboard copy failed: {e}", file=sys.stderr)
    return False


def launch_gallery_editor(file_path: str):
    """Spawns sadeem-gallery --edit <file_path>."""
    if not os.path.isfile(file_path):
        return

    try:
        subprocess.Popen(
            ["sadeem-gallery", "--edit", file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        print(f"[CaptureClient] Failed to spawn sadeem-gallery: {e}", file=sys.stderr)
