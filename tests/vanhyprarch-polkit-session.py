#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import shutil
import socket
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parent.parent
HELPER = REPOSITORY / "bin/vanhyprarch-polkit-session"
DROP_IN = (
    REPOSITORY
    / "home/.config/systemd/user/hyprpolkitagent.service.d/10-vanhyprarch-session-lifecycle.conf"
)
PACKAGE_UNIT = Path("/usr/lib/systemd/user/hyprpolkitagent.service")
CORE = REPOSITORY / "home/.config/hypr/vanhyprarch/core.lua"
POWER_ACTIONS = (
    REPOSITORY
    / "home/.config/quickshell/vanhyprarch/components/PowerActions.qml"
)
MANIFEST = REPOSITORY / "deployment/ownership-v1.toml"


def load_helper() -> object:
    loader = importlib.machinery.SourceFileLoader(
        "vanhyprarch_polkit_session", str(HELPER)
    )
    specification = importlib.util.spec_from_loader(loader.name, loader)
    assert specification is not None
    module = importlib.util.module_from_spec(specification)
    loader.exec_module(module)
    return module


helper = load_helper()


class FakeSystemd:
    def __init__(self, state: str = "inactive") -> None:
        self.state = state
        self.agent_count = 1 if state == "active" else 0
        self.operations: list[tuple[str, ...]] = []
        self.fail_operation = ""

    def __call__(self, arguments: object) -> int:
        operation = tuple(arguments)
        self.operations.append(operation)
        if operation[0] == self.fail_operation:
            return 1
        if operation[0] == "reset-failed":
            if self.state == "failed":
                self.state = "inactive"
        elif operation[0] == "restart":
            self.state = "active"
            self.agent_count = 1
        elif operation[0] == "stop":
            self.state = "inactive"
            self.agent_count = 0
        return 0


class PolkitSessionLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temporary.name) / "runtime"
        self.signature = "test_signature_123"
        self.wayland_display = "wayland-test"
        self.instance = self.runtime / "hypr" / self.signature
        self.instance.mkdir(parents=True)
        self.sockets: list[socket.socket] = []
        for path in (
            self.runtime / self.wayland_display,
            self.instance / ".socket.sock",
        ):
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            self.sockets.append(listener)
        self.environment = {
            "XDG_RUNTIME_DIR": str(self.runtime),
            "HYPRLAND_INSTANCE_SIGNATURE": self.signature,
            "WAYLAND_DISPLAY": self.wayland_display,
            "DISPLAY": ":1",
        }

    def tearDown(self) -> None:
        for listener in self.sockets:
            listener.close()
        self.temporary.cleanup()

    def call_with_session(self, function: object, *arguments: object) -> object:
        with mock.patch.dict(os.environ, self.environment, clear=True):
            return function(*arguments)

    def test_active_wayland_session_satisfies_service_condition(self) -> None:
        self.assertEqual(self.call_with_session(helper.condition), 0)

    def test_absent_compositor_skips_start_without_a_restart_storm(self) -> None:
        self.sockets[1].close()
        self.sockets.pop()
        (self.instance / ".socket.sock").unlink()
        self.assertEqual(self.call_with_session(helper.condition), 1)
        drop_in = DROP_IN.read_text(encoding="utf-8")
        self.assertIn("ExecCondition=%h/.local/bin/vanhyprarch-polkit-session condition", drop_in)
        self.assertIn("RestartSec=1s", drop_in)

    def test_prior_start_limit_failure_is_cleared_before_one_agent_starts(self) -> None:
        systemd = FakeSystemd("failed")
        result = self.call_with_session(helper.session_start, systemd)
        self.assertEqual(result, 0)
        self.assertEqual(
            systemd.operations,
            [
                (
                    "import-environment",
                    "HYPRLAND_INSTANCE_SIGNATURE",
                    "WAYLAND_DISPLAY",
                    "DISPLAY",
                ),
                ("reset-failed", "hyprpolkitagent.service"),
                ("restart", "hyprpolkitagent.service"),
            ],
        )
        self.assertEqual(systemd.state, "active")
        self.assertEqual(systemd.agent_count, 1)

    def test_repeated_session_start_never_duplicates_the_agent(self) -> None:
        systemd = FakeSystemd("inactive")
        self.assertEqual(self.call_with_session(helper.session_start, systemd), 0)
        self.assertEqual(self.call_with_session(helper.session_start, systemd), 0)
        self.assertEqual(systemd.agent_count, 1)
        self.assertEqual(
            systemd.operations.count(("restart", "hyprpolkitagent.service")), 2
        )

    def test_failed_environment_import_cannot_start_the_agent(self) -> None:
        systemd = FakeSystemd("failed")
        systemd.fail_operation = "import-environment"
        self.assertEqual(self.call_with_session(helper.session_start, systemd), 1)
        self.assertEqual(
            systemd.operations,
            [
                (
                    "import-environment",
                    "HYPRLAND_INSTANCE_SIGNATURE",
                    "WAYLAND_DISPLAY",
                    "DISPLAY",
                )
            ],
        )
        self.assertEqual(systemd.state, "failed")

    def test_graceful_logout_stops_agent_before_hyprshutdown(self) -> None:
        systemd = FakeSystemd("active")
        events: list[tuple[str, ...]] = []

        def execer(path: str, arguments: object) -> None:
            events.append(("exec", path, *arguments))

        runner = lambda arguments: (
            events.append(("systemctl", *arguments)), systemd(arguments)
        )[1]
        self.assertEqual(helper.logout(runner, execer), 0)
        self.assertEqual(
            events,
            [
                ("systemctl", "stop", "hyprpolkitagent.service"),
                ("exec", "/usr/bin/hyprshutdown", "/usr/bin/hyprshutdown"),
            ],
        )
        self.assertEqual(systemd.agent_count, 0)

    def test_failed_service_stop_prevents_compositor_shutdown(self) -> None:
        systemd = FakeSystemd("active")
        systemd.fail_operation = "stop"
        execer = mock.Mock()
        self.assertEqual(helper.logout(systemd, execer), 1)
        execer.assert_not_called()
        self.assertEqual(systemd.agent_count, 1)

    def test_active_session_crash_policy_keeps_package_recovery(self) -> None:
        package = PACKAGE_UNIT.read_text(encoding="utf-8")
        self.assertIn("Restart=on-failure", package)
        self.assertEqual(self.call_with_session(helper.condition), 0)
        self.assertEqual(
            PACKAGE_UNIT.read_text(encoding="utf-8"), package,
            "the package unit changed during the test",
        )

    def test_session_hooks_use_the_managed_lifecycle_owner(self) -> None:
        core = CORE.read_text(encoding="utf-8")
        power_actions = POWER_ACTIONS.read_text(encoding="utf-8")
        self.assertIn(
            '"/.local/bin/vanhyprarch-polkit-session session-start"', core
        )
        self.assertNotIn("systemctl --user start hyprpolkitagent", core)
        self.assertIn(
            '["vanhyprarch-polkit-session", "logout"]', power_actions
        )
        self.assertNotIn('execDetached(["hyprshutdown"])', power_actions)

    def test_drop_in_and_helper_are_managed_without_replacing_package_unit(self) -> None:
        with MANIFEST.open("rb") as stream:
            artifacts = tomllib.load(stream)["artifact"]
        by_target = {artifact["target"]: artifact for artifact in artifacts}
        helper_artifact = by_target["$HOME/.local/bin/vanhyprarch-polkit-session"]
        drop_in_target = (
            "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/"
            "hyprpolkitagent.service.d/10-vanhyprarch-session-lifecycle.conf"
        )
        self.assertEqual(helper_artifact["class"], "MANAGED")
        self.assertEqual(helper_artifact["mode"], "0755")
        self.assertEqual(by_target[drop_in_target]["class"], "MANAGED")
        self.assertFalse(
            (REPOSITORY / "home/.config/systemd/user/hyprpolkitagent.service").exists()
        )

    def test_package_unit_and_drop_in_verify_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unit = Path(temporary) / "hyprpolkitagent.service"
            shutil.copyfile(PACKAGE_UNIT, unit)
            drop_in_directory = Path(str(unit) + ".d")
            drop_in_directory.mkdir()
            verification_drop_in = DROP_IN.read_text(encoding="utf-8").replace(
                "%h/.local/bin/vanhyprarch-polkit-session", str(HELPER)
            )
            (drop_in_directory / DROP_IN.name).write_text(
                verification_drop_in, encoding="utf-8"
            )
            result = subprocess.run(
                ["/usr/bin/systemd-analyze", "verify", str(unit)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                shell=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
