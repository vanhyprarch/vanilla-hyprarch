#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import configparser
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
THEME = REPOSITORY / "system/usr/share/sddm/themes/vanhyprarch"
SESSION = REPOSITORY / "system/usr/share/wayland-sessions/vanhyprarch.desktop"
CANONICAL_LOGO = REPOSITORY / "home/.config/quickshell/vanhyprarch/assets/logo.svg"


def read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with path.open(encoding="utf-8") as stream:
        parser.read_file(stream)
    return parser


class SddmThemeContractTests(unittest.TestCase):
    def test_exact_theme_inventory(self) -> None:
        self.assertEqual(
            sorted(path.name for path in THEME.iterdir()),
            [
                "LoginScene.qml",
                "Main.qml",
                "SessionResolver.qml",
                "logo.svg",
                "metadata.desktop",
                "theme.conf",
            ],
        )
        self.assertFalse((THEME / "theme.conf.user").exists())

    def test_metadata_selects_qt6_main_and_project_license(self) -> None:
        metadata = read_ini(THEME / "metadata.desktop")["SddmGreeterTheme"]
        self.assertEqual(metadata["Name"], "Vanilla HyprArch")
        self.assertEqual(metadata["Type"], "sddm-theme")
        self.assertEqual(metadata["MainScript"], "Main.qml")
        self.assertEqual(metadata["ConfigFile"], "theme.conf")
        self.assertEqual(metadata["QtVersion"], "6")
        self.assertEqual(metadata["Theme-Id"], "vanhyprarch")
        self.assertEqual(metadata["Theme-API"], "2.0")
        self.assertEqual(metadata["License"], "GPL-2.0-only")
        self.assertNotRegex("\n".join(metadata.values()), r"(?i)omarchy")

    def test_generic_theme_configuration_has_no_machine_binding(self) -> None:
        configuration = read_ini(THEME / "theme.conf")
        self.assertEqual(configuration.sections(), ["General"])
        self.assertEqual(
            dict(configuration["General"]),
            {
                "needsFullUserModel": "false",
                "targetUser": "",
                "targetSessionFile": "",
            },
        )

    def test_distribution_logo_is_exact_canonical_copy(self) -> None:
        canonical = CANONICAL_LOGO.read_bytes()
        distributed = (THEME / "logo.svg").read_bytes()
        self.assertEqual(distributed, canonical)
        self.assertEqual(
            hashlib.sha256(distributed).hexdigest(),
            hashlib.sha256(canonical).hexdigest(),
        )

    def test_normal_scene_has_only_the_accepted_visible_elements(self) -> None:
        scene = (THEME / "LoginScene.qml").read_text(encoding="utf-8")
        main = (THEME / "Main.qml").read_text(encoding="utf-8")
        self.assertEqual(scene.count("TextInput {"), 1)
        self.assertEqual(scene.count("Image {"), 1)
        self.assertIn('source: Qt.resolvedUrl("logo.svg")', scene)
        self.assertIn('text: "F1 Shutdown"', scene)
        self.assertIn('text: "F2 Reboot"', scene)
        self.assertIn('color: "#000000"', main)
        self.assertIn("radius: 0", scene)
        self.assertNotIn("gradient", scene.lower())
        self.assertNotIn("animation", scene.lower())
        literal_texts = re.findall(r'^\s*text:\s*"([^"]*)"', scene, re.MULTILINE)
        self.assertEqual(literal_texts, ["F1 Shutdown", "F2 Reboot"])

    def test_theme_contains_no_forbidden_models_or_visible_features(self) -> None:
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(THEME.glob("*.qml"))
        )
        for forbidden in (
            "userModel",
            "lastUser",
            "lastIndex",
            "UWSM",
            "uwsm",
            "hostName",
            "hostname",
            "Clock",
            "calendar",
            "suspend",
            "hibernate",
            "keyboard.layouts",
            "avatar",
            "Process",
            "WorkerScript",
            "XMLHttpRequest",
            "/home/",
        ):
            self.assertNotIn(forbidden, sources)

    def test_password_and_failure_contract_is_explicit(self) -> None:
        scene = (THEME / "LoginScene.qml").read_text(encoding="utf-8")
        self.assertIn("echoMode: TextInput.Password", scene)
        self.assertIn("cursorVisible: activeFocus", scene)
        self.assertIn("passwordInput.forceActiveFocus()", scene)
        self.assertIn('root.authenticationError = "Authentication failed"', scene)
        self.assertGreaterEqual(scene.count('passwordInput.text = ""'), 2)
        self.assertIn("if (!root.canSubmit || root.submissionLocked)", scene)

    def test_main_fails_closed_and_calls_login_with_resolved_identity(self) -> None:
        main = (THEME / "Main.qml").read_text(encoding="utf-8")
        self.assertIn('configString("targetUser")', main)
        self.assertIn('configString("targetSessionFile")', main)
        self.assertIn("if (root.submitting || !root.bindingValid", main)
        self.assertIn(
            "root.sddmApi.login(root.targetUser, password,\n"
            "            sessionResolver.sessionIndex)",
            main,
        )
        self.assertNotRegex(main, r"\.login\([^,]+,[^,]+,\s*[0-9]+\s*\)")

    def test_session_resolver_uses_named_file_role_and_exact_cardinality(self) -> None:
        resolver = (THEME / "SessionResolver.qml").read_text(encoding="utf-8")
        self.assertIn("required property string file", resolver)
        self.assertIn("entry.sessionFile === root.targetFile", resolver)
        self.assertIn("matches === 1 ? matchingIndex : -1", resolver)
        self.assertIn("matchCount === 1 && sessionIndex >= 0", resolver)
        self.assertNotIn("Qt.UserRole", resolver)
        self.assertNotIn("lastIndex", resolver)

    def test_primary_screen_and_scaling_contract(self) -> None:
        main = (THEME / "Main.qml").read_text(encoding="utf-8")
        scene = (THEME / "LoginScene.qml").read_text(encoding="utf-8")
        self.assertIn("primaryScreenActive", main)
        self.assertIn("interactive: root.primaryScreenActive", main)
        self.assertIn("Math.max(0.72, Math.min(2.0", scene)
        self.assertIn("Math.round(parent.width * 0.72)", scene)
        self.assertIn("Math.round(root.width * 0.25)", scene)

    def test_session_entry_is_exact_direct_wayland_contract(self) -> None:
        desktop = read_ini(SESSION)
        self.assertEqual(desktop.sections(), ["Desktop Entry"])
        self.assertEqual(
            dict(desktop["Desktop Entry"]),
            {
                "Name": "Vanilla HyprArch",
                "Comment": "A curated desktop. A vanilla system.",
                "Exec": "/usr/bin/start-hyprland",
                "TryExec": "/usr/bin/start-hyprland",
                "Type": "Application",
                "DesktopNames": "Hyprland",
            },
        )
        raw = SESSION.read_text(encoding="utf-8")
        self.assertNotRegex(raw, r"(?i)uwsm|/home/|(?:^|[= ])(?:sh|bash|env)(?:[ /]|$)")

    def test_desktop_file_validator_has_only_known_session_extension_diagnostic(self) -> None:
        validator = shutil.which("desktop-file-validate")
        if validator is None:
            self.skipTest("desktop-file-validate is unavailable")
        result = subprocess.run(
            [validator, str(SESSION)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        diagnostics = [line for line in result.stdout.splitlines() if line]
        known_suffix = (
            'error: file contains key "DesktopNames" in group "Desktop Entry", '
            "but keys extending the format should start with \"X-\""
        )
        unexpected = [line for line in diagnostics if not line.endswith(known_suffix)]
        self.assertEqual(unexpected, [])
        if result.returncode != 0:
            self.assertEqual(len(diagnostics), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
