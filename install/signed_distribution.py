"""Authenticated acquisition and crash-safe updater security state.

No cryptography is implemented here. Trust comes from packaged public pins;
Minisign and the existing release verifier authenticate all downloaded code.
"""
from __future__ import annotations

import base64
import importlib.resources
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from release import distribution as D
from install.update_bootstrap_integration import BootstrapIntegration, SECURITY_STATE

SERVERPLAN = "https://vanhyprarch.it/dist/v1/vanilla-hyprarch/"
GITHUB_METADATA = "https://raw.githubusercontent.com/vanhyprarch/vanilla-hyprarch/distribution-v1/vanilla-hyprarch/"
GITHUB_ASSETS = "https://github.com/vanhyprarch/vanilla-hyprarch/releases/download/"
SECURITY = SECURITY_STATE
MAX_ROOT_CHAIN = 16
MAX_LEDGER = 12 * 1024 * 1024


class Unavailable(RuntimeError):
    """Only transport availability failures permit trying another endpoint."""


class PublicationPending(D.DistributionError):
    """A write-ahead record requires authenticated exact-transaction recovery."""


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decoded(value, maximum: int) -> bytes:
    D.require(type(value) is str and len(value) <= maximum * 2, "invalid encoded security proof")
    try:
        data = base64.b64decode(value, validate=True)
    except ValueError as error:
        raise D.DistributionError("invalid security proof encoding") from error
    D.require(len(data) <= maximum and encode(data) == value, "noncanonical or oversized proof")
    return data


def fixed_path(path: str) -> None:
    D.require(type(path) is str, "invalid transport path")
    if path in {"channels/stable.json", "channels/candidate.json"}:
        return
    if re.fullmatch(r"roots/[1-9][0-9]{0,8}\.json", path):
        return
    parts = path.split("/")
    D.require(len(parts) in {3, 4} and parts[0] == "releases", "invalid distribution path")
    D._version(parts[1])
    D.require(parts[2:] in (["manifest.json"], ["manifest.json.sig"],
                           ["assets", "release.json"],
                           ["assets", D.contract.artifact_name(parts[1])]), "invalid release path")


def endpoint_url(endpoint: str, path: str) -> str:
    fixed_path(path)
    D.require(endpoint in {"github", "serverplan"}, "unknown distribution endpoint")
    if endpoint == "serverplan":
        return SERVERPLAN + path
    parts = path.split("/")
    if len(parts) == 4 and parts[0] == "releases" and parts[2] == "assets":
        return GITHUB_ASSETS + parts[1] + "/" + parts[3]
    return GITHUB_METADATA + path


