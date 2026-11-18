#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image processing, adjustments, filters, transforms, Cairo vector markup
(with PangoCairo Arabic/English text), blur/pixelation, undo/redo history,
and save/clipboard utilities for Sadeem Gallery.
"""

import copy
import io
import math
import os

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Pango, PangoCairo
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def default_adjustments():
    return {
        "brightness": 1.0,
        "contrast": 1.0,
        "saturation": 1.0,
        "sharpness": 1.0,
        "warmth": 0.0,
        "filter": "original",
    }


def pil_to_gdk_texture(img):
    """Convert PIL Image to GTK4 Gdk.MemoryTexture directly in memory."""
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    data = GLib.Bytes.new(rgba.tobytes())
    return Gdk.MemoryTexture.new(
        rgba.width, rgba.height, Gdk.MemoryFormat.R8G8B8A8, data, rgba.width * 4
    )


def pil_to_cairo_surface(img):
    """Convert PIL Image to a Cairo ARGB32 ImageSurface (premultiplied BGRA on LE)."""
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    pre = rgba.convert("RGBa")
    r, g, b, a = pre.split()
    bgra = bytearray(Image.merge("RGBA", (b, g, r, a)).tobytes())
    surf = cairo.ImageSurface.create_for_data(
        bgra, cairo.FORMAT_ARGB32, rgba.width, rgba.height, rgba.width * 4
    )
    return surf


def cairo_surface_to_pil(surf):
    """Convert a Cairo ARGB32 ImageSurface back to a PIL RGBA Image."""
    surf.flush()
    w = surf.get_width()
    h = surf.get_height()
    raw = bytes(surf.get_data())
    return Image.frombuffer("RGBA", (w, h), raw, "raw", "BGRa", 0, 1).convert("RGBA")


def _apply_warmth(rgb_img, warmth):
    """Shift red/blue channel LUT smoothly based on warmth (-50 .. +50)."""
    if abs(warmth) < 0.5:
        return rgb_img
    shift = warmth * 0.9
    r_lut = [max(0, min(255, int(i + shift))) for i in range(256)]
    g_lut = [max(0, min(255, int(i + shift * 0.15))) for i in range(256)]
    b_lut = [max(0, min(255, int(i - shift))) for i in range(256)]
    r, g, b = rgb_img.split()
    return Image.merge("RGB", (r.point(r_lut), g.point(g_lut), b.point(b_lut)))


def apply_adjustments_and_filter(pil_img, adj):
    """Apply preset filter + brightness/contrast/saturation/sharpness/warmth to a PIL RGBA image."""
    if pil_img is None:
        return None
    if not adj:
        return pil_img.copy()

    flt = adj.get("filter", "original")
    brightness = float(adj.get("brightness", 1.0))
    contrast = float(adj.get("contrast", 1.0))
    saturation = float(adj.get("saturation", 1.0))
    sharpness = float(adj.get("sharpness", 1.0))
    warmth = float(adj.get("warmth", 0.0))

    if (
        flt == "original"
        and abs(brightness - 1.0) < 0.01
        and abs(contrast - 1.0) < 0.01
        and abs(saturation - 1.0) < 0.01
        and abs(sharpness - 1.0) < 0.01
        and abs(warmth) < 0.5
    ):
        return pil_img.copy()

    rgba = pil_img if pil_img.mode == "RGBA" else pil_img.convert("RGBA")
    alpha = rgba.split()[3]
    rgb = rgba.convert("RGB")

    # 1. Preset Filter
    if flt == "auto":
        rgb = ImageOps.autocontrast(rgb, cutoff=1)
        rgb = ImageEnhance.Color(rgb).enhance(1.12)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.10)
    elif flt == "vivid":
        rgb = ImageEnhance.Contrast(rgb).enhance(1.16)
        rgb = ImageEnhance.Color(rgb).enhance(1.38)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.15)
    elif flt == "bw":
        rgb = ImageOps.grayscale(rgb).convert("RGB")
        rgb = ImageEnhance.Contrast(rgb).enhance(1.12)
    elif flt == "warm":
        rgb = _apply_warmth(rgb, 24.0)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
        rgb = ImageEnhance.Color(rgb).enhance(1.08)
    elif flt == "cool":
        rgb = _apply_warmth(rgb, -24.0)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
        rgb = ImageEnhance.Color(rgb).enhance(1.05)

    # 2. Live Manual Sliders
    if abs(brightness - 1.0) >= 0.01:
        rgb = ImageEnhance.Brightness(rgb).enhance(brightness)
    if abs(contrast - 1.0) >= 0.01:
        rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    if abs(saturation - 1.0) >= 0.01:
        rgb = ImageEnhance.Color(rgb).enhance(saturation)
    if abs(sharpness - 1.0) >= 0.01:
        rgb = ImageEnhance.Sharpness(rgb).enhance(sharpness)
    if abs(warmth) >= 0.5:
        rgb = _apply_warmth(rgb, warmth)

    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def rotate_90(pil_img, clockwise=True):
    if clockwise:
        return pil_img.transpose(Image.Transpose.ROTATE_270)
    return pil_img.transpose(Image.Transpose.ROTATE_90)


def flip_image(pil_img, horizontal=True):
    if horizontal:
        return pil_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return pil_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def straighten_image(pil_img, angle_deg):
    """Rotate by fine angle (-45..+45 deg) with bicubic interpolation and clean inner crop."""
    if abs(angle_deg) < 0.05:
        return pil_img.copy()
    w, h = pil_img.size
    rotated = pil_img.rotate(-angle_deg, resample=Image.Resampling.BICUBIC, expand=True)
    # Compute largest axis-aligned rectangle inside rotated image so there are no black corners
    rad = math.radians(abs(angle_deg))
    sin_a = abs(math.sin(rad))
    cos_a = abs(math.cos(rad))
    w_long, h_short = (w, h) if w >= h else (h, w)
    if h_short <= 2.0 * sin_a * cos_a * w_long or abs(cos_a - sin_a) < 1e-6:
        x = 0.5 * h_short
        wr, hr = (x / sin_a, x / cos_a) if w >= h else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr = (w * cos_a - h * sin_a) / cos_2a
        hr = (h * cos_a - w * sin_a) / cos_2a
    wr = max(16, min(int(round(wr)), rotated.width))
    hr = max(16, min(int(round(hr)), rotated.height))
    cx, cy = rotated.width / 2.0, rotated.height / 2.0
    left = max(0, int(round(cx - wr / 2.0)))
    top = max(0, int(round(cy - hr / 2.0)))
    return rotated.crop((left, top, min(rotated.width, left + wr), min(rotated.height, top + hr)))


def crop_image(pil_img, rect):
    """Crop PIL image using (x, y, w, h) in image pixel coordinates."""
    x, y, w, h = rect
    x0 = max(0, min(pil_img.width - 1, int(round(x))))
    y0 = max(0, min(pil_img.height - 1, int(round(y))))
    x1 = max(x0 + 1, min(pil_img.width, int(round(x + w))))
    y1 = max(y0 + 1, min(pil_img.height, int(round(y + h))))
    return pil_img.crop((x0, y0, x1, y1))


def resize_image(pil_img, new_w, new_h):
    nw = max(1, min(16384, int(new_w)))
    nh = max(1, min(16384, int(new_h)))
    return pil_img.resize((nw, nh), Image.Resampling.LANCZOS)


def hex_to_rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return (r, g, b, alpha)
    return (0.48, 0.11, 0.20, alpha)


def apply_blur_stroke_to_pil(pil_img, stroke):
    """Pixelate + softly blur a rectangular region on PIL image to obscure sensitive content."""
    x0 = int(round(min(stroke["x1"], stroke["x2"])))
    y0 = int(round(min(stroke["y1"], stroke["y2"])))
    x1 = int(round(max(stroke["x1"], stroke["x2"])))
    y1 = int(round(max(stroke["y1"], stroke["y2"])))

    x0 = max(0, min(pil_img.width - 1, x0))
    y0 = max(0, min(pil_img.height - 1, y0))
    x1 = max(x0 + 1, min(pil_img.width, x1))
    y1 = max(y0 + 1, min(pil_img.height, y1))
    rw = x1 - x0
    rh = y1 - y0
    if rw < 2 or rh < 2:
        return pil_img

    block = max(8, int(stroke.get("width", 14) * 1.4))
    region = pil_img.crop((x0, y0, x1, y1))
    small_w = max(1, rw // block)
    small_h = max(1, rh // block)
    pixelated = region.resize((small_w, small_h), Image.Resampling.BILINEAR).resize(
        (rw, rh), Image.Resampling.NEAREST
    )
    pixelated = pixelated.filter(ImageFilter.GaussianBlur(radius=1.2))
    out = pil_img.copy()
    out.paste(pixelated, (x0, y0))
    return out


def draw_stroke_on_cairo(ctx, stroke, scale_factor=1.0):
    """
    Draw a single vector markup stroke in image-coordinate space onto a Cairo context.
    Handles freehand, highlighter, arrow, rect, ellipse, text (PangoCairo Arabic+English),
    and blur preview frame.
    """
    tool = stroke.get("tool")
    color_hex = stroke.get("color", "#7a1c33")
    width = max(1.0, float(stroke.get("width", 6.0)))

    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)

    if tool == "freehand":
        pts = stroke.get("points", [])
        if len(pts) >= 2:
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 1.0))
            ctx.set_line_width(width)
            ctx.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                ctx.line_to(x, y)
            ctx.stroke()
        elif len(pts) == 1:
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 1.0))
            ctx.arc(pts[0][0], pts[0][1], width / 2.0, 0, math.tau)
            ctx.fill()

    elif tool == "highlighter":
        pts = stroke.get("points", [])
        if len(pts) >= 2:
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 0.38))
            ctx.set_line_width(max(12.0, width * 2.8))
            ctx.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                ctx.line_to(x, y)
            ctx.stroke()

    elif tool == "arrow":
        x1, y1 = stroke.get("x1", 0.0), stroke.get("y1", 0.0)
        x2, y2 = stroke.get("x2", 0.0), stroke.get("y2", 0.0)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length >= 2.0:
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 1.0))
            ctx.set_line_width(width)
            angle = math.atan2(dy, dx)
            head_len = max(16.0, width * 3.4)
            head_ang = math.radians(28)
            # Shorten shaft slightly so it meets arrowhead base cleanly
            shaft_x2 = x2 - math.cos(angle) * (head_len * 0.65)
            shaft_y2 = y2 - math.sin(angle) * (head_len * 0.65)
            ctx.move_to(x1, y1)
            ctx.line_to(shaft_x2, shaft_y2)
            ctx.stroke()

            p1x = x2 - head_len * math.cos(angle - head_ang)
            p1y = y2 - head_len * math.sin(angle - head_ang)
            p2x = x2 - head_len * math.cos(angle + head_ang)
            p2y = y2 - head_len * math.sin(angle + head_ang)
            ctx.move_to(x2, y2)
            ctx.line_to(p1x, p1y)
            ctx.line_to(p2x, p2y)
            ctx.close_path()
            ctx.fill()

    elif tool == "rect":
        x1, y1 = stroke.get("x1", 0.0), stroke.get("y1", 0.0)
        x2, y2 = stroke.get("x2", 0.0), stroke.get("y2", 0.0)
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        if rw >= 1.0 and rh >= 1.0:
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 1.0))
            ctx.set_line_width(width)
            ctx.rectangle(rx, ry, rw, rh)
            ctx.stroke()

    elif tool == "ellipse":
        x1, y1 = stroke.get("x1", 0.0), stroke.get("y1", 0.0)
        x2, y2 = stroke.get("x2", 0.0), stroke.get("y2", 0.0)
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        rx, ry = abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0
        if rx >= 1.0 and ry >= 1.0:
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 1.0))
            ctx.set_line_width(width)
            ctx.save()
            ctx.translate(cx, cy)
            ctx.scale(rx, ry)
            ctx.arc(0.0, 0.0, 1.0, 0.0, math.tau)
            ctx.restore()
            ctx.stroke()

    elif tool == "text":
        txt = stroke.get("text", "")
        if txt:
            x, y = stroke.get("x1", 0.0), stroke.get("y1", 0.0)
            font_px = max(18, int(round(width * 3.8)))
            layout = PangoCairo.create_layout(ctx)
            desc = Pango.FontDescription.from_string(f"Sans Bold {font_px}px")
            layout.set_font_description(desc)
            layout.set_text(txt, -1)
            ink, logical = layout.get_pixel_extents()
            tw = max(1, logical.width)
            th = max(1, logical.height)
            pad = max(6, int(font_px * 0.22))
            # Subtle dark pill backdrop for crisp legibility on any photo
            ctx.set_source_rgba(0.06, 0.08, 0.12, 0.58)
            ctx.rectangle(x - pad, y - pad, tw + pad * 2, th + pad * 2)
            ctx.fill()

            ctx.move_to(x, y)
            ctx.set_source_rgba(*hex_to_rgba(color_hex, 1.0))
            PangoCairo.show_layout(ctx, layout)

    elif tool == "blur_preview":
        x1, y1 = stroke.get("x1", 0.0), stroke.get("y1", 0.0)
        x2, y2 = stroke.get("x2", 0.0), stroke.get("y2", 0.0)
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        if rw >= 1.0 and rh >= 1.0:
            ctx.set_source_rgba(0.06, 0.30, 0.36, 0.30)
            ctx.rectangle(rx, ry, rw, rh)
            ctx.fill_preserve()
            ctx.set_source_rgba(0.60, 0.96, 0.89, 0.95)
            ctx.set_line_width(max(2.0, 2.0 / max(scale_factor, 0.1)))
            ctx.set_dash([8.0 / max(scale_factor, 0.1), 5.0 / max(scale_factor, 0.1)])
            ctx.stroke()

    ctx.restore()


def composite_full_image(base_img, adjustments, strokes, straighten_angle=0.0):
    """Render full-resolution edited PIL RGBA image combining adjustments, blur, Cairo markup, and rotation."""
    if base_img is None:
        return None
    img = apply_adjustments_and_filter(base_img, adjustments)

    # Apply blur/pixelate regions directly onto pixels first
    vector_strokes = []
    for st in strokes:
        if st.get("tool") == "blur":
            img = apply_blur_stroke_to_pil(img, st)
        else:
            vector_strokes.append(st)

    # Render Cairo vector markup (freehand, highlighter, arrows, shapes, Arabic/English text)
    if vector_strokes:
        surf = pil_to_cairo_surface(img)
        ctx = cairo.Context(surf)
        for st in vector_strokes:
            draw_stroke_on_cairo(ctx, st, scale_factor=1.0)
        img = cairo_surface_to_pil(surf)

    if abs(straighten_angle) >= 0.05:
        img = straighten_image(img, straighten_angle)

    return img


class EditorHistory:
    """Undo/Redo history stack storing full editor states."""

    def __init__(self, max_steps=25):
        self.max_steps = max_steps
        self._undo = []
        self._redo = []

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def push(self, base_img, strokes, adjustments):
        snap = (
            base_img.copy() if base_img is not None else None,
            copy.deepcopy(strokes),
            copy.deepcopy(adjustments),
        )
        self._undo.append(snap)
        if len(self._undo) > self.max_steps:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self):
        return len(self._undo) > 0

    def can_redo(self):
        return len(self._redo) > 0

    def undo(self, cur_img, cur_strokes, cur_adj):
        if not self._undo:
            return None
        self._redo.append((
            cur_img.copy() if cur_img is not None else None,
            copy.deepcopy(cur_strokes),
            copy.deepcopy(cur_adj),
        ))
        return self._undo.pop()

    def redo(self, cur_img, cur_strokes, cur_adj):
        if not self._redo:
            return None
        self._undo.append((
            cur_img.copy() if cur_img is not None else None,
            copy.deepcopy(cur_strokes),
            copy.deepcopy(cur_adj),
        ))
        return self._redo.pop()


def save_pil_image(pil_img, dest_path, fmt=None, quality=92):
    """Save PIL Image in PNG, JPEG, or WebP format safely."""
    ext = os.path.splitext(dest_path)[1].lower()
    if not fmt:
        if ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
        elif ext == ".webp":
            fmt = "WEBP"
        elif ext == ".bmp":
            fmt = "BMP"
        elif ext in (".tif", ".tiff"):
            fmt = "TIFF"
        else:
            fmt = "PNG"
    fmt = fmt.upper()
    if fmt == "JPG":
        fmt = "JPEG"

    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    if fmt == "JPEG":
        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
        if pil_img.mode == "RGBA":
            bg.paste(pil_img, mask=pil_img.split()[3])
        else:
            bg.paste(pil_img.convert("RGB"))
        bg.save(dest_path, format="JPEG", quality=quality, optimize=True)
    elif fmt == "WEBP":
        pil_img.save(dest_path, format="WEBP", quality=quality, method=4)
    elif fmt == "PNG":
        pil_img.save(dest_path, format="PNG", optimize=True)
    else:
        pil_img.save(dest_path, format=fmt)


def copy_pil_to_clipboard(pil_img, display=None):
    """Copy a PIL Image as PNG bytes into the GTK4 system clipboard."""
    if display is None:
        display = Gdk.Display.get_default()
    if not display:
        raise RuntimeError("No display available")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    png_bytes = GLib.Bytes.new(buf.getvalue())
    provider = Gdk.ContentProvider.new_for_bytes("image/png", png_bytes)
    clipboard = display.get_clipboard()
    clipboard.set_content(provider)
