#!/usr/bin/env python3
"""DF2 Phase 4 system integration.

This is an installer-internal, root-run stage.  It consumes the published
package, service, and ownership manifests; it is not the top-level installer.
Tests inject a command runner and a disposable system root.  The production
CLI deliberately has no alternate-root option.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Callable, Protocol, Sequence


SCHEMA_VERSION = 1
STATE_DIRECTORY = "/var/lib/vanhyprarch"
STATE_FILE = f"{STATE_DIRECTORY}/system-integration-v1.json"
TRANSACTION_FILE = f"{STATE_DIRECTORY}/system-integration-transaction-v1.json"
LOCK_FILE = f"{STATE_DIRECTORY}/system-integration.lock"
BLUEZ_BACKUP = f"{STATE_DIRECTORY}/bluez/main.conf.pre-vanilla"
FLATHUB_NAME = "flathub"
FLATHUB_URL = "https://dl.flathub.org/repo/"
AUR_YAY_ORIGIN = "https://aur.archlinux.org/yay.git"
PACKAGE_NAME = re.compile(r"^[a-z0-9@._+:-]+$")
DEPENDENCY_NAME = re.compile(r"^([a-z0-9@._+:-]+)")
SERVICE_NAME = re.compile(r"^[A-Za-z0-9@_.:-]+\.(?:service|socket|path)$")


class IntegrationError(RuntimeError):
    """A fail-closed integration error."""


@dataclasses.dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        user: "TargetUser | None" = None,
    ) -> CommandResult: ...


@dataclasses.dataclass(frozen=True)
class TargetUser:
    name: str
    uid: int
    gid: int
    home: Path


class SubprocessRunner:
    """Run fixed argv arrays; optionally cross the privilege boundary."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        user: TargetUser | None = None,
    ) -> CommandResult:
        command = list(argv)
        process_env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        if env:
            process_env.update(env)
        if user is not None:
            command = [
                "/usr/bin/runuser",
                "--user",
                user.name,
                "--",
                "/usr/bin/env",
                f"HOME={user.home}",
                f"USER={user.name}",
                f"LOGNAME={user.name}",
                "PATH=/usr/bin:/bin",
                "LC_ALL=C",
                *command,
            ]
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=process_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as error:
            raise IntegrationError(f"could not execute {command[0]}: {error}") from error
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclasses.dataclass(frozen=True)
class PlanItem:
    action: str
    subject: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        result = {"action": self.action, "subject": self.subject}
        if self.detail:
            result["detail"] = self.detail
        return result


@dataclasses.dataclass(frozen=True)
class SystemPlan:
    items: tuple[PlanItem, ...]

    @property
    def blockers(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if item.action in {"prerequisite-block", "bluez-conflict", "flathub-conflict", "conflict", "recovery-required"})

    @property
    def changes(self) -> tuple[PlanItem, ...]:
        preserved = {"package-preserve", "aur-preserve", "bluez-preserve", "service-preserve", "flathub-preserve"}
        return tuple(item for item in self.items if item.action not in preserved and item not in self.blockers)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_VERSION,
            "blocked": bool(self.blockers),
            "items": [item.as_dict() for item in self.items],
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _dependency_name(value: str) -> str:
    match = DEPENDENCY_NAME.match(value)
    if match is None:
        raise IntegrationError(f"invalid PKGBUILD dependency: {value!r}")
    return match.group(1)


