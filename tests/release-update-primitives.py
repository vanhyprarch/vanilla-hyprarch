#!/usr/bin/env python3
"""Isolated registry, migration, journal, and runtime-lock tests."""

from __future__ import annotations

import copy
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "install"))
from release_migrations import MigrationError, MigrationRegistry, MigrationRunner  # noqa: E402
from update_journal import (  # noqa: E402
    JOURNAL_RELATIVE, LOCK_RELATIVE, JournalError, UpdateJournal, parse_record,
)
from release import build as contract  # noqa: E402


def metadata(version: str, *, level: int, minimum_level: int = 0,
             minimum_version: str | None = None, marker: str = "2") -> dict:
    value = {
        "schema": 1, "version": version,
        "channel": "candidate" if "-rc" in version else "stable",
        "commit": marker * 40, "architecture": "x86_64", "update_protocol": 1,
        "minimum_installed_version": minimum_version,
        "minimum_migration_level": minimum_level, "migration_level": level,
        "artifact": {"name": contract.artifact_name(version), "size": 123,
                     "sha256": marker * 64},
        "summary": "Fixture release",
    }
    return contract.parse_metadata(contract.metadata_bytes(value))


SOURCE = metadata("v1.0.0-rc1", level=0, marker="1")


def declaration(value: dict) -> bytes:
    fields = [
        f'schema = {value["schema"]}', f'version = "{value["version"]}"',
        f'channel = "{value["channel"]}"',
        f'architecture = "{value["architecture"]}"',
        f'update_protocol = {value["update_protocol"]}',
        f'minimum_migration_level = {value["minimum_migration_level"]}',
        f'migration_level = {value["migration_level"]}',
        f'summary = "{value["summary"]}"',
    ]
    if value["minimum_installed_version"] is not None:
        fields.append(f'minimum_installed_version = "{value["minimum_installed_version"]}"')
    return ("\n".join(fields) + "\n").encode()


def migration_code(identifier: int, *, apply_failure: bool = False,
                   validate_failure: bool = False, user_conflict: bool = False) -> str:
    return f'''from pathlib import Path

OLD = "{identifier - 1}"
NEW = "{identifier}"

def _state(ctx):
    path = ctx.system_root / "migration-state.txt"
    return path, path.read_text() if path.exists() else "0"

def plan(ctx):
    if not (ctx.release_root / "release/release.toml").is_file():
        raise ValueError("target release tree is unavailable")
    path, current = _state(ctx)
    if {user_conflict!r} and (ctx.system_root / "user-owned.txt").exists():
        raise ValueError("USER_OWNED conflict: preserve user bytes")
    if current not in {{OLD, NEW}}:
        raise ValueError("foreign migration state")
    return ["migration {identifier:04d}: " + ("preserve" if current == NEW else "write target")]

def apply(ctx):
    if {apply_failure!r}:
        raise ValueError("fixture apply failed")
    path, current = _state(ctx)
    if current not in {{OLD, NEW}}:
        raise ValueError("foreign migration state")
    with (ctx.system_root / "apply-trace.txt").open("a") as trace:
        trace.write("{identifier}\\n")
    if current != NEW:
        path.write_text(NEW)

def validate(ctx):
    return not {validate_failure!r} and _state(ctx)[1] == NEW
'''


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "system"
        self.root.mkdir()
        identity = self.root / "usr/share/vanhyprarch"
        identity.mkdir(parents=True)
        self.identity_path = identity / "release.json"
        self.identity_path.write_bytes(contract.metadata_bytes(SOURCE))
        self.identity_path.chmod(0o644)
        self.release = self.base / "release-tree"
        (self.release / "release/migrations").mkdir(parents=True)
        self.journal = UpdateJournal(self.root, uid=os.getuid(), gid=os.getgid())

    def target(self, level: int, *, minimum_level: int = 0) -> dict:
        return metadata("v1.0.0-rc2", level=level, minimum_level=minimum_level,
                        minimum_version=SOURCE["version"])

    def registry(self, target: dict, ids: list[int], *, entries: list[dict] | None = None,
                 code_options: dict[int, dict] | None = None) -> MigrationRegistry:
        (self.release / "release/release.toml").write_bytes(declaration(target))
        if entries is None:
            entries = [{"id": identifier, "name": f"fixture-{identifier}",
                        "path": f"release/migrations/{identifier:04d}-fixture-{identifier}.py",
                        "scope": "BACKEND_OWNED fixture state", "touches_user_state": False}
                       for identifier in ids]
        lines = ["schema = 1"]
        for entry in entries:
            lines.append("\n[[migration]]")
            for key, value in entry.items():
                if isinstance(value, bool):
                    lines.append(f"{key} = {str(value).lower()}")
                elif isinstance(value, int):
                    lines.append(f"{key} = {value}")
                else:
                    lines.append(f"{key} = {json.dumps(value)}")
        (self.release / "release/migrations/registry.toml").write_text("\n".join(lines) + "\n")
        for identifier in ids:
            name = next((entry["path"] for entry in entries if entry["id"] == identifier
                         and entry["path"].startswith("release/migrations/")), None)
            if name is not None:
                path = self.release / name
                path.write_text(migration_code(identifier,
                                               **(code_options or {}).get(identifier, {})))
        return MigrationRegistry(self.release, target=target)

    def start(self, target: dict) -> None:
        with self.journal.lock.acquire():
            self.journal.begin(SOURCE, target)

    def runner(self, target: dict, registry: MigrationRegistry) -> MigrationRunner:
        return MigrationRunner(registry, self.journal, SOURCE, target)


