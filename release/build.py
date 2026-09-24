#!/usr/bin/env python3
"""Build and verify the offline Vanilla HyprArch release contract."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path
from collections.abc import Iterator
from typing import Any, BinaryIO


SCHEMA = 1
UPDATE_PROTOCOL = 1
ARCHITECTURE = "x86_64"
MAX_METADATA = 4096
MAX_DECLARATION = 4096
MAX_SUMMARY_CHARACTERS = 160
MAX_SUMMARY_BYTES = 320
MAX_ARTIFACT = 512 * 1024 * 1024
MAX_MEMBERS = 2048
MAX_MEMBER = 128 * 1024 * 1024
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_TAR_STREAM = MAX_UNCOMPRESSED + MAX_MEMBERS * 1024 + 1024
MAX_PATH_BYTES = 255
MAX_VERSION_BYTES = 64
MAX_MIGRATION_LEVEL = 1_000_000

VERSION = re.compile(
    r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-rc([1-9][0-9]*))?\Z",
    re.ASCII,
)
SHA40 = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
SHA64 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
PATH_PART = re.compile(r"[A-Za-z0-9._+-]+\Z", re.ASCII)
DECLARATION_KEYS = {
    "schema", "version", "channel", "architecture", "update_protocol",
    "minimum_installed_version", "minimum_migration_level",
    "migration_level", "summary",
}
METADATA_KEYS = DECLARATION_KEYS | {"commit", "artifact"}
ARTIFACT_KEYS = {"name", "size", "sha256"}
REQUIRED_FILES = {
    "release/release.toml", "install.sh", "install/bootstrap",
    "install/system_integration.py", "install/managed_deploy.py",
    "install/create_once.py", "packages/manifest-v1.toml",
    "deployment/ownership-v2.toml", "deployment/service-policy-v1.toml",
}
REQUIRED_EXECUTABLES = {"install/bootstrap"}


class ReleaseError(ValueError):
    """Invalid source, release metadata, or archive."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def _utf8_size(value: str, name: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeError as error:
        raise ReleaseError(f"invalid Unicode in {name}") from error


def version_tuple(value: object) -> tuple[int, int, int, int, int]:
    require(type(value) is str and _utf8_size(value, "version") <= MAX_VERSION_BYTES,
            "invalid version type or length")
    match = VERSION.fullmatch(value)
    require(match is not None, "noncanonical Vanilla version")
    major, minor, patch, rc = match.groups()
    # Cap components before conversion to avoid pathological decimal integers.
    require(all(len(part) <= 9 for part in (major, minor, patch, rc or "0")),
            "version component is too large")
    return (int(major), int(minor), int(patch), 0 if rc else 1,
            int(rc) if rc else 0)


def _bounded_integer(value: object, minimum: int, maximum: int, name: str) -> int:
    require(type(value) is int and minimum <= value <= maximum, f"invalid {name}")
    return value


def _validate_common(value: object, *, metadata: bool) -> dict[str, Any]:
    require(type(value) is dict, "release record must be an object/table")
    keys = set(value)
    allowed = METADATA_KEYS if metadata else DECLARATION_KEYS
    require(keys <= allowed, "unknown release field")
    required = allowed - {"minimum_installed_version"}
    require(required <= keys, "missing release field")
    require(value["schema"] == SCHEMA and type(value["schema"]) is int,
            "unsupported release schema")
    current = version_tuple(value["version"])
    channel = value["channel"]
    require(type(channel) is str and channel in {"stable", "candidate"},
            "unsupported release channel")
    require((channel == "candidate") == (current[3] == 0),
            "channel/version mismatch")
    require(value["architecture"] == ARCHITECTURE
            and type(value["architecture"]) is str,
            "unsupported architecture")
    require(value["update_protocol"] == UPDATE_PROTOCOL
            and type(value["update_protocol"]) is int,
            "unsupported update protocol")
    minimum = value.get("minimum_installed_version")
    if metadata:
        require("minimum_installed_version" in keys,
                "metadata must contain minimum_installed_version")
    if minimum is not None:
        require(version_tuple(minimum) <= current,
                "minimum installed version exceeds release version")
    low = _bounded_integer(value["minimum_migration_level"], 0,
                           MAX_MIGRATION_LEVEL, "minimum migration level")
    high = _bounded_integer(value["migration_level"], 0,
                            MAX_MIGRATION_LEVEL, "migration level")
    require(low <= high, "minimum migration level exceeds migration level")
    summary = value["summary"]
    require(type(summary) is str and 1 <= len(summary) <= MAX_SUMMARY_CHARACTERS,
            "invalid summary length")
    require(_utf8_size(summary, "summary") <= MAX_SUMMARY_BYTES
            and summary.strip() == summary
            and all(ch.isprintable() for ch in summary), "invalid summary")
    return dict(value)


