#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import importlib.machinery
import importlib.util
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


REPOSITORY = Path(__file__).resolve().parent.parent
HELPER = REPOSITORY / "bin/vanhyprarch-appearance"
ASSET_ROOT = REPOSITORY / "assets/wallpapers"
LOADER = importlib.machinery.SourceFileLoader("vanhyprarch_appearance", str(HELPER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
if SPEC is None:
    raise RuntimeError("could not load appearance manager")
appearance = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = appearance
LOADER.exec_module(appearance)


class FakeSystem:
    def __init__(self) -> None:
        self.host = "prefer-light"
        self.portal = 2
        self.portal_override: int | None = None
        self.processes = [1200]
        self.monitors = ["DP-1"]
        self.monitor_snapshots: list[list[str]] = []
        self.monitor_payload: object | None = None
        self.active: dict[str, str] = {}
        self.fallback: str | None = None
        self.ignore_wallpaper: set[str] = set()
        self.mime = "image/png"
        self.fail: set[tuple[str, ...]] = set()
        self.calls: list[list[str]] = []
        self.spawn_calls: list[list[str]] = []

    def process_probe(self) -> list[int]:
        return list(self.processes)

    def runner(self, arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(arguments)
        self.calls.append(argv)
        key = tuple(argv)
        if key in self.fail:
            return subprocess.CompletedProcess(argv, 1, "", "fixture failure")
        if argv[:2] == [appearance.GSETTINGS, "get"]:
            return subprocess.CompletedProcess(argv, 0, f"'{self.host}'\n", "")
        if argv[:2] == [appearance.GSETTINGS, "set"]:
            self.host = argv[-1]
            if self.portal_override is None:
                self.portal = 1 if self.host == "prefer-dark" else 2
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[0] == appearance.BUSCTL:
            value = self.portal if self.portal_override is None else self.portal_override
            return subprocess.CompletedProcess(argv, 0, f"v v u {value}\n", "")
        if argv == [appearance.HYPRCTL, "-j", "monitors"]:
            if self.monitor_payload is not None:
                return subprocess.CompletedProcess(
                    argv, 0, json.dumps(self.monitor_payload), ""
                )
            if self.monitor_snapshots:
                previous = set(self.monitors)
                self.monitors = list(self.monitor_snapshots.pop(0))
                if self.fallback is not None:
                    for monitor in set(self.monitors) - previous:
                        self.active.setdefault(monitor, self.fallback)
            output = json.dumps(
                [{"name": monitor, "disabled": False} for monitor in self.monitors]
            )
            return subprocess.CompletedProcess(argv, 0, output, "")
        if argv == [appearance.HYPRCTL, "hyprpaper", "listactive"]:
            output = "".join(f"{monitor}: {path}\n" for monitor, path in self.active.items())
            return subprocess.CompletedProcess(argv, 0, output, "")
        if argv[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]:
            if len(argv) != 4:
                return subprocess.CompletedProcess(argv, 1, "", "invalid argument shape")
            monitor, path, fit_mode = argv[3].split(",", 2)
            if fit_mode != "cover":
                return subprocess.CompletedProcess(argv, 1, "", "invalid fit mode")
            if monitor:
                if monitor not in self.monitors:
                    return subprocess.CompletedProcess(argv, 1, "", "invalid monitor")
                if monitor not in self.ignore_wallpaper:
                    self.active[monitor] = path
            else:
                self.fallback = path
                for current in self.monitors:
                    self.active.setdefault(current, path)
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[:4] == [appearance.FILE, "--brief", "--mime-type", "--"]:
            return subprocess.CompletedProcess(argv, 0, self.mime + "\n", "")
        raise AssertionError(f"unexpected command: {argv}")

    def popen(self, arguments: list[str], **kwargs: Any) -> object:
        self.spawn_calls.append(list(arguments))
        self.processes = [1300]
        return object()


class AppearanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="vanhyprarch-appearance-test."
        )
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.data = self.root / "data"
        self.runtime = self.root / "runtime"
        for directory in (self.home, self.config, self.state, self.data, self.runtime):
            directory.mkdir(mode=0o700)
        self.environ = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state),
            "XDG_DATA_HOME": str(self.data),
            "XDG_RUNTIME_DIR": str(self.runtime),
        }
        self.asset_root = self.root / "official-assets"
        self.official_bytes = {
            "Light/Official Light.png": b"official light bytes",
            "Dark/Official Dark.png": b"official dark bytes",
        }
        self.official_wallpapers = {
            relative: hashlib.sha256(contents).hexdigest()
            for relative, contents in self.official_bytes.items()
        }
        for relative, contents in self.official_bytes.items():
            source = self.asset_root / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(contents)
        self.system = FakeSystem()
        self.manager = appearance.AppearanceManager(
            self.environ,
            runner=self.system.runner,
            popen=self.system.popen,
            process_probe=self.system.process_probe,
            sleeper=lambda _: None,
            clock=lambda: 1000.0,
            asset_root=self.asset_root,
            official_wallpapers=self.official_wallpapers,
            default_wallpapers={
                "light": "Official Light.png",
                "dark": "Official Dark.png",
            },
        )
        self.manager.ensure_user_directories()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def wallpaper(self, mode: str, name: str, contents: bytes = b"png") -> Path:
        path = self.manager.mode_directory(mode) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def write_preference(
        self,
        mode: str = "light",
        light: str | None = None,
        dark: str | None = None,
    ) -> None:
        self.manager.write_preference(appearance.Preference(mode, light, dark))

    def test_xdg_pictures_resolution_and_required_plural_directories(self) -> None:
        pictures = self.home / "Images and Pictures"
        (self.config / "user-dirs.dirs").write_text(
            'XDG_PICTURES_DIR="$HOME/Images and Pictures"\n', encoding="utf-8"
        )
        manager = appearance.AppearanceManager(
            self.environ,
            runner=self.system.runner,
            process_probe=self.system.process_probe,
        )
        self.assertEqual(manager.pictures, pictures)
        self.assertEqual(manager.mode_directory("light"), pictures / "Wallpapers/Light")
        self.assertEqual(manager.mode_directory("dark"), pictures / "Wallpapers/Dark")

    def test_xdg_pictures_falls_back_without_helper_or_configuration(self) -> None:
        self.assertEqual(self.manager.pictures, self.home / "Pictures")

    def test_spaces_and_unicode_are_persisted_as_relative_paths(self) -> None:
        selected = self.wallpaper("light", "Alpi d’estate ☀.png")
        self.manager.set_wallpaper("light", str(selected))
        preference = self.manager.read_preference()
        self.assertIsNotNone(preference)
        self.assertEqual(preference.light_wallpaper, "Alpi d’estate ☀.png")

    def test_each_mode_remembers_an_independent_wallpaper(self) -> None:
        light = self.wallpaper("light", "light.png")
        dark = self.wallpaper("dark", "dark.png")
        self.manager.set_wallpaper("light", str(light))
        self.manager.set_wallpaper("dark", str(dark))
        preference = self.manager.read_preference()
        self.assertEqual(preference.light_wallpaper, "light.png")
        self.assertEqual(preference.dark_wallpaper, "dark.png")

    def test_preference_is_atomic_private_and_schema_strict(self) -> None:
        self.write_preference("dark")
        self.assertEqual(self.manager.preference_path.stat().st_mode & 0o777, 0o600)
        value = json.loads(self.manager.preference_path.read_text(encoding="utf-8"))
        value["unexpected"] = True
        self.manager.preference_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(appearance.AppearanceError, "schema"):
            self.manager.read_preference()

    def test_directory_creation_preserves_existing_user_content(self) -> None:
        existing = self.wallpaper("dark", "keep me.png", b"personal bytes")
        self.manager.ensure_user_directories()
        self.assertEqual(existing.read_bytes(), b"personal bytes")

    def test_clean_asset_seed_preserves_exact_bytes_and_is_idempotent(self) -> None:
        result = self.manager.seed_official_assets()
        self.assertEqual(result["seeded"], sorted(self.official_bytes))
        self.assertEqual(result["errors"], [])
        for relative, contents in self.official_bytes.items():
            self.assertEqual((self.manager.wallpaper_root / relative).read_bytes(), contents)

        before = self.manager.asset_receipt_path.read_bytes()
        second = self.manager.seed_official_assets()
        self.assertEqual(second["current"], sorted(self.official_bytes))
        self.assertEqual(second["seeded"], [])
        self.assertEqual(second["updated"], [])
        self.assertEqual(self.manager.asset_receipt_path.read_bytes(), before)

    def test_asset_seed_creates_missing_plural_mode_directories(self) -> None:
        shutil.rmtree(self.manager.wallpaper_root)

        result = self.manager.seed_official_assets()

        self.assertEqual(result["errors"], [])
        self.assertTrue(self.manager.mode_directory("light").is_dir())
        self.assertTrue(self.manager.mode_directory("dark").is_dir())

    def test_asset_seed_preserves_unrelated_and_same_name_user_content(self) -> None:
        unrelated = self.wallpaper("light", "My mountain ☀.png", b"user image")
        collision = self.manager.mode_directory("dark") / "Official Dark.png"
        collision.write_bytes(b"user-modified official filename")

        result = self.manager.seed_official_assets()

        self.assertEqual(unrelated.read_bytes(), b"user image")
        self.assertEqual(collision.read_bytes(), b"user-modified official filename")
        self.assertEqual(result["preserved"], ["Dark/Official Dark.png"])
        self.assertEqual(
            (self.manager.mode_directory("light") / "Official Light.png").read_bytes(),
            self.official_bytes["Light/Official Light.png"],
        )

    def test_existing_byte_identical_official_copy_is_recognized(self) -> None:
        relative = "Light/Official Light.png"
        destination = self.manager.wallpaper_root / relative
        destination.write_bytes(self.official_bytes[relative])

        result = self.manager.seed_official_assets()

        self.assertIn(relative, result["current"])
        self.assertNotIn(relative, result["seeded"])
        self.assertEqual(
            self.manager.read_asset_receipt()[relative],
            self.official_wallpapers[relative],
        )

    def test_asset_reseed_updates_unchanged_seed_and_adds_new_asset(self) -> None:
        self.assertEqual(self.manager.seed_official_assets()["errors"], [])
        updated_relative = "Light/Official Light.png"
        updated_bytes = b"updated official light bytes"
        (self.asset_root / updated_relative).write_bytes(updated_bytes)
        self.manager.official_wallpapers[updated_relative] = hashlib.sha256(
            updated_bytes
        ).hexdigest()

        new_relative = "Dark/New night – Dolomiti.png"
        new_bytes = b"new official dark bytes"
        new_source = self.asset_root / new_relative
        new_source.write_bytes(new_bytes)
        self.manager.official_wallpapers[new_relative] = hashlib.sha256(
            new_bytes
        ).hexdigest()

        result = self.manager.seed_official_assets()

        self.assertEqual(result["updated"], [updated_relative])
        self.assertEqual(result["seeded"], [new_relative])
        self.assertEqual(
            (self.manager.wallpaper_root / updated_relative).read_bytes(), updated_bytes
        )
        self.assertEqual(
            (self.manager.wallpaper_root / new_relative).read_bytes(), new_bytes
        )

    def test_user_modified_previously_seeded_asset_is_not_overwritten(self) -> None:
        self.manager.seed_official_assets()
        relative = "Light/Official Light.png"
        destination = self.manager.wallpaper_root / relative
        destination.write_bytes(b"user modification")
        (self.asset_root / relative).write_bytes(b"new release bytes")
        self.manager.official_wallpapers[relative] = hashlib.sha256(
            b"new release bytes"
        ).hexdigest()

        result = self.manager.seed_official_assets()

        self.assertEqual(destination.read_bytes(), b"user modification")
        self.assertIn(relative, result["preserved"])

    def test_clean_preference_uses_explicit_official_defaults(self) -> None:
        self.assertEqual(self.manager.reconcile(), [])
        preference = self.manager.read_preference()
        self.assertEqual(preference.light_wallpaper, "Official Light.png")
        self.assertEqual(preference.dark_wallpaper, "Official Dark.png")
        self.assertEqual(
            set(self.system.active.values()),
            {str(self.manager.mode_directory("light") / "Official Light.png")},
        )

        self.assertEqual(self.manager.set_mode("dark"), [])
        self.assertEqual(
            set(self.system.active.values()),
            {str(self.manager.mode_directory("dark") / "Official Dark.png")},
        )
        self.assertEqual(self.manager.set_mode("light"), [])
        self.assertEqual(
            set(self.system.active.values()),
            {str(self.manager.mode_directory("light") / "Official Light.png")},
        )

    def test_existing_wallpaper_preferences_are_not_replaced_by_defaults(self) -> None:
        light = self.wallpaper("light", "chosen light.png")
        dark = self.wallpaper("dark", "chosen dark.png")
        self.write_preference("dark", light.name, dark.name)

        self.assertEqual(self.manager.reconcile(), [])

        preference = self.manager.read_preference()
        self.assertEqual(preference.light_wallpaper, light.name)
        self.assertEqual(preference.dark_wallpaper, dark.name)

    def test_mode_switch_applies_only_the_remembered_target_wallpaper(self) -> None:
        light = self.wallpaper("light", "light.png")
        dark = self.wallpaper("dark", "dark.png")
        self.write_preference("light", light.name, dark.name)
        errors = self.manager.set_mode("dark")
        self.assertEqual(errors, [])
        wallpaper_calls = [
            call for call in self.system.calls if call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
        ]
        self.assertEqual(
            wallpaper_calls,
            [
                [
                    appearance.HYPRCTL,
                    "hyprpaper",
                    "wallpaper",
                    f",{dark},cover",
                ],
                [
                    appearance.HYPRCTL,
                    "hyprpaper",
                    "wallpaper",
                    f"DP-1,{dark},cover",
                ],
            ],
        )
        self.assertEqual(self.manager.read_preference().mode, "dark")

    def test_current_mode_alias_sets_and_applies_current_wallpaper(self) -> None:
        dark = self.wallpaper("dark", "current dark.png")
        self.write_preference("dark")
        self.assertEqual(self.manager.set_wallpaper("current", str(dark)), [])
        self.assertEqual(self.manager.read_preference().dark_wallpaper, dark.name)
        self.assertEqual(set(self.system.active.values()), {str(dark)})

    def test_path_outside_mode_directory_is_rejected(self) -> None:
        outside = self.home / "outside.png"
        outside.write_bytes(b"png")
        with self.assertRaisesRegex(appearance.AppearanceError, "escapes"):
            self.manager.validate_wallpaper("light", outside)

    def test_wrong_mode_directory_is_rejected(self) -> None:
        dark = self.wallpaper("dark", "dark.png")
        with self.assertRaisesRegex(appearance.AppearanceError, "escapes"):
            self.manager.validate_wallpaper("light", dark)

    def test_symlink_escape_is_rejected_but_internal_symlink_is_accepted(self) -> None:
        inside = self.wallpaper("light", "real.png")
        internal = self.manager.mode_directory("light") / "internal link.png"
        internal.symlink_to(inside)
        validated, relative = self.manager.validate_wallpaper("light", internal)
        self.assertEqual(validated, inside)
        self.assertEqual(relative, inside.name)

        outside = self.home / "outside.png"
        outside.write_bytes(b"png")
        escaping = self.manager.mode_directory("light") / "escape.png"
        escaping.symlink_to(outside)
        with self.assertRaisesRegex(appearance.AppearanceError, "escapes"):
            self.manager.validate_wallpaper("light", escaping)

    def test_missing_directory_and_regular_file_are_rejected(self) -> None:
        with self.assertRaisesRegex(appearance.AppearanceError, "does not exist"):
            self.manager.validate_wallpaper(
                "light", self.manager.mode_directory("light") / "missing.png"
            )
        with self.assertRaisesRegex(appearance.AppearanceError, "regular file"):
            self.manager.validate_wallpaper("light", self.manager.mode_directory("light"))

    def test_content_type_not_extension_controls_validation(self) -> None:
        unusual = self.wallpaper("light", "wallpaper.not-an-image-extension")
        validated, _ = self.manager.validate_wallpaper("light", unusual)
        self.assertEqual(validated, unusual)
        self.system.mime = "text/plain"
        with self.assertRaisesRegex(appearance.AppearanceError, "unsupported"):
            self.manager.validate_wallpaper("light", unusual)

    def test_no_selection_still_reconciles_shell_host_authority(self) -> None:
        self.write_preference("dark")
        self.assertEqual(self.manager.reconcile(), [])
        self.assertEqual(self.system.host, "prefer-dark")
        status = self.manager.status()
        self.assertIsNone(status["current_wallpaper"])
        self.assertEqual(status["renderer"]["state"], "unselected")

    def test_invalid_selection_does_not_block_host_reconciliation(self) -> None:
        self.write_preference("dark", dark="removed.png")
        errors = self.manager.reconcile()
        self.assertEqual(self.system.host, "prefer-dark")
        self.assertTrue(any("does not exist" in error for error in errors))
        self.assertFalse(
            any(call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"] for call in self.system.calls)
        )

    def test_host_mapping_and_effective_readback(self) -> None:
        self.write_preference("light")
        self.assertEqual(self.manager.set_mode("dark"), [])
        status = self.manager.status()
        self.assertEqual(status["host"]["gsettings"], "prefer-dark")
        self.assertEqual(status["host"]["portal"], 1)
        self.assertTrue(status["host"]["matches"])
        self.assertEqual(self.manager.set_mode("light"), [])
        self.assertEqual(self.system.host, "prefer-light")
        self.assertEqual(self.system.portal, 2)

    def test_host_command_failure_is_reported_without_per_app_mutation(self) -> None:
        command = (
            appearance.GSETTINGS,
            "set",
            "org.gnome.desktop.interface",
            "color-scheme",
            "prefer-dark",
        )
        self.system.fail.add(command)
        errors = self.manager.set_mode("dark")
        self.assertEqual(errors, ["fixture failure"])
        flattened = "\n".join(" ".join(call) for call in self.system.calls)
        self.assertNotIn("firefox", flattened.lower())
        self.assertNotIn("gtk-theme", flattened)
        self.assertNotIn("QT_STYLE_OVERRIDE", flattened)

    def test_portal_backend_mismatch_is_reported(self) -> None:
        self.system.portal_override = 2
        errors = self.manager.set_mode("dark")
        self.assertIn(
            "portal color-scheme did not match the requested host preference", errors
        )
        self.assertEqual(self.manager.read_preference().mode, "dark")
        status = self.manager.status()
        self.assertFalse(status["host"]["matches"])
        self.assertIn("portal", status["host"]["error"])

    def test_renderer_already_running_is_not_spawned(self) -> None:
        self.assertIsNone(self.manager.ensure_renderer())
        self.assertEqual(self.system.spawn_calls, [])

    def test_missing_renderer_is_started_once_and_becomes_available(self) -> None:
        self.system.processes = []
        self.assertIsNone(self.manager.ensure_renderer())
        self.assertEqual(self.system.spawn_calls, [[appearance.HYPRPAPER]])
        self.assertEqual(self.system.processes, [1300])

    def test_missing_renderer_binary_is_a_capability_failure(self) -> None:
        self.system.processes = []
        with mock.patch.object(appearance, "HYPRPAPER", str(self.root / "missing")):
            self.assertEqual(
                self.manager.ensure_renderer(), "Hyprpaper is not installed or executable"
            )
            status = self.manager.status()
        self.assertEqual(status["renderer"]["state"], "missing")
        self.assertFalse(status["consistent"])

    def test_failed_renderer_start_is_not_retried_in_a_spawn_storm(self) -> None:
        self.system.processes = []

        def failing_popen(arguments: list[str], **kwargs: Any) -> object:
            self.system.spawn_calls.append(list(arguments))
            raise OSError("fixture spawn failure")

        self.manager.popen = failing_popen
        first = self.manager.ensure_renderer()
        second = self.manager.ensure_renderer()
        self.assertIn("fixture spawn failure", first)
        self.assertIn("temporarily suppressed", second)
        self.assertEqual(self.system.spawn_calls, [[appearance.HYPRPAPER]])

    def test_multiple_renderers_fail_closed_without_spawn(self) -> None:
        self.system.processes = [1200, 1201]
        self.assertEqual(
            self.manager.ensure_renderer(), "multiple Hyprpaper processes are running"
        )
        self.assertEqual(self.system.spawn_calls, [])

    def test_renderer_command_failure_is_reported(self) -> None:
        dark = self.wallpaper("dark", "dark.png")
        old = self.wallpaper("dark", "old.png")
        self.write_preference("dark", dark=dark.name)
        self.system.active = {"DP-1": str(old)}
        command = (
            appearance.HYPRCTL,
            "hyprpaper",
            "wallpaper",
            f"DP-1,{dark},cover",
        )
        self.system.fail.add(command)
        errors = self.manager.reconcile()
        self.assertTrue(any("fixture failure" in error for error in errors))
        self.assertEqual(self.manager.status()["renderer"]["state"], "mismatch")

    def test_existing_explicit_target_is_replaced_without_restarting_renderer(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        old = self.wallpaper("light", "old.png")
        self.write_preference("light", light=desired.name)
        self.system.active = {"DP-1": str(old)}

        errors = self.manager.reconcile()

        self.assertEqual(errors, [])
        self.assertEqual(self.system.active, {"DP-1": str(desired)})
        self.assertEqual(self.system.processes, [1200])
        self.assertEqual(self.system.spawn_calls, [])
        requests = [
            call[3]
            for call in self.system.calls
            if call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
        ]
        self.assertEqual(requests, [f",{desired},cover", f"DP-1,{desired},cover"])

    def test_fallback_does_not_override_existing_explicit_target(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        old = self.wallpaper("light", "old.png")
        self.system.active = {"DP-1": str(old)}

        result = self.system.runner(
            [
                appearance.HYPRCTL,
                "hyprpaper",
                "wallpaper",
                f",{desired},cover",
            ]
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.system.active, {"DP-1": str(old)})

    def test_two_active_outputs_each_receive_an_explicit_request(self) -> None:
        desired = self.wallpaper("dark", "two outputs.png")
        self.write_preference("dark", dark=desired.name)
        self.system.host = "prefer-dark"
        self.system.portal = 1
        self.system.monitors = ["DP-1", "HDMI-A-1"]
        self.system.active = {
            "DP-1": str(self.wallpaper("dark", "old one.png")),
            "HDMI-A-1": str(self.wallpaper("dark", "old two.png")),
        }

        self.assertEqual(self.manager.reconcile(), [])

        requests = [
            call[3]
            for call in self.system.calls
            if call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
        ]
        self.assertEqual(
            requests,
            [
                f",{desired},cover",
                f"DP-1,{desired},cover",
                f"HDMI-A-1,{desired},cover",
            ],
        )
        self.assertEqual(set(self.system.active), {"DP-1", "HDMI-A-1"})
        self.assertEqual(set(self.system.active.values()), {str(desired)})

    def test_one_of_two_monitor_requests_failing_prevents_full_success(self) -> None:
        desired = self.wallpaper("dark", "desired.png")
        old = self.wallpaper("dark", "old.png")
        self.write_preference("dark", dark=desired.name)
        self.system.host = "prefer-dark"
        self.system.portal = 1
        self.system.monitors = ["DP-1", "HDMI-A-1"]
        self.system.active = {"DP-1": str(old), "HDMI-A-1": str(old)}
        self.system.fail.add(
            (
                appearance.HYPRCTL,
                "hyprpaper",
                "wallpaper",
                f"HDMI-A-1,{desired},cover",
            )
        )

        errors = self.manager.reconcile()

        self.assertTrue(any(error.startswith("HDMI-A-1: ") for error in errors))
        self.assertEqual(self.system.active["DP-1"], str(desired))
        self.assertEqual(self.system.active["HDMI-A-1"], str(old))
        status = self.manager.status()
        self.assertEqual(status["renderer"]["state"], "mismatch")
        self.assertFalse(status["consistent"])

    def test_successful_request_with_listactive_mismatch_is_not_success(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        old = self.wallpaper("light", "old.png")
        self.write_preference("light", light=desired.name)
        self.system.active = {"DP-1": str(old)}
        self.system.ignore_wallpaper.add("DP-1")

        errors = self.manager.reconcile()

        self.assertTrue(any("did not match" in error for error in errors))
        status = self.manager.status()
        self.assertFalse(status["renderer"]["matches"])
        self.assertFalse(status["consistent"])

    def test_monitor_disappearing_during_apply_requires_reconcile(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        self.write_preference("light", light=desired.name)
        self.system.monitors = ["DP-1", "HDMI-A-1"]
        self.system.monitor_snapshots = [
            ["DP-1", "HDMI-A-1"],
            ["DP-1"],
        ]

        errors = self.manager.reconcile()

        self.assertIn("active monitor set changed during wallpaper application", errors)
        self.assertTrue(any("inactive wallpaper outputs" in error for error in errors))

    def test_new_monitor_race_fails_then_next_reconcile_targets_every_output(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        self.write_preference("light", light=desired.name)
        self.system.monitor_snapshots = [
            ["DP-1"],
            ["DP-1", "HDMI-A-1"],
        ]

        first_errors = self.manager.reconcile()
        self.assertIn(
            "active monitor set changed during wallpaper application", first_errors
        )

        self.system.calls.clear()
        self.assertEqual(self.manager.reconcile(), [])
        explicit = [
            call[3].split(",", 1)[0]
            for call in self.system.calls
            if call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
            and not call[3].startswith(",")
        ]
        self.assertEqual(explicit, ["DP-1", "HDMI-A-1"])

    def test_no_active_outputs_reports_failure_without_wildcard_success(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        self.write_preference("light", light=desired.name)
        self.system.monitors = []

        errors = self.manager.reconcile()

        self.assertEqual(
            errors, ["Hyprland reported no active outputs for wallpaper application"]
        )
        self.assertFalse(
            any(
                call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
                for call in self.system.calls
            )
        )
        status = self.manager.status()
        self.assertEqual(status["renderer"]["state"], "no-active-outputs")
        self.assertFalse(status["renderer"]["matches"])

    def test_monitor_discovery_failure_prevents_wallpaper_requests(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        self.write_preference("light", light=desired.name)
        self.system.fail.add((appearance.HYPRCTL, "-j", "monitors"))

        errors = self.manager.reconcile()

        self.assertEqual(errors, ["fixture failure"])
        self.assertFalse(
            any(
                call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
                for call in self.system.calls
            )
        )
        self.assertEqual(self.manager.status()["renderer"]["state"], "monitor-error")

    def test_invalid_monitor_json_shape_fails_closed(self) -> None:
        desired = self.wallpaper("light", "desired.png")
        self.write_preference("light", light=desired.name)
        self.system.monitor_payload = {"name": "DP-1"}

        errors = self.manager.reconcile()

        self.assertEqual(errors, ["Hyprland returned invalid active-monitor state"])
        self.assertFalse(
            any(
                call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
                for call in self.system.calls
            )
        )

    def test_status_reports_effective_wallpaper_mismatch(self) -> None:
        dark = self.wallpaper("dark", "desired.png")
        other = self.wallpaper("dark", "other.png")
        self.write_preference("dark", dark=dark.name)
        self.system.host = "prefer-dark"
        self.system.portal = 1
        self.system.active = {"DP-1": str(other)}
        status = self.manager.status()
        self.assertEqual(status["renderer"]["state"], "mismatch")
        self.assertFalse(status["renderer"]["matches"])
        self.assertFalse(status["consistent"])

    def test_reconcile_preserves_state_while_reasserting_explicit_target(self) -> None:
        light = self.wallpaper("light", "light.png")
        self.write_preference("light", light=light.name)
        self.system.active = {"DP-1": str(light)}
        before = self.manager.preference_path.read_bytes()
        self.assertEqual(self.manager.reconcile(), [])
        self.assertEqual(self.manager.preference_path.read_bytes(), before)
        self.assertFalse(any(call[:2] == [appearance.GSETTINGS, "set"] for call in self.system.calls))
        self.assertEqual(
            [
                call
                for call in self.system.calls
                if call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
            ],
            [
                [appearance.HYPRCTL, "hyprpaper", "wallpaper", f",{light},cover"],
                [appearance.HYPRCTL, "hyprpaper", "wallpaper", f"DP-1,{light},cover"],
            ],
        )
        self.assertEqual(self.system.spawn_calls, [])

    def test_seed_prefers_legacy_mode_and_only_adopts_contained_active_wallpaper(self) -> None:
        legacy = self.state / "vanhyprarch/theme-mode"
        legacy.parent.mkdir()
        legacy.write_text("dark", encoding="utf-8")
        selected = self.wallpaper("dark", "existing.png")
        self.system.active = {"DP-1": str(selected)}
        preference = self.manager.seed_preference()
        self.assertEqual(preference.mode, "dark")
        self.assertEqual(preference.dark_wallpaper, selected.name)

        self.system.active = {"DP-1": str(self.home / "outside.png")}
        preference = self.manager.seed_preference()
        self.assertIsNone(preference.dark_wallpaper)

    def test_seed_never_chooses_first_directory_entry(self) -> None:
        self.wallpaper("light", "a.png")
        self.wallpaper("dark", "a.png")
        self.system.active = {}
        preference = self.manager.seed_preference()
        self.assertIsNone(preference.light_wallpaper)
        self.assertIsNone(preference.dark_wallpaper)

    def test_catalog_is_deterministic_and_separate_from_thumbnails(self) -> None:
        second = self.wallpaper("light", "Žena.png")
        first = self.wallpaper("light", "alpine.png")
        catalog = self.manager.catalog("light")
        self.assertEqual(catalog["wallpapers"], [str(first), str(second)])
        self.assertNotIn("thumbnail", json.dumps(catalog).lower())

    def test_current_catalog_is_limited_to_the_current_mode_directory(self) -> None:
        light = self.wallpaper("light", "light only.png")
        dark = self.wallpaper("dark", "dark only.png")
        self.write_preference("dark", light.name, dark.name)

        catalog = self.manager.catalog("current")

        self.assertEqual(catalog["mode"], "dark")
        self.assertEqual(catalog["directory"], str(self.manager.mode_directory("dark")))
        self.assertEqual(catalog["wallpapers"], [str(dark)])

    def test_shell_metacharacters_remain_one_literal_argument(self) -> None:
        selected = self.wallpaper("dark", "$(touch SHOULD_NOT_EXIST); dark.png")
        self.write_preference("dark", dark=selected.name)
        self.assertEqual(self.manager.reconcile(), [])
        wallpaper_call = next(
            call for call in self.system.calls if call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
        )
        self.assertEqual(wallpaper_call[3], f",{selected},cover")
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_comma_in_wallpaper_path_is_not_persisted_or_cataloged(self) -> None:
        selected = self.wallpaper("light", "mountain, edited.png")
        existing = self.wallpaper("light", "existing.png")
        self.write_preference("light", light=existing.name)
        before = self.manager.preference_path.read_bytes()

        with self.assertRaisesRegex(
            appearance.AppearanceError, "unsupported characters"
        ):
            self.manager.set_wallpaper("light", str(selected))

        self.assertEqual(self.manager.preference_path.read_bytes(), before)
        self.assertNotIn(str(selected), self.manager.catalog("light")["wallpapers"])
        self.assertFalse(
            any(
                call[:3] == [appearance.HYPRCTL, "hyprpaper", "wallpaper"]
                for call in self.system.calls
            )
        )

    def test_status_json_is_machine_readable_and_diagnostics_are_separate(self) -> None:
        self.write_preference("light")
        status = self.manager.status()
        encoded = json.dumps(status, ensure_ascii=False, sort_keys=True)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["version"], 1)
        self.assertEqual(decoded["mode"], "light")
        self.assertEqual(decoded["directories"]["light"], str(self.manager.mode_directory("light")))


class StaticIntegrationTests(unittest.TestCase):
    def test_manager_has_no_shell_interpolation_or_application_specific_paths(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("sh -c", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn(".mozilla", source)
        self.assertNotIn("QT_STYLE_OVERRIDE", source)
        self.assertIsNone(re.search(r"/home/[A-Za-z0-9_.-]+", source))

    def test_hyprland_starts_renderer_through_one_appearance_authority(self) -> None:
        core = (
            REPOSITORY / "home/.config/hypr/vanhyprarch/core.lua"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'hl.exec_cmd("exec " .. sessionHome .. "/.local/bin/vanhyprarch-appearance renderer-start")',
            core,
        )
        self.assertNotIn('hl.exec_cmd("hyprpaper")', core)

    def test_official_asset_metadata_and_pair_one_defaults_are_exact(self) -> None:
        self.assertEqual(
            appearance.DEFAULT_WALLPAPERS,
            {
                "light": "Wolkenstein_1_light.png",
                "dark": "Wolkenstein_1_dark.png",
            },
        )
        self.assertEqual(len(appearance.OFFICIAL_WALLPAPERS), 8)
        for relative, expected_digest in appearance.OFFICIAL_WALLPAPERS.items():
            asset = ASSET_ROOT / relative
            self.assertTrue(asset.is_file(), relative)
            self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), expected_digest)

    def test_product_paths_use_wallpapers_plural(self) -> None:
        paths = [
            path
            for path in REPOSITORY.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and "__pycache__" not in path.parts
            and path.suffix != ".png"
        ]
        contents = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        singular_directory = "Wallpaper"
        self.assertNotIn(f"Pictures/{singular_directory}/", contents)
        self.assertNotIn(f"<XDG Pictures>/{singular_directory}/", contents)
        self.assertIn('self.pictures / "Wallpapers"', HELPER.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
