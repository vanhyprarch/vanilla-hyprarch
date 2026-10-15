#!/usr/bin/env python3
"""Installed, fixed-repository release acquisition and verified target handoff.

This module is packaged in the root-owned vanhyprarch-update executable.
Target code runs only from a verified root-controlled preview after independent
signature, release-identity, archive, and durable authorization checks.
"""

from __future__ import annotations

import argparse
import http.client
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
from pathlib import Path
from typing import Any

from release import build as contract
from install.release_identity import InstalledReleaseIdentity, IdentityError
from install.release_update import BundleStore, TargetUser, UpdateError
from install.secret_service_preflight import capture_context, ProviderError
from install.update_journal import (UpdateJournal, JournalError,
                                    _compact_source, _compact_target)
from install.signed_distribution import (SecurityStore, Acquisition, Unavailable, PublicationPending,
                                         SERVERPLAN, GITHUB_METADATA, fixed_path)
from install.update_bootstrap_integration import BootstrapIntegration, payload_trust, provenance_bytes


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
TRUSTED_HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com",
                 "raw.githubusercontent.com", "vanhyprarch.it"}
ASSET_HOST = "release-assets.githubusercontent.com"
SYSTEM_UPDATE_VARIABLES = (
    "PATH", "TERM", "COLORTERM", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_DATA_DIRS", "XDG_STATE_HOME", "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
)


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
        elif url.startswith(SERVERPLAN) or url.startswith(GITHUB_METADATA):
            prefix = SERVERPLAN if url.startswith(SERVERPLAN) else GITHUB_METADATA
            fixed_path(url.removeprefix(prefix))
            asset = False
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
                    raise BootstrapError(f"unexpected distribution HTTP status {response.status}")
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
                        raise Unavailable("download is truncated")
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
                        raise Unavailable("download is truncated")
                    output.flush()
                    os.fsync(output.fileno())
                return None
        except urllib.error.HTTPError as error:
            error.close()
            if error.code == 403 and error.headers.get("X-RateLimit-Remaining") == "0":
                raise Unavailable("GitHub API rate limit reached") from error
            if error.code in {401, 403, 404, 408, 429} or 500 <= error.code <= 599:
                raise Unavailable(f"distribution returned HTTP {error.code}") from error
            raise BootstrapError(f"GitHub returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout, ssl.SSLError,
                http.client.IncompleteRead) as error:
            raise Unavailable("network unavailable or interrupted") from error



