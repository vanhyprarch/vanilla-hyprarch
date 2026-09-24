#!/usr/bin/env python3
"""Commit and inspect the root-owned installed Vanilla release identity."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release import build as contract  # noqa: E402


RELATIVE_DIRECTORY = Path("usr/share/vanhyprarch")
FILENAME = "release.json"


class IdentityError(ValueError):
    """Unsafe or conflicting installed release state."""


class InstalledReleaseIdentity:
    """One fresh-install commit marker; test roots are injected only in Python."""

    def __init__(self, root: Path = Path("/"), *, uid: int = 0, gid: int = 0,
                 fsync: Any = os.fsync) -> None:
        if not root.is_absolute():
            raise IdentityError("system root must be absolute")
        self.root = root
        self.uid = uid
        self.gid = gid
        self.fsync = fsync
        self.directory = root / RELATIVE_DIRECTORY
        self.path = self.directory / FILENAME

    def _directory(self, path: Path, *, absent_ok: bool = False) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            if absent_ok:
                return False
            raise IdentityError(f"required directory is absent: {path}") from None
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != self.uid or info.st_gid != self.gid:
            raise IdentityError(f"unsafe directory type or owner: {path}")
        if info.st_mode & 0o022:
            raise IdentityError(f"directory is group- or world-writable: {path}")
        return True

    def _parents(self, *, final_absent_ok: bool) -> bool:
        self._directory(self.root)
        self._directory(self.root / "usr")
        self._directory(self.root / "usr/share")
        return self._directory(self.directory, absent_ok=final_absent_ok)

    def _existing(self) -> os.stat_result | None:
        try:
            return self.path.lstat()
        except FileNotFoundError:
            return None

    def fresh_preflight(self) -> None:
        self._parents(final_absent_ok=True)
        if self._existing() is not None:
            raise IdentityError("installed release identity already exists; fresh reinstall is unsupported")

    def validate(self, *, allow_absent: bool = False) -> dict[str, Any] | None:
        parent_exists = self._parents(final_absent_ok=allow_absent)
        info = self._existing() if parent_exists else None
        if info is None:
            if allow_absent:
                return None
            raise IdentityError("installed release identity is absent")
        if not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_gid != self.gid:
            raise IdentityError("installed release identity has unsafe type or owner")
        if stat.S_IMODE(info.st_mode) != 0o644:
            raise IdentityError("installed release identity mode must be 0644")
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError as error:
            raise IdentityError(f"could not safely open installed release identity: {error}") from error
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise IdentityError("installed release identity changed during validation")
            if not 0 < opened.st_size <= contract.MAX_METADATA:
                raise IdentityError("installed release identity size is invalid")
            data = source.read(contract.MAX_METADATA + 1)
            after = os.fstat(source.fileno())
            if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise IdentityError("installed release identity changed during validation")
        return contract.parse_metadata(data)

    @staticmethod
    def _verified_source(metadata: Path, artifact: Path, source_root: Path) -> tuple[bytes, dict[str, Any]]:
        record = contract.verify(metadata, artifact)
        declaration_path = source_root / "release/release.toml"
        with contract._open_regular(declaration_path, contract.MAX_DECLARATION,
                                    "extracted release declaration") as (source, info):
            declaration = contract.parse_declaration(source.read(info.st_size + 1))
        for field in contract.DECLARATION_KEYS:
            if declaration.get(field) != record.get(field):
                raise IdentityError(f"installed source differs from verified release: {field}")
        with contract._open_regular(metadata, contract.MAX_METADATA,
                                    "release metadata") as (source, info):
            data = source.read(info.st_size + 1)
        if contract.parse_metadata(data) != record:
            raise IdentityError("release metadata changed after verification")
        return data, record

    def preflight(self, metadata: Path, artifact: Path, source_root: Path) -> dict[str, Any]:
        _data, record = self._verified_source(metadata, artifact, source_root)
        self.fresh_preflight()
        return record

    def commit(self, metadata: Path, artifact: Path, source_root: Path) -> dict[str, Any]:
        if os.geteuid() != 0 and self.uid == 0:
            raise IdentityError("release identity commit requires root")
        data, record = self._verified_source(metadata, artifact, source_root)
        self.fresh_preflight()
        if not self.directory.exists():
            self.directory.mkdir(mode=0o755)
            self.fsync_directory(self.root / "usr/share")
        self._parents(final_absent_ok=False)
        staged: Path | None = None
        published = False
        staged_info: os.stat_result | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory,
                                             prefix=".release-identity-",
                                             delete=False) as temporary:
                staged = Path(temporary.name)
                os.fchmod(temporary.fileno(), 0o644)
                temporary.write(data)
                temporary.flush()
                self.fsync(temporary.fileno())
                staged_info = os.fstat(temporary.fileno())
            self.fresh_preflight()
            os.link(staged, self.path, follow_symlinks=False)
            published = True
            self.fsync_directory(self.directory)
            installed = self.validate()
            if installed != record or self.path.read_bytes() != data:
                raise IdentityError("published release identity differs from verified metadata")
            staged.unlink()
            staged = None
            self.fsync_directory(self.directory)
            return record
        except Exception:
            if published and staged_info is not None:
                try:
                    current = self.path.lstat()
                    if (current.st_dev, current.st_ino) == (staged_info.st_dev, staged_info.st_ino):
                        self.path.unlink()
                        self.fsync_directory(self.directory)
                except OSError:
                    pass
            raise
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    def fsync_directory(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.fsync(descriptor)
        finally:
            os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "commit"):
        operation = commands.add_parser(name)
        operation.add_argument("--metadata", type=Path, required=True)
        operation.add_argument("--artifact", type=Path, required=True)
        operation.add_argument("--source-root", type=Path, required=True)
    checker = commands.add_parser("validate")
    checker.add_argument("--allow-absent", action="store_true")
    arguments = parser.parse_args(argv)
    identity = InstalledReleaseIdentity()
    try:
        if arguments.command == "validate":
            record = identity.validate(allow_absent=arguments.allow_absent)
            print("unreleased/development" if record is None else record["version"])
        else:
            if os.geteuid() != 0:
                raise IdentityError(f"{arguments.command} requires root")
            action = identity.preflight if arguments.command == "preflight" else identity.commit
            record = action(arguments.metadata, arguments.artifact, arguments.source_root)
            print(record["commit"] if arguments.command == "preflight"
                  else f"committed: {record['version']}")
    except (IdentityError, contract.ReleaseError, OSError) as error:
        print(f"release identity: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
