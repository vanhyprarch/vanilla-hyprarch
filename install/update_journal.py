#!/usr/bin/env python3
"""Durable, privileged progress for one already-approved release update.

The caller verifies the target release and completes preflight before begin().
This module never discovers releases or commits installed release identity.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_identity import InstalledReleaseIdentity  # noqa: E402

from release import build as contract  # noqa: E402


SCHEMA = 1
MAX_JOURNAL_BYTES = 16384
MAX_MIGRATIONS = 2048
JOURNAL_RELATIVE = Path("var/lib/vanhyprarch/update/journal.json")
LOCK_RELATIVE = Path("run/vanhyprarch/update.lock")
CHECKPOINTS = (
    "preflight-complete", "system-integration", "migrations",
    "managed-deployment", "create-once", "final-validation",
)
PHASES = ("applying", "validating", "ready-for-final-commit")
JOURNAL_KEYS = {
    "schema", "source", "target", "phase", "checkpoint",
    "completed_migrations", "pending_migration",
}
SOURCE_KEYS = {"version", "commit", "artifact_sha256", "migration_level"}
TARGET_KEYS = {
    "version", "commit", "artifact_sha256", "update_protocol",
    "minimum_migration_level", "migration_level",
}


class JournalError(ValueError):
    """Unsafe update state or invalid lifecycle transition."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise JournalError(f"duplicate journal key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise JournalError(f"invalid journal constant: {value}")


def _compact_source(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": metadata["version"], "commit": metadata["commit"],
        "artifact_sha256": metadata["artifact"]["sha256"],
        "migration_level": metadata["migration_level"],
    }


def _compact_target(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": metadata["version"], "commit": metadata["commit"],
        "artifact_sha256": metadata["artifact"]["sha256"],
        "update_protocol": metadata["update_protocol"],
        "minimum_migration_level": metadata["minimum_migration_level"],
        "migration_level": metadata["migration_level"],
    }


