#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Cairo Vector Markup Renderer for Sadeem Video Editor.
Renders annotations (freehand, arrow, rect, ellipse, text, blur) directly onto Cairo
surfaces for live preview and video export overlay generation.
Safely manages Cairo buffer memory references to prevent garbage collection crashes.
"""

import math
import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo
from PIL import Image


def hex_to_rgba(hex_color, alpha=1.0):
    """Convert hex color (#RRGGBB or #RGB) to normalized RGBA tuple (0.0..1.0)."""
    s = str(hex_color).lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) >= 6:
        try:
            r = int(s[0:2], 16) / 255.0
            g = int(s[2:4], 16) / 255.0
            b = int(s[4:6], 16) / 255.0
            return r, g, b, float(alpha)
        except ValueError:
            pass
    return 0.48, 0.11, 0.20, float(alpha)


_SURFACE_BUFFERS = {}


def pil_to_cairo_surface(pil_img):
    """
    Convert PIL RGBA image to a Cairo ImageSurface.
    Safely stores bytearray in module-level dictionary to prevent garbage collection
    and native heap memory corruption.
    """
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    w, h = pil_img.size
    # ARGB32 in Cairo on little-endian is BGRA in byte order
    r, g, b, a = pil_img.split()
    bgra = Image.merge("RGBA", (b, g, r, a))
    data = bytearray(bgra.tobytes())
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, w)
    surf = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, w, h, stride)
    _SURFACE_BUFFERS[id(surf)] = data
    return surf


def cairo_surface_to_pil(surface):
    """Convert Cairo ARGB32 ImageSurface to PIL RGBA image."""
    surface.flush()
    w = surface.get_width()
    h = surface.get_height()
    data = bytes(surface.get_data())
    bgra = Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", 0, 1)
    b, g, r, a = bgra.split()
    return Image.merge("RGBA", (r, g, b, a))


