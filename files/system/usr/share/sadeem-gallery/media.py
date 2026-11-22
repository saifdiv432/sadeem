#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media scanning, EXIF extraction, RAW/HEIC/AVIF decoding, thumbnail caching,
and desktop wallpaper integration for Sadeem Gallery.
"""

import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile

from gi.repository import GLib
from PIL import ExifTags, Image, ImageOps

import i18n

CONFIG_DIR = os.path.expanduser("~/.config/sadeem-gallery")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
CACHE_DIR = os.path.expanduser("~/.cache/sadeem-gallery")
THUMB_CACHE_DIR = os.path.join(CACHE_DIR, "thumbs")
META_CACHE_FILE = os.path.join(CACHE_DIR, "meta.json")
THUMB_SIZE = 220

STANDARD_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".ico", ".svg",
    ".heif", ".heic", ".avif", ".jxl",
}

RAW_EXTS = {
    ".cr2", ".cr3", ".nef", ".arw", ".dng",
    ".raf", ".orf", ".rw2", ".raw", ".pef", ".srw",
}

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

ALL_IMAGE_EXTS = STANDARD_EXTS | RAW_EXTS
ALL_MEDIA_EXTS = ALL_IMAGE_EXTS | VIDEO_EXTS
MAGICK_PREFERRED_EXTS = RAW_EXTS | {".heif", ".heic", ".avif", ".jxl", ".svg"}

# Reverse map EXIF tag names -> IDs
EXIF_TAG_MAP = {v: k for k, v in ExifTags.TAGS.items()}
TAG_DATETIME_ORIG = EXIF_TAG_MAP.get("DateTimeOriginal", 36867)
TAG_DATETIME = EXIF_TAG_MAP.get("DateTime", 306)
TAG_MAKE = EXIF_TAG_MAP.get("Make", 271)
TAG_MODEL = EXIF_TAG_MAP.get("Model", 272)
TAG_FNUMBER = EXIF_TAG_MAP.get("FNumber", 33437)
TAG_ISO = EXIF_TAG_MAP.get("ISOSpeedRatings", 34855)
TAG_EXPOSURE = EXIF_TAG_MAP.get("ExposureTime", 33434)
TAG_FOCAL = EXIF_TAG_MAP.get("FocalLength", 37386)
TAG_LENS = EXIF_TAG_MAP.get("LensModel", 42036)


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)


def _magick_bin():
    return shutil.which("magick") or shutil.which("convert")


def load_meta_cache():
    if os.path.isfile(META_CACHE_FILE):
        try:
            with open(META_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_meta_cache(cache_data):
    ensure_dirs()
    try:
        tmp = f"{META_CACHE_FILE}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
        os.replace(tmp, META_CACHE_FILE)
    except Exception:
        pass


def get_default_pictures_dir():
    try:
        pic_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pic_dir and os.path.isdir(pic_dir):
            return pic_dir
    except Exception:
        pass
    for candidate in (os.path.expanduser("~/Pictures"), os.path.expanduser("~/الصور")):
        if os.path.isdir(candidate):
            return candidate
    return os.path.expanduser("~/Pictures")


def load_settings():
    ensure_dirs()
    defaults = {"extra_folders": []}
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
    return defaults


def save_settings(settings):
    ensure_dirs()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_scan_directories(settings=None):
    if settings is None:
        settings = load_settings()
    dirs = []
    default_dir = get_default_pictures_dir()
    if default_dir and os.path.isdir(default_dir):
        dirs.append(os.path.abspath(default_dir))
    for folder in settings.get("extra_folders", []):
        ap = os.path.abspath(os.path.expanduser(folder))
        if os.path.isdir(ap) and ap not in dirs:
            dirs.append(ap)
    return dirs


def is_supported_image(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in ALL_IMAGE_EXTS


def is_video_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in VIDEO_EXTS


def is_supported_media(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in ALL_MEDIA_EXTS


def is_raw_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in RAW_EXTS


def is_animated_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".gif":
        return True
    if ext == ".webp":
        try:
            with Image.open(path) as img:
                return bool(getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1)
        except Exception:
            return False
    return False


def _parse_exif_datetime(raw_str):
    if not raw_str:
        return None
    s = str(raw_str).strip().replace("\x00", "")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.datetime.strptime(s[:19], fmt)
        except Exception:
            continue
    return None


def _probe_svg_dimensions(path):
    """Quickly parse width/height or viewBox from the header of an SVG file."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(8192)
        m_vb = re.search(r'viewBox\s*=\s*["\']\s*[-+\d.]+\s+[-+\d.]+\s+([+\d.]+)\s+([+\d.]+)\s*["\']', head, re.IGNORECASE)
        if m_vb:
            return int(float(m_vb.group(1))), int(float(m_vb.group(2)))
        mw = re.search(r'\bwidth\s*=\s*["\']\s*([+\d.]+)', head, re.IGNORECASE)
        mh = re.search(r'\bheight\s*=\s*["\']\s*([+\d.]+)', head, re.IGNORECASE)
        if mw and mh:
            return int(float(mw.group(1))), int(float(mh.group(1)))
    except Exception:
        pass
    return 0, 0


