#!/usr/bin/env python3
"""Isolated Default Apps parsing, precedence, and transaction tests."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "bin/vanhyprarch-default-apps"
loader = importlib.machinery.SourceFileLoader("default_apps", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
MODULE = importlib.util.module_from_spec(spec)
loader.exec_module(MODULE)


class DefaultAppsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.config.mkdir()
        self.env = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_CURRENT_DESKTOP": "Hyprland",
        })
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def select(self, category: str, desktop_id: str, effective: str | None = None):
        with mock.patch.object(MODULE, "installed", return_value={}), \
                mock.patch.object(MODULE, "candidates", return_value=[desktop_id]), \
                mock.patch.object(MODULE, "effective", return_value={category: effective or desktop_id}), \
                mock.patch.object(MODULE, "status", return_value={"version": 1}):
            return MODULE.select(category, desktop_id)

    def test_browser_three_keys_preserve_unrelated_bytes_and_format(self) -> None:
        path = self.config / "mimeapps.list"
        initial = (b"# personal note\r\n[Default Applications]\r\n"
                   b"text/html=old.desktop;\r\nimage/png=viewer.desktop;\r\n"
                   b"[Added Associations]\r\ntext/plain=extra.desktop;\r\n")
        path.write_bytes(initial)
        self.select("browser", "browser.desktop")
        changed = path.read_bytes()
        self.assertIn(b"text/html=browser.desktop;\r\n", changed)
        self.assertIn(b"x-scheme-handler/http=browser.desktop;\r\n", changed)
        self.assertIn(b"x-scheme-handler/https=browser.desktop;\r\n", changed)
        self.assertIn(b"# personal note\r\n", changed)
        self.assertIn(b"image/png=viewer.desktop;\r\n", changed)
        self.assertIn(b"[Added Associations]\r\ntext/plain=extra.desktop;\r\n", changed)

    def test_editor_only_plain_text_and_missing_file(self) -> None:
        path = self.config / "mimeapps.list"
        self.select("editor", "editor.desktop")
        self.assertEqual(path.read_bytes(), b"[Default Applications]\ntext/plain=editor.desktop;\n")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        path.write_bytes(b"[Default Applications]\ntext/html=browser.desktop;\n")
        self.select("editor", "editor.desktop")
        self.assertIn(b"text/html=browser.desktop;\n", path.read_bytes())
        path.write_bytes(b"[Default Applications]")
        self.select("editor", "editor.desktop")
        self.assertEqual(path.read_bytes(),
                         b"[Default Applications]\ntext/plain=editor.desktop;\n")

    def test_desktop_specific_override_is_selected(self) -> None:
        generic = self.config / "mimeapps.list"
        specific = self.config / "hyprland-mimeapps.list"
        generic.write_bytes(b"[Default Applications]\ntext/html=generic.desktop;\n")
        specific.write_bytes(b"# override\n[Default Applications]\nx-scheme-handler/http=old.desktop;\n")
        self.select("browser", "browser.desktop")
        self.assertEqual(generic.read_bytes(), b"[Default Applications]\ntext/html=generic.desktop;\n")
        for key in MODULE.BROWSER_TYPES:
            self.assertIn((key + "=browser.desktop;").encode(), specific.read_bytes())

    def test_terminal_list_preserves_other_preferences(self) -> None:
        path = self.config / "xdg-terminals.list"
        path.write_bytes(b"# mine\nold.desktop\n-other.desktop\n")
        self.select("terminal", "foot.desktop")
        self.assertEqual(path.read_bytes(), b"# mine\nfoot.desktop\nold.desktop\n-other.desktop\n")
        specific = self.config / "hyprland-xdg-terminals.list"
        specific.write_bytes(b"other.desktop\n")
        self.select("terminal", "foot.desktop")
        self.assertTrue(specific.read_bytes().startswith(b"foot.desktop\n"))
        self.assertEqual(path.read_bytes(), b"# mine\nfoot.desktop\nold.desktop\n-other.desktop\n")
        specific.write_bytes(b"# no final newline")
        self.select("terminal", "foot.desktop")
        self.assertEqual(specific.read_bytes(), b"# no final newline\nfoot.desktop\n")

    def test_ambiguous_mime_and_unsafe_targets_fail_closed(self) -> None:
        path = self.config / "mimeapps.list"
        for content in (b"[Default Applications]\ntext/plain=one.desktop;\ntext/plain=two.desktop;\n",
                        b"[Default Applications]\n[Default Applications]\n",
                        b"[Default Applications\ntext/plain=old.desktop;\n"):
            path.write_bytes(content)
            with self.assertRaises(MODULE.DefaultAppsError):
                self.select("editor", "editor.desktop")
            self.assertEqual(path.read_bytes(), content)
        path.unlink()
        outside = self.root / "outside"
        outside.write_bytes(b"untouched")
        path.symlink_to(outside)
        with self.assertRaises(OSError):
            self.select("editor", "editor.desktop")
        self.assertEqual(outside.read_bytes(), b"untouched")
        path.unlink()
        path.mkdir()
        with self.assertRaises(MODULE.DefaultAppsError):
            self.select("editor", "editor.desktop")

    def test_verification_mismatch_rolls_back_exact_preimage(self) -> None:
        path = self.config / "mimeapps.list"
        initial = b"# exact\n[Default Applications]\ntext/plain=old.desktop;\n"
        path.write_bytes(initial)
        with self.assertRaisesRegex(MODULE.DefaultAppsError, "effective editor remains"):
            self.select("editor", "editor.desktop", effective="old.desktop")
        self.assertEqual(path.read_bytes(), initial)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_post_publication_failure_rolls_back_and_unsafe_owner_rejected(self) -> None:
        path = self.config / "mimeapps.list"
        old = b"[Default Applications]\ntext/plain=old.desktop;\n"
        path.write_bytes(old)
        actual_publish = MODULE.publish
        calls = 0

        def fail_after_publish(destination, data, mode):
            nonlocal calls
            calls += 1
            actual_publish(destination, data, mode)
            if calls == 1:
                raise OSError("injected post-publication failure")

        with mock.patch.object(MODULE, "publish", side_effect=fail_after_publish):
            with self.assertRaisesRegex(OSError, "injected"):
                self.select("editor", "editor.desktop")
        self.assertEqual(path.read_bytes(), old)
        with mock.patch.object(MODULE.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(MODULE.DefaultAppsError):
                self.select("editor", "editor.desktop")
        self.assertEqual(path.read_bytes(), old)

    def test_terminal_duplicate_selection_and_unsafe_parent(self) -> None:
        path = self.config / "xdg-terminals.list"
        original = b"foot.desktop\n# note\nfoot.desktop\n"
        path.write_bytes(original)
        with self.assertRaisesRegex(MODULE.DefaultAppsError, "duplicate selected terminal"):
            self.select("terminal", "foot.desktop")
        self.assertEqual(path.read_bytes(), original)
        path.write_bytes(b"not a terminal ID\n")
        with self.assertRaisesRegex(MODULE.DefaultAppsError, "malformed terminal"):
            self.select("terminal", "foot.desktop")
        other = self.root / "outside"
        other.mkdir()
        config_link = self.root / "linked-config"
        config_link.symlink_to(other, target_is_directory=True)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config_link)}):
            with self.assertRaises(MODULE.DefaultAppsError):
                self.select("editor", "editor.desktop")
        self.assertEqual(list(other.iterdir()), [])

    def test_readback_is_zero_write(self) -> None:
        path = self.config / "mimeapps.list"
        path.write_bytes(b"[Default Applications]\ntext/html=firefox.desktop;\n")
        before = (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes())
        MODULE.status()
        self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes()), before)
        self.assertFalse((self.config / ".vanhyprarch-default-apps.lock").exists())

    def test_candidate_eligibility_requires_direct_mime_types(self) -> None:
        class FakeApp:
            def __init__(self, types):
                self.types = types

            def get_supported_types(self):
                return self.types

        apps = {"complete.desktop": FakeApp(MODULE.BROWSER_TYPES),
                "partial.desktop": FakeApp(MODULE.BROWSER_TYPES[:2]),
                "editor.desktop": FakeApp(["text/plain"])}
        self.assertEqual(MODULE.candidates("browser", apps), ["complete.desktop"])
        self.assertEqual(MODULE.candidates("editor", apps), ["editor.desktop"])

    def test_real_gio_readback_eligibility_and_selection(self) -> None:
        data = self.root / "data/applications"
        data.mkdir(parents=True)
        user_data = self.root / "user-data"
        user_data.mkdir()
        for desktop_id, name, mime in (
            ("first.desktop", "First", "text/html;x-scheme-handler/http;x-scheme-handler/https;"),
            ("second.desktop", "Second", "text/html;x-scheme-handler/http;x-scheme-handler/https;"),
            ("incomplete.desktop", "Incomplete", "text/html;x-scheme-handler/http;"),
            ("editor.desktop", "Editor", "text/plain;"),
        ):
            (data / desktop_id).write_text(
                "[Desktop Entry]\nType=Application\nName=" + name
                + "\nExec=/usr/bin/true\nMimeType=" + mime + "\n",
                encoding="utf-8",
            )
        (self.config / "mimeapps.list").write_bytes(
            b"[Default Applications]\ntext/html=first.desktop;\n"
            b"x-scheme-handler/http=first.desktop;\n"
            b"x-scheme-handler/https=first.desktop;\n"
            b"text/plain=editor.desktop;\n"
        )
        env = dict(os.environ, XDG_DATA_HOME=str(user_data), XDG_DATA_DIRS=str(data.parent))

        def command(*args):
            result = subprocess.run([str(SOURCE), *args], env=env, text=True,
                                    capture_output=True, check=False, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return MODULE.json.loads(result.stdout)

        current = command("status")
        self.assertEqual(current["effective"]["browser"], "first.desktop")
        self.assertEqual(current["effective"]["editor"], "editor.desktop")
        self.assertEqual(current["candidates"]["browser"], ["first.desktop", "second.desktop"])
        mimeapps = self.config / "mimeapps.list"
        mimeapps.write_bytes(mimeapps.read_bytes().replace(
            b"x-scheme-handler/https=first.desktop;",
            b"x-scheme-handler/https=second.desktop;",
        ))
        self.assertEqual(command("status")["effective"]["browser"], "mixed")
        selected = command("select", "browser", "second.desktop")
        self.assertEqual(selected["effective"]["browser"], "second.desktop")
        self.assertIn(b"text/plain=editor.desktop;", (self.config / "mimeapps.list").read_bytes())

    def test_packaged_terminal_resolver_foot_and_user_override(self) -> None:
        resolver = os.environ.get("VANHYPRARCH_XTE_TEST_EXECUTABLE") or shutil.which("xdg-terminal-exec")
        if not resolver:
            self.skipTest("official xdg-terminal-exec package is not installed")
        data = self.root / "local/share/xdg-terminal-exec"
        data.mkdir(parents=True)
        (data / "hyprland-xdg-terminals.list").write_bytes(b"foot.desktop\n")
        apps = self.root / "local/share/applications"
        apps.mkdir()
        (apps / "alternative.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Alternative\n"
            "Exec=/usr/bin/true\nCategories=System;TerminalEmulator;\n"
            "X-TerminalArgExec=-e\n", encoding="utf-8")
        env = dict(os.environ, XDG_DATA_DIRS=str(data.parent) + ":/usr/share",
                   XDG_DATA_HOME=str(self.root / "user-data"),
                   XDG_CACHE_HOME=str(self.root / "cache"), XTE_CACHE_ENABLED="0",
                   PATH=str(Path(resolver).parent) + ":" + os.environ.get("PATH", ""))

        def print_result(*args):
            result = subprocess.run([resolver, *args], env=env, text=True,
                                    capture_output=True, check=False, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        self.assertEqual(print_result("--print-id"), "foot.desktop")
        self.assertEqual(print_result("--print-cmd", "/usr/bin/true"),
                         "foot\n-e\n/usr/bin/true")
        cache = Path(env["XDG_CACHE_HOME"])
        cache.mkdir()
        existing_cache = cache / "xdg-terminal-exec"
        existing_cache.write_bytes(b"preexisting user cache\n")
        cache_before = (existing_cache.stat().st_ino, existing_cache.stat().st_mtime_ns,
                        existing_cache.read_bytes())
        readback = subprocess.run([str(SOURCE), "status"], env=env, text=True,
                                  capture_output=True, check=False, timeout=10)
        self.assertEqual(readback.returncode, 0, readback.stderr)
        self.assertEqual(MODULE.json.loads(readback.stdout)["effective"]["terminal"],
                         "foot.desktop")
        self.assertEqual((existing_cache.stat().st_ino, existing_cache.stat().st_mtime_ns,
                          existing_cache.read_bytes()), cache_before)
        chosen = subprocess.run([str(SOURCE), "select", "terminal", "alternative.desktop"],
                                env=env, text=True, capture_output=True, check=False, timeout=10)
        self.assertEqual(chosen.returncode, 0, chosen.stderr)
        self.assertEqual(MODULE.json.loads(chosen.stdout)["effective"]["terminal"],
                         "alternative.desktop")
        self.assertEqual((self.config / "xdg-terminals.list").read_bytes(),
                         b"alternative.desktop\n")
        self.assertEqual((existing_cache.stat().st_ino, existing_cache.stat().st_mtime_ns,
                          existing_cache.read_bytes()), cache_before)
        self.assertEqual(print_result("--print-id"), "alternative.desktop")


if __name__ == "__main__":
    unittest.main()
