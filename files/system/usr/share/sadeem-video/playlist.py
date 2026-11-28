#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playlist management (natural sort + sibling folder discovery) and persistent
playback state (~/.config/sadeem-video/state.json) for Sadeem Video.
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple


VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".mpeg", ".mpg",
    ".m2ts", ".ts", ".ogv", ".3gp", ".3g2", ".m4v", ".wmv",
})

SUBTITLE_EXTENSIONS = frozenset({
    ".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx",
})

_NAT_RE = re.compile(r"(\d+)")
_URI_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def is_network_url(path: str) -> bool:
    if not path:
        return False
    low = path.strip().lower()
    if low.startswith("file://"):
        return False
    return bool(_URI_SCHEME_RE.match(low))


def normalize_media_target(target: str) -> str:
    if not target:
        return ""
    if is_network_url(target):
        return target.strip()
    return os.path.abspath(target)


def natural_sort_key(text: str) -> Tuple:
    """Case-insensitive natural sort key so ep2 sorts before ep10."""
    parts = _NAT_RE.split(text.casefold())
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part), part))
        elif part:
            key.append((1, 0, part))
    return tuple(key)


def is_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def is_subtitle_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUBTITLE_EXTENSIONS


def scan_sibling_videos(file_path: str) -> List[str]:
    """Return naturally sorted video paths from file_path's parent directory."""
    abs_path = os.path.abspath(file_path)
    parent = os.path.dirname(abs_path)
    if not parent or not os.path.isdir(parent):
        return [abs_path] if os.path.isfile(abs_path) else []

    items: List[str] = []
    try:
        with os.scandir(parent) as it:
            for entry in it:
                try:
                    if entry.is_file() and not entry.name.startswith(".") and is_video_file(entry.name):
                        items.append(os.path.abspath(entry.path))
                except OSError:
                    continue
    except OSError:
        return [abs_path] if os.path.isfile(abs_path) else []

    if os.path.isfile(abs_path) and abs_path not in items:
        items.append(abs_path)

    items.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
    return items


class PlaylistManager:
    """Manages an ordered playlist with sibling discovery and index tracking."""

    def __init__(self) -> None:
        self.items: List[str] = []
        self.current_index: int = -1

    @property
    def current_path(self) -> Optional[str]:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def load_with_siblings(self, target_path: str) -> Optional[str]:
        abs_target = os.path.abspath(target_path)
        siblings = scan_sibling_videos(abs_target)
        self.items = siblings
        if abs_target in self.items:
            self.current_index = self.items.index(abs_target)
        elif self.items:
            self.current_index = 0
        else:
            self.current_index = -1
        return self.current_path

    def add_files(self, paths: List[str], select_first_added: bool = False) -> int:
        added = 0
        first_new_idx = -1
        existing = set(self.items)
        for p in paths:
            if not p:
                continue
            abs_p = os.path.abspath(p)
            if abs_p not in existing and os.path.isfile(abs_p):
                existing.add(abs_p)
                if first_new_idx < 0:
                    first_new_idx = len(self.items)
                self.items.append(abs_p)
                added += 1
        if select_first_added and first_new_idx >= 0:
            self.current_index = first_new_idx
        elif self.current_index < 0 and self.items:
            self.current_index = 0
        return added

    def clear(self) -> None:
        self.items.clear()
        self.current_index = -1

    def set_current(self, index: int) -> Optional[str]:
        if 0 <= index < len(self.items):
            self.current_index = index
            return self.items[index]
        return None

    def select_path(self, path: str) -> Optional[str]:
        norm = normalize_media_target(path)
        if norm in self.items:
            self.current_index = self.items.index(norm)
            return norm
        if is_network_url(norm) or os.path.isfile(norm):
            self.items = [norm]
            self.current_index = 0
            return norm
        return None

    def has_next(self, wrap: bool = False) -> bool:
        if not self.items:
            return False
        return wrap or (self.current_index + 1 < len(self.items))

    def has_previous(self, wrap: bool = False) -> bool:
        if not self.items:
            return False
        return wrap or (self.current_index - 1 >= 0)

    def next(self, wrap: bool = False) -> Optional[str]:
        if not self.items:
            return None
        nxt = self.current_index + 1
        if nxt >= len(self.items):
            if wrap:
                nxt = 0
            else:
                return None
        self.current_index = nxt
        return self.items[nxt]

    def previous(self, wrap: bool = False) -> Optional[str]:
        if not self.items:
            return None
        prev = self.current_index - 1
        if prev < 0:
            if wrap:
                prev = len(self.items) - 1
            else:
                return None
        self.current_index = prev
        return self.items[prev]


