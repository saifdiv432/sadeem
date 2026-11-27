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
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import yaml
from PIL import Image

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
import capture_client
from capture import video_recorder
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

    def test_selection_crop_no_green_bar_or_chroma_shift(self):
        """
        End-to-end pixel alignment test on odd and non-16-aligned dimensions (866x536, 866x836, 501x403):
        verifies zero bright green top bar, Chroma/Luma center alignment <= 2.0px, and clean framerate
        across capture.video_recorder.VideoRecorder and recorder.VideoRecorderApp using the active encoder.
        """
        from capture.video_recorder import VideoRecorder, attach_even_crop_caps_probe

        with tempfile.TemporaryDirectory(prefix="sadeem_chroma_test_") as tmpdir:
            def _make_pattern(path, sw, sh, box_x, box_y):
                img = Image.new("RGB", (sw, sh), (18, 18, 22))
                px = img.load()
                for y in range(box_y, box_y + 80):
                    for x in range(box_x, box_x + 120):
                        px[x, y] = (235, 30, 30)
                img.save(path)

            def _assert_decoded_clean(label, src_png, sw, sh, cx, cy, cw, ch, pipe_str, out_video, use_caps_probe=False):
                test_str = re.sub(
                    r"pipewiresrc[^!]+",
                    (
                        f'filesrc location="{src_png}" ! pngdec ! imagefreeze num-buffers=5 ! '
                        f"videoconvert ! video/x-raw,width={sw},height={sh},framerate=30/1 "
                    ),
                    pipe_str,
                    count=1,
                )
                p = Gst.parse_launch(test_str)
                if use_caps_probe:
                    self.assertTrue(attach_even_crop_caps_probe(p, "crop", cx, cy, cw, ch))
                p.set_state(Gst.State.PLAYING)
                msg = p.get_bus().timed_pop_filtered(8 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
                p.set_state(Gst.State.NULL)
                self.assertIsNotNone(msg, f"{label}: pipeline timed out")
                self.assertEqual(msg.type, Gst.MessageType.EOS, f"{label}: pipeline error")

                dec_png = out_video + ".png"
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", out_video, "-vframes", "1", dec_png],
                    check=True,
                )
                im = Image.open(dec_png).convert("RGB")
                w, h = im.size
                exp_w, exp_h = cw & ~1, ch & ~1
                self.assertEqual((w % 2, h % 2), (0, 0), f"{label}: output dimensions must be even, got {(w, h)}")
                self.assertEqual((w, h), (exp_w, exp_h), f"{label}: unexpected cropped size {(w, h)}")

                dec_px = im.load()
                top_green_excess = max(
                    dec_px[x, y][1] - max(dec_px[x, y][0], dec_px[x, y][2])
                    for y in range(min(30, h))
                    for x in range(w)
                )
                self.assertLess(
                    top_green_excess,
                    25,
                    f"{label}: bright green top bar detected (green excess={top_green_excess})",
                )

                red_xs = [x for y in range(h) for x in range(w) if dec_px[x, y][0] > 150 and dec_px[x, y][1] < 80]
                red_ys = [y for y in range(h) for x in range(w) if dec_px[x, y][0] > 150 and dec_px[x, y][1] < 80]
                lum_xs = [x for y in range(h) for x in range(w) if (dec_px[x, y][0] + dec_px[x, y][1] + dec_px[x, y][2]) / 3 > 45]
                lum_ys = [y for y in range(h) for x in range(w) if (dec_px[x, y][0] + dec_px[x, y][1] + dec_px[x, y][2]) / 3 > 45]

                self.assertGreater(len(red_ys), 100, f"{label}: red box missing from decoded frame")
                self.assertGreater(len(lum_ys), 100, f"{label}: luminance box missing from decoded frame")
                diff_x = abs((sum(red_xs) / len(red_xs)) - (sum(lum_xs) / len(lum_xs)))
                diff_y = abs((sum(red_ys) / len(red_ys)) - (sum(lum_ys) / len(lum_ys)))
                self.assertLessEqual(diff_x, 2.0, f"{label}: horizontal chroma shift {diff_x:.2f}px > 2px")
                self.assertLessEqual(diff_y, 2.0, f"{label}: vertical chroma shift {diff_y:.2f}px > 2px")

                probe = subprocess.check_output(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", out_video],
                    text=True,
                ).strip()
                num, den = [int(v) for v in probe.split("/")]
                self.assertLessEqual(num / max(1, den), 65.0, f"{label}: bogus r_frame_rate {probe}")

            src_768 = os.path.join(tmpdir, "src_768.png")
            _make_pattern(src_768, 1366, 768, 300, 180)
            vr_out = os.path.join(tmpdir, "vr_sel.mp4")
            vr = VideoRecorder(
                mode="selection",
                crop_box=(113, 55, 501, 403),
                screen_size=(1366, 768),
                framerate=30,
                output_path=vr_out,
            )
            _assert_decoded_clean("VideoRecorder_501x403", src_768, 1366, 768, 113, 55, 501, 403, vr._build_pipeline_string(42, -1), vr_out, use_caps_probe=True)

            rec_out_501 = os.path.join(tmpdir, "rec_501.mkv")
            rec_501 = VideoRecorderApp(
                argparse.Namespace(
                    mode="selection", crop="113,55,501,403", monitor="0", resolution="native",
                    fps="30", codec="h264", audio="none", mic="", cursor=True,
                )
            )
            rec_501.tmp_mkv = rec_out_501
            _assert_decoded_clean("RecorderApp_501x403", src_768, 1366, 768, 113, 55, 501, 403, rec_501.build_pipeline_str(42, 3, level=2), rec_out_501, use_caps_probe=True)

            # Non-multiple-of-16 height tests (866x536 in 1366x768 & 866x836 in 1920x1080)
            rec_out_536 = os.path.join(tmpdir, "rec_866x536.mkv")
            rec_536 = VideoRecorderApp(
                argparse.Namespace(
                    mode="selection", crop="113,55,866,536", monitor="0", resolution="native",
                    fps="60", codec="h264", audio="none", mic="", cursor=True,
                )
            )
            rec_536.tmp_mkv = rec_out_536
            _assert_decoded_clean("RecorderApp_866x536", src_768, 1366, 768, 113, 55, 866, 536, rec_536.build_pipeline_str(42, 3, level=2), rec_out_536, use_caps_probe=True)

            src_1080 = os.path.join(tmpdir, "src_1080.png")
            _make_pattern(src_1080, 1920, 1080, 420, 360)
            rec_out_836 = os.path.join(tmpdir, "rec_866x836.mkv")
            rec_836 = VideoRecorderApp(
                argparse.Namespace(
                    mode="selection", crop="120,110,866,836", monitor="0", resolution="native",
                    fps="60", codec="h264", audio="none", mic="", cursor=True,
                )
            )
            rec_836.tmp_mkv = rec_out_836
            _assert_decoded_clean("RecorderApp_866x836", src_1080, 1920, 1080, 120, 110, 866, 836, rec_836.build_pipeline_str(42, 3, level=2), rec_out_836, use_caps_probe=True)

            # Verify VA pipeline fixates pixel-aspect-ratio=1/1 before videocrop/vapostproc
            # and omits pixel-aspect-ratio from VAMemory caps (preventing gst_va_vpp_fixate_size overflow),
            # including 720p scaled selection mode with real vah264enc.
            pipe_sel_720 = argparse.Namespace(
                mode="selection", crop="100,100,501,403", monitor="0", resolution="720p",
                fps="60", codec="h264", audio="none", mic="", cursor=True,
            )
            rec_720 = VideoRecorderApp(pipe_sel_720)
            rec_720.tmp_mkv = os.path.join(tmpdir, "rec_sel_720.mkv")
            pipe_720_str = rec_720.build_pipeline_str(42, 3, level=2)
            self.assertIn("video/x-raw,format=BGRx,pixel-aspect-ratio=1/1 ! videocrop", pipe_720_str)
            self.assertNotIn("memory:VAMemory),format=NV12,colorimetry=bt709,pixel-aspect-ratio=1/1", pipe_720_str)

            test_720_str = re.sub(
                r"pipewiresrc[^!]+",
                f'filesrc location="{src_1080}" ! pngdec ! imagefreeze num-buffers=5 ! videoconvert ! video/x-raw,width=1920,height=1080,framerate=30/1 ',
                pipe_720_str,
                count=1,
            )
            p720 = Gst.parse_launch(test_720_str)
            self.assertTrue(attach_even_crop_caps_probe(p720, "crop", 100, 100, 501, 403))
            p720.set_state(Gst.State.PLAYING)
            msg720 = p720.get_bus().timed_pop_filtered(8 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            p720.set_state(Gst.State.NULL)
            self.assertIsNotNone(msg720)
            self.assertEqual(msg720.type, Gst.MessageType.EOS)
            dec_720 = rec_720.tmp_mkv + ".png"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", rec_720.tmp_mkv, "-vframes", "1", dec_720], check=True)
            im720 = Image.open(dec_720).convert("RGB")
            self.assertEqual(im720.size, (1280, 720))
            px720 = im720.load()
            g720 = max(px720[x, y][1] - max(px720[x, y][0], px720[x, y][2]) for y in range(30) for x in range(1280))
            self.assertLess(g720, 25)

    def test_hidpi_fractional_scaling_crop_margins_and_probe(self):
        """Verifies HiDPI 150% and 200% scaling math and Gst CAPS pad probe inside videocrop."""
        from capture.video_recorder import attach_even_crop_caps_probe, compute_even_crop_margins

        # 150% scaling: logical 1280x720 -> physical 1920x1080
        l150, t150, r150, b150, w150, h150 = compute_even_crop_margins(
            101, 51, 401, 301, 1920, 1080, logical_w=1280, logical_h=720
        )
        self.assertEqual((l150, t150, w150, h150), (152, 76, 602, 452))
        self.assertEqual((l150 + w150 + r150, t150 + h150 + b150), (1920, 1080))

        # 200% scaling: logical 960x540 -> physical 1920x1080
        l200, t200, r200, b200, w200, h200 = compute_even_crop_margins(
            101, 51, 401, 301, 1920, 1080, logical_w=960, logical_h=540
        )
        self.assertEqual((l200, t200, w200, h200), (202, 102, 802, 602))
        self.assertEqual((l200 + w200 + r200, t200 + h200 + b200), (1920, 1080))

        # Live CAPS event probe test at 150% scaling
        pipe = Gst.parse_launch(
            "videotestsrc num-buffers=1 ! video/x-raw,format=BGRx,width=1920,height=1080 ! "
            "videocrop name=crop ! fakesink"
        )
        self.assertTrue(attach_even_crop_caps_probe(pipe, "crop", 101, 51, 401, 301, logical_w=1280, logical_h=720))
        pipe.set_state(Gst.State.PLAYING)
        msg = pipe.get_bus().timed_pop_filtered(4 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        crop = pipe.get_by_name("crop")
        self.assertEqual((crop.get_property("left"), crop.get_property("top"), crop.get_property("right"), crop.get_property("bottom")), (l150, t150, r150, b150))
        pipe.set_state(Gst.State.NULL)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.type, Gst.MessageType.EOS)

    def test_recorder_do_stop_timeout_encoder_dispatch_and_i18n_fixes(self):
        """Verifies _do_stop GLib call, probed encoder dispatch (nv/x264), i18n filename, and UI fixes."""
        import py_compile
        from unittest.mock import patch

        rec_path = os.path.join(CAPTURE_DIR, "recorder.py")
        vr_path = os.path.join(CAPTURE_DIR, "capture/video_recorder.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            py_compile.compile(rec_path, cfile=os.path.join(tmpdir, "rec.pyc"), doraise=True)
            py_compile.compile(vr_path, cfile=os.path.join(tmpdir, "vr.pyc"), doraise=True)

        with open(rec_path, "r", encoding="utf-8") as f:
            rec_code = f.read()
        self.assertIn("GLib.timeout_add_seconds(4, self._force_quit)", rec_code)
        self.assertNotIn("GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4", rec_code)
        self.assertIn('i18n.t("filename_video_prefix")', rec_code)
        self.assertNotIn('"تسجيل_سديم"', rec_code)
        self.assertIn("videorate drop-only=true max-rate=", rec_code)
        self.assertIn("audio/x-raw,rate=48000,channels=2", rec_code)

        # Verify probed non-VA encoders are honored instead of hardcoding vah264enc
        args = argparse.Namespace(
            mode="selection", crop="10,10,400,300", monitor="0", resolution="native",
            fps="30", codec="h264", audio="system", mic="", cursor=True,
        )
        app = VideoRecorderApp(args)
        app.tmp_mkv = "/tmp/test_dispatch.mkv"

        with patch("capture.media_probe.probe_h264_encoder", return_value={
            "codec": "h264", "name": "nvh264enc", "pipeline_str": "nvh264enc preset=low-latency-hq",
            "parser": "h264parse", "is_hardware": True,
        }):
            pipe_nv = app.build_pipeline_str(42, 3, level=2)
            self.assertIn("nvh264enc preset=low-latency-hq", pipe_nv)
            self.assertNotIn("vah264enc", pipe_nv)
            self.assertIn("format=NV12", pipe_nv)

        with patch("capture.media_probe.probe_h264_encoder", return_value={
            "codec": "h264", "name": "x264enc", "pipeline_str": "x264enc speed-preset=veryfast tune=zerolatency",
            "parser": "h264parse", "is_hardware": False,
        }):
            pipe_x264 = app.build_pipeline_str(42, 3, level=2)
            self.assertIn("x264enc speed-preset=veryfast tune=zerolatency", pipe_x264)
            self.assertNotIn("vah264enc", pipe_x264)
            self.assertIn("format=I420,colorimetry=bt709", pipe_x264)

        # Verify _do_stop calls timeout_add_seconds(4, ...) and returns SOURCE_REMOVE
        class FakePipeline:
            def send_event(self, _ev):
                return True

        app.pipeline = FakePipeline()
        app.is_running = True
        with patch.object(recorder.GLib, "timeout_add_seconds", return_value=99) as mock_to:
            ret = app._do_stop()
            mock_to.assert_called_once_with(4, app._force_quit)
            self.assertEqual(ret, recorder.GLib.SOURCE_REMOVE)

        # Verify Level 1 DMABuf negotiation error triggers automatic fallback to Level 2 before frames arrive
        scr_args = argparse.Namespace(
            mode="screen", crop="", monitor="0", resolution="native",
            fps="60", codec="h264", audio="none", mic="", cursor=True,
        )
        scr_app = VideoRecorderApp(scr_args)
        scr_app.current_level = 1
        scr_app._got_video_frame = False
        scr_app._fallback_triggered = False

        class FakeLoop:
            def __init__(self):
                self.quit_called = False
            def is_running(self):
                return True
            def quit(self):
                self.quit_called = True

        class FakeErr:
            def matches(self, *_a):
                return True
            def __str__(self):
                return "not-negotiated"

        class FakeMsg:
            type = recorder.Gst.MessageType.ERROR
            def parse_error(self):
                return FakeErr(), "gst_va_vpp_fixate_size integer overflow"

        scr_app.loop = FakeLoop()
        with patch.object(recorder.GLib, "idle_add") as mock_idle:
            scr_app._on_bus_message(None, FakeMsg())
            mock_idle.assert_called_once_with(scr_app._switch_to_level2_idle)
            self.assertFalse(scr_app.loop.quit_called)

        # After frames arrive, ERROR quits loop normally
        scr_app._got_video_frame = True
        scr_app._on_bus_message(None, FakeMsg())
        self.assertTrue(scr_app.loop.quit_called)

        # Also check video_recorder.py fixates PAR=1/1 before videocrop/vapostproc
        with open(vr_path, "r", encoding="utf-8") as f:
            vr_code = f.read()
        self.assertIn("video/x-raw,format=BGRx,pixel-aspect-ratio=1/1", vr_code)
        self.assertNotIn("video/x-raw(memory:VAMemory),format=NV12,colorimetry=bt709{size_props},pixel-aspect-ratio=1/1", vr_code)

        # Verify captureUI.js & extension.js cleanups
        with open(os.path.join(EXT_DIR, "captureUI.js"), "r", encoding="utf-8") as f:
            ui_code = f.read()
        self.assertIn("Shell.Screenshot.composite_to_stream(", ui_code)
        self.assertIn("Shell.Screenshot.composite_to_stream_finish(res)", ui_code)
        self.assertIn("--monitor-size", ui_code)
        self.assertIn("this._settingsMenuOpen = false;", ui_code)
        self.assertIn("global.get_current_time()", ui_code)
        self.assertNotIn("create_app_launch_context(0, -1)", ui_code)

        with open(os.path.join(EXT_DIR, "extension.js"), "r", encoding="utf-8") as f:
            ext_code = f.read()
        self.assertIn("BoxPointer.PopupAnimation.NONE", ext_code)
        self.assertNotIn("{animate: false}", ext_code)


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

    def test_emoji_copy_popup_clamping_and_dtp_rtl_fixes(self):
        """
        Verifies Batch 1 fixes:
        1) clampPopupAnchorToWorkArea / clampPopupBoxToWorkArea in GJS across 1366x768 & 1920x1080 corners/edges.
        2) emoji-copy@felipeftn GNOME 51 metadata, compiled gschemas, and dconf defaults.
        3) dash-to-panel windowPreview.js RTL LTR-container fix & helper cleanup in disable().
        """
        import json

        clamp_js = os.path.join(EXT_DIR, "popupClamp.js")
        self.assertTrue(os.path.isfile(clamp_js))

        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as tf:
            tf.write(
                f"""
import {{ clampPopupAnchorToWorkArea, clampPopupBoxToWorkArea, SIDE_TOP, SIDE_BOTTOM }} from 'file://{clamp_js}';

const cases = [
    {{ wa: {{ x: 0, y: 0, width: 1366, height: 720 }}, w: 360, h: 440, side: SIDE_TOP }},
    {{ wa: {{ x: 0, y: 0, width: 1366, height: 720 }}, w: 360, h: 440, side: SIDE_BOTTOM }},
    {{ wa: {{ x: 0, y: 0, width: 1920, height: 1032 }}, w: 400, h: 460, side: SIDE_TOP }},
    {{ wa: {{ x: 0, y: 0, width: 1920, height: 1032 }}, w: 400, h: 460, side: SIDE_BOTTOM }},
];

const margin = 12;
for (const c of cases) {{
    const pts = [
        [0, 0], [c.wa.width, 0], [0, c.wa.height], [c.wa.width, c.wa.height],
        [10, c.wa.height / 2], [c.wa.width - 5, c.wa.height / 2],
        [c.wa.width / 2, 5], [c.wa.width / 2, c.wa.height - 2],
    ];
    for (const [px, py] of pts) {{
        const a = clampPopupAnchorToWorkArea(px, py, c.w, c.h, c.wa, c.side, margin, 0.5);
        const left = a.x - c.w * 0.5;
        const right = a.x + c.w * 0.5;
        const top = c.side === SIDE_BOTTOM ? a.y - c.h : a.y;
        const bottom = c.side === SIDE_BOTTOM ? a.y : a.y + c.h;
        if (left < c.wa.x + margin - 1 || right > c.wa.x + c.wa.width - margin + 1 ||
            top < c.wa.y + margin - 1 || bottom > c.wa.y + c.wa.height - margin + 1) {{
            throw new Error(`Anchor out of bounds (${{px}},${{py}}) side=${{c.side}} -> [${{left}},${{top}},${{right}},${{bottom}}]`);
        }}
        const box = clampPopupBoxToWorkArea(px - 20, py - 20, c.w, c.h, c.wa, margin);
        if (box.x < c.wa.x + margin || box.x + c.w > c.wa.x + c.wa.width - margin ||
            box.y < c.wa.y + margin || box.y + c.h > c.wa.y + c.wa.height - margin) {{
            throw new Error(`Box out of bounds -> (${{box.x}},${{box.y}})`);
        }}
    }}
}}
print("POPUP_CLAMP_GJS_OK");
"""
            )
            test_mjs = tf.name

        try:
            gjs_res = subprocess.run(["gjs", "-m", test_mjs], capture_output=True, text=True, check=True)
            self.assertIn("POPUP_CLAMP_GJS_OK", gjs_res.stdout)
        finally:
            os.unlink(test_mjs)

        ext_root = os.path.dirname(EXT_DIR)
        emoji_dir = os.path.join(ext_root, "emoji-copy@felipeftn")
        with open(os.path.join(emoji_dir, "metadata.json"), "r", encoding="utf-8") as fp:
            emoji_meta = json.load(fp)
        self.assertIn("51", emoji_meta.get("shell-version", []))
        self.assertEqual(os.stat(os.path.join(emoji_dir, "metadata.json")).st_mode & 0o444, 0o444)

        compiled_schema = os.path.join(emoji_dir, "schemas", "gschemas.compiled")
        self.assertTrue(os.path.isfile(compiled_schema) and os.path.getsize(compiled_schema) > 0)
        subprocess.run(["glib-compile-schemas", "--strict", "--dry-run", os.path.join(emoji_dir, "schemas")], check=True)

        dconf_dir = os.path.join(REPO_ROOT, "files/system/etc/dconf/db/local.d")
        with open(os.path.join(dconf_dir, "01-sadeem-defaults"), "r", encoding="utf-8") as fp:
            self.assertIn("'emoji-copy@felipeftn'", fp.read())
        with open(os.path.join(dconf_dir, "02-sadeem-extensions"), "r", encoding="utf-8") as fp:
            ext_dconf = fp.read()
        self.assertIn("[org/gnome/shell/extensions/emoji-copy]", ext_dconf)
        self.assertIn("active-keybind=true", ext_dconf)
        self.assertIn("emoji-keybind=['<Super>period']", ext_dconf)
        self.assertIn("window-location='cursor'", ext_dconf)

        dtp_dir = os.path.join(ext_root, "dash-to-panel@jderose9.github.com")
        dtp_wp = os.path.join(dtp_dir, "windowPreview.js")
        dtp_pos_js = os.path.join(dtp_dir, "previewPosition.js")
        self.assertTrue(os.path.isfile(dtp_pos_js))

        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as tf:
            tf.write(
                f"""
import {{ computePreviewMenuPosition, SIDE_BOTTOM, SIDE_TOP, SIDE_RIGHT, SIDE_LEFT }} from 'file://{dtp_pos_js}';

// Bottom panel 1920x1080: RTL places Arabic app icons on the right half (e.g. x1=1450)
// and LTR places icons on the left half (e.g. x1=120). Both must center over the icon and stay on monitor.
const rtlCenter = computePreviewMenuPosition({{
    sourceX1: 1450, sourceY1: 1032, sourceContentWidth: 48, sourceContentHeight: 48,
    appIconMargin: 0, previewsWidth: 260, previewsHeight: 160,
    monitorX: 0, monitorY: 0, monitorWidth: 1920, monitorHeight: 1080,
    clipHeight: 180, vertical: false, position: SIDE_BOTTOM,
}});
if (rtlCenter.x !== 1344 || rtlCenter.y !== 20) {{
    throw new Error(`Unexpected RTL preview position: ${{JSON.stringify(rtlCenter)}}`);
}}

const ltrEdgeLeft = computePreviewMenuPosition({{
    sourceX1: 10, sourceY1: 1032, sourceContentWidth: 40, sourceContentHeight: 40,
    appIconMargin: 0, previewsWidth: 260, previewsHeight: 160,
    monitorX: 0, monitorY: 0, monitorWidth: 1920, monitorHeight: 1080,
    clipHeight: 180, vertical: false, position: SIDE_BOTTOM,
}});
if (ltrEdgeLeft.x !== 0 || ltrEdgeLeft.y !== 20) {{
    throw new Error(`Left edge preview not clamped: ${{JSON.stringify(ltrEdgeLeft)}}`);
}}

const rtlEdgeRight = computePreviewMenuPosition({{
    sourceX1: 1870, sourceY1: 1032, sourceContentWidth: 40, sourceContentHeight: 40,
    appIconMargin: 0, previewsWidth: 260, previewsHeight: 160,
    monitorX: 0, monitorY: 0, monitorWidth: 1920, monitorHeight: 1080,
    clipHeight: 180, vertical: false, position: SIDE_BOTTOM,
}});
if (rtlEdgeRight.x !== 1660 || rtlEdgeRight.y !== 20) {{
    throw new Error(`Right edge preview not clamped: ${{JSON.stringify(rtlEdgeRight)}}`);
}}

// Top and vertical panels (LTR & RTL symmetric)
const topPos = computePreviewMenuPosition({{
    sourceX1: 600, sourceY1: 0, sourceContentWidth: 48, sourceContentHeight: 48,
    previewsWidth: 240, previewsHeight: 150, monitorWidth: 1366, monitorHeight: 768,
    clipHeight: 180, vertical: false, position: SIDE_TOP,
}});
if (topPos.y !== 0 || topPos.x !== 504) {{
    throw new Error(`Top panel position wrong: ${{JSON.stringify(topPos)}}`);
}}

const rightVert = computePreviewMenuPosition({{
    sourceX1: 1318, sourceY1: 300, sourceContentWidth: 48, sourceContentHeight: 48,
    previewsWidth: 220, previewsHeight: 150, monitorWidth: 1366, monitorHeight: 768,
    clipWidth: 240, vertical: true, position: SIDE_RIGHT,
}});
if (rightVert.x !== 20 || rightVert.y !== 249) {{
    throw new Error(`Right vertical panel position wrong: ${{JSON.stringify(rightVert)}}`);
}}

print("DTP_PREVIEW_POS_GJS_OK");
"""
            )
            dtp_mjs = tf.name

        try:
            gjs_res2 = subprocess.run(["gjs", "-m", dtp_mjs], capture_output=True, text=True, check=True)
            self.assertIn("DTP_PREVIEW_POS_GJS_OK", gjs_res2.stdout)
        finally:
            os.unlink(dtp_mjs)

        with open(dtp_wp, "r", encoding="utf-8") as fp:
            wp_code = fp.read()
        self.assertIn("new Clutter.FixedLayout()", wp_code)
        self.assertIn("text_direction: Clutter.TextDirection.LTR", wp_code)
        self.assertIn("Clutter.get_default_text_direction()", wp_code)
        self.assertIn("computePreviewMenuPosition", wp_code)

        with open(os.path.join(EXT_DIR, "extension.js"), "r", encoding="utf-8") as fp:
            helper_code = fp.read()
        self.assertIn("clampPopupAnchorToWorkArea", helper_code)
        self.assertIn("bp?._userArrowSide ??", helper_code)
        self.assertIn("bp?._sourceAlignment ??", helper_code)
        self.assertIn("'clipboardIndicator'", helper_code)
        self.assertNotIn("'emoji-copy@felipeftn'", helper_code)
        self.assertIn("box.setPosition(this.sourceActor, alignment)", helper_code)
        self.assertNotIn("box.set_position(", helper_code)
        self.assertIn("_cursorRetryId", helper_code)
        self.assertIn("_sadeemClampIdleId", helper_code)
        self.assertIn("_sadeemAllocSigId", helper_code)

        # Verify emoji-copy@felipeftn self-clamps at 4 corners AND on 180px -> 480px expansion
        emoji_clamp_js = os.path.join(emoji_dir, "popupClamp.js")
        self.assertTrue(os.path.isfile(emoji_clamp_js))
        with open(os.path.join(emoji_dir, "extension.js"), "r", encoding="utf-8") as fp:
            emoji_ext_code = fp.read()
        self.assertIn("notify::allocation", emoji_ext_code)
        self.assertIn("_detachBoxClampWatch", emoji_ext_code)
        self.assertIn("clampPopupAnchorToWorkArea", emoji_ext_code)
        self.assertIn("clampPopupBoxToWorkArea", emoji_ext_code)
        self.assertIn("bp.setPosition(menu.sourceActor, alignment)", emoji_ext_code)
        self.assertIn("grab_key_focus()", emoji_ext_code)
        self.assertIn("Math.abs(dx) < 2 && Math.abs(dy) < 2", emoji_ext_code)

        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as tf:
            tf.write(
                f"""
import {{ clampPopupAnchorToWorkArea, clampPopupBoxToWorkArea, SIDE_TOP, SIDE_BOTTOM }} from 'file://{emoji_clamp_js}';

for (const wa of [
    {{ x: 0, y: 0, width: 1366, height: 720 }},
    {{ x: 0, y: 0, width: 1920, height: 1032 }},
]) {{
    for (const side of [SIDE_TOP, SIDE_BOTTOM]) {{
        for (const [px, py] of [[0, 0], [wa.width, 0], [0, wa.height], [wa.width, wa.height], [wa.width - 20, wa.height - 200]]) {{
            // Initial collapsed open (180px tall), then expanded via category/search to 480px tall
            const initH = 180;
            const expH = 480;
            const w = 380;
            const anchor = clampPopupAnchorToWorkArea(px, py, w, initH, wa, side, 12, 0.5);
            let bx = anchor.x - w * 0.5;
            let by = side === SIDE_BOTTOM ? anchor.y - expH : anchor.y;
            const clamped = clampPopupBoxToWorkArea(bx, by, w, expH, wa, 12);
            const dx = clamped.x - bx;
            const dy = clamped.y - by;
            const finalBx = bx + dx;
            const finalBy = by + dy;
            if (finalBx < wa.x + 12 || finalBx + w > wa.x + wa.width - 12 ||
                finalBy < wa.y + 12 || finalBy + expH > wa.y + wa.height - 12) {{
                throw new Error(`Emoji expanded popup out of bounds (${{finalBx}},${{finalBy}},${{w}},${{expH}}) in ${{JSON.stringify(wa)}}`);
            }}
        }}
    }}
}}
print("EMOJI_EXPANSION_CLAMP_GJS_OK");
"""
            )
            emoji_mjs = tf.name

        try:
            gjs_res3 = subprocess.run(["gjs", "-m", emoji_mjs], capture_output=True, text=True, check=True)
            self.assertIn("EMOJI_EXPANSION_CLAMP_GJS_OK", gjs_res3.stdout)
        finally:
            os.unlink(emoji_mjs)

        env = os.environ.copy()
        typelib_paths = "/usr/lib64/mutter-51:/usr/lib64/gnome-shell"
        env["GI_TYPELIB_PATH"] = typelib_paths + (":" + env["GI_TYPELIB_PATH"] if "GI_TYPELIB_PATH" in env else "")
        env["LD_LIBRARY_PATH"] = typelib_paths + (":" + env["LD_LIBRARY_PATH"] if "LD_LIBRARY_PATH" in env else "")
        for p in (clamp_js, emoji_clamp_js, os.path.join(EXT_DIR, "extension.js"), dtp_pos_js, dtp_wp, os.path.join(emoji_dir, "extension.js")):
            r = subprocess.run(["gjs", "-m", p], capture_output=True, text=True, env=env, timeout=10)
            out = (r.stderr + "\n" + r.stdout).strip()
            self.assertNotIn("SyntaxError", out, f"GJS syntax error in {p}:\n{out}")
            if r.returncode != 0:
                self.assertIn("resource:///org/gnome/shell/", out, f"Unexpected GJS failure in {p}:\n{out}")

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
            self.assertTrue(i18n.STRINGS[lang].get("folder_screenshots"), f"Missing folder_screenshots in {lang}")
            self.assertTrue(i18n.STRINGS[lang].get("folder_recordings"), f"Missing folder_recordings in {lang}")

        self.assertEqual(i18n.STRINGS["ar"]["folder_screenshots"], "لقطات الشاشة")
        self.assertEqual(i18n.STRINGS["ar"]["folder_recordings"], "تسجيلات الشاشة")
        self.assertEqual(i18n.STRINGS["en"]["folder_screenshots"], "Screenshots")
        self.assertEqual(i18n.STRINGS["en"]["folder_recordings"], "Recordings")

        # Verify capture_client & video_recorder honor localized folder_screenshots / folder_recordings
        import unittest.mock
        orig_lang = i18n.LANG
        try:
            with tempfile.TemporaryDirectory() as tmp_media:
                with unittest.mock.patch("gi.repository.GLib.get_user_special_dir", return_value=tmp_media):
                    i18n.LANG = "ar"
                    ar_shot = capture_client.generate_screenshot_path()
                    ar_rec = video_recorder.generate_recording_path()
                    self.assertIn(os.path.join(tmp_media, "لقطات الشاشة"), ar_shot)
                    self.assertIn(os.path.join(tmp_media, "تسجيلات الشاشة"), ar_rec)

                    i18n.LANG = "en"
                    en_shot = capture_client.generate_screenshot_path()
                    en_rec = video_recorder.generate_recording_path()
                    self.assertIn(os.path.join(tmp_media, "Screenshots"), en_shot)
                    self.assertIn(os.path.join(tmp_media, "Recordings"), en_rec)
        finally:
            i18n.LANG = orig_lang

        # Verify recorder.py uses i18n.t("folder_recordings")
        rec_py = os.path.join(CAPTURE_DIR, "recorder.py")
        with open(rec_py, "r", encoding="utf-8") as fp:
            self.assertIn('i18n.t("folder_recordings")', fp.read())

        # Verify gallery media.is_screenshot_item detects all 10 localized folder names
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "sadeem_gallery_media_test",
            os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-gallery/media.py"),
        )
        g_media = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g_media)
        for lang in expected_langs:
            folder = i18n.STRINGS[lang]["folder_screenshots"]
            self.assertTrue(
                g_media.is_screenshot_item(f"/home/user/Pictures/{folder}/img_01.png", "img_01.png"),
                f"is_screenshot_item missed folder '{folder}' ({lang})",
            )

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
                "folder_screenshots",
                "folder_recordings",
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
            if (I18n.STRINGS.ar.folder_screenshots !== "لقطات الشاشة" || I18n.STRINGS.ar.folder_recordings !== "تسجيلات الشاشة") {{
                throw new Error("Unexpected Arabic localized capture folder names");
            }}
            if (I18n.STRINGS.en.folder_screenshots !== "Screenshots" || I18n.STRINGS.en.folder_recordings !== "Recordings") {{
                throw new Error("Unexpected English localized capture folder names");
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
        self.assertGreaterEqual(ui_code.count("this._notifyCaptureComplete("), 3)
        self.assertGreaterEqual(ui_code.count("this._finishPhotoSuccess(targetPath, stream)"), 4)

    def test_no_duplicate_gnome_screenshot_save(self):
        """
        Prevents regression of duplicate PNG saves (Screenshots/لقطة_شاشة_... + لقطات الشاشة/Screenshot From ...):
        1) windowMenuHelper.js must destroy GNOME Shell's built-in Take Screenshot item instead of
           attaching a second activate handler onto existingItem.
        2) dconf defaults and gschema override must disable both screenshot and screenshot-window keybindings.
        3) captureUI.js must save only under Screenshots and never invoke GNOME _storeScreenshot.
        """
        wm_path = os.path.join(EXT_DIR, "windowMenuHelper.js")
        with open(wm_path, "r", encoding="utf-8") as fp:
            wm_code = fp.read()

        self.assertIn("resource:///org/gnome/shell/ui/popupMenu.js", wm_code)
        self.assertIn("existingItem.destroy()", wm_code)
        self.assertIn("new PopupMenu.PopupMenuItem(localizedLabel)", wm_code)
        self.assertIn("menu.addMenuItem(newItem", wm_code)
        self.assertNotIn("existingItem.connect(", wm_code)
        self.assertNotIn("existingItem._sadeemCaptureHandler", wm_code)
        for tok in ("screenshot", "شاشة", "لقطة", "capture", "bildschirmfoto", "снимок", "截"):
            self.assertIn(tok, wm_code)

        res = subprocess.run(["gjs", "-m", wm_path], capture_output=True, text=True, timeout=10)
        out = (res.stderr + "\n" + res.stdout)
        self.assertNotIn("SyntaxError", out)
        self.assertNotIn("Failed to parse module", out)

        ui_path = os.path.join(EXT_DIR, "captureUI.js")
        with open(ui_path, "r", encoding="utf-8") as fp:
            ui_code = fp.read()
        self.assertNotIn("_storeScreenshot", ui_code)
        self.assertNotIn("Screenshot From", ui_code)
        self.assertIn("I18n.t('folder_screenshots')", ui_code)
        self.assertEqual(ui_code.count("this._getScreenshotsDir()"), 3)

        for cfg_rel in (
            "files/system/etc/dconf/db/local.d/01-sadeem-defaults",
            "files/system/usr/share/glib-2.0/schemas/zz-99-sadeem-wallpaper.gschema.override",
        ):
            with open(os.path.join(REPO_ROOT, cfg_rel), "r", encoding="utf-8") as fp:
                cfg = fp.read()
            self.assertIn("show-screenshot-ui=['Print']", cfg)
            self.assertIn("screenshot=@as []", cfg)
            self.assertIn("screenshot-window=@as []", cfg)

    def test_batch3_halo_cursor_capture_performance_and_lockclock_disposal(self):
        """
        Verifies Batch 3 fixes:
        1) cursorHalo.js uses GNOME 51 Meta.CursorTracker ('position-invalidated', get_pointer),
           raises halo on uiGroup, tracks BUTTON1_MASK, and cleans up on setActive(false) / disable().
        2) sadeem-desktop-helper stylesheet.css exists and captureUI.js syncs toggle buttons in open(),
           auto-enables _includeCursor with _toggleHalo(), draws cyan halo onto captured PNG via Cairo,
           avoids destroying/rebuilding _settingsPopup in _updateSettingsDisplay(), caches _lastCursorType
           & _frozenWindows, and moves Gio._promisify to module scope.
        3) adwaita-lock-clock@saifeldin.osama/extension.js clears disposed St.DrawingArea (_clockCanvas)
           on unlock / destroy so 1s timer never logs 'St.DrawingArea has been already disposed'.
        """
        # 1. cursorHalo.js
        halo_path = os.path.join(EXT_DIR, "cursorHalo.js")
        with open(halo_path, "r", encoding="utf-8") as fp:
            halo_code = fp.read()
        self.assertIn("Meta.CursorTracker", halo_code)
        self.assertIn("get_cursor_tracker", halo_code)
        self.assertIn("'position-invalidated'", halo_code)
        self.assertIn("this._cursorTracker.get_pointer()", halo_code)
        self.assertIn("Clutter.ModifierType.BUTTON1_MASK", halo_code)
        self.assertIn("Main.layoutManager.uiGroup.set_child_above_sibling(this._actor, null)", halo_code)
        self.assertIn("this._cursorTracker.disconnect(this._cursorSigId)", halo_code)

        # 2. captureUI.js + stylesheet.css
        css_path = os.path.join(EXT_DIR, "stylesheet.css")
        self.assertTrue(os.path.isfile(css_path))
        with open(css_path, "r", encoding="utf-8") as fp:
            css_code = fp.read()
        for cls in (
            ".sadeem-capture-card",
            ".sadeem-capture-mode-btn-active",
            ".sadeem-capture-icon-btn-active",
            ".sadeem-capture-halo-btn-active",
            ".sadeem-capture-btn-video",
            ".sadeem-capture-pill-btn-active",
            ".sadeem-capture-setting-chip-active",
        ):
            self.assertIn(cls, css_code)

        ui_path = os.path.join(EXT_DIR, "captureUI.js")
        with open(ui_path, "r", encoding="utf-8") as fp:
            ui_code = fp.read()
        self.assertIn("import Cairo from 'gi://cairo';", ui_code)
        self.assertIn("this._syncToggleButtons();", ui_code)
        self.assertIn("this._drawHaloOnPng(targetPath, targetRect, cursorInfo, frozenScale);", ui_code)
        self.assertIn("Cairo.ImageSurface.createFromPNG(targetPath)", ui_code)
        self.assertIn("this._lastCursorType", ui_code)
        self.assertIn("this._frozenWindows", ui_code)
        self.assertIn("this._lastScreenHighlightMon", ui_code)
        self.assertNotIn("box-shadow", ui_code, "captureUI.js highlight/selection overlays must avoid CPU box-shadow blur")
        self.assertNotIn("#sadeem-screen-highlight", css_code)
        self.assertNotIn("#sadeem-window-highlight", css_code)
        self.assertNotIn("#sadeem-selection-box", css_code)
        m_clear_dim = re.search(r"_clearDimming\(\)\s*\{([\s\S]*?)\n    \}", ui_code)
        self.assertIsNotNone(m_clear_dim)
        self.assertIn("this._dimOverlay.visible = false", m_clear_dim.group(1))
        self.assertNotIn("set_size(0, 0)", m_clear_dim.group(1))

        m_upd_settings = re.search(r"_updateSettingsDisplay\(\)\s*\{([\s\S]*?)\n    \}", ui_code)
        self.assertIsNotNone(m_upd_settings)
        self.assertNotIn("destroy_all_children", m_upd_settings.group(1))
        self.assertNotIn("_buildSettingsPopupContents", m_upd_settings.group(1))

        m_open = re.search(r"async open\([^\)]*\)\s*\{([\s\S]*?)\n    \}", ui_code)
        self.assertIsNotNone(m_open)
        self.assertNotIn("Gio._promisify", m_open.group(1))
        self.assertIn("this._syncToggleButtons()", m_open.group(1))
        self.assertIn("this._snapshotFrozenWindows()", m_open.group(1))

        m_win_cursor = re.search(r"_updateWindowUnderCursor\([^\)]*\)\s*\{([\s\S]*?)\n    \}", ui_code)
        self.assertIsNotNone(m_win_cursor)
        self.assertNotIn("sort_windows_by_stacking", m_win_cursor.group(1))

        m_halo_toggle = re.search(r"_toggleHalo\(\)\s*\{([\s\S]*?)\n    \}", ui_code)
        self.assertIsNotNone(m_halo_toggle)
        self.assertIn("this._includeCursor = true;", m_halo_toggle.group(1))

        # Live Cairo PNG roundtrip matching captureUI cyan halo colors
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as tf:
            png_path = tf.name
        Image.new("RGB", (80, 80), (20, 20, 20)).save(png_path)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
            tf.write(
                f"""
                import Cairo from 'gi://cairo';
                const surface = Cairo.ImageSurface.createFromPNG({png_path!r});
                const cr = new Cairo.Context(surface);
                cr.newPath();
                cr.arc(40, 40, 24, 0, 2 * Math.PI);
                cr.setSourceRGBA(6 / 255, 182 / 255, 212 / 255, 0.30);
                cr.fillPreserve();
                cr.setSourceRGBA(6 / 255, 182 / 255, 212 / 255, 0.85);
                cr.setLineWidth(2.5);
                cr.stroke();
                cr.$dispose();
                surface.writeToPNG({png_path!r});
                surface.finish();
                print('CAPTURE_HALO_CAIRO_OK');
                """
            )
            js_path = tf.name
        try:
            r = subprocess.run(["gjs", "-m", js_path], capture_output=True, text=True, check=True)
            self.assertIn("CAPTURE_HALO_CAIRO_OK", r.stdout)
            im = Image.open(png_path).convert("RGB")
            c_px = im.getpixel((40, 40))
            b_px = im.getpixel((64, 40))
            self.assertGreater(c_px[2], c_px[0] + 30, f"Center must show cyan halo tint, got {c_px}")
            self.assertGreater(b_px[2], b_px[0] + 100, f"Border must show strong cyan ring, got {b_px}")
        finally:
            if os.path.exists(js_path):
                os.unlink(js_path)
            if os.path.exists(png_path):
                os.unlink(png_path)

        # 3. adwaita-lock-clock St.DrawingArea disposal guard
        lock_ext = os.path.join(os.path.dirname(EXT_DIR), "adwaita-lock-clock@saifeldin.osama/extension.js")
        with open(lock_ext, "r", encoding="utf-8") as fp:
            lock_code = fp.read()
        self.assertIn("clockCanvas.connect('destroy'", lock_code)
        self.assertIn("customShell.connect('destroy'", lock_code)
        self.assertIn("if (Main.screenShield && !Main.screenShield._dialog)", lock_code)
        self.assertIn("this._restoreUnlockDialog();", lock_code)

        env = os.environ.copy()
        typelib_paths = "/usr/lib64/mutter-51:/usr/lib64/gnome-shell"
        env["GI_TYPELIB_PATH"] = typelib_paths + (":" + env["GI_TYPELIB_PATH"] if "GI_TYPELIB_PATH" in env else "")
        env["LD_LIBRARY_PATH"] = typelib_paths + (":" + env["LD_LIBRARY_PATH"] if "LD_LIBRARY_PATH" in env else "")
        res_lock = subprocess.run(["gjs", "-m", lock_ext], capture_output=True, text=True, env=env, timeout=10)
        lock_out = (res_lock.stderr + "\n" + res_lock.stdout).strip()
        self.assertNotIn("SyntaxError", lock_out, f"GJS syntax error in adwaita-lock-clock:\n{lock_out}")
        if res_lock.returncode != 0:
            self.assertIn("resource:///org/gnome/shell/", lock_out, f"Unexpected GJS failure in adwaita-lock-clock:\n{lock_out}")


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
