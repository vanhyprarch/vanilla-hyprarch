#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""Initialize create-once and backend-owned Vanilla user state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from managed_deploy import (
    ManifestError,
    SafetyError,
    TargetContext,
    _fsync_directory,
    _inside,
    _lexists,
    _mode,
    _validate_relative,
    _walk_existing_without_symlinks,
)


CREATE_ONCE_CLASSES = {"CREATE_ONCE_MACHINE", "CREATE_ONCE_USER"}
SUPPORTED_SCHEMA = 2
TRANSACTION_VERSION = 1
TEST_MODE_ENV = "VANHYPRARCH_CREATE_ONCE_TESTING"
TEST_FAULT_ENV = "VANHYPRARCH_CREATE_ONCE_TEST_FAULT_AT"


class InitializationError(Exception):
    """Base error for safe initialization refusal."""


class ConflictError(InitializationError):
    """Existing state is unsafe or ambiguous."""


@dataclass(frozen=True)
class InitTarget:
    xdg: TargetContext
    runtime: Path | None

    @classmethod
    def from_environment(
        cls,
        *,
        home: str | None = None,
        config: str | None = None,
        data: str | None = None,
        state: str | None = None,
        cache: str | None = None,
        runtime: str | None = None,
    ) -> "InitTarget":
        context = TargetContext.from_environment(
            home=home,
            config=config,
            data=data,
            state=state,
            cache=cache,
        )
        selected_runtime = runtime if runtime is not None else os.environ.get("XDG_RUNTIME_DIR")
        runtime_path = None
        if selected_runtime:
            runtime_path = TargetContext._absolute(selected_runtime, "XDG_RUNTIME_DIR")
        return cls(context, runtime_path)

    def environment(self) -> dict[str, str]:
        result = os.environ.copy()
        result.update(
            {
                "HOME": str(self.xdg.home),
                "XDG_CONFIG_HOME": str(self.xdg.config),
                "XDG_DATA_HOME": str(self.xdg.data),
                "XDG_STATE_HOME": str(self.xdg.state),
                "XDG_CACHE_HOME": str(self.xdg.cache),
            }
        )
        if self.runtime is not None:
            result["XDG_RUNTIME_DIR"] = str(self.runtime)
        else:
            result.pop("XDG_RUNTIME_DIR", None)
        return result


@dataclass(frozen=True)
class SeedArtifact:
    identifier: str
    source: PurePosixPath
    target: str
    ownership_class: str
    mode: int
    validators: tuple[str, ...]


