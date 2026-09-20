#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import argparse
import importlib.util
import os
import select
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parent.parent
HELPER = (
    REPOSITORY
    / "home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_bluetooth_agent.py"
)
EVENT_TIMEOUT_SECONDS = 3.0


def wait_for_line(stream: object, description: str) -> str:
    ready, _, _ = select.select([stream], [], [], EVENT_TIMEOUT_SECONDS)
    if not ready:
        raise AssertionError(f"timed out waiting for {description}")
    line = stream.readline()
    if not line:
        raise AssertionError(f"stream closed while waiting for {description}")
    return line.rstrip("\n")


def fixture_parent() -> int:
    child = subprocess.Popen(
        [sys.executable, str(HELPER), "--parent-death-probe"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
    )
    assert child.stdout is not None
    try:
        ready = wait_for_line(child.stdout, "pairing helper readiness")
        if not ready.startswith(f"ready pid={child.pid} parent={os.getpid()}"):
            raise RuntimeError(f"unexpected helper readiness: {ready}")
        print(f"ready parent={os.getpid()} helper={child.pid}", flush=True)
        command = sys.stdin.readline().strip()
        if command != "terminate":
            raise RuntimeError(f"unexpected fixture command: {command}")
        child.send_signal(signal.SIGTERM)
        return child.wait(timeout=EVENT_TIMEOUT_SECONDS)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


class ParentHarness:
    def __init__(self, adapter_state: str = "on") -> None:
        environment = os.environ.copy()
        environment["VANHYPRARCH_TEST_ADAPTER_STATE"] = adapter_state
        self.parent = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--fixture-parent"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            close_fds=True,
            env=environment,
        )
        assert self.parent.stdout is not None
        ready = wait_for_line(self.parent.stdout, "fixture parent readiness")
        fields = dict(field.split("=", 1) for field in ready.split()[1:])
        self.parent_pid = int(fields["parent"])
        self.helper_pid = int(fields["helper"])
        if self.parent_pid != self.parent.pid:
            raise AssertionError("fixture reported the wrong parent PID")
        self.helper_pidfd = os.pidfd_open(self.helper_pid)

    def helper_exited(self, timeout: float = EVENT_TIMEOUT_SECONDS) -> bool:
        ready, _, _ = select.select([self.helper_pidfd], [], [], timeout)
        return bool(ready)

    def assert_helper_alive(self) -> None:
        if self.helper_exited(0):
            raise AssertionError("pairing helper exited unexpectedly")
        cmdline = Path(f"/proc/{self.helper_pid}/cmdline").read_bytes()
        if b"--parent-death-probe" not in cmdline:
            raise AssertionError("fixture PID is not the pairing helper probe")

    def terminate_helper(self) -> None:
        assert self.parent.stdin is not None
        self.parent.stdin.write("terminate\n")
        self.parent.stdin.flush()
        self.parent.wait(timeout=EVENT_TIMEOUT_SECONDS)
        if not self.helper_exited():
            raise AssertionError("SIGTERM did not stop the pairing helper")

    def kill_parent(self) -> None:
        self.parent.kill()
        self.parent.wait(timeout=EVENT_TIMEOUT_SECONDS)
        if not self.helper_exited():
            raise AssertionError("pairing helper survived its parent")

    def close(self) -> None:
        try:
            if self.parent.poll() is None:
                self.parent.kill()
                self.parent.wait(timeout=EVENT_TIMEOUT_SECONDS)
            if not self.helper_exited(0):
                os.kill(self.helper_pid, signal.SIGKILL)
                self.helper_exited()
        finally:
            os.close(self.helper_pidfd)


class BluetoothParentLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harnesses: list[ParentHarness] = []

    def tearDown(self) -> None:
        for harness in reversed(self.harnesses):
            harness.close()

    def launch(self, adapter_state: str = "on") -> ParentHarness:
        harness = ParentHarness(adapter_state)
        self.harnesses.append(harness)
        harness.assert_helper_alive()
        return harness

    def test_normal_start_and_component_teardown_leave_zero(self) -> None:
        harness = self.launch()
        harness.terminate_helper()

    def test_whole_parent_death_leaves_zero(self) -> None:
        harness = self.launch()
        harness.kill_parent()

    def test_parent_restart_has_only_the_new_helper(self) -> None:
        old = self.launch()
        old.kill_parent()
        new = self.launch()
        new.assert_helper_alive()
        self.assertTrue(old.helper_exited(0))
        new.terminate_helper()

    def test_repeated_parent_lifecycle_never_accumulates_helpers(self) -> None:
        prior: list[ParentHarness] = []
        for _ in range(4):
            current = self.launch()
            for old in prior:
                self.assertTrue(old.helper_exited(0))
            current.kill_parent()
            prior.append(current)

    def test_adapter_off_does_not_change_parent_ownership(self) -> None:
        harness = self.launch(adapter_state="off")
        harness.kill_parent()

    def test_parent_death_does_not_signal_an_independent_helper(self) -> None:
        first = self.launch()
        independent = self.launch()
        first.kill_parent()
        independent.assert_helper_alive()
        independent.terminate_helper()

    def test_parent_death_race_is_rejected_after_prctl(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "vanhyprarch_bluetooth_agent", HELPER
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)

        class FakePrctl:
            argtypes = None
            restype = None

            def __call__(self, *_arguments: object) -> int:
                return 0

        fake_libc = type("FakeLibc", (), {"prctl": FakePrctl()})()
        with (
            mock.patch.object(module.os, "getppid", side_effect=[4321, 1]),
            mock.patch.object(module.ctypes, "CDLL", return_value=fake_libc),
        ):
            with self.assertRaises(module.ParentProcessExited):
                module.arm_parent_death_signal()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-parent", action="store_true")
    arguments = parser.parse_args()
    if arguments.fixture_parent:
        return fixture_parent()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        BluetoothParentLifecycleTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
