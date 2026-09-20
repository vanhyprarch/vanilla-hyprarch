#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
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
PACKAGE_UNIT_SHA256 = "4460a3fb800e4f0bde159ea9317184373696c6e5a95c2222fa9dbfaa4d84244d"
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
    sys.modules[loader.name] = module
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
        if operation[0] == "is-failed":
            return 0 if self.state == "failed" else 1
        if operation[0] == "reset-failed":
            self.state = "inactive"
        elif operation[0] == "restart":
            self.state = "active"
            self.agent_count = 1
        elif operation[0] == "is-active":
            return 0 if self.state == "active" else 3
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
        self.socket_paths = (
            self.runtime / self.wayland_display,
            self.instance / ".socket.sock",
        )
        self.sockets: dict[Path, socket.socket] = {}
        for path in self.socket_paths:
            self.bind_socket(path)
        self.environment = {
            "XDG_RUNTIME_DIR": str(self.runtime),
            "HYPRLAND_INSTANCE_SIGNATURE": self.signature,
            "WAYLAND_DISPLAY": self.wayland_display,
            "DISPLAY": ":1",
        }
        self.logs: list[tuple[str, str]] = []

    def tearDown(self) -> None:
        for listener in self.sockets.values():
            listener.close()
        self.temporary.cleanup()

    def bind_socket(self, path: Path) -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        self.sockets[path] = listener

    def remove_socket(self, path: Path) -> None:
        listener = self.sockets.pop(path)
        listener.close()
        path.unlink()

    def call_with_session(self, function: object, *arguments: object) -> object:
        with mock.patch.dict(os.environ, self.environment, clear=True):
            return function(*arguments)

    def start(
        self,
        systemd: FakeSystemd,
        waiter: object = helper.wait_for_session_sockets,
    ) -> int:
        return self.call_with_session(
            helper.session_start,
            systemd,
            lambda level, message: self.logs.append((level, message)),
            waiter,
        )

    def test_active_wayland_session_satisfies_service_condition(self) -> None:
        self.assertEqual(self.call_with_session(helper.condition), 0)

    def test_absent_compositor_skips_start_without_a_restart_storm(self) -> None:
        self.remove_socket(self.instance / ".socket.sock")
        self.assertEqual(self.call_with_session(helper.condition), 1)
        drop_in = DROP_IN.read_text(encoding="utf-8")
        self.assertIn(
            "ExecCondition=%h/.local/bin/vanhyprarch-polkit-session condition",
            drop_in,
        )
        self.assertIn("RestartSec=1s", drop_in)

    def test_unloaded_inactive_unit_skips_reset_and_starts(self) -> None:
        systemd = FakeSystemd("unloaded")
        self.assertEqual(self.start(systemd), 0)
        self.assertEqual(
            systemd.operations,
            [
                (
                    "import-environment",
                    "HYPRLAND_INSTANCE_SIGNATURE",
                    "WAYLAND_DISPLAY",
                    "DISPLAY",
                ),
                ("is-failed", "--quiet", "hyprpolkitagent.service"),
                ("restart", "hyprpolkitagent.service"),
                ("is-active", "--quiet", "hyprpolkitagent.service"),
            ],
        )
        self.assertEqual(systemd.agent_count, 1)
        self.assertTrue(
            any("reset-failed not required" in message for _level, message in self.logs)
        )

    def test_prior_start_limit_failure_is_cleared_before_one_agent_starts(self) -> None:
        systemd = FakeSystemd("failed")
        self.assertEqual(self.start(systemd), 0)
        self.assertEqual(
            systemd.operations,
            [
                (
                    "import-environment",
                    "HYPRLAND_INSTANCE_SIGNATURE",
                    "WAYLAND_DISPLAY",
                    "DISPLAY",
                ),
                ("is-failed", "--quiet", "hyprpolkitagent.service"),
                ("reset-failed", "hyprpolkitagent.service"),
                ("restart", "hyprpolkitagent.service"),
                ("is-active", "--quiet", "hyprpolkitagent.service"),
            ],
        )
        self.assertEqual(systemd.state, "active")
        self.assertEqual(systemd.agent_count, 1)

    def test_cold_start_waits_for_both_sockets_without_polling(self) -> None:
        for path in self.socket_paths:
            self.remove_socket(path)
        systemd = FakeSystemd("inactive")
        monitor_ready = threading.Event()

        def create_sockets() -> None:
            monitor_ready.wait()
            self.assertEqual(systemd.operations, [])
            for path in self.socket_paths:
                self.bind_socket(path)

        worker = threading.Thread(target=create_sockets)
        worker.start()
        original_ready = helper.session_sockets_ready
        readiness_calls = 0

        def controlled_ready(identity: object) -> bool:
            nonlocal readiness_calls
            readiness_calls += 1
            result = original_ready(identity)
            if readiness_calls == 2:
                monitor_ready.set()
            return result

        waiter = lambda identity: helper.wait_for_session_sockets(identity, 1_000)
        with mock.patch.object(
            helper, "session_sockets_ready", side_effect=controlled_ready
        ):
            self.assertEqual(self.start(systemd, waiter), 0)
        worker.join()
        self.assertEqual(
            systemd.operations.count(("restart", "hyprpolkitagent.service")), 1
        )
        self.assertEqual(
            systemd.operations.count(
                (
                    "import-environment",
                    "HYPRLAND_INSTANCE_SIGNATURE",
                    "WAYLAND_DISPLAY",
                    "DISPLAY",
                )
            ),
            1,
        )
        self.assertTrue(
            any("readiness became-ready" in message for _level, message in self.logs)
        )
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn("inotify_add_watch", source)
        self.assertIn("selectors.DefaultSelector", source)
        self.assertNotIn("time.sleep", source)

    def test_socket_never_appears_is_a_bounded_failure(self) -> None:
        self.remove_socket(self.instance / ".socket.sock")
        systemd = FakeSystemd("inactive")
        waiter = lambda identity: helper.wait_for_session_sockets(identity, 5)
        self.assertEqual(self.start(systemd, waiter), 1)
        self.assertEqual(systemd.operations, [])
        self.assertTrue(
            any("not ready within 5 ms" in message for _level, message in self.logs)
        )

    def test_compositor_identity_disappearing_while_waiting_aborts(self) -> None:
        self.remove_socket(self.instance / ".socket.sock")
        systemd = FakeSystemd("inactive")
        monitor_ready = threading.Event()

        def remove_identity() -> None:
            monitor_ready.wait()
            self.instance.rmdir()

        worker = threading.Thread(target=remove_identity)
        worker.start()
        original_ready = helper.session_sockets_ready
        readiness_calls = 0

        def controlled_ready(identity: object) -> bool:
            nonlocal readiness_calls
            readiness_calls += 1
            result = original_ready(identity)
            if readiness_calls == 2:
                monitor_ready.set()
            return result

        waiter = lambda identity: helper.wait_for_session_sockets(identity, 1_000)
        with mock.patch.object(
            helper, "session_sockets_ready", side_effect=controlled_ready
        ):
            self.assertEqual(self.start(systemd, waiter), 1)
        worker.join()
        self.assertEqual(systemd.operations, [])
        self.assertTrue(
            any("instance disappeared" in message for _level, message in self.logs)
        )

    def test_stale_signature_never_starts_service(self) -> None:
        systemd = FakeSystemd("inactive")
        stale = dict(self.environment)
        stale["HYPRLAND_INSTANCE_SIGNATURE"] = "stale_signature"
        with mock.patch.dict(os.environ, stale, clear=True):
            result = helper.session_start(
                systemd,
                lambda level, message: self.logs.append((level, message)),
            )
        self.assertEqual(result, 1)
        self.assertEqual(systemd.operations, [])

    def test_wrong_wayland_socket_never_starts_service(self) -> None:
        wayland = self.runtime / self.wayland_display
        self.remove_socket(wayland)
        wayland.write_text("not a socket\n", encoding="utf-8")
        systemd = FakeSystemd("inactive")
        self.assertEqual(self.start(systemd), 1)
        self.assertEqual(systemd.operations, [])

    def test_already_ready_fast_path_has_no_monitor_delay(self) -> None:
        identity = self.call_with_session(helper.read_session_identity)
        with mock.patch.object(helper.ctypes, "CDLL") as library_factory:
            self.assertEqual(helper.wait_for_session_sockets(identity), "already-ready")
        library_factory.assert_not_called()

    def test_repeated_session_start_never_duplicates_the_agent(self) -> None:
        systemd = FakeSystemd("inactive")
        self.assertEqual(self.start(systemd), 0)
        self.assertEqual(self.start(systemd), 0)
        self.assertEqual(systemd.agent_count, 1)
        self.assertEqual(
            systemd.operations.count(("restart", "hyprpolkitagent.service")), 2
        )

    def test_failed_environment_import_cannot_start_the_agent(self) -> None:
        systemd = FakeSystemd("failed")
        systemd.fail_operation = "import-environment"
        self.assertEqual(self.start(systemd), 1)
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

    def test_reset_failed_error_prevents_restart(self) -> None:
        systemd = FakeSystemd("failed")
        systemd.fail_operation = "reset-failed"
        self.assertEqual(self.start(systemd), 1)
        self.assertNotIn(("restart", "hyprpolkitagent.service"), systemd.operations)
        self.assertTrue(
            any("failed at reset-failed" in message for _level, message in self.logs)
        )

    def test_restart_error_is_reported(self) -> None:
        systemd = FakeSystemd("inactive")
        systemd.fail_operation = "restart"
        self.assertEqual(self.start(systemd), 1)
        self.assertEqual(
            systemd.operations.count(("restart", "hyprpolkitagent.service")), 1
        )
        self.assertTrue(
            any("failed at service-restart" in message for _level, message in self.logs)
        )

    def test_unknown_service_state_prevents_restart(self) -> None:
        systemd = FakeSystemd("inactive")

        def runner(arguments: object) -> int:
            operation = tuple(arguments)
            if operation[0] == "is-failed":
                systemd.operations.append(operation)
                return 4
            return systemd(arguments)

        result = self.call_with_session(
            helper.session_start,
            runner,
            lambda level, message: self.logs.append((level, message)),
            helper.wait_for_session_sockets,
        )
        self.assertEqual(result, 1)
        self.assertNotIn(("restart", "hyprpolkitagent.service"), systemd.operations)
        self.assertTrue(
            any(
                "failed at failure-state inspection" in message
                for _level, message in self.logs
            )
        )

    def test_failed_final_service_verification_is_reported(self) -> None:
        systemd = FakeSystemd("inactive")
        systemd.fail_operation = "is-active"
        self.assertEqual(self.start(systemd), 1)
        self.assertEqual(
            systemd.operations.count(("restart", "hyprpolkitagent.service")), 1
        )
        self.assertTrue(
            any(
                "failed at service-verification" in message
                for _level, message in self.logs
            )
        )

    def test_stale_identity_after_import_prevents_reset_and_restart(self) -> None:
        systemd = FakeSystemd("inactive")

        def runner(arguments: object) -> int:
            result = systemd(arguments)
            if tuple(arguments)[0] == "import-environment":
                self.instance.rename(self.instance.with_name("replaced-instance"))
            return result

        result = self.call_with_session(
            helper.session_start,
            runner,
            lambda level, message: self.logs.append((level, message)),
            helper.wait_for_session_sockets,
        )
        self.assertEqual(result, 1)
        self.assertEqual(len(systemd.operations), 1)

    def test_session_start_logs_every_success_stage(self) -> None:
        systemd = FakeSystemd("failed")
        self.assertEqual(self.start(systemd), 0)
        messages = "\n".join(message for _level, message in self.logs)
        for expected in (
            "session-start invoked",
            "session-start identity",
            "session-start readiness already-ready",
            "session-start environment-import succeeded",
            "session-start reset-failed succeeded",
            "session-start service-restart succeeded",
            "session-start service-verification succeeded",
            "session-start completed",
        ):
            self.assertIn(expected, messages)

    def test_journal_logging_uses_exact_argv_without_a_shell(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(helper.subprocess, "run", return_value=completed) as run:
            helper.journal_log("info", "session-start invoked")
        run.assert_called_once_with(
            [
                "/usr/bin/logger",
                "--tag",
                "vanhyprarch-polkit-session",
                "--priority",
                "user.info",
                "--stderr",
                "--",
                "session-start invoked",
            ],
            stdin=subprocess.DEVNULL,
            check=False,
            shell=False,
        )

    def test_graceful_logout_stops_agent_before_hyprshutdown(self) -> None:
        systemd = FakeSystemd("active")
        events: list[tuple[str, ...]] = []

        def execer(path: str, arguments: object) -> None:
            events.append(("exec", path, *arguments))

        runner = lambda arguments: (
            events.append(("systemctl", *arguments)),
            systemd(arguments),
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
            PACKAGE_UNIT.read_text(encoding="utf-8"),
            package,
            "the package unit changed during the test",
        )
        self.assertEqual(
            hashlib.sha256(PACKAGE_UNIT.read_bytes()).hexdigest(),
            PACKAGE_UNIT_SHA256,
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
