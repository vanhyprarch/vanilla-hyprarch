#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the launcher owner's no-clobber and fail-closed file protocol."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_launcher_state"
DEFAULTS = ["firefox", "foot", "thunar", "io.github.kolunmi.Bazaar"]


class LauncherStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="vanhyprarch-launcher-state-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state_home = self.root / "state"
        self.state_home.mkdir()
        self.path = self.state_home / "quickshell/by-shell/test-id/launchers.json"
        self.environment = dict(os.environ, XDG_STATE_HOME=str(self.state_home))

    def call(self, command: str, *arguments: str) -> dict:
        result = subprocess.run(
            [str(HELPER), command, str(self.path), *arguments],
            env=self.environment, text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def put(self, data: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(data)

    def test_absent_seed_exactly_once(self) -> None:
        self.assertEqual(self.call("inspect")["status"], "absent")
        result = self.call("seed")
        self.assertEqual(result["status"], "valid")
        self.assertEqual([item["desktopId"] for item in result["launchers"]], DEFAULTS)
        before = self.path.read_bytes()
        self.assertEqual(self.call("seed")["status"], "conflict")
        self.assertEqual(self.path.read_bytes(), before)

    def test_valid_bytes_optional_icon_and_unresolved_entries(self) -> None:
        before = (b'{ "note": "keep", "launchers": ['
                  b'{"desktopId":"gone","customIcon":"custom"},'
                  b'{"desktopId":"foot"}] }\n')
        self.put(before)
        result = self.call("inspect")
        self.assertEqual(result["status"], "valid")
        self.assertEqual([item["desktopId"] for item in result["launchers"]],
                         ["gone", "foot"])
        self.assertEqual(self.path.read_bytes(), before)
        updated = self.call("edit", result["revision"], "move", "foot", "0")
        self.assertEqual(updated["status"], "valid")
        self.assertEqual([item["desktopId"] for item in updated["launchers"]],
                         ["foot", "gone"])
        self.assertEqual(updated["launchers"][1]["customIcon"], "custom")
        self.assertNotIn("customIcon", updated["launchers"][0])
        self.assertEqual(json.loads(self.path.read_bytes())["note"], "keep")

    def test_empty_is_valid_and_preserved(self) -> None:
        before = b'{ "launchers": [] }\n'
        self.put(before)
        self.assertEqual(self.call("inspect")["launchers"], [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_explicit_add_and_remove_preserve_other_pins(self) -> None:
        self.put(b'{"launchers":[{"desktopId":"gone"}]}')
        original = self.call("inspect")
        added = self.call("edit", original["revision"], "add", "foot")
        self.assertEqual([item["desktopId"] for item in added["launchers"]],
                         ["gone", "foot"])
        removed = self.call("edit", added["revision"], "remove", "foot")
        self.assertEqual(removed["launchers"], [{"desktopId": "gone"}])

    def test_malformed_cases_preserve_exact_bytes(self) -> None:
        cases = (
            b'{ bad', b'[]', b'{}', b'{"launchers":false}',
            b'{"launchers":[{}]}',
            b'{"launchers":[{"desktopId":3}]}',
            b'{"launchers":[{"desktopId":"foot"},{"desktopId":"foot"}]}',
            b'{"launchers":[{"desktopId":"foot","customIcon":false}]}',
            b'{"launchers":[{"desktopId":"foot"},null]}',
            b'{"launchers":[],"launchers":[]}',
            b'{"launchers":[{"desktopId":"foot"}],"x":NaN}',
        )
        for before in cases:
            with self.subTest(before=before):
                self.put(before)
                self.assertEqual(self.call("inspect")["status"], "malformed")
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.call("seed")["status"], "conflict")
                self.assertEqual(self.path.read_bytes(), before)

    def test_unsafe_targets_are_never_followed_or_repaired(self) -> None:
        outside = self.root / "outside"
        outside.write_bytes(b"outside bytes")
        self.path.parent.mkdir(parents=True)
        self.path.symlink_to(outside)
        self.assertEqual(self.call("inspect")["status"], "unsafe")
        self.assertEqual(self.call("seed")["status"], "conflict")
        self.assertEqual(outside.read_bytes(), b"outside bytes")
        self.path.unlink()
        self.path.symlink_to(self.root / "missing")
        self.assertEqual(self.call("inspect")["status"], "unsafe")
        self.assertEqual(self.call("seed")["status"], "conflict")
        self.path.unlink()
        self.path.mkdir()
        self.assertEqual(self.call("inspect")["status"], "unsafe")
        self.path.rmdir()
        self.path.parent.rmdir()
        self.path.parent.symlink_to(self.root)
        self.assertEqual(self.call("inspect")["status"], "unsafe")
        self.assertEqual(self.call("seed")["status"], "unsafe")

    def test_wrong_owner_is_rejected(self) -> None:
        self.put(b'{"launchers":[]}')
        loader = importlib.machinery.SourceFileLoader("launcher_owner_test", str(HELPER))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            loader.exec_module(module)
        fd = os.open(self.path.parent, module.DIR_FLAGS)
        try:
            with mock.patch.object(module, "UID", os.getuid() + 1):
                with self.assertRaises(module.Unsafe):
                    module.read_at(fd)
        finally:
            os.close(fd)
        self.assertEqual(self.path.read_bytes(), b'{"launchers":[]}')

    def test_unsafe_parent_permissions_are_rejected(self) -> None:
        self.put(b'{"launchers":[]}')
        before = self.path.read_bytes()
        original_mode = self.state_home.stat().st_mode & 0o7777
        try:
            self.state_home.chmod(0o777)
            self.assertEqual(self.call("inspect")["status"], "unsafe")
            self.assertEqual(self.call("seed")["status"], "unsafe")
            self.assertEqual(self.path.read_bytes(), before)
        finally:
            self.state_home.chmod(original_mode)

    def test_retry_reclassifies_repaired_file(self) -> None:
        self.put(b"invalid")
        self.assertEqual(self.call("inspect")["status"], "malformed")
        replacement = b'{ "launchers": [{"desktopId":"foot"}] }\n'
        self.put(replacement)
        self.assertEqual(self.call("inspect")["status"], "valid")
        self.assertEqual(self.path.read_bytes(), replacement)

    def test_external_edit_conflict_preserves_external_bytes(self) -> None:
        self.put(b'{"launchers":[{"desktopId":"foot"}]}')
        revision = self.call("inspect")["revision"]
        external = b'{ "launchers": [] }\n'
        self.put(external)
        self.assertEqual(self.call("edit", revision, "remove", "foot")["status"],
                         "conflict")
        self.assertEqual(self.path.read_bytes(), external)


if __name__ == "__main__":
    unittest.main()