class StateStore:
    """Persists watch positions, recent files, and playback settings in state.json."""

    MAX_POSITIONS = 200
    MAX_RECENT_FILES = 8
    RESUME_MIN_POS = 10.0
    RESUME_TAIL_MARGIN = 30.0
    RESUME_MODES = ("ask", "auto", "never")

    def __init__(self, state_path: Optional[str] = None) -> None:
        if state_path is None:
            cfg_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
                os.path.expanduser("~"), ".config"
            )
            state_path = os.path.join(cfg_home, "sadeem-video", "state.json")
        self.state_path = state_path
        self.data: Dict[str, Any] = {
            "positions": {},
            "recent_files": [],
            "settings": {
                "volume": 100.0,
                "muted": False,
                "speed": 1.0,
                "loop_mode": "off",
                "resume_mode": "ask",
                "pause_on_minimize": True,
                "sub_bidi_compat": False,
                "audio_night_mode": False,
                "audio_eq_preset": "normal",
                "sub_pos": 100,
                "sub_color": "#FFFFFF",
                "sub_back_box": False,
                "sub_font": "",
            },
        }
        self.load()

    def load(self) -> None:
        if not os.path.isfile(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                pos = raw.get("positions")
                if isinstance(pos, dict):
                    self.data["positions"] = pos
                recent = raw.get("recent_files")
                if isinstance(recent, list):
                    self.data["recent_files"] = [
                        item for item in recent
                        if isinstance(item, dict) and isinstance(item.get("path"), str)
                    ][: self.MAX_RECENT_FILES]
                settings = raw.get("settings")
                if isinstance(settings, dict):
                    self.data["settings"].update(settings)
        except Exception:
            pass

    def save(self) -> None:
        try:
            parent = os.path.dirname(self.state_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            # Keep newest MAX_POSITIONS entries
            positions = self.data.get("positions", {})
            if len(positions) > self.MAX_POSITIONS:
                sorted_items = sorted(
                    positions.items(),
                    key=lambda kv: float(kv[1].get("updated", 0.0)) if isinstance(kv[1], dict) else 0.0,
                    reverse=True,
                )[: self.MAX_POSITIONS]
                self.data["positions"] = dict(sorted_items)
            recent = self.data.get("recent_files", [])
            if isinstance(recent, list):
                recent.sort(key=lambda it: float(it.get("last_watched", 0.0)), reverse=True)
                self.data["recent_files"] = recent[: self.MAX_RECENT_FILES]
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def record_recent(self, file_path: str, pos: float = 0.0, duration: float = 0.0) -> None:
        if not file_path:
            return
        norm = normalize_media_target(file_path)
        now = round(time.time(), 2)
        recent = self.data.setdefault("recent_files", [])
        existing = next((it for it in recent if isinstance(it, dict) and it.get("path") == norm), None)
        clean_pos = round(max(0.0, float(pos)), 2)
        clean_dur = round(max(0.0, float(duration)), 2)
        if existing is not None:
            if clean_dur > 0.0:
                existing["duration"] = clean_dur
                existing["pos"] = clean_pos
            elif clean_pos > 0.0:
                existing["pos"] = clean_pos
            existing["last_watched"] = now
        else:
            recent.insert(
                0,
                {
                    "path": norm,
                    "pos": clean_pos,
                    "duration": clean_dur,
                    "last_watched": now,
                },
            )
        recent.sort(key=lambda it: float(it.get("last_watched", 0.0)), reverse=True)
        self.data["recent_files"] = recent[: self.MAX_RECENT_FILES]

    def get_recent_files(self, existing_only: bool = True, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        recent = self.data.get("recent_files", [])
        if not isinstance(recent, list):
            return []
        ordered = sorted(
            (it for it in recent if isinstance(it, dict) and it.get("path")),
            key=lambda it: float(it.get("last_watched", 0.0)),
            reverse=True,
        )
        out: List[Dict[str, Any]] = []
        for it in ordered:
            p = str(it["path"])
            if existing_only and not is_network_url(p) and not os.path.isfile(p):
                continue
            out.append(dict(it))
            if limit is not None and len(out) >= int(limit):
                break
        return out

    def clear_recent_files(self) -> None:
        self.data["recent_files"] = []
        self.save()

    def get_resume_position(self, file_path: str) -> float:
        norm = normalize_media_target(file_path)
        entry = self.data.get("positions", {}).get(norm)
        if not isinstance(entry, dict):
            return 0.0
        pos = float(entry.get("pos", 0.0))
        dur = float(entry.get("duration", 0.0))
        if pos <= self.RESUME_MIN_POS:
            return 0.0
        if dur > 0.0 and pos >= (dur - self.RESUME_TAIL_MARGIN):
            return 0.0
        return pos

    def get_resume_action(self, file_path: str) -> Tuple[str, float, float]:
        """
        Return (mode, immediate_start_sec, ask_prompt_sec) according to resume_mode.
        - 'ask'  : starts at 0.0 and returns prompt position if valid.
        - 'auto' : returns saved position as immediate_start_sec.
        - 'never': always starts at 0.0 with no prompt.
        """
        mode = str(self.get_setting("resume_mode", "ask"))
        if mode not in self.RESUME_MODES:
            mode = "ask"
        saved = self.get_resume_position(file_path)
        if saved <= 0.0 or mode == "never":
            return mode, 0.0, 0.0
        if mode == "auto":
            return mode, saved, 0.0
        return "ask", 0.0, saved

    def set_position(self, file_path: str, pos: float, duration: float) -> None:
        if not file_path:
            return
        norm = normalize_media_target(file_path)
        positions = self.data.setdefault("positions", {})
        if duration > 0.0 and pos >= (duration - self.RESUME_TAIL_MARGIN):
            # Completed playback (within last 30s): reset stored resume position
            positions.pop(norm, None)
        else:
            positions[norm] = {
                "pos": round(max(0.0, float(pos)), 2),
                "duration": round(max(0.0, float(duration)), 2),
                "updated": round(time.time(), 2),
            }
        self.record_recent(norm, pos=pos, duration=duration)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.data.get("settings", {}).get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.data.setdefault("settings", {})[key] = value