@dataclass(frozen=True)
class InitHook:
    identifier: str
    kind: str
    state_artifact: str
    command: str | None
    command_artifact: str | None
    initialize_arguments: tuple[str, ...]
    status_arguments: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    action: str
    identifier: str
    target: str
    reason: str

    def line(self) -> str:
        return f"{self.action}\t{self.identifier}\t{self.target}\t{self.reason}"


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _regular_owned(path: Path) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ConflictError(f"could not inspect {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        kind = "symlink" if stat.S_ISLNK(metadata.st_mode) else "non-regular path"
        raise ConflictError(f"{kind} is forbidden for create-once state: {path}")
    if metadata.st_uid != os.getuid():
        raise ConflictError(f"create-once state has an unsafe owner: {path}")
    return metadata


def _read_regular(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SafetyError(f"not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read()
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SafetyError(f"file changed while reading: {path}")
        return data
    finally:
        os.close(descriptor)


def _ensure_directory(path: Path, root: Path, mode: int = 0o755) -> None:
    if not _inside(path, root):
        raise SafetyError(f"directory escapes target root: {path}")
    if not _lexists(root):
        _walk_existing_without_symlinks(root)
        root.mkdir(mode=mode, parents=True, exist_ok=True)
    relative = path.relative_to(root)
    candidates = [root]
    candidates.extend(
        root.joinpath(*relative.parts[:index])
        for index in range(1, len(relative.parts) + 1)
    )
    for current in candidates:
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            try:
                os.mkdir(current, mode)
            except FileExistsError:
                metadata = os.lstat(current)
            else:
                os.chmod(current, mode)
                _fsync_directory(current.parent)
                metadata = os.lstat(current)
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise SafetyError(f"unsafe directory path: {current}")
        if metadata.st_uid != os.getuid():
            raise SafetyError(f"directory is not owned by the target user: {current}")


class CreateOnceInitializer:
    """Manifest-driven Phase 3 initializer; never replaces create-once content."""

    def __init__(
        self,
        *,
        source_root: str | Path,
        target: InitTarget,
        manifest_relative: str = "deployment/ownership-v2.toml",
    ) -> None:
        if os.geteuid() == 0:
            raise SafetyError("create-once initialization must not run as root")
        source = Path(source_root)
        if not source.is_absolute() or not _lexists(source):
            raise ManifestError("source root must be an existing absolute directory")
        metadata = os.lstat(source)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SafetyError("source root must be a real directory")
        self.source_root = Path(os.path.normpath(source))
        _walk_existing_without_symlinks(self.source_root)
        self.target = target
        manifest_path = self._source_path(
            _validate_relative(manifest_relative, "ownership manifest")
        )
        try:
            with manifest_path.open("rb") as stream:
                self.manifest = tomllib.load(stream)
        except tomllib.TOMLDecodeError as error:
            raise ManifestError(f"invalid ownership manifest: {error}") from error
        self._load_manifest()

    def _source_path(self, relative: PurePosixPath) -> Path:
        path = self.source_root.joinpath(*relative.parts)
        if not _inside(path, self.source_root):
            raise SafetyError(f"source escapes release root: {relative}")
        _walk_existing_without_symlinks(path)
        try:
            metadata = os.lstat(path)
        except FileNotFoundError as error:
            raise ManifestError(f"missing source file: {relative}") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SafetyError(f"seed source must be a regular file: {relative}")
        return path

    def _load_manifest(self) -> None:
        if self.manifest.get("schema_version") != SUPPORTED_SCHEMA:
            raise ManifestError("unsupported ownership manifest schema")
        records = self.manifest.get("artifact")
        if not isinstance(records, list):
            raise ManifestError("ownership manifest artifacts are missing")
        self.records: dict[str, dict[str, object]] = {}
        self.seeds: list[SeedArtifact] = []
        destinations: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise ManifestError("artifact record must be a table")
            identifier = record.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in self.records:
                raise ManifestError("artifact identifiers must be unique and non-empty")
            self.records[identifier] = record
            if record.get("class") not in CREATE_ONCE_CLASSES:
                continue
            if record.get("status") != "implemented":
                continue
            if record.get("kind") != "file":
                raise ManifestError(f"{identifier} create-once kind must be file")
            source = _validate_relative(record.get("source"), f"{identifier} source")
            target = record.get("target")
            if not isinstance(target, str) or target in destinations:
                raise ManifestError(f"{identifier} target is invalid or duplicated")
            validators = record.get("validators", [])
            if not isinstance(validators, list) or not all(
                isinstance(item, str) and item for item in validators
            ):
                raise ManifestError(f"{identifier} validators must be strings")
            destinations.add(target)
            self.seeds.append(
                SeedArtifact(
                    identifier,
                    source,
                    target,
                    str(record["class"]),
                    _mode(record.get("mode"), f"{identifier} mode"),
                    tuple(validators),
                )
            )
        self.seeds.sort(key=lambda item: item.identifier)
        hooks = self.manifest.get("initializer", [])
        if not isinstance(hooks, list):
            raise ManifestError("initializer declarations must be tables")
        self.hooks: list[InitHook] = []
        seen_hooks: set[str] = set()
        for value in hooks:
            if not isinstance(value, dict):
                raise ManifestError("initializer declaration must be a table")
            identifier = value.get("id")
            kind = value.get("kind")
            state_artifact = value.get("state_artifact")
            if (
                not isinstance(identifier, str)
                or not identifier
                or identifier in seen_hooks
                or kind not in {"external-command", "artifact-command"}
                or not isinstance(state_artifact, str)
                or state_artifact not in self.records
            ):
                raise ManifestError("initializer declaration is invalid")
            seen_hooks.add(identifier)
            command = value.get("command")
            command_artifact = value.get("command_artifact")
            if kind == "external-command":
                if not isinstance(command, str) or not command or command_artifact is not None:
                    raise ManifestError(f"{identifier} external command is invalid")
            else:
                if (
                    not isinstance(command_artifact, str)
                    or command_artifact not in self.records
                    or command is not None
                ):
                    raise ManifestError(f"{identifier} command artifact is invalid")
            initialize = value.get("initialize_arguments", [])
            status_args = value.get("status_arguments", [])
            if not all(isinstance(item, str) and item for item in initialize + status_args):
                raise ManifestError(f"{identifier} command arguments are invalid")
            self.hooks.append(
                InitHook(
                    identifier,
                    kind,
                    state_artifact,
                    command if isinstance(command, str) else None,
                    command_artifact if isinstance(command_artifact, str) else None,
                    tuple(initialize),
                    tuple(status_args),
                )
            )
        transaction_id = self.manifest.get("create_once_transaction_state")
        if not isinstance(transaction_id, str) or transaction_id not in self.records:
            raise ManifestError("create-once transaction state declaration is missing")
        transaction = self.records[transaction_id]
        if transaction.get("class") != "BACKEND_OWNED":
            raise ManifestError("create-once transaction state must be BACKEND_OWNED")
        self.transaction_path, self.transaction_root = self.target.xdg.resolve(
            transaction["target"]
        )

    @staticmethod
    def _validate_seed(artifact: SeedArtifact, data: bytes) -> None:
        for validator in artifact.validators:
            if validator != "mimeapps-defaults":
                raise ManifestError(f"unknown create-once validator: {validator}")
            try:
                lines = data.decode("utf-8").splitlines()
            except UnicodeDecodeError as error:
                raise ManifestError("MIME seed must be UTF-8") from error
            if not lines or lines[0] != "[Default Applications]" or any(
                line.startswith("[") for line in lines[1:]
            ):
                raise ManifestError("MIME seed must contain only Default Applications")
            keys: set[str] = set()
            for line in lines[1:]:
                if not line or "=" not in line:
                    raise ManifestError("MIME seed contains an invalid line")
                mime_type, desktop = line.split("=", 1)
                if (
                    mime_type in keys
                    or re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", mime_type) is None
                    or re.fullmatch(r"[A-Za-z0-9_.+-]+\.desktop;", desktop) is None
                ):
                    raise ManifestError("MIME seed contains an invalid or duplicate mapping")
                keys.add(mime_type)

    def _fault(self, point: str, identifier: str) -> None:
        if os.environ.get(TEST_MODE_ENV) == "1":
            selected = os.environ.get(TEST_FAULT_ENV)
            if selected in {point, f"{point}:{identifier}"}:
                os._exit(197)

    def _existing_result(self, artifact: SeedArtifact, destination: Path) -> Result | None:
        if not _lexists(destination):
            return None
        _regular_owned(destination)
        return Result(
            "preserve-existing",
            artifact.identifier,
            str(destination),
            "user-owned file already exists",
        )

    def _mime_alternate(self, artifact: SeedArtifact) -> Result | None:
        if artifact.identifier != "mimeapps-config":
            return None
        locations = [self.target.xdg.config, self.target.xdg.data / "applications"]
        candidates: list[Path] = []
        for location in locations:
            if not _lexists(location):
                continue
            metadata = os.lstat(location)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ConflictError(f"unsafe MIME configuration directory: {location}")
            if metadata.st_uid != os.getuid():
                raise ConflictError(
                    f"MIME configuration directory has an unsafe owner: {location}"
                )
            candidates.extend(sorted(location.glob("*-mimeapps.list")))
            if location != self.target.xdg.config:
                candidates.append(location / "mimeapps.list")
        for candidate in candidates:
            if not _lexists(candidate):
                continue
            _regular_owned(candidate)
            return Result(
                "preserve-existing",
                artifact.identifier,
                str(candidate),
                "an existing standards-compliant user MIME configuration prevents seeding",
            )
        return None

    def _transaction_exists(self) -> bool:
        return _lexists(self.transaction_path)

    def _read_intent(self) -> dict[str, object]:
        metadata = os.lstat(self.transaction_path)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
        ):
            raise ConflictError("create-once transaction state is unsafe")
        allowed = {"intent.json", "published"}
        names = {item.name for item in self.transaction_path.iterdir()}
        if not names or not names <= allowed or "intent.json" not in names:
            raise ConflictError("create-once transaction state contains unknown data")
        intent_path = self.transaction_path / "intent.json"
        metadata = _regular_owned(intent_path)
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 65536:
            raise ConflictError("create-once transaction intent is unsafe")
        try:
            value = json.loads(intent_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ConflictError(f"create-once transaction intent is malformed: {error}") from error
        required = {"version", "operation_id", "artifact", "target", "candidate", "sha256", "mode"}
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("version") != TRANSACTION_VERSION
        ):
            raise ConflictError("create-once transaction intent has an invalid schema")
        identifier = value.get("artifact")
        artifact = next((item for item in self.seeds if item.identifier == identifier), None)
        if artifact is None:
            raise ConflictError("create-once transaction names an unknown artifact")
        destination, _ = self.target.xdg.resolve(artifact.target)
        operation_id = value.get("operation_id")
        expected_candidate = destination.parent / f".vanhyprarch-create-once-{operation_id}"
        if (
            not isinstance(operation_id, str)
            or len(operation_id) != 32
            or any(character not in "0123456789abcdef" for character in operation_id)
            or value.get("target") != str(destination)
            or value.get("candidate") != str(expected_candidate)
            or value.get("mode") != f"0{artifact.mode:03o}"
            or not isinstance(value.get("sha256"), str)
        ):
            raise ConflictError("create-once transaction intent does not match the manifest")
        return value

    def _clear_transaction(self, intent: dict[str, object]) -> None:
        candidate = Path(str(intent["candidate"]))
        if _lexists(candidate):
            _regular_owned(candidate)
            candidate.unlink()
            _fsync_directory(candidate.parent)
        for name in ("published", "intent.json"):
            path = self.transaction_path / name
            if _lexists(path):
                _regular_owned(path)
                path.unlink()
        if any(self.transaction_path.iterdir()):
            raise ConflictError("refusing to clean unknown transaction data")
        self.transaction_path.rmdir()
        _fsync_directory(self.transaction_path.parent)

    def recover(self) -> Result | None:
        if not self._transaction_exists():
            return None
        intent = self._read_intent()
        destination = Path(str(intent["target"]))
        if _lexists(destination):
            _regular_owned(destination)
            reason = (
                "preserved destination created during or concurrent with "
                "interrupted initialization"
            )
        else:
            reason = "discarded unpublished candidate from interrupted initialization"
        self._clear_transaction(intent)
        return Result("recovered", str(intent["artifact"]), str(destination), reason)

    def _begin_transaction(
        self, artifact: SeedArtifact, destination: Path, data: bytes
    ) -> dict[str, object]:
        _ensure_directory(self.transaction_path.parent, self.transaction_root, 0o700)
        try:
            os.mkdir(self.transaction_path, 0o700)
        except FileExistsError as error:
            raise ConflictError(
                "an incomplete create-once transaction requires recovery"
            ) from error
        os.chmod(self.transaction_path, 0o700)
        _fsync_directory(self.transaction_path.parent)
        operation_id = secrets.token_hex(16)
        intent: dict[str, object] = {
            "version": TRANSACTION_VERSION,
            "operation_id": operation_id,
            "artifact": artifact.identifier,
            "target": str(destination),
            "candidate": str(destination.parent / f".vanhyprarch-create-once-{operation_id}"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "mode": f"0{artifact.mode:03o}",
        }
        intent_path = self.transaction_path / "intent.json"
        descriptor = os.open(
            intent_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(_canonical_json(intent))
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        _fsync_directory(self.transaction_path)
        return intent

    def _create_seed(self, artifact: SeedArtifact) -> Result:
        source = self._source_path(artifact.source)
        data = _read_regular(source)
        self._validate_seed(artifact, data)
        destination, root = self.target.xdg.resolve(artifact.target)
        _ensure_directory(destination.parent, root)
        existing = self._existing_result(artifact, destination)
        if existing is not None:
            return existing
        alternate = self._mime_alternate(artifact)
        if alternate is not None:
            return alternate
        intent = self._begin_transaction(artifact, destination, data)
        candidate = Path(str(intent["candidate"]))
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0),
                artifact.mode,
            )
            try:
                os.fchmod(descriptor, artifact.mode)
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(descriptor)
            self._fault("before-publish", artifact.identifier)
            try:
                os.link(candidate, destination, follow_symlinks=False)
            except FileExistsError:
                result = self._existing_result(artifact, destination)
                assert result is not None
                self._clear_transaction(intent)
                return result
            _fsync_directory(destination.parent)
            self._fault("after-publish", artifact.identifier)
            final = _regular_owned(destination)
            if stat.S_IMODE(final.st_mode) != artifact.mode or _read_regular(destination) != data:
                raise ConflictError(f"created seed failed final verification: {destination}")
            marker = self.transaction_path / "published"
            marker_descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(marker_descriptor, b"published\n")
                os.fsync(marker_descriptor)
            finally:
                os.close(marker_descriptor)
            _fsync_directory(self.transaction_path)
            self._fault("after-metadata-commit", artifact.identifier)
            self._clear_transaction(intent)
            return Result(
                "seeded-by-vanilla",
                artifact.identifier,
                str(destination),
                f"created with mode 0{artifact.mode:03o}",
            )
        except Exception:
            # Normal exceptions recover through the same conservative path. Abrupt exits bypass it.
            self.recover()
            raise

    def _command_for_hook(self, hook: InitHook) -> list[str] | None:
        if hook.kind == "external-command":
            found = shutil.which(str(hook.command), path=self.target.environment().get("PATH"))
            return [found] if found else None
        assert hook.command_artifact is not None
        record = self.records[hook.command_artifact]
        destination, _ = self.target.xdg.resolve(record["target"])
        if not _lexists(destination):
            return None
        metadata = _regular_owned(destination)
        if stat.S_IMODE(metadata.st_mode) & 0o111 == 0:
            raise ConflictError(f"backend command is not executable: {destination}")
        return [str(destination)]

    def _hook_state(self, hook: InitHook) -> tuple[Path, bool]:
        record = self.records[hook.state_artifact]
        state_path, _ = self.target.xdg.resolve(record["target"])
        if not _lexists(state_path):
            return state_path, False
        _regular_owned(state_path)
        return state_path, True

    def _run_hook(self, hook: InitHook, *, initialize: bool) -> Result:
        state_path, exists = self._hook_state(hook)
        command = self._command_for_hook(hook)
        if command is None:
            if exists:
                return Result(
                    "already-initialized",
                    hook.identifier,
                    str(state_path),
                    "state exists; owner command is unavailable",
                )
            return Result(
                "external-hook",
                hook.identifier,
                str(state_path),
                "required owner command is unavailable",
            )
        if not initialize:
            owner_needs_initialization = not exists
            if command is not None and hook.status_arguments:
                completed = subprocess.run(
                    command + list(hook.status_arguments),
                    env=self.target.environment(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    shell=False,
                )
                if completed.returncode != 0:
                    detail = completed.stderr.strip() or completed.stdout.strip()
                    raise ConflictError(f"{hook.identifier} state is invalid: {detail}")
                owner_needs_initialization = owner_needs_initialization or (
                    '"missing"' in completed.stdout
                    or "=missing\n" in completed.stdout
                    or completed.stdout.endswith("=missing\n")
                )
            return Result(
                "backend-initialize"
                if owner_needs_initialization
                else "already-initialized",
                hook.identifier,
                str(state_path),
                "owner state classified through its read-only status interface",
            )
        if hook.kind == "external-command" and exists:
            return Result(
                "already-initialized",
                hook.identifier,
                str(state_path),
                "existing user directory configuration is preserved",
            )
        arguments = hook.initialize_arguments
        if hook.kind == "artifact-command" and self.target.runtime is None:
            raise ConflictError(f"{hook.identifier} requires an explicit XDG_RUNTIME_DIR")
        if self.target.runtime is not None:
            _ensure_directory(self.target.runtime, self.target.runtime, 0o700)
        completed = subprocess.run(
            command + list(arguments),
            env=self.target.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            detail = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"exit {completed.returncode}"
            )
            raise ConflictError(f"{hook.identifier} initialization failed: {detail}")
        return Result(
            "already-initialized" if exists else "backend-initialized",
            hook.identifier,
            str(state_path),
            completed.stdout.strip() or "owner initialization completed",
        )

    def plan(self) -> list[Result]:
        if self._transaction_exists():
            return [
                Result(
                    "recovery-required",
                    "create-once-transaction",
                    str(self.transaction_path),
                    "initialize must recover the interrupted operation",
                )
            ]
        results: list[Result] = []
        for artifact in self.seeds:
            data = _read_regular(self._source_path(artifact.source))
            self._validate_seed(artifact, data)
            destination, root = self.target.xdg.resolve(artifact.target)
            _walk_existing_without_symlinks(destination.parent)
            existing = self._existing_result(artifact, destination)
            if existing is not None:
                results.append(existing)
                continue
            alternate = self._mime_alternate(artifact)
            results.append(
                alternate
                or Result(
                    "create",
                    artifact.identifier,
                    str(destination),
                    "create-once target is absent",
                )
            )
        for hook in self.hooks:
            results.append(self._run_hook(hook, initialize=False))
        return results

    def initialize(self) -> list[Result]:
        results: list[Result] = []
        recovered = self.recover()
        if recovered is not None:
            results.append(recovered)
        for artifact in self.seeds:
            results.append(self._create_seed(artifact))
        for hook in self.hooks:
            results.append(self._run_hook(hook, initialize=True))
        return results

    def validate(self) -> list[Result]:
        if self._transaction_exists():
            raise ConflictError("create-once recovery is required")
        results: list[Result] = []
        for artifact in self.seeds:
            destination, _ = self.target.xdg.resolve(artifact.target)
            if _lexists(destination):
                _regular_owned(destination)
                results.append(
                    Result(
                        "user-customized/preserved",
                        artifact.identifier,
                        str(destination),
                        "safe user-owned create-once file",
                    )
                )
                continue
            alternate = self._mime_alternate(artifact)
            if alternate is not None:
                results.append(alternate)
                continue
            raise ConflictError(f"create-once target is missing: {destination}")
        for hook in self.hooks:
            result = self._run_hook(hook, initialize=False)
            if result.action in {"backend-initialize", "external-hook"}:
                raise ConflictError(f"backend state is not initialized: {hook.identifier}")
            results.append(
                Result(
                    "valid",
                    hook.identifier,
                    result.target,
                    "authoritative owner state is valid",
                )
            )
        return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--manifest", default="deployment/ownership-v2.toml")
    parser.add_argument("--home")
    parser.add_argument("--xdg-config-home")
    parser.add_argument("--xdg-data-home")
    parser.add_argument("--xdg-state-home")
    parser.add_argument("--xdg-cache-home")
    parser.add_argument("--xdg-runtime-dir")
    parser.add_argument("command", choices=("plan", "initialize", "validate"))
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        initializer = CreateOnceInitializer(
            source_root=arguments.source_root,
            target=InitTarget.from_environment(
                home=arguments.home,
                config=arguments.xdg_config_home,
                data=arguments.xdg_data_home,
                state=arguments.xdg_state_home,
                cache=arguments.xdg_cache_home,
                runtime=arguments.xdg_runtime_dir,
            ),
            manifest_relative=arguments.manifest,
        )
        operation = getattr(initializer, arguments.command)
        results = operation()
        for result in results:
            print(result.line())
        conflicts = {"conflict", "recovery-required", "external-hook"}
        return 2 if any(result.action in conflicts for result in results) else 0
    except (InitializationError, ManifestError, SafetyError) as error:
        print(f"vanhyprarch create-once initialization: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
