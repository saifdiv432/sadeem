#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast video editing engine for Sadeem Gallery using FFmpeg subprocess pipelines.
Features:
- Stream-copy fast path for trimming and full audio muting (instant, lossless).
- Audio-only re-encode path for timed partial muting while keeping video stream copy.
- Full re-encode path with hardware/libx264 for cropping and timed transparent PNG overlays.
- Real-time progress monitoring via `-progress pipe:1`.
- Clean cancellation support and atomic file replacement.
"""

import os
import re
import shutil
import subprocess
import tempfile
import threading

_FFMPEG_BIN = shutil.which("ffmpeg")
_FFPROBE_BIN = shutil.which("ffprobe")


def _get_duration(path):
    if not _FFPROBE_BIN or not os.path.isfile(path):
        return 0.0
    cmd = [
        _FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return 0.0


def export_video(
    input_path,
    output_path,
    trim_start=None,
    trim_end=None,
    mute_all=False,
    mute_ranges=None,
    crop_box=None,
    overlay_png_path=None,
    overlay_start=None,
    overlay_end=None,
    progress_callback=None,
    cancel_event=None,
):
    """
    Export edited video with optimal speed and quality.

    Arguments:
    - input_path: path to source video file
    - output_path: destination file path
    - trim_start: start time in seconds (float, optional)
    - trim_end: end time in seconds (float, optional)
    - mute_all: bool, drop audio entirely
    - mute_ranges: list of (start_sec, end_sec) for partial audio silencing
    - crop_box: tuple of (x, y, w, h) in pixels
    - overlay_png_path: path to RGBA PNG image for annotations/watermark
    - overlay_start, overlay_end: time range in seconds for overlay visibility
    - progress_callback: func(fraction: float, time_sec: float)
    - cancel_event: threading.Event to abort processing

    Returns:
    (success: bool, error_msg: str or None)
    """
    if not _FFMPEG_BIN:
        return False, "FFmpeg binary not found in PATH"
    if not os.path.isfile(input_path):
        return False, f"Input video file not found: {input_path}"

    total_in_dur = _get_duration(input_path)
    eff_start = max(0.0, float(trim_start)) if trim_start is not None else 0.0
    eff_end = float(trim_end) if (trim_end is not None and trim_end > 0) else total_in_dur
    if eff_end <= eff_start:
        eff_end = total_in_dur if total_in_dur > eff_start else eff_start + 1.0

    target_duration = max(0.1, eff_end - eff_start)

    # Determine execution strategy
    has_crop = bool(crop_box and len(crop_box) == 4 and crop_box[2] > 0 and crop_box[3] > 0)
    has_overlay = bool(overlay_png_path and os.path.isfile(overlay_png_path))
    has_partial_mute = bool(mute_ranges and len(mute_ranges) > 0 and not mute_all)

    # Temporary output for atomic write
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    tmp_out = os.path.join(out_dir, f".sadeem_export_{os.getpid()}_{os.path.basename(output_path)}")

    cmd = [_FFMPEG_BIN, "-y", "-hide_banner"]

    # Seeking input: fast seek before -i if possible
    if eff_start > 0:
        cmd.extend(["-ss", f"{eff_start:.3f}"])

    cmd.extend(["-i", input_path])

    # Secondary input for overlay if needed
    if has_overlay:
        cmd.extend(["-i", overlay_png_path])

    # Duration limit
    if trim_end is not None or eff_start > 0:
        cmd.extend(["-t", f"{target_duration:.3f}"])

    # Fast path: Stream Copy (no crop, no overlay, no partial mute)
    if not has_crop and not has_overlay and not has_partial_mute:
        cmd.extend(["-c:v", "copy"])
        if mute_all:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "copy"])
        cmd.extend(["-movflags", "+faststart"])
    # Audio-only re-encode path (partial mute, but no crop and no overlay)
    elif not has_crop and not has_overlay and has_partial_mute:
        cmd.extend(["-c:v", "copy"])
        # Build volume filter for mute ranges
        filters = []
        for ms, me in mute_ranges:
            # Shift timestamps relative to trim start
            rel_s = max(0.0, ms - eff_start)
            rel_e = max(0.0, me - eff_start)
            if rel_e > rel_s:
                filters.append(f"volume=enable='between(t,{rel_s:.3f},{rel_e:.3f})':volume=0")
        af_str = ",".join(filters) if filters else "anull"
        cmd.extend(["-af", af_str, "-c:a", "aac", "-b:a", "192k"])
        cmd.extend(["-movflags", "+faststart"])
    # Full re-encode path (crop or overlay or both)
    else:
        vf_filters = []
        if has_crop:
            cx, cy, cw, ch = crop_box
            # Ensure even dimensions for h264/yuv420p
            cw = int(cw // 2 * 2)
            ch = int(ch // 2 * 2)
            cx = int(cx // 2 * 2)
            cy = int(cy // 2 * 2)
            vf_filters.append(f"crop={cw}:{ch}:{cx}:{cy}")

        if has_overlay:
            # Overlay timing
            ov_s = max(0.0, (overlay_start if overlay_start is not None else 0.0) - eff_start)
            ov_e = max(0.0, (overlay_end if overlay_end is not None else target_duration) - eff_start)
            enable_expr = f"between(t,{ov_s:.3f},{ov_e:.3f})"
            # Use filter_complex for overlay input
            vf_crop_prefix = f"[0:v]{','.join(vf_filters)}[vcropped];[vcropped][1:v]" if vf_filters else "[0:v][1:v]"
            filter_complex = f"{vf_crop_prefix}overlay=0:0:enable='{enable_expr}'[vfinal]"
            cmd.extend(["-filter_complex", filter_complex, "-map", "[vfinal]"])
            if not mute_all:
                cmd.extend(["-map", "0:a?"])
        else:
            if vf_filters:
                cmd.extend(["-vf", ",".join(vf_filters)])

        # Video encoding settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "21",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])

        # Audio handling in re-encode path
        if mute_all:
            cmd.append("-an")
        elif has_partial_mute:
            filters = []
            for ms, me in mute_ranges:
                rel_s = max(0.0, ms - eff_start)
                rel_e = max(0.0, me - eff_start)
                if rel_e > rel_s:
                    filters.append(f"volume=enable='between(t,{rel_s:.3f},{rel_e:.3f})':volume=0")
            af_str = ",".join(filters) if filters else "anull"
            cmd.extend(["-af", af_str, "-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

    # Progress reporting pipe
    cmd.extend(["-progress", "pipe:1", tmp_out])

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Monitor progress in real-time
        out_time_re = re.compile(r"out_time_us=(\d+)")
        progress_re = re.compile(r"progress=(\w+)")

        for line in proc.stdout:
            if cancel_event and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    proc.kill()
                if os.path.isfile(tmp_out):
                    try:
                        os.remove(tmp_out)
                    except OSError:
                        pass
                return False, "Export cancelled by user"

            line = line.strip()
            m = out_time_re.match(line)
            if m and progress_callback:
                us = int(m.group(1))
                time_sec = us / 1_000_000.0
                fraction = min(1.0, max(0.0, time_sec / target_duration))
                progress_callback(fraction, time_sec)

        proc.wait()

        if proc.returncode != 0:
            err = proc.stderr.read() if proc.stderr else "FFmpeg process failed"
            if os.path.isfile(tmp_out):
                try:
                    os.remove(tmp_out)
                except OSError:
                    pass
            return False, err.strip()

        # Check final output file
        if not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) == 0:
            return False, "Generated output file is missing or empty"

        # Atomic replacement
        os.replace(tmp_out, output_path)

        if progress_callback:
            progress_callback(1.0, target_duration)

        return True, None

    except Exception as exc:
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        if os.path.isfile(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
        return False, str(exc)
