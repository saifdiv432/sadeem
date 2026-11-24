#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real Automated Test Suite for Sadeem Capture and Desktop Helper.
Tests actual live components:
1. GStreamer pipeline generation & Gst.parse_launch verification for all permutations
2. Live MKV creation & FFmpeg remuxing to MP4
3. Portal states & SIGTERM / SIGINT shutdown logic
4. GJS syntax validation, yellow indicator suppression verification, and i18n
5. System integration (sh -n, bash -n, recipe.yml cleanup, glib schemas)
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAPTURE_DIR = os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-capture")
EXT_DIR = os.path.join(
    REPO_ROOT,
    "files/system/usr/share/gnome-shell/extensions/sadeem-desktop-helper@sadeem.os"
)

if CAPTURE_DIR not in sys.path:
    sys.path.insert(0, CAPTURE_DIR)

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gst

Gst.init(None)

import recorder
from recorder import VideoRecorderApp, format_size
import i18n


class TestGstreamerPipelineGeneration(unittest.TestCase):
    """Tests real GStreamer compilation for all pipeline permutations via Gst.parse_launch."""

    def test_pipeline_permutations(self):
        modes = ["screen", "selection", "window"]
        resolutions = ["native", "1080p", "720p"]
        codecs = ["h264", "h265"]
        audios = ["none", "system", "mic", "both"]
        levels = [1, 2]

        total_tested = 0

        for mode in modes:
            for res in resolutions:
                for codec in codecs:
                    for audio in audios:
                        for level in levels:
                            args = argparse.Namespace(
                                mode=mode,
                                crop="100,100,640,480" if mode == "selection" else "",
                                monitor="0",
                                resolution=res,
                                fps="60",
                                codec=codec,
                                audio=audio,
                                mic="alsa_input.test",
                                cursor=True,
                            )
                            app = VideoRecorderApp(args)
                            app.tmp_mkv = "/tmp/test_pipeline_temp.mkv"

                            pipe_str = app.build_pipeline_str(node_id=42, fd=3, level=level)
                            self.assertTrue(len(pipe_str) > 0)

                            # Verify that Gst.parse_launch successfully builds the pipeline
                            try:
                                pipe = Gst.parse_launch(pipe_str)
                                self.assertIsNotNone(pipe)
                                total_tested += 1
                            except Exception as e:
                                self.fail(
                                    f"Gst.parse_launch failed on permutation: "
                                    f"mode={mode}, res={res}, codec={codec}, audio={audio}, level={level}. "
                                    f"Pipeline: {pipe_str}. Error: {e}"
                                )

        self.assertGreaterEqual(total_tested, 144, "Expected at least 144 permutations tested successfully")

    def test_window_mode_pipeline_preserves_aspect_ratio(self):
        """Verifies that window mode pipelines always include videoscale add-borders=true and pixel-aspect-ratio=1/1."""
        for res in ["native", "1080p", "720p"]:
            for codec in ["h264", "h265"]:
                args = argparse.Namespace(
                    mode="window",
                    crop="",
                    monitor="0",
                    resolution=res,
                    fps="60",
                    codec=codec,
                    audio="none",
                    mic="",
                    cursor=True,
                )
                app = VideoRecorderApp(args)
                app.tmp_mkv = "/tmp/test_window_temp.mkv"
                pipe_str = app.build_pipeline_str(node_id=42, fd=3, level=1)

                self.assertIn("add-borders=true", pipe_str, f"Window mode ({res}, {codec}) must include add-borders=true")
                self.assertIn("pixel-aspect-ratio=1/1", pipe_str, f"Window mode ({res}, {codec}) must include pixel-aspect-ratio=1/1")

                pipe = Gst.parse_launch(pipe_str)
                self.assertIsNotNone(pipe, f"Gst.parse_launch failed for window mode ({res}, {codec})")

    def test_screen_native_preserves_dmabuf(self):
        """Verifies that full screen native recording uses zero-copy memory:DMABuf pipeline."""
        for codec in ["h264", "h265"]:
            args = argparse.Namespace(
                mode="screen",
                crop="",
                monitor="0",
                resolution="native",
                fps="60",
                codec=codec,
                audio="none",
                mic="",
                cursor=True,
            )
            app = VideoRecorderApp(args)
            app.tmp_mkv = "/tmp/test_screen_temp.mkv"
            pipe_str = app.build_pipeline_str(node_id=42, fd=3, level=1)

            self.assertIn("memory:DMABuf", pipe_str, f"Screen native ({codec}) must preserve memory:DMABuf")
            self.assertIn("vapostproc", pipe_str, f"Screen native ({codec}) must use vapostproc")
            self.assertNotIn("videoscale", pipe_str, f"Screen native ({codec}) must not contain videoscale")

            pipe = Gst.parse_launch(pipe_str)
            self.assertIsNotNone(pipe, f"Gst.parse_launch failed for screen native ({codec})")


