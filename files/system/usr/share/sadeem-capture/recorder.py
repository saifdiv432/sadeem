#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
High-Performance On-Demand Video Recorder for Sadeem OS.
Captures screen, window, or selection via PipeWire and Hardware DMA-BUF VA-API.
Transmuxes temporary MKV to MP4 with FFmpeg upon completion.
Zero GTK/GUI overhead; runs purely during recording.
"""

import argparse
import datetime
import os
import signal
import subprocess
import sys
import time

import gi
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gio, Gst

from capture.portal_screencast import ScreenCastPortalSession
from capture import media_probe


def format_size(bytes_val: int) -> str:
    val = float(bytes_val)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


class VideoRecorderApp:
    def __init__(self, args):
        self.args = args
        self.portal = None
        self.pipeline = None
        self.loop = None
        self.is_running = False
        self.stop_requested = False
        self.tmp_mkv = ""
        self.final_mp4 = ""
        self.current_level = 1

    def build_pipeline_str(self, node_id: int, fd: int, level: int = 1) -> str:
        codec = self.args.codec.lower()
        fps = int(self.args.fps)
        key_int = fps * 2
        res = self.args.resolution.lower()

        # Resolution caps
        if res == "1080p":
            res_caps_raw = "video/x-raw,width=1920,height=1080,pixel-aspect-ratio=1/1 ! "
        elif res == "720p":
            res_caps_raw = "video/x-raw,width=1280,height=720,pixel-aspect-ratio=1/1 ! "
        else:
            res_caps_raw = "video/x-raw,pixel-aspect-ratio=1/1 ! "

        # Video Encoder
        if codec == "h265":
            if media_probe.probe_h265_encoder().get("is_hardware"):
                enc_str = f"vah265enc b-frames=0 target-usage=7 rate-control=cqp qpi=24 key-int-max={key_int} ! h265parse"
            else:
                enc_str = "x265enc speed-preset=ultrafast tune=zerolatency ! h265parse"
        else:
            if media_probe.probe_h264_encoder().get("is_hardware"):
                enc_str = f"vah264enc b-frames=0 target-usage=7 rate-control=cqp qpi=24 key-int-max={key_int} ! h264parse"
            else:
                enc_str = "x264enc speed-preset=ultrafast tune=zerolatency ! h264parse"

        # Level 1: Zero-copy DMA-BUF (screen mode at native resolution)
        if level == 1 and self.args.mode == "screen" and res == "native":
            video_pipeline = (
                f"pipewiresrc fd={fd} path=\"{node_id}\" do-timestamp=true keepalive-time=1000 ! "
                f"video/x-raw(memory:DMABuf),pixel-aspect-ratio=1/1 ! vapostproc ! "
                f"{enc_str} ! queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! mux."
            )
        else:
            # Modes with dynamic / scaled aspect ratio (window, scaled screen, or selection crop)
            crop_filter = ""
            if self.args.mode == "selection" and self.args.crop:
                try:
                    parts = [int(p) for p in self.args.crop.split(",")]
                    if len(parts) == 4:
                        crop_filter = "videocrop name=crop ! "
                except Exception:
                    crop_filter = ""

            video_pipeline = (
                f"pipewiresrc fd={fd} path=\"{node_id}\" do-timestamp=true keepalive-time=1000 ! "
                f"video/x-raw ! {crop_filter}videoconvert ! videoscale add-borders=true ! {res_caps_raw}"
                f"{enc_str} ! queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! mux."
            )

        # Audio branch
        audio_mode = self.args.audio.lower()
        audio_pipeline = ""
        if audio_mode == "system":
            audio_pipeline = (
                "pulsesrc device=\"@DEFAULT_SINK@.monitor\" ! audioconvert ! audioresample ! "
                "avenc_aac ! aacparse ! queue ! mux."
            )
        elif audio_mode == "mic":
            mic_dev = f"device=\"{self.args.mic}\"" if self.args.mic else ""
            audio_pipeline = (
                f"pulsesrc {mic_dev} ! audioconvert ! audioresample ! "
                "avenc_aac ! aacparse ! queue ! mux."
            )
        elif audio_mode == "both":
            mic_dev = f"device=\"{self.args.mic}\"" if self.args.mic else ""
            audio_pipeline = (
                f"pulsesrc device=\"@DEFAULT_SINK@.monitor\" ! audioconvert ! audioresample ! queue ! mixer. "
                f"pulsesrc {mic_dev} ! audioconvert ! audioresample ! queue ! mixer. "
                "audiomixer name=mixer ! audioconvert ! audioresample ! avenc_aac ! aacparse ! queue ! mux."
            )

        full_pipeline = (
            f"{video_pipeline} {audio_pipeline} "
            f"matroskamux name=mux ! filesink location=\"{self.tmp_mkv}\""
        )
        return full_pipeline

    def run(self) -> int:
        Gst.init(None)

        # Setup destination directory
        videos_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS) or os.path.expanduser("~/Videos")
        recordings_dir = os.path.join(videos_dir, "Recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = "تسجيل_سديم"
        self.final_mp4 = os.path.join(recordings_dir, f"{prefix}_{now_str}.mp4")
        self.tmp_mkv = os.path.join(recordings_dir, f".sadeem_tmp_{now_str}.mkv")

        # 1. Establish Portal Screencast Session
        self.portal = ScreenCastPortalSession()
        cursor_mode = 2 if self.args.cursor else 1
        status, node_id, fd = self.portal.request_screencast(
            mode=self.args.mode,
            cursor_mode=cursor_mode
        )

        if status == "canceled":
            # Portal dialog dismissed by user: exit code 2
            return 2
        if status != "success" or node_id is None or fd < 0:
            print("[Recorder] Failed to obtain screencast portal session", file=sys.stderr)
            return 1

        # 2. Setup GStreamer pipeline (Level 1 zero-copy or Level 2)
        initial_level = 2 if (self.args.mode == "selection" and self.args.crop) else 1
        self.current_level = initial_level
        pipe_str = self.build_pipeline_str(node_id, fd, level=initial_level)

        try:
            self.pipeline = Gst.parse_launch(pipe_str)
        except Exception as e:
            print(f"[Recorder] Pipeline parse error on Level {initial_level}: {e}", file=sys.stderr)
            if initial_level == 1:
                # Fallback to Level 2
                self.current_level = 2
                pipe_str = self.build_pipeline_str(node_id, fd, level=2)
                try:
                    self.pipeline = Gst.parse_launch(pipe_str)
                except Exception as e2:
                    print(f"[Recorder] Level 2 pipeline parse error: {e2}", file=sys.stderr)
                    self.portal.close()
                    return 1
            else:
                self.portal.close()
                return 1

        # Configure dynamic videocrop if present
        if self.args.crop:
            try:
                crop_elem = self.pipeline.get_by_name("crop")
                if crop_elem:
                    parts = [int(p) for p in self.args.crop.split(",")]
                    if len(parts) == 4:
                        cx, cy, cw, ch = parts
                        crop_elem.set_property("left", max(0, cx))
                        crop_elem.set_property("top", max(0, cy))
            except Exception:
                pass

        self.loop = GLib.MainLoop()
        bus = self.pipeline.get_bus()
        bus.add_watch(GLib.PRIORITY_DEFAULT, self._on_bus_message)

        # 3. Register signal handlers for clean SIGINT / SIGTERM stop
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # 4. Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print(f"[Recorder] Failed to start pipeline on Level {self.current_level}", file=sys.stderr)
            if self.current_level == 1:
                # Retry on Level 2
                self.pipeline.set_state(Gst.State.NULL)
                self.current_level = 2
                pipe_str = self.build_pipeline_str(node_id, fd, level=2)
                try:
                    self.pipeline = Gst.parse_launch(pipe_str)
                    bus = self.pipeline.get_bus()
                    bus.add_watch(GLib.PRIORITY_DEFAULT, self._on_bus_message)
                    ret = self.pipeline.set_state(Gst.State.PLAYING)
                    if ret == Gst.StateChangeReturn.FAILURE:
                        self.portal.close()
                        return 1
                except Exception as e:
                    print(f"[Recorder] Level 2 launch error: {e}", file=sys.stderr)
                    self.portal.close()
                    return 1
            else:
                self.portal.close()
                return 1

        self.is_running = True
        # Output status to listening captureUI
        print("STATUS:RECORDING", flush=True)

        try:
            self.loop.run()
        except KeyboardInterrupt:
            self._do_stop()

        # 5. Clean teardown and remuxing
        return self._finalize_recording()

    def _handle_signal(self, signum, frame):
        if not self.stop_requested:
            self.stop_requested = True
            GLib.idle_add(self._do_stop)

    def _do_stop(self):
        if self.pipeline and self.is_running:
            self.is_running = False
            self.pipeline.send_event(Gst.Event.new_eos())

            # Await EOS for up to 4 seconds
            GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4, self._force_quit)

    def _force_quit(self):
        if self.loop and self.loop.is_running():
            self.loop.quit()
        return GLib.SOURCE_REMOVE

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            if self.loop and self.loop.is_running():
                self.loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"[Recorder] GStreamer error: {err}, debug: {debug}", file=sys.stderr)
            if self.loop and self.loop.is_running():
                self.loop.quit()
        return True

    def _finalize_recording(self) -> int:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        if self.portal:
            self.portal.close()
            self.portal = None

        if not os.path.isfile(self.tmp_mkv) or os.path.getsize(self.tmp_mkv) == 0:
            print("[Recorder] Recording file is empty or missing", file=sys.stderr)
            return 1

        # Remux temporary MKV to MP4 with FFmpeg
        remux_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-i", self.tmp_mkv,
            "-c", "copy",
            "-movflags", "+faststart",
            self.final_mp4,
        ]

        try:
            res = subprocess.run(remux_cmd, capture_output=True, timeout=15)
            if res.returncode == 0 and os.path.isfile(self.final_mp4) and os.path.getsize(self.final_mp4) > 0:
                # Success: delete tmp mkv
                try:
                    os.unlink(self.tmp_mkv)
                except Exception:
                    pass
                final_size = os.path.getsize(self.final_mp4)
                size_str = format_size(final_size)
                print(f"STATUS:SAVED:{size_str}:{self.final_mp4}", flush=True)
                return 0
        except Exception as e:
            print(f"[Recorder] FFmpeg remuxing error: {e}", file=sys.stderr)

        # Fallback: keep MKV if remuxing failed
        safe_mkv = self.tmp_mkv.replace("/.sadeem_tmp_", "/تسجيل_سديم_")
        try:
            os.rename(self.tmp_mkv, safe_mkv)
            final_size = os.path.getsize(safe_mkv)
            size_str = format_size(final_size)
            print(f"STATUS:SAVED:{size_str}:{safe_mkv}", flush=True)
            return 0
        except Exception:
            final_size = os.path.getsize(self.tmp_mkv)
            size_str = format_size(final_size)
            print(f"STATUS:SAVED:{size_str}:{self.tmp_mkv}", flush=True)
            return 0


def main():
    parser = argparse.ArgumentParser(description="Sadeem OS High-Performance Screen Recorder")
    parser.add_argument("--mode", default="screen", choices=["selection", "screen", "window"])
    parser.add_argument("--crop", default="", help="Cropping rectangle x,y,w,h")
    parser.add_argument("--monitor", default="0", help="Monitor index")
    parser.add_argument("--resolution", default="native", choices=["native", "1080p", "720p"])
    parser.add_argument("--fps", default="60", choices=["30", "60"])
    parser.add_argument("--codec", default="h264", choices=["h264", "h265"])
    parser.add_argument("--audio", default="none", choices=["none", "system", "mic", "both"])
    parser.add_argument("--mic", default="", help="Microphone source name")
    parser.add_argument("--cursor", action="store_true", help="Include mouse cursor")

    args = parser.parse_args()
    app = VideoRecorderApp(args)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
