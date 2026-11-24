#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Windows Shortcut & Icon Synchronizer.
Parses Wine/Windows .lnk shortcuts inside the Sadeem-Windows bottle, extracts
application/game icons from .ico or 32/64-bit PE (.exe/.dll) resources in pure Python,
and manages GNOME .desktop entries under ~/.local/share/applications/.
"""

import glob
import hashlib
import io
import os
import re
import shutil
import struct
import subprocess
import tempfile

from PIL import Image

BOTTLE_NAME = "Sadeem-Windows"
DEFAULT_BOTTLE_DIR = os.path.expanduser(
    f"~/.var/app/com.usebottles.bottles/data/bottles/bottles/{BOTTLE_NAME}"
)
DEFAULT_APPLICATIONS_DIR = os.path.expanduser("~/.local/share/applications")
DEFAULT_ICONS_DIR = os.path.expanduser("~/.local/share/sadeem-windows/icons")
HANDLER_EXECUTABLE = "/usr/bin/sadeem-windows-exe-handler"
FALLBACK_ICON_NAME = "application-x-ms-dos-executable"

LNK_CLSID = b"\x01\x14\x02\x00\x00\x00\x00\x00\xc0\x00\x00\x00\x00\x00\x00F"

# MS-SHLLINK LinkFlags
FLAG_HAS_ID_LIST = 0x00000001
FLAG_HAS_LINK_INFO = 0x00000002
FLAG_HAS_NAME = 0x00000004
FLAG_HAS_RELATIVE_PATH = 0x00000008
FLAG_HAS_WORKING_DIR = 0x00000010
FLAG_HAS_ARGUMENTS = 0x00000020
FLAG_HAS_ICON_LOCATION = 0x00000040
FLAG_IS_UNICODE = 0x00000080

# ExtraData block signatures
SIG_ENV_VAR_DATA = 0xA0000001
SIG_ICON_ENV_DATA = 0xA0000007

# PE resource types
RT_ICON = 3
RT_GROUP_ICON = 14

SUPPORTED_TARGET_EXTS = (".exe", ".bat", ".cmd")
MANAGED_DESKTOP_PREFIX = "sadeem-win-"
MANAGED_KEY = "X-Sadeem-Windows-Managed"

JUNK_SUBSTRINGS = (
    "uninstall",
    "unins0",
    "uninst",
    "unwise",
    "readme",
    "changelog",
    "eula",
    "website",
    "homepage",
    "documentation",
    "check for updates",
    "إلغاء التثبيت",
    "إزالة",
)

JUNK_WORD_RE = re.compile(
    r"\b(?:remove|help|manual|license|licence|register|visit|support|faq|docs|update)\b",
    re.IGNORECASE,
)

JUNK_EXECUTABLES = frozenset({
    "unins000.exe",
    "uninstall.exe",
    "uninst.exe",
    "unwise.exe",
    "hh.exe",
    "winhlp32.exe",
})

GAME_HINT_RE = re.compile(
    r"\b(?:game|games|play|launcher|repack|dodi|fitgirl|steam|gog|epic|ubisoft|"
    r"origin|ea|generals|cnc|directx|dx|benchmark)\b",
    re.IGNORECASE,
)


def _clean_str(val):
    if not val:
        return ""
    return val.replace("\x00", "").strip()


def _read_c_str(buf, offset, limit, encoding="cp1252"):
    if offset <= 0 or offset >= limit or offset >= len(buf):
        return ""
    end = buf.find(b"\x00", offset, min(limit, len(buf)))
    if end == -1:
        end = min(limit, len(buf))
    return _clean_str(buf[offset:end].decode(encoding, errors="replace"))


def _read_c_wstr(buf, offset, limit):
    if offset <= 0 or offset >= limit or offset + 1 >= len(buf):
        return ""
    max_end = min(limit, len(buf))
    pos = offset
    while pos + 1 < max_end:
        if buf[pos] == 0 and buf[pos + 1] == 0:
            break
        pos += 2
    return _clean_str(buf[offset:pos].decode("utf-16-le", errors="replace"))


def _join_win_path(base, suffix):
    base = _clean_str(base)
    suffix = _clean_str(suffix)
    if not base:
        return suffix
    if not suffix:
        return base
    return base.rstrip("\\/") + "\\" + suffix.lstrip("\\/")


def _infer_bottle_dir(path):
    """Best-effort bottle root inference from a path inside .../drive_c/..."""
    norm = os.path.abspath(path)
    marker = os.sep + "drive_c" + os.sep
    idx = norm.lower().find(marker)
    if idx != -1:
        return norm[:idx]
    if norm.lower().endswith(os.sep + "drive_c"):
        return norm[: -len(os.sep + "drive_c")]
    return None


def _detect_bottle_user(bottle_dir, hint_path=None):
    """Detect active Windows username folder inside bottle_dir/drive_c/users."""
    drive_c = os.path.join(bottle_dir, "drive_c")
    users_dir = resolve_case_insensitive_path(drive_c, ["users"])
    if hint_path and users_dir:
        try:
            rel = os.path.relpath(os.path.abspath(hint_path), users_dir)
            parts = [p for p in rel.split(os.sep) if p and p != "."]
            if parts and not parts[0].startswith("..") and parts[0].lower() != "public":
                return parts[0]
        except Exception:
            pass

    if users_dir and os.path.isdir(users_dir):
        entries = sorted(
            e for e in os.listdir(users_dir)
            if os.path.isdir(os.path.join(users_dir, e))
        )
        linux_user = os.environ.get("USER", "").lower()
        for e in entries:
            if e.lower() == linux_user and e.lower() != "public":
                return e
        for e in entries:
            if e.lower() not in ("public", "default", "all users"):
                return e

    return os.environ.get("USER", "steamuser") or "steamuser"


def expand_windows_env_vars(win_path, bottle_dir, hint_path=None):
    """Expand common Windows environment variables inside a path string."""
    if not win_path:
        return ""
    user = _detect_bottle_user(bottle_dir, hint_path=hint_path)
    user_profile = f"C:\\users\\{user}"
    env_map = {
        "programfiles": "C:\\Program Files",
        "programfiles(x86)": "C:\\Program Files (x86)",
        "programw6432": "C:\\Program Files",
        "commonprogramfiles": "C:\\Program Files\\Common Files",
        "commonprogramfiles(x86)": "C:\\Program Files (x86)\\Common Files",
        "systemroot": "C:\\Windows",
        "windir": "C:\\Windows",
        "system32": "C:\\Windows\\System32",
        "programdata": "C:\\ProgramData",
        "allusersprofile": "C:\\ProgramData",
        "public": "C:\\users\\Public",
        "userprofile": user_profile,
        "username": user,
        "appdata": f"{user_profile}\\AppData\\Roaming",
        "roamingappdata": f"{user_profile}\\AppData\\Roaming",
        "localappdata": f"{user_profile}\\AppData\\Local",
        "temp": f"{user_profile}\\Temp",
        "tmp": f"{user_profile}\\Temp",
        "homedrive": "C:",
        "systemdrive": "C:",
    }

    def _repl(match):
        key = match.group(1).lower()
        return env_map.get(key, match.group(0))

    return re.sub(r"%([^%]+)%", _repl, win_path)


def resolve_case_insensitive_path(root_dir, parts):
    """Resolve path segments under root_dir matching components case-insensitively."""
    cur = root_dir
    if not os.path.isdir(cur):
        return None

    clean_parts = []
    for p in parts:
        if not p or p == ".":
            continue
        if p == "..":
            if clean_parts:
                clean_parts.pop()
            continue
        clean_parts.append(p)

    for idx, seg in enumerate(clean_parts):
        direct = os.path.join(cur, seg)
        if os.path.exists(direct):
            cur = direct
            continue
        if not os.path.isdir(cur):
            return os.path.join(cur, *clean_parts[idx:])
        try:
            entries = os.listdir(cur)
        except OSError:
            return os.path.join(cur, *clean_parts[idx:])
        seg_low = seg.lower()
        match = next((e for e in entries if e.lower() == seg_low), None)
        if match is not None:
            cur = os.path.join(cur, match)
        else:
            return os.path.join(cur, *clean_parts[idx:])
    return cur


def resolve_windows_path(win_path, bottle_dir, base_dir=None, hint_path=None):
    """
    Convert a Windows path (drive-letter, %ENV% variable, or relative path)
    to a real Linux path inside bottle_dir/drive_c using case-insensitive resolution.
    Returns None if bottle_dir/drive_c does not exist or path is empty.
    """
    if not win_path or not bottle_dir:
        return None

    expanded = expand_windows_env_vars(_clean_str(win_path), bottle_dir, hint_path=hint_path)
    if not expanded:
        return None

    # Allow an already-Linux path if it resides on disk directly
    if expanded.startswith("/") and os.path.exists(expanded):
        return os.path.abspath(expanded)

    drive_c = os.path.join(bottle_dir, "drive_c")
    if not os.path.isdir(drive_c):
        return None

    # Normalize separators
    unix_like = expanded.replace("\\", "/")

    # Handle drive prefix (e.g. C:/..., Z:/...)
    drive_match = re.match(r"^([a-zA-Z]):[\\/]?(.*)$", unix_like)
    if drive_match:
        drive_letter = drive_match.group(1).lower()
        rest = drive_match.group(2)
        if drive_letter == "c":
            root = drive_c
        elif drive_letter == "z":
            root = "/"
        else:
            dos_link = os.path.join(bottle_dir, "dosdevices", f"{drive_letter}:")
            if os.path.exists(dos_link):
                root = os.path.realpath(dos_link)
            else:
                return None
        parts = [p for p in rest.split("/") if p]
        if not parts:
            return root
        resolved = resolve_case_insensitive_path(root, parts)
        win_low = win_path.lower()
        if (
            drive_letter == "c"
            and (not resolved or not os.path.exists(resolved))
            and parts[0].lower() == "program files"
            and ("%programfiles%" in win_low or "%commonprogramfiles%" in win_low)
        ):
            alt_parts = ["Program Files (x86)"] + parts[1:]
            alt_resolved = resolve_case_insensitive_path(root, alt_parts)
            if alt_resolved and os.path.exists(alt_resolved):
                return alt_resolved
        return resolved

    # Relative path (relative to base_dir / lnk directory / drive_c)
    rel_parts = [p for p in unix_like.lstrip("/").split("/") if p]
    if base_dir and os.path.isdir(base_dir):
        resolved = resolve_case_insensitive_path(base_dir, rel_parts)
        if resolved and os.path.exists(resolved):
            return resolved
    return resolve_case_insensitive_path(drive_c, rel_parts)


def split_icon_location_spec(icon_spec):
    """Split 'C:\\path\\app.exe,-128' into ('C:\\path\\app.exe', -128) or (spec, None)."""
    spec = _clean_str(icon_spec)
    if not spec:
        return "", None
    m = re.match(r"^(.*),\s*(-?\d+)\s*$", spec)
    if m:
        try:
            return _clean_str(m.group(1)), int(m.group(2))
        except ValueError:
            pass
    return spec, None


def parse_lnk(lnk_path, bottle_dir=None):
    """
    Pure-Python [MS-SHLLINK] .lnk binary parser.
    Reads 76-byte ShellLinkHeader, LinkFlags, LinkTargetIDList, LinkInfo
    (LocalBasePath / LocalBasePathUnicode), StringData (Name, RelativePath,
    WorkingDir, Arguments, IconLocation), ExtraData env blocks, and IconIndex.
    Returns dict on success or None if invalid/corrupt.
    """
    try:
        with open(lnk_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    if len(data) < 76:
        return None

    header_size = struct.unpack_from("<I", data, 0)[0]
    clsid = data[4:20]
    if header_size != 0x4C or clsid != LNK_CLSID:
        return None

    link_flags = struct.unpack_from("<I", data, 20)[0]
    icon_index = struct.unpack_from("<i", data, 56)[0]
    show_command = struct.unpack_from("<I", data, 60)[0]

    pos = 76
    total_len = len(data)

    # 1. LinkTargetIDList
    if link_flags & FLAG_HAS_ID_LIST:
        if pos + 2 > total_len:
            return None
        id_list_size = struct.unpack_from("<H", data, pos)[0]
        pos += 2 + id_list_size
        if pos > total_len:
            return None

    # 2. LinkInfo
    local_base_path = ""
    if link_flags & FLAG_HAS_LINK_INFO:
        if pos + 4 > total_len:
            return None
        li_size = struct.unpack_from("<I", data, pos)[0]
        if li_size < 28 or pos + li_size > total_len:
            return None

        li_hdr_size = struct.unpack_from("<I", data, pos + 4)[0]
        li_end = pos + li_size
        lb_off = struct.unpack_from("<I", data, pos + 16)[0]
        cps_off = struct.unpack_from("<I", data, pos + 24)[0]

        base_ansi = _read_c_str(data, pos + lb_off, li_end) if lb_off else ""
        suffix_ansi = _read_c_str(data, pos + cps_off, li_end) if cps_off else ""

        base_uni = ""
        suffix_uni = ""
        if li_hdr_size >= 0x24 and pos + 36 <= li_end:
            lb_uoff = struct.unpack_from("<I", data, pos + 28)[0]
            cps_uoff = struct.unpack_from("<I", data, pos + 32)[0]
            if lb_uoff:
                base_uni = _read_c_wstr(data, pos + lb_uoff, li_end)
            if cps_uoff:
                suffix_uni = _read_c_wstr(data, pos + cps_uoff, li_end)

        chosen_base = base_uni or base_ansi
        chosen_suffix = suffix_uni or suffix_ansi
        local_base_path = _join_win_path(chosen_base, chosen_suffix)
        pos = li_end

    # 3. StringData in mandatory MS-SHLLINK flag order
    is_unicode = bool(link_flags & FLAG_IS_UNICODE)
    string_fields = {}
    for flag_bit, field_name in (
        (FLAG_HAS_NAME, "description"),
        (FLAG_HAS_RELATIVE_PATH, "relative_path"),
        (FLAG_HAS_WORKING_DIR, "working_dir"),
        (FLAG_HAS_ARGUMENTS, "arguments"),
        (FLAG_HAS_ICON_LOCATION, "icon_location"),
    ):
        if link_flags & flag_bit:
            if pos + 2 > total_len:
                break
            count_chars = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            byte_len = count_chars * (2 if is_unicode else 1)
            if pos + byte_len > total_len:
                byte_len = max(0, total_len - pos)
            raw = data[pos : pos + byte_len]
            pos += byte_len
            encoding = "utf-16-le" if is_unicode else "cp1252"
            string_fields[field_name] = _clean_str(raw.decode(encoding, errors="replace"))
        else:
            string_fields[field_name] = ""

    # 4. ExtraData blocks (EnvironmentVariableDataBlock & IconEnvironmentDataBlock)
    env_target = ""
    env_icon = ""
    while pos + 4 <= total_len:
        block_size = struct.unpack_from("<I", data, pos)[0]
        if block_size < 4:
            break
        if pos + block_size > total_len or pos + 8 > total_len:
            break
        block_sig = struct.unpack_from("<I", data, pos + 4)[0]
        if block_sig in (SIG_ENV_VAR_DATA, SIG_ICON_ENV_DATA) and block_size >= 788:
            ansi_val = _read_c_str(data, pos + 8, pos + 268)
            uni_val = _read_c_wstr(data, pos + 268, pos + 788)
            best_val = uni_val or ansi_val
            if block_sig == SIG_ENV_VAR_DATA and not env_target:
                env_target = best_val
            elif block_sig == SIG_ICON_ENV_DATA and not env_icon:
                env_icon = best_val
        pos += block_size

    relative_path = string_fields["relative_path"]
    working_dir = string_fields["working_dir"]
    arguments = string_fields["arguments"]
    description = string_fields["description"]
    icon_loc_raw, inline_idx = split_icon_location_spec(
        string_fields["icon_location"] or env_icon
    )
    if inline_idx is not None:
        icon_index = inline_idx

    # Determine primary Windows target expression
    target_win = local_base_path or env_target
    if not target_win and relative_path:
        if working_dir and not re.match(r"^[a-zA-Z]:", relative_path):
            target_win = _join_win_path(working_dir, relative_path)
        else:
            target_win = relative_path

    # Resolve paths if bottle_dir is known or inferable
    effective_bottle = bottle_dir or _infer_bottle_dir(lnk_path)
    lnk_dir = os.path.dirname(os.path.abspath(lnk_path))

    resolved_working_dir = None
    if effective_bottle and working_dir:
        resolved_working_dir = resolve_windows_path(
            working_dir, effective_bottle, base_dir=lnk_dir, hint_path=lnk_path
        )

    resolved_target = None
    if effective_bottle:
        for candidate in (local_base_path, env_target, target_win):
            if not candidate:
                continue
            cand_res = resolve_windows_path(
                candidate,
                effective_bottle,
                base_dir=lnk_dir,
                hint_path=lnk_path,
            )
            if cand_res and os.path.isfile(cand_res):
                resolved_target = cand_res
                break
            if resolved_target is None and cand_res:
                resolved_target = cand_res

        if (not resolved_target or not os.path.isfile(resolved_target)) and relative_path:
            for base in (lnk_dir, resolved_working_dir):
                if not base:
                    continue
                rel_res = resolve_windows_path(
                    relative_path, effective_bottle, base_dir=base, hint_path=lnk_path
                )
                if rel_res and os.path.isfile(rel_res):
                    resolved_target = rel_res
                    break

    resolved_icon = None
    if effective_bottle and icon_loc_raw:
        exe_dir = os.path.dirname(resolved_target) if resolved_target else lnk_dir
        resolved_icon = resolve_windows_path(
            icon_loc_raw, effective_bottle, base_dir=exe_dir, hint_path=lnk_path
        )

    shortcut_name = os.path.splitext(os.path.basename(lnk_path))[0].strip()

    return {
        "lnk_path": lnk_path,
        "shortcut_name": shortcut_name,
        "description": description,
        "link_flags": link_flags,
        "show_command": show_command,
        "target_win": target_win,
        "local_base_path": local_base_path,
        "relative_path": relative_path,
        "working_dir_win": working_dir,
        "arguments": arguments,
        "icon_location_win": icon_loc_raw,
        "icon_index": icon_index,
        "resolved_target": resolved_target,
        "resolved_working_dir": resolved_working_dir,
        "resolved_icon_location": resolved_icon,
    }


def _extract_pe_icon_bytes(pe_path, icon_index=0):
    """
    Pure-Python PE32 / PE32+ resource parser extracting RT_GROUP_ICON + RT_ICON
    into a valid in-memory .ico binary stream. Returns bytes or None.
    """
    try:
        with open(pe_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    size = len(data)
    if size < 64 or data[:2] != b"MZ":
        return None

    e_lfanew = struct.unpack_from("<I", data, 60)[0]
    if e_lfanew + 24 > size or data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return None

    num_sections = struct.unpack_from("<H", data, e_lfanew + 6)[0]
    opt_size = struct.unpack_from("<H", data, e_lfanew + 20)[0]
    opt_off = e_lfanew + 24
    if opt_off + opt_size > size or opt_size < 96:
        return None

    magic = struct.unpack_from("<H", data, opt_off)[0]
    if magic == 0x10B:  # PE32
        dd_off = opt_off + 96
    elif magic == 0x20B:  # PE32+ (64-bit)
        dd_off = opt_off + 112
    else:
        return None

    if dd_off + 24 > opt_off + opt_size:
        return None

    num_rva = struct.unpack_from("<I", data, dd_off - 4)[0]
    if num_rva < 3:
        return None

    rsrc_rva, rsrc_sz = struct.unpack_from("<II", data, dd_off + 2 * 8)
    if rsrc_rva == 0 or rsrc_sz == 0:
        return None

    sec_table_off = opt_off + opt_size
    if sec_table_off + num_sections * 40 > size:
        return None

    sections = []
    for i in range(num_sections):
        so = sec_table_off + i * 40
        vsz, va, rsz, ra = struct.unpack_from("<IIII", data, so + 8)
        sections.append((va, vsz, ra, rsz))

    def rva_to_off(rva):
        for va, vsz, ra, rsz in sections:
            span = max(vsz, rsz)
            if va <= rva < va + span:
                off = ra + (rva - va)
                if 0 <= off < size:
                    return off
        return None

    rsrc_base = rva_to_off(rsrc_rva)
    if rsrc_base is None:
        return None

    def read_dir(dir_off):
        if dir_off is None or dir_off + 16 > size:
            return []
        n_named, n_id = struct.unpack_from("<HH", data, dir_off + 12)
        entries = []
        max_entries = min(n_named + n_id, 4096)
        for i in range(max_entries):
            e_off = dir_off + 16 + i * 8
            if e_off + 8 > size:
                break
            name_or_id, off_data = struct.unpack_from("<II", data, e_off)
            entries.append((name_or_id, off_data))
        return entries

    def read_data_blob(entry_off):
        if entry_off < 0 or entry_off + 16 > size:
            return None
        d_rva, d_sz, _, _ = struct.unpack_from("<IIII", data, entry_off)
        d_off = rva_to_off(d_rva)
        if d_off is None or d_sz == 0 or d_off + d_sz > size:
            return None
        return data[d_off : d_off + d_sz]

    def get_lang_blobs(leaf_or_dir_off):
        """Return list of (lang_id, blob_bytes) for a resource node."""
        blobs = []
        if leaf_or_dir_off & 0x80000000:
            sub = rsrc_base + (leaf_or_dir_off & 0x7FFFFFFF)
            for lid, loff in read_dir(sub):
                if loff & 0x80000000:
                    continue
                blob = read_data_blob(rsrc_base + loff)
                if blob:
                    blobs.append((lid & 0xFFFF, blob))
        else:
            blob = read_data_blob(rsrc_base + leaf_or_dir_off)
            if blob:
                blobs.append((0, blob))
        return blobs

    root_entries = read_dir(rsrc_base)
    icon_dir_off = None
    group_dir_off = None
    for tid, toff in root_entries:
        if tid & 0x80000000:
            continue
        if tid == RT_ICON and (toff & 0x80000000):
            icon_dir_off = rsrc_base + (toff & 0x7FFFFFFF)
        elif tid == RT_GROUP_ICON and (toff & 0x80000000):
            group_dir_off = rsrc_base + (toff & 0x7FFFFFFF)

    if icon_dir_off is None:
        return None

    # Map RT_ICON id -> {lang_id: blob}
    rt_icons = {}
    for rid, roff in read_dir(icon_dir_off):
        if rid & 0x80000000:
            continue
        icon_id = rid & 0xFFFF
        blobs = get_lang_blobs(roff)
        if blobs:
            rt_icons[icon_id] = dict(blobs)

    if not rt_icons:
        return None

    def pick_icon_blob(icon_id, preferred_lang):
        lang_map = rt_icons.get(icon_id)
        if not lang_map:
            return None
        if preferred_lang in lang_map:
            return lang_map[preferred_lang]
        return next(iter(lang_map.values()))

    group_blob = None
    group_lang = 0
    if group_dir_off is not None:
        groups = read_dir(group_dir_off)
        if groups:
            chosen = None
            if icon_index is not None and icon_index < 0:
                target_id = -icon_index
                for rid, roff in groups:
                    if not (rid & 0x80000000) and (rid & 0xFFFF) == target_id:
                        chosen = roff
                        break
            if chosen is None:
                idx = icon_index if (icon_index is not None and 0 <= icon_index < len(groups)) else 0
                chosen = groups[idx][1]
            blobs = get_lang_blobs(chosen)
            if blobs:
                group_lang, group_blob = blobs[0]

    ico_entries = []
    if group_blob and len(group_blob) >= 6:
        _, g_type, g_count = struct.unpack_from("<HHH", group_blob, 0)
        if g_type in (1, 2) and g_count > 0:
            for i in range(g_count):
                off = 6 + i * 14
                if off + 14 > len(group_blob):
                    break
                bw, bh, cc, _, planes, bpp, _, nid = struct.unpack_from(
                    "<BBBBHHIH", group_blob, off
                )
                blob = pick_icon_blob(nid, group_lang)
                if not blob:
                    continue
                w = bw or 256
                h = bh or 256
                ico_entries.append((w * h, bpp, bw, bh, cc, planes, bpp, blob))

    # Fallback when RT_GROUP_ICON is missing/broken: wrap the largest RT_ICON
    if not ico_entries:
        best_blob = max(
            (b for lm in rt_icons.values() for b in lm.values()),
            key=len,
            default=None,
        )
        if best_blob:
            if best_blob.startswith(b"\x89PNG\r\n\x1a\n"):
                ico_entries.append((256 * 256, 32, 0, 0, 0, 1, 32, best_blob))
            elif len(best_blob) >= 40:
                dib_w, dib_h = struct.unpack_from("<ii", best_blob, 4)
                dib_bpp = struct.unpack_from("<H", best_blob, 14)[0]
                actual_h = abs(dib_h) // 2
                bw = dib_w if 0 < dib_w < 256 else 0
                bh = actual_h if 0 < actual_h < 256 else 0
                ico_entries.append((dib_w * actual_h, dib_bpp, bw, bh, 0, 1, dib_bpp, best_blob))

    if not ico_entries:
        return None

    # Deduplicate by (bw, bh) keeping highest bpp/blob, and put largest resolution first
    best_by_dim = {}
    for item in ico_entries:
        dim = (item[2], item[3])
        prev = best_by_dim.get(dim)
        if prev is None or (item[1], len(item[7])) > (prev[1], len(prev[7])):
            best_by_dim[dim] = item

    ordered = sorted(best_by_dim.values(), key=lambda x: (x[0], x[1], len(x[7])), reverse=True)
    header = bytearray(struct.pack("<HHH", 0, 1, len(ordered)))
    body = bytearray()
    offset = 6 + len(ordered) * 16
    for _, _, bw, bh, cc, planes, bpp, blob in ordered:
        header.extend(
            struct.pack("<BBBBHHII", bw, bh, cc, 0, planes, bpp, len(blob), offset)
        )
        body.extend(blob)
        offset += len(blob)

    return bytes(header + body)


def _save_best_pillow_icon(im, out_png_path):
    """Select the highest-resolution frame from an opened PIL Image and write PNG atomically."""
    chosen = im
    if hasattr(im, "ico") and im.ico:
        try:
            sizes = sorted(
                im.ico.sizes(),
                key=lambda s: (s[0] * s[1], s[0]),
                reverse=True,
            )
            if sizes:
                chosen = im.ico.getimage(sizes[0])
        except Exception:
            chosen = im

    rgba = chosen.convert("RGBA")
    if rgba.width <= 0 or rgba.height <= 0:
        return False

    out_dir = os.path.dirname(os.path.abspath(out_png_path))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".icon-", suffix=".png", dir=out_dir)
    os.close(fd)
    try:
        rgba.save(tmp_path, format="PNG")
        if os.path.getsize(tmp_path) <= 0:
            os.remove(tmp_path)
            return False
        os.replace(tmp_path, out_png_path)
        return True
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def _extract_via_icoutils(pe_path, out_png_path):
    """Fallback extraction via wrestool + icotool if installed on system."""
    wrestool = shutil.which("wrestool")
    icotool = shutil.which("icotool")
    if not wrestool or not icotool or not os.path.isfile(pe_path):
        return False

    with tempfile.TemporaryDirectory(prefix="sadeem-ico-") as tmpdir:
        ico_path = os.path.join(tmpdir, "icon.ico")
        res = subprocess.run(
            [wrestool, "-x", "-t", "14", "-o", ico_path, pe_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        candidates = glob.glob(os.path.join(tmpdir, "*.ico"))
        if res.returncode != 0 or not candidates:
            return False

        # Try Pillow on extracted .ico first, then icotool -> PNGs
        for cand in candidates:
            try:
                with Image.open(cand) as im:
                    if _save_best_pillow_icon(im, out_png_path):
                        return True
            except Exception:
                pass

        subprocess.run(
            [icotool, "-x", "-o", tmpdir, *candidates],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        pngs = glob.glob(os.path.join(tmpdir, "*.png"))
        best_png = None
        best_pixels = -1
        for p in pngs:
            try:
                with Image.open(p) as im:
                    pixels = im.width * im.height
                    if pixels > best_pixels:
                        best_pixels = pixels
                        best_png = p
            except Exception:
                continue
        if best_png:
            with Image.open(best_png) as im:
                return _save_best_pillow_icon(im, out_png_path)
    return False


def _extract_from_single_source(src_path, icon_idx, out_png_path):
    if not src_path or not os.path.isfile(src_path):
        return False

    ext = os.path.splitext(src_path)[1].lower()
    # Direct image / .ico files
    if ext in (".ico", ".png", ".bmp", ".jpg", ".jpeg", ".gif"):
        try:
            with Image.open(src_path) as im:
                if _save_best_pillow_icon(im, out_png_path):
                    return True
        except Exception:
            pass

    # Pure-Python PE resource extraction (.exe / .dll / .ocx / .cpl / unknown)
    ico_bytes = _extract_pe_icon_bytes(src_path, icon_index=icon_idx)
    if ico_bytes:
        try:
            with Image.open(io.BytesIO(ico_bytes)) as im:
                if _save_best_pillow_icon(im, out_png_path):
                    return True
        except Exception:
            pass

    # Secondary Pillow attempt (in case extensionless .ico)
    if ext not in (".exe", ".dll", ".bat", ".cmd"):
        try:
            with Image.open(src_path) as im:
                if _save_best_pillow_icon(im, out_png_path):
                    return True
        except Exception:
            pass

    # Optional external fallback (wrestool + icotool)
    return _extract_via_icoutils(src_path, out_png_path)


def extract_windows_icon(target_exe, icon_loc, icon_idx, out_png_path):
    """
    Extract best icon for a Windows shortcut into out_png_path (RGBA PNG).
    Supports .ico, image files, and PE32/PE32+ (.exe/.dll) resources via pure Python + Pillow,
    with optional wrestool/icotool fallback. Returns True on success, False otherwise.
    """
    idx = 0 if icon_idx is None else icon_idx

    if icon_loc and os.path.isfile(icon_loc):
        if _extract_from_single_source(icon_loc, idx, out_png_path):
            return True

    if target_exe and os.path.isfile(target_exe):
        # If icon_loc differed from target_exe and failed, fallback to primary group 0 on target_exe
        target_idx = idx if (not icon_loc or os.path.abspath(icon_loc) == os.path.abspath(target_exe)) else 0
        if _extract_from_single_source(target_exe, target_idx, out_png_path):
            return True

    return False


def _is_junk_text(text):
    if not text:
        return False
    low = text.lower()
    if any(tok in low for tok in JUNK_SUBSTRINGS):
        return True
    normalized = re.sub(r"[_.\-]+", " ", low)
    if JUNK_WORD_RE.search(normalized):
        return True
    return False


def is_junk_shortcut(parsed):
    """Filter uninstallers, help docs, readmes, web links, and non-executable targets."""
    target = parsed.get("resolved_target") or ""
    if not target or not os.path.isfile(target):
        return True

    ext = os.path.splitext(target)[1].lower()
    if ext not in SUPPORTED_TARGET_EXTS:
        return True

    target_base = os.path.basename(target).lower()
    if target_base in JUNK_EXECUTABLES:
        return True

    args_low = (parsed.get("arguments") or "").lower()
    if target_base == "msiexec.exe" and ("/x" in args_low or "/uninstall" in args_low):
        return True

    for text in (
        parsed.get("shortcut_name"),
        parsed.get("description"),
        os.path.basename(os.path.dirname(target)),
        target_base,
    ):
        if _is_junk_text(text):
            return True

    return False


def _get_shortcut_roots(bottle_dir):
    """Return deduplicated list of (root_path, is_desktop, recursive) tuples in drive_c."""
    drive_c = os.path.join(bottle_dir, "drive_c")
    if not os.path.isdir(drive_c):
        return []

    search_roots = []
    seen_roots = set()

    def _add_root(path, is_desktop, recursive):
        if not path or not os.path.isdir(path):
            return
        real = os.path.realpath(path)
        if real in seen_roots:
            return
        seen_roots.add(real)
        search_roots.append((path, is_desktop, recursive))

    # Desktop roots
    _add_root(
        resolve_case_insensitive_path(drive_c, ["users", "Public", "Desktop"]),
        is_desktop=True,
        recursive=True,
    )
    users_dir = resolve_case_insensitive_path(drive_c, ["users"])
    if users_dir and os.path.isdir(users_dir):
        for entry in sorted(os.listdir(users_dir)):
            if entry.lower() in ("public", "default", "all users"):
                continue
            udir = os.path.join(users_dir, entry)
            if not os.path.isdir(udir):
                continue
            _add_root(
                resolve_case_insensitive_path(udir, ["Desktop"]),
                is_desktop=True,
                recursive=True,
            )

    # Start Menu roots (recursive)
    _add_root(
        resolve_case_insensitive_path(
            drive_c, ["ProgramData", "Microsoft", "Windows", "Start Menu", "Programs"]
        ),
        is_desktop=False,
        recursive=True,
    )
    if users_dir and os.path.isdir(users_dir):
        for entry in sorted(os.listdir(users_dir)):
            if entry.lower() in ("public", "default", "all users"):
                continue
            udir = os.path.join(users_dir, entry)
            if not os.path.isdir(udir):
                continue
            _add_root(
                resolve_case_insensitive_path(
                    udir, ["AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"]
                ),
                is_desktop=False,
                recursive=True,
            )
    return search_roots


def find_shortcut_files(bottle_dir):
    """
    Collect candidate .lnk shortcuts across Desktop and Start Menu roots in drive_c.
    Returns list of tuples: (lnk_path, is_desktop).
    """
    search_roots = _get_shortcut_roots(bottle_dir)
    if not search_roots:
        return []

    collected = []
    seen_lnks = set()
    for root_dir, is_desktop, recursive in search_roots:
        if recursive:
            for cur_root, dirs, files in os.walk(root_dir):
                dirs.sort()
                for fn in sorted(files):
                    if fn.lower().endswith(".lnk"):
                        full = os.path.join(cur_root, fn)
                        real = os.path.realpath(full)
                        if real not in seen_lnks:
                            seen_lnks.add(real)
                            collected.append((full, is_desktop))
        else:
            for fn in sorted(os.listdir(root_dir)):
                if fn.lower().endswith(".lnk"):
                    full = os.path.join(root_dir, fn)
                    if os.path.isfile(full):
                        real = os.path.realpath(full)
                        if real not in seen_lnks:
                            seen_lnks.add(real)
                            collected.append((full, is_desktop))

    # Desktop shortcuts sorted before Start Menu for deterministic priority
    collected.sort(key=lambda item: (0 if item[1] else 1, item[0].lower()))
    return collected


def _desktop_exec_quote(arg):
    """Quote a single Exec argument strictly according to the FreeDesktop Desktop Entry Spec."""
    s = str(arg).replace("\n", " ").replace("\r", " ")
    # % must always be doubled in Exec values
    s_escaped_pct = s.replace("%", "%%")
    needs_quotes = (
        not s_escaped_pct
        or any(ch in s_escaped_pct for ch in ' \t"\'\\><~|&;$*?#()`')
    )
    if not needs_quotes:
        return s_escaped_pct
    escaped = (
        s_escaped_pct
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def _desktop_string_escape(val):
    """Escape a non-Exec Desktop Entry string value cleanly."""
    return (
        str(val or "")
        .replace("\\", "\\\\")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .strip()
    )


def _infer_category(entry_name, parsed):
    haystack = " ".join(
        filter(
            None,
            [
                entry_name,
                parsed.get("description", ""),
                parsed.get("resolved_target", ""),
                parsed.get("lnk_path", ""),
            ],
        )
    )
    cleaned = re.sub(r"[_.\-\\/]+", " ", haystack)
    if GAME_HINT_RE.search(cleaned):
        return "Game;"
    return "Utility;"


def _stable_entry_id(target_path, args_norm, bottle_dir):
    try:
        rel_or_abs = os.path.relpath(os.path.realpath(target_path), os.path.realpath(bottle_dir))
    except Exception:
        rel_or_abs = os.path.realpath(target_path)
    key = f"{rel_or_abs.lower()}\0{args_norm}".encode("utf-8", errors="replace")
    return hashlib.sha256(key).hexdigest()[:12]


def clean_shortcut_name(raw_name):
    """
    Strip common Windows installer prefixes ('Play ', 'Launch ', 'Start ', 'Run ')
    and trailing suffixes ('- Shortcut', '.exe') while keeping full words like
    'PlayStation' or standalone words like 'Play' intact.
    """
    s = " ".join(str(raw_name or "").split()).strip()
    if not s:
        return ""

    candidate = re.sub(r"\s*[-–—]?\s*shortcut$", "", s, flags=re.IGNORECASE).strip()
    candidate = re.sub(r"\.exe$", "", candidate, flags=re.IGNORECASE).strip()

    prefix_match = re.match(r"^(?:play|launch|start|run)\s+(.+)$", candidate, flags=re.IGNORECASE)
    if prefix_match and prefix_match.group(1).strip():
        candidate = prefix_match.group(1).strip()

    candidate = " ".join(candidate.split()).strip()
    return candidate or s


def _make_icon_slug(name, stable_id):
    ascii_part = re.sub(r"[^a-zA-Z0-9._-]+", "-", name or "").strip("-").lower()
    if len(ascii_part) > 40:
        ascii_part = ascii_part[:40].rstrip("-")
    if ascii_part:
        return f"{ascii_part}-{stable_id}"
    return f"win-{stable_id}"


def _build_desktop_content(name, comment, target_exe, args_norm, icon_value, category):
    exec_parts = [
        _desktop_exec_quote(HANDLER_EXECUTABLE),
        "--launch-installed",
        _desktop_exec_quote(target_exe),
    ]
    if args_norm:
        exec_parts.extend(["--args", _desktop_exec_quote(args_norm)])

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={_desktop_string_escape(name)}",
        f"Comment={_desktop_string_escape(comment or name)}",
        f"Exec={' '.join(exec_parts)}",
        f"Icon={_desktop_string_escape(icon_value or FALLBACK_ICON_NAME)}",
        "Terminal=false",
        "StartupNotify=true",
        f"Categories={category}",
        f"{MANAGED_KEY}=true",
        f"X-Sadeem-Windows-Target={_desktop_string_escape(target_exe)}",
    ]
    return "\n".join(lines) + "\n"


def _is_managed_desktop_file(desktop_path):
    try:
        with open(desktop_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip() == f"{MANAGED_KEY}=true":
                    return True
    except OSError:
        return False
    return False


def sync_bottle_shortcuts(
    bottle_dir=DEFAULT_BOTTLE_DIR,
    applications_dir=None,
    icons_dir=None,
    run_update_db=True,
):
    """
    Scan Windows shortcuts inside bottle_dir, extract icons, create/update managed
    .desktop files in applications_dir, remove stale managed entries, and update
    the desktop database when changes occur.

    Returns dict: {"added": [...], "updated": [...], "removed": [...], "active": [...]}.
    """
    apps_dir = os.path.abspath(applications_dir or DEFAULT_APPLICATIONS_DIR)
    ico_dir = os.path.abspath(icons_dir or DEFAULT_ICONS_DIR)
    os.makedirs(apps_dir, exist_ok=True)
    os.makedirs(ico_dir, exist_ok=True)

    dedup = {}  # (real_target_lower, args_norm) -> candidate record
    if bottle_dir and os.path.isdir(os.path.join(bottle_dir, "drive_c")):
        for lnk_path, is_desktop in find_shortcut_files(bottle_dir):
            parsed = parse_lnk(lnk_path, bottle_dir=bottle_dir)
            if not parsed or is_junk_shortcut(parsed):
                continue

            resolved_target = os.path.abspath(parsed["resolved_target"])
            args_norm = " ".join((parsed.get("arguments") or "").split())
            dedup_key = (os.path.realpath(resolved_target).lower(), args_norm)

            existing = dedup.get(dedup_key)
            if existing is None or (is_desktop and not existing["is_desktop"]):
                dedup[dedup_key] = {
                    "parsed": parsed,
                    "is_desktop": is_desktop,
                    "target_exe": resolved_target,
                    "args_norm": args_norm,
                }

    added = []
    updated = []
    active = []
    expected_desktop_names = set()
    used_icons = set()
    changed = False

    for item in dedup.values():
        parsed = item["parsed"]
        target_exe = item["target_exe"]
        args_norm = item["args_norm"]
        raw_name = parsed["shortcut_name"] or os.path.splitext(os.path.basename(target_exe))[0]
        name = clean_shortcut_name(raw_name) or raw_name
        comment = parsed.get("description") or name
        stable_id = _stable_entry_id(target_exe, args_norm, bottle_dir)

        desktop_filename = f"{MANAGED_DESKTOP_PREFIX}{stable_id}.desktop"
        desktop_path = os.path.join(apps_dir, desktop_filename)
        expected_desktop_names.add(desktop_filename)

        icon_slug = _make_icon_slug(name, stable_id)
        out_png_path = os.path.join(ico_dir, f"{icon_slug}.png")

        extracted_ok = extract_windows_icon(
            target_exe=target_exe,
            icon_loc=parsed.get("resolved_icon_location"),
            icon_idx=parsed.get("icon_index", 0),
            out_png_path=out_png_path,
        )
        if extracted_ok and os.path.isfile(out_png_path):
            icon_value = out_png_path
            used_icons.add(os.path.abspath(out_png_path))
        else:
            icon_value = FALLBACK_ICON_NAME

        category = _infer_category(name, parsed)
        content = _build_desktop_content(
            name=name,
            comment=comment,
            target_exe=target_exe,
            args_norm=args_norm,
            icon_value=icon_value,
            category=category,
        )

        existed_before = os.path.isfile(desktop_path)
        prev_content = None
        if existed_before:
            try:
                with open(desktop_path, "r", encoding="utf-8", errors="replace") as f:
                    prev_content = f.read()
            except OSError:
                prev_content = None

        if prev_content != content:
            fd, tmp_desktop = tempfile.mkstemp(prefix=".desktop-", suffix=".tmp", dir=apps_dir)
            os.close(fd)
            try:
                with open(tmp_desktop, "w", encoding="utf-8") as f:
                    f.write(content)
                os.chmod(tmp_desktop, 0o644)
                os.replace(tmp_desktop, desktop_path)
                changed = True
            except Exception:
                if os.path.exists(tmp_desktop):
                    try:
                        os.remove(tmp_desktop)
                    except OSError:
                        pass
                raise

        entry_info = {
            "name": name,
            "desktop_path": desktop_path,
            "icon": icon_value,
            "target": target_exe,
            "args": args_norm,
            "category": category,
        }
        active.append(entry_info)
        if not existed_before:
            added.append(entry_info)
        elif prev_content != content:
            updated.append(entry_info)

    # Clean stale Sadeem-managed desktop entries only
    removed = []
    for fname in sorted(os.listdir(apps_dir)):
        if not (fname.startswith(MANAGED_DESKTOP_PREFIX) and fname.endswith(".desktop")):
            continue
        if fname in expected_desktop_names:
            continue
        fpath = os.path.join(apps_dir, fname)
        if os.path.isfile(fpath) and _is_managed_desktop_file(fpath):
            try:
                os.remove(fpath)
                removed.append(fpath)
                changed = True
            except OSError:
                pass

    # Clean orphaned extracted icons
    for iname in sorted(os.listdir(ico_dir)):
        if not iname.lower().endswith(".png"):
            continue
        ipath = os.path.abspath(os.path.join(ico_dir, iname))
        if ipath not in used_icons and os.path.isfile(ipath):
            try:
                os.remove(ipath)
            except OSError:
                pass

    if changed and run_update_db:
        updater = shutil.which("update-desktop-database")
        if updater:
            try:
                subprocess.run(
                    [updater, apps_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            except Exception:
                pass

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "active": active,
    }


def get_shortcuts_fingerprint(bottle_dir=DEFAULT_BOTTLE_DIR):
    """Return an immutable snapshot of shortcut files and mtimes/sizes for change polling."""
    if not bottle_dir or not os.path.isdir(os.path.join(bottle_dir, "drive_c")):
        return ()
    entries = []
    for lnk_path, _ in find_shortcut_files(bottle_dir):
        try:
            st = os.stat(lnk_path)
            entries.append((lnk_path, st.st_mtime_ns, st.st_size))
        except OSError:
            entries.append((lnk_path, -1, -1))
    return tuple(entries)

