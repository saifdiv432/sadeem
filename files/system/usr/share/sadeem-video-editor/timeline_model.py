#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timeline Model for Sadeem Video Editor.
Manages:
- Video segments covering [0.0 .. duration] with speed (0.5x .. 4.0x) and keep/cut status.
- Independent overlay items (drawings, arrows, shapes, text, blur).
- Audio mute ranges.
- External audio track positioning and trimming.
- Time mapping from source video space to output timeline space.
- Undo / Redo serialization.
"""

import copy
import math


class TimelineModel:
    def __init__(self, duration=0.0):
        self.duration = max(0.1, float(duration))
        self._next_id = 1
        self._next_audio_id = 1
        self._next_overlay_id = 1
        self._next_mute_id = 1
        self._next_ext_audio_id = 1
        self.segments = []
        self.audio_segments = []
        self.overlays = []
        self.mute_ranges = []
        self.external_audio = None
        self.external_audio_clips = []
        self.reset()

    def reset(self, duration=None):
        """Reset timeline to a single full segment [0.0, duration] and clear tracks."""
        if duration is not None:
            self.duration = max(0.1, float(duration))
        self._next_id = 1
        self._next_audio_id = 1
        self._next_overlay_id = 1
        self._next_mute_id = 1
        self._next_ext_audio_id = 1
        self.segments = [
            {
                "id": self._next_id,
                "start": 0.0,
                "end": self.duration,
                "kept": True,
                "speed": 1.0,
            }
        ]
        self._next_id += 1
        self.audio_segments = [
            {
                "id": self._next_audio_id,
                "start": 0.0,
                "end": self.duration,
                "kept": True,
            }
        ]
        self._next_audio_id += 1
        self.overlays = []
        self.mute_ranges = []
        self.external_audio = None
        self.external_audio_clips = []

    def count(self):
        """Return total number of segments."""
        return len(self.segments)

    def kept_count(self):
        """Return number of segments marked as kept."""
        return sum(1 for s in self.segments if s.get("kept", True))

    def get_segment_by_id(self, seg_id):
        """Retrieve segment by unique ID."""
        for s in self.segments:
            if s["id"] == seg_id:
                return s
        return None

    def get_segment_at(self, time_sec):
        """Find the segment containing time_sec."""
        t = max(0.0, min(self.duration, float(time_sec)))
        for i, s in enumerate(self.segments):
            if i == len(self.segments) - 1:
                if s["start"] <= t <= s["end"]:
                    return s
            else:
                if s["start"] <= t < s["end"]:
                    return s
        return self.segments[-1] if self.segments else None

    def get_segment_index_at(self, time_sec):
        """Find the index of the segment containing time_sec."""
        t = max(0.0, min(self.duration, float(time_sec)))
        for i, s in enumerate(self.segments):
            if i == len(self.segments) - 1:
                if s["start"] <= t <= s["end"]:
                    return i
            else:
                if s["start"] <= t < s["end"]:
                    return i
        return len(self.segments) - 1 if self.segments else 0

    def split_at(self, time_sec, min_seg=0.2):
        """
        Split the segment containing time_sec into two contiguous segments.
        Both resulting segments must be at least min_seg in length.
        Returns newly created segment ID if successful, None otherwise.
        """
        t = float(time_sec)
        idx = self.get_segment_index_at(t)
        if idx < 0 or idx >= len(self.segments):
            return None

        seg = self.segments[idx]
        if (t - seg["start"] < min_seg) or (seg["end"] - t < min_seg):
            return None

        new_id = self._next_id
        self._next_id += 1

        right_seg = {
            "id": new_id,
            "start": t,
            "end": seg["end"],
            "kept": seg.get("kept", True),
            "speed": seg.get("speed", 1.0),
        }
        seg["end"] = t
        self.segments.insert(idx + 1, right_seg)
        return new_id

    def delete_segment(self, seg_id):
        """
        Mark the segment with seg_id as deleted (kept = False).
        Rejects operation and returns False if this is the only kept segment.
        """
        seg = self.get_segment_by_id(seg_id)
        if not seg:
            return False

        if not seg.get("kept", True):
            return True

        if self.kept_count() <= 1:
            return False

        seg["kept"] = False
        return True

    def restore_segment(self, seg_id):
        """Restore a deleted segment (kept = True)."""
        seg = self.get_segment_by_id(seg_id)
        if not seg:
            return False
        seg["kept"] = True
        return True

    def toggle_segment_kept(self, seg_id):
        """Toggle kept state of segment, respecting the minimum 1 kept segment rule."""
        seg = self.get_segment_by_id(seg_id)
        if not seg:
            return False
        if seg.get("kept", True):
            return self.delete_segment(seg_id)
        else:
            return self.restore_segment(seg_id)

    def keep_only_segment(self, seg_id):
        """Keep only the specified segment and mark all others as deleted."""
        target = self.get_segment_by_id(seg_id)
        if not target:
            return False

        for s in self.segments:
            s["kept"] = (s["id"] == seg_id)
        return True

    def set_segment_speed(self, seg_id, speed):
        """Set speed multiplier for the segment (e.g. 0.5, 1.0, 1.5, 2.0, 4.0)."""
        seg = self.get_segment_by_id(seg_id)
        if not seg:
            return False
        try:
            sp = float(speed)
            if sp <= 0.05:
                sp = 1.0
            seg["speed"] = sp
            return True
        except (ValueError, TypeError):
            return False

    def move_cut_boundary(self, left_idx, new_time, min_seg=0.2):
        """
        Move the boundary between segments[left_idx] and segments[left_idx + 1].
        Ensures both segments remain >= min_seg in length.
        """
        if left_idx < 0 or left_idx >= len(self.segments) - 1:
            return False

        s_left = self.segments[left_idx]
        s_right = self.segments[left_idx + 1]

        t = float(new_time)
        min_allowed = s_left["start"] + min_seg
        max_allowed = s_right["end"] - min_seg

        if min_allowed > max_allowed:
            return False

        t_clamped = max(min_allowed, min(max_allowed, t))
        s_left["end"] = t_clamped
        s_right["start"] = t_clamped
        return True

    # -------------------------------------------------------------------------
    # ORIGINAL AUDIO TRACK & SEGMENTS (INDEPENDENT FROM VIDEO)
    # -------------------------------------------------------------------------
    def get_audio_segment_by_id(self, seg_id):
        """Retrieve original audio segment by unique ID."""
        for s in self.audio_segments:
            if s["id"] == seg_id:
                return s
        return None

    def get_audio_segment_at(self, time_sec):
        """Find the audio segment containing time_sec."""
        t = max(0.0, min(self.duration, float(time_sec)))
        for i, s in enumerate(self.audio_segments):
            if i == len(self.audio_segments) - 1:
                if s["start"] <= t <= s["end"]:
                    return s
            else:
                if s["start"] <= t < s["end"]:
                    return s
        return self.audio_segments[-1] if self.audio_segments else None

    def get_audio_segment_index_at(self, time_sec):
        """Find the index of the audio segment containing time_sec."""
        t = max(0.0, min(self.duration, float(time_sec)))
        for i, s in enumerate(self.audio_segments):
            if i == len(self.audio_segments) - 1:
                if s["start"] <= t <= s["end"]:
                    return i
            else:
                if s["start"] <= t < s["end"]:
                    return i
        return len(self.audio_segments) - 1 if self.audio_segments else 0

    def split_audio_at(self, time_sec, min_seg=0.2):
        """
        Split original audio segment containing time_sec into two contiguous segments.
        Both resulting segments must be >= min_seg in duration.
        Does NOT alter or split video segments.
        Returns newly created segment ID if successful, None otherwise.
        """
        t = float(time_sec)
        idx = self.get_audio_segment_index_at(t)
        if idx < 0 or idx >= len(self.audio_segments):
            return None

        seg = self.audio_segments[idx]
        if (t - seg["start"] < min_seg) or (seg["end"] - t < min_seg):
            return None

        new_id = self._next_audio_id
        self._next_audio_id += 1

        right_seg = {
            "id": new_id,
            "start": t,
            "end": seg["end"],
            "kept": seg.get("kept", True),
        }
        seg["end"] = t
        self.audio_segments.insert(idx + 1, right_seg)
        return new_id

    def toggle_audio_segment_kept(self, seg_id):
        """Toggle kept state of an audio segment (mute or unmute)."""
        seg = self.get_audio_segment_by_id(seg_id)
        if not seg:
            return False
        seg["kept"] = not seg.get("kept", True)
        return True

    def delete_audio_segment(self, seg_id):
        """Mute an audio segment (kept = False)."""
        seg = self.get_audio_segment_by_id(seg_id)
        if not seg:
            return False
        seg["kept"] = False
        return True

    def restore_audio_segment(self, seg_id):
        """Unmute an audio segment (kept = True)."""
        seg = self.get_audio_segment_by_id(seg_id)
        if not seg:
            return False
        seg["kept"] = True
        return True

    def move_audio_cut_boundary(self, left_idx, new_time, min_seg=0.2):
        """
        Move boundary between audio_segments[left_idx] and audio_segments[left_idx + 1].
        Ensures both segments remain >= min_seg.
        """
        if left_idx < 0 or left_idx >= len(self.audio_segments) - 1:
            return False

        s_left = self.audio_segments[left_idx]
        s_right = self.audio_segments[left_idx + 1]

        t = float(new_time)
        min_allowed = s_left["start"] + min_seg
        max_allowed = s_right["end"] - min_seg

        if min_allowed > max_allowed:
            return False

        t_clamped = max(min_allowed, min(max_allowed, t))
        s_left["end"] = t_clamped
        s_right["start"] = t_clamped
        return True

    def get_muted_source_ranges(self):
        """
        Gathers all muted time ranges from non-kept audio segments (kept=False)
        and explicitly added mute_ranges. Merges overlapping or adjacent intervals.
        Returns a sorted list of (start_sec, end_sec) tuples in source time.
        """
        raw_intervals = []
        for s in self.audio_segments:
            if not s.get("kept", True):
                raw_intervals.append((round(s["start"], 4), round(s["end"], 4)))
        for m in self.mute_ranges:
            raw_intervals.append((round(m["start"], 4), round(m["end"], 4)))

        if not raw_intervals:
            return []

        raw_intervals.sort(key=lambda x: (x[0], x[1]))
        merged = []
        for s, e in raw_intervals:
            if not merged:
                merged.append([s, e])
            else:
                prev = merged[-1]
                if s <= prev[1] + 0.005:
                    prev[1] = max(prev[1], e)
                else:
                    merged.append([s, e])

        return [(m[0], m[1]) for m in merged]

    def get_kept_segments(self):
        """Return list of active kept segment dictionaries with speed."""
        return [
            {
                "id": s["id"],
                "start": round(s["start"], 4),
                "end": round(s["end"], 4),
                "speed": s.get("speed", 1.0),
            }
            for s in self.segments
            if s.get("kept", True)
        ]

    def get_kept_ranges(self):
        """
        Return merged list of contiguous kept time ranges [(start, end), ...].
        Adjacent kept segments with the same speed are merged.
        """
        ranges = []
        cur_start = None
        cur_end = None
        cur_speed = None

        for s in self.segments:
            if s.get("kept", True):
                sp = s.get("speed", 1.0)
                if cur_start is None:
                    cur_start = s["start"]
                    cur_end = s["end"]
                    cur_speed = sp
                else:
                    if abs(s["start"] - cur_end) < 0.001 and abs(sp - cur_speed) < 0.01:
                        cur_end = s["end"]
                    else:
                        ranges.append((round(cur_start, 4), round(cur_end, 4)))
                        cur_start = s["start"]
                        cur_end = s["end"]
                        cur_speed = sp
            else:
                if cur_start is not None:
                    ranges.append((round(cur_start, 4), round(cur_end, 4)))
                    cur_start = None
                    cur_end = None
                    cur_speed = None

        if cur_start is not None:
            ranges.append((round(cur_start, 4), round(cur_end, 4)))

        return ranges

    def get_output_duration(self):
        """Calculate total duration of all kept segments in seconds, taking speed into account."""
        dur = 0.0
        for s in self.segments:
            if s.get("kept", True):
                sp = max(0.05, s.get("speed", 1.0))
                dur += (s["end"] - s["start"]) / sp
        return dur

    def next_playable_time(self, cur_sec):
        """
        Smart playback helper:
        If cur_sec is inside a deleted segment (kept=False), returns the start
        time of the next kept segment.
        If past all kept segments, returns None.
        If inside a kept segment, returns cur_sec.
        """
        t = max(0.0, min(self.duration, float(cur_sec)))
        seg = self.get_segment_at(t)
        if not seg:
            return None

        if seg.get("kept", True):
            return t

        for s in self.segments:
            if s["start"] >= seg["end"] - 0.001 and s.get("kept", True):
                return s["start"]

        return None

    # -------------------------------------------------------------------------
    # TIME MAPPING (SOURCE TIME <-> OUTPUT TIMELINE TIME)
    # -------------------------------------------------------------------------
    def map_source_to_output_time(self, src_t):
        """
        Converts a timestamp in original source video time to its corresponding
        timestamp in the exported/output video timeline.
        Accounts for deleted (skipped) segments and per-segment speed alterations.
        """
        t = float(src_t)
        out_time = 0.0

        for s in self.segments:
            seg_start = s["start"]
            seg_end = s["end"]
            seg_sp = max(0.05, s.get("speed", 1.0))

            if not s.get("kept", True):
                if t <= seg_start:
                    return out_time
                elif t <= seg_end:
                    return out_time
                continue

            # Segment is kept
            if t <= seg_start:
                return out_time
            elif t <= seg_end:
                offset_out = (t - seg_start) / seg_sp
                return out_time + offset_out
            else:
                out_time += (seg_end - seg_start) / seg_sp

        return out_time

    def map_source_range_to_output_ranges(self, start_sec, end_sec):
        """
        Converts a time interval [start_sec, end_sec] in source video time
        into a list of active intervals [(out_s, out_e), ...] in output time.
        Excludes portions that fall into deleted segments.
        """
        s_req = max(0.0, float(start_sec))
        e_req = min(self.duration, float(end_sec))
        if e_req <= s_req:
            return []

        out_ranges = []
        for seg in self.segments:
            if not seg.get("kept", True):
                continue

            inter_s = max(s_req, seg["start"])
            inter_e = min(e_req, seg["end"])
            if inter_e > inter_s + 0.002:
                out_s = self.map_source_to_output_time(inter_s)
                out_e = self.map_source_to_output_time(inter_e)
                if out_e > out_s + 0.001:
                    out_ranges.append((round(out_s, 4), round(out_e, 4)))

        # Merge adjacent or overlapping output intervals
        merged = []
        for r_s, r_e in out_ranges:
            if not merged:
                merged.append([r_s, r_e])
            else:
                prev = merged[-1]
                if r_s <= prev[1] + 0.005:
                    prev[1] = max(prev[1], r_e)
                else:
                    merged.append([r_s, r_e])

        return [(m[0], m[1]) for m in merged]

    # -------------------------------------------------------------------------
    # OVERLAYS (MARKUP & BLUR TRACK)
    # -------------------------------------------------------------------------
    def add_overlay(self, tool, start=None, end=None, **data):
        """
        Add an overlay annotation item (freehand, arrow, rect, ellipse, text, blur).
        Returns unique overlay ID.
        """
        s = max(0.0, float(start)) if start is not None else 0.0
        s_floored = math.floor(s * 1000.0) / 1000.0
        e = min(self.duration, max(s + 0.2, float(end))) if end is not None else min(self.duration, s + 3.0)

        ov_id = self._next_overlay_id
        self._next_overlay_id += 1

        item = {
            "id": ov_id,
            "tool": str(tool),
            "start": s_floored,
            "end": round(e, 3),
            "color": data.get("color", "#7a1c33"),
            "width": max(1.0, float(data.get("width", 5.0))),
            "font_size": int(data.get("font_size", 24)),
            "blur_style": str(data.get("blur_style", "pixelate")),
            "blur_strength": max(1, min(100, int(data.get("blur_strength", 50)))),
        }
        for k in ("points", "x1", "y1", "x2", "y2", "text"):
            if k in data:
                item[k] = copy.deepcopy(data[k])

        self.overlays.append(item)
        return ov_id

    def get_overlay_by_id(self, ov_id):
        for o in self.overlays:
            if o["id"] == ov_id:
                return o
        return None

    def update_overlay_timing(self, ov_id, start, end, min_dur=0.2):
        item = self.get_overlay_by_id(ov_id)
        if not item:
            return False
        s = max(0.0, min(self.duration - min_dur, float(start)))
        e = max(s + min_dur, min(self.duration, float(end)))
        item["start"] = round(s, 3)
        item["end"] = round(e, 3)
        return True

    def update_overlay(self, ov_id, **fields):
        """Update properties of an overlay (e.g. text, font_size, color, blur_strength, blur_style)."""
        item = self.get_overlay_by_id(ov_id)
        if not item:
            return False
        for k, v in fields.items():
            if k == "blur_strength":
                item[k] = max(1, min(100, int(v)))
            elif k == "width":
                item[k] = max(1.0, float(v))
            elif k == "font_size":
                item[k] = max(8, int(v))
            elif k in ("start", "end"):
                item[k] = round(float(v), 3)
            else:
                item[k] = copy.deepcopy(v)
        return True

    def move_overlay(self, ov_id, dx, dy, orig_state=None, video_w=None, video_h=None):
        """Move an overlay in 2D coordinate space, optionally from an orig_state baseline."""
        ov = self.get_overlay_by_id(ov_id)
        if not ov:
            return False
        if isinstance(orig_state, (int, float)):
            video_h = video_w
            video_w = orig_state
            orig_state = None
        base = orig_state if isinstance(orig_state, dict) else ov
        ov.pop("_pill_bounds", None)

        dx = float(dx)
        dy = float(dy)

        if "points" in base and base["points"]:
            pts = base["points"]
            min_x = min(p[0] for p in pts)
            max_x = max(p[0] for p in pts)
            min_y = min(p[1] for p in pts)
            max_y = max(p[1] for p in pts)
            if video_w is not None and video_h is not None and video_w > 0 and video_h > 0:
                if min_x + dx < 0 and dx < 0:
                    dx = -min_x
                if max_x + dx > video_w and dx > 0:
                    dx = video_w - max_x
                if min_y + dy < 0 and dy < 0:
                    dy = -min_y
                if max_y + dy > video_h and dy > 0:
                    dy = video_h - max_y
            ov["points"] = [(p[0] + dx, p[1] + dy) for p in pts]
            if "x1" in base and "x2" in base and "y1" in base and "y2" in base:
                ov["x1"] = base["x1"] + dx
                ov["x2"] = base["x2"] + dx
                ov["y1"] = base["y1"] + dy
                ov["y2"] = base["y2"] + dy
            return True

        if "x1" in base and "x2" in base and "y1" in base and "y2" in base:
            x1, x2 = base["x1"], base["x2"]
            y1, y2 = base["y1"], base["y2"]
            min_x, max_x = min(x1, x2), max(x1, x2)
            min_y, max_y = min(y1, y2), max(y1, y2)
            if video_w is not None and video_h is not None and video_w > 0 and video_h > 0:
                if min_x + dx < 0 and dx < 0:
                    dx = -min_x
                if max_x + dx > video_w and dx > 0:
                    dx = video_w - max_x
                if min_y + dy < 0 and dy < 0:
                    dy = -min_y
                if max_y + dy > video_h and dy > 0:
                    dy = video_h - max_y
            ov["x1"] = base["x1"] + dx
            ov["x2"] = base["x2"] + dx
            ov["y1"] = base["y1"] + dy
            ov["y2"] = base["y2"] + dy
            return True
        return False

    def resize_overlay(self, ov_id, handle, dx, dy, orig_state=None, video_w=None, video_h=None):
        """Resize an overlay via its active corner handle or arrow point."""
        ov = self.get_overlay_by_id(ov_id)
        if not ov:
            return False
        if isinstance(orig_state, (int, float)):
            video_h = video_w
            video_w = orig_state
            orig_state = None
        base = orig_state if isinstance(orig_state, dict) else ov
        ov.pop("_pill_bounds", None)

        dx = float(dx)
        dy = float(dy)
        h_str = str(handle).lower()
        tool = ov.get("tool", "")

        if tool == "arrow":
            if h_str in ("p1", "start", "nw", "sw"):
                ov["x1"] = base.get("x1", 0) + dx
                ov["y1"] = base.get("y1", 0) + dy
                ov["x2"] = base.get("x2", 0)
                ov["y2"] = base.get("y2", 0)
            else:
                ov["x1"] = base.get("x1", 0)
                ov["y1"] = base.get("y1", 0)
                ov["x2"] = base.get("x2", 0) + dx
                ov["y2"] = base.get("y2", 0) + dy
            return True

        if tool == "freehand" and "points" in base and base["points"]:
            pts = base["points"]
            old_min_x = min(p[0] for p in pts)
            old_max_x = max(p[0] for p in pts)
            old_min_y = min(p[1] for p in pts)
            old_max_y = max(p[1] for p in pts)
            old_w = max(4.0, old_max_x - old_min_x)
            old_h = max(4.0, old_max_y - old_min_y)

            new_min_x, new_max_x = old_min_x, old_max_x
            new_min_y, new_max_y = old_min_y, old_max_y

            if "l" in h_str or "w" in h_str:
                new_min_x = min(old_max_x - 4.0, old_min_x + dx)
            if "r" in h_str or "e" in h_str:
                new_max_x = max(old_min_x + 4.0, old_max_x + dx)
            if "t" in h_str or "n" in h_str:
                new_min_y = min(old_max_y - 4.0, old_min_y + dy)
            if "b" in h_str or "s" in h_str:
                new_max_y = max(old_min_y + 4.0, old_max_y + dy)

            new_w = max(4.0, new_max_x - new_min_x)
            new_h = max(4.0, new_max_y - new_min_y)
            sx = new_w / old_w
            sy = new_h / old_h

            ov["points"] = [
                (new_min_x + (p[0] - old_min_x) * sx, new_min_y + (p[1] - old_min_y) * sy)
                for p in pts
            ]
            ov["x1"], ov["y1"] = new_min_x, new_min_y
            ov["x2"], ov["y2"] = new_max_x, new_max_y
            return True

        if "x1" in base and "x2" in base and "y1" in base and "y2" in base:
            x1, y1 = base["x1"], base["y1"]
            x2, y2 = base["x2"], base["y2"]
            min_x, max_x = min(x1, x2), max(x1, x2)
            min_y, max_y = min(y1, y2), max(y1, y2)

            if "l" in h_str or "w" in h_str:
                min_x = min(max_x - 5.0, min_x + dx)
            if "r" in h_str or "e" in h_str:
                max_x = max(min_x + 5.0, max_x + dx)
            if "t" in h_str or "n" in h_str:
                min_y = min(max_y - 5.0, min_y + dy)
            if "b" in h_str or "s" in h_str:
                max_y = max(min_y + 5.0, max_y + dy)

            ov["x1"] = min_x
            ov["y1"] = min_y
            ov["x2"] = max_x
            ov["y2"] = max_y

            if tool == "text":
                new_h = max_y - min_y
                ov["font_size"] = max(10, min(144, int(round(new_h * 0.7))))
            return True

        return False

    def delete_overlay(self, ov_id):
        idx = next((i for i, o in enumerate(self.overlays) if o["id"] == ov_id), None)
        if idx is not None:
            self.overlays.pop(idx)
            return True
        return False

    def get_overlays_at(self, time_sec):
        """Return all overlays active at time_sec."""
        t = float(time_sec)
        return [o for o in self.overlays if (o["start"] - 1e-3) <= t <= (o["end"] + 1e-3)]

    # -------------------------------------------------------------------------
    # AUDIO MUTE RANGES
    # -------------------------------------------------------------------------
    def add_mute_range(self, start=None, end=None):
        s = max(0.0, float(start)) if start is not None else 0.0
        e = min(self.duration, max(s + 0.2, float(end))) if end is not None else min(self.duration, s + 2.0)

        mid = self._next_mute_id
        self._next_mute_id += 1

        item = {
            "id": mid,
            "start": round(s, 3),
            "end": round(e, 3),
        }
        self.mute_ranges.append(item)
        return mid

    def get_mute_range_by_id(self, mute_id):
        for m in self.mute_ranges:
            if m["id"] == mute_id:
                return m
        return None

    def update_mute_range(self, mute_id, start, end, min_dur=0.2):
        item = self.get_mute_range_by_id(mute_id)
        if not item:
            return False
        s = max(0.0, min(self.duration - min_dur, float(start)))
        e = max(s + min_dur, min(self.duration, float(end)))
        item["start"] = round(s, 3)
        item["end"] = round(e, 3)
        return True

    def delete_mute_range(self, mute_id):
        idx = next((i for i, m in enumerate(self.mute_ranges) if m["id"] == mute_id), None)
        if idx is not None:
            self.mute_ranges.pop(idx)
            return True
        return False

    def is_time_muted(self, time_sec):
        t = float(time_sec)
        if any(m["start"] <= t <= m["end"] for m in self.mute_ranges):
            return True
        for aseg in self.audio_segments:
            if not aseg.get("kept", True):
                if aseg["start"] <= t <= aseg["end"]:
                    return True
        return False

    # -------------------------------------------------------------------------
    # EXTERNAL AUDIO CLIPS (MULTI-TRACK & SPLITTABLE)
    # -------------------------------------------------------------------------
    def add_external_audio_clip(
        self,
        path,
        name=None,
        timeline_start=0.0,
        source_start=0.0,
        duration=None,
        volume=1.0,
        replace_original=False,
    ):
        import os
        dur = float(duration) if duration and duration > 0.1 else self.duration
        clip_id = self._next_ext_audio_id
        self._next_ext_audio_id += 1

        clip = {
            "id": clip_id,
            "path": str(path),
            "name": name or os.path.basename(str(path)),
            "timeline_start": max(0.0, float(timeline_start)),
            "source_start": max(0.0, float(source_start)),
            "trim_start": max(0.0, float(source_start)),
            "duration": min(self.duration, float(dur)),
            "volume": max(0.0, min(2.0, float(volume))),
            "replace_original": bool(replace_original),
        }
        self.external_audio_clips.append(clip)
        self.external_audio = clip
        return clip_id

    def get_external_audio_clip_by_id(self, clip_id):
        for c in self.external_audio_clips:
            if c["id"] == clip_id:
                return c
        return None

    def split_external_audio_at(self, clip_id, time_sec, min_seg=0.2):
        """
        Split external audio clip at time_sec (timeline coordinates) into two clips.
        Returns newly created clip_id if successful, None otherwise.
        """
        clip = self.get_external_audio_clip_by_id(clip_id)
        if not clip:
            return None

        t = float(time_sec)
        clip_start = clip["timeline_start"]
        clip_end = clip_start + clip["duration"]

        if (t - clip_start < min_seg) or (clip_end - t < min_seg):
            return None

        first_dur = t - clip_start
        second_dur = clip_end - t
        second_src_start = clip["source_start"] + first_dur

        clip["duration"] = round(first_dur, 3)

        new_id = self._next_ext_audio_id
        self._next_ext_audio_id += 1

        right_clip = {
            "id": new_id,
            "path": clip["path"],
            "name": clip["name"],
            "timeline_start": round(t, 3),
            "source_start": round(second_src_start, 3),
            "trim_start": round(second_src_start, 3),
            "duration": round(second_dur, 3),
            "volume": clip.get("volume", 1.0),
            "replace_original": clip.get("replace_original", False),
        }

        idx = self.external_audio_clips.index(clip)
        self.external_audio_clips.insert(idx + 1, right_clip)
        if self.external_audio_clips:
            self.external_audio = self.external_audio_clips[0]
        return new_id

    def delete_external_audio_clip(self, clip_id):
        idx = next((i for i, c in enumerate(self.external_audio_clips) if c["id"] == clip_id), None)
        if idx is not None:
            self.external_audio_clips.pop(idx)
            self.external_audio = self.external_audio_clips[0] if self.external_audio_clips else None
            return True
        return False

    def move_external_audio_clip(self, clip_id, new_start):
        clip = self.get_external_audio_clip_by_id(clip_id)
        if not clip:
            return False
        s = max(0.0, min(self.duration - 0.2, float(new_start)))
        clip["timeline_start"] = round(s, 3)
        return True

    def resize_external_audio_clip(self, clip_id, new_duration):
        clip = self.get_external_audio_clip_by_id(clip_id)
        if not clip:
            return False
        max_d = max(0.2, self.duration - clip["timeline_start"])
        d = max(0.2, min(max_d, float(new_duration)))
        clip["duration"] = round(d, 3)
        return True

    def set_external_audio(
        self,
        path,
        name=None,
        timeline_start=0.0,
        trim_start=0.0,
        duration=None,
        volume=1.0,
        replace_original=False,
    ):
        self.external_audio_clips.clear()
        cid = self.add_external_audio_clip(
            path,
            name=name,
            timeline_start=timeline_start,
            source_start=trim_start,
            duration=duration,
            volume=volume,
            replace_original=replace_original,
        )
        return self.get_external_audio_clip_by_id(cid)

    def move_external_audio(self, new_start):
        if self.external_audio_clips:
            return self.move_external_audio_clip(self.external_audio_clips[0]["id"], new_start)
        return False

    def resize_external_audio(self, new_duration):
        if self.external_audio_clips:
            return self.resize_external_audio_clip(self.external_audio_clips[0]["id"], new_duration)
        return False

    def clear_external_audio(self):
        self.external_audio = None
        self.external_audio_clips.clear()

    # -------------------------------------------------------------------------
    # UNDO / REDO SERIALIZATION
    # -------------------------------------------------------------------------
    def get_state(self):
        """Serialize state for Undo/Redo."""
        return {
            "duration": self.duration,
            "next_id": self._next_id,
            "next_audio_id": self._next_audio_id,
            "next_overlay_id": self._next_overlay_id,
            "next_mute_id": self._next_mute_id,
            "next_ext_audio_id": self._next_ext_audio_id,
            "segments": copy.deepcopy(self.segments),
            "audio_segments": copy.deepcopy(self.audio_segments),
            "overlays": copy.deepcopy(self.overlays),
            "mute_ranges": copy.deepcopy(self.mute_ranges),
            "external_audio": copy.deepcopy(self.external_audio),
            "external_audio_clips": copy.deepcopy(self.external_audio_clips),
        }

    def restore_state(self, state):
        """Restore state from Undo/Redo snapshot."""
        self.duration = float(state.get("duration", self.duration))
        self._next_id = int(state.get("next_id", len(state.get("segments", [])) + 1))
        self._next_audio_id = int(state.get("next_audio_id", len(state.get("audio_segments", [])) + 1))
        self._next_overlay_id = int(state.get("next_overlay_id", 1))
        self._next_mute_id = int(state.get("next_mute_id", 1))
        self._next_ext_audio_id = int(state.get("next_ext_audio_id", 1))
        self.segments = copy.deepcopy(state.get("segments", []))
        self.audio_segments = copy.deepcopy(state.get("audio_segments", []))
        if not self.audio_segments and self.segments:
            self.audio_segments = [
                {"id": s["id"], "start": s["start"], "end": s["end"], "kept": s.get("kept", True)}
                for s in self.segments
            ]
        self.overlays = copy.deepcopy(state.get("overlays", []))
        self.mute_ranges = copy.deepcopy(state.get("mute_ranges", []))
        self.external_audio = copy.deepcopy(state.get("external_audio", None))
        self.external_audio_clips = copy.deepcopy(state.get("external_audio_clips", []))
        if not self.external_audio_clips and self.external_audio:
            self.external_audio_clips = [copy.deepcopy(self.external_audio)]
