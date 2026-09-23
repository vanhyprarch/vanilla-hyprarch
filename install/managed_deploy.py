#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""Deploy only VANILLA_MANAGED user artifacts from an ownership manifest."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


PHASE2_CLASS = "VANILLA_MANAGED"
STATE_SCHEMA_VERSION = 1
SUPPORTED_MANIFEST_SCHEMA = 2
VALID_ACTIONS = {
    "create",
    "replace",
    "remove",
    "preserve",
    "conflict",
    "recovery-required",
}
TRANSACTION_VERSION = 1
TRANSACTION_NAME = re.compile(r"\.vanhyprarch-transaction-([0-9a-f]{32})\Z")
TEST_FAULT_ENV = "VANHYPRARCH_DEPLOY_TEST_FAULT_AT"
TEST_MODE_ENV = "VANHYPRARCH_DEPLOY_TESTING"


class DeploymentError(Exception):
    """Base error for a safe managed deployment refusal."""


class ManifestError(DeploymentError):
    """The ownership manifest or deployment state is malformed."""


class SafetyError(DeploymentError):
    """A path, type, symlink, or ownership boundary is unsafe."""


class ConflictError(DeploymentError):
    """Existing content cannot be proven to be Vanilla-managed."""


class ValidationError(DeploymentError):
    """Source, staged, installed, or restored content failed validation."""


def _mode(value: object, label: str) -> int:
    if not isinstance(value, str) or len(value) != 4 or value[0] != "0":
        raise ManifestError(f"{label} must be a four-digit octal mode")
    try:
        parsed = int(value, 8)
    except ValueError as error:
        raise ManifestError(f"{label} must be an octal mode") from error
    if f"0{parsed:03o}" != value:
        raise ManifestError(f"{label} is not a canonical octal mode")
    return parsed


def _mode_text(value: int) -> str:
    return f"0{value:03o}"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SafetyError(f"source is not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _overlap(first: Path, second: Path) -> bool:
    return _inside(first, second) or _inside(second, first)


def _validate_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ManifestError(f"{label} must be a non-empty path without NUL")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or str(path) == "."
        or str(path) != value
    ):
        raise ManifestError(f"{label} must be a normalized relative path: {value}")
    return path


def _walk_existing_without_symlinks(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not _lexists(current):
            continue
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode):
            raise SafetyError(f"symlink traversal is forbidden: {current}")
        if current != absolute and not stat.S_ISDIR(metadata.st_mode):
            raise SafetyError(f"non-directory parent blocks path: {current}")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_exchange(first: Path, second: Path) -> None:
    """Atomically exchange two same-filesystem paths through Linux renameat2."""
    library = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(library, "renameat2", None)
    if renameat2 is None:
        raise SafetyError("installed-mode replacement requires Linux renameat2")
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_exchange = 2
    result = renameat2(
        at_fdcwd,
        os.fsencode(first),
        at_fdcwd,
        os.fsencode(second),
        rename_exchange,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
            raise SafetyError(
                "target filesystem does not support atomic generation exchange"
            )
        raise OSError(error_number, os.strerror(error_number), os.fspath(second))


def _remove_controlled(path: Path) -> None:
    if not _lexists(path):
        return
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode):
        raise SafetyError(f"refusing to remove symlink as controlled data: {path}")
    if stat.S_ISDIR(metadata.st_mode):
        shutil.rmtree(path)
    elif stat.S_ISREG(metadata.st_mode):
        path.unlink()
    else:
        raise SafetyError(f"refusing to remove special file: {path}")


