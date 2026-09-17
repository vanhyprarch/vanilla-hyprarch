#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest import mock


REPOSITORY = Path(__file__).resolve().parent.parent
HELPER = REPOSITORY / "bin" / "vanhyprarch-screenshot"
HYPRLAND_CONFIG = REPOSITORY / "home/.config/hypr/hyprland.lua"
LOADER = importlib.machinery.SourceFileLoader("vanhyprarch_screenshot", str(HELPER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
if SPEC is None:
    raise RuntimeError("could not load screenshot helper")
screenshot = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = screenshot
LOADER.exec_module(screenshot)


MONITORS = [
    {
        "id": 0,
        "x": 0,
        "y": 0,
        "width": 3840,
        "height": 2160,
        "scale": 1.25,
        "transform": 0,
        "disabled": False,
        "activeWorkspace": {"id": 1},
        "specialWorkspace": {"id": 0},
    }
]
CLIENTS = [
    {
        "mapped": True,
        "hidden": False,
        "visible": True,
        "at": [100, 200],
        "size": [800, 600],
        "workspace": {"id": 1},
        "monitor": 0,
        "pinned": False,
    }
]


class FakeRunner:
    def __init__(self) -> None:
        self.monitors: Any = MONITORS
        self.clients: Any = CLIENTS
        self.selection: str | None = "100,200 800x600\n"
        self.selection_error = ""
        self.clipboard_returncode = 0
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.clipboard_bytes: bytes | None = None

    def __call__(self, arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        self.calls.append((list(arguments), dict(kwargs)))
        command = arguments[0]
        if command == screenshot.HYPRCTL:
            payload = self.monitors if arguments[1] == "monitors" else self.clients
            return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")
        if command == screenshot.SLURP:
            if self.selection is None:
                return subprocess.CompletedProcess(
                    arguments, 1, "", self.selection_error
                )
            return subprocess.CompletedProcess(arguments, 0, self.selection, "")
        if command == screenshot.GRIM:
            Path(arguments[-1]).write_bytes(screenshot.PNG_SIGNATURE + b"test-png")
            return subprocess.CompletedProcess(arguments, 0, "", "")
        if command == screenshot.WL_COPY:
            clipboard_input = kwargs.get("stdin")
            self.clipboard_bytes = clipboard_input.read()
            error = b"clipboard unavailable" if self.clipboard_returncode else b""
            if error:
                error_output = kwargs.get("stderr")
                error_output.write(error)
                error_output.flush()
            return subprocess.CompletedProcess(
                arguments, self.clipboard_returncode, b"", None
            )
        raise AssertionError(f"unexpected command: {arguments}")


class ScreenshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="vanhyprarch-screenshot-test."
        )
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.runtime = self.root / "runtime"
        self.home.mkdir()
        self.runtime.mkdir()
        self.environ = {
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
        }
        self.moment = datetime(2026, 9, 17, 14, 5, 6)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def evaluated_session_path(self, inherited_path: str) -> str:
        harness = r'''
local environment = {}
local function noop(...)
    return {}
end

hl = setmetatable({}, { __index = function() return noop end })
hl.env = function(name, value)
    environment[name] = value
end
hl.on = function(event, callback)
    if event == "hyprland.start" then
        assert(environment.PATH ~= nil, "PATH was set after session startup")
    end
end
dofile = function(path) end

assert(loadfile(arg[1]))()
io.write(environment.PATH)
'''
        result = subprocess.run(
            ["/usr/bin/lua", "-", str(HYPRLAND_CONFIG)],
            input=harness,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
            env={"HOME": str(self.home), "PATH": inherited_path},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_screenshot_directory_uses_configured_xdg_pictures(self) -> None:
        config = self.home / ".config"
        config.mkdir()
        (config / "user-dirs.dirs").write_text(
            'XDG_PICTURES_DIR="$HOME/Images and Pictures"\n', encoding="utf-8"
        )
        self.assertEqual(
            screenshot.screenshot_directory(self.environ),
            self.home / "Images and Pictures" / "Screenshots",
        )

    def test_screenshot_directory_falls_back_to_home_pictures(self) -> None:
        self.assertEqual(
            screenshot.screenshot_directory(self.environ),
            self.home / "Pictures" / "Screenshots",
        )

    def test_unsafe_xdg_pictures_value_is_not_executed(self) -> None:
        config = self.home / ".config"
        config.mkdir()
        marker = self.root / "must-not-exist"
        (config / "user-dirs.dirs").write_text(
            f'XDG_PICTURES_DIR="$(touch {marker})"\n', encoding="utf-8"
        )
        self.assertEqual(
            screenshot.screenshot_directory(self.environ),
            self.home / "Pictures" / "Screenshots",
        )
        self.assertFalse(marker.exists())

    def test_filename_format_and_collision_suffix(self) -> None:
        self.assertEqual(
            screenshot.filename_for(self.moment),
            "screenshot-2026-09-17_14-05-06.png",
        )
        runner = FakeRunner()
        output = self.home / "Pictures" / "Screenshots"
        output.mkdir(parents=True)
        (output / screenshot.filename_for(self.moment)).write_bytes(b"existing")
        saved = screenshot.run_screenshot(self.environ, runner, self.moment)
        self.assertEqual(
            saved, output / "screenshot-2026-09-17_14-05-06-1.png"
        )
        self.assertEqual(
            (output / screenshot.filename_for(self.moment)).read_bytes(), b"existing"
        )

    def test_monitor_geometry_fractional_scale_and_transforms(self) -> None:
        monitors = [
            MONITORS[0],
            {
                "id": 1,
                "x": -1080,
                "y": 0,
                "width": 2160,
                "height": 3840,
                "scale": 2,
                "transform": 1,
                "activeWorkspace": {"id": 2},
                "specialWorkspace": {"id": 0},
            },
            {
                "id": 2,
                "x": 3072,
                "y": 0,
                "width": 2160,
                "height": 3840,
                "scale": 2,
                "transform": 5,
                "activeWorkspace": {"id": 3},
                "specialWorkspace": {"id": 0},
            },
        ]
        self.assertEqual(
            screenshot.monitor_rectangles(monitors),
            [
                screenshot.Rectangle(0, 0, 3072, 1728),
                screenshot.Rectangle(-1080, 0, 1920, 1080),
                screenshot.Rectangle(3072, 0, 1920, 1080),
            ],
        )

    def test_windows_filter_hidden_unmapped_invisible_and_inactive(self) -> None:
        visible = CLIENTS[0]
        hidden = {**visible, "hidden": True, "at": [1, 1]}
        unmapped = {**visible, "mapped": False, "at": [2, 2]}
        invisible = {**visible, "visible": False, "at": [3, 3]}
        inactive = {**visible, "workspace": {"id": 9}, "at": [4, 4]}
        pinned = {
            **visible,
            "workspace": {"id": 9},
            "pinned": True,
            "at": [50, 60],
            "size": [70, 80],
        }
        self.assertEqual(
            screenshot.window_rectangles(
                [visible, hidden, unmapped, invisible, inactive, pinned], MONITORS
            ),
            [
                screenshot.Rectangle(100, 200, 800, 600),
                screenshot.Rectangle(50, 60, 70, 80),
            ],
        )

    def test_smart_rectangles_remove_duplicates_and_put_windows_first(self) -> None:
        runner = FakeRunner()
        runner.clients = CLIENTS + CLIENTS
        rectangles = screenshot.smart_rectangles(runner)
        self.assertEqual(
            rectangles,
            [
                screenshot.Rectangle(100, 200, 800, 600),
                screenshot.Rectangle(0, 0, 3072, 1728),
            ],
        )

    def test_slurp_uses_unrestricted_argv_and_predefined_input(self) -> None:
        runner = FakeRunner()
        rectangles = [
            screenshot.Rectangle(10, 20, 30, 40),
            screenshot.Rectangle(0, 0, 3072, 1728),
        ]
        geometry = screenshot.select_geometry(rectangles, runner)
        self.assertEqual(geometry, "100,200 800x600")
        arguments, kwargs = runner.calls[-1]
        self.assertEqual(arguments, ["/usr/bin/slurp"])
        self.assertEqual(kwargs["input"], "10,20 30x40\n0,0 3072x1728\n")
        self.assertNotIn("-r", arguments)
        self.assertIs(kwargs["shell"], False)

    def test_invalid_slurp_geometry_is_rejected_before_capture(self) -> None:
        runner = FakeRunner()
        runner.selection = "100,200 0x600\n"
        with self.assertRaises(screenshot.ScreenshotError):
            screenshot.run_screenshot(self.environ, runner, self.moment)
        self.assertFalse((self.home / "Pictures").exists())
        commands = [arguments[0] for arguments, _ in runner.calls]
        self.assertNotIn(screenshot.GRIM, commands)
        self.assertNotIn(screenshot.WL_COPY, commands)

    def test_cancellation_creates_no_screenshot_and_does_not_copy(self) -> None:
        runner = FakeRunner()
        runner.selection = None
        saved = screenshot.run_screenshot(self.environ, runner, self.moment)
        self.assertIsNone(saved)
        self.assertFalse((self.home / "Pictures").exists())
        commands = [arguments[0] for arguments, _ in runner.calls]
        self.assertNotIn(screenshot.GRIM, commands)
        self.assertNotIn(screenshot.WL_COPY, commands)

    def test_slurp_failure_is_not_misreported_as_cancellation(self) -> None:
        runner = FakeRunner()
        runner.selection = None
        runner.selection_error = "wayland connection failed"
        with self.assertRaisesRegex(
            screenshot.ScreenshotError, "wayland connection failed"
        ):
            screenshot.run_screenshot(self.environ, runner, self.moment)
        self.assertFalse((self.home / "Pictures").exists())

    def test_grim_and_clipboard_argv_are_exact(self) -> None:
        runner = FakeRunner()
        saved = screenshot.run_screenshot(self.environ, runner, self.moment)
        self.assertIsNotNone(saved)
        assert saved is not None
        grim_arguments = next(
            arguments for arguments, _ in runner.calls if arguments[0] == screenshot.GRIM
        )
        self.assertEqual(
            grim_arguments[:5],
            ["/usr/bin/grim", "-t", "png", "-g", "100,200 800x600"],
        )
        self.assertEqual(len(grim_arguments), 6)
        self.assertRegex(grim_arguments[5], r"/\.vanhyprarch-screenshot-.*\.png$")
        clipboard_arguments, clipboard_kwargs = next(
            (arguments, kwargs)
            for arguments, kwargs in runner.calls
            if arguments[0] == screenshot.WL_COPY
        )
        self.assertEqual(
            clipboard_arguments, ["/usr/bin/wl-copy", "--type", "image/png"]
        )
        self.assertIsNot(clipboard_kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(runner.clipboard_bytes, saved.read_bytes())
        for _, kwargs in runner.calls:
            self.assertIs(kwargs["shell"], False)

    def test_daemonized_clipboard_provider_does_not_retain_runtime_lock(self) -> None:
        provider_pid_file = self.root / "clipboard-provider.pid"
        stop_file = self.root / "stop-clipboard-provider"
        fake_wl_copy = self.root / "wl-copy"
        fake_wl_copy.write_text(
            """#!/usr/bin/python
import os
import sys
import time
from pathlib import Path

if sys.argv[1:] != ["--type", "image/png"]:
    raise SystemExit(64)
sys.stdin.buffer.read()
provider_pid = os.fork()
if provider_pid:
    os._exit(0)
Path(sys.argv[0] + ".pid-target").write_text(str(os.getpid()), encoding="ascii")
deadline = time.monotonic() + 5
stop = Path(sys.argv[0] + ".stop-target")
while not stop.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
os._exit(0)
""",
            encoding="utf-8",
        )
        fake_wl_copy.chmod(0o755)
        (self.root / "wl-copy.pid-target").symlink_to(provider_pid_file)
        (self.root / "wl-copy.stop-target").symlink_to(stop_file)

        class DaemonizingClipboardRunner(FakeRunner):
            def __call__(
                self, arguments: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[Any]:
                if arguments[0] == screenshot.WL_COPY:
                    self.calls.append((list(arguments), dict(kwargs)))
                    return subprocess.run(arguments, **kwargs)
                return super().__call__(arguments, **kwargs)

        def provider_is_alive(pid: int) -> bool:
            try:
                state = Path(f"/proc/{pid}/stat").read_text(
                    encoding="utf-8"
                ).split()[2]
            except (FileNotFoundError, OSError, IndexError):
                return False
            return state not in {"X", "Z"}

        provider_pid: int | None = None
        try:
            with mock.patch.object(screenshot, "WL_COPY", str(fake_wl_copy)):
                first = DaemonizingClipboardRunner()
                saved = screenshot.run_screenshot(
                    self.environ, first, self.moment
                )
                self.assertIsNotNone(saved)

                deadline = time.monotonic() + 1
                while not provider_pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(provider_pid_file.exists())
                provider_pid = int(provider_pid_file.read_text(encoding="ascii"))
                self.assertTrue(provider_is_alive(provider_pid))

                second = DaemonizingClipboardRunner()
                second.selection = None
                self.assertIsNone(
                    screenshot.run_screenshot(self.environ, second, self.moment)
                )
                self.assertTrue(provider_is_alive(provider_pid))

                _, clipboard_kwargs = next(
                    (arguments, kwargs)
                    for arguments, kwargs in first.calls
                    if arguments[0] == str(fake_wl_copy)
                )
                self.assertIsNot(clipboard_kwargs["stderr"], subprocess.PIPE)
        finally:
            stop_file.touch()
            if provider_pid is not None:
                deadline = time.monotonic() + 1
                while provider_is_alive(provider_pid) and time.monotonic() < deadline:
                    time.sleep(0.01)

    def test_runtime_lock_rejects_concurrent_session(self) -> None:
        with screenshot.runtime_lock(self.environ):
            with self.assertRaises(screenshot.ScreenshotBusy):
                with screenshot.runtime_lock(self.environ):
                    self.fail("second lock unexpectedly succeeded")

    def test_clipboard_failure_preserves_saved_png(self) -> None:
        runner = FakeRunner()
        runner.clipboard_returncode = 1
        with self.assertRaises(screenshot.ClipboardCopyError) as raised:
            screenshot.run_screenshot(self.environ, runner, self.moment)
        saved = raised.exception.saved_path
        self.assertEqual(str(raised.exception), "clipboard unavailable")
        self.assertTrue(saved.is_file())
        self.assertTrue(saved.read_bytes().startswith(screenshot.PNG_SIGNATURE))

    def test_helper_contains_no_shell_interpreter_or_dynamic_shell_execution(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("/bin/sh", source)
        self.assertNotIn("/usr/bin/bash", source)
        self.assertNotIn("eval(", source)
        self.assertFalse(re.search(r"subprocess\.(?:call|Popen|run)\([^\n]*['\"]sh['\"]", source))

    def test_command_binding_and_required_packages_are_tracked(self) -> None:
        bindings = (REPOSITORY / "home/.config/hypr/bindings.lua").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'bind("PRINT", "Capture", "Screenshot", '
            'hl.dsp.exec_cmd("vanhyprarch-screenshot"))',
            bindings,
        )
        packages = set(
            (REPOSITORY / "packages/official.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertTrue({"grim", "slurp", "wl-clipboard"} <= packages)
        self.assertTrue({"hyprpicker", "jq", "wayfreeze"}.isdisjoint(packages))
        self.assertTrue(os.access(HELPER, os.X_OK))

    def test_session_path_prepends_local_bin_once_before_autostart(self) -> None:
        local_bin = str(self.home / ".local/bin")
        initial = "/usr/local/bin::/usr/bin:"
        expected = f"{local_bin}:{initial}"
        first_evaluation = self.evaluated_session_path(initial)
        self.assertEqual(first_evaluation, expected)
        self.assertEqual(self.evaluated_session_path(first_evaluation), expected)
        self.assertEqual(first_evaluation.split(":").count(local_bin), 1)
        self.assertEqual(self.evaluated_session_path(""), local_bin)

        duplicated = f"/usr/local/bin:{local_bin}:/usr/bin:{local_bin}"
        self.assertEqual(
            self.evaluated_session_path(duplicated),
            f"{local_bin}:/usr/local/bin:/usr/bin",
        )

    def test_session_path_requires_home(self) -> None:
        harness = r'''
local function noop(...)
    return {}
end
hl = setmetatable({}, { __index = function() return noop end })
hl.env = function(name, value) end
hl.on = function(event, callback) end
dofile = function(path) end
assert(loadfile(arg[1]))()
'''
        result = subprocess.run(
            ["/usr/bin/lua", "-", str(HYPRLAND_CONFIG)],
            input=harness,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
            env={"HOME": "", "PATH": "/usr/bin"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HOME is not set", result.stderr)

    def test_screenshot_deployment_contract_keeps_transitional_workarounds(self) -> None:
        installation = (
            REPOSITORY / "docs/installation-strategy.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`vanhyprarch-screenshot`, under `$HOME/.local/bin`", installation)
        self.assertIn("production deployment uses regular\nfiles", installation)

        hyprland = HYPRLAND_CONFIG.read_text(encoding="utf-8")
        self.assertIn(
            'sh -lc \'export PATH="$HOME/.local/bin:$PATH"; '
            "exec hypridle -v'",
            hyprland,
        )
        idle_controller = (
            REPOSITORY
            / "home/.config/quickshell/vanhyprarch/components/IdleController.qml"
        ).read_text(encoding="utf-8")
        self.assertIn('home + "/.local/bin/vanhyprarch-idle"', idle_controller)
        self.assertIn('environment: ({ "PATH": root.processPath })', idle_controller)


if __name__ == "__main__":
    unittest.main()
