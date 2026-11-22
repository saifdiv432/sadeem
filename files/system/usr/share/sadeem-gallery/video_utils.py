#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video metadata extraction, duration formatting, and fast thumbnail generation
for Sadeem Gallery using ffprobe and ffmpeg.
"""

import json
import os
import shutil
import subprocess

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

_FFPROBE_BIN = shutil.which("ffprobe")
_FFMPEG_BIN = shutil.which("ffmpeg")


def is_video_file(path):
    if not path:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in VIDEO_EXTS


def format_duration(seconds):
    """Format duration in seconds to MM:SS or HH:MM:SS."""
    try:
        s = max(0, int(round(float(seconds))))
    except (ValueError, TypeError):
        return "00:00"

    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60

    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def get_video_metadata(path):
    """
    Extract video width, height, duration (seconds float), framerate, and codec
    via ffprobe. Returns a dict.
    """
    res = {
        "width": 0,
        "height": 0,
        "duration": 0.0,
        "duration_str": "00:00",
        "framerate": 30.0,
        "codec": "",
    }
    if not _FFPROBE_BIN or not os.path.isfile(path):
        return res

    cmd = [
        _FFPROBE_BIN,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration,size",
        "-of", "json",
        path,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
        if proc.returncode == 0 and proc.stdout:
            data = json.loads(proc.stdout)
            streams = data.get("streams", [])
            fmt = data.get("format", {})

            if streams:
                v = streams[0]
                res["width"] = int(v.get("width") or 0)
                res["height"] = int(v.get("height") or 0)
                res["codec"] = v.get("codec_name") or ""
                fps_raw = v.get("r_frame_rate", "30/1")
                if "/" in fps_raw:
                    num, den = fps_raw.split("/", 1)
                    try:
                        n, d = float(num), float(den)
                        if d > 0:
                            res["framerate"] = round(n / d, 2)
                    except ValueError:
                        pass
                else:
                    try:
                        res["framerate"] = float(fps_raw)
                    except ValueError:
                        pass

            dur_raw = fmt.get("duration")
            if dur_raw:
                try:
                    dur_val = float(dur_raw)
                    res["duration"] = max(0.0, dur_val)
                    res["duration_str"] = format_duration(dur_val)
                except ValueError:
                    pass
    except Exception:
        pass

    return res


def generate_video_thumbnail(video_path, output_path, duration=None):
    """
    Extract a clean representative thumbnail frame using ffmpeg.
    Uses seek to 1.0s or mid-point if short, scaling to max width 360px.
    """
    if not _FFMPEG_BIN or not os.path.isfile(video_path) or not output_path:
        return False

    seek_time = "00:00:01.000"
    if duration is not None:
        try:
            d = float(duration)
            if d <= 1.5 and d > 0.1:
                seek_time = f"{d / 2.0:.3f}"
            elif d <= 0.1:
                seek_time = "00:00:00.000"
        except (ValueError, TypeError):
            pass

    cmd = [
        _FFMPEG_BIN,
        "-y",
        "-ss", seek_time,
        "-i", video_path,
        "-vframes", "1",
        "-vf", "scale=360:-1:flags=lanczos",
        "-q:v", "3",
        output_path,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=5.0, check=False)
        if proc.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return True
    except Exception:
        pass

    # Fallback to seeking at 0.0s if 1.0s failed (e.g. video shorter than 1s)
    if seek_time != "00:00:00.000":
        try:
            cmd[2] = "00:00:00.000"
            proc = subprocess.run(cmd, capture_output=True, timeout=4.0, check=False)
            if proc.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception:
            pass

    return False
