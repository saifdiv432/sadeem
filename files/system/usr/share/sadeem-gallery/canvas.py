#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive GTK4 DrawingArea canvas for Sadeem Gallery:
- Smooth zoom (Ctrl+Scroll / buttons), Fit-to-screen & 100%, drag-to-pan
- Animated GIF / WebP playback
- Interactive Crop overlay with 8 drag handles & aspect ratio lock
- Interactive Cairo Markup drawing (freehand, highlighter, arrow, rect, ellipse, text, blur)
"""

import math
import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk

import editor


class ImageCanvas(Gtk.DrawingArea):
    def __init__(self, on_zoom_changed=None, on_stroke_finished=None, on_text_click=None):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)
        self.set_draw_func(self._on_draw)

        self.on_zoom_changed = on_zoom_changed
        self.on_stroke_finished = on_stroke_finished
        self.on_text_click = on_text_click

        # Display surface & image dimensions
        self.display_surface = None
        self.img_w = 0
        self.img_h = 0

        # Zoom & pan
        self.fit_mode = True
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._last_cursor = (0.0, 0.0)

        # Animation playback
        self.anim_surfaces = []  # [(cairo.ImageSurface, delay_ms)]
        self.anim_idx = 0
        self._anim_timer = None

        # Crop overlay state
        self.crop_active = False
        self.crop_rect = None  # [x, y, w, h] in image pixels
        self.crop_aspect = None  # None (free) or float w/h

        # Markup drawing state
        self.markup_tool = "none"
        self.markup_color = "#7a1c33"
        self.markup_width = 6.0
        self.strokes = []
        self.active_stroke = None

        # Drag state
        self._drag_mode = None  # "pan", "crop_move", "crop_<handle>", "markup"
        self._drag_start_screen = (0.0, 0.0)
        self._drag_start_pan = (0.0, 0.0)
        self._drag_start_crop = None
        self._drag_start_img = (0.0, 0.0)

        self._setup_controllers()

    def _setup_controllers(self):
        # Mouse wheel zoom (supports Ctrl+Scroll and direct scroll)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        # Pointer tracking
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self.add_controller(motion)

        # Drag gesture for pan, crop, and markup
        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        # Click gesture for text placement and double-click zoom toggle
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_click)
        self.add_controller(click)

    # -------------------------------------------------------------------------
    # Public Image / Animation API
    # -------------------------------------------------------------------------
    def stop_animation(self):
        if self._anim_timer is not None:
            try:
                GLib.source_remove(self._anim_timer)
            except Exception:
                pass
            self._anim_timer = None
        self.anim_surfaces = []
        self.anim_idx = 0

    def set_pil_image(self, pil_img, reset_view=False):
        self.stop_animation()
        if pil_img is None:
            self.display_surface = None
            self.img_w = 0
            self.img_h = 0
            self.queue_draw()
            return
        self.display_surface = editor.pil_to_cairo_surface(pil_img)
        self.img_w = pil_img.width
        self.img_h = pil_img.height
        if reset_view:
            self.fit_mode = True
            self.pan_x = 0.0
            self.pan_y = 0.0
        if self.crop_active:
            self._clamp_crop_rect()
        self.queue_draw()
        self._emit_zoom()

    def set_animated_frames(self, frames):
        """Start animated playback from [(PIL.Image, delay_ms), ...]."""
        self.stop_animation()
        if not frames:
            return
        self.anim_surfaces = [(editor.pil_to_cairo_surface(im), delay) for im, delay in frames]
        self.anim_idx = 0
        surf, delay = self.anim_surfaces[0]
        self.display_surface = surf
        self.img_w = surf.get_width()
        self.img_h = surf.get_height()
        self.fit_mode = True
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.queue_draw()
        self._emit_zoom()
        self._schedule_next_frame(delay)

    def _schedule_next_frame(self, delay_ms):
        def _tick():
            self._anim_timer = None
            if not self.anim_surfaces:
                return False
            self.anim_idx = (self.anim_idx + 1) % len(self.anim_surfaces)
            surf, nxt_delay = self.anim_surfaces[self.anim_idx]
            self.display_surface = surf
            self.queue_draw()
            self._schedule_next_frame(nxt_delay)
            return False

        self._anim_timer = GLib.timeout_add(max(25, int(delay_ms)), _tick)

    def set_strokes(self, strokes):
        self.strokes = strokes
        self.queue_draw()

    # -------------------------------------------------------------------------
    # Zoom & View Controls
    # -------------------------------------------------------------------------
    def _compute_fit_scale(self, w, h):
        if self.img_w <= 0 or self.img_h <= 0 or w <= 0 or h <= 0:
            return 1.0
        pad = 24.0
        avail_w = max(32.0, w - pad * 2)
        avail_h = max(32.0, h - pad * 2)
        return min(avail_w / self.img_w, avail_h / self.img_h)

    def _get_effective_scale(self, w=None, h=None):
        if w is None:
            w = max(1, self.get_width())
        if h is None:
            h = max(1, self.get_height())
        if self.fit_mode:
            return self._compute_fit_scale(w, h)
        return self.zoom

    def _get_image_rect(self, w=None, h=None):
        if w is None:
            w = max(1, self.get_width())
        if h is None:
            h = max(1, self.get_height())
        scale = self._get_effective_scale(w, h)
        dw = self.img_w * scale
        dh = self.img_h * scale
        ox = (w - dw) / 2.0 + (0.0 if self.fit_mode else self.pan_x)
        oy = (h - dh) / 2.0 + (0.0 if self.fit_mode else self.pan_y)
        return ox, oy, dw, dh, scale

    def screen_to_image(self, sx, sy):
        ox, oy, _dw, _dh, scale = self._get_image_rect()
        if scale <= 0:
            return 0.0, 0.0
        return (sx - ox) / scale, (sy - oy) / scale

    def image_to_screen(self, ix, iy):
        ox, oy, _dw, _dh, scale = self._get_image_rect()
        return ox + ix * scale, oy + iy * scale

    def _emit_zoom(self):
        if self.on_zoom_changed and self.img_w > 0:
            pct = int(round(self._get_effective_scale() * 100))
            self.on_zoom_changed(pct)

    def zoom_fit(self):
        self.fit_mode = True
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.queue_draw()
        self._emit_zoom()

    def zoom_100(self):
        self.fit_mode = False
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.queue_draw()
        self._emit_zoom()

    def zoom_by(self, factor, anchor=None):
        if self.img_w <= 0:
            return
        w = max(1, self.get_width())
        h = max(1, self.get_height())
        old_scale = self._get_effective_scale(w, h)
        new_scale = max(0.1, min(8.0, old_scale * factor))

        if anchor is None:
            ax, ay = w / 2.0, h / 2.0
        else:
            ax, ay = anchor

        ox, oy, _dw, _dh, _s = self._get_image_rect(w, h)
        ix = (ax - ox) / max(old_scale, 1e-6)
        iy = (ay - oy) / max(old_scale, 1e-6)

        self.fit_mode = False
        self.zoom = new_scale
        new_dw = self.img_w * new_scale
        new_dh = self.img_h * new_scale
        new_ox = ax - ix * new_scale
        new_oy = ay - iy * new_scale
        self.pan_x = new_ox - (w - new_dw) / 2.0
        self.pan_y = new_oy - (h - new_dh) / 2.0

        self.queue_draw()
        self._emit_zoom()

    # -------------------------------------------------------------------------
    # Crop Overlay Controls
    # -------------------------------------------------------------------------
    def set_crop_active(self, active):
        self.crop_active = bool(active)
        if self.crop_active and self.img_w > 0 and self.img_h > 0:
            self.reset_crop_rect()
        else:
            self.crop_rect = None
        self.queue_draw()

    def set_crop_aspect(self, aspect):
        self.crop_aspect = aspect
        if self.crop_active and self.img_w > 0 and self.img_h > 0:
            self.reset_crop_rect()
        self.queue_draw()

    def reset_crop_rect(self):
        if self.img_w <= 0 or self.img_h <= 0:
            self.crop_rect = None
            return
        margin_x = self.img_w * 0.08
        margin_y = self.img_h * 0.08
        rw = self.img_w - 2 * margin_x
        rh = self.img_h - 2 * margin_y
        if self.crop_aspect:
            if rw / max(rh, 1.0) > self.crop_aspect:
                rw = rh * self.crop_aspect
            else:
                rh = rw / self.crop_aspect
        rx = (self.img_w - rw) / 2.0
        ry = (self.img_h - rh) / 2.0
        self.crop_rect = [rx, ry, rw, rh]

    def _clamp_crop_rect(self):
        if not self.crop_rect or self.img_w <= 0 or self.img_h <= 0:
            return
        x, y, w, h = self.crop_rect
        w = max(20.0, min(self.img_w, w))
        h = max(20.0, min(self.img_h, h))
        x = max(0.0, min(self.img_w - w, x))
        y = max(0.0, min(self.img_h - h, y))
        self.crop_rect = [x, y, w, h]

    def _hit_test_crop(self, sx, sy):
        if not self.crop_active or not self.crop_rect:
            return None
        x, y, w, h = self.crop_rect
        x0, y0 = self.image_to_screen(x, y)
        x1, y1 = self.image_to_screen(x + w, y + h)
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        r = 14.0
        handles = [
            ("nw", x0, y0), ("ne", x1, y0), ("sw", x0, y1), ("se", x1, y1),
            ("n", mx, y0), ("s", mx, y1), ("w", x0, my), ("e", x1, my),
        ]
        for name, hx, hy in handles:
            if math.hypot(sx - hx, sy - hy) <= r:
                return f"crop_{name}"
        if x0 <= sx <= x1 and y0 <= sy <= y1:
            return "crop_move"
        return None

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------
    def _on_scroll(self, _ctrl, _dx, dy):
        if dy < 0:
            self.zoom_by(1.14, anchor=self._last_cursor)
        elif dy > 0:
            self.zoom_by(1.0 / 1.14, anchor=self._last_cursor)
        return True

    def _on_motion(self, _ctrl, x, y):
        self._last_cursor = (x, y)
        if self.crop_active and self.crop_rect:
            hit = self._hit_test_crop(x, y)
            cursor_map = {
                "crop_nw": "nwse-resize", "crop_se": "nwse-resize",
                "crop_ne": "nesw-resize", "crop_sw": "nesw-resize",
                "crop_n": "ns-resize", "crop_s": "ns-resize",
                "crop_e": "ew-resize", "crop_w": "ew-resize",
                "crop_move": "grab",
            }
            self.set_cursor_from_name(cursor_map.get(hit, "default"))
        elif self.markup_tool != "none":
            self.set_cursor_from_name("crosshair")
        elif not self.fit_mode:
            self.set_cursor_from_name("grab")
        else:
            self.set_cursor_from_name("default")

    def _on_click(self, _gesture, n_press, x, y):
        if self.img_w <= 0:
            return
        if self.markup_tool == "text" and n_press == 1 and not self.crop_active:
            ix, iy = self.screen_to_image(x, y)
            if 0 <= ix <= self.img_w and 0 <= iy <= self.img_h:
                if self.on_text_click:
                    self.on_text_click(ix, iy)
            return

        if n_press == 2 and not self.crop_active and self.markup_tool == "none":
            if self.fit_mode:
                self.zoom_100()
            else:
                self.zoom_fit()

    def _on_drag_begin(self, _gesture, start_x, start_y):
        if self.img_w <= 0:
            self._drag_mode = None
            return
        self._drag_start_screen = (start_x, start_y)

        if self.crop_active and self.crop_rect:
            hit = self._hit_test_crop(start_x, start_y)
            if hit:
                self._drag_mode = hit
                self._drag_start_crop = list(self.crop_rect)
                self._drag_start_img = self.screen_to_image(start_x, start_y)
                return

        if self.markup_tool not in ("none", "text") and not self.crop_active:
            ix, iy = self.screen_to_image(start_x, start_y)
            ix = max(0.0, min(self.img_w, ix))
            iy = max(0.0, min(self.img_h, iy))
            self._drag_mode = "markup"
            self._drag_start_img = (ix, iy)
            if self.markup_tool in ("freehand", "highlighter"):
                self.active_stroke = {
                    "tool": self.markup_tool,
                    "color": self.markup_color,
                    "width": self.markup_width,
                    "points": [(ix, iy)],
                }
            else:
                self.active_stroke = {
                    "tool": "blur_preview" if self.markup_tool == "blur" else self.markup_tool,
                    "final_tool": self.markup_tool,
                    "color": self.markup_color,
                    "width": self.markup_width,
                    "x1": ix, "y1": iy, "x2": ix, "y2": iy,
                }
            self.queue_draw()
            return

        # Default: drag-to-pan when zoomed in
        if not self.fit_mode:
            self._drag_mode = "pan"
            self._drag_start_pan = (self.pan_x, self.pan_y)
        else:
            self._drag_mode = None

    def _on_drag_update(self, _gesture, offset_x, offset_y):
        if not self._drag_mode:
            return
        sx = self._drag_start_screen[0] + offset_x
        sy = self._drag_start_screen[1] + offset_y

        if self._drag_mode == "pan":
            self.pan_x = self._drag_start_pan[0] + offset_x
            self.pan_y = self._drag_start_pan[1] + offset_y
            self.queue_draw()

        elif self._drag_mode.startswith("crop_") and self._drag_start_crop:
            ix, iy = self.screen_to_image(sx, sy)
            dx = ix - self._drag_start_img[0]
            dy = iy - self._drag_start_img[1]
            ox, oy, ow, oh = self._drag_start_crop
            min_sz = 24.0
            mode = self._drag_mode

            if mode == "crop_move":
                nx = max(0.0, min(self.img_w - ow, ox + dx))
                ny = max(0.0, min(self.img_h - oh, oy + dy))
                self.crop_rect = [nx, ny, ow, oh]
            else:
                x0, y0, x1, y1 = ox, oy, ox + ow, oy + oh
                if "w" in mode[5:]:
                    x0 = max(0.0, min(x1 - min_sz, ox + dx))
                if "e" in mode[5:]:
                    x1 = min(float(self.img_w), max(x0 + min_sz, ox + ow + dx))
                if "n" in mode[5:]:
                    y0 = max(0.0, min(y1 - min_sz, oy + dy))
                if "s" in mode[5:]:
                    y1 = min(float(self.img_h), max(y0 + min_sz, oy + oh + dy))

                nw, nh = x1 - x0, y1 - y0
                if self.crop_aspect:
                    aspect = self.crop_aspect
                    if mode in ("crop_n", "crop_s"):
                        nw = nh * aspect
                    elif mode in ("crop_e", "crop_w"):
                        nh = nw / aspect
                    else:
                        if nw / max(nh, 1.0) > aspect:
                            nw = nh * aspect
                        else:
                            nh = nw / aspect
                    if "w" in mode[5:]:
                        x0 = x1 - nw
                    if "n" in mode[5:]:
                        y0 = y1 - nh
                    # Keep within image bounds
                    if x0 < 0:
                        x0 = 0.0
                        nw = min(nw, self.img_w)
                        nh = nw / aspect
                    if y0 < 0:
                        y0 = 0.0
                        nh = min(nh, self.img_h)
                        nw = nh * aspect
                    if x0 + nw > self.img_w:
                        nw = self.img_w - x0
                        nh = nw / aspect
                    if y0 + nh > self.img_h:
                        nh = self.img_h - y0
                        nw = nh * aspect
                self.crop_rect = [x0, y0, max(min_sz, nw), max(min_sz, nh)]
            self.queue_draw()

        elif self._drag_mode == "markup" and self.active_stroke:
            ix, iy = self.screen_to_image(sx, sy)
            ix = max(0.0, min(self.img_w, ix))
            iy = max(0.0, min(self.img_h, iy))
            if self.active_stroke["tool"] in ("freehand", "highlighter"):
                pts = self.active_stroke["points"]
                if not pts or math.hypot(ix - pts[-1][0], iy - pts[-1][1]) >= 1.5:
                    pts.append((ix, iy))
            else:
                self.active_stroke["x2"] = ix
                self.active_stroke["y2"] = iy
            self.queue_draw()

    def _on_drag_end(self, _gesture, _offset_x, _offset_y):
        if self._drag_mode == "markup" and self.active_stroke:
            finished = self.active_stroke
            self.active_stroke = None
            if finished.get("final_tool") == "blur":
                finished["tool"] = "blur"
                finished.pop("final_tool", None)
            else:
                finished.pop("final_tool", None)

            valid = True
            if finished["tool"] in ("arrow", "rect", "ellipse", "blur"):
                if math.hypot(finished["x2"] - finished["x1"], finished["y2"] - finished["y1"]) < 3.0:
                    valid = False
            if valid and self.on_stroke_finished:
                self.on_stroke_finished(finished)
            self.queue_draw()
        self._drag_mode = None

    # -------------------------------------------------------------------------
    # Cairo Drawing
    # -------------------------------------------------------------------------
    def _on_draw(self, _area, ctx, width, height):
        # Neutral deep slate canvas backdrop for accurate color inspection
        ctx.set_source_rgb(0.09, 0.10, 0.12)
        ctx.rectangle(0, 0, width, height)
        ctx.fill()

        if self.display_surface is None or self.img_w <= 0 or self.img_h <= 0:
            return

        ox, oy, dw, dh, scale = self._get_image_rect(width, height)

        # Subtle checkerboard behind transparent PNGs
        ctx.save()
        ctx.rectangle(ox, oy, dw, dh)
        ctx.clip()
        ctx.set_source_rgb(0.16, 0.17, 0.20)
        ctx.rectangle(ox, oy, dw, dh)
        ctx.fill()

        # Render image surface
        ctx.translate(ox, oy)
        ctx.scale(scale, scale)
        ctx.set_source_surface(self.display_surface, 0, 0)
        pat = ctx.get_source()
        pat.set_filter(cairo.FILTER_BILINEAR if scale < 1.5 else cairo.FILTER_NEAREST)
        ctx.paint()

        # Render committed vector strokes + live active stroke
        for st in self.strokes:
            if st.get("tool") != "blur":
                editor.draw_stroke_on_cairo(ctx, st, scale_factor=scale)
        if self.active_stroke:
            editor.draw_stroke_on_cairo(ctx, self.active_stroke, scale_factor=scale)
        ctx.restore()

        # Crisp 1px silver frame around image
        ctx.set_source_rgba(0.89, 0.91, 0.94, 0.20)
        ctx.set_line_width(1.0)
        ctx.rectangle(ox + 0.5, oy + 0.5, dw - 1.0, dh - 1.0)
        ctx.stroke()

        # Interactive Crop Overlay
        if self.crop_active and self.crop_rect:
            self._draw_crop_overlay(ctx, ox, oy, dw, dh, scale)

    def _draw_crop_overlay(self, ctx, ox, oy, dw, dh, scale):
        cx, cy, cw, ch = self.crop_rect
        x0 = ox + cx * scale
        y0 = oy + cy * scale
        w_px = cw * scale
        h_px = ch * scale
        x1 = x0 + w_px
        y1 = y0 + h_px

        # Dark scrim outside crop box (within image bounds)
        ctx.save()
        ctx.set_source_rgba(0.0, 0.0, 0.0, 0.58)
        ctx.rectangle(ox, oy, dw, max(0.0, y0 - oy))
        ctx.rectangle(ox, y1, dw, max(0.0, (oy + dh) - y1))
        ctx.rectangle(ox, y0, max(0.0, x0 - ox), h_px)
        ctx.rectangle(x1, y0, max(0.0, (ox + dw) - x1), h_px)
        ctx.fill()

        # Rule-of-thirds interior grid lines
        ctx.set_source_rgba(0.89, 0.91, 0.94, 0.45)
        ctx.set_line_width(1.0)
        for frac in (1.0 / 3.0, 2.0 / 3.0):
            gx = x0 + w_px * frac
            gy = y0 + h_px * frac
            ctx.move_to(gx, y0)
            ctx.line_to(gx, y1)
            ctx.move_to(x0, gy)
            ctx.line_to(x1, gy)
        ctx.stroke()

        # Outer crop border in crisp silver/white
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        ctx.set_line_width(2.0)
        ctx.rectangle(x0, y0, w_px, h_px)
        ctx.stroke()

        # 8 drag handles in Sadeem Burgundy with silver border
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        for hx, hy in (
            (x0, y0), (x1, y0), (x0, y1), (x1, y1),
            (mx, y0), (mx, y1), (x0, my), (x1, my),
        ):
            ctx.arc(hx, hy, 6.5, 0.0, math.tau)
            ctx.set_source_rgb(0.48, 0.11, 0.20)  # #7a1c33
            ctx.fill_preserve()
            ctx.set_source_rgb(0.89, 0.91, 0.94)  # #e2e8f0
            ctx.set_line_width(2.0)
            ctx.stroke()
        ctx.restore()
