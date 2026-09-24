#!/usr/bin/env python3
"""Offline target-driver, staging, authority orchestration, and recovery tests."""

from __future__ import annotations

import copy
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from install.release_update import (  # noqa: E402
    AuthorityRunner, Bundle, BundleStore, ReleaseUpdate, TargetUser, UpdateError,
)
from install.release_identity import IdentityError, InstalledReleaseIdentity  # noqa: E402
from install.update_journal import JournalError  # noqa: E402
from release import build as contract  # noqa: E402


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *arguments], check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def declaration(version: str, *, minimum: str | None, low: int, high: int) -> bytes:
    values = ["schema = 1", f'version = "{version}"',
              f'channel = "{"candidate" if "-rc" in version else "stable"}"',
              'architecture = "x86_64"', "update_protocol = 1",
              f"minimum_migration_level = {low}", f"migration_level = {high}",
              'summary = "Fixture release"']
    if minimum is not None:
        values.append(f'minimum_installed_version = "{minimum}"')
    return ("\n".join(values) + "\n").encode()


MIGRATION = '''def plan(ctx):
    path = ctx.system_root / "migration-state.txt"
    if path.exists() and path.read_text() != "1":
        raise ValueError("foreign migration state")
    return ["initialize fixture backend state"]

def apply(ctx):
    if (ctx.system_root / "migration-fail").exists():
        raise ValueError("fixture migration interrupted")
    path = ctx.system_root / "migration-state.txt"
    if path.exists() and path.read_text() != "1":
        raise ValueError("foreign migration state")
    path.write_text("1")

def validate(ctx):
    path = ctx.system_root / "migration-state.txt"
    return path.exists() and path.read_text() == "1"
'''


class BundleFixture:
    @staticmethod
    def build(base: Path, *, target_version: str = "v1.0.0-rc2",
              minimum: str = "v1.0.0-rc1", low: int = 0,
              high: int = 1, registry_ids: list[int] | None = None) -> tuple[dict, Path, Path, dict]:
        repo = base / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")
        for name in contract.REQUIRED_FILES | set((
                "install/sddm_login_integration.py", "release/migrations/registry.toml")):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(declaration("v1.0.0-rc1", minimum=None, low=0, high=0)
                             if name == "release/release.toml" else b"fixture\n")
        (repo / "release/migrations/registry.toml").write_text("schema = 1\n")
        (repo / "install/bootstrap").chmod(0o755)
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "source")
        source_commit = git(repo, "rev-parse", "HEAD")
        source_dir = base / "source-output"
        source_dir.mkdir()
        source_json, _source_archive = contract.build(repo, source_commit, source_dir)
        source = contract.parse_metadata(source_json.read_bytes())

        (repo / "release/release.toml").write_bytes(
            declaration(target_version, minimum=minimum, low=low, high=high))
        entries = (list(range(low + 1, high + 1)) if registry_ids is None
                   else registry_ids)
        lines = ["schema = 1"]
        for number in entries:
            lines.extend(("", "[[migration]]", f"id = {number}",
                          f'name = "fixture-{number}"',
                          f'path = "release/migrations/{number:04d}-fixture-{number}.py"',
                          'scope = "BACKEND_OWNED fixture"',
                          "touches_user_state = false"))
            (repo / f"release/migrations/{number:04d}-fixture-{number}.py").write_text(MIGRATION)
        (repo / "release/migrations/registry.toml").write_text("\n".join(lines) + "\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "target")
        target_commit = git(repo, "rev-parse", "HEAD")
        target_dir = base / "target-output"
        target_dir.mkdir()
        target_json, target_archive = contract.build(repo, target_commit, target_dir)
        target = contract.parse_metadata(target_json.read_bytes())
        return source, target_json, target_archive, target


class FakeAuthorities:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, str]] = []
        self.fail_before: str | None = None
        self.fail_after: str | None = None
        self.validate_count: dict[str, int] = {}
        self.fail_validation_count: tuple[str, int] | None = None
        self.fail_plan: str | None = None

    def invoke(self, stage: str, operation: str, bundle, _user) -> str:
        self.calls.append((stage, operation))
        if operation == "plan":
            if self.fail_plan == stage:
                raise UpdateError("authority failed", f"{stage} preflight blocked")
            return f"{stage}: plan"
        marker = self.root / f"{stage}.done"
        if operation == "validate":
            self.validate_count[stage] = self.validate_count.get(stage, 0) + 1
            if self.fail_validation_count == (stage, self.validate_count[stage]):
                raise UpdateError("authority failed", f"{stage} final validation interrupted")
            if not marker.exists() or marker.read_text() != bundle.metadata["artifact"]["sha256"]:
                raise UpdateError("authority failed", f"{stage} target state not installed")
            return f"{stage}: valid"
        if self.fail_before == stage:
            self.fail_before = None
            raise UpdateError("authority failed", f"{stage} interrupted before apply")
        marker.write_text(bundle.metadata["artifact"]["sha256"])
        if self.fail_after == stage:
            self.fail_after = None
            raise UpdateError("authority failed", f"{stage} interrupted after apply")
        return f"{stage}: applied"


class DriverFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = tempfile.TemporaryDirectory()
        cls.source, cls.target_json, cls.target_archive, cls.target = BundleFixture.build(
            Path(cls.fixture.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "system"
        self.root.mkdir()
        (self.root / "run").mkdir()
        directory = self.root / "usr/share/vanhyprarch"
        directory.mkdir(parents=True)
        self.identity_path = directory / "release.json"
        self.identity_path.write_bytes(contract.metadata_bytes(self.source))
        self.identity_path.chmod(0o644)
        self.authority = FakeAuthorities(self.root)
        self.user = TargetUser("fixture", os.getuid(), os.getgid(),
                               Path("/home/fixture"), (os.getgid(),))
        self.driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(),
                                    gid=os.getgid(), testing=True,
                                    authority=self.authority)

    def staged(self) -> Path:
        return self.driver.store.parent / self.target["artifact"]["sha256"]


class DriverTests(DriverFixture):

    def test_plan_is_read_only_and_includes_all_authorities(self) -> None:
        before = self.identity_path.read_bytes()
        plan = self.driver.plan(self.target_json, self.target_archive)
        self.assertEqual(plan.source, self.source)
        self.assertEqual(plan.target, self.target)
        self.assertEqual(plan.migrations[0][0], 1)
        self.assertEqual(list(plan.authorities), ["system-integration", "managed-deployment", "create-once"])
        self.assertEqual(self.identity_path.read_bytes(), before)
        self.assertIsNone(self.driver.journal.inspect())
        self.assertFalse(self.staged().exists())
        self.assertFalse(self.driver.store.parent.exists())
        self.assertFalse(list(self.driver.store.preview_parent.glob("vanhyprarch-preview-*")))
        self.assertFalse(list(self.root.glob("*.done")))

    def test_authority_preflight_blocker_leaves_no_journal(self) -> None:
        self.authority.fail_plan = "system-integration"
        with self.assertRaisesRegex(UpdateError, "preflight blocked"):
            self.driver.apply(self.target_json, self.target_archive)
        self.assertIsNone(self.driver.journal.inspect())
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))

    def test_success_stage_order_commit_last_and_cleanup(self) -> None:
        before = self.identity_path.read_bytes()
        original = self.driver.identity.upgrade_commit

        def commit(source, data):
            self.assertEqual(self.identity_path.read_bytes(), before)
            self.assertEqual(self.driver.journal.inspect()["phase"], "ready-for-final-commit")
            self.assertEqual(self.driver.journal.inspect()["checkpoint"], "final-validation")
            self.assertEqual(self.root.joinpath("migration-state.txt").read_text(), "1")
            self.assertTrue(all(self.root.joinpath(f"{stage}.done").exists()
                                for stage in ("system-integration", "managed-deployment", "create-once")))
            self.assertTrue(all(self.authority.validate_count.get(stage, 0) >= 3
                                for stage in ("system-integration", "managed-deployment", "create-once")))
            return original(source, data)

        with mock.patch.object(self.driver.identity, "upgrade_commit", side_effect=commit):
            result = self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(result, self.target)
        self.assertEqual(self.identity_path.read_bytes(), self.target_json.read_bytes())
        self.assertIsNone(self.driver.journal.inspect())
        self.assertFalse(self.staged().exists())
        applied = [stage for stage, operation in self.authority.calls if operation == "apply"]
        self.assertEqual(applied, ["system-integration", "managed-deployment", "create-once"])

    def test_interrupted_migration_is_pending_and_resume_validates_first(self) -> None:
        (self.root / "migration-fail").touch()
        with self.assertRaisesRegex(UpdateError, "journal retained"):
            self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(self.driver.journal.inspect()["pending_migration"], 1)
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        (self.root / "migration-fail").unlink()
        (self.root / "migration-state.txt").write_text("1")
        self.assertEqual(self.driver.resume(), self.target)
        self.assertIsNone(self.driver.journal.inspect())

    def test_authority_interruption_before_and_after_apply_resumes(self) -> None:
        for stage, timing in (("system-integration", "before"),
                              ("system-integration", "after"),
                              ("managed-deployment", "before"),
                              ("managed-deployment", "after"),
                              ("create-once", "before"),
                              ("create-once", "after")):
            with self.subTest(stage=stage, timing=timing):
                with self.subTest("fresh root"):
                    self.setUp()
                setattr(self.authority, f"fail_{timing}", stage)
                with self.assertRaises(UpdateError):
                    self.driver.apply(self.target_json, self.target_archive)
                self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
                self.assertEqual(self.driver.journal.inspect()["target"]["artifact_sha256"],
                                 self.target["artifact"]["sha256"])
                previous_applies = self.authority.calls.count((stage, "apply"))
                self.assertEqual(self.driver.resume(), self.target)
                if timing == "after":
                    self.assertEqual(self.authority.calls.count((stage, "apply")), previous_applies)

    def test_interruption_immediately_after_journal_initialization_resumes(self) -> None:
        with mock.patch.object(self.driver, "_run_transaction", side_effect=RuntimeError("stopped")):
            with self.assertRaisesRegex(UpdateError, "journal retained"):
                self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(self.driver.journal.inspect()["checkpoint"], "preflight-complete")
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        self.assertEqual(self.driver.resume(), self.target)

    def test_final_validation_interruption_resumes_without_identity_advance(self) -> None:
        self.authority.fail_validation_count = ("managed-deployment", 3)
        with self.assertRaises(UpdateError):
            self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        self.assertEqual(self.driver.journal.inspect()["phase"], "validating")
        self.assertEqual(self.driver.resume(), self.target)

    def test_final_commit_failure_retains_old_identity_and_ready_journal(self) -> None:
        with mock.patch.object(self.driver.identity, "upgrade_commit", side_effect=OSError("write failed")):
            with self.assertRaisesRegex(UpdateError, "write failed"):
                self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        self.assertEqual(self.driver.journal.inspect()["phase"], "ready-for-final-commit")
        self.assertEqual(self.driver.resume(), self.target)

    def test_identity_committed_journal_present_terminal_cleanup(self) -> None:
        with mock.patch.object(self.driver.journal, "clear_after_commit", side_effect=OSError("clear interrupted")):
            with self.assertRaisesRegex(UpdateError, "resume to clear journal"):
                self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(self.identity_path.read_bytes(), self.target_json.read_bytes())
        self.assertIsNotNone(self.driver.journal.inspect())
        with self.assertRaises(UpdateError) as context:
            self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(context.exception.kind, "resume required")
        before = list(self.authority.calls)
        self.assertEqual(self.driver.resume(), self.target)
        self.assertEqual(self.authority.calls, before)
        self.assertIsNone(self.driver.journal.inspect())
        self.assertFalse(self.staged().exists())

    def test_identity_publication_error_after_replace_uses_terminal_recovery(self) -> None:
        real_fsync = os.fsync
        calls = 0

        def failing_fsync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("identity directory fsync interrupted")
            return real_fsync(descriptor)

        self.driver.identity.fsync = failing_fsync
        with self.assertRaises(UpdateError) as context:
            self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(context.exception.kind, "terminal cleanup required")
        self.assertEqual(self.identity_path.read_bytes(), self.target_json.read_bytes())
        self.assertIsNotNone(self.driver.journal.inspect())
        self.driver.identity.fsync = os.fsync
        self.assertEqual(self.driver.resume(), self.target)

    def test_interruption_after_journal_clear_cleans_exact_committed_stage(self) -> None:
        with mock.patch.object(self.driver.store, "remove_committed", side_effect=OSError("cleanup interrupted")):
            with self.assertRaises(UpdateError) as context:
                self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(context.exception.kind, "terminal cleanup required")
        self.assertIsNone(self.driver.journal.inspect())
        self.assertTrue(self.staged().exists())
        self.assertEqual(self.identity_path.read_bytes(), self.target_json.read_bytes())
        before = list(self.authority.calls)
        self.assertEqual(self.driver.resume(), self.target)
        self.assertEqual(self.authority.calls, before)
        self.assertFalse(self.staged().exists())

    def test_resume_is_offline_and_rejects_tampered_stage(self) -> None:
        self.authority.fail_before = "system-integration"
        with self.assertRaises(UpdateError):
            self.driver.apply(self.target_json, self.target_archive)
        self.target_archive.rename(self.target_archive.with_suffix(".removed"))
        self.addCleanup(self.target_archive.with_suffix(".removed").rename, self.target_archive)
        staged_file = self.staged() / "source" / contract.archive_root(self.target["version"]) / "install.sh"
        original = staged_file.read_bytes()
        staged_file.write_bytes(b"tampered")
        with self.assertRaisesRegex(UpdateError, "staged file differs"):
            self.driver.resume()
        staged_file.write_bytes(original)
        self.assertEqual(self.driver.resume(), self.target)

    def test_resume_rejects_symlinked_stage_and_changed_installed_source(self) -> None:
        self.authority.fail_before = "system-integration"
        with self.assertRaises(UpdateError):
            self.driver.apply(self.target_json, self.target_archive)
        staged_file = self.staged() / "source" / contract.archive_root(self.target["version"]) / "install.sh"
        original = staged_file.read_bytes()
        staged_file.unlink()
        staged_file.symlink_to(self.target_json)
        with self.assertRaises(UpdateError) as context:
            self.driver.resume()
        self.assertEqual(context.exception.kind, "transaction mismatch")
        self.assertIsNotNone(self.driver.journal.inspect())
        staged_file.unlink()
        staged_file.write_bytes(original)
        staged_file.chmod(0o644)
        changed = copy.deepcopy(self.source)
        changed["commit"] = "f" * 40
        self.identity_path.write_bytes(contract.metadata_bytes(changed))
        with self.assertRaises(UpdateError):
            self.driver.resume()
        self.assertIsNotNone(self.driver.journal.inspect())

    def test_active_journal_requires_resume_and_rejects_target_mismatch(self) -> None:
        self.authority.fail_before = "system-integration"
        with self.assertRaises(UpdateError):
            self.driver.apply(self.target_json, self.target_archive)
        with self.assertRaises(UpdateError) as context:
            self.driver.apply(self.target_json, self.target_archive)
        self.assertEqual(context.exception.kind, "resume required")
        changed = copy.deepcopy(self.target)
        changed["artifact"]["sha256"] = "a" * 64
        with self.assertRaises(JournalError):
            self.driver.journal.bound(self.source, changed)
        other_root = Path(self.temporary.name) / "other-bundle"
        other_root.mkdir()
        _source, other_json, other_archive, _other = BundleFixture.build(
            other_root, target_version="v1.0.0")
        with self.assertRaises(UpdateError) as context:
            self.driver.plan(other_json, other_archive)
        self.assertEqual(context.exception.kind, "transaction mismatch")

    def test_resume_rejects_different_target_user_before_authorities(self) -> None:
        self.authority.fail_before = "system-integration"
        with self.assertRaises(UpdateError):
            self.driver.apply(self.target_json, self.target_archive)
        other = TargetUser("other", self.user.uid, self.user.gid, self.user.home,
                           self.user.groups)
        different = ReleaseUpdate(other, root=self.root, uid=os.getuid(),
                                  gid=os.getgid(), testing=True,
                                  authority=self.authority)
        calls = list(self.authority.calls)
        with self.assertRaisesRegex(UpdateError, "different target user"):
            different.resume()
        self.assertEqual(self.authority.calls, calls)

    def test_development_missing_identity_rejected(self) -> None:
        self.identity_path.unlink()
        with self.assertRaises(IdentityError):
            self.driver.plan(self.target_json, self.target_archive)
        self.assertIsNone(self.driver.journal.inspect())

    def test_same_version_downgrade_stable_candidate_and_bad_bundle_rejected(self) -> None:
        for version, channel in (("v1.0.0-rc2", "candidate"),
                                 ("v1.0.0", "stable"),
                                 ("v0.9.0", "stable")):
            with self.subTest(version=version):
                source = copy.deepcopy(self.source)
                source["version"], source["channel"] = version, channel
                source["artifact"]["name"] = contract.artifact_name(version)
                self.identity_path.write_bytes(contract.metadata_bytes(source))
                with self.assertRaises((UpdateError, JournalError)):
                    self.driver.plan(self.target_json, self.target_archive)
        self.identity_path.write_bytes(contract.metadata_bytes(self.source))
        bad = Path(self.temporary.name) / self.target_archive.name
        bad.write_bytes(self.target_archive.read_bytes() + b"bad")
        with self.assertRaises(contract.ReleaseError):
            self.driver.plan(self.target_json, bad)

    def test_architecture_and_protocol_rejected(self) -> None:
        with mock.patch("install.release_update.platform.machine", return_value="aarch64"):
            with self.assertRaisesRegex(UpdateError, "architecture"):
                self.driver.plan(self.target_json, self.target_archive)
        malformed = copy.deepcopy(self.target)
        malformed["update_protocol"] = 2
        with self.assertRaises(contract.ReleaseError):
            contract.parse_metadata(contract.metadata_bytes(malformed))


