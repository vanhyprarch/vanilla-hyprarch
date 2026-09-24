#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parent.parent
MODULE_PATH = REPOSITORY / "install/managed_deploy.py"
SPEC = importlib.util.spec_from_file_location("vanhyprarch_managed_deploy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
DEPLOY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DEPLOY
SPEC.loader.exec_module(DEPLOY)


def artifact_table(
    identifier: str,
    source: str,
    target: str,
    *,
    kind: str = "file",
    mode: str = "0644",
    validators: tuple[str, ...] = (),
) -> str:
    lines = [
        "[[artifact]]",
        f'id = "{identifier}"',
        f'source = "{source}"',
        f'target = "{target}"',
        'class = "VANILLA_MANAGED"',
        'component = "fixture"',
        f'kind = "{kind}"',
    ]
    if kind == "file":
        lines.append(f'mode = "{mode}"')
    else:
        lines.extend(
            (
                'mode_policy = "explicit"',
                'directory_mode = "0755"',
                'file_mode = "0644"',
            )
        )
    if validators:
        lines.append("validators = [" + ", ".join(f'"{item}"' for item in validators) + "]")
    lines.extend(
        (
            'authority = "vanilla-hyprarch"',
            'status = "implemented"',
            "user_editable = false",
            "machine_specific = false",
            "",
        )
    )
    return "\n".join(lines)


def manifest_text(artifacts: list[str]) -> str:
    return "\n".join(
        (
            "schema_version = 2",
            'installed_mode = "regular-files"',
            'development_mode = "repository-symlinks-allowed"',
            "runtime_source_independent = true",
            'managed_deployment_provenance = "managed-deployment-provenance"',
            "",
            *artifacts,
            "[[artifact]]",
            'id = "create-once-fixture"',
            'target = "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/create-once.txt"',
            'class = "CREATE_ONCE_USER"',
            'component = "fixture"',
            'kind = "file"',
            'mode = "0644"',
            'authority = "user"',
            'status = "implemented"',
            "user_editable = true",
            "machine_specific = false",
            "",
            "[[artifact]]",
            'id = "managed-deployment-provenance"',
            'target = "${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/managed-deployment-v1.json"',
            'class = "BACKEND_OWNED"',
            'component = "distribution"',
            'kind = "file"',
            'mode = "0600"',
            'authority = "vanhyprarch-managed-deploy"',
            'status = "implemented"',
            "user_editable = false",
            "machine_specific = false",
            "",
        )
    )


class Fixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="vanhyprarch-managed-deploy-test-")
        self.root = Path(self.temporary.name)
        self.target_home = self.root / "target/home"
        self.target_home.mkdir(parents=True)
        self.target = DEPLOY.TargetContext.build(
            home=self.target_home,
            config=self.root / "target/config",
            data=self.root / "target/data",
            state=self.root / "target/state",
        )
        self.release_a = self.root / "release-a"
        self.release_b = self.root / "release-b"
        self._write_release(self.release_a, "A")
        self._write_release(self.release_b, "B")

    def cleanup(self) -> None:
        self.temporary.cleanup()

    def _write(self, root: Path, relative: str, content: str, mode: int = 0o600) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)

    def _write_release(self, root: Path, version: str) -> None:
        artifacts = [
            artifact_table(
                "changed",
                "payload/changed.txt",
                "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/changed.txt",
            ),
            artifact_table(
                "mode-change",
                "payload/mode-change",
                "$HOME/.local/bin/mode-change",
                mode="0644" if version == "A" else "0755",
            ),
            artifact_table(
                "python-helper",
                "payload/helper.py",
                "$HOME/.local/bin/fixture-helper",
                mode="0755",
                validators=("python-compile",),
            ),
            artifact_table(
                "tree",
                "payload/tree",
                "${XDG_DATA_HOME:-$HOME/.local/share}/fixture/tree",
                kind="tree",
            ),
            artifact_table(
                "unchanged",
                "payload/unchanged.txt",
                "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/unchanged.txt",
            ),
        ]
        if version == "A":
            artifacts.append(
                artifact_table(
                    "removed",
                    "payload/removed.txt",
                    "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/removed.txt",
                )
            )
        else:
            artifacts.append(
                artifact_table(
                    "added",
                    "payload/added.txt",
                    "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/added.txt",
                )
            )
        self._write(root, "deployment/ownership-v2.toml", manifest_text(artifacts), 0o644)
        self._write(root, "payload/unchanged.txt", "same\n", 0o777)
        self._write(root, "payload/changed.txt", "old\n" if version == "A" else "new\n")
        self._write(root, "payload/mode-change", "#!/bin/sh\nexit 0\n", 0o600)
        self._write(root, "payload/helper.py", "#!/usr/bin/python\nVALUE = 1\n", 0o600)
        self._write(root, "payload/tree/keep.txt", "same tree\n", 0o777)
        self._write(root, "payload/tree/change.txt", "old tree\n" if version == "A" else "new tree\n")
        if version == "A":
            self._write(root, "payload/tree/removed.txt", "remove from tree\n")
            self._write(root, "payload/removed.txt", "stale\n")
        else:
            self._write(root, "payload/tree/added.txt", "add to tree\n")
            self._write(root, "payload/added.txt", "added\n")

    def engine(
        self,
        release: Path,
        release_id: str,
        fault_hook: DEPLOY.FaultHook | None = None,
    ) -> DEPLOY.ManagedDeployment:
        return DEPLOY.ManagedDeployment(
            source_root=release,
            target=self.target,
            release_id=release_id,
            fault_hook=fault_hook,
        )

    def write_minimal_release(
        self,
        name: str,
        artifacts: list[str],
        files: dict[str, str],
    ) -> Path:
        root = self.root / name
        self._write(
            root,
            "deployment/ownership-v2.toml",
            manifest_text(artifacts),
            0o644,
        )
        for relative, content in files.items():
            self._write(root, relative, content)
        return root

    def cli(
        self,
        release: Path,
        release_id: str,
        command: str,
        *,
        operation: str | None = None,
        fault: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            sys.executable,
            os.fspath(MODULE_PATH),
            "--source-root",
            os.fspath(release),
            "--release-id",
            release_id,
            "--home",
            os.fspath(self.target.home),
            "--xdg-config-home",
            os.fspath(self.target.config),
            "--xdg-data-home",
            os.fspath(self.target.data),
            "--xdg-state-home",
            os.fspath(self.target.state),
            command,
        ]
        if operation is not None:
            arguments.append(operation)
        environment = os.environ.copy()
        if fault is not None:
            environment[DEPLOY.TEST_MODE_ENV] = "1"
            environment[DEPLOY.TEST_FAULT_ENV] = fault
        else:
            environment.pop(DEPLOY.TEST_MODE_ENV, None)
            environment.pop(DEPLOY.TEST_FAULT_ENV, None)
        return subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def target_snapshot(self) -> tuple[tuple[str, str, int, bytes], ...]:
        target_root = self.root / "target"
        result: list[tuple[str, str, int, bytes]] = []
        for path in sorted(target_root.rglob("*")):
            metadata = os.lstat(path)
            relative = os.fspath(path.relative_to(target_root))
            if stat.S_ISDIR(metadata.st_mode):
                result.append((relative, "directory", stat.S_IMODE(metadata.st_mode), b""))
            elif stat.S_ISREG(metadata.st_mode):
                result.append((relative, "file", stat.S_IMODE(metadata.st_mode), path.read_bytes()))
            elif stat.S_ISLNK(metadata.st_mode):
                result.append((relative, "symlink", stat.S_IMODE(metadata.st_mode), os.fsencode(os.readlink(path))))
        return tuple(result)

    @property
    def provenance(self) -> Path:
        return self.target.state / "vanhyprarch/managed-deployment-v1.json"


class FixtureTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.cleanup()


class ManifestConsumptionTests(FixtureTestCase):
    def test_repository_manifest_selects_exact_managed_inventory(self) -> None:
        engine = DEPLOY.ManagedDeployment(
            source_root=REPOSITORY,
            target=self.fixture.target,
            release_id="repository",
        )
        self.assertEqual(
            [item.identifier for item in engine.artifacts],
            [
                "appearance-command",
                "dictation-command",
                "dictation-resources",
                "hypridle-config",
                "hyprland-loader",
                "hyprland-managed-core",
                "hyprlock-config",
                "hyprpaper-config",
                "idle-command",
                "keyboard-command",
                "keyboard-unit",
                "monitor-command",
                "monitor-transaction-unit",
                "polkit-command",
                "polkit-drop-in",
                "quickshell-config",
                "screensaver-command",
                "screenshot-command",
                "wallpaper-assets",
                "zig-screensaver-manager",
                "zig-screensaver-metadata",
            ],
        )
        with self.assertRaises(DEPLOY.SafetyError):
            engine.require_phase2_artifact("machine-hyprland")
        with self.assertRaises(DEPLOY.SafetyError):
            engine.require_phase2_artifact("bluez-main-config")

    def test_tree_modes_are_manifest_driven(self) -> None:
        engine = DEPLOY.ManagedDeployment(
            source_root=REPOSITORY,
            target=self.fixture.target,
        )
        quickshell = engine.require_phase2_artifact("quickshell-config")
        self.assertEqual(quickshell.directory_mode, 0o755)
        self.assertEqual(quickshell.file_mode, 0o644)
        self.assertEqual(quickshell.executable_mode, 0o755)
        self.assertEqual(len(quickshell.executable), 3)

    def test_duplicate_target_is_rejected(self) -> None:
        path = self.fixture.release_a / "deployment/ownership-v2.toml"
        text = path.read_text(encoding="utf-8")
        duplicate = artifact_table(
            "duplicate",
            "payload/added.txt",
            "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/changed.txt",
        )
        self.fixture._write(self.fixture.release_a, "payload/added.txt", "duplicate\n")
        path.write_text(text + duplicate, encoding="utf-8")
        with self.assertRaises(DEPLOY.ManifestError):
            self.fixture.engine(self.fixture.release_a, "A")

    def test_missing_source_is_rejected(self) -> None:
        (self.fixture.release_a / "payload/changed.txt").unlink()
        with self.assertRaises(DEPLOY.ManifestError):
            self.fixture.engine(self.fixture.release_a, "A").plan("install")

    def test_malformed_manifest_is_rejected(self) -> None:
        (self.fixture.release_a / "deployment/ownership-v2.toml").write_text(
            "not = [valid", encoding="utf-8"
        )
        with self.assertRaises(DEPLOY.ManifestError):
            self.fixture.engine(self.fixture.release_a, "A")

    def test_absolute_and_traversing_sources_are_rejected(self) -> None:
        path = self.fixture.release_a / "deployment/ownership-v2.toml"
        original = path.read_text(encoding="utf-8")
        for unsafe in ("/etc/passwd", "../outside"):
            with self.subTest(unsafe=unsafe):
                path.write_text(
                    original.replace('source = "payload/changed.txt"', f'source = "{unsafe}"', 1),
                    encoding="utf-8",
                )
                with self.assertRaises(DEPLOY.ManifestError):
                    self.fixture.engine(self.fixture.release_a, "A")
        path.write_text(original, encoding="utf-8")


