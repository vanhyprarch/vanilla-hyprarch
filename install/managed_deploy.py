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
VALID_ACTIONS = {"create", "replace", "remove", "preserve", "conflict"}


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

    @classmethod
    def build(
        cls,
        *,
        home: str | Path,
        config: str | Path | None = None,
        data: str | Path | None = None,
        state: str | Path | None = None,
    ) -> "TargetContext":
        home_path = cls._absolute(home, "HOME")
        return cls(
            home=home_path,
            config=cls._absolute(config or home_path / ".config", "XDG_CONFIG_HOME"),
            data=cls._absolute(data or home_path / ".local/share", "XDG_DATA_HOME"),
            state=cls._absolute(state or home_path / ".local/state", "XDG_STATE_HOME"),
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
        )

    def resolve(self, expression: object) -> tuple[Path, Path]:
        if not isinstance(expression, str) or not expression or "\x00" in expression:
            raise ManifestError("target must be a non-empty string without NUL")
        prefixes = (
            ("${XDG_CONFIG_HOME:-$HOME/.config}", self.config),
            ("${XDG_DATA_HOME:-$HOME/.local/share}", self.data),
            ("${XDG_STATE_HOME:-$HOME/.local/state}", self.state),
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
        return tuple(item for item in self.items if item.action == "conflict")

    @property
    def changes(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if item.action in {"create", "replace", "remove"})


@dataclass
class _PreparedReplacement:
    destination: Path
    container: Path
    backup: Path | None
    created: bool
    old_snapshot: Snapshot | None


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
        for record in records:
            if not isinstance(record, dict):
                raise ConflictError("deployment provenance artifact record is invalid")
            identifier = record.get("id")
            target = record.get("target")
            entries = record.get("entries")
            if not isinstance(identifier, str) or identifier in seen_ids:
                raise ConflictError("deployment provenance has duplicate artifact ids")
            if not isinstance(target, str) or target in seen_targets:
                raise ConflictError("deployment provenance has duplicate artifact targets")
            if record.get("kind") not in {"file", "tree"} or not isinstance(entries, list):
                raise ConflictError(f"deployment provenance record is malformed: {identifier}")
            if record.get("class") != PHASE2_CLASS:
                raise ConflictError(
                    f"deployment provenance ownership class is invalid: {identifier}"
                )
            if record.get("digest") != _sha256_bytes(_canonical_bytes(tuple(entries))):
                raise ConflictError(f"deployment provenance digest is invalid: {identifier}")
            self.target.resolve(target)
            seen_ids.add(identifier)
            seen_targets.add(target)
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

    def _copy_regular(self, source: Path, destination: Path, mode: int) -> None:
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
                        os.fsync(destination_descriptor)
            finally:
                os.close(destination_descriptor)
        finally:
            os.close(source_descriptor)

    def _stage(self, artifact: Artifact, destination: Path, root: Path) -> tuple[Path, Path, Snapshot]:
        self._ensure_parent(destination, root)
        container = Path(tempfile.mkdtemp(prefix=".vanhyprarch-stage-", dir=destination.parent))
        os.chmod(container, 0o700)
        payload = container / "payload"
        try:
            source = self._source_path(artifact.source, artifact.kind)
            if artifact.kind == "file":
                assert artifact.mode is not None
                self._copy_regular(source, payload, artifact.mode)
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
                        self._copy_regular(source_path, staged, mode)
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
            return container, payload, desired
        except Exception:
            _remove_controlled(container)
            raise

    def _prepare_replacement(
        self,
        artifact: Artifact,
        destination: Path,
        root: Path,
        create: bool,
        expected_desired: Snapshot,
        expected_previous: dict[str, object] | None,
    ) -> tuple[_PreparedReplacement, Snapshot]:
        container, payload, desired = self._stage(artifact, destination, root)
        backup = payload
        old_snapshot = None
        created = not _lexists(destination)
        switched = False
        try:
            if desired != expected_desired:
                raise ConflictError(f"source changed while planning: {artifact.identifier}")
            if create and not created:
                raise ConflictError(f"destination appeared during create: {destination}")
            if not create:
                if created:
                    raise ConflictError(f"managed destination disappeared during update: {destination}")
                old_snapshot = self._actual_snapshot(artifact, destination)
                if expected_previous is None or not self._snapshot_matches_record(
                    old_snapshot, expected_previous
                ):
                    raise ConflictError(
                        f"managed destination changed while planning: {artifact.identifier}"
                    )
                _atomic_exchange(payload, destination)
                switched = True
                self.fault_hook("after-backup", artifact.identifier)
            else:
                os.replace(payload, destination)
                switched = True
            _fsync_directory(destination.parent)
            self.fault_hook("after-replace", artifact.identifier)
            installed = self._actual_snapshot(artifact, destination)
            self._run_validators(artifact, destination)
            if installed != desired:
                raise ValidationError(f"installed verification failed: {artifact.identifier}")
            return (
                _PreparedReplacement(destination, container, None if created else backup, created, old_snapshot),
                desired,
            )
        except Exception:
            if switched:
                if _lexists(destination):
                    _remove_controlled(destination)
                if not created and _lexists(backup):
                    os.replace(backup, destination)
                    _fsync_directory(destination.parent)
                    if old_snapshot is not None:
                        restored = self._actual_snapshot(artifact, destination)
                        if restored != old_snapshot:
                            raise ValidationError(
                                f"rollback verification failed: {artifact.identifier}"
                            )
            _remove_controlled(container)
            raise

    def _prepare_removal(
        self, identifier: str, target_text: str, record: dict[str, object]
    ) -> _PreparedReplacement | None:
        destination, root = self.target.resolve(target_text)
        self._ensure_parent(destination, root)
        if not _lexists(destination):
            return None
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
        old = self._actual_snapshot(synthetic, destination)
        if not self._snapshot_matches_record(old, record):
            raise ConflictError(f"stale artifact changed before removal: {identifier}")
        container = Path(tempfile.mkdtemp(prefix=".vanhyprarch-stage-", dir=destination.parent))
        os.chmod(container, 0o700)
        backup = container / "backup"
        try:
            os.replace(destination, backup)
            _fsync_directory(destination.parent)
            self.fault_hook("after-backup", identifier)
            return _PreparedReplacement(destination, container, backup, False, old)
        except Exception:
            if _lexists(backup):
                os.replace(backup, destination)
                _fsync_directory(destination.parent)
            _remove_controlled(container)
            raise

    def _rollback_prepared(self, prepared: _PreparedReplacement | None, artifact: Artifact | None) -> None:
        if prepared is None:
            return
        if _lexists(prepared.destination):
            _remove_controlled(prepared.destination)
        if prepared.backup is not None and _lexists(prepared.backup):
            os.replace(prepared.backup, prepared.destination)
            _fsync_directory(prepared.destination.parent)
            if prepared.old_snapshot is not None:
                verifier = artifact or Artifact(
                    identifier=prepared.old_snapshot.identifier,
                    source=PurePosixPath("unused"),
                    target=prepared.old_snapshot.target,
                    ownership_class=PHASE2_CLASS,
                    kind=prepared.old_snapshot.kind,
                    mode=None,
                    directory_mode=None,
                    file_mode=None,
                    executable_mode=None,
                    executable=(),
                    included=(),
                    validators=(),
                )
                restored = self._actual_snapshot(verifier, prepared.destination)
                if restored != prepared.old_snapshot:
                    raise ValidationError(
                        f"rollback verification failed: {prepared.old_snapshot.identifier}"
                    )
        _remove_controlled(prepared.container)

    def _finish_prepared(self, prepared: _PreparedReplacement | None) -> None:
        if prepared is None:
            return
        if prepared.backup is not None and _lexists(prepared.backup):
            _remove_controlled(prepared.backup)
        _remove_controlled(prepared.container)

    def _state_document(
        self,
        *,
        operation: str,
        status: str,
        release_digest: str,
        records: dict[str, dict[str, object]],
    ) -> dict[str, object]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "ownership_manifest_schema": SUPPORTED_MANIFEST_SCHEMA,
            "status": status,
            "operation": operation if status == "partial" else "complete",
            "release_id": self.release_id,
            "release_digest": release_digest,
            "artifacts": [records[name] for name in sorted(records)],
        }

    def _atomic_state_write(self, document: dict[str, object], old_raw: bytes | None, identifier: str) -> None:
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
                os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            self.fault_hook("before-state-write", identifier)
            os.replace(temporary, self.provenance_path)
            _fsync_directory(self.provenance_path.parent)
            self.fault_hook("after-state-replace", identifier)
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

    def apply(self, operation: str) -> DeploymentPlan:
        self._ensure_home_identity()
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
            old_state_raw = state_raw
            prepared: _PreparedReplacement | None = None
            artifact: Artifact | None = self.artifacts_by_id.get(item.identifier)
            try:
                if item.action in {"create", "replace"}:
                    assert artifact is not None
                    destination, root = self.target.resolve(artifact.target)
                    prepared, installed_snapshot = self._prepare_replacement(
                        artifact,
                        destination,
                        root,
                        item.action == "create",
                        desired_snapshots[item.identifier],
                        records.get(item.identifier),
                    )
                    records[item.identifier] = installed_snapshot.record()
                elif item.action == "remove":
                    prior = records[item.identifier]
                    prepared = self._prepare_removal(item.identifier, item.target, prior)
                    records.pop(item.identifier)
                remaining = index + 1 < len(actionable)
                document = self._state_document(
                    operation=operation,
                    status="partial" if remaining else "complete",
                    release_digest=plan.release_digest,
                    records=records,
                )
                self._atomic_state_write(document, old_state_raw, item.identifier)
                state_raw = self.provenance_path.read_bytes()
                self._finish_prepared(prepared)
            except Exception:
                self._rollback_prepared(prepared, artifact)
                raise

        if not actionable:
            document = self._state_document(
                operation=operation,
                status="complete",
                release_digest=plan.release_digest,
                records=records,
            )
            self._atomic_state_write(document, state_raw, "@provenance")
        if set(records) != set(desired_snapshots):
            raise ValidationError("completed deployment has an incomplete artifact inventory")
        for identifier, expected in desired_snapshots.items():
            artifact = self.artifacts_by_id[identifier]
            destination, _root = self.target.resolve(artifact.target)
            actual = self._actual_snapshot(artifact, destination)
            if actual != expected or records[identifier] != expected.record():
                raise ValidationError(f"final deployment verification failed: {identifier}")
        return plan

    def validate_installed(self, *, require_current_release: bool = True) -> int:
        desired, release_digest = self._desired()
        state, _raw = self._load_state()
        if state is None:
            raise ValidationError("no managed deployment provenance exists")
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
    plan.add_argument("operation", choices=("install", "update"))
    subparsers.add_parser("install", help="install into clean managed targets")
    subparsers.add_parser("update", help="update a proven managed deployment")
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
            plan = deployment.plan(arguments.operation)
            for item in plan.items:
                print(item.line())
            return 2 if plan.conflicts else 0
        if arguments.command in {"install", "update"}:
            plan = deployment.apply(arguments.command)
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