def parse_declaration(data: bytes) -> dict[str, Any]:
    require(0 < len(data) <= MAX_DECLARATION, "release declaration size is invalid")
    try:
        value = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseError(f"invalid release TOML: {error}") from error
    result = _validate_common(value, metadata=False)
    result["minimum_installed_version"] = result.get("minimum_installed_version")
    return result


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReleaseError(f"invalid JSON constant: {value}")


def parse_metadata(data: bytes) -> dict[str, Any]:
    require(0 < len(data) <= MAX_METADATA, "release metadata size is invalid")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseError(f"invalid release JSON: {error}") from error
    result = _validate_common(value, metadata=True)
    require(type(result["commit"]) is str and SHA40.fullmatch(result["commit"]) is not None,
            "invalid full commit SHA")
    artifact = result["artifact"]
    require(type(artifact) is dict and set(artifact) == ARTIFACT_KEYS,
            "invalid artifact fields")
    require(type(artifact["name"]) is str
            and artifact["name"] == artifact_name(result["version"]),
            "invalid artifact filename")
    _bounded_integer(artifact["size"], 1, MAX_ARTIFACT, "artifact size")
    require(type(artifact["sha256"]) is str
            and SHA64.fullmatch(artifact["sha256"]) is not None,
            "invalid artifact SHA-256")
    return result


def metadata_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def artifact_name(version: str) -> str:
    version_tuple(version)
    return f"vanhyprarch-{version}.tar.gz"


def archive_root(version: str) -> str:
    version_tuple(version)
    return f"vanhyprarch-{version}"


def _safe_path(path: str) -> None:
    require(type(path) is str and 0 < _utf8_size(path, "archive path") <= MAX_PATH_BYTES,
            "invalid archive path length")
    parts = path.split("/")
    require(all(part not in {"", ".", ".."} and PATH_PART.fullmatch(part)
                for part in parts), f"unsafe archive path: {path!r}")
    require(".git" not in parts and "__pycache__" not in parts,
            "forbidden archive path")


def _git(repo: Path, *arguments: str) -> bytes:
    process = subprocess.run(["git", "-C", str(repo), *arguments],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             check=False)
    if process.returncode != 0:
        raise ReleaseError(f"Git failed for {arguments[0]}: "
                           f"{process.stderr.decode('utf-8', 'replace').strip()}")
    return process.stdout


def _tree(repo: Path, commit: str) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    raw = _git(repo, "ls-tree", "-rz", "--full-tree", commit)
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            identity, encoded_path = entry.split(b"\t", 1)
            mode, kind, oid = identity.decode("ascii").split(" ")
            path = encoded_path.decode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise ReleaseError("malformed Git tree entry") from error
        _safe_path(path)
        require(mode in {"100644", "100755"} and kind == "blob"
                and SHA40.fullmatch(oid) is not None,
                f"unsupported tracked object: {path}")
        require(Path(path).name not in {"release.json"}
                and not re.fullmatch(r"vanhyprarch-v.*\.tar\.gz", Path(path).name),
                f"tracked release output is forbidden: {path}")
        records.append((path, mode, oid))
    require(len(records) <= MAX_MEMBERS - 1, "too many tracked release files")
    names = {item[0] for item in records}
    require(len(names) == len(records), "duplicate Git tree path")
    require(REQUIRED_FILES <= names, "release tree lacks required installer files")
    return sorted(records)