class TargetResolutionTests(FixtureTestCase):
    def test_xdg_defaults_and_overrides(self) -> None:
        defaults = DEPLOY.TargetContext.from_environment(
            environment={"HOME": str(self.fixture.target_home)}
        )
        self.assertEqual(defaults.config, self.fixture.target_home / ".config")
        self.assertEqual(defaults.data, self.fixture.target_home / ".local/share")
        self.assertEqual(defaults.state, self.fixture.target_home / ".local/state")
        self.assertEqual(
            self.fixture.target.resolve(
                "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/value"
            )[0],
            self.fixture.target.config / "fixture/value",
        )

    def test_relative_target_roots_are_rejected(self) -> None:
        with self.assertRaises(DEPLOY.SafetyError):
            DEPLOY.TargetContext.build(home="relative")

    def test_user_deployment_refuses_root_execution(self) -> None:
        engine = self.fixture.engine(self.fixture.release_a, "A")
        with mock.patch.object(DEPLOY.os, "geteuid", return_value=0):
            with self.assertRaises(DEPLOY.SafetyError):
                engine.apply("install")
        self.assertFalse(self.fixture.provenance.exists())

    def test_target_traversal_and_pattern_are_rejected(self) -> None:
        for target in (
            "${XDG_CONFIG_HOME:-$HOME/.config}/../escape",
            "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/*",
            "/etc/escape",
        ):
            with self.subTest(target=target), self.assertRaises(
                (DEPLOY.ManifestError, DEPLOY.SafetyError)
            ):
                self.fixture.target.resolve(target)
        with self.assertRaises(DEPLOY.ManifestError):
            self.fixture.target.resolve(
                "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/nu\x00l"
            )

    def test_source_destination_overlap_is_rejected(self) -> None:
        target = DEPLOY.TargetContext.build(
            home=self.fixture.release_a,
            config=self.fixture.release_a / "config",
            data=self.fixture.release_a / "data",
            state=self.fixture.release_a / "state",
        )
        with self.assertRaises(DEPLOY.SafetyError):
            DEPLOY.ManagedDeployment(source_root=self.fixture.release_a, target=target)


