#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Test Suite for Sadeem Gallery Maintenance, Video Decoupling & Capture Integration.
Tests:
1. Video decoupling: launch_video_player priority (sadeem-video -> system default),
   sadeem-gallery <video> opens launcher without empty viewer window, --edit <video>
   redirects to sadeem-video-editor, and sadeem-gallery.desktop excludes video/* MIME types.
2. Media listing separation: list_sibling_images excludes videos (images only), while
   scan_directories preserves videos in timeline grid with THUMB_SIZE=320.
3. Editor --edit deferred activation until _on_image_loaded completes, plus EditorHistory
   immutable base_image reference sharing (no redundant pixel copies).
4. i18n parity across all 10 languages, removal of dead video-editor keys, Arabic plural
   rules (format_item_count), and clean viewer_counter without LRM marks.
5. SadeemGalleryApp multi-window architecture: opening separate files yields distinct windows,
   duplicate files focus existing windows without duplication.
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

for mod_name in ["app", "video_utils", "i18n", "editor", "canvas", "media"]:
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
import video_utils
from capture import portal_screencast


class MockCommandLine:
    def __init__(self, args):
        self._args = args

    def get_arguments(self):
        return self._args


class TestGalleryArchitectureAndEditor(unittest.TestCase):
    """Verifies video decoupling, --edit lifecycle, EditorHistory memory sharing, and i18n."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="sadeem_test_gallery_arch_")
        cls.img1 = os.path.join(cls.test_dir, "photo1.png")
        cls.img2 = os.path.join(cls.test_dir, "photo2.jpg")
        cls.video1 = os.path.join(cls.test_dir, "clip1.mp4")

        Image.new("RGBA", (120, 90), (255, 0, 0, 255)).save(cls.img1)
        Image.new("RGB", (100, 80), (0, 255, 0)).save(cls.img2)

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15",
            "-t", "0.4",
            "-c:v", "libx264", "-an",
            cls.video1,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"FFmpeg sample generation failed: {res.stderr}"

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_video_player_file_removed_and_desktop_excludes_video_mime(self):
        self.assertFalse(os.path.exists(os.path.join(GALLERY_DIR, "video_player.py")))
        desktop_path = os.path.join(REPO_ROOT, "files/system/usr/share/applications/sadeem-gallery.desktop")
        with open(desktop_path, "r", encoding="utf-8") as f:
            desktop_txt = f.read()
        self.assertIn("image/png;", desktop_txt)
        self.assertNotIn("video/", desktop_txt)

    def test_launch_video_player_priority_and_fallback(self):
        with mock.patch.object(gallery_app, "_find_exec_binary", return_value="/usr/bin/sadeem-video"), \
             mock.patch.object(gallery_app.subprocess, "Popen") as mock_popen:
            ok = gallery_app.launch_video_player(self.video1)
            self.assertTrue(ok)
            mock_popen.assert_called_once_with(
                ["/usr/bin/sadeem-video", self.video1],
                start_new_session=True,
                close_fds=True,
            )

        with mock.patch.object(gallery_app, "_find_exec_binary", return_value=None), \
             mock.patch.object(gallery_app.Gio.AppInfo, "launch_default_for_uri", return_value=True) as mock_uri:
            ok = gallery_app.launch_video_player(self.video1)
            self.assertTrue(ok)
            mock_uri.assert_called_once()
            self.assertTrue(mock_uri.call_args[0][0].startswith("file://"))

    def test_list_sibling_images_excludes_videos_while_scan_keeps_them(self):
        self.assertEqual(media.THUMB_SIZE, 320)
        siblings, idx = media.list_sibling_images(self.img1)
        names = [it["name"] for it in siblings]
        self.assertIn("photo1.png", names)
        self.assertIn("photo2.jpg", names)
        self.assertNotIn("clip1.mp4", names)
        self.assertEqual(os.path.realpath(siblings[idx]["path"]), os.path.realpath(self.img1))

        scanned = media.scan_directories([self.test_dir])
        scanned_names = [it["name"] for it in scanned]
        self.assertIn("clip1.mp4", scanned_names)
        vid_items = [it for it in scanned if it["name"] == "clip1.mp4"]
        self.assertTrue(vid_items[0]["is_video"])

    def test_edit_cli_defers_edit_mode_until_image_loaded(self):
        app = gallery_app.SadeemGalleryApp()
        app.set_application_id("org.sadeem.Gallery.TestEditDeferred")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        app.register(None)

        try:
            with mock.patch.object(gallery_app.threading, "Thread"):
                res = app.do_command_line(MockCommandLine(["sadeem-gallery", "--edit", self.img1]))
            self.assertEqual(res, 0)
            wins = app.get_windows()
            self.assertEqual(len(wins), 1)
            win = wins[0]
            self.assertTrue(win._pending_enter_edit)
            self.assertFalse(win.edit_mode)

            pil_img = Image.open(self.img1)
            win._on_image_loaded(win._load_generation, self.img1, pil_img, None, {}, None)
            self.assertFalse(win._pending_enter_edit)
            self.assertTrue(win.edit_mode)
            self.assertIs(win.base_image, pil_img)
        finally:
            for w in app.get_windows():
                w.destroy()

    def test_editor_history_shares_base_image_reference_and_i18n_parity(self):
        hist = editor.EditorHistory(max_steps=10)
        base1 = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
        adj1 = editor.default_adjustments()
        hist.push(base1, [], adj1)

        adj2 = editor.default_adjustments()
        adj2["brightness"] = 1.2
        hist.push(base1, [{"tool": "freehand"}], adj2)

        base2 = Image.new("RGBA", (32, 32), (40, 50, 60, 255))
        snap = hist.undo(base2, [], adj2)
        self.assertIsNotNone(snap)
        self.assertIs(snap[0], base1, "EditorHistory must share immutable base_img reference without copying")

        snap_redo = hist.redo(snap[0], snap[1], snap[2])
        self.assertIsNotNone(snap_redo)
        self.assertIs(snap_redo[0], base2)

        # Verify all 10 locales have parity, no dead keys, and clean Arabic viewer_counter & plurals
        en_keys = set(gallery_i18n.STRINGS["en"].keys())
        self.assertNotIn("vtab_trim", en_keys)
        self.assertNotIn("cat_all", en_keys)
        self.assertNotIn("\u200e", gallery_i18n.STRINGS["ar"]["viewer_counter"])

        for lang in gallery_i18n.SUPPORTED_LANGUAGES:
            self.assertEqual(set(gallery_i18n.STRINGS[lang].keys()), en_keys, f"Key mismatch in {lang}")
            for k in en_keys:
                self.assertTrue(bool(str(gallery_i18n.STRINGS[lang][k]).strip()), f"Empty {k} in {lang}")

        orig_lang = gallery_i18n.LANG
        try:
            gallery_i18n.LANG = "ar"
            self.assertEqual(gallery_i18n.format_item_count(0), "0 عنصر")
            self.assertEqual(gallery_i18n.format_item_count(1), "عنصر واحد")
            self.assertEqual(gallery_i18n.format_item_count(2), "عنصران")
            self.assertEqual(gallery_i18n.format_item_count(6), "6 عناصر")
            self.assertEqual(gallery_i18n.format_item_count(15), "15 عنصراً")
            self.assertEqual(gallery_i18n.format_item_count(100), "100 عنصر")
        finally:
            gallery_i18n.LANG = orig_lang

    def test_thumb_tile_size_and_lri_viewer_title(self):
        app = gallery_app.SadeemGalleryApp()
        app.set_application_id("org.sadeem.Gallery.TestTileAndLri")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        app.register(None)

        win = gallery_app.SadeemGalleryWindow(app)
        try:
            img_item = {
                "path": self.img1,
                "name": "لقطة_2026-11-27.png",
                "ext": ".png",
                "is_video": False,
                "is_raw": False,
                "is_animated": False,
            }
            vid_item = {
                "path": self.video1,
                "name": "تسجيل_2026-11-27.mp4",
                "ext": ".mp4",
                "is_video": True,
                "duration_str": "00:05",
                "is_raw": False,
                "is_animated": False,
            }

            tile_img, _pic_img = win._build_thumb_tile(img_item, [img_item])
            self.assertNotIsInstance(tile_img, Gtk.AspectFrame)
            min_w, nat_w, _, _ = tile_img.measure(Gtk.Orientation.HORIZONTAL, -1)
            min_h, nat_h, _, _ = tile_img.measure(Gtk.Orientation.VERTICAL, -1)
            self.assertGreaterEqual(min_w, 170)
            self.assertGreaterEqual(min_h, 170)
            self.assertGreaterEqual(nat_w, 184)
            self.assertGreaterEqual(nat_h, 184)
            self.assertEqual(nat_w, nat_h)

            tile_vid, _pic_vid = win._build_thumb_tile(vid_item, [vid_item])
            vmin_w, _, _, _ = tile_vid.measure(Gtk.Orientation.HORIZONTAL, -1)
            vmin_h, _, _, _ = tile_vid.measure(Gtk.Orientation.VERTICAL, -1)
            self.assertGreaterEqual(vmin_w, 170)
            self.assertGreaterEqual(vmin_h, 170)

            win.viewer_items = [img_item]
            with mock.patch.object(gallery_app.threading, "Thread"):
                win._load_viewer_index(0)
            self.assertEqual(win.viewer_title.get_title(), "\u2066لقطة_2026-11-27.png\u2069")
        finally:
            win.destroy()


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

    @unittest.mock.patch.object(gallery_app, "launch_video_player")
    @unittest.mock.patch.object(gallery_app, "launch_video_editor")
    def test_open_video_directly_and_edit_redirect(self, mock_edit_launch, mock_play_launch):
        app = gallery_app.SadeemGalleryApp()
        app.set_application_id("org.sadeem.Gallery.TestOpenVideoDirectly")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        app.register(None)

        try:
            res_play = app.do_command_line(MockCommandLine(["sadeem-gallery", self.video1]))
            self.assertEqual(res_play, 0)
            mock_play_launch.assert_called_once_with(self.video1)
            self.assertEqual(len(app.get_windows()), 0)

            res_edit = app.do_command_line(MockCommandLine(["sadeem-gallery", "--edit", self.video1]))
            self.assertEqual(res_edit, 0)
            mock_edit_launch.assert_called_once_with(self.video1)
            # Standalone launcher redirection returns 0 without opening empty gallery window
            self.assertEqual(len(app.get_windows()), 0)
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
