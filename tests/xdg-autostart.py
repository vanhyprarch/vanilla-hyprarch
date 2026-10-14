#!/usr/bin/python
"""Test the managed start hook and upstream dex with harmless isolated entries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
CORE = REPOSITORY / "home/.config/hypr/vanhyprarch/core.lua"
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--dex", default=shutil.which("dex"),
                    help="explicit upstream dex executable for isolated package tests")
options, unittest_arguments = parser.parse_known_args()
DEX = options.dex
sys.argv = [sys.argv[0], *unittest_arguments]
VARIABLES = ["DISPLAY", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
             "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "PATH"]

LUA_HARNESS = r'''
local callbacks = {}
local phase = "load"
local function inert()
    return setmetatable({}, {
        __index = function() return inert() end,
        __call = function() return inert() end,
    })
end
hl = inert()
hl.on = function(name, callback)
    assert(callbacks[name] == nil, "duplicate event handler")
    callbacks[name] = callback
end
hl.exec_cmd = function(command)
    io.write(phase, "\0", command, "\0")
end
local function loadCore()
    callbacks = {}
    assert(loadfile(arg[1]))()
end
loadCore()
phase = "start"
callbacks["hyprland.start"]()
phase = "reparse"
loadCore()
phase = "reload"
callbacks["config.reloaded"]()
phase = "new-session"
loadCore()
callbacks["hyprland.start"]()
'''


def executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class StartHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="vanhyprarch-autostart-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = dict(HOME=str(self.root / "home"), XDG_DATA_HOME=str(self.root / "data"),
            PATH="/usr/bin", DISPLAY=":99", WAYLAND_DISPLAY="wayland-test",
            HYPRLAND_INSTANCE_SIGNATURE="fixture-session", XDG_CURRENT_DESKTOP="Hyprland",
            XDG_SESSION_TYPE="wayland", AUTOSTART_TEST_ROOT=str(self.root))

    def hook_commands(self):
        result = subprocess.run(["/usr/bin/lua", "-", str(CORE)], input=LUA_HARNESS,
            env=self.env, capture_output=True, text=True, timeout=5, check=True)
        fields = result.stdout.split("\0")[:-1]
        commands = {}
        for phase, command in zip(fields[::2], fields[1::2]):
            commands.setdefault(phase, []).append(command)
        return commands

    def autostart_command(self):
        commands = [cmd for cmd in self.hook_commands()["start"] if "/usr/bin/dex " in cmd]
        self.assertEqual(len(commands), 1)
        return commands[0]

    def test_start_once_reload_inert_and_unrelated_startup_preserved(self):
        for dictation in (False, True):
            with self.subTest(dictation=dictation):
                if dictation:
                    marker = Path(self.env["XDG_DATA_HOME"]) / "vanhyprarch/components/dictation"
                    marker.parent.mkdir(parents=True)
                    marker.write_text("vanhyprarch-dictation-v1\n")
                commands = self.hook_commands()
                self.assertNotIn("load", commands)
                self.assertNotIn("reparse", commands)
                self.assertEqual(commands["reload"],
                    ["systemctl --user reload vanhyprarch-keyboard-sync.service"])
                self.assertEqual(commands["start"], commands["new-session"])
                self.assertEqual(sum("/usr/bin/dex " in c for c in commands["start"]), 1)
                expected = [f"exec {self.env['HOME']}/.local/bin/vanhyprarch-{helper} session-start"
                            for helper in ("polkit-session", "keyboard-sync", "idle")]
                expected.insert(0, f"exec {self.env['HOME']}/.local/bin/vanhyprarch-appearance renderer-start")
                expected.append("qs -n -c vanhyprarch")
                if dictation:
                    expected.append("systemctl --user start vanhyprarch-voxtype.service")
                self.assertEqual(commands["start"][:-1], expected)
                self.assertNotIn("xdg-desktop-autostart.target", "\n".join(commands["start"]))
                self.assertNotIn("gnome-keyring", "\n".join(commands["start"]))

    def run_command(self, *, publication_fails=False, missing=None):
        command = self.autostart_command()
        log = self.root / "events.jsonl"
        self.env["PUBLICATION_FAILS"] = str(int(publication_fails))
        stub = '''#!/usr/bin/python
import json, os, pathlib, sys
root = pathlib.Path(os.environ["AUTOSTART_TEST_ROOT"])
name = pathlib.Path(sys.argv[0]).name
def record(event, **fields):
    with (root / "events.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(event=event, **fields)) + "\\n")
if name == "publisher":
    record("publication-start", argv=sys.argv[1:])
    if os.environ["PUBLICATION_FAILS"] == "1":
        sys.exit(17)
    record("publication-complete")
elif name == "dex":
    record("dex", argv=sys.argv[1:], path=os.environ["PATH"],
        display=os.environ["WAYLAND_DISPLAY"], desktop=os.environ["XDG_CURRENT_DESKTOP"])
elif name == "logger":
    record("diagnostic", argv=sys.argv[1:])
'''
        for name, path in ("publisher", "/usr/bin/dbus-update-activation-environment"), ("dex", "/usr/bin/dex"), ("logger", "/usr/bin/logger"):
            destination = self.root / name
            executable(destination, stub)
            command = command.replace(path, str(destination))
        env = self.env.copy()
        if missing:
            env[missing] = ""
        result = subprocess.run(["/bin/sh", "-c", command], env=env,
            capture_output=True, text=True, timeout=5)
        events = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, events

    def test_publication_completes_before_dex_with_exact_allowlist(self):
        result, events = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([e["event"] for e in events],
                         ["publication-start", "publication-complete", "dex"])
        self.assertEqual(events[0]["argv"], ["--systemd", *VARIABLES])
        self.assertEqual(events[-1]["argv"], ["--autostart", "--term", "/usr/bin/xdg-terminal-exec"])
        self.assertEqual(events[-1]["path"], self.env["PATH"])
        self.assertEqual(events[-1]["display"], self.env["WAYLAND_DISPLAY"])
        self.assertEqual(events[-1]["desktop"], "Hyprland")

    def test_publication_failure_skips_dex_and_reports_diagnostic(self):
        result, events = self.run_command(publication_fails=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([e["event"] for e in events], ["publication-start", "diagnostic"])
        self.assertIn("Environment publication failed; XDG Autostart skipped", events[-1]["argv"])

    def test_missing_required_environment_skips_publication_and_dex(self):
        for variable in VARIABLES:
            with self.subTest(variable=variable):
                (self.root / "events.jsonl").unlink(missing_ok=True)
                result, events = self.run_command(missing=variable)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([e["event"] for e in events], ["diagnostic"])

    def test_posix_shell_syntax(self):
        subprocess.run(["/bin/sh", "-n", "-c", self.autostart_command()], check=True)


@unittest.skipUnless(DEX, "Install official dex to run upstream desktop-entry tests")
class DexEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="vanhyprarch-dex-entries-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.user = self.root / "config/autostart"
        self.system = self.root / "system/autostart"
        self.later = self.root / "later/autostart"
        for directory in (self.user, self.system, self.later):
            directory.mkdir(parents=True)
        self.recorder = self.root / "record"
        executable(self.recorder, '#!/usr/bin/python\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        self.terminal = self.root / "terminal"
        executable(self.terminal, '''#!/usr/bin/python
import json, subprocess, sys
print(json.dumps(["terminal", *sys.argv[1:]]), flush=True)
assert sys.argv[1] == "-e"
subprocess.run(sys.argv[2:], check=True)
''')
        self.env = dict(HOME=str(self.root), PATH=f"{self.root}:/usr/bin",
            XDG_CONFIG_HOME=str(self.user.parent),
            XDG_CONFIG_DIRS=f"{self.system.parent}:{self.later.parent}",
            XDG_CURRENT_DESKTOP="Hyprland")

    def entry(self, directory, name, label, extra="", arguments=""):
        (directory / name).write_text(
            f"[Desktop Entry]\nType=Application\nName=Fixture\nExec={self.recorder} {label} {arguments}\n{extra}")

    def launch(self, *, returncode=0):
        result = subprocess.run([DEX, "--autostart", "--term", str(self.terminal)],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, returncode, result.stderr)
        return sorted(json.loads(line) for line in result.stdout.splitlines())

    def test_user_system_directories_and_same_filename_precedence(self):
        self.entry(self.system, "override.desktop", "system-shadowed")
        self.entry(self.user, "override.desktop", "user")
        self.entry(self.system, "order.desktop", "system-first")
        self.entry(self.later, "order.desktop", "system-later-shadowed")
        self.entry(self.later, "unique.desktop", "later-unique")
        self.assertEqual(self.launch(), [["later-unique"], ["system-first"], ["user"]])

    def test_hidden_user_entry_suppresses_system_entry(self):
        self.entry(self.system, "hidden.desktop", "system-hidden")
        self.entry(self.user, "hidden.desktop", "user-hidden", "Hidden=true\n")
        self.assertEqual(self.launch(), [])

    def test_onlyshowin_notshowin_and_nodisplay(self):
        for name, label, extra in (
            ("only.desktop", "only-hyprland", "OnlyShowIn=GNOME;Hyprland;\n"),
            ("other.desktop", "other-desktop", "OnlyShowIn=GNOME;\n"),
            ("excluded.desktop", "excluded", "NotShowIn=Hyprland;\n"),
            ("allowed.desktop", "allowed", "NotShowIn=GNOME;\n"),
            ("nodisplay.desktop", "nodisplay", "NoDisplay=true\n"),
        ):
            self.entry(self.user, name, label, extra)
        self.assertEqual(self.launch(), [["allowed"], ["nodisplay"], ["only-hyprland"]])

    def test_tryexec_absolute_relative_missing_and_nonexecutable(self):
        executable(self.root / "available", "#!/bin/sh\nexit 0\n")
        (self.root / "nonexecutable").write_text("not executable")
        for name, label, value in (
            ("absolute.desktop", "absolute", "/usr/bin/true"),
            ("relative.desktop", "relative", "available"),
            ("missing.desktop", "missing", str(self.root / "absent")),
            ("nonexecutable.desktop", "nonexecutable", str(self.root / "nonexecutable")),
        ):
            self.entry(self.user, name, label, f"TryExec={value}\n")
        self.assertEqual(self.launch(), [["absolute"], ["relative"]])

    def test_terminal_true_exec_arguments_and_field_codes(self):
        self.entry(self.user, "terminal.desktop", "terminal-app", "Terminal=true\n",
                   '"argument with spaces" %U')
        self.assertEqual(self.launch(), [
            ["terminal", "-e", str(self.recorder), "terminal-app", "argument with spaces"],
            ["terminal-app", "argument with spaces"],
        ])

    def test_missing_name_based_tryexec_skips_entry_and_continues(self):
        self.entry(self.user, "missing-name.desktop", "missing",
                   "TryExec=vanhyprarch-nonexistent-test-executable\n")
        self.entry(self.user, "valid.desktop", "valid")
        self.assertEqual(self.launch(returncode=1), [["valid"]])


if __name__ == "__main__":
    unittest.main()
