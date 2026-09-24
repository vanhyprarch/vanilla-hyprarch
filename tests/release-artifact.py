#!/usr/bin/env python3
"""Offline release contract, reproducibility, and hostile archive fixtures."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_build", PROJECT / "release/build.py")
assert SPEC is not None and SPEC.loader is not None
RELEASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RELEASE
SPEC.loader.exec_module(RELEASE)

DECLARATION = b'''schema = 1
version = "v1.0.0-rc1"
channel = "candidate"
architecture = "x86_64"
update_protocol = 1
minimum_migration_level = 0
migration_level = 0
summary = "First candidate."
'''


def git(repo: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(["git", "-C", str(repo), *arguments],
                            env=env, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def write_fixture(repo: Path) -> str:
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    for name in RELEASE.REQUIRED_FILES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(DECLARATION if name == "release/release.toml"
                         else f"fixture {name}\n".encode())
    command = repo / "install/bootstrap"
    command.chmod(0o755)
    git(repo, "add", ".")
    env = dict(os.environ, GIT_AUTHOR_DATE="1700000000 +0000",
               GIT_COMMITTER_DATE="1700000000 +0000")
    git(repo, "commit", "-qm", "fixture", env=env)
    return git(repo, "rev-parse", "HEAD")


def metadata_with(archive: Path, metadata: dict[str, object], output: Path) -> Path:
    updated = json.loads(json.dumps(metadata))
    data = archive.read_bytes()
    updated["artifact"]["size"] = len(data)
    updated["artifact"]["sha256"] = hashlib.sha256(data).hexdigest()
    output.write_bytes(RELEASE.metadata_bytes(updated))
    return output


class ReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temporary.name)
        cls.repo = cls.base / "repo"
        cls.repo.mkdir()
        cls.commit = write_fixture(cls.repo)
        cls.output = cls.base / "release"
        cls.output.mkdir()
        cls.metadata_path, cls.artifact_path = RELEASE.build(cls.repo, cls.commit,
                                                              cls.output)
        cls.metadata = RELEASE.parse_metadata(cls.metadata_path.read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.work = Path(self.scratch.name)

    def declaration(self, **changes: object) -> dict[str, object]:
        value = RELEASE.parse_declaration(DECLARATION)
        value.update(changes)
        return value

    def rejects_declaration(self, **changes: object) -> None:
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE._validate_common(self.declaration(**changes), metadata=False)

    def altered_archive(self, *, added: list[tarfile.TarInfo] | None = None,
                        replacements: dict[str, bytes] | None = None,
                        renames: dict[str, str] | None = None) -> tuple[Path, Path]:
        added = added or []
        replacements = replacements or {}
        renames = renames or {}
        archive_path = self.work / self.artifact_path.name
        with archive_path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|",
                                  format=tarfile.USTAR_FORMAT) as output:
                    with tarfile.open(self.artifact_path, "r:gz") as original:
                        for member in original:
                            if member.name in replacements:
                                data = replacements[member.name]
                            elif member.isfile():
                                source = original.extractfile(member)
                                assert source is not None
                                data = source.read()
                            else:
                                data = b""
                            member.name = renames.get(member.name, member.name)
                            if member.isfile():
                                member.size = len(data)
                            output.addfile(member, io.BytesIO(data) if member.isfile() else None)
                    for member in added:
                        output.addfile(member, io.BytesIO(b"x" * member.size)
                                if member.isfile() else None)
        meta_path = metadata_with(archive_path, self.metadata,
                                  self.work / "release.json")
        return meta_path, archive_path

    def member(self, name: str, kind: bytes = tarfile.REGTYPE,
               size: int = 1, mode: int = 0o644) -> tarfile.TarInfo:
        info = tarfile.TarInfo(name)
        info.type = kind
        info.size = size if kind == tarfile.REGTYPE else 0
        info.mode = mode
        info.mtime = 1700000000
        return info

    def reject_archive(self, **changes: object) -> None:
        meta, archive = self.altered_archive(**changes)
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.verify(meta, archive)

    def test_authored_declaration_current_values(self) -> None:
        current = RELEASE.parse_declaration((PROJECT / "release/release.toml").read_bytes())
        self.assertEqual(current["version"], "v1.0.0")
        self.assertEqual(current["channel"], "stable")
        self.assertEqual(current["minimum_installed_version"], "v1.0.0-rc1")
        self.assertEqual(current["minimum_migration_level"], 0)
        self.assertEqual(current["migration_level"], 1)
        self.assertEqual(current["summary"], "First stable release of Vanilla HyprArch.")

    def test_generated_metadata_exact_fields(self) -> None:
        self.assertEqual(set(self.metadata), RELEASE.METADATA_KEYS)
        self.assertIsNone(self.metadata["minimum_installed_version"])
        self.assertEqual(set(self.metadata["artifact"]), RELEASE.ARTIFACT_KEYS)
        self.assertEqual(self.metadata["artifact"]["name"], self.artifact_path.name)
        self.assertEqual(self.metadata["artifact"]["size"],
                         self.artifact_path.stat().st_size)

    def test_stable_and_explicit_minimum(self) -> None:
        value = self.declaration(version="v1.0.0", channel="stable",
                                 minimum_installed_version="v1.0.0-rc1")
        self.assertEqual(RELEASE._validate_common(value, metadata=False)["version"],
                         "v1.0.0")

    def test_version_grammar(self) -> None:
        for value in ("v1.0.0-rc1", "v1.0.0-rc2", "v1.0.0", "v1.0.1", "v1.1.0"):
            with self.subTest(value=value):
                RELEASE.version_tuple(value)
        for value in ("1.0.0", "v01.0.0", "v1.0", "v1.0.0-RC1",
                      "v1.0.0-rc01", "v1.0.0-beta1", "v1.0.0-rc0"):
            with self.subTest(value=value), self.assertRaises(RELEASE.ReleaseError):
                RELEASE.version_tuple(value)

    def test_bad_channel_version_pairs(self) -> None:
        self.rejects_declaration(channel="stable")
        self.rejects_declaration(version="v1.0.0", channel="candidate")

    def test_bad_migration_bounds_and_types(self) -> None:
        for change in ({"minimum_migration_level": 1}, {"migration_level": -1},
                       {"migration_level": True}, {"migration_level": "0"},
                       {"migration_level": RELEASE.MAX_MIGRATION_LEVEL + 1}):
            with self.subTest(change=change):
                self.rejects_declaration(**change)

    def test_minimum_installed_version_policy(self) -> None:
        self.rejects_declaration(minimum_installed_version="v1.0.1")
        self.rejects_declaration(minimum_installed_version="")
        self.rejects_declaration(minimum_installed_version=0)

    def test_malformed_types_and_unknown_fields(self) -> None:
        for change in ({"schema": True}, {"version": 1}, {"channel": 1},
                       {"summary": 1}, {"unexpected": "x"}):
            with self.subTest(change=change):
                self.rejects_declaration(**change)

    def test_unsupported_identity_and_summary_bounds(self) -> None:
        for change in ({"schema": 2}, {"update_protocol": 2},
                       {"architecture": "aarch64"}, {"summary": "x" * 161},
                       {"summary": "line\nbreak"}, {"summary": ""}):
            with self.subTest(change=change):
                self.rejects_declaration(**change)

    def test_declaration_duplicate_and_excess_bytes(self) -> None:
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.parse_declaration(DECLARATION + b"schema = 1\n")
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.parse_declaration(DECLARATION + b"#" * RELEASE.MAX_DECLARATION)

    def test_determinism_across_directories(self) -> None:
        second = self.work / "second"
        second.mkdir()
        third = self.work / "third"
        third.mkdir()
        m2, a2 = RELEASE.build(self.repo, self.commit, second)
        m3, a3 = RELEASE.build(self.repo, self.commit, third)
        self.assertEqual(self.artifact_path.read_bytes(), a2.read_bytes())
        self.assertEqual(a2.read_bytes(), a3.read_bytes())
        self.assertEqual(self.metadata_path.read_bytes(), m2.read_bytes())
        self.assertEqual(m2.read_bytes(), m3.read_bytes())
        self.assertEqual(self.metadata["artifact"]["sha256"],
                         hashlib.sha256(a2.read_bytes()).hexdigest())

    def test_dirty_and_untracked_bytes_not_in_artifact(self) -> None:
        tracked = self.repo / "install.sh"
        original = tracked.read_bytes()
        junk = self.repo / "untracked-secret.txt"
        try:
            tracked.write_bytes(b"dirty data never shipped\n")
            junk.write_bytes(b"untracked data never shipped\n")
            output = self.work / "dirty"
            output.mkdir()
            metadata, archive = RELEASE.build(self.repo, self.commit, output)
            self.assertEqual(archive.read_bytes(), self.artifact_path.read_bytes())
            self.assertEqual(metadata.read_bytes(), self.metadata_path.read_bytes())
        finally:
            tracked.write_bytes(original)
            junk.unlink(missing_ok=True)

    def test_commit_identity(self) -> None:
        self.assertEqual(self.metadata["commit"], self.commit)
        output = self.work / "bad"
        output.mkdir()
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.build(self.repo, "main", output)

    def test_publication_tag_checks(self) -> None:
        git(self.repo, "tag", "v1.0.0-rc1", self.commit)
        output = self.work / "tagged"
        output.mkdir()
        RELEASE.build(self.repo, self.commit, output, "v1.0.0-rc1")
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.build(self.repo, self.commit, output, "v1.0.0-rc2")
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.build(self.repo, self.commit, output, "v1.0.0")

    def test_tag_at_other_commit_rejected(self) -> None:
        (self.repo / "extra.txt").write_text("another commit\n")
        git(self.repo, "add", "extra.txt")
        env = dict(os.environ, GIT_AUTHOR_DATE="1700000001 +0000",
                   GIT_COMMITTER_DATE="1700000001 +0000")
        git(self.repo, "commit", "-qm", "other", env=env)
        newer = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "tag", "-f", "v1.0.0-rc1", newer)
        output = self.work / "wrong-target"
        output.mkdir()
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.build(self.repo, self.commit, output, "v1.0.0-rc1")

    def test_archive_root_modes_and_declaration(self) -> None:
        root = RELEASE.archive_root(self.metadata["version"])
        with tarfile.open(self.artifact_path, "r:gz") as bundle:
            members = bundle.getmembers()
            self.assertEqual(members[0].name, root)
            self.assertTrue(members[0].isdir())
            self.assertEqual(bundle.getmember(root + "/install/bootstrap").mode, 0o755)
            self.assertEqual(bundle.getmember(root + "/install.sh").mode, 0o644)
            self.assertEqual(bundle.getmember(root + "/release/release.toml").mode,
                             0o644)
            self.assertEqual({member.mtime for member in members}, {1700000000})
            self.assertTrue(all(member.uid == member.gid == 0 for member in members))
            self.assertNotIn(root + "/.git", {member.name for member in members})

    def test_round_trip_is_offline_and_does_not_extract(self) -> None:
        with mock.patch.object(tarfile.TarFile, "extractall",
                               side_effect=AssertionError("extraction forbidden")):
            result = RELEASE.verify(self.metadata_path, self.artifact_path)
        self.assertEqual(result["version"], "v1.0.0-rc1")

    def test_sha_and_size_mismatch(self) -> None:
        archive = self.work / self.artifact_path.name
        shutil.copyfile(self.artifact_path, archive)
        metadata = self.work / "release.json"
        shutil.copyfile(self.metadata_path, metadata)
        archive.write_bytes(archive.read_bytes() + b"x")
        with self.assertRaisesRegex(RELEASE.ReleaseError, "size mismatch"):
            RELEASE.verify(metadata, archive)
        archive.write_bytes(self.artifact_path.read_bytes()[:-1] + b"x")
        with self.assertRaisesRegex(RELEASE.ReleaseError, "SHA-256 mismatch"):
            RELEASE.verify(metadata, archive)

    def test_wrong_artifact_name(self) -> None:
        archive = self.work / "wrong.tar.gz"
        shutil.copyfile(self.artifact_path, archive)
        with self.assertRaisesRegex(RELEASE.ReleaseError, "filename mismatch"):
            RELEASE.verify(self.metadata_path, archive)

    def test_symlinked_input_is_rejected(self) -> None:
        linked = self.work / self.artifact_path.name
        linked.symlink_to(self.artifact_path)
        with self.assertRaisesRegex(RELEASE.ReleaseError, "safely open artifact"):
            RELEASE.verify(self.metadata_path, linked)

    def test_metadata_mismatch_and_duplicate_keys(self) -> None:
        value = json.loads(self.metadata_path.read_text())
        value["summary"] = "Changed summary."
        path = self.work / "release.json"
        path.write_bytes(RELEASE.metadata_bytes(value))
        with self.assertRaisesRegex(RELEASE.ReleaseError, "embedded"):
            RELEASE.verify(path, self.artifact_path)
        with self.assertRaisesRegex(RELEASE.ReleaseError, "duplicate JSON key"):
            RELEASE.parse_metadata(b'{"schema":1,"schema":1}')

    def test_embedded_declaration_mismatch(self) -> None:
        name = RELEASE.archive_root("v1.0.0-rc1") + "/release/release.toml"
        self.reject_archive(replacements={name: DECLARATION.replace(
            b"First candidate.", b"Different candidate.")})

    def test_bad_metadata_types_and_fields(self) -> None:
        for change in ({"schema": True}, {"update_protocol": 3},
                       {"architecture": "arm64"}, {"commit": "a" * 39},
                       {"minimum_installed_version": ""}, {"unknown": 1}):
            with self.subTest(change=change):
                value = json.loads(self.metadata_path.read_text())
                value.update(change)
                with self.assertRaises(RELEASE.ReleaseError):
                    RELEASE.parse_metadata(RELEASE.metadata_bytes(value))
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.parse_metadata(self.metadata_path.read_bytes().replace(
                b'"First candidate."', b'"\\ud800"'))

    def test_absolute_traversal_and_normalization(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        for path in ("/absolute", root + "/../outside", root + "/./dot",
                     root + "//double", root + "/bad\\name"):
            with self.subTest(path=path):
                self.reject_archive(added=[self.member(path)])

    def test_duplicate_destination(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        self.reject_archive(added=[self.member(root + "/install.sh")])

    def test_second_top_level_root(self) -> None:
        self.reject_archive(added=[self.member("another-root/file")])

    def test_links_and_special_objects(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE,
                     tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                self.reject_archive(added=[self.member(root + "/bad", kind=kind)])

    def test_unsafe_modes(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        for mode in (0o600, 0o777, 0o4755):
            with self.subTest(mode=mode):
                self.reject_archive(added=[self.member(root + "/bad", mode=mode)])

    def test_oversized_member(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        metadata, archive = self.altered_archive(
            added=[self.member(root + "/zz-large", size=8)])
        with mock.patch.object(RELEASE, "MAX_MEMBER", 7):
            with self.assertRaisesRegex(RELEASE.ReleaseError, "member exceeds size"):
                RELEASE.verify(metadata, archive)

    def test_too_many_members(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        metadata, archive = self.altered_archive(
            added=[self.member(root + "/zz-extra")])
        with mock.patch.object(RELEASE, "MAX_MEMBERS", 12):
            with self.assertRaisesRegex(RELEASE.ReleaseError, "too many members"):
                RELEASE.verify(metadata, archive)

    def test_excessive_total_expansion(self) -> None:
        root = RELEASE.archive_root("v1.0.0-rc1")
        metadata, archive = self.altered_archive(
            added=[self.member(root + "/zz-extra", size=8)])
        existing = sum(member.size for member in tarfile.open(self.artifact_path)
                       if member.isfile())
        with mock.patch.object(RELEASE, "MAX_UNCOMPRESSED", existing + 7):
            with self.assertRaisesRegex(RELEASE.ReleaseError, "total uncompressed"):
                RELEASE.verify(metadata, archive)

    def test_metadata_and_path_byte_bounds(self) -> None:
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.parse_metadata(b" " * (RELEASE.MAX_METADATA + 1))
        root = RELEASE.archive_root("v1.0.0-rc1")
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE._safe_path(root + "/" + "a" * 240)

    def test_untracked_git_symlink_rejected_when_committed(self) -> None:
        extra = self.work / "symlink-repo"
        shutil.copytree(self.repo, extra, ignore=shutil.ignore_patterns(".git"))
        git(extra, "init", "-q")
        git(extra, "config", "user.name", "Fixture")
        git(extra, "config", "user.email", "fixture@example.invalid")
        (extra / "link").symlink_to("install.sh")
        git(extra, "add", ".")
        git(extra, "commit", "-qm", "symlink fixture")
        commit = git(extra, "rev-parse", "HEAD")
        with self.assertRaisesRegex(RELEASE.ReleaseError, "unsupported tracked object"):
            RELEASE.build(extra, commit, self.work)


if __name__ == "__main__":
    unittest.main()
