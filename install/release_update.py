#!/usr/bin/env python3
"""Offline, exact-bundle Vanilla release upgrade driver.

Discovery, download, confirmation, and user-facing update selection belong to
the future installed bootstrap. This module requires an explicit local bundle.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import pwd
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release import build as contract  # noqa: E402
from install.release_identity import IdentityError, InstalledReleaseIdentity  # noqa: E402
from install.release_migrations import (  # noqa: E402
    MigrationContext, MigrationError, MigrationRegistry, MigrationRunner,
)
from install.update_journal import JournalError, UpdateJournal  # noqa: E402
from install.update_journal import _identities  # noqa: E402


STAGE_RELATIVE = Path("var/lib/vanhyprarch-update/staging")
STAGES = ("migrations", "system-integration", "managed-deployment", "create-once")
AUTHORITY_FILES = (
    "install/system_integration.py", "install/managed_deploy.py",
    "install/create_once.py", "install/sddm_login_integration.py",
)


class UpdateError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class TargetUser:
    name: str
    uid: int
    gid: int
    home: Path
    groups: tuple[int, ...]
    xdg_config: Path | None = None
    xdg_data: Path | None = None
    xdg_state: Path | None = None
    xdg_cache: Path | None = None

    @classmethod
    def resolve(cls, name: str, *, system_root: Path = Path("/"),
                xdg_config: Path | None = None, xdg_data: Path | None = None,
                xdg_state: Path | None = None, xdg_cache: Path | None = None) -> "TargetUser":
        if not name or name == "root" or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in name):
            raise UpdateError("preflight failed", "an explicit non-root target username is required")
        try:
            account = pwd.getpwnam(name)
        except KeyError as error:
            raise UpdateError("preflight failed", f"target account does not exist: {name}") from error
        home = Path(account.pw_dir)
        if account.pw_uid == 0 or not home.is_absolute() or ".." in home.parts:
            raise UpdateError("preflight failed", "target account has an unsafe identity or home")
        actual_home = system_root / home.relative_to("/")
        try:
            info = actual_home.lstat()
        except FileNotFoundError as error:
            raise UpdateError("preflight failed", "target home is absent") from error
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != account.pw_uid
                or info.st_mode & 0o022 or actual_home.resolve() != actual_home):
            raise UpdateError("preflight failed", "target home has unsafe type, owner, or mode")
        overrides = (xdg_config, xdg_data, xdg_state, xdg_cache)
        for path in overrides:
            if path is not None and (not path.is_absolute() or ".." in path.parts
                                     or path.resolve(strict=False) != path):
                raise UpdateError("preflight failed", "XDG directory override is unsafe")
        return cls(name, account.pw_uid, account.pw_gid, home,
                   tuple(os.getgrouplist(name, account.pw_gid)), *overrides)


@dataclass(frozen=True)
class Bundle:
    stage: Path
    tree: Path
    metadata_path: Path
    artifact_path: Path
    metadata: dict[str, Any]
    metadata_bytes: bytes


class BundleStore:
    """Root-controlled, bounded exact target material retained across reboot."""

    def __init__(self, root: Path = Path("/"), *, uid: int = 0, gid: int = 0,
                 fsync: Callable[[int], None] = os.fsync) -> None:
        if not root.is_absolute() or root.is_symlink() or root.resolve(strict=True) != root:
            raise UpdateError("preflight failed", "system root must be an absolute real directory")
        self.root, self.uid, self.gid, self.fsync = root, uid, gid, fsync
        self.parent = root / STAGE_RELATIVE
        self.preview_parent = root / "run"

    def _directory(self, path: Path, *, create: bool = False, exact: int | None = None) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            if not create:
                raise UpdateError("preflight failed", f"staging directory is absent: {path}") from None
            path.mkdir(mode=exact or 0o755)
            path.chmod(exact or 0o755)
            self._sync_directory(path.parent)
            info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or info.st_mode & 0o022
                or (exact is not None and stat.S_IMODE(info.st_mode) != exact)):
            raise UpdateError("preflight failed", f"unsafe staging directory: {path}")

    def _sync_directory(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _parents(self, *, create: bool) -> None:
        current = self.root
        self._directory(current)
        for component in STAGE_RELATIVE.parts:
            current = current / component
            self._directory(current, create=create, exact=0o755)

    def _copy_verified_input(self, source_path: Path, destination: Path, maximum: int) -> None:
        with contract._open_regular(source_path, maximum, "release input") as (source, info):
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as target:
                    remaining = info.st_size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise UpdateError("preflight failed", "release input changed during staging")
                        target.write(chunk)
                        remaining -= len(chunk)
                    target.flush()
                    self.fsync(target.fileno())
                os.fchmod(descriptor, 0o644)
                self.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _extract(self, archive_path: Path, destination: Path, metadata: dict[str, Any]) -> Path:
        destination.mkdir(mode=0o755)
        expected_root = contract.archive_root(metadata["version"])
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                contract._safe_path(member.name)
                if member.name != expected_root and not member.name.startswith(expected_root + "/"):
                    raise UpdateError("preflight failed", "archive root changed during extraction")
                path = destination.joinpath(*Path(member.name).parts)
                if member.isdir():
                    path.mkdir(mode=0o755)
                    path.chmod(0o755)
                elif member.isfile():
                    source = archive.extractfile(member)
                    if source is None:
                        raise UpdateError("preflight failed", "archive member could not be read")
                    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                    try:
                        with os.fdopen(descriptor, "wb", closefd=False) as target:
                            shutil.copyfileobj(source, target, 1024 * 1024)
                            target.flush()
                            self.fsync(target.fileno())
                        os.fchmod(descriptor, member.mode)
                        self.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                        source.close()
                else:
                    raise UpdateError("preflight failed", "archive member type changed during extraction")
        for directory, _children, _files in os.walk(destination, topdown=False):
            self._sync_directory(Path(directory))
        return destination / expected_root

    def _check_file(self, path: Path, *, mode: int | None = None) -> os.stat_result:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or info.st_nlink != 1
                or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
            raise UpdateError("transaction mismatch", f"unsafe staged release file: {path}")
        return info

    def _verify_tree(self, bundle: Bundle) -> None:
        self._directory(bundle.stage, exact=0o755)
        source_dir = bundle.stage / "source"
        self._directory(source_dir, exact=0o755)
        self._directory(bundle.tree, exact=0o755)
        if set(path.name for path in bundle.stage.iterdir()) != {
                "source", "release.json", bundle.metadata["artifact"]["name"]}:
            raise UpdateError("transaction mismatch", "staged bundle contains unexpected content")
        if {path.name for path in source_dir.iterdir()} != {bundle.tree.name}:
            raise UpdateError("transaction mismatch", "staged source has an unexpected root")
        expected: set[Path] = set()
        with tarfile.open(bundle.artifact_path, "r:gz") as archive:
            for member in archive:
                relative = Path(member.name)
                expected.add(relative)
                path = source_dir / relative
                info = path.lstat()
                if ((info.st_uid, info.st_gid) != (self.uid, self.gid)
                        or stat.S_IMODE(info.st_mode) != member.mode
                        or (member.isdir() and not stat.S_ISDIR(info.st_mode))
                        or (member.isfile() and (not stat.S_ISREG(info.st_mode)
                                                or info.st_nlink != 1))):
                    raise UpdateError("transaction mismatch", f"staged source differs from artifact: {member.name}")
                if member.isfile():
                    source = archive.extractfile(member)
                    assert source is not None
                    with path.open("rb") as installed:
                        while chunk := source.read(1024 * 1024):
                            if installed.read(len(chunk)) != chunk:
                                raise UpdateError("transaction mismatch", f"staged file differs: {member.name}")
                        if installed.read(1):
                            raise UpdateError("transaction mismatch", f"staged file grew: {member.name}")
        actual = {path.relative_to(source_dir) for path in source_dir.rglob("*")}
        if actual != expected:
            raise UpdateError("transaction mismatch", "staged source has missing or extra members")
        for relative in AUTHORITY_FILES:
            self._check_file(bundle.tree / relative)
        MigrationRegistry(bundle.tree, target=bundle.metadata)

    def _inspect(self, stage: Path, expected_digest: str, *, preview: bool = False) -> Bundle:
        if preview:
            self._directory(self.preview_parent)
            if stage.parent != self.preview_parent or not stage.name.startswith("vanhyprarch-preview-"):
                raise UpdateError("preflight failed", "unsafe release preview path")
        else:
            self._parents(create=False)
        self._directory(stage, exact=0o755)
        metadata_path = stage / "release.json"
        self._check_file(metadata_path, mode=0o644)
        with contract._open_regular(metadata_path, contract.MAX_METADATA, "staged metadata") as (source, info):
            metadata_bytes = source.read(info.st_size + 1)
        metadata = contract.parse_metadata(metadata_bytes)
        if metadata["artifact"]["sha256"] != expected_digest:
            raise UpdateError("transaction mismatch", "staged target digest differs from journal")
        artifact_path = stage / metadata["artifact"]["name"]
        self._check_file(artifact_path, mode=0o644)
        if contract.verify(metadata_path, artifact_path) != metadata:
            raise UpdateError("transaction mismatch", "staged bundle verification disagrees")
        tree = stage / "source" / contract.archive_root(metadata["version"])
        bundle = Bundle(stage, tree, metadata_path, artifact_path, metadata, metadata_bytes)
        self._verify_tree(bundle)
        return bundle

    def prepare(self, metadata_path: Path, artifact_path: Path, *, permanent: bool) -> Bundle:
        if not metadata_path.is_absolute() or not artifact_path.is_absolute():
            raise UpdateError("preflight failed", "release bundle paths must be absolute")
        metadata = contract.verify(metadata_path, artifact_path)
        if permanent:
            self._parents(create=True)
        else:
            self._directory(self.preview_parent)
        destination = self.parent / metadata["artifact"]["sha256"]
        if permanent:
            unexpected = [entry.name for entry in self.parent.iterdir() if entry != destination]
            if unexpected:
                raise UpdateError("preflight failed", "unrelated retained staging requires review")
        if permanent and os.path.lexists(destination):
            bundle = self._inspect(destination, metadata["artifact"]["sha256"])
            if bundle.metadata != metadata:
                raise UpdateError("transaction mismatch", "existing staged target differs from input")
            return bundle
        temporary = Path(tempfile.mkdtemp(prefix=(".staging-" if permanent
                                                 else "vanhyprarch-preview-"),
                                          dir=self.parent if permanent else self.preview_parent))
        published = False
        try:
            copied_metadata = temporary / "release.json"
            copied_artifact = temporary / metadata["artifact"]["name"]
            self._copy_verified_input(metadata_path, copied_metadata, contract.MAX_METADATA)
            self._copy_verified_input(artifact_path, copied_artifact, contract.MAX_ARTIFACT)
            if contract.verify(copied_metadata, copied_artifact) != metadata:
                raise UpdateError("preflight failed", "release input changed during staging")
            self._extract(copied_artifact, temporary / "source", metadata)
            temporary.chmod(0o755)
            self._sync_directory(temporary)
            self._sync_directory(temporary.parent)
            bundle = self._inspect(temporary, metadata["artifact"]["sha256"],
                                   preview=not permanent)
            if permanent:
                if os.path.lexists(destination):
                    raise UpdateError("transaction mismatch", "target staging appeared before publication")
                os.rename(temporary, destination)
                published = True
                self._sync_directory(self.parent)
                return self._inspect(destination, metadata["artifact"]["sha256"])
            return bundle
        finally:
            if not published and (permanent or sys.exc_info()[0] is not None):
                shutil.rmtree(temporary)

    def preview_cleanup(self, bundle: Bundle) -> None:
        if (bundle.stage.parent != self.preview_parent
                or not bundle.stage.name.startswith("vanhyprarch-preview-")):
            raise UpdateError("preflight failed", "unsafe preview cleanup path")
        shutil.rmtree(bundle.stage)
        self._sync_directory(self.preview_parent)

    def resume(self, digest: str) -> Bundle:
        if contract.SHA64.fullmatch(digest) is None:
            raise UpdateError("transaction mismatch", "journal target digest is invalid")
        return self._inspect(self.parent / digest, digest)

    def remove_committed(self, bundle: Bundle) -> None:
        if bundle.stage != self.parent / bundle.metadata["artifact"]["sha256"]:
            raise UpdateError("terminal cleanup required", "unsafe committed staging path")
        self._inspect(bundle.stage, bundle.metadata["artifact"]["sha256"])
        shutil.rmtree(bundle.stage)
        self._sync_directory(self.parent)


class AuthorityRunner:
    """Invoke the target release's existing authorities with fixed arguments."""

    @staticmethod
    def _user_environment(user: TargetUser) -> dict[str, str]:
        runtime = Path(f"/run/user/{user.uid}")
        try:
            info = runtime.lstat()
        except FileNotFoundError as error:
            raise UpdateError("preflight failed", "target user's XDG runtime directory is unavailable") from error
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != user.uid
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise UpdateError("preflight failed", "target user's XDG runtime directory is unsafe")
        return {
            "PATH": "/usr/bin:/bin", "HOME": str(user.home), "USER": user.name,
            "LOGNAME": user.name, "XDG_RUNTIME_DIR": str(runtime),
            "XDG_CONFIG_HOME": str(user.xdg_config or user.home / ".config"),
            "XDG_DATA_HOME": str(user.xdg_data or user.home / ".local/share"),
            "XDG_STATE_HOME": str(user.xdg_state or user.home / ".local/state"),
            "XDG_CACHE_HOME": str(user.xdg_cache or user.home / ".cache"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def invoke(self, stage: str, operation: str, bundle: Bundle, user: TargetUser) -> str:
        python = "/usr/bin/python3"
        root = str(bundle.tree)
        if stage == "system-integration":
            command = [python, f"{root}/install/system_integration.py", operation,
                       "--lifecycle", "upgrade", "--source-root", root,
                       "--target-user", user.name]
            user_arguments: dict[str, Any] = {}
            environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        elif stage == "managed-deployment":
            command = [python, f"{root}/install/managed_deploy.py", "--source-root", root,
                       "--release-id", bundle.metadata["commit"], "--home", str(user.home)]
            command += ["plan", "update"] if operation == "plan" else [
                "update" if operation == "apply" else "validate"]
            environment = self._user_environment(user)
            user_arguments = {"user": user.uid, "group": user.gid,
                              "extra_groups": user.groups}
        elif stage == "create-once":
            command = [python, f"{root}/install/create_once.py", "--source-root", root,
                       "--lifecycle", "upgrade", "--home", str(user.home),
                       "initialize" if operation == "apply" else operation]
            environment = self._user_environment(user)
            user_arguments = {"user": user.uid, "group": user.gid,
                              "extra_groups": user.groups}
        else:
            raise UpdateError("preflight failed", f"unsupported authority stage: {stage}")
        result = subprocess.run(command, env=environment, cwd="/", text=True,
                                capture_output=True, check=False, **user_arguments)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise UpdateError("authority failed", f"{stage} {operation} failed ({result.returncode}): {detail[:2000]}")
        return result.stdout.strip()


@dataclass(frozen=True)
class UpdatePlan:
    source: dict[str, Any]
    target: dict[str, Any]
    migrations: tuple[tuple[int, tuple[str, ...]], ...]
    authorities: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source["version"], "target": self.target["version"],
            "target_sha256": self.target["artifact"]["sha256"],
            "migrations": [{"id": identifier, "plan": list(lines)}
                           for identifier, lines in self.migrations],
            "authorities": self.authorities,
        }


class ReleaseUpdate:
    """A single exact target transaction; no discovery or download."""

    def __init__(self, target_user: TargetUser, *, root: Path = Path("/"),
                 uid: int = 0, gid: int = 0, testing: bool = False,
                 authority: AuthorityRunner | None = None,
                 fsync: Callable[[int], None] = os.fsync) -> None:
        if not testing and (root != Path("/") or uid != 0 or gid != 0):
            raise UpdateError("preflight failed", "alternate root is available only to isolated tests")
        self.user = target_user
        self.root = root
        self.uid = uid
        self.gid = gid
        self.testing = testing
        self.identity = InstalledReleaseIdentity(root, uid=uid, gid=gid, fsync=fsync)
        self.journal = UpdateJournal(root, uid=uid, gid=gid, fsync=fsync)
        self.store = BundleStore(root, uid=uid, gid=gid, fsync=fsync)
        self.authority = authority or AuthorityRunner()

    def _require_privilege(self) -> None:
        if not self.testing and os.geteuid() != 0:
            raise UpdateError("preflight failed", "release update requires root")

    def _installed(self) -> dict[str, Any]:
        value = self.identity.validate()
        assert value is not None
        return value

    @staticmethod
    def _compatible(source: dict[str, Any], target: dict[str, Any]) -> None:
        _identities(source, target)
        if source["architecture"] != target["architecture"] or target["architecture"] != platform.machine():
            raise UpdateError("incompatible target", "target architecture differs from installed machine")
        if source["channel"] == "stable" and target["channel"] != "stable":
            raise UpdateError("incompatible target", "stable releases cannot upgrade to candidates")
        if source["channel"] == "candidate":
            old_base = contract.version_tuple(source["version"])[:3]
            new_base = contract.version_tuple(target["version"])[:3]
            if old_base != new_base:
                raise UpdateError("incompatible target", "candidate upgrade must stay in its product version")
        if target["update_protocol"] != contract.UPDATE_PROTOCOL:
            raise UpdateError("incompatible target", "unsupported target update protocol")

    def _migration_plan(self, registry: MigrationRegistry, source: dict[str, Any],
                        target: dict[str, Any], bundle: Bundle) -> tuple[tuple[int, tuple[str, ...]], ...]:
        result: list[tuple[int, tuple[str, ...]]] = []
        for identifier in registry.range_from(source["migration_level"]):
            module = registry._module(identifier)
            context = MigrationContext(self.root, bundle.tree,
                                       copy.deepcopy(source), copy.deepcopy(target),
                                       identifier, registry.entries[identifier]["scope"])
            lines = module.plan(context)
            if (type(lines) is not list or not lines
                    or any(type(line) is not str or not 1 <= len(line) <= 320
                           or not line.isprintable() for line in lines)):
                raise UpdateError("preflight failed", f"migration {identifier:04d} returned an invalid plan")
            result.append((identifier, tuple(lines)))
        return tuple(result)

    def plan(self, metadata_path: Path, artifact_path: Path) -> UpdatePlan:
        self._require_privilege()
        source = self._installed()
        target = contract.verify(metadata_path, artifact_path)
        active = self.journal.inspect()
        if active is not None:
            kind = ("resume required" if active["target"]["artifact_sha256"] ==
                    target["artifact"]["sha256"] else "transaction mismatch")
            raise UpdateError(kind, "active update journal must be resumed with its exact retained target")
        self._compatible(source, target)
        bundle = self.store.prepare(metadata_path, artifact_path, permanent=False)
        try:
            if bundle.metadata != target:
                raise UpdateError("preflight failed", "release bundle changed during preflight")
            registry = MigrationRegistry(bundle.tree, target=target)
            migrations = self._migration_plan(registry, source, target, bundle)
            plans = {stage: self.authority.invoke(stage, "plan", bundle, self.user)
                     for stage in STAGES[1:]}
            return UpdatePlan(source, target, migrations, plans)
        finally:
            self.store.preview_cleanup(bundle)

    def _validate_all(self, source: dict[str, Any], bundle: Bundle) -> None:
        registry = MigrationRegistry(bundle.tree, target=bundle.metadata)
        MigrationRunner(registry, self.journal, source, bundle.metadata).validate_level()
        for stage in STAGES[1:]:
            self.authority.invoke(stage, "validate", bundle, self.user)

    def _run_transaction(self, source: dict[str, Any], bundle: Bundle) -> dict[str, Any]:
        target = bundle.metadata
        state = self.journal.bound(source, target)
        if state["phase"] == "applying":
            registry = MigrationRegistry(bundle.tree, target=target)
            MigrationRunner(registry, self.journal, source, target).run()
            for index, stage in enumerate(STAGES[1:], 1):
                self.journal.checkpoint(source, target, stage)
                try:
                    self.authority.invoke(stage, "validate", bundle, self.user)
                except UpdateError:
                    self.authority.invoke(stage, "apply", bundle, self.user)
                    self.authority.invoke(stage, "validate", bundle, self.user)
                if index + 1 < len(STAGES):
                    self.journal.checkpoint(source, target, STAGES[index + 1])
            self.journal.checkpoint(source, target, "final-validation")
            self.journal.phase(source, target, "validating")
        self._validate_all(source, bundle)
        if self.journal.bound(source, target)["phase"] == "validating":
            self.journal.phase(source, target, "ready-for-final-commit")
        self.store.resume(target["artifact"]["sha256"])
        try:
            self.identity.upgrade_commit(source, bundle.metadata_bytes)
        except Exception as error:
            try:
                committed = self.identity.validate() == target
            except Exception:
                committed = False
            if committed:
                raise UpdateError("terminal cleanup required", "target identity committed; resume to clear journal") from error
            raise UpdateError("final commit failed", str(error)) from error
        if self.identity.validate() != target:
            raise UpdateError("terminal cleanup required", "committed identity did not validate")
        try:
            self.journal.clear_after_commit(source, target)
        except Exception as error:
            raise UpdateError("terminal cleanup required", "target identity committed; resume to clear journal") from error
        try:
            self.store.remove_committed(bundle)
        except Exception as error:
            raise UpdateError("terminal cleanup required", f"journal cleared but staged target cleanup failed: {error}") from error
        return target

    def apply(self, metadata_path: Path, artifact_path: Path) -> dict[str, Any]:
        self._require_privilege()
        with self.journal.lock.acquire():
            plan = self.plan(metadata_path, artifact_path)
            bundle = self.store.prepare(metadata_path, artifact_path, permanent=True)
            if bundle.metadata != plan.target:
                raise UpdateError("transaction mismatch", "staged target differs from preflight")
            try:
                self.journal.begin(plan.source, bundle.metadata)
            except Exception:
                if self.journal.inspect() is None:
                    self.store.remove_committed(bundle)
                raise
            try:
                return self._run_transaction(plan.source, bundle)
            except UpdateError as error:
                if error.kind in {"terminal cleanup required", "final commit failed"}:
                    raise
                raise UpdateError("update incomplete", f"journal retained: {error}") from error
            except Exception as error:
                raise UpdateError("update incomplete", f"journal retained: {error}") from error

    def resume(self) -> dict[str, Any]:
        self._require_privilege()
        with self.journal.lock.acquire():
            state = self.journal.inspect()
            if state is None:
                installed = self._installed()
                digest = installed["artifact"]["sha256"]
                stage = self.store.parent / digest
                if not os.path.lexists(stage):
                    raise UpdateError("preflight failed", "no update journal exists to resume")
                if set(path.name for path in self.store.parent.iterdir()) != {digest}:
                    raise UpdateError("transaction mismatch", "unrelated staged targets require review")
                bundle = self.store.resume(digest)
                if bundle.metadata != installed:
                    raise UpdateError("transaction mismatch", "committed staging differs from installed release")
                self.store.remove_committed(bundle)
                return installed
            try:
                bundle = self.store.resume(state["target"]["artifact_sha256"])
            except Exception as error:
                raise UpdateError("transaction mismatch", f"retained target cannot be verified: {error}") from error
            if bundle.metadata["version"] != state["target"]["version"] or bundle.metadata["commit"] != state["target"]["commit"]:
                raise UpdateError("transaction mismatch", "staged target identity differs from journal")
            installed = self._installed()
            if installed == bundle.metadata:
                if state["phase"] != "ready-for-final-commit":
                    raise UpdateError("transaction mismatch", "target identity committed before journal was ready")
                self.journal.clear_committed_target(bundle.metadata)
                self.store.remove_committed(bundle)
                return installed
            if (installed["version"] != state["source"]["version"]
                    or installed["commit"] != state["source"]["commit"]
                    or installed["artifact"]["sha256"] != state["source"]["artifact_sha256"]
                    or installed["migration_level"] != state["source"]["migration_level"]):
                raise UpdateError("transaction mismatch", "installed source differs from active journal")
            self._compatible(installed, bundle.metadata)
            self.journal.begin(installed, bundle.metadata, resume=True)
            try:
                return self._run_transaction(installed, bundle)
            except UpdateError as error:
                if error.kind in {"terminal cleanup required", "final commit failed"}:
                    raise
                raise UpdateError("update incomplete", f"journal retained: {error}") from error
            except Exception as error:
                raise UpdateError("update incomplete", f"journal retained: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "apply", "resume"))
    parser.add_argument("--target-user", required=True)
    parser.add_argument("--release-metadata", type=Path)
    parser.add_argument("--release-artifact", type=Path)
    parser.add_argument("--xdg-config-home", type=Path)
    parser.add_argument("--xdg-data-home", type=Path)
    parser.add_argument("--xdg-state-home", type=Path)
    parser.add_argument("--xdg-cache-home", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.operation != "resume" and (arguments.release_metadata is None or arguments.release_artifact is None):
        parser.error("plan/apply require --release-metadata and --release-artifact")
    if arguments.operation == "resume" and (arguments.release_metadata is not None or arguments.release_artifact is not None):
        parser.error("resume uses the exact retained target; bundle paths are not accepted")
    try:
        user = TargetUser.resolve(arguments.target_user, xdg_config=arguments.xdg_config_home,
                                  xdg_data=arguments.xdg_data_home,
                                  xdg_state=arguments.xdg_state_home,
                                  xdg_cache=arguments.xdg_cache_home)
        driver = ReleaseUpdate(user)
        if arguments.operation == "plan":
            print(json.dumps(driver.plan(arguments.release_metadata, arguments.release_artifact).as_dict(), indent=2))
        else:
            target = (driver.apply(arguments.release_metadata, arguments.release_artifact)
                      if arguments.operation == "apply" else driver.resume())
            print(f"Vanilla HyprArch update complete: {target['version']}")
        return 0
    except (UpdateError, IdentityError, JournalError, MigrationError,
            contract.ReleaseError, OSError, subprocess.SubprocessError) as error:
        kind = error.kind if isinstance(error, UpdateError) else "preflight failed"
        print(f"Vanilla HyprArch {kind}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