class RegistryTests(Fixture):
    def test_production_rc2_registry_contains_first_migration(self) -> None:
        registry = MigrationRegistry(PROJECT)
        self.assertEqual(registry.declaration["version"], "v1.0.0-rc2")
        self.assertEqual(registry.declaration["minimum_installed_version"], "v1.0.0-rc1")
        self.assertEqual(registry.declaration["migration_level"], 1)
        self.assertEqual(registry.declaration["minimum_migration_level"], 0)
        self.assertEqual(sorted(registry.entries), [1])
        self.assertEqual(
            registry.entries[1]["path"],
            "release/migrations/0001-update-bootstrap-state-v2.py",
        )
        self.assertFalse(registry.entries[1]["touches_user_state"])

    def test_empty_registry_requires_zero_migration_level(self) -> None:
        target = self.target(1, minimum_level=1)
        with self.assertRaisesRegex(MigrationError, "declaration mismatch"):
            self.registry(target, [])

    def test_valid_one_and_three_step_chains(self) -> None:
        for count in (1, 3):
            with self.subTest(count=count):
                target = self.target(count)
                registry = self.registry(target, list(range(1, count + 1)))
                self.assertEqual(registry.range_from(0), list(range(1, count + 1)))
                for path in (self.release / "release/migrations").glob("*.py"):
                    path.unlink()

    def test_supported_floor_needs_only_the_remaining_chain(self) -> None:
        target = self.target(3, minimum_level=1)
        registry = self.registry(target, [2, 3])
        self.assertEqual(registry.range_from(1), [2, 3])
        self.assertEqual(registry.range_from(2), [3])
        with self.assertRaisesRegex(MigrationError, "support range"):
            registry.range_from(0)

    def test_duplicate_gap_and_wrong_order_fail(self) -> None:
        target = self.target(3)
        base = [{"id": number, "name": f"fixture-{number}",
                 "path": f"release/migrations/{number:04d}-fixture-{number}.py",
                 "scope": "BACKEND_OWNED", "touches_user_state": False}
                for number in (1, 2, 3)]
        for entries, message in (([base[0], base[0]], "duplicate"),
                                 ([base[0], base[2]], "gap"),
                                 ([base[1], base[0], base[2]], "wrong order")):
            with self.subTest(message=message):
                with self.assertRaises(MigrationError):
                    self.registry(target, [1, 2, 3], entries=entries)
                for path in (self.release / "release/migrations").glob("*.py"):
                    path.unlink()

    def test_bad_path_missing_file_and_unregistered_file_fail(self) -> None:
        target = self.target(1)
        entry = {"id": 1, "name": "fixture-1", "path": "../outside.py",
                 "scope": "BACKEND_OWNED", "touches_user_state": False}
        with self.assertRaisesRegex(MigrationError, "path"):
            self.registry(target, [1], entries=[entry])
        self.registry(target, [1])
        implementation = self.release / "release/migrations/0001-fixture-1.py"
        implementation.unlink()
        with self.assertRaisesRegex(MigrationError, "missing"):
            MigrationRegistry(self.release)
        implementation.write_text(migration_code(1))
        (self.release / "release/migrations/extra.py").write_text("pass\n")
        with self.assertRaisesRegex(MigrationError, "unregistered"):
            MigrationRegistry(self.release)

    def test_malformed_registry_and_declaration_mismatch_fail(self) -> None:
        target = self.target(0)
        self.registry(target, [])
        registry_file = self.release / "release/migrations/registry.toml"
        for contents in ("schema = 2\n", "schema = true\n", "schema = 1\nunknown = 1\n",
                         "schema = 1\nschema = 1\n"):
            registry_file.write_text(contents)
            with self.assertRaises(MigrationError):
                MigrationRegistry(self.release)
        registry_file.write_text("schema = 1\n")
        altered = copy.deepcopy(target)
        altered["migration_level"] = 1
        with self.assertRaises(MigrationError):
            MigrationRegistry(self.release, target=altered)
        bad = declaration(target).replace(b"minimum_migration_level = 0",
                                          b"minimum_migration_level = 1")
        (self.release / "release/release.toml").write_bytes(bad)
        with self.assertRaises(MigrationError):
            MigrationRegistry(self.release)

    def test_symlink_and_unsafe_implementation_fail(self) -> None:
        target = self.target(1)
        self.registry(target, [1])
        implementation = self.release / "release/migrations/0001-fixture-1.py"
        implementation.chmod(0o666)
        with self.assertRaisesRegex(MigrationError, "unsafe"):
            MigrationRegistry(self.release)
        implementation.unlink()
        implementation.symlink_to(self.release / "release/release.toml")
        with self.assertRaisesRegex(MigrationError, "symlink"):
            MigrationRegistry(self.release)
        implementation.unlink()
        os.mkfifo(implementation)
        with self.assertRaisesRegex(MigrationError, "unsafe"):
            MigrationRegistry(self.release)

    def test_user_state_policy_must_be_explicit(self) -> None:
        target = self.target(1)
        entry = {"id": 1, "name": "fixture-1",
                 "path": "release/migrations/0001-fixture-1.py",
                 "scope": "USER_OWNED fixture", "touches_user_state": True}
        with self.assertRaisesRegex(MigrationError, "preservation"):
            self.registry(target, [1], entries=[entry])


