#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video & Audio Recording Engine for Sadeem OS.
Orchestrates ScreenCast Portal + PipeWire + GStreamer with hardware acceleration,
flexible audio mixing (system + mic), window stabilization, and clean MP4 finalizing.
"""

import datetime
import os
import sys
import time

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gst

# Initialize GStreamer
if not Gst.is_initialized():
    Gst.init(None)

from capture import media_probe
from capture.portal_screencast import ScreenCastPortalSession


def compute_even_crop_margins(
    crop_x: int,
    crop_y: int,
    crop_w: int,
    crop_h: int,
    frame_w: int,
    frame_h: int,
    logical_w: int = 0,
    logical_h: int = 0,
):
    """
    Clamp selection rectangle to physical frame dimensions, optionally scaling from logical
    monitor coordinates when HiDPI / fractional scaling is active, and align x, y, width,
    height to strict even integers (& ~1). Returns (left, top, right, bottom, even_w, even_h).
    """
    sx_factor = 1.0
    sy_factor = 1.0
    if logical_w > 0 and logical_h > 0 and frame_w > 0 and frame_h > 0:
        if frame_w != logical_w or frame_h != logical_h:
            sx_factor = float(frame_w) / float(logical_w)
            sy_factor = float(frame_h) / float(logical_h)

    px_x = int(round(crop_x * sx_factor))
    px_y = int(round(crop_y * sy_factor))
    px_w = int(round(crop_w * sx_factor))
    px_h = int(round(crop_h * sy_factor))

    fw = max(2, int(frame_w) & ~1)
    fh = max(2, int(frame_h) & ~1)
    left = min(max(0, px_x & ~1), max(0, fw - 2))
    top = min(max(0, px_y & ~1), max(0, fh - 2))
    max_w = max(2, (fw - left) & ~1)
    max_h = max(2, (fh - top) & ~1)
    even_w = max(2, min(px_w & ~1, max_w))
    even_h = max(2, min(px_h & ~1, max_h))
    right = max(0, int(frame_w) - left - even_w)
    bottom = max(0, int(frame_h) - top - even_h)
    return left, top, right, bottom, even_w, even_h


def build_video_encoder_spec(codec: str, fps: int) -> dict:
    """
    Build encoder command spec respecting the actual probed encoder (vah264enc/vaapi/nvenc/x264/x265)
    and whether VA-API vapostproc zero-copy GPU conversion is supported.
    """
    fps_val = int(fps) if int(fps) in (30, 60) else 60
    key_int = fps_val * 2
    enc_info = media_probe.probe_h265_encoder() if str(codec).lower() == "h265" else media_probe.probe_h264_encoder()
    name = str(enc_info.get("name", "x264enc"))
    parser = str(enc_info.get("parser", "h264parse"))
    is_hw = bool(enc_info.get("is_hardware", False))
    base_pipe = str(enc_info.get("pipeline_str", name))
    has_vapostproc = Gst.ElementFactory.find("vapostproc") is not None

    if name in ("vah264enc", "vah265enc"):
        enc_pipe = f"{base_pipe} b-frames=0 target-usage=7 rate-control=cqp qpi=24 key-int-max={key_int}"
        uses_va_postproc = has_vapostproc
        yuv_format = "NV12"
    elif name in ("vaapih264enc", "vaapih265enc") or name.startswith("nv") or is_hw:
        enc_pipe = base_pipe
        uses_va_postproc = False
        yuv_format = "NV12"
    elif name in ("x264enc", "x265enc"):
        enc_pipe = base_pipe if "speed-preset=" in base_pipe else f"{name} speed-preset=ultrafast tune=zerolatency"
        uses_va_postproc = False
        yuv_format = "I420"
    else:
        enc_pipe = base_pipe
        uses_va_postproc = False
        yuv_format = "I420"

    return {
        "codec": str(codec).lower(),
        "name": name,
        "pipeline_str": enc_pipe,
        "full_str": f"{enc_pipe} ! {parser}",
        "parser": parser,
        "is_hardware": is_hw,
        "uses_va_postproc": uses_va_postproc,
        "yuv_format": yuv_format,
    }


def get_encoder_yuv_format(enc_info: dict) -> str:
    """Return optimal planar/semi-planar YUV format accepted by the selected encoder."""
    if not enc_info:
        return "I420"
    name = str(enc_info.get("name", ""))
    if enc_info.get("is_hardware") or name.startswith(("va", "nv")):
        return "NV12"
    return "I420"


def attach_even_crop_caps_probe(
    pipeline,
    crop_name: str,
    crop_x: int,
    crop_y: int,
    crop_w: int,
    crop_h: int,
    logical_w: int = 0,
    logical_h: int = 0,
):
    """
    Attach a downstream CAPS event probe on videocrop's sink pad so left/top/right/bottom
    are always aligned to strict even integers matching the actual stream frame size and HiDPI scale.
    """
    if not pipeline:
        return False
    crop_elem = pipeline.get_by_name(crop_name)
    if not crop_elem:
        return False
    sink_pad = crop_elem.get_static_pad("sink")
    if not sink_pad:
        return False

    def _on_caps_probe(_pad, info):
        ev = info.get_event()
        if ev and ev.type == Gst.EventType.CAPS:
            caps = ev.parse_caps()
            if caps and caps.get_size() > 0:
                s = caps.get_structure(0)
                ok_w, in_w = s.get_int("width")
                ok_h, in_h = s.get_int("height")
                if ok_w and ok_h and in_w >= 2 and in_h >= 2:
                    left, top, right, bottom, _ew, _eh = compute_even_crop_margins(
                        crop_x, crop_y, crop_w, crop_h, in_w, in_h,
                        logical_w=logical_w, logical_h=logical_h,
                    )
                    crop_elem.set_property("left", left)
                    crop_elem.set_property("top", top)
                    crop_elem.set_property("right", right)
                    crop_elem.set_property("bottom", bottom)
        return Gst.PadProbeReturn.OK

    sink_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, _on_caps_probe)
    return True


def generate_recording_path() -> str:
    """Generates destination file path in ~/Videos/Screencasts."""
    videos_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
    if not videos_dir:
        videos_dir = os.path.expanduser("~/Videos")
    screencasts_dir = os.path.join(videos_dir, "Screencasts")
    os.makedirs(screencasts_dir, exist_ok=True)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(screencasts_dir, f"Sadeem_Recording_{now_str}.mp4")


class VideoRecorder:
    def __init__(
        self,
        mode="screen",
        crop_box=None,
        screen_size=None,
        scale_factor=1.0,
        resolution="native",
        framerate=30,
        codec="h264",
        audio_mode="none",
        microphone_id="@DEFAULT_SOURCE@",
        cursor_enabled=True,
        halo_enabled=False,
        output_path=None,
        capture_client=None,
        on_stream_ended=None,
    ):
        self.mode = mode  # "screen", "selection", "window"
        self.crop_box = crop_box  # (x, y, w, h)
        self.screen_size = screen_size or (1920, 1080)
        self.scale_factor = scale_factor or 1.0
        self.resolution = resolution  # "native", "1080p", "720p"
        self.framerate = framerate if framerate in (30, 60) else 30
        self.codec = codec  # "h264" or "h265"
        self.audio_mode = audio_mode  # "none", "system", "mic", "both"
        self.microphone_id = microphone_id or "@DEFAULT_SOURCE@"
        self.cursor_enabled = cursor_enabled
        self.halo_enabled = halo_enabled
        self.output_path = output_path or generate_recording_path()
        self.client = capture_client
        self.on_stream_ended = on_stream_ended

        self.portal = None
        self.pipeline = None
        self._bus = None
        self._bus_watch_id = None
        self.is_recording = False
        self._stopping = False
        self.start_time = 0.0

    def start(self):
        """
        Starts the video and audio recording pipeline.
        Returns: "success", "canceled", or "error".
        """
        if self.is_recording:
            return "success"

        # 1. Suppress GNOME built-in yellow indicator BEFORE portal session request
        if self.client:
            self.client.set_gnome_indicator_suppressed(True)

        # 2. Request ScreenCast session from Portal
        self.portal = ScreenCastPortalSession()
        cursor_mode = 2 if self.cursor_enabled else 1
        status, node_id, pw_fd = self.portal.request_screencast(
            mode=self.mode,
            cursor_mode=cursor_mode,
        )

        if status == "canceled":
            print("[VideoRecorder] Portal request was canceled by user.", file=sys.stderr)
            if self.client:
                self.client.set_gnome_indicator_suppressed(False)
            self.portal.close()
            self.portal = None
            return "canceled"

        if status != "success" or node_id is None:
            print("[VideoRecorder] Portal request failed.", file=sys.stderr)
            if self.client:
                self.client.set_gnome_indicator_suppressed(False)
            self.portal.close()
            self.portal = None
            return "error"

        # 3. Build GStreamer Pipeline String
        try:
            pipeline_str = self._build_pipeline_string(node_id, pw_fd)
            self.pipeline = Gst.parse_launch(pipeline_str)
            if self.mode == "selection" and self.crop_box:
                attach_even_crop_caps_probe(
                    self.pipeline,
                    "crop",
                    int(self.crop_box[0] * self.scale_factor),
                    int(self.crop_box[1] * self.scale_factor),
                    int(self.crop_box[2] * self.scale_factor),
                    int(self.crop_box[3] * self.scale_factor),
                )
        except Exception as exc:
            print(f"[VideoRecorder] Failed to create GStreamer pipeline: {exc}", file=sys.stderr)
            if self.client:
                self.client.set_gnome_indicator_suppressed(False)
            self.portal.close()
            self.portal = None
            return "error"

        # 4. Activate Halo if requested
        if self.halo_enabled and self.cursor_enabled and self.mode != "window":
            if self.client:
                self.client.set_halo_active(True)

        # 5. Activate bus watch before PLAYING
        self._bus = self.pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus_watch_id = self._bus.connect("message", self._on_bus_message)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("[VideoRecorder] GStreamer failed to transition to PLAYING.", file=sys.stderr)
            if self.client:
                self.client.set_gnome_indicator_suppressed(False)
            self._cleanup_on_failure()
            return "error"

        self.is_recording = True
        self.start_time = time.time()

        # 6. Show Sadeem Red Recording Indicator in panel ONLY after PLAYING succeeds
        if self.client:
            self.client.set_recording_state(True)

        return "success"

    def _build_pipeline_string(self, node_id: int, pw_fd: int) -> str:
        """Constructs robust, validated GStreamer pipeline string."""
        # Video Source
        if pw_fd >= 0:
            v_src = f'pipewiresrc fd={pw_fd} path="{node_id}" do-timestamp=true keepalive-time=1000'
        else:
            v_src = f'pipewiresrc path="{node_id}" do-timestamp=true'

        # Crop element for selection mode (strict even alignment + packed BGRx before videocrop)
        crop_elem = ""
        even_sel_w, even_sel_h = 0, 0
        if self.mode == "selection" and self.crop_box:
            sel_x, sel_y, sel_w, sel_h = self.crop_box
            sw, sh = self.screen_size

            # Scale to physical coordinates if needed
            sel_x = int(sel_x * self.scale_factor)
            sel_y = int(sel_y * self.scale_factor)
            sel_w = int(sel_w * self.scale_factor)
            sel_h = int(sel_h * self.scale_factor)
            sw = int(sw * self.scale_factor)
            sh = int(sh * self.scale_factor)

            crop_left, crop_top, crop_right, crop_bottom, even_sel_w, even_sel_h = compute_even_crop_margins(
                sel_x, sel_y, sel_w, sel_h, sw, sh
            )
            crop_elem = (
                f"videoconvert ! video/x-raw,format=BGRx,pixel-aspect-ratio=1/1 ! "
                f"videocrop name=crop top={crop_top} left={crop_left} right={crop_right} bottom={crop_bottom} !"
            )

        # Video encoder spec
        v_enc = build_video_encoder_spec(self.codec, self.framerate)
        is_native_screen = (self.mode == "screen" and self.resolution == "native")
        use_va_postproc = bool(v_enc.get("uses_va_postproc"))
        use_va_dmabuf = is_native_screen and use_va_postproc and not crop_elem

        scale_size_props = ""
        if self.resolution == "1080p":
            scale_size_props = ",width=1920,height=1080"
        elif self.resolution == "720p":
            scale_size_props = ",width=1280,height=720"
        elif self.mode == "window" and self.crop_box:
            init_w = max(2, int(self.crop_box[2]) & ~1)
            init_h = max(2, int(self.crop_box[3]) & ~1)
            scale_size_props = f",width={init_w},height={init_h}"

        needs_scale = (self.mode == "window" or self.resolution != "native")
        if use_va_dmabuf:
            conv_scale_caps = "video/x-raw(memory:DMABuf),pixel-aspect-ratio=1/1 ! vapostproc ! video/x-raw(memory:VAMemory),format=NV12,colorimetry=bt709"
        elif use_va_postproc:
            pre_src = "" if crop_elem else "videoconvert ! video/x-raw,format=BGRx,pixel-aspect-ratio=1/1 ! "
            scale_step = f"videoscale add-borders=true ! video/x-raw,format=BGRx{scale_size_props},pixel-aspect-ratio=1/1 ! " if needs_scale else ""
            conv_scale_caps = f"{pre_src}{scale_step}vapostproc ! video/x-raw(memory:VAMemory),format=NV12,colorimetry=bt709"
        else:
            yuv_fmt = v_enc["yuv_format"]
            color_prop = ",colorimetry=bt709" if yuv_fmt == "I420" else ""
            pre_src = "" if crop_elem else "video/x-raw,pixel-aspect-ratio=1/1 ! "
            scale_step = "" if is_native_screen else "videoscale add-borders=true ! "
            conv_scale_caps = f"{pre_src}videoconvert ! {scale_step}video/x-raw,format={yuv_fmt}{color_prop}{scale_size_props},pixel-aspect-ratio=1/1"

        # Drop excess frames cleanly without duplicating on static screen
        rate_elem = f"videorate drop-only=true max-rate={self.framerate} !"
        leaky_queue = "queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0 !"

        v_pipeline = (
            f"{v_src} ! {crop_elem} {conv_scale_caps} ! {rate_elem} "
            f"{leaky_queue} {v_enc['full_str']} ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! mux."
        )

        # Audio Pipeline
        a_enc = media_probe.probe_audio_encoder()
        a_pipeline = ""
        a_caps = "audio/x-raw,rate=48000,channels=2"

        if self.audio_mode == "system":
            a_pipeline = (
                f'pulsesrc device="@DEFAULT_SINK@.monitor" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! '
                f"audioconvert ! audioresample ! {a_caps} ! {a_enc['pipeline_str']} ! {a_enc['parser']} ! queue ! mux."
            )
        elif self.audio_mode == "mic":
            a_pipeline = (
                f'pulsesrc device="{self.microphone_id}" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! '
                f"audioconvert ! audioresample ! {a_caps} ! {a_enc['pipeline_str']} ! {a_enc['parser']} ! queue ! mux."
            )
        elif self.audio_mode == "both":
            a_pipeline = (
                f"audiomixer name=mix ! audioconvert ! audioresample ! {a_caps} ! {a_enc['pipeline_str']} ! {a_enc['parser']} ! queue ! mux. "
                f'pulsesrc device="@DEFAULT_SINK@.monitor" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! audioconvert ! audioresample ! {a_caps} ! mix. '
                f'pulsesrc device="{self.microphone_id}" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! audioconvert ! audioresample ! {a_caps} ! mix.'
            )

        mux_str = f'{media_probe.get_muxer_element()} name=mux ! filesink location="{self.output_path}"'

        return f"{mux_str} {v_pipeline} {a_pipeline}"

    def _on_bus_message(self, bus, message):
        if not self.is_recording or self._stopping:
            return
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            print("[VideoRecorder] Stream EOS received from bus.", file=sys.stderr)
            if callable(self.on_stream_ended):
                GLib.idle_add(self.on_stream_ended, None)
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            err_str = f"{err} ({debug})"
            print(f"[VideoRecorder] Stream ERROR received from bus: {err_str}", file=sys.stderr)
            if callable(self.on_stream_ended):
                GLib.idle_add(self.on_stream_ended, err_str)

    def stop(self):
        """
        Stops the recording cleanly by sending EOS, flushing headers,
        and shutting down GStreamer and Portal.
        Returns: (success: bool, output_path: str, file_size: int, duration_sec: float)
        """
        if self._stopping or not self.is_recording or not self.pipeline:
            return False, "", 0, 0.0

        self._stopping = True
        duration_sec = max(0.1, time.time() - self.start_time)

        try:
            # 1. Turn off red panel recording indicator and cursor halo immediately
            # GNOME yellow indicator remains suppressed!
            if self.client:
                try:
                    self.client.set_recording_state(False)
                    self.client.set_halo_active(False)
                except Exception:
                    pass

            # 2. Disconnect bus watch before sending EOS so internal bus watch doesn't double-fire
            if self._bus and self._bus_watch_id:
                try:
                    self._bus.disconnect(self._bus_watch_id)
                except Exception:
                    pass
                try:
                    self._bus.remove_signal_watch()
                except Exception:
                    pass
                self._bus_watch_id = None
                self._bus = None

            # 3. Send EOS event to flush MP4 moov atom & finalize file
            self.pipeline.send_event(Gst.Event.new_eos())

            # 4. Wait on bus for EOS (up to 4 seconds timeout)
            bus = self.pipeline.get_bus()
            msg = bus.timed_pop_filtered(
                4 * Gst.SECOND,
                Gst.MessageType.EOS | Gst.MessageType.ERROR,
            )

            if msg and msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"[VideoRecorder] Error during stop EOS flush: {err} ({debug})", file=sys.stderr)

            # 5. Set state to NULL
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

            # 6. Close portal session completely
            if self.portal:
                self.portal.close()
                self.portal = None

            # 7. AFTER portal is completely closed, release GNOME yellow indicator suppression
            if self.client:
                try:
                    self.client.set_gnome_indicator_suppressed(False)
                except Exception:
                    pass

            self.is_recording = False

            # 8. Verify file output
            file_size = os.path.getsize(self.output_path) if os.path.isfile(self.output_path) else 0
            success = file_size > 0
            return success, self.output_path, file_size, duration_sec

        finally:
            self._cleanup_on_failure()

    def _cleanup_on_failure(self):
        had_resources = (self.pipeline is not None or self.portal is not None or self.is_recording)
        self.is_recording = False
        if self._bus and self._bus_watch_id:
            try:
                self._bus.disconnect(self._bus_watch_id)
            except Exception:
                pass
            try:
                self._bus.remove_signal_watch()
            except Exception:
                pass
            self._bus_watch_id = None
            self._bus = None
        if self.pipeline:
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
            self.pipeline = None
        if self.portal:
            try:
                self.portal.close()
            except Exception:
                pass
            self.portal = None
        if had_resources and self.client:
            try:
                self.client.set_recording_state(False)
                self.client.set_halo_active(False)
                self.client.set_gnome_indicator_suppressed(False)
            except Exception:
                pass
