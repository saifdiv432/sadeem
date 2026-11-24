#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Freedesktop ScreenCast Portal Client for Sadeem OS.
Communicates with org.freedesktop.portal.ScreenCast to establish PipeWire video streams
for monitors, area selections, and individual windows.
Manages persistent restore tokens in ~/.config/sadeem-capture/state.json.
"""

import json
import os
import random
import string
import sys
import time

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

CONFIG_DIR = os.path.expanduser("~/.config/sadeem-capture")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")


def load_state():
    if os.path.isfile(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def get_restore_token(mode: str) -> str:
    state = load_state()
    return state.get("restore_tokens", {}).get(mode, "")


def set_restore_token(mode: str, token: str):
    if not token or mode == "window":
        return
    state = load_state()
    if "restore_tokens" not in state:
        state["restore_tokens"] = {}
    state["restore_tokens"][mode] = token
    save_state(state)


def clear_restore_token(mode: str):
    state = load_state()
    if "restore_tokens" in state and mode in state["restore_tokens"]:
        del state["restore_tokens"][mode]
        save_state(state)


def random_token(prefix="sadeem_"):
    chars = string.ascii_letters + string.digits
    suffix = "".join(random.choices(chars, k=10))
    return f"{prefix}{suffix}"


class ScreenCastPortalSession:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.session_handle = None
        self.pipewire_fd = -1
        self.node_id = None
        self.mode = "screen"

    def request_screencast(self, mode="screen", cursor_mode=2, parent_window=""):
        """
        Requests a ScreenCast session via org.freedesktop.portal.ScreenCast.
        mode: "screen", "selection", or "window"
        cursor_mode: 1 (Hidden), 2 (Embedded)
        Returns: (status: str, node_id: int, fd: int) where status is "success", "canceled", or "error".
        """
        self.mode = mode
        sender = self.bus.get_unique_name().replace(".", "_").lstrip(":")

        # 1. CreateSession
        sess_token = random_token("sess_")
        session_req_token = random_token("req_")
        create_opts = {
            "session_handle_token": GLib.Variant("s", sess_token),
            "handle_token": GLib.Variant("s", session_req_token),
        }

        res = self._call_portal_sync_request(
            "CreateSession",
            GLib.Variant("(a{sv})", (create_opts,)),
            session_req_token,
            sender,
        )
        if not res:
            return "error", None, -1
        if res[0] == 1:
            return "canceled", None, -1
        if res[0] != 0:
            print(f"[Portal] CreateSession failed: {res}", file=sys.stderr)
            return "error", None, -1

        results = res[1]
        self.session_handle = results.get("session_handle")
        if not self.session_handle:
            # Reconstruct session handle if not returned directly in dict
            self.session_handle = f"/org/freedesktop/portal/desktop/session/{sender}/{sess_token}"

        # 2. SelectSources
        # types: bit 0 (1) = Monitor, bit 1 (2) = Window
        source_type = 2 if mode == "window" else 1
        select_token = random_token("req_")
        persist_val = 0 if mode == "window" else 2
        select_opts = {
            "types": GLib.Variant("u", source_type),
            "multiple": GLib.Variant("b", False),
            "cursor_mode": GLib.Variant("u", cursor_mode),
            "persist_mode": GLib.Variant("u", persist_val),
            "handle_token": GLib.Variant("s", select_token),
        }

        if mode == "window":
            clear_restore_token("window")
        else:
            # Check existing restore_token for screen / selection
            saved_token = get_restore_token(mode)
            if saved_token:
                select_opts["restore_token"] = GLib.Variant("s", saved_token)

        res = self._call_portal_sync_request(
            "SelectSources",
            GLib.Variant("(oa{sv})", (self.session_handle, select_opts)),
            select_token,
            sender,
        )
        if not res:
            self.close()
            return "error", None, -1
        if res[0] == 1:
            self.close()
            return "canceled", None, -1
        if res[0] != 0:
            print(f"[Portal] SelectSources failed: {res}", file=sys.stderr)
            self.close()
            return "error", None, -1

        # 3. Start Session
        start_token = random_token("req_")
        start_opts = {
            "handle_token": GLib.Variant("s", start_token),
        }

        res = self._call_portal_sync_request(
            "Start",
            GLib.Variant("(osa{sv})", (self.session_handle, parent_window or "", start_opts)),
            start_token,
            sender,
        )
        if not res:
            self.close()
            return "error", None, -1
        if res[0] == 1:
            self.close()
            return "canceled", None, -1
        if res[0] != 0:
            print(f"[Portal] Start failed: {res}", file=sys.stderr)
            self.close()
            return "error", None, -1

        start_results = res[1]
        streams = start_results.get("streams", [])
        if not streams:
            print("[Portal] No streams returned in Start response", file=sys.stderr)
            self.close()
            return "error", None, -1

        # Extract first stream node_id
        # streams is array of (uint32 node_id, a{sv} stream_properties)
        self.node_id = streams[0][0]

        # Save new restore_token if provided (never for window mode)
        if mode != "window":
            new_token = start_results.get("restore_token")
            if new_token:
                set_restore_token(mode, new_token)

        # 4. OpenPipeWireRemote
        self.pipewire_fd = self._open_pipewire_remote()

        return "success", self.node_id, self.pipewire_fd

    def _open_pipewire_remote(self) -> int:
        """Calls OpenPipeWireRemote on session_handle to obtain the file descriptor."""
        try:
            res, fd_list = self.bus.call_with_unix_fd_list_sync(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.ScreenCast",
                "OpenPipeWireRemote",
                GLib.Variant("(oa{sv})", (self.session_handle, {})),
                GLib.VariantType.new("(h)"),
                Gio.DBusCallFlags.NONE,
                3000,
                None,
                None,
            )
            if fd_list and fd_list.get_length() > 0:
                idx = res.unpack()[0] if res else 0
                raw_fd = fd_list.get(idx)
                if raw_fd >= 0:
                    return os.dup(raw_fd)
        except Exception as e:
            print(f"[Portal] OpenPipeWireRemote error: {e}", file=sys.stderr)
        return -1

    def _call_portal_sync_request(self, method_name, parameters, req_token, sender, timeout_ms=45000):
        """
        Synchronously calls a portal method that returns a Request object
        and waits on a GLib main loop until the Response signal fires.
        """
        req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{req_token}"
        loop = GLib.MainLoop()
        response_data = []

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            # Signature: (uint32 response, a{sv} results)
            unpacked = params.unpack()
            response_data.append((unpacked[0], unpacked[1]))
            if loop.is_running():
                loop.quit()

        sub_id = self.bus.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Request",
            "Response",
            req_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
        )

        timeout_id = None
        try:
            # Invoke method
            self.bus.call_sync(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.ScreenCast",
                method_name,
                parameters,
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )

            # Timeout safety
            def on_timeout():
                if loop.is_running():
                    loop.quit()
                return GLib.SOURCE_REMOVE

            timeout_id = GLib.timeout_add(timeout_ms, on_timeout)
            loop.run()
        except Exception as exc:
            print(f"[Portal] Call {method_name} failed: {exc}", file=sys.stderr)
            return None
        finally:
            if timeout_id:
                GLib.source_remove(timeout_id)
            if sub_id:
                self.bus.signal_unsubscribe(sub_id)

        return response_data[0] if response_data else None

    def close(self):
        """Closes the ScreenCast session."""
        if self.session_handle:
            try:
                self.bus.call_sync(
                    "org.freedesktop.portal.Desktop",
                    self.session_handle,
                    "org.freedesktop.portal.Session",
                    "Close",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    1500,
                    None,
                )
            except Exception:
                pass
            self.session_handle = None

        if self.pipewire_fd >= 0:
            try:
                os.close(self.pipewire_fd)
            except Exception:
                pass
            self.pipewire_fd = -1