class SecurityStore:
    """One atomic ledger, serialized by the existing release-update lock.

    The provenance marker is published AFTER an fsynced initial ledger and
    BEFORE any discovery. A false marker admits only the exact empty seed;
    a true marker never permits recreating missing state.
    """

    def __init__(self, journal, *, anchor: bytes | None = None,
                 minisign: D.Minisign | None = None, now=time.time):
        self.journal = journal
        self.root, self.uid, self.gid = journal.root, journal.uid, journal.gid
        D.require(self.root != Path("/") or anchor is None and minisign is None,
                  "test trust overrides cannot target the live system")
        data = anchor if anchor is not None else importlib.resources.files("release").joinpath("trust.json").read_bytes()
        self.anchor = D.decode(data, D.MAX_ENVELOPE)
        D.fields(self.anchor, {"schema", "public_key", "root_sha256", "root"})
        D.require(type(self.anchor["schema"]) is int and self.anchor["schema"] == 1,
                  "unsupported packaged trust schema")
        D.require(all(type(self.anchor[name]) is str for name in ("public_key", "root_sha256", "root")),
                  "publisher trust is unconfigured; release preparation is not approved")
        self.anchor_envelope = decoded(self.anchor["root"], D.MAX_ENVELOPE)
        self.minisign = minisign or D.Minisign()
        self.now = now
        self.api = BootstrapIntegration(Path("."), self.root, uid=self.uid, gid=self.gid)
        self.path = self.root / SECURITY

    def clock(self, at: int | None = None) -> D.Clock:
        return D.Clock(int(self.now()) if at is None else at)

    def _initial(self, *, historical=False) -> D.TrustedRoot:
        clock = self.clock()
        if historical:
            payload, _ = D._open_envelope(self.anchor_envelope)
            clock = self.clock(D.timestamp(D.validate_object(payload)["issued_at"]))
        return D.TrustedRoot.initial(self.anchor_envelope,
                                    pinned_public_key=self.anchor["public_key"],
                                    pinned_root_sha256=self.anchor["root_sha256"],
                                    minisign=self.minisign, clock=clock)

    def roots(self, value) -> list[D.TrustedRoot]:
        D.require(type(value["roots"]) is list and len(value["roots"]) <= MAX_ROOT_CHAIN,
                  "root chain exceeds bound")
        roots = [self._initial(historical=True)]
        for encoded in value["roots"]:
            data = decoded(encoded, D.MAX_ENVELOPE)
            payload, _ = D._open_envelope(data)
            issued = D.timestamp(D.validate_object(payload)["issued_at"])
            roots.append(roots[-1].rotate(data, minisign=self.minisign, clock=self.clock(issued)))
        return roots

    def _read(self):
        D.require(self.api._parents(self.path), "security-state parent is missing")
        try:
            info = self.path.lstat()
        except FileNotFoundError as error:
            raise D.DistributionError("initialized security state is missing; explicit recovery required") from error
        D.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                  and (info.st_uid, info.st_gid) == (self.uid, self.gid)
                  and stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size <= MAX_LEDGER,
                  "unsafe security-state file")
        def fingerprint(item):
            return (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid,
                    item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        with os.fdopen(os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            D.require(fingerprint(os.fstat(stream.fileno())) == fingerprint(info), "security state changed during open")
            data = stream.read(MAX_LEDGER + 1)
            D.require(fingerprint(os.fstat(stream.fileno())) == fingerprint(info) and len(data) == info.st_size,
                      "security state changed during read")
        value = D.decode(data, MAX_LEDGER)
        D.fields(value, {"schema", "roots", "state", "authorization"})
        D.require(type(value["schema"]) is int and value["schema"] == 1, "unsupported security ledger")
        state = D.parse_state(D.canonical(value["state"]))
        roots = self.roots(value)
        D.require(state["root_sha256"] == D.digest(roots[-1].payload)
                  and state["root_version"] == roots[-1].value["root_version"], "security-state root mismatch")
        proof = value["authorization"]
        if proof is not None:
            D.fields(proof, {"catalog", "manifest", "signature", "metadata", "authenticated_at", "updater"})
            D.integer(proof["authenticated_at"], 0, state["clock_high_water"])
            updater = proof["updater"]
            D.fields(updater, {"schema", "sha256", "update_protocol", "distribution_initialized",
                               "distribution_anchor_sha256"})
            D.require(type(updater["schema"]) is int and updater["schema"] == 3
                      and type(updater["update_protocol"]) is int and updater["update_protocol"] == 1
                      and updater["distribution_initialized"] is True
                      and updater["distribution_anchor_sha256"] == self.anchor["root_sha256"],
                      "invalid original updater authorization receipt")
            D.sha(updater["sha256"])
            for key, maximum in (("catalog", D.MAX_ENVELOPE), ("manifest", D.MAX_MANIFEST),
                                 ("signature", D.MAX_SIGNATURE), ("metadata", D.contract.MAX_METADATA)):
                decoded(proof[key], maximum)
        return value

    def _locked(self):
        D.require(self.journal.lock.held and (self.uid != 0 or os.geteuid() == 0),
                  "security-state mutation requires the privileged update lock")

    def publish(self, value, *, initial=False):
        self._locked()
        data = D.canonical(value)
        D.require(len(data) <= MAX_LEDGER, "security-state size bound")
        self.api._parents(self.path, create=True, private=True)
        if not initial:
            self._read()
            self.api._publish(self.path, data, 0o600)
        else:
            descriptor, name = tempfile.mkstemp(prefix=".distribution-", dir=self.path.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    os.fchown(stream.fileno(), self.uid, self.gid)
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(name, self.path, follow_symlinks=False)
                descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                Path(name).unlink(missing_ok=True)
        D.require(self._read() == value, "security-state publication differs from intent")

    def start(self):
        self._locked()
        record = self.api._record()
        D.require(record is not None and record["schema"] == 3
                  and record["distribution_anchor_sha256"] == self.anchor["root_sha256"],
                  "signed updater provenance or pinned trust mismatch")
        installed = self.api._installed()
        if "publication" in record:
            D.require(installed in {record["sha256"], record["publication"]["replacement_sha256"]},
                      "installed updater differs from both authorized publication hashes")
            raise PublicationPending("updater publication requires signed exact-target recovery")
        D.require(record["sha256"] == installed, "signed updater provenance or pinned trust mismatch")
        if not record["distribution_initialized"]:
            root = self._initial()
            seed = {"schema": 1, "roots": [], "state": D.parse_state(D.initial_state(root)), "authorization": None}
            if os.path.lexists(self.path):
                D.require(self._read() == seed, "unexpected state before initialization marker; explicit recovery required")
            else:
                self.publish(seed, initial=True)
            self.api._publish(self.api.state, (json.dumps(
                {**record, "distribution_initialized": True}, sort_keys=True) + "\n").encode(), 0o600)
        return self._read()

    def authorize(self, identity, *, resume=False):
        value = self._read()
        proof = value["authorization"]
        D.require(proof is not None, "retained target lacks signed authorization")
        roots = self.roots(value)
        high_water = value["state"]["clock_high_water"]
        D.require(self.clock().now >= high_water, "clock rollback")
        at = proof["authenticated_at"] if resume else self.clock().now
        catalog_data = decoded(proof["catalog"], D.MAX_ENVELOPE)
        payload, _ = D._open_envelope(catalog_data)
        catalog_value = D.validate_object(payload)
        catalog_root = catalog_value["root_version"]
        D.require(1 <= catalog_root <= len(roots), "unknown authorization root")
        root = roots[catalog_root - 1]
        catalog = D.verify_catalog(catalog_data, root, channel=catalog_value["channel"],
                                   state=D.initial_state(root), minisign=self.minisign, clock=self.clock(at))
        manifest = decoded(proof["manifest"], D.MAX_MANIFEST)
        manifest_version = D.validate_object(manifest)["root_version"]
        D.require(1 <= manifest_version <= len(roots), "unknown manifest signing root")
        actual = D.verify_release(manifest, decoded(proof["signature"], D.MAX_SIGNATURE),
                                  decoded(proof["metadata"], D.contract.MAX_METADATA), catalog,
                                  identity["version"], root, minisign=self.minisign, clock=self.clock(at),
                                  manifest_root=roots[manifest_version - 1])
        D.require(actual == identity, "retained signed identity mismatch")
        binding = next(entry for entry in catalog.value["releases"] if entry["version"] == identity["version"])
        D.require(value["state"]["bindings"].get(identity["version"]) == binding,
                  "authorization differs from immutable security binding")
        accepted = value["state"]["channels"].get(catalog.value["channel"])
        D.require(accepted and accepted["sequence"] >= catalog.value["sequence"]
                  and (accepted["sequence"] != catalog.value["sequence"]
                       or accepted["sha256"] == D.digest(catalog.payload)), "authorization catalog is unrecognized")


class Acquisition:
    def __init__(self, store: SecurityStore, transport, *, primary="github"):
        D.require(primary in {"github", "serverplan"}, "unknown primary transport")
        self.store, self.transport, self.primary = store, transport, primary

    def fetch(self, path, limit, destination=None, *, preferred=None):
        D.require(destination is None or not os.path.lexists(destination), "download destination already exists")
        first = preferred or self.primary
        failures = []
        for endpoint in (first, "serverplan" if first == "github" else "github"):
            try:
                return self.transport.fetch(endpoint_url(endpoint, path), limit, destination), endpoint
            except Unavailable:
                failures.append(endpoint)
                if destination is not None:
                    destination.unlink(missing_ok=True)  # Only our private in-progress download.
        raise Unavailable("distribution unavailable on " + " and ".join(failures))

    def acquire(self, source, directory):
        self.store._locked()
        ledger = self.store._read()
        roots = self.store.roots(ledger)
        clock = self.store.clock()
        clock.validate(roots[-1].value, high_water=ledger["state"]["clock_high_water"])
        catalog_data, endpoint = self.fetch("channels/" + source["channel"] + ".json", D.MAX_ENVELOPE)
        payload, _ = D._open_envelope(catalog_data)
        proposed_root = D.validate_object(payload)["root_version"]
        D.require(roots[-1].value["root_version"] <= proposed_root <= MAX_ROOT_CHAIN + 1,
                  "catalog root rollback or unsupported root chain")
        while len(roots) < proposed_root:
            record, _ = self.fetch(f"roots/{len(roots) + 1}.json", D.MAX_ENVELOPE, preferred=endpoint)
            roots.append(roots[-1].rotate(record, minisign=self.store.minisign, clock=clock))
            ledger["roots"].append(encode(record))
            ledger["state"].update(root_version=roots[-1].value["root_version"],
                                   root_sha256=D.digest(roots[-1].payload))
        root = roots[-1]
        catalog = D.verify_catalog(catalog_data, root, channel=source["channel"],
                                   state=D.canonical(ledger["state"]), minisign=self.store.minisign, clock=clock)
        ledger["state"] = D.parse_state(catalog.proposed_state)
        ledger["authorization"] = None
        self.store.publish(ledger)  # Persist authenticated observations before any target code.
        version = D.select_release(catalog, source, clock=clock)
        if version is None:
            return None
        entry = next(entry for entry in catalog.value["releases"] if entry["version"] == version)
        manifest, _ = self.fetch(entry["manifest"]["path"], entry["manifest"]["length"], preferred=endpoint)
        signature, _ = self.fetch(entry["signature"]["path"], entry["signature"]["length"], preferred=endpoint)
        prefix = f"releases/{version}/assets/"
        metadata, _ = self.fetch(prefix + "release.json", D.contract.MAX_METADATA, preferred=endpoint)
        manifest_version = D.validate_object(manifest)["root_version"]
        D.require(1 <= manifest_version <= len(roots), "unknown manifest root")
        target = D.verify_release(manifest, signature, metadata, catalog, version, root,
                                  minisign=self.store.minisign, clock=clock,
                                  manifest_root=roots[manifest_version - 1])
        D.compatible_release(source, target)
        metadata_path, archive_path = directory / "release.json", directory / target["artifact"]["name"]
        metadata_path.write_bytes(metadata)
        self.fetch(prefix + archive_path.name, target["artifact"]["size"], archive_path, preferred=endpoint)
        D.verify_artifact(target, metadata_path, archive_path)
        # Recheck wall clock after downloads; record the actual authorization time.
        clock = self.store.clock()
        clock.validate(root.value, high_water=ledger["state"]["clock_high_water"])
        clock.validate(catalog.value, catalog=True, high_water=ledger["state"]["clock_high_water"])
        ledger["state"]["clock_high_water"] = clock.now
        updater = self.store.api._record()
        D.require(updater is not None and "publication" not in updater
                  and updater["sha256"] == self.store.api._installed(),
                  "updater provenance changed during acquisition")
        ledger["authorization"] = {"catalog": encode(catalog_data), "manifest": encode(manifest),
                                   "signature": encode(signature), "metadata": encode(metadata),
                                   "authenticated_at": clock.now, "updater": updater}
        self.store.publish(ledger)
        return target, metadata_path, archive_path
