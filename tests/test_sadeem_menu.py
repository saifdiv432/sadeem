#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Test Suite for Sadeem Menu (sadeem-menu@sadeem.os) - Unified 2D Free Board & Compact Foldable Groups.
Verifies:
1. metadata.json validity and GNOME 50/51 compatibility.
2. GJS ESM syntax for all extension JS files + GNOME 51 GIRepository St/Clutter property &
   Clutter.CursorType enum validation + Step 1 input/overlay/scroll fixes.
3. GSettings schema org.sadeem.menu strict compilation & defaults
   (menu-width=1140, menu-height=680, icon-size-level=2 [64x70..98x104], etc.).
4. Complete 10-language i18n coverage across all keys referenced in code.
5. Live GJS execution of tileLayout.js (cell presets 0..4 default 78x84, compact foldable group
   slots <=capacity and >capacity with 2x2 overflow mosaic cluster, computeUnifiedBoardRects,
   placeBoardItemAt collision pushdown, hitTestUnifiedBoard, detectResizeEdge, computeSurfacePosition,
   clampContextMenuPosition, and free pixel computeMenuGeometry).
6. Live GJS execution of appData.js (default 1x1 loose core apps + non-empty 2x2 smart groups,
   merging two apps into a group, adding app to group, extracting app to free board with smart exclusion,
   resizing/moving/renaming/deleting groups, strict Games exclusion filter, user-only seen-apps) & searchEngine.js.
