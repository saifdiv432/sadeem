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

from capture.media_probe import (
    get_muxer_element,
    probe_audio_encoder,
    probe_h264_encoder,
    probe_h265_encoder,
)
from capture.portal_screencast import ScreenCastPortalSession


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

        self.portal = None
        self.pipeline = None
        self.is_recording = False
        self.start_time = 0.0

    def start(self) -> bool:
        """
        Starts the video and audio recording pipeline.
        Returns True on success, False if canceled or failed.
        """
        if self.is_recording:
            return True

        # 1. Request ScreenCast session from Portal
        self.portal = ScreenCastPortalSession()
        cursor_mode = 2 if self.cursor_enabled else 1
        node_id, pw_fd = self.portal.request_screencast(
            mode=self.mode,
            cursor_mode=cursor_mode,
        )

        if node_id is None:
            print("[VideoRecorder] Portal request was canceled or failed.", file=sys.stderr)
            self.portal.close()
            self.portal = None
            return False

        # 2. Build GStreamer Pipeline String
        try:
            pipeline_str = self._build_pipeline_string(node_id, pw_fd)
            self.pipeline = Gst.parse_launch(pipeline_str)
        except Exception as exc:
            print(f"[VideoRecorder] Failed to create GStreamer pipeline: {exc}", file=sys.stderr)
            self.portal.close()
            self.portal = None
            return False

        # 3. Activate Halo if requested
        if self.halo_enabled and self.cursor_enabled and self.mode != "window":
            if self.client:
                self.client.set_halo_active(True)

        # 4. Start Pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("[VideoRecorder] GStreamer failed to transition to PLAYING.", file=sys.stderr)
            self._cleanup_on_failure()
            return False

        self.is_recording = True
        self.start_time = time.time()

        # 5. Tell Sadeem Desktop Helper to display recording indicator in panel
        if self.client:
            self.client.set_recording_state(True)

        return True

    def _build_pipeline_string(self, node_id: int, pw_fd: int) -> str:
        """Constructs robust, validated GStreamer pipeline string."""
        # Video Source
        if pw_fd >= 0:
            v_src = f'pipewiresrc fd={pw_fd} path="{node_id}" do-timestamp=true keepalive-time=1000'
        else:
            v_src = f'pipewiresrc path="{node_id}" do-timestamp=true'

        # Crop element for selection mode
        crop_elem = ""
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

            # Ensure even dimensions (required by encoders)
            sel_w = max(4, sel_w - (sel_w % 2))
            sel_h = max(4, sel_h - (sel_h % 2))

            crop_left = max(0, sel_x)
            crop_top = max(0, sel_y)
            crop_right = max(0, sw - (crop_left + sel_w))
            crop_bottom = max(0, sh - (crop_top + sel_h))

            crop_elem = f"videocrop top={crop_top} left={crop_left} right={crop_right} bottom={crop_bottom} !"

        # Video encoder probe
        if self.codec == "h265":
            v_enc = probe_h265_encoder()
        else:
            v_enc = probe_h264_encoder()

        # Check if vapostproc is available for VA GPU zero-copy path
        has_vapostproc = Gst.ElementFactory.find("vapostproc") is not None
        is_native_screen = (self.mode == "screen" and self.resolution == "native")
        use_va_gpu = (
            v_enc.get("is_hardware", False)
            and v_enc.get("name", "").startswith("va")
            and has_vapostproc
            and not crop_elem
        )

        # Determine target caps
        if self.resolution == "1080p":
            caps_str = f"video/x-raw,width=1920,height=1080,framerate={self.framerate}/1"
        elif self.resolution == "720p":
            caps_str = f"video/x-raw,width=1280,height=720,framerate={self.framerate}/1"
        else:
            if self.mode == "window" and self.crop_box:
                init_w = max(4, int(self.crop_box[2]) - (int(self.crop_box[2]) % 2))
                init_h = max(4, int(self.crop_box[3]) - (int(self.crop_box[3]) % 2))
                caps_str = f"video/x-raw,width={init_w},height={init_h},framerate={self.framerate}/1"
            elif self.mode == "selection" and self.crop_box:
                sel_w = max(4, int(self.crop_box[2] * self.scale_factor))
                sel_w -= (sel_w % 2)
                sel_h = max(4, int(self.crop_box[3] * self.scale_factor))
                sel_h -= (sel_h % 2)
                caps_str = f"video/x-raw,width={sel_w},height={sel_h},framerate={self.framerate}/1"
            else:
                caps_str = f"video/x-raw,framerate={self.framerate}/1"

        # Performance optimizations:
        # 1. In native screen mode: skip videoscale entirely to eliminate unnecessary copies
        # 2. In VA hardware mode: use vapostproc directly in GPU memory when available
        if is_native_screen:
            conv_scale_elem = "vapostproc !" if use_va_gpu else "videoconvert !"
        elif use_va_gpu:
            conv_scale_elem = "vapostproc !"
        else:
            conv_scale_elem = "videoconvert ! videoscale add-borders=true !"

        # 3. Anti-stutter safety valve: drop excess frames downstream if GPU/CPU is overwhelmed
        leaky_queue = "queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0 !"

        v_pipeline = (
            f"{v_src} ! {crop_elem} {conv_scale_elem} videorate ! {caps_str} ! "
            f"{leaky_queue} {v_enc['pipeline_str']} ! {v_enc['parser']} ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! mux."
        )

        # Audio Pipeline
        a_enc = probe_audio_encoder()
        a_pipeline = ""

        if self.audio_mode == "system":
            a_pipeline = (
                f'pulsesrc device="@DEFAULT_SINK@.monitor" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! '
                f"audioconvert ! audioresample ! {a_enc['pipeline_str']} ! {a_enc['parser']} ! queue ! mux."
            )
        elif self.audio_mode == "mic":
            a_pipeline = (
                f'pulsesrc device="{self.microphone_id}" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! '
                f"audioconvert ! audioresample ! {a_enc['pipeline_str']} ! {a_enc['parser']} ! queue ! mux."
            )
        elif self.audio_mode == "both":
            a_pipeline = (
                f"audiomixer name=mix ! audioconvert ! audioresample ! {a_enc['pipeline_str']} ! {a_enc['parser']} ! queue ! mux. "
                f'pulsesrc device="@DEFAULT_SINK@.monitor" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! audioconvert ! audioresample ! mix. '
                f'pulsesrc device="{self.microphone_id}" ! queue max-size-buffers=0 max-size-time=1000000000 max-size-bytes=0 ! audioconvert ! audioresample ! mix.'
            )

        mux_str = f'{get_muxer_element()} name=mux ! filesink location="{self.output_path}"'

        return f"{mux_str} {v_pipeline} {a_pipeline}"

    def stop(self):
        """
        Stops the recording cleanly by sending EOS, flushing headers,
        and shutting down GStreamer and Portal.
        Returns: (success: bool, output_path: str, file_size: int, duration_sec: float)
        """
        if not self.is_recording or not self.pipeline:
            return False, "", 0, 0.0

        duration_sec = max(0.1, time.time() - self.start_time)

        try:
            # 1. Turn off panel recording indicator and cursor halo immediately
            if self.client:
                try:
                    self.client.set_recording_state(False)
                    self.client.set_halo_active(False)
                except Exception:
                    pass

            # 2. Send EOS event to flush MP4 moov atom & finalize file
            self.pipeline.send_event(Gst.Event.new_eos())

            # 3. Wait on bus for EOS (up to 5 seconds timeout)
            bus = self.pipeline.get_bus()
            msg = bus.timed_pop_filtered(
                5 * Gst.SECOND,
                Gst.MessageType.EOS | Gst.MessageType.ERROR,
            )

            if msg and msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"[VideoRecorder] Error during stop EOS flush: {err} ({debug})", file=sys.stderr)

            # 4. Set state to NULL
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

            # 5. Close portal session
            if self.portal:
                self.portal.close()
                self.portal = None

            self.is_recording = False

            # 6. Verify file output
            file_size = os.path.getsize(self.output_path) if os.path.isfile(self.output_path) else 0
            success = file_size > 0
            return success, self.output_path, file_size, duration_sec

        finally:
            self._cleanup_on_failure()

    def _cleanup_on_failure(self):
        self.is_recording = False
        if self.client:
            try:
                self.client.set_recording_state(False)
                self.client.set_halo_active(False)
            except Exception:
                pass
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
