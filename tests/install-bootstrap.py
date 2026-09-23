#!/usr/bin/env python3
"""Focused tests for the public one-command installation orchestrator."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY / "install.sh"
REVISION = "a" * 40
MANAGED_SPEC = importlib.util.spec_from_file_location(
    "install_bootstrap_managed_deploy", REPOSITORY / "install/managed_deploy.py"
)
assert MANAGED_SPEC is not None and MANAGED_SPEC.loader is not None
MANAGED = importlib.util.module_from_spec(MANAGED_SPEC)
sys.modules[MANAGED_SPEC.name] = MANAGED
MANAGED_SPEC.loader.exec_module(MANAGED)


def executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


class Fixture:
    def __init__(self, *, python_present: bool = True, arch: bool = True) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".vanhyprarch-install-test-root").write_text(
            "VANHYPRARCH_INSTALL_TEST_ROOT_V1\n", encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.target_uid = os.getuid() if os.getuid() != 0 else 1000
        if os.getuid() == 0:
            os.chown(self.home, self.target_uid, os.getgid())
            os.chown(self.runtime, self.target_uid, os.getgid())
        self.os_release = self.root / "os-release"
        self.os_release.write_text(
            'NAME="Arch Linux"\nID=arch\n' if arch else 'NAME="Other"\nID=other\n',
            encoding="utf-8",
        )
        self.events = self.root / "events"
        self.events.touch()
        self.archive = self.root / "source.tar.gz"
        self._make_archive()
        self.curl = self.root / "curl"
        self.sudo = self.root / "sudo"
        self.python = self.root / "python"
        self.pacman = self.root / "pacman"
        self._make_commands()
        self.python_present = python_present

    def close(self) -> None:
        self.temporary.cleanup()

    def _make_archive(self) -> None:
        source = self.root / "fixture-source" / f"vanilla-hyprarch-{REVISION}"
        install = source / "install"
        install.mkdir(parents=True)
        executable(
            install / "bootstrap",
            """
            #!/bin/sh
            [ "$#" -eq 3 ] && [ "$2" = --target-user ] &&
                [ "$3" = fixture-user ] || exit 91
            key=bootstrap-$1
            printf 'stage:%s\n' "$key" >> "$INSTALL_FIXTURE_EVENTS"
            [ "${INSTALL_FIXTURE_FAIL-}" != "$key" ]
            """,
        )
        (install / "managed_deploy.py").write_text("# fixture\n", encoding="utf-8")
        (install / "create_once.py").write_text("# fixture\n", encoding="utf-8")
        with tarfile.open(self.archive, "w:gz") as bundle:
            bundle.add(source, arcname=source.name)

    def _make_commands(self) -> None:
        executable(
            self.curl,
            """
            #!/bin/sh
            printf 'curl' >> "$INSTALL_FIXTURE_EVENTS"
            for argument in "$@"; do
                printf '<%s>' "$argument" >> "$INSTALL_FIXTURE_EVENTS"
            done
            printf '\n' >> "$INSTALL_FIXTURE_EVENTS"
            case " $* " in
                *api.github.com*)
                    [ "${INSTALL_FIXTURE_SOURCE_FAIL-}" != resolve ] || exit 22
                    printf '%s\n' "$INSTALL_FIXTURE_REVISION"
                    exit 0
                    ;;
            esac
            [ "${INSTALL_FIXTURE_SOURCE_FAIL-}" != archive ] || exit 23
            output=
            take_output=false
            for argument in "$@"; do
                if [ "$take_output" = true ]; then
                    output=$argument
                    take_output=false
                elif [ "$argument" = --output ]; then
                    take_output=true
                fi
            done
            [ -n "$output" ] || exit 24
            cp "$INSTALL_FIXTURE_ARCHIVE" "$output"
            dirname "$output" > "$INSTALL_FIXTURE_TEMP_ROOT_RECORD"
            """,
        )
        executable(
            self.sudo,
            """
            #!/bin/sh
            if [ "$1" = -v ]; then
                printf 'stage:sudo-check\n' >> "$INSTALL_FIXTURE_EVENTS"
                [ "${INSTALL_FIXTURE_FAIL-}" != sudo-check ]
                exit
            fi
            [ "$#" -eq 4 ] && [ "$3" = --target-user ] &&
                [ "$4" = fixture-user ] || exit 92
            operation=$2
            if [ "$operation" = bootstrap-python ]; then
                key=python-bootstrap
            else
                key=system-$operation
            fi
            printf 'stage:%s\n' "$key" >> "$INSTALL_FIXTURE_EVENTS"
            [ "${INSTALL_FIXTURE_FAIL-}" != "$key" ]
            """,
        )
        executable(
            self.python,
            """
            #!/bin/sh
            [ "${PYTHONDONTWRITEBYTECODE-}" = 1 ] || exit 97
            if [ "$1" = -c ]; then
                printf 'stage:python-check\n' >> "$INSTALL_FIXTURE_EVENTS"
                [ "${INSTALL_FIXTURE_FAIL-}" != python-check ]
                exit
            fi
            script=${1##*/}
            case "$script" in
                managed_deploy.py)
                    [ "$2" = --source-root ] && [ -n "$3" ] &&
                        [ "$4" = --release-id ] &&
                        [ "$5" = "$INSTALL_FIXTURE_REVISION" ] || exit 93
                    ;;
                create_once.py)
                    [ "$2" = --source-root ] && [ -n "$3" ] || exit 94
                    ;;
                *) exit 95 ;;
            esac
            arguments=" $* "
            case "$script:$arguments" in
                managed_deploy.py:*' plan reconcile '*)
                    [ "${INSTALL_FIXTURE_MANAGED_CONFLICT-}" != 1 ] || exit 96
                    if [ -f "$INSTALL_FIXTURE_MANAGED_STATE" ]; then
                        operation=update
                    else
                        operation=install
                    fi
                    printf 'managed:%s-plan\n' "$operation" >> "$INSTALL_FIXTURE_EVENTS"
                    key=managed-plan
                    ;;
                managed_deploy.py:*' reconcile '*)
                    if [ -f "$INSTALL_FIXTURE_MANAGED_STATE" ]; then
                        operation=update
                    else
                        operation=install
                    fi
                    printf 'managed:%s-apply\n' "$operation" >> "$INSTALL_FIXTURE_EVENTS"
                    key=managed-apply
                    : > "$INSTALL_FIXTURE_MANAGED_STATE"
                    ;;
                managed_deploy.py:*' validate '*) key=managed-validate ;;
                create_once.py:*' plan '*) key=create-once-plan ;;
                create_once.py:*' initialize '*) key=create-once-apply ;;
                create_once.py:*' validate '*) key=create-once-validate ;;
                *) key=unexpected-python-call ;;
            esac
            printf 'stage:%s\n' "$key" >> "$INSTALL_FIXTURE_EVENTS"
            [ "${INSTALL_FIXTURE_FAIL-}" != "$key" ]
            """,
        )
        executable(self.pacman, "#!/bin/sh\nexit 0\n")

    def run(
        self,
        *arguments: str,
        input_text: str | None = None,
        effective_uid: int = 1000,
        ref: str = "main",
        fail: str | None = None,
        source_fail: str | None = None,
        managed_conflict: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            "HOME": str(self.home),
            "PATH": "/usr/bin:/bin",
            "VANHYPRARCH_REF": ref,
            "VANHYPRARCH_INSTALL_TESTING": "1",
            "VANHYPRARCH_INSTALL_TEST_ROOT": str(self.root),
            "VANHYPRARCH_INSTALL_TEST_EFFECTIVE_UID": str(effective_uid),
            "VANHYPRARCH_INSTALL_TEST_OS_RELEASE": str(self.os_release),
            "VANHYPRARCH_INSTALL_TEST_CURL": str(self.curl),
            "VANHYPRARCH_INSTALL_TEST_SUDO": str(self.sudo),
            "VANHYPRARCH_INSTALL_TEST_PYTHON": str(self.python),
            "VANHYPRARCH_INSTALL_TEST_PACMAN": str(self.pacman),
            "VANHYPRARCH_INSTALL_TEST_HOME": str(self.home),
            "VANHYPRARCH_INSTALL_TEST_RESOLVED_HOME": str(self.home),
            "VANHYPRARCH_INSTALL_TEST_RUNTIME": str(self.runtime),
            "VANHYPRARCH_INSTALL_TEST_PYTHON_PRESENT": (
                "1" if self.python_present else "0"
            ),
            "VANHYPRARCH_INSTALL_TEST_TARGET_USER": "fixture-user",
            "VANHYPRARCH_INSTALL_TEST_TARGET_UID": str(self.target_uid),
            "INSTALL_FIXTURE_EVENTS": str(self.events),
            "INSTALL_FIXTURE_ARCHIVE": str(self.archive),
            "INSTALL_FIXTURE_REVISION": REVISION,
            "INSTALL_FIXTURE_MANAGED_STATE": str(self.root / "managed-state"),
            "INSTALL_FIXTURE_TEMP_ROOT_RECORD": str(self.root / "temp-root"),
        }
        if fail is not None:
            environment["INSTALL_FIXTURE_FAIL"] = fail
        if source_fail is not None:
            environment["INSTALL_FIXTURE_SOURCE_FAIL"] = source_fail
        if managed_conflict:
            environment["INSTALL_FIXTURE_MANAGED_CONFLICT"] = "1"
        return subprocess.run(
            [str(INSTALLER), *arguments],
            cwd=REPOSITORY,
            env=environment,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def stages(self) -> list[str]:
        return [
            line.removeprefix("stage:")
            for line in self.events.read_text(encoding="utf-8").splitlines()
            if line.startswith("stage:")
        ]

    def curl_calls(self) -> list[str]:
        return [
            line
            for line in self.events.read_text(encoding="utf-8").splitlines()
            if line.startswith("curl")
        ]

    def managed_operations(self) -> list[str]:
        return [
            line.removeprefix("managed:")
            for line in self.events.read_text(encoding="utf-8").splitlines()
            if line.startswith("managed:")
        ]

    def downloaded_temporary_root(self) -> Path:
        return Path((self.root / "temp-root").read_text(encoding="utf-8").strip())


class InstallBootstrapTests(unittest.TestCase):
    def fixture(self, **arguments: object) -> Fixture:
        fixture = Fixture(**arguments)
        self.addCleanup(fixture.close)
        return fixture

    def test_rejects_root_execution(self) -> None:
        result = self.fixture().run("--yes", effective_uid=0)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("normal target user, not root", result.stderr)

    def test_rejects_non_arch_environment(self) -> None:
        result = self.fixture(arch=False).run("--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires Arch Linux", result.stderr)

    def test_source_acquisition_failure_is_clear(self) -> None:
        result = self.fixture().run("--yes", source_fail="archive")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source archive download failed", result.stderr)
        self.assertNotIn("installation validated successfully", result.stdout)

    def test_successful_install_source_cleanup_is_user_removable(self) -> None:
        fixture = self.fixture()
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(fixture.downloaded_temporary_root().exists())

    def test_failed_install_source_cleanup_is_user_removable(self) -> None:
        fixture = self.fixture()
        result = fixture.run("--yes", fail="create-once-apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(fixture.downloaded_temporary_root().exists())

    def test_ref_resolves_to_exact_commit_archive(self) -> None:
        fixture = self.fixture()
        result = fixture.run("--yes", ref="v1.2.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = fixture.curl_calls()
        self.assertIn("/commits/v1.2.3", calls[0])
        self.assertIn(f"/tar.gz/{REVISION}", calls[1])
        self.assertIn(f"Commit: {REVISION}", result.stdout)
        self.assertIn("Archive SHA-256:", result.stdout)

    def test_python_missing_uses_only_existing_bootstrap_transition(self) -> None:
        fixture = self.fixture(python_present=False)
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        stages = fixture.stages()
        self.assertIn("bootstrap-plan", stages)
        self.assertIn("python-bootstrap", stages)
        self.assertLess(stages.index("python-bootstrap"), stages.index("system-plan"))

    def test_python_present_skips_bootstrap_transition(self) -> None:
        fixture = self.fixture(python_present=True)
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("bootstrap-plan", fixture.stages())
        self.assertNotIn("python-bootstrap", fixture.stages())

    def test_authoritative_stages_run_in_dependency_order(self) -> None:
        fixture = self.fixture()
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        relevant = [
            stage
            for stage in fixture.stages()
            if stage not in {"sudo-check", "python-check"}
        ]
        self.assertEqual(
            relevant,
            [
                "system-plan",
                "system-apply",
                "managed-plan",
                "managed-apply",
                "create-once-plan",
                "create-once-apply",
                "managed-validate",
                "create-once-validate",
                "system-validate",
            ],
        )

    def test_fresh_managed_path_selects_install(self) -> None:
        fixture = self.fixture()
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.managed_operations(), ["install-plan", "install-apply"])

    def test_existing_managed_provenance_selects_update(self) -> None:
        fixture = self.fixture()
        (fixture.root / "managed-state").touch()
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.managed_operations(), ["update-plan", "update-apply"])

    def test_interrupted_after_managed_install_reruns_through_update(self) -> None:
        fixture = self.fixture()
        interrupted = fixture.run("--yes", fail="create-once-apply")
        self.assertNotEqual(interrupted.returncode, 0)
        self.assertEqual(fixture.managed_operations(), ["install-plan", "install-apply"])

        resumed = fixture.run("--yes")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(
            fixture.managed_operations(),
            ["install-plan", "install-apply", "update-plan", "update-apply"],
        )

    def test_fully_installed_rerun_is_idempotent(self) -> None:
        fixture = self.fixture()
        first = fixture.run("--yes")
        second = fixture.run("--yes")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            fixture.managed_operations(),
            ["install-plan", "install-apply", "update-plan", "update-apply"],
        )
        self.assertEqual(fixture.stages().count("create-once-apply"), 2)
        self.assertEqual(fixture.stages().count("system-validate"), 2)

    def test_authoritative_reconcile_fails_closed_on_bad_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            target = MANAGED.TargetContext.build(
                home=home,
                config=root / "config",
                data=root / "data",
                state=root / "state",
            )
            deployment = MANAGED.ManagedDeployment(
                source_root=REPOSITORY,
                target=target,
                release_id=REVISION,
            )
            self.assertEqual(deployment.reconcile_operation(), "install")
            deployment.apply_reconciled()

            installed = MANAGED.ManagedDeployment(
                source_root=REPOSITORY,
                target=target,
                release_id=REVISION,
            )
            self.assertEqual(installed.reconcile_operation(), "update")
            self.assertFalse(installed.plan_reconciled().conflicts)
            installed.provenance_path.write_text("not json\n", encoding="utf-8")
            with self.assertRaisesRegex(MANAGED.ConflictError, "malformed"):
                installed.reconcile_operation()

    def test_managed_provenance_conflict_stops_bootstrap(self) -> None:
        fixture = self.fixture()
        result = fixture.run("--yes", managed_conflict=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("managed-apply", fixture.stages())
        self.assertNotIn("create-once-plan", fixture.stages())
        self.assertNotIn("installation validated successfully", result.stdout)

    def test_failure_in_any_stage_stops_without_success(self) -> None:
        stages = (
            "system-plan",
            "system-apply",
            "managed-plan",
            "managed-apply",
            "create-once-plan",
            "create-once-apply",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                fixture = Fixture()
                try:
                    result = fixture.run("--yes", fail=stage)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn(
                        "installation validated successfully", result.stdout
                    )
                    self.assertNotIn("system-validate", fixture.stages())
                finally:
                    fixture.close()

    def test_success_requires_every_final_validation(self) -> None:
        for stage in (
            "managed-validate",
            "create-once-validate",
            "system-validate",
        ):
            with self.subTest(stage=stage):
                fixture = Fixture()
                try:
                    result = fixture.run("--yes", fail=stage)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn(
                        "installation validated successfully", result.stdout
                    )
                finally:
                    fixture.close()

    def test_yes_is_noninteractive_and_default_prompt_can_cancel(self) -> None:
        automatic = self.fixture().run("--yes", input_text="")
        self.assertEqual(automatic.returncode, 0, automatic.stderr)
        self.assertNotIn("Proceed?", automatic.stdout)

        fixture = self.fixture()
        cancelled = fixture.run(input_text="n\n")
        self.assertEqual(cancelled.returncode, 0, cancelled.stderr)
        self.assertIn("Installation cancelled", cancelled.stdout)
        self.assertNotIn("system-plan", fixture.stages())

    def test_no_machine_specific_user_or_uid_hardcodes(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("/home/giacomo", source)
        self.assertNotIn("Virtual-1", source)
        self.assertNotRegex(source, r"target_(?:user|uid)=['\"]?(?:giacomo|1000)")

    def test_archive_digest_is_the_downloaded_payload(self) -> None:
        fixture = self.fixture()
        expected = hashlib.sha256(fixture.archive.read_bytes()).hexdigest()
        result = fixture.run("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Archive SHA-256: {expected}", result.stdout)

    def test_shell_syntax_and_sddm_validation_contract(self) -> None:
        syntax = subprocess.run(
            ["/bin/sh", "-n", str(INSTALLER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        bootstrap = (REPOSITORY / "install/bootstrap").read_text(encoding="utf-8")
        self.assertIn(
            'exec "$python_command" "$system_integration" "$operation"', bootstrap
        )
        system_source = (
            REPOSITORY / "install/system_integration.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(system_source)
        validate = next(
            child
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SystemIntegration"
            for child in node.body
            if isinstance(child, ast.FunctionDef) and child.name == "validate"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_validate_sddm_login"
                for node in ast.walk(validate)
            )
        )

    def test_all_checkout_python_runs_suppress_bytecode_without_sudo_cleanup(self) -> None:
        wrapper = INSTALLER.read_text(encoding="utf-8")
        bootstrap = (REPOSITORY / "install/bootstrap").read_text(encoding="utf-8")
        for source in (wrapper, bootstrap):
            self.assertIn("PYTHONDONTWRITEBYTECODE=1", source)
            self.assertIn("export PYTHONDONTWRITEBYTECODE", source)
        cleanup = wrapper[wrapper.index("cleanup() {") : wrapper.index("trap cleanup EXIT")]
        self.assertIn('/usr/bin/rm -rf -- "$temporary_root"', cleanup)
        self.assertNotIn("sudo_command", cleanup)
        self.assertNotIn("sudo rm", wrapper)

    def test_wrapper_does_not_duplicate_authoritative_inventories(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("pacman -S", source)
        self.assertNotIn("NetworkManager.service", source)
        self.assertNotIn("bluetooth.service", source)
        self.assertNotIn("/etc/bluetooth/main.conf", source)
        self.assertNotIn("flathub.flatpakrepo", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
