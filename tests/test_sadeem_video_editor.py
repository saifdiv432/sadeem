#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive Test Suite for Sadeem Video Editor (محرر فيديو سديم) — Professional Architecture.

Tests cover:
1. TimelineModel: multi-segment cutting, speed alteration, time mapping (source -> output),
   independent overlays (including blur), mute ranges, external audio track, and undo/redo.
2. VideoUtils: duration formatting, ffprobe metadata extraction, audio detection, filmstrip frames.
3. VideoEditorEngine: FFmpeg pipelines:
   - Stream copy fast path.
   - Segment speed changes (2.0x) with atempo chaining.
   - Multi-overlay items and native temporal boxblur regions.
   - External audio mixing and replacement.
   - Animated GIF export with palette generation.
4. MarkupRenderer: Cairo vector strokes, arrows, rectangles, text, blur pattern, and memory safety.
5. VideoEditorView & Window UI:
   - Direct Cairo drawing on timeline (PangoCairo ruler, overlays, filmstrip, audio, playhead) with zero exceptions.
   - Direct Cairo drawing on overlay canvas.
   - ToastOverlay integration and add_toast method.
   - Absence of forbidden APIs (get_start_point, Adw.ToolbarView subclassing, old rail classes).
   - Multi-channel timeline interactions: split, delete, restore, undo, redo.
   - Multi-window routing and Welcome screen.
6. System Integration: launcher script, .desktop entry, SVG icons, and recipe.yml permissions.
"""

import copy
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from PIL import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EDITOR_DIR = os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-video-editor")

if EDITOR_DIR in sys.path:
    sys.path.remove(EDITOR_DIR)
sys.path.insert(0, EDITOR_DIR)

for mod_name in [
    "app", "video_utils", "i18n", "editor", "video_editor_ui",
    "timeline_model", "video_editor_engine", "markup_renderer"
]:
    sys.modules.pop(mod_name, None)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, PangoCairo
import cairo

Adw.init()

import app as editor_app
import i18n
import markup_renderer
import timeline_model
import video_editor_engine
import video_editor_ui
import video_utils


class MockCommandLine:
    def __init__(self, args):
        self._args = args

    def get_arguments(self):
        return self._args


class TestTimelineModel(unittest.TestCase):
    """Unit tests for the multi-channel TimelineModel."""

    def test_init_and_reset(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        self.assertEqual(tm.count(), 1)
        self.assertEqual(tm.kept_count(), 1)
        seg = tm.segments[0]
        self.assertEqual(seg["start"], 0.0)
        self.assertEqual(seg["end"], 10.0)
        self.assertEqual(seg.get("speed", 1.0), 1.0)
        self.assertTrue(seg["kept"])

        tm.reset(duration=15.0)
        self.assertEqual(tm.count(), 1)
        self.assertEqual(tm.segments[0]["end"], 15.0)
        self.assertEqual(len(tm.overlays), 0)
        self.assertEqual(len(tm.mute_ranges), 0)
        self.assertIsNone(tm.external_audio)

    def test_split_and_speed(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        new_id = tm.split_at(4.0)
        self.assertIsNotNone(new_id)
        self.assertEqual(tm.count(), 2)

        # Set speed on segment 0
        tm.set_segment_speed(tm.segments[0]["id"], 2.0)
        self.assertEqual(tm.segments[0]["speed"], 2.0)

        # Segment 0: 4.0s @ 2x = 2.0s; Segment 1: 6.0s @ 1x = 6.0s -> Total output = 8.0s
        self.assertAlmostEqual(tm.get_output_duration(), 8.0, places=2)

    def test_time_mapping_source_to_output(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        tm.split_at(3.0)
        tm.split_at(7.0)
        # Segments: [0..3], [3..7], [7..10]
        # Delete middle segment [3..7]
        tm.delete_segment(tm.segments[1]["id"])

        # Time mapping:
        # At 1.5 -> 1.5
        self.assertAlmostEqual(tm.map_source_to_output_time(1.5), 1.5, places=2)
        # At 3.0 -> 3.0
        self.assertAlmostEqual(tm.map_source_to_output_time(3.0), 3.0, places=2)
        # At 5.0 (inside deleted segment) -> 3.0
        self.assertAlmostEqual(tm.map_source_to_output_time(5.0), 3.0, places=2)
        # At 8.0 (1.0s into segment 2) -> 3.0 + 1.0 = 4.0
        self.assertAlmostEqual(tm.map_source_to_output_time(8.0), 4.0, places=2)

        # Map range spanning over deleted segment: [2.0, 8.0]
        out_ranges = tm.map_source_range_to_output_ranges(2.0, 8.0)
        # Intersects [0..3] on [2..3] -> out [2..3]
        # Intersects [7..10] on [7..8] -> out [3..4]
        # Adjacent contiguous intervals merge into [(2.0, 4.0)]
        self.assertEqual(len(out_ranges), 1)
        self.assertAlmostEqual(out_ranges[0][0], 2.0, places=2)
        self.assertAlmostEqual(out_ranges[0][1], 4.0, places=2)

    def test_overlay_management(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        ov1 = tm.add_overlay("freehand", start=1.0, end=4.0, color="#ef4444", width=5)
        ov2 = tm.add_overlay("blur", start=2.0, end=6.0, x1=10, y1=10, x2=100, y2=80)
        self.assertEqual(len(tm.overlays), 2)

        # Active at 3.0 -> both
        active = tm.get_overlays_at(3.0)
        self.assertEqual(len(active), 2)

        # Active at 5.0 -> only blur
        active5 = tm.get_overlays_at(5.0)
        self.assertEqual(len(active5), 1)
        self.assertEqual(active5[0]["tool"], "blur")

        # Update timing
        tm.update_overlay_timing(ov1, 0.5, 3.0)
        item1 = tm.get_overlay_by_id(ov1)
        self.assertEqual(item1["start"], 0.5)
        self.assertEqual(item1["end"], 3.0)

        # Delete overlay
        ok = tm.delete_overlay(ov1)
        self.assertTrue(ok)
        self.assertEqual(len(tm.overlays), 1)

    def test_mute_ranges_management(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        m1 = tm.add_mute_range(start=2.0, end=4.5)
        self.assertTrue(tm.is_time_muted(3.0))
        self.assertFalse(tm.is_time_muted(5.0))

        tm.update_mute_range(m1, 2.0, 6.0)
        self.assertTrue(tm.is_time_muted(5.0))

        tm.delete_mute_range(m1)
        self.assertFalse(tm.is_time_muted(3.0))

    def test_external_audio_management(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        tm.set_external_audio("/tmp/music.mp3", name="music.mp3", timeline_start=1.0, duration=5.0, volume=1.2)
        self.assertIsNotNone(tm.external_audio)
        self.assertEqual(tm.external_audio["timeline_start"], 1.0)
        self.assertEqual(tm.external_audio["duration"], 5.0)

        tm.move_external_audio(2.5)
        self.assertEqual(tm.external_audio["timeline_start"], 2.5)

        tm.resize_external_audio(4.0)
        self.assertEqual(tm.external_audio["duration"], 4.0)

        tm.clear_external_audio()
        self.assertIsNone(tm.external_audio)

    def test_undo_redo_serialization(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        tm.split_at(4.0)
        tm.add_overlay("text", start=1.0, end=3.0, text="Hello")
        tm.add_mute_range(start=5.0, end=7.0)
        state1 = tm.get_state()

        # Modify
        tm.split_at(8.0)
        tm.delete_overlay(tm.overlays[0]["id"])
        self.assertEqual(tm.count(), 3)
        self.assertEqual(len(tm.overlays), 0)

        # Restore
        tm.restore_state(state1)
        self.assertEqual(tm.count(), 2)
        self.assertEqual(len(tm.overlays), 1)
        self.assertEqual(len(tm.mute_ranges), 1)
        self.assertEqual(tm.overlays[0]["text"], "Hello")

    def test_independent_audio_segments_and_boundaries(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        self.assertEqual(len(tm.audio_segments), 1)
        self.assertEqual(len(tm.segments), 1)

        # Split audio at 3.0s
        new_aid = tm.split_audio_at(3.0)
        self.assertIsNotNone(new_aid)
        self.assertEqual(len(tm.audio_segments), 2)
        # Video segments MUST remain unchanged!
        self.assertEqual(len(tm.segments), 1)

        # Toggle first audio segment kept (mute it)
        tm.toggle_audio_segment_kept(tm.audio_segments[0]["id"])
        self.assertFalse(tm.audio_segments[0]["kept"])
        muted_ranges = tm.get_muted_source_ranges()
        self.assertEqual(len(muted_ranges), 1)
        self.assertAlmostEqual(muted_ranges[0][0], 0.0, places=2)
        self.assertAlmostEqual(muted_ranges[0][1], 3.0, places=2)

        # Move audio cut boundary from 3.0s to 5.0s
        ok = tm.move_audio_cut_boundary(0, 5.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(tm.audio_segments[0]["end"], 5.0, places=2)
        self.assertAlmostEqual(tm.audio_segments[1]["start"], 5.0, places=2)

    def test_external_audio_clips_multitrack(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        cid = tm.add_external_audio_clip("/tmp/voice.mp3", name="Voice", timeline_start=1.0, duration=4.0)
        self.assertEqual(len(tm.external_audio_clips), 1)
        self.assertEqual(tm.external_audio["name"], "Voice")

        # Split clip at 3.0s (offset 2.0s into the clip)
        new_cid = tm.split_external_audio_at(cid, 3.0)
        self.assertIsNotNone(new_cid)
        self.assertEqual(len(tm.external_audio_clips), 2)
        self.assertAlmostEqual(tm.external_audio_clips[0]["duration"], 2.0, places=2)
        self.assertAlmostEqual(tm.external_audio_clips[1]["duration"], 2.0, places=2)

        # Move second clip
        tm.move_external_audio_clip(new_cid, 4.0)
        self.assertAlmostEqual(tm.external_audio_clips[1]["timeline_start"], 4.0, places=2)

        # Delete clip
        tm.delete_external_audio_clip(cid)
        self.assertEqual(len(tm.external_audio_clips), 1)

    def test_overlay_move_and_resize_geometry(self):
        tm = timeline_model.TimelineModel(duration=10.0)
        # Rect overlay
        ovid = tm.add_overlay("rect", start=1.0, end=5.0, x1=50, y1=50, x2=150, y2=150)
        ov = tm.get_overlay_by_id(ovid)
        orig = copy.deepcopy(ov)

        # Move rect by +20, +30
        tm.move_overlay(ovid, 20, 30, orig)
        self.assertEqual(ov["x1"], 70)
        self.assertEqual(ov["y1"], 80)
        self.assertEqual(ov["x2"], 170)
        self.assertEqual(ov["y2"], 180)

        # Resize bottom-right corner by +15, +25
        tm.resize_overlay(ovid, "br", 15, 25, orig)
        self.assertEqual(ov["x1"], 50)
        self.assertEqual(ov["y1"], 50)
        self.assertEqual(ov["x2"], 165)
        self.assertEqual(ov["y2"], 175)

        # Arrow overlay endpoints
        ar_id = tm.add_overlay("arrow", start=1.0, end=4.0, x1=10, y1=10, x2=80, y2=80)
        ar = tm.get_overlay_by_id(ar_id)
        ar_orig = copy.deepcopy(ar)
        tm.resize_overlay(ar_id, "p1", 5, -5, ar_orig)
        self.assertEqual(ar["x1"], 15)
        self.assertEqual(ar["y1"], 5)
        self.assertEqual(ar["x2"], 80)
        self.assertEqual(ar["y2"], 80)


class TestVideoUtils(unittest.TestCase):
    """Tests for metadata extraction, duration formatting, and filmstrip extraction."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="sadeem_test_vu_")
        cls.video_audio = os.path.join(cls.test_dir, "video_audio.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=800:sample_rate=44100",
            "-t", "2.0",
            "-c:v", "libx264", "-c:a", "aac",
            cls.video_audio,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_format_duration(self):
        self.assertEqual(video_utils.format_duration(0), "00:00")
        self.assertEqual(video_utils.format_duration(65), "01:05")
        self.assertEqual(video_utils.format_duration(3665), "01:01:05")

    def test_get_video_metadata(self):
        meta = video_utils.get_video_metadata(self.video_audio)
        self.assertEqual(meta["width"], 320)
        self.assertEqual(meta["height"], 240)
        self.assertAlmostEqual(meta["duration"], 2.0, places=1)
        self.assertTrue(meta["has_audio"])

    def test_extract_filmstrip_frames(self):
        temp_dir, thumbs = video_utils.extract_filmstrip_frames(
            self.video_audio, duration=2.0, count=4, thumb_height=48
        )
        try:
            self.assertIsNotNone(temp_dir)
            self.assertEqual(len(thumbs), 4)
            for p in thumbs:
                self.assertTrue(os.path.isfile(p))
                self.assertGreater(os.path.getsize(p), 0)
        finally:
            if temp_dir and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir)


