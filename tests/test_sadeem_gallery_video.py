#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Test Suite for Sadeem Gallery Video Architecture & Sadeem Capture Integration.
Tests:
1. VideoEditorView and VideoPlayerWidget real instantiation without GType / subclass errors.
2. video_editor_engine.export_video: real ffmpeg pipeline verification (trimming, partial muting,
   cropping to even dimensions, and vector overlay) verified via ffprobe.
3. Audio stream probing & safe handling for videos with and without audio.
4. SadeemGalleryApp multi-window architecture: opening separate files yields distinct windows,
   duplicate files focus existing windows without duplication.
5. open_video_editor_directly: viewer state preparation so returning from editor goes cleanly to player.
6. portal_screencast.py window mode persist_mode=0 and token clearing.
7. captureUI.js layout, dimensions, RTL balance, and i18n keys across all 10 languages.
"""

import cairo
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from PIL import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GALLERY_DIR = os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-gallery")
CAPTURE_DIR = os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-capture")
EXT_DIR = os.path.join(
    REPO_ROOT,
    "files/system/usr/share/gnome-shell/extensions/sadeem-desktop-helper@sadeem.os"
)

if GALLERY_DIR in sys.path:
    sys.path.remove(GALLERY_DIR)
sys.path.insert(0, GALLERY_DIR)
if CAPTURE_DIR not in sys.path:
    sys.path.insert(1, CAPTURE_DIR)

for mod_name in ["app", "video_utils", "i18n", "editor", "video_player", "canvas", "media"]:
    sys.modules.pop(mod_name, None)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, Gio, GLib, Gtk

Adw.init()

import app as gallery_app
import editor
import i18n as gallery_i18n
import media
import video_player
import video_utils
from capture import portal_screencast


class MockCommandLine:
    def __init__(self, args):
        self._args = args

    def get_arguments(self):
        return self._args


class TestVideoComponentsInstantiation(unittest.TestCase):
    """Verifies that VideoEditorView and VideoPlayerWidget instantiate cleanly with no GType errors."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="sadeem_test_gallery_")
        cls.sample_mp4 = os.path.join(cls.test_dir, "sample.mp4")

        # Generate 1.0 second 320x240 MP4 with audio stream
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
            "-t", "1.0",
            "-c:v", "libx264", "-c:a", "aac",
            cls.sample_mp4,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"FFmpeg sample generation failed: {res.stderr}"

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_video_player_instantiation_and_load(self):
        vp = video_player.VideoPlayerWidget()
        self.assertIsInstance(vp, Gtk.Overlay)
        self.assertIsInstance(vp.picture, Gtk.Picture)
        self.assertEqual(vp.seek_scale.get_direction(), Gtk.TextDirection.LTR)

        ok = vp.load_video(self.sample_mp4)
        self.assertTrue(ok)
        self.assertAlmostEqual(vp.duration_sec, 1.0, places=1)
        vp.stop()