def _tarinfo(name: str, mode: int, timestamp: int, *, directory: bool,
             size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = timestamp
    info.size = size
    return info


def _commit_time(repo: Path, commit: str) -> int:
    raw = _git(repo, "show", "-s", "--format=%ct", commit).strip()
    require(raw.isdigit(), "invalid Git commit timestamp")
    timestamp = int(raw)
    require(0 <= timestamp <= 2**32 - 1, "Git timestamp exceeds USTAR bounds")
    return timestamp


def _verify_tag(repo: Path, tag: str, commit: str, version: str) -> None:
    require(tag == version, "publication tag differs from release version")
    require(VERSION.fullmatch(tag) is not None, "invalid publication tag")
    ref = f"refs/tags/{tag}"
    actual = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode("ascii").strip()
    require(actual == commit, "publication tag resolves to another commit")


def build(repo: Path, commit: str, output_dir: Path, tag: str | None = None) -> tuple[Path, Path]:
    require(SHA40.fullmatch(commit) is not None, "build requires exact lowercase commit SHA")
    require(_git(repo, "cat-file", "-t", commit).strip() == b"commit",
            "build identity is not a Git commit")
    entries = _tree(repo, commit)
    declaration_oid = next(oid for path, _mode, oid in entries
                           if path == "release/release.toml")
    declaration = parse_declaration(_git(repo, "cat-file", "blob", declaration_oid))
    if tag is not None:
        _verify_tag(repo, tag, commit, declaration["version"])
    root = archive_root(declaration["version"])
    timestamp = _commit_time(repo, commit)
    directories = {root}
    total = 0
    for path, _mode, oid in entries:
        pieces = path.split("/")
        for index in range(1, len(pieces)):
            directories.add(root + "/" + "/".join(pieces[:index]))
        size = int(_git(repo, "cat-file", "-s", oid).strip())
        require(size <= MAX_MEMBER, f"tracked file exceeds member bound: {path}")
        total += size
        require(total <= MAX_UNCOMPRESSED, "tracked tree exceeds expansion bound")
        _safe_path(root + "/" + path)
    require(len(directories) + len(entries) <= MAX_MEMBERS,
            "tracked tree exceeds member bound")
    require(output_dir.is_dir() and not output_dir.is_symlink(),
            "output directory must be an existing real directory")
    archive_path = output_dir / artifact_name(declaration["version"])
    metadata_path = output_dir / "release.json"
    require(not archive_path.is_symlink() and not metadata_path.is_symlink(),
            "output targets must not be symlinks")
    temp_archive: Path | None = None
    temp_metadata: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".release-archive-",
                                         delete=False) as temporary:
            temp_archive = Path(temporary.name)
            with gzip.GzipFile(fileobj=temporary, mode="wb", filename="",
                               mtime=0, compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|",
                                  format=tarfile.USTAR_FORMAT) as archive:
                    archive.addfile(_tarinfo(root, 0o755, timestamp, directory=True))
                    for directory in sorted(directories - {root}):
                        archive.addfile(_tarinfo(directory, 0o755, timestamp,
                                                  directory=True))
                    for path, mode, oid in entries:
                        data = _git(repo, "cat-file", "blob", oid)
                        info = _tarinfo(root + "/" + path,
                                        0o755 if mode == "100755" else 0o644,
                                        timestamp, directory=False, size=len(data))
                        archive.addfile(info, io.BytesIO(data))
            temporary.flush()
            os.fsync(temporary.fileno())
        size = temp_archive.stat().st_size
        require(0 < size <= MAX_ARTIFACT, "built archive exceeds compressed-size bound")
        digest = _hash_file(temp_archive)
        metadata = {**declaration, "commit": commit,
                    "artifact": {"name": archive_path.name, "size": size,
                                 "sha256": digest}}
        encoded = metadata_bytes(metadata)
        require(len(encoded) <= MAX_METADATA, "generated metadata exceeds bound")
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".release-metadata-",
                                         delete=False) as temporary:
            temp_metadata = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        verify(temp_metadata, temp_archive, check_filename=False)
        os.chmod(temp_archive, 0o644)
        os.chmod(temp_metadata, 0o644)
        os.replace(temp_archive, archive_path)
        temp_archive = None
        os.replace(temp_metadata, metadata_path)
        temp_metadata = None
        return metadata_path, archive_path
    finally:
        for temporary in (temp_archive, temp_metadata):
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _hash_stream(source: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _hash_file(path: Path) -> str:
    with path.open("rb") as source:
        return _hash_stream(source)


@contextmanager
def _open_regular(path: Path, maximum: int, label: str) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as error:
        raise ReleaseError(f"could not safely open {label}: {error}") from error
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum,
                f"{label} must be a bounded regular file")
        yield source, before
        after = os.fstat(source.fileno())
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                 after.st_ctime_ns), f"{label} changed during verification")


class _BoundedReader:
    """Limit even tar headers/extended records before tarfile parses them."""

    def __init__(self, source: gzip.GzipFile, maximum: int) -> None:
        self.source = source
        self.remaining = maximum

    def read(self, size: int = -1) -> bytes:
        if self.remaining == 0:
            require(self.source.read(1) == b"", "archive expansion exceeds stream bound")
            return b""
        require(0 <= size <= self.remaining, "archive expansion exceeds stream bound")
        result = self.source.read(size)
        self.remaining -= len(result)
        return result


