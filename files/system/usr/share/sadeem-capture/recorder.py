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
from capture.video_recorder import attach_even_crop_caps_probe, build_video_encoder_spec
from capture import media_probe
import i18n


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
        self.node_id = None
        self.fd = -1
        self._bus_watch_id = 0
        self._got_video_frame = False
        self._fallback_triggered = False

    def build_pipeline_str(self, node_id: int, fd: int, level: int = 1) -> str:
        codec = self.args.codec.lower()
        fps = int(self.args.fps) if int(self.args.fps) in (30, 60) else 60
        res = self.args.resolution.lower()

        v_enc = build_video_encoder_spec(codec, fps)
        enc_str = v_enc["full_str"]
        use_va_postproc = bool(v_enc.get("uses_va_postproc"))
        rate_elem = f"videorate drop-only=true max-rate={fps}"
        vqueue = "queue name=vqueue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0"

        size_props = ""
        if res == "1080p":
            size_props = ",width=1920,height=1080"
        elif res == "720p":
            size_props = ",width=1280,height=720"

        # Level 1: Zero-copy DMA-BUF (screen mode at native resolution)
        if level == 1 and self.args.mode == "screen" and res == "native":
            if use_va_postproc:
                va_caps = "video/x-raw(memory:VAMemory),format=NV12,colorimetry=bt709"
                video_pipeline = (
                    f"pipewiresrc fd={fd} path=\"{node_id}\" do-timestamp=true keepalive-time=1000 ! "
                    f"video/x-raw(memory:DMABuf),pixel-aspect-ratio=1/1 ! vapostproc ! {va_caps} ! {rate_elem} ! "
                    f"{vqueue} ! {enc_str} ! queue ! mux."
                )
            else:
                yuv_fmt = v_enc["yuv_format"]
                color_prop = ",colorimetry=bt709" if yuv_fmt == "I420" else ""
                video_pipeline = (
                    f"pipewiresrc fd={fd} path=\"{node_id}\" do-timestamp=true keepalive-time=1000 ! "
                    f"video/x-raw(memory:DMABuf),pixel-aspect-ratio=1/1 ! vapostproc ! "
                    f"video/x-raw,format={yuv_fmt}{color_prop},pixel-aspect-ratio=1/1 ! {rate_elem} ! "
                    f"{vqueue} ! {enc_str} ! queue ! mux."
                )
        else:
            # Level 2: Fixate pixel-aspect-ratio=1/1 on BGRx BEFORE videocrop and vapostproc
            # to prevent unfixated upstream PAR (e.g. 1/2147483647) overflowing gst_va_vpp_fixate_size.
            has_crop = False
            if self.args.mode == "selection" and self.args.crop:
                try:
                    parts = [int(p) for p in self.args.crop.split(",")]
                    has_crop = len(parts) == 4
                except Exception:
                    has_crop = False

            needs_scale = (self.args.mode == "window" or res != "native")
            if use_va_postproc:
                bgrx_caps = "video/x-raw,format=BGRx,pixel-aspect-ratio=1/1"
                prep = f"videoconvert ! {bgrx_caps} ! videocrop name=crop ! " if has_crop else f"videoconvert ! {bgrx_caps} ! "
                scale_part = f"videoscale add-borders=true ! video/x-raw,format=BGRx{size_props},pixel-aspect-ratio=1/1 ! " if needs_scale else ""
                va_caps = "video/x-raw(memory:VAMemory),format=NV12,colorimetry=bt709"
                video_pipeline = (
                    f"pipewiresrc fd={fd} path=\"{node_id}\" do-timestamp=true keepalive-time=1000 ! "
                    f"{prep}{scale_part}vapostproc ! {va_caps} ! {rate_elem} ! "
                    f"{vqueue} ! {enc_str} ! queue ! mux."
                )
            else:
                yuv_fmt = v_enc["yuv_format"]
                color_prop = ",colorimetry=bt709" if yuv_fmt == "I420" else ""
                prep = "videoconvert ! video/x-raw,format=BGRx,pixel-aspect-ratio=1/1 ! videocrop name=crop ! " if has_crop else "video/x-raw,pixel-aspect-ratio=1/1 ! "
                scale_part = "videoscale add-borders=true ! " if needs_scale else ""
                raw_caps = f"video/x-raw,format={yuv_fmt}{color_prop}{size_props},pixel-aspect-ratio=1/1"
                video_pipeline = (
                    f"pipewiresrc fd={fd} path=\"{node_id}\" do-timestamp=true keepalive-time=1000 ! "
                    f"{prep}videoconvert ! {scale_part}{raw_caps} ! {rate_elem} ! "
                    f"{vqueue} ! {enc_str} ! queue ! mux."
                )

        # Audio branch (consistent buffering + 48kHz stereo caps across all modes)
        audio_mode = self.args.audio.lower()
        audio_pipeline = ""
        a_caps = "audio/x-raw,rate=48000,channels=2"
        q_audio = "queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0"
        if audio_mode == "system":
            audio_pipeline = (
                f'pulsesrc device="@DEFAULT_SINK@.monitor" ! {q_audio} ! audioconvert ! audioresample ! '
                f"{a_caps} ! avenc_aac ! aacparse ! queue ! mux."
            )
        elif audio_mode == "mic":
            mic_dev = f"device=\"{self.args.mic}\"" if self.args.mic else ""
            audio_pipeline = (
                f"pulsesrc {mic_dev} ! {q_audio} ! audioconvert ! audioresample ! "
                f"{a_caps} ! avenc_aac ! aacparse ! queue ! mux."
            )
        elif audio_mode == "both":
            mic_dev = f"device=\"{self.args.mic}\"" if self.args.mic else ""
            audio_pipeline = (
                f'pulsesrc device="@DEFAULT_SINK@.monitor" ! {q_audio} ! audioconvert ! audioresample ! {a_caps} ! queue ! mixer. '
                f"pulsesrc {mic_dev} ! {q_audio} ! audioconvert ! audioresample ! {a_caps} ! queue ! mixer. "
                f"audiomixer name=mixer ! audioconvert ! audioresample ! {a_caps} ! avenc_aac ! aacparse ! queue ! mux."
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
        folder_name = i18n.t("folder_recordings") or "Recordings"
        recordings_dir = os.path.join(videos_dir, folder_name)
        os.makedirs(recordings_dir, exist_ok=True)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = i18n.t("filename_video_prefix") or "Sadeem_Recording"
        self.final_mp4 = os.path.join(recordings_dir, f"{prefix}_{now_str}.mp4")
        idx = 1
        while os.path.exists(self.final_mp4):
            self.final_mp4 = os.path.join(recordings_dir, f"{prefix}_{now_str}_{idx}.mp4")
            idx += 1
        self.tmp_mkv = os.path.join(recordings_dir, f".sadeem_tmp_{now_str}_{os.getpid()}.mkv")

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

        self.node_id = node_id
        self.fd = fd
        self.loop = GLib.MainLoop()

        # 2. Setup GStreamer pipeline (Level 1 zero-copy or Level 2)
        initial_level = 2 if (self.args.mode == "selection" and self.args.crop) else 1
        if not self._setup_and_start_pipeline(initial_level):
            if initial_level == 1 and not self._switch_to_level2():
                self.portal.close()
                return 1
            elif initial_level != 1:
                self.portal.close()
                return 1

        # 3. Register signal handlers for clean SIGINT / SIGTERM stop
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.is_running = True
        # Output status to listening captureUI
        print("STATUS:RECORDING", flush=True)

        try:
            self.loop.run()
        except KeyboardInterrupt:
            self._do_stop()

        # 5. Clean teardown and remuxing
        return self._finalize_recording()

    def _teardown_pipeline(self):
        if self._bus_watch_id:
            try:
                GLib.source_remove(self._bus_watch_id)
            except Exception:
                pass
            self._bus_watch_id = 0
        if self.pipeline:
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
            self.pipeline = None

    def _attach_probes(self):
        if not self.pipeline:
            return
        if self.args.mode == "selection" and self.args.crop:
            try:
                parts = [int(p) for p in self.args.crop.split(",")]
                if len(parts) == 4:
                    cx, cy, cw, ch = parts
                    lw, lh = 0, 0
                    mon_sz = getattr(self.args, "monitor_size", "") or ""
                    if mon_sz:
                        ms_parts = [int(v) for v in mon_sz.split(",")]
                        if len(ms_parts) == 2 and ms_parts[0] > 0 and ms_parts[1] > 0:
                            lw, lh = ms_parts[0], ms_parts[1]
                    attach_even_crop_caps_probe(
                        self.pipeline, "crop", cx, cy, cw, ch,
                        logical_w=lw, logical_h=lh,
                    )
            except Exception:
                pass

        vqueue = self.pipeline.get_by_name("vqueue")
        if vqueue:
            sink_pad = vqueue.get_static_pad("sink")
            if sink_pad:
                def _on_first_video_frame(_pad, _info):
                    self._got_video_frame = True
                    return Gst.PadProbeReturn.REMOVE
                sink_pad.add_probe(Gst.PadProbeType.BUFFER, _on_first_video_frame)

    def _setup_and_start_pipeline(self, level: int) -> bool:
        self._teardown_pipeline()
        self.current_level = level
        self._got_video_frame = False
        pipe_str = self.build_pipeline_str(self.node_id, self.fd, level=level)
        try:
            self.pipeline = Gst.parse_launch(pipe_str)
        except Exception as e:
            print(f"[Recorder] Pipeline parse error on Level {level}: {e}", file=sys.stderr)
            self.pipeline = None
            return False

        self._attach_probes()
        bus = self.pipeline.get_bus()
        self._bus_watch_id = bus.add_watch(GLib.PRIORITY_DEFAULT, self._on_bus_message)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print(f"[Recorder] Failed to start pipeline on Level {level}", file=sys.stderr)
            self._teardown_pipeline()
            return False
        return True

    def _switch_to_level2(self) -> bool:
        self._fallback_triggered = True
        if self._setup_and_start_pipeline(2):
            return True
        if self.loop and self.loop.is_running():
            self.loop.quit()
        return False

    def _switch_to_level2_idle(self):
        if not self.stop_requested:
            self._switch_to_level2()
        return GLib.SOURCE_REMOVE

    def _handle_signal(self, signum, frame):
        if not self.stop_requested:
            self.stop_requested = True
            GLib.idle_add(self._do_stop)

    def _do_stop(self):
        if self.pipeline and self.is_running:
            self.is_running = False
            self.pipeline.send_event(Gst.Event.new_eos())

            # Await EOS for up to 4 seconds
            GLib.timeout_add_seconds(4, self._force_quit)
        return GLib.SOURCE_REMOVE

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
            err_lower = f"{err} {debug or ''}".lower()
            is_negotiation = (
                "not-negotiated" in err_lower
                or "negotiation" in err_lower
                or "not negotiated" in err_lower
                or err.matches(Gst.CoreError.quark(), Gst.CoreError.NEGOTIATION)
                or err.matches(Gst.StreamError.quark(), Gst.StreamError.FORMAT)
            )
            if (
                self.current_level == 1
                and not self._got_video_frame
                and not self._fallback_triggered
                and is_negotiation
            ):
                self._fallback_triggered = True
                print(
                    f"[Recorder] Level 1 DMABuf negotiation error ({err}), falling back to Level 2...",
                    file=sys.stderr,
                )
                GLib.idle_add(self._switch_to_level2_idle)
                return True
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
        fb_prefix = i18n.t("filename_video_prefix") or "Sadeem_Recording"
        safe_mkv = self.tmp_mkv.replace("/.sadeem_tmp_", f"/{fb_prefix}_")
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
    parser.add_argument("--monitor-size", default="", help="Logical monitor dimensions W,H for HiDPI scaling")
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
