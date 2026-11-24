#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video metadata extraction, duration formatting, and filmstrip thumbnail generation
for Sadeem Video Editor using ffprobe and ffmpeg.
"""

import json
import os
import shutil
import subprocess
import tempfile

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

_FFPROBE_BIN = shutil.which("ffprobe")
_FFMPEG_BIN = shutil.which("ffmpeg")


def is_video_file(path):
    if not path:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in VIDEO_EXTS


def format_duration(seconds):
    """Format duration in seconds to MM:SS or HH:MM:SS (or MM:SS.s when precision needed)."""
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


def has_audio_stream(path):
    """Check if the video has at least one valid audio stream."""
    if not _FFPROBE_BIN or not os.path.isfile(path):
        return False
    cmd = [
        _FFPROBE_BIN,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
        return bool(res.stdout.strip())
    except Exception:
        return False


def get_video_metadata(path):
    """
    Extract video width, height, duration (seconds float), framerate, codec,
    and audio presence via ffprobe. Returns a dict.
    """
    res = {
        "width": 0,
        "height": 0,
        "duration": 0.0,
        "duration_str": "00:00",
        "framerate": 30.0,
        "codec": "",
        "has_audio": False,
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

    res["has_audio"] = has_audio_stream(path)
    return res


def extract_filmstrip_frames(video_path, duration, count=12, thumb_height=56):
    """
    Extract a sequence of evenly spaced thumbnail frames across the video duration
    using a single fast FFmpeg invocation.

    Returns:
    (temp_dir: str, thumb_paths: list of str)
    """
    if not _FFMPEG_BIN or not os.path.isfile(video_path):
        return None, []

    count = max(1, min(64, int(count)))
    thumb_h = max(24, int(thumb_height))
    out_dir = tempfile.mkdtemp(prefix="sadeem_filmstrip_")

    try:
        eff_dur = float(duration) if duration and duration > 0.1 else 1.0
    except (ValueError, TypeError):
        eff_dur = 1.0

    if eff_dur <= 0.2:
        # Very short clip: single frame at 0.0s
        out_file = os.path.join(out_dir, "thumb_001.jpg")
        cmd = [
            _FFMPEG_BIN, "-y", "-hide_banner", "-v", "error",
            "-ss", "00:00:00.000",
            "-i", video_path,
            "-vframes", "1",
            "-vf", f"scale=-1:{thumb_h}:flags=fast_bilinear",
            "-q:v", "4",
            out_file,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=4.0, check=False)
            if os.path.isfile(out_file) and os.path.getsize(out_file) > 0:
                return out_dir, [out_file]
        except Exception:
            pass
        return out_dir, []

    # Fast sequential multi-frame extraction via fps filter
    fps_rate = count / eff_dur
    out_pattern = os.path.join(out_dir, "thumb_%03d.jpg")
    cmd = [
        _FFMPEG_BIN, "-y", "-hide_banner", "-v", "error",
        "-i", video_path,
        "-vf", f"fps={fps_rate:.6f},scale=-1:{thumb_h}:flags=fast_bilinear",
        "-q:v", "4",
        out_pattern,
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=8.0, check=False)
        files = sorted(
            [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("thumb_") and f.endswith(".jpg")]
        )
        return out_dir, files[:count]
    except Exception:
        return out_dir, []