class PreflightPolicyTests(DriverFixture):
    def _variant(self, **options):
        folder = Path(self.temporary.name) / f"variant-{len(list(Path(self.temporary.name).glob('variant-*')))}"
        folder.mkdir()
        _source, metadata_path, artifact_path, _target = BundleFixture.build(folder, **options)
        return metadata_path, artifact_path

    def test_minimum_installed_version_is_enforced(self) -> None:
        metadata_path, artifact_path = self._variant(minimum="v1.0.0-rc2")
        with self.assertRaisesRegex(JournalError, "support floor"):
            self.driver.plan(metadata_path, artifact_path)
        self.assertIsNone(self.driver.journal.inspect())

    def test_minimum_migration_level_is_enforced(self) -> None:
        metadata_path, artifact_path = self._variant(low=1, high=2)
        with self.assertRaisesRegex(JournalError, "support range"):
            self.driver.plan(metadata_path, artifact_path)

    def test_incomplete_target_migration_chain_fails_before_mutation(self) -> None:
        metadata_path, artifact_path = self._variant(high=2, registry_ids=[1])
        with self.assertRaisesRegex(ValueError, "registry has a gap"):
            self.driver.plan(metadata_path, artifact_path)
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        self.assertIsNone(self.driver.journal.inspect())

    def test_malformed_target_metadata_fails_before_target_code(self) -> None:
        for field, value in (("architecture", "aarch64"), ("update_protocol", 2)):
            with self.subTest(field=field):
                bad = copy.deepcopy(self.target)
                bad[field] = value
                metadata_path = Path(self.temporary.name) / "release.json"
                metadata_path.write_bytes(contract.metadata_bytes(bad))
                with self.assertRaises(contract.ReleaseError):
                    self.driver.plan(metadata_path, self.target_archive)
                self.assertEqual(self.authority.calls, [])

    def test_unsafe_staging_parent_fails_closed(self) -> None:
        parent = self.root / "var/lib"
        parent.mkdir(parents=True)
        (parent / "vanhyprarch-update").symlink_to(self.root / "usr")
        with self.assertRaisesRegex(UpdateError, "unsafe staging directory"):
            self.driver.apply(self.target_json, self.target_archive)
        self.assertIsNone(self.driver.journal.inspect())


