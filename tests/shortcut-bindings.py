#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
BINDINGS = REPOSITORY / "home/.config/hypr/vanhyprarch/bindings.lua"
SHORTCUTS_QML = (
    REPOSITORY
    / "home/.config/quickshell/vanhyprarch/components/Shortcuts.qml"
)
SHORTCUTS_PANEL_QML = (
    REPOSITORY
    / "home/.config/quickshell/vanhyprarch/components/ShortcutsPanel.qml"
)
SEPARATOR = "\x1f"
METADATA_START = "\U000e0001"
METADATA_END = "\U000e007f"

LUA_HARNESS = r'''
local function proxy()
    local value = {}
    return setmetatable(value, {
        __index = function() return proxy() end,
        __call = function() return proxy() end,
    })
end

local dispatchers = proxy()
dispatchers.exec_cmd = function(command) return command end

hl = {
    dsp = dispatchers,
    bind = function(keys, dispatcher, options)
        local opts = options or {}
        io.write(keys, "\31", opts.description or "", "\31",
            tostring(opts.release == true), "\31",
            tostring(opts.availability), "\31", tostring(dispatcher), "\31",
            tostring(opts.locked == true), "\31",
            tostring(opts.repeating == true), "\n")
        return proxy()
    end,
}

assert(loadfile(arg[1]))()
'''


def decode_description(description: str) -> tuple[str, str]:
    start = description.find(METADATA_START)
    if start < 0:
        if METADATA_END in description:
            raise AssertionError("stray metadata terminator")
        return description, ""
    if not description.endswith(METADATA_END):
        raise AssertionError("unterminated metadata")

    encoded = description[start + 1 : -1]
    payload = "".join(chr(ord(character) - 0xE0000) for character in encoded)
    prefix = "vh1;availability="
    if not payload.startswith(prefix) or len(payload) == len(prefix):
        raise AssertionError(f"invalid metadata payload: {payload!r}")
    return description[:start], payload[len(prefix) :]