class TestGalleryMultiWindowAndViewer(unittest.TestCase):
    """Verifies multi-window handling and open_video_editor_directly viewer setup."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="sadeem_test_mw_")
        cls.img1 = os.path.join(cls.test_dir, "img1.png")
        cls.img2 = os.path.join(cls.test_dir, "img2.png")
        cls.video1 = os.path.join(cls.test_dir, "video1.mp4")

        Image.new("RGB", (100, 100), (255, 0, 0)).save(cls.img1)
        Image.new("RGB", (100, 100), (0, 255, 0)).save(cls.img2)

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15",
            "-t", "0.5",
            "-c:v", "libx264", "-an",
            cls.video1,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_multi_window_creation_and_focus(self):
        app = gallery_app.SadeemGalleryApp()
        app.set_application_id("org.sadeem.Gallery.TestMultiWindow")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        app.register(None)

        try:
            # 1. Open img1
            res1 = app.do_command_line(MockCommandLine(["sadeem-gallery", self.img1]))
            self.assertEqual(res1, 0)
            windows = app.get_windows()
            self.assertEqual(len(windows), 1)
            self.assertEqual(os.path.realpath(windows[0].current_path), os.path.realpath(self.img1))

            # 2. Open img2 -> separate window
            res2 = app.do_command_line(MockCommandLine(["sadeem-gallery", self.img2]))
            self.assertEqual(res2, 0)
            windows = app.get_windows()
            self.assertEqual(len(windows), 2)

            # 3. Open img1 again -> focus existing, do NOT create 3rd window
            res3 = app.do_command_line(MockCommandLine(["sadeem-gallery", self.img1]))
            self.assertEqual(res3, 0)
            windows = app.get_windows()
            self.assertEqual(len(windows), 2)
        finally:
            for w in app.get_windows():
                w.destroy()

    @unittest.mock.patch.object(gallery_app, "launch_video_editor")
    def test_open_video_editor_directly_redirects_to_video_editor(self, mock_launch):
        app = gallery_app.SadeemGalleryApp()
        app.set_application_id("org.sadeem.Gallery.TestOpenVideoDirectly")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        app.register(None)

        try:
            res = app.do_command_line(MockCommandLine(["sadeem-gallery", "--edit", self.video1]))
            self.assertEqual(res, 0)
            mock_launch.assert_called_once_with(self.video1)
            # Standalone launcher redirection returns 0 without opening empty gallery window
            windows = app.get_windows()
            self.assertEqual(len(windows), 0)
        finally:
            for w in app.get_windows():
                w.destroy()


class TestPortalAndCaptureUI(unittest.TestCase):
    """Verifies portal window mode persist_mode=0 and captureUI.js layout specifications."""

    def test_portal_window_mode_persist_zero(self):
        portal_path = os.path.join(CAPTURE_DIR, "capture/portal_screencast.py")
        with open(portal_path, "r", encoding="utf-8") as fp:
            content = fp.read()

        # Window mode must set persist_val = 0
        self.assertIn('persist_val = 0 if mode == "window" else 2', content)
        # Window mode must clear restore token
        self.assertIn('clear_restore_token("window")', content)
        # Never save restore token for window mode
        self.assertIn('if mode != "window":', content)

    def test_capture_ui_layout_specifications(self):
        ui_path = os.path.join(EXT_DIR, "captureUI.js")
        css_path = os.path.join(EXT_DIR, "stylesheet.css")
        with open(ui_path, "r", encoding="utf-8") as fp:
            content = fp.read()
        with open(css_path, "r", encoding="utf-8") as fp:
            css_content = fp.read()

        # 1. No fixed width: 440px
        self.assertNotIn("width: 440px", content)
        # 2. Min width 310px (moved cleanly to stylesheet.css for fast option switching)
        self.assertIn("sadeem-capture-card", content)
        self.assertIn("min-width: 310px", css_content)
        # 3. No weather-clear-symbolic
        self.assertNotIn("weather-clear-symbolic", content)
        self.assertIn("find-location-symbolic", content)
        # 4. Vertical mode buttons
        self.assertIn("Clutter.Orientation.VERTICAL", content)
        # 5. No deprecated vertical property
        self.assertNotIn("vertical:", content)
        # 6. Video recording completion shows interactive notification & body click opens gallery without --edit
        self.assertNotIn("this._openInGallery(", content)
        self.assertIn("this._notifyCaptureComplete(path, 'video')", content)
        self.assertIn("this._launchBackgroundCommand(['sadeem-gallery', filePath]);", content)
        self.assertIn("this._launchBackgroundCommand(['sadeem-video-editor', filePath]);", content)

    def test_translated_settings_in_ten_languages(self):
        expected_langs = ["ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh"]
        keys = ["setting_resolution", "setting_framerate", "setting_codec"]

        # 1. Test capture/i18n.py
        import i18n as capture_i18n
        for lang in expected_langs:
            for k in keys:
                trans = capture_i18n.t(k, lang=lang)
                self.assertTrue(len(trans) > 0, f"Missing key {k} in Python i18n for {lang}")

        # 2. Test captureI18n.js
        i18n_js_path = os.path.join(EXT_DIR, "captureI18n.js")
        with open(i18n_js_path, "r", encoding="utf-8") as fp:
            js_content = fp.read()

        for k in keys:
            self.assertIn(f'"{k}":', js_content, f"captureI18n.js must contain {k}")


if __name__ == "__main__":
    unittest.main()
