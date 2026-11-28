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
        abs_p = os.path.abspath(path)
        if abs_p in self.items:
            self.current_index = self.items.index(abs_p)
            return abs_p
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
    """Persists watch positions and playback settings in state.json."""

    MAX_POSITIONS = 200

    def __init__(self, state_path: Optional[str] = None) -> None:
        if state_path is None:
            cfg_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
                os.path.expanduser("~"), ".config"
            )
            state_path = os.path.join(cfg_home, "sadeem-video", "state.json")
        self.state_path = state_path
        self.data: Dict[str, Any] = {
            "positions": {},
            "settings": {
                "volume": 100.0,
                "muted": False,
                "speed": 1.0,
                "loop_mode": "off",
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
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_resume_position(self, file_path: str) -> float:
        abs_p = os.path.abspath(file_path)
        entry = self.data.get("positions", {}).get(abs_p)
        if not isinstance(entry, dict):
            return 0.0
        pos = float(entry.get("pos", 0.0))
        dur = float(entry.get("duration", 0.0))
        if pos < 3.0:
            return 0.0
        if dur > 10.0 and pos >= (dur - 5.0):
            return 0.0
        return pos

    def set_position(self, file_path: str, pos: float, duration: float) -> None:
        if not file_path:
            return
        abs_p = os.path.abspath(file_path)
        positions = self.data.setdefault("positions", {})
        if duration > 10.0 and pos >= (duration - 5.0):
            # Completed playback: reset stored resume position
            positions.pop(abs_p, None)
        else:
            positions[abs_p] = {
                "pos": round(max(0.0, float(pos)), 2),
                "duration": round(max(0.0, float(duration)), 2),
                "updated": round(time.time(), 2),
            }

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.data.get("settings", {}).get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.data.setdefault("settings", {})[key] = value
