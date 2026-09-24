from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

STATE = Path("var/lib/vanhyprarch/update-bootstrap-v1.json")
MAX_BYTES = 512
HEX = frozenset("0123456789abcdef")
TARGET_SCHEMA = 2
TARGET_PROTOCOL = 1


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate updater provenance key")
        value[key] = item
    return value


def _parents(ctx, path):
    current = ctx.system_root
    for component in STATE.parts[:-1]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError as error:
            raise ValueError("updater provenance parent is missing") from error
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or info.st_mode & 0o022
        ):
            raise ValueError("unsafe updater provenance parent")


def _read(ctx):
    if ctx.source["update_protocol"] != TARGET_PROTOCOL:
        raise ValueError("unsupported source update protocol")
    if ctx.target["update_protocol"] != TARGET_PROTOCOL:
        raise ValueError("unsupported target update protocol")

    path = ctx.system_root / STATE
    _parents(ctx, path)

    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("RC1 updater provenance is missing") from error

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or not 0 < info.st_size <= MAX_BYTES
    ):
        raise ValueError("unsafe updater provenance")

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        data = os.read(fd, MAX_BYTES + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)

    if (
        (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or len(data) != opened.st_size
    ):
        raise ValueError("updater provenance changed while reading")

    try:
        value = json.loads(data, object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid updater provenance JSON") from error

    if type(value) is not dict:
        raise ValueError("invalid updater provenance")

    digest = value.get("sha256")
    if (
        type(digest) is not str
        or len(digest) != 64
        or any(character not in HEX for character in digest)
    ):
        raise ValueError("invalid updater provenance digest")

    if set(value) == {"schema", "sha256"} and type(value["schema"]) is int and value["schema"] == 1:
        return 1, digest

    if (
        set(value) == {"schema", "sha256", "update_protocol"}
        and type(value["schema"]) is int
        and value["schema"] == TARGET_SCHEMA
        and type(value["update_protocol"]) is int
        and value["update_protocol"] == TARGET_PROTOCOL
    ):
        return TARGET_SCHEMA, digest

    raise ValueError("unsupported updater provenance schema")


def plan(ctx):
    schema, _digest = _read(ctx)
    return [
        "migration 0001: preserve updater provenance schema 2"
        if schema == TARGET_SCHEMA
        else "migration 0001: upgrade updater provenance schema 1 to schema 2"
    ]


def apply(ctx):
    schema, digest = _read(ctx)
    if schema == TARGET_SCHEMA:
        return None

    path = ctx.system_root / STATE
    payload = (
        json.dumps(
            {
                "schema": TARGET_SCHEMA,
                "sha256": digest,
                "update_protocol": TARGET_PROTOCOL,
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()

    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=".update-bootstrap-migration-"
    )
    temporary = Path(temporary_name)
    try:
        os.fchown(fd, os.geteuid(), os.getegid())
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())

        # Fail closed if the source changed before publication.
        current_schema, current_digest = _read(ctx)
        if current_schema != 1 or current_digest != digest:
            raise ValueError("updater provenance changed before migration publication")

        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)

    return None


def validate(ctx):
    schema, _digest = _read(ctx)
    return schema == TARGET_SCHEMA
