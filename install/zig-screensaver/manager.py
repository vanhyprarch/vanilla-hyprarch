#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

"""Private implementation for the vanhyprarch-screensaver component API."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import NoReturn, Sequence


SCHEMA_VERSION = 1
MANAGER_VERSION = 1
COMPONENT_ID = "zig-screensaver"
MARKER_BYTES = b"vanhyprarch-zig-screensaver-v1\n"
EXPECTED_VERSION = "v0.1.1"
EXPECTED_ARCHITECTURE = "x86_64"
EXPECTED_ASSET = "vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz"
EXPECTED_ARCHIVE_SHA256 = "9bd759283aa823aba124c94d64b9696df670551a1d6418ca1a32194ea0b1a887"
EXPECTED_REPOSITORY_URL = "https://github.com/vanhyprarch/vanhyprarch-zig-player"
EXPECTED_RELEASE_URL = EXPECTED_REPOSITORY_URL + "/releases/tag/v0.1.1"
EXPECTED_DOWNLOAD_URL = EXPECTED_REPOSITORY_URL + "/releases/download/v0.1.1/" + EXPECTED_ASSET
EXPECTED_SOURCE_TAG_URL = EXPECTED_REPOSITORY_URL + "/tree/v0.1.1"
EXPECTED_SOURCE_ARCHIVE_URL = EXPECTED_REPOSITORY_URL + "/archive/refs/tags/v0.1.1.tar.gz"
EXPECTED_MEMBER_HASHES = {
    "vanhyprarch-zig-player": "e5669983b2c9af6f121096c77796116df52b85bdf014c3bb30ced18a7353e9cf",
    "LICENSE": "edaef632cbb643e4e7a221717a6c441a4c1a7c918e6e4d56debc3d8739b233f6",
    "THIRD_PARTY_NOTICES.md": "c1864fa1b0d2bcd2ae63d5e310ba8e4f89f088f6e7ccb3d7f481ec73a3878685",
    "README.md": "3bad365d85d3123875f378dbd05fe368a113f7e8520f1908f34c270a70851834",
}


class ManagerError(RuntimeError):
    pass


def fail(message: str) -> NoReturn:
    raise ManagerError(message)


def test_overrides_allowed() -> bool:
    return os.environ.get("VANHYPRARCH_ALLOW_TEST_OVERRIDES") == "1"


def absolute_xdg(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    result = Path(value) if value else fallback
    if not result.is_absolute():
        fail(f"{name} must be absolute")
    return result


def paths() -> dict[str, Path]:
    home_value = os.environ.get("HOME")
    if not home_value or not Path(home_value).is_absolute():
        fail("HOME must be set to an absolute path")
    home = Path(home_value)
    data_home = absolute_xdg("XDG_DATA_HOME", home / ".local/share")
    runtime_value = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_value or not Path(runtime_value).is_absolute():
        fail("XDG_RUNTIME_DIR must be set to an absolute path")
    runtime_home = Path(runtime_value)
    return {
        "home": home,
        "data_home": data_home,
        "runtime_home": runtime_home,
        "runtime": runtime_home / "vanhyprarch",
        "lock": runtime_home / "vanhyprarch/zig-screensaver-component.lock",
        "receipt": runtime_home / "vanhyprarch/zig-screensaver-install.receipt",
        "binary": home / ".local/bin/vanhyprarch-zig-player",
        "license_dir": data_home / "licenses/vanhyprarch-zig-player",
        "license": data_home / "licenses/vanhyprarch-zig-player/LICENSE",
        "notices": data_home / "licenses/vanhyprarch-zig-player/THIRD_PARTY_NOTICES.md",
        "doc_dir": data_home / "doc/vanhyprarch-zig-player",
        "readme": data_home / "doc/vanhyprarch-zig-player/README.md",
        "release": data_home / "doc/vanhyprarch-zig-player/vanhyprarch-zig-player.conf",
        "marker": data_home / "vanhyprarch/components/zig-screensaver",
        "managed_resources": data_home / "vanhyprarch/zig-screensaver",
        "legacy_license_dir": home / ".local/share/licenses/vanhyprarch-zig-player",
        "legacy_doc_dir": home / ".local/share/doc/vanhyprarch-zig-player",
    }


def resources() -> tuple[Path, Path]:
    override = os.environ.get("VANHYPRARCH_ZIG_SCREENSAVER_RESOURCE_DIR")
    if override:
        if not test_overrides_allowed():
            fail("resource overrides are allowed only for isolated tests")
        root = Path(override)
    else:
        candidate = paths()["managed_resources"]
        if (candidate / "vanhyprarch-zig-player.conf").is_file():
            root = candidate
        else:
            source = Path(__file__).resolve().parent.parent
            if not (source.parent / ".git").exists():
                fail("managed Zig Screensaver resources are unavailable")
            root = source
    metadata = root / "vanhyprarch-zig-player.conf"
    require_regular(metadata, "canonical release metadata")
    return root, metadata


def current_uid() -> int:
    return os.getuid()


def lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def require_regular(path: Path, label: str, *, owner: bool = True) -> os.stat_result:
    info = lstat_optional(path)
    if info is None or not stat.S_ISREG(info.st_mode):
        fail(f"{label} is not a regular file: {path}")
    if owner and info.st_uid != current_uid():
        fail(f"{label} is not owned by the current user: {path}")
    return info


def require_directory(path: Path, label: str) -> os.stat_result:
    info = lstat_optional(path)
    if info is None or not stat.S_ISDIR(info.st_mode):
        fail(f"{label} is not a directory: {path}")
    if info.st_uid != current_uid():
        fail(f"{label} is not owned by the current user: {path}")
    return info


def ensure_owned_directory(path: Path, mode: int = 0o700) -> None:
    missing: list[Path] = []
    cursor = path
    while lstat_optional(cursor) is None:
        missing.append(cursor)
        cursor = cursor.parent
    require_directory(cursor, "installation parent")
    for directory in reversed(missing):
        directory.mkdir(mode=mode)
    require_directory(path, "installation directory")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            fail("canonical release metadata is malformed")
        key, value = line.split("=", 1)
        if key in result or not key.startswith("VANHYPRARCH_ZIG_PLAYER_"):
            fail("canonical release metadata contains an invalid key")
        result[key] = value
    expected = {
        "VANHYPRARCH_ZIG_PLAYER_VERSION": EXPECTED_VERSION,
        "VANHYPRARCH_ZIG_PLAYER_ARCHITECTURE": EXPECTED_ARCHITECTURE,
        "VANHYPRARCH_ZIG_PLAYER_ASSET": EXPECTED_ASSET,
        "VANHYPRARCH_ZIG_PLAYER_SHA256": EXPECTED_ARCHIVE_SHA256,
        "VANHYPRARCH_ZIG_PLAYER_BINARY_SHA256": EXPECTED_MEMBER_HASHES["vanhyprarch-zig-player"],
        "VANHYPRARCH_ZIG_PLAYER_LICENSE_SHA256": EXPECTED_MEMBER_HASHES["LICENSE"],
        "VANHYPRARCH_ZIG_PLAYER_NOTICES_SHA256": EXPECTED_MEMBER_HASHES["THIRD_PARTY_NOTICES.md"],
        "VANHYPRARCH_ZIG_PLAYER_README_SHA256": EXPECTED_MEMBER_HASHES["README.md"],
        "VANHYPRARCH_ZIG_PLAYER_REPOSITORY_URL": EXPECTED_REPOSITORY_URL,
        "VANHYPRARCH_ZIG_PLAYER_RELEASE_URL": EXPECTED_RELEASE_URL,
        "VANHYPRARCH_ZIG_PLAYER_DOWNLOAD_URL": EXPECTED_DOWNLOAD_URL,
        "VANHYPRARCH_ZIG_PLAYER_SOURCE_TAG_URL": EXPECTED_SOURCE_TAG_URL,
        "VANHYPRARCH_ZIG_PLAYER_SOURCE_ARCHIVE_URL": EXPECTED_SOURCE_ARCHIVE_URL,
    }
    if test_overrides_allowed():
        required = set(expected)
        if set(result) != required:
            fail("test release metadata fields are incomplete")
        for key in required:
            if not result[key]:
                fail(f"test release metadata field is empty: {key}")
    elif result != expected:
        fail("canonical release metadata differs from the reviewed v0.1.1 contract")
    return result


def marker_state(path: Path) -> str:
    parent_info = lstat_optional(path.parent)
    if parent_info is not None and (not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != current_uid()):
        return "invalid"
    info = lstat_optional(path)
    if info is None:
        return "absent"
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != current_uid()
            or stat.S_IMODE(info.st_mode) != 0o644):
        return "invalid"
    try:
        return "valid" if path.read_bytes() == MARKER_BYTES else "invalid"
    except OSError:
        return "invalid"


def validate_elf_x86_64(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] != 2:
        fail("player is not a 64-bit ELF executable")
    byte_order = "<" if header[5] == 1 else ">" if header[5] == 2 else ""
    if not byte_order or struct.unpack(byte_order + "H", header[18:20])[0] != 62:
        fail("player is not an x86_64 ELF executable")


def validate_runtime_libraries() -> None:
    if test_overrides_allowed() and os.environ.get("VANHYPRARCH_TEST_MISSING_LIBRARY") == "1":
        fail("required runtime library is unavailable: injected test failure")
    for library in ("libwayland-client.so.0", "libc.so.6"):
        try:
            ctypes.CDLL(library)
        except OSError as error:
            fail(f"required runtime library is unavailable: {library}: {error}")


def member_hashes(metadata: Path) -> dict[str, str]:
    values = parse_metadata(metadata)
    return {
        "vanhyprarch-zig-player": values["VANHYPRARCH_ZIG_PLAYER_BINARY_SHA256"],
        "LICENSE": values["VANHYPRARCH_ZIG_PLAYER_LICENSE_SHA256"],
        "THIRD_PARTY_NOTICES.md": values["VANHYPRARCH_ZIG_PLAYER_NOTICES_SHA256"],
        "README.md": values["VANHYPRARCH_ZIG_PLAYER_README_SHA256"],
    }


def payload_spec(path_map: dict[str, Path], metadata: Path) -> tuple[tuple[str, Path, int, str | None], ...]:
    hashes = member_hashes(metadata)
    return (
        ("player", path_map["binary"], 0o755, hashes["vanhyprarch-zig-player"]),
        ("license", path_map["license"], 0o644, hashes["LICENSE"]),
        ("notices", path_map["notices"], 0o644, hashes["THIRD_PARTY_NOTICES.md"]),
        ("readme", path_map["readme"], 0o644, hashes["README.md"]),
        ("release metadata", path_map["release"], 0o644, None),
    )


def legacy_payload_spec(path_map: dict[str, Path]) -> dict[str, Path]:
    return {
        "LICENSE": path_map["legacy_license_dir"] / "LICENSE",
        "THIRD_PARTY_NOTICES.md": path_map["legacy_license_dir"] / "THIRD_PARTY_NOTICES.md",
        "README.md": path_map["legacy_doc_dir"] / "README.md",
        "release": path_map["legacy_doc_dir"] / "vanhyprarch-zig-player.conf",
    }


def validate_legacy_release(path: Path, metadata: Path) -> None:
    if sha256_file(path) == sha256_file(metadata):
        return
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            fail("legacy release metadata is malformed")
        key, value = line.split("=", 1)
        if key in values:
            fail("legacy release metadata contains duplicate keys")
        values[key] = value
    expected = {
        "VANHYPRARCH_ZIG_PLAYER_VERSION": EXPECTED_VERSION,
        "VANHYPRARCH_ZIG_PLAYER_ARCHITECTURE": EXPECTED_ARCHITECTURE,
        "VANHYPRARCH_ZIG_PLAYER_ASSET": EXPECTED_ASSET,
        "VANHYPRARCH_ZIG_PLAYER_SHA256": EXPECTED_ARCHIVE_SHA256,
        "VANHYPRARCH_ZIG_PLAYER_REPOSITORY_URL": EXPECTED_REPOSITORY_URL,
        "VANHYPRARCH_ZIG_PLAYER_RELEASE_URL": EXPECTED_RELEASE_URL,
        "VANHYPRARCH_ZIG_PLAYER_DOWNLOAD_URL": EXPECTED_DOWNLOAD_URL,
        "VANHYPRARCH_ZIG_PLAYER_SOURCE_TAG_URL": EXPECTED_SOURCE_TAG_URL,
        "VANHYPRARCH_ZIG_PLAYER_SOURCE_ARCHIVE_URL": EXPECTED_SOURCE_ARCHIVE_URL,
    }
    if values != expected:
        fail("legacy release metadata does not describe the reviewed v0.1.1 release")


def validate_legacy_ancillary(path_map: dict[str, Path], metadata: Path) -> dict[str, Path]:
    legacy = legacy_payload_spec(path_map)
    expected_dirs = {
        path_map["legacy_license_dir"]: {"LICENSE", "THIRD_PARTY_NOTICES.md"},
        path_map["legacy_doc_dir"]: {"README.md", "vanhyprarch-zig-player.conf"},
    }
    for directory, names in expected_dirs.items():
        require_directory(directory, "legacy Zig player data directory")
        if {entry.name for entry in directory.iterdir()} != names:
            fail("legacy Zig player directory contains ambiguous material")
    hashes = member_hashes(metadata)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
        info = require_regular(legacy[name], f"legacy {name}")
        if stat.S_IMODE(info.st_mode) != 0o644 or sha256_file(legacy[name]) != hashes[name]:
            fail(f"legacy {name} is not canonical")
    release_info = require_regular(legacy["release"], "legacy release metadata")
    if stat.S_IMODE(release_info.st_mode) != 0o644:
        fail("legacy release metadata mode is not 0644")
    validate_legacy_release(legacy["release"], metadata)
    return legacy


def payload_present(path_map: dict[str, Path], metadata: Path) -> bool:
    return any(lstat_optional(path) is not None for _, path, _, _ in payload_spec(path_map, metadata)) \
        or lstat_optional(path_map["license_dir"]) is not None \
        or lstat_optional(path_map["doc_dir"]) is not None \
        or lstat_optional(path_map["receipt"]) is not None


def validate_payload_members(path_map: dict[str, Path], metadata: Path) -> None:
    require_directory(path_map["binary"].parent, "user-local command directory")
    require_directory(path_map["license_dir"], "player license directory")
    require_directory(path_map["doc_dir"], "player documentation directory")
    for label, path, mode, expected_hash in payload_spec(path_map, metadata):
        if label == "release metadata":
            continue
        info = require_regular(path, label)
        if stat.S_IMODE(info.st_mode) != mode:
            fail(f"{label} has mode {stat.S_IMODE(info.st_mode):04o}, expected {mode:04o}")
        actual_hash = sha256_file(path)
        wanted_hash = sha256_file(metadata) if label == "release metadata" else expected_hash
        if actual_hash != wanted_hash:
            fail(f"{label} does not match the reviewed v0.1.1 payload")
    validate_elf_x86_64(path_map["binary"])
    validate_runtime_libraries()


def validate_exact_component_directories(path_map: dict[str, Path]) -> None:
    expected = {
        path_map["license_dir"]: {"LICENSE", "THIRD_PARTY_NOTICES.md"},
        path_map["doc_dir"]: {"README.md", "vanhyprarch-zig-player.conf"},
    }
    for directory, names in expected.items():
        require_directory(directory, "component-owned data directory")
        actual = {entry.name for entry in directory.iterdir()}
        if actual != names:
            fail(f"component-owned directory membership is not canonical: {directory}")


def validate_payload(path_map: dict[str, Path], metadata: Path) -> None:
    validate_payload_members(path_map, metadata)
    info = require_regular(path_map["release"], "release metadata")
    if stat.S_IMODE(info.st_mode) != 0o644:
        fail("release metadata does not have mode 0644")
    if sha256_file(path_map["release"]) != sha256_file(metadata):
        fail("release metadata does not match the reviewed v0.1.1 contract")
    validate_exact_component_directories(path_map)


def receipt_record_is_safe(path_map: dict[str, Path]) -> bool:
    receipt = path_map["receipt"]
    try:
        info = require_regular(receipt, "install receipt")
        return stat.S_IMODE(info.st_mode) == 0o600 \
            and receipt.read_bytes() == b"vanhyprarch-zig-screensaver-install-v1\n"
    except (ManagerError, OSError):
        return False


def receipt_is_valid(path_map: dict[str, Path], metadata: Path) -> bool:
    try:
        if not receipt_record_is_safe(path_map):
            return False
        for label, path, mode, expected_hash in payload_spec(path_map, metadata):
            existing = lstat_optional(path)
            if existing is None:
                continue
            if (not stat.S_ISREG(existing.st_mode) or existing.st_uid != current_uid()
                    or stat.S_IMODE(existing.st_mode) != mode):
                return False
            wanted = sha256_file(metadata) if label == "release metadata" else expected_hash
            if sha256_file(path) != wanted:
                return False
        return True
    except (ManagerError, OSError):
        return False


def write_install_receipt(path_map: dict[str, Path]) -> None:
    ensure_owned_directory(path_map["receipt"].parent)
    try:
        descriptor = os.open(path_map["receipt"], os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        fail("an install recovery receipt already exists; manual review is required")
    with os.fdopen(descriptor, "wb") as output:
        output.write(b"vanhyprarch-zig-screensaver-install-v1\n")
        output.flush()
        os.fsync(output.fileno())


def remove_install_receipt(path_map: dict[str, Path]) -> None:
    info = lstat_optional(path_map["receipt"])
    if info is None:
        return
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != current_uid()
            or stat.S_IMODE(info.st_mode) != 0o600):
        fail("install receipt is unsafe")
    path_map["receipt"].unlink()


def cleanup_is_safe(path_map: dict[str, Path], metadata: Path) -> bool:
    try:
        if marker_state(path_map["marker"]) != "valid" and not receipt_is_valid(path_map, metadata):
            return False
        if lstat_optional(path_map["receipt"]) is not None \
                and not receipt_record_is_safe(path_map):
            return False
        for _, path, _, _ in payload_spec(path_map, metadata):
            info = lstat_optional(path)
            if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_uid != current_uid()):
                return False
        for key in ("license_dir", "doc_dir"):
            info = lstat_optional(path_map[key])
            if info is not None and (not stat.S_ISDIR(info.st_mode) or info.st_uid != current_uid()):
                return False
        allowed = {
            path_map["license_dir"]: {"LICENSE", "THIRD_PARTY_NOTICES.md"},
            path_map["doc_dir"]: {"README.md", "vanhyprarch-zig-player.conf"},
        }
        for directory, names in allowed.items():
            if lstat_optional(directory) is not None:
                if {entry.name for entry in directory.iterdir()} - names:
                    return False
        marker_info = lstat_optional(path_map["marker"])
        marker_parent = lstat_optional(path_map["marker"].parent)
        if marker_parent is not None and (not stat.S_ISDIR(marker_parent.st_mode)
                or marker_parent.st_uid != current_uid()):
            return False
        if marker_info is not None and (not stat.S_ISREG(marker_info.st_mode)
                or marker_info.st_uid != current_uid()):
            return False
        return True
    except OSError:
        return False


def status_document() -> dict[str, object]:
    path_map = paths()
    _, metadata = resources()
    parse_metadata(metadata)
    marker = marker_state(path_map["marker"])
    any_payload = payload_present(path_map, metadata)
    errors: list[str] = []
    state = "not-installed"
    installed = False
    if marker == "valid":
        try:
            validate_payload(path_map, metadata)
            state = "installed"
            installed = True
        except ManagerError as error:
            state = "incomplete"
            errors.append(str(error))
    elif marker == "invalid":
        state = "error" if not cleanup_is_safe(path_map, metadata) else "incomplete"
        errors.append("component marker is invalid or unsafe")
    elif any_payload:
        state = "incomplete" if cleanup_is_safe(path_map, metadata) else "error"
        errors.append("optional payload exists without a valid component marker")
    return {
        "schema_version": SCHEMA_VERSION,
        "manager_version": MANAGER_VERSION,
        "component": COMPONENT_ID,
        "state": state,
        "installed": installed,
        "capability": "installed" if installed else ("absent" if state == "not-installed" else "incomplete"),
        "version": EXPECTED_VERSION,
        "architecture": EXPECTED_ARCHITECTURE,
        "marker": marker,
        "cleanup_safe": cleanup_is_safe(path_map, metadata),
        "errors": errors,
    }


def atomic_copy(source: Path, destination: Path, mode: int) -> None:
    ensure_owned_directory(destination.parent)
    existing = lstat_optional(destination)
    if existing is not None and (not stat.S_ISREG(existing.st_mode)
            or existing.st_uid != current_uid()):
        fail(f"unsafe existing destination: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".vanhyprarch-zig.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_stream:
            shutil.copyfileobj(input_stream, output)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_bytes(data: bytes, destination: Path, mode: int) -> None:
    ensure_owned_directory(destination.parent)
    existing = lstat_optional(destination)
    if existing is not None and (not stat.S_ISREG(existing.st_mode)
            or existing.st_uid != current_uid()):
        fail(f"unsafe existing destination: {destination}")
    with tempfile.NamedTemporaryFile(prefix=".vanhyprarch-zig.", dir=destination.parent,
            delete=False) as output:
        temporary = Path(output.name)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    try:
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def run(argv: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(argv), text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"status {result.returncode}"
        fail(f"{Path(argv[0]).name} failed: {detail}")
    return result


def controller_command() -> str:
    override = os.environ.get("VANHYPRARCH_SCREENSAVER_EXECUTABLE")
    if override:
        if not test_overrides_allowed():
            fail("controller overrides are allowed only for isolated tests")
        return override
    command = paths()["home"] / ".local/bin/vanhyprarch-screensaver"
    if not os.access(command, os.X_OK):
        fail("baseline vanhyprarch-screensaver controller is unavailable")
    return str(command)


def idle_command() -> str:
    override = os.environ.get("VANHYPRARCH_IDLE_EXECUTABLE")
    if override:
        if not test_overrides_allowed():
            fail("idle backend overrides are allowed only for isolated tests")
        return override
    command = paths()["home"] / ".local/bin/vanhyprarch-idle"
    if not os.access(command, os.X_OK):
        fail("vanhyprarch-idle is unavailable")
    return str(command)


def component_lock(path_map: dict[str, Path]):
    ensure_owned_directory(path_map["runtime"])
    os.chmod(path_map["runtime"], 0o700)
    descriptor = os.open(path_map["lock"], os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0), 0o600)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != current_uid():
        os.close(descriptor)
        fail("component lock is unsafe")
    os.fchmod(descriptor, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def download_candidate(work: Path, metadata: Path) -> dict[str, Path]:
    values = parse_metadata(metadata)
    architecture_override = os.environ.get("VANHYPRARCH_TARGET_ARCHITECTURE")
    if architecture_override and not test_overrides_allowed():
        fail("architecture overrides are allowed only for isolated tests")
    target_arch = architecture_override or os.uname().machine
    if target_arch != values["VANHYPRARCH_ZIG_PLAYER_ARCHITECTURE"]:
        fail(f"unsupported architecture: {target_arch}")
    archive = work / values["VANHYPRARCH_ZIG_PLAYER_ASSET"]
    test_archive = os.environ.get("VANHYPRARCH_TEST_ARCHIVE")
    if test_archive:
        if not test_overrides_allowed():
            fail("archive overrides are allowed only for isolated tests")
        shutil.copyfile(test_archive, archive)
    else:
        curl = "/usr/bin/curl"
        if not os.access(curl, os.X_OK):
            fail("/usr/bin/curl is required to install Zig Screensaver")
        run([curl, "--fail", "--location", "--proto", "=https", "--tlsv1.2",
            "--output", str(archive), values["VANHYPRARCH_ZIG_PLAYER_DOWNLOAD_URL"]])
    if sha256_file(archive) != values["VANHYPRARCH_ZIG_PLAYER_SHA256"]:
        fail("player archive checksum verification failed")
    root = values["VANHYPRARCH_ZIG_PLAYER_ASSET"].removesuffix(".tar.gz")
    expected = {root + "/", *(f"{root}/{name}" for name in
        ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "vanhyprarch-zig-player"))}
    extracted = work / "extracted"
    extracted.mkdir(mode=0o700)
    with tarfile.open(archive, "r:gz") as package:
        names = {member.name + ("/" if member.isdir() and not member.name.endswith("/") else "")
            for member in package.getmembers()}
        if names != expected:
            fail("player archive contains an unexpected path or is incomplete")
        result: dict[str, Path] = {}
        for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "vanhyprarch-zig-player"):
            member = package.getmember(f"{root}/{name}")
            if not member.isfile():
                fail(f"archive member is not a regular file: {name}")
            source = package.extractfile(member)
            if source is None:
                fail(f"could not extract archive member: {name}")
            destination = extracted / name
            with destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(destination, 0o755 if name == "vanhyprarch-zig-player" else 0o644)
            hash_key = {
                "vanhyprarch-zig-player": "VANHYPRARCH_ZIG_PLAYER_BINARY_SHA256",
                "LICENSE": "VANHYPRARCH_ZIG_PLAYER_LICENSE_SHA256",
                "THIRD_PARTY_NOTICES.md": "VANHYPRARCH_ZIG_PLAYER_NOTICES_SHA256",
                "README.md": "VANHYPRARCH_ZIG_PLAYER_README_SHA256",
            }[name]
            if sha256_file(destination) != values[hash_key]:
                fail(f"extracted member checksum verification failed: {name}")
            result[name] = destination
    validate_elf_x86_64(result["vanhyprarch-zig-player"])
    validate_runtime_libraries()
    return result


def snapshot_payload(path_map: dict[str, Path], metadata: Path, backup: Path) -> tuple[set[str], set[str]]:
    present: set[str] = set()
    directories: set[str] = set()
    backup.mkdir(mode=0o700)
    for key in ("license_dir", "doc_dir"):
        if lstat_optional(path_map[key]) is not None:
            require_directory(path_map[key], key)
            directories.add(key)
    for key, path, _, _ in payload_spec(path_map, metadata):
        if lstat_optional(path) is not None:
            require_regular(path, key)
            shutil.copy2(path, backup / key)
            present.add(key)
    return present, directories


def publish_candidate(candidate: dict[str, Path], metadata: Path,
        path_map: dict[str, Path]) -> None:
    mapping = (
        (candidate["vanhyprarch-zig-player"], path_map["binary"], 0o755),
        (candidate["LICENSE"], path_map["license"], 0o644),
        (candidate["THIRD_PARTY_NOTICES.md"], path_map["notices"], 0o644),
        (candidate["README.md"], path_map["readme"], 0o644),
        (metadata, path_map["release"], 0o644),
    )
    failure_after = os.environ.get("VANHYPRARCH_TEST_FAIL_AFTER_PUBLISH", "")
    if failure_after and not test_overrides_allowed():
        fail("publication overrides are allowed only for isolated tests")
    if failure_after and not failure_after.isdigit():
        fail("invalid publication failure override")
    for index, (source, destination, mode) in enumerate(mapping, start=1):
        atomic_copy(source, destination, mode)
        if failure_after and int(failure_after) == index:
            fail("injected payload publication failure")


def remove_payload(path_map: dict[str, Path], metadata: Path, *, include_marker: bool,
        removal_preflight_complete: bool = False) -> None:
    if not removal_preflight_complete and not cleanup_is_safe(path_map, metadata):
        fail("component payload contains ambiguous or unsafe material; manual review is required")
    if include_marker:
        path_map["marker"].unlink(missing_ok=True)
    for _, path, _, _ in payload_spec(path_map, metadata):
        path.unlink(missing_ok=True)
    for key in ("license_dir", "doc_dir"):
        directory = path_map[key]
        if lstat_optional(directory) is not None:
            require_directory(directory, "component data directory")
            try:
                directory.rmdir()
            except OSError:
                fail(f"component data directory contains unrecognized material: {directory}")


def restore_snapshot(path_map: dict[str, Path], metadata: Path, backup: Path,
        present: set[str], directories: set[str]) -> None:
    for key, path, mode, _ in payload_spec(path_map, metadata):
        saved = backup / key
        if key in present:
            atomic_copy(saved, path, mode)
        else:
            path.unlink(missing_ok=True)
    for key in ("license_dir", "doc_dir"):
        if key not in directories and lstat_optional(path_map[key]) is not None:
            path_map[key].rmdir()


def command_install(kind: str) -> None:
    if os.geteuid() == 0:
        fail("do not manage the user Zig Screensaver component as root")
    path_map = paths()
    _, metadata = resources()
    descriptor = component_lock(path_map)
    try:
        before = status_document()
        if kind == "install" and before["state"] != "not-installed":
            fail("Install requires a clean not-installed state")
        if kind == "reinstall" and before["state"] != "installed":
            fail("Reinstall requires a valid installed component")
        if kind == "repair" and before["state"] not in ("incomplete", "error"):
            fail("Repair requires an incomplete or error state")
        if before["state"] != "installed":
            run([idle_command(), "reconcile-screensaver", "absent"])
        with tempfile.TemporaryDirectory(prefix="vanhyprarch-zig-screensaver.") as temporary:
            work = Path(temporary)
            candidate = download_candidate(work, metadata)
            backup = work / "backup"
            present, directories = snapshot_payload(path_map, metadata, backup)
            marker_was_valid = marker_state(path_map["marker"]) == "valid"
            try:
                if marker_was_valid:
                    run([controller_command(), "stop"])
                    path_map["marker"].unlink()
                    run([idle_command(), "reconcile-screensaver", "absent"])
                run([idle_command(), "validate-screensaver-reconcile", "installed"])
                if kind == "install":
                    write_install_receipt(path_map)
                publish_candidate(candidate, metadata, path_map)
                validate_payload(path_map, metadata)
                atomic_bytes(MARKER_BYTES, path_map["marker"], 0o644)
                run([idle_command(), "reconcile-screensaver", "installed"])
                final = status_document()
                if final["state"] != "installed":
                    fail("installed payload did not reach authoritative installed state")
                remove_install_receipt(path_map)
            except Exception:
                path_map["marker"].unlink(missing_ok=True)
                restore_snapshot(path_map, metadata, backup, present, directories)
                if marker_was_valid:
                    validate_payload(path_map, metadata)
                    atomic_bytes(MARKER_BYTES, path_map["marker"], 0o644)
                    try:
                        run([idle_command(), "reconcile-screensaver", "installed"])
                    except Exception:
                        path_map["marker"].unlink(missing_ok=True)
                        run([idle_command(), "reconcile-screensaver", "absent"])
                        raise
                else:
                    run([idle_command(), "reconcile-screensaver", "absent"])
                remove_install_receipt(path_map)
                raise
        print(f"{kind.capitalize()}ed Zig Screensaver {EXPECTED_VERSION} successfully.")
    finally:
        os.close(descriptor)


def command_adopt() -> None:
    if os.geteuid() == 0:
        fail("do not adopt the user Zig Screensaver component as root")
    path_map = paths()
    _, metadata = resources()
    descriptor = component_lock(path_map)
    try:
        if marker_state(path_map["marker"]) != "absent":
            fail("Adopt requires an absent marker")
        with tempfile.TemporaryDirectory(prefix="vanhyprarch-zig-adopt.") as temporary:
            work = Path(temporary)
            candidate = download_candidate(work, metadata)
            require_regular(path_map["binary"], "existing player")
            binary_info = path_map["binary"].stat()
            if stat.S_IMODE(binary_info.st_mode) != 0o755:
                fail("existing player mode is not 0755")
            validate_elf_x86_64(path_map["binary"])
            validate_runtime_libraries()
            canonical_data_present = any(lstat_optional(path) is not None for path in (
                path_map["license_dir"], path_map["doc_dir"], path_map["license"],
                path_map["notices"], path_map["readme"], path_map["release"]))
            legacy_mode = False
            if canonical_data_present:
                validate_payload_members(path_map, metadata)
                validate_exact_component_directories(path_map)
                source_paths = {
                    "LICENSE": path_map["license"],
                    "THIRD_PARTY_NOTICES.md": path_map["notices"],
                    "README.md": path_map["readme"],
                }
            else:
                default_data = path_map["home"] / ".local/share"
                if path_map["data_home"] == default_data:
                    fail("Adopt requires an existing complete player payload")
                legacy = validate_legacy_ancillary(path_map, metadata)
                source_paths = {name: legacy[name] for name in
                    ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md")}
                legacy_mode = True
            comparisons = (
                (candidate["vanhyprarch-zig-player"], path_map["binary"]),
                (candidate["LICENSE"], source_paths["LICENSE"]),
                (candidate["THIRD_PARTY_NOTICES.md"], source_paths["THIRD_PARTY_NOTICES.md"]),
                (candidate["README.md"], source_paths["README.md"]),
            )
            if any(source.read_bytes() != target.read_bytes() for source, target in comparisons):
                fail("existing payload differs from the canonical verified archive")
            backup = work / "backup"
            present, directories = snapshot_payload(path_map, metadata, backup)
            try:
                run([idle_command(), "reconcile-screensaver", "absent"])
                run([idle_command(), "validate-screensaver-reconcile", "installed"])
                if legacy_mode:
                    atomic_copy(candidate["LICENSE"], path_map["license"], 0o644)
                    atomic_copy(candidate["THIRD_PARTY_NOTICES.md"], path_map["notices"], 0o644)
                    atomic_copy(candidate["README.md"], path_map["readme"], 0o644)
                    atomic_copy(metadata, path_map["release"], 0o644)
                else:
                    atomic_copy(metadata, path_map["release"], 0o644)
                validate_payload(path_map, metadata)
                atomic_bytes(MARKER_BYTES, path_map["marker"], 0o644)
                run([idle_command(), "reconcile-screensaver", "installed"])
                if status_document()["state"] != "installed":
                    fail("adopted payload did not reach authoritative installed state")
            except Exception:
                path_map["marker"].unlink(missing_ok=True)
                restore_snapshot(path_map, metadata, backup, present, directories)
                run([idle_command(), "reconcile-screensaver", "absent"])
                raise
        print(f"Adopted existing Zig Screensaver {EXPECTED_VERSION} without replacing it.")
    finally:
        os.close(descriptor)


def command_uninstall(plan_token: str) -> None:
    if os.geteuid() == 0:
        fail("do not uninstall the user Zig Screensaver component as root")
    path_map = paths()
    descriptor = component_lock(path_map)
    try:
        before = status_document()
        if before["state"] == "not-installed":
            print("Zig Screensaver is already not installed.")
            return
        if before["state"] != "installed":
            fail("normal uninstall requires a valid installed component; use clean-up for proven incomplete payload")
        _, metadata = resources()
        if not cleanup_is_safe(path_map, metadata):
            fail("uninstall preflight could not prove every removal target")
        current_plan = uninstall_plan_document(path_map, metadata)
        if not plan_token or plan_token != current_plan["plan_token"]:
            fail("uninstall plan is stale; refresh and confirm the current plan")
        run([controller_command(), "stop"])
        run([idle_command(), "remove-screensaver"])
        path_map["marker"].unlink()
        remove_payload(path_map, metadata, include_marker=False,
            removal_preflight_complete=True)
        remove_install_receipt(path_map)
        if status_document()["state"] != "not-installed":
            fail("uninstall did not produce a clean not-installed state")
        print("Uninstalled Zig Screensaver; the baseline controller remains available.")
    finally:
        os.close(descriptor)


def command_cleanup() -> None:
    if os.geteuid() == 0:
        fail("do not clean up the user Zig Screensaver component as root")
    path_map = paths()
    _, metadata = resources()
    descriptor = component_lock(path_map)
    try:
        before = status_document()
        if before["state"] not in ("incomplete", "error") or not before["cleanup_safe"]:
            fail("component material cannot be proven safe for automatic clean-up")
        run([controller_command(), "stop"])
        run([idle_command(), "remove-screensaver"])
        remove_payload(path_map, metadata, include_marker=True)
        remove_install_receipt(path_map)
        if status_document()["state"] != "not-installed":
            fail("clean-up did not produce a clean not-installed state")
        print("Cleaned up proven Zig Screensaver component material.")
    finally:
        os.close(descriptor)


def component_identity(path_map: dict[str, Path], metadata: Path) -> str:
    fields: list[str] = []
    for _, path, _, _ in payload_spec(path_map, metadata):
        info = require_regular(path, "uninstall payload")
        fields.append(f"{path}:{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}")
    marker_info = require_regular(path_map["marker"], "component marker")
    fields.append(f"{path_map['marker']}:{marker_info.st_dev}:{marker_info.st_ino}:"
        f"{marker_info.st_size}:{marker_info.st_mtime_ns}")
    return hashlib.sha256("\n".join(fields).encode()).hexdigest()


def uninstall_plan_document(path_map: dict[str, Path], metadata: Path) -> dict[str, object]:
    status = status_document()
    if status["state"] != "installed" or not cleanup_is_safe(path_map, metadata):
        fail("uninstall planning requires a valid, safely removable installed component")
    result = run([idle_command(), "screensaver-uninstall-plan"])
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            fail("idle backend returned an invalid uninstall plan")
        key, value = line.split("=", 1)
        values[key] = value
    if set(values) != {"stored_lock", "resulting_lock", "preference_sha256"}:
        fail("idle backend returned an incomplete uninstall plan")
    if values["stored_lock"] not in {"none", "screensaver", "display", "suspend"} \
            or values["resulting_lock"] not in {"none", "display", "suspend"}:
        fail("idle backend returned an invalid uninstall lock plan")
    preference_digest = values["preference_sha256"]
    if preference_digest != "absent" and (len(preference_digest) != 64
            or any(character not in "0123456789abcdef" for character in preference_digest)):
        fail("idle backend returned an invalid preference digest")
    binding = json.dumps({"component": COMPONENT_ID,
        "component_identity": component_identity(path_map, metadata),
        "preference_sha256": values["preference_sha256"],
        "resulting_lock": values["resulting_lock"],
        "stored_lock": values["stored_lock"]}, sort_keys=True, separators=(",", ":"))
    return {"schema_version": 1, "component": COMPONENT_ID,
        "stored_lock": values["stored_lock"], "resulting_lock": values["resulting_lock"],
        "plan_token": hashlib.sha256(binding.encode()).hexdigest()}


def command_uninstall_plan() -> None:
    path_map = paths()
    _, metadata = resources()
    print(json.dumps(uninstall_plan_document(path_map, metadata),
        sort_keys=True, separators=(",", ":")))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="vanhyprarch-screensaver")
    commands = root.add_subparsers(dest="command", required=True)
    status = commands.add_parser("component-status")
    status.add_argument("--json", action="store_true")
    commands.add_parser("component-capability")
    commands.add_parser("install")
    commands.add_parser("reinstall")
    commands.add_parser("repair")
    commands.add_parser("adopt")
    uninstall = commands.add_parser("uninstall")
    uninstall.add_argument("--plan-token", required=True)
    commands.add_parser("clean-up")
    plan = commands.add_parser("uninstall-plan")
    plan.add_argument("--json", action="store_true", required=True)
    return root


def main(argv: Sequence[str]) -> int:
    try:
        arguments = parser().parse_args(argv[1:])
        if arguments.command == "component-status":
            document = status_document()
            if arguments.json:
                print(json.dumps(document, sort_keys=True, separators=(",", ":")))
            else:
                print(document["state"])
        elif arguments.command == "component-capability":
            print(status_document()["capability"])
        elif arguments.command in ("install", "reinstall", "repair"):
            command_install(arguments.command)
        elif arguments.command == "adopt":
            command_adopt()
        elif arguments.command == "uninstall":
            command_uninstall(arguments.plan_token)
        elif arguments.command == "clean-up":
            command_cleanup()
        elif arguments.command == "uninstall-plan":
            command_uninstall_plan()
        return 0
    except (ManagerError, OSError, tarfile.TarError) as error:
        print(f"vanhyprarch-screensaver: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
