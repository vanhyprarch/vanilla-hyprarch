#!/usr/bin/env python3
"""Disposable-root tests for the installed release commit marker."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_identity_under_test", PROJECT / "install/release_identity.py"
)
assert SPEC is not None and SPEC.loader is not None
IDENTITY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = IDENTITY
SPEC.loader.exec_module(IDENTITY)
CONTRACT = IDENTITY.contract

DECLARATION = (PROJECT / "release/release.toml").read_bytes()


class InstalledReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temporary.name)
        cls.repo = cls.base / "source"
        cls.repo.mkdir()
        subprocess.run(["git", "-C", str(cls.repo), "init", "-q"], check=True)
        for name in CONTRACT.REQUIRED_FILES:
            target = cls.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(DECLARATION if name == "release/release.toml"
                               else f"fixture {name}\n".encode())
        (cls.repo / "install/bootstrap").chmod(0o755)
        subprocess.run(["git", "-C", str(cls.repo), "add", "."], check=True)
        environment = dict(os.environ, GIT_AUTHOR_DATE="1700000000 +0000",
                           GIT_COMMITTER_DATE="1700000000 +0000")
        subprocess.run(["git", "-C", str(cls.repo), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                        "release fixture"], env=environment, check=True)
        commit = subprocess.check_output(
            ["git", "-C", str(cls.repo), "rev-parse", "HEAD"], text=True).strip()
        cls.bundle = cls.base / "bundle"
        cls.bundle.mkdir()
        cls.metadata, cls.artifact = CONTRACT.build(cls.repo, commit, cls.bundle)
        CONTRACT.verify(cls.metadata, cls.artifact)
        cls.extracted = cls.base / "extracted"
        cls.extracted.mkdir()
        with tarfile.open(cls.artifact, "r:gz") as archive:
            archive.extractall(cls.extracted, filter="data")
        cls.record = CONTRACT.parse_metadata(cls.metadata.read_bytes())
        cls.source_root = cls.extracted / CONTRACT.archive_root(cls.record["version"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        self.temporary_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_root.cleanup)
        self.root = Path(self.temporary_root.name)
        (self.root / "usr/share").mkdir(parents=True)
        self.identity = IDENTITY.InstalledReleaseIdentity(
            self.root, uid=os.getuid(), gid=os.getgid()
        )

    def commit(self) -> dict[str, object]:
        return self.identity.commit(self.metadata, self.artifact, self.source_root)

    def write_record(self, value: dict[str, object] | bytes) -> None:
        self.identity.directory.mkdir(exist_ok=True)
        data = value if isinstance(value, bytes) else CONTRACT.metadata_bytes(value)
        self.identity.path.write_bytes(data)
        self.identity.path.chmod(0o644)

    def test_fresh_commit_copies_exact_verified_metadata(self) -> None:
        self.assertIsNone(self.identity.validate(allow_absent=True))
        self.assertEqual(self.identity.preflight(self.metadata, self.artifact,
                                                 self.source_root), self.record)
        committed = self.commit()
        self.assertEqual(committed, self.record)
        self.assertEqual(self.identity.path.read_bytes(), self.metadata.read_bytes())
        self.assertEqual(self.identity.path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.identity.path.stat().st_uid, os.getuid())
        self.assertEqual(self.identity.path.stat().st_gid, os.getgid())
        self.assertEqual(self.identity.validate(), self.record)

    def test_record_is_offline_and_source_independent(self) -> None:
        self.commit()
        with mock.patch.object(CONTRACT, "verify", side_effect=AssertionError("network/source")):
            self.assertEqual(self.identity.validate(), self.record)

    def test_development_absence_is_explicit(self) -> None:
        self.assertIsNone(self.identity.validate(allow_absent=True))
        with self.assertRaisesRegex(IDENTITY.IdentityError, "absent"):
            self.identity.validate()
        self.assertFalse(self.identity.path.exists())

    def test_existing_record_is_a_fresh_install_conflict(self) -> None:
        self.write_record(self.metadata.read_bytes())
        with self.assertRaisesRegex(IDENTITY.IdentityError, "already exists"):
            self.identity.preflight(self.metadata, self.artifact, self.source_root)
        with self.assertRaisesRegex(IDENTITY.IdentityError, "already exists"):
            self.commit()
        self.assertEqual(self.identity.path.read_bytes(), self.metadata.read_bytes())

    def test_existing_symlink_is_never_followed(self) -> None:
        self.identity.directory.mkdir()
        outside = self.root / "outside"
        outside.write_text("sentinel", encoding="utf-8")
        self.identity.path.symlink_to(outside)
        with self.assertRaises(IDENTITY.IdentityError):
            self.identity.validate()
        with self.assertRaises(IDENTITY.IdentityError):
            self.commit()
        self.assertEqual(outside.read_text(encoding="utf-8"), "sentinel")

    def test_unsafe_parent_is_refused(self) -> None:
        self.identity.directory.mkdir()
        self.identity.directory.chmod(0o777)
        with self.assertRaisesRegex(IDENTITY.IdentityError, "writable"):
            self.identity.validate(allow_absent=True)
        with self.assertRaisesRegex(IDENTITY.IdentityError, "writable"):
            self.commit()

    def test_symlinked_parent_is_refused(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        self.identity.directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(IDENTITY.IdentityError, "unsafe directory"):
            self.identity.validate(allow_absent=True)

    def test_wrong_mode_and_owner_are_refused(self) -> None:
        self.write_record(self.metadata.read_bytes())
        self.identity.path.chmod(0o600)
        with self.assertRaisesRegex(IDENTITY.IdentityError, "mode"):
            self.identity.validate()
        self.identity.path.chmod(0o644)
        original = Path.lstat

        def wrong_owner(path: Path) -> os.stat_result:
            result = original(path)
            if path == self.identity.path:
                fields = list(result)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return result

        with mock.patch.object(Path, "lstat", wrong_owner):
            with self.assertRaisesRegex(IDENTITY.IdentityError, "owner"):
                self.identity.validate()

    def test_malformed_record_and_duplicate_keys_fail(self) -> None:
        for data in (b"invalid", b'{"schema":1,"schema":1}'):
            with self.subTest(data=data):
                self.write_record(data)
                with self.assertRaises(CONTRACT.ReleaseError):
                    self.identity.validate()

    def test_invalid_identity_fields_fail(self) -> None:
        alternate_version = (
            self.record["version"] + "-rc1"
            if self.record["channel"] == "stable"
            else self.record["version"].split("-rc", 1)[0]
        )
        alternate_channel = (
            "candidate" if self.record["channel"] == "stable" else "stable"
        )
        changes = (
            {"version": alternate_version}, {"channel": alternate_channel},
            {"architecture": "aarch64"}, {"schema": 2},
            {"update_protocol": 2}, {"migration_level": -1},
            {"minimum_migration_level": self.record["migration_level"] + 1},
            {"artifact": {**self.record["artifact"], "sha256": "bad"}},
            {"artifact": {**self.record["artifact"], "name": "wrong.tar.gz"}},
            {"artifact": {**self.record["artifact"], "size": 0}},
        )
        for change in changes:
            with self.subTest(change=change):
                self.write_record({**self.record, **change})
                with self.assertRaises(CONTRACT.ReleaseError):
                    self.identity.validate()

    def test_metadata_mismatch_and_source_mismatch_fail_before_commit(self) -> None:
        changed = self.root / "release.json"
        changed.write_bytes(CONTRACT.metadata_bytes({**self.record,
                                                      "summary": "Other summary."}))
        with self.assertRaises(CONTRACT.ReleaseError):
            self.identity.commit(changed, self.artifact, self.source_root)
        self.assertFalse(self.identity.path.exists())
        source = self.source_root / "release/release.toml"
        original = source.read_bytes()
        try:
            declared = CONTRACT.parse_declaration(original)
            changed = original.replace(
                f'summary = "{declared["summary"]}"'.encode(),
                b'summary = "Other summary."',
            )
            self.assertNotEqual(changed, original)
            source.write_bytes(changed)
            with self.assertRaisesRegex(IDENTITY.IdentityError, "source differs"):
                self.commit()
        finally:
            source.write_bytes(original)
        self.assertFalse(self.identity.path.exists())

    def test_write_and_publication_failures_leave_no_record(self) -> None:
        self.identity.directory.mkdir()
        with mock.patch.object(self.identity, "fsync", side_effect=OSError("fsync failed")):
            with self.assertRaises(OSError):
                self.commit()
        self.assertFalse(self.identity.path.exists())
        with mock.patch.object(IDENTITY.os, "link", side_effect=OSError("link failed")):
            with self.assertRaises(OSError):
                self.commit()
        self.assertFalse(self.identity.path.exists())

    def test_post_publish_fsync_failure_rolls_back_owned_file(self) -> None:
        self.identity.directory.mkdir()
        real_fsync = os.fsync
        calls = 0

        def fail_second(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory fsync failed")
            real_fsync(descriptor)

        self.identity.fsync = fail_second
        with self.assertRaises(OSError):
            self.commit()
        self.assertFalse(self.identity.path.exists())


if __name__ == "__main__":
    unittest.main()
