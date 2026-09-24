#!/usr/bin/env python3
"""Strict release-owned migration registry and ordered stage runner.

Only a caller that has verified the target artifact may execute this code.
The runner does not discover releases or advance installed release identity.
"""

from __future__ import annotations

import copy
import os
import re
import stat
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_journal import JournalError, UpdateJournal, _metadata  # noqa: E402

from release import build as contract  # noqa: E402


MAX_REGISTRY_BYTES = 65536
MAX_IMPLEMENTATION_BYTES = 128 * 1024
MAX_MIGRATIONS = 2048
SLUG = re.compile(r"[a-z][a-z0-9-]{0,63}\Z", re.ASCII)
ENTRY_KEYS = {"id", "name", "path", "scope", "touches_user_state"}
USER_KEYS = {"user_state_preservation", "user_state_conflict"}


class MigrationError(ValueError):
    """Unsafe registry, migration, or resume state."""


@dataclass(frozen=True)
class MigrationContext:
    system_root: Path
    release_root: Path
    source: dict[str, Any]
    target: dict[str, Any]
    identifier: int
    scope: str


class MigrationRegistry:
    """Read a target declaration and its complete supported migration chain."""

    def __init__(self, source_root: Path, *, target: dict[str, Any] | None = None) -> None:
        if (not source_root.is_absolute() or source_root.is_symlink()
                or source_root.resolve(strict=True) != source_root):
            raise MigrationError("target release root must be an absolute real directory")
        self.root = source_root
        declaration = self._read_file("release/release.toml", contract.MAX_DECLARATION)
        try:
            self.declaration = contract.parse_declaration(declaration)
        except contract.ReleaseError as error:
            raise MigrationError(f"invalid target release declaration: {error}") from error
        if target is not None:
            checked = _metadata(target)
            for field in contract.DECLARATION_KEYS:
                if self.declaration.get(field) != checked.get(field):
                    raise MigrationError(f"target metadata differs from declaration: {field}")
        raw = self._read_file("release/migrations/registry.toml", MAX_REGISTRY_BYTES)
        try:
            registry = tomllib.loads(raw.decode("utf-8"))
        except (UnicodeError, tomllib.TOMLDecodeError) as error:
            raise MigrationError(f"invalid migration registry TOML: {error}") from error
        if type(registry) is not dict or set(registry) not in ({"schema"}, {"schema", "migration"}):
            raise MigrationError("invalid migration registry schema")
        if type(registry["schema"]) is not int or registry["schema"] != 1:
            raise MigrationError("unsupported migration registry schema")
        entries = registry.get("migration", [])
        if type(entries) is not list or len(entries) > MAX_MIGRATIONS:
            raise MigrationError("invalid migration entries")
        self.entries: dict[int, dict[str, Any]] = {}
        ordered: list[int] = []
        for entry in entries:
            self._validate_entry(entry)
            identifier = entry["id"]
            if identifier in self.entries:
                raise MigrationError(f"duplicate migration ID: {identifier:04d}")
            self._read_file(entry["path"], MAX_IMPLEMENTATION_BYTES)
            self.entries[identifier] = entry
            ordered.append(identifier)
        low = self.declaration["minimum_migration_level"]
        high = self.declaration["migration_level"]
        if ((not ordered and (low, high) != (0, 0))
                or high - low > MAX_MIGRATIONS
                or ordered != list(range(low + 1, high + 1))):
            raise MigrationError("migration registry has a gap, wrong order, or declaration mismatch")
        expected = {"registry.toml", *(Path(entry["path"]).name for entry in entries)}
        directory = self.root / "release/migrations"
        if {path.name for path in directory.iterdir()} != expected:
            raise MigrationError("migration directory contains unregistered content")

    @staticmethod
    def _text(value: object, name: str) -> str:
        if (type(value) is not str or not 1 <= len(value) <= 160
                or value != value.strip() or not all(char.isprintable() for char in value)):
            raise MigrationError(f"invalid migration {name}")
        return value

    def _validate_entry(self, entry: object) -> None:
        if type(entry) is not dict or not ENTRY_KEYS <= set(entry) or set(entry) - ENTRY_KEYS - USER_KEYS:
            raise MigrationError("invalid migration entry fields")
        identifier = entry["id"]
        if type(identifier) is not int or not 1 <= identifier <= contract.MAX_MIGRATION_LEVEL:
            raise MigrationError("invalid migration ID")
        name = entry["name"]
        if type(name) is not str or SLUG.fullmatch(name) is None:
            raise MigrationError("invalid migration name")
        if entry["path"] != f"release/migrations/{identifier:04d}-{name}.py":
            raise MigrationError("migration implementation path does not match its ID and name")
        self._text(entry["scope"], "scope")
        touches = entry["touches_user_state"]
        if type(touches) is not bool:
            raise MigrationError("invalid USER_OWNED declaration")
        if touches:
            if set(entry) != ENTRY_KEYS | USER_KEYS:
                raise MigrationError("USER_OWNED migration needs preservation and conflict policies")
            self._text(entry["user_state_preservation"], "user-state preservation")
            self._text(entry["user_state_conflict"], "user-state conflict")
        elif set(entry) != ENTRY_KEYS:
            raise MigrationError("unexpected USER_OWNED policy fields")

    def _read_file(self, relative: str, maximum: int) -> bytes:
        parts = Path(relative).parts
        if (not parts or Path(relative).is_absolute() or ".." in parts
                or any(part in {"", "."} for part in parts)):
            raise MigrationError("unsafe migration source path")
        current = self.root
        root_info = current.lstat()
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                or root_info.st_mode & 0o022):
            raise MigrationError("unsafe target release root ownership or mode")
        for part in parts:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError as error:
                raise MigrationError(f"missing migration source: {relative}") from error
            if stat.S_ISLNK(info.st_mode):
                raise MigrationError(f"migration source crosses a symlink: {relative}")
            if (info.st_uid != os.geteuid() or info.st_mode & 0o022
                    or (current != self.root.joinpath(*parts)
                        and not stat.S_ISDIR(info.st_mode))):
                raise MigrationError(f"unsafe migration source owner or parent: {relative}")
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o644:
            raise MigrationError(f"unsafe migration source file: {relative}")
        if not 0 < info.st_size <= maximum:
            raise MigrationError(f"migration source size is invalid: {relative}")
        descriptor = os.open(current, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                raise MigrationError("migration source changed during inspection")
            data = os.read(descriptor, maximum + 1)
            after = os.fstat(descriptor)
            if len(data) != opened.st_size or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise MigrationError("migration source changed during inspection")
            return data
        finally:
            os.close(descriptor)

    def range_from(self, level: int) -> list[int]:
        low, high = self.declaration["minimum_migration_level"], self.declaration["migration_level"]
        if type(level) is not int or not low <= level <= high:
            raise MigrationError("source migration level is outside target support range")
        return list(range(level + 1, high + 1))

    def _module(self, identifier: int) -> ModuleType:
        entry = self.entries.get(identifier)
        if entry is None:
            raise MigrationError(f"migration is not registered: {identifier:04d}")
        data = self._read_file(entry["path"], MAX_IMPLEMENTATION_BYTES)
        try:
            source = data.decode("utf-8")
            code = compile(source, str(self.root / entry["path"]), "exec")
        except (UnicodeError, SyntaxError) as error:
            raise MigrationError(f"invalid migration implementation {identifier:04d}: {error}") from error
        module = ModuleType(f"vanhyprarch_migration_{identifier:04d}")
        exec(code, module.__dict__)
        if any(not callable(getattr(module, name, None)) for name in ("plan", "apply", "validate")):
            raise MigrationError(f"migration {identifier:04d} lacks plan/apply/validate")
        return module


class MigrationRunner:
    def __init__(self, registry: MigrationRegistry, journal: UpdateJournal,
                 source: dict[str, Any], target: dict[str, Any]) -> None:
        self.registry, self.journal = registry, journal
        self.source, self.target = _metadata(source), _metadata(target)
        for field in contract.DECLARATION_KEYS:
            if registry.declaration.get(field) != self.target.get(field):
                raise MigrationError(f"runner target differs from release tree: {field}")
        registry.range_from(self.source["migration_level"])

    def _context(self, identifier: int) -> MigrationContext:
        return MigrationContext(self.journal.root, self.registry.root,
                                copy.deepcopy(self.source), copy.deepcopy(self.target),
                                identifier, self.registry.entries[identifier]["scope"])

    def _plan_one(self, identifier: int) -> list[str]:
        module = self.registry._module(identifier)
        result = module.plan(self._context(identifier))
        if (type(result) is not list or not result
                or any(type(item) is not str or not 1 <= len(item) <= 320
                       or not item.isprintable() for item in result)):
            raise MigrationError(f"migration {identifier:04d} returned an invalid plan")
        return result

    def plan(self) -> tuple[int, list[str]] | None:
        value = self.journal.bound(self.source, self.target)
        remaining = self.registry.range_from(self.source["migration_level"])
        index = len(value["completed_migrations"])
        if index >= len(remaining):
            return None
        identifier = remaining[index]
        return identifier, self._plan_one(identifier)

    def run(self) -> list[int]:
        if not self.journal.lock.held:
            raise MigrationError("migration execution requires the update lock")
        value = self.journal.bound(self.source, self.target)
        required = self.registry.range_from(self.source["migration_level"])
        if value["phase"] != "applying":
            if value["pending_migration"] is None and value["completed_migrations"] == required:
                self.validate_level()
                return required
            raise MigrationError("incomplete migrations cannot run outside applying")
        if value["checkpoint"] != "migrations":
            if value["pending_migration"] is None and value["completed_migrations"] == required:
                self.validate_level()
                return required
            self.journal.checkpoint(self.source, self.target, "migrations")
        for identifier in required:
            value = self.journal.bound(self.source, self.target)
            if identifier in value["completed_migrations"]:
                continue
            module = self.registry._module(identifier)
            context = self._context(identifier)
            if value["pending_migration"] is not None:
                if value["pending_migration"] != identifier:
                    raise MigrationError("pending migration differs from next required ID")
                if module.validate(context) is True:
                    self.journal.complete(self.source, self.target, identifier)
                    continue
                self._plan_one(identifier)
            else:
                self._plan_one(identifier)
                self.journal.pending(self.source, self.target, identifier)
            if module.apply(context) is not None:
                raise MigrationError(f"migration {identifier:04d} apply must return None")
            if module.validate(context) is not True:
                raise MigrationError(f"migration {identifier:04d} target validation failed")
            self.journal.complete(self.source, self.target, identifier)
        self.validate_level()
        return self.journal.bound(self.source, self.target)["completed_migrations"]

    def validate_level(self) -> None:
        value = self.journal.bound(self.source, self.target)
        required = self.registry.range_from(self.source["migration_level"])
        if value["pending_migration"] is not None or value["completed_migrations"] != required:
            raise MigrationError("target migration level is incomplete")
        if required and self.registry._module(required[-1]).validate(self._context(required[-1])) is not True:
            raise MigrationError("final migration state is invalid")