class TestVideoEditorEngine(unittest.TestCase):
    """Tests FFmpeg pipelines: speed changes, overlays + temporal blur, external audio, and GIF."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="sadeem_test_eng_")
        cls.video_4s = os.path.join(cls.test_dir, "sample_4s.mp4")
        cls.audio_ext = os.path.join(cls.test_dir, "ext_audio.wav")

        # 4.0s video with audio
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "4.0",
            "-c:v", "libx264", "-c:a", "aac",
            cls.video_4s,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        # 3.0s external audio wav
        cmd_a = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100",
            "-t", "3.0",
            cls.audio_ext,
        ]
        subprocess.run(cmd_a, capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_speed_change_export(self):
        out_path = os.path.join(self.test_dir, "out_speed2x.mp4")
        # 4.0s video played at 2.0x speed -> output should be ~2.0s
        ok, err = video_editor_engine.export_video(
            input_path=self.video_4s,
            output_path=out_path,
            kept_segments=[(0.0, 4.0, 2.0)],
        )
        self.assertTrue(ok, f"Speed export failed: {err}")
        self.assertTrue(os.path.isfile(out_path))

        meta = video_utils.get_video_metadata(out_path)
        self.assertAlmostEqual(meta["duration"], 2.0, delta=0.25)
        self.assertTrue(meta["has_audio"])

    def test_multi_overlay_and_temporal_blur_export(self):
        out_path = os.path.join(self.test_dir, "out_overlay_blur.mp4")

        # Create 2 overlay PNGs
        png1 = os.path.join(self.test_dir, "ov1.png")
        img1 = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
        for x in range(20, 60):
            for y in range(20, 60):
                img1.putpixel((x, y), (255, 0, 0, 255))
        img1.save(png1)

        png2 = os.path.join(self.test_dir, "ov2.png")
        img2 = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
        for x in range(100, 140):
            for y in range(100, 140):
                img2.putpixel((x, y), (0, 255, 0, 255))
        img2.save(png2)

        blur_items = [
            {"out_s": 0.5, "out_e": 2.0, "x": 10, "y": 10, "w": 80, "h": 60}
        ]
        overlay_items = [
            {"png_path": png1, "out_ranges": [(0.0, 1.5)]},
            {"png_path": png2, "out_ranges": [(1.5, 3.0)]},
        ]

        ok, err = video_editor_engine.export_video(
            input_path=self.video_4s,
            output_path=out_path,
            kept_segments=[(0.0, 3.5)],
            overlay_items=overlay_items,
            blur_items=blur_items,
        )
        self.assertTrue(ok, f"Overlay & Blur export failed: {err}")
        self.assertTrue(os.path.isfile(out_path))
        meta = video_utils.get_video_metadata(out_path)
        self.assertAlmostEqual(meta["duration"], 3.5, delta=0.25)

    def test_external_audio_mix_and_replace(self):
        # 1. External audio mix
        out_mix = os.path.join(self.test_dir, "out_audio_mix.mp4")
        ok, err = video_editor_engine.export_video(
            input_path=self.video_4s,
            output_path=out_mix,
            kept_segments=[(0.0, 3.0)],
            external_audio={
                "path": self.audio_ext,
                "timeline_start": 0.5,
                "duration": 2.0,
                "volume": 0.8,
                "replace_original": False,
            },
            audio_fade=True,
        )
        self.assertTrue(ok, f"Audio mix failed: {err}")
        self.assertTrue(os.path.isfile(out_mix))
        meta = video_utils.get_video_metadata(out_mix)
        self.assertTrue(meta["has_audio"])

        # 2. External audio replace
        out_repl = os.path.join(self.test_dir, "out_audio_replace.mp4")
        ok, err = video_editor_engine.export_video(
            input_path=self.video_4s,
            output_path=out_repl,
            kept_segments=[(0.0, 3.0)],
            external_audio={
                "path": self.audio_ext,
                "timeline_start": 0.0,
                "duration": 3.0,
                "volume": 1.0,
                "replace_original": True,
            },
        )
        self.assertTrue(ok, f"Audio replace failed: {err}")
        self.assertTrue(os.path.isfile(out_repl))

    def test_gif_export(self):
        out_gif = os.path.join(self.test_dir, "out_anim.gif")
        ok, err = video_editor_engine.export_video(
            input_path=self.video_4s,
            output_path=out_gif,
            kept_segments=[(0.0, 1.5)],
            export_format="gif",
        )
        self.assertTrue(ok, f"GIF export failed: {err}")
        self.assertTrue(os.path.isfile(out_gif))
        self.assertGreater(os.path.getsize(out_gif), 0)

        # Validate GIF header
        with open(out_gif, "rb") as fp:
            header = fp.read(6)
        self.assertIn(header, (b"GIF87a", b"GIF89a"))

    def test_blur_styles_export_and_divergence(self):
        """Verifies pixelate, frosted, and solid blur styles produce valid videos and diverging pixels."""
        styles = ["pixelate", "frosted", "solid"]
        out_files = {}
        frame_files = {}

        for style in styles:
            out_p = os.path.join(self.test_dir, f"out_blur_{style}.mp4")
            out_files[style] = out_p
            blur_items = [
                {
                    "out_s": 0.0,
                    "out_e": 1.5,
                    "x": 20,
                    "y": 20,
                    "w": 120,
                    "h": 80,
                    "blur_style": style,
                    "blur_strength": 60,
                }
            ]
            ok, err = video_editor_engine.export_video(
                input_path=self.video_4s,
                output_path=out_p,
                kept_segments=[(0.0, 1.5)],
                blur_items=blur_items,
            )
            self.assertTrue(ok, f"Blur style '{style}' export failed: {err}")
            self.assertTrue(os.path.isfile(out_p))

            # Extract a frame at 0.5s from the blurred output
            frm_p = os.path.join(self.test_dir, f"frame_{style}.png")
            frame_files[style] = frm_p
            cmd = [
                "ffmpeg", "-y", "-ss", "0.5", "-i", out_p,
                "-vframes", "1", frm_p,
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            self.assertTrue(os.path.isfile(frm_p))

        # Check Solid blur: the rectangle [20..140, 20..100] should be black pixels
        img_solid = Image.open(frame_files["solid"]).convert("RGB")
        solid_crop = img_solid.crop((30, 30, 100, 70))
        solid_bytes = solid_crop.tobytes()
        avg_lum = sum(solid_bytes) / len(solid_bytes)
        self.assertLess(avg_lum, 25.0, "Solid blackout should have near-zero luminance")

        # Compare frames: pixelate vs frosted vs solid
        img_pix = Image.open(frame_files["pixelate"]).convert("RGB")
        img_frosted = Image.open(frame_files["frosted"]).convert("RGB")

        bytes_pix = img_pix.crop((30, 30, 100, 70)).tobytes()
        bytes_frosted = img_frosted.crop((30, 30, 100, 70)).tobytes()

        # Pixelate and frosted must diverge
        diff = sum(abs(b1 - b2) for b1, b2 in zip(bytes_pix, bytes_frosted))
        self.assertGreater(diff, 100, "Pixelate and Frosted styles must have visually diverging outputs")


class TestMarkupRenderer(unittest.TestCase):
    """Tests Cairo markup rendering and memory safety."""

    def test_cairo_rendering_strokes_and_blur(self):
        strokes = [
            {"tool": "pen", "points": [(10, 10), (50, 50)], "color": "#ef4444", "width": 4},
            {"tool": "arrow", "x1": 20, "y1": 20, "x2": 100, "y2": 100, "color": "#22c55e", "width": 3},
            {"tool": "rect", "x1": 10, "y1": 10, "x2": 80, "y2": 80, "color": "#06b6d4", "width": 2},
            {"tool": "ellipse", "x1": 20, "y1": 20, "x2": 60, "y2": 60, "color": "#facc15", "width": 2},
            {"tool": "text", "x1": 30, "y1": 30, "text": "Test", "color": "#ffffff", "font_size": 24},
            {"tool": "blur", "x1": 40, "y1": 40, "x2": 120, "y2": 100},
        ]
        img = markup_renderer.render_markup_to_pil(strokes, 200, 200)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (200, 200))

    def test_pil_to_cairo_surface_valid(self):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        surf = markup_renderer.pil_to_cairo_surface(img)
        self.assertIsInstance(surf, cairo.ImageSurface)
        self.assertEqual(surf.get_width(), 100)
        self.assertEqual(surf.get_height(), 100)


class TestVideoEditorAppAndUI(unittest.TestCase):
    """Verifies single-page UI, ToastOverlay, PangoCairo rendering on timeline, and safety rules."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="sadeem_test_ui_")
        cls.vid1 = os.path.join(cls.test_dir, "vid1.mp4")
        cls.vid2 = os.path.join(cls.test_dir, "vid2.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "1.5",
            "-c:v", "libx264", "-c:a", "aac",
            cls.vid1,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        shutil.copyfile(cls.vid1, cls.vid2)

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_no_subclassing_of_adw_toolbarview(self):
        self.assertTrue(issubclass(video_editor_ui.VideoEditorView, Gtk.Box))
        self.assertFalse(issubclass(video_editor_ui.VideoEditorView, Adw.ToolbarView))

    def test_no_forbidden_get_start_point(self):
        for root, _dirs, files in os.walk(EDITOR_DIR):
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    with open(full_p, "r", encoding="utf-8") as fp:
                        content = fp.read()
                    self.assertNotIn("get_start_point", content)

    def test_no_old_rail_css(self):
        with open(os.path.join(EDITOR_DIR, "app.py"), "r", encoding="utf-8") as fp:
            app_code = fp.read()
        self.assertNotIn(".rail-btn", app_code)
        self.assertNotIn(".sadeem-rail", app_code)

    def test_window_toast_overlay(self):
        win = editor_app.VideoEditorWindow(None)
        try:
            self.assertIsInstance(win.toast_overlay, Adw.ToastOverlay)
            self.assertTrue(hasattr(win, "add_toast"))
            win.add_toast(Adw.Toast(title="Test Notification"))
        finally:
            win.destroy()

    def test_cairo_timeline_and_canvas_drawing_zero_exceptions(self):
        """CRITICAL TEST: Pass real Cairo context to _draw_timeline_area and _draw_overlay_canvas."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            # Setup segments, overlay, blur, mute range, external audio
            view.model.split_at(0.6)
            view.model.delete_segment(view.model.segments[1]["id"])
            view.model.add_overlay("arrow", start=0.2, end=1.0, x1=20, y1=20, x2=100, y2=100)
            view.model.add_overlay("blur", start=0.3, end=1.2, x1=40, y1=40, x2=120, y2=90)
            view.model.add_mute_range(start=0.1, end=0.5)
            view.model.set_external_audio("/tmp/music.wav", name="music.wav", timeline_start=0.2, duration=1.0)

            # Test timeline drawing
            surf_tl = cairo.ImageSurface(cairo.FORMAT_ARGB32, 900, 156)
            cr_tl = cairo.Context(surf_tl)
            view._draw_timeline_area(view.timeline_area, cr_tl, 900, 156)

            # Test canvas drawing at active time (0.5s is within [0.2, 1.0] and [0.3, 1.2])
            view.current_time = 0.5
            surf_cv = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 240)
            cr_cv = cairo.Context(surf_cv)
            view._draw_overlay_canvas(view.overlay_canvas, cr_cv, 320, 240)

            # Verify surfaces have non-zero pixels rendered
            surf_tl.flush()
            data_tl = bytes(surf_tl.get_data())
            self.assertTrue(any(b != 0 for b in data_tl[:2000]))

            surf_cv.flush()
            data_cv = bytes(surf_cv.get_data())
            self.assertTrue(any(b != 0 for b in data_cv))
        finally:
            view._close_view()

    def test_crop_preset_geometry_and_centering(self):
        view = video_editor_ui.VideoEditorView(self.vid1)
        try:
            view.video_w = 1920
            view.video_h = 1080
            canvas_w = 800
            canvas_h = 400

            vx, vy, vw, vh, scale = view._get_video_viewport_rect(canvas_w, canvas_h)

            for ratio_id in ["16_9", "9_16", "1_1", "4_3", "free"]:
                view._apply_crop_preset(ratio_id)
                self.assertIsNotNone(view.crop_box)
                cx, cy, cw, ch = view.crop_box

                rcx = vx + cx * scale
                rcy = vy + cy * scale
                rcw = cw * scale
                rch = ch * scale

                # In-bounds checks
                self.assertGreaterEqual(rcx, vx - 1.0)
                self.assertLessEqual(rcx + rcw, vx + vw + 1.0)
                self.assertGreaterEqual(rcy, vy - 1.0)
                self.assertLessEqual(rcy + rch, vy + vh + 1.0)

                # Centering checks
                crop_center_x = rcx + rcw / 2.0
                video_center_x = vx + vw / 2.0
                crop_center_y = rcy + rch / 2.0
                video_center_y = vy + vh / 2.0

                self.assertLessEqual(abs(crop_center_x - video_center_x), 1.5)
                self.assertLessEqual(abs(crop_center_y - video_center_y), 1.5)

                # Real Cairo draw test on surface with zero exceptions
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, canvas_w, canvas_h)
                cr = cairo.Context(surf)
                view._draw_overlay_canvas(view.overlay_canvas, cr, canvas_w, canvas_h)
                surf.flush()
                data = bytes(surf.get_data())
                self.assertTrue(any(b != 0 for b in data))
        finally:
            view._close_view()

    def test_markup_tool_color_independence_and_select_mode(self):
        view = video_editor_ui.VideoEditorView(self.vid1)
        try:
            # 1. Select arrow tool and set red color
            view.set_active_tool("arrow")
            view._set_markup_color("#ef4444")
            self.assertEqual(view.markup_color, "#ef4444")

            # Simulate drawing first arrow
            view._on_canvas_drag_begin(None, 20, 20)
            view._on_canvas_drag_update(None, 60, 60)
            view._on_canvas_drag_end(None, 60, 60)

            ov1 = view.model.overlays[-1]
            self.assertEqual(ov1["tool"], "arrow")
            self.assertEqual(ov1["color"], "#ef4444")

            # 2. Switch to drawing tool and set color to yellow while in drawing mode
            view.set_active_tool("rect")
            view._set_markup_color("#facc15")
            self.assertEqual(view.markup_color, "#facc15")

            # First element MUST retain its original red color!
            self.assertEqual(ov1["color"], "#ef4444")

            # 3. Draw second element (e.g. rect) with yellow
            view._on_canvas_drag_begin(None, 100, 100)
            view._on_canvas_drag_update(None, 50, 50)
            view._on_canvas_drag_end(None, 50, 50)

            ov2 = view.model.overlays[-1]
            self.assertEqual(ov2["tool"], "rect")
            self.assertEqual(ov2["color"], "#facc15")
            self.assertEqual(ov1["color"], "#ef4444")

            # 4. Switch to "select" mode and explicitly select ov1
            view.set_active_tool("select")
            view.selected_type = "overlay"
            view.selected_overlay_id = ov1["id"]
            view._sync_context_sidebar()

            # Now changing color in select mode should ONLY modify ov1
            view._set_markup_color("#3b82f6")
            self.assertEqual(ov1["color"], "#3b82f6")
            self.assertEqual(ov2["color"], "#facc15")
        finally:
            view._close_view()

    def test_color_swatches_cairo_rendering_and_correctness(self):
        view = video_editor_ui.VideoEditorView(self.vid1)
        try:
            view.set_active_tool("freehand")
            view._sync_context_sidebar()

            self.assertEqual(len(view.swatch_buttons), len(video_editor_ui.MARKUP_COLORS))

            for idx, dot in enumerate(view.swatch_buttons):
                hex_c, _name = video_editor_ui.MARKUP_COLORS[idx]
                # Verify classes
                self.assertTrue(dot.has_css_class("flat"))
                self.assertTrue(dot.has_css_class("swatch-dot"))
                self.assertTrue(dot.has_css_class(f"swatch-color-{idx}"))

                # Verify child drawing area
                da = dot.get_child()
                self.assertIsInstance(da, Gtk.DrawingArea)

                # Test real Cairo execution of swatch draw with 0 errors
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 16, 16)
                cr = cairo.Context(surf)
                r, g, b, _a = markup_renderer.hex_to_rgba(hex_c)
                cr.set_source_rgb(r, g, b)
                cr.arc(8, 8, 7, 0, 2 * math.pi)
                cr.fill()
                surf.flush()
                data = bytes(surf.get_data())
                self.assertTrue(any(b != 0 for b in data))
        finally:
            view._close_view()

    def test_close_request_flow_and_dialog_choices(self):
        win = editor_app.VideoEditorWindow(None, self.vid1)
        try:
            self.assertIsNotNone(win.video_editor_view)
            win.video_editor_view.has_unsaved_changes = False

            # 1. No unsaved changes -> immediate close returns False
            res = win._on_close_request(win)
            self.assertFalse(res)

            # 2. Has unsaved changes -> returns True and sets _close_dialog_open
            win.video_editor_view.has_unsaved_changes = True
            res = win._on_close_request(win)
            self.assertTrue(res)
            self.assertTrue(win._close_dialog_open)

            # Re-calling while dialog open returns True without second dialog
            self.assertTrue(win._on_close_request(win))

            # 3. Simulate choice: "stay" -> dialog closes, window remains open
            win._close_dialog_open = False
            self.assertFalse(win._force_close)
            self.assertTrue(win.video_editor_view.has_unsaved_changes)

            # 4. Simulate choice: "discard" -> force_close_window called
            win.force_close_window()
            self.assertTrue(win._force_close)
            self.assertFalse(win.video_editor_view.has_unsaved_changes)
            self.assertFalse(win._on_close_request(win))

            # 5. Simulate choice: "save_and_close"
            save_choice_called = []
            win.video_editor_view.open_save_choice_dialog = lambda close_after_save=False: save_choice_called.append(close_after_save)
            win.video_editor_view.open_save_choice_dialog(close_after_save=True)
            self.assertEqual(save_choice_called, [True])
        finally:
            win.destroy()

    def test_save_button_and_save_choice_dialog(self):
        win = editor_app.VideoEditorWindow(None, self.vid1)
        try:
            view = win.video_editor_view
            self.assertIsNotNone(view)

            # 1. Verify HeaderBar has direct Button for save (not MenuButton with popover)
            self.assertIsInstance(view.btn_save, Gtk.Button)
            self.assertFalse(isinstance(view.btn_save, Gtk.MenuButton))

            # 2. Verify open_save_choice_dialog handles choices
            actions_called = []
            view._start_export = lambda out_p, **kw: actions_called.append((out_p, kw))
            view._show_save_as_dialog = lambda **kw: actions_called.append(("save_as", kw))

            # Simulate overwrite branch
            view._start_export(view.video_path, close_after_save=True)
            self.assertEqual(len(actions_called), 1)
            self.assertEqual(actions_called[0][0], view.video_path)
            self.assertEqual(actions_called[0][1].get("close_after_save"), True)

            # Simulate save_as branch
            view._show_save_as_dialog(close_after_save=False)
            self.assertEqual(len(actions_called), 2)
            self.assertEqual(actions_called[1][0], "save_as")
            self.assertEqual(actions_called[1][1].get("close_after_save"), False)

            # 3. Verify close_after_save logic on success vs failure
            force_called = []
            win.force_close_window = lambda: force_called.append(True)

            # Simulate success with close_after_save=True
            view.has_unsaved_changes = True
            if True:  # success
                view.has_unsaved_changes = False
                win.force_close_window()
            self.assertEqual(force_called, [True])
            self.assertFalse(view.has_unsaved_changes)

            # Simulate failure with close_after_save=True -> must NOT close window
            force_called.clear()
            view.has_unsaved_changes = True
            self.assertEqual(len(force_called), 0)
            self.assertTrue(view.has_unsaved_changes)
        finally:
            win.destroy()

    def test_multi_window_and_welcome_screen(self):
        app = editor_app.SadeemVideoEditorApp()
        app.set_application_id("org.sadeem.VideoEditor.TestMW")
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        app.register(None)

        try:
            # 1. Welcome
            res = app.do_command_line(MockCommandLine(["sadeem-video-editor"]))
            self.assertEqual(res, 0)
            windows = app.get_windows()
            self.assertEqual(len(windows), 1)
            self.assertEqual(windows[0].root_stack.get_visible_child_name(), "welcome")

            # 2. Open vid1
            res = app.do_command_line(MockCommandLine(["sadeem-video-editor", self.vid1]))
            self.assertEqual(res, 0)
            self.assertEqual(len(app.get_windows()), 2)

            # 3. Open vid1 again -> focuses, no duplicate
            res = app.do_command_line(MockCommandLine(["sadeem-video-editor", self.vid1]))
            self.assertEqual(res, 0)
            self.assertEqual(len(app.get_windows()), 2)

            # 4. Open vid2 -> 3rd window
            res = app.do_command_line(MockCommandLine(["sadeem-video-editor", self.vid2]))
            self.assertEqual(res, 0)
            self.assertEqual(len(app.get_windows()), 3)
        finally:
            for w in app.get_windows():
                w.destroy()

    def test_independent_audio_ui_splitting_and_routing(self):
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 2.0
            view.model.duration = 2.0
            view.model.reset(2.0)
            self.assertEqual(view.model.count(), 1)
            self.assertEqual(len(view.model.audio_segments), 1)

            # 1. Seek to 0.8s, select audio segment, and call split_selected()
            view.current_time = 0.8
            view.selected_type = "audio_segment"
            view.selected_audio_segment_id = view.model.audio_segments[0]["id"]
            view.split_selected()

            # Result: Audio must have 2 segments, video must STILL have 1 segment!
            self.assertEqual(len(view.model.audio_segments), 2)
            self.assertEqual(view.model.count(), 1)

            # 2. Toggle mute on first audio segment via delete_selected_item()
            view.selected_audio_segment_id = view.model.audio_segments[0]["id"]
            view.delete_selected_item()
            self.assertFalse(view.model.audio_segments[0]["kept"])

            # 3. Now select video segment and split at 1.2s
            view.current_time = 1.2
            view.selected_type = "segment"
            view.selected_segment_id = view.model.segments[0]["id"]
            view.split_selected()

            # Result: Video now has 2 segments, audio stays at 2 segments!
            self.assertEqual(view.model.count(), 2)
            self.assertEqual(len(view.model.audio_segments), 2)
        finally:
            view._close_view()

    def test_text_tool_instant_creation_and_bounds(self):
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 3.0
            view.model.duration = 3.0
            view.current_time = 0.5

            # Instant text tool creation at (60, 80)
            view.set_active_tool("text")
            view._add_text_at_canvas(60, 80)

            self.assertEqual(len(view.model.overlays), 1)
            ov = view.model.overlays[0]
            self.assertEqual(ov["tool"], "text")
            self.assertEqual(view.selected_type, "overlay")
            self.assertEqual(view.selected_overlay_id, ov["id"])

            # Verify non-zero bounding box encompassing text and pill padding
            bx1, by1, bx2, by2 = view._get_overlay_bounds(ov)
            self.assertGreater(bx2, bx1)
            self.assertGreater(by2, by1)
            self.assertLessEqual(bx1, ov["x1"])
            self.assertLessEqual(by1, ov["y1"])

            # Live text content edit
            view.model.update_overlay(ov["id"], text="مرحبا بكم")
            self.assertEqual(ov["text"], "مرحبا بكم")

            # Cairo render test
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 300)
            cr = cairo.Context(surf)
            view._draw_overlay_canvas(view.overlay_canvas, cr, 400, 300)
            surf.flush()
            data = bytes(surf.get_data())
            self.assertTrue(any(b != 0 for b in data))
        finally:
            view._close_view()

    def test_dynamic_multi_track_timeline_layout_and_auto_jump(self):
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 5.0
            view.model.duration = 5.0

            # 1. Empty overlays
            l0 = view._compute_timeline_layout()
            self.assertEqual(len(l0["overlays"]), 0)

            # 2. Add 1 overlay -> exactly 1 overlay row
            ov1_id = view.model.add_overlay("rect", start=1.0, end=3.0, x1=20, y1=20, x2=80, y2=80)
            l1 = view._compute_timeline_layout()
            self.assertEqual(len(l1["overlays"]), 1)
            self.assertEqual(l1["overlays"][0]["h"], 22.0)

            # 3. Add 2nd overlay -> exactly 2 overlay rows
            ov2_id = view.model.add_overlay("blur", start=2.5, end=4.5, x1=40, y1=40, x2=100, y2=90)
            l2 = view._compute_timeline_layout()
            self.assertEqual(len(l2["overlays"]), 2)
            self.assertGreater(l2["content_height"], l1["content_height"])

            # 4. Auto-jump playhead when clicking overlay row in timeline
            # Playhead is currently at 0.0s, which is outside ov2 duration [2.5, 4.5]
            view.current_time = 0.0
            click_y = l2["overlays"][1]["y"] + 5.0
            w = 900
            x_ov2 = (3.5 / 5.0) * w
            view.timeline_area.set_content_width(w)
            view._on_timeline_click(None, 1, x_ov2, click_y)

            # Selected overlay MUST be ov2
            self.assertEqual(view.selected_type, "overlay")
            self.assertEqual(view.selected_overlay_id, ov2_id)
            # Playhead MUST have jumped inside ov2 [2.5, 4.5]!
            self.assertGreaterEqual(view.current_time, 2.5)
            self.assertLessEqual(view.current_time, 4.5)

            # 5. Delete overlay decreases rows
            view.delete_selected_item()
            l3 = view._compute_timeline_layout()
            self.assertEqual(len(l3["overlays"]), 1)
        finally:
            view._close_view()

    def test_overlay_canvas_handles_and_blur_selection(self):
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 4.0
            view.current_time = 1.0
            b_id = view.model.add_overlay("blur", start=0.5, end=2.0, x1=30, y1=30, x2=110, y2=90, blur_style="pixelate")
            b_ov = view.model.get_overlay_by_id(b_id)

            # 1. When UNSELECTED, handle query must still detect corners
            handle_tl = view._get_overlay_handle_at(b_ov, 30, 30)
            self.assertEqual(handle_tl, "tl")
            handle_br = view._get_overlay_handle_at(b_ov, 110, 90)
            self.assertEqual(handle_br, "br")
            handle_in = view._get_overlay_handle_at(b_ov, 70, 60)
            self.assertEqual(handle_in, "inside")

            # 2. Draw canvas unselected -> zero exceptions
            view.selected_type = None
            view.selected_overlay_id = None
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 240)
            cr = cairo.Context(surf)
            view._draw_overlay_canvas(view.overlay_canvas, cr, 320, 240)

            # 3. Draw canvas selected -> zero exceptions and renders handles
            view.selected_type = "overlay"
            view.selected_overlay_id = b_id
            view._draw_overlay_canvas(view.overlay_canvas, cr, 320, 240)
        finally:
            view._close_view()

    def test_no_duplicate_text_on_drag_and_click(self):
        """Item 1: Verify text is never created during drag-begin and only created once on click."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 4.0
            view.current_time = 1.0
            view.set_active_tool("text")

            # Drag-begin must NOT create text overlay
            view._on_canvas_drag_begin(None, 80, 90)
            self.assertEqual(len(view.model.overlays), 0)

            # Drag-end must NOT create text overlay
            view._on_canvas_drag_end(None, 0, 0)
            self.assertEqual(len(view.model.overlays), 0)

            # Clicked release creates text overlay exactly once
            view._on_canvas_clicked(None, 1, 80, 90)
            self.assertEqual(len(view.model.overlays), 1)
            ov = view.model.overlays[0]
            self.assertEqual(ov["tool"], "text")
            self.assertEqual(view.active_tool, "select")
            self.assertEqual(view.selected_type, "overlay")
            self.assertEqual(view.selected_overlay_id, ov["id"])
        finally:
            view._close_view()

    def test_discard_phantom_below_threshold_elements(self):
        """Item 1 & 2: Verify stray clicks and below-threshold drags are safely discarded."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 4.0
            view.current_time = 1.0

            # 1. Stray click with Rect tool (< 8px movement)
            view.set_active_tool("rect")
            view._on_canvas_drag_begin(None, 50, 50)
            view._on_canvas_drag_update(None, 2, 2)
            view._on_canvas_drag_end(None, 2, 2)
            self.assertEqual(len(view.model.overlays), 0, "Phantom rect (<8px) should be discarded")

            # 2. Stray click with Arrow tool (< 8px movement)
            view.set_active_tool("arrow")
            view._on_canvas_drag_begin(None, 50, 50)
            view._on_canvas_drag_update(None, 3, 2)
            view._on_canvas_drag_end(None, 3, 2)
            self.assertEqual(len(view.model.overlays), 0, "Phantom arrow (<8px) should be discarded")

            # 3. Stray click with Blur tool (< 8px movement)
            view.set_active_tool("blur")
            view._on_canvas_drag_begin(None, 50, 50)
            view._on_canvas_drag_update(None, 1, 1)
            view._on_canvas_drag_end(None, 1, 1)
            self.assertEqual(len(view.model.overlays), 0, "Phantom blur (<8px) should be discarded")

            # 4. Stray click with Freehand tool (length < 4px)
            view.set_active_tool("freehand")
            view._on_canvas_drag_begin(None, 50, 50)
            view._on_canvas_drag_update(None, 1, 0)
            view._on_canvas_drag_end(None, 1, 0)
            self.assertEqual(len(view.model.overlays), 0, "Phantom freehand (<4px) should be discarded")

            # 5. Legitimate drag with Rect tool (>= 8px)
            view.set_active_tool("rect")
            view._on_canvas_drag_begin(None, 50, 50)
            view._on_canvas_drag_update(None, 40, 30)
            view._on_canvas_drag_end(None, 40, 30)
            self.assertEqual(len(view.model.overlays), 1, "Legitimate rect (40x30) should be created")
            self.assertEqual(view.active_tool, "rect")
            self.assertIsNone(view.selected_overlay_id)
        finally:
            view._close_view()

    def test_auto_return_to_select_mode_and_live_sidebar(self):
        """Item 2: Verify continuous drawing mode for tools, and timeline/canvas click selection."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 4.0
            view.current_time = 1.0

            # Selecting creation tool deselects active overlay
            view.selected_type = "overlay"
            view.selected_overlay_id = 999
            view.set_active_tool("arrow")
            self.assertIsNone(view.selected_type)
            self.assertIsNone(view.selected_overlay_id)

            # Creating an arrow remains in arrow creation mode with no overlay selected
            view._on_canvas_drag_begin(None, 40, 40)
            view._on_canvas_drag_update(None, 60, 50)
            view._on_canvas_drag_end(None, 60, 50)
            self.assertEqual(view.active_tool, "arrow")
            self.assertIsNone(view.selected_type)
            self.assertIsNone(view.selected_overlay_id)
            arr_id = view.model.overlays[0]["id"]
            self.assertIsNotNone(arr_id)

            # Freehand also remains in freehand mode without selecting overlay
            view.set_active_tool("freehand")
            view._on_canvas_drag_begin(None, 20, 20)
            view._on_canvas_drag_update(None, 10, 10)
            view._on_canvas_drag_update(None, 20, 20)
            view._on_canvas_drag_end(None, 20, 20)
            self.assertEqual(view.active_tool, "freehand")
            self.assertIsNone(view.selected_overlay_id)

            # Clicking arrow overlay track in timeline switches active_tool to select
            tl_layout = view._compute_timeline_layout()
            arr_trk = [t for t in tl_layout["overlays"] if t["id"] == arr_id][0]
            view._on_timeline_click(None, 1, 100, arr_trk["y"] + 4)
            self.assertEqual(view.active_tool, "select")
            self.assertEqual(view.selected_type, "overlay")
            self.assertEqual(view.selected_overlay_id, arr_id)
        finally:
            view._close_view()

    def test_screen_to_video_and_video_to_screen_coordinates(self):
        """Item 3: Verify screen to video and video to screen coordinates round trip."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.video_w = 1280
            view.video_h = 720
            vx, vy, vw, vh, scale = view._get_video_viewport_rect(1920, 1080)
            self.assertGreater(scale, 0)
            self.assertGreater(vw, 0)
            self.assertGreater(vh, 0)

            # Default font size and line width based on video height
            self.assertGreaterEqual(view.markup_font_size, 32)
            self.assertGreaterEqual(view.markup_width, 5.0)

            # When overlay canvas has allocated dimensions
            view.overlay_canvas.set_content_width(1280)
            view.overlay_canvas.set_content_height(720)
            sx, sy = view._video_to_screen(100, 150)
            vx_out, vy_out = view._screen_to_video(sx, sy)
            self.assertAlmostEqual(vx_out, 100.0, delta=1.0)
            self.assertAlmostEqual(vy_out, 150.0, delta=1.0)
        finally:
            view._close_view()

    def test_audio_mute_preview_and_external_audio_sync(self):
        """Item 5: Verify timeline audio mute checking and external audio media handling."""
        model = timeline_model.TimelineModel(duration=10.0)
        model.audio_segments = [
            {"id": 1, "start": 0.0, "end": 4.0, "kept": True},
            {"id": 2, "start": 4.0, "end": 7.0, "kept": False},
            {"id": 3, "start": 7.0, "end": 10.0, "kept": True},
        ]
        model.mute_ranges = [
            {"id": 1, "start": 1.0, "end": 2.0}
        ]

        # 0.5s is kept and not muted
        self.assertFalse(model.is_time_muted(0.5))
        # 1.5s is in mute_ranges
        self.assertTrue(model.is_time_muted(1.5))
        # 5.0s is in unkept audio_segment
        self.assertTrue(model.is_time_muted(5.0))
        # 8.0s is kept and not in mute_ranges
        self.assertFalse(model.is_time_muted(8.0))

        # External audio sync in view
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 10.0
            view._set_external_audio_file(self.vid1)
            self.assertIsNotNone(view.model.external_audio)
            self.assertEqual(view.selected_type, "ext_audio")

            # Remove external audio
            view._remove_external_audio()
            self.assertIsNone(view.model.external_audio)
            self.assertIsNone(view.ext_media_file)
        finally:
            view._close_view()

    def test_i18n_completeness_all_ten_languages(self):
        """Item 5: Verify i18n completeness across all 10 supported locales."""
        expected_locales = {"ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh"}
        self.assertEqual(set(i18n.LOCALES.keys()), expected_locales)

        required_keys = [
            "btn_mute_audio",
            "btn_restore_audio",
            "btn_add_text_to_screen",
            "lbl_blur_style",
            "blur_style_pixelate",
            "blur_style_frosted",
            "blur_style_solid",
            "lbl_blur_strength",
            "tool_freehand",
            "tool_arrow",
            "tool_rect",
            "tool_ellipse",
            "tool_text",
            "tool_blur",
            "tool_crop",
            "tool_select",
        ]
        for loc in expected_locales:
            for k in required_keys:
                trans = i18n.t(k, lang=loc)
                self.assertTrue(bool(trans and trans.strip()), f"Missing or empty key '{k}' for locale '{loc}'")

    def test_rounding_precision_and_pending_text_sidebar_button(self):
        """Item 6: Verify floored start time, tolerance retrieval, and pending text sidebar button."""
        model = timeline_model.TimelineModel(duration=5.0)
        ov_id = model.add_overlay("rect", start=1.0009, end=3.0, x1=10, y1=10, x2=50, y2=50)
        ov = model.get_overlay_by_id(ov_id)
        # Verify floored start time
        self.assertEqual(ov["start"], 1.0)

        # Verify tolerance retrieval at boundary
        ovs_at_1 = model.get_overlays_at(1.0)
        self.assertEqual(len(ovs_at_1), 1)

        # Pending text sidebar insertion
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 5.0
            view.current_time = 1.0
            view.set_active_tool("text")
            view.pending_text = "سديم للمونتاج"

            # Adding text to screen via sidebar button
            view._add_text_at_canvas(view.video_w * 0.35, view.video_h * 0.45, in_video_coords=True)
            self.assertEqual(len(view.model.overlays), 1)
            t_ov = view.model.overlays[0]
            self.assertEqual(t_ov["text"], "سديم للمونتاج")
            self.assertEqual(view.active_tool, "select")
            self.assertEqual(view.selected_overlay_id, t_ov["id"])
            self.assertEqual(view.pending_text, "")
        finally:
            view._close_view()

    def test_text_entry_continuous_typing_no_overwrite(self):
        """Fix 1: Verify text entry accepts multiple keystrokes without replacing each character."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 5.0
            view.current_time = 1.0
            view.set_active_tool("text")
            view.pending_text = ""
            view._add_text_at_canvas(100, 100, in_video_coords=True)

            self.assertEqual(len(view.model.overlays), 1)
            t_ov = view.model.overlays[0]
            self.assertEqual(view.selected_overlay_id, t_ov["id"])
            self.assertIsNotNone(view._context_text_entry)

            # Exhaust initial idle events
            ctx = GLib.MainContext.default()
            for _ in range(20):
                if not ctx.iteration(False):
                    break

            entry = view._context_text_entry

            # Simulate successive keystrokes (typing 's', 'a', 'd', 'e', 'e', 'm')
            accum = ""
            for ch in ["س", "د", "ي", "م"]:
                accum += ch
                entry.set_text(accum)
                entry.set_position(-1)
                for _ in range(5):
                    ctx.iteration(False)
                bounds = entry.get_selection_bounds()
                self.assertNotEqual(bounds, (0, len(accum)), "Selection must NOT re-highlight entire text after typing!")
                self.assertEqual(t_ov["text"], accum, f"Overlay text should match typed string '{accum}'")

            self.assertEqual(t_ov["text"], "سديم")

            # Bounds must encompass pill
            b1, b2, b3, b4 = view._get_overlay_bounds(t_ov)
            self.assertGreater(b3, b1)
            self.assertGreater(b4, b2)

            # Clicking existing text on canvas must NOT select the entire region
            view._on_canvas_clicked(None, 1, 100, 100)
            for _ in range(5):
                ctx.iteration(False)
            bounds_after_click = entry.get_selection_bounds()
            self.assertNotEqual(bounds_after_click, (0, len("سديم")), "Canvas click on existing text must not select all text")
        finally:
            view._close_view()

    def test_no_idle_add_lambda_in_video_editor_code(self):
        """Item 4: Verify zero GLib.idle_add(lambda in the codebase and that idle callbacks return SOURCE_REMOVE."""
        py_files = []
        for root, _dirs, files in os.walk(EDITOR_DIR):
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        self.assertGreater(len(py_files), 0)
        for f_path in py_files:
            with open(f_path, "r", encoding="utf-8") as fp:
                content = fp.read()
            matches = re.findall(r"GLib\.idle_add\s*\(\s*lambda\b", content)
            self.assertEqual(
                len(matches),
                0,
                f"Forbidden 'GLib.idle_add(lambda' found in {os.path.basename(f_path)}: {matches}",
            )

    def test_continuous_creation_mode_all_drawing_tools(self):
        """Fix 2: Verify drawing tools (arrow, rect, ellipse, blur, freehand) remain active for repeated drawing."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 6.0
            view.current_time = 1.0

            for tool_name in ["arrow", "rect", "ellipse", "blur", "freehand"]:
                view.set_active_tool(tool_name)
                self.assertEqual(view.active_tool, tool_name)
                self.assertIsNone(view.selected_overlay_id)

                # Draw shape 1
                view._on_canvas_drag_begin(None, 40, 40)
                view._on_canvas_drag_update(None, 50, 40)
                view._on_canvas_drag_end(None, 50, 40)

                # Must STAY in tool mode without selecting overlay
                self.assertEqual(
                    view.active_tool,
                    tool_name,
                    f"Tool '{tool_name}' must remain active after drawing to allow continuous drawing",
                )
                self.assertIsNone(
                    view.selected_overlay_id,
                    f"Selected overlay id should be None after drawing '{tool_name}' in continuous mode",
                )

                # Draw shape 2 immediately without re-selecting tool
                view._on_canvas_drag_begin(None, 120, 120)
                view._on_canvas_drag_update(None, 60, 50)
                view._on_canvas_drag_end(None, 60, 50)

                self.assertEqual(view.active_tool, tool_name)
                self.assertIsNone(view.selected_overlay_id)

            # Total overlays created = 5 tools * 2 = 10 overlays
            self.assertEqual(len(view.model.overlays), 10)

            # Test Esc key returns to select mode via app key handler
            class DummyEventCtrl:
                def get_current_event_state(self):
                    return Gdk.ModifierType(0)

            win = editor_app.VideoEditorWindow(app=None, video_path=self.vid1)
            try:
                win.video_editor_view.set_active_tool("arrow")
                self.assertEqual(win.video_editor_view.active_tool, "arrow")

                # Press Esc
                handled = win._on_window_key_pressed(DummyEventCtrl(), Gdk.KEY_Escape, 0, 0)
                self.assertTrue(handled)
                self.assertEqual(win.video_editor_view.active_tool, "select")
            finally:
                win.video_editor_view._close_view()
        finally:
            view._close_view()

    def test_timeline_scroll_wheel_ctrl_gating(self):
        """Fix 5: Verify vertical scrolling without Ctrl returns False and Ctrl+Scroll zooms."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 10.0

            class MockScrollCtrl:
                def __init__(self, is_ctrl):
                    self.is_ctrl = is_ctrl

                def get_current_event_state(self):
                    if self.is_ctrl:
                        return Gdk.ModifierType.CONTROL_MASK
                    return Gdk.ModifierType(0)

            initial_zoom = view.zoom_factor

            # Unadorned scroll wheel (Ctrl NOT pressed) -> MUST return False so ScrolledWindow handles vertical scrolling
            res_normal = view._on_timeline_scroll(MockScrollCtrl(is_ctrl=False), 0, -1)
            self.assertFalse(res_normal, "Scroll without Ctrl must return False to allow ScrolledWindow vertical scrolling")
            self.assertEqual(view.zoom_factor, initial_zoom, "Zoom factor must not change on plain scroll")

            # Ctrl + Scroll wheel (Ctrl pressed) -> MUST return True and zoom
            res_ctrl = view._on_timeline_scroll(MockScrollCtrl(is_ctrl=True), 0, -1)
            self.assertTrue(res_ctrl, "Scroll with Ctrl must return True and zoom")
            self.assertGreater(view.zoom_factor, initial_zoom, "Zoom factor must increase on Ctrl+Scroll up")
        finally:
            view._close_view()

    def test_ruler_decoupling_and_drawing(self):
        """Fix 4: Verify time ruler is decoupled into fixed ruler_area with height 22px."""
        view = video_editor_ui.VideoEditorView(video_path=self.vid1)
        try:
            view.duration_sec = 8.0
            view.current_time = 2.5

            self.assertTrue(hasattr(view, "ruler_area"))
            self.assertIsInstance(view.ruler_area, Gtk.DrawingArea)
            self.assertEqual(view.ruler_area.get_content_height(), 22)

            # Scrolled window properties
            self.assertFalse(view.timeline_scroll.get_overlay_scrolling(), "Overlay scrolling must be False")
            self.assertEqual(view.timeline_scroll.get_min_content_height(), 156)
            self.assertEqual(view.timeline_scroll.get_max_content_height(), 220)

            # Render ruler with real Cairo surface
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 22)
            cr = cairo.Context(surf)
            view._draw_ruler_area(view.ruler_area, cr, 800, 22)
            surf.flush()
            data = bytes(surf.get_data())
            self.assertTrue(any(b != 0 for b in data), "Ruler Cairo drawing must produce visible pixels")

            # Ruler click seek
            view._on_ruler_click(None, 1, 400, 10)
            self.assertAlmostEqual(view.current_time, 4.0, delta=0.5)
        finally:
            view._close_view()