def evaluate_bindings(installed: bool) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        home = root / "home"
        data = root / "data"
        components = data / "vanhyprarch/components"
        components.mkdir(parents=True)
        home.mkdir()
        if installed:
            (components / "dictation").write_text(
                "vanhyprarch-dictation-v1\n", encoding="utf-8"
            )
        environment = {
            "HOME": str(home),
            "XDG_DATA_HOME": str(data),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        result = subprocess.run(
            ["/usr/bin/lua", "-", str(BINDINGS)],
            input=LUA_HARNESS,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
            env=environment,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr)

    records: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        (
            keys,
            description,
            released,
            leaked_availability,
            dispatcher,
            locked,
            repeating,
        ) = line.split(SEPARATOR)
        visible, availability = decode_description(description)
        category, action = (part.strip() for part in visible.split("|", 1))
        records.append(
            {
                "keys": keys,
                "description": description,
                "visible": visible,
                "category": category,
                "action": action,
                "availability": availability,
                "release": released == "true",
                "leaked_availability": leaked_availability,
                "dispatcher": dispatcher,
                "locked": locked == "true",
                "repeating": repeating == "true",
            }
        )
    return records


class ShortcutBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.absent = evaluate_bindings(False)
        cls.installed = evaluate_bindings(True)

    def test_dictation_bindings_are_actual_conditional_bindings(self) -> None:
        absent_f9 = [item for item in self.absent if item["keys"] == "F9"]
        installed_f9 = [item for item in self.installed if item["keys"] == "F9"]
        self.assertEqual(absent_f9, [])
        self.assertEqual(len(installed_f9), 2)
        self.assertEqual(
            {item["action"] for item in installed_f9},
            {"Start recording", "Stop and transcribe"},
        )
        self.assertEqual(
            {item["release"] for item in installed_f9}, {False, True}
        )
        self.assertTrue(
            all(item["availability"] == "local-dictation" for item in installed_f9)
        )
        self.assertEqual(len(self.installed), len(self.absent) + 2)

    def test_project_metadata_does_not_leak_to_hl_bind(self) -> None:
        self.assertTrue(
            all(item["leaked_availability"] == "nil" for item in self.installed)
        )

    def test_metadata_transport_is_invisible_and_json_safe(self) -> None:
        conditional = [item for item in self.installed if item["availability"]]
        self.assertEqual(len(conditional), 2)
        for item in conditional:
            description = str(item["description"])
            suffix = description[description.index(METADATA_START) :]
            self.assertTrue(all(unicodedata.category(character) == "Cf" for character in suffix))
            document = json.dumps(
                [{"has_description": True, "description": description}],
                ensure_ascii=False,
            )
            self.assertEqual(json.loads(document)[0]["description"], description)
            visible, availability = decode_description(description)
            self.assertEqual(visible, item["visible"])
            self.assertEqual(availability, "local-dictation")

    def test_legacy_descriptions_remain_byte_exact(self) -> None:
        for item in self.absent:
            self.assertEqual(item["description"], item["visible"])
            self.assertNotIn(METADATA_START, str(item["description"]))
        command_center = next(
            item for item in self.absent if item["keys"] == "SUPER + SPACE"
        )
        self.assertEqual(command_center["visible"], "Shell | Open command center")

    def test_no_unexpected_key_phase_conflicts(self) -> None:
        seen: set[tuple[str, bool]] = set()
        for item in self.installed:
            identity = (str(item["keys"]), bool(item["release"]))
            self.assertNotIn(identity, seen, identity)
            seen.add(identity)
        self.assertIn(("F9", False), seen)
        self.assertIn(("F9", True), seen)

    def test_core_system_bindings_use_authoritative_actions(self) -> None:
        lock = next(
            item for item in self.absent if item["keys"] == "SUPER + CTRL + L"
        )
        caffeine = next(
            item for item in self.absent if item["keys"] == "SUPER + CTRL + I"
        )
        background = next(
            item for item in self.absent if item["keys"] == "SUPER + CTRL + SPACE"
        )
        self.assertEqual(
            (lock["category"], lock["action"]), ("System", "Lock system")
        )
        self.assertEqual(
            lock["dispatcher"],
            "qs ipc -c vanhyprarch call vanhyprarch.power lock",
        )
        self.assertEqual(
            (caffeine["category"], caffeine["action"], caffeine["dispatcher"]),
            ("System", "Toggle Caffeine", "vanhyprarch-idle caffeine toggle"),
        )
        self.assertEqual(background["action"], "Choose background")
        self.assertEqual(
            background["dispatcher"],
            "qs ipc -c vanhyprarch call vanhyprarch.backgroundPicker toggle",
        )

    def test_audio_hardware_bindings_follow_exact_contract(self) -> None:
        audio = [item for item in self.absent if item["category"] == "Audio"]
        expected = {
            "XF86AudioRaiseVolume": {
                "description": "Audio | Volume up",
                "dispatcher": "wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+",
                "repeating": True,
            },
            "XF86AudioLowerVolume": {
                "description": "Audio | Volume down",
                "dispatcher": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
                "repeating": True,
            },
            "XF86AudioMute": {
                "description": "Audio | Toggle mute",
                "dispatcher": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
                "repeating": False,
            },
            "XF86AudioMicMute": {
                "description": "Audio | Toggle microphone mute",
                "dispatcher": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
                "repeating": False,
            },
        }
        self.assertEqual({item["keys"] for item in audio}, set(expected))
        for item in audio:
            contract = expected[str(item["keys"])]
            self.assertEqual(item["description"], contract["description"])
            self.assertEqual(item["visible"], contract["description"])
            self.assertEqual(item["dispatcher"], contract["dispatcher"])
            self.assertTrue(item["locked"])
            self.assertEqual(item["repeating"], contract["repeating"])
            self.assertFalse(item["release"])
            self.assertEqual(item["availability"], "")

    def test_super_k_has_no_manual_action_catalog(self) -> None:
        production_qml = SHORTCUTS_QML.read_text(
            encoding="utf-8"
        ) + SHORTCUTS_PANEL_QML.read_text(encoding="utf-8")
        for item in self.installed:
            self.assertNotIn(f'"{item["action"]}"', production_qml)
        self.assertIn('command = ["hyprctl", "-j", "binds"]', production_qml)


if __name__ == "__main__":
    unittest.main()