class Bootstrap:
    def __init__(self, user: TargetUser, *, transport: Transport | None = None,
                 root: Path = Path("/"), uid: int = 0, gid: int = 0,
                 run=subprocess.run, security: SecurityStore | None = None,
                 system_update_environment: dict[str, str] | None = None) -> None:
        self.user = user
        self.transport = transport or Transport()
        self.identity = InstalledReleaseIdentity(root, uid=uid, gid=gid)
        self.journal = UpdateJournal(root, uid=uid, gid=gid)
        self.store = BundleStore(root, uid=uid, gid=gid)
        self.root = root
        self.run = run
        self.security = security
        self.system_update_environment = system_update_environment

    def _recover_publication(self, source):
        """Complete only a previously recorded, signed transaction's pair.

        No target module is imported. The installed packager reconstructs bytes
        from the independently authenticated retained archive before the existing
        publication authority is allowed to repair either component.
        """
        from release import distribution as D
        self.security._locked()
        record = self.security.api._record()
        D.require(record is not None and "publication" in record, "publication intent is missing")
        snapshot = record["publication"]["journal"]
        D.require(self.journal.inspect() == snapshot and snapshot["target_user"] == self.user.name
                  and _compact_source(source) == snapshot["source"], "publication transaction or source identity mismatch")
        retained = self.store.resume(snapshot["target"]["artifact_sha256"])
        D.require(_compact_target(retained.metadata) == snapshot["target"]
                  and retained.metadata_bytes == D.canonical(retained.metadata), "publication target identity or bytes mismatch")
        self.security.authorize(retained.metadata, resume=True)
        proof = self.security._read()["authorization"]
        D.require({key: value for key, value in record.items() if key != "publication"} == proof["updater"],
                  "original updater provenance differs from its authorization receipt")
        D.compatible_release(source, retained.metadata)
        authority = BootstrapIntegration(retained.tree, self.root, uid=self.store.uid, gid=self.store.gid)
        payload = authority.build()
        D.require(D.digest(payload) == record["publication"]["replacement_sha256"]
                  and payload_trust(payload) == self.security.anchor,
                  "publication updater bytes or pinned trust differ from signed target")
        expected = json.loads(provenance_bytes(payload, record))
        D.require(expected["distribution_initialized"] and expected["distribution_anchor_sha256"]
                  == record["distribution_anchor_sha256"], "publication security provenance mismatch")
        authority.apply(lifecycle="upgrade")
        authority.validate()
        D.require(authority._record() == expected, "recovered updater provenance differs")

    def _authorize(self, metadata, *, resume=False):
        if self.security is None:
            raise BootstrapError("signed authorization is unavailable")
        with self.journal.lock.acquire():
            if not resume and self.journal.inspect() is not None:
                raise BootstrapError("an active update requires exact-target resume")
            self.security.authorize(metadata, resume=resume)

    def _driver(self, bundle, operation: str) -> str:
        driver = bundle.tree / "install/release_update.py"
        details = driver.lstat()
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != self.store.uid
                or details.st_gid != self.store.gid or details.st_mode & 0o022):
            raise BootstrapError("verified target driver has unsafe ownership or mode")
        command = ["/usr/bin/python3", str(driver), operation,
                   "--target-user", self.user.name]
        if self.user.provider_context is not None and (bundle.tree / "install/secret_service_preflight.py").is_file():
            command += ["--target-context-json", json.dumps(self.user.provider_context)]
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
                if os.path.lexists(self.store.parent):
                    self.store._parents(create=False)
                    if any(self.store.parent.iterdir()):
                        raise BootstrapError("uncommitted retained staging requires explicit exact-target recovery; discovery blocked")
                return False
        else:
            if state["target_user"] != self.user.name:
                raise BootstrapError("active update belongs to a different target user")
            digest = state["target"]["artifact_sha256"]
        retained = self.store.resume(digest)
        if retained.metadata_bytes != contract.metadata_bytes(retained.metadata):
            raise BootstrapError("retained metadata bytes differ from signed canonical identity")
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
            self._authorize(preview.metadata, resume=True)
            print("Resuming the exact incomplete Vanilla HyprArch update.")
            self._driver(preview, "resume")
            self._completed(preview.metadata)
            print(f"Vanilla HyprArch update complete: {preview.metadata['version']}")
            return True
        finally:
            self.store.preview_cleanup(preview)

    def _arch_maintenance(self) -> bool:
        """Reuse Update System's yay -Syu as the desktop user in this terminal.

        Package snapshots describe actual installed changes, not repository
        freshness. Yay owns the full repository/AUR update and its sudo prompts.
        Avoid guessing which changed libraries/processes need restarting: pause
        for an operator reboot after any package/version change. No reboot or
        maintenance receipt is installed, and release recovery never calls here.
        """
        environment = {"PATH": "/usr/bin:/bin"}
        captured = self.system_update_environment
        if (self.user.uid == 0 or type(captured) is not dict
                or set(captured) - set(SYSTEM_UPDATE_VARIABLES)
                or any(type(value) is not str or any(ord(c) < 32 for c in value)
                       for value in captured.values())
                or len(json.dumps(captured)) > 16384):
            raise BootstrapError("Update System requires the desktop user's captured environment; invoke Vanilla Update from that user's terminal.")
        user_environment = {**environment, **captured, "HOME": str(self.user.home),
                            "USER": self.user.name, "LOGNAME": self.user.name}

        def packages():
            result = self.run(["/usr/bin/pacman", "-Q"], cwd="/", env=environment,
                              text=True, capture_output=True, check=False)
            if result.returncode != 0 or not result.stdout.strip():
                raise BootstrapError("Cannot inspect installed Arch packages; Vanilla update not started.")
            return frozenset(result.stdout.splitlines())

        before = packages()
        try:
            # Identical executable/options to UpdateActions.qml. Yay, not a
            # project package updater, owns repository and AUR maintenance.
            result = self.run(["/usr/bin/yay", "-Syu"], cwd=str(self.user.home),
                              env=user_environment, user=self.user.uid, group=self.user.gid,
                              extra_groups=self.user.groups, check=False)
        except KeyboardInterrupt:
            raise BootstrapError("Update System interrupted; complete yay -Syu before retrying. Vanilla update not started.") from None
        if result.returncode != 0:
            raise BootstrapError("Update System failed or was canceled; complete yay -Syu before retrying. Vanilla update not started.")
        after = packages()
        pending = self.run(["/usr/bin/pacman", "-Qu"], cwd="/", env=environment,
                           text=True, capture_output=True, check=False)
        if (pending.returncode not in {0, 1}
                or (pending.returncode == 1 and pending.stderr.strip())):
            raise BootstrapError("Cannot verify completion of Arch maintenance; Vanilla update not started.")
        if pending.stdout.strip():
            raise BootstrapError("Arch upgrades remain (possibly canceled or ignored); complete yay -Syu before retrying. Vanilla update not started.")
        if before != after:
            print("\nArch packages changed. Vanilla update has not started.")
            print("Reboot using the normal power menu, then invoke Vanilla Update again.")
            print("This conservative pause also covers kernel, systemd, Hyprland and Quickshell updates.")
            return False
        return True

    def run_update(self, answer=input) -> int:
        print("Vanilla HyprArch Update\n")
        source = self.identity.validate(allow_absent=True)
        if source is None:
            raise BootstrapError("This Vanilla HyprArch installation is unreleased/development. Automatic release updates are unavailable.")
        self.security = self.security or SecurityStore(self.journal)
        self.security.journal = self.journal
        with self.journal.lock.acquire():
            try:
                self.security.start()
            except PublicationPending:
                self._recover_publication(source)
                self.security.start()
        if self.resume_if_needed():
            return 0
        self.store._directory(self.root / "run")
        with tempfile.TemporaryDirectory(prefix="vanhyprarch-acquire-", dir=self.root / "run") as directory:
            temporary = Path(directory)
            with self.journal.lock.acquire():
                result = Acquisition(self.security, self.transport).acquire(source, temporary)
            if result is None:
                print(f"Vanilla HyprArch is up to date.\nInstalled: {source['version']}")
                return 0
            metadata, metadata_path, artifact_path = result
            tag = metadata["version"]
            print(f"Installed: {source['version']}\nAvailable: {tag}\n")
            print(metadata["summary"])
            print(f"Release notes: {RELEASES}/tag/{tag}\n")
            print("\nBefore Vanilla preflight, run Update System (yay -Syu: Arch repositories and AUR).")
            print("Review Arch upgrade notices first; yay retains its normal sudo and interactive prompts.")
            print("If packages change, reboot before continuing. No automatic reboot will occur.")
            try:
                approved = answer("Run Update System before Vanilla? [y/N] ").strip().lower() == "y"
            except (EOFError, KeyboardInterrupt):
                approved = False
            if not approved:
                print("Vanilla update canceled; Arch maintenance and Vanilla apply were not started.")
                return 0
            with self.journal.lock.acquire():
                if self.identity.validate() != source:
                    raise BootstrapError("installed release changed before Arch maintenance")
                if self.journal.inspect() is not None:
                    raise BootstrapError("an active update requires exact-target resume")
                self.security.authorize(metadata)
                if not self._arch_maintenance():
                    return 0
            print("\nArch maintenance complete; installed packages unchanged. Checking Vanilla target.")
            preview = self.store.prepare(metadata_path, artifact_path, permanent=False)
            try:
                self._authorize(metadata)
                plan_text = self._driver(preview, "plan")
                plan = _json(plan_text.encode("utf-8"))
                if (type(plan) is not dict or plan.get("source") != source["version"]
                        or plan.get("target") != tag
                        or plan.get("target_sha256") != metadata["artifact"]["sha256"]
                        or type(plan.get("migrations")) is not list
                        or type(plan.get("authorities")) is not dict):
                    raise BootstrapError("target preflight returned an invalid plan")
                stages = ", ".join(plan["authorities"])
                print(f"Plan: {len(plan['migrations'])} migration(s)"
                      + (f"; {stages}" if stages else ""))
                if answer("Update Vanilla HyprArch? [y/N] ").strip().lower() != "y":
                    print("Update canceled.")
                    return 0
                self._authorize(metadata)
                self._driver(preview, "apply")
                self._completed(metadata)
                print(f"Vanilla HyprArch update complete: {tag}")
                return 0
            finally:
                self.store.preview_cleanup(preview)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-user")
    parser.add_argument("--target-context-json")
    parser.add_argument("--system-update-environment", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if os.geteuid() != 0:
        if (arguments.target_user is not None or arguments.target_context_json is not None
                or arguments.system_update_environment is not None):
            parser.error("--target-user is supplied by the sudo handoff")
        name = pwd.getpwuid(os.getuid()).pw_name
        try:
            context = capture_context(os.environ, os.getuid(), Path(pwd.getpwuid(os.getuid()).pw_dir))
        except (ProviderError, ValueError):
            print("Vanilla HyprArch update unavailable: invalid target-user XDG context", file=sys.stderr)
            return 1
        return subprocess.call(["/usr/bin/sudo", "--", "/usr/local/bin/vanhyprarch-update",
                                "--target-user", name, "--target-context-json", json.dumps(context),
                                "--system-update-environment", json.dumps({
                                    key: os.environ[key] for key in SYSTEM_UPDATE_VARIABLES
                                    if key in os.environ})])
    if arguments.target_user is None:
        parser.error("root invocation requires explicit --target-user")
    try:
        user = TargetUser.resolve(arguments.target_user,
                                  provider_context=json.loads(arguments.target_context_json) if arguments.target_context_json else None)
        return Bootstrap(user, system_update_environment=(
            json.loads(arguments.system_update_environment)
            if arguments.system_update_environment is not None else None)).run_update()
    except (BootstrapError, Unavailable, IdentityError, JournalError, UpdateError,
            contract.ReleaseError, OSError, ValueError) as error:
        print(f"Vanilla HyprArch update unavailable: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
