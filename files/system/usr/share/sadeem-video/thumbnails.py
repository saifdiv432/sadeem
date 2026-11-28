#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
On-demand seekbar preview thumbnail extractor for Sadeem Video (فيديو سديم).
Runs ffmpeg asynchronously in a debounced low-priority worker with in-memory LRU caching.
"""

from collections import OrderedDict
import os
import re
import shutil
import subprocess
import threading
from typing import Any, Callable, Optional, Tuple


_NETWORK_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def is_network_url(target: str) -> bool:
    if not target:
        return False
    low = target.strip().lower()
    if low.startswith("file://"):
        return False
    return bool(_NETWORK_URI_RE.match(low))


def compute_quantized_step(duration: float) -> float:
    """Return dynamic timestamp quantization step (2-5s) scaled to video duration."""
    if duration <= 0.0:
        return 2.0
    if duration <= 300.0:
        return 2.0
    if duration <= 1800.0:
        return 3.0
    if duration <= 3600.0:
        return 4.0
    return 5.0


def quantize_timestamp(seconds: float, duration: float) -> float:
    """Snap hover seek time to nearest quantization bucket within valid media bounds."""
    step = compute_quantized_step(duration)
    clamped = max(0.0, float(seconds))
    if duration > 1.0:
        clamped = min(clamped, max(0.0, duration - 0.5))
    snapped = round(clamped / step) * step
    if duration > 1.0:
        snapped = min(snapped, max(0.0, duration - 0.5))
    return round(max(0.0, snapped), 2)


class ThumbnailExtractor:
    """Debounced background ffmpeg thumbnail extractor with an in-memory LRU cache."""

    DEFAULT_CACHE_SIZE = 60
    DEFAULT_DEBOUNCE_MS = 140
    DEFAULT_WIDTH = 160
    FFMPEG_TIMEOUT_S = 2.5

    def __init__(
        self,
        ffmpeg_bin: Optional[str] = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        thumb_width: int = DEFAULT_WIDTH,
        dispatcher: Optional[Callable[[Callable[[], Any]], Any]] = None,
    ) -> None:
        self._ffmpeg_bin = ffmpeg_bin if ffmpeg_bin is not None else shutil.which("ffmpeg")
        self._cache_size = max(1, int(cache_size))
        self._debounce_s = max(0.0, float(debounce_ms) / 1000.0)
        self._thumb_width = max(64, int(thumb_width))
        self._dispatcher = dispatcher

        self._lock = threading.Lock()
        self._cache: "OrderedDict[Tuple[str, float], bytes]" = OrderedDict()
        self._current_video: Optional[str] = None
        self._request_seq: int = 0
        self._debounce_timer: Optional[threading.Timer] = None
        self._active_proc: Optional[subprocess.Popen] = None
        self._destroyed: bool = False

    @property
    def is_available(self) -> bool:
        return bool(self._ffmpeg_bin) and not self._destroyed

    @staticmethod
    def can_extract_for(path: Optional[str]) -> bool:
        if not path or is_network_url(path):
            return False
        return os.path.isfile(path)

    def _dispatch(self, fn: Callable[[], None]) -> None:
        if self._destroyed:
            return
        if self._dispatcher is not None:
            self._dispatcher(fn)
        else:
            fn()

    def _terminate_active_proc_locked(self) -> None:
        proc = self._active_proc
        self._active_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    def _cancel_timer_locked(self) -> None:
        if self._debounce_timer is not None:
            try:
                self._debounce_timer.cancel()
            except Exception:
                pass
            self._debounce_timer = None

    def clear(self, clear_cache: bool = True) -> None:
        """Cancel pending debounce/ffmpeg tasks and optionally empty the LRU cache."""
        with self._lock:
            self._request_seq += 1
            self._cancel_timer_locked()
            self._terminate_active_proc_locked()
            if clear_cache:
                self._cache.clear()

    def set_video(self, path: Optional[str]) -> None:
        """Switch active video source and discard stale queued extractions."""
        with self._lock:
            if path == self._current_video:
                return
            self._current_video = path
            self._request_seq += 1
            self._cancel_timer_locked()
            self._terminate_active_proc_locked()
            self._cache.clear()

    def get_cached(self, video_path: str, seconds: float, duration: float) -> Optional[bytes]:
        q_ts = quantize_timestamp(seconds, duration)
        key = (video_path, q_ts)
        with self._lock:
            data = self._cache.get(key)
            if data is not None:
                self._cache.move_to_end(key)
            return data

    def _put_cached(self, key: Tuple[str, float], data: bytes) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = data
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def request_thumbnail(
        self,
        video_path: str,
        seconds: float,
        duration: float,
        on_ready: Callable[[str, float, Optional[bytes]], None],
    ) -> bool:
        """
        Schedule debounced extraction for (video_path, seconds).
        Returns True if a cached hit or extraction was scheduled; False if ineligible.
        """
        if not self.is_available or not self.can_extract_for(video_path):
            return False

        q_ts = quantize_timestamp(seconds, duration)
        key = (video_path, q_ts)

        with self._lock:
            if self._destroyed:
                return False
            self._current_video = video_path
            if key in self._cache:
                self._cache.move_to_end(key)
                cached = self._cache[key]
                self._request_seq += 1
                self._cancel_timer_locked()
                self._dispatch(lambda vp=video_path, ts=q_ts, b=cached: on_ready(vp, ts, b))
                return True

            self._request_seq += 1
            seq = self._request_seq
            self._cancel_timer_locked()

            timer = threading.Timer(
                self._debounce_s,
                self._start_worker,
                args=(seq, video_path, q_ts, on_ready),
            )
            timer.daemon = True
            self._debounce_timer = timer
            timer.start()
            return True

    def _start_worker(
        self,
        seq: int,
        video_path: str,
        q_ts: float,
        on_ready: Callable[[str, float, Optional[bytes]], None],
    ) -> None:
        with self._lock:
            if self._destroyed or seq != self._request_seq or video_path != self._current_video:
                return
            self._debounce_timer = None
            self._terminate_active_proc_locked()

        t = threading.Thread(
            target=self._run_ffmpeg,
            args=(seq, video_path, q_ts, on_ready),
            daemon=True,
        )
        t.start()

    @staticmethod
    def _lower_priority() -> None:
        try:
            os.nice(10)
        except Exception:
            pass

    def _run_ffmpeg(
        self,
        seq: int,
        video_path: str,
        q_ts: float,
        on_ready: Callable[[str, float, Optional[bytes]], None],
    ) -> None:
        cmd = [
            str(self._ffmpeg_bin),
            "-nostdin",
            "-loglevel",
            "error",
            "-ss",
            f"{q_ts:.3f}",
            "-i",
            video_path,
            "-frames:v",
            "1",
            "-vf",
            f"scale={self._thumb_width}:-1:flags=fast_bilinear",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ]
        png_bytes: Optional[bytes] = None
        proc: Optional[subprocess.Popen] = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                preexec_fn=self._lower_priority,
            )
            with self._lock:
                if self._destroyed or seq != self._request_seq:
                    proc.kill()
                    proc.wait(timeout=0.5)
                    return
                self._active_proc = proc

            out, _ = proc.communicate(timeout=self.FFMPEG_TIMEOUT_S)
            if proc.returncode == 0 and out and len(out) > 16:
                png_bytes = out
        except subprocess.TimeoutExpired:
            if proc is not None:
                try:
                    proc.kill()
                    proc.communicate(timeout=0.5)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            with self._lock:
                if self._active_proc is proc:
                    self._active_proc = None

        if png_bytes:
            self._put_cached((video_path, q_ts), png_bytes)

        with self._lock:
            still_current = (not self._destroyed) and (seq == self._request_seq) and (video_path == self._current_video)

        if still_current and png_bytes:
            self._dispatch(lambda vp=video_path, ts=q_ts, b=png_bytes: on_ready(vp, ts, b))

    def shutdown(self) -> None:
        with self._lock:
            self._destroyed = True
            self._request_seq += 1
            self._cancel_timer_locked()
            self._terminate_active_proc_locked()
            self._cache.clear()
