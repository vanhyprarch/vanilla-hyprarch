#!/usr/bin/env python3
"""Installed, fixed-repository release acquisition and verified target handoff.

This module is packaged in the root-owned vanhyprarch-update executable. It
never executes a release driver from a download or a mutable checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from release import build as contract
from install.release_identity import InstalledReleaseIdentity, IdentityError
from install.release_update import BundleStore, TargetUser, UpdateError
from install.update_journal import (UpdateJournal, JournalError,
                                    _compact_source, _compact_target)


OWNER = "vanhyprarch"
REPOSITORY = "vanilla-hyprarch"
API = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases"
RELEASES = f"https://github.com/{OWNER}/{REPOSITORY}/releases"
MAX_LISTING = 8 * 1024 * 1024
MAX_PAGES = 5
MAX_RELEASES = MAX_PAGES * 100
MAX_REDIRECTS = 3
TIMEOUT = 20
USER_AGENT = "vanhyprarch-update/1"
TRUSTED_HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com"}
ASSET_HOST = "release-assets.githubusercontent.com"


class BootstrapError(RuntimeError):
    pass


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapError(f"duplicate GitHub response key: {key}")
        result[key] = value
    return result


def _json(data: bytes) -> object:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              BootstrapError(f"invalid JSON constant: {value}")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BootstrapError(f"malformed GitHub response: {error}") from error


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, asset: bool) -> None:
        self.count = 0
        self.asset = asset

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > MAX_REDIRECTS:
            raise BootstrapError("too many download redirects")
        _trusted_url(newurl)
        previous = urllib.parse.urlsplit(request.full_url).hostname
        destination = urllib.parse.urlsplit(newurl).hostname
        if (not self.asset or destination != ASSET_HOST
                or previous not in {"github.com", ASSET_HOST}):
            raise BootstrapError("unexpected GitHub redirect target")
        checked = super().redirect_request(request, fp, code, msg, headers, newurl)
        if checked is None:
            return None
        # Carry no credentials or cookies across the GitHub/CDN boundary.
        return urllib.request.Request(newurl, headers={"User-Agent": USER_AGENT},
                                      method=checked.get_method())


def _trusted_url(value: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise BootstrapError("malformed download URL") from error
    if (parsed.scheme != "https" or parsed.hostname not in TRUSTED_HOSTS
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or parsed.fragment):
        raise BootstrapError("untrusted or non-HTTPS download URL")


class Transport:
    """Bounded HTTPS transport; injectable only through the Python test API."""

    def fetch(self, url: str, limit: int, destination: Path | None = None) -> bytes | None:
        _trusted_url(url)
        host = urllib.parse.urlsplit(url).hostname
        if host == "api.github.com":
            page = url.removeprefix(API + "?per_page=100&page=")
            if (url != API and (not url.startswith(API + "?per_page=100&page=")
                                or not 1 <= len(page) <= 2
                                or not page.isascii() or not page.isdecimal()
                                or not 1 <= int(page) <= MAX_PAGES)):
                raise BootstrapError("API request is outside the fixed repository")
            asset = False
        elif host == "github.com" and url.startswith(RELEASES + "/download/"):
            asset = True
        else:
            raise BootstrapError("request is outside the fixed release authority")
        redirects = _Redirects(asset=asset)
        # A privileged invocation must not inherit a caller-controlled proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), redirects)
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
        })
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                _trusted_url(response.url)
                if response.status != 200:
                    raise BootstrapError(f"GitHub returned HTTP {response.status}")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isascii() or not length.isdecimal()
                                           or int(length) > limit):
                    raise BootstrapError("download has an invalid or excessive Content-Length")
                written = 0
                if destination is None:
                    chunks: list[bytes] = []
                    while chunk := response.read(min(1024 * 1024, limit - written + 1)):
                        written += len(chunk)
                        if written > limit:
                            raise BootstrapError("download exceeds the size bound")
                        chunks.append(chunk)
                    if length is not None and written != int(length):
                        raise BootstrapError("download is truncated")
                    return b"".join(chunks)
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    while chunk := response.read(min(1024 * 1024, limit - written + 1)):
                        written += len(chunk)
                        if written > limit:
                            raise BootstrapError("download exceeds the size bound")
                        output.write(chunk)
                    if length is not None and written != int(length):
                        raise BootstrapError("download is truncated")
                    output.flush()
                    os.fsync(output.fileno())
                return None
        except urllib.error.HTTPError as error:
            if error.code == 403 and error.headers.get("X-RateLimit-Remaining") == "0":
                raise BootstrapError("GitHub API rate limit reached") from error
            raise BootstrapError(f"GitHub returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as error:
            raise BootstrapError(f"network unavailable: {error}") from error


@dataclass(frozen=True)
class Release:
    tag: str
    metadata_url: str
    metadata_size: int
    artifact_url: str
    artifact_size: int


def _asset_url(asset: dict[str, Any], tag: str, name: str) -> str:
    url = asset.get("browser_download_url")
    expected = f"{RELEASES}/download/{tag}/{name}"
    if url != expected or asset.get("state") != "uploaded":
        raise BootstrapError(f"untrusted release asset endpoint: {name}")
    return url


def _release(row: object) -> Release | None:
    if type(row) is not dict:
        raise BootstrapError("malformed release listing entry")
    if type(row.get("draft")) is not bool or type(row.get("prerelease")) is not bool:
        raise BootstrapError("malformed release publication flags")
    if row["draft"]:
        return None
    tag = row.get("tag_name")
    try:
        version = contract.version_tuple(tag)
    except (contract.ReleaseError, TypeError):
        return None
    if row.get("immutable") is not True:
        raise BootstrapError(f"release {tag} is not marked immutable by GitHub")
    if row.get("prerelease") is not (version[3] == 0):
        raise BootstrapError(f"release {tag} has inconsistent prerelease status")
    assets = row.get("assets")
    if type(assets) is not list or len(assets) > 64:
        raise BootstrapError(f"release {tag} has malformed assets")
    names = ("release.json", contract.artifact_name(tag))
    selected = {}
    for name in names:
        matches = [item for item in assets if type(item) is dict and item.get("name") == name]
        if len(matches) != 1:
            raise BootstrapError(f"release {tag} requires exactly one {name} asset")
        selected[name] = matches[0]
    size = selected[names[1]].get("size")
    metadata_size = selected[names[0]].get("size")
    if (type(size) is not int or not 0 < size <= contract.MAX_ARTIFACT
            or type(metadata_size) is not int or not 0 < metadata_size <= contract.MAX_METADATA):
        raise BootstrapError(f"release {tag} asset size is invalid")
    return Release(tag, _asset_url(selected[names[0]], tag, names[0]),
                   metadata_size, _asset_url(selected[names[1]], tag, names[1]), size)


def _eligible(source: dict[str, Any], tag: str) -> bool:
    old = contract.version_tuple(source["version"])
    new = contract.version_tuple(tag)
    if new <= old:
        return False
    if source["channel"] == "stable":
        return new[3] == 1
    return new[:3] == old[:3]


class Bootstrap:
    def __init__(self, user: TargetUser, *, transport: Transport | None = None,
                 root: Path = Path("/"), uid: int = 0, gid: int = 0,
                 run=subprocess.run) -> None:
        self.user = user
        self.transport = transport or Transport()
        self.identity = InstalledReleaseIdentity(root, uid=uid, gid=gid)
        self.journal = UpdateJournal(root, uid=uid, gid=gid)
        self.store = BundleStore(root, uid=uid, gid=gid)
        self.root = root
        self.run = run

    def discover(self, source: dict[str, Any]) -> Release | None:
        candidates: list[Release] = []
        seen: set[str] = set()
        inspected = 0
        for page in range(1, MAX_PAGES + 1):
            data = self.transport.fetch(f"{API}?per_page=100&page={page}", MAX_LISTING)
            rows = _json(data)
            if type(rows) is not list or len(rows) > 100:
                raise BootstrapError("malformed release listing")
            inspected += len(rows)
            if inspected > MAX_RELEASES:
                raise BootstrapError("release listing exceeds total release bound")
            for row in rows:
                if type(row) is not dict:
                    raise BootstrapError("malformed release listing entry")
                tag = row.get("tag_name") if type(row) is dict else None
                try:
                    relevant = _eligible(source, tag)
                except (contract.ReleaseError, TypeError):
                    continue
                if not relevant:
                    continue
                release = _release(row)
                if release is None:
                    continue
                if release.tag in seen:
                    raise BootstrapError(f"duplicate published release: {release.tag}")
                seen.add(release.tag)
                candidates.append(release)
            if len(rows) < 100:
                break
        else:
            raise BootstrapError("release listing exceeds supported page limit")
        return max(candidates, key=lambda value: contract.version_tuple(value.tag), default=None)

    def _driver(self, bundle, operation: str) -> str:
        driver = bundle.tree / "install/release_update.py"
        details = driver.lstat()
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != self.store.uid
                or details.st_gid != self.store.gid or details.st_mode & 0o022):
            raise BootstrapError("verified target driver has unsafe ownership or mode")
        command = ["/usr/bin/python3", str(driver), operation,
                   "--target-user", self.user.name]
        if operation != "resume":
            command += ["--release-metadata", str(bundle.metadata_path),
                        "--release-artifact", str(bundle.artifact_path)]
        result = self.run(command, cwd="/", env={"PATH": "/usr/bin:/bin",
                          "PYTHONDONTWRITEBYTECODE": "1"}, text=True,
                          capture_output=True, check=False)
        if result.returncode != 0:
            raise BootstrapError(f"target {operation} failed: {(result.stderr or result.stdout).strip()[:2000]}")
        return result.stdout.strip()

    def _completed(self, target: dict[str, Any]) -> None:
        if self.journal.inspect() is not None or self.identity.validate() != target:
            raise BootstrapError("target driver returned without completing the exact transaction")

    def resume_if_needed(self) -> bool:
        state = self.journal.inspect()
        if state is None:
            source = self.identity.validate(allow_absent=True)
            if source is None:
                return False
            digest = source["artifact"]["sha256"]
            if not os.path.lexists(self.store.parent / digest):
                return False
        else:
            if state["target_user"] != self.user.name:
                raise BootstrapError("active update belongs to a different target user")
            digest = state["target"]["artifact_sha256"]
        retained = self.store.resume(digest)
        if state is not None:
            if _compact_target(retained.metadata) != state["target"]:
                raise BootstrapError("retained target differs from active journal")
            installed = self.identity.validate()
            if (installed != retained.metadata
                    and _compact_source(installed) != state["source"]):
                raise BootstrapError("installed identity differs from active journal")
        preview = self.store.prepare(retained.metadata_path, retained.artifact_path,
                                     permanent=False)
        try:
            print("Resuming the exact incomplete Vanilla HyprArch update.")
            self._driver(preview, "resume")
            self._completed(preview.metadata)
            print(f"Vanilla HyprArch update complete: {preview.metadata['version']}")
            return True
        finally:
            self.store.preview_cleanup(preview)

    def run_update(self, answer=input) -> int:
        print("Vanilla HyprArch Update\n")
        if self.resume_if_needed():
            return 0
        source = self.identity.validate(allow_absent=True)
        if source is None:
            raise BootstrapError("This Vanilla HyprArch installation is unreleased/development. Automatic release updates are unavailable.")
        release = self.discover(source)
        if release is None:
            print(f"Vanilla HyprArch is up to date.\nInstalled: {source['version']}")
            return 0
        self.store._directory(self.root / "run")
        with tempfile.TemporaryDirectory(prefix="vanhyprarch-acquire-", dir=self.root / "run") as directory:
            temporary = Path(directory)
            metadata_path = temporary / "release.json"
            artifact_path = temporary / contract.artifact_name(release.tag)
            self.transport.fetch(release.metadata_url, contract.MAX_METADATA, metadata_path)
            if metadata_path.stat().st_size != release.metadata_size:
                raise BootstrapError("release metadata asset size changed")
            metadata = contract.parse_metadata(metadata_path.read_bytes())
            if metadata["version"] != release.tag or metadata["artifact"]["name"] != artifact_path.name:
                raise BootstrapError("release metadata does not match the published tag/assets")
            if metadata["artifact"]["size"] != release.artifact_size:
                raise BootstrapError("release asset size disagrees with metadata")
            self.transport.fetch(release.artifact_url, contract.MAX_ARTIFACT, artifact_path)
            if contract.verify(metadata_path, artifact_path) != metadata:
                raise BootstrapError("release bundle identity changed")
            preview = self.store.prepare(metadata_path, artifact_path, permanent=False)
            try:
                plan_text = self._driver(preview, "plan")
                plan = _json(plan_text.encode("utf-8"))
                if (type(plan) is not dict or plan.get("source") != source["version"]
                        or plan.get("target") != release.tag
                        or plan.get("target_sha256") != metadata["artifact"]["sha256"]
                        or type(plan.get("migrations")) is not list
                        or type(plan.get("authorities")) is not dict):
                    raise BootstrapError("target preflight returned an invalid plan")
                print(f"Installed: {source['version']}\nAvailable: {release.tag}\n")
                print(metadata["summary"])
                print(f"Release notes: {RELEASES}/tag/{release.tag}\n")
                stages = ", ".join(plan["authorities"])
                print(f"Plan: {len(plan['migrations'])} migration(s)"
                      + (f"; {stages}" if stages else ""))
                if answer("Update Vanilla HyprArch? [y/N] ").strip().lower() != "y":
                    print("Update canceled.")
                    return 0
                self._driver(preview, "apply")
                self._completed(metadata)
                print(f"Vanilla HyprArch update complete: {release.tag}")
                return 0
            finally:
                self.store.preview_cleanup(preview)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-user")
    arguments = parser.parse_args(argv)
    if os.geteuid() != 0:
        if arguments.target_user is not None:
            parser.error("--target-user is supplied by the sudo handoff")
        name = pwd.getpwuid(os.getuid()).pw_name
        return subprocess.call(["/usr/bin/sudo", "--", "/usr/local/bin/vanhyprarch-update",
                                "--target-user", name])
    if arguments.target_user is None:
        parser.error("root invocation requires explicit --target-user")
    try:
        user = TargetUser.resolve(arguments.target_user)
        return Bootstrap(user).run_update()
    except (BootstrapError, IdentityError, JournalError, UpdateError,
            contract.ReleaseError, OSError) as error:
        print(f"Vanilla HyprArch update unavailable: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
