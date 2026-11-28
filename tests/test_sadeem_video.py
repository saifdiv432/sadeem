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

for mod_name in ("app", "i18n", "mpris", "mpv_engine", "playlist", "popovers", "thumbnails"):
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
        self.render_params = []
        self.update_calls = 0
        self.swap_calls = 0
        self.update_return_flags = mpv_engine.MPV_RENDER_UPDATE_FRAME

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

    def mpv_render_context_update(self, _rctx):
        self.update_calls += 1
        return self.update_return_flags

    def mpv_render_context_render(self, _rctx, params):
        self.render_params.clear()
        i = 0
        while params[i].type != mpv_engine.MPV_RENDER_PARAM_INVALID:
            ptype = int(params[i].type)
            pval = None
            if ptype in (mpv_engine.MPV_RENDER_PARAM_FLIP_Y, mpv_engine.MPV_RENDER_PARAM_BLOCK_FOR_TARGET_TIME):
                pval = ctypes.cast(params[i].data, ctypes.POINTER(ctypes.c_int)).contents.value
            self.render_params.append((ptype, pval))
            i += 1
        return 0

    def mpv_render_context_report_swap(self, _rctx):
        self.swap_calls += 1

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
        self.assertEqual(fake.options["volume-max"], "200")
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

        eng.set_volume(250.0)
        self.assertEqual(fake.props_double["volume"], 200.0)
        eng.set_volume(175.0)
        self.assertEqual(fake.props_double["volume"], 175.0)
        eng.set_volume(-10.0)
        self.assertEqual(fake.props_double["volume"], 0.0)

        # Named audio filters (@night + @eq) + audio-delay
        eng.set_night_mode(True)
        self.assertIn((0, ["af", "add", "@night:lavfi=[dynaudnorm=f=150:g=15:p=0.9]"]), fake.async_commands)
        eng.set_audio_eq_preset("cinema")
        self.assertIn((0, ["af", "add", f"@eq:lavfi=[{mpv_engine.MpvEngine.AUDIO_EQ_PRESETS['cinema']}]"]), fake.async_commands)
        eng.set_night_mode(False)
        self.assertIn((0, ["af", "remove", "@night"]), fake.async_commands)
        eng.set_audio_eq_preset("normal")
        self.assertIn((0, ["af", "remove", "@eq"]), fake.async_commands)
        eng.set_audio_delay(0.4)
        self.assertEqual(fake.props_double["audio-delay"], 0.4)

        # Secondary subtitle & appearance options
        eng.set_secondary_subtitle_track(2)
        self.assertEqual(fake.props_int["secondary-sid"], 2)
        eng.set_secondary_subtitle_track(None)
        self.assertEqual(fake.props_str["secondary-sid"], "no")
        eng.set_sub_pos(85)
        self.assertEqual(fake.props_int["sub-pos"], 85)
        eng.set_sub_color("#FACC15")
        self.assertEqual(fake.props_str["sub-color"], "#FACC15")
        eng.set_sub_back_box(True)
        self.assertEqual(fake.props_str["sub-border-style"], "opaque-box")
        self.assertEqual(fake.props_str["sub-back-color"], "#80000000")
        eng.set_sub_back_box(False)
        self.assertEqual(fake.props_str["sub-border-style"], "outline-and-shadow")
        eng.set_sub_font("Noto Sans Arabic")
        self.assertEqual(fake.props_str["sub-font"], "Noto Sans Arabic")

        # Frame stepping, zoom, panscan, chapters
        eng.frame_step()
        eng.frame_back_step()
        self.assertIn(["frame-step"], fake.commands)
        self.assertIn(["frame-back-step"], fake.commands)
        eng.set_video_zoom(0.25)
        self.assertEqual(fake.props_double["video-zoom"], 0.25)
        eng.set_panscan(1.0)
        self.assertEqual(fake.props_double["panscan"], 1.0)
        eng.jump_to_chapter(2)
        self.assertEqual(fake.props_int["chapter"], 2)

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

    def test_phase1_resume_modes_chapters_zoom_audio_and_fullscreen_safety(self):
        # 1. Verify StateStore resume thresholds (>10s and < dur - 30s) & 3 modes
        state_path = os.path.join(self.tmp_dir.name, "phase1_state.json")
        store = playlist.StateStore(state_path=state_path)
        vid = os.path.join(self.tmp_dir.name, "movie.mp4")
        with open(vid, "wb") as fp:
            fp.write(b"fake")

        store.set_position(vid, 9.5, 200.0)
        self.assertEqual(store.get_resume_position(vid), 0.0)
        store.set_position(vid, 175.0, 200.0)
        self.assertEqual(store.get_resume_position(vid), 0.0)
        store.set_position(vid, 65.0, 200.0)
        self.assertAlmostEqual(store.get_resume_position(vid), 65.0, places=2)

        store.set_setting("resume_mode", "ask")
        self.assertEqual(store.get_resume_action(vid), ("ask", 0.0, 65.0))
        store.set_setting("resume_mode", "auto")
        self.assertEqual(store.get_resume_action(vid), ("auto", 65.0, 0.0))
        store.set_setting("resume_mode", "never")
        self.assertEqual(store.get_resume_action(vid), ("never", 0.0, 0.0))

        # 2. Verify app.py modular split (< 80 KB) and popovers.py + fullscreen geometry safety
        self.assertTrue(os.path.isfile(os.path.join(VIDEO_DIR, "popovers.py")))
        self.assertLess(os.path.getsize(os.path.join(VIDEO_DIR, "app.py")), 80 * 1024)
        with open(os.path.join(VIDEO_DIR, "app.py"), "r", encoding="utf-8") as fp:
            app_src = fp.read()
        fs_section = app_src.split("def toggle_fullscreen", 1)[1].split("def toggle_mini_mode", 1)[0]
        self.assertNotIn("set_default_size", fs_section)
        self.assertNotIn("maximize(", fs_section)
        self.assertNotIn("unmaximize(", fs_section)

        # 3. Verify SadeemVideoWindow resume banner, skip_intro, mini_mode, chapter marks & tracks stack
        fake = _FakeMpvLib()
        eng = mpv_engine.MpvEngine(libmpv=fake)
        store.set_setting("resume_mode", "ask")
        app = video_app.SadeemVideoApp()
        app.set_application_id("org.sadeem.Video.TestPhase1")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        app.register(None)

        win = video_app.SadeemVideoWindow(app=app, engine=eng, state_store=store)
        try:
            self.assertIsInstance(win.resume_revealer, Gtk.Revealer)
            self.assertIsInstance(win.tracks_stack, Gtk.Stack)
            self.assertEqual(win.vol_adj.get_upper(), 200.0)
            for pname in ("main", "audio_eq", "secondary_sub", "sub_style"):
                self.assertIsNotNone(win.tracks_stack.get_child_by_name(pname))
            self.assertIsNotNone(win.settings_stack.get_child_by_name("resume"))
            self.assertIsNotNone(win.settings_stack.get_child_by_name("chapters"))

            # Start file -> 'ask' mode loads at 0.0 and reveals resume banner at 65s
            win.open_paths([vid])
            win._start_playback(vid)
            self.assertTrue(win.resume_revealer.get_reveal_child())
            self.assertIn((0, ["loadfile", vid, "replace"]), fake.async_commands)
            win._on_resume_action_clicked(None)
            self.assertFalse(win.resume_revealer.get_reveal_child())
            self.assertIn((0, ["seek", "65.000", "absolute"]), fake.async_commands)

            # Skip intro +85s
            win.skip_intro(85.0)
            self.assertIn((0, ["seek", "85.000", "relative"]), fake.async_commands)

            # Chapter marks on seek_scale
            win.seek_scale.clear_marks()
            win.seek_scale.add_mark(42.0, Gtk.PositionType.TOP, None)

            # Mini player toggle on/off
            self.assertFalse(win._is_mini_mode)
            win.toggle_mini_mode()
            self.assertTrue(win._is_mini_mode)
            self.assertFalse(win.edit_btn.get_visible())
            win.toggle_mini_mode()
            self.assertFalse(win._is_mini_mode)
            self.assertTrue(win.edit_btn.get_visible())

            # Sub appearance & Night mode UI switches
            win.night_mode_switch.set_active(True)
            self.assertTrue(store.get_setting("audio_night_mode"))
            win.set_audio_eq_preset("voice")
            self.assertEqual(store.get_setting("audio_eq_preset"), "voice")
            win.set_sub_pos(82)
            self.assertEqual(fake.props_int["sub-pos"], 82)
            win.sub_back_box_switch.set_active(True)
            self.assertEqual(fake.props_str["sub-border-style"], "opaque-box")
            win.reset_video_view(reset_speed=True)
            self.assertEqual(fake.props_double["video-zoom"], 0.0)
            self.assertEqual(fake.props_double["panscan"], 0.0)
        finally:
            win.shutdown()
            win.destroy()

    def test_gl_sync_coalescing_and_tracks_popover_tabs_and_icons(self):
        import popovers

        self.assertEqual(mpv_engine.MPV_RENDER_PARAM_BLOCK_FOR_TARGET_TIME, 12)
        self.assertEqual(mpv_engine.MPV_RENDER_UPDATE_FRAME, 1)

        fake = _FakeMpvLib()
        eng = mpv_engine.MpvEngine(libmpv=fake)
        store = playlist.StateStore(state_path=os.path.join(self.tmp_dir.name, "gl_tabs_state.json"))
        app = video_app.SadeemVideoApp()
        app.set_application_id("org.sadeem.Video.TestGlTabs")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        app.register(None)

        win = video_app.SadeemVideoWindow(app=app, engine=eng, state_store=store)
        try:
            # 1. Verify render_frame passes BLOCK_FOR_TARGET_TIME=0 and calls report_swap
            self.assertEqual(eng.update_render_context(), 0)
            eng._render_ctx = 0xCAFE
            self.assertTrue(eng.render_frame(1280, 720, fbo_id=1))
            self.assertIn((12, 0), fake.render_params)
            self.assertEqual(fake.swap_calls, 1)
            self.assertEqual(eng.update_render_context(), 1)

            # 2. Verify _queue_gl_redraw coalescing & conditional queue_render
            scheduled = []
            render_calls = []
            orig_idle_add = video_app.GLib.idle_add
            orig_realized = win.gl_area.get_realized
            orig_queue_render = win.gl_area.queue_render
            try:
                video_app.GLib.idle_add = lambda fn, *a: (scheduled.append(fn), 1)[1]
                win.gl_area.get_realized = lambda: True
                win.gl_area.queue_render = lambda: render_calls.append(1)

                # Reset initial flag to test pure update-flag gating
                win._gl_needs_initial_draw = False
                fake.update_calls = 0
                fake.update_return_flags = 0

                for _ in range(5):
                    win._queue_gl_redraw()
                self.assertEqual(len(scheduled), 1)
                self.assertTrue(win._gl_redraw_pending)

                scheduled.pop(0)()
                self.assertFalse(win._gl_redraw_pending)
                self.assertEqual(fake.update_calls, 1)
                self.assertEqual(len(render_calls), 0)

                fake.update_return_flags = mpv_engine.MPV_RENDER_UPDATE_FRAME
                win._queue_gl_redraw()
                scheduled.pop(0)()
                self.assertEqual(fake.update_calls, 2)
                self.assertEqual(len(render_calls), 1)
            finally:
                video_app.GLib.idle_add = orig_idle_add
                win.gl_area.get_realized = orig_realized
                win.gl_area.queue_render = orig_queue_render
                eng._render_ctx = None

            # 3. Verify toggle_fullscreen relies directly on self.is_fullscreen()
            fs_actions = []
            orig_is_fs = win.is_fullscreen
            orig_unfs = win.unfullscreen
            orig_fs = win.fullscreen
            try:
                win._is_fullscreen = False
                win.is_fullscreen = lambda: True
                win.unfullscreen = lambda: fs_actions.append("unfs")
                win.fullscreen = lambda: fs_actions.append("fs")
                win.toggle_fullscreen()
                self.assertEqual(fs_actions, ["unfs"])
            finally:
                win.is_fullscreen = orig_is_fs
                win.unfullscreen = orig_unfs
                win.fullscreen = orig_fs

            # 4. Verify tracks_popover two-tab structure, 345px width & icon-only reset buttons
            self.assertEqual(win.tracks_stack.get_size_request()[0], 345)
            self.assertIsInstance(win.tracks_tab_audio_btn, Gtk.ToggleButton)
            self.assertIsInstance(win.tracks_tab_sub_btn, Gtk.ToggleButton)
            self.assertEqual(win.tracks_tab_stack.get_visible_child_name(), "audio_tab")

            win.tracks_tab_sub_btn.set_active(True)
            self.assertEqual(win.tracks_tab_stack.get_visible_child_name(), "sub_tab")
            win.tracks_stack.set_visible_child_name("sub_style")
            win.tracks_stack.set_visible_child_name("main")
            self.assertEqual(win.tracks_tab_stack.get_visible_child_name(), "sub_tab")

            # Collect all Gtk.Buttons inside audio_delay/sub_delay/sub_scale/sub_pos rows
            def _walk_buttons(widget):
                out = []
                if isinstance(widget, Gtk.Button):
                    out.append(widget)
                child = widget.get_first_child()
                while child is not None:
                    out.extend(_walk_buttons(child))
                    child = child.get_next_sibling()
                return out

            buttons = _walk_buttons(win.tracks_stack)
            icon_names = [b.get_icon_name() for b in buttons if b.get_icon_name()]
            self.assertGreaterEqual(icon_names.count("edit-undo-symbolic"), 4)
            text_reset_btns = [b for b in buttons if b.get_label() == video_i18n.t("reset")]
            self.assertEqual(text_reset_btns, [])

            # 5. Verify _make_directional_arrow for RTL vs LTR
            orig_dir = Gtk.Widget.get_default_direction()
            try:
                Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
                arr_enter_rtl = popovers._make_directional_arrow(entering=True)
                arr_back_rtl = popovers._make_directional_arrow(entering=False)
                self.assertEqual(arr_enter_rtl.get_icon_name(), "go-previous-symbolic")
                self.assertEqual(arr_back_rtl.get_icon_name(), "go-next-symbolic")
                self.assertEqual(arr_enter_rtl.get_direction(), Gtk.TextDirection.LTR)
                self.assertEqual(arr_back_rtl.get_direction(), Gtk.TextDirection.LTR)

                Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
                arr_enter_ltr = popovers._make_directional_arrow(entering=True)
                arr_back_ltr = popovers._make_directional_arrow(entering=False)
                self.assertEqual(arr_enter_ltr.get_icon_name(), "go-next-symbolic")
                self.assertEqual(arr_back_ltr.get_icon_name(), "go-previous-symbolic")
            finally:
                Gtk.Widget.set_default_direction(orig_dir)
        finally:
            win.shutdown()
            win.destroy()

    def test_phase2_thumbnails_mpris_recent_url_inhibit_shortcuts_and_vlc_removal(self):
        import json
        import mpris
        import thumbnails

        # 1. Thumbnails module: quantization, LRU eviction, network URL rejection, missing ffmpeg safety
        self.assertEqual(thumbnails.compute_quantized_step(120.0), 2.0)
        self.assertEqual(thumbnails.compute_quantized_step(900.0), 3.0)
        self.assertEqual(thumbnails.compute_quantized_step(2400.0), 4.0)
        self.assertEqual(thumbnails.compute_quantized_step(5400.0), 5.0)
        self.assertEqual(thumbnails.quantize_timestamp(11.3, 120.0), 12.0)
        self.assertLessEqual(thumbnails.quantize_timestamp(119.9, 120.0), 119.5)

        self.assertTrue(thumbnails.is_network_url("https://example.com/live.m3u8"))
        self.assertTrue(thumbnails.is_network_url("rtsp://cam.local/stream"))
        self.assertFalse(thumbnails.is_network_url("/tmp/movie.mp4"))
        self.assertFalse(thumbnails.is_network_url("file:///tmp/movie.mp4"))

        vid = os.path.join(self.tmp_dir.name, "sample_thumb.mp4")
        with open(vid, "wb") as fp:
            fp.write(b"fakevideo")

        ext_no_ff = thumbnails.ThumbnailExtractor(ffmpeg_bin="")
        self.assertFalse(ext_no_ff.is_available)
        self.assertFalse(ext_no_ff.request_thumbnail(vid, 10.0, 100.0, lambda *_: None))

        ext = thumbnails.ThumbnailExtractor(ffmpeg_bin="/bin/true", cache_size=2, debounce_ms=10)
        self.assertTrue(ext.is_available)
        self.assertFalse(ext.can_extract_for("https://example.com/a.mp4"))
        self.assertFalse(ext.request_thumbnail("https://example.com/a.mp4", 5.0, 100.0, lambda *_: None))
        ext._put_cached((vid, 2.0), b"PNG1")
        ext._put_cached((vid, 4.0), b"PNG2")
        ext._put_cached((vid, 6.0), b"PNG3")
        self.assertIsNone(ext.get_cached(vid, 2.0, 100.0))
        self.assertEqual(ext.get_cached(vid, 4.0, 100.0), b"PNG2")
        self.assertEqual(ext.get_cached(vid, 6.0, 100.0), b"PNG3")
        ext.shutdown()

        # 2. StateStore recent_files ordering, cap=8, existing_only filtering & clear
        state_path = os.path.join(self.tmp_dir.name, "phase2_state.json")
        store = playlist.StateStore(state_path=state_path)
        created_vids = []
        for idx in range(10):
            p = os.path.join(self.tmp_dir.name, f"v{idx}.mp4")
            with open(p, "wb") as fp:
                fp.write(b"v")
            created_vids.append(p)
            store.set_position(p, 20.0 + idx, 100.0)
            # Ensure strictly increasing timestamp ordering
            store.data["recent_files"][0]["last_watched"] = 1000.0 + idx
        store.record_recent("https://example.com/stream.m3u8", 0.0, 0.0)
        store.data["recent_files"][0]["last_watched"] = 2000.0
        store.save()

        reloaded = playlist.StateStore(state_path=state_path)
        self.assertEqual(len(reloaded.get_recent_files(existing_only=False)), 8)
        self.assertEqual(reloaded.get_recent_files(existing_only=False)[0]["path"], "https://example.com/stream.m3u8")
        os.remove(created_vids[-1])
        filtered = reloaded.get_recent_files(existing_only=True)
        self.assertNotIn(created_vids[-1], [it["path"] for it in filtered])
        reloaded.clear_recent_files()
        self.assertEqual(reloaded.get_recent_files(existing_only=False), [])

        # 3. MPRIS2 helper conversions & Metadata formatting
        self.assertEqual(mpris.seconds_to_us(12.5), 12_500_000)
        self.assertAlmostEqual(mpris.us_to_seconds(-5_000_000), -5.0, places=3)
        self.assertEqual(mpris.playback_status_str(False, False), "Stopped")
        self.assertEqual(mpris.playback_status_str(True, True), "Playing")
        self.assertEqual(mpris.playback_status_str(True, False), "Paused")
        meta = mpris.build_metadata_variants(0, "movie.mp4", created_vids[0], 95.0)
        self.assertEqual(meta["mpris:length"].get_int64(), 95_000_000)
        self.assertEqual(meta["xesam:title"].get_string(), "movie.mp4")

        # 4. Window Phase 2: recent UI, open_url, inhibit/uninhibit, pause_on_minimize, shortcuts & media info
        fake = _FakeMpvLib()
        eng = mpv_engine.MpvEngine(libmpv=fake)
        store.record_recent(created_vids[0], 30.0, 120.0)
        app = video_app.SadeemVideoApp()
        app.set_application_id("org.sadeem.Video.TestPhase2")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        app.register(None)

        inhibit_log = []
        app.inhibit = lambda win_, flags_, reason_: (inhibit_log.append(("in", int(flags_))), 77)[1]
        app.uninhibit = lambda cookie: inhibit_log.append(("out", cookie))

        win = video_app.SadeemVideoWindow(app=app, engine=eng, state_store=store)
        try:
            self.assertTrue(win.recent_section_box.get_visible())
            self.assertIsInstance(win.open_url_welcome_btn, Gtk.Button)

            # Open invalid vs valid network URL
            self.assertFalse(win.open_url("not-a-valid-url"))
            self.assertTrue(win.open_url("https://example.com/video.mp4"))
            self.assertFalse(win.welcome_box.get_visible())
            self.assertFalse(win.edit_btn.get_sensitive())
            win._start_playback("https://example.com/video.mp4")
            self.assertIn((0, ["loadfile", "https://example.com/video.mp4", "replace"]), fake.async_commands)

            # Check inhibit/uninhibit transitions
            self.assertTrue(win.is_playing)
            self.assertIn(("in", int(Gtk.ApplicationInhibitFlags.IDLE)), inhibit_log)

            # Pause on minimize
            self.assertTrue(win._pause_on_minimize)
            win._handle_window_minimized(True)
            self.assertFalse(win.is_playing)
            self.assertTrue(win._paused_by_minimize)
            self.assertIn(("out", 77), inhibit_log)
            win._handle_window_minimized(False)
            self.assertFalse(win._paused_by_minimize)

            # Play local file, test MPRIS properties, shortcuts dialog & media info page
            win.play_path(created_vids[0])
            win._start_playback(created_vids[0])
            props = win.mpris_service.get_player_properties()
            self.assertEqual(props["PlaybackStatus"].get_string(), "Playing")
            self.assertEqual(props["Metadata"].unpack()["xesam:title"], os.path.basename(created_vids[0]))

            sc_page = win.build_shortcuts_page()
            self.assertIsInstance(sc_page, Adw.ToolbarView)
            info_page = win.build_media_info_page()
            self.assertIsInstance(info_page, Adw.ToolbarView)

            # Verify MenuButton double-ring fix & stream URL hint/ytdl setting
            self.assertFalse(win.tracks_btn.get_has_frame())
            self.assertFalse(win.settings_btn.get_has_frame())
            css = video_app.SADEEM_VIDEO_PLAYER_CSS
            self.assertIn("menubutton.sadeem-hud-btn > button", css)
            self.assertIn("menubutton.sadeem-hud-btn > button:checked", css)
            self.assertIn("menubutton.sadeem-hud-btn,", css)
            mb_rule = css.split("menubutton.sadeem-hud-btn,", 1)[1].split("}", 1)[0]
            self.assertIn("padding: 0;", mb_rule)
            self.assertIn("min-width: 0;", mb_rule)
            self.assertIn("background-color: transparent;", mb_rule)
            self.assertEqual(mpv_engine.MpvEngine.DEFAULT_OPTIONS.get("ytdl"), "no")
            for lang in video_i18n.SUPPORTED_LANGUAGES:
                self.assertIn("m3u8", video_i18n.STRINGS[lang]["open_url_hint"])
                self.assertIn("rtsp", video_i18n.STRINGS[lang]["open_url_hint"])

            win.stop_playback()
            self.assertTrue(win.welcome_box.get_visible())
            win._on_clear_recent_clicked()
            self.assertFalse(win.recent_section_box.get_visible())
        finally:
            win.shutdown()
            win.destroy()

        # 5. Clean removal of VLC from sadeem-welcome, default-flatpaks, setup script, recipe & mimeapps
        for rel in (
            "files/system/usr/bin/sadeem-welcome",
            "files/system/usr/bin/sadeem-flatpak-setup",
            "files/system/usr/share/sadeem/default-flatpaks.json",
            "recipes/recipe.yml",
            "files/system/etc/xdg/mimeapps.list",
            "files/system/usr/share/applications/mimeapps.list",
        ):
            with open(os.path.join(REPO_ROOT, rel), "r", encoding="utf-8") as fp:
                txt = fp.read()
            self.assertNotIn("vlc", txt.lower(), f"Found residual VLC reference in {rel}")
            self.assertNotIn("videolan", txt.lower(), f"Found residual VideoLAN reference in {rel}")

        with open(os.path.join(REPO_ROOT, "files/system/usr/share/sadeem/default-flatpaks.json"), "r", encoding="utf-8") as fp:
            parsed_flatpaks = json.load(fp)
        self.assertTrue(isinstance(parsed_flatpaks, list) and len(parsed_flatpaks) >= 8)

    def test_wayland_rtl_outer_window_direction_isolation(self):
        orig_dir = Gtk.Widget.get_default_direction()
        try:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
            fake = _FakeMpvLib()
            eng = mpv_engine.MpvEngine(libmpv=fake)
            store = playlist.StateStore(state_path=os.path.join(self.tmp_dir.name, "rtl_iso_state.json"))
            app = video_app.SadeemVideoApp()
            app.set_application_id("org.sadeem.Video.TestRtlIso")
            app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
            app.register(None)

            win = video_app.SadeemVideoWindow(app=app, engine=eng, state_store=store)
            try:
                self.assertEqual(win.get_direction(), Gtk.TextDirection.LTR)
                self.assertEqual(win._ui_direction, Gtk.TextDirection.RTL)
                self.assertEqual(Gtk.Widget.get_default_direction(), Gtk.TextDirection.RTL)
                self.assertEqual(win.toast_overlay.get_direction(), Gtk.TextDirection.RTL)
                self.assertEqual(win.split_view.get_direction(), Gtk.TextDirection.RTL)
                self.assertEqual(win.progress_row.get_direction(), Gtk.TextDirection.LTR)

                for dlg in (
                    win.show_media_info_dialog(),
                    win.show_shortcuts_dialog(),
                    win.prompt_open_url(),
                ):
                    self.assertIsNotNone(dlg)
                    self.assertEqual(dlg.get_direction(), Gtk.TextDirection.RTL)
                    if hasattr(dlg, "force_close"):
                        dlg.force_close()
                    elif hasattr(dlg, "close"):
                        dlg.close()
            finally:
                win.shutdown()
                win.destroy()
        finally:
            Gtk.Widget.set_default_direction(orig_dir)


if __name__ == "__main__":
    unittest.main()