class InstallAndPlanTests(FixtureTestCase):
    def test_plan_is_deterministic_and_performs_zero_writes(self) -> None:
        engine = self.fixture.engine(self.fixture.release_a, "A")
        first = [item.line() for item in engine.plan("install").items]
        second = [item.line() for item in engine.plan("install").items]
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertTrue(all(line.startswith("create\t") for line in first))
        self.assertFalse(self.fixture.provenance.exists())
        self.assertFalse(self.fixture.target.config.exists())
        self.assertFalse(self.fixture.target.data.exists())

    def test_install_uses_regular_files_exact_modes_and_provenance(self) -> None:
        engine = self.fixture.engine(self.fixture.release_a, "A")
        previous_umask = os.umask(0o077)
        try:
            engine.apply("install")
        finally:
            os.umask(previous_umask)
        unchanged = self.fixture.target.config / "fixture/unchanged.txt"
        command = self.fixture.target.home / ".local/bin/fixture-helper"
        tree = self.fixture.target.data / "fixture/tree"
        for path in (unchanged, command, tree, tree / "keep.txt", self.fixture.provenance):
            self.assertFalse(path.is_symlink(), path)
        self.assertTrue(unchanged.is_file())
        self.assertTrue(command.is_file())
        self.assertTrue(tree.is_dir())
        self.assertEqual(stat.S_IMODE(unchanged.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(command.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(tree.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((tree / "keep.txt").stat().st_mode), 0o644)
        self.assertEqual(
            stat.S_IMODE((self.fixture.target.config / "fixture").stat().st_mode),
            0o755,
        )
        self.assertEqual(stat.S_IMODE(self.fixture.provenance.stat().st_mode), 0o600)
        state = json.loads(self.fixture.provenance.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["operation"], "complete")
        self.assertEqual(state["release_id"], "A")
        self.assertEqual({item["class"] for item in state["artifacts"]}, {"VANILLA_MANAGED"})
        self.assertNotIn("preference", self.fixture.provenance.read_text(encoding="utf-8"))
        self.assertFalse(
            (self.fixture.target.config / "fixture/create-once.txt").exists()
        )
        self.assertFalse(
            any(
                path.name.startswith((".vanhyprarch-stage-", ".vanhyprarch-state-"))
                for path in (self.fixture.root / "target").rglob("*")
            )
        )

    def test_installed_tree_survives_source_rename(self) -> None:
        engine = self.fixture.engine(self.fixture.release_a, "A")
        engine.apply("install")
        moved = self.fixture.root / "release-a-removed"
        self.fixture.release_a.rename(moved)
        self.assertEqual(
            (self.fixture.target.config / "fixture/changed.txt").read_text(encoding="utf-8"),
            "old\n",
        )
        self.assertEqual(
            (self.fixture.target.data / "fixture/tree/keep.txt").read_text(encoding="utf-8"),
            "same tree\n",
        )
        for path in (self.fixture.target.config, self.fixture.target.data):
            self.assertFalse(any(candidate.is_symlink() for candidate in path.rglob("*")))

    def test_identical_install_and_update_are_noops(self) -> None:
        engine = self.fixture.engine(self.fixture.release_a, "A")
        engine.apply("install")
        managed = self.fixture.target.config / "fixture/unchanged.txt"
        before = (managed.stat().st_ino, managed.stat().st_mtime_ns, self.fixture.provenance.read_bytes())
        install_plan = engine.apply("install")
        middle = (managed.stat().st_ino, managed.stat().st_mtime_ns, self.fixture.provenance.read_bytes())
        update_plan = engine.apply("update")
        after = (managed.stat().st_ino, managed.stat().st_mtime_ns, self.fixture.provenance.read_bytes())
        self.assertFalse(install_plan.changes)
        self.assertFalse(update_plan.changes)
        self.assertEqual(before, middle)
        self.assertEqual(middle, after)

    def test_cli_plan_is_script_friendly_and_zero_write(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--source-root",
                str(self.fixture.release_a),
                "--release-id",
                "A",
                "--home",
                str(self.fixture.target.home),
                "--xdg-config-home",
                str(self.fixture.target.config),
                "--xdg-data-home",
                str(self.fixture.target.data),
                "--xdg-state-home",
                str(self.fixture.target.state),
                "plan",
                "install",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(len(line.split("\t")) == 4 for line in result.stdout.splitlines()))
        self.assertFalse(self.fixture.provenance.exists())


class UpdateTests(FixtureTestCase):
    def test_release_b_update_covers_add_change_remove_mode_and_tree(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        outside = self.fixture.target.config / "fixture-user-owned.txt"
        outside.write_text("preserve me\n", encoding="utf-8")
        engine = self.fixture.engine(self.fixture.release_b, "B")
        plan = {item.identifier: item.action for item in engine.plan("update").items}
        self.assertEqual(plan["unchanged"], "preserve")
        self.assertEqual(plan["changed"], "replace")
        self.assertEqual(plan["added"], "create")
        self.assertEqual(plan["removed"], "remove")
        self.assertEqual(plan["mode-change"], "replace")
        self.assertEqual(plan["tree"], "replace")
        with mock.patch.object(
            DEPLOY, "_atomic_exchange", wraps=DEPLOY._atomic_exchange
        ) as exchange:
            engine.apply("update")
        self.assertEqual(
            (self.fixture.target.config / "fixture/changed.txt").read_text(encoding="utf-8"),
            "new\n",
        )
        self.assertTrue((self.fixture.target.config / "fixture/added.txt").is_file())
        self.assertFalse((self.fixture.target.config / "fixture/removed.txt").exists())
        self.assertEqual(
            stat.S_IMODE((self.fixture.target.home / ".local/bin/mode-change").stat().st_mode),
            0o755,
        )
        tree = self.fixture.target.data / "fixture/tree"
        self.assertTrue(
            any(Path(call.args[1]) == tree for call in exchange.call_args_list),
            "tree update did not use atomic generation exchange",
        )
        self.assertEqual((tree / "change.txt").read_text(encoding="utf-8"), "new tree\n")
        self.assertTrue((tree / "added.txt").is_file())
        self.assertFalse((tree / "removed.txt").exists())
        self.assertEqual(outside.read_text(encoding="utf-8"), "preserve me\n")
        self.assertEqual(
            json.loads(self.fixture.provenance.read_text(encoding="utf-8"))["release_id"],
            "B",
        )

    def test_update_requires_provenance(self) -> None:
        plan = self.fixture.engine(self.fixture.release_b, "B").plan("update")
        self.assertEqual(len(plan.conflicts), 1)
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_b, "B").apply("update")

    def test_unknown_file_and_managed_drift_are_preserved_and_refused(self) -> None:
        destination = self.fixture.target.config / "fixture/changed.txt"
        destination.parent.mkdir(parents=True)
        destination.write_text("unknown\n", encoding="utf-8")
        engine = self.fixture.engine(self.fixture.release_a, "A")
        self.assertEqual(
            {item.identifier: item.action for item in engine.plan("install").items}["changed"],
            "conflict",
        )
        with self.assertRaises(DEPLOY.ConflictError):
            engine.apply("install")
        self.assertEqual(destination.read_text(encoding="utf-8"), "unknown\n")

        destination.unlink()
        engine.apply("install")
        destination.write_text("user edit\n", encoding="utf-8")
        update = self.fixture.engine(self.fixture.release_b, "B")
        with self.assertRaises(DEPLOY.ConflictError):
            update.apply("update")
        self.assertEqual(destination.read_text(encoding="utf-8"), "user edit\n")

    def test_unknown_file_inside_managed_tree_causes_conflict(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        extra = self.fixture.target.data / "fixture/tree/user.txt"
        extra.write_text("unknown\n", encoding="utf-8")
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_b, "B").apply("update")
        self.assertEqual(extra.read_text(encoding="utf-8"), "unknown\n")

    def test_modified_stale_artifact_is_never_removed(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        stale = self.fixture.target.config / "fixture/removed.txt"
        stale.write_text("changed after install\n", encoding="utf-8")
        engine = self.fixture.engine(self.fixture.release_b, "B")
        plan = {item.identifier: item.action for item in engine.plan("update").items}
        self.assertEqual(plan["removed"], "conflict")
        with self.assertRaises(DEPLOY.ConflictError):
            engine.apply("update")
        self.assertEqual(stale.read_text(encoding="utf-8"), "changed after install\n")

    def test_malformed_or_symlinked_provenance_is_refused(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        self.fixture.provenance.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_b, "B").plan("update")

        self.fixture.provenance.write_text('{"schema_version":', encoding="utf-8")
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_b, "B").plan("update")

        self.fixture.cleanup()
        self.fixture = Fixture()
        outside = self.fixture.root / "outside-state.json"
        outside.write_text("safe\n", encoding="utf-8")
        self.fixture.provenance.parent.mkdir(parents=True)
        self.fixture.provenance.symlink_to(outside)
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_a, "A").plan("install")
        self.assertEqual(outside.read_text(encoding="utf-8"), "safe\n")


class SymlinkAndTypeSafetyTests(FixtureTestCase):
    def test_source_symlink_outside_root_is_rejected(self) -> None:
        source = self.fixture.release_a / "payload/changed.txt"
        source.unlink()
        source.symlink_to("/etc/passwd")
        with self.assertRaises(DEPLOY.SafetyError):
            self.fixture.engine(self.fixture.release_a, "A").plan("install")

    def test_destination_symlink_is_refused(self) -> None:
        outside = self.fixture.root / "outside.txt"
        outside.write_text("safe\n", encoding="utf-8")
        destination = self.fixture.target.config / "fixture/changed.txt"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(outside)
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_a, "A").apply("install")
        self.assertEqual(outside.read_text(encoding="utf-8"), "safe\n")

    def test_destination_parent_symlink_is_refused(self) -> None:
        outside = self.fixture.root / "outside"
        outside.mkdir()
        self.fixture.target.config.mkdir(parents=True)
        (self.fixture.target.config / "fixture").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(DEPLOY.SafetyError):
            self.fixture.engine(self.fixture.release_a, "A").plan("install")
        self.assertEqual(list(outside.iterdir()), [])

    def test_file_directory_type_confusion_is_refused(self) -> None:
        file_target = self.fixture.target.config / "fixture/changed.txt"
        file_target.mkdir(parents=True)
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_a, "A").apply("install")
        self.assertTrue(file_target.is_dir())

        self.fixture.cleanup()
        self.fixture = Fixture()
        tree_target = self.fixture.target.data / "fixture/tree"
        tree_target.parent.mkdir(parents=True)
        tree_target.write_text("unknown\n", encoding="utf-8")
        with self.assertRaises(DEPLOY.ConflictError):
            self.fixture.engine(self.fixture.release_a, "A").apply("install")
        self.assertEqual(tree_target.read_text(encoding="utf-8"), "unknown\n")


