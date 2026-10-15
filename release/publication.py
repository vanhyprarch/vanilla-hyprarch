#!/usr/bin/env python3
"""Offline static publisher. No networking, key generation, or installed state."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time

from release import distribution as D

MAX_HISTORY = 10000


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Publisher:
    """A private local workspace, append-only receipts, and a public export tree.

    Receipts precede public publication. A release retry reuses its exact frozen
    signature; a catalog retry cannot reuse a sequence for different payloads.
    Losing receipts is not permission to initialize from an untrusted mirror.
    This initial publication workflow deliberately supports root 1 only.
    """

    def __init__(self, workspace, *, minisign=None, now=time.time):
        self.workspace = Path(workspace).absolute()
        D.require(self.workspace.resolve() == self.workspace, "symlinked publisher workspace")
        self.minisign, self.now = minisign or D.Minisign(), now
        self.public = self.workspace / "public/vanilla-hyprarch"
        self.receipts = self.workspace / "receipts"

    def clock(self):
        return D.Clock(int(self.now()))

    def directory(self, path):
        D.require(path.is_relative_to(self.workspace), "path outside publisher workspace")
        for item in (self.workspace, *[self.workspace.joinpath(*path.relative_to(self.workspace).parts[:i])
                                     for i in range(1, len(path.relative_to(self.workspace).parts) + 1)]):
            info = item.lstat()
            D.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                      and not info.st_mode & 0o022
                      and (item != self.workspace or stat.S_IMODE(info.st_mode) == 0o700),
                      "unsafe publisher directory")

    def file(self, path, maximum):
        self.directory(path.parent)
        info = path.lstat()
        D.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                  and info.st_nlink == 1 and 0 < info.st_size <= maximum, "unsafe publisher file")

    def read(self, path, maximum):
        self.file(path, maximum)
        return D._read(path, maximum)

    @contextmanager
    def locked(self):
        self.directory(self.workspace)
        path = self.workspace / "publisher.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            D.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                      and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
                      "unsafe publisher lock")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise D.DistributionError("another publisher holds the workspace lock") from error
            yield
        finally:
            os.close(descriptor)

    def _write(self, path, data, *, mode=0o644):
        with path.open("xb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())

    def _new_file(self, path, data, *, mode=0o600):
        self.directory(path.parent)
        descriptor, name = tempfile.mkstemp(prefix=".complete-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                os.fchmod(output.fileno(), mode)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.link(name, path, follow_symlinks=False)  # Never replace a receipt.
            sync_directory(path.parent)
        finally:
            Path(name).unlink(missing_ok=True)

    @classmethod
    def initialize(cls, workspace, root_envelope, public_key, root_sha256, *, minisign=None, now=time.time):
        publisher = cls(workspace, minisign=minisign, now=now)
        D.TrustedRoot.initial(root_envelope, pinned_public_key=public_key,
            pinned_root_sha256=root_sha256, minisign=publisher.minisign, clock=publisher.clock())
        publisher.workspace.mkdir(mode=0o700)  # Existing workspaces are never adopted.
        sync_directory(publisher.workspace.parent)
        for relative in ("public", "public/vanilla-hyprarch", "public/vanilla-hyprarch/roots",
                         "public/vanilla-hyprarch/releases", "public/vanilla-hyprarch/channels",
                         "receipts", "receipts/releases", "receipts/catalogs",
                         "receipts/catalogs/stable", "receipts/catalogs/candidate"):
            path = publisher.workspace / relative
            path.mkdir(mode=0o700 if relative.startswith("receipts") else 0o755)
            path.chmod(0o700 if relative.startswith("receipts") else 0o755)
            sync_directory(path.parent)
        anchor = D.canonical({"schema": 1, "public_key": public_key, "root_sha256": root_sha256,
                              "root": base64.b64encode(root_envelope).decode("ascii")})
        publisher._new_file(publisher.workspace / "trust.json", anchor)
        publisher._new_file(publisher.workspace / "publisher.lock", b"publisher lock\n")
        publisher._new_file(publisher.public / "roots/1.json", root_envelope, mode=0o644)
        return publisher

    def root(self):
        anchor = D.decode(self.read(self.workspace / "trust.json", D.MAX_ENVELOPE), D.MAX_ENVELOPE)
        D.fields(anchor, {"schema", "public_key", "root_sha256", "root"})
        D.require(type(anchor["schema"]) is int and anchor["schema"] == 1, "invalid publisher trust")
        try:
            envelope = base64.b64decode(anchor["root"], validate=True)
        except (ValueError, TypeError) as error:
            raise D.DistributionError("invalid publisher root encoding") from error
        D.require(base64.b64encode(envelope).decode("ascii") == anchor["root"], "noncanonical publisher root")
        root = D.TrustedRoot.initial(envelope, pinned_public_key=anchor["public_key"],
            pinned_root_sha256=anchor["root_sha256"], minisign=self.minisign, clock=self.clock())
        self.directory(self.public)
        D.require({p.name for p in self.public.iterdir()} == {"roots", "channels", "releases"},
                  "unexpected public export content")
        self.directory(self.public / "roots")
        D.require({path.name for path in (self.public / "roots").iterdir()} == {"1.json"}
                  and self.read(self.public / "roots/1.json", D.MAX_ENVELOPE) == envelope,
                  "immutable root changed or unsupported rotation")
        return root

    def _receipt(self, version, root):
        D._version(version)
        directory = self.receipts / "releases" / version
        self.directory(directory)
        D.require({p.name for p in directory.iterdir()} == {"manifest.json", "manifest.json.sig"},
                  "unexpected release receipt content")
        manifest = self.read(directory / "manifest.json", D.MAX_MANIFEST)
        signature = self.read(directory / "manifest.json.sig", D.MAX_SIGNATURE)
        value = D.validate_object(manifest)
        D.require(value["kind"] == "release" and value["root_version"] == 1
                  and value["release"]["version"] == version, "release receipt identity mismatch")
        self.minisign.verify(manifest, signature, root.value["public_key"])
        return manifest, signature

    def _verify_release(self, version, root):
        manifest, signature = self._receipt(version, root)
        value = D.validate_object(manifest)
        directory = self.public / "releases" / version
        self.directory(directory / "assets")
        D.require({p.name for p in directory.iterdir()} == {"assets", "manifest.json", "manifest.json.sig"}
                  and {p.name for p in (directory / "assets").iterdir()} == {
                      "release.json", value["release"]["artifact"]["name"]}, "incomplete or unexpected release tree")
        D.require(self.read(directory / "manifest.json", D.MAX_MANIFEST) == manifest
                  and self.read(directory / "manifest.json.sig", D.MAX_SIGNATURE) == signature,
                  "immutable release manifest or signature changed")
        metadata = directory / "assets/release.json"
        archive = directory / "assets" / value["release"]["artifact"]["name"]
        self.file(archive, D.contract.MAX_ARTIFACT)
        D._matches(value["release_json"], self.read(metadata, D.contract.MAX_METADATA))
        D.verify_artifact(value["release"], metadata, archive)
        return D.catalog_entry(manifest, signature)

    def inventory(self, root, *, missing=None):
        for path in (self.receipts / "releases", self.public / "releases"):
            self.directory(path)
        known = {p.name for p in (self.receipts / "releases").iterdir()}
        actual = {p.name for p in (self.public / "releases").iterdir()}
        D.require(actual <= known and known - actual <= ({missing} if missing else set()),
                  "unregistered or missing immutable release; restore receipts or retry the exact input")
        D.require(len(known) <= D.MAX_BINDINGS, "release receipt count bound")
        for version in known:
            D._version(version)
            self._receipt(version, root)
            if version in actual:
                self._verify_release(version, root)

    def _sign(self, data, root, secret_key):
        D.require(secret_key is not None and not Path(secret_key).resolve().is_relative_to(self.workspace),
                  "explicit signing key must remain outside the publication workspace")
        return self.minisign.sign(data, Path(secret_key), root.value["public_key"])

    def _copy(self, source, destination, expected):
        with D.contract._open_regular(source, expected, "release input") as (input_file, info):
            D.require(info.st_size == expected, "release input length changed")
            with destination.open("xb") as output:
                os.fchmod(output.fileno(), 0o644)
                remaining = expected
                while remaining:
                    chunk = input_file.read(min(1024 * 1024, remaining))
                    D.require(chunk, "release input truncated during copy")
                    output.write(chunk)
                    remaining -= len(chunk)
                D.require(not input_file.read(1), "release input grew during copy")
                output.flush()
                os.fsync(output.fileno())

    def add_release(self, metadata, archive, approved_commit, secret_key=None):
        with self.locked():
            root = self.root()
            manifest = D.make_manifest(Path(metadata), Path(archive), root_version=1)
            identity = D.validate_object(manifest)["release"]
            D.require(type(approved_commit) is str and D.contract.SHA40.fullmatch(approved_commit) is not None
                      and identity["commit"] == approved_commit, "release differs from approved exact commit")
            version = identity["version"]
            self.inventory(root, missing=version)
            receipt = self.receipts / "releases" / version
            if os.path.lexists(receipt):
                frozen, signature = self._receipt(version, root)
                D.require(frozen == manifest, "immutable version already belongs to different release bytes")
            else:
                signature = self._sign(manifest, root, secret_key)
            stage = Path(tempfile.mkdtemp(prefix=".release-", dir=self.workspace))
            try:
                (stage / "assets").mkdir(mode=0o755)
                (stage / "assets").chmod(0o755)
                self._copy(Path(metadata), stage / "assets/release.json",
                           D.validate_object(manifest)["release_json"]["length"])
                self._copy(Path(archive), stage / "assets" / identity["artifact"]["name"], identity["artifact"]["size"])
                self._write(stage / "manifest.json", manifest)
                self._write(stage / "manifest.json.sig", signature)
                D.verify_artifact(identity, stage / "assets/release.json", stage / "assets" / identity["artifact"]["name"])
                D._matches(D.validate_object(manifest)["release_json"], (stage / "assets/release.json").read_bytes())
                sync_directory(stage / "assets")
                sync_directory(stage)
                if not os.path.lexists(receipt):
                    frozen_dir = Path(tempfile.mkdtemp(prefix=".receipt-", dir=self.workspace))
                    try:
                        self._write(frozen_dir / "manifest.json", manifest)
                        self._write(frozen_dir / "manifest.json.sig", signature)
                        sync_directory(frozen_dir)
                        os.rename(frozen_dir, receipt)
                        sync_directory(receipt.parent)
                    finally:
                        if frozen_dir.exists(): shutil.rmtree(frozen_dir)
                destination = self.public / "releases" / version
                if not os.path.lexists(destination):
                    stage.chmod(0o755)
                    os.rename(stage, destination)
                    sync_directory(destination.parent)
                self._verify_release(version, root)
                return version
            finally:
                if stage.exists(): shutil.rmtree(stage)

    def history(self, root):
        records, latest = [], {}
        for channel in sorted(D.CHANNELS):
            directory = self.receipts / "catalogs" / channel
            self.directory(directory)
            paths = list(directory.iterdir())
            D.require(len(records) + len(paths) <= MAX_HISTORY, "catalog history bound")
            sequences = []
            for path in paths:
                D.require(re.fullmatch(r"[1-9][0-9]{0,18}\.json", path.name) is not None,
                          "unexpected catalog receipt")
                data = self.read(path, D.MAX_ENVELOPE)
                payload, _ = D._open_envelope(data)
                value = D.validate_object(payload)
                sequence = int(path.stem)
                D.require(value["kind"] == "catalog" and value["channel"] == channel
                          and value["sequence"] == sequence, "catalog receipt path mismatch")
                sequences.append(sequence)
                records.append((D.timestamp(value["issued_at"]), sequence, channel, data))
            sequences.sort()
            floor = root.value["channel_floors"][channel]
            D.require(not sequences or sequences == list(range(floor, floor + len(sequences))),
                      "missing or noncontiguous catalog history")
        state = D.initial_state(root)
        for issued, sequence, channel, data in sorted(records):
            catalog = D.verify_catalog(data, root, channel=channel, state=state,
                                      minisign=self.minisign, clock=D.Clock(issued))
            for entry in catalog.value["releases"]:
                D.require(self._verify_release(entry["version"], root) == entry,
                          "historical immutable binding changed")
            state = catalog.proposed_state
            latest[channel] = (data, catalog)
        self.directory(self.public / "channels")
        D.require({p.name for p in (self.public / "channels").iterdir()} <= {c + ".json" for c in D.CHANNELS},
                  "unexpected public channel files")
        for channel in D.CHANNELS:
            path = self.public / "channels" / (channel + ".json")
            if os.path.lexists(path):
                current = self.read(path, D.MAX_ENVELOPE)
                D.require(any(c == channel and data == current for _, _, c, data in records),
                          "public catalog has no exact frozen receipt")
        return state, latest

    def _replace_channel(self, channel, data):
        parent = self.public / "channels"
        descriptor, name = tempfile.mkstemp(prefix=".catalog-", suffix=".part", dir=self.workspace)
        try:
            with os.fdopen(descriptor, "wb") as output:
                os.fchmod(output.fileno(), 0o644)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, parent / (channel + ".json"))
            sync_directory(parent)
            sync_directory(self.workspace)
        finally:
            Path(name).unlink(missing_ok=True)

    def catalog(self, channel, sequence, versions, issued_at, *, expires_at=None, secret_key=None):
        D.require(channel in D.CHANNELS, "invalid channel")
        with self.locked():
            root = self.root()
            self.inventory(root)
            state, latest = self.history(root)
            entries = [self._verify_release(version, root) for version in versions]
            payload = D.make_catalog(channel, sequence, entries, root_version=1,
                                     issued_at=issued_at, expires_at=expires_at)
            previous = latest.get(channel)
            if previous and sequence == previous[1].value["sequence"]:
                D.require(payload == previous[1].payload, "same-sequence catalog equivocation")
                data = previous[0]
            else:
                expected = previous[1].value["sequence"] + 1 if previous else root.value["channel_floors"][channel]
                D.require(sequence == expected, "catalog must use the next reserved sequence")
                D.require(not previous or D.timestamp(issued_at) >= D.timestamp(previous[1].value["issued_at"]),
                          "catalog issuance rollback")
                data = D.envelope(payload, [(root.value["public_key"], self._sign(payload, root, secret_key))])
            D.verify_catalog(data, root, channel=channel, state=state, minisign=self.minisign, clock=self.clock())
            log = self.receipts / "catalogs" / channel / f"{sequence}.json"
            if not os.path.lexists(log): self._new_file(log, data)
            self._replace_channel(channel, data)
            return D.validate_object(payload)

    def resume_channel(self, channel):
        D.require(channel in D.CHANNELS, "invalid channel")
        with self.locked():
            root = self.root()
            self.inventory(root)
            state, latest = self.history(root)
            D.require(channel in latest, "no reserved catalog to resume")
            data, _ = latest[channel]
            D.verify_catalog(data, root, channel=channel, state=state, minisign=self.minisign, clock=self.clock())
            self._replace_channel(channel, data)

    def check(self):
        with self.locked():
            root = self.root()
            self.inventory(root)
            state, latest = self.history(root)
            pending = []
            for channel, (data, _) in latest.items():
                D.verify_catalog(data, root, channel=channel, state=state, minisign=self.minisign, clock=self.clock())
                path = self.public / "channels" / (channel + ".json")
                if not path.exists() or self.read(path, D.MAX_ENVELOPE) != data: pending.append(channel)
            return {"root_sha256": D.digest(root.payload), "pending_channels": sorted(pending),
                    "releases": sorted(p.name for p in (self.receipts / "releases").iterdir())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--minisign", type=Path, default=Path("/usr/bin/minisign"))
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--root-envelope", type=Path, required=True)
    init.add_argument("--public-key", required=True)
    init.add_argument("--root-sha256", required=True)
    release = commands.add_parser("release")
    release.add_argument("--metadata", type=Path, required=True)
    release.add_argument("--archive", type=Path, required=True)
    release.add_argument("--approved-commit", required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--channel", choices=sorted(D.CHANNELS), required=True)
    catalog.add_argument("--sequence", type=int, required=True)
    catalog.add_argument("--version", action="append", default=[])
    catalog.add_argument("--issued-at", required=True)
    catalog.add_argument("--expires-at")
    for command in (release, catalog): command.add_argument("--secret-key", type=Path)
    resume = commands.add_parser("resume-channel")
    resume.add_argument("--channel", choices=sorted(D.CHANNELS), required=True)
    commands.add_parser("check")
    args = parser.parse_args(argv)
    try:
        minisign = D.Minisign(args.minisign)
        publisher = Publisher(args.workspace, minisign=minisign)
        if args.command == "init":
            publisher = Publisher.initialize(args.workspace, D._read(args.root_envelope, D.MAX_ENVELOPE),
                args.public_key, args.root_sha256, minisign=minisign)
            result = publisher.check()
        elif args.command == "release":
            result = {"release": publisher.add_release(args.metadata, args.archive, args.approved_commit, args.secret_key)}
        elif args.command == "catalog":
            result = publisher.catalog(args.channel, args.sequence, args.version, args.issued_at,
                                       expires_at=args.expires_at, secret_key=args.secret_key)
        elif args.command == "resume-channel":
            publisher.resume_channel(args.channel)
            result = publisher.check()
        else: result = publisher.check()
        print(D.canonical(result).decode(), end="")
    except (D.DistributionError, D.contract.ReleaseError, OSError, ValueError) as error:
        parser.exit(1, f"static publication: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