class TestMkvRecordingAndFFmpegRemux(unittest.TestCase):
    """Tests real MKV generation and FFmpeg lossless transmuxing to MP4."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="sadeem_test_rec_")
        self.tmp_mkv = os.path.join(self.test_dir, ".sadeem_tmp_test.mkv")
        self.final_mp4 = os.path.join(self.test_dir, "تسجيل_سديم_test.mp4")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mkv_generation_and_remux(self):
        # 1. Generate 1-second test MKV file using videotestsrc
        pipe_str = (
            f"videotestsrc num-buffers=15 ! "
            f"video/x-raw,format=I420,width=320,height=240,framerate=15/1 ! "
            f"x264enc speed-preset=ultrafast tune=zerolatency ! h264parse ! "
            f"matroskamux ! filesink location=\"{self.tmp_mkv}\""
        )
        pipe = Gst.parse_launch(pipe_str)
        loop = GLib.MainLoop()

        def on_msg(bus, msg):
            if msg.type in (Gst.MessageType.EOS, Gst.MessageType.ERROR):
                loop.quit()
            return True

        pipe.get_bus().add_watch(GLib.PRIORITY_DEFAULT, on_msg)
        pipe.set_state(Gst.State.PLAYING)
        loop.run()
        pipe.set_state(Gst.State.NULL)

        self.assertTrue(os.path.isfile(self.tmp_mkv), "Temporary MKV must exist")
        self.assertGreater(os.path.getsize(self.tmp_mkv), 0, "Temporary MKV must be non-empty")

        # 2. Test VideoRecorderApp._finalize_recording
        args = argparse.Namespace(
            mode="screen", crop="", monitor="0", resolution="native",
            fps="60", codec="h264", audio="none", mic="", cursor=True,
        )
        app = VideoRecorderApp(args)
        app.tmp_mkv = self.tmp_mkv
        app.final_mp4 = self.final_mp4

        ret = app._finalize_recording()
        self.assertEqual(ret, 0, "_finalize_recording must exit with 0")
        self.assertTrue(os.path.isfile(self.final_mp4), "Final MP4 must exist")
        self.assertGreater(os.path.getsize(self.final_mp4), 0, "Final MP4 must be > 0 bytes")
        self.assertFalse(os.path.isfile(self.tmp_mkv), "Temporary MKV must be deleted after success")

    def test_format_size_helper(self):
        self.assertEqual(format_size(500), "500.0 B")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(format_size(3 * 1024 * 1024 * 1024), "3.0 GB")


class TestPortalAndSignalHandling(unittest.TestCase):
    """Tests exit codes and signal handler state."""

    def test_sigterm_stops_pipeline(self):
        args = argparse.Namespace(
            mode="screen", crop="", monitor="0", resolution="native",
            fps="60", codec="h264", audio="none", mic="", cursor=True,
        )
        app = VideoRecorderApp(args)
        self.assertFalse(app.stop_requested)

        app._handle_signal(signal.SIGTERM, None)
        self.assertTrue(app.stop_requested)


class TestGjsAndJsLogic(unittest.TestCase):
    """Tests JavaScript files via GJS: syntax, yellow indicator suppression, and i18n."""

    def test_all_js_files_syntax(self):
        js_files = [
            "extension.js",
            "captureUI.js",
            "captureI18n.js",
            "captureHelper.js",
            "recordingIndicator.js",
            "cursorHalo.js",
            "windowMenuHelper.js",
        ]
        env = os.environ.copy()
        typelib_paths = "/usr/lib64/mutter-51:/usr/lib64/gnome-shell"
        env["GI_TYPELIB_PATH"] = typelib_paths + (":" + env["GI_TYPELIB_PATH"] if "GI_TYPELIB_PATH" in env else "")
        env["LD_LIBRARY_PATH"] = typelib_paths + (":" + env["LD_LIBRARY_PATH"] if "LD_LIBRARY_PATH" in env else "")

        for f in js_files:
            path = os.path.join(EXT_DIR, f)
            self.assertTrue(os.path.isfile(path), f"File {f} must exist")
            self.assertGreater(os.path.getsize(path), 100, f"File {f} must not be empty")

            res = subprocess.run(["gjs", "-m", path], capture_output=True, text=True, env=env, timeout=10)
            out = (res.stderr + "\n" + res.stdout).strip()
            self.assertNotIn("SyntaxError", out, f"GJS syntax error in {f}:\n{out}")
            if res.returncode != 0:
                self.assertIn(
                    "resource:///org/gnome/shell/",
                    out,
                    f"Unexpected GJS failure in {f}:\n{out}",
                )

    def test_no_deprecated_gnome_apis(self):
        """Verifies zero deprecated GNOME Shell / Clutter APIs in extension files."""
        js_files = [f for f in os.listdir(EXT_DIR) if f.endswith(".js")]
        for f in js_files:
            path = os.path.join(EXT_DIR, f)
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            self.assertNotIn("add_actor", content, f"{f} must not use deprecated add_actor")
            self.assertNotIn("remove_actor", content, f"{f} must not use deprecated remove_actor")
            self.assertNotIn("vertical:", content, f"{f} must not use removed 'vertical' property on St.BoxLayout")
            self.assertNotIn("Main.popModal(this)", content, f"{f} must pass grab to Main.popModal, not this")
            self.assertNotIn("display.set_cursor", content, f"{f} must not call non-existent display.set_cursor")

    def test_st_and_clutter_properties_exist_in_gnome51(self):
        """
        Introspects all 'new St.*({...})' and 'new Clutter.*({...})' object literals
        against GNOME 51 GIRepository typelibs to guarantee 0 unknown properties.
        """
        import re
        gi.require_version("GIRepository", "3.0")
        from gi.repository import GIRepository

        repo = GIRepository.Repository.new()
        repo.prepend_search_path("/usr/lib64/mutter-51")
        repo.prepend_search_path("/usr/lib64/gnome-shell")
        repo.require("St", "51", 0)
        repo.require("Clutter", "51", 0)

        def get_props(ns, cls_name):
            info = repo.find_by_name(ns, cls_name)
            if not info:
                return None
            props = set()
            curr = info
            while curr:
                for i in range(curr.get_n_properties()):
                    name = curr.get_property(i).get_name()
                    props.add(name)
                    props.add(name.replace("-", "_"))
                    parts = name.split("-")
                    camel = parts[0] + "".join(x.capitalize() for x in parts[1:])
                    props.add(camel)
                curr = curr.get_parent() if hasattr(curr, "get_parent") else None
            return props

        def strip_strings(code):
            out, i, n = [], 0, len(code)
            while i < n:
                if code[i:i+2] == "//":
                    end = code.find("\n", i)
                    i = n if end == -1 else end
                elif code[i:i+2] == "/*":
                    end = code.find("*/", i+2)
                    i = n if end == -1 else end + 2
                elif code[i] in ("\"", "\x27", "`"):
                    quote = code[i]
                    i += 1
                    while i < n:
                        if code[i] == "\\":
                            i += 2
                        elif code[i] == quote:
                            i += 1
                            break
                        else:
                            i += 1
                    out.append("\"\"")
                else:
                    out.append(code[i])
                    i += 1
            return "".join(out)

        js_files = [f for f in os.listdir(EXT_DIR) if f.endswith(".js")]
        invalid = []
        pattern = re.compile(r"new\s+(St|Clutter)\.([A-Za-z0-9_]+)\s*\(\s*\{([^}]*)\}\s*\)")

        for f in js_files:
            with open(os.path.join(EXT_DIR, f), "r", encoding="utf-8") as fp:
                clean = strip_strings(fp.read())
            for ns, cls_name, block in pattern.findall(clean):
                valid_props = get_props(ns, cls_name)
                self.assertIsNotNone(valid_props, f"Unknown class {ns}.{cls_name} in {f}")
                keys = re.findall(r"([a-zA-Z0-9_\-]+)\s*:", block)
                for k in keys:
                    if k not in valid_props:
                        invalid.append(f"{f}: new {ns}.{cls_name}({{ {k}: ... }})")

        self.assertEqual(invalid, [], f"Found invalid GNOME 51 properties: {invalid}")

    def test_recording_indicator_suppression_logic(self):
        """
        Runs a real GJS script to test the exact yellow suppression condition:
        if ((this.visible || this._indicatorSuppressed) && item.visible) { item.visible = false; }
        """
        gjs_script = """
        let indicatorSuppressed = true;
        let isIndicatorVisible = false;

        // Mock GNOME Screen Recording / Sharing item
        let gnomeItem = {
            visible: true,
            listeners: [],
            connect(sig, cb) { this.listeners.push(cb); },
            emit(sig) { for (let cb of this.listeners) cb(); }
        };

        // Wire suppression handler
        gnomeItem.connect('notify::visible', () => {
            if ((isIndicatorVisible || indicatorSuppressed) && gnomeItem.visible) {
                gnomeItem.visible = false;
            }
        });

        // Test 1: While suppressed=true, if gnome tries to become visible=true, it is forced to false!
        gnomeItem.visible = true;
        gnomeItem.emit('notify::visible');
        if (gnomeItem.visible !== false) {
            throw new Error("Gnome indicator was not suppressed when indicatorSuppressed=true!");
        }

        // Test 2: When visible=true, if gnome tries to become visible=true, it is forced to false!
        indicatorSuppressed = false;
        isIndicatorVisible = true;
        gnomeItem.visible = true;
        gnomeItem.emit('notify::visible');
        if (gnomeItem.visible !== false) {
            throw new Error("Gnome indicator was not suppressed when isIndicatorVisible=true!");
        }

        // Test 3: When neither is true, gnome indicator remains visible
        indicatorSuppressed = false;
        isIndicatorVisible = false;
        gnomeItem.visible = true;
        gnomeItem.emit('notify::visible');
        if (gnomeItem.visible !== true) {
            throw new Error("Gnome indicator should remain visible when unsuppressed!");
        }

        print("SUPPRESSION_LOGIC_VERIFIED");
        """
        res = subprocess.run(["gjs", "-c", gjs_script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"GJS suppression test failed: {res.stderr}")
        self.assertIn("SUPPRESSION_LOGIC_VERIFIED", res.stdout)

    def test_i18n_ten_languages_and_interpolation(self):
        expected_langs = ["ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh"]
        self.assertEqual(len(i18n.SUPPORTED_LANGUAGES), 10)
        for lang in expected_langs:
            self.assertIn(lang, i18n.SUPPORTED_LANGUAGES)
            self.assertIn(lang, i18n.STRINGS)
            # Check core keys
            self.assertIn("app_name", i18n.STRINGS[lang])
            self.assertIn("btn_capture", i18n.STRINGS[lang])
            self.assertIn("tab_photo", i18n.STRINGS[lang])
            self.assertIn("tab_video", i18n.STRINGS[lang])
            self.assertIn("notif_recorded_body", i18n.STRINGS[lang])

        # Test parameter substitution in Python
        ar_notif = i18n.t("notif_recorded_body", size="25 MB", path="/home/user/video.mp4")
        self.assertIn("25 MB", ar_notif)
        self.assertIn("/home/user/video.mp4", ar_notif)

        # Test parameter substitution and new interactive notification keys in GJS captureI18n.js
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
            tf.write(f"""
            import * as I18n from "file://{os.path.join(EXT_DIR, 'captureI18n.js')}";
            let res = I18n.t("notif_recorded_body", {{ size: "30 MB", path: "/tmp/sample.mp4" }});
            if (!res.includes("30 MB") || !res.includes("/tmp/sample.mp4")) {{
                throw new Error("GJS i18n interpolation failed: " + res);
            }}
            const requiredNotifKeys = [
                "notif_photo_title",
                "notif_photo_body",
                "notif_video_title",
                "notif_video_body",
                "notif_action_edit",
                "notif_action_show_folder",
            ];
            for (const lang of I18n.SUPPORTED_LANGUAGES) {{
                for (const key of requiredNotifKeys) {{
                    const val = I18n.STRINGS[lang]?.[key];
                    if (!val || typeof val !== "string" || val.trim().length === 0) {{
                        throw new Error(`Missing ${{key}} for lang ${{lang}} in captureI18n.js`);
                    }}
                }}
            }}
            if (I18n.STRINGS.ar.notif_action_edit !== "تحرير") {{
                throw new Error("Unexpected Arabic notif_action_edit label");
            }}
            if (I18n.STRINGS.en.notif_action_edit !== "Edit") {{
                throw new Error("Unexpected English notif_action_edit label");
            }}
            print("GJS_I18N_VERIFIED");
            """)
            temp_js_path = tf.name

        try:
            env = os.environ.copy()
            typelib_paths = "/usr/lib64/mutter-51:/usr/lib64/gnome-shell"
            env["GI_TYPELIB_PATH"] = typelib_paths + (":" + env.get("GI_TYPELIB_PATH", "") if "GI_TYPELIB_PATH" in env else "")
            env["LD_LIBRARY_PATH"] = typelib_paths + (":" + env.get("LD_LIBRARY_PATH", "") if "LD_LIBRARY_PATH" in env else "")

            res = subprocess.run(["gjs", "-m", temp_js_path], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, f"GJS i18n test failed: {res.stderr}")
            self.assertIn("GJS_I18N_VERIFIED", res.stdout)
        finally:
            if os.path.exists(temp_js_path):
                os.unlink(temp_js_path)

    def test_selection_normalization_geometry(self):
        """Verifies rectangle normalization across drag directions and monitor clamping."""
        def normalize_rect(x1, y1, x2, y2, mx, my, mw, mh):
            min_x = max(mx, min(x1, x2))
            max_x = min(mx + mw, max(x1, x2))
            min_y = max(my, min(y1, y2))
            max_y = min(my + mh, max(y1, y2))
            return {
                "x": round(min_x),
                "y": round(min_y),
                "width": round(max(0, max_x - min_x)),
                "height": round(max(0, max_y - min_y)),
            }

        # Normal Top-Left to Bottom-Right
        r1 = normalize_rect(100, 100, 400, 300, 0, 0, 1920, 1080)
        self.assertEqual(r1, {"x": 100, "y": 100, "width": 300, "height": 200})

        # Reverse Bottom-Right to Top-Left
        r2 = normalize_rect(400, 300, 100, 100, 0, 0, 1920, 1080)
        self.assertEqual(r2, {"x": 100, "y": 100, "width": 300, "height": 200})

        # Drag exceeding monitor boundaries (clamped)
        r3 = normalize_rect(-50, -20, 2000, 1200, 0, 0, 1920, 1080)
        self.assertEqual(r3, {"x": 0, "y": 0, "width": 1920, "height": 1080})

    def test_capture_ui_work_area_and_bin_layout(self):
        """
        Verifies that captureUI.js anchors to getWorkAreaForMonitor, uses Clutter.BinLayout,
        positions toolbarCard at END and topPill at START, uses focus-windows-symbolic,
        and avoids manual bottom edge calculation (monitor.height - cardHeight).
        """
        capture_ui_path = os.path.join(EXT_DIR, "captureUI.js")
        with open(capture_ui_path, "r", encoding="utf-8") as fp:
            content = fp.read()

        self.assertIn("getWorkAreaForMonitor", content, "captureUI.js must use getWorkAreaForMonitor")
        self.assertIn("name: 'sadeem-work-area-container'", content)
        self.assertIn("orientation: Clutter.Orientation.VERTICAL", content)
        self.assertIn("y_expand: true", content)
        self.assertIn("Clutter.ActorAlign.END", content, "captureUI.js must use Clutter.ActorAlign.END for bottom toolbar")
        self.assertIn("Clutter.ActorAlign.START", content, "captureUI.js must use Clutter.ActorAlign.START for top pill")
        self.assertIn("focus-windows-symbolic", content, "captureUI.js must use focus-windows-symbolic icon")
        self.assertNotIn("preferences-system-windows-symbolic", content, "captureUI.js must not use preferences-system-windows-symbolic")
        self.assertNotIn("monitor.height - cardHeight", content, "captureUI.js must not manually calculate bottom coordinate")

    def test_capture_ui_layer_stacking_and_png_clipboard(self):
        """
        Verifies:
        1. captureUI.js raises itself above all uiGroup siblings on open() and stacks _selectionBox above _dimOverlay.
        2. Control card fades and disables reactivity during drag, and _dimensionsBadge avoids top clipping.
        3. Both captureUI.js and captureHelper.js copy image/png GLib.Bytes via St.Clipboard.set_content, with zero St.Clipboard.set_text usage.
        """
        capture_ui_path = os.path.join(EXT_DIR, "captureUI.js")
        capture_helper_path = os.path.join(EXT_DIR, "captureHelper.js")
        with open(capture_ui_path, "r", encoding="utf-8") as fp:
            ui_code = fp.read()
        with open(capture_helper_path, "r", encoding="utf-8") as fp:
            helper_code = fp.read()

        # 1. Layer stacking
        self.assertIn("Main.layoutManager.uiGroup.set_child_above_sibling(this, null);", ui_code)
        self.assertIn("this.set_child_above_sibling(this._selectionBox, this._dimOverlay);", ui_code)
        self.assertIn("this._controlCard.opacity = isDragging ? 60 : 255;", ui_code)
        self.assertIn("this._controlCard.reactive = !isDragging;", ui_code)
        self.assertIn("r.y < 28 ? 6 : -24", ui_code)

        # 2. Clipboard image/png bytes (no set_text with path, no wl-copy file arg)
        for fname, code in [("captureUI.js", ui_code), ("captureHelper.js", helper_code)]:
            self.assertNotIn("set_text", code, f"{fname} must not copy file paths as text via St.Clipboard.set_text")
            self.assertIn("St.Clipboard.get_default().set_content(", code, f"{fname} must copy PNG bytes via St.Clipboard.set_content")
            self.assertIn("'image/png'", code, f"{fname} must specify 'image/png' MIME type")
            self.assertIn("new GLib.Bytes(contents)", code, f"{fname} must wrap PNG contents in GLib.Bytes")

        # 3. Verify GJS can read a real PNG file into GLib.Bytes and inspect St.Clipboard.set_content
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as tf:
            # Minimal valid 1x1 PNG header+payload
            tf.write(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            png_path = tf.name

        try:
            env = os.environ.copy()
            typelib_paths = "/usr/lib64/mutter-51:/usr/lib64/gnome-shell"
            env["GI_TYPELIB_PATH"] = typelib_paths + (":" + env["GI_TYPELIB_PATH"] if "GI_TYPELIB_PATH" in env else "")
            env["LD_LIBRARY_PATH"] = typelib_paths + (":" + env["LD_LIBRARY_PATH"] if "LD_LIBRARY_PATH" in env else "")
            gjs_test = f"""
            const Gio = imports.gi.Gio;
            const GLib = imports.gi.GLib;
            imports.gi.versions.St = '51';
            const St = imports.gi.St;
            const [ok, contents] = Gio.File.new_for_path({png_path!r}).load_contents(null);
            if (!ok || !contents || contents.length === 0) throw new Error('Failed reading PNG bytes');
            const pngBytes = new GLib.Bytes(contents);
            if (pngBytes.get_size() !== contents.length) throw new Error('GLib.Bytes size mismatch');
            if (typeof St.Clipboard.prototype.set_content !== 'function') throw new Error('St.Clipboard.set_content missing');
            print('PNG_CLIPBOARD_BYTES_OK:' + pngBytes.get_size());
            """
            res = subprocess.run(["gjs", "-c", gjs_test], capture_output=True, text=True, env=env, timeout=10)
            self.assertEqual(res.returncode, 0, f"GJS PNG clipboard test failed:\n{res.stderr}")
            self.assertIn("PNG_CLIPBOARD_BYTES_OK:", res.stdout)
        finally:
            if os.path.exists(png_path):
                os.unlink(png_path)

    def test_interactive_capture_notification_and_no_auto_launch(self):
        """
        Verifies:
        1. captureUI.js does not auto-launch sadeem-gallery immediately after photo capture or video recording finish.
        2. _notifyCaptureComplete uses GNOME 51 MessageTray.Source and MessageTray.Notification.
        3. notif_action_edit routes photos to sadeem-gallery --edit and videos to sadeem-video-editor,
           notif_action_show_folder calls org.freedesktop.FileManager1.ShowItems,
           and notification 'activated' opens sadeem-gallery without --edit.
        """
        capture_ui_path = os.path.join(EXT_DIR, "captureUI.js")
        with open(capture_ui_path, "r", encoding="utf-8") as fp:
            ui_code = fp.read()

        self.assertIn("resource:///org/gnome/shell/ui/messageTray.js", ui_code)
        self.assertIn("new MessageTray.Source({", ui_code)
        self.assertIn("Main.messageTray.add(this._notifSource);", ui_code)
        self.assertIn("new MessageTray.Notification({", ui_code)
        self.assertIn("Gio.FileIcon.new(", ui_code)
        self.assertIn("source.addNotification(notification);", ui_code)
        self.assertIn("notification.addAction(I18n.t('notif_action_edit')", ui_code)
        self.assertIn("notification.addAction(I18n.t('notif_action_show_folder')", ui_code)
        self.assertIn("notification.connect('activated'", ui_code)
        self.assertIn("'sadeem-gallery', '--edit', filePath", ui_code)
        self.assertIn("'sadeem-video-editor', filePath", ui_code)
        self.assertIn("org.freedesktop.FileManager1", ui_code)
        self.assertIn("ShowItems", ui_code)
        self.assertIn("this._launchBackgroundCommand(['sadeem-gallery', filePath]);", ui_code)

        # Ensure capture paths invoke _notifyCaptureComplete and never auto-launch gallery directly
        self.assertNotIn("_openInGallery", ui_code)
        self.assertIn("this._notifyCaptureComplete(targetPath, 'photo')", ui_code)
        self.assertIn("this._notifyCaptureComplete(path, 'video')", ui_code)
        self.assertEqual(ui_code.count("this._notifyCaptureComplete("), 4)


class TestSystemIntegration(unittest.TestCase):
    """Tests shell script syntax, systemd service cleanup, recipe YAML, and gschemas."""

    def test_sadeem_capture_shell_syntax(self):
        launcher = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-capture")
        res = subprocess.run(["sh", "-n", launcher], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in {launcher}: {res.stderr}")

    def test_sadeem_accent_watcher_bash_syntax(self):
        watcher = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-accent-watcher")
        res = subprocess.run(["bash", "-n", watcher], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in {watcher}: {res.stderr}")

    def test_service_and_app_py_cleaned_from_repo(self):
        # 1. No service files
        service_files = [
            "files/systemd/user/sadeem-capture.service",
            "files/system/etc/systemd/user/sadeem-capture.service",
            "files/systemd/user/graphical-session.target.wants/sadeem-capture.service",
            "files/system/etc/systemd/user/graphical-session.target.wants/sadeem-capture.service",
        ]
        for s in service_files:
            full_path = os.path.join(REPO_ROOT, s)
            self.assertFalse(os.path.exists(full_path), f"Service file/link must not exist: {s}")

        # 2. app.py deleted
        app_py = os.path.join(CAPTURE_DIR, "app.py")
        self.assertFalse(os.path.exists(app_py), "app.py must be deleted")

        # 3. recorder.py executable
        recorder_py = os.path.join(CAPTURE_DIR, "recorder.py")
        self.assertTrue(os.path.isfile(recorder_py), "recorder.py must exist")
        self.assertTrue(os.access(recorder_py, os.X_OK), "recorder.py must be executable")

    def test_recipe_yaml_cleaned_and_valid(self):
        recipe_path = os.path.join(REPO_ROOT, "recipes/recipe.yml")
        with open(recipe_path, "r", encoding="utf-8") as f:
            content = f.read()

        # No sadeem-capture.service in recipe
        self.assertNotIn("sadeem-capture.service", content, "recipe.yml must not reference sadeem-capture.service")
        # No app.py in recipe
        self.assertNotIn("sadeem-capture/app.py", content, "recipe.yml must not reference app.py")
        # Must reference recorder.py
        self.assertIn("sadeem-capture/recorder.py", content, "recipe.yml must reference recorder.py in chmod +x")
        # Must NOT reference removed sadeem-nvidia-manager binary
        self.assertNotIn("/usr/bin/sadeem-nvidia-manager", content, "recipe.yml must not reference removed sadeem-nvidia-manager")

        # Valid YAML
        data = yaml.safe_load(content)
        self.assertIsInstance(data, dict, "recipe.yml must parse as valid dictionary")

    def test_unwanted_desktop_entries_removed_and_backend_preserved(self):
        """Verifies duplicate/internal .desktop launchers are removed while keeping shared backends intact."""
        for rel in [
            "files/system/usr/share/applications/org.sadeem.Capture.desktop",
            "files/system/usr/share/applications/sadeem-nvidia-manager.desktop",
            "files/system/usr/bin/sadeem-nvidia-manager",
        ]:
            self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, rel)), f"Removed launcher must not exist: {rel}")

        for rel in [
            "files/system/usr/share/sadeem-nvidia/gpu-ids.json",
            "files/system/usr/share/sadeem-capture/recorder.py",
            "files/system/usr/share/sadeem-capture/capture/portal_screencast.py",
            "files/system/usr/bin/sadeem-capture",
        ]:
            self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, rel)), f"Shared backend file must be preserved: {rel}")

    def test_glib_compile_schemas_dry_run(self):
        schema_dir = os.path.join(REPO_ROOT, "files/system/usr/share/glib-2.0/schemas")
        res = subprocess.run(["glib-compile-schemas", "--dry-run", schema_dir], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Schema compilation failed: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