@dataclass(frozen=True)
class TargetContext:
    home: Path
    config: Path
    data: Path
    state: Path
    cache: Path

    @classmethod
    def build(
        cls,
        *,
        home: str | Path,
        config: str | Path | None = None,
        data: str | Path | None = None,
        state: str | Path | None = None,
        cache: str | Path | None = None,
    ) -> "TargetContext":
        home_path = cls._absolute(home, "HOME")
        return cls(
            home=home_path,
            config=cls._absolute(config or home_path / ".config", "XDG_CONFIG_HOME"),
            data=cls._absolute(data or home_path / ".local/share", "XDG_DATA_HOME"),
            state=cls._absolute(state or home_path / ".local/state", "XDG_STATE_HOME"),
            cache=cls._absolute(cache or home_path / ".cache", "XDG_CACHE_HOME"),
        )

    @staticmethod
    def _absolute(value: str | Path, label: str) -> Path:
        text = os.fspath(value)
        if not text or "\x00" in text:
            raise SafetyError(f"{label} must be non-empty and contain no NUL")
        path = Path(text)
        if not path.is_absolute():
            raise SafetyError(f"{label} must be absolute")
        normalized = Path(os.path.normpath(path))
        _walk_existing_without_symlinks(normalized)
        return normalized

    @classmethod
    def from_environment(
        cls,
        *,
        home: str | None = None,
        config: str | None = None,
        data: str | None = None,
        state: str | None = None,
        cache: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> "TargetContext":
        values = os.environ if environment is None else environment
        selected_home = home if home is not None else values.get("HOME")
        if not selected_home:
            raise SafetyError("HOME is required")
        return cls.build(
            home=selected_home,
            config=config if config is not None else values.get("XDG_CONFIG_HOME"),
            data=data if data is not None else values.get("XDG_DATA_HOME"),
            state=state if state is not None else values.get("XDG_STATE_HOME"),
            cache=cache if cache is not None else values.get("XDG_CACHE_HOME"),
        )

    def resolve(self, expression: object) -> tuple[Path, Path]:
        if not isinstance(expression, str) or not expression or "\x00" in expression:
            raise ManifestError("target must be a non-empty string without NUL")
        prefixes = (
            ("${XDG_CONFIG_HOME:-$HOME/.config}", self.config),
            ("${XDG_DATA_HOME:-$HOME/.local/share}", self.data),
            ("${XDG_STATE_HOME:-$HOME/.local/state}", self.state),
            ("${XDG_CACHE_HOME:-$HOME/.cache}", self.cache),
            ("$HOME", self.home),
        )
        for prefix, root in prefixes:
            if expression == prefix:
                relative = PurePosixPath()
            elif expression.startswith(prefix + "/"):
                relative = _validate_relative(expression[len(prefix) + 1 :], "target suffix")
            else:
                continue
            destination = Path(os.path.normpath(root.joinpath(*relative.parts)))
            if not _inside(destination, root):
                raise SafetyError(f"target escapes its declared root: {expression}")
            if any(character in str(relative) for character in ("*", "{", "}")):
                raise ManifestError(f"deployable target may not contain patterns: {expression}")
            return destination, root
        raise ManifestError(f"unsupported deployable target expression: {expression}")


@dataclass(frozen=True)
class Artifact:
    identifier: str
    source: PurePosixPath
    target: str
    ownership_class: str
    kind: str
    mode: int | None
    directory_mode: int | None
    file_mode: int | None
    executable_mode: int | None
    executable: tuple[PurePosixPath, ...]
    included: tuple[PurePosixPath, ...]
    validators: tuple[str, ...]

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "Artifact":
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ManifestError("artifact id must be non-empty")
        ownership_class = record.get("class")
        source = _validate_relative(record.get("source"), f"{identifier} source")
        target = record.get("target")
        if not isinstance(target, str):
            raise ManifestError(f"{identifier} target must be a string")
        kind = record.get("kind")
        if kind not in {"file", "tree"}:
            raise ManifestError(f"{identifier} has unsupported managed kind: {kind}")
        mode = None
        directory_mode = None
        file_mode = None
        executable_mode = None
        if kind == "file":
            mode = _mode(record.get("mode"), f"{identifier} mode")
        else:
            if record.get("mode_policy") != "explicit":
                raise ManifestError(f"{identifier} tree modes must be explicit")
            directory_mode = _mode(
                record.get("directory_mode"), f"{identifier} directory_mode"
            )
            file_mode = _mode(record.get("file_mode"), f"{identifier} file_mode")
            if directory_mode & 0o111 != 0o111:
                raise ManifestError(f"{identifier} directory_mode must be searchable")
        executable = tuple(
            _validate_relative(item, f"{identifier} executable")
            for item in record.get("executable", [])
        )
        if executable:
            executable_mode = _mode(
                record.get("executable_mode"), f"{identifier} executable_mode"
            )
            if executable_mode & 0o111 == 0:
                raise ManifestError(f"{identifier} executable_mode must be executable")
        included = tuple(
            _validate_relative(item, f"{identifier} included")
            for item in record.get("included", [])
        )
        validators_raw = record.get("validators", [])
        if not isinstance(validators_raw, list) or not all(
            isinstance(item, str) and item for item in validators_raw
        ):
            raise ManifestError(f"{identifier} validators must be strings")
        return cls(
            identifier=identifier,
            source=source,
            target=target,
            ownership_class=str(ownership_class),
            kind=kind,
            mode=mode,
            directory_mode=directory_mode,
            file_mode=file_mode,
            executable_mode=executable_mode,
            executable=executable,
            included=included,
            validators=tuple(validators_raw),
        )


@dataclass(frozen=True)
class Snapshot:
    identifier: str
    target: str
    kind: str
    entries: tuple[dict[str, str], ...]
    digest: str

    def record(self) -> dict[str, object]:
        return {
            "id": self.identifier,
            "target": self.target,
            "class": PHASE2_CLASS,
            "kind": self.kind,
            "digest": self.digest,
            "entries": [dict(item) for item in self.entries],
        }


@dataclass(frozen=True)
class PlanItem:
    action: str
    identifier: str
    target: str
    reason: str

    def __post_init__(self) -> None:
        if self.action not in VALID_ACTIONS:
            raise ValueError(f"invalid plan action: {self.action}")

    def line(self) -> str:
        return f"{self.action}\t{self.identifier}\t{self.target}\t{self.reason}"


@dataclass(frozen=True)
class DeploymentPlan:
    operation: str
    items: tuple[PlanItem, ...]
    release_digest: str
    release_id: str | None

    @property
    def conflicts(self) -> tuple[PlanItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.action in {"conflict", "recovery-required"}
        )

    @property
    def changes(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if item.action in {"create", "replace", "remove"})


FaultHook = Callable[[str, str], None]


class ManagedDeployment:
    """Small Phase 2 engine for user-owned VANILLA_MANAGED artifacts."""

    def __init__(
        self,
        *,
        source_root: str | Path,
        target: TargetContext,
        manifest_relative: str = "deployment/ownership-v2.toml",
        release_id: str | None = None,
        fault_hook: FaultHook | None = None,
    ) -> None:
        source_input = Path(source_root)
        if not source_input.is_absolute():
            raise SafetyError("source root must be explicit and absolute")
        if not _lexists(source_input):
            raise ManifestError(f"source root does not exist: {source_input}")
        source_metadata = os.lstat(source_input)
        if stat.S_ISLNK(source_metadata.st_mode) or not stat.S_ISDIR(source_metadata.st_mode):
            raise SafetyError("source root must be a real directory, not a symlink")
        self.source_root = Path(os.path.normpath(source_input))
        _walk_existing_without_symlinks(self.source_root)
        self.target = target
        self.release_id = release_id
        self.fault_hook = fault_hook or (lambda _point, _identifier: None)
        manifest_path = self._source_path(
            _validate_relative(manifest_relative, "ownership manifest"), "file"
        )
        with manifest_path.open("rb") as stream:
            try:
                self.manifest = tomllib.load(stream)
            except tomllib.TOMLDecodeError as error:
                raise ManifestError(f"invalid ownership manifest: {error}") from error
        self._load_manifest()

    def _fault(self, point: str, identifier: str) -> None:
        """Run an injected test fault; abrupt exits require an explicit test guard."""
        self.fault_hook(point, identifier)
        if os.environ.get(TEST_MODE_ENV) != "1":
            return
        selected = os.environ.get(TEST_FAULT_ENV)
        if selected in {point, f"{point}:{identifier}"}:
            os._exit(197)

    def _load_manifest(self) -> None:
        if self.manifest.get("schema_version") != SUPPORTED_MANIFEST_SCHEMA:
            raise ManifestError("unsupported ownership manifest schema")
        if self.manifest.get("installed_mode") != "regular-files":
            raise ManifestError("installed mode must require regular files")
        if self.manifest.get("runtime_source_independent") is not True:
            raise ManifestError("installed runtime must be source-independent")
        records = self.manifest.get("artifact")
        if not isinstance(records, list):
            raise ManifestError("ownership manifest has no artifact list")
        identifiers: set[str] = set()
        targets: set[str] = set()
        self.records_by_id: dict[str, dict[str, object]] = {}
        managed: list[Artifact] = []
        for record in records:
            if not isinstance(record, dict):
                raise ManifestError("artifact record must be a table")
            identifier = record.get("id")
            target = record.get("target")
            if not isinstance(identifier, str) or identifier in identifiers:
                raise ManifestError(f"duplicate or invalid artifact id: {identifier}")
            if not isinstance(target, str) or target in targets:
                raise ManifestError(f"duplicate or invalid artifact target: {target}")
            identifiers.add(identifier)
            targets.add(target)
            self.records_by_id[identifier] = record
            if record.get("class") == PHASE2_CLASS:
                if record.get("status") != "implemented":
                    raise ManifestError(f"managed artifact is not implemented: {identifier}")
                managed.append(Artifact.from_record(record))
        provenance_id = self.manifest.get("managed_deployment_provenance")
        if not isinstance(provenance_id, str) or provenance_id not in self.records_by_id:
            raise ManifestError("managed deployment provenance artifact is not declared")
        provenance = self.records_by_id[provenance_id]
        if provenance.get("class") != "BACKEND_OWNED":
            raise ManifestError("deployment provenance must be BACKEND_OWNED")
        if provenance.get("authority") != "vanhyprarch-managed-deploy":
            raise ManifestError("deployment provenance authority is invalid")
        if provenance.get("kind") != "file":
            raise ManifestError("deployment provenance must be a file")
        self.provenance_mode = _mode(provenance.get("mode"), "provenance mode")
        self.provenance_target = str(provenance["target"])
        self.provenance_path, self.provenance_root = self.target.resolve(
            self.provenance_target
        )
        self.artifacts = tuple(sorted(managed, key=lambda item: item.identifier))
        self.artifacts_by_id = {item.identifier: item for item in self.artifacts}
        self._validate_destinations()

    def require_phase2_artifact(self, identifier: str) -> Artifact:
        record = self.records_by_id.get(identifier)
        if record is None:
            raise ManifestError(f"unknown artifact: {identifier}")
        if record.get("class") != PHASE2_CLASS:
            raise SafetyError(
                f"Phase 2 refuses ownership class {record.get('class')}: {identifier}"
            )
        return self.artifacts_by_id[identifier]

    def _validate_destinations(self) -> None:
        resolved: list[tuple[Artifact, Path]] = []
        sources: list[tuple[Artifact, Path]] = []
        for artifact in self.artifacts:
            destination, _root = self.target.resolve(artifact.target)
            source = self._source_path(artifact.source, artifact.kind)
            if _overlap(destination, self.source_root):
                raise SafetyError(
                    f"source and destination overlap for {artifact.identifier}: {destination}"
                )
            for previous, previous_path in resolved:
                if _overlap(destination, previous_path):
                    raise ManifestError(
                        f"managed targets overlap: {previous.identifier} and {artifact.identifier}"
                    )
            for previous, previous_source in sources:
                if _overlap(source, previous_source):
                    raise ManifestError(
                        f"managed sources overlap: {previous.identifier} and {artifact.identifier}"
                    )
            resolved.append((artifact, destination))
            sources.append((artifact, source))
        for artifact, destination in resolved:
            if _overlap(destination, self.provenance_path):
                raise ManifestError(
                    f"managed target overlaps deployment provenance: {artifact.identifier}"
                )
            for record in self.records_by_id.values():
                if record.get("class") == PHASE2_CLASS:
                    continue
                target = record.get("target")
                if not isinstance(target, str):
                    continue
                try:
                    protected, _protected_root = self.target.resolve(target)
                except ManifestError:
                    continue
                if _overlap(destination, protected):
                    raise ManifestError(
                        f"managed target {artifact.identifier} overlaps non-managed "
                        f"artifact {record.get('id')}"
                    )

    def _source_path(self, relative: PurePosixPath, expected: str) -> Path:
        path = self.source_root.joinpath(*relative.parts)
        if not _inside(path, self.source_root):
            raise SafetyError(f"source escapes source root: {relative}")
        current = self.source_root
        for part in relative.parts:
            current /= part
            if not _lexists(current):
                raise ManifestError(f"missing source artifact: {relative}")
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise SafetyError(f"source symlink is forbidden: {current}")
            if current != path and not stat.S_ISDIR(metadata.st_mode):
                raise SafetyError(f"source parent is not a directory: {current}")
        metadata = os.lstat(path)
        if expected == "file" and not stat.S_ISREG(metadata.st_mode):
            raise ManifestError(f"source is not a regular file: {relative}")
        if expected == "tree" and not stat.S_ISDIR(metadata.st_mode):
            raise ManifestError(f"source is not a directory tree: {relative}")
        return path

    def _tree_sources(self, artifact: Artifact) -> tuple[tuple[PurePosixPath, Path, str], ...]:
        root = self._source_path(artifact.source, "tree")
        entries: list[tuple[PurePosixPath, Path, str]] = []
        if artifact.included:
            included_seen: set[PurePosixPath] = set()
            for relative in sorted(artifact.included, key=str):
                if relative in included_seen:
                    raise ManifestError(f"duplicate included path in {artifact.identifier}: {relative}")
                included_seen.add(relative)
                path = root.joinpath(*relative.parts)
                current = root
                for part in relative.parts:
                    current /= part
                    if not _lexists(current):
                        raise ManifestError(
                            f"missing included source in {artifact.identifier}: {relative}"
                        )
                    metadata = os.lstat(current)
                    if stat.S_ISLNK(metadata.st_mode):
                        raise SafetyError(f"included source symlink is forbidden: {current}")
                if not stat.S_ISREG(os.lstat(path).st_mode):
                    raise ManifestError(f"included source must be a file: {relative}")
                entries.append((relative, path, "file"))
        else:
            def visit(directory: Path, relative_directory: PurePosixPath) -> None:
                for entry in sorted(os.scandir(directory), key=lambda item: item.name):
                    relative = relative_directory / entry.name
                    if entry.is_symlink():
                        raise SafetyError(f"source tree symlink is forbidden: {entry.path}")
                    if entry.is_dir(follow_symlinks=False):
                        entries.append((relative, Path(entry.path), "directory"))
                        visit(Path(entry.path), relative)
                    elif entry.is_file(follow_symlinks=False):
                        entries.append((relative, Path(entry.path), "file"))
                    else:
                        raise SafetyError(f"source tree special file is forbidden: {entry.path}")

            visit(root, PurePosixPath())
        executable = set(artifact.executable)
        files = {relative for relative, _path, kind in entries if kind == "file"}
        unknown = executable - files
        if unknown:
            raise ManifestError(
                f"executable entries are not deployed files in {artifact.identifier}: "
                + ", ".join(map(str, sorted(unknown, key=str)))
            )
        return tuple(entries)

    def _source_snapshot(self, artifact: Artifact) -> Snapshot:
        source = self._source_path(artifact.source, artifact.kind)
        self._run_validators(artifact, source)
        if artifact.kind == "file":
            assert artifact.mode is not None
            entries = (
                {
                    "path": ".",
                    "type": "file",
                    "mode": _mode_text(artifact.mode),
                    "sha256": _sha256_file(source),
                },
            )
        else:
            assert artifact.directory_mode is not None
            assert artifact.file_mode is not None
            values: list[dict[str, str]] = [
                {
                    "path": ".",
                    "type": "directory",
                    "mode": _mode_text(artifact.directory_mode),
                }
            ]
            executable = set(artifact.executable)
            for relative, path, kind in self._tree_sources(artifact):
                if kind == "directory":
                    values.append(
                        {
                            "path": str(relative),
                            "type": "directory",
                            "mode": _mode_text(artifact.directory_mode),
                        }
                    )
                else:
                    mode = (
                        artifact.executable_mode
                        if relative in executable
                        else artifact.file_mode
                    )
                    assert mode is not None
                    values.append(
                        {
                            "path": str(relative),
                            "type": "file",
                            "mode": _mode_text(mode),
                            "sha256": _sha256_file(path),
                        }
                    )
            entries = tuple(values)
        digest = _sha256_bytes(_canonical_bytes(entries))
        return Snapshot(artifact.identifier, artifact.target, artifact.kind, entries, digest)

    def _actual_snapshot(self, artifact: Artifact, destination: Path) -> Snapshot:
        if not _lexists(destination):
            raise ValidationError(f"installed artifact is missing: {destination}")
        metadata = os.lstat(destination)
        if stat.S_ISLNK(metadata.st_mode):
            raise SafetyError(f"installed artifact may not be a symlink: {destination}")
        if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
            raise SafetyError(f"installed artifact has unexpected ownership: {destination}")
        values: list[dict[str, str]] = []
        if artifact.kind == "file":
            if not stat.S_ISREG(metadata.st_mode):
                raise ValidationError(f"installed target is not a file: {destination}")
            values.append(
                {
                    "path": ".",
                    "type": "file",
                    "mode": _mode_text(stat.S_IMODE(metadata.st_mode)),
                    "sha256": _sha256_file(destination),
                }
            )
        else:
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValidationError(f"installed target is not a tree: {destination}")
            values.append(
                {
                    "path": ".",
                    "type": "directory",
                    "mode": _mode_text(stat.S_IMODE(metadata.st_mode)),
                }
            )

            def visit(directory: Path, relative_directory: PurePosixPath) -> None:
                for entry in sorted(os.scandir(directory), key=lambda item: item.name):
                    relative = relative_directory / entry.name
                    entry_metadata = entry.stat(follow_symlinks=False)
                    if entry.is_symlink():
                        raise SafetyError(f"installed tree contains a symlink: {entry.path}")
                    if entry_metadata.st_uid != os.geteuid() or entry_metadata.st_gid != os.getegid():
                        raise SafetyError(f"installed tree has unexpected ownership: {entry.path}")
                    if entry.is_dir(follow_symlinks=False):
                        values.append(
                            {
                                "path": str(relative),
                                "type": "directory",
                                "mode": _mode_text(stat.S_IMODE(entry_metadata.st_mode)),
                            }
                        )
                        visit(Path(entry.path), relative)
                    elif entry.is_file(follow_symlinks=False):
                        values.append(
                            {
                                "path": str(relative),
                                "type": "file",
                                "mode": _mode_text(stat.S_IMODE(entry_metadata.st_mode)),
                                "sha256": _sha256_file(Path(entry.path)),
                            }
                        )
                    else:
                        raise SafetyError(f"installed tree contains a special file: {entry.path}")

            visit(destination, PurePosixPath())
        entries = tuple(values)
        return Snapshot(
            artifact.identifier,
            artifact.target,
            artifact.kind,
            entries,
            _sha256_bytes(_canonical_bytes(entries)),
        )

    def _run_validators(self, artifact: Artifact, path: Path) -> None:
        for validator in artifact.validators:
            if validator == "python-compile":
                if artifact.kind != "file":
                    raise ManifestError("python-compile requires a file artifact")
                try:
                    source = path.read_text(encoding="utf-8")
                    compile(source, str(path), "exec")
                except (OSError, UnicodeError, SyntaxError) as error:
                    raise ValidationError(
                        f"Python validation failed for {artifact.identifier}: {error}"
                    ) from error
            elif validator == "shell-syntax":
                if artifact.kind != "file":
                    raise ManifestError("shell-syntax requires a file artifact")
                result = subprocess.run(
                    ["/bin/sh", "-n", str(path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    shell=False,
                )
                if result.returncode != 0:
                    raise ValidationError(
                        f"shell validation failed for {artifact.identifier}: {result.stderr.strip()}"
                    )
            elif validator == "quickshell-tree":
                if artifact.kind != "tree" or not (path / "shell.qml").is_file():
                    raise ValidationError("Quickshell tree must contain shell.qml")
                for candidate in sorted(path.rglob("*")):
                    if candidate.is_symlink():
                        raise SafetyError(f"Quickshell source symlink is forbidden: {candidate}")
                    if not candidate.is_file():
                        continue
                    if candidate.suffix in {".qml", ".js", ".svg"}:
                        try:
                            candidate.read_text(encoding="utf-8")
                        except (OSError, UnicodeError) as error:
                            raise ValidationError(
                                f"Quickshell text validation failed: {candidate}"
                            ) from error
                    elif candidate.suffix == ".py":
                        try:
                            compile(candidate.read_text(encoding="utf-8"), str(candidate), "exec")
                        except (OSError, UnicodeError, SyntaxError) as error:
                            raise ValidationError(
                                f"Quickshell Python validation failed: {candidate}: {error}"
                            ) from error
            else:
                raise ManifestError(
                    f"unknown validator for {artifact.identifier}: {validator}"
                )

    def _desired(self) -> tuple[dict[str, Snapshot], str]:
        desired = {artifact.identifier: self._source_snapshot(artifact) for artifact in self.artifacts}
        digest_input = {
            "manifest_schema": SUPPORTED_MANIFEST_SCHEMA,
            "artifacts": [desired[name].record() for name in sorted(desired)],
        }
        return desired, _sha256_bytes(_canonical_bytes(digest_input))

    def _check_target_parent(self, path: Path, root: Path) -> None:
        if not _inside(path, root):
            raise SafetyError(f"destination escapes target root: {path}")
        _walk_existing_without_symlinks(path.parent)
        current = root
        if _lexists(root):
            metadata = os.lstat(root)
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise SafetyError(f"target root is not a real directory: {root}")
            if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
                raise SafetyError(f"target root is not owned by the current user: {root}")
        relative_parent = path.parent.relative_to(root)
        for part in relative_parent.parts:
            current /= part
            if not _lexists(current):
                break
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise SafetyError(f"unsafe destination parent: {current}")
            if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
                raise SafetyError(f"destination parent is not user-owned: {current}")

    def _ensure_parent(self, path: Path, root: Path) -> None:
        self._check_target_parent(path, root)
        current = root
        if not _lexists(current):
            current.mkdir(mode=0o755, parents=True)
            os.chmod(current, 0o755)
        if os.lstat(current).st_uid != os.geteuid():
            raise SafetyError(f"target root is not user-owned: {current}")
        for part in path.parent.relative_to(root).parts:
            current /= part
            if _lexists(current):
                metadata = os.lstat(current)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    raise SafetyError(f"unsafe destination parent: {current}")
                if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
                    raise SafetyError(f"destination parent is not user-owned: {current}")
            else:
                current.mkdir(mode=0o755)
                os.chmod(current, 0o755)
                _fsync_directory(current.parent)

    def _validate_state_record(
        self, record: object, *, label: str
    ) -> dict[str, object]:
        if not isinstance(record, dict):
            raise ConflictError(f"{label} is invalid")
        identifier = record.get("id")
        target = record.get("target")
        entries = record.get("entries")
        if not isinstance(identifier, str) or not identifier:
            raise ConflictError(f"{label} id is invalid")
        if not isinstance(target, str):
            raise ConflictError(f"{label} target is invalid")
        if record.get("kind") not in {"file", "tree"} or not isinstance(entries, list):
            raise ConflictError(f"{label} is malformed: {identifier}")
        if record.get("class") != PHASE2_CLASS:
            raise ConflictError(f"{label} ownership class is invalid: {identifier}")
        if record.get("digest") != _sha256_bytes(_canonical_bytes(tuple(entries))):
            raise ConflictError(f"{label} digest is invalid: {identifier}")
        self.target.resolve(target)
        return record

    def _validate_transaction(
        self,
        transaction: object,
        records: dict[str, dict[str, object]],
    ) -> dict[str, object] | None:
        if transaction is None:
            return None
        if not isinstance(transaction, dict):
            raise ConflictError("deployment transaction is invalid")
        expected_keys = {
            "version",
            "id",
            "action",
            "artifact_id",
            "target",
            "kind",
            "container",
            "phase",
            "prior_state_absent",
            "prior",
            "candidate",
        }
        if set(transaction) != expected_keys:
            raise ConflictError("deployment transaction fields are invalid")
        transaction_id = transaction.get("id")
        container = transaction.get("container")
        if (
            transaction.get("version") != TRANSACTION_VERSION
            or not isinstance(transaction_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None
            or container != f".vanhyprarch-transaction-{transaction_id}"
            or TRANSACTION_NAME.fullmatch(str(container)) is None
        ):
            raise ConflictError("deployment transaction identity is invalid")
        action = transaction.get("action")
        phase = transaction.get("phase")
        artifact_id = transaction.get("artifact_id")
        target = transaction.get("target")
        kind = transaction.get("kind")
        if (
            action not in {"create", "replace", "remove"}
            or phase not in {"staging", "prepared", "committed", "cleaning"}
            or not isinstance(artifact_id, str)
            or not isinstance(target, str)
            or kind not in {"file", "tree"}
            or not isinstance(transaction.get("prior_state_absent"), bool)
        ):
            raise ConflictError("deployment transaction metadata is invalid")
        self.target.resolve(target)
        prior_raw = transaction.get("prior")
        candidate_raw = transaction.get("candidate")
        prior = (
            None
            if prior_raw is None
            else self._validate_state_record(prior_raw, label="transaction prior record")
        )
        candidate = (
            None
            if candidate_raw is None
            else self._validate_state_record(
                candidate_raw, label="transaction candidate record"
            )
        )
        for record in (prior, candidate):
            if record is not None and (
                record.get("id") != artifact_id
                or record.get("target") != target
                or record.get("kind") != kind
            ):
                raise ConflictError("deployment transaction record identity is invalid")
        if action == "create" and (prior is not None or candidate is None):
            raise ConflictError("create transaction records are invalid")
        if action == "replace" and (prior is None or candidate is None):
            raise ConflictError("replace transaction records are invalid")
        if action == "remove" and (prior is None or candidate is not None):
            raise ConflictError("remove transaction records are invalid")
        recorded = records.get(artifact_id)
        authoritative = prior if phase in {"staging", "prepared"} else candidate
        if authoritative is None:
            if recorded is not None:
                raise ConflictError("deployment transaction conflicts with provenance")
        elif recorded != authoritative:
            raise ConflictError("deployment transaction conflicts with provenance")
        return transaction

    def _load_state(self) -> tuple[dict[str, object] | None, bytes | None]:
        self._check_target_parent(self.provenance_path, self.provenance_root)
        if not _lexists(self.provenance_path):
            return None, None
        metadata = os.lstat(self.provenance_path)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ConflictError("deployment provenance exists but is not a regular file")
        if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
            raise ConflictError("deployment provenance is not owned by the current user")
        if stat.S_IMODE(metadata.st_mode) != self.provenance_mode:
            raise ConflictError("deployment provenance has an unexpected mode")
        raw = self.provenance_path.read_bytes()
        try:
            state = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ConflictError("deployment provenance is malformed") from error
        if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ConflictError("deployment provenance schema is unsupported")
        if state.get("ownership_manifest_schema") != SUPPORTED_MANIFEST_SCHEMA:
            raise ConflictError("deployment provenance manifest schema is unsupported")
        if state.get("status") not in {"complete", "partial"}:
            raise ConflictError("deployment provenance status is invalid")
        if state.get("operation") not in {"install", "update", "complete"}:
            raise ConflictError("deployment provenance operation is invalid")
        records = state.get("artifacts")
        if not isinstance(records, list):
            raise ConflictError("deployment provenance artifact list is invalid")
        seen_ids: set[str] = set()
        seen_targets: set[str] = set()
        normalized: dict[str, dict[str, object]] = {}
        for raw_record in records:
            record = self._validate_state_record(
                raw_record, label="deployment provenance artifact record"
            )
            identifier = str(record["id"])
            target = str(record["target"])
            if identifier in seen_ids:
                raise ConflictError("deployment provenance has duplicate artifact ids")
            if target in seen_targets:
                raise ConflictError("deployment provenance has duplicate artifact targets")
            seen_ids.add(identifier)
            seen_targets.add(target)
            normalized[identifier] = record
        self._validate_transaction(state.get("transaction"), normalized)
        return state, raw

    @staticmethod
    def _records(state: dict[str, object] | None) -> dict[str, dict[str, object]]:
        if state is None:
            return {}
        return {str(item["id"]): item for item in state["artifacts"]}  # type: ignore[index]

    @staticmethod
    def _snapshot_matches_record(snapshot: Snapshot, record: dict[str, object]) -> bool:
        return snapshot.record() == record

    def plan(self, operation: str) -> DeploymentPlan:
        if operation not in {"install", "update"}:
            raise ValueError("operation must be install or update")
        desired, release_digest = self._desired()
        state, _raw = self._load_state()
        previous = self._records(state)
        items: list[PlanItem] = []
        if state is not None and state.get("transaction") is not None:
            transaction = state["transaction"]
            assert isinstance(transaction, dict)
            items.append(
                PlanItem(
                    "recovery-required",
                    str(transaction["artifact_id"]),
                    str(transaction["target"]),
                    f"interrupted {transaction['action']} is in {transaction['phase']} phase",
                )
            )
            return DeploymentPlan(operation, tuple(items), release_digest, self.release_id)
        if operation == "update" and state is None:
            items.append(
                PlanItem("conflict", "@provenance", self.provenance_target, "update requires prior provenance")
            )
            return DeploymentPlan(operation, tuple(items), release_digest, self.release_id)
        if state is not None and state.get("status") == "partial":
            if state.get("release_digest") != release_digest or state.get("operation") != operation:
                items.append(
                    PlanItem(
                        "conflict",
                        "@provenance",
                        self.provenance_target,
                        "partial deployment may resume only the same operation and release",
                    )
                )
                return DeploymentPlan(operation, tuple(items), release_digest, self.release_id)

        for identifier in sorted(desired):
            artifact = self.artifacts_by_id[identifier]
            destination, root = self.target.resolve(artifact.target)
            self._check_target_parent(destination, root)
            prior = previous.get(identifier)
            if prior is None:
                if _lexists(destination):
                    items.append(
                        PlanItem("conflict", identifier, artifact.target, "destination is not proven Vanilla-managed")
                    )
                else:
                    items.append(PlanItem("create", identifier, artifact.target, "destination is absent"))
                continue
            if prior.get("target") != artifact.target or prior.get("kind") != artifact.kind:
                items.append(
                    PlanItem("conflict", identifier, artifact.target, "managed identity changed target or kind")
                )
                continue
            if not _lexists(destination):
                items.append(
                    PlanItem("conflict", identifier, artifact.target, "proven managed destination is missing")
                )
                continue
            actual = self._actual_snapshot(artifact, destination)
            if not self._snapshot_matches_record(actual, prior):
                items.append(
                    PlanItem("conflict", identifier, artifact.target, "installed managed artifact drifted")
                )
            elif actual == desired[identifier]:
                items.append(PlanItem("preserve", identifier, artifact.target, "bytes and modes already match"))
            else:
                items.append(PlanItem("replace", identifier, artifact.target, "managed bytes or modes changed"))

        for identifier in sorted(set(previous) - set(desired)):
            record = previous[identifier]
            target_text = str(record["target"])
            destination, root = self.target.resolve(target_text)
            self._check_target_parent(destination, root)
            if not _lexists(destination):
                items.append(PlanItem("remove", identifier, target_text, "stale managed artifact is already absent"))
                continue
            synthetic = Artifact(
                identifier=identifier,
                source=PurePosixPath("unused"),
                target=target_text,
                ownership_class=PHASE2_CLASS,
                kind=str(record["kind"]),
                mode=None,
                directory_mode=None,
                file_mode=None,
                executable_mode=None,
                executable=(),
                included=(),
                validators=(),
            )
            actual = self._actual_snapshot(synthetic, destination)
            if not self._snapshot_matches_record(actual, record):
                items.append(
                    PlanItem("conflict", identifier, target_text, "stale managed artifact drifted")
                )
            else:
                items.append(PlanItem("remove", identifier, target_text, "artifact is absent from new manifest"))

        if operation == "install" and state is not None and state.get("status") == "complete":
            for index, item in enumerate(items):
                if item.action != "preserve":
                    items[index] = PlanItem(
                        "conflict",
                        item.identifier,
                        item.target,
                        "install may only repeat an identical completed release; use update",
                    )
        return DeploymentPlan(operation, tuple(items), release_digest, self.release_id)

    def reconcile_operation(self) -> str:
        """Select the provenance-compatible install or update operation."""
        state, _raw = self._load_state()
        if state is None:
            return "install"
        if state.get("status") == "partial":
            operation = state.get("operation")
            if operation not in {"install", "update"}:
                raise ConflictError(
                    "partial deployment has no resumable install/update operation"
                )
            return str(operation)
        return "update"

    def plan_reconciled(self) -> DeploymentPlan:
        return self.plan(self.reconcile_operation())

    def _ensure_home_identity(self) -> None:
        if os.geteuid() == 0:
            raise SafetyError("Phase 2 user deployment must not run as root")
        if not _lexists(self.target.home):
            raise SafetyError("target HOME must already exist")
        metadata = os.lstat(self.target.home)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SafetyError("target HOME must be a real directory")
        if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
            raise SafetyError("Phase 2 must run as the target user; HOME ownership differs")

    def _copy_regular(
        self, source: Path, destination: Path, mode: int, identifier: str
    ) -> None:
        source_descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(source_descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise SafetyError(f"copy source is not a regular file: {source}")
            destination_descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                mode,
            )
            try:
                with os.fdopen(source_descriptor, "rb", closefd=False) as source_stream:
                    with os.fdopen(destination_descriptor, "wb", closefd=False) as destination_stream:
                        shutil.copyfileobj(source_stream, destination_stream, 1024 * 1024)
                        destination_stream.flush()
                        os.fchmod(destination_descriptor, mode)
                        self._fault("before-stage-file-fsync", identifier)
                        os.fsync(destination_descriptor)
                        self._fault("after-stage-file-fsync", identifier)
            finally:
                os.close(destination_descriptor)
        finally:
            os.close(source_descriptor)

    def _stage(
        self,
        artifact: Artifact,
        destination: Path,
        root: Path,
        container: Path,
    ) -> tuple[Path, Snapshot]:
        self._ensure_parent(destination, root)
        container.mkdir(mode=0o700)
        os.chmod(container, 0o700)
        payload = container / "payload"
        try:
            source = self._source_path(artifact.source, artifact.kind)
            if artifact.kind == "file":
                assert artifact.mode is not None
                self._copy_regular(source, payload, artifact.mode, artifact.identifier)
            else:
                assert artifact.directory_mode is not None
                assert artifact.file_mode is not None
                payload.mkdir(mode=artifact.directory_mode)
                os.chmod(payload, artifact.directory_mode)
                executable = set(artifact.executable)
                for relative, source_path, kind in self._tree_sources(artifact):
                    staged = payload.joinpath(*relative.parts)
                    if kind == "directory":
                        staged.mkdir(mode=artifact.directory_mode)
                        os.chmod(staged, artifact.directory_mode)
                    else:
                        staged.parent.mkdir(mode=artifact.directory_mode, parents=True, exist_ok=True)
                        mode = (
                            artifact.executable_mode
                            if relative in executable
                            else artifact.file_mode
                        )
                        assert mode is not None
                        self._copy_regular(
                            source_path, staged, mode, artifact.identifier
                        )
                for directory, child_directories, _files in os.walk(payload, topdown=False):
                    for child in child_directories:
                        os.chmod(Path(directory) / child, artifact.directory_mode)
                        _fsync_directory(Path(directory) / child)
                    _fsync_directory(Path(directory))
            self._run_validators(artifact, payload)
            staged = self._actual_snapshot(artifact, payload)
            desired = self._source_snapshot(artifact)
            if staged != desired:
                raise ValidationError(f"staged content differs from source contract: {artifact.identifier}")
            _fsync_directory(container)
            _fsync_directory(destination.parent)
            return payload, desired
        except Exception:
            _remove_controlled(container)
            _fsync_directory(destination.parent)
            raise

    @staticmethod
    def _synthetic_artifact(record: dict[str, object]) -> Artifact:
        return Artifact(
            identifier=str(record["id"]),
            source=PurePosixPath("unused"),
            target=str(record["target"]),
            ownership_class=PHASE2_CLASS,
            kind=str(record["kind"]),
            mode=None,
            directory_mode=None,
            file_mode=None,
            executable_mode=None,
            executable=(),
            included=(),
            validators=(),
        )

    def _path_matches_record(
        self, path: Path, record: dict[str, object] | None
    ) -> bool:
        if record is None or not _lexists(path):
            return False
        try:
            actual = self._actual_snapshot(self._synthetic_artifact(record), path)
        except DeploymentError:
            return False
        return self._snapshot_matches_record(actual, record)

    def _transaction_paths(
        self, transaction: dict[str, object]
    ) -> tuple[Path, Path, Path]:
        destination, root = self.target.resolve(transaction["target"])
        self._check_target_parent(destination, root)
        container_name = str(transaction["container"])
        match = TRANSACTION_NAME.fullmatch(container_name)
        if match is None or match.group(1) != transaction["id"]:
            raise ConflictError("deployment transaction container is invalid")
        container = destination.parent / container_name
        if not _inside(container, root):
            raise SafetyError("deployment transaction container escapes target root")
        if _lexists(container):
            metadata = os.lstat(container)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_gid != os.getegid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise ConflictError("deployment transaction container is unsafe")
        return destination, root, container

    @staticmethod
    def _container_entries(container: Path) -> set[str]:
        if not _lexists(container):
            return set()
        with os.scandir(container) as entries:
            return {entry.name for entry in entries}

    def _new_transaction(
        self,
        *,
        item: PlanItem,
        artifact: Artifact | None,
        prior: dict[str, object] | None,
        candidate: Snapshot | None,
        state: dict[str, object] | None,
        state_raw: bytes | None,
        operation: str,
        release_digest: str,
        records: dict[str, dict[str, object]],
    ) -> tuple[dict[str, object], bytes]:
        destination, root = self.target.resolve(item.target)
        self._ensure_parent(destination, root)
        transaction_id = secrets.token_hex(16)
        container = destination.parent / f".vanhyprarch-transaction-{transaction_id}"
        candidate_record = None if candidate is None else candidate.record()
        if item.action == "create":
            if _lexists(destination):
                raise ConflictError(f"destination appeared during create: {destination}")
            assert artifact is not None and candidate is not None
        elif item.action == "replace":
            assert artifact is not None and prior is not None and candidate is not None
            if not self._path_matches_record(destination, prior):
                raise ConflictError(
                    f"managed destination changed while planning: {artifact.identifier}"
                )
        else:
            assert item.action == "remove" and prior is not None
            if not self._path_matches_record(destination, prior):
                raise ConflictError(
                    f"stale artifact changed before removal: {item.identifier}"
                )

        transaction: dict[str, object] = {
            "version": TRANSACTION_VERSION,
            "id": transaction_id,
            "action": item.action,
            "artifact_id": item.identifier,
            "target": item.target,
            "kind": str((prior or candidate_record)["kind"]),
            "container": container.name,
            "phase": "staging",
            "prior_state_absent": state is None,
            "prior": prior,
            "candidate": candidate_record,
        }
        if state is None:
            intent = self._state_document(
                operation=operation,
                status="partial",
                release_digest=release_digest,
                records=records,
                transaction=transaction,
            )
        else:
            intent = dict(state)
            intent["transaction"] = transaction
        self._atomic_state_write(
            intent, state_raw, item.identifier, milestone="intent"
        )
        try:
            intent_raw = self.provenance_path.read_bytes()
            if item.action == "create":
                _payload, staged = self._stage(
                    artifact, destination, root, container
                )
                if staged != candidate:
                    raise ConflictError(
                        f"source changed while planning: {artifact.identifier}"
                    )
            elif item.action == "replace":
                _payload, staged = self._stage(
                    artifact, destination, root, container
                )
                if staged != candidate or not self._path_matches_record(destination, prior):
                    raise ConflictError(
                        f"source or destination changed while staging: {artifact.identifier}"
                    )
            else:
                container.mkdir(mode=0o700)
                os.chmod(container, 0o700)
                _fsync_directory(container)
                _fsync_directory(destination.parent)
            prepared = dict(transaction)
            prepared["phase"] = "prepared"
            intent = dict(intent)
            intent["transaction"] = prepared
            self._atomic_state_write(
                intent, intent_raw, item.identifier, milestone="intent-ready"
            )
            return prepared, self.provenance_path.read_bytes()
        except Exception:
            self._recover_incomplete()
            raise

    def _publish_transaction(
        self, transaction: dict[str, object], artifact: Artifact | None
    ) -> None:
        destination, _root, container = self._transaction_paths(transaction)
        action = str(transaction["action"])
        identifier = str(transaction["artifact_id"])
        payload = container / ("backup" if action == "remove" else "payload")
        prior = transaction.get("prior")
        candidate = transaction.get("candidate")
        expected_entries = set() if action == "remove" else {"payload"}
        if self._container_entries(container) != expected_entries:
            raise ConflictError("prepared deployment transaction content changed")
        if action == "create":
            if _lexists(destination) or not isinstance(
                candidate, dict
            ) or not self._path_matches_record(payload, candidate):
                raise ConflictError("prepared create state changed before publish")
        elif action == "replace":
            if (
                not isinstance(prior, dict)
                or not isinstance(candidate, dict)
                or not self._path_matches_record(destination, prior)
                or not self._path_matches_record(payload, candidate)
            ):
                raise ConflictError("prepared replacement state changed before publish")
        elif not isinstance(prior, dict) or not self._path_matches_record(
            destination, prior
        ):
            raise ConflictError("prepared removal state changed before publish")
        self._fault("before-publish", identifier)
        if action == "create":
            os.replace(payload, destination)
        elif action == "replace":
            _atomic_exchange(payload, destination)
            self._fault("after-backup", identifier)
        else:
            os.replace(destination, payload)
            self._fault("after-backup", identifier)
        self._fault("after-publish", identifier)
        self._fault("before-publish-container-fsync", identifier)
        _fsync_directory(container)
        self._fault("after-publish-container-fsync", identifier)
        self._fault("before-publish-parent-fsync", identifier)
        _fsync_directory(destination.parent)
        self._fault("after-publish-parent-fsync", identifier)
        if action == "remove":
            if _lexists(destination):
                raise ValidationError(f"stale artifact removal failed: {identifier}")
        else:
            assert isinstance(candidate, dict) and artifact is not None
            if not self._path_matches_record(destination, candidate):
                raise ValidationError(f"installed verification failed: {identifier}")
            self._run_validators(artifact, destination)
        self._fault("after-replace", identifier)
        self._fault("after-publish-verify", identifier)

    def _cleanup_committed_transaction(
        self, transaction: dict[str, object]
    ) -> None:
        destination, _root, container = self._transaction_paths(transaction)
        action = str(transaction["action"])
        identifier = str(transaction["artifact_id"])
        prior = transaction.get("prior")
        candidate = transaction.get("candidate")
        if action == "remove":
            if _lexists(destination):
                raise ConflictError(
                    f"committed removal target reappeared: {identifier}"
                )
        elif not isinstance(candidate, dict) or not self._path_matches_record(
            destination, candidate
        ):
            raise ConflictError(
                f"committed deployment target drifted: {identifier}"
            )
        expected_entry = "backup" if action == "remove" else "payload"
        entries = self._container_entries(container)
        if entries - {expected_entry}:
            raise ConflictError("deployment transaction container has unknown content")
        rollback = container / expected_entry
        if _lexists(rollback):
            if action == "create" or not isinstance(prior, dict):
                raise ConflictError("deployment transaction rollback material is unexpected")
            if transaction["phase"] == "committed" and not self._path_matches_record(
                rollback, prior
            ):
                raise ConflictError("deployment transaction rollback material drifted")
            if transaction["phase"] == "cleaning":
                self._validate_transaction_container_tree(container)
        self._fault("before-cleanup", identifier)
        if _lexists(rollback):
            _remove_controlled(rollback)
        self._fault("during-cleanup", identifier)
        if _lexists(container):
            _remove_controlled(container)
        _fsync_directory(destination.parent)
        self._fault("after-cleanup", identifier)

    def _validate_transaction_container_tree(self, container: Path) -> None:
        if not _lexists(container):
            return
        for directory, child_directories, files in os.walk(
            container, topdown=True, followlinks=False
        ):
            for name in child_directories + files:
                path = Path(directory) / name
                metadata = os.lstat(path)
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode))
                    or metadata.st_uid != os.geteuid()
                    or metadata.st_gid != os.getegid()
                ):
                    raise ConflictError(
                        "deployment transaction staging content is unsafe"
                    )

    def _restore_staging_transaction(
        self, transaction: dict[str, object]
    ) -> None:
        destination, _root, container = self._transaction_paths(transaction)
        action = str(transaction["action"])
        identifier = str(transaction["artifact_id"])
        prior = transaction.get("prior")
        if action == "create":
            if _lexists(destination):
                raise ConflictError(
                    f"destination changed during interrupted staging: {identifier}"
                )
        elif not isinstance(prior, dict) or not self._path_matches_record(
            destination, prior
        ):
            raise ConflictError(
                f"managed destination changed during interrupted staging: {identifier}"
            )
        self._validate_transaction_container_tree(container)
        if _lexists(container):
            _remove_controlled(container)
            _fsync_directory(destination.parent)

    def _restore_prepared_transaction(
        self, transaction: dict[str, object]
    ) -> None:
        destination, _root, container = self._transaction_paths(transaction)
        action = str(transaction["action"])
        identifier = str(transaction["artifact_id"])
        prior = transaction.get("prior")
        candidate = transaction.get("candidate")
        expected_entry = "backup" if action == "remove" else "payload"
        entries = self._container_entries(container)
        if entries - {expected_entry}:
            raise ConflictError("deployment transaction container has unknown content")
        rollback = container / expected_entry

        if action == "create":
            assert isinstance(candidate, dict)
            if not _lexists(destination) and (
                not _lexists(rollback)
                or self._path_matches_record(rollback, candidate)
            ):
                pass
            elif self._path_matches_record(destination, candidate) and not _lexists(rollback):
                _remove_controlled(destination)
                _fsync_directory(destination.parent)
            else:
                raise ConflictError(
                    f"interrupted create no longer matches transaction evidence: {identifier}"
                )
        elif action == "replace":
            assert isinstance(prior, dict) and isinstance(candidate, dict)
            if self._path_matches_record(destination, prior) and (
                not _lexists(rollback)
                or self._path_matches_record(rollback, candidate)
            ):
                pass
            elif self._path_matches_record(
                destination, candidate
            ) and self._path_matches_record(rollback, prior):
                _atomic_exchange(rollback, destination)
                _fsync_directory(container)
                _fsync_directory(destination.parent)
            else:
                raise ConflictError(
                    f"interrupted replacement no longer matches transaction evidence: {identifier}"
                )
        else:
            assert isinstance(prior, dict)
            if self._path_matches_record(destination, prior) and not _lexists(rollback):
                pass
            elif not _lexists(destination) and self._path_matches_record(rollback, prior):
                os.replace(rollback, destination)
                _fsync_directory(container)
                _fsync_directory(destination.parent)
            else:
                raise ConflictError(
                    f"interrupted removal no longer matches transaction evidence: {identifier}"
                )
        if _lexists(container):
            _remove_controlled(container)
        _fsync_directory(destination.parent)

    def _state_document(
        self,
        *,
        operation: str,
        status: str,
        release_digest: str,
        records: dict[str, dict[str, object]],
        transaction: dict[str, object] | None = None,
    ) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": STATE_SCHEMA_VERSION,
            "ownership_manifest_schema": SUPPORTED_MANIFEST_SCHEMA,
            "status": status,
            "operation": operation if status == "partial" else "complete",
            "release_id": self.release_id,
            "release_digest": release_digest,
            "artifacts": [records[name] for name in sorted(records)],
        }
        if transaction is not None:
            document["transaction"] = transaction
        return document

    def _atomic_state_write(
        self,
        document: dict[str, object],
        old_raw: bytes | None,
        identifier: str,
        *,
        milestone: str = "provenance",
    ) -> None:
        self._ensure_parent(self.provenance_path, self.provenance_root)
        new_raw = json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        if old_raw == new_raw:
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".vanhyprarch-state-", dir=self.provenance_path.parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, self.provenance_mode)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(new_raw)
                stream.flush()
                self._fault(f"before-{milestone}-state-file-fsync", identifier)
                os.fsync(descriptor)
                self._fault(f"after-{milestone}-state-file-fsync", identifier)
            os.close(descriptor)
            descriptor = -1
            self._fault("before-state-write", identifier)
            os.replace(temporary, self.provenance_path)
            self._fault(f"after-{milestone}-state-publish", identifier)
            self._fault(f"before-{milestone}-state-directory-fsync", identifier)
            _fsync_directory(self.provenance_path.parent)
            self._fault(f"after-{milestone}-state-directory-fsync", identifier)
            self._fault("after-state-replace", identifier)
            if self.provenance_path.read_bytes() != new_raw:
                raise ValidationError("deployment provenance readback failed")
            metadata = os.lstat(self.provenance_path)
            if stat.S_IMODE(metadata.st_mode) != self.provenance_mode:
                raise ValidationError("deployment provenance mode verification failed")
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            if _lexists(temporary):
                temporary.unlink()
            self._restore_state_raw(old_raw)
            raise

    def _restore_state_raw(self, old_raw: bytes | None) -> None:
        if old_raw is None:
            if _lexists(self.provenance_path):
                metadata = os.lstat(self.provenance_path)
                if stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                    self.provenance_path.unlink()
                    _fsync_directory(self.provenance_path.parent)
            return
        descriptor, name = tempfile.mkstemp(
            prefix=".vanhyprarch-state-rollback-", dir=self.provenance_path.parent
        )
        temporary = Path(name)
        try:
            os.fchmod(descriptor, self.provenance_mode)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(old_raw)
                stream.flush()
                os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, self.provenance_path)
            _fsync_directory(self.provenance_path.parent)
            if self.provenance_path.read_bytes() != old_raw:
                raise ValidationError("deployment provenance rollback failed")
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if _lexists(temporary):
                temporary.unlink()

    @staticmethod
    def _without_transaction(state: dict[str, object]) -> dict[str, object]:
        document = dict(state)
        document.pop("transaction", None)
        return document

    def _mark_transaction_cleaning(
        self,
        state: dict[str, object],
        state_raw: bytes,
        transaction: dict[str, object],
    ) -> tuple[dict[str, object], bytes, dict[str, object]]:
        cleaning = dict(transaction)
        cleaning["phase"] = "cleaning"
        document = dict(state)
        document["transaction"] = cleaning
        self._atomic_state_write(
            document,
            state_raw,
            str(transaction["artifact_id"]),
            milestone="cleanup-intent",
        )
        return document, self.provenance_path.read_bytes(), cleaning

    def _recover_incomplete(self) -> bool:
        state, state_raw = self._load_state()
        if state is None or state.get("transaction") is None:
            return False
        transaction = self._validate_transaction(
            state["transaction"], self._records(state)
        )
        assert transaction is not None and state_raw is not None
        if transaction["phase"] == "staging":
            self._restore_staging_transaction(transaction)
        elif transaction["phase"] == "prepared":
            self._restore_prepared_transaction(transaction)
        if transaction["phase"] in {"staging", "prepared"}:
            if transaction["prior_state_absent"]:
                metadata = os.lstat(self.provenance_path)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    raise ConflictError("prepared provenance became unsafe during recovery")
                self.provenance_path.unlink()
                _fsync_directory(self.provenance_path.parent)
            else:
                self._atomic_state_write(
                    self._without_transaction(state),
                    state_raw,
                    str(transaction["artifact_id"]),
                    milestone="recovery",
                )
        else:
            if transaction["phase"] == "committed":
                state, state_raw, transaction = self._mark_transaction_cleaning(
                    state, state_raw, transaction
                )
            self._cleanup_committed_transaction(transaction)
            self._atomic_state_write(
                self._without_transaction(state),
                state_raw,
                str(transaction["artifact_id"]),
                milestone="recovery",
            )
        return True

    def apply(self, operation: str) -> DeploymentPlan:
        self._ensure_home_identity()
        self._recover_incomplete()
        plan = self.plan(operation)
        if plan.conflicts:
            raise ConflictError("; ".join(item.line() for item in plan.conflicts))
        state, state_raw = self._load_state()
        records = self._records(state)
        desired_snapshots, desired_digest = self._desired()
        if desired_digest != plan.release_digest:
            raise ConflictError("source changed after planning")
        actionable = list(plan.changes)
        for index, item in enumerate(actionable):
            artifact: Artifact | None = self.artifacts_by_id.get(item.identifier)
            prior = records.get(item.identifier)
            destination, _root = self.target.resolve(item.target)
            if item.action == "remove" and not _lexists(destination):
                records.pop(item.identifier)
                remaining = index + 1 < len(actionable)
                document = self._state_document(
                    operation=operation,
                    status="partial" if remaining else "complete",
                    release_digest=plan.release_digest,
                    records=records,
                )
                self._atomic_state_write(
                    document, state_raw, item.identifier, milestone="provenance"
                )
                state, state_raw = self._load_state()
                continue
            candidate = desired_snapshots.get(item.identifier)
            transaction: dict[str, object] | None = None
            try:
                transaction, state_raw = self._new_transaction(
                    item=item,
                    artifact=artifact,
                    prior=prior,
                    candidate=candidate,
                    state=state,
                    state_raw=state_raw,
                    operation=operation,
                    release_digest=plan.release_digest,
                    records=records,
                )
                self._publish_transaction(transaction, artifact)
                if item.action == "remove":
                    records.pop(item.identifier)
                else:
                    assert candidate is not None
                    records[item.identifier] = candidate.record()
                remaining = index + 1 < len(actionable)
                committed_transaction = dict(transaction)
                committed_transaction["phase"] = "committed"
                document = self._state_document(
                    operation=operation,
                    status="partial" if remaining else "complete",
                    release_digest=plan.release_digest,
                    records=records,
                    transaction=committed_transaction,
                )
                self._atomic_state_write(
                    document, state_raw, item.identifier, milestone="provenance"
                )
                transaction = committed_transaction
                state_raw = self.provenance_path.read_bytes()
                self._fault("after-provenance-commit", item.identifier)
                document, state_raw, transaction = self._mark_transaction_cleaning(
                    document, state_raw, transaction
                )
                self._fault("after-cleanup-intent", item.identifier)
                self._cleanup_committed_transaction(transaction)
                final_document = self._without_transaction(document)
                self._atomic_state_write(
                    final_document, state_raw, item.identifier, milestone="finalize"
                )
                state, state_raw = self._load_state()
            except Exception:
                if transaction is not None:
                    self._recover_incomplete()
                    state, state_raw = self._load_state()
                    records = self._records(state)
                raise

        if not actionable:
            document = self._state_document(
                operation=operation,
                status="complete",
                release_digest=plan.release_digest,
                records=records,
            )
            self._atomic_state_write(
                document, state_raw, "@provenance", milestone="provenance"
            )
        if set(records) != set(desired_snapshots):
            raise ValidationError("completed deployment has an incomplete artifact inventory")
        for identifier, expected in desired_snapshots.items():
            artifact = self.artifacts_by_id[identifier]
            destination, _root = self.target.resolve(artifact.target)
            actual = self._actual_snapshot(artifact, destination)
            if actual != expected or records[identifier] != expected.record():
                raise ValidationError(f"final deployment verification failed: {identifier}")
        return plan

    def apply_reconciled(self) -> DeploymentPlan:
        self._ensure_home_identity()
        self._recover_incomplete()
        return self.apply(self.reconcile_operation())

    def validate_installed(self, *, require_current_release: bool = True) -> int:
        desired, release_digest = self._desired()
        state, _raw = self._load_state()
        if state is None:
            raise ValidationError("no managed deployment provenance exists")
        if state.get("transaction") is not None:
            raise ValidationError("managed deployment recovery is required")
        if state.get("status") != "complete":
            raise ValidationError("managed deployment is incomplete")
        if require_current_release and state.get("release_digest") != release_digest:
            raise ValidationError("installed deployment does not match this source release")
        records = self._records(state)
        if require_current_release and set(records) != set(desired):
            raise ValidationError("installed artifact inventory differs from this source release")
        for identifier, record in records.items():
            artifact = self.artifacts_by_id.get(identifier)
            if artifact is None:
                if require_current_release:
                    raise ValidationError(f"stale installed artifact remains: {identifier}")
                continue
            destination, root = self.target.resolve(artifact.target)
            self._check_target_parent(destination, root)
            actual = self._actual_snapshot(artifact, destination)
            if not self._snapshot_matches_record(actual, record):
                raise ValidationError(f"installed artifact differs from provenance: {identifier}")
            self._run_validators(artifact, destination)
            if require_current_release and actual != desired[identifier]:
                raise ValidationError(f"installed artifact differs from source: {identifier}")
        return len(records)


