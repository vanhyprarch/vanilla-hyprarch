#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""Transactionally deploy the Vanilla SDDM theme and session contract."""

from __future__ import annotations

import argparse
import configparser
import contextlib
import ctypes
import dataclasses
import errno
import fcntl
import hashlib
import json
import os
import pwd
import re
import secrets
import shutil
import stat
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Callable, Iterator, Sequence


SCHEMA_VERSION = 1
INTEGRATION_VERSION = 1
SESSION_PATH = "/usr/share/wayland-sessions/vanhyprarch.desktop"
SHADOW_SESSION_PATH = "/usr/local/share/wayland-sessions/vanhyprarch.desktop"
THEME_PATH = "/usr/share/sddm/themes/vanhyprarch"
BINDING_PATH = f"{THEME_PATH}/theme.conf.user"
CONFIG_PATH = "/etc/sddm.conf.d/10-vanhyprarch.conf"
START_HYPRLAND_PATH = "/usr/bin/start-hyprland"
STATE_DIRECTORY = "/var/lib/vanhyprarch/sddm-login"
PROVENANCE_PATH = f"{STATE_DIRECTORY}/provenance-v1.json"
TRANSACTION_PATH = f"{STATE_DIRECTORY}/transaction-v1.json"
LOCK_PATH = f"{STATE_DIRECTORY}/sddm-login.lock"
THEME_SOURCE = "system/usr/share/sddm/themes/vanhyprarch"
SESSION_SOURCE = "system/usr/share/wayland-sessions/vanhyprarch.desktop"
CONFIG_SOURCE = "system/etc/sddm.conf.d/10-vanhyprarch.conf"
CANONICAL_LOGO_SOURCE = "home/.config/quickshell/vanhyprarch/assets/logo.svg"
OWNERSHIP_SOURCE = "deployment/ownership-v2.toml"
THEME_SOURCE_FILES = (
    "LoginScene.qml",
    "Main.qml",
    "SessionResolver.qml",
    "logo.svg",
    "metadata.desktop",
    "theme.conf",
)
THEME_INSTALLED_FILES = (*THEME_SOURCE_FILES, "theme.conf.user")
TRANSACTION_PHASES = {
    "staging",
    "prepared",
    "publishing",
    "verifying",
    "committed",
    "cleaning",
}
USERNAME = re.compile(r"[a-z_][a-z0-9_-]{0,30}\$?\Z")
RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")
TRANSACTION_ID = re.compile(r"[0-9a-f]{32}\Z")
TEST_MODE_ENV = "VANHYPRARCH_SDDM_LOGIN_TESTING"
TEST_FAULT_ENV = "VANHYPRARCH_SDDM_LOGIN_FAULT_AT"


class IntegrationError(RuntimeError):
    """A safe SDDM login integration refusal."""


class SafetyError(IntegrationError):
    """A filesystem boundary, type, owner, or mode is unsafe."""


class ConflictError(IntegrationError):
    """Existing content cannot be proven to be owned by this backend."""


class ValidationError(IntegrationError):
    """Source, staged, or installed content violates the contract."""


@dataclasses.dataclass(frozen=True)
class TargetUser:
    name: str
    uid: int
    gid: int


@dataclasses.dataclass(frozen=True)
class PlanItem:
    action: str
    subject: str
    target: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class DeploymentPlan:
    target_user: str
    items: tuple[PlanItem, ...]

    @property
    def blockers(self) -> tuple[PlanItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.action in {"conflict", "recovery-required"}
        )

    @property
    def changes(self) -> tuple[PlanItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.action.endswith("-create") or item.action.endswith("-update")
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_VERSION,
            "blocked": bool(self.blockers),
            "target_user": self.target_user,
            "items": [item.as_dict() for item in self.items],
        }


FaultHook = Callable[[str], None]
AccountResolver = Callable[[str], TargetUser]


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_CLOEXEC
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_exchange(first: Path, second: Path) -> None:
    """Atomically exchange complete generations using Linux renameat2."""
    library = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(library, "renameat2", None)
    if renameat2 is None:
        raise SafetyError("system deployment requires Linux renameat2")
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(first), -100, os.fsencode(second), 2)
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
            raise SafetyError(
                "target filesystem does not support atomic generation exchange"
            )
        raise OSError(error_number, os.strerror(error_number), os.fspath(second))