class MigrationExecutionTests(Fixture):
    def test_zero_level_target_runs_no_historical_migrations(self) -> None:
        target = self.target(0)
        registry = self.registry(target, [])
        self.start(target)
        before = self.identity_path.read_bytes()
        with self.journal.lock.acquire():
            self.assertEqual(self.runner(target, registry).run(), [])
            self.runner(target, registry).validate_level()
        self.assertEqual(self.identity_path.read_bytes(), before)

    def test_plan_is_read_only_then_apply_validate_and_rerun(self) -> None:
        target = self.target(1)
        registry = self.registry(target, [1])
        self.start(target)
        runner = self.runner(target, registry)
        before = self.journal.path.read_bytes()
        self.assertEqual(runner.plan()[0], 1)
        self.assertFalse((self.root / "migration-state.txt").exists())
        self.assertEqual(self.journal.path.read_bytes(), before)
        with self.journal.lock.acquire():
            self.assertEqual(runner.run(), [1])
            runner.validate_level()
            self.assertEqual(runner.run(), [1])
        self.assertEqual((self.root / "apply-trace.txt").read_text(), "1\n")
        self.assertEqual(self.journal.inspect()["completed_migrations"], [1])
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(SOURCE))

    def test_apply_failure_and_validate_failure_remain_pending(self) -> None:
        for option in ("apply_failure", "validate_failure"):
            with self.subTest(option=option):
                target = self.target(1)
                registry = self.registry(target, [1], code_options={1: {option: True}})
                if self.journal.inspect() is None:
                    self.start(target)
                runner = self.runner(target, registry)
                with self.journal.lock.acquire():
                    with self.assertRaises((ValueError, MigrationError)):
                        runner.run()
                self.assertEqual(self.journal.inspect()["pending_migration"], 1)
                self.assertEqual(self.journal.inspect()["completed_migrations"], [])
                self.journal.path.unlink()
                (self.root / "migration-state.txt").unlink(missing_ok=True)
                (self.root / "apply-trace.txt").unlink(missing_ok=True)

    def test_resume_pending_valid_state_skips_apply(self) -> None:
        target = self.target(1)
        registry = self.registry(target, [1])
        self.start(target)
        with self.journal.lock.acquire():
            self.journal.checkpoint(SOURCE, target, "migrations")
            self.journal.pending(SOURCE, target, 1)
        (self.root / "migration-state.txt").write_text("1")
        runner = self.runner(target, registry)
        with self.journal.lock.acquire():
            self.assertEqual(runner.run(), [1])
        self.assertFalse((self.root / "apply-trace.txt").exists())

    def test_resume_pending_old_state_safely_reapplies(self) -> None:
        target = self.target(1)
        registry = self.registry(target, [1])
        self.start(target)
        with self.journal.lock.acquire():
            self.journal.checkpoint(SOURCE, target, "migrations")
            self.journal.pending(SOURCE, target, 1)
        runner = self.runner(target, registry)
        with self.journal.lock.acquire():
            self.assertEqual(runner.run(), [1])
        self.assertEqual((self.root / "apply-trace.txt").read_text(), "1\n")

    def test_three_migrations_run_in_order_and_resume_at_next(self) -> None:
        target = self.target(3)
        registry = self.registry(target, [1, 2, 3])
        self.start(target)
        runner = self.runner(target, registry)
        with self.journal.lock.acquire():
            self.journal.checkpoint(SOURCE, target, "migrations")
            self.journal.pending(SOURCE, target, 1)
            (self.root / "migration-state.txt").write_text("1")
            self.journal.complete(SOURCE, target, 1)
        self.assertEqual(runner.plan()[0], 2)
        with self.journal.lock.acquire():
            self.assertEqual(runner.run(), [1, 2, 3])
            runner.validate_level()
        self.assertEqual((self.root / "apply-trace.txt").read_text(), "2\n3\n")
        self.assertEqual((self.root / "migration-state.txt").read_text(), "3")

    def test_completed_migrations_are_read_only_after_later_checkpoint(self) -> None:
        target = self.target(1)
        registry = self.registry(target, [1])
        self.start(target)
        runner = self.runner(target, registry)
        with self.journal.lock.acquire():
            runner.run()
            self.journal.checkpoint(SOURCE, target, "managed-deployment")
            before = (self.journal.path.read_bytes(),
                      (self.root / "apply-trace.txt").read_bytes())
            self.assertEqual(runner.run(), [1])
            self.assertEqual((self.journal.path.read_bytes(),
                              (self.root / "apply-trace.txt").read_bytes()), before)

    def test_stage_checkpoint_does_not_assume_migration_order(self) -> None:
        target = self.target(1)
        registry = self.registry(target, [1])
        self.start(target)
        with self.journal.lock.acquire():
            self.journal.checkpoint(SOURCE, target, "system-integration")
            self.assertEqual(self.runner(target, registry).run(), [1])
            self.assertEqual(self.journal.inspect()["checkpoint"], "migrations")

    def test_user_owned_conflict_fails_before_pending_or_mutation(self) -> None:
        target = self.target(1)
        entry = {"id": 1, "name": "fixture-1",
                 "path": "release/migrations/0001-fixture-1.py",
                 "scope": "USER_OWNED fixture", "touches_user_state": True,
                 "user_state_preservation": "Never rewrite user-owned bytes",
                 "user_state_conflict": "Fail if the user-owned path exists"}
        registry = self.registry(target, [1], entries=[entry],
                                 code_options={1: {"user_conflict": True}})
        self.start(target)
        user_path = self.root / "user-owned.txt"
        user_path.write_bytes(b"personal bytes\n")
        with self.journal.lock.acquire():
            with self.assertRaisesRegex(ValueError, "USER_OWNED conflict"):
                self.runner(target, registry).run()
        self.assertEqual(user_path.read_bytes(), b"personal bytes\n")
        self.assertIsNone(self.journal.inspect()["pending_migration"])