def _target_from_arguments(arguments: argparse.Namespace) -> TargetContext:
    return TargetContext.from_environment(
        home=arguments.home,
        config=arguments.xdg_config_home,
        data=arguments.xdg_data_home,
        state=arguments.xdg_state_home,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, help="absolute Vanilla release root")
    parser.add_argument("--manifest", default="deployment/ownership-v2.toml")
    parser.add_argument("--release-id")
    parser.add_argument("--home")
    parser.add_argument("--xdg-config-home")
    parser.add_argument("--xdg-data-home")
    parser.add_argument("--xdg-state-home")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="print a zero-write deployment plan")
    plan.add_argument("operation", choices=("install", "update", "reconcile"))
    subparsers.add_parser("install", help="install into clean managed targets")
    subparsers.add_parser("update", help="update a proven managed deployment")
    subparsers.add_parser(
        "reconcile", help="install fresh or update according to managed provenance"
    )
    subparsers.add_parser("validate", help="validate installed managed files")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        deployment = ManagedDeployment(
            source_root=arguments.source_root,
            target=_target_from_arguments(arguments),
            manifest_relative=arguments.manifest,
            release_id=arguments.release_id,
        )
        if arguments.command == "plan":
            plan = (
                deployment.plan_reconciled()
                if arguments.operation == "reconcile"
                else deployment.plan(arguments.operation)
            )
            for item in plan.items:
                print(item.line())
            return 2 if plan.conflicts else 0
        if arguments.command in {"install", "update"}:
            plan = deployment.apply(arguments.command)
            for item in plan.items:
                print(item.line())
            return 0
        if arguments.command == "reconcile":
            plan = deployment.apply_reconciled()
            for item in plan.items:
                print(item.line())
            return 0
        count = deployment.validate_installed(require_current_release=True)
        print(f"valid\t{count}\tmanaged artifacts")
        return 0
    except DeploymentError as error:
        print(f"vanhyprarch managed deployment: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
