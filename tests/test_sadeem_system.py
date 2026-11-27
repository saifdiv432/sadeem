#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for sadeem-system pure helpers and i18n parity:
1. parse_ostree_deployments: booted + rollback, booted + staged (no false rollback),
   single deployment, and malformed/empty JSON handling.
2. find_shadowed_extensions & remove_shadowed_extensions: detection, directory and
   symlink cleanup, preserving non-shadowed user extensions, and blocking path traversal.
3. TRANSLATIONS parity across all 10 supported locales for rollback, extension detector,
   and quick-start/shortcuts guide keys.
"""

import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SADEEM_SYSTEM_PATH = os.path.join(REPO_ROOT, "files/system/usr/bin/sadeem-system")


def load_sadeem_system_module():
    loader = importlib.machinery.SourceFileLoader("sadeem_system_test_mod", SADEEM_SYSTEM_PATH)
    spec = importlib.util.spec_from_loader("sadeem_system_test_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestSadeemSystemHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_sadeem_system_module()

    def test_parse_ostree_deployments_booted_and_rollback(self):
        payload = json.dumps({
            "deployments": [
                {
                    "booted": True,
                    "staged": False,
                    "version": "44.20261126.0",
                    "timestamp": 1764115200,
                    "origin": "ostree-image-signed:docker://ghcr.io/sadeem/sadeem:latest",
                },
                {
                    "booted": False,
                    "staged": False,
                    "version": "44.20261120.0",
                    "timestamp": 1763596800,
                    "container-image-reference": "ostree-image-signed:docker://ghcr.io/sadeem/sadeem:prev",
                },
            ]
        })
        parsed = self.mod.parse_ostree_deployments(payload)
        self.assertIsNotNone(parsed["booted"])
        self.assertEqual(parsed["booted"]["version"], "44.20261126.0")
        self.assertEqual(parsed["booted"]["timestamp"], 1764115200)
        self.assertIn("sadeem:latest", parsed["booted"]["origin"])
        self.assertIsNone(parsed["staged"])
        self.assertIsNotNone(parsed["rollback"])
        self.assertEqual(parsed["rollback"]["version"], "44.20261120.0")
        self.assertEqual(parsed["rollback"]["timestamp"], 1763596800)

    def test_parse_ostree_deployments_staged_is_never_rollback(self):
        payload = json.dumps({
            "deployments": [
                {
                    "booted": False,
                    "staged": True,
                    "version": "44.20261127.0",
                    "timestamp": 1764201600,
                    "origin": "ostree-image-signed:docker://ghcr.io/sadeem/sadeem:next",
                },
                {
                    "booted": True,
                    "staged": False,
                    "version": "44.20261126.0",
                    "timestamp": 1764115200,
                    "origin": "ostree-image-signed:docker://ghcr.io/sadeem/sadeem:latest",
                },
            ]
        })
        parsed = self.mod.parse_ostree_deployments(payload)
        self.assertIsNotNone(parsed["booted"])
        self.assertEqual(parsed["booted"]["version"], "44.20261126.0")
        self.assertIsNotNone(parsed["staged"])
        self.assertEqual(parsed["staged"]["version"], "44.20261127.0")
        self.assertIsNone(parsed["rollback"], "Staged deployment must never be mistaken for rollback")

    def test_parse_ostree_deployments_single_and_malformed(self):
        single = json.dumps({
            "deployments": [
                {"booted": True, "staged": False, "version": "44.1", "timestamp": 1700000000}
            ]
        })
        parsed_single = self.mod.parse_ostree_deployments(single)
        self.assertEqual(parsed_single["booted"]["version"], "44.1")
        self.assertIsNone(parsed_single["staged"])
        self.assertIsNone(parsed_single["rollback"])

        for bad in ("", "   ", "{not json", "[]", json.dumps({"deployments": "bad"}), None):
            res = self.mod.parse_ostree_deployments(bad)
            self.assertEqual(res, {"booted": None, "staged": None, "rollback": None})

    def test_find_and_remove_shadowed_extensions_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_dir = os.path.join(tmpdir, "user_ext")
            sys_dir = os.path.join(tmpdir, "sys_ext")
            outside_dir = os.path.join(tmpdir, "outside_target")
            os.makedirs(user_dir)
            os.makedirs(sys_dir)
            os.makedirs(outside_dir)

            # System extensions
            os.makedirs(os.path.join(sys_dir, "dash-to-panel@jderose9.github.com"))
            os.makedirs(os.path.join(sys_dir, "emoji-copy@felipeftn"))
            os.makedirs(os.path.join(sys_dir, "sadeem-menu@sadeem.os"))

            # User extensions:
            # 1) folder shadowing dash-to-panel
            shadow_folder = os.path.join(user_dir, "dash-to-panel@jderose9.github.com")
            os.makedirs(shadow_folder)
            with open(os.path.join(shadow_folder, "extension.js"), "w", encoding="utf-8") as f:
                f.write("// old local copy")

            # 2) symlink shadowing emoji-copy (pointing outside_dir; unlink must not touch outside_dir!)
            shadow_link = os.path.join(user_dir, "emoji-copy@felipeftn")
            os.symlink(outside_dir, shadow_link)
            outside_marker = os.path.join(outside_dir, "keep.txt")
            with open(outside_marker, "w", encoding="utf-8") as f:
                f.write("keep")

            # 3) user-only extension (not in sys_dir) -> must NEVER be flagged or deleted
            user_only = os.path.join(user_dir, "blur-my-shell@aunetx")
            os.makedirs(user_only)

            conflicts = self.mod.find_shadowed_extensions(user_dir, sys_dir)
            self.assertEqual(
                conflicts,
                ["dash-to-panel@jderose9.github.com", "emoji-copy@felipeftn"],
            )

            # Attempt to remove valid conflicts + non-system ext + path traversal payloads
            to_remove = conflicts + [
                "blur-my-shell@aunetx",
                "../outside_target",
                "a/b",
                "..",
            ]
            removed, errors = self.mod.remove_shadowed_extensions(to_remove, user_dir, sys_dir)

            self.assertEqual(
                removed,
                ["dash-to-panel@jderose9.github.com", "emoji-copy@felipeftn"],
            )
            self.assertEqual(len(errors), 4)
            self.assertFalse(os.path.lexists(shadow_folder))
            self.assertFalse(os.path.lexists(shadow_link))
            self.assertTrue(os.path.isfile(outside_marker), "Unlinking symlink must not delete its target")
            self.assertTrue(os.path.isdir(user_only), "Non-shadowed user extension must remain intact")
            self.assertEqual(self.mod.find_shadowed_extensions(user_dir, sys_dir), [])

    def test_translations_complete_for_wave2_keys(self):
        expected_langs = ("ar", "en", "fr", "es", "de", "tr", "ru", "pt", "it", "zh")
        required_prefixes = ("rollback_", "ext_shadow_", "guide_")
        en_dict = self.mod.TRANSLATIONS["en"]
        wave2_keys = {
            k for k in en_dict if k.startswith(required_prefixes)
        } | {"btn_ok"}
        self.assertGreaterEqual(len(wave2_keys), 35)

        for lang in expected_langs:
            self.assertIn(lang, self.mod.TRANSLATIONS)
            loc = self.mod.TRANSLATIONS[lang]
            for key in wave2_keys:
                val = loc.get(key)
                self.assertTrue(
                    isinstance(val, str) and bool(val.strip()),
                    f"Missing or empty translation '{key}' in locale '{lang}'",
                )


if __name__ == "__main__":
    unittest.main()