class AuthorityInvocationTests(DriverFixture):
    def test_target_authority_commands_and_user_boundary(self) -> None:
        runner = AuthorityRunner()
        bundle = Bundle(Path("/var/lib/vanhyprarch-update/staging/digest"),
                        Path("/var/lib/vanhyprarch-update/staging/digest/source/target"),
                        Path("/metadata"), Path("/artifact"), self.target, b"metadata")
        completed = SimpleNamespace(returncode=0, stdout="planned\n", stderr="")
        with mock.patch("install.release_update.subprocess.run", return_value=completed) as call:
            runner.invoke("system-integration", "plan", bundle, self.user)
            command = call.call_args.args[0]
            self.assertEqual(command[1], str(bundle.tree / "install/system_integration.py"))
            self.assertIn("upgrade", command)
            self.assertIn(self.user.name, command)
            self.assertNotIn("user", call.call_args.kwargs)
        with (mock.patch.object(runner, "_user_environment", return_value={"HOME": str(self.user.home)}),
              mock.patch("install.release_update.subprocess.run", return_value=completed) as call):
            runner.invoke("managed-deployment", "apply", bundle, self.user)
            command = call.call_args.args[0]
            self.assertIn("update", command)
            self.assertEqual(call.call_args.kwargs["user"], self.user.uid)
            self.assertEqual(call.call_args.kwargs["group"], self.user.gid)
            runner.invoke("create-once", "apply", bundle, self.user)
            command = call.call_args.args[0]
            self.assertIn("initialize", command)
            self.assertIn("upgrade", command)
            self.assertEqual(call.call_args.kwargs["user"], self.user.uid)


