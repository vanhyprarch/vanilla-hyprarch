#!/usr/bin/env python3
"""Deterministic tests for the pre-Python Arch bootstrap boundary."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPOSITORY / "install/bootstrap"


def executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


class Fixture:
    def __init__(self, *, python_installed: bool = False) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin = self.root / "usr/bin"
        self.bin.mkdir(parents=True)
        (self.root / "usr/lib").mkdir(parents=True)
        (self.root / ".vanhyprarch-bootstrap-test-root").write_text(
            "VANHYPRARCH_BOOTSTRAP_TEST_ROOT_V1\n", encoding="utf-8"
        )
        (self.root / "usr/lib/os-release").write_text(
            'NAME="Arch Linux"\nID=arch\n', encoding="utf-8"
        )
        self.log = self.root / "commands.log"
        self.log.touch()
        (self.root / "architecture").write_text("x86_64\n", encoding="utf-8")
        (self.root / "pending").write_text("", encoding="utf-8")
        (self.root / "resolvable").write_text("yes\n", encoding="utf-8")
        self._write_commands()
        if python_installed:
            (self.root / "installed-python").touch()
            shutil.copy2(self.root / "python-template", self.bin / "python")
            (self.bin / "python").chmod(0o755)

    def _write_commands(self) -> None:
        executable(
            self.bin / "uname",
            """
            #!/bin/sh
            printf 'uname' >> "$BOOTSTRAP_FIXTURE_LOG"
            for argument in "$@"; do printf '<%s>' "$argument" >> "$BOOTSTRAP_FIXTURE_LOG"; done
            printf '\n' >> "$BOOTSTRAP_FIXTURE_LOG"
            cat "$BOOTSTRAP_FIXTURE_ROOT/architecture"
            """,
        )
        executable(
            self.bin / "id",
            """
            #!/bin/sh
            printf 'id' >> "$BOOTSTRAP_FIXTURE_LOG"
            for argument in "$@"; do printf '<%s>' "$argument" >> "$BOOTSTRAP_FIXTURE_LOG"; done
            printf '\n' >> "$BOOTSTRAP_FIXTURE_LOG"
            if [ "$#" -eq 3 ] && [ "$1" = -u ] && [ "$2" = -- ] && [ "$3" = tester ]; then
                printf '1000\n'
                exit 0
            fi
            if [ "$#" -eq 3 ] && [ "$1" = -u ] && [ "$2" = -- ] && [ "$3" = root ]; then
                printf '0\n'
                exit 0
            fi
            exit 1
            """,
        )
        executable(
            self.bin / "pacman",
            """
            #!/bin/sh
            printf 'pacman' >> "$BOOTSTRAP_FIXTURE_LOG"
            for argument in "$@"; do printf '<%s>' "$argument" >> "$BOOTSTRAP_FIXTURE_LOG"; done
            printf '\n' >> "$BOOTSTRAP_FIXTURE_LOG"
            case "$1" in
                -Qu)
                    cat "$BOOTSTRAP_FIXTURE_ROOT/pending"
                    exit 0
                    ;;
                -Q)
                    if [ "$#" -eq 3 ] && [ "$2" = -- ] && [ "$3" = python ] &&
                       [ -f "$BOOTSTRAP_FIXTURE_ROOT/installed-python" ]; then
                        printf 'python 3.fixture-1\n'
                        exit 0
                    fi
                    exit 1
                    ;;
                -Sp)
                    [ "$*" = "-Sp --print-format %n --needed -- python" ] || exit 97
                    [ "$(cat "$BOOTSTRAP_FIXTURE_ROOT/resolvable")" = yes ] || exit 1
                    printf 'python\n'
                    exit 0
                    ;;
                -S)
                    [ "$*" = "-S --needed --noconfirm -- python" ] || exit 96
                    [ ! -f "$BOOTSTRAP_FIXTURE_ROOT/pacman-failure" ] || exit 42
                    : > "$BOOTSTRAP_FIXTURE_ROOT/installed-python"
                    cp "$BOOTSTRAP_FIXTURE_ROOT/python-template" "$BOOTSTRAP_FIXTURE_ROOT/usr/bin/python"
                    chmod 755 "$BOOTSTRAP_FIXTURE_ROOT/usr/bin/python"
                    exit 0
                    ;;
            esac
            exit 95
            """,
        )
        executable(
            self.root / "python-template",
            """
            #!/bin/sh
            printf 'python' >> "$BOOTSTRAP_FIXTURE_LOG"
            for argument in "$@"; do printf '<%s>' "$argument" >> "$BOOTSTRAP_FIXTURE_LOG"; done
            printf '\n' >> "$BOOTSTRAP_FIXTURE_LOG"
            if [ "$1" = -c ]; then
                [ ! -f "$BOOTSTRAP_FIXTURE_ROOT/interpreter-failure" ] || exit 43
                exit 0
            fi
            exit 0
            """,
        )

    def close(self) -> None:
        self.temporary.cleanup()

    def run(
        self,
        operation: str,
        *,
        target_user: str = "tester",
        effective_uid: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "VANHYPRARCH_BOOTSTRAP_TESTING": "1",
            "VANHYPRARCH_BOOTSTRAP_TEST_ROOT": str(self.root),
            "VANHYPRARCH_BOOTSTRAP_TEST_EFFECTIVE_UID": str(effective_uid),
            "BOOTSTRAP_FIXTURE_ROOT": str(self.root),
            "BOOTSTRAP_FIXTURE_LOG": str(self.log),
        }
        return subprocess.run(
            [str(BOOTSTRAP), operation, "--target-user", target_user],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def commands(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()


class PythonBootstrapTests(unittest.TestCase):
    def fixture(self, **kwargs) -> Fixture:
        value = Fixture(**kwargs)
        self.addCleanup(value.close)
        return value

    def test_absent_python_apply_installs_only_python_and_delegates(self) -> None:
        fixture = self.fixture()
        result = fixture.run("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = fixture.commands()
        installs = [line for line in commands if line.startswith("pacman<-S>")]
        self.assertEqual(installs, ["pacman<-S><--needed><--noconfirm><--><python>"])
        self.assertTrue((fixture.root / "installed-python").exists())
        self.assertTrue(any("system_integration.py><apply>" in line for line in commands))
        self.assertFalse(any("systemctl" in line or "flatpak" in line or "yay" in line for line in commands))

    def test_present_python_is_preserved_without_package_transaction(self) -> None:
        fixture = self.fixture(python_installed=True)
        result = fixture.run("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_repeated_apply_is_idempotent(self) -> None:
        fixture = self.fixture()
        first = fixture.run("apply")
        second = fixture.run("apply")
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        installs = [line for line in fixture.commands() if line.startswith("pacman<-S>")]
        self.assertEqual(len(installs), 1)

    def test_plan_is_read_only_when_python_is_absent(self) -> None:
        fixture = self.fixture()
        result = fixture.run("plan", effective_uid=1000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("package-install python", result.stdout)
        self.assertFalse((fixture.root / "installed-python").exists())
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_validate_does_not_install_absent_python(self) -> None:
        fixture = self.fixture()
        result = fixture.run("validate", effective_uid=1000)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python is not installed", result.stderr)
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_pending_upgrades_block_without_mutation(self) -> None:
        fixture = self.fixture()
        (fixture.root / "pending").write_text("linux 1 -> 2\n", encoding="utf-8")
        result = fixture.run("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pacman -Syu", result.stderr)
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_unresolvable_python_blocks_without_mutation(self) -> None:
        fixture = self.fixture()
        (fixture.root / "resolvable").write_text("no\n", encoding="utf-8")
        result = fixture.run("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot be resolved", result.stderr)
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_pacman_failure_propagates_without_delegation(self) -> None:
        fixture = self.fixture()
        (fixture.root / "pacman-failure").touch()
        result = fixture.run("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not install python", result.stderr)
        self.assertFalse(any("system_integration.py" in line for line in fixture.commands()))

    def test_interpreter_verification_failure_blocks_delegation(self) -> None:
        fixture = self.fixture()
        (fixture.root / "interpreter-failure").touch()
        result = fixture.run("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not start", result.stderr)
        delegated = [line for line in fixture.commands() if "system_integration.py" in line]
        self.assertEqual(delegated, [])

    def test_wrong_os_and_architecture_block(self) -> None:
        fixture = self.fixture()
        (fixture.root / "usr/lib/os-release").write_text("ID=other\n", encoding="utf-8")
        wrong_os = fixture.run("apply")
        self.assertNotEqual(wrong_os.returncode, 0)
        self.assertIn("requires Arch Linux", wrong_os.stderr)

        (fixture.root / "usr/lib/os-release").write_text("ID=arch\n", encoding="utf-8")
        (fixture.root / "architecture").write_text("aarch64\n", encoding="utf-8")
        wrong_arch = fixture.run("apply")
        self.assertNotEqual(wrong_arch.returncode, 0)
        self.assertIn("unsupported architecture", wrong_arch.stderr)
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_root_or_untrusted_target_argument_is_rejected_without_shell_execution(self) -> None:
        fixture = self.fixture()
        root = fixture.run("apply", target_user="root")
        self.assertNotEqual(root.returncode, 0)
        self.assertIn("non-root target user", root.stderr)

        marker = fixture.root / "argument-was-executed"
        hostile = f"tester;touch {marker}"
        rejected = fixture.run("apply", target_user=hostile)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_apply_requires_root_before_install(self) -> None:
        fixture = self.fixture()
        result = fixture.run("apply", effective_uid=1000)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apply must run as root", result.stderr)
        self.assertFalse(any(line.startswith("pacman<-S>") for line in fixture.commands()))

    def test_no_database_refresh_or_full_upgrade_command_exists(self) -> None:
        fixture = self.fixture()
        result = fixture.run("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = fixture.commands()
        self.assertFalse(any("<-Sy>" in line or "<-Syu>" in line for line in commands))


if __name__ == "__main__":
    unittest.main()