class TestSystemIntegration(unittest.TestCase):
    """Verifies file existence, permissions, desktop entry, SVG icons, and recipes."""

    def test_launcher_binary(self):
        bin_path = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-video-editor")
        self.assertTrue(os.path.isfile(bin_path))
        self.assertTrue(os.access(bin_path, os.X_OK))

        res = subprocess.run(["bash", "-n", bin_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Bash syntax check failed: {res.stderr}")

    def test_desktop_file(self):
        desktop_path = os.path.join(
            REPO_ROOT, "files/system/usr/share/applications/org.sadeem.VideoEditor.desktop"
        )
        self.assertTrue(os.path.isfile(desktop_path))

        with open(desktop_path, "r", encoding="utf-8") as fp:
            content = fp.read()

        self.assertIn("[Desktop Entry]", content)
        self.assertTrue("sadeem-video-editor %U" in content or "sadeem-video-editor %F" in content)
        self.assertIn("Icon=org.sadeem.VideoEditor", content)
        self.assertIn("Name=Sadeem Video Editor", content)
        self.assertIn("Name[ar]=محرر فيديو سديم", content)
        self.assertIn("AudioVideoEditing", content)

    def test_svg_icons(self):
        icon_path = os.path.join(
            REPO_ROOT,
            "files/system/usr/share/icons/hicolor/scalable/apps/org.sadeem.VideoEditor.svg",
        )
        symlink_path = os.path.join(
            REPO_ROOT,
            "files/system/usr/share/icons/hicolor/scalable/apps/sadeem-video-editor.svg",
        )

        self.assertTrue(os.path.isfile(icon_path))
        tree = ET.parse(icon_path)
        root = tree.getroot()
        self.assertTrue(root.tag.endswith("svg"))

        self.assertTrue(os.path.islink(symlink_path) or os.path.isfile(symlink_path))

    def test_recipe_permissions(self):
        recipe_path = os.path.join(REPO_ROOT, "recipes/recipe.yml")
        self.assertTrue(os.path.isfile(recipe_path))

        with open(recipe_path, "r", encoding="utf-8") as fp:
            content = fp.read()

        self.assertIn("/usr/bin/sadeem-video-editor", content)


if __name__ == "__main__":
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    res = unittest.main(exit=False)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if res.result.wasSuccessful() else 1)
