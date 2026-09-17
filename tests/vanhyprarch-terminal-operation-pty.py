#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""PTY regressions for the terminal-operation helper."""

from __future__ import annotations

import errno
import os
import pty
import select
import signal
import sys
import time
from collections.abc import Sequence


TIMEOUT_SECONDS = 5.0


class PtySession:
    def __init__(self, argv: Sequence[str]) -> None:
        pid, master_fd = pty.fork()
        if pid == 0:
            try:
                os.execv(argv[0], list(argv))
            except OSError as error:
                print(f"exec failed: {error}", file=sys.stderr, flush=True)
                os._exit(127)

        self.pid = pid
        self.master_fd = master_fd
        self.output = bytearray()
        self.reaped = False
        self.wait_status = 0

    def _read_once(self) -> bool:
        try:
            chunk = os.read(self.master_fd, 4096)
        except OSError as error:
            if error.errno == errno.EIO:
                return False
            raise
        if not chunk:
            return False
        self.output.extend(chunk)
        return True

    def wait_for(self, expected: bytes) -> None:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while expected not in self.output:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail(f"timed out waiting for {expected!r}")
            readable, _, _ = select.select(
                [self.master_fd], [], [], remaining
            )
            if not readable or not self._read_once():
                self.fail(f"terminal closed before {expected!r}")

    def send(self, data: bytes) -> None:
        offset = 0
        while offset < len(data):
            offset += os.write(self.master_fd, data[offset:])

    def remains_running(self, duration: float) -> bool:
        deadline = time.monotonic() + duration
        while True:
            finished_pid, status = os.waitpid(self.pid, os.WNOHANG)
            if finished_pid == self.pid:
                self.reaped = True
                self.wait_status = status
                return False

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            readable, _, _ = select.select(
                [self.master_fd], [], [], min(remaining, 0.05)
            )
            if readable:
                self._read_once()

    def wait_for_exit(self) -> int:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while True:
            finished_pid, status = os.waitpid(self.pid, os.WNOHANG)
            if finished_pid == self.pid:
                self.reaped = True
                self.wait_status = status
                return os.waitstatus_to_exitcode(status)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail("timed out waiting for wrapper exit")
            readable, _, _ = select.select(
                [self.master_fd], [], [], min(remaining, 0.05)
            )
            if readable:
                self._read_once()

    def fail(self, message: str) -> None:
        output = self.output.decode(errors="replace")
        raise AssertionError(f"{message}\nPTY output:\n{output}")

    def close(self) -> None:
        if not self.reaped:
            finished_pid, status = os.waitpid(self.pid, os.WNOHANG)
            if finished_pid == self.pid:
                self.reaped = True
                self.wait_status = status
            else:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(self.pid, 0)
                self.reaped = True
        os.close(self.master_fd)


def check_stale_enter(helper: str) -> None:
    child_code = """
import os
print("Child prompt [Y/n]", flush=True)
os.read(0, 1)
print("Child exiting with status 1", flush=True)
raise SystemExit(1)
"""
    session = PtySession([helper, sys.executable, "-c", child_code])
    try:
        session.wait_for(b"Child prompt [Y/n]")
        session.send(b"n\n")
        session.wait_for(b"Press Enter to close.")
        if not session.remains_running(0.25):
            session.fail("stale child Enter closed the wrapper")
        session.send(b"\n")
        if session.wait_for_exit() != 1:
            session.fail("fresh Enter did not preserve child status 1")
    finally:
        session.close()


def check_child_ctrl_c(helper: str) -> None:
    child_code = """
import time
print("Child running", flush=True)
time.sleep(30)
"""
    session = PtySession([helper, sys.executable, "-c", child_code])
    try:
        session.wait_for(b"Child running")
        session.send(b"\x03")
        session.wait_for(b"Operation cancelled.")
        session.wait_for(b"Press Enter to close.")
        if not session.remains_running(0.1):
            session.fail("child cancellation bypassed the final prompt")
        session.send(b"\n")
        if session.wait_for_exit() != 130:
            session.fail("child Ctrl+C status was not preserved")
    finally:
        session.close()


def check_final_ctrl_c(helper: str) -> None:
    session = PtySession([helper, "/usr/bin/true"])
    try:
        session.wait_for(b"Press Enter to close.")
        if not session.remains_running(0.1):
            session.fail("wrapper exited before final Ctrl+C")
        session.send(b"\x03")
        if session.wait_for_exit() != 0:
            session.fail("final Ctrl+C changed the successful child status")
    finally:
        session.close()


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <terminal-operation-helper>", file=sys.stderr)
        return 64

    helper = os.path.abspath(argv[1])
    check_stale_enter(helper)
    check_child_ctrl_c(helper)
    check_final_ctrl_c(helper)
    print("vanhyprarch terminal-operation PTY self-check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