def _read_ini_bytes(data: bytes, description: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(data.decode("utf-8"))
    except (UnicodeDecodeError, configparser.Error) as error:
        raise ValidationError(f"invalid {description}: {error}") from error
    return parser


class SddmLoginIntegration:
    """Own only the privileged Vanilla SDDM theme/session payload."""

    def __init__(
        self,
        *,
        target_username: str,
        source_root: str | Path | None = None,
        release_id: str | None = None,
        system_root: str | Path = Path("/"),
        account_resolver: AccountResolver | None = None,
        effective_uid: int | None = None,
        root_identity: tuple[int, int] = (0, 0),
        testing: bool = False,
        fault_hook: FaultHook | None = None,
    ) -> None:
        self.testing = testing
        self.effective_uid = os.geteuid() if effective_uid is None else effective_uid
        self.root_uid, self.root_gid = root_identity
        if release_id is not None and RELEASE_ID.fullmatch(release_id) is None:
            raise IntegrationError("release identity must be a safe opaque identifier")
        self.release_id = release_id
        self.fault_hook = fault_hook or (lambda _point: None)

        root_input = Path(system_root)
        if not root_input.is_absolute():
            raise SafetyError("system root must be absolute")
        self.system_root = Path(os.path.abspath(root_input))
        if self.system_root != Path("/") and not testing:
            raise SafetyError("an alternate system root is available only to isolated tests")
        self._validate_real_directory(self.system_root, "system root")
        root_details = self.system_root.lstat()
        if (root_details.st_uid, root_details.st_gid) != (
            self.root_uid,
            self.root_gid,
        ):
            raise SafetyError("system root has unexpected ownership")
        if root_details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise SafetyError("system root must not be group/world writable")

        self.source_root: Path | None = None
        if source_root is not None:
            source_input = Path(source_root)
            if not source_input.is_absolute():
                raise SafetyError("source root must be explicit and absolute")
            source_path = Path(os.path.abspath(source_input))
            self._validate_real_directory(source_path, "source root")
            current = Path(source_path.anchor)
            for part in source_path.parts[1:]:
                current /= part
                details = os.lstat(current)
                if stat.S_ISLNK(details.st_mode):
                    raise SafetyError(f"source root crosses a symlink: {current}")
                if current != source_path and not stat.S_ISDIR(details.st_mode):
                    raise SafetyError(f"source root parent is not a directory: {current}")
            self.source_root = source_path

        if (
            not isinstance(target_username, str)
            or USERNAME.fullmatch(target_username) is None
        ):
            raise IntegrationError("an explicit non-root target user is required")
        resolver = account_resolver or self._resolve_account
        try:
            target = resolver(target_username)
        except (KeyError, LookupError) as error:
            raise IntegrationError(
                f"target user does not exist: {target_username}"
            ) from error
        if not isinstance(target, TargetUser):
            raise IntegrationError("account resolver returned an invalid account")
        if not USERNAME.fullmatch(target.name):
            raise IntegrationError("target account has an unsupported canonical username")
        if target.uid == 0 or target.name == "root":
            raise IntegrationError("an explicit non-root target user is required")
        if target.uid < 0 or target.gid < 0:
            raise IntegrationError("target account has an invalid numeric identity")
        self.target_user = target

    @staticmethod
    def _resolve_account(name: str) -> TargetUser:
        account = pwd.getpwnam(name)
        return TargetUser(account.pw_name, account.pw_uid, account.pw_gid)

    def _require_root(self) -> None:
        if self.effective_uid != 0:
            raise IntegrationError(
                "SDDM login integration requires root privileges; rerun with sudo"
            )

    @staticmethod
    def _validate_real_directory(path: Path, description: str) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise SafetyError(f"{description} does not exist: {path}") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise SafetyError(f"{description} must be a real directory: {path}")

    def _path(self, absolute: str) -> Path:
        value = Path(absolute)
        if not value.is_absolute() or ".." in value.parts:
            raise SafetyError(f"unsafe fixed system path: {absolute}")
        result = self.system_root / value.relative_to("/")
        try:
            result.relative_to(self.system_root)
        except ValueError as error:
            raise SafetyError(f"system path escaped target root: {absolute}") from error
        return result

    def _check_parent_chain(self, path: Path) -> None:
        if self.system_root not in path.parents and path != self.system_root:
            raise SafetyError(f"path escaped system root: {path}")
        current = self.system_root
        for part in path.relative_to(self.system_root).parts:
            current /= part
            if not _lexists(current):
                continue
            details = os.lstat(current)
            if stat.S_ISLNK(details.st_mode):
                raise SafetyError(f"symlink parent is forbidden: {current}")
            if current != path and not stat.S_ISDIR(details.st_mode):
                raise SafetyError(f"non-directory parent blocks path: {current}")
            if stat.S_ISDIR(details.st_mode):
                if (details.st_uid, details.st_gid) != (
                    self.root_uid,
                    self.root_gid,
                ):
                    raise SafetyError(f"system parent has unexpected ownership: {current}")
                if details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    raise SafetyError(f"system parent is group/world writable: {current}")

    def _ensure_directory(self, path: Path, mode: int) -> None:
        self._check_parent_chain(path)
        missing: list[Path] = []
        current = path
        while not _lexists(current):
            missing.append(current)
            if current == self.system_root:
                break
            current = current.parent
        for directory in reversed(missing):
            wanted = mode if directory == path else 0o755
            os.mkdir(directory, wanted)
            os.chmod(directory, wanted)
            os.chown(directory, self.root_uid, self.root_gid)
            _fsync_directory(directory.parent)
        details = os.lstat(path)
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise SafetyError(f"required directory is unsafe: {path}")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise SafetyError(f"required directory has unexpected ownership: {path}")
        if stat.S_IMODE(details.st_mode) != mode:
            raise SafetyError(
                f"required directory has mode {stat.S_IMODE(details.st_mode):04o}, "
                f"expected {mode:04o}: {path}"
            )

    def _ensure_public_parents(self) -> None:
        for path in (
            self._path(THEME_PATH).parent,
            self._path(SESSION_PATH).parent,
            self._path(CONFIG_PATH).parent,
        ):
            self._ensure_directory(path, 0o755)

    def _ensure_state_directory(self) -> None:
        state = self._path(STATE_DIRECTORY)
        parent = state.parent
        if not _lexists(parent):
            self._ensure_directory(parent, 0o700)
        else:
            self._ensure_directory(parent, 0o700)
        self._ensure_directory(state, 0o700)

    def _source_file(self, relative: str) -> Path:
        if self.source_root is None:
            raise IntegrationError("plan/apply require --source-root")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise SafetyError(f"unsafe source path: {relative}")
        current = self.source_root
        for part in relative_path.parts:
            current /= part
            try:
                details = current.lstat()
            except FileNotFoundError as error:
                raise ValidationError(f"required source is missing: {relative}") from error
            if stat.S_ISLNK(details.st_mode):
                raise SafetyError(f"source path crosses a symlink: {relative}")
        if not stat.S_ISREG(current.lstat().st_mode):
            raise ValidationError(f"source is not a regular file: {relative}")
        return current

    @staticmethod
    def _read_regular(path: Path, description: str) -> bytes:
        flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise SafetyError(f"cannot open safe {description}: {path}: {error}") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise SafetyError(f"{description} is not a regular file: {path}")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def _load_source_files(self) -> tuple[dict[str, bytes], bytes, bytes, bytes]:
        theme_directory = self._source_file(f"{THEME_SOURCE}/Main.qml").parent
        actual = sorted(path.name for path in theme_directory.iterdir())
        if actual != sorted(THEME_SOURCE_FILES):
            raise ValidationError("theme source inventory is not exact")
        theme = {
            name: self._read_regular(
                self._source_file(f"{THEME_SOURCE}/{name}"), f"theme source {name}"
            )
            for name in THEME_SOURCE_FILES
        }
        session = self._read_regular(
            self._source_file(SESSION_SOURCE), "session source"
        )
        config = self._read_regular(
            self._source_file(CONFIG_SOURCE), "SDDM configuration source"
        )
        canonical_logo = self._read_regular(
            self._source_file(CANONICAL_LOGO_SOURCE), "canonical logo"
        )
        self._validate_ownership_manifest()
        self._validate_theme_bytes(theme, canonical_logo=canonical_logo)
        self._validate_session_bytes(session)
        self._validate_config_bytes(config)
        source_bytes = os.fsencode(self.source_root)
        for name, data in (
            *theme.items(),
            ("vanhyprarch.desktop", session),
            ("10-vanhyprarch.conf", config),
        ):
            if source_bytes in data:
                raise ValidationError(f"source checkout path leaked into {name}")
        return theme, session, config, canonical_logo

    def _validate_ownership_manifest(self) -> None:
        path = self._source_file(OWNERSHIP_SOURCE)
        try:
            with path.open("rb") as stream:
                manifest = tomllib.load(stream)
        except tomllib.TOMLDecodeError as error:
            raise ValidationError(f"invalid ownership manifest: {error}") from error
        classes = {
            item.get("name"): item for item in manifest.get("ownership_class", [])
        }
        expected_class = {
            "name": "VANILLA_MANAGED_SYSTEM",
            "deployable": True,
            "source_policy": "required",
            "install_action": "copy-as-root",
            "update_action": "replace-after-validation",
        }
        if classes.get("VANILLA_MANAGED_SYSTEM") != expected_class:
            raise ValidationError("ownership manifest lacks the exact managed-system class")
        records = {item.get("id"): item for item in manifest.get("artifact", [])}
        expected = {
            "sddm-vanilla-theme": {
                "source": THEME_SOURCE,
                "target": THEME_PATH,
                "class": "VANILLA_MANAGED_SYSTEM",
                "kind": "tree",
                "directory_mode": "0755",
                "file_mode": "0644",
                "authority": "vanhyprarch-sddm-login",
            },
            "vanhyprarch-wayland-session": {
                "source": SESSION_SOURCE,
                "target": SESSION_PATH,
                "class": "VANILLA_MANAGED_SYSTEM",
                "kind": "file",
                "mode": "0644",
                "authority": "vanhyprarch-sddm-login",
            },
            "sddm-target-binding": {
                "target": BINDING_PATH,
                "class": "GENERATED",
                "kind": "file",
                "mode": "0644",
                "authority": "vanhyprarch-sddm-login",
            },
            "sddm-vanilla-config": {
                "source": CONFIG_SOURCE,
                "target": CONFIG_PATH,
                "class": "VANILLA_MANAGED_SYSTEM",
                "kind": "file",
                "mode": "0644",
                "authority": "vanhyprarch-sddm-login",
            },
            "sddm-login-state": {
                "target": STATE_DIRECTORY,
                "class": "BACKEND_OWNED",
                "kind": "tree",
                "mode": "0700",
                "authority": "vanhyprarch-sddm-login",
            },
        }
        for identifier, fields in expected.items():
            record = records.get(identifier)
            if not isinstance(record, dict):
                raise ValidationError(f"ownership artifact is missing: {identifier}")
            if any(record.get(key) != value for key, value in fields.items()):
                raise ValidationError(f"ownership artifact is invalid: {identifier}")
        if "source" in records["sddm-target-binding"]:
            raise ValidationError("generated SDDM binding must not have a source")

    @staticmethod
    def _validate_theme_bytes(
        theme: dict[str, bytes], *, canonical_logo: bytes | None = None
    ) -> None:
        if set(theme) != set(THEME_SOURCE_FILES):
            raise ValidationError("immutable theme inventory is not exact")
        if canonical_logo is not None and theme["logo.svg"] != canonical_logo:
            raise ValidationError("SDDM logo differs from the canonical project logo")

        metadata = _read_ini_bytes(theme["metadata.desktop"], "theme metadata")
        if metadata.sections() != ["SddmGreeterTheme"]:
            raise ValidationError("theme metadata has an unexpected section")
        meta = dict(metadata["SddmGreeterTheme"])
        required_meta = {
            "Name": "Vanilla HyprArch",
            "Type": "sddm-theme",
            "MainScript": "Main.qml",
            "ConfigFile": "theme.conf",
            "QtVersion": "6",
            "Theme-Id": "vanhyprarch",
            "Theme-API": "2.0",
            "License": "GPL-2.0-only",
        }
        if any(meta.get(key) != value for key, value in required_meta.items()):
            raise ValidationError("theme metadata contract changed")

        generic = _read_ini_bytes(theme["theme.conf"], "generic theme config")
        if generic.sections() != ["General"] or dict(generic["General"]) != {
            "needsFullUserModel": "false",
            "targetUser": "",
            "targetSessionFile": "",
        }:
            raise ValidationError("generic theme configuration is not reusable")

        try:
            qml = "\n".join(
                theme[name].decode("utf-8")
                for name in ("Main.qml", "LoginScene.qml", "SessionResolver.qml")
            )
            textual_theme = "\n".join(data.decode("utf-8") for data in theme.values())
        except UnicodeDecodeError as error:
            raise ValidationError(f"theme source is not valid UTF-8: {error}") from error
        required = (
            'color: "#000000"',
            'text: "F1 Shutdown"',
            'text: "F2 Reboot"',
            "echoMode: TextInput.Password",
            'configString("targetUser")',
            'configString("targetSessionFile")',
            "required property string file",
            "matches === 1 ? matchingIndex : -1",
        )
        if any(value not in qml for value in required):
            raise ValidationError("theme QML contract is incomplete")
        if qml.count("TextInput {") != 1:
            raise ValidationError("theme must contain exactly one password input")
        for forbidden in (
            "userModel",
            "lastUser",
            "lastIndex",
            "UWSM",
            "uwsm",
            "hostname",
            "hibernate",
            "suspend",
            "/home/",
        ):
            if forbidden in qml:
                raise ValidationError(f"forbidden theme content: {forbidden}")
        if "/home/" in textual_theme:
            raise ValidationError("theme source contains a hardcoded home path")

    @staticmethod
    def _validate_session_bytes(data: bytes) -> None:
        desktop = _read_ini_bytes(data, "Vanilla session entry")
        if desktop.sections() != ["Desktop Entry"] or dict(
            desktop["Desktop Entry"]
        ) != {
            "Name": "Vanilla HyprArch",
            "Comment": "A curated desktop. A vanilla system.",
            "Exec": START_HYPRLAND_PATH,
            "TryExec": START_HYPRLAND_PATH,
            "Type": "Application",
            "DesktopNames": "Hyprland",
        }:
            raise ValidationError("Vanilla session entry contract changed")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(f"session entry is not valid UTF-8: {error}") from error
        if re.search(r"(?i)uwsm|/home/|(?:^|[= ])(?:sh|bash|env)(?:[ /]|$)", text):
            raise ValidationError("session entry contains a forbidden launch path")

    @staticmethod
    def _validate_config_bytes(data: bytes) -> None:
        config = _read_ini_bytes(data, "Vanilla SDDM configuration")
        expected = {
            "General": {"DisplayServer": "x11"},
            "Theme": {"Current": "vanhyprarch", "EnableAvatars": "false"},
            "Users": {
                "RememberLastUser": "false",
                "RememberLastSession": "false",
                "ReuseSession": "false",
            },
        }
        if config.sections() != list(expected) or any(
            dict(config[section]) != values for section, values in expected.items()
        ):
            raise ValidationError("Vanilla SDDM configuration contract changed")
        text = data.decode("utf-8")
        if re.search(r"(?i)autologin|displayserver\s*=\s*wayland|/home/|uwsm", text):
            raise ValidationError("SDDM configuration contains forbidden behavior")

    def _binding_bytes(self) -> bytes:
        return (
            "[General]\n"
            f"targetUser={self.target_user.name}\n"
            f"targetSessionFile={SESSION_PATH}\n"
        ).encode("utf-8")

    @staticmethod
    def _entry(
        relative: str,
        kind: str,
        mode: int,
        uid: int,
        gid: int,
        data: bytes | None = None,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "path": relative,
            "kind": kind,
            "mode": f"0{mode:03o}",
            "uid": uid,
            "gid": gid,
        }
        if data is not None:
            value["sha256"] = _sha256(data)
        return value

    @staticmethod
    def _record(
        identifier: str,
        ownership_class: str,
        target: str,
        kind: str,
        entries: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "id": identifier,
            "class": ownership_class,
            "target": target,
            "kind": kind,
            "digest": _sha256(_canonical_bytes(entries)),
            "entries": entries,
        }

    def _candidate_provenance(self) -> tuple[dict[str, object], dict[str, bytes]]:
        theme, session, config, canonical_logo = self._load_source_files()
        binding = self._binding_bytes()
        theme_entries = [
            self._entry(".", "directory", 0o755, self.root_uid, self.root_gid)
        ]
        for name in sorted(THEME_SOURCE_FILES):
            theme_entries.append(
                self._entry(
                    name,
                    "file",
                    0o644,
                    self.root_uid,
                    self.root_gid,
                    theme[name],
                )
            )
        theme_entries.append(
            self._entry(
                "theme.conf.user",
                "file",
                0o644,
                self.root_uid,
                self.root_gid,
                binding,
            )
        )
        session_entries = [
            self._entry(
                ".", "file", 0o644, self.root_uid, self.root_gid, session
            )
        ]
        binding_entries = [
            self._entry(
                ".", "file", 0o644, self.root_uid, self.root_gid, binding
            )
        ]
        config_entries = [
            self._entry(".", "file", 0o644, self.root_uid, self.root_gid, config)
        ]
        immutable_hashes = {
            f"theme/{name}": _sha256(theme[name]) for name in sorted(theme)
        }
        immutable_hashes["session/vanhyprarch.desktop"] = _sha256(session)
        immutable_hashes["config/10-vanhyprarch.conf"] = _sha256(config)
        artifacts = {
            "sddm-vanilla-theme": self._record(
                "sddm-vanilla-theme",
                "VANILLA_MANAGED_SYSTEM",
                THEME_PATH,
                "tree",
                theme_entries,
            ),
            "vanhyprarch-wayland-session": self._record(
                "vanhyprarch-wayland-session",
                "VANILLA_MANAGED_SYSTEM",
                SESSION_PATH,
                "file",
                session_entries,
            ),
            "sddm-target-binding": self._record(
                "sddm-target-binding",
                "GENERATED",
                BINDING_PATH,
                "file",
                binding_entries,
            ),
            "sddm-vanilla-config": self._record(
                "sddm-vanilla-config",
                "VANILLA_MANAGED_SYSTEM",
                CONFIG_PATH,
                "file",
                config_entries,
            ),
        }
        provenance: dict[str, object] = {
            "schema": SCHEMA_VERSION,
            "integration_version": INTEGRATION_VERSION,
            "status": "complete",
            "target_user": self.target_user.name,
            "target_session": SESSION_PATH,
            "release": {
                "id": self.release_id,
                "sha256": _sha256(_canonical_bytes(immutable_hashes)),
            },
            "canonical_logo_sha256": _sha256(canonical_logo),
            "artifacts": artifacts,
        }
        payload = {
            **theme,
            "theme.conf.user": binding,
            "@session": session,
            "@config": config,
        }
        return provenance, payload

    def _validate_record(self, record: object, identifier: str) -> dict[str, object]:
        if not isinstance(record, dict) or record.get("id") != identifier:
            raise ValidationError(f"invalid provenance record: {identifier}")
        expected = {
            "sddm-vanilla-theme": (
                "VANILLA_MANAGED_SYSTEM",
                THEME_PATH,
                "tree",
            ),
            "vanhyprarch-wayland-session": (
                "VANILLA_MANAGED_SYSTEM",
                SESSION_PATH,
                "file",
            ),
            "sddm-target-binding": ("GENERATED", BINDING_PATH, "file"),
            "sddm-vanilla-config": (
                "VANILLA_MANAGED_SYSTEM",
                CONFIG_PATH,
                "file",
            ),
        }[identifier]
        if (
            record.get("class"),
            record.get("target"),
            record.get("kind"),
        ) != expected:
            raise ValidationError(f"provenance identity changed: {identifier}")
        entries = record.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValidationError(f"provenance entries are invalid: {identifier}")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) not in (
                {"path", "kind", "mode", "uid", "gid"},
                {"path", "kind", "mode", "uid", "gid", "sha256"},
            ):
                raise ValidationError(f"invalid provenance entry: {identifier}")
            if entry.get("uid") != self.root_uid or entry.get("gid") != self.root_gid:
                raise ValidationError(f"provenance owner changed: {identifier}")
        if record.get("digest") != _sha256(_canonical_bytes(entries)):
            raise ValidationError(f"provenance digest mismatch: {identifier}")
        return record

    def _validate_provenance(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict) or value.get("schema") != SCHEMA_VERSION:
            raise ValidationError("unsupported SDDM login provenance schema")
        if value.get("integration_version") != INTEGRATION_VERSION:
            raise ValidationError("unsupported SDDM login integration version")
        if value.get("status") != "complete" or value.get("target_session") != SESSION_PATH:
            raise ValidationError("SDDM login provenance is incomplete")
        user = value.get("target_user")
        if not isinstance(user, str) or USERNAME.fullmatch(user) is None:
            raise ValidationError("SDDM login provenance has an invalid target user")
        release = value.get("release")
        if (
            not isinstance(release, dict)
            or not isinstance(release.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", release["sha256"]) is None
            or release.get("id") is not None
            and (
                not isinstance(release.get("id"), str)
                or RELEASE_ID.fullmatch(release["id"]) is None
            )
        ):
            raise ValidationError("SDDM login provenance has invalid release identity")
        logo = value.get("canonical_logo_sha256")
        if not isinstance(logo, str) or re.fullmatch(r"[0-9a-f]{64}", logo) is None:
            raise ValidationError("SDDM login provenance has invalid logo identity")
        artifacts = value.get("artifacts")
        expected_ids = {
            "sddm-vanilla-theme",
            "vanhyprarch-wayland-session",
            "sddm-target-binding",
            "sddm-vanilla-config",
        }
        if not isinstance(artifacts, dict) or set(artifacts) != expected_ids:
            raise ValidationError("SDDM login provenance inventory is invalid")
        for identifier in expected_ids:
            self._validate_record(artifacts[identifier], identifier)
        theme_entries = {
            item["path"]: item for item in artifacts["sddm-vanilla-theme"]["entries"]
        }
        logo_entry = theme_entries.get("logo.svg")
        if not isinstance(logo_entry, dict) or logo_entry.get("sha256") != logo:
            raise ValidationError("canonical logo provenance is inconsistent")
        binding_entries = artifacts["sddm-target-binding"]["entries"]
        theme_binding = theme_entries.get("theme.conf.user")
        if (
            len(binding_entries) != 1
            or not isinstance(theme_binding, dict)
            or {
                key: value
                for key, value in binding_entries[0].items()
                if key != "path"
            }
            != {
                key: value for key, value in theme_binding.items() if key != "path"
            }
        ):
            raise ValidationError("generated binding provenance is inconsistent")
        return value

    def _validate_owned_file(self, path: Path, mode: int, description: str) -> bytes:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise ValidationError(f"{description} is missing: {path}") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise ValidationError(f"{description} is not a regular file: {path}")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise ValidationError(f"{description} has unexpected ownership: {path}")
        if stat.S_IMODE(details.st_mode) != mode:
            raise ValidationError(f"{description} has unexpected mode: {path}")
        return self._read_regular(path, description)

    def _snapshot_file(
        self, path: Path, identifier: str, ownership_class: str, target: str
    ) -> dict[str, object]:
        data = self._validate_owned_file(path, 0o644, identifier)
        return self._record(
            identifier,
            ownership_class,
            target,
            "file",
            [
                self._entry(
                    ".", "file", 0o644, self.root_uid, self.root_gid, data
                )
            ],
        )

    def _snapshot_theme(self) -> tuple[dict[str, object], dict[str, bytes]]:
        root = self._path(THEME_PATH)
        try:
            details = root.lstat()
        except FileNotFoundError as error:
            raise ValidationError("installed Vanilla SDDM theme is missing") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise ValidationError("installed Vanilla SDDM theme is not a real directory")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise ValidationError("installed Vanilla SDDM theme has unexpected ownership")
        if stat.S_IMODE(details.st_mode) != 0o755:
            raise ValidationError("installed Vanilla SDDM theme has unexpected mode")
        names = sorted(path.name for path in root.iterdir())
        if names != sorted(THEME_INSTALLED_FILES):
            raise ValidationError("installed Vanilla SDDM theme inventory is not exact")
        entries = [
            self._entry(".", "directory", 0o755, self.root_uid, self.root_gid)
        ]
        data: dict[str, bytes] = {}
        for name in names:
            content = self._validate_owned_file(root / name, 0o644, f"theme {name}")
            data[name] = content
            entries.append(
                self._entry(
                    name,
                    "file",
                    0o644,
                    self.root_uid,
                    self.root_gid,
                    content,
                )
            )
        return (
            self._record(
                "sddm-vanilla-theme",
                "VANILLA_MANAGED_SYSTEM",
                THEME_PATH,
                "tree",
                entries,
            ),
            data,
        )

    def _live_records(
        self, *, validate_semantics: bool
    ) -> tuple[dict[str, dict[str, object]], dict[str, bytes]]:
        theme_record, theme_data = self._snapshot_theme()
        session_path = self._path(SESSION_PATH)
        session_record = self._snapshot_file(
            session_path,
            "vanhyprarch-wayland-session",
            "VANILLA_MANAGED_SYSTEM",
            SESSION_PATH,
        )
        binding_record = self._snapshot_file(
            self._path(BINDING_PATH),
            "sddm-target-binding",
            "GENERATED",
            BINDING_PATH,
        )
        config_path = self._path(CONFIG_PATH)
        config_record = self._snapshot_file(
            config_path,
            "sddm-vanilla-config",
            "VANILLA_MANAGED_SYSTEM",
            CONFIG_PATH,
        )
        if validate_semantics:
            immutable = {name: theme_data[name] for name in THEME_SOURCE_FILES}
            self._validate_theme_bytes(immutable)
            self._validate_session_bytes(self._read_regular(session_path, "session"))
            expected_binding = self._binding_bytes()
            if theme_data["theme.conf.user"] != expected_binding:
                raise ValidationError("generated SDDM target binding is invalid")
            self._validate_config_bytes(
                self._read_regular(config_path, "Vanilla SDDM configuration")
            )
        return (
            {
                "sddm-vanilla-theme": theme_record,
                "vanhyprarch-wayland-session": session_record,
                "sddm-target-binding": binding_record,
                "sddm-vanilla-config": config_record,
            },
            theme_data,
        )

    def _read_json_file(self, path: Path, description: str) -> tuple[object, bytes]:
        data = self._validate_owned_file(path, 0o600, description)
        try:
            return json.loads(data), data
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError(f"invalid {description}: {error}") from error

    def _read_provenance(self) -> tuple[dict[str, object] | None, bytes | None]:
        path = self._path(PROVENANCE_PATH)
        if not _lexists(path):
            return None, None
        value, data = self._read_json_file(path, "SDDM login provenance")
        return self._validate_provenance(value), data

    def _read_transaction(self) -> tuple[dict[str, object] | None, bytes | None]:
        path = self._path(TRANSACTION_PATH)
        if not _lexists(path):
            return None, None
        value, data = self._read_json_file(path, "SDDM login transaction")
        if not isinstance(value, dict) or value.get("schema") != SCHEMA_VERSION:
            raise ValidationError("unsupported SDDM login transaction schema")
        identifier = value.get("id")
        if not isinstance(identifier, str) or TRANSACTION_ID.fullmatch(identifier) is None:
            raise ValidationError("SDDM login transaction ID is invalid")
        if value.get("phase") not in TRANSACTION_PHASES:
            raise ValidationError("SDDM login transaction phase is invalid")
        if value.get("target_user") != self.target_user.name:
            raise ConflictError("incomplete SDDM transaction belongs to another target user")
        candidate = self._validate_provenance(value.get("candidate"))
        prior = value.get("prior")
        if prior is not None:
            self._validate_provenance(prior)
        changes = value.get("changes")
        if not isinstance(changes, dict) or set(changes) != {
            "session",
            "theme",
            "config",
        }:
            raise ValidationError("SDDM login transaction changes are invalid")
        if not all(isinstance(item, bool) for item in changes.values()):
            raise ValidationError("SDDM login transaction changes are malformed")
        expected_containers = {
            "session": f".vanhyprarch-sddm-login-{identifier}-session",
            "theme": f".vanhyprarch-sddm-login-{identifier}-theme",
            "config": f".vanhyprarch-sddm-login-{identifier}-config",
        }
        if value.get("containers") != expected_containers:
            raise ValidationError("SDDM login transaction containers are invalid")
        value["candidate"] = candidate
        return value, data

    def _state_inventory_error(self, *, internal: bool = False) -> str | None:
        state = self._path(STATE_DIRECTORY)
        if not _lexists(state):
            return None
        try:
            details = os.lstat(state)
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
                return "root-private state path is not a real directory"
            if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
                return "root-private state directory has unexpected ownership"
            if stat.S_IMODE(details.st_mode) != 0o700:
                return "root-private state directory must have mode 0700"
            names = {path.name for path in state.iterdir()}
        except OSError as error:
            return f"root-private state is unreadable: {error}"
        allowed = {
            Path(PROVENANCE_PATH).name,
            Path(TRANSACTION_PATH).name,
            Path(LOCK_PATH).name,
        }
        if names - allowed:
            return "root-private state contains unexpected files"
        if Path(LOCK_PATH).name in names:
            try:
                self._validate_owned_file(
                    self._path(LOCK_PATH), 0o600, "SDDM login integration lock"
                )
            except IntegrationError as error:
                return str(error)
        if (
            not internal
            and not _lexists(self._path(PROVENANCE_PATH))
            and not _lexists(self._path(TRANSACTION_PATH))
            and names != {Path(LOCK_PATH).name}
        ):
            return "pre-existing root-private state lacks Vanilla provenance"
        return None

    def _prerequisite_error(self) -> str | None:
        path = self._path(START_HYPRLAND_PATH)
        try:
            details = path.lstat()
        except FileNotFoundError:
            return f"{START_HYPRLAND_PATH} is missing"
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            return f"{START_HYPRLAND_PATH} is not a regular executable"
        if not details.st_mode & 0o111:
            return f"{START_HYPRLAND_PATH} is not executable"
        return None

    def _shadow_error(self) -> str | None:
        shadow = self._path(SHADOW_SESSION_PATH)
        self._check_parent_chain(shadow)
        if _lexists(shadow):
            return f"shadowing session entry exists: {SHADOW_SESSION_PATH}"
        return None

    def _plan(self, *, internal: bool = False) -> DeploymentPlan:
        self._require_root()
        if self.source_root is None:
            raise IntegrationError("plan requires --source-root")
        items: list[PlanItem] = []

        for path in (
            self._path(THEME_PATH),
            self._path(SESSION_PATH),
            self._path(CONFIG_PATH),
            self._path(STATE_DIRECTORY),
            self._path(SHADOW_SESSION_PATH),
        ):
            try:
                self._check_parent_chain(path)
            except IntegrationError as error:
                items.append(PlanItem("conflict", "path-safety", str(path), str(error)))
                return DeploymentPlan(self.target_user.name, tuple(items))

        state_error = self._state_inventory_error(internal=internal)
        if state_error is not None:
            items.append(PlanItem("conflict", "provenance", STATE_DIRECTORY, state_error))
            return DeploymentPlan(self.target_user.name, tuple(items))
        transaction, _transaction_raw = self._read_transaction()
        if transaction is not None:
            items.append(
                PlanItem(
                    "recovery-required",
                    "transaction",
                    TRANSACTION_PATH,
                    f"incomplete transaction is {transaction['phase']}",
                )
            )
            return DeploymentPlan(self.target_user.name, tuple(items))

        candidate, _payload = self._candidate_provenance()

        shadow_error = self._shadow_error()
        if shadow_error is not None:
            items.append(
                PlanItem("conflict", "session-shadow", SHADOW_SESSION_PATH, shadow_error)
            )
        prerequisite_error = self._prerequisite_error()
        if prerequisite_error is not None:
            items.append(
                PlanItem(
                    "conflict",
                    "runtime-prerequisite",
                    START_HYPRLAND_PATH,
                    prerequisite_error,
                )
            )

        provenance, _raw = self._read_provenance()
        if provenance is None:
            theme_exists = _lexists(self._path(THEME_PATH))
            session_exists = _lexists(self._path(SESSION_PATH))
            config_exists = _lexists(self._path(CONFIG_PATH))
            items.append(
                PlanItem(
                    "conflict" if theme_exists else "system-create",
                    "sddm-vanilla-theme",
                    THEME_PATH,
                    "pre-existing theme is not provenance-proven"
                    if theme_exists
                    else "install complete Vanilla theme generation",
                )
            )
            items.append(
                PlanItem(
                    "conflict" if config_exists else "system-create",
                    "sddm-vanilla-config",
                    CONFIG_PATH,
                    "pre-existing SDDM drop-in is not provenance-proven"
                    if config_exists
                    else "install Vanilla X11 greeter and theme selection policy",
                )
            )
            items.append(
                PlanItem(
                    "conflict" if session_exists else "system-create",
                    "vanhyprarch-wayland-session",
                    SESSION_PATH,
                    "pre-existing session is not provenance-proven"
                    if session_exists
                    else "install direct Vanilla Wayland session",
                )
            )
            items.append(
                PlanItem(
                    "conflict" if theme_exists else "generated-create",
                    "sddm-target-binding",
                    BINDING_PATH,
                    "pre-existing theme may contain an unproven generated binding"
                    if theme_exists
                    else f"bind greeter to canonical user {self.target_user.name}",
                )
            )
            items.append(
                PlanItem(
                    "state-create",
                    "sddm-login-state",
                    PROVENANCE_PATH,
                    "record root-private deployment provenance",
                )
            )
            return DeploymentPlan(self.target_user.name, tuple(items))

        if provenance["target_user"] != self.target_user.name:
            items.append(
                PlanItem(
                    "conflict",
                    "target-user",
                    BINDING_PATH,
                    "v1 greeter binding is already owned by another target user; "
                    "an explicit future migration is required",
                )
            )
            return DeploymentPlan(self.target_user.name, tuple(items))
        try:
            live, _data = self._live_records(validate_semantics=True)
        except IntegrationError as error:
            items.append(
                PlanItem(
                    "conflict",
                    "installed-state",
                    THEME_PATH,
                    f"provenance-proven deployment diverged: {error}",
                )
            )
            return DeploymentPlan(self.target_user.name, tuple(items))
        if live != provenance["artifacts"]:
            items.append(
                PlanItem(
                    "conflict",
                    "installed-state",
                    THEME_PATH,
                    "managed files differ from root-private provenance",
                )
            )
            return DeploymentPlan(self.target_user.name, tuple(items))

        prior_artifacts = provenance["artifacts"]
        candidate_artifacts = candidate["artifacts"]
        theme_change = (
            prior_artifacts["sddm-vanilla-theme"]
            != candidate_artifacts["sddm-vanilla-theme"]
        )
        session_change = (
            prior_artifacts["vanhyprarch-wayland-session"]
            != candidate_artifacts["vanhyprarch-wayland-session"]
        )
        config_change = (
            prior_artifacts["sddm-vanilla-config"]
            != candidate_artifacts["sddm-vanilla-config"]
        )
        state_change = provenance != candidate
        items.extend(
            (
                PlanItem(
                    "system-update" if theme_change else "system-preserve",
                    "sddm-vanilla-theme",
                    THEME_PATH,
                    "publish changed complete theme generation"
                    if theme_change
                    else "installed theme matches source and provenance",
                ),
                PlanItem(
                    "system-update" if session_change else "system-preserve",
                    "vanhyprarch-wayland-session",
                    SESSION_PATH,
                    "publish changed session entry"
                    if session_change
                    else "installed session matches source and provenance",
                ),
                PlanItem(
                    "generated-update" if theme_change else "generated-preserve",
                    "sddm-target-binding",
                    BINDING_PATH,
                    "republish deterministic binding inside the changed theme generation"
                    if theme_change
                    else "generated binding matches target-user provenance",
                ),
                PlanItem(
                    "system-update" if config_change else "system-preserve",
                    "sddm-vanilla-config",
                    CONFIG_PATH,
                    "publish changed SDDM configuration"
                    if config_change
                    else "installed SDDM configuration matches source and provenance",
                ),
                PlanItem(
                    "state-update" if state_change else "state-preserve",
                    "sddm-login-state",
                    PROVENANCE_PATH,
                    "advance root-private release provenance"
                    if state_change
                    else "provenance already describes the installed release",
                ),
            )
        )
        return DeploymentPlan(self.target_user.name, tuple(items))

    def plan(self) -> DeploymentPlan:
        return self._plan(internal=False)

    def _atomic_write(self, path: Path, data: bytes, mode: int) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, mode)
            os.fchown(descriptor, self.root_uid, self.root_gid)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _fsync_directory(path.parent)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise

    @contextlib.contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        self._ensure_state_directory()
        path = self._path(LOCK_PATH)
        flags = os.O_RDWR | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        created = False
        try:
            descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            descriptor = os.open(path, flags)
        try:
            if created:
                os.fchmod(descriptor, 0o600)
                os.fchown(descriptor, self.root_uid, self.root_gid)
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or (
                details.st_uid,
                details.st_gid,
            ) != (self.root_uid, self.root_gid):
                raise SafetyError("SDDM login integration lock is unsafe")
            if stat.S_IMODE(details.st_mode) != 0o600:
                raise SafetyError("SDDM login integration lock must have mode 0600")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ConflictError(
                    "another SDDM login integration mutation is active"
                ) from error
            _fsync_directory(path.parent)
            yield
        finally:
            os.close(descriptor)

    def _fault(self, point: str) -> None:
        self.fault_hook(point)
        if (
            self.testing
            and os.environ.get(TEST_MODE_ENV) == "1"
            and os.environ.get(TEST_FAULT_ENV) == point
        ):
            os._exit(197)

    def _write_transaction(self, transaction: dict[str, object], phase: str) -> None:
        if phase not in TRANSACTION_PHASES:
            raise ValueError(f"invalid transaction phase: {phase}")
        updated = dict(transaction)
        updated["phase"] = phase
        self._atomic_write(
            self._path(TRANSACTION_PATH), _canonical_bytes(updated), 0o600
        )
        transaction.clear()
        transaction.update(updated)

    def _remove_transaction(self) -> None:
        path = self._path(TRANSACTION_PATH)
        if _lexists(path):
            self._validate_owned_file(path, 0o600, "SDDM login transaction")
            path.unlink()
            _fsync_directory(path.parent)

    def _container_path(self, transaction: dict[str, object], kind: str) -> Path:
        name = transaction["containers"][kind]
        parent = {
            "session": self._path(SESSION_PATH).parent,
            "theme": self._path(THEME_PATH).parent,
            "config": self._path(CONFIG_PATH).parent,
        }[kind]
        expected = f".vanhyprarch-sddm-login-{transaction['id']}-{kind}"
        if name != expected or Path(name).name != name:
            raise ValidationError("transaction container identity is invalid")
        return parent / name

    def _create_private_container(self, path: Path) -> None:
        if _lexists(path):
            raise ConflictError(f"transaction container already exists: {path}")
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        os.chown(path, self.root_uid, self.root_gid)
        _fsync_directory(path.parent)

    def _write_payload_file(self, path: Path, data: bytes, mode: int) -> None:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        try:
            os.fchmod(descriptor, mode)
            os.fchown(descriptor, self.root_uid, self.root_gid)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)

    def _stage(self, transaction: dict[str, object], payload: dict[str, bytes]) -> None:
        changes = transaction["changes"]
        if changes["theme"]:
            container = self._container_path(transaction, "theme")
            self._create_private_container(container)
            root = container / "payload"
            os.mkdir(root, 0o755)
            os.chmod(root, 0o755)
            os.chown(root, self.root_uid, self.root_gid)
            for index, name in enumerate(sorted(THEME_SOURCE_FILES)):
                self._write_payload_file(root / name, payload[name], 0o644)
                if index == 0:
                    self._fault("during-theme-staging")
            _fsync_directory(root)
            self._fault("after-theme-staging")
        if changes["session"]:
            container = self._container_path(transaction, "session")
            self._create_private_container(container)
            self._write_payload_file(container / "payload", payload["@session"], 0o644)
            _fsync_directory(container)
            self._fault("after-session-staging")
        if changes["config"]:
            container = self._container_path(transaction, "config")
            self._create_private_container(container)
            self._write_payload_file(container / "payload", payload["@config"], 0o644)
            _fsync_directory(container)
            self._fault("after-config-staging")
        if changes["theme"]:
            root = self._container_path(transaction, "theme") / "payload"
            self._write_payload_file(
                root / "theme.conf.user", payload["theme.conf.user"], 0o644
            )
            _fsync_directory(root)
            _fsync_directory(root.parent)
            self._fault("after-generated-binding-staging")
        self._write_transaction(transaction, "prepared")

    def _path_matches_record(self, path: Path, record: dict[str, object]) -> bool:
        try:
            if record["kind"] == "tree":
                actual, _data = self._snapshot_theme_at(path)
            else:
                actual = self._snapshot_file_at(path, record)
        except IntegrationError:
            return False
        return actual == record

    def _snapshot_file_at(
        self, path: Path, record: dict[str, object]
    ) -> dict[str, object]:
        data = self._validate_owned_file(path, 0o644, str(record["id"]))
        return self._record(
            str(record["id"]),
            str(record["class"]),
            str(record["target"]),
            "file",
            [self._entry(".", "file", 0o644, self.root_uid, self.root_gid, data)],
        )

    def _snapshot_theme_at(
        self, path: Path
    ) -> tuple[dict[str, object], dict[str, bytes]]:
        expected_path = self._path(THEME_PATH)
        if path == expected_path:
            return self._snapshot_theme()
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise ValidationError("theme generation is absent") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise ValidationError("theme generation is not a directory")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise ValidationError("theme generation owner mismatch")
        if stat.S_IMODE(details.st_mode) != 0o755:
            raise ValidationError("theme generation mode mismatch")
        names = sorted(item.name for item in path.iterdir())
        if names != sorted(THEME_INSTALLED_FILES):
            raise ValidationError("theme generation inventory mismatch")
        entries = [self._entry(".", "directory", 0o755, self.root_uid, self.root_gid)]
        data: dict[str, bytes] = {}
        for name in names:
            content = self._validate_owned_file(path / name, 0o644, f"theme {name}")
            data[name] = content
            entries.append(
                self._entry(name, "file", 0o644, self.root_uid, self.root_gid, content)
            )
        return (
            self._record(
                "sddm-vanilla-theme",
                "VANILLA_MANAGED_SYSTEM",
                THEME_PATH,
                "tree",
                entries,
            ),
            data,
        )

    def _publish_one(
        self,
        transaction: dict[str, object],
        kind: str,
        prior: dict[str, object] | None,
        candidate: dict[str, object],
    ) -> None:
        destination = self._path(
            {
                "session": SESSION_PATH,
                "theme": THEME_PATH,
                "config": CONFIG_PATH,
            }[kind]
        )
        container = self._container_path(transaction, kind)
        payload = container / "payload"
        if prior is None:
            if _lexists(destination) or not self._path_matches_record(payload, candidate):
                raise ConflictError(f"prepared {kind} create state changed")
            os.replace(payload, destination)
        else:
            if not self._path_matches_record(destination, prior):
                raise ConflictError(f"installed {kind} changed before publication")
            if not self._path_matches_record(payload, candidate):
                raise ConflictError(f"staged {kind} candidate changed before publication")
            _atomic_exchange(payload, destination)
        _fsync_directory(container)
        _fsync_directory(destination.parent)
        if not self._path_matches_record(destination, candidate):
            raise ValidationError(f"published {kind} candidate failed verification")

    def _publish(self, transaction: dict[str, object]) -> None:
        self._write_transaction(transaction, "publishing")
        prior = transaction["prior"]
        candidate = transaction["candidate"]
        prior_artifacts = {} if prior is None else prior["artifacts"]
        candidate_artifacts = candidate["artifacts"]
        if transaction["changes"]["session"]:
            self._publish_one(
                transaction,
                "session",
                prior_artifacts.get("vanhyprarch-wayland-session"),
                candidate_artifacts["vanhyprarch-wayland-session"],
            )
            self._fault("after-first-publication")
        if transaction["changes"]["theme"]:
            self._fault("before-final-publication")
            self._publish_one(
                transaction,
                "theme",
                prior_artifacts.get("sddm-vanilla-theme"),
                candidate_artifacts["sddm-vanilla-theme"],
            )
        if transaction["changes"]["config"]:
            self._publish_one(
                transaction,
                "config",
                prior_artifacts.get("sddm-vanilla-config"),
                candidate_artifacts["sddm-vanilla-config"],
            )
        self._write_transaction(transaction, "verifying")

    def _remove_container(self, path: Path) -> None:
        if not _lexists(path):
            return
        details = os.lstat(path)
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise SafetyError(f"transaction container is unsafe: {path}")
        if (details.st_uid, details.st_gid) != (self.root_uid, self.root_gid):
            raise SafetyError(f"transaction container owner changed: {path}")
        for current, directories, files in os.walk(path, topdown=True, followlinks=False):
            for name in (*directories, *files):
                child = Path(current) / name
                child_details = os.lstat(child)
                if stat.S_ISLNK(child_details.st_mode) or not (
                    stat.S_ISDIR(child_details.st_mode)
                    or stat.S_ISREG(child_details.st_mode)
                ):
                    raise SafetyError(f"unsafe transaction content: {child}")
                if (child_details.st_uid, child_details.st_gid) != (
                    self.root_uid,
                    self.root_gid,
                ):
                    raise SafetyError(f"transaction content owner changed: {child}")
        shutil.rmtree(path)
        _fsync_directory(path.parent)

    def _restore_one(
        self,
        transaction: dict[str, object],
        kind: str,
        prior: dict[str, object] | None,
        candidate: dict[str, object],
    ) -> None:
        destination = self._path(
            {
                "session": SESSION_PATH,
                "theme": THEME_PATH,
                "config": CONFIG_PATH,
            }[kind]
        )
        container = self._container_path(transaction, kind)
        payload = container / "payload"
        if not _lexists(container):
            if prior is None:
                if _lexists(destination):
                    raise ConflictError(f"untracked {kind} appeared during recovery")
            elif not self._path_matches_record(destination, prior):
                raise ConflictError(f"prior {kind} changed during recovery")
            return
        destination_is_prior = prior is not None and self._path_matches_record(
            destination, prior
        )
        destination_is_candidate = self._path_matches_record(destination, candidate)
        payload_is_prior = prior is not None and self._path_matches_record(payload, prior)
        payload_is_candidate = self._path_matches_record(payload, candidate)
        if prior is None:
            if destination_is_candidate and not _lexists(payload):
                os.replace(destination, payload)
                _fsync_directory(destination.parent)
                _fsync_directory(container)
            elif not _lexists(destination) and payload_is_candidate:
                pass
            elif not _lexists(destination) and not _lexists(payload):
                pass
            else:
                raise ConflictError(f"ambiguous new {kind} state during recovery")
        else:
            if destination_is_candidate and payload_is_prior:
                _atomic_exchange(destination, payload)
                _fsync_directory(destination.parent)
                _fsync_directory(container)
            elif destination_is_prior and payload_is_candidate:
                pass
            elif destination_is_prior and not _lexists(payload):
                pass
            else:
                raise ConflictError(f"ambiguous updated {kind} state during recovery")
        self._remove_container(container)

    def _cleanup_committed(self, transaction: dict[str, object]) -> None:
        candidate = transaction["candidate"]["artifacts"]
        removed = 0
        for kind, identifier in (
            ("session", "vanhyprarch-wayland-session"),
            ("theme", "sddm-vanilla-theme"),
            ("config", "sddm-vanilla-config"),
        ):
            if not transaction["changes"][kind]:
                continue
            destination = self._path(
                {
                    "session": SESSION_PATH,
                    "theme": THEME_PATH,
                    "config": CONFIG_PATH,
                }[kind]
            )
            if not self._path_matches_record(destination, candidate[identifier]):
                raise ConflictError(f"committed {kind} candidate drifted")
            self._remove_container(self._container_path(transaction, kind))
            removed += 1
            if removed == 1:
                self._fault("during-cleanup")

    def _recover_locked(self) -> bool:
        transaction, _raw = self._read_transaction()
        if transaction is None:
            return False
        provenance, provenance_raw = self._read_provenance()
        candidate_raw = _canonical_bytes(transaction["candidate"])
        prior = transaction["prior"]
        prior_raw = None if prior is None else _canonical_bytes(prior)
        committed = provenance_raw == candidate_raw
        precommit = provenance_raw == prior_raw
        if not committed and not precommit:
            raise ConflictError(
                "transaction provenance matches neither prior nor candidate state"
            )
        if committed:
            self._cleanup_committed(transaction)
        else:
            prior_artifacts = {} if prior is None else prior["artifacts"]
            candidate_artifacts = transaction["candidate"]["artifacts"]
            if transaction["phase"] in {"staging", "prepared"}:
                for kind, identifier in (
                    ("theme", "sddm-vanilla-theme"),
                    ("session", "vanhyprarch-wayland-session"),
                    ("config", "sddm-vanilla-config"),
                ):
                    if not transaction["changes"][kind]:
                        continue
                    destination = self._path(
                        {
                            "session": SESSION_PATH,
                            "theme": THEME_PATH,
                            "config": CONFIG_PATH,
                        }[kind]
                    )
                    old_record = prior_artifacts.get(identifier)
                    if old_record is None:
                        if _lexists(destination):
                            raise ConflictError(
                                f"new {kind} appeared before publication"
                            )
                    elif not self._path_matches_record(destination, old_record):
                        raise ConflictError(f"prior {kind} changed during staging")
                    self._remove_container(self._container_path(transaction, kind))
            else:
                for kind, identifier in (
                    ("theme", "sddm-vanilla-theme"),
                    ("session", "vanhyprarch-wayland-session"),
                    ("config", "sddm-vanilla-config"),
                ):
                    if transaction["changes"][kind]:
                        self._restore_one(
                            transaction,
                            kind,
                            prior_artifacts.get(identifier),
                            candidate_artifacts[identifier],
                        )
        self._remove_transaction()
        return True

    def recover(self) -> bool:
        self._require_root()
        with self._mutation_lock():
            return self._recover_locked()

    def _validate_live_against(self, provenance: dict[str, object]) -> None:
        if provenance["target_user"] != self.target_user.name:
            raise ConflictError(
                "installed greeter is bound to another target user; rebinding is unsupported"
            )
        live, theme_data = self._live_records(validate_semantics=True)
        if live != provenance["artifacts"]:
            raise ValidationError("installed SDDM login files differ from provenance")
        if _sha256(theme_data["logo.svg"]) != provenance["canonical_logo_sha256"]:
            raise ValidationError("installed logo differs from canonical deployment provenance")

    def apply(self) -> DeploymentPlan:
        self._require_root()
        if self.source_root is None:
            raise IntegrationError("apply requires --source-root")
        initial_plan = self.plan()
        hard_blockers = tuple(
            item for item in initial_plan.blockers if item.action != "recovery-required"
        )
        if hard_blockers:
            raise ConflictError(
                "; ".join(f"{item.subject}: {item.detail}" for item in hard_blockers)
            )
        self._fault("before-transaction-intent")
        with self._mutation_lock():
            self._recover_locked()
            plan = self._plan(internal=True)
            if plan.blockers:
                raise ConflictError(
                    "; ".join(f"{item.subject}: {item.detail}" for item in plan.blockers)
                )
            if not plan.changes:
                self._validate_installed_locked()
                return plan
            candidate, payload = self._candidate_provenance()
            prior, _prior_raw = self._read_provenance()
            prior_artifacts = {} if prior is None else prior["artifacts"]
            candidate_artifacts = candidate["artifacts"]
            transaction_id = secrets.token_hex(16)
            transaction: dict[str, object] = {
                "schema": SCHEMA_VERSION,
                "id": transaction_id,
                "phase": "staging",
                "target_user": self.target_user.name,
                "prior": prior,
                "candidate": candidate,
                "changes": {
                    "session": prior_artifacts.get("vanhyprarch-wayland-session")
                    != candidate_artifacts["vanhyprarch-wayland-session"],
                    "theme": prior_artifacts.get("sddm-vanilla-theme")
                    != candidate_artifacts["sddm-vanilla-theme"],
                    "config": prior_artifacts.get("sddm-vanilla-config")
                    != candidate_artifacts["sddm-vanilla-config"],
                },
                "containers": {
                    "session": f".vanhyprarch-sddm-login-{transaction_id}-session",
                    "theme": f".vanhyprarch-sddm-login-{transaction_id}-theme",
                    "config": f".vanhyprarch-sddm-login-{transaction_id}-config",
                },
            }
            try:
                self._write_transaction(transaction, "staging")
                self._fault("after-transaction-intent")
                self._ensure_public_parents()
                self._stage(transaction, payload)
                self._publish(transaction)
                self._validate_live_against(candidate)
                self._fault("after-live-verification")
                self._fault("before-provenance-commit")
                self._atomic_write(
                    self._path(PROVENANCE_PATH), _canonical_bytes(candidate), 0o600
                )
                self._fault("after-provenance-commit")
                self._write_transaction(transaction, "committed")
                self._write_transaction(transaction, "cleaning")
                self._cleanup_committed(transaction)
                self._remove_transaction()
                self._validate_installed_locked()
                return plan
            except Exception:
                try:
                    self._recover_locked()
                except Exception:
                    pass
                raise

    def _validate_state_inventory(self) -> None:
        error = self._state_inventory_error(internal=True)
        if error is not None:
            raise ValidationError(error)
        state = self._path(STATE_DIRECTORY)
        names = {path.name for path in state.iterdir()}
        allowed = {Path(PROVENANCE_PATH).name, Path(LOCK_PATH).name}
        if names - allowed or Path(PROVENANCE_PATH).name not in names:
            raise ValidationError("root-private state inventory is not complete")
        if Path(LOCK_PATH).name in names:
            self._validate_owned_file(self._path(LOCK_PATH), 0o600, "integration lock")

    def _validate_installed_locked(self) -> DeploymentPlan:
        transaction, _raw = self._read_transaction()
        if transaction is not None:
            raise ValidationError(
                f"incomplete SDDM login transaction requires recovery: {transaction['phase']}"
            )
        self._validate_state_inventory()
        provenance, _provenance_raw = self._read_provenance()
        if provenance is None:
            raise ValidationError("no SDDM login deployment provenance exists")
        self._validate_live_against(provenance)
        shadow_error = self._shadow_error()
        if shadow_error is not None:
            raise ValidationError(shadow_error)
        prerequisite_error = self._prerequisite_error()
        if prerequisite_error is not None:
            raise ValidationError(prerequisite_error)
        return DeploymentPlan(
            self.target_user.name,
            (
                PlanItem(
                    "system-preserve",
                    "sddm-vanilla-theme",
                    THEME_PATH,
                    "installed theme matches root-private provenance",
                ),
                PlanItem(
                    "system-preserve",
                    "vanhyprarch-wayland-session",
                    SESSION_PATH,
                    "installed session matches root-private provenance",
                ),
                PlanItem(
                    "generated-preserve",
                    "sddm-target-binding",
                    BINDING_PATH,
                    "generated binding matches canonical target user",
                ),
                PlanItem(
                    "system-preserve",
                    "sddm-vanilla-config",
                    CONFIG_PATH,
                    "installed SDDM configuration matches root-private provenance",
                ),
                PlanItem(
                    "state-preserve",
                    "sddm-login-state",
                    PROVENANCE_PATH,
                    "root-private provenance is complete",
                ),
            ),
        )

    def validate(self) -> DeploymentPlan:
        self._require_root()
        return self._validate_installed_locked()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "apply", "validate"))
    parser.add_argument("--target-user", required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--release-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if os.geteuid() != 0:
            raise IntegrationError(
                "SDDM login integration requires root privileges; rerun with sudo"
            )
        if arguments.operation in {"plan", "apply"} and arguments.source_root is None:
            raise IntegrationError(f"{arguments.operation} requires --source-root")
        integration = SddmLoginIntegration(
            source_root=arguments.source_root,
            target_username=arguments.target_user,
            release_id=arguments.release_id,
        )
        if arguments.operation == "plan":
            plan = integration.plan()
        elif arguments.operation == "apply":
            plan = integration.apply()
        else:
            plan = integration.validate()
        print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
        return 2 if plan.blockers else 0
    except IntegrationError as error:
        print(f"SDDM login integration: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