class IdentityUpgradeTests(DriverFixture):
    def test_exact_newer_target_replaces_source(self) -> None:
        identity = self.driver.identity
        self.assertEqual(identity.upgrade_commit(self.source, self.target_json.read_bytes()), self.target)
        self.assertEqual(self.identity_path.read_bytes(), self.target_json.read_bytes())
        self.assertEqual(stat.S_IMODE(self.identity_path.stat().st_mode), 0o644)

    def test_source_mismatch_same_version_downgrade_and_malformed_target_block(self) -> None:
        identity = self.driver.identity
        wrong = copy.deepcopy(self.source)
        wrong["commit"] = "f" * 40
        with self.assertRaises(IdentityError):
            identity.upgrade_commit(wrong, self.target_json.read_bytes())
        with self.assertRaises(IdentityError):
            identity.upgrade_commit(self.source, contract.metadata_bytes(self.source))
        older = copy.deepcopy(self.source)
        older["version"] = "v0.9.0"
        older["channel"] = "stable"
        older["artifact"]["name"] = contract.artifact_name("v0.9.0")
        with self.assertRaises(IdentityError):
            identity.upgrade_commit(self.source, contract.metadata_bytes(older))
        with self.assertRaises(contract.ReleaseError):
            identity.upgrade_commit(self.source, b"{}")
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))

    def test_unsafe_identity_and_write_failure_leave_source(self) -> None:
        identity = self.driver.identity
        before = self.identity_path.read_bytes()
        identity.fsync = mock.Mock(side_effect=OSError("fsync failed"))
        with self.assertRaisesRegex(OSError, "fsync failed"):
            identity.upgrade_commit(self.source, self.target_json.read_bytes())
        self.assertEqual(self.identity_path.read_bytes(), before)
        identity.fsync = os.fsync
        self.identity_path.unlink()
        self.identity_path.symlink_to(self.target_json)
        with self.assertRaises(IdentityError):
            identity.upgrade_commit(self.source, self.target_json.read_bytes())

    def test_preimage_change_blocks_atomic_upgrade(self) -> None:
        identity = self.driver.identity
        real_validate = identity.validate
        changed = copy.deepcopy(self.source)
        changed["commit"] = "f" * 40
        calls = 0

        def changing_validate(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.identity_path.write_bytes(contract.metadata_bytes(changed))
            return real_validate(*args, **kwargs)

        with mock.patch.object(identity, "validate", side_effect=changing_validate):
            with self.assertRaisesRegex(IdentityError, "changed before upgrade commit"):
                identity.upgrade_commit(self.source, self.target_json.read_bytes())
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(changed))

    def test_post_replace_fsync_failure_never_reports_success(self) -> None:
        identity = self.driver.identity
        real_fsync = os.fsync
        calls = 0

        def failing_fsync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory fsync failed")
            return real_fsync(descriptor)

        identity.fsync = failing_fsync
        with self.assertRaisesRegex(OSError, "directory fsync failed"):
            identity.upgrade_commit(self.source, self.target_json.read_bytes())
        self.assertEqual(self.identity_path.read_bytes(), self.target_json.read_bytes())


if __name__ == "__main__":
    unittest.main()