class RollbackTests(FixtureTestCase):
    def test_file_replacement_and_provenance_roll_back(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        target = self.fixture.target.config / "fixture/changed.txt"
        old_stat = (target.read_bytes(), stat.S_IMODE(target.stat().st_mode))
        state_before_failure: list[bytes] = []

        def fail(point: str, identifier: str) -> None:
            if point == "before-state-write" and identifier == "changed":
                state_before_failure.append(self.fixture.provenance.read_bytes())
            if point == "after-state-replace" and identifier == "changed":
                raise OSError("fixture state failure")

        with self.assertRaises(OSError):
            self.fixture.engine(self.fixture.release_b, "B", fail).apply("update")
        self.assertEqual((target.read_bytes(), stat.S_IMODE(target.stat().st_mode)), old_stat)
        self.assertEqual(self.fixture.provenance.read_bytes(), state_before_failure[0])

    def test_post_replace_validation_failure_restores_file(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        target = self.fixture.target.config / "fixture/changed.txt"
        old = target.read_bytes()

        def fail(point: str, identifier: str) -> None:
            if point == "after-replace" and identifier == "changed":
                raise DEPLOY.ValidationError("fixture installed validation failure")

        with self.assertRaises(DEPLOY.ValidationError):
            self.fixture.engine(self.fixture.release_b, "B", fail).apply("update")
        self.assertEqual(target.read_bytes(), old)
        state = json.loads(self.fixture.provenance.read_text(encoding="utf-8"))
        self.assertNotIn("transaction", state)
        self.assertEqual(state["status"], "partial")

    def test_complete_tree_rolls_back_after_interrupted_switch(self) -> None:
        self.fixture.engine(self.fixture.release_a, "A").apply("install")
        tree = self.fixture.target.data / "fixture/tree"
        before = {path.relative_to(tree): path.read_bytes() for path in tree.rglob("*") if path.is_file()}

        def fail(point: str, identifier: str) -> None:
            if point == "after-backup" and identifier == "tree":
                raise OSError("fixture interrupted tree switch")

        with self.assertRaises(OSError):
            self.fixture.engine(self.fixture.release_b, "B", fail).apply("update")
        after = {path.relative_to(tree): path.read_bytes() for path in tree.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        partial = json.loads(self.fixture.provenance.read_text(encoding="utf-8"))
        self.assertNotIn("transaction", partial)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["operation"], "update")
        self.fixture.engine(self.fixture.release_b, "B").apply("update")
        completed = json.loads(self.fixture.provenance.read_text(encoding="utf-8"))
        self.assertEqual(completed["status"], "complete")
        self.assertEqual((tree / "change.txt").read_text(encoding="utf-8"), "new tree\n")

    def test_new_artifact_is_removed_when_state_write_fails(self) -> None:
        single = self.fixture.root / "single"
        self.fixture._write(single, "payload/new.txt", "new\n")
        self.fixture._write(
            single,
            "deployment/ownership-v2.toml",
            manifest_text(
                [
                    artifact_table(
                        "new",
                        "payload/new.txt",
                        "${XDG_CONFIG_HOME:-$HOME/.config}/fixture/new.txt",
                    )
                ]
            ),
            0o644,
        )

        def fail(point: str, identifier: str) -> None:
            if point == "before-state-write" and identifier == "new":
                raise OSError("fixture state failure")

        engine = self.fixture.engine(single, "single", fail)
        with self.assertRaises(OSError):
            engine.apply("install")
        self.assertFalse((self.fixture.target.config / "fixture/new.txt").exists())
        self.assertFalse(self.fixture.provenance.exists())

    def test_permission_failure_leaves_unknown_state_untouched(self) -> None:
        engine = self.fixture.engine(self.fixture.release_a, "A")
        target = self.fixture.target.config / "fixture/changed.txt"
        real_replace = DEPLOY.os.replace

        def denied(source: object, destination: object) -> None:
            if Path(destination) == target:
                raise PermissionError("fixture denied")
            real_replace(source, destination)

        with mock.patch.object(DEPLOY.os, "replace", side_effect=denied):
            with self.assertRaises(PermissionError):
                engine.apply("install")
        self.assertFalse(target.exists())
        self.assertFalse(self.fixture.provenance.exists())

    def test_source_validation_failure_writes_nothing(self) -> None:
        (self.fixture.release_a / "payload/helper.py").write_text(
            "this is not Python !\n", encoding="utf-8"
        )
        with self.assertRaises(DEPLOY.ValidationError):
            self.fixture.engine(self.fixture.release_a, "A").apply("install")
        self.assertFalse(self.fixture.provenance.exists())
        self.assertFalse(self.fixture.target.config.exists())


class CrashConsistencyTests(FixtureTestCase):
    def _reset(self) -> None:
        self.fixture.cleanup()
        self.fixture = Fixture()

    def _replacement_pair(self, *, tree: bool = False) -> tuple[Path, Path, Path]:
        if tree:
            table = artifact_table(
                "subject",
                "payload/tree",
                "${XDG_DATA_HOME:-$HOME/.local/share}/crash/tree",
                kind="tree",
            )
            release_a = self.fixture.write_minimal_release(
                "crash-a",
                [table],
                {
                    "payload/tree/keep.txt": "same\n",
                    "payload/tree/change.txt": "old\n",
                    "payload/tree/removed.txt": "old member\n",
                },
            )
            release_b = self.fixture.write_minimal_release(
                "crash-b",
                [table],
                {
                    "payload/tree/keep.txt": "same\n",
                    "payload/tree/change.txt": "new\n",
                    "payload/tree/added.txt": "new member\n",
                },
            )
            target = self.fixture.target.data / "crash/tree"
        else:
            table = artifact_table(
                "subject",
                "payload/subject.txt",
                "${XDG_CONFIG_HOME:-$HOME/.config}/crash/subject.txt",
            )
            release_a = self.fixture.write_minimal_release(
                "crash-a", [table], {"payload/subject.txt": "old\n"}
            )
            release_b = self.fixture.write_minimal_release(
                "crash-b", [table], {"payload/subject.txt": "new\n"}
            )
            target = self.fixture.target.config / "crash/subject.txt"
        self.fixture.engine(release_a, "A").apply("install")
        return release_a, release_b, target

    def _creation_pair(self) -> tuple[Path, Path, Path]:
        release_a = self.fixture.write_minimal_release("create-a", [], {})
        table = artifact_table(
            "subject",
            "payload/subject.txt",
            "${XDG_CONFIG_HOME:-$HOME/.config}/crash/subject.txt",
        )
        release_b = self.fixture.write_minimal_release(
            "create-b", [table], {"payload/subject.txt": "new\n"}
        )
        self.fixture.engine(release_a, "A").apply("install")
        return release_a, release_b, self.fixture.target.config / "crash/subject.txt"

    def _removal_pair(self) -> tuple[Path, Path, Path]:
        table = artifact_table(
            "subject",
            "payload/subject.txt",
            "${XDG_CONFIG_HOME:-$HOME/.config}/crash/subject.txt",
        )
        release_a = self.fixture.write_minimal_release(
            "remove-a", [table], {"payload/subject.txt": "old\n"}
        )
        release_b = self.fixture.write_minimal_release("remove-b", [], {})
        self.fixture.engine(release_a, "A").apply("install")
        return release_a, release_b, self.fixture.target.config / "crash/subject.txt"

    def _assert_clean_recovery(self) -> bytes:
        state_bytes = self.fixture.provenance.read_bytes()
        state = json.loads(state_bytes.decode("utf-8"))
        self.assertNotIn("transaction", state)
        self.assertEqual(
            list((self.fixture.root / "target").rglob(".vanhyprarch-transaction-*")),
            [],
        )
        return state_bytes

    def _crash(self, release: Path, point: str) -> None:
        result = self.fixture.cli(
            release,
            "B",
            "update",
            fault=f"{point}:subject",
        )
        self.assertEqual(result.returncode, 197, result.stderr)

    def test_replacement_windows_r1_through_r5_recover_idempotently(self) -> None:
        precommit = (
            "after-intent-state-publish",
            "after-stage-file-fsync",
            "after-intent-ready-state-publish",
            "before-publish",
            "after-publish",
            "after-publish-verify",
        )
        postcommit = (
            "after-provenance-state-publish",
            "after-provenance-commit",
            "after-cleanup-intent",
            "during-cleanup",
            "after-cleanup",
        )
        for point in precommit + postcommit:
            with self.subTest(point=point):
                self._reset()
                release_a, release_b, target = self._replacement_pair()
                self._crash(release_b, point)
                state = json.loads(self.fixture.provenance.read_text(encoding="utf-8"))
                self.assertIn("transaction", state)
                recovery_release = release_a if point in precommit else release_b
                recovery_id = "A" if point in precommit else "B"
                recovery_command = "install" if point in precommit else "update"
                first = self.fixture.cli(recovery_release, recovery_id, recovery_command)
                self.assertEqual(first.returncode, 0, first.stderr)
                expected = b"old\n" if point in precommit else b"new\n"
                self.assertEqual(target.read_bytes(), expected)
                ledger = self._assert_clean_recovery()
                second = self.fixture.cli(recovery_release, recovery_id, recovery_command)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self.fixture.provenance.read_bytes(), ledger)

    def test_create_windows_n1_through_n3_recover_idempotently(self) -> None:
        cases = (
            ("before-publish", False),
            ("after-publish", False),
            ("after-provenance-commit", True),
        )
        for point, committed in cases:
            with self.subTest(point=point):
                self._reset()
                release_a, release_b, target = self._creation_pair()
                self._crash(release_b, point)
                recovery_release = release_b if committed else release_a
                recovery_id = "B" if committed else "A"
                command = "update" if committed else "install"
                first = self.fixture.cli(recovery_release, recovery_id, command)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(target.exists(), committed)
                ledger = self._assert_clean_recovery()
                second = self.fixture.cli(recovery_release, recovery_id, command)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self.fixture.provenance.read_bytes(), ledger)

    def test_stale_removal_windows_s1_through_s3_recover_idempotently(self) -> None:
        cases = (
            ("before-publish", False),
            ("after-publish", False),
            ("after-provenance-commit", True),
        )
        for point, committed in cases:
            with self.subTest(point=point):
                self._reset()
                release_a, release_b, target = self._removal_pair()
                self._crash(release_b, point)
                recovery_release = release_b if committed else release_a
                recovery_id = "B" if committed else "A"
                command = "update" if committed else "install"
                first = self.fixture.cli(recovery_release, recovery_id, command)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(target.exists(), not committed)
                if not committed:
                    self.assertEqual(target.read_bytes(), b"old\n")
                ledger = self._assert_clean_recovery()
                second = self.fixture.cli(recovery_release, recovery_id, command)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self.fixture.provenance.read_bytes(), ledger)

    def test_tree_exchange_is_always_one_complete_generation(self) -> None:
        for point, committed in (
            ("after-publish", False),
            ("after-publish-verify", False),
            ("after-provenance-commit", True),
        ):
            with self.subTest(point=point):
                self._reset()
                release_a, release_b, tree = self._replacement_pair(tree=True)
                self._crash(release_b, point)
                visible = {path.name: path.read_text(encoding="utf-8") for path in tree.iterdir()}
                self.assertIn(
                    visible,
                    (
                        {"keep.txt": "same\n", "change.txt": "old\n", "removed.txt": "old member\n"},
                        {"keep.txt": "same\n", "change.txt": "new\n", "added.txt": "new member\n"},
                    ),
                )
                source = release_b if committed else release_a
                release_id = "B" if committed else "A"
                command = "update" if committed else "install"
                result = self.fixture.cli(source, release_id, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected_member = "added.txt" if committed else "removed.txt"
                absent_member = "removed.txt" if committed else "added.txt"
                self.assertTrue((tree / expected_member).exists())
                self.assertFalse((tree / absent_member).exists())
                self._assert_clean_recovery()

    def test_tree_cleanup_resumes_from_a_partially_removed_rollback(self) -> None:
        _release_a, release_b, tree = self._replacement_pair(tree=True)
        self._crash(release_b, "after-cleanup-intent")
        state = json.loads(self.fixture.provenance.read_text(encoding="utf-8"))
        transaction = state["transaction"]
        self.assertEqual(transaction["phase"], "cleaning")
        rollback = tree.parent / transaction["container"] / "payload"
        (rollback / "removed.txt").unlink()
        result = self.fixture.cli(release_b, "B", "update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((tree / "change.txt").read_text(encoding="utf-8"), "new\n")
        self.assertTrue((tree / "added.txt").exists())
        self.assertFalse((tree / "removed.txt").exists())
        self._assert_clean_recovery()

    def test_plan_and_validate_report_interruption_without_writes(self) -> None:
        _release_a, release_b, _target = self._replacement_pair()
        self._crash(release_b, "after-publish")
        before = self.fixture.target_snapshot()
        plan = self.fixture.cli(release_b, "B", "plan", operation="update")
        self.assertEqual(plan.returncode, 2)
        self.assertIn("recovery-required\tsubject", plan.stdout)
        self.assertEqual(self.fixture.target_snapshot(), before)
        validate = self.fixture.cli(release_b, "B", "validate")
        self.assertEqual(validate.returncode, 2)
        self.assertIn("recovery is required", validate.stderr)
        self.assertEqual(self.fixture.target_snapshot(), before)

    def test_manual_drift_during_interruption_remains_a_conflict(self) -> None:
        release_a, release_b, target = self._replacement_pair()
        self._crash(release_b, "after-publish")
        target.write_text("manual\n", encoding="utf-8")
        result = self.fixture.cli(release_a, "A", "install")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no longer matches transaction evidence", result.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), "manual\n")
        self.assertIn(
            "transaction",
            json.loads(self.fixture.provenance.read_text(encoding="utf-8")),
        )

    def test_unknown_content_inside_tree_during_interruption_conflicts(self) -> None:
        release_a, release_b, tree = self._replacement_pair(tree=True)
        self._crash(release_b, "after-publish")
        (tree / "manual.txt").write_text("manual\n", encoding="utf-8")
        result = self.fixture.cli(release_a, "A", "install")
        self.assertEqual(result.returncode, 2)
        self.assertTrue((tree / "manual.txt").exists())

    def test_fsync_failures_never_report_success_and_recover_old_state(self) -> None:
        points = (
            "before-stage-file-fsync",
            "before-publish-parent-fsync",
            "before-provenance-state-file-fsync",
            "before-provenance-state-directory-fsync",
        )
        for point in points:
            with self.subTest(point=point):
                self._reset()
                release_a, release_b, target = self._replacement_pair()
                ledger_a = self.fixture.provenance.read_bytes()

                def fail(selected: str, identifier: str) -> None:
                    if selected == point and identifier == "subject":
                        raise OSError(f"injected {point}")

                with self.assertRaises(OSError):
                    self.fixture.engine(release_b, "B", fail).apply("update")
                self.assertEqual(target.read_bytes(), b"old\n")
                self.assertEqual(self.fixture.provenance.read_bytes(), ledger_a)
                self._assert_clean_recovery()

    def test_unrecorded_lookalike_cleanup_targets_are_preserved(self) -> None:
        _release_a, release_b, target = self._replacement_pair()
        state_lookalike = self.fixture.provenance.parent / ".vanhyprarch-state-user"
        state_lookalike.write_text("user\n", encoding="utf-8")
        transaction_lookalike = target.parent / (
            ".vanhyprarch-transaction-" + "f" * 32
        )
        transaction_lookalike.mkdir(mode=0o700)
        (transaction_lookalike / "user.txt").write_text("user\n", encoding="utf-8")
        self.fixture.engine(release_b, "B").apply("update")
        self.assertEqual(state_lookalike.read_text(encoding="utf-8"), "user\n")
        self.assertEqual(
            (transaction_lookalike / "user.txt").read_text(encoding="utf-8"),
            "user\n",
        )


class DocumentationAndBoundaryTests(unittest.TestCase):
    def test_phase2_documentation_records_scope_and_safety(self) -> None:
        document = (REPOSITORY / "docs/managed-file-deployment.md").read_text(
            encoding="utf-8"
        )
        for expected in (
            "`VANILLA_MANAGED`",
            "plan/install/update/reconcile/validate",
            "renameat2(RENAME_EXCHANGE)",
            "partial` ledger",
            "`recovery-required`",
            "`staging` and `prepared`",
            "`committed` and `cleaning`",
            "`os._exit`",
            "does not call `chown`",
            "does not invoke pacman, yay, sudo, systemctl",
            "does not create machine or override",
            "not the complete installer",
        ):
            self.assertIn(expected, document)

    def test_executor_contains_no_package_or_service_mutation_commands(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in (
            '"pacman"',
            '"yay"',
            '"sudo"',
            '"systemctl"',
            "daemon-reload",
            "/etc/bluetooth",
        ):
            self.assertNotIn(forbidden, source)

    def test_phase2_sources_have_no_development_machine_paths(self) -> None:
        paths = (
            MODULE_PATH,
            REPOSITORY / "deployment/ownership-v2.toml",
            REPOSITORY / "docs/managed-file-deployment.md",
        )
        for path in paths:
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("/home/giacomo", content)
            self.assertNotIn("/tmp/vanilla-hyprarch-df2-phase2", content)


if __name__ == "__main__":
    unittest.main()
