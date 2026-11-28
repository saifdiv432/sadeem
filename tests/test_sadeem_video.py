#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit & integration tests for Sadeem Video (فيديو سديم).
Runs both locally (with live libmpv.so.2 probe) and headlessly on Ubuntu CI
under xvfb-run without requiring libmpv.so.2 to be installed.
"""

import ctypes
import locale
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VIDEO_DIR = os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-video")

if VIDEO_DIR in sys.path:
    sys.path.remove(VIDEO_DIR)
sys.path.insert(0, VIDEO_DIR)

for mod_name in ("app", "i18n", "mpv_engine", "playlist"):
    sys.modules.pop(mod_name, None)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

Adw.init()

import app as video_app
import i18n as video_i18n
import mpv_engine
import playlist


class _FakeMpvLib:
    """Minimal mock of libmpv.so.2 C functions for CI & unit verification."""

    def __init__(self) -> None:
        self.options = {}
        self.props_str = {"volume": "100", "hwdec-current": "vaapi", "video-codec": "h264"}
        self.props_bool = {"pause": 0, "mute": 0}
        self.props_int = {"aid": 1, "sid": 0, "video-rotate": 0, "width": 1920, "height": 1080}
        self.props_double = {"volume": 100.0, "speed": 1.0, "time-pos": 12.5, "duration": 120.0}
        self.commands = []
        self.async_commands = []
        self.terminated = False
        self.queued_events = []
        self._allocated = []

    def mpv_create(self):
        return 0x123456

    def mpv_initialize(self, _ctx):
        return 0

    def mpv_terminate_destroy(self, _ctx):
        self.terminated = True

    def mpv_set_option_string(self, _ctx, k, v):
        self.options[k.decode("utf-8")] = v.decode("utf-8")
        return 0

    def mpv_set_property_string(self, _ctx, k, v):
        self.props_str[k.decode("utf-8")] = v.decode("utf-8")
        return 0

    def mpv_set_property(self, _ctx, k, fmt, val_ptr):
        key = k.decode("utf-8")
        if fmt == mpv_engine.MPV_FORMAT_FLAG:
            self.props_bool[key] = ctypes.cast(val_ptr, ctypes.POINTER(ctypes.c_int)).contents.value
        elif fmt == mpv_engine.MPV_FORMAT_INT64:
            self.props_int[key] = ctypes.cast(val_ptr, ctypes.POINTER(ctypes.c_int64)).contents.value
        elif fmt == mpv_engine.MPV_FORMAT_DOUBLE:
            self.props_double[key] = ctypes.cast(val_ptr, ctypes.POINTER(ctypes.c_double)).contents.value
        return 0

    def mpv_get_property(self, _ctx, k, fmt, out_ptr):
        key = k.decode("utf-8")
        if fmt == mpv_engine.MPV_FORMAT_FLAG:
            ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_int)).contents.value = self.props_bool.get(key, 0)
            return 0
        if fmt == mpv_engine.MPV_FORMAT_INT64:
            ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_int64)).contents.value = self.props_int.get(key, 0)
            return 0
        if fmt == mpv_engine.MPV_FORMAT_DOUBLE:
            ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_double)).contents.value = self.props_double.get(key, 0.0)
            return 0
        return -1

    def mpv_get_property_string(self, _ctx, k):
        key = k.decode("utf-8")
        val = self.props_str.get(key)
        if val is None:
            return None
        buf = ctypes.create_string_buffer(val.encode("utf-8"))
        self._allocated.append(buf)
        return ctypes.cast(buf, ctypes.c_void_p).value

    def mpv_free(self, _ptr):
        pass

    def mpv_free_node_contents(self, _node):
        pass

    def mpv_error_string(self, rc):
        return f"error {rc}".encode("utf-8")

    def mpv_command(self, _ctx, arr):
        items = []
        i = 0
        while arr[i] is not None:
            items.append(arr[i].decode("utf-8"))
            i += 1
        self.commands.append(items)
        return 0

    def mpv_command_async(self, _ctx, reply_userdata, arr):
        items = []
        i = 0
        while arr[i] is not None:
            items.append(arr[i].decode("utf-8"))
            i += 1
        self.async_commands.append((reply_userdata, items))
        return 0

    def mpv_wait_event(self, _ctx, _timeout):
        if self.queued_events:
            ev = self.queued_events.pop(0)
        else:
            ev = mpv_engine.MpvEvent(mpv_engine.MPV_EVENT_NONE, 0, 0, None)
        return ctypes.pointer(ev)

    def mpv_render_context_free(self, _rctx):
        pass


class TestSadeemVideo(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="sadeem_video_test_")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_playlist_natural_sort_and_siblings(self):
        d = self.tmp_dir.name
        names = ["ep10.mp4", "ep2.mp4", "ep1.mp4", "Alpha_12.mkv", "Alpha_3.mkv", "readme.txt", ".hidden.mp4", "sub.srt"]
        for n in names:
            with open(os.path.join(d, n), "wb") as fp:
                fp.write(b"data")

        siblings = playlist.scan_sibling_videos(os.path.join(d, "ep2.mp4"))
        basenames = [os.path.basename(p) for p in siblings]
        self.assertEqual(basenames, ["Alpha_3.mkv", "Alpha_12.mkv", "ep1.mp4", "ep2.mp4", "ep10.mp4"])

        mgr = playlist.PlaylistManager()
        cur = mgr.load_with_siblings(os.path.join(d, "ep2.mp4"))
        self.assertEqual(os.path.basename(cur), "ep2.mp4")
        self.assertEqual(os.path.basename(mgr.next()), "ep10.mp4")
        self.assertIsNone(mgr.next(wrap=False))
        self.assertEqual(os.path.basename(mgr.next(wrap=True)), "Alpha_3.mkv")
        self.assertEqual(os.path.basename(mgr.previous(wrap=True)), "ep10.mp4")

    def test_state_store_persistence_and_resume_thresholds(self):
        state_path = os.path.join(self.tmp_dir.name, "sub", "state.json")
        store = playlist.StateStore(state_path=state_path)
        vid = os.path.join(self.tmp_dir.name, "clip.mp4")

        store.set_position(vid, 2.0, 100.0)
        store.set_position(vid + "_mid", 45.25, 100.0)
        store.set_position(vid + "_end", 97.0, 100.0)
        store.set_setting("volume", 125.0)
        store.set_setting("muted", True)
        store.set_setting("speed", 1.5)
        store.set_setting("loop_mode", "playlist")
        store.save()

        reloaded = playlist.StateStore(state_path=state_path)
        self.assertEqual(reloaded.get_resume_position(vid), 0.0)
        self.assertAlmostEqual(reloaded.get_resume_position(vid + "_mid"), 45.25, places=2)
        self.assertEqual(reloaded.get_resume_position(vid + "_end"), 0.0)
        self.assertEqual(reloaded.get_setting("volume"), 125.0)
        self.assertTrue(reloaded.get_setting("muted"))
        self.assertEqual(reloaded.get_setting("speed"), 1.5)
        self.assertEqual(reloaded.get_setting("loop_mode"), "playlist")

    def test_i18n_ten_languages_complete(self):
        self.assertEqual(
            video_i18n.SUPPORTED_LANGUAGES,
            ("ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh"),
        )
        base_keys = set(video_i18n.STRINGS["ar"].keys())
        self.assertGreaterEqual(len(base_keys), 50)
        for lang in video_i18n.SUPPORTED_LANGUAGES:
            table = video_i18n.STRINGS[lang]
            self.assertEqual(set(table.keys()), base_keys, f"Key mismatch in {lang}")
            for k, val in table.items():
                self.assertTrue(isinstance(val, str) and len(val.strip()) > 0, f"Empty {lang}.{k}")
            # Verify formatted keys don't raise
            self.assertTrue(table["osd_volume"].format(v=100))
            self.assertTrue(table["osd_speed"].format(v=1.25))
            self.assertTrue(table["playlist_count"].format(n=3))

    def test_mpv_engine_mock_commands_and_properties(self):
        fake = _FakeMpvLib()
        eng = mpv_engine.MpvEngine(libmpv=fake)
        eng.initialize()

        self.assertEqual(fake.options["vo"], "libmpv")
        self.assertEqual(fake.options["hwdec"], "auto-copy")
        self.assertEqual(fake.options["keep-open"], "yes")
        self.assertEqual(fake.options["sub-auto"], "fuzzy")
        self.assertEqual(fake.options["sub-codepage"], "auto")
        self.assertEqual(fake.options["sub-vsfilter-bidi-compat"], "no")
        self.assertEqual(fake.options["sub-margin-y"], "34")
        self.assertEqual(fake.options["sub-border-size"], "2.5")
        self.assertEqual(fake.options["embeddedfonts"], "yes")

        with open(os.path.join(VIDEO_DIR, "mpv_engine.py"), "r", encoding="utf-8") as fp:
            eng_src = fp.read()
        self.assertNotIn("utf8:cp1256", eng_src)
        self.assertEqual(fake.options["volume-max"], "150")
        self.assertEqual(fake.options["osd-level"], "0")

        eng.load_file("/tmp/demo.mp4", start_seconds=25.0)
        self.assertIn((0, ["loadfile", "/tmp/demo.mp4", "replace", "-1", "start=25.000"]), fake.async_commands)

        eng.add_subtitle("/tmp/arabic.srt")
        self.assertIn((0, ["sub-add", "/tmp/arabic.srt", "select"]), fake.async_commands)

        self.assertFalse(eng.get_sub_bidi_compat())
        eng.set_sub_bidi_compat(True)
        self.assertEqual(fake.props_str["sub-vsfilter-bidi-compat"], "yes")
        self.assertTrue(eng.get_sub_bidi_compat())
        eng.set_sub_bidi_compat(False)
        self.assertEqual(fake.props_str["sub-vsfilter-bidi-compat"], "no")
        self.assertFalse(eng.get_sub_bidi_compat())
        eng.seek(10.0)
        self.assertIn((0, ["seek", "10.000", "relative"]), fake.async_commands)

        eng.set_volume(200.0)
        self.assertEqual(fake.props_double["volume"], 150.0)
        eng.set_volume(-10.0)
        self.assertEqual(fake.props_double["volume"], 0.0)

        eng.set_speed(2.0)
        self.assertEqual(fake.props_double["speed"], 2.0)
        eng.set_aspect_ratio("fill")
        self.assertEqual(fake.props_double["panscan"], 1.0)
        eng.set_rotation(90)
        self.assertEqual(fake.props_int["video-rotate"], 90)
        eng.set_equalizer(brightness=10.0, contrast=-5.0, saturation=15.0, gamma=3.0)
        self.assertEqual(fake.props_double["brightness"], 10.0)
        self.assertEqual(fake.props_double["contrast"], -5.0)
        eng.reset_equalizer()
        self.assertEqual(fake.props_double["brightness"], 0.0)

        shot = os.path.join(self.tmp_dir.name, "shots", "snap.png")
        eng.take_screenshot(shot)
        self.assertIn(["screenshot-to-file", shot, "subtitles"], fake.commands)

        fake.queued_events = [
            mpv_engine.MpvEvent(mpv_engine.MPV_EVENT_START_FILE, 0, 0, None),
            mpv_engine.MpvEvent(mpv_engine.MPV_EVENT_FILE_LOADED, 0, 0, None),
        ]
        events = eng.drain_events()
        self.assertEqual([e["event_id"] for e in events], [6, 8])

        eng.destroy()
        self.assertTrue(fake.terminated)

    def test_real_libmpv_if_available(self):
        try:
            mpv_engine.load_libmpv()
        except mpv_engine.MpvUnavailableError:
            # Skip live C probe cleanly on CI machines without libmpv.so.2
            return

        eng = mpv_engine.MpvEngine()
        eng.initialize()
        try:
            ver = eng.get_property_string("mpv-version")
            self.assertIsNotNone(ver)
            self.assertEqual(eng.get_property_string("vo"), "libmpv")
            eng.drain_events()
        finally:
            eng.destroy()

    def test_sadeem_video_window_ui_ltr_bidi_and_css(self):
        # Validate CSS compiles with zero warnings/errors
        css_errors = []
        provider = Gtk.CssProvider()
        provider.connect("parsing-error", lambda _p, _sec, err: css_errors.append(err.message))
        provider.load_from_string(video_app.SADEEM_VIDEO_PLAYER_CSS)
        self.assertEqual(css_errors, [], f"CSS errors found: {css_errors}")

        fake = _FakeMpvLib()
        eng = mpv_engine.MpvEngine(libmpv=fake)
        store = playlist.StateStore(state_path=os.path.join(self.tmp_dir.name, "state.json"))
        app = video_app.SadeemVideoApp()
        app.set_application_id("org.sadeem.Video.TestUI")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        app.register(None)

        # Verify LC_NUMERIC="C" was enforced in do_startup
        self.assertEqual(locale.setlocale(locale.LC_NUMERIC), "C")

        vid = os.path.join(self.tmp_dir.name, "تجربة_فيديو.mp4")
        with open(vid, "wb") as fp:
            fp.write(b"fake")

        win = video_app.SadeemVideoWindow(app=app, initial_files=[vid], engine=eng, state_store=store)
        try:
            self.assertEqual(video_app.APP_ID, "org.sadeem.Video")
            self.assertEqual(win.get_icon_name(), "sadeem-video")
            self.assertEqual(win.progress_row.get_direction(), Gtk.TextDirection.LTR)
            self.assertEqual(win.seek_scale.get_direction(), Gtk.TextDirection.LTR)
            self.assertEqual(win.transport_box.get_direction(), Gtk.TextDirection.LTR)

            # Revealer CROSSFADE + Adw.Clamp capsule + crisp info icon (never lightbulb)
            self.assertIsInstance(win.top_revealer, Gtk.Revealer)
            self.assertIsInstance(win.bottom_revealer, Gtk.Revealer)
            self.assertEqual(win.top_revealer.get_transition_type(), Gtk.RevealerTransitionType.CROSSFADE)
            self.assertEqual(win.bottom_revealer.get_transition_type(), Gtk.RevealerTransitionType.CROSSFADE)
            self.assertIsInstance(win.bottom_clamp, Adw.Clamp)
            self.assertEqual(win.info_btn.get_icon_name(), "info-outline-symbolic")

            with open(os.path.join(VIDEO_DIR, "app.py"), "r", encoding="utf-8") as fp:
                app_src = fp.read()
            self.assertNotIn("dialog-information-symbolic", app_src)

            # Verify Settings Popover uses Gtk.Stack with expected sub-pages & zero burgundy inside popovers
            self.assertIsInstance(win.settings_stack, Gtk.Stack)
            self.assertEqual(
                win.settings_stack.get_transition_type(),
                Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
            )
            self.assertFalse(win.settings_stack.get_vhomogeneous())
            for page_name in ("main", "speed", "repeat", "video", "eq"):
                self.assertIsNotNone(win.settings_stack.get_child_by_name(page_name))
            self.assertEqual(win.settings_stack.get_visible_child_name(), "main")
            win.settings_stack.set_visible_child_name("speed")
            self.assertEqual(win.settings_stack.get_visible_child_name(), "speed")

            self.assertNotIn("rgba(122, 28, 51", video_app.SADEEM_VIDEO_PLAYER_CSS)
            self.assertNotIn("sadeem-pill-active", video_app.SADEEM_VIDEO_PLAYER_CSS)
            self.assertNotIn("sadeem-row-active", video_app.SADEEM_VIDEO_PLAYER_CSS)
            self.assertIn(".sadeem-popover-active", video_app.SADEEM_VIDEO_PLAYER_CSS)
            self.assertIn("alpha(currentColor, 0.10)", video_app.SADEEM_VIDEO_PLAYER_CSS)

            # Start playback directly (without requiring GL realize in headless CI)
            win._start_playback(vid)
            self.assertTrue(win.is_playing)
            self.assertEqual(win.play_btn.get_icon_name(), "media-playback-pause-symbolic")

            win.toggle_hud()
            self.assertFalse(win.top_revealer.get_reveal_child())
            self.assertFalse(win.bottom_revealer.get_reveal_child())

            # Seed initial pointer position, then send small jitter <= 2px -> must stay hidden
            win._on_stage_pointer_motion(None, 200.0, 200.0)
            win.toggle_hud()
            self.assertFalse(win.bottom_revealer.get_reveal_child())
            win._on_stage_pointer_motion(None, 201.0, 201.5)
            self.assertFalse(win.bottom_revealer.get_reveal_child())

            # Real movement (> 2px) reveals HUD and schedules auto-hide
            win._on_stage_pointer_motion(None, 230.0, 230.0)
            self.assertTrue(win.top_revealer.get_reveal_child())
            self.assertTrue(win.bottom_revealer.get_reveal_child())

            # Auto-hide fires while playing; pause cancels auto-hide & switches icon
            win._on_hud_hide_timeout()
            self.assertFalse(win.bottom_revealer.get_reveal_child())

            win.toggle_play_pause()
            self.assertFalse(win.is_playing)
            self.assertEqual(win.play_btn.get_icon_name(), "media-playback-start-symbolic")
            self.assertTrue(win.bottom_revealer.get_reveal_child())

            title_txt = win.title_label.get_text()
            self.assertTrue(title_txt.startswith("\u2066") and title_txt.endswith("\u2069"))
            self.assertIn("تجربة_فيديو.mp4", title_txt)
        finally:
            win.shutdown()
            win.destroy()

    def test_system_integration_desktop_icon_recipe_mime(self):
        launcher = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-video")
        self.assertTrue(os.path.isfile(launcher))
        self.assertTrue(os.access(launcher, os.X_OK))
        res = subprocess.run(["bash", "-n", launcher], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

        desktop = os.path.join(REPO_ROOT, "files/system/usr/share/applications/sadeem-video.desktop")
        with open(desktop, "r", encoding="utf-8") as f:
            desk_txt = f.read()
        self.assertIn("StartupWMClass=org.sadeem.Video", desk_txt)
        self.assertIn("Exec=/usr/bin/sadeem-video", desk_txt)
        self.assertIn("Icon=sadeem-video", desk_txt)

        required_mimes = (
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
        )
        for m in required_mimes:
            self.assertIn(m, desk_txt)

        svg_path = os.path.join(REPO_ROOT, "files/system/usr/share/icons/hicolor/scalable/apps/sadeem-video.svg")
        svg_tree = ET.parse(svg_path)
        svg_root = svg_tree.getroot()
        self.assertEqual(svg_root.attrib.get("viewBox"), "0 0 128 128")
        self.assertEqual(svg_root.attrib.get("width"), "128")
        self.assertEqual(svg_root.attrib.get("height"), "128")
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_txt = f.read()
        self.assertIn("#7a1c33", svg_txt)
        self.assertIn("#442646", svg_txt)
        self.assertIn("#0f4c5c", svg_txt)
        self.assertIn('x="8" y="8" width="112" height="112" rx="26"', svg_txt)
        self.assertIn("clipPath", svg_txt)
        self.assertIn("feGaussianBlur", svg_txt)
        self.assertNotIn("<image", svg_txt)
        self.assertNotIn(".jpg", svg_txt.lower())
        self.assertTrue(os.path.exists(
            os.path.join(REPO_ROOT, "files/system/usr/share/icons/hicolor/scalable/apps/org.sadeem.Video.svg")
        ))

        recipe_path = os.path.join(REPO_ROOT, "recipes/recipe.yml")
        with open(recipe_path, "r", encoding="utf-8") as f:
            recipe_txt = f.read()
        self.assertIn("- mpv-libs", recipe_txt)
        self.assertIn("/usr/bin/sadeem-video", recipe_txt)

        for mime_rel in (
            "files/system/etc/xdg/mimeapps.list",
            "files/system/usr/share/applications/mimeapps.list",
        ):
            with open(os.path.join(REPO_ROOT, mime_rel), "r", encoding="utf-8") as f:
                mime_txt = f.read()
            for m in required_mimes:
                self.assertIn(f"{m}=sadeem-video.desktop", mime_txt, f"Missing {m} in {mime_rel}")

        self.assertFalse(os.path.exists(os.path.join(VIDEO_DIR, "subtitle_utils.py")))

    def test_native_bidi_compat_toggle_and_i18n_ten_languages(self):
        for lang in video_i18n.SUPPORTED_LANGUAGES:
            self.assertIn("sub_bidi_compat", video_i18n.STRINGS[lang])
            self.assertTrue(video_i18n.STRINGS[lang]["sub_bidi_compat"].strip())

        fake = _FakeMpvLib()
        eng = mpv_engine.MpvEngine(libmpv=fake)
        store = playlist.StateStore(state_path=os.path.join(self.tmp_dir.name, "state_bidi.json"))
        app = video_app.SadeemVideoApp()
        app.set_application_id("org.sadeem.Video.TestBidiToggle")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        app.register(None)

        win = video_app.SadeemVideoWindow(app=app, engine=eng, state_store=store)
        try:
            self.assertFalse(win.sub_bidi_switch.get_active())
            self.assertEqual(fake.props_str.get("sub-vsfilter-bidi-compat"), "no")

            win.sub_bidi_switch.set_active(True)
            self.assertEqual(fake.props_str.get("sub-vsfilter-bidi-compat"), "yes")
            self.assertTrue(store.get_setting("sub_bidi_compat"))

            win.sub_bidi_switch.set_active(False)
            self.assertEqual(fake.props_str.get("sub-vsfilter-bidi-compat"), "no")
            self.assertFalse(store.get_setting("sub_bidi_compat"))
        finally:
            win.shutdown()
            win.destroy()


if __name__ == "__main__":
    unittest.main()