def _metadata(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return contract.parse_metadata(contract.metadata_bytes(value))
    except (contract.ReleaseError, TypeError, ValueError, KeyError) as error:
        raise JournalError(f"invalid release identity: {error}") from error


def _identities(source: dict[str, Any], target: dict[str, Any]) -> tuple[dict, dict]:
    old, new = _metadata(source), _metadata(target)
    if contract.version_tuple(new["version"]) <= contract.version_tuple(old["version"]):
        raise JournalError("target release must be newer than installed source")
    minimum_version = new["minimum_installed_version"]
    if (minimum_version is not None
            and contract.version_tuple(old["version"]) < contract.version_tuple(minimum_version)):
        raise JournalError("installed source is below target support floor")
    if not (new["minimum_migration_level"] <= old["migration_level"]
            <= new["migration_level"]):
        raise JournalError("source migration level is outside target support range")
    if new["migration_level"] - old["migration_level"] > MAX_MIGRATIONS:
        raise JournalError("migration chain exceeds journal bounds")
    return _compact_source(old), _compact_target(new)


def validate_record(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != JOURNAL_KEYS:
        raise JournalError("invalid journal schema")
    if type(value["schema"]) is not int or value["schema"] != SCHEMA:
        raise JournalError("unsupported journal schema")
    source, target = value["source"], value["target"]
    if type(source) is not dict or set(source) != SOURCE_KEYS:
        raise JournalError("invalid journal source identity")
    if type(target) is not dict or set(target) != TARGET_KEYS:
        raise JournalError("invalid journal target identity")
    for identity in (source, target):
        contract.version_tuple(identity["version"])
        if type(identity["commit"]) is not str or contract.SHA40.fullmatch(identity["commit"]) is None:
            raise JournalError("invalid journal commit")
        digest = identity["artifact_sha256"]
        if type(digest) is not str or contract.SHA64.fullmatch(digest) is None:
            raise JournalError("invalid journal artifact digest")
        contract._bounded_integer(identity["migration_level"], 0,
                                  contract.MAX_MIGRATION_LEVEL, "journal migration level")
    contract._bounded_integer(target["minimum_migration_level"], 0,
                              contract.MAX_MIGRATION_LEVEL, "journal minimum migration level")
    if type(target["update_protocol"]) is not int or target["update_protocol"] != contract.UPDATE_PROTOCOL:
        raise JournalError("unsupported journal update protocol")
    if (contract.version_tuple(target["version"]) <= contract.version_tuple(source["version"])
            or not target["minimum_migration_level"] <= source["migration_level"] <= target["migration_level"]):
        raise JournalError("inconsistent journal release identities")
    if value["phase"] not in PHASES or type(value["phase"]) is not str:
        raise JournalError("invalid journal phase")
    if value["checkpoint"] not in CHECKPOINTS or type(value["checkpoint"]) is not str:
        raise JournalError("invalid journal checkpoint")
    completed = value["completed_migrations"]
    start, end = source["migration_level"], target["migration_level"]
    if (end - start > MAX_MIGRATIONS or type(completed) is not list
            or len(completed) > MAX_MIGRATIONS
            or any(type(item) is not int for item in completed)
            or completed != list(range(start + 1, start + 1 + len(completed)))
            or (completed and completed[-1] > end)):
        raise JournalError("invalid completed migration sequence")
    pending = value["pending_migration"]
    if pending is not None and (type(pending) is not int
                                or pending != start + len(completed) + 1 or pending > end
                                or value["phase"] != "applying"
                                or value["checkpoint"] != "migrations"):
        raise JournalError("invalid pending migration")
    if value["phase"] != "applying" and (pending is not None or len(completed) != end - start
                                            or value["checkpoint"] != "final-validation"):
        raise JournalError("validation phase requires completed migrations")
    return value


def parse_record(data: bytes) -> dict[str, Any]:
    if not 0 < len(data) <= MAX_JOURNAL_BYTES:
        raise JournalError("journal size is invalid")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise JournalError(f"malformed journal JSON: {error}") from error
    try:
        return validate_record(value)
    except contract.ReleaseError as error:
        raise JournalError(f"invalid journal release field: {error}") from error


def _encoded(value: dict[str, Any]) -> bytes:
    validate_record(value)
    data = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if len(data) > MAX_JOURNAL_BYTES:
        raise JournalError("journal exceeds size bound")
    return data


class _RootPaths:
    def __init__(self, root: Path, uid: int, gid: int, fsync: Any) -> None:
        if (not root.is_absolute() or root.is_symlink()
                or root.resolve(strict=True) != root):
            raise JournalError("system root must be an absolute real directory")
        self.root, self.uid, self.gid, self.fsync = root, uid, gid, fsync

    def _directory(self, path: Path, *, exact_mode: int | None = None,
                   create: bool = False) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            if not create:
                return False
            os.mkdir(path, exact_mode or 0o755)
            os.chmod(path, exact_mode or 0o755)
            self._fsync_dir(path.parent)
            info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or info.st_mode & 0o022
                or (exact_mode is not None and stat.S_IMODE(info.st_mode) != exact_mode)):
            raise JournalError(f"unsafe root-owned directory: {path}")
        return True

    def _parents(self, relative: Path, *, create: bool, private_from: int) -> bool:
        current = self.root
        if not self._directory(current):
            raise JournalError("system root is missing")
        for index, part in enumerate(relative.parts[:-1]):
            current = current / part
            if not self._directory(current, exact_mode=0o700 if index >= private_from else None,
                                   create=create):
                return False
        return True

    def _fsync_dir(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _file(self, path: Path, mode: int) -> os.stat_result | None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or stat.S_IMODE(info.st_mode) != mode):
            raise JournalError(f"unsafe root-owned file: {path}")
        return info


class UpdateLock(_RootPaths):
    """A persistent runtime inode held by flock; process death releases it."""

    def __init__(self, root: Path = Path("/"), *, uid: int = 0, gid: int = 0,
                 fsync: Any = os.fsync) -> None:
        super().__init__(root, uid, gid, fsync)
        self.path = root / LOCK_RELATIVE
        self.held = False

    @contextlib.contextmanager
    def acquire(self) -> Iterator[None]:
        if self.held:
            raise JournalError("update lock is already held by this instance")
        self._parents(LOCK_RELATIVE, create=True, private_from=1)
        existing = self._file(self.path, 0o600)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        try:
            descriptor = os.open(self.path, flags | os.O_CREAT | os.O_EXCL, 0o600) if existing is None else os.open(self.path, flags)
        except FileExistsError as error:
            raise JournalError("update lock appeared during acquisition") from error
        try:
            if existing is None:
                os.fchmod(descriptor, 0o600)
            opened = os.fstat(descriptor)
            current = self._file(self.path, 0o600)
            if (not stat.S_ISREG(opened.st_mode) or current is None
                    or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
                raise JournalError("update lock changed during acquisition")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JournalError("another Vanilla update holds the lock") from error
            self._fsync_dir(self.path.parent)
            self.held = True
            yield
        finally:
            self.held = False
            os.close(descriptor)


class UpdateJournal(_RootPaths):
    def __init__(self, root: Path = Path("/"), *, uid: int = 0, gid: int = 0,
                 fsync: Any = os.fsync) -> None:
        super().__init__(root, uid, gid, fsync)
        self.path = root / JOURNAL_RELATIVE
        self.lock = UpdateLock(root, uid=uid, gid=gid, fsync=fsync)
        self.identity = InstalledReleaseIdentity(root, uid=uid, gid=gid, fsync=fsync)

    def _require_lock(self) -> None:
        if not self.lock.held:
            raise JournalError("journal mutation requires the update lock")
        if self.uid == 0 and os.geteuid() != 0:
            raise JournalError("journal mutation requires root")

    def inspect(self) -> dict[str, Any] | None:
        if not self._parents(JOURNAL_RELATIVE, create=False, private_from=2):
            return None
        info = self._file(self.path, 0o600)
        if info is None:
            return None
        if not 0 < info.st_size <= MAX_JOURNAL_BYTES:
            raise JournalError("journal file size is invalid")
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                raise JournalError("journal changed during inspection")
            data = os.read(descriptor, MAX_JOURNAL_BYTES + 1)
            after = os.fstat(descriptor)
            if len(data) != opened.st_size or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise JournalError("journal changed during inspection")
        finally:
            os.close(descriptor)
        return parse_record(data)

    def _publish(self, value: dict[str, Any], *, initial: bool) -> None:
        self._require_lock()
        data = _encoded(value)
        self._parents(JOURNAL_RELATIVE, create=True, private_from=2)
        current = self.inspect()
        if initial != (current is None):
            raise JournalError("journal publication state changed")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".journal-", dir=self.path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                self.fsync(stream.fileno())
            if initial:
                os.link(temporary, self.path, follow_symlinks=False)
            else:
                self.inspect()
                os.replace(temporary, self.path)
            self._fsync_dir(self.path.parent)
            if self.inspect() != value:
                raise JournalError("published journal differs from intent")
        finally:
            os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def begin(self, source: dict[str, Any], target: dict[str, Any], *, resume: bool = False) -> dict:
        self._require_lock()
        old, new = _identities(source, target)
        installed = self.identity.validate()
        if installed != _metadata(source):
            raise JournalError("installed release does not match proposed source")
        existing = self.inspect()
        if existing is not None:
            if not resume:
                raise JournalError("active update journal requires explicit resume")
            if existing["source"] != old or existing["target"] != new:
                raise JournalError("active journal is bound to a different source or target")
            return existing
        if resume:
            raise JournalError("no active journal exists to resume")
        value = {
            "schema": SCHEMA, "source": old, "target": new, "phase": "applying",
            "checkpoint": "preflight-complete", "completed_migrations": [],
            "pending_migration": None,
        }
        self._publish(value, initial=True)
        return value

    def bound(self, source: dict[str, Any], target: dict[str, Any]) -> dict:
        old, new = _identities(source, target)
        value = self.inspect()
        if value is None:
            raise JournalError("active update journal is absent")
        if value["source"] != old or value["target"] != new:
            raise JournalError("active journal is bound to a different source or target")
        installed = self.identity.validate()
        if installed != _metadata(source):
            raise JournalError("installed source changed during incomplete update")
        return value

    def checkpoint(self, source: dict, target: dict, stage: str) -> dict:
        self._require_lock()
        value = self.bound(source, target)
        if value["phase"] != "applying" or stage not in CHECKPOINTS:
            raise JournalError("invalid applying checkpoint")
        value["checkpoint"] = stage
        self._publish(value, initial=False)
        return value

    def pending(self, source: dict, target: dict, identifier: int) -> dict:
        self._require_lock()
        value = self.bound(source, target)
        expected = value["source"]["migration_level"] + len(value["completed_migrations"]) + 1
        if (value["phase"] != "applying" or value["checkpoint"] != "migrations"
                or value["pending_migration"] is not None or type(identifier) is not int
                or identifier != expected or identifier > value["target"]["migration_level"]):
            raise JournalError("migration cannot be marked pending out of order")
        value["pending_migration"] = identifier
        self._publish(value, initial=False)
        return value

    def complete(self, source: dict, target: dict, identifier: int) -> dict:
        self._require_lock()
        value = self.bound(source, target)
        if type(identifier) is not int or value["pending_migration"] != identifier:
            raise JournalError("migration completion does not match pending intent")
        value["completed_migrations"].append(identifier)
        value["pending_migration"] = None
        self._publish(value, initial=False)
        return value

    def phase(self, source: dict, target: dict, next_phase: str) -> dict:
        self._require_lock()
        value = self.bound(source, target)
        current = value["phase"]
        if ((current, next_phase) not in {
                ("applying", "validating"), ("validating", "ready-for-final-commit")}
                or value["pending_migration"] is not None
                or len(value["completed_migrations"]) != (
                    value["target"]["migration_level"] - value["source"]["migration_level"])):
            raise JournalError("invalid update phase transition")
        value["phase"] = next_phase
        self._publish(value, initial=False)
        return value

    def clear_after_commit(self, source: dict, target: dict) -> None:
        self._require_lock()
        old, new = _identities(source, target)
        value = self.inspect()
        if (value is None or value["source"] != old or value["target"] != new
                or value["phase"] != "ready-for-final-commit"
                or value["pending_migration"] is not None):
            raise JournalError("journal is not ready for exact final clearing")
        if self.identity.validate() != _metadata(target):
            raise JournalError("installed release has not committed the exact target")
        self._file(self.path, 0o600)
        self.path.unlink()
        self._fsync_dir(self.path.parent)

    def clear_committed_target(self, target: dict[str, Any]) -> None:
        """Finish a ready transaction after identity commit survived a crash.

        The old full installed record is no longer present. The retained journal
        still binds its compact source and exact target artifact identity.
        """
        self._require_lock()
        new = _metadata(target)
        value = self.inspect()
        if (value is None or value["target"] != _compact_target(new)
                or value["phase"] != "ready-for-final-commit"
                or value["pending_migration"] is not None):
            raise JournalError("journal is not ready for exact committed-target clearing")
        if self.identity.validate() != new:
            raise JournalError("installed release does not match exact committed target")
        self._file(self.path, 0o600)
        self.path.unlink()
        self._fsync_dir(self.path.parent)