def _probe_raw_dimensions(path):
    """Attempt fast dimension extraction for RAW formats via ImageMagick identify."""
    mbin = _magick_bin()
    if not mbin:
        return 0, 0
    try:
        cmd = [mbin, "identify", "-format", "%w %h", f"{path}[0]"] if os.path.basename(mbin) == "magick" else [mbin, "-format", "%w %h", f"{path}[0]"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0, check=False)
        if res.returncode == 0 and res.stdout:
            parts = res.stdout.strip().split()
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 0, 0


def _probe_fast_metadata(path, ext, st):
    """
    Fast lazy header probe returning (dt, width, height, is_animated, duration, duration_str).
    Avoids pixel decoding so directory scans stay instantaneous.
    """
    dt = None
    w, h = 0, 0
    animated = (ext == ".gif")
    duration = 0.0
    duration_str = "00:00"

    if ext in VIDEO_EXTS:
        try:
            import video_utils
            vmeta = video_utils.get_video_metadata(path)
            w = vmeta.get("width", 0)
            h = vmeta.get("height", 0)
            duration = vmeta.get("duration", 0.0)
            duration_str = vmeta.get("duration_str", "00:00")
        except Exception:
            pass
    elif ext == ".svg":
        w, h = _probe_svg_dimensions(path)
    else:
        try:
            with Image.open(path) as img:
                w, h = img.size
                if ext == ".webp":
                    animated = bool(getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1)
                if ext in (".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".png") or ext in RAW_EXTS:
                    exif = img.getexif()
                    if exif:
                        # Swap width/height for 90°/270° EXIF orientation tags
                        orient = exif.get(274)
                        if orient in (5, 6, 7, 8):
                            w, h = h, w
                        dt_str = None
                        try:
                            sub = exif.get_ifd(0x8769)
                            if sub:
                                dt_str = sub.get(TAG_DATETIME_ORIG)
                        except Exception:
                            pass
                        if not dt_str:
                            dt_str = exif.get(TAG_DATETIME_ORIG) or exif.get(TAG_DATETIME)
                        dt = _parse_exif_datetime(dt_str)
        except Exception:
            pass

    if ext in RAW_EXTS and (w <= 0 or h <= 0):
        rw, rh = _probe_raw_dimensions(path)
        if rw > 0 and rh > 0:
            w, h = rw, rh

    if dt is None:
        try:
            mtime = st.st_mtime if st is not None else os.path.getmtime(path)
            dt = datetime.datetime.fromtimestamp(mtime)
        except Exception:
            dt = datetime.datetime.now()

    return dt, w, h, animated, duration, duration_str


def is_screenshot_item(path, name):
    """Detect screenshots by folder name or filename prefix (Arabic & English)."""
    parts = [p.lower() for p in os.path.normpath(os.path.dirname(path)).split(os.sep)]
    if any(p in ("screenshots", "screenshot", "لقطات الشاشة", "لقطات_الشاشة") for p in parts):
        return True
    low = name.strip().lower()
    for prefix in ("screenshot", "screen shot", "screen_shot", "لقطة شاشة", "لقطة_شاشة", "لقطة للشاشة", "لقطة من"):
        if low.startswith(prefix):
            return True
    return False


def matches_format(item, fmt):
    """Match media format category."""
    if not fmt or fmt == "all":
        return True
    ext = (item.get("ext") or "").lower()
    if fmt == "video":
        return bool(item.get("is_video", False)) or ext in VIDEO_EXTS
    if fmt == "jpeg":
        return ext in (".jpg", ".jpeg")
    if fmt == "png":
        return ext == ".png"
    if fmt == "webp":
        return ext == ".webp"
    if fmt == "heic_avif":
        return ext in (".heic", ".heif", ".avif")
    if fmt == "animated":
        return bool(item.get("is_animated", False)) or ext == ".gif"
    if fmt == "raw":
        return bool(item.get("is_raw", False)) or ext in RAW_EXTS
    if fmt == "vector":
        return ext in (".svg", ".ico")
    if fmt == "other":
        return ext in (".tiff", ".tif", ".bmp", ".jxl")
    return True


def matches_dimensions(item, dim):
    """Match image dimensions and aspect ratio category."""
    if not dim or dim == "all":
        return True
    w = int(item.get("width", 0) or 0)
    h = int(item.get("height", 0) or 0)
    if w <= 0 or h <= 0:
        return False
    ratio = w / h
    longest = max(w, h)
    shortest = min(w, h)
    aspect_max = longest / shortest
    if dim == "landscape":
        return w > h
    if dim == "portrait":
        return h > w
    if dim == "square":
        return 0.95 <= ratio <= 1.05
    if dim == "ultrawide":
        return aspect_max >= 1.7
    if dim == "standard":
        return 1.25 <= aspect_max <= 1.65
    return True


def matches_resolution(item, res):
    """Match image resolution category based on longest side max(width, height)."""
    if not res or res == "all":
        return True
    w = int(item.get("width", 0) or 0)
    h = int(item.get("height", 0) or 0)
    longest = max(w, h)
    if longest <= 0:
        return False
    if res == "low":
        return longest < 1280
    if res == "hd":
        return 1280 <= longest < 1920
    if res == "fhd":
        return 1920 <= longest < 2560
    if res == "2k":
        return 2560 <= longest < 3840
    if res == "4k":
        return longest >= 3840
    return True


def matches_filters(item, fmt="all", dim="all", res="all"):
    """Evaluate whether an item matches all 3 orthogonal filters simultaneously (AND logic)."""
    return (
        matches_format(item, fmt) and
        matches_dimensions(item, dim) and
        matches_resolution(item, res)
    )


def matches_category(item, category):
    """Legacy helper for backward compatibility."""
    if not category or category == "all":
        return True
    if category in ("camera", "screenshots", "hd", "portrait", "landscape", "animated", "raw", "vector"):
        ext = item.get("ext", "")
        w = int(item.get("width", 0) or 0)
        h = int(item.get("height", 0) or 0)
        if category == "camera":
            return ext in (".jpg", ".jpeg", ".heic", ".heif", ".png")
        if category == "screenshots":
            return bool(item.get("is_screenshot", False))
        if category == "hd":
            return max(w, h) >= 1920
        if category == "portrait":
            return h > w > 0
        if category == "landscape":
            return w > h > 0
        if category == "animated":
            return bool(item.get("is_animated", False)) or ext == ".gif"
        if category == "raw":
            return bool(item.get("is_raw", False)) or ext in RAW_EXTS
        if category == "vector":
            return ext in (".svg", ".ico")
    return matches_filters(item, fmt=category)


def scan_directories(directories):
    """Recursively scan directories excluding hidden folders/files, sorted newest-first with fast metadata caching."""
    meta_cache = load_meta_cache()
    dirty = False
    items = []
    seen = set()

    for root_dir in directories:
        if not os.path.isdir(root_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Exclude hidden directories in-place
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                if fname.startswith("."):
                    continue
                full = os.path.join(dirpath, fname)
                if not is_supported_media(full):
                    continue
                try:
                    real = os.path.realpath(full)
                    if real in seen:
                        continue
                    seen.add(real)
                    st = os.stat(full)
                except OSError:
                    continue

                ext = os.path.splitext(full)[1].lower()
                cached = meta_cache.get(real)
                if (
                    cached
                    and isinstance(cached, dict)
                    and cached.get("mtime") == st.st_mtime
                    and cached.get("width", 0) > 0
                    and cached.get("height", 0) > 0
                ):
                    w = int(cached.get("width") or 0)
                    h = int(cached.get("height") or 0)
                    animated = bool(cached.get("is_animated", False))
                    duration = float(cached.get("duration", 0.0) or 0.0)
                    duration_str = cached.get("duration_str", "00:00")
                    dt_str = cached.get("dt")
                    dt = None
                    if dt_str:
                        try:
                            dt = datetime.datetime.fromisoformat(dt_str)
                        except Exception:
                            dt = None
                    if dt is None:
                        dt = datetime.datetime.fromtimestamp(st.st_mtime)
                else:
                    dt, w, h, animated, duration, duration_str = _probe_fast_metadata(full, ext, st)
                    meta_cache[real] = {
                        "mtime": st.st_mtime,
                        "dt": dt.isoformat() if dt else None,
                        "width": w,
                        "height": h,
                        "is_animated": animated,
                        "is_video": (ext in VIDEO_EXTS),
                        "duration": duration,
                        "duration_str": duration_str,
                    }
                    dirty = True

                items.append({
                    "path": full,
                    "name": fname,
                    "ext": ext,
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                    "dt": dt,
                    "width": w,
                    "height": h,
                    "is_raw": ext in RAW_EXTS,
                    "is_animated": animated,
                    "is_video": ext in VIDEO_EXTS,
                    "duration": duration,
                    "duration_str": duration_str,
                    "is_screenshot": is_screenshot_item(full, fname),
                })

    if dirty:
        save_meta_cache(meta_cache)

    items.sort(key=lambda x: (x["dt"], x["mtime"]), reverse=True)
    return items


def list_sibling_images(file_path):
    """List supported media in the same folder sorted newest-first, plus active index."""
    folder = os.path.dirname(os.path.abspath(file_path))
    target_real = os.path.realpath(file_path)
    items = []
    try:
        for fname in os.listdir(folder):
            if fname.startswith("."):
                continue
            full = os.path.join(folder, fname)
            if not os.path.isfile(full) or not is_supported_media(full):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            ext = os.path.splitext(full)[1].lower()
            is_vid = ext in VIDEO_EXTS
            dur = 0.0
            dur_str = "00:00"
            if is_vid:
                try:
                    import video_utils
                    vmeta = video_utils.get_video_metadata(full)
                    dur = vmeta.get("duration", 0.0)
                    dur_str = vmeta.get("duration_str", "00:00")
                except Exception:
                    pass
            items.append({
                "path": full,
                "name": fname,
                "ext": ext,
                "mtime": st.st_mtime,
                "size": st.st_size,
                "dt": datetime.datetime.fromtimestamp(st.st_mtime),
                "is_raw": ext in RAW_EXTS,
                "is_animated": ext == ".gif" or (ext == ".webp" and is_animated_file(full)),
                "is_video": is_vid,
                "duration": dur,
                "duration_str": dur_str,
            })
    except OSError:
        pass

    items.sort(key=lambda x: (x["mtime"], x["name"].lower()), reverse=True)
    idx = 0
    found = False
    for i, it in enumerate(items):
        if os.path.realpath(it["path"]) == target_real:
            idx = i
            found = True
            break
    if not found and os.path.isfile(file_path):
        st = os.stat(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        is_vid = ext in VIDEO_EXTS
        dur = 0.0
        dur_str = "00:00"
        if is_vid:
            try:
                import video_utils
                vmeta = video_utils.get_video_metadata(file_path)
                dur = vmeta.get("duration", 0.0)
                dur_str = vmeta.get("duration_str", "00:00")
            except Exception:
                pass
        items.insert(0, {
            "path": os.path.abspath(file_path),
            "name": os.path.basename(file_path),
            "ext": ext,
            "mtime": st.st_mtime,
            "size": st.st_size,
            "dt": datetime.datetime.fromtimestamp(st.st_mtime),
            "is_raw": ext in RAW_EXTS,
            "is_animated": is_animated_file(file_path),
            "is_video": is_vid,
            "duration": dur,
            "duration_str": dur_str,
        })
        idx = 0
    return items, idx


def group_items_by_date(items):
    """Group sorted items into ordered (group_label, [items]) sections."""
    now = datetime.datetime.now()
    today = now.date()
    yesterday = today - datetime.timedelta(days=1)

    groups = []
    group_map = {}

    for item in items:
        d = item["dt"].date()
        if d == today:
            key = ("today", i18n.t("date_today"))
        elif d == yesterday:
            key = ("yesterday", i18n.t("date_yesterday"))
        elif d.year == today.year and d.month == today.month:
            key = ("this_month", i18n.t("date_this_month"))
        else:
            key = (f"{d.year}-{d.month:02d}", i18n.format_month_year(d.year, d.month))

        if key not in group_map:
            bucket = []
            group_map[key] = bucket
            groups.append((key[1], bucket))
        group_map[key].append(item)

    return groups


def _thumb_cache_path(path, mtime, size):
    ensure_dirs()
    sig = f"{os.path.realpath(path)}|{int(mtime)}|{size}|{THUMB_SIZE}"
    h = hashlib.md5(sig.encode("utf-8", errors="ignore")).hexdigest()
    return os.path.join(THUMB_CACHE_DIR, f"{h}.jpg")


def _extract_embedded_jpeg_preview(raw_path, max_scan_bytes=12 * 1024 * 1024):
    """
    Quickly extract the largest embedded JPEG preview from a camera RAW file
    (CR2/CR3/NEF/ARW/DNG/ORF/RW2/RAF) without invoking a full demosaic pass.
    """
    try:
        with open(raw_path, "rb") as f:
            data = f.read(max_scan_bytes)
        best_img = None
        best_pixels = 0
        pos = 0
        # Scan up to 8 embedded JPEG segments
        found = 0
        while found < 8:
            start = data.find(b"\xff\xd8\xff", pos)
            if start < 0:
                break
            end = data.find(b"\xff\xd9", start + 3)
            if end < 0:
                break
            chunk = data[start:end + 2]
            pos = end + 2
            if len(chunk) < 12000:
                continue
            found += 1
            try:
                with Image.open(io.BytesIO(chunk)) as candidate:
                    w, h = candidate.size
                    if w * h > best_pixels and w >= 160 and h >= 120:
                        best_pixels = w * h
                        best_img = ImageOps.exif_transpose(candidate).convert("RGB")
            except Exception:
                continue
        return best_img
    except Exception:
        return None


def _magick_decode_to_pil(path, max_dim=None):
    """Decode RAW/HEIC/AVIF/JXL/SVG via ImageMagick into a PIL Image."""
    mbin = _magick_bin()
    if not mbin:
        raise RuntimeError("ImageMagick (magick) is not available")

    tmp_fd, tmp_out = tempfile.mkstemp(prefix="sadeem-gal-", suffix=".png")
    os.close(tmp_fd)
    try:
        cmd = [mbin, f"{path}[0]", "-auto-orient"]
        if max_dim:
            cmd += ["-thumbnail", f"{max_dim}x{max_dim}>"]
        cmd.append(tmp_out)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
        if res.returncode != 0 or not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) == 0:
            err = (res.stderr or res.stdout or "magick failed").strip()
            raise RuntimeError(err)
        with Image.open(tmp_out) as im:
            return im.convert("RGBA")
    finally:
        try:
            os.remove(tmp_out)
        except OSError:
            pass


def get_or_create_thumbnail(item):
    """Generate and cache a 220x220 JPEG thumbnail on disk, returning its path or None."""
    path = item["path"]
    cache_path = _thumb_cache_path(path, item.get("mtime", 0), item.get("size", 0))
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
        return cache_path

    ext = item.get("ext", os.path.splitext(path)[1].lower())

    # Video thumbnail extraction via ffmpeg
    if ext in VIDEO_EXTS or item.get("is_video"):
        try:
            import video_utils
            ok = video_utils.generate_video_thumbnail(path, cache_path, duration=item.get("duration"))
            if ok and os.path.isfile(cache_path):
                return cache_path
        except Exception:
            pass
        return None

    thumb_img = None

    # 1. Fast embedded JPEG preview for RAW files
    if ext in RAW_EXTS:
        thumb_img = _extract_embedded_jpeg_preview(path)

    # 2. Native Pillow path for standard images
    if thumb_img is None and ext not in RAW_EXTS and ext != ".svg":
        try:
            with Image.open(path) as im:
                im.seek(0)
                im = ImageOps.exif_transpose(im)
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA")
                if im.mode == "RGBA":
                    bg = Image.new("RGB", im.size, (28, 28, 34))
                    bg.paste(im, mask=im.split()[3])
                    thumb_img = bg
                else:
                    thumb_img = im.convert("RGB")
        except Exception:
            thumb_img = None

    # 3. SVG via GdkPixbuf (fast) or ImageMagick fallback
    if thumb_img is None and ext == ".svg":
        try:
            import gi
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, THUMB_SIZE, THUMB_SIZE, True)
            ok, buf = pb.save_to_bufferv("png", [], [])
            if ok:
                with Image.open(io.BytesIO(buf)) as im:
                    im = im.convert("RGBA")
                    bg = Image.new("RGB", im.size, (28, 28, 34))
                    bg.paste(im, mask=im.split()[3])
                    thumb_img = bg
        except Exception:
            thumb_img = None

    # 4. ImageMagick fallback for RAW / HEIC / AVIF / JXL / SVG
    if thumb_img is None:
        try:
            im = _magick_decode_to_pil(path, max_dim=THUMB_SIZE * 2)
            bg = Image.new("RGB", im.size, (28, 28, 34))
            bg.paste(im, mask=im.split()[3])
            thumb_img = bg
        except Exception:
            return None

    try:
        fitted = ImageOps.fit(thumb_img, (THUMB_SIZE, THUMB_SIZE), method=Image.Resampling.LANCZOS)
        tmp_path = f"{cache_path}.{os.getpid()}.tmp"
        fitted.save(tmp_path, format="JPEG", quality=86, optimize=True)
        os.replace(tmp_path, cache_path)
        return cache_path
    except Exception:
        return None


def load_full_image(path):
    """Load full-resolution image as PIL RGBA, honoring EXIF orientation and RAW/HEIC/SVG."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".svg":
        try:
            import gi
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 1600, 1600, True)
            ok, buf = pb.save_to_bufferv("png", [], [])
            if ok:
                with Image.open(io.BytesIO(buf)) as im:
                    return im.convert("RGBA")
        except Exception:
            pass
        return _magick_decode_to_pil(path, max_dim=2400)

    if ext in RAW_EXTS:
        # Try full ImageMagick decode first for highest quality; fall back to embedded JPEG if slow/unsupported
        try:
            return _magick_decode_to_pil(path)
        except Exception:
            preview = _extract_embedded_jpeg_preview(path, max_scan_bytes=32 * 1024 * 1024)
            if preview is not None:
                return preview.convert("RGBA")
            raise

    # Try Pillow first (handles JPEG/PNG/WebP/GIF/TIFF/BMP/ICO, and HEIC/AVIF if plugin present)
    try:
        with Image.open(path) as im:
            im.seek(0)
            im = ImageOps.exif_transpose(im)
            return im.convert("RGBA")
    except Exception:
        # Fallback to ImageMagick for HEIC/HEIF/AVIF/JXL or unusual variants
        return _magick_decode_to_pil(path)


def load_animated_frames(path, max_frames=240):
    """Return list of (PIL.Image RGBA, duration_ms) if animated GIF/WebP, else None."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".gif", ".webp"):
        return None
    try:
        with Image.open(path) as im:
            n_frames = getattr(im, "n_frames", 1)
            if not getattr(im, "is_animated", False) or n_frames <= 1:
                return None
            frames = []
            count = min(n_frames, max_frames)
            for idx in range(count):
                im.seek(idx)
                delay = int(im.info.get("duration", 80) or 80)
                delay = max(25, min(delay, 2000))
                frames.append((im.convert("RGBA"), delay))
            return frames if len(frames) > 1 else None
    except Exception:
        return None


def _fmt_filesize(num_bytes):
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def _fmt_rational(val):
    try:
        if hasattr(val, "numerator") and hasattr(val, "denominator"):
            if val.denominator == 0:
                return None
            return val.numerator / val.denominator
        if isinstance(val, tuple) and len(val) == 2 and val[1]:
            return val[0] / val[1]
        return float(val)
    except Exception:
        return None


def _fmt_shutter(val):
    f = _fmt_rational(val)
    if f is None or f <= 0:
        return None
    if f >= 1.0:
        return f"{f:.1f} s"
    denom = int(round(1.0 / f))
    return f"1/{denom} s"


def extract_exif_info(path, pil_image=None):
    """Extract human-readable EXIF & file metadata dict."""
    info = {
        "filename": os.path.basename(path),
        "folder": os.path.dirname(os.path.abspath(path)),
        "dimensions": i18n.t("exif_unknown"),
        "filesize": i18n.t("exif_unknown"),
        "format": os.path.splitext(path)[1].lstrip(".").upper() or i18n.t("exif_unknown"),
        "date": i18n.t("exif_unknown"),
        "camera": i18n.t("exif_unknown"),
        "lens": i18n.t("exif_unknown"),
        "aperture": i18n.t("exif_unknown"),
        "iso": i18n.t("exif_unknown"),
        "shutter": i18n.t("exif_unknown"),
        "focal": i18n.t("exif_unknown"),
    }

    try:
        st = os.stat(path)
        info["filesize"] = _fmt_filesize(st.st_size)
        info["date"] = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d  %H:%M")
    except OSError:
        pass

    if pil_image is not None:
        info["dimensions"] = f"{pil_image.width} × {pil_image.height} px"

    # Try Pillow EXIF first
    try:
        with Image.open(path) as im:
            if pil_image is None:
                info["dimensions"] = f"{im.width} × {im.height} px"
            if im.format:
                info["format"] = im.format
            exif = im.getexif()
            if exif:
                merged = dict(exif)
                try:
                    sub = exif.get_ifd(0x8769)
                    if sub:
                        merged.update(sub)
                except Exception:
                    pass

                dt_raw = merged.get(TAG_DATETIME_ORIG) or merged.get(TAG_DATETIME)
                dt = _parse_exif_datetime(dt_raw)
                if dt:
                    info["date"] = dt.strftime("%Y-%m-%d  %H:%M:%S")

                make = str(merged.get(TAG_MAKE, "")).strip().replace("\x00", "")
                model = str(merged.get(TAG_MODEL, "")).strip().replace("\x00", "")
                if model:
                    if make and make.lower() not in model.lower():
                        info["camera"] = f"{make} {model}"
                    else:
                        info["camera"] = model
                elif make:
                    info["camera"] = make

                lens = str(merged.get(TAG_LENS, "")).strip().replace("\x00", "")
                if lens:
                    info["lens"] = lens

                fnum = _fmt_rational(merged.get(TAG_FNUMBER))
                if fnum:
                    info["aperture"] = f"f/{fnum:.1f}"

                iso_val = merged.get(TAG_ISO)
                if isinstance(iso_val, (list, tuple)) and iso_val:
                    iso_val = iso_val[0]
                if iso_val:
                    info["iso"] = f"ISO {iso_val}"

                shutter = _fmt_shutter(merged.get(TAG_EXPOSURE))
                if shutter:
                    info["shutter"] = shutter

                focal = _fmt_rational(merged.get(TAG_FOCAL))
                if focal:
                    info["focal"] = f"{focal:.0f} mm"
    except Exception:
        # Fallback for RAW/HEIC/AVIF via ImageMagick identify
        mbin = _magick_bin()
        if mbin:
            try:
                fmt_str = (
                    "W=%w\nH=%h\nFMT=%m\nDATE=%[exif:DateTimeOriginal]\n"
                    "MAKE=%[exif:Make]\nMODEL=%[exif:Model]\nLENS=%[exif:LensModel]\n"
                    "FNUM=%[exif:FNumber]\nISO=%[exif:ISOSpeedRatings]\n"
                    "EXP=%[exif:ExposureTime]\nFOCAL=%[exif:FocalLength]"
                )
                cmd = [mbin, "identify", "-format", fmt_str, f"{path}[0]"] if os.path.basename(mbin) == "magick" else ["identify", "-format", fmt_str, f"{path}[0]"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
                if res.returncode == 0 and res.stdout:
                    kv = {}
                    for line in res.stdout.splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            kv[k.strip()] = v.strip()
                    if kv.get("W") and kv.get("H") and info["dimensions"] == i18n.t("exif_unknown"):
                        info["dimensions"] = f"{kv['W']} × {kv['H']} px"
                    if kv.get("FMT"):
                        info["format"] = kv["FMT"]
                    dt = _parse_exif_datetime(kv.get("DATE"))
                    if dt:
                        info["date"] = dt.strftime("%Y-%m-%d  %H:%M:%S")
                    if kv.get("MODEL"):
                        mk = kv.get("MAKE", "")
                        md = kv["MODEL"]
                        info["camera"] = f"{mk} {md}".strip() if (mk and mk.lower() not in md.lower()) else md
                    if kv.get("LENS"):
                        info["lens"] = kv["LENS"]
                    if kv.get("FNUM"):
                        m = re.match(r"(\d+)\s*/\s*(\d+)", kv["FNUM"])
                        val = (int(m.group(1)) / int(m.group(2))) if (m and int(m.group(2))) else _fmt_rational(kv["FNUM"])
                        if val:
                            info["aperture"] = f"f/{val:.1f}"
                    if kv.get("ISO"):
                        info["iso"] = f"ISO {kv['ISO']}"
                    if kv.get("EXP"):
                        if "/" in kv["EXP"]:
                            info["shutter"] = f"{kv['EXP']} s"
                        else:
                            sh = _fmt_shutter(kv["EXP"])
                            if sh:
                                info["shutter"] = sh
                    if kv.get("FOCAL"):
                        m = re.match(r"(\d+)\s*/\s*(\d+)", kv["FOCAL"])
                        val = (int(m.group(1)) / int(m.group(2))) if (m and int(m.group(2))) else _fmt_rational(kv["FOCAL"])
                        if val:
                            info["focal"] = f"{val:.0f} mm"
            except Exception:
                pass

    return info


def set_desktop_wallpaper(path, pil_image=None):
    """Set GNOME desktop wallpaper (light + dark). Converts RAW/HEIC automatically."""
    target_path = os.path.abspath(path)
    ext = os.path.splitext(target_path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        bg_dir = os.path.expanduser("~/.local/share/backgrounds")
        os.makedirs(bg_dir, exist_ok=True)
        target_path = os.path.join(bg_dir, "sadeem-gallery-wallpaper.jpg")
        img = pil_image if pil_image is not None else load_full_image(path)
        img.convert("RGB").save(target_path, format="JPEG", quality=94)

    uri = GLib.filename_to_uri(target_path, None)
    for key in ("picture-uri", "picture-uri-dark"):
        res = subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", key, uri],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError((res.stderr or "gsettings failed").strip())
    return target_path
