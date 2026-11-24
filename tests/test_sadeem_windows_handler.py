#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive Test Suite for Sadeem Windows App Runner & Shortcut Synchronizer.
Tests:
1. Pure-Python [MS-SHLLINK] .lnk binary parser (Unicode, spaces, Arguments, WorkingDir,
   IconLocation, IconIndex, %ENV% expansion, RelativePath, case-insensitive bottle paths,
   and read-only verification against real Play Generals Zero Hour.lnk if present).
2. Icon extractor from multi-size .ico, synthetic PE32 (32-bit) & PE32+ (64-bit) executables
   including negative resource ID selection, plus real Launcher.exe if present.
3. Shortcut filtering, desktop-preferred deduplication, distinct-arg preservation, XDG Exec
   escaping (GLib.shell_parse_argv compatibility), and safe cleanup of stale managed .desktop files.
4. Runner window close behavior (_launched_ok=True skips terminate(), manual cancel calls terminate()),
   --sync-watch launcher invocation, flock single-instance lock, CLI parsing, and Arabic notification text.
"""

import importlib.machinery
import importlib.util
import io
import os
import stat
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from PIL import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYNC_DIR = os.path.join(REPO_ROOT, "files/system/usr/share/sadeem-windows")
HANDLER_PATH = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-windows-exe-handler")

if SYNC_DIR not in sys.path:
    sys.path.insert(0, SYNC_DIR)

import shortcut_sync  # noqa: E402

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

Adw.init()


def _load_handler_module():
    spec = importlib.util.spec_from_loader(
        "sadeem_windows_exe_handler",
        importlib.machinery.SourceFileLoader("sadeem_windows_exe_handler", HANDLER_PATH),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_png_bytes(size, rgba_color=(200, 30, 60, 255)):
    buf = io.BytesIO()
    img = Image.new("RGBA", (size, size), rgba_color)
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_test_ico(sizes=(16, 64)):
    payloads = [(s, _make_png_bytes(s, (30 * i % 250, 90, 180, 255))) for i, s in enumerate(sizes, 1)]
    cnt = len(payloads)
    header = bytearray(struct.pack("<HHH", 0, 1, cnt))
    body = bytearray()
    offset = 6 + cnt * 16
    for s, blob in payloads:
        bw = s if s < 256 else 0
        bh = s if s < 256 else 0
        header.extend(struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32, len(blob), offset))
        body.extend(blob)
        offset += len(blob)
    return bytes(header + body)


def _build_test_lnk(
    local_base_path="",
    name="",
    relative_path="",
    working_dir="",
    arguments="",
    icon_location="",
    icon_index=0,
    env_target="",
    env_icon="",
    unicode_strings=True,
    include_id_list=True,
    trailing_nul=False,
):
    flags = 0
    if include_id_list:
        flags |= shortcut_sync.FLAG_HAS_ID_LIST
    if local_base_path:
        flags |= shortcut_sync.FLAG_HAS_LINK_INFO
    if name:
        flags |= shortcut_sync.FLAG_HAS_NAME
    if relative_path:
        flags |= shortcut_sync.FLAG_HAS_RELATIVE_PATH
    if working_dir:
        flags |= shortcut_sync.FLAG_HAS_WORKING_DIR
    if arguments:
        flags |= shortcut_sync.FLAG_HAS_ARGUMENTS
    if icon_location:
        flags |= shortcut_sync.FLAG_HAS_ICON_LOCATION
    if unicode_strings:
        flags |= shortcut_sync.FLAG_IS_UNICODE

    header = bytearray(76)
    struct.pack_into("<I", header, 0, 0x4C)
    header[4:20] = shortcut_sync.LNK_CLSID
    struct.pack_into("<I", header, 20, flags)
    struct.pack_into("<i", header, 56, icon_index)
    struct.pack_into("<I", header, 60, 1)

    out = bytearray(header)

    if include_id_list:
        dummy_id_list = b"\x14\x00" + (b"\xAA" * 18) + b"\x00\x00"
        out.extend(struct.pack("<H", len(dummy_id_list)))
        out.extend(dummy_id_list)

    if local_base_path:
        li_hdr_size = 0x24
        vol_off = li_hdr_size
        vol_bytes = b"\x10\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x10\x00\x00\x00"
        lb_ansi_off = vol_off + len(vol_bytes)
        lb_ansi = local_base_path.encode("cp1252", errors="replace") + b"\x00"
        cps_off = lb_ansi_off + len(lb_ansi)
        cps_ansi = b"\x00"
        lb_uoff = cps_off + len(cps_ansi)
        lb_uni = local_base_path.encode("utf-16-le") + b"\x00\x00"
        cps_uoff = lb_uoff + len(lb_uni)
        cps_uni = b"\x00\x00"
        li_size = cps_uoff + len(cps_uni)

        out.extend(
            struct.pack(
                "<IIIIIIIII",
                li_size,
                li_hdr_size,
                1,
                vol_off,
                lb_ansi_off,
                0,
                cps_off,
                lb_uoff,
                cps_uoff,
            )
        )
        out.extend(vol_bytes + lb_ansi + cps_ansi + lb_uni + cps_uni)

    for flag_bit, val in (
        (shortcut_sync.FLAG_HAS_NAME, name),
        (shortcut_sync.FLAG_HAS_RELATIVE_PATH, relative_path),
        (shortcut_sync.FLAG_HAS_WORKING_DIR, working_dir),
        (shortcut_sync.FLAG_HAS_ARGUMENTS, arguments),
        (shortcut_sync.FLAG_HAS_ICON_LOCATION, icon_location),
    ):
        if flags & flag_bit:
            txt = val + ("\x00" if trailing_nul else "")
            enc = txt.encode("utf-16-le" if unicode_strings else "cp1252")
            out.extend(struct.pack("<H", len(txt)))
            out.extend(enc)

    for sig, val in (
        (shortcut_sync.SIG_ENV_VAR_DATA, env_target),
        (shortcut_sync.SIG_ICON_ENV_DATA, env_icon),
    ):
        if val:
            blk = bytearray(788)
            struct.pack_into("<II", blk, 0, 788, sig)
            ansi_b = val.encode("cp1252", errors="replace")[:259]
            blk[8 : 8 + len(ansi_b)] = ansi_b
            uni_b = val.encode("utf-16-le")[:518]
            blk[268 : 268 + len(uni_b)] = uni_b
            out.extend(blk)

    out.extend(struct.pack("<I", 0))
    return bytes(out)


def _build_test_pe_with_icon(is_pe32_plus=False, icon_id=1, group_id=105, png_size=48):
    """Build a minimal valid PE32 or PE32+ binary containing RT_ICON and RT_GROUP_ICON."""
    png_blob = _make_png_bytes(png_size, (120, 40, 180, 255))
    grp_blob = bytearray(struct.pack("<HHH", 0, 1, 1))
    bw = png_size if png_size < 256 else 0
    grp_blob.extend(struct.pack("<BBBBHHIH", bw, bw, 0, 0, 1, 32, len(png_blob), icon_id))

    rsrc_rva = 0x2000
    rsrc_file_off = 0x400

    # Layout inside .rsrc (offsets relative to rsrc_base):
    # 0x000: Root Dir (16 + 2*8 = 32 bytes -> ends 0x020)
    # 0x020: Type 3 (RT_ICON) Dir (16 + 8 = 24 bytes -> ends 0x038)
    # 0x038: Type 3 Lang Dir (16 + 8 = 24 bytes -> ends 0x050)
    # 0x050: Type 14 (RT_GROUP_ICON) Dir (16 + 8 = 24 bytes -> ends 0x068)
    # 0x068: Type 14 Lang Dir (16 + 8 = 24 bytes -> ends 0x080)
    # 0x080: DataEntry for icon (16 bytes -> ends 0x090)
    # 0x090: DataEntry for group (16 bytes -> ends 0x0A0)
    # 0x0A0: icon blob + group blob
    rsrc = bytearray(0x0A0)
    struct.pack_into("<IIHHHH", rsrc, 0x000, 0, 0, 0, 0, 0, 2)
    struct.pack_into("<II", rsrc, 0x010, shortcut_sync.RT_ICON, 0x80000000 | 0x020)
    struct.pack_into("<II", rsrc, 0x018, shortcut_sync.RT_GROUP_ICON, 0x80000000 | 0x050)

    # RT_ICON dir -> id entry -> lang dir -> data entry
    struct.pack_into("<IIHHHH", rsrc, 0x020, 0, 0, 0, 0, 0, 1)
    struct.pack_into("<II", rsrc, 0x030, icon_id, 0x80000000 | 0x038)
    struct.pack_into("<IIHHHH", rsrc, 0x038, 0, 0, 0, 0, 0, 1)
    struct.pack_into("<II", rsrc, 0x048, 1033, 0x080)

    # RT_GROUP_ICON dir -> id entry -> lang dir -> data entry
    struct.pack_into("<IIHHHH", rsrc, 0x050, 0, 0, 0, 0, 0, 1)
    struct.pack_into("<II", rsrc, 0x060, group_id, 0x80000000 | 0x068)
    struct.pack_into("<IIHHHH", rsrc, 0x068, 0, 0, 0, 0, 0, 1)
    struct.pack_into("<II", rsrc, 0x078, 1033, 0x090)

    icon_blob_rva = rsrc_rva + len(rsrc)
    rsrc.extend(png_blob)
    grp_blob_rva = rsrc_rva + len(rsrc)
    rsrc.extend(grp_blob)

    struct.pack_into("<IIII", rsrc, 0x080, icon_blob_rva, len(png_blob), 0, 0)
    struct.pack_into("<IIII", rsrc, 0x090, grp_blob_rva, len(grp_blob), 0, 0)

    opt_size = 240 if is_pe32_plus else 224
    dd_off_in_opt = 112 if is_pe32_plus else 96
    magic = 0x20B if is_pe32_plus else 0x10B

    headers = bytearray(rsrc_file_off)
    headers[:2] = b"MZ"
    e_lfanew = 0x80
    struct.pack_into("<I", headers, 60, e_lfanew)
    headers[e_lfanew : e_lfanew + 4] = b"PE\x00\x00"
    machine = 0x8664 if is_pe32_plus else 0x014C
    struct.pack_into("<HHIIIHH", headers, e_lfanew + 4, machine, 1, 0, 0, 0, opt_size, 0x0002)

    opt_off = e_lfanew + 24
    struct.pack_into("<H", headers, opt_off, magic)
    struct.pack_into("<I", headers, opt_off + dd_off_in_opt - 4, 16)
    struct.pack_into("<II", headers, opt_off + dd_off_in_opt + 2 * 8, rsrc_rva, len(rsrc))

    sec_off = opt_off + opt_size
    headers[sec_off : sec_off + 8] = b".rsrc\x00\x00\x00"
    struct.pack_into(
        "<IIIIIIHHI",
        headers,
        sec_off + 8,
        len(rsrc),
        rsrc_rva,
        len(rsrc),
        rsrc_file_off,
        0,
        0,
        0,
        0,
        0x40000040,
    )

    return bytes(headers + rsrc)


class TestSadeemWindowsSyncAndHandler(unittest.TestCase):
    def test_lnk_parser_unicode_env_and_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            bottle = os.path.join(tmp, "Sadeem-Windows")
            exe_dir = os.path.join(bottle, "drive_c", "Program Files (x86)", "My Space Game")
            desk_dir = os.path.join(bottle, "drive_c", "users", "Public", "Desktop")
            os.makedirs(exe_dir, exist_ok=True)
            os.makedirs(desk_dir, exist_ok=True)

            real_exe = os.path.join(exe_dir, "LaunchGame.exe")
            with open(real_exe, "wb") as f:
                f.write(b"MZ" + b"\x00" * 64)

            real_ico = os.path.join(exe_dir, "game.ico")
            with open(real_ico, "wb") as f:
                f.write(_build_test_ico((16, 48)))

            # Intentional mismatched case + trailing NULs like Wine creates
            lnk_path = os.path.join(desk_dir, "My Game.lnk")
            lnk_bytes = _build_test_lnk(
                local_base_path="c:\\program files (x86)\\MY SPACE GAME\\launchgame.exe",
                name="Play My Space Game",
                working_dir="C:\\PROGRAM FILES (X86)\\My Space Game",
                arguments='-quickstart -profile="Player One"',
                icon_location="C:\\Program Files (x86)\\my space game\\GAME.ICO",
                icon_index=2,
                unicode_strings=True,
                trailing_nul=True,
            )
            with open(lnk_path, "wb") as f:
                f.write(lnk_bytes)

            parsed = shortcut_sync.parse_lnk(lnk_path, bottle_dir=bottle)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["shortcut_name"], "My Game")
            self.assertEqual(parsed["description"], "Play My Space Game")
            self.assertEqual(parsed["arguments"], '-quickstart -profile="Player One"')
            self.assertEqual(parsed["icon_index"], 2)
            self.assertEqual(parsed["resolved_target"], real_exe)
            self.assertEqual(parsed["resolved_working_dir"], exe_dir)
            self.assertEqual(parsed["resolved_icon_location"], real_ico)

            # Env var + RelativePath only shortcut (%ProgramFiles(x86)%, %USERPROFILE%, %SystemRoot%)
            user_app = os.path.join(bottle, "drive_c", "users", "saif", "AppData", "Local", "tool.exe")
            os.makedirs(os.path.dirname(user_app), exist_ok=True)
            with open(user_app, "wb") as f:
                f.write(b"MZ" + b"\x00" * 64)

            env_lnk = os.path.join(desk_dir, "User Tool.lnk")
            with open(env_lnk, "wb") as f:
                f.write(
                    _build_test_lnk(
                        env_target="%USERPROFILE%\\appdata\\local\\TOOL.EXE",
                        env_icon="%SystemRoot%\\system32\\missing.dll,-3",
                    )
                )
            parsed_env = shortcut_sync.parse_lnk(env_lnk, bottle_dir=bottle)
            self.assertIsNotNone(parsed_env)
            self.assertEqual(parsed_env["resolved_target"], user_app)
            self.assertEqual(parsed_env["icon_index"], -3)

            # Wow64 fallback: %ProgramFiles%\...\LaunchGame.exe -> Program Files (x86)
            pf_wow_lnk = os.path.join(desk_dir, "Wow64 App.lnk")
            with open(pf_wow_lnk, "wb") as f:
                f.write(_build_test_lnk(env_target="%ProgramFiles%\\My Space Game\\LaunchGame.exe"))
            parsed_wow = shortcut_sync.parse_lnk(pf_wow_lnk, bottle_dir=bottle)
            self.assertEqual(parsed_wow["resolved_target"], real_exe)

    def test_real_generals_lnk_and_pe_icon_if_present(self):
        real_lnk = (
            "/var/home/saifeldin/.var/app/com.usebottles.bottles/data/bottles/bottles/"
            "Sadeem-Windows/drive_c/users/Public/Desktop/Play Generals Zero Hour.lnk"
        )
        if not os.path.isfile(real_lnk):
            self.skipTest("Real Play Generals Zero Hour.lnk not present on host")

        parsed = shortcut_sync.parse_lnk(real_lnk)
        self.assertIsNotNone(parsed)
        self.assertIn("CnC Zero Hour - Launcher.exe", parsed["target_win"])
        if parsed["resolved_target"] and os.path.isfile(parsed["resolved_target"]):
            with tempfile.TemporaryDirectory() as tmp:
                out_png = os.path.join(tmp, "generals.png")
                ok = shortcut_sync.extract_windows_icon(
                    parsed["resolved_target"], None, 0, out_png
                )
                self.assertTrue(ok)
                self.assertGreater(os.path.getsize(out_png), 0)
                with Image.open(out_png) as im:
                    self.assertGreaterEqual(im.width, 32)
                    self.assertEqual(im.format, "PNG")

    def test_icon_extraction_ico_pe32_and_pe32_plus(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 1. Multi-size .ico -> chooses highest resolution (64x64)
            ico_path = os.path.join(tmp, "app.ico")
            with open(ico_path, "wb") as f:
                f.write(_build_test_ico((16, 64)))
            out_ico_png = os.path.join(tmp, "from_ico.png")
            self.assertTrue(shortcut_sync.extract_windows_icon(None, ico_path, 0, out_ico_png))
            self.assertGreater(os.path.getsize(out_ico_png), 0)
            with Image.open(out_ico_png) as im:
                self.assertEqual(im.size, (64, 64))

            # 2. Synthetic 32-bit PE32 with group ID 105 (negative icon index -105)
            pe32_path = os.path.join(tmp, "app32.exe")
            with open(pe32_path, "wb") as f:
                f.write(_build_test_pe_with_icon(is_pe32_plus=False, group_id=105, png_size=48))
            out_pe32 = os.path.join(tmp, "from_pe32.png")
            self.assertTrue(shortcut_sync.extract_windows_icon(pe32_path, None, -105, out_pe32))
            self.assertGreater(os.path.getsize(out_pe32), 0)
            with Image.open(out_pe32) as im:
                self.assertEqual(im.size, (48, 48))

            # 3. Synthetic 64-bit PE32+ executable
            pe64_path = os.path.join(tmp, "app64.exe")
            with open(pe64_path, "wb") as f:
                f.write(_build_test_pe_with_icon(is_pe32_plus=True, group_id=200, png_size=64))
            out_pe64 = os.path.join(tmp, "from_pe64.png")
            self.assertTrue(shortcut_sync.extract_windows_icon(pe64_path, None, 0, out_pe64))
            self.assertGreater(os.path.getsize(out_pe64), 0)
            with Image.open(out_pe64) as im:
                self.assertEqual(im.size, (64, 64))

            # 4. Missing/invalid binary gracefully returns False without creating file
            bad_exe = os.path.join(tmp, "plain.exe")
            with open(bad_exe, "wb") as f:
                f.write(b"not a pe")
            out_bad = os.path.join(tmp, "bad.png")
            self.assertFalse(shortcut_sync.extract_windows_icon(bad_exe, None, 0, out_bad))
            self.assertFalse(os.path.exists(out_bad))

    def test_sync_filtering_deduplication_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            bottle = os.path.join(tmp, "bottle")
            apps_dir = os.path.join(tmp, "applications")
            icons_dir = os.path.join(tmp, "icons")
            os.makedirs(apps_dir, exist_ok=True)
            os.makedirs(icons_dir, exist_ok=True)

            game_dir = os.path.join(bottle, "drive_c", "Games", "Awesome Game")
            desk_dir = os.path.join(bottle, "drive_c", "users", "Public", "Desktop")
            start_dir = os.path.join(
                bottle, "drive_c", "ProgramData", "Microsoft", "Windows", "Start Menu", "Programs", "Awesome"
            )
            os.makedirs(game_dir, exist_ok=True)
            os.makedirs(desk_dir, exist_ok=True)
            os.makedirs(start_dir, exist_ok=True)

            game_exe = os.path.join(game_dir, "awesome.exe")
            uninst_exe = os.path.join(game_dir, "unins000.exe")
            help_txt = os.path.join(game_dir, "readme.txt")
            with open(game_exe, "wb") as f:
                f.write(_build_test_pe_with_icon(is_pe32_plus=True, png_size=48))
            with open(uninst_exe, "wb") as f:
                f.write(b"MZ" + b"\x00" * 64)
            with open(help_txt, "w", encoding="utf-8") as f:
                f.write("help")

            # Desktop and Start Menu both point to awesome.exe (Desktop should win!)
            desk_lnk = os.path.join(desk_dir, "Awesome Game.lnk")
            start_lnk = os.path.join(start_dir, "Play Awesome StartMenu.lnk")
            for lnk_p in (desk_lnk, start_lnk):
                with open(lnk_p, "wb") as f:
                    f.write(_build_test_lnk(local_base_path="C:\\Games\\Awesome Game\\awesome.exe"))

            # Junk shortcuts that MUST be ignored
            for junk_name, win_target in (
                ("Uninstall Game.lnk", "C:\\Games\\Awesome Game\\unins000.exe"),
                ("ReadMe.lnk", "C:\\Games\\Awesome Game\\awesome.exe"),
                ("Visit Website.lnk", "C:\\Games\\Awesome Game\\awesome.exe"),
                ("إلغاء التثبيت.lnk", "C:\\Games\\Awesome Game\\awesome.exe"),
                ("Manual.lnk", "C:\\Games\\Awesome Game\\readme.txt"),
            ):
                with open(os.path.join(start_dir, junk_name), "wb") as f:
                    f.write(_build_test_lnk(local_base_path=win_target))

            # Separate entry with distinct arguments SHOULD remain distinct
            mod_lnk = os.path.join(start_dir, "Awesome Modded.lnk")
            with open(mod_lnk, "wb") as f:
                f.write(
                    _build_test_lnk(
                        local_base_path="C:\\Games\\Awesome Game\\awesome.exe",
                        arguments="-win -mod foo",
                    )
                )

            # Unmanaged user .desktop files that MUST NEVER be touched
            user_desktop = os.path.join(apps_dir, "my-custom-app.desktop")
            unmanaged_prefix = os.path.join(apps_dir, "sadeem-win-unmanaged.desktop")
            for p in (user_desktop, unmanaged_prefix):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=Custom\nExec=true\n")

            res = shortcut_sync.sync_bottle_shortcuts(
                bottle_dir=bottle,
                applications_dir=apps_dir,
                icons_dir=icons_dir,
                run_update_db=False,
            )

            self.assertEqual(len(res["added"]), 2)
            self.assertEqual(len(res["active"]), 2)
            names = {item["name"] for item in res["active"]}
            self.assertEqual(names, {"Awesome Game", "Awesome Modded"})

            # Verify valid XDG Desktop Entry keys & GLib.shell_parse_argv compatibility
            main_entry = next(i for i in res["active"] if i["name"] == "Awesome Game")
            mod_entry = next(i for i in res["active"] if i["name"] == "Awesome Modded")
            self.assertEqual(main_entry["category"], "Game;")
            self.assertTrue(os.path.isfile(main_entry["icon"]))

            kf = GLib.KeyFile()
            kf.load_from_file(mod_entry["desktop_path"], GLib.KeyFileFlags.NONE)
            self.assertTrue(kf.get_boolean("Desktop Entry", "X-Sadeem-Windows-Managed"))
            ok, argv = GLib.shell_parse_argv(kf.get_string("Desktop Entry", "Exec"))
            self.assertTrue(ok)
            self.assertEqual(
                argv,
                [
                    shortcut_sync.HANDLER_EXECUTABLE,
                    "--launch-installed",
                    game_exe,
                    "--args",
                    "-win -mod foo",
                ],
            )

            # Delete Awesome Game shortcuts -> should clean Awesome Game .desktop & keep Awesome Modded + unmanaged
            os.remove(desk_lnk)
            os.remove(start_lnk)
            res2 = shortcut_sync.sync_bottle_shortcuts(
                bottle_dir=bottle,
                applications_dir=apps_dir,
                icons_dir=icons_dir,
                run_update_db=False,
            )
            self.assertEqual(res2["removed"], [main_entry["desktop_path"]])
            self.assertFalse(os.path.exists(main_entry["desktop_path"]))
            self.assertTrue(os.path.exists(mod_entry["desktop_path"]))
            self.assertTrue(os.path.exists(user_desktop))
            self.assertTrue(os.path.exists(unmanaged_prefix))

            # Delete target .exe -> Awesome Modded .desktop should also be cleaned up automatically
            os.remove(game_exe)
            res3 = shortcut_sync.sync_bottle_shortcuts(
                bottle_dir=bottle,
                applications_dir=apps_dir,
                icons_dir=icons_dir,
                run_update_db=False,
            )
            self.assertEqual(res3["removed"], [mod_entry["desktop_path"]])
            self.assertEqual(res3["active"], [])
            self.assertTrue(os.path.exists(user_desktop))
            self.assertTrue(os.path.exists(unmanaged_prefix))

    def test_close_request_respects_launched_ok_and_manual_cancel(self):
        handler = _load_handler_module()
        WinCls = handler.create_runner_window_class()
        win = WinCls(app=None, target_path="/tmp/fake-installer.exe")
        try:
            proc_running = mock.MagicMock()
            proc_running.poll.return_value = None
            win._current_proc = proc_running

            # Case 1: Launched successfully (_launched_ok=True) -> NEVER terminate child
            win._launched_ok = True
            win._on_close_request(win)
            proc_running.terminate.assert_not_called()
            self.assertFalse(win._is_cancelled)

            # Case 2: Manual user close while still setting up (_launched_ok=False) -> terminate child
            win._launched_ok = False
            win._on_close_request(win)
            proc_running.terminate.assert_called_once()
            self.assertTrue(win._is_cancelled)

            # Case 3: Worker thread spawns --sync-watch and calls _finish_launch_success (which sets _launched_ok=True)
            win._is_cancelled = False
            win._launched_ok = False
            proc_running.reset_mock()
            idle_calls = []
            with mock.patch.object(handler, "is_bottle_present", return_value=True), \
                 mock.patch.object(handler.subprocess, "Popen", return_value=proc_running), \
                 mock.patch.object(handler.time, "sleep", return_value=None), \
                 mock.patch.object(handler, "_spawn_sync_watch") as mock_watch, \
                 mock.patch.object(GLib, "idle_add", side_effect=lambda fn, *a: idle_calls.append((fn, a)) or 1):
                win._worker_thread()

            mock_watch.assert_called_once()
            finish_funcs = [fn for fn, _ in idle_calls if fn == win._finish_launch_success]
            self.assertEqual(len(finish_funcs), 1)
            with mock.patch.object(win, "close") as mock_close:
                ret = win._finish_launch_success()
            self.assertFalse(ret)
            self.assertTrue(win._launched_ok)
            mock_close.assert_called_once()
        finally:
            win.destroy()

    def test_launch_installed_silent_and_translations_parity(self):
        handler = _load_handler_module()
        base_keys = set(handler.TRANSLATIONS["en"].keys())
        self.assertEqual(
            set(handler.TRANSLATIONS.keys()),
            {"en", "ar", "fr", "es", "de", "tr", "ru", "pt", "it", "zh"},
        )
        for lang_code, mapping in handler.TRANSLATIONS.items():
            self.assertEqual(set(mapping.keys()), base_keys, f"Missing keys in {lang_code}")

        with tempfile.TemporaryDirectory() as tmp:
            fake_exe = os.path.join(tmp, "game.exe")
            with open(fake_exe, "wb") as f:
                f.write(b"MZ" + b"\x00" * 32)
            proc = mock.MagicMock()
            proc.poll.return_value = None
            with mock.patch.object(handler, "is_bottles_installed", return_value=True), \
                 mock.patch.object(handler, "is_bottle_present", return_value=True), \
                 mock.patch.object(handler.subprocess, "Popen", return_value=proc) as mock_popen, \
                 mock.patch.object(handler.time, "sleep", return_value=None), \
                 mock.patch.object(handler, "_run_gui_app") as mock_gui:
                rc = handler.launch_installed_silent(fake_exe, "-quickstart")
            self.assertEqual(rc, 0)
            mock_gui.assert_not_called()
            mock_popen.assert_called_once()
            self.assertIn("-quickstart", mock_popen.call_args[0][0])

    def test_cli_parsing_commands_and_sync_watch_lock_and_notifications(self):
        handler = _load_handler_module()

        self.assertTrue(os.access(HANDLER_PATH, os.X_OK))
        self.assertEqual(handler.parse_cli_args(["--sync"]), {"mode": "sync"})
        self.assertEqual(handler.parse_cli_args(["--sync-watch"]), {"mode": "sync-watch"})
        self.assertEqual(
            handler.parse_cli_args(["--launch-installed", "/tmp/game.exe", "--args", "-quickstart -win"]),
            {
                "mode": "launch-installed",
                "target": os.path.abspath("/tmp/game.exe"),
                "args": "-quickstart -win",
            },
        )
        # Binfmt wrapper passes "$1" "$@" -> first two args duplicate exe path
        self.assertEqual(
            handler.parse_cli_args(["file:///tmp/setup.exe", "/tmp/setup.exe", "/S"]),
            {
                "mode": "gui",
                "target": os.path.abspath("/tmp/setup.exe"),
                "args": "/S",
            },
        )

        # Verify bottles-cli command keeps `--` before flags like -quickstart
        cmd = handler.build_bottles_run_cmd("/tmp/game.exe", '-quickstart -name="Player 1"')
        self.assertEqual(
            cmd,
            [
                "flatpak",
                "run",
                "--command=bottles-cli",
                "com.usebottles.bottles",
                "run",
                "-b",
                handler.BOTTLE_NAME,
                "-e",
                "/tmp/game.exe",
                "--",
                "-quickstart",
                "-name=Player 1",
            ],
        )

        # Verify flock single-instance lock & new app notification in --sync-watch
        with tempfile.TemporaryDirectory() as tmp:
            bottle = os.path.join(tmp, "bottle")
            apps_dir = os.path.join(tmp, "apps")
            icons_dir = os.path.join(tmp, "icons")
            lock_path = os.path.join(tmp, "sync.lock")

            desk_dir = os.path.join(bottle, "drive_c", "users", "Public", "Desktop")
            exe_dir = os.path.join(bottle, "drive_c", "Games", "TestApp")
            os.makedirs(desk_dir, exist_ok=True)
            os.makedirs(exe_dir, exist_ok=True)
            exe_path = os.path.join(exe_dir, "TestApp.exe")
            with open(exe_path, "wb") as f:
                f.write(_build_test_pe_with_icon(png_size=32))
            with open(os.path.join(desk_dir, "Test App.lnk"), "wb") as f:
                f.write(_build_test_lnk(local_base_path="C:\\Games\\TestApp\\TestApp.exe"))

            notified = []
            with mock.patch.object(handler, "is_bottle_process_active", return_value=False), \
                 mock.patch.object(
                     handler,
                     "send_app_added_notification",
                     side_effect=lambda name, icon=None: notified.append((name, icon)) or True,
                 ):
                rc = handler.run_sync_watch(
                    bottle_dir=bottle,
                    lock_path=lock_path,
                    poll_interval=0.01,
                    grace_seconds=0.02,
                    max_seconds=2.0,
                    applications_dir=apps_dir,
                    icons_dir=icons_dir,
                )
            self.assertEqual(rc, 0)
            self.assertEqual(len(notified), 1)
            self.assertEqual(notified[0][0], "Test App")

            # Verify Arabic notification format
            self.assertIn(
                "تمت إضافة {name} إلى قائمة التطبيقات",
                handler.TRANSLATIONS["ar"]["notif_app_added_body"],
            )

            # Verify active flock prevents duplicate watcher
            import fcntl
            with open(lock_path, "a+", encoding="utf-8") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    with mock.patch.object(handler.shortcut_sync, "sync_bottle_shortcuts") as mock_sync:
                        rc2 = handler.run_sync_watch(
                            bottle_dir=bottle,
                            lock_path=lock_path,
                            poll_interval=0.01,
                            grace_seconds=0.02,
                            applications_dir=apps_dir,
                            icons_dir=icons_dir,
                        )
                    self.assertEqual(rc2, 0)
                    mock_sync.assert_not_called()
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def test_clean_shortcut_name_and_handler_desktop_nodisplay(self):
        # Name cleanup rules
        self.assertEqual(
            shortcut_sync.clean_shortcut_name("Play Generals Zero Hour"),
            "Generals Zero Hour",
        )
        self.assertEqual(
            shortcut_sync.clean_shortcut_name("Launch My App - Shortcut"),
            "My App",
        )
        self.assertEqual(
            shortcut_sync.clean_shortcut_name("PlayStation Store"),
            "PlayStation Store",
        )
        self.assertEqual(shortcut_sync.clean_shortcut_name("Startcraft"), "Startcraft")
        self.assertEqual(shortcut_sync.clean_shortcut_name("Play"), "Play")
        self.assertEqual(shortcut_sync.clean_shortcut_name("Run Tool.exe"), "Tool")

        # End-to-end sync + watch notification uses cleaned name
        handler = _load_handler_module()
        with tempfile.TemporaryDirectory() as tmp:
            bottle = os.path.join(tmp, "bottle")
            apps_dir = os.path.join(tmp, "apps")
            icons_dir = os.path.join(tmp, "icons")
            lock_path = os.path.join(tmp, "sync.lock")
            desk_dir = os.path.join(bottle, "drive_c", "users", "Public", "Desktop")
            exe_dir = os.path.join(bottle, "drive_c", "Games", "ZeroHour")
            os.makedirs(desk_dir, exist_ok=True)
            os.makedirs(exe_dir, exist_ok=True)
            with open(os.path.join(exe_dir, "zh.exe"), "wb") as f:
                f.write(_build_test_pe_with_icon(png_size=32))
            with open(os.path.join(desk_dir, "Play Generals Zero Hour.lnk"), "wb") as f:
                f.write(_build_test_lnk(local_base_path="C:\\Games\\ZeroHour\\zh.exe"))

            notified = []
            with mock.patch.object(handler, "is_bottle_process_active", return_value=False), \
                 mock.patch.object(
                     handler,
                     "send_app_added_notification",
                     side_effect=lambda name, icon=None: notified.append(name) or True,
                 ):
                rc = handler.run_sync_watch(
                    bottle_dir=bottle,
                    lock_path=lock_path,
                    poll_interval=0.01,
                    grace_seconds=0.02,
                    max_seconds=2.0,
                    applications_dir=apps_dir,
                    icons_dir=icons_dir,
                )
            self.assertEqual(rc, 0)
            self.assertEqual(notified, ["Generals Zero Hour"])
            desktops = [fn for fn in os.listdir(apps_dir) if fn.startswith("sadeem-win-") and fn.endswith(".desktop")]
            self.assertEqual(len(desktops), 1)
            kf_gen = GLib.KeyFile()
            kf_gen.load_from_file(os.path.join(apps_dir, desktops[0]), GLib.KeyFileFlags.NONE)
            self.assertEqual(kf_gen.get_string("Desktop Entry", "Name"), "Generals Zero Hour")

        # Handler desktop entry must have NoDisplay=true, keep MimeType/Exec, and avoid Hidden=true
        handler_desktop = os.path.join(
            REPO_ROOT, "files/system/usr/share/applications/sadeem-windows-exe-handler.desktop"
        )
        self.assertTrue(os.path.isfile(handler_desktop))
        with open(handler_desktop, "r", encoding="utf-8") as f:
            raw_desktop = f.read()
        self.assertNotIn("Hidden=true", raw_desktop)

        kf = GLib.KeyFile()
        kf.load_from_file(handler_desktop, GLib.KeyFileFlags.NONE)
        self.assertTrue(kf.get_boolean("Desktop Entry", "NoDisplay"))
        self.assertEqual(kf.get_string("Desktop Entry", "Exec"), "/usr/bin/sadeem-windows-exe-handler %U")
        mimes = kf.get_string("Desktop Entry", "MimeType")
        self.assertIn("application/x-ms-dos-executable", mimes)
        self.assertIn("application/x-msi", mimes)


if __name__ == "__main__":
    unittest.main()