def draw_stroke_on_cairo(ctx, stroke, scale_factor=1.0, selected=False, live_blur_handled=False):
    """
    Draw a single vector markup stroke in image-coordinate space onto a Cairo context.
    Handles freehand, arrow, rect, ellipse, text, and blur.
    When live_blur_handled=True, blur layers are assumed rendered by live GPU shaders,
    so only pixelation grids or selection dashes are rendered in Cairo.
    """
    tool = stroke.get("tool")
    color_hex = stroke.get("color", "#7a1c33")
    width = max(1.0, float(stroke.get("width", 6.0)))

    ctx.save()
    r, g, b, a = hex_to_rgba(color_hex, 1.0)
    ctx.set_source_rgba(r, g, b, a)
    ctx.set_line_width(width)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)

    if tool in ("pen", "freehand"):
        pts = stroke.get("points", [])
        if len(pts) >= 2:
            ctx.move_to(pts[0][0], pts[0][1])
            for pt in pts[1:]:
                ctx.line_to(pt[0], pt[1])
            ctx.stroke()
        elif len(pts) == 1:
            ctx.arc(pts[0][0], pts[0][1], width / 2.0, 0, math.tau)
            ctx.fill()

    elif tool == "arrow":
        x1, y1 = float(stroke.get("x1", 0.0)), float(stroke.get("y1", 0.0))
        x2, y2 = float(stroke.get("x2", 0.0)), float(stroke.get("y2", 0.0))
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length > 2.0:
            angle = math.atan2(dy, dx)
            head_len = min(length * 0.45, max(16.0, width * 3.2))
            head_angle = 0.42  # ~24 degrees

            # Draw shaft
            ctx.move_to(x1, y1)
            ctx.line_to(x2, y2)
            ctx.stroke()

            # Draw arrowhead
            p1_x = x2 - head_len * math.cos(angle - head_angle)
            p1_y = y2 - head_len * math.sin(angle - head_angle)
            p2_x = x2 - head_len * math.cos(angle + head_angle)
            p2_y = y2 - head_len * math.sin(angle + head_angle)

            ctx.move_to(x2, y2)
            ctx.line_to(p1_x, p1_y)
            ctx.line_to(p2_x, p2_y)
            ctx.close_path()
            ctx.fill()

    elif tool == "rect":
        x1, y1 = float(stroke.get("x1", 0.0)), float(stroke.get("y1", 0.0))
        x2, y2 = float(stroke.get("x2", 0.0)), float(stroke.get("y2", 0.0))
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        if rw > 1.0 and rh > 1.0:
            ctx.rectangle(rx, ry, rw, rh)
            ctx.stroke()

    elif tool == "ellipse":
        x1, y1 = float(stroke.get("x1", 0.0)), float(stroke.get("y1", 0.0))
        x2, y2 = float(stroke.get("x2", 0.0)), float(stroke.get("y2", 0.0))
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        rx = abs(x2 - x1) / 2.0
        ry = abs(y2 - y1) / 2.0
        if rx > 1.0 and ry > 1.0:
            ctx.save()
            ctx.translate(cx, cy)
            ctx.scale(rx, ry)
            ctx.arc(0.0, 0.0, 1.0, 0.0, math.tau)
            ctx.restore()
            ctx.stroke()

    elif tool == "text":
        txt = stroke.get("text", "")
        if txt:
            x, y = float(stroke.get("x1", 0.0)), float(stroke.get("y1", 0.0))
            font_px = int(stroke.get("font_size") or max(18, int(round(width * 3.8))))
            layout = PangoCairo.create_layout(ctx)
            desc = Pango.FontDescription.from_string(f"Sans Bold {font_px}px")
            layout.set_font_description(desc)
            layout.set_text(txt, -1)
            ink, logical = layout.get_pixel_extents()
            tw = max(1, logical.width)
            th = max(1, logical.height)
            pad = max(6, int(font_px * 0.22))

            # Store computed text bounds on stroke for hit testing and handles
            stroke["_pill_bounds"] = (x - pad, y - pad, x + tw + pad, y + th + pad)
            stroke["x2"] = x + tw + pad
            stroke["y2"] = y + th + pad

            # Subtle dark pill backdrop for crisp legibility
            ctx.set_source_rgba(0.06, 0.08, 0.12, 0.62)
            ctx.rectangle(x - pad, y - pad, tw + pad * 2, th + pad * 2)
            ctx.fill()

            ctx.move_to(x, y)
            ctx.set_source_rgba(r, g, b, 1.0)
            PangoCairo.show_layout(ctx, layout)

    elif tool == "blur":
        x1, y1 = float(stroke.get("x1", 0.0)), float(stroke.get("y1", 0.0))
        x2, y2 = float(stroke.get("x2", 0.0)), float(stroke.get("y2", 0.0))
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        if rw > 2.0 and rh > 2.0:
            b_style = str(stroke.get("blur_style", "pixelate")).lower()
            strength = max(1, min(100, int(stroke.get("blur_strength", 50))))

            ctx.save()
            if not live_blur_handled:
                if b_style == "solid":
                    ctx.set_source_rgba(0.06, 0.07, 0.09, 0.98)
                    ctx.rectangle(rx, ry, rw, rh)
                    ctx.fill()
                elif b_style == "frosted":
                    # Soft frosted glass with translucent blue-grey tint and soft sheen
                    ctx.set_source_rgba(0.25, 0.35, 0.50, 0.70)
                    ctx.rectangle(rx, ry, rw, rh)
                    ctx.fill()
                    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.12)
                    ctx.rectangle(rx, ry, rw, rh)
                    ctx.fill()
                else:  # pixelate (default)
                    ctx.rectangle(rx, ry, rw, rh)
                    ctx.clip()
                    tile_sz = max(6.0, round(6.0 + (strength / 100.0) * 26.0))
                    ty = ry
                    row = 0
                    while ty < ry + rh:
                        tx = rx
                        col = 0
                        while tx < rx + rw:
                            val = 0.22 + (((row * 7 + col * 13) % 9) - 4) * 0.015
                            ctx.set_source_rgba(val, val + 0.03, val + 0.06, 0.85)
                            ctx.rectangle(tx, ty, tile_sz, tile_sz)
                            ctx.fill()
                            tx += tile_sz
                            col += 1
                        ty += tile_sz
                        row += 1
            else:
                if b_style == "pixelate":
                    ctx.rectangle(rx, ry, rw, rh)
                    ctx.clip()
                    tile_sz = max(6.0, round(6.0 + (strength / 100.0) * 26.0))
                    ctx.set_source_rgba(0.0, 0.0, 0.0, 0.15)
                    ctx.set_line_width(1.0)
                    tx = rx
                    while tx < rx + rw:
                        ctx.move_to(tx, ry)
                        ctx.line_to(tx, ry + rh)
                        tx += tile_sz
                    ty = ry
                    while ty < ry + rh:
                        ctx.move_to(rx, ty)
                        ctx.line_to(rx + rw, ty)
                        ty += tile_sz
                    ctx.stroke()

            is_item_selected = selected or stroke.get("_selected", False)
            if is_item_selected:
                # Cyan dashed boundary ONLY when selected
                ctx.set_source_rgba(0.13, 0.83, 0.93, 0.9)
                ctx.set_line_width(max(1.5, width * 0.5))
                ctx.set_dash([6.0, 4.0])
                ctx.rectangle(rx, ry, rw, rh)
                ctx.stroke()
            ctx.restore()

    ctx.restore()


def render_markup_to_pil(strokes, width, height, skip_blur=False):
    """
    Render a list of markup strokes onto a transparent PIL RGBA image of size (width, height).
    If skip_blur is True, blur regions are omitted (for FFmpeg native boxblur filter export).
    """
    w = max(1, int(width))
    h = max(1, int(height))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    for s in strokes:
        if skip_blur and s.get("tool") == "blur":
            continue
        draw_stroke_on_cairo(ctx, s, scale_factor=1.0)
    return cairo_surface_to_pil(surface)