7. Coexistence check: ArcMenu defaults preserved & recipe.yml schema compilation intact.
"""

import importlib.machinery
import importlib.util
import json
import os
import py_compile
import re
import subprocess
import tempfile
import unittest

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MENU_DIR = os.path.join(
    REPO_ROOT,
    "files/system/usr/share/gnome-shell/extensions/sadeem-menu@sadeem.os",
)
SCHEMA_FILE = os.path.join(
    REPO_ROOT,
    "files/system/usr/share/glib-2.0/schemas/org.sadeem.menu.gschema.xml",
)


def _gjs_env():
    env = os.environ.copy()
    typelib_paths = "/usr/lib64/mutter-51:/usr/lib64/gnome-shell"
    env["GI_TYPELIB_PATH"] = typelib_paths + (
        ":" + env["GI_TYPELIB_PATH"] if env.get("GI_TYPELIB_PATH") else ""
    )
    env["LD_LIBRARY_PATH"] = typelib_paths + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else ""
    )
    return env


def _run_gjs_script(script_body):
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tf:
        tf.write(script_body)
        temp_path = tf.name
    try:
        return subprocess.run(
            ["gjs", "-m", temp_path],
            capture_output=True,
            text=True,
            env=_gjs_env(),
            timeout=15,
        )
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


class TestSadeemMenuTileBoard(unittest.TestCase):
    def test_metadata_json_and_extension_files(self):
        meta_path = os.path.join(MENU_DIR, "metadata.json")
        self.assertTrue(os.path.isfile(meta_path))
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertEqual(meta.get("uuid"), "sadeem-menu@sadeem.os")
        self.assertEqual(meta.get("settings-schema"), "org.sadeem.menu")
        self.assertIn("51", meta.get("shell-version", []))

        for fname in (
            "extension.js",
            "menuUI.js",
            "contextMenu.js",
            "groupModal.js",
            "boardView.js",
            "sidebarView.js",
            "bottomStrip.js",
            "dragManager.js",
            "resizeManager.js",
            "tileLayout.js",
            "appData.js",
            "searchEngine.js",
            "i18n.js",
            "stylesheet.css",
        ):
            self.assertTrue(
                os.path.isfile(os.path.join(MENU_DIR, fname)),
                f"Missing extension file: {fname}",
            )

    def test_gjs_syntax_gnome51_properties_cursor_enums_and_input_fixes(self):
        js_files = sorted(f for f in os.listdir(MENU_DIR) if f.endswith(".js"))
        self.assertGreaterEqual(len(js_files), 6)

        env = _gjs_env()
        pure_files = {"i18n.js", "tileLayout.js", "appData.js", "searchEngine.js"}

        for f in js_files:
            path = os.path.join(MENU_DIR, f)
            res = subprocess.run(["gjs", "-m", path], capture_output=True, text=True, env=env, timeout=10)
            out = (res.stderr + "\n" + res.stdout).strip()
            self.assertNotIn("SyntaxError", out, f"GJS syntax error in {f}:\n{out}")
            if f in pure_files:
                self.assertEqual(res.returncode, 0, f"Pure module {f} failed under gjs -m:\n{out}")
            elif res.returncode != 0:
                self.assertIn(
                    "resource:///org/gnome/shell/",
                    out,
                    f"Unexpected non-shell import error in {f}:\n{out}",
                )

            with open(path, "r", encoding="utf-8") as fp:
                code = fp.read()
            self.assertNotIn("add_actor", code, f"{f} must not use deprecated add_actor")
            self.assertNotIn("remove_actor", code, f"{f} must not use deprecated remove_actor")
            self.assertNotIn("vertical:", code, f"{f} must not use removed 'vertical' on St.BoxLayout")
            self.assertNotIn("pointerWatcher.js", code, f"{f} must not import removed pointerWatcher.js")
            self.assertNotIn("ButtonMask.ONE", code)
            self.assertNotIn("homogeneous:", code, f"{f} must not pass removed 'homogeneous' constructor prop on St.BoxLayout")
            self.assertNotIn("enter-event", code, f"{f} must use notify::hover via bindTooltip instead of enter-event")
            self.assertNotIn("leave-event", code, f"{f} must use notify::hover via bindTooltip instead of leave-event")

            if f == "menuUI.js":
                self.assertLess(len(code.splitlines()), 450, "menuUI.js orchestrator must remain < 450 lines")
                self.assertIn("extends PanelMenu.Button", code)
                self.assertIn("super(0.5, I18n.t('menu_title'), false)", code)
                self.assertIn("popupMenu.js", code)
                self.assertIn("boxpointer.js", code)
                self.assertIn("PopupMenu.PopupMenuSection", code)
                self.assertIn("this._boardDirty", code)
                self.assertIn("this._sidebarDirty", code)
                self.assertIn("this._stripKey", code)
                self.assertIn("markInstalledChanged()", code)
                self.assertIn("refreshStripOnly()", code)
                self.assertIn("BoxPointer.PopupAnimation.NONE", code)
                self.assertIn("rec.shellApp.activate()", code)
                self.assertIn("global.get_current_time()", code)
                self.assertIn("launchUninstaller", code)
                self.assertIn("bindTooltip", code)
                self.assertIn("_menuRootStack.set_child_above_sibling(this._contextMenu, null)", code)
                self.assertIn("refreshSeenAppsAsync().then(() => this.refreshStripOnly())", code)
                self.assertIn("DragManager", code)
                self.assertIn("ResizeOverlay", code)
                self.assertIn("this._resizeOverlay.syncBounds(geom.totalWidth, geom.totalHeight)", code)
                self.assertIn("pinLooseApp(id, null, null", code)
                self.assertIn("changed::menu-opacity", code)
                self.assertIn("_syncSurfaceOpacity()", code)
                self.assertIn("mostCount, recentCount", code)
                self.assertIn("most-used-count", code)
                self.assertIn("recently-installed-count", code)
                self.assertIn("k === 'auto-categorize'", code)
                self.assertIn("disabled-smart-groups", code)
                self.assertIn("_syncRestoredSmartGroups", code)
                self.assertNotIn("this.menu.actor.opacity", code, "Opacity must apply to background alpha only, not actor.opacity")
                self.assertNotIn("this._menuRootStack.opacity", code, "Opacity must apply to background alpha only, not actor.opacity")
                m_opacity = re.search(r"_syncSurfaceOpacity\(\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_opacity, "_syncSurfaceOpacity missing in menuUI.js")
                self.assertIn("background-color: rgba(", m_opacity.group(1))
                self.assertIn("this.menu?.box", m_opacity.group(1))
                self.assertIn("10, 100", m_opacity.group(1))
                m_theme = re.search(r"_syncTheme\(\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_theme)
                self.assertIn("this._syncSurfaceOpacity()", m_theme.group(1))
                self.assertNotIn("_menuRootStack.style =", code, "menuUI must resize via set_size(), not inline .style")
                for forbidden in (
                    "Main.pushModal",
                    "Main.popModal",
                    "set_cursor_type",
                    "DirectStageDragController",
                    "_stageHost",
                    "captured-event",
                    "pointerWatcher",
                ):
                    self.assertNotIn(forbidden, code, f"Phase A/B menuUI.js must not contain {forbidden}")

            if f == "dragManager.js":
                self.assertNotIn("Main.pushModal", code)
                self.assertIn("DRAG_THRESHOLD_PX = 8", code)
                self.assertIn("transform_stage_point", code)
                self.assertIn("hitTestUnifiedBoard", code)
                self.assertIn("visualActor", code)
                m_bp = re.search(r"actor\.connect\('button-press-event',\s*\([^\)]*\)\s*=>\s*\{([\s\S]*?)\}\);", code)
                self.assertIsNotNone(m_bp)
                self.assertNotIn("EVENT_STOP", m_bp.group(1), "dragManager button-press-event must never return EVENT_STOP")
                self.assertIn("return Clutter.EVENT_PROPAGATE", m_bp.group(1))

            if f == "resizeManager.js":
                self.assertNotIn("Main.pushModal", code)
                self.assertNotIn("global.stage", code)
                self.assertNotIn("global.display", code)
                self.assertNotIn("_menuActor.set_cursor_type", code)
                self.assertNotIn("_rootStack.set_cursor_type", code)
                self.assertNotIn("BinLayout", code, "resizeManager.js must use Clutter.FixedLayout, not BinLayout")
                self.assertIn("Clutter.FixedLayout", code)
                self.assertIn("computeResizeHandleBounds", code)
                self.assertIn("syncBounds(width, height)", code)
                self.assertIn("this._topHandle.set_cursor_type(Clutter.CursorType.N_RESIZE)", code)
                self.assertIn("this._sideHandle.set_cursor_type(sideCursor)", code)
                self.assertIn("this._cornerHandle.set_cursor_type(cornerCursor)", code)
                self.assertIn("this._settings.set_int('menu-width', finalW)", code)
                self.assertIn("this._settings.set_int('menu-height', finalH)", code)
                m_motion = re.search(r"_onResizeMotion\(ev\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_motion, "_onResizeMotion missing in resizeManager.js")
                self.assertNotIn(".style =", m_motion.group(1), "resize MOTION must never mutate .style")
                self.assertIn("this._rootStack.set_size(activeW, activeH)", m_motion.group(1))
                self.assertIn("this.syncBounds(activeW, activeH)", m_motion.group(1))
                m_cap = re.search(r"_onCapturedEvent\(ev\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_cap)
                self.assertNotIn(".style =", m_cap.group(1), "resize captured-event must never mutate .style")
                self.assertIn("this._onResizeMotion(ev)", m_cap.group(1))

            if f == "contextMenu.js":
                self.assertIn("ctx_uninstall", code)
                self.assertIn("ctx_new_window", code)
                self.assertIn("sadeem-uninstaller", code)
                self.assertIn("CORE_CRITICAL_EXCLUSIONS", code)
                self.assertIn("sadeem-context-size-grid", code)
                self.assertIn("options.slice(i, i + 2)", code)
                self.assertIn("row.layout_manager.homogeneous = true", code)
                self.assertIn("Pango.EllipsizeMode.END", code)
                self.assertIn("GLib.idle_add", code)
                self.assertNotIn("captured-event", code, "contextMenu.js must not use captured-event")
                self.assertIn("this.set_child_above_sibling(this._menuBox, this._dismissBackdrop)", code)
                self.assertIn("transform_stage_point(", code)
                self.assertNotIn("this._menuBox.connect('button-press-event'", code, "contextMenu._menuBox must never intercept button-press-event")
                self.assertIn("_cleanupIdleId", code)
                self.assertGreaterEqual(code.count("button_mask: St.ButtonMask.PRIMARY"), 3)
                self.assertGreaterEqual(code.count("track_hover: true"), 3)
                self.assertNotIn("_menuBox.set_size(", code, "contextMenu.js must never call fixed set_size() on _menuBox")

            if f == "bottomStrip.js":
                self.assertIn("notify::hover", code)
                self.assertIn("button-press-event", code)
                self.assertIn("mostLimit", code)
                self.assertIn("recentLimit", code)
                self.assertIn("apps.slice(0, limit)", code)
                self.assertIn("1, 4", code)
                self.assertNotIn("apps.slice(0, 3)", code, "bottomStrip.js must respect dynamic maxCount instead of slicing to 3")

            if f == "groupModal.js":
                self.assertIn("Math.ceil(apps.length / cols)", code)
                self.assertIn("Math.max(185, contentH)", code)
                self.assertNotIn("Math.min(400, Math.max(240, containerH - 48))", code)
                self.assertNotIn("this._card.connect('button-press-event'", code, "groupModal._card must never intercept button-press-event")
                self.assertNotIn("attachDraggable", code, "groupModal app tiles must not be draggable")
                self.assertIn("_cleanupIdleId", code)

            if f == "boardView.js":
                self.assertIn("hscrollbar_policy: St.PolicyType.AUTOMATIC", code)
                self.assertIn("vscrollbar_policy: St.PolicyType.AUTOMATIC", code)
                self.assertIn("getLooseAppIconSize", code)
                self.assertIn("getCompactGroupIconSize", code)
                self.assertIn("bindTooltip", code)
                self.assertIn(".length > 18", code)
                m_slot = re.search(r"_createGroupSlotButton\([^\)]*\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_slot, "_createGroupSlotButton missing in boardView.js")
                self.assertIn("attachDraggable(slotBtn, 'board-group', groupDragPayload", m_slot.group(1))
                self.assertNotIn("'board-app'", m_slot.group(1), "Group slot buttons must drag whole group, not individual app")
                self.assertIn("onLaunchApp?.(rec, false)", m_slot.group(1))
                self.assertIn("onGroupAppContext?.(group, rec", m_slot.group(1))
                m_over = re.search(r"_createOverflowSlotButton\([^\)]*\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_over)
                self.assertIn("attachDraggable(btn, 'board-group', groupDragPayload", m_over.group(1))
                m_card = re.search(r"_createGroupCard\([^\)]*\)\s*\{([\s\S]*?)\n    \}", code)
                self.assertIsNotNone(m_card, "_createGroupCard missing in boardView.js")
                self.assertIn("new St.BoxLayout(", m_card.group(1))
                self.assertIn("sadeem-group-title-btn", m_card.group(1))
                self.assertIn("sadeem-group-action-btn", m_card.group(1))
                self.assertIn("sadeem-group-empty-slot-btn", m_card.group(1))
                m_card_press = re.search(r"card\.connect\('button-press-event',\s*\([^\)]*\)\s*=>\s*\{([\s\S]*?)\}\);", m_card.group(1))
                self.assertIsNotNone(m_card_press, "card.connect('button-press-event') missing")
                self.assertNotIn("BUTTON_PRIMARY", m_card_press.group(1), "card parent must never intercept BUTTON_PRIMARY")

            if "get_scroll_delta" in code:
                self.assertIn("Clutter.ScrollDirection.SMOOTH", code, f"{f} must guard get_scroll_delta behind SMOOTH")

        css_path = os.path.join(MENU_DIR, "stylesheet.css")
        with open(css_path, "r", encoding="utf-8") as cf:
            css = cf.read()
        self.assertIn(".sadeem-popup-menu", css)
        self.assertIn("border-radius: 20px;", css)
        self.assertIn("background-color: transparent;", css)
        self.assertIn(".sadeem-tile-btn", css)
        self.assertIn(".sadeem-group-card", css)
        m_slot_css = re.search(r"\.sadeem-group-slot-app\s*\{([^\}]*)\}", css)
        self.assertIsNotNone(m_slot_css)
        self.assertIn("background-color: transparent;", m_slot_css.group(1))
        m_empty_css = re.search(r"\.sadeem-group-empty-slot-btn,\s*\.sadeem-group-empty-slot-btn:hover,\s*\.sadeem-group-empty-slot-btn:focus,\s*\.sadeem-group-empty-slot-btn:active\s*\{([^\}]*)\}", css)
        self.assertIsNotNone(m_empty_css, "Explicit transparent hover/focus/active rule missing for .sadeem-group-empty-slot-btn")
        self.assertIn("background-color: transparent;", m_empty_css.group(1))
        self.assertIn("border: none;", m_empty_css.group(1))
        self.assertIn("box-shadow: none;", m_empty_css.group(1))
        self.assertIn("outline: none;", m_empty_css.group(1))
        m_chip_css = re.search(r"\.sadeem-context-size-chip\s*\{([^\}]*)\}", css)
        self.assertIsNotNone(m_chip_css)
        self.assertIn("min-width: 0px;", m_chip_css.group(1))
        self.assertIn(".sadeem-group-overflow-slot", css)
        self.assertIn(".sadeem-group-modal", css)
        self.assertIn(".sadeem-group-modal-backdrop", css)
        self.assertIn(".sadeem-menu-main-body-no-sidebar", css)
        self.assertIn(".sadeem-context-item-danger", css)
        self.assertIn("min-width: 240px;", css)
        self.assertIn("width: 138px;", css)
        self.assertIn("min-height: 0px;", css)
        self.assertIn(".sadeem-drop-preview-slot", css)
        self.assertIn(".sadeem-tile-drop-folder", css)
        self.assertIn(".sadeem-resize-handle-top", css)
        self.assertIn(".sadeem-resize-handle-side", css)
        self.assertIn(".sadeem-resize-handle-corner", css)
        self.assertNotIn("max-width: none", css)

        gi.require_version("GIRepository", "3.0")
        from gi.repository import GIRepository

        repo = GIRepository.Repository.new()
        repo.prepend_search_path("/usr/lib64/mutter-51")
        repo.prepend_search_path("/usr/lib64/gnome-shell")
        repo.require("St", "51", 0)
        repo.require("Clutter", "51", 0)

        def get_props(ns, cls_name):
            curr = repo.find_by_name(ns, cls_name)
            if not curr:
                return None
            props = set()
            while curr:
                for i in range(curr.get_n_properties()):
                    name = curr.get_property(i).get_name()
                    props.add(name)
                    props.add(name.replace("-", "_"))
                    parts = name.split("-")
                    props.add(parts[0] + "".join(x.capitalize() for x in parts[1:]))
                curr = curr.get_parent() if hasattr(curr, "get_parent") else None
            return props

        cursor_enum = repo.find_by_name("Clutter", "CursorType")
        self.assertIsNotNone(cursor_enum, "Clutter.CursorType enum missing in Clutter-51")
        valid_cursors = {
            cursor_enum.get_value(i).get_name().upper()
            for i in range(cursor_enum.get_n_values())
        }

        def strip_strings_and_comments(src):
            out, i, n = [], 0, len(src)
            while i < n:
                if src[i : i + 2] == "//":
                    end = src.find("\n", i)
                    i = n if end == -1 else end
                elif src[i : i + 2] == "/*":
                    end = src.find("*/", i + 2)
                    i = n if end == -1 else end + 2
                elif src[i] in ('"', "'", "`"):
                    q = src[i]
                    i += 1
                    while i < n:
                        if src[i] == "\\":
                            i += 2
                        elif src[i] == q:
                            i += 1
                            break
                        else:
                            i += 1
                    out.append('""')
                else:
                    out.append(src[i])
                    i += 1
            return "".join(out)

        pattern = re.compile(r"new\s+(St|Clutter)\.([A-Za-z0-9_]+)\s*\(\s*\{([^}]*)\}\s*\)")
        cursor_pattern = re.compile(r"Clutter\.CursorType\.([A-Z0-9_]+)")
        invalid = []
        invalid_cursors = []
        for f in js_files:
            with open(os.path.join(MENU_DIR, f), "r", encoding="utf-8") as fp:
                clean = strip_strings_and_comments(fp.read())
            self.assertNotIn("makeDraggable", clean, f"{f} must not call DND.makeDraggable")
            self.assertNotIn("GridLayout", clean, f"{f} must not use GridLayout in code")
            for ns, cls_name, block in pattern.findall(clean):
                valid = get_props(ns, cls_name)
                self.assertIsNotNone(valid, f"Unknown class {ns}.{cls_name} in {f}")
                for k in re.findall(r"([a-zA-Z0-9_\-]+)\s*:", block):
                    if k not in valid:
                        invalid.append(f"{f}: new {ns}.{cls_name}({{ {k}: ... }})")
            for c_name in cursor_pattern.findall(clean):
                if c_name not in valid_cursors:
                    invalid_cursors.append(f"{f}: Clutter.CursorType.{c_name}")

        self.assertEqual(invalid, [], f"Invalid GNOME 51 properties detected: {invalid}")
        self.assertEqual(invalid_cursors, [], f"Invalid Clutter.CursorType enums: {invalid_cursors}")

    def test_gsettings_schema_strict_compile_and_defaults(self):
        self.assertTrue(os.path.isfile(SCHEMA_FILE))
        with tempfile.TemporaryDirectory() as tmpdir:
            dest_xml = os.path.join(tmpdir, os.path.basename(SCHEMA_FILE))
            with open(SCHEMA_FILE, "rb") as src, open(dest_xml, "wb") as dst:
                dst.write(src.read())

            dry = subprocess.run(
                ["glib-compile-schemas", "--strict", "--dry-run", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(dry.returncode, 0, f"Schema validation failed:\n{dry.stderr}")

            comp = subprocess.run(
                ["glib-compile-schemas", "--strict", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(comp.returncode, 0, f"Schema compile failed:\n{comp.stderr}")

            source = Gio.SettingsSchemaSource.new_from_directory(tmpdir, None, False)
            schema = source.lookup("org.sadeem.menu", False)
            self.assertIsNotNone(schema)
            backend = Gio.memory_settings_backend_new()
            settings = Gio.Settings.new_full(schema, backend, None)

            self.assertEqual(settings.get_int("tile-columns"), 3)
            self.assertEqual(settings.get_int("menu-width"), 1140)
            self.assertEqual(settings.get_int("menu-height"), 680)
            self.assertEqual(settings.get_int("icon-size-level"), 2)
            self.assertEqual(settings.get_int("menu-opacity"), 96)
            self.assertTrue(settings.get_boolean("show-all-apps-sidebar"))
            self.assertTrue(settings.get_boolean("show-most-used"))
            self.assertEqual(settings.get_int("most-used-count"), 3)
            self.assertTrue(settings.get_boolean("show-recently-installed"))
            self.assertEqual(settings.get_int("recently-installed-count"), 3)
            self.assertEqual(settings.get_int("bottom-section-count"), 3)
            self.assertTrue(settings.get_boolean("auto-categorize"))
            self.assertEqual(settings.get_strv("disabled-smart-groups"), [])
            self.assertFalse(settings.get_boolean("show-power-buttons"))
            self.assertTrue(settings.get_boolean("bind-super-key"))
            self.assertEqual(settings.get_string("layout-config"), "{}")

            self.assertTrue(settings.set_strv("disabled-smart-groups", ["games"]))
            self.assertEqual(settings.get_strv("disabled-smart-groups"), ["games"])

            self.assertTrue(settings.set_int("menu-width", 440))
            self.assertTrue(settings.set_int("menu-width", 1800))
            self.assertTrue(settings.set_int("menu-height", 380))
            self.assertTrue(settings.set_int("menu-height", 1020))
            self.assertTrue(settings.set_int("menu-opacity", 10))
            self.assertTrue(settings.set_int("menu-opacity", 100))
            self.assertTrue(settings.set_int("most-used-count", 1))
            self.assertTrue(settings.set_int("most-used-count", 4))
            self.assertTrue(settings.set_int("recently-installed-count", 1))
            self.assertTrue(settings.set_int("recently-installed-count", 4))

    def test_i18n_ten_languages_and_used_keys(self):
        used_keys = set()
        for f in os.listdir(MENU_DIR):
            if not f.endswith(".js"):
                continue
            with open(os.path.join(MENU_DIR, f), "r", encoding="utf-8") as fp:
                used_keys.update(re.findall(r"I18n\.t\(\s*['\"]([a-zA-Z0-9_]+)['\"]", fp.read()))
        required_new = {
            "group_size_2x2",
            "group_size_3x2",
            "group_size_3x3",
            "group_size_4x3",
            "ctx_open_group",
            "ctx_new_window",
            "ctx_uninstall",
            "ctx_extract_to_board",
            "ctx_remove_from_board",
            "ctx_remove_from_group",
        }
        self.assertTrue(required_new.issubset(used_keys), f"Missing code usage of keys: {required_new - used_keys}")

        used_keys_json = json.dumps(sorted(used_keys))
        script = f"""
        import * as I18n from 'file://{os.path.join(MENU_DIR, "i18n.js")}';
        const expectedLangs = ['ar', 'en', 'fr', 'es', 'de', 'tr', 'ru', 'pt', 'it', 'zh'];
        if (I18n.SUPPORTED_LANGUAGES.length !== 10)
            throw new Error('Expected 10 supported languages');
        for (const lang of expectedLangs) {{
            if (!I18n.SUPPORTED_LANGUAGES.includes(lang) || !I18n.STRINGS[lang])
                throw new Error('Missing lang: ' + lang);
        }}
        const keys = new Set([
            ...Object.keys(I18n.STRINGS.en),
            ...{used_keys_json},
        ]);
        for (const lang of expectedLangs) {{
            for (const key of keys) {{
                const val = I18n.STRINGS[lang]?.[key];
                if (!val || typeof val !== 'string' || !val.trim())
                    throw new Error(`Missing translation key ${{key}} in ${{lang}}`);
            }}
        }}
        if (!I18n.isRtl('ar') || I18n.isRtl('en'))
            throw new Error('RTL detection mismatch');
        print('I18N_ALL_TEN_OK:' + keys.size);
        """
        res = _run_gjs_script(script)
        self.assertEqual(res.returncode, 0, f"GJS i18n check failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("I18N_ALL_TEN_OK:", res.stdout)

    def test_unified_2d_board_geometry_slots_and_hit_testing_in_gjs(self):
        script = f"""
        import * as TileLayout from 'file://{os.path.join(MENU_DIR, "tileLayout.js")}';

        // 1. Cell presets 0..4 and default 72x82px (distinct loose vs compact hierarchy)
        const cDef = TileLayout.getCellDimensions(2);
        if (cDef.w !== 72 || cDef.h !== 82 || TileLayout.CELL_GAP !== 10)
            throw new Error('Default level 2 cell mismatch: ' + JSON.stringify(cDef));
        if (TileLayout.getCellDimensions(0).w !== 58 || TileLayout.getCellDimensions(4).w !== 90)
            throw new Error('Cell preset bounds mismatch');
        if (TileLayout.getLooseAppIconSize(72) !== 46)
            throw new Error('Loose app icon size mismatch');
        const gIcon = TileLayout.getCompactGroupIconSize(67, 63);
        if (gIcon < 30 || gIcon > 34)
            throw new Error('Compact group icon size out of 30..34 range: ' + gIcon);

        const dLoose = TileLayout.getBoardItemDimensions('app', '1x1', 72, 82, 10);
        const d2x2 = TileLayout.getBoardItemDimensions('group', '2x2', 72, 82, 10);
        const d3x3 = TileLayout.getBoardItemDimensions('group', '3x3', 72, 82, 10);
        const d4x3 = TileLayout.getBoardItemDimensions('group', '4x3', 72, 82, 10);
        if (dLoose.width !== 72 || dLoose.height !== 82 ||
            d2x2.width !== 154 || d2x2.height !== 174 ||
            d3x3.width !== 236 || d3x3.height !== 266 ||
            d4x3.width !== 318 || d4x3.height !== 266)
            throw new Error('Board item dimension mismatch');

        // 2. computeCompactGroupSlots <= capacity vs > capacity (2x2 capacity=4)
        const apps4 = [{{ id: 'a1' }}, {{ id: 'a2' }}, {{ id: 'a3' }}, {{ id: 'a4' }}];
        const sUnder = TileLayout.computeCompactGroupSlots(apps4, '2x2');
        if (sUnder.capacity !== 4 || sUnder.hasOverflowCluster || sUnder.directApps.length !== 4 || sUnder.overflowApps.length !== 0)
            throw new Error('<=capacity slots mismatch: ' + JSON.stringify(sUnder));

        const apps7 = [{{ id: 'a1' }}, {{ id: 'a2' }}, {{ id: 'a3' }}, {{ id: 'a4' }}, {{ id: 'a5' }}, {{ id: 'a6' }}, {{ id: 'a7' }}];
        const sOver = TileLayout.computeCompactGroupSlots(apps7, '2x2');
        if (!sOver.hasOverflowCluster || sOver.directApps.length !== 3 || sOver.overflowCount !== 4 || sOver.clusterApps.length !== 4)
            throw new Error('>capacity slots mismatch: ' + JSON.stringify(sOver));

        const apps10 = [...apps7, {{ id: 'a8' }}, {{ id: 'a9' }}, {{ id: 'a10' }}];
        const s3x3 = TileLayout.computeCompactGroupSlots(apps10, '3x3');
        if (!s3x3.hasOverflowCluster || s3x3.directApps.length !== 8 || s3x3.overflowCount !== 2)
            throw new Error('3x3 overflow slots mismatch: ' + JSON.stringify(s3x3));

        // 3. computeUnifiedBoardRects + placeBoardItemAt free 2D moves with downward push
        const initialItems = [
            {{ type: 'app', id: 'app1', col: 0, row: 0 }},
            {{ type: 'app', id: 'app2', col: 1, row: 0 }},
            {{ type: 'group', id: 'games', cardSize: '2x2', col: 0, row: 1, apps: [] }},
            {{ type: 'group', id: 'office', cardSize: '2x2', col: 2, row: 1, apps: [] }},
        ];
        const packedRtl = TileLayout.computeUnifiedBoardRects(initialItems, 78, 84, 10, 10, true);
        const app1Rtl = packedRtl.rects.find(r => r.item.id === 'app1');
        if (app1Rtl.width !== 78 || app1Rtl.height !== 84 || app1Rtl.x !== (packedRtl.totalWidth - 78))
            throw new Error('RTL col 0 loose app position wrong: ' + JSON.stringify(app1Rtl));

        const movedItems = TileLayout.placeBoardItemAt(initialItems, 'app:app1', 0, 1, 10);
        const movedApp1 = movedItems.find(it => it.id === 'app1');
        const pushedGames = movedItems.find(it => it.id === 'games');
        const untouchedOffice = movedItems.find(it => it.id === 'office');
        if (movedApp1.col !== 0 || movedApp1.row !== 1 || pushedGames.row < 2 || untouchedOffice.col !== 2 || untouchedOffice.row !== 1)
            throw new Error('placeBoardItemAt must push only colliding items downward: ' + JSON.stringify(movedItems));

        // Ensure expanding horizontally beyond column 9 grows totalCols without overlap
        const grown = TileLayout.placeBoardItemAt(initialItems, 'group:games', 10, 0, 10);
        const packedGrown = TileLayout.computeUnifiedBoardRects(grown, 78, 84, 10, 10, false);
        if (packedGrown.totalCols < 12)
            throw new Error('Unified board must expand horizontally when placing beyond minCols: ' + packedGrown.totalCols);

        // 4. hitTestUnifiedBoard: merge apps, add to group, place empty 2D cell
        const packedLtr = TileLayout.computeUnifiedBoardRects(initialItems, 78, 84, 10, 10, false);
        const hitMerge = TileLayout.hitTestUnifiedBoard({{
            localX: 127,
            localY: 42,
            boardCols: packedLtr.totalCols,
            totalWidth: packedLtr.totalWidth,
            cellW: 78,
            cellH: 84,
            gap: 10,
            itemRects: packedLtr.rects,
            dragKind: 'board-app',
            dragPayload: {{ itemType: 'app', itemId: 'app1' }},
            isRtl: false,
        }});
        if (!hitMerge || hitMerge.action !== 'merge-apps-into-group' || hitMerge.targetAppId !== 'app2')
            throw new Error('hitTestUnifiedBoard failed center merge detection: ' + JSON.stringify(hitMerge));

        const hitAddGrp = TileLayout.hitTestUnifiedBoard({{
            localX: 40,
            localY: 140,
            boardCols: packedLtr.totalCols,
            totalWidth: packedLtr.totalWidth,
            cellW: 78,
            cellH: 84,
            gap: 10,
            itemRects: packedLtr.rects,
            dragKind: 'board-app',
            dragPayload: {{ itemType: 'app', itemId: 'app1' }},
            isRtl: false,
        }});
        if (!hitAddGrp || hitAddGrp.action !== 'add-to-group' || hitAddGrp.targetGroupId !== 'games')
            throw new Error('hitTestUnifiedBoard failed add-to-group detection: ' + JSON.stringify(hitAddGrp));

        const hitEmpty = TileLayout.hitTestUnifiedBoard({{
            localX: 460,
            localY: 30,
            boardCols: packedLtr.totalCols,
            totalWidth: packedLtr.totalWidth,
            cellW: 78,
            cellH: 84,
            gap: 10,
            itemRects: packedLtr.rects,
            dragKind: 'board-app',
            dragPayload: {{ itemType: 'app', itemId: 'app1' }},
            isRtl: false,
        }});
        if (!hitEmpty || hitEmpty.action !== 'place-board-item' || hitEmpty.targetCol !== 5 || hitEmpty.targetRow !== 0 || !hitEmpty.previewRect)
            throw new Error('hitTestUnifiedBoard failed empty cell snap: ' + JSON.stringify(hitEmpty));

        // 5. Edge resize (12px inner / 6px outer rim) & window clamping math
        const pr = {{ x: 100, y: 80, width: 1140, height: 680 }};
        if (TileLayout.detectResizeEdge(104, 84, pr, true, 12, 6) !== 'corner')
            throw new Error('RTL corner detection failed');
        if (TileLayout.detectResizeEdge(95, 400, pr, true, 12, 6) !== 'side')
            throw new Error('Outer 5px glow rim must still trigger side resize edge cleanly');
        if (TileLayout.detectResizeEdge(111, 400, pr, true, 12, 6) !== 'side')
            throw new Error('Inner 11px edge must trigger side resize edge cleanly');
        if (TileLayout.detectResizeEdge(120, 400, pr, true, 12, 6) !== null)
            throw new Error('Interior area outside edgePx must return null');
        const freeGeom = TileLayout.computeMenuGeometry({{ workAreaWidth: 1366, workAreaHeight: 768, showAllAppsSidebar: true, desiredWidth: 743, desiredHeight: 591 }});
        if (freeGeom.totalWidth !== 743 || freeGeom.totalHeight !== 591)
            throw new Error('Free pixel resize snapped unexpectedly');

        print('UNIFIED_2D_BOARD_GEOMETRY_OK');
        """
        res = _run_gjs_script(script)
        self.assertEqual(res.returncode, 0, f"GJS tileLayout test failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("UNIFIED_2D_BOARD_GEOMETRY_OK", res.stdout)

    def test_unified_board_appdata_groups_filter_and_search_in_gjs(self):
        script = f"""
        import GLib from 'gi://GLib';
        import * as Search from 'file://{os.path.join(MENU_DIR, "searchEngine.js")}';
        import * as AppData from 'file://{os.path.join(MENU_DIR, "appData.js")}';

        // 1. Multilingual Search
        const searchApps = [
            {{
                id: 'org.gnome.Settings.desktop',
                name: 'إعدادات النظام',
                untranslatedName: 'Settings',
                description: 'Configure your desktop',
                keywords: ['preferences', 'تحكم'],
                exec: 'gnome-control-center',
            }},
            {{
                id: 'com.example.Cafe.desktop',
                name: 'Café Résumé',
                untranslatedName: 'Café Résumé',
                description: 'French diacritics + C++',
                keywords: ['cpp'],
                exec: 'cafe-app',
            }},
            {{
                id: 'com.tencent.WeChat.desktop',
                name: '微信 WeChat',
                untranslatedName: 'WeChat',
                description: 'ёжик чат',
                keywords: [],
                exec: 'wechat',
            }},
        ];
        if (Search.searchAppRecords(searchApps, 'اعدادات')[0]?.id !== 'org.gnome.Settings.desktop')
            throw new Error('Arabic hamza search failed');
        if (Search.searchAppRecords(searchApps, 'cafe resume')[0]?.id !== 'com.example.Cafe.desktop')
            throw new Error('Latin diacritic stripping failed');
        if (Search.searchAppRecords(searchApps, '微信')[0]?.id !== 'com.tencent.WeChat.desktop')
            throw new Error('Chinese search failed');

        // 2. Strict Games Exclusion Filter & Unified Default Board
        const testApps = [
            {{ id: 'org.mozilla.firefox.desktop', name: 'Firefox', untranslatedName: 'Firefox', categories: ['Network', 'WebBrowser'], exec: 'firefox' }},
            {{ id: 'org.gnome.Nautilus.desktop', name: 'Files', untranslatedName: 'Files', categories: ['System'], exec: 'nautilus' }},
            {{ id: 'org.gnome.Software.desktop', name: 'Software', untranslatedName: 'Software', categories: ['PackageManager'], exec: 'gnome-software' }},
            {{ id: 'org.gnome.TextEditor.desktop', name: 'Text Editor', untranslatedName: 'Text Editor', categories: ['Utility'], exec: 'gnome-text-editor' }},
            {{ id: 'com.usebottles.bottles.desktop', name: 'القوارير (Bottles)', untranslatedName: 'Bottles', categories: ['Utility', 'Game'], exec: 'bottles' }},
            {{ id: 'net.davidotek.pupgui2.desktop', name: 'ProtonUp-Qt', untranslatedName: 'ProtonUp-Qt', categories: ['Utility', 'Game'], exec: 'pupgui2' }},
            {{ id: 'io.github.dvlv.boxbuddyrs.desktop', name: 'BoxBuddy', untranslatedName: 'BoxBuddy', categories: ['System', 'Game'], exec: 'boxbuddy' }},
            {{ id: 'net.lutris.Lutris.desktop', name: 'Lutris', untranslatedName: 'Lutris', categories: ['Game'], exec: 'lutris' }},
            {{ id: 'com.heroicgameslauncher.hgl.desktop', name: 'Heroic', untranslatedName: 'Heroic Games Launcher', categories: ['Game'], exec: 'heroic' }},
            {{ id: 'sadeem-windows-exe-handler.desktop', name: 'مشغّل برامج ويندوز', untranslatedName: 'Sadeem Windows Runner', categories: ['System', 'Game'], exec: 'sadeem-windows-exe-handler' }},
            {{ id: 'sadeem-win-4976f9252979.desktop', name: 'Generals Zero Hour', untranslatedName: 'Generals Zero Hour', categories: ['Game'], exec: '/usr/bin/sadeem-windows-exe-handler --launch-installed "game.exe"' }},
            {{ id: 'net.supertuxkart.SuperTuxKart.desktop', name: 'SuperTuxKart', untranslatedName: 'SuperTuxKart', categories: ['Game', 'RacingGame'], exec: 'supertuxkart' }},
            {{ id: 'libreoffice-writer.desktop', name: 'LibreOffice Writer', untranslatedName: 'LibreOffice Writer', categories: ['Office'], exec: 'libreoffice --writer' }},
            {{ id: 'org.telegram.desktop.desktop', name: 'Telegram', untranslatedName: 'Telegram', categories: ['InstantMessaging'], exec: 'telegram' }},
        ];

        const initBoard = AppData.computeTileBoardModel({{ records: testApps, layoutJson: '{{}}', autoCategorize: true }});
        const loose = initBoard.items.filter(it => it.type === 'app');
        if (loose.length !== 4 || loose[0].id !== 'org.mozilla.firefox.desktop')
            throw new Error('Default 4 loose core apps mismatch: ' + JSON.stringify(loose));

        // Smart group 'sadeem' has 0 apps -> omitted cleanly; office/games/social should be '2x2' foldable cards
        if (initBoard.groups.some(g => g.id === 'sadeem'))
            throw new Error('Empty smart group should be hidden');
        const gamesGrp = initBoard.groups.find(g => g.id === 'games');
        if (!gamesGrp || gamesGrp.cardSize !== '2x2')
            throw new Error('Games 2x2 foldable group card missing');

        const gameIds = new Set(gamesGrp.apps.map(a => a.id));
        if (gameIds.has('com.usebottles.bottles.desktop') ||
            gameIds.has('net.davidotek.pupgui2.desktop') ||
            gameIds.has('io.github.dvlv.boxbuddyrs.desktop') ||
            gameIds.has('net.lutris.Lutris.desktop') ||
            gameIds.has('com.heroicgameslauncher.hgl.desktop') ||
            gameIds.has('sadeem-windows-exe-handler.desktop'))
            throw new Error('Game utility launchers leaked into games: ' + JSON.stringify([...gameIds]));

        if (!gameIds.has('sadeem-win-4976f9252979.desktop') || !gameIds.has('net.supertuxkart.SuperTuxKart.desktop'))
            throw new Error('Real games missing from games: ' + JSON.stringify([...gameIds]));

        // 3. Merge two loose apps into a new foldable 2x2 group
        const merged = AppData.mutateLayoutMergeAppsIntoGroup('{{}}', {{
            targetAppId: 'org.gnome.Nautilus.desktop',
            sourceAppId: 'org.gnome.Software.desktop',
            targetCol: 1,
            targetRow: 0,
            name: 'النظام',
            records: testApps,
            autoCategorize: true,
        }});
        if (!merged.groupId)
            throw new Error('Merge two apps failed to create group');

        let lay = AppData.mutateLayoutAddAppToGroupItem(merged.layoutJson, {{
            targetGroupId: merged.groupId,
            appId: 'org.gnome.TextEditor.desktop',
            removeLoose: true,
            records: testApps,
        }});
        let board = AppData.computeTileBoardModel({{ records: testApps, layoutJson: lay, autoCategorize: true }});
        const customGrp = board.groups.find(g => g.id === merged.groupId);
        if (!customGrp || customGrp.name !== 'النظام' || customGrp.apps.length !== 3)
            throw new Error('Merged + added app group state invalid: ' + JSON.stringify(customGrp));
        if (board.items.some(it => it.type === 'app' && it.id === 'org.gnome.TextEditor.desktop'))
            throw new Error('TextEditor should be removed from loose items after dropping into group');

        // 4. Resize group card 2x2 -> 3x3 & extract app from smart group back to free board
        lay = AppData.mutateLayoutSetGroupCardSize(lay, {{
            groupId: merged.groupId,
            cardSize: '3x3',
            records: testApps,
        }});
        lay = AppData.mutateLayoutExtractAppToBoard(lay, {{
            groupId: 'games',
            appId: 'net.supertuxkart.SuperTuxKart.desktop',
            targetCol: 5,
            targetRow: 0,
            records: testApps,
        }});
        board = AppData.computeTileBoardModel({{ records: testApps, layoutJson: lay, autoCategorize: true }});
        const resizedCustom = board.groups.find(g => g.id === merged.groupId);
        const gamesAfterExtract = board.groups.find(g => g.id === 'games');
        const extractedLoose = board.items.find(it => it.type === 'app' && it.id === 'net.supertuxkart.SuperTuxKart.desktop');
        if (resizedCustom?.cardSize !== '3x3')
            throw new Error('Group card resize to 3x3 failed');
        if (!extractedLoose || extractedLoose.col !== 5 || extractedLoose.row !== 0)
            throw new Error('Extracted app missing on free board at (5,0): ' + JSON.stringify(extractedLoose));
        if (gamesAfterExtract.apps.some(a => a.id === 'net.supertuxkart.SuperTuxKart.desktop'))
            throw new Error('Smart group re-added extracted app despite autoCategorize=true');

        // 5. pinLooseApp auto-placement (targetCol=null, targetRow=null) finds first empty 1x1 cell (4, 0) without shifting Firefox or sadeem
        const ptyxisApp = {{ id: 'org.gnome.Ptyxis.desktop', name: 'Ptyxis', untranslatedName: 'Ptyxis', categories: ['System', 'TerminalEmulator'], exec: 'ptyxis' }};
        const sadeemApp = {{ id: 'sadeem-welcome.desktop', name: 'Sadeem Welcome', untranslatedName: 'Sadeem Welcome', categories: ['System'], exec: 'sadeem-welcome' }};
        const pinApps = [...testApps, sadeemApp, ptyxisApp];
        const pinnedLay = AppData.mutateLayoutPlaceBoardItem('{{}}', {{
            itemType: 'app',
            itemId: 'org.gnome.Ptyxis.desktop',
            targetCol: null,
            targetRow: null,
            records: pinApps,
            autoCategorize: true,
        }});
        const pinnedBoard = AppData.computeTileBoardModel({{ records: pinApps, layoutJson: pinnedLay, autoCategorize: true }});
        const ptyxisLoose = pinnedBoard.items.find(it => it.type === 'app' && it.id === 'org.gnome.Ptyxis.desktop');
        const firefoxLoose = pinnedBoard.items.find(it => it.type === 'app' && it.id === 'org.mozilla.firefox.desktop');
        const sadeemGrpAfterPin = pinnedBoard.items.find(it => it.type === 'group' && it.id === 'sadeem');
        if (!ptyxisLoose || ptyxisLoose.col !== 4 || ptyxisLoose.row !== 0)
            throw new Error('Auto-pinned app expected at first free cell (4,0), got: ' + JSON.stringify(ptyxisLoose));
        if (!firefoxLoose || firefoxLoose.col !== 0 || firefoxLoose.row !== 0)
            throw new Error('Firefox shifted unexpectedly after auto-pin: ' + JSON.stringify(firefoxLoose));
        if (!sadeemGrpAfterPin || sadeemGrpAfterPin.col !== 0 || sadeemGrpAfterPin.row !== 1)
            throw new Error('Sadeem group shifted unexpectedly after auto-pin: ' + JSON.stringify(sadeemGrpAfterPin));

        // 6. Disabling autoCategorize hides smart groups even after saving layout-config, preserves custom groups & restores positions on re-enable
        const gamesBeforeOff = board.groups.find(g => g.id === 'games');
        if (!gamesBeforeOff)
            throw new Error('Expected games smart group before disabling autoCategorize');
        const hiddenBoard = AppData.computeTileBoardModel({{ records: testApps, layoutJson: lay, autoCategorize: false }});
        if (hiddenBoard.items.some(it => it.type === 'group' && it.isSmart) ||
            hiddenBoard.groups.some(g => g.isSmart) ||
            hiddenBoard.allGroups.some(g => g.isSmart))
            throw new Error('Smart groups must be hidden across items/groups/allGroups when autoCategorize=false');
        if (!hiddenBoard.groups.some(g => g.id === merged.groupId && !g.isSmart))
            throw new Error('Custom user groups must remain visible when autoCategorize=false');
        const restoredBoard = AppData.computeTileBoardModel({{ records: testApps, layoutJson: lay, autoCategorize: true }});
        const gamesRestored = restoredBoard.groups.find(g => g.id === 'games');
        if (!gamesRestored || gamesRestored.col !== gamesBeforeOff.col || gamesRestored.row !== gamesBeforeOff.row)
            throw new Error('Smart groups must restore at their exact saved coordinates when autoCategorize is re-enabled');

        // 6b. disabledSmartGroups hides only specified smart group(s) and restores at exact saved coordinates + clears removed_groups on restore
        const oneDisabled = AppData.computeTileBoardModel({{ records: testApps, layoutJson: lay, autoCategorize: true, disabledSmartGroups: ['games'] }});
        if (oneDisabled.groups.some(g => g.id === 'games'))
            throw new Error('Disabled smart group games must be hidden');
        if (!oneDisabled.groups.some(g => g.id === 'office'))
            throw new Error('Non-disabled smart group office must remain visible');
        const restoredOne = AppData.computeTileBoardModel({{ records: testApps, layoutJson: lay, autoCategorize: true, disabledSmartGroups: [] }});
        const gamesReEnabled = restoredOne.groups.find(g => g.id === 'games');
        if (!gamesReEnabled || gamesReEnabled.col !== gamesBeforeOff.col || gamesReEnabled.row !== gamesBeforeOff.row)
            throw new Error('Individually re-enabled smart group must restore at exact saved coordinates');
        const deletedGamesLay = AppData.mutateLayoutDeleteGroup(lay, 'games', testApps, true);
        const restoredGamesLay = AppData.mutateLayoutRestoreSmartGroup(deletedGamesLay, 'games', testApps, true);
        const restoredFromRemoved = AppData.computeTileBoardModel({{ records: testApps, layoutJson: restoredGamesLay, autoCategorize: true }});
        if (!restoredFromRemoved.groups.some(g => g.id === 'games'))
            throw new Error('mutateLayoutRestoreSmartGroup failed to restore manually removed smart group');

        // 7. Seen apps user-scoped isolation check
        const seenRes = AppData.reconcileSeenApps([
            {{ id: 'sys.desktop', filename: '/usr/share/applications/sys.desktop', homeDir: '/home/u', mtimeSec: 100 }},
            {{ id: 'user.desktop', filename: '/home/u/.local/share/applications/user.desktop', homeDir: '/home/u', mtimeSec: 200 }},
        ], null, 500);
        if (Object.keys(seenRes.state.apps).length !== 1 || seenRes.state.apps['user.desktop'] !== 200)
            throw new Error('reconcileSeenApps isolation failed');

        // 8. Independent most-used-count & recently-installed-count (1..4) in AppDataManager
        const homeDir = GLib.get_home_dir();
        const fiveApps = [
            {{ id: 'a1.desktop', get_id: () => 'a1.desktop', get_name: () => 'A1', get_display_name: () => 'A1', get_description: () => '', get_categories: () => 'Utility;', get_executable: () => 'a1', get_filename: () => homeDir + '/.local/share/applications/a1.desktop', should_show: () => true }},
            {{ id: 'a2.desktop', get_id: () => 'a2.desktop', get_name: () => 'A2', get_display_name: () => 'A2', get_description: () => '', get_categories: () => 'Utility;', get_executable: () => 'a2', get_filename: () => homeDir + '/.local/share/applications/a2.desktop', should_show: () => true }},
            {{ id: 'a3.desktop', get_id: () => 'a3.desktop', get_name: () => 'A3', get_display_name: () => 'A3', get_description: () => '', get_categories: () => 'Utility;', get_executable: () => 'a3', get_filename: () => homeDir + '/.local/share/applications/a3.desktop', should_show: () => true }},
            {{ id: 'a4.desktop', get_id: () => 'a4.desktop', get_name: () => 'A4', get_display_name: () => 'A4', get_description: () => '', get_categories: () => 'Utility;', get_executable: () => 'a4', get_filename: () => homeDir + '/.local/share/applications/a4.desktop', should_show: () => true }},
            {{ id: 'a5.desktop', get_id: () => 'a5.desktop', get_name: () => 'A5', get_display_name: () => 'A5', get_description: () => '', get_categories: () => 'Utility;', get_executable: () => 'a5', get_filename: () => homeDir + '/.local/share/applications/a5.desktop', should_show: () => true }},
        ];
        const mgrCounts = new AppData.AppDataManager({{
            settings: {{
                get_string: () => '{{}}',
                set_string: () => true,
                get_boolean: () => true,
                get_int: k => (k === 'most-used-count' ? 2 : (k === 'recently-installed-count' ? 4 : 3)),
            }},
            appSystem: {{ get_installed: () => fiveApps, lookup_app: () => null }},
            appUsage: {{ get_most_used: () => fiveApps }},
        }});
        mgrCounts._seenState = {{ apps: {{ 'a1.desktop': 10, 'a2.desktop': 20, 'a3.desktop': 30, 'a4.desktop': 40, 'a5.desktop': 50 }} }};
        const mostRes = mgrCounts.getMostUsedRecords();
        const recentRes = mgrCounts.getRecentlyInstalledRecords();
        if (mostRes.length !== 2)
            throw new Error('Expected most-used-count=2 to limit to 2, got ' + mostRes.length);
        if (recentRes.length !== 4)
            throw new Error('Expected recently-installed-count=4 to limit to 4, got ' + recentRes.length);
        mgrCounts.destroy();

        print('GJS_UNIFIED_APPDATA_OK');
        """
        res = _run_gjs_script(script)
        self.assertEqual(res.returncode, 0, f"GJS unified board test failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("GJS_UNIFIED_APPDATA_OK", res.stdout)

    def test_extension_app_data_manager_signature_and_open_resilience(self):
        ext_path = os.path.join(MENU_DIR, "extension.js")
        with open(ext_path, "r", encoding="utf-8") as f:
            ext_code = f.read()

        m_call = re.search(r"new\s+AppDataManager\s*\(([\s\S]*?)\);", ext_code)
        self.assertIsNotNone(m_call, "AppDataManager instantiation missing in extension.js")
        call_args = m_call.group(1).strip()
        self.assertTrue(call_args.startswith("{"), f"extension.js must pass a single options object to AppDataManager, got: {call_args}")
        self.assertIn("settings:", call_args)
        self.assertIn("appSystem:", call_args)
        self.assertIn("appUsage:", call_args)

        ui_path = os.path.join(MENU_DIR, "menuUI.js")
        with open(ui_path, "r", encoding="utf-8") as f:
            ui_code = f.read()
        m_open = re.search(r"_onMenuOpened\(\)\s*\{([\s\S]*?)\n    \}", ui_code)
        self.assertIsNotNone(m_open, "_onMenuOpened() method missing in menuUI.js")
        open_body = m_open.group(1)
        idx_theme = open_body.find("this._syncTheme()")
        idx_geom = open_body.find("this._applyGeometry()")
        idx_render = open_body.find("this.renderCurrentView()")
        self.assertGreater(idx_theme, 0)
        self.assertGreater(idx_geom, idx_theme)
        self.assertGreater(idx_render, idx_geom, "_syncTheme and _applyGeometry must run before renderCurrentView()")
        self.assertIn("console.error('[SadeemMenu] renderCurrentView failed:'", open_body)

        script = f"""
        import * as AppData from 'file://{os.path.join(MENU_DIR, "appData.js")}';

        const mockSettings = {{
            get_string: () => '{{}}',
            set_string: () => true,
            get_boolean: () => true,
            get_int: () => 3,
        }};
        const fakeAppInfo = {{
            get_id: () => 'org.example.Demo.desktop',
            get_name: () => 'Demo App',
            get_display_name: () => 'Demo App',
            get_description: () => 'Demo description',
            get_categories: () => 'Utility;',
            get_executable: () => 'demo-app',
            get_filename: () => '/usr/share/applications/org.example.Demo.desktop',
            should_show: () => true,
        }};
        const mockAppSystem = {{
            get_installed: () => [fakeAppInfo],
            lookup_app: id => id === 'org.example.Demo.desktop' ? {{
                get_id: () => id,
                get_name: () => 'Demo App',
                get_app_info: () => fakeAppInfo,
                launch: () => true,
            }} : null,
        }};
        const mockAppUsage = {{ get_most_used: () => [] }};

        // 1. Options-object constructor signature (extension.js)
        const mgrOpts = new AppData.AppDataManager({{
            settings: mockSettings,
            appSystem: mockAppSystem,
            appUsage: mockAppUsage,
        }});
        const recsOpts = mgrOpts.getInstalledRecords();
        if (recsOpts.length !== 1 || recsOpts[0].id !== 'org.example.Demo.desktop')
            throw new Error('AppDataManager({{ settings, appSystem, appUsage }}) getInstalledRecords failed');

        // 2. Legacy 2-arg constructor signature compatibility
        const mgrLegacy = new AppData.AppDataManager(mockSettings, {{
            appSystem: mockAppSystem,
            appUsage: mockAppUsage,
        }});
        const recsLegacy = mgrLegacy.getInstalledRecords();
        if (recsLegacy.length !== 1 || recsLegacy[0].id !== 'org.example.Demo.desktop')
            throw new Error('Legacy AppDataManager(settings, opts) compatibility failed');

        // 3. Fallback when appSystem is null/undefined (Gio.AppInfo.get_all)
        const mgrFallback = new AppData.AppDataManager({{ settings: mockSettings }});
        const recsFallback = mgrFallback.getInstalledRecords();
        if (!Array.isArray(recsFallback))
            throw new Error('AppDataManager fallback getInstalledRecords must return an array');

        mgrOpts.destroy();
        mgrLegacy.destroy();
        mgrFallback.destroy();
        print('APPDATA_MANAGER_CONSTRUCTOR_OK');
        """
        res = _run_gjs_script(script)
        self.assertEqual(res.returncode, 0, f"GJS AppDataManager constructor check failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("APPDATA_MANAGER_CONSTRUCTOR_OK", res.stdout)

    def test_resize_handle_fixed_layout_bounds_in_gjs(self):
        script = f"""
        import * as ResizeMgr from 'file://{os.path.join(MENU_DIR, "resizeManager.js")}';

        const rtl = ResizeMgr.computeResizeHandleBounds(1140, 680, true);
        if (rtl.side.x !== 0 || rtl.corner.x !== 0 || rtl.top.y !== 0 || rtl.corner.y !== 0)
            throw new Error('RTL resize handle bounds mismatch: ' + JSON.stringify(rtl));
        if (rtl.top.x !== 14 || rtl.top.width !== 1126 || rtl.top.height !== 6 ||
            rtl.side.y !== 14 || rtl.side.width !== 6 || rtl.side.height !== 666 ||
            rtl.corner.width !== 14 || rtl.corner.height !== 14)
            throw new Error('RTL resize handle dimensions mismatch: ' + JSON.stringify(rtl));

        const ltr = ResizeMgr.computeResizeHandleBounds(1140, 680, false);
        if (ltr.side.x !== 1134 || ltr.corner.x !== 1126 || ltr.top.y !== 0 || ltr.corner.y !== 0)
            throw new Error('LTR resize handle bounds mismatch: ' + JSON.stringify(ltr));
        if (ltr.top.x !== 0 || ltr.top.width !== 1126 || ltr.top.height !== 6 ||
            ltr.side.y !== 14 || ltr.side.width !== 6 || ltr.side.height !== 666 ||
            ltr.corner.width !== 14 || ltr.corner.height !== 14)
            throw new Error('LTR resize handle dimensions mismatch: ' + JSON.stringify(ltr));

        print('RESIZE_FIXED_LAYOUT_BOUNDS_OK');
        """
        res = _run_gjs_script(script)
        self.assertEqual(res.returncode, 0, f"GJS resize handle bounds test failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("RESIZE_FIXED_LAYOUT_BOUNDS_OK", res.stdout)

    def test_sadeem_system_menu_settings_page_and_translations(self):
        sys_bin = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-system")
        self.assertTrue(os.path.isfile(sys_bin))

        with tempfile.TemporaryDirectory() as tmpdir:
            py_compile.compile(sys_bin, cfile=os.path.join(tmpdir, "sadeem_system.pyc"), doraise=True)

            # Compile repo schema strictly to cross-check every bound key
            dest_xml = os.path.join(tmpdir, os.path.basename(SCHEMA_FILE))
            with open(SCHEMA_FILE, "rb") as src, open(dest_xml, "wb") as dst:
                dst.write(src.read())
            comp = subprocess.run(["glib-compile-schemas", "--strict", tmpdir], capture_output=True, text=True)
            self.assertEqual(comp.returncode, 0, f"Schema compile failed:\n{comp.stderr}")
            schema_src = Gio.SettingsSchemaSource.new_from_directory(tmpdir, None, False)
            schema = schema_src.lookup("org.sadeem.menu", False)
            self.assertIsNotNone(schema)
            schema_keys = set(schema.list_keys())

        with open(sys_bin, "r", encoding="utf-8") as f:
            sys_code = f.read()

        self.assertNotIn("tile-columns", sys_code, "sadeem-system must never expose deprecated tile-columns key")
        self.assertNotIn("Adw.ViewSwitcher", sys_code, "sadeem-system must use Adw.NavigationSplitView instead of Adw.ViewSwitcher")
        self.assertIn("Adw.NavigationSplitView", sys_code)
        self.assertIn("Adw.NavigationPage", sys_code)
        self.assertIn("navigation-sidebar", sys_code)
        self.assertIn("Adw.Breakpoint", sys_code)
        self.assertIn("max-width: 680sp", sys_code)
        self.assertIn("set_show_content(True)", sys_code)
        self.assertIn("build_menu_page", sys_code)
        self.assertIn("Adw.PreferencesPage", sys_code)
        self.assertIn("Adw.PreferencesGroup", sys_code)
        self.assertIn("Adw.ExpanderRow", sys_code)
        self.assertIn("show_enable_switch=True", sys_code)
        self.assertIn("Adw.SpinRow", sys_code)
        self.assertIn("Adw.ComboRow", sys_code)
        self.assertIn("Gtk.Scale", sys_code)
        self.assertIn("Adw.AlertDialog", sys_code)
        self.assertIn("_bind_menu_scale_row(settings, \"menu-opacity\", opacity_scale, opacity_lbl, 10, 100, syncing)", sys_code)
        self.assertNotIn("_bind_menu_spin_row(settings, \"menu-width\"", sys_code)
        self.assertNotIn("_bind_menu_spin_row(settings, \"menu-height\"", sys_code)
        self.assertIn("most-used-count", sys_code)
        self.assertIn("recently-installed-count", sys_code)

        loader = importlib.machinery.SourceFileLoader("sadeem_system_mod", sys_bin)
        spec = importlib.util.spec_from_loader("sadeem_system_mod", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)

        # CLI --page=menu and --page menu routing
        self.assertEqual(mod.parse_sadeem_system_cli_args(["sadeem-system", "--page=menu"]), ("menu", False))
        self.assertEqual(mod.parse_sadeem_system_cli_args(["sadeem-system", "--page", "menu"]), ("menu", False))
        self.assertEqual(mod.parse_sadeem_system_cli_args(["sadeem-system", "--tab=menu"]), ("menu", False))
        self.assertEqual(mod.parse_sadeem_system_cli_args(["sadeem-system"]), ("updates", False))
        self.assertIn("menu", mod.SADEEM_SYSTEM_VALID_TABS)

        # Bound keys match schema cleanly without tile-columns
        bound = set(mod.SADEEM_MENU_BOUND_KEYS)
        self.assertTrue(bound.issubset(schema_keys), f"Unknown GSettings keys in sadeem-system: {bound - schema_keys}")
        self.assertNotIn("tile-columns", bound)
        self.assertIn("menu-opacity", bound)
        self.assertIn("most-used-count", bound)
        self.assertIn("recently-installed-count", bound)
        self.assertIn("disabled-smart-groups", bound)
        self.assertIn("bind-super-key", bound)

        # All 10 locales contain complete menu_* and tab_menu translations
        expected_langs = ("ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh")
        en_keys = set(mod.TRANSLATIONS["en"].keys())
        menu_keys = {k for k in en_keys if k.startswith("menu_") or k == "tab_menu"}
        self.assertGreaterEqual(len(menu_keys), 40)
        for lang in expected_langs:
            self.assertIn(lang, mod.TRANSLATIONS)
            loc = mod.TRANSLATIONS[lang]
            for k in en_keys:
                val = loc.get(k)
                self.assertTrue(bool(val), f"Missing or empty key '{k}' in sadeem-system locale '{lang}'")
            sizes = loc.get("menu_icon_sizes")
            self.assertIsInstance(sizes, list)
            self.assertEqual(len(sizes), 5, f"menu_icon_sizes must have 5 levels in '{lang}'")
            for label in sizes:
                self.assertTrue(isinstance(label, str) and bool(label.strip()))

    def test_distro_defaults_replace_arcmenu_with_sadeem_menu(self):
        recipe_path = os.path.join(REPO_ROOT, "recipes/recipe.yml")
        with open(recipe_path, "r", encoding="utf-8") as f:
            recipe = f.read()
        self.assertIn("glib-compile-schemas /usr/share/glib-2.0/schemas", recipe)
        self.assertIn("dconf update", recipe)
        self.assertNotIn("arcmenu", recipe.lower())

        defaults_path = os.path.join(REPO_ROOT, "files/system/etc/dconf/db/local.d/01-sadeem-defaults")
        with open(defaults_path, "r", encoding="utf-8") as f:
            defaults = f.read()
        self.assertNotIn("arcmenu", defaults.lower())
        self.assertIn("'sadeem-menu@sadeem.os'", defaults)

        ext_dconf_path = os.path.join(REPO_ROOT, "files/system/etc/dconf/db/local.d/02-sadeem-extensions")
        with open(ext_dconf_path, "r", encoding="utf-8") as f:
            ext_dconf = f.read()
        self.assertNotIn("arcmenu", ext_dconf.lower())

        override_path = os.path.join(REPO_ROOT, "files/system/usr/share/glib-2.0/schemas/zz-99-sadeem-wallpaper.gschema.override")
        with open(override_path, "r", encoding="utf-8") as f:
            override_txt = f.read()
        self.assertNotIn("arcmenu", override_txt.lower())
        self.assertIn("'sadeem-menu@sadeem.os'", override_txt)

        helper_ext = os.path.join(REPO_ROOT, "files/system/usr/share/gnome-shell/extensions/sadeem-desktop-helper@sadeem.os/extension.js")
        with open(helper_ext, "r", encoding="utf-8") as f:
            self.assertNotIn("arcmenu", f.read().lower())

        self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, "files/system/usr/share/gnome-shell/extensions/arcmenu@arcmenu.com")))
        self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, "files/system/usr/share/glib-2.0/schemas/org.gnome.shell.extensions.arcmenu.gschema.xml")))


if __name__ == "__main__":
    unittest.main()
