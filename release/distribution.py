#!/usr/bin/env python3
"""Offline signed-distribution foundation. No network or installed-state access.

All authentication is delegated to Minisign. Builders and validators share the
existing release contract; no separately authored product identity is introduced.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from release import build as contract


PROJECT = "vanilla-hyprarch"
PROTOCOL = 1
SCHEMA = 1
SECONDS_PER_DAY = 86400
DEFAULT_CATALOG_LIFETIME = 365 * SECONDS_PER_DAY
MAX_CATALOG_LIFETIME = 365 * SECONDS_PER_DAY
ROOT_YEARS = 5
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_ROOT = 16 * 1024
MAX_MANIFEST = 16 * 1024
MAX_CATALOG = 256 * 1024
MAX_ENVELOPE = 384 * 1024
MAX_SIGNATURE = 4096
MAX_RELEASES = 500
MAX_BINDINGS = 10000
MAX_STATE = 8 * 1024 * 1024
MAX_COUNTER = (1 << 63) - 1
CHANNELS = {"stable", "candidate"}
HEADER = {"schema", "distribution_protocol", "project", "kind"}


class DistributionError(ValueError):
    """Untrusted metadata, authentication failure, or incompatible policy."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DistributionError(message)


def canonical(value: Any) -> bytes:
    """Protocol encoding: sorted compact ASCII JSON followed by exactly one LF."""
    try:
        return contract.metadata_bytes(value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise DistributionError("cannot encode canonical JSON") from error


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise DistributionError("non-finite JSON number")


def decode(data: bytes, limit: int) -> dict[str, Any]:
    require(type(data) is bytes and 0 < len(data) <= limit, "metadata size limit")
    try:
        value = json.loads(data.decode("ascii"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise DistributionError("invalid JSON") from error
    require(type(value) is dict and canonical(value) == data, "noncanonical JSON")
    return value


def fields(value: Any, keys: set[str]) -> None:
    require(type(value) is dict and set(value) == keys, "missing or unknown fields")


def integer(value: Any, low: int = 1, high: int = MAX_COUNTER) -> int:
    require(type(value) is int and low <= value <= high, "invalid integer")
    return value


def sha(value: Any) -> None:
    require(type(value) is str and contract.SHA64.fullmatch(value) is not None,
            "invalid SHA-256")


def header(kind: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "distribution_protocol": PROTOCOL,
            "project": PROJECT, "kind": kind}


def _header(value: dict[str, Any], kind: str, extra: set[str]) -> None:
    fields(value, HEADER | extra)
    require(type(value["schema"]) is int and value["schema"] == SCHEMA,
            "unsupported distribution schema")
    require(type(value["distribution_protocol"]) is int
            and value["distribution_protocol"] == PROTOCOL,
            "unsupported distribution protocol")
    require(value["project"] == PROJECT and value["kind"] == kind,
            "wrong project or object kind")


def _version(value: Any) -> tuple[int, int, int, int, int]:
    try:
        return contract.version_tuple(value)
    except contract.ReleaseError as error:
        raise DistributionError("invalid release version") from error


def timestamp(value: Any) -> int:
    require(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is not None,
        "invalid UTC timestamp")
    try:
        elapsed = (datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
                   .replace(tzinfo=timezone.utc) - EPOCH)
        result = elapsed.days * SECONDS_PER_DAY + elapsed.seconds
    except (ValueError, OverflowError) as error:
        raise DistributionError("invalid UTC date") from error
    integer(result, 0)
    return result


def _interval(value: dict[str, Any]) -> tuple[int, int]:
    issued, expires = timestamp(value["issued_at"]), timestamp(value["expires_at"])
    require(issued < expires, "invalid validity interval")
    return issued, expires


def root_expiration(issued_at: str) -> str:
    """Five UTC calendar years; Feb 29 maps to Feb 28 in a non-leap year."""
    issued = EPOCH + timedelta(seconds=timestamp(issued_at))
    year = issued.year + ROOT_YEARS
    require(year <= 9999, "root expiration is outside timestamp range")
    day = min(issued.day, calendar.monthrange(year, issued.month)[1])
    return issued.replace(year=year, day=day).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Clock:
    """Caller supplies time; catalog policy may be stricter than the v1 ceiling."""

    now: int
    maximum_catalog_lifetime: int = MAX_CATALOG_LIFETIME
    allowed_skew: int = 0

    def validate(self, value: dict[str, Any], *, catalog: bool = False,
                 high_water: int = 0) -> None:
        integer(self.now, 0)
        integer(self.maximum_catalog_lifetime, 1, MAX_CATALOG_LIFETIME)
        integer(self.allowed_skew, 0, 300)
        integer(high_water, 0)
        require(self.now + self.allowed_skew >= high_water, "clock rollback")
        issued, expires = _interval(value)
        effective = max(self.now, high_water)
        require(issued <= effective + self.allowed_skew, "metadata issued in future")
        require(effective < expires, "expired metadata")
        if catalog:
            require(expires - issued <= self.maximum_catalog_lifetime,
                    "catalog lifetime exceeds policy")


def public_key_id(public_key: str) -> str:
    """Fingerprint the complete native public packet, not Minisign's short ID."""
    require(type(public_key) is str and len(public_key) == 56, "invalid public key")
    try:
        packet = base64.b64decode(public_key, validate=True)
    except (ValueError, binascii.Error) as error:
        raise DistributionError("invalid public key encoding") from error
    require(len(packet) == 42 and packet[:2] == b"Ed"
            and base64.b64encode(packet).decode("ascii") == public_key,
            "unsupported public key packet")
    return digest(packet)


class Minisign:
    """A trusted executable is supplied locally, never by distribution metadata."""

    def __init__(self, executable: Path = Path("/usr/bin/minisign")) -> None:
        require(executable.is_absolute(), "Minisign path must be absolute")
        self.executable = executable

    def verify(self, data: bytes, signature: bytes, public_key: str) -> None:
        public_key_id(public_key)
        require(type(data) is bytes and len(data) <= MAX_CATALOG,
                "signed message size limit")
        require(type(signature) is bytes and 0 < len(signature) <= MAX_SIGNATURE,
                "signature size limit")
        with tempfile.TemporaryDirectory(prefix="vanhyprarch-signature-") as directory:
            message, detached = Path(directory) / "message", Path(directory) / "signature"
            message.write_bytes(data)
            detached.write_bytes(signature)
            try:
                result = subprocess.run(
                    [str(self.executable), "-V", "-H", "-q", "-P", public_key,
                     "-m", str(message), "-x", str(detached)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise DistributionError("Minisign verification unavailable") from error
            require(result.returncode == 0, "Minisign signature verification failed")

    def sign(self, data: bytes, secret_key: Path, public_key: str) -> bytes:
        """Publisher-only. Minisign opens the key and handles any password prompt."""
        public_key_id(public_key)
        # Validate protocol bytes before asking the signing tool to use a key.
        validate_object(data)
        with tempfile.TemporaryDirectory(prefix="vanhyprarch-signing-") as directory:
            message, detached = Path(directory) / "message", Path(directory) / "signature"
            message.write_bytes(data)
            try:
                result = subprocess.run(
                    [str(self.executable), "-S", "-s", str(secret_key.absolute()),
                     "-m", str(message), "-x", str(detached),
                     "-c", "Vanilla HyprArch distribution signature",
                     "-t", "Vanilla HyprArch distribution protocol 1"],
                    stdout=subprocess.DEVNULL, check=False)
            except OSError as error:
                raise DistributionError("Minisign signing unavailable") from error
            require(result.returncode == 0, "Minisign signing failed")
            require(detached.stat().st_size <= MAX_SIGNATURE, "signature size limit")
            signature = detached.read_bytes()
            self.verify(data, signature, public_key)
            return signature


def descriptor(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "length": len(data), "sha256": digest(data)}


def _descriptor(value: Any, path: str, limit: int) -> None:
    fields(value, {"path", "length", "sha256"})
    require(value["path"] == path, "invalid fixed relative path")
    integer(value["length"], 1, limit)
    sha(value["sha256"])


def _matches(value: dict[str, Any], data: bytes) -> None:
    require(type(data) is bytes and len(data) == value["length"], "length mismatch")
    require(digest(data) == value["sha256"], "SHA-256 mismatch")


def _identity(value: Any) -> dict[str, Any]:
    try:
        return contract.parse_metadata(canonical(value))
    except contract.ReleaseError as error:
        raise DistributionError("invalid release identity") from error


def _root(value: dict[str, Any]) -> None:
    _header(value, "root", {"root_version", "previous_root_sha256", "public_key",
                            "issued_at", "expires_at", "channel_floors"})
    version = integer(value["root_version"])
    if version == 1:
        require(value["previous_root_sha256"] is None, "initial root has predecessor")
    else:
        sha(value["previous_root_sha256"])
    public_key_id(value["public_key"])
    _interval(value)
    require(value["expires_at"] == root_expiration(value["issued_at"]),
            "root lifetime must be five UTC calendar years")
    fields(value["channel_floors"], CHANNELS)
    for floor in value["channel_floors"].values():
        integer(floor)


def _manifest(value: dict[str, Any]) -> None:
    _header(value, "release", {"root_version", "release", "release_json", "archive"})
    integer(value["root_version"])
    identity = _identity(value["release"])
    _descriptor(value["release_json"], "assets/release.json", contract.MAX_METADATA)
    artifact = identity["artifact"]
    _descriptor(value["archive"], "assets/" + artifact["name"], contract.MAX_ARTIFACT)
    require(value["archive"]["length"] == artifact["size"]
            and value["archive"]["sha256"] == artifact["sha256"],
            "archive differs from release identity")


def _entry(value: Any) -> None:
    fields(value, {"version", "manifest", "signature"})
    _version(value["version"])
    prefix = "releases/" + value["version"] + "/manifest.json"
    _descriptor(value["manifest"], prefix, MAX_MANIFEST)
    _descriptor(value["signature"], prefix + ".sig", MAX_SIGNATURE)


def _catalog(value: dict[str, Any]) -> None:
    _header(value, "catalog", {"root_version", "channel", "sequence",
                               "issued_at", "expires_at", "releases"})
    integer(value["root_version"])
    require(type(value["channel"]) is str and value["channel"] in CHANNELS,
            "invalid channel")
    integer(value["sequence"])
    issued, expires = _interval(value)
    require(expires - issued <= MAX_CATALOG_LIFETIME, "catalog lifetime exceeds protocol maximum")
    releases = value["releases"]
    require(type(releases) is list and len(releases) <= MAX_RELEASES,
            "catalog release count limit")
    versions = []
    for entry in releases:
        _entry(entry)
        version = _version(entry["version"])
        require(value["channel"] != "stable" or version[3] == 1,
                "candidate in stable catalog")
        versions.append(version)
    require(versions == sorted(set(versions)), "duplicate or unsorted releases")


def validate_object(data: bytes) -> dict[str, Any]:
    value = decode(data, MAX_CATALOG)
    kind = value.get("kind")
    if kind == "root":
        require(len(data) <= MAX_ROOT, "root size limit")
        _root(value)
    elif kind == "release":
        require(len(data) <= MAX_MANIFEST, "manifest size limit")
        _manifest(value)
    elif kind == "catalog":
        _catalog(value)
    else:
        raise DistributionError("unknown metadata kind")
    return value


def envelope(payload: bytes, signatures: list[tuple[str, bytes]]) -> bytes:
    """One self-contained atomic publication unit for a channel or root."""
    validate_object(payload)
    result = canonical({"schema": SCHEMA, "payload": base64.b64encode(payload).decode("ascii"),
                        "signatures": [{"key_id": public_key_id(key),
                                        "minisign": signature.decode("ascii")}
                                       for key, signature in signatures]})
    _open_envelope(result)
    return result


def _open_envelope(data: bytes) -> tuple[bytes, dict[str, bytes]]:
    value = decode(data, MAX_ENVELOPE)
    fields(value, {"schema", "payload", "signatures"})
    require(type(value["schema"]) is int and value["schema"] == SCHEMA,
            "unsupported envelope schema")
    require(type(value["payload"]) is str, "invalid envelope payload")
    try:
        payload = base64.b64decode(value["payload"], validate=True)
    except (ValueError, binascii.Error) as error:
        raise DistributionError("invalid payload encoding") from error
    require(base64.b64encode(payload).decode("ascii") == value["payload"],
            "noncanonical payload encoding")
    require(type(value["signatures"]) is list and 1 <= len(value["signatures"]) <= 2,
            "signature count limit")
    signatures = {}
    for item in value["signatures"]:
        fields(item, {"key_id", "minisign"})
        sha(item["key_id"])
        require(item["key_id"] not in signatures, "duplicate signer")
        require(type(item["minisign"]) is str and item["minisign"].isascii()
                and 0 < len(item["minisign"]) <= MAX_SIGNATURE, "signature size limit")
        signatures[item["key_id"]] = item["minisign"].encode("ascii")
    return payload, signatures


@dataclass(frozen=True)
class TrustedRoot:
    # Keep authenticated objects as immutable bytes, never mutable caller dicts.
    payload: bytes

    @property
    def value(self) -> dict[str, Any]:
        return validate_object(self.payload)

    @classmethod
    def initial(cls, data: bytes, *, pinned_public_key: str,
                pinned_root_sha256: str, minisign: Minisign, clock: Clock) -> TrustedRoot:
        sha(pinned_root_sha256)
        key_id = public_key_id(pinned_public_key)
        payload, signatures = _open_envelope(data)
        require(digest(payload) == pinned_root_sha256, "root differs from trust anchor")
        value = validate_object(payload)
        require(value["kind"] == "root" and value["root_version"] == 1,
                "only initial root loading is implemented")
        require(value["public_key"] == pinned_public_key and set(signatures) == {key_id},
                "root signing key differs from trust anchor")
        minisign.verify(payload, signatures[key_id], pinned_public_key)
        clock.validate(value)
        return cls(payload)

    def rotate(self, data: bytes, *, minisign: Minisign, clock: Clock) -> TrustedRoot:
        payload, signatures = _open_envelope(data)
        value, old = validate_object(payload), self.value
        require(value["kind"] == "root" and value["root_version"] == old["root_version"] + 1,
                "root rotation must advance exactly one version")
        require(value["previous_root_sha256"] == digest(self.payload), "root predecessor mismatch")
        old_key, new_key = old["public_key"], value["public_key"]
        require(old_key != new_key, "root rotation requires a new key")
        require(set(signatures) == {public_key_id(old_key), public_key_id(new_key)},
                "root rotation requires old and new signatures")
        for key in (old_key, new_key):
            minisign.verify(payload, signatures[public_key_id(key)], key)
        require(timestamp(value["issued_at"]) >= timestamp(old["issued_at"]), "root issuance rollback")
        require(all(value["channel_floors"][name] >= old["channel_floors"][name]
                    for name in CHANNELS), "root sequence floor rollback")
        clock.validate(old)
        clock.validate(value)
        return TrustedRoot(payload)


@dataclass(frozen=True)
class VerifiedCatalog:
    payload: bytes
    root_sha256: str
    proposed_state: bytes

    @property
    def value(self) -> dict[str, Any]:
        return validate_object(self.payload)


def verify_catalog(data: bytes, root: TrustedRoot, *, channel: str,
                   state: bytes, minisign: Minisign, clock: Clock) -> VerifiedCatalog:
    require(type(channel) is str and channel in CHANNELS, "invalid requested channel")
    trusted = root.value
    clock.validate(trusted)
    payload, signatures = _open_envelope(data)
    value = validate_object(payload)
    require(value["kind"] == "catalog" and value["channel"] == channel,
            "wrong catalog or channel")
    require(value["root_version"] == trusted["root_version"], "unknown catalog root")
    key_id = public_key_id(trusted["public_key"])
    require(set(signatures) == {key_id}, "unknown catalog signer")
    minisign.verify(payload, signatures[key_id], trusted["public_key"])
    clock.validate(value, catalog=True)
    require(value["sequence"] >= trusted["channel_floors"][channel],
            "catalog below root sequence floor")
    authenticated = VerifiedCatalog(payload, digest(root.payload), b"")
    proposed = advance_state(state, authenticated, root, clock=clock)
    return VerifiedCatalog(payload, authenticated.root_sha256, proposed)


def verify_release(manifest: bytes, signature: bytes, release_json: bytes,
                   catalog: VerifiedCatalog, version: str, root: TrustedRoot,
                   *, minisign: Minisign, clock: Clock,
                   manifest_root: TrustedRoot | None = None) -> dict[str, Any]:
    trusted, channel = root.value, catalog.value
    require(catalog.root_sha256 == digest(root.payload), "catalog trust-root mismatch")
    clock.validate(trusted)
    clock.validate(channel, catalog=True,
                   high_water=parse_state(catalog.proposed_state)["clock_high_water"])
    require(channel["root_version"] == trusted["root_version"], "unknown catalog root")
    entries = [entry for entry in channel["releases"] if entry["version"] == version]
    require(len(entries) == 1, "release absent from authenticated catalog")
    entry = entries[0]
    _matches(entry["manifest"], manifest)
    _matches(entry["signature"], signature)
    value = validate_object(manifest)
    signing_root = (manifest_root or root).value
    require(value["kind"] == "release" and value["root_version"] == signing_root["root_version"]
            and signing_root["root_version"] <= trusted["root_version"],
            "wrong manifest or root")
    # Historical roots are supplied only from the authenticated rotation chain;
    # their manifests require the exact binding in the current signed catalog.
    minisign.verify(manifest, signature, signing_root["public_key"])
    _matches(value["release_json"], release_json)
    identity = _identity(decode(release_json, contract.MAX_METADATA))
    require(identity == value["release"] and identity["version"] == version,
            "release identity mismatch")
    require(channel["channel"] != "stable" or identity["channel"] == "stable",
            "candidate selected through stable catalog")
    return identity


def verify_artifact(identity: dict[str, Any], metadata_path: Path,
                    archive_path: Path) -> None:
    """Reuses the existing bounded digest AND archive verifier; no extraction."""
    identity = _identity(identity)
    try:
        actual = contract.verify(metadata_path, archive_path)
        require(_read(metadata_path, contract.MAX_METADATA) == canonical(identity),
                "artifact metadata bytes differ from authenticated identity")
    except (OSError, contract.ReleaseError) as error:
        raise DistributionError("release artifact verification failed") from error
    require(actual == identity, "artifact identity mismatch")


def select_release(catalog: VerifiedCatalog, installed: dict[str, Any],
                   *, clock: Clock) -> str | None:
    """Select only catalog-authenticated versions; verify their manifests next."""
    value, installed = catalog.value, _identity(installed)
    clock.validate(value, catalog=True,
                   high_water=parse_state(catalog.proposed_state)["clock_high_water"])
    require(value["channel"] == installed["channel"], "installed/catalog channel mismatch")
    old = _version(installed["version"])
    eligible = [entry["version"] for entry in value["releases"]
                if _version(entry["version"]) > old
                and (installed["channel"] == "stable"
                     or _version(entry["version"])[:3] == old[:3])]
    return max(eligible, key=_version) if eligible else None


def compatible_release(installed: dict[str, Any], target: dict[str, Any]) -> None:
    installed, target = _identity(installed), _identity(target)
    old, new = _version(installed["version"]), _version(target["version"])
    require(new > old, "product downgrade or replay")
    require(installed["channel"] != "stable" or target["channel"] == "stable",
            "stable cannot upgrade to candidate")
    require(installed["channel"] != "candidate" or old[:3] == new[:3],
            "candidate must stay in its product version")
    minimum = target["minimum_installed_version"]
    require(minimum is None or old >= _version(minimum), "installed version too old")
    require(target["minimum_migration_level"] <= installed["migration_level"]
            <= target["migration_level"], "incompatible migration range")
    require(installed["architecture"] == target["architecture"], "architecture mismatch")


def initial_state(root: TrustedRoot) -> bytes:
    return canonical({**header("security-state"), "root_version": root.value["root_version"],
                      "root_sha256": digest(root.payload), "clock_high_water": 0,
                      "channels": {}, "bindings": {}})


def parse_state(data: bytes) -> dict[str, Any]:
    value = decode(data, MAX_STATE)
    _header(value, "security-state", {"root_version", "root_sha256", "clock_high_water",
                                      "channels", "bindings"})
    integer(value["root_version"])
    sha(value["root_sha256"])
    integer(value["clock_high_water"], 0)
    require(type(value["channels"]) is dict and set(value["channels"]) <= CHANNELS,
            "invalid stored channels")
    for accepted in value["channels"].values():
        fields(accepted, {"sequence", "sha256"})
        integer(accepted["sequence"])
        sha(accepted["sha256"])
    require(type(value["bindings"]) is dict and len(value["bindings"]) <= MAX_BINDINGS,
            "stored release binding count limit")
    for version, entry in value["bindings"].items():
        _entry(entry)
        require(version == entry["version"], "stored binding version mismatch")
    return value


def advance_state(state: bytes, catalog: VerifiedCatalog, root: TrustedRoot,
                  *, clock: Clock) -> bytes:
    """Pure proposal. The future privileged updater must durably commit it first.

    Never auto-initialize missing/corrupt installed state; initial_state is an
    explicit trust-install operation. No filesystem paths or live writes here.
    """
    current, value, trusted = parse_state(state), catalog.value, root.value
    require(current["root_version"] == trusted["root_version"]
            and current["root_sha256"] == digest(root.payload)
            and catalog.root_sha256 == digest(root.payload)
            and value["root_version"] == trusted["root_version"], "security-state root mismatch")
    clock.validate(trusted, high_water=current["clock_high_water"])
    clock.validate(value, catalog=True, high_water=current["clock_high_water"])
    channel, sequence = value["channel"], value["sequence"]
    require(sequence >= trusted["channel_floors"][channel], "catalog below root floor")
    previous = current["channels"].get(channel)
    if previous:
        require(sequence >= previous["sequence"], "catalog sequence rollback")
        require(sequence != previous["sequence"] or digest(catalog.payload) == previous["sha256"],
                "same-sequence catalog equivocation")
    for entry in value["releases"]:
        version = entry["version"]
        prior = current["bindings"].get(version)
        require(prior is None or prior == entry, "immutable release binding changed")
        current["bindings"][version] = entry
    current["channels"][channel] = {"sequence": sequence, "sha256": digest(catalog.payload)}
    current["clock_high_water"] = max(clock.now, current["clock_high_water"])
    result = canonical(current)
    parse_state(result)
    return result


def make_root(public_key: str, *, issued_at: str, expires_at: str | None = None,
              stable_floor: int = 1, candidate_floor: int = 1,
              root_version: int = 1, previous_root_sha256: str | None = None) -> bytes:
    result = canonical({**header("root"), "root_version": root_version,
                        "previous_root_sha256": previous_root_sha256,
                        "public_key": public_key, "issued_at": issued_at,
                        "expires_at": root_expiration(issued_at) if expires_at is None else expires_at,
                        "channel_floors": {"stable": stable_floor, "candidate": candidate_floor}})
    validate_object(result)
    return result


def make_manifest(metadata_path: Path, archive_path: Path, *, root_version: int) -> bytes:
    try:
        identity = contract.verify(metadata_path, archive_path)
        with contract._open_regular(metadata_path, contract.MAX_METADATA, "metadata") as (source, info):
            metadata = source.read(info.st_size + 1)
    except (OSError, contract.ReleaseError) as error:
        raise DistributionError("cannot build manifest from release artifacts") from error
    require(metadata == canonical(identity), "noncanonical generated release metadata")
    # The second read must still be the identity which the archive verifier saw.
    require(_identity(decode(metadata, contract.MAX_METADATA)) == identity,
            "release metadata changed during generation")
    artifact = identity["artifact"]
    result = canonical({**header("release"), "root_version": root_version, "release": identity,
                        "release_json": descriptor("assets/release.json", metadata),
                        "archive": {"path": "assets/" + artifact["name"],
                                    "length": artifact["size"], "sha256": artifact["sha256"]}})
    validate_object(result)
    return result


def catalog_entry(manifest: bytes, signature: bytes) -> dict[str, Any]:
    value = validate_object(manifest)
    require(value["kind"] == "release", "entry requires release manifest")
    version = value["release"]["version"]
    path = "releases/" + version + "/manifest.json"
    entry = {"version": version, "manifest": descriptor(path, manifest),
             "signature": descriptor(path + ".sig", signature)}
    _entry(entry)
    return entry


def make_catalog(channel: str, sequence: int, entries: list[dict[str, Any]], *,
                 root_version: int, issued_at: str, expires_at: str | None = None) -> bytes:
    if expires_at is None:
        try:
            expires_at = (EPOCH + timedelta(seconds=timestamp(issued_at)
                                            + DEFAULT_CATALOG_LIFETIME)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except OverflowError as error:
            raise DistributionError("catalog expiration is outside timestamp range") from error
    result = canonical({**header("catalog"), "root_version": root_version,
                        "channel": channel, "sequence": sequence,
                        "issued_at": issued_at, "expires_at": expires_at,
                        "releases": sorted(entries, key=lambda entry: _version(entry["version"]))})
    validate_object(result)
    return result


def _read(path: Path, maximum: int) -> bytes:
    try:
        with contract._open_regular(path, maximum, "publisher input") as (source, info):
            return source.read(info.st_size + 1)
    except contract.ReleaseError as error:
        raise DistributionError("cannot safely read publisher input") from error


def main() -> int:
    """Local construction only; output creation refuses existing destinations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minisign", type=Path, default=Path("/usr/bin/minisign"))
    commands = parser.add_subparsers(dest="command", required=True)
    root = commands.add_parser("root")
    root.add_argument("--public-key", required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--metadata", type=Path, required=True)
    manifest.add_argument("--archive", type=Path, required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--channel", choices=sorted(CHANNELS), required=True)
    catalog.add_argument("--sequence", type=int, required=True)
    catalog.add_argument("--release", type=Path, nargs=2, action="append", default=[],
                         metavar=("MANIFEST", "SIGNATURE"))
    sign = commands.add_parser("sign")
    sign.add_argument("--input", type=Path, required=True)
    sign.add_argument("--secret-key", type=Path, required=True)
    sign.add_argument("--public-key", required=True)
    sign.add_argument("--envelope", action="store_true")
    for command in (root, catalog):
        command.add_argument("--issued-at", required=True)
        command.add_argument("--expires-at",
                             help="UTC expiry; roots use five calendar years, catalogs default to 365 days")
    for command in (manifest, catalog):
        command.add_argument("--root-version", type=int, required=True)
    for command in (root, manifest, catalog, sign):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "root":
            output = make_root(args.public_key, issued_at=args.issued_at, expires_at=args.expires_at)
        elif args.command == "manifest":
            output = make_manifest(args.metadata, args.archive, root_version=args.root_version)
        elif args.command == "catalog":
            entries = [catalog_entry(_read(manifest, MAX_MANIFEST), _read(signature, MAX_SIGNATURE))
                       for manifest, signature in args.release]
            output = make_catalog(args.channel, args.sequence, entries, root_version=args.root_version,
                                  issued_at=args.issued_at, expires_at=args.expires_at)
        else:
            payload = _read(args.input, MAX_CATALOG)
            kind = validate_object(payload)["kind"]
            require(args.envelope == (kind in {"root", "catalog"}),
                    "root/catalog require --envelope; releases require detached signatures")
            signature = Minisign(args.minisign).sign(payload, args.secret_key, args.public_key)
            output = envelope(payload, [(args.public_key, signature)]) if args.envelope else signature
        with args.output.open("xb") as destination:
            destination.write(output)
    except (DistributionError, OSError) as error:
        parser.exit(1, f"signed metadata: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