class SystemIntegration:
    """Manifest-driven Phase 4 integration with injectable system boundaries."""

    def __init__(
        self,
        *,
        source_root: Path,
        target_username: str,
        runner: CommandRunner | None = None,
        system_root: Path = Path("/"),
        account_resolver: Callable[[str], TargetUser] | None = None,
        effective_uid: int | None = None,
        root_identity: tuple[int, int] = (0, 0),
        testing: bool = False,
    ) -> None:
        self.source_root = source_root.resolve()
        self.system_root = system_root.resolve()
        self.runner = runner or SubprocessRunner()
        self.testing = testing
        self.effective_uid = os.geteuid() if effective_uid is None else effective_uid
        self.root_uid, self.root_gid = root_identity
        if self.system_root != Path("/") and not testing:
            raise IntegrationError("an alternate system root is available only to isolated tests")
        if not self.source_root.is_dir():
            raise IntegrationError(f"source root is not a directory: {self.source_root}")
        if not target_username or target_username == "root":
            raise IntegrationError("an explicit non-root target user is required")
        self._account_resolver = account_resolver or self._resolve_account
        try:
            self.target_user = self._account_resolver(target_username)
        except (KeyError, LookupError) as error:
            raise IntegrationError(f"target user does not exist: {target_username}") from error
        if self.target_user.uid == 0:
            raise IntegrationError("AUR builds must never target root")
        self._validate_target_home()
        self.package_manifest = self._load_toml("packages/manifest-v1.toml")
        self.service_manifest = self._load_toml("deployment/service-policy-v1.toml")
        self.ownership_manifest = self._load_toml("deployment/ownership-v2.toml")
        self._validate_manifests()

    @staticmethod
    def _resolve_account(name: str) -> TargetUser:
        account = pwd.getpwnam(name)
        return TargetUser(account.pw_name, account.pw_uid, account.pw_gid, Path(account.pw_dir))

    def _system_path(self, absolute: str | Path) -> Path:
        path = Path(absolute)
        if not path.is_absolute() or ".." in path.parts:
            raise IntegrationError(f"unsafe system path: {path}")
        return self.system_root / path.relative_to("/")

    def _validate_target_home(self) -> None:
        if not self.target_user.home.is_absolute() or ".." in self.target_user.home.parts:
            raise IntegrationError("target user HOME must be an absolute safe path")
        home = self._system_path(self.target_user.home)
        try:
            details = home.lstat()
        except FileNotFoundError as error:
            raise IntegrationError(f"target user HOME does not exist: {self.target_user.home}") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise IntegrationError("target user HOME must be a real directory")
        if details.st_uid != self.target_user.uid:
            raise IntegrationError("target user HOME has unexpected ownership")
        if details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise IntegrationError("target user HOME must not be group/world writable")

    def _load_toml(self, relative: str) -> dict:
        path = self._safe_source_file(relative, "required manifest")
        with path.open("rb") as stream:
            try:
                return tomllib.load(stream)
            except tomllib.TOMLDecodeError as error:
                raise IntegrationError(f"invalid TOML manifest {relative}: {error}") from error

    def _safe_source_file(self, relative: str, description: str) -> Path:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise IntegrationError(f"unsafe {description} path: {relative}")
        current = self.source_root
        for part in relative_path.parts:
            current = current / part
            try:
                details = current.lstat()
            except FileNotFoundError as error:
                raise IntegrationError(f"{description} is missing: {relative}") from error
            if stat.S_ISLNK(details.st_mode):
                raise IntegrationError(f"{description} crosses a source symlink: {relative}")
        if not stat.S_ISREG(current.lstat().st_mode):
            raise IntegrationError(f"{description} is not a safe regular file: {relative}")
        return current

    def _validate_manifests(self) -> None:
        packages = self.package_manifest.get("package", [])
        seen: set[str] = set()
        for package in packages:
            name = package.get("name")
            if not isinstance(name, str) or PACKAGE_NAME.fullmatch(name) is None:
                raise IntegrationError(f"unsafe package name in manifest: {name!r}")
            if name in seen:
                raise IntegrationError(f"duplicate package in manifest: {name}")
            seen.add(name)
        aur = [item["name"] for item in packages if item.get("source") == "aur" and item.get("default_install") is True]
        if aur != ["yay"] or self.package_manifest.get("aur", {}).get("approved_default") != ["yay"]:
            raise IntegrationError("the sole default AUR package must be yay")
        adopted = [item for item in self.ownership_manifest.get("artifact", []) if item.get("class") == "ADOPTED_PRIVILEGED"]
        if len(adopted) != 1 or adopted[0].get("id") != "bluez-main-config":
            raise IntegrationError("ownership manifest must declare exactly the BlueZ adopted target")
        target = adopted[0].get("target")
        source = adopted[0].get("source")
        if target != "/etc/bluetooth/main.conf" or not isinstance(source, str):
            raise IntegrationError("unexpected BlueZ adoption mapping")
        self.bluez_record = adopted[0]
        services = self.service_manifest.get("service", [])
        names: set[str] = set()
        for service in services:
            name = service.get("name")
            if not isinstance(name, str) or SERVICE_NAME.fullmatch(name) is None:
                raise IntegrationError(f"unsafe service name: {name!r}")
            if name in names:
                raise IntegrationError(f"duplicate service policy: {name}")
            names.add(name)

    @property
    def official_default_packages(self) -> tuple[str, ...]:
        return tuple(sorted(item["name"] for item in self.package_manifest["package"] if item["source"] == "official" and item["default_install"] is True))

    @property
    def excluded_default_packages(self) -> tuple[str, ...]:
        return tuple(sorted(item["name"] for item in self.package_manifest["package"] if item["default_install"] is False))

    @property
    def recommended_default_packages(self) -> tuple[str, ...]:
        return tuple(sorted(item["name"] for item in self.package_manifest["package"] if item["source"] == "official" and item["role"] == "recommended" and item["default_install"] is True))

    @property
    def desired_system_services(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.service_manifest["service"]:
            if item["scope"] != "system" or item["default_install"] is not True:
                continue
            if item["policy"] not in {"enabled", "disabled"}:
                raise IntegrationError(f"unsupported default system service policy: {item['name']}")
            result[item["name"]] = item["policy"]
        return dict(sorted(result.items()))

    def _run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        user: TargetUser | None = None,
    ) -> CommandResult:
        if not argv or any(not isinstance(value, str) or "\x00" in value for value in argv):
            raise IntegrationError("invalid command argv")
        return self.runner.run(argv, cwd=cwd, env={"LC_ALL": "C"}, user=user)

    def _require_success(self, result: CommandResult, description: str) -> str:
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise IntegrationError(f"{description}: {message}")
        return result.stdout

    def _read_installed_packages(self) -> set[str]:
        output = self._require_success(self._run(["/usr/bin/pacman", "-Qq"]), "pacman local database is unusable")
        return {line.strip() for line in output.splitlines() if line.strip()}

    def _pending_upgrades(self) -> tuple[str, ...]:
        result = self._run(["/usr/bin/pacman", "-Qu"])
        if result.returncode not in {0, 1}:
            self._require_success(result, "could not inspect pending upgrades from current sync databases")
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    def _base_preflight(self) -> tuple[set[str], tuple[str, ...]]:
        release = self._system_path("/etc/arch-release")
        if not release.is_file() or release.is_symlink():
            raise IntegrationError("supported base requires Arch Linux")
        try:
            release_text = release.read_text(encoding="utf-8")
        except OSError as error:
            raise IntegrationError(f"could not read Arch release identity: {error}") from error
        if "Arch Linux" not in release_text:
            raise IntegrationError("supported base requires Arch Linux")
        architecture = self._require_success(self._run(["/usr/bin/uname", "-m"]), "could not inspect architecture").strip()
        if architecture != "x86_64":
            raise IntegrationError(f"unsupported architecture: {architecture or 'unknown'}")
        installed = self._read_installed_packages()
        sync_probe = self._run(["/usr/bin/pacman", "-Si", "--", "pacman"])
        self._require_success(sync_probe, "pacman sync databases are unavailable or unusable")
        pending = self._pending_upgrades()
        return installed, pending

    def _resolve_official(self, packages: Sequence[str]) -> None:
        if not packages:
            return
        result = self._run(["/usr/bin/pacman", "-Sp", "--print-format", "%n", "--needed", "--", *packages])
        self._require_success(result, "required packages cannot be resolved from the current sync databases")

    def _package_plan(self) -> tuple[list[PlanItem], set[str], tuple[str, ...]]:
        installed, pending = self._base_preflight()
        items: list[PlanItem] = []
        if pending:
            items.append(PlanItem("prerequisite-block", "arch-system-upgrade", f"{len(pending)} pending upgrade(s); administrator must run a normal pacman -Syu"))
        missing = [name for name in self.official_default_packages if name not in installed]
        for name in self.official_default_packages:
            role = next(item["role"] for item in self.package_manifest["package"] if item["name"] == name)
            action = "package-install" if name in missing else "package-preserve"
            items.append(PlanItem(action, name, f"role={role}; default_install=true"))
        if not pending:
            self._resolve_official(missing)
        excluded_components = sorted({item.get("component") for item in self.package_manifest["package"] if not item["default_install"] and item.get("component")})
        items.append(PlanItem("package-preserve", "non-default-components", "excluded=" + ",".join(excluded_components)))
        return items, installed, pending

    def _yay_status(self, installed: set[str]) -> PlanItem:
        if "yay" not in installed:
            return PlanItem("aur-bootstrap", "yay", "sole approved AUR exception")
        query = self._run(["/usr/bin/pacman", "-Q", "--", "yay"])
        self._require_success(query, "installed yay identity could not be queried")
        foreign = self._run(["/usr/bin/pacman", "-Qm", "--", "yay"])
        if foreign.returncode != 0:
            return PlanItem("conflict", "yay", "installed yay is not identified as a foreign/AUR package")
        owner = self._run(["/usr/bin/pacman", "-Qqo", "--", "/usr/bin/yay"])
        if owner.returncode != 0 or owner.stdout.strip() != "yay":
            return PlanItem("conflict", "yay", "/usr/bin/yay is not owned by package yay")
        executable = self._system_path("/usr/bin/yay")
        if not executable.is_file() or executable.is_symlink() or not os.access(executable, os.X_OK):
            return PlanItem("conflict", "yay", "owned executable /usr/bin/yay is unavailable or unsafe")
        return PlanItem("aur-preserve", "yay", query.stdout.strip())

    def _service_state(self, unit: str) -> str:
        result = self._run(["/usr/bin/systemctl", "is-enabled", "--", unit])
        value = result.stdout.strip()
        if not value:
            value = "unknown"
        return value

    def _service_plan(self) -> list[PlanItem]:
        items: list[PlanItem] = []
        for unit, desired in self.desired_system_services.items():
            current = self._service_state(unit)
            action = "service-preserve" if current == desired else ("service-enable" if desired == "enabled" else "service-disable")
            items.append(PlanItem(action, unit, f"current={current}; desired={desired}"))
        return items

    def _read_state(self) -> dict:
        path = self._system_path(STATE_FILE)
        if not path.exists():
            return {"schema": SCHEMA_VERSION}
        self._validate_private_file(path, 0o600, "system integration state")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IntegrationError(f"invalid system integration state: {error}") from error
        if not isinstance(value, dict) or value.get("schema") != SCHEMA_VERSION:
            raise IntegrationError("unsupported system integration state schema")
        return value

    def _read_transaction(self) -> dict | None:
        path = self._system_path(TRANSACTION_FILE)
        if not path.exists():
            return None
        self._validate_private_file(path, 0o600, "system integration transaction")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IntegrationError(f"invalid system integration transaction: {error}") from error
        if not isinstance(value, dict) or value.get("schema") != SCHEMA_VERSION or value.get("kind") not in {"bluez-adopt", "service-policy"}:
            raise IntegrationError("unsupported system integration transaction")
        return value

    def _validate_private_directory(self, path: Path) -> None:
        details = path.lstat()
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise IntegrationError(f"unsafe privileged state directory: {path}")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise IntegrationError(f"privileged state directory has unexpected ownership: {path}")
        if stat.S_IMODE(details.st_mode) != 0o700:
            raise IntegrationError(f"privileged state directory has unexpected mode: {path}")

    def _ensure_private_directory(self, path: Path) -> None:
        current = self.system_root
        relative_parts = path.relative_to(self.system_root).parts
        for part in relative_parts:
            current = current / part
            if current.exists():
                details = current.lstat()
                if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                    raise IntegrationError(f"unsafe privileged-state parent: {current}")
                if current == path:
                    self._validate_private_directory(current)
                continue
            os.mkdir(current, 0o700)
            os.chmod(current, 0o700)
            os.chown(current, self.root_uid, self.root_gid)
            self._fsync_directory(current.parent)
        self._validate_private_directory(path)

    def _validate_private_file(self, path: Path, mode: int, description: str) -> None:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise IntegrationError(f"{description} is not a safe regular file")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise IntegrationError(f"{description} has unexpected ownership")
        if stat.S_IMODE(details.st_mode) != mode:
            raise IntegrationError(f"{description} has unexpected mode")

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _atomic_write(self, path: Path, data: bytes, mode: int, uid: int, gid: int) -> None:
        self._ensure_private_directory(path.parent) if path.parent == self._system_path(STATE_DIRECTORY) else None
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, mode)
            os.fchown(descriptor, uid, gid)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            self._fsync_directory(path.parent)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise

    def _write_state(self, value: dict) -> None:
        directory = self._system_path(STATE_DIRECTORY)
        self._ensure_private_directory(directory)
        self._atomic_write(self._system_path(STATE_FILE), _json_bytes(value), 0o600, self.root_uid, self.root_gid)

    def _write_transaction(self, value: dict) -> None:
        directory = self._system_path(STATE_DIRECTORY)
        self._ensure_private_directory(directory)
        self._atomic_write(self._system_path(TRANSACTION_FILE), _json_bytes(value), 0o600, self.root_uid, self.root_gid)

    def _remove_transaction(self) -> None:
        path = self._system_path(TRANSACTION_FILE)
        if path.exists():
            self._validate_private_file(path, 0o600, "system integration transaction")
            path.unlink()
            self._fsync_directory(path.parent)

    @contextlib.contextmanager
    def _mutation_lock(self):
        directory = self._system_path(STATE_DIRECTORY)
        self._ensure_private_directory(directory)
        path = self._system_path(LOCK_FILE)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
                raise IntegrationError("system integration lock is unsafe")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise IntegrationError("another system integration mutation is active") from error
            self._fsync_directory(directory)
            yield
        finally:
            os.close(descriptor)

    def _fault(self, checkpoint: str) -> None:
        if not self.testing or os.environ.get("VANHYPRARCH_SYSTEM_INTEGRATION_TESTING") != "1":
            return
        if os.environ.get("VANHYPRARCH_SYSTEM_INTEGRATION_FAULT_AT") == checkpoint:
            os._exit(197)

    def _bluez_source(self) -> tuple[Path, bytes]:
        relative = self.bluez_record["source"]
        path = self._safe_source_file(relative, "BlueZ source")
        data = path.read_bytes()
        if not data:
            raise IntegrationError("BlueZ source is empty")
        return path, data

    def _bluez_target_details(self) -> tuple[Path, os.stat_result, bytes]:
        target = self._system_path(self.bluez_record["target"])
        try:
            details = target.lstat()
        except FileNotFoundError as error:
            raise IntegrationError("BlueZ package configuration is missing") from error
        if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise IntegrationError("BlueZ configuration is not a safe regular file")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise IntegrationError("BlueZ configuration has unexpected ownership")
        if stat.S_IMODE(details.st_mode) != int(self.bluez_record["mode"], 8):
            raise IntegrationError("BlueZ configuration has unexpected mode")
        return target, details, target.read_bytes()

    def _bluez_package_version(self) -> str:
        output = self._require_success(self._run(["/usr/bin/pacman", "-Q", "--", "bluez"]), "BlueZ package is unavailable").strip()
        fields = output.split()
        if len(fields) != 2 or fields[0] != "bluez":
            raise IntegrationError("unexpected pacman BlueZ identity output")
        return fields[1]

    def _bluez_is_package_pristine(self, version: str) -> bool:
        owner = self._run(["/usr/bin/pacman", "-Qo", "--", "/etc/bluetooth/main.conf"])
        if owner.returncode != 0 or re.search(rf"\bbluez\s+{re.escape(version)}\b", owner.stdout) is None:
            return False
        info = self._run(["/usr/bin/pacman", "-Qii", "--", "bluez"])
        if info.returncode != 0:
            return False
        normalized = info.stdout.lower()
        path = "/etc/bluetooth/main.conf"
        patterns = (rf"unmodified\s+{re.escape(path)}(?:\s|$)", rf"{re.escape(path)}\s+\[unmodified\]")
        return any(re.search(pattern, normalized) is not None for pattern in patterns)

    def _bluez_classification(self) -> PlanItem:
        try:
            target, details, data = self._bluez_target_details()
            _, candidate = self._bluez_source()
            state = self._read_state()
            adopted = state.get("bluez")
            if adopted is not None:
                if (
                    not isinstance(adopted, dict)
                    or adopted.get("target") != self.bluez_record["target"]
                    or adopted.get("backup_path") != BLUEZ_BACKUP
                ):
                    raise IntegrationError("invalid BlueZ adoption provenance")
                backup = self._system_path(adopted.get("backup_path", ""))
                if adopted.get("deployed_sha256") != _sha256(data) or data != candidate:
                    raise IntegrationError("adopted BlueZ configuration drifted")
                if adopted.get("deployed_mode") != f"{stat.S_IMODE(details.st_mode):04o}" or adopted.get("deployed_uid") != details.st_uid or adopted.get("deployed_gid") != details.st_gid:
                    raise IntegrationError("adopted BlueZ metadata drifted")
                self._validate_private_file(backup, 0o600, "BlueZ backup")
                if _sha256(backup.read_bytes()) != adopted.get("original_sha256"):
                    raise IntegrationError("BlueZ backup does not match provenance")
                return PlanItem("bluez-preserve", str(target), "previously Vanilla-adopted")
            version = self._bluez_package_version()
            if self._bluez_is_package_pristine(version):
                return PlanItem("bluez-adopt", str(target), f"package-pristine bluez {version}")
            return PlanItem("bluez-conflict", str(target), "existing configuration is not proven package-pristine")
        except IntegrationError as error:
            return PlanItem("bluez-conflict", self.bluez_record["target"], str(error))

    def _flatpak_status(self) -> PlanItem:
        result = self._run(["/usr/bin/flatpak", "remotes", "--system", "--columns=name,url"])
        if result.returncode != 0:
            return PlanItem("prerequisite-block", "flathub", "Flatpak system remotes cannot be inspected")
        matches = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2 and fields[0] == FLATHUB_NAME:
                matches.append(fields[1])
        if not matches:
            return PlanItem("flathub-add", FLATHUB_NAME, FLATHUB_URL)
        if len(matches) != 1 or matches[0] != FLATHUB_URL:
            return PlanItem("flathub-conflict", FLATHUB_NAME, "same-named system remote has unexpected or duplicate configuration")
        return PlanItem("flathub-preserve", FLATHUB_NAME, FLATHUB_URL)

    def plan(self) -> SystemPlan:
        transaction = self._read_transaction()
        if transaction is not None:
            return SystemPlan((PlanItem("recovery-required", transaction["kind"], transaction.get("phase", "unknown")),))
        package_items, installed, pending = self._package_plan()
        items = package_items
        items.append(self._yay_status(installed))
        if "bluez" in installed:
            items.append(self._bluez_classification())
        else:
            items.append(PlanItem("bluez-adopt", self.bluez_record["target"], "after the planned bluez package installation"))
        if "flatpak" in installed:
            items.append(self._flatpak_status())
        else:
            items.append(PlanItem("flathub-add", FLATHUB_NAME, "after the planned flatpak package installation"))
        items.extend(self._service_plan())
        if pending:
            items.append(PlanItem("prerequisite-block", "phase4-apply", "package provisioning is blocked until administrator-managed full upgrade"))
        return SystemPlan(tuple(items))

    def _require_root_apply(self) -> None:
        if self.effective_uid != 0:
            raise IntegrationError("Phase 4 apply must run as root with an explicit non-root target user")

    def _install_official_packages(self, installed: set[str]) -> None:
        missing = [name for name in self.official_default_packages if name not in installed]
        self._resolve_official(missing)
        if missing:
            result = self._run(["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--", *missing])
            self._require_success(result, "official package transaction failed")
        after = self._read_installed_packages()
        absent = sorted(set(self.official_default_packages) - after)
        if absent:
            raise IntegrationError("official package verification failed: " + ", ".join(absent))

    def _save_yay_provenance(self, *, commit: str, package_sha256: str) -> None:
        state = self._read_state()
        state["yay"] = {
            "source_origin": AUR_YAY_ORIGIN,
            "source_commit": commit,
            "installed_package": "yay",
            "package_sha256": package_sha256,
        }
        self._write_state(state)

    def _parse_srcinfo(self, text: str) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        pkgbase = ""
        packages: list[str] = []
        architectures: list[str] = []
        dependencies: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            if key == "pkgbase":
                pkgbase = value
            elif key == "pkgname":
                packages.append(value)
            elif key == "arch":
                architectures.append(value)
            elif key == "depends" or key == "makedepends" or key == "checkdepends" or key.startswith(("depends_", "makedepends_", "checkdepends_")):
                dependencies.append(_dependency_name(value))
        if pkgbase != "yay" or packages != ["yay"]:
            raise IntegrationError("yay PKGBUILD metadata has unexpected pkgbase/package identity")
        if not architectures or not set(architectures).issubset({"x86_64", "any"}):
            raise IntegrationError("yay PKGBUILD metadata has unexpected architecture")
        return pkgbase, tuple(packages), tuple(sorted(set(architectures))), tuple(sorted(set(dependencies)))

    def _verify_yay_dependency_policy(self, dependencies: Sequence[str]) -> None:
        unavailable = []
        for dependency in dependencies:
            result = self._run(["/usr/bin/pacman", "-Si", "--", dependency])
            if result.returncode != 0:
                unavailable.append(dependency)
        if unavailable:
            raise IntegrationError("yay requires non-official dependencies outside the approved AUR policy: " + ", ".join(unavailable))

    def _bootstrap_yay(self) -> None:
        installed = self._read_installed_packages()
        status = self._yay_status(installed)
        if status.action == "aur-preserve":
            return
        if status.action == "conflict":
            raise IntegrationError(status.detail)
        build_parent = self._system_path("/var/tmp")
        if not build_parent.is_dir() or build_parent.is_symlink():
            raise IntegrationError("/var/tmp is unavailable or unsafe")
        build_parent_details = build_parent.lstat()
        if (build_parent_details.st_uid, build_parent_details.st_gid) != (self.root_uid, self.root_gid):
            raise IntegrationError("/var/tmp has unexpected ownership")
        if build_parent_details.st_mode & stat.S_IWOTH and not build_parent_details.st_mode & stat.S_ISVTX:
            raise IntegrationError("world-writable /var/tmp must have the sticky bit")
        build_directory = Path(tempfile.mkdtemp(prefix="vanhyprarch-yay.", dir=build_parent))
        os.chmod(build_directory, 0o700)
        os.chown(build_directory, self.target_user.uid, self.target_user.gid)
        repository = build_directory / "yay"
        try:
            clone = self._run(["/usr/bin/git", "clone", "--", AUR_YAY_ORIGIN, str(repository)], cwd=build_directory, user=self.target_user)
            self._require_success(clone, "could not clone the authoritative yay AUR repository")
            if not repository.is_dir() or repository.is_symlink():
                raise IntegrationError("yay clone did not produce a safe private repository")
            if repository.stat().st_uid != self.target_user.uid:
                raise IntegrationError("yay clone has unexpected ownership")
            origin = self._require_success(self._run(["/usr/bin/git", "-C", str(repository), "remote", "get-url", "origin"], user=self.target_user), "could not verify yay AUR origin").strip()
            if origin != AUR_YAY_ORIGIN:
                raise IntegrationError(f"unexpected yay AUR origin: {origin}")
            commit = self._require_success(self._run(["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"], user=self.target_user), "could not record yay source commit").strip()
            if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
                raise IntegrationError("yay source commit is invalid")
            srcinfo = self._require_success(self._run(["/usr/bin/makepkg", "--printsrcinfo"], cwd=repository, user=self.target_user), "could not inspect yay PKGBUILD metadata")
            _, _, _, dependencies = self._parse_srcinfo(srcinfo)
            self._verify_yay_dependency_policy(dependencies)
            installed_now = self._read_installed_packages()
            missing_dependencies = [name for name in dependencies if name not in installed_now]
            self._resolve_official(missing_dependencies)
            if missing_dependencies:
                result = self._run(["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--", *missing_dependencies])
                self._require_success(result, "could not install official yay build dependencies")
            expected_output = self._require_success(self._run(["/usr/bin/makepkg", "--packagelist"], cwd=repository, user=self.target_user), "could not determine yay package output")
            expected_paths = [Path(line.strip()) for line in expected_output.splitlines() if line.strip()]
            if len(expected_paths) != 1:
                raise IntegrationError("yay build must produce exactly one expected package output")
            build = self._run(["/usr/bin/makepkg", "--cleanbuild", "--clean", "--noconfirm"], cwd=repository, user=self.target_user)
            self._require_success(build, "yay build failed")
            package = expected_paths[0]
            if not package.is_absolute():
                package = repository / package
            resolved_package = package.resolve()
            if repository.resolve() not in resolved_package.parents or not package.is_file() or package.is_symlink():
                raise IntegrationError("yay build output is missing, unsafe, or outside the private build tree")
            metadata = self._require_success(self._run(["/usr/bin/bsdtar", "-xOf", str(package), ".PKGINFO"]), "could not inspect built yay package metadata")
            values: dict[str, list[str]] = {}
            for line in metadata.splitlines():
                if " = " in line:
                    key, value = line.split(" = ", 1)
                    values.setdefault(key, []).append(value)
            if values.get("pkgname") != ["yay"] or values.get("pkgbase") != ["yay"] or values.get("arch") not in (["x86_64"], ["any"]):
                raise IntegrationError("built package metadata does not identify the expected yay package")
            package_digest = _sha256(package.read_bytes())
            install = self._run(["/usr/bin/pacman", "-U", "--noconfirm", "--", str(package)])
            self._require_success(install, "could not install the verified yay package")
            status = self._yay_status(self._read_installed_packages())
            if status.action != "aur-preserve":
                raise IntegrationError("installed yay failed package/executable verification")
            self._save_yay_provenance(commit=commit, package_sha256=package_digest)
        finally:
            if build_directory.exists():
                details = build_directory.lstat()
                if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode) or details.st_uid != self.target_user.uid:
                    raise IntegrationError("refusing to remove unsafe yay build directory")
                shutil.rmtree(build_directory)

    def _write_backup_no_clobber(self, data: bytes) -> None:
        backup = self._system_path(BLUEZ_BACKUP)
        parent = backup.parent
        if parent.exists():
            self._validate_private_directory(parent)
        else:
            self._ensure_private_directory(parent)
        try:
            backup.lstat()
        except FileNotFoundError:
            pass
        else:
            raise IntegrationError("refusing to overwrite an existing BlueZ backup without adoption provenance")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        try:
            descriptor = os.open(backup, flags, 0o600)
        except FileExistsError as error:
            raise IntegrationError("BlueZ backup appeared concurrently; refusing adoption") from error
        try:
            os.fchmod(descriptor, 0o600)
            os.fchown(descriptor, self.root_uid, self.root_gid)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            backup.unlink(missing_ok=True)
            raise
        self._fsync_directory(parent)

    def _publish_root_file(self, target: Path, data: bytes, mode: int, uid: int, gid: int) -> None:
        parent = target.parent
        if not parent.is_dir() or parent.is_symlink():
            raise IntegrationError(f"unsafe target parent: {parent}")
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.vanhyprarch.", dir=parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, mode)
            os.fchown(descriptor, uid, gid)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            self._fsync_directory(parent)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise

    def _apply_bluez(self) -> None:
        classification = self._bluez_classification()
        if classification.action == "bluez-preserve":
            return
        if classification.action != "bluez-adopt":
            raise IntegrationError(classification.detail)
        target, details, original = self._bluez_target_details()
        _, candidate = self._bluez_source()
        version = self._bluez_package_version()
        backup = self._system_path(BLUEZ_BACKUP)
        try:
            backup.lstat()
        except FileNotFoundError:
            pass
        else:
            raise IntegrationError("refusing BlueZ adoption while an unproven backup already exists")
        transaction = {
            "schema": SCHEMA_VERSION,
            "kind": "bluez-adopt",
            "phase": "prepared",
            "target": self.bluez_record["target"],
            "backup_path": BLUEZ_BACKUP,
            "original_sha256": _sha256(original),
            "original_mode": f"{stat.S_IMODE(details.st_mode):04o}",
            "original_uid": details.st_uid,
            "original_gid": details.st_gid,
            "candidate_sha256": _sha256(candidate),
            "candidate_mode": self.bluez_record["mode"],
            "package_version": version,
        }
        self._write_transaction(transaction)
        self._fault("bluez-before-backup-commit")
        try:
            self._write_backup_no_clobber(original)
            transaction["phase"] = "backup-committed"
            self._write_transaction(transaction)
            self._fault("bluez-after-backup-commit")
            self._publish_root_file(target, candidate, int(self.bluez_record["mode"], 8), self.root_uid, self.root_gid)
            self._fault("bluez-after-config-publish")
            _, published_details, published = self._bluez_target_details()
            if published != candidate:
                raise IntegrationError("BlueZ candidate verification failed")
            transaction["phase"] = "config-published"
            self._write_transaction(transaction)
            self._fault("bluez-before-state-commit")
            state = self._read_state()
            state["bluez"] = {
                "target": self.bluez_record["target"],
                "backup_path": BLUEZ_BACKUP,
                "original_sha256": _sha256(original),
                "original_mode": f"{stat.S_IMODE(details.st_mode):04o}",
                "original_uid": details.st_uid,
                "original_gid": details.st_gid,
                "bluez_package_version": version,
                "deployed_sha256": _sha256(candidate),
                "deployed_mode": f"{stat.S_IMODE(published_details.st_mode):04o}",
                "deployed_uid": published_details.st_uid,
                "deployed_gid": published_details.st_gid,
            }
            self._write_state(state)
            self._fault("bluez-after-state-commit")
            self._remove_transaction()
        except BaseException:
            if not isinstance(sys.exc_info()[1], SystemExit):
                try:
                    self._recover_bluez(transaction)
                except BaseException:
                    pass
            raise

    def _recover_bluez(self, transaction: dict) -> None:
        if transaction.get("target") != self.bluez_record["target"] or transaction.get("backup_path") != BLUEZ_BACKUP:
            raise IntegrationError("invalid BlueZ recovery paths")
        target, _, current = self._bluez_target_details()
        state = self._read_state()
        adopted = state.get("bluez")
        if isinstance(adopted, dict) and adopted.get("deployed_sha256") == transaction.get("candidate_sha256"):
            if _sha256(current) != transaction.get("candidate_sha256"):
                raise IntegrationError("committed BlueZ adoption has unexpected target bytes")
            self._remove_transaction()
            return
        current_hash = _sha256(current)
        original_hash = transaction.get("original_sha256")
        candidate_hash = transaction.get("candidate_sha256")
        if current_hash not in {original_hash, candidate_hash}:
            raise IntegrationError("interrupted BlueZ target does not match expected old or candidate state")
        backup = self._system_path(transaction["backup_path"])
        phase = transaction.get("phase")
        if phase == "prepared":
            if current_hash != original_hash:
                raise IntegrationError("BlueZ candidate appeared before durable backup commit")
            if backup.exists():
                self._validate_private_file(backup, 0o600, "interrupted BlueZ backup")
                backup.unlink()
                self._fsync_directory(backup.parent)
            self._remove_transaction()
            return
        self._validate_private_file(backup, 0o600, "BlueZ recovery backup")
        original = backup.read_bytes()
        if _sha256(original) != original_hash:
            raise IntegrationError("BlueZ recovery backup hash mismatch")
        if current_hash == candidate_hash:
            self._publish_root_file(target, original, int(transaction["original_mode"], 8), transaction["original_uid"], transaction["original_gid"])
        backup.unlink()
        self._fsync_directory(backup.parent)
        self._remove_transaction()

    def _set_service_state(self, unit: str, desired: str) -> None:
        verb = "enable" if desired == "enabled" else "disable"
        result = self._run(["/usr/bin/systemctl", verb, "--", unit])
        self._require_success(result, f"could not {verb} {unit}")
        current = self._service_state(unit)
        if current != desired:
            raise IntegrationError(f"service enablement verification failed for {unit}: {current}")

    def _apply_services(self) -> None:
        desired = self.desired_system_services
        prior = {unit: self._service_state(unit) for unit in desired}
        unsupported = {unit: value for unit, value in prior.items() if value not in {"enabled", "disabled"}}
        if unsupported:
            raise IntegrationError("unsupported pre-existing service enablement state: " + ", ".join(f"{unit}={value}" for unit, value in unsupported.items()))
        if prior == desired:
            return
        transaction = {"schema": SCHEMA_VERSION, "kind": "service-policy", "phase": "prepared", "prior": prior, "desired": desired}
        self._write_transaction(transaction)
        self._fault("services-before-first-change")
        try:
            changed = 0
            for unit, wanted in desired.items():
                if prior[unit] == wanted:
                    continue
                self._set_service_state(unit, wanted)
                changed += 1
                if changed == 1:
                    self._fault("services-after-one-change")
            transaction["phase"] = "changed"
            self._write_transaction(transaction)
            self._fault("services-before-state-commit")
            state = self._read_state()
            state["services"] = {"desired": desired, "policy_sha256": _sha256(_json_bytes(desired))}
            self._write_state(state)
            self._fault("services-after-state-commit")
            self._remove_transaction()
        except BaseException:
            try:
                self._recover_services(transaction)
            except BaseException:
                pass
            raise

    def _recover_services(self, transaction: dict) -> None:
        prior = transaction.get("prior")
        desired = transaction.get("desired")
        if not isinstance(prior, dict) or not isinstance(desired, dict):
            raise IntegrationError("invalid service recovery transaction")
        if set(prior) != set(self.desired_system_services) or desired != self.desired_system_services:
            raise IntegrationError("service recovery transaction does not match manifest policy")
        if any(value not in {"enabled", "disabled"} for value in prior.values()):
            raise IntegrationError("service recovery transaction has unsupported prior state")
        current = {unit: self._service_state(unit) for unit in prior}
        state = self._read_state()
        committed = isinstance(state.get("services"), dict) and state["services"].get("desired") == desired
        if committed:
            if current != desired:
                raise IntegrationError("committed service policy does not match current enablement")
            self._remove_transaction()
            return
        for unit in prior:
            if current[unit] not in {prior[unit], desired[unit]}:
                raise IntegrationError(f"service {unit} drifted during interrupted transaction")
        for unit, old in prior.items():
            if current[unit] != old:
                self._set_service_state(unit, old)
        self._remove_transaction()

    def recover(self) -> None:
        transaction = self._read_transaction()
        if transaction is None:
            return
        if transaction["kind"] == "bluez-adopt":
            self._recover_bluez(transaction)
        elif transaction["kind"] == "service-policy":
            self._recover_services(transaction)
        else:
            raise IntegrationError("unknown system integration transaction")

    def _apply_flatpak(self) -> None:
        status = self._flatpak_status()
        if status.action == "flathub-preserve":
            return
        if status.action != "flathub-add":
            raise IntegrationError(status.detail)
        helper = self._safe_source_file("install/configure-flatpak", "authoritative Flatpak helper")
        if not os.access(helper, os.X_OK):
            raise IntegrationError("authoritative Flatpak helper is missing or unsafe")
        result = self._run([str(helper)])
        after = self._flatpak_status()
        if result.returncode != 0:
            if after.action == "flathub-preserve":
                raise IntegrationError("Flatpak helper reported failure after Flathub became correct; rerun validation")
            raise IntegrationError("Flatpak helper failed: " + (result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"))
        if after.action != "flathub-preserve":
            raise IntegrationError("Flathub remote was not established exactly")

    def apply(self) -> SystemPlan:
        self._require_root_apply()
        with self._mutation_lock():
            self.recover()
            installed, pending = self._base_preflight()
            if pending:
                raise IntegrationError("pending Arch upgrades detected; administrator must complete a normal pacman -Syu before Vanilla package provisioning")
            self._install_official_packages(installed)
            self._bootstrap_yay()
            self._apply_bluez()
            self._apply_flatpak()
            self._apply_services()
            self.validate()
            return self.plan()

    def validate(self) -> SystemPlan:
        transaction = self._read_transaction()
        if transaction is not None:
            raise IntegrationError(f"incomplete {transaction['kind']} transaction requires recovery")
        installed, pending = self._base_preflight()
        if pending:
            raise IntegrationError("pending Arch upgrades remain")
        missing = sorted(set(self.official_default_packages) - installed)
        if missing:
            raise IntegrationError("missing official default packages: " + ", ".join(missing))
        yay = self._yay_status(installed)
        if yay.action != "aur-preserve":
            raise IntegrationError("yay baseline is invalid: " + yay.detail)
        bluez = self._bluez_classification()
        if bluez.action != "bluez-preserve":
            raise IntegrationError("BlueZ adoption is incomplete: " + bluez.detail)
        flatpak = self._flatpak_status()
        if flatpak.action != "flathub-preserve":
            raise IntegrationError("system Flathub is invalid: " + flatpak.detail)
        for unit, desired in self.desired_system_services.items():
            current = self._service_state(unit)
            if current != desired:
                raise IntegrationError(f"service policy mismatch: {unit} is {current}, expected {desired}")
        default_names = set(self.official_default_packages)
        forbidden_direct = {"cups", "cups-pk-helper", "system-config-printer", "avahi", "p7zip"}
        overlap = sorted(default_names & forbidden_direct)
        if overlap:
            raise IntegrationError("non-default/forbidden packages entered default manifest: " + ", ".join(overlap))
        return self.plan()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vanilla HyprArch DF2 system integration")
    parser.add_argument("operation", choices=("plan", "apply", "validate"))
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--target-user", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        integration = SystemIntegration(source_root=arguments.source_root, target_username=arguments.target_user)
        if arguments.operation == "plan":
            plan = integration.plan()
        elif arguments.operation == "apply":
            plan = integration.apply()
        else:
            plan = integration.validate()
        print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
        return 2 if plan.blockers else 0
    except IntegrationError as error:
        print(f"system integration: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
