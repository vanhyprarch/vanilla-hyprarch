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
CLIPBOARD_KEYS = ("A", "C", "V", "X")

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
local bindings = {}

hl = {
    dsp = dispatchers,
    bind = function(keys, dispatcher, options)
        local opts = options or {}
        bindings[keys] = { dispatcher = dispatcher, options = opts }
        if arg[2] ~= "callbacks" then
            io.write(keys, "\31", opts.description or "", "\31",
                tostring(opts.release == true), "\31",
                tostring(opts.availability), "\31", tostring(dispatcher), "\31",
                tostring(opts.locked == true), "\31",
                tostring(opts.repeating == true), "\n")
        end
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


def run_lua(harness: str, *, installed: bool = False, mode: str = "catalog") -> str:
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
            ["/usr/bin/lua", "-", str(BINDINGS), mode],
            input=harness,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
            env=environment,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout


def evaluate_bindings(installed: bool) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in run_lua(LUA_HARNESS, installed=installed).splitlines():
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


def clipboard_events(windows: list[dict[str, object] | None], *, rapid: bool = False) -> list[tuple[str, ...]]:
    fixtures = []
    for window in windows:
        fields = [] if window is None else [
            f"[{json.dumps(key)}] = {json.dumps(value) if value is not None else 'nil'}"
            for key, value in window.items()
        ]
        literal = "nil" if window is None else "{" + ", ".join(fields) + "}"
        fixtures.append("{ window = " + literal + " }")
    harness = LUA_HARNESS + r'''
local function forbidden() error("clipboard callback attempted a non-native action") end
hl.exec_cmd = forbidden
hl.dsp.exec_cmd = forbidden
hl.dsp.send_shortcut = forbidden
os.execute = forbidden
io.popen = forbidden

local reads = 0
local currentWindow
local now = 0
local timers = {}
local eventCount = 0
local presses = 0
local scheduled = 0
local collectedHandles = 0
local balance = {}
hl.get_active_window = function()
    reads = reads + 1
    return currentWindow
end
hl.dsp.send_key_state = function(spec)
    local count = 0
    for field in pairs(spec) do
        assert(field == "mods" or field == "key" or field == "state")
        count = count + 1
    end
    assert(count == 3, "unexpected key-event arguments or window target")
    return function()
        local chord = spec.mods .. ":" .. spec.key
        balance[chord] = (balance[chord] or 0) + (spec.state == "down" and 1 or -1)
        assert(balance[chord] >= 0, "release did not match a press")
        if spec.state == "down" then presses = presses + 1 end
        eventCount = eventCount + 1
        io.write(spec.mods, "\31", spec.key, "\31", spec.state, "\n")
    end
end
hl.dispatch = function(dispatcher)
    assert(type(dispatcher) == "function", "unexpected dispatcher")
    dispatcher()
end
hl.timer = function(callback, options)
    assert(type(callback) == "function")
    assert(presses == scheduled + 1, "timer must be scheduled after its key-down")
    assert(options.timeout == 50 and options.type == "oneshot")
    for field in pairs(options) do
        assert(field == "timeout" or field == "type")
    end
    scheduled = scheduled + 1
    table.insert(timers, { callback = callback, due = now + options.timeout })
    -- Native Hyprland owns the callback independently of the returned handle.
    return setmetatable({}, { __gc = function() collectedHandles = collectedHandles + 1 end })
end
local function advance(milliseconds)
    now = now + milliseconds
    local pending = timers
    timers = {}
    for _, timer in ipairs(pending) do
        if timer.due <= now then
            timer.callback()
        else
            table.insert(timers, timer)
        end
    end
end
local function releaseTimers()
    local before = eventCount
    local count = #timers
    local beforeReads = reads
    currentWindow = nil
    collectgarbage("collect")
    assert(collectedHandles == scheduled, "timer unexpectedly needs its Lua handle")
    advance(49)
    assert(eventCount == before, "key-up fired before 50 ms")
    advance(1)
    assert(eventCount == before + count and #timers == 0, "pending release was lost")
    assert(reads == beforeReads, "release must not reclassify focus")
    for _, pending in pairs(balance) do
        assert(pending == 0, "unbalanced key events after timers fired")
    end
end
''' + "\nlocal fixtures = {" + ", ".join(fixtures) + "}\nlocal rapid = " + str(rapid).lower() + r'''
for _, fixture in ipairs(fixtures) do
    for _, key in ipairs({ "A", "C", "V", "X" }) do
        currentWindow = fixture.window
        local binding = assert(bindings["SUPER + " .. key])
        for option in pairs(binding.options) do
            assert(option == "description", "unexpected clipboard binding flag")
        end
        local before = reads
        local beforeEvents, beforeTimers = eventCount, #timers
        binding.dispatcher()
        assert(reads == before + 1, "focus must be read once per activation")
        local suitable = currentWindow and currentWindow.mapped == true
            and currentWindow.accepts_input == true
        local expected = suitable and 1 or 0
        assert(eventCount == beforeEvents + expected, "press must precede its timer")
        assert(#timers == beforeTimers + expected, "one release timer is required per press")
        if not rapid then releaseTimers() end
    end
end
if rapid then releaseTimers() end
'''
    return [tuple(line.split(SEPARATOR)) for line in run_lua(harness, mode="callbacks").splitlines()]


class ShortcutBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.absent = evaluate_bindings(False)
        cls.installed = evaluate_bindings(True)

    def test_clipboard_bindings_are_described_once_without_native_chord_changes(self) -> None:
        for records in (self.absent, self.installed):
            for key, action in (("A", "Select all"), ("C", "Copy"), ("V", "Paste"), ("X", "Cut")):
                matches = [item for item in records if item["keys"] == f"SUPER + {key}"]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["description"], f"Clipboard | {action}")
                self.assertTrue(str(matches[0]["dispatcher"]).startswith("function:"))
                for flag in ("locked", "repeating", "release", "availability"):
                    self.assertFalse(matches[0][flag])
                for mods in ("CTRL", "CTRL + SHIFT"):
                    self.assertFalse(any(item["keys"] == f"{mods} + {key}" for item in records))

    def assert_clipboard_modifiers(self, window: dict[str, object], mods: str) -> None:
        expected = [(mods if key in ("C", "V") else "CTRL", key, state)
                    for key in CLIPBOARD_KEYS for state in ("down", "up")]
        self.assertEqual(clipboard_events([{"mapped": True, "accepts_input": True, **window}]), expected)

    def test_exact_terminal_classes_and_initial_classes_use_terminal_shortcuts(self) -> None:
        for identifier in ("foot", "footclient", "org.codeberg.dnkl.foot", "Alacritty",
                "kitty", "com.mitchellh.ghostty", "wezterm", "org.wezfurlong.wezterm"):
            for field in ("class", "initial_class"):
                for other in (None, "changed.application.id"):
                    with self.subTest(identifier=identifier, field=field, other=other):
                        window = {"class": other, "initial_class": other, field: identifier}
                        self.assert_clipboard_modifiers(window, "CTRL SHIFT")

    def test_graphical_and_unknown_classes_use_plain_control(self) -> None:
        for identifier in ("firefox", "thunar", "keepassxc", "org.telegram.desktop",
                "xterm", "custom-terminal", "foot-extra", "org.codeberg.dnkl.foot.extra",
                "Foot", "alacritty", "kittycat", "wezterm-extra", "com.mitchellh.ghostty.extra",
                "org.omarchy.terminal", "TUI.float", "", None):
            with self.subTest(identifier=identifier):
                self.assert_clipboard_modifiers({"class": identifier, "initial_class": identifier,
                    "title": "foot terminal"}, "CTRL")
        self.assert_clipboard_modifiers({"class": "xwayland-test", "xwayland": True}, "CTRL")
        self.assert_clipboard_modifiers({}, "CTRL")

    def test_missing_unmapped_and_non_input_windows_do_not_forward(self) -> None:
        windows = [None, {}, {"class": "foot", "mapped": False, "accepts_input": True},
            {"class": "foot", "mapped": True, "accepts_input": False},
            {"class": "foot", "mapped": True}, {"class": "foot", "accepts_input": True}]
        self.assertEqual(clipboard_events(windows), [])

    def test_select_all_and_cut_keep_plain_control_in_terminals(self) -> None:
        windows = [{"mapped": True, "accepts_input": True, "class": name}
                   for name in ("firefox", "foot", "Alacritty", "kitty",
                                "com.mitchellh.ghostty", "org.wezfurlong.wezterm")]
        events = [event for event in clipboard_events(windows) if event[1] in ("A", "X")]
        expected = [("CTRL", key, state) for _ in windows
                    for key in ("A", "X") for state in ("down", "up")]
        self.assertEqual(events, expected)

    def test_focus_changes_keep_each_shortcut_pair_balanced(self) -> None:
        windows = [{"mapped": True, "accepts_input": True, "class": name}
                   for name in ("foot", "firefox", "footclient", "thunar")]
        expected = [(mods if key in ("C", "V") else "CTRL", key, state)
                    for mods in ("CTRL SHIFT", "CTRL", "CTRL SHIFT", "CTRL")
                    for key in CLIPBOARD_KEYS for state in ("down", "up")]
        self.assertEqual(clipboard_events(windows), expected)

    def test_rapid_invocations_keep_independent_release_callbacks_alive(self) -> None:
        windows = [{"mapped": True, "accepts_input": True, "class": name}
                   for name in ("foot", "firefox", "kitty", "thunar") * 10]
        modifiers = ("CTRL SHIFT", "CTRL", "CTRL SHIFT", "CTRL") * 10
        expected = [(mods if key in ("C", "V") else "CTRL", key, state)
                    for state in ("down", "up")
                    for mods in modifiers for key in CLIPBOARD_KEYS]
        self.assertEqual(clipboard_events(windows, rapid=True), expected)

    def test_user_override_can_unbind_and_replace_clipboard_shortcuts(self) -> None:
        harness = LUA_HARNESS + r'''
local originalTerminal = bindings["SUPER + RETURN"]
hl.unbind = function(key) bindings[key] = nil end
for _, key in ipairs({ "A", "C", "V", "X" }) do
    hl.unbind("SUPER + " .. key)
    assert(bindings["SUPER + " .. key] == nil)
    hl.bind("SUPER + " .. key, function() end, { description = "Custom " .. key })
    assert(bindings["SUPER + " .. key].options.description == "Custom " .. key)
end
assert(bindings["SUPER + RETURN"] == originalTerminal)
'''
        self.assertEqual(run_lua(harness, mode="callbacks"), "")

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