def verify(metadata_path: Path, archive_path: Path, *, check_filename: bool = True) -> dict[str, Any]:
    with _open_regular(metadata_path, MAX_METADATA, "metadata") as (source, info):
        metadata = parse_metadata(source.read(info.st_size + 1))
    artifact = metadata["artifact"]
    if check_filename:
        require(archive_path.name == artifact["name"], "artifact filename mismatch")
    root = archive_root(metadata["version"])
    try:
        with _open_regular(archive_path, MAX_ARTIFACT, "artifact") as (raw, info):
            require(info.st_size == artifact["size"], "artifact size mismatch")
            require(_hash_stream(raw) == artifact["sha256"], "artifact SHA-256 mismatch")
            raw.seek(0)
            with gzip.GzipFile(fileobj=raw) as decompressed:
                bounded = _BoundedReader(decompressed, MAX_TAR_STREAM)
                with tarfile.open(fileobj=bounded, mode="r|") as archive:
                    _verify_members(archive, root, metadata)
                while bounded.read(min(1024 * 1024, bounded.remaining)):
                    pass
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ReleaseError(f"invalid release archive: {error}") from error
    return metadata


def _verify_members(archive: tarfile.TarFile, root: str,
                    metadata: dict[str, Any]) -> None:
    names: set[str] = set()
    files: set[str] = set()
    total = 0
    declaration: dict[str, Any] | None = None
    first = True
    timestamp: int | None = None
    seen_file = False
    previous_directory = ""
    previous_file = ""
    try:
        for member in archive:
            require(len(names) < MAX_MEMBERS, "archive has too many members")
            name = member.name
            _safe_path(name)
            require(name == root or name.startswith(root + "/"),
                    "archive has unexpected top-level root")
            require(name not in names, "duplicate archive destination")
            require(member.isdir() or member.isfile(), "archive contains link or special object")
            require(member.size >= 0, "negative archive member size")
            require(not member.isdir() or member.size == 0,
                    "archive directory has payload")
            require(member.mode == (0o755 if member.isdir() else 0o644)
                    or (member.isfile() and member.mode == 0o755),
                    "unsafe or unexpected archive mode")
            require(member.uid == member.gid == 0
                    and member.uname == member.gname == ""
                    and member.linkname == "" and not member.pax_headers,
                    "unexpected archive ownership or extended metadata")
            require(type(member.mtime) is int and 0 <= member.mtime <= 2**32 - 1,
                    "invalid archive timestamp")
            if timestamp is None:
                timestamp = member.mtime
            require(member.mtime == timestamp, "inconsistent archive timestamps")
            if first:
                require(name == root and member.isdir(), "archive root must be first")
                first = False
            elif member.isdir():
                require(name != root, "duplicate archive root")
                require(not seen_file and name > previous_directory,
                        "archive directories are not in canonical order")
                require(name.rsplit("/", 1)[0] in names,
                        "archive directory lacks an earlier parent")
                previous_directory = name
            else:
                seen_file = True
                require(name > previous_file, "archive files are not in canonical order")
                require(name.rsplit("/", 1)[0] in names,
                        "archive file lacks an earlier directory")
                previous_file = name
                require(member.size <= MAX_MEMBER, "archive member exceeds size bound")
                total += member.size
                require(total <= MAX_UNCOMPRESSED,
                        "archive exceeds total uncompressed bound")
                relative = name[len(root) + 1:]
                if relative in REQUIRED_EXECUTABLES:
                    require(member.mode == 0o755, "required installer is not executable")
                files.add(relative)
                source = archive.extractfile(member)
                require(source is not None, "could not inspect archive member")
                if name == root + "/release/release.toml":
                    require(member.size <= MAX_DECLARATION,
                            "embedded declaration exceeds size bound")
                    content = source.read(MAX_DECLARATION + 1)
                    require(len(content) == member.size, "truncated archive member")
                    declaration = parse_declaration(content)
                else:
                    read = 0
                    while chunk := source.read(1024 * 1024):
                        read += len(chunk)
                    require(read == member.size, "truncated archive member")
                source.close()
            names.add(name)
        require(REQUIRED_FILES <= files, "archive lacks required installer files")
        require(declaration is not None, "archive lacks release declaration")
        for field in DECLARATION_KEYS:
            require(declaration.get(field) == metadata.get(field),
                    f"embedded release declaration differs: {field}")
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ReleaseError(f"invalid release archive: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build", help="build from an exact committed Git tree")
    builder.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    builder.add_argument("--commit", required=True, help="exact lowercase 40-hex commit")
    builder.add_argument("--output-dir", type=Path, required=True)
    builder.add_argument("--tag", help="require the named publication tag at --commit")
    checker = commands.add_parser("verify", help="verify metadata and archive offline")
    checker.add_argument("metadata", type=Path)
    checker.add_argument("artifact", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "build":
            metadata_path, archive_path = build(arguments.repo, arguments.commit,
                                                arguments.output_dir, arguments.tag)
            print(metadata_path)
            print(archive_path)
        else:
            result = verify(arguments.metadata, arguments.artifact)
            print(f"Verified {result['version']} ({result['commit']})")
    except (ReleaseError, OSError) as error:
        print(f"release contract: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
