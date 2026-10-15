#!/usr/bin/env python3
"""Prepare public TEST-ONLY fixtures or perform read-only isolated HTTPS probes.

No FTPS client, credentials, remote writes, production paths, or production keys.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release import distribution as D

BASE = "https://vanhyprarch.it/dist/v1/_acceptance/vanilla-hyprarch/"
PURPOSE = "TEST-ONLY hosting acceptance; never production trust"
PROBE = b"Vanilla HyprArch TEST-ONLY immutable hosting probe\n"
HEADERS = ("ETag", "Last-Modified", "Cache-Control", "Age", "Date", "Vary", "Content-Length", "Content-Type")


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def prepare(directory, minisign, *, now=time.time):
    """Only public files survive; signing keys exist solely in a private temp dir."""
    directory = Path(directory).absolute()
    D.require(directory.resolve() == directory, "symlinked fixture directory")
    directory.mkdir(mode=0o700)
    identifier, at = secrets.token_hex(16), int(now())
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-test-only-keys-") as temporary:
        secret, public = Path(temporary) / "TEST-ONLY.key", Path(temporary) / "TEST-ONLY.pub"
        result = subprocess.run([str(minisign.executable), "-G", "-W", "-s", str(secret), "-p", str(public)],
                                capture_output=True, check=False)
        D.require(result.returncode == 0, "disposable TEST-ONLY key generation failed")
        secret.chmod(0o600)
        key = public.read_text().splitlines()[1]
        root = D.make_root(key, issued_at=utc(at))
        envelope = D.envelope(root, [(key, minisign.sign(root, secret, key))])
        pointers = []
        for sequence in (1, 2):
            payload = D.make_catalog("candidate", sequence, [], root_version=1,
                issued_at=utc(at), expires_at=utc(at + D.SECONDS_PER_DAY))
            pointers.append(D.envelope(payload, [(key, minisign.sign(payload, secret, key))]))
    files = {"upload/root.json": envelope, "upload/pointer.json": pointers[0],
             "upload/immutable/probe.bin": PROBE, "switch/pointer-v2.json.part": pointers[1],
             "switch/incomplete.json.part": pointers[1][:len(pointers[1]) // 2]}
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    receipt = {"schema": 1, "purpose": PURPOSE, "test_id": identifier,
               "public_key": key, "root_sha256": D.digest(root),
               "files": {name: D.descriptor(name, data) for name, data in files.items()}}
    (directory / "fixture.json").write_bytes(D.canonical(receipt))
    return {"test_id": identifier, "proposed_url": BASE + identifier + "/",
            "key_fingerprint": D.public_key_id(key), "private_keys_removed": True,
            "catalog_expires_at": utc(at + D.SECONDS_PER_DAY), "remote_writes_authorized": False}


def fixture(directory, minisign, *, now=time.time):
    directory = Path(directory).absolute()
    D.require(directory.resolve() == directory, "symlinked fixture directory")
    receipt = D.decode(D._read(directory / "fixture.json", D.MAX_MANIFEST), D.MAX_MANIFEST)
    D.fields(receipt, {"schema", "purpose", "test_id", "public_key", "root_sha256", "files"})
    D.require(type(receipt["schema"]) is int and receipt["schema"] == 1 and receipt["purpose"] == PURPOSE
              and type(receipt["test_id"]) is str and re.fullmatch(r"[0-9a-f]{32}", receipt["test_id"]),
              "not an isolated TEST-ONLY fixture")
    names = {"upload/root.json", "upload/pointer.json", "upload/immutable/probe.bin",
             "switch/pointer-v2.json.part", "switch/incomplete.json.part"}
    D.fields(receipt["files"], names)
    data = {}
    for name in names:
        path = directory / name
        D.require(path.resolve() == path, "symlinked fixture input")
        D._descriptor(receipt["files"][name], name, D.MAX_ENVELOPE)
        data[name] = D._read(path, D.MAX_ENVELOPE)
        D._matches(receipt["files"][name], data[name])
    root = D.TrustedRoot.initial(data["upload/root.json"], pinned_public_key=receipt["public_key"],
        pinned_root_sha256=receipt["root_sha256"], minisign=minisign, clock=D.Clock(int(now())))
    state = D.initial_state(root)
    for sequence, name in ((1, "upload/pointer.json"), (2, "switch/pointer-v2.json.part")):
        catalog = D.verify_catalog(data[name], root, channel="candidate", state=state,
                                   minisign=minisign, clock=D.Clock(int(now())))
        D.require(catalog.value["sequence"] == sequence and not catalog.value["releases"],
                  "unexpected fixture catalog")
        state = catalog.proposed_state
    D.require(data["upload/immutable/probe.bin"] == PROBE, "invalid immutable probe")
    return BASE + receipt["test_id"] + "/", root, data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise D.DistributionError("hosting probe redirects are refused")


def fetch(base, path, *, headers=None, allow_304=False):
    D.require(base.startswith(BASE) and re.fullmatch(r"[0-9a-f]{32}/", base.removeprefix(BASE)) is not None,
              "network probe is restricted to the isolated acceptance prefix")
    D.require(path in {"pointer.json", "root.json", "immutable/probe.bin", "pointer.json.complete"},
              "invalid hosting probe path")
    request = urllib.request.Request(base + path, headers={"Accept-Encoding": "identity", **(headers or {})})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as error:
        with error:
            D.require(allow_304 and error.code == 304, f"hosting probe HTTP {error.code}")
            return 304, b"", {name: str(error.headers[name])[:512] for name in HEADERS if name in error.headers}
    with response:
        D.require(response.status == 200 and response.url == request.full_url, "unexpected hosting HTTP response")
        D.require(response.headers.get("Content-Encoding", "identity") == "identity", "encoded probe response")
        data = response.read(D.MAX_ENVELOPE + 1)
        D.require(0 < len(data) <= D.MAX_ENVELOPE, "hosting response size bound")
        length = response.headers.get("Content-Length")
        D.require(length is None or length.isascii() and length.isdecimal() and int(length) == len(data),
                  "truncated or incorrect hosting Content-Length")
        return 200, data, {name: str(response.headers[name])[:512] for name in HEADERS if name in response.headers}


def inspect(directory, minisign, *, staged=False, now=time.time, get=fetch):
    base, root, data = fixture(directory, minisign, now=now)
    observations = {}
    for name, expected in (("root.json", data["upload/root.json"]), ("immutable/probe.bin", PROBE)):
        _, actual, headers = get(base, name, headers={"Cache-Control": "no-cache"})
        D.require(actual == expected, "immutable remote object differs; do not overwrite")
        observations[name] = {"sha256": D.digest(actual), "headers": headers}
    _, actual, headers = get(base, "pointer.json", headers={"Cache-Control": "no-cache"})
    D.require(actual in {data["upload/pointer.json"], data["switch/pointer-v2.json.part"]}, "unknown or incomplete pointer")
    catalog = D.verify_catalog(actual, root, channel="candidate", state=D.initial_state(root),
                               minisign=minisign, clock=D.Clock(int(now())))
    conditional = {}
    if "ETag" in headers: conditional["If-None-Match"] = headers["ETag"]
    elif "Last-Modified" in headers: conditional["If-Modified-Since"] = headers["Last-Modified"]
    status = None
    if conditional:
        status, body, _ = get(base, "pointer.json", headers=conditional, allow_304=True)
        D.require(status == 304 or body == actual, "pointer changed during conditional inspection; repeat")
    observations["pointer.json"] = {"sha256": D.digest(actual), "sequence": catalog.value["sequence"],
                                     "headers": headers, "conditional_status": status}
    if staged:
        _, complete, stage_headers = get(base, "pointer.json.complete", headers={"Cache-Control": "no-cache"})
        D.require(complete == data["switch/pointer-v2.json.part"], "staged pointer is incomplete or substituted")
        observations["pointer.json.complete"] = {"sha256": D.digest(complete), "headers": stage_headers}
    return {"url": base, "observations": observations, "atomicity_guaranteed": False,
            "immutable_remote_exists": True, "duplicate_immutable_upload": "REFUSE; reuse verified bytes only"}


def watch(directory, minisign, *, samples=400, interval=0.05, cache_mode="revalidate",
          expect_sequence=2, now=time.time, get=fetch, sleep=time.sleep):
    D.require(type(samples) is int and 1 <= samples <= 10000 and 0 <= interval <= 5
              and samples * interval <= 60, "invalid bounded observation window")
    D.require(cache_mode in {"normal", "revalidate"} and expect_sequence in {1, 2}, "invalid probe policy")
    base, root, data = fixture(directory, minisign, now=now)
    state, seen, etags, last_headers = D.initial_state(root), set(), {}, {}
    for _ in range(samples):
        _, body, last_headers = get(base, "pointer.json",
            headers={"Cache-Control": "no-cache"} if cache_mode == "revalidate" else {})
        D.require(body in {data["upload/pointer.json"], data["switch/pointer-v2.json.part"]},
                  "observed missing, truncated, mixed, or unexpected pointer")
        catalog = D.verify_catalog(body, root, channel="candidate", state=state,
                                   minisign=minisign, clock=D.Clock(int(now())))
        state = catalog.proposed_state  # A stale cached response after seq 2 is a rollback.
        seen.add(catalog.value["sequence"])
        etag = last_headers.get("ETag")
        if etag:
            D.require(etag not in etags or etags[etag] == D.digest(body), "ETag reused for changed pointer bytes")
            etags[etag] = D.digest(body)
        if interval: sleep(interval)
    D.require(expect_sequence in seen, "expected pointer version was not observed; acceptance remains pending")
    return {"url": base, "samples": samples, "cache_mode": cache_mode, "sequences_seen": sorted(seen),
            "last_headers": last_headers, "observed_incomplete_responses": 0, "atomicity_guaranteed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minisign", type=Path, default=Path("/usr/bin/minisign"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "inspect", "watch"):
        command = commands.add_parser(name)
        command.add_argument("--directory", type=Path, required=True)
        if name == "inspect": command.add_argument("--staged", action="store_true")
        if name == "watch":
            command.add_argument("--samples", type=int, default=400)
            command.add_argument("--interval", type=float, default=0.05)
            command.add_argument("--cache-mode", choices=("normal", "revalidate"), default="revalidate")
            command.add_argument("--expect-sequence", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    try:
        native = D.Minisign(args.minisign)
        if args.command == "prepare": result = prepare(args.directory, native)
        elif args.command == "inspect": result = inspect(args.directory, native, staged=args.staged)
        else: result = watch(args.directory, native, samples=args.samples, interval=args.interval,
                            cache_mode=args.cache_mode, expect_sequence=args.expect_sequence)
        print(json.dumps(result, sort_keys=True))
    except (D.DistributionError, OSError, ValueError, urllib.error.URLError) as error:
        parser.exit(1, f"hosting acceptance: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
