#!/usr/bin/env python3

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
MONITOR_PANEL = (
    REPOSITORY
    / "home/.config/quickshell/vanhyprarch/components/MonitorPanel.qml"
)
DECISIONS = REPOSITORY / "docs/decisions.md"
CURRENT_STATE = REPOSITORY / "docs/current-state.md"


def load_scale_edit_script() -> str:
    source = MONITOR_PANEL.read_text(encoding="utf-8")
    match = re.search(
        r'readonly property string scaleEditScript:\s*\[\n(.*?)\n\s*\]\.join\("\\n"\)',
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("MonitorPanel scaleEditScript was not found")

    lines = []
    for raw_line in match.group(1).splitlines():
        value = raw_line.strip()
        if value.endswith(","):
            value = value[:-1]
        lines.append(json.loads(value))
    return "\n".join(lines)


def machine_configuration(
    connector: str = "HDMI-A-7",
    scale: str = "1.25",
) -> str:
    return f'''-- Local machine settings.

hl.monitor({{
    output = "",
    mode = "preferred",
    position = "auto",
    scale = "auto",
}})

-- Vanilla HyprArch UI-owned field for this explicit output profile.
local vanhyprarchMonitorScale = {scale}

hl.monitor({{
    output = "{connector}",
    mode = "2560x1440@59.95",
    position = "1920x0",
    scale = vanhyprarchMonitorScale,
    bitdepth = 10,
    cm = "auto",
}})

-- Unrelated machine content must remain byte-for-byte identical.
hl.device({{
    name = "test-device",
    sensitivity = -0.25,
}})
'''


class MonitorPanelScaleWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel_source = MONITOR_PANEL.read_text(encoding="utf-8")
        cls.script = load_scale_edit_script()

    def run_writer(
        self,
        configuration: str,
        *,
        connector: str = "HDMI-A-7",
        value: str = "1.50",
        use_xdg: bool = True,
        symlink_target: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path, str, int]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        home = root / "home"
        config_home = root / "xdg-config" if use_xdg else home / ".config"
        machine_directory = config_home / "vanhyprarch/machine"
        machine_directory.mkdir(parents=True)
        target = machine_directory / "hyprland.lua"
        actual_target = root / "actual-machine.lua" if symlink_target else target
        actual_target.write_text(configuration, encoding="utf-8")
        actual_target.chmod(0o640)
        if symlink_target:
            target.symlink_to(actual_target)

        managed_directory = config_home / "hypr/vanhyprarch"
        managed_directory.mkdir(parents=True)
        managed_before = "-- managed bytes must not be changed\n"
        (config_home / "hypr/hyprland.lua").write_text(
            managed_before, encoding="utf-8"
        )
        (managed_directory / "core.lua").write_text(
            managed_before, encoding="utf-8"
        )

        environment = os.environ.copy()
        environment["HOME"] = str(home)
        if use_xdg:
            environment["XDG_CONFIG_HOME"] = str(config_home)
        else:
            environment.pop("XDG_CONFIG_HOME", None)

        result = subprocess.run(
            ["sh", "-c", self.script, "quickshell-scale-edit", connector, value],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

        self.assertEqual(
            (config_home / "hypr/hyprland.lua").read_text(encoding="utf-8"),
            managed_before,
        )
        self.assertEqual(
            (managed_directory / "core.lua").read_text(encoding="utf-8"),
            managed_before,
        )
        return result, actual_target, configuration, stat.S_IMODE(actual_target.stat().st_mode)

    def test_writer_uses_xdg_machine_file_and_preserves_other_bytes(self) -> None:
        before = machine_configuration()
        result, target, original, original_mode = self.run_writer(before)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = original.replace(
            "local vanhyprarchMonitorScale = 1.25",
            "local vanhyprarchMonitorScale = 1.50",
        )
        self.assertEqual(target.read_text(encoding="utf-8"), expected)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), original_mode)
        self.assertIn('scale = "auto"', target.read_text(encoding="utf-8"))

    def test_writer_uses_home_config_fallback(self) -> None:
        result, target, _, _ = self.run_writer(
            machine_configuration(), use_xdg=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "local vanhyprarchMonitorScale = 1.50",
            target.read_text(encoding="utf-8"),
        )

    def test_writer_has_no_public_connector_assumption(self) -> None:
        self.assertNotIn("DP-1", self.panel_source)
        self.assertIn("root.connectorName, preset", self.panel_source)
        self.assertIn(
            'target="$configHome/vanhyprarch/machine/hyprland.lua"',
            self.script,
        )
        self.assertNotIn("$configHome/hypr/hyprland.lua", self.script)
        self.assertNotIn("$configHome/hypr/vanhyprarch", self.script)
        self.assertIn('[ -f "$target" ] && [ ! -L "$target" ]', self.script)
        self.assertIn('stat -c %u -- "$target"', self.script)
        self.assertIn('$(id -u)', self.script)

    def test_writer_rejects_symlink_target(self) -> None:
        before = machine_configuration()
        result, actual_target, original, _ = self.run_writer(
            before, symlink_target=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(actual_target.read_text(encoding="utf-8"), original)

    def test_writer_fails_closed_on_profile_mismatch_or_ambiguity(self) -> None:
        valid = machine_configuration()
        cases = {
            "wrong connector": (valid, "DP-9"),
            "missing token": (
                valid.replace("local vanhyprarchMonitorScale = 1.25\n", ""),
                "HDMI-A-7",
            ),
            "duplicate token": (
                valid.replace(
                    "local vanhyprarchMonitorScale = 1.25",
                    "local vanhyprarchMonitorScale = 1.25\n"
                    "local vanhyprarchMonitorScale = 1.25",
                ),
                "HDMI-A-7",
            ),
            "literal explicit scale": (
                valid.replace(
                    "scale = vanhyprarchMonitorScale", "scale = 1.25"
                ),
                "HDMI-A-7",
            ),
            "fallback uses token": (
                valid.replace('scale = "auto"', "scale = vanhyprarchMonitorScale"),
                "HDMI-A-7",
            ),
            "extra monitor profile": (
                valid
                + '''\nhl.monitor({
    output = "DP-9",
    mode = "preferred",
    position = "auto",
    scale = "auto",
})
''',
                "HDMI-A-7",
            ),
        }
        for name, (configuration, connector) in cases.items():
            with self.subTest(name=name):
                result, target, original, _ = self.run_writer(
                    configuration, connector=connector
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_writer_rejects_non_absolute_xdg_config_home(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        environment = os.environ.copy()
        environment["HOME"] = str(Path(temporary.name) / "home")
        environment["XDG_CONFIG_HOME"] = "relative-config"
        result = subprocess.run(
            [
                "sh",
                "-c",
                self.script,
                "quickshell-scale-edit",
                "HDMI-A-7",
                "1.50",
            ],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_future_keyboard_and_safe_apply_boundaries_are_documented(self) -> None:
        decisions = DECISIONS.read_text(encoding="utf-8")
        current_state = CURRENT_STATE.read_text(encoding="utf-8")

        self.assertIn("systemd-localed", decisions)
        self.assertIn("source of truth for the Hyprland keyboard layout", decisions)
        self.assertIn("subscribe", decisions)
        self.assertIn("localectl --no-convert", decisions)
        self.assertIn("Device-specific keyboard rules remain", decisions)
        self.assertIn("Future milestone; not implemented", decisions)

        self.assertIn("10-second confirmation", decisions)
        self.assertIn("never persisted", decisions)
        self.assertIn("Text Size remains one global preference", decisions)
        self.assertIn("System Keyboard Synchronization", current_state)
        self.assertIn("Monitor Control & Safe Apply", current_state)


if __name__ == "__main__":
    unittest.main()