class JournalTests(Fixture):
    def test_initialize_exact_bytes_modes_and_no_identity_mutation(self) -> None:
        target = self.target(1)
        before = self.identity_path.read_bytes()
        with self.journal.lock.acquire():
            value = self.journal.begin(SOURCE, target)
        self.assertEqual(self.journal.path.read_bytes(),
                         (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
        self.assertEqual(self.journal.inspect(), value)
        self.assertEqual(self.identity_path.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(self.journal.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.journal.path.parent.stat().st_mode), 0o700)
        self.assertEqual(self.journal.path.stat().st_uid, os.getuid())
        self.assertEqual(self.journal.path.stat().st_gid, os.getgid())
        self.assertEqual(value["source"]["artifact_sha256"], SOURCE["artifact"]["sha256"])
        self.assertEqual(value["target"]["artifact_sha256"], target["artifact"]["sha256"])

    def test_explicit_resume_only_for_exact_source_target(self) -> None:
        target = self.target(1)
        self.start(target)
        other = metadata("v1.0.0-rc3", level=1, minimum_version=SOURCE["version"], marker="3")
        with self.journal.lock.acquire():
            with self.assertRaisesRegex(JournalError, "explicit resume"):
                self.journal.begin(SOURCE, target)
            self.assertEqual(self.journal.begin(SOURCE, target, resume=True), self.journal.inspect())
            with self.assertRaisesRegex(JournalError, "different source or target"):
                self.journal.begin(SOURCE, other, resume=True)
            other_digest = copy.deepcopy(target)
            other_digest["artifact"]["sha256"] = "5" * 64
            with self.assertRaisesRegex(JournalError, "different source or target"):
                self.journal.begin(SOURCE, other_digest, resume=True)
            bad_source = copy.deepcopy(SOURCE)
            bad_source["commit"] = "4" * 40
            with self.assertRaisesRegex(JournalError, "installed release"):
                self.journal.begin(bad_source, target, resume=True)

    def test_target_user_is_durable_transaction_identity(self) -> None:
        target = self.target(1)
        with self.journal.lock.acquire():
            record = self.journal.begin(SOURCE, target, target_user="alice")
            self.assertEqual(record["target_user"], "alice")
            with self.assertRaisesRegex(JournalError, "different target user"):
                self.journal.begin(SOURCE, target, resume=True, target_user="bob")
            self.assertEqual(self.journal.begin(SOURCE, target, resume=True,
                                                target_user="alice"), record)

    def test_source_mismatch_and_incompatible_target_fail_before_creation(self) -> None:
        target = self.target(1)
        bad_source = copy.deepcopy(SOURCE)
        bad_source["artifact"]["sha256"] = "4" * 64
        with self.journal.lock.acquire():
            with self.assertRaises(JournalError):
                self.journal.begin(bad_source, target)
            below = self.target(1, minimum_level=1)
            with self.assertRaisesRegex(JournalError, "support range"):
                self.journal.begin(SOURCE, below)
        self.assertIsNone(self.journal.inspect())

    def test_incomplete_journal_rejects_changed_installed_source(self) -> None:
        target = self.target(1)
        self.start(target)
        changed = copy.deepcopy(SOURCE)
        changed["commit"] = "4" * 40
        self.identity_path.write_bytes(contract.metadata_bytes(changed))
        with self.assertRaisesRegex(JournalError, "installed source changed"):
            self.journal.bound(SOURCE, target)

    def test_malformed_duplicate_symlink_mode_and_parent_fail_closed(self) -> None:
        target = self.target(1)
        self.start(target)
        for data in (b"{", b'{"schema":1,"schema":1}'):
            self.journal.path.write_bytes(data)
            with self.assertRaises(JournalError):
                self.journal.inspect()
        self.journal.path.unlink()
        self.journal.path.symlink_to(self.identity_path)
        with self.assertRaisesRegex(JournalError, "unsafe root-owned file"):
            self.journal.inspect()
        self.journal.path.unlink()
        self.journal.path.write_text("{}")
        self.journal.path.chmod(0o644)
        with self.assertRaisesRegex(JournalError, "unsafe root-owned file"):
            self.journal.inspect()
        self.journal.path.unlink()
        self.journal.path.parent.chmod(0o777)
        with self.assertRaisesRegex(JournalError, "unsafe root-owned directory"):
            self.journal.inspect()

    def test_malformed_active_journal_is_never_replaced_on_begin(self) -> None:
        target = self.target(1)
        self.start(target)
        self.journal.path.write_bytes(b"{bad")
        before = self.journal.path.read_bytes()
        with self.journal.lock.acquire():
            with self.assertRaises(JournalError):
                self.journal.begin(SOURCE, target, resume=True)
        self.assertEqual(self.journal.path.read_bytes(), before)

    def test_wrong_owner_and_publication_failure_fail_closed(self) -> None:
        target = self.target(1)
        self.start(target)
        original = self.journal.path.lstat()
        real_lstat = Path.lstat

        def wrong_owner(path: Path, *args, **kwargs):
            result = real_lstat(path, *args, **kwargs)
            if path == self.journal.path:
                values = list(result)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return result

        with mock.patch.object(Path, "lstat", wrong_owner):
            with self.assertRaisesRegex(JournalError, "unsafe root-owned file"):
                self.journal.inspect()
        self.assertEqual(self.journal.path.lstat().st_ino, original.st_ino)
        before = self.journal.path.read_bytes()
        with self.journal.lock.acquire():
            self.journal.fsync = mock.Mock(side_effect=OSError("fsync failed"))
            with self.assertRaisesRegex(OSError, "fsync failed"):
                self.journal.checkpoint(SOURCE, target, "system-integration")
        self.journal.fsync = os.fsync
        self.assertEqual(self.journal.path.read_bytes(), before)

    def test_initial_publication_failure_does_not_claim_journal(self) -> None:
        target = self.target(1)
        with self.journal.lock.acquire():
            with mock.patch("update_journal.os.link", side_effect=OSError("link failed")):
                with self.assertRaisesRegex(OSError, "link failed"):
                    self.journal.begin(SOURCE, target)
        self.assertIsNone(self.journal.inspect())
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(SOURCE))

    def test_pending_completion_phase_and_clear_require_exact_commit(self) -> None:
        target = self.target(1)
        self.start(target)
        with self.journal.lock.acquire():
            with self.assertRaises(JournalError):
                self.journal.clear_after_commit(SOURCE, target)
            self.journal.checkpoint(SOURCE, target, "migrations")
            self.journal.pending(SOURCE, target, 1)
            self.assertEqual(self.journal.inspect()["pending_migration"], 1)
            self.journal.complete(SOURCE, target, 1)
            self.assertEqual(self.journal.inspect()["completed_migrations"], [1])
            self.journal.checkpoint(SOURCE, target, "final-validation")
            self.journal.phase(SOURCE, target, "validating")
            self.journal.phase(SOURCE, target, "ready-for-final-commit")
            with self.assertRaisesRegex(JournalError, "not committed"):
                self.journal.clear_after_commit(SOURCE, target)
        self.identity_path.write_bytes(contract.metadata_bytes(target))
        with self.journal.lock.acquire():
            self.journal.clear_after_commit(SOURCE, target)
        self.assertIsNone(self.journal.inspect())

    def test_parse_rejects_bad_schema_and_progress(self) -> None:
        target = self.target(1)
        self.start(target)
        value = self.journal.inspect()
        for change in ({"schema": True}, {"phase": "committed"},
                       {"phase": "validating"},
                       {"completed_migrations": [1, 1]},
                       {"pending_migration": 2}, {"checkpoint": "other"}):
            with self.subTest(change=change):
                bad = {**value, **change}
                with self.assertRaises(JournalError):
                    parse_record(json.dumps(bad).encode())
        for field, replacement in (("commit", "bad"), ("artifact_sha256", "A" * 64)):
            bad = copy.deepcopy(value)
            bad["target"][field] = replacement
            with self.assertRaises(JournalError):
                parse_record(json.dumps(bad).encode())
        bad = copy.deepcopy(value)
        bad["target"]["update_protocol"] = 2
        with self.assertRaises(JournalError):
            parse_record(json.dumps(bad).encode())


class LockTests(Fixture):
    def test_exclusive_lock_and_existing_inode(self) -> None:
        second = UpdateJournal(self.root, uid=os.getuid(), gid=os.getgid())
        with self.journal.lock.acquire():
            inode = self.journal.lock.path.stat().st_ino
            with self.assertRaisesRegex(JournalError, "another Vanilla update"):
                with second.lock.acquire():
                    self.fail("second holder acquired update lock")
        with second.lock.acquire():
            self.assertEqual(second.lock.path.stat().st_ino, inode)
            self.assertEqual(stat.S_IMODE(second.lock.path.stat().st_mode), 0o600)

    def test_process_death_releases_lock_but_retains_journal(self) -> None:
        target = self.target(1)
        child = os.fork()
        if child == 0:
            with self.journal.lock.acquire():
                self.journal.begin(SOURCE, target)
                os._exit(0)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertIsNotNone(self.journal.inspect())
        resumed = UpdateJournal(self.root, uid=os.getuid(), gid=os.getgid())
        with resumed.lock.acquire():
            self.assertEqual(resumed.begin(SOURCE, target, resume=True), resumed.inspect())

    def test_unsafe_runtime_lock_fails_closed(self) -> None:
        with self.journal.lock.acquire():
            path = self.journal.lock.path
        path.chmod(0o644)
        with self.assertRaisesRegex(JournalError, "unsafe root-owned file"):
            with self.journal.lock.acquire():
                self.fail("unsafe runtime lock was accepted")
        path.unlink()
        path.symlink_to(self.identity_path)
        with self.assertRaisesRegex(JournalError, "unsafe root-owned file"):
            with self.journal.lock.acquire():
                self.fail("symlinked runtime lock was accepted")


if __name__ == "__main__":
    unittest.main()
