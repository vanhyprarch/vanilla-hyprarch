#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""One-time, offline v1.0.0 updater preparation. Never invokes a release update."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]


def protected_source():
    """Check before importing project code across the administrative boundary."""
    paths = [PROJECT / "admin/prepare-updater.py"]
    for directory in (PROJECT / "install", PROJECT / "release"):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("administrative source directory is unsafe")
        paths.extend(directory.rglob("*.py"))
    for path in paths:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (0, 0)
                or info.st_mode & 0o022):
            raise ValueError("administrative source is not root protected")
        for parent in path.parents:
            info = parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (0, 0)
                    or info.st_mode & 0o022):
                raise ValueError("administrative source parent is not root protected")


if __name__ == "__main__" and os.getuid() == 0:
    try:
        protected_source()
    except (ValueError, OSError) as error:
        print(f"updater preparation refused: {error}", file=sys.stderr)
        raise SystemExit(1)

sys.path.insert(0, str(PROJECT))
from install.update_bootstrap_integration import (BootstrapIntegration, FILES, TARGET, STATE,
                                                 provenance_bytes, payload_trust)
from install.release_identity import InstalledReleaseIdentity
from install.release_update import TargetUser, STAGE_RELATIVE
from install.update_journal import UpdateJournal
from install.secret_service_preflight import capture_context, context_environment
from release import build as contract
from release import distribution as distribution
from install.signed_distribution import SECURITY
from install.signed_distribution import decoded

ORIGINAL_COMMIT = "8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb"
ORIGINAL_UPDATER = "13435389ce2e8d2e89d081ddab96b6f8287ccb58213d9a2c23b3b8fc6b9fb54d"
ORIGINAL_IDENTITY = "6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c"
BACKUP = Path("root/vanhyprarch-updater-preparation")
GUARDS = (Path("var/lib/vanhyprarch/system-integration-transaction-v1.json"), STAGE_RELATIVE)


class PreparationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PreparationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate administrative receipt key")
        result[key] = value
    return result


def provenance(payload):
    return provenance_bytes(payload)


def protected_bundle(metadata, artifact):
    safety = BootstrapIntegration(PROJECT)
    for path in (metadata, artifact):
        require(path.is_absolute() and path.resolve(strict=True) == path and safety._parents(path),
                "bundle parent is absent or unsafe")
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and (info.st_uid, info.st_gid) == (0, 0)
                and stat.S_IMODE(info.st_mode) == 0o644,
                "bundle files must be protected root-owned mode-0644 regular files")


def updater_running(proc=Path("/proc")):
    """Inspect Python executable/script names only, never application arguments."""
    for entry in proc.iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            executable = Path(os.readlink(entry / "exe")).name
            if not executable.startswith("python"):
                continue
            with (entry / "cmdline").open("rb", buffering=0) as stream:
                for _ in range(2):
                    argument = bytearray()
                    for _ in range(4096):
                        char = stream.read(1)
                        if char in {b"", b"\0"}:
                            break
                        argument.extend(char)
                    else:
                        raise PreparationError("unverifiable running Python command")
                    if (argument == b"/usr/local/bin/vanhyprarch-update"
                            or argument.endswith(b"/install/release_update.py")):
                        return True
        except FileNotFoundError:
            continue
    return False


def captured_context(environment, uid, home):
    context = {"provider": capture_context(environment, uid, home),
               "state": environment.get("XDG_STATE_HOME") or str(home / ".local/state"),
               "cache": environment.get("XDG_CACHE_HOME") or str(home / ".cache")}
    validate_context(context, uid, home)
    return context


def validate_context(context, uid, home):
    require(type(context) is dict and set(context) == {"provider", "state", "cache"},
            "explicit invoking-user XDG context is required")
    context_environment(context["provider"], uid, home)
    require(context["state"] == str(home / ".local/state")
            and context["cache"] == str(home / ".cache"),
            "prepared updater requires default XDG_STATE_HOME and XDG_CACHE_HOME")


def payload_from_bundle(metadata, artifact, commit, bundle_hash):
    require(contract.SHA40.fullmatch(commit) is not None
            and contract.SHA64.fullmatch(bundle_hash) is not None, "exact approval hashes required")
    value = contract.verify(metadata, artifact)
    require(value["commit"] == commit and value["artifact"]["sha256"] == bundle_hash,
            "bundle differs from explicitly approved source/artifact")
    require(value["update_protocol"] == 1 and value["migration_level"] == 1,
            "unsupported preparation protocol or migration level")
    # Read only verified regular archive members; reuse the authoritative zipapp
    # packager without extracting anything in check mode.
    with contract._open_regular(artifact, contract.MAX_ARTIFACT, "artifact") as (raw, _):
        require(hashlib.file_digest(raw, "sha256").hexdigest() == bundle_hash,
                "artifact changed before reading updater")
        raw.seek(0)
        with tarfile.open(fileobj=raw, mode="r:gz") as archive:
            prefix = contract.archive_root(value["version"]) + "/"
            sources = {}
            for name in FILES:
                member = archive.getmember(prefix + name)
                require(member.isfile() and member.size <= 1024 * 1024, "unsafe updater member")
                sources[name] = archive.extractfile(member).read(1024 * 1024 + 1)
        raw.seek(0)
        require(hashlib.file_digest(raw, "sha256").hexdigest() == bundle_hash,
                "artifact changed while reading updater")
    require(contract.verify(metadata, artifact) == value, "bundle changed during verification")
    with contract._open_regular(metadata, contract.MAX_METADATA, "metadata") as (stream, _):
        require(stream.read(contract.MAX_METADATA + 1) == contract.metadata_bytes(value),
                "preparation requires unchanged canonical bundle metadata")
    return value, BootstrapIntegration.package_files(sources)


def build_bundle(source, commit, output):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args]).decode().strip()
    require(source.resolve() != PROJECT and source.is_dir(), "use a separate clean checkout")
    require(git("rev-parse", "HEAD") == commit and not git("status", "--porcelain", "--untracked-files=all"),
            "source checkout must be clean at the explicitly approved commit")
    require(git("remote", "get-url", "origin") in {
        "https://github.com/vanhyprarch/vanilla-hyprarch.git",
        "git@github.com:vanhyprarch/vanilla-hyprarch.git"}, "unexpected source repository")
    require(output.is_dir() and not any(output.iterdir()), "use an empty bundle output directory")
    authenticate_source(source, commit)
    metadata, artifact = contract.build(source, commit, output)
    value = contract.verify(metadata, artifact)
    _, payload = payload_from_bundle(metadata, artifact, commit, value["artifact"]["sha256"])
    # Run the approved checkout's existing packager as the ordinary builder
    # user; compare its bytes with the read-only archive packaging path. No
    # source-provided Python is executed during privileged preparation.
    approved_payload = subprocess.check_output([
        sys.executable, "-I", "-B", "-c",
        "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
        "from install.update_bootstrap_integration import BootstrapIntegration; "
        "sys.stdout.buffer.write(BootstrapIntegration(Path(sys.argv[1])).build())",
        str(source)])
    require(payload == approved_payload, "source/archive updater mismatch")
    require(git("rev-parse", "HEAD") == commit and not git("status", "--porcelain", "--untracked-files=all"),
            "source changed during construction")
    return {"source_commit": commit, "bundle_sha256": value["artifact"]["sha256"],
            "metadata_sha256": digest(metadata.read_bytes()), "updater_sha256": digest(payload),
            "provenance_sha256": digest(provenance(payload)),
            "authentication": "approved commit reachable from authenticated origin/main fetch; SHA-256 is integrity only"}


def authenticate_source(source, commit):
    # Reuse normal authenticated Git transport; no signature or trust protocol
    # is invented here. The operator must approve the exact commit separately.
    subprocess.run(["git", "-C", str(source), "fetch", "--no-tags", "origin", "main"],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor", commit, "FETCH_HEAD"],
                   check=True, stdout=subprocess.DEVNULL)


class FixedPayload(BootstrapIntegration):
    """Already verified bytes; retain the authority's plan/publication/validation."""
    def __init__(self, payload, root, uid=0, gid=0):
        super().__init__(Path("."), root, uid=uid, gid=gid)
        self.payload = payload

    def build(self):
        return self.payload


class Preparation:
    def __init__(self, metadata, artifact, commit, bundle_hash, *, root=Path("/"), uid=0, gid=0):
        self.root, self.uid, self.gid = root, uid, gid
        self.metadata, self.artifact = metadata, artifact
        self.commit, self.bundle_hash = commit, bundle_hash
        self.value, self.payload = payload_from_bundle(metadata, artifact, commit, bundle_hash)
        self.metadata_hash = digest(contract.metadata_bytes(self.value))
        require(digest(self.payload) != ORIGINAL_UPDATER, "preparation payload is unchanged")
        self.api = FixedPayload(self.payload, root, uid, gid)
        self.journal = UpdateJournal(root, uid=uid, gid=gid)
        self.backup = root / BACKUP

    def read(self, path, mode, limit=1024 * 1024):
        require(self.api._parents(path), "required preparation parent is absent")
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and (info.st_uid, info.st_gid) == (self.uid, self.gid)
                and stat.S_IMODE(info.st_mode) == mode and info.st_size <= limit,
                "unsafe preparation file metadata")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb") as stream:
            require(os.fstat(stream.fileno()) == info, "preparation file changed during open")
            data = stream.read(limit + 1)
        require(len(data) <= limit, "preparation file exceeds bound")
        return data

    def prerequisites(self):
        """Read-only official verifier and pinned-root checks before real preparation."""
        trust = payload_trust(self.payload)
        require(trust is not None and trust["root_sha256"] is not None,
                "preparation payload lacks a configured production trust anchor")
        executable = Path("/usr/bin/minisign")
        require(executable.is_file() and not executable.is_symlink(),
                "official Arch minisign must be installed before updater preparation")
        self.api._dir(executable.parent)
        info = executable.stat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and info.st_mode & 0o111,
                "Minisign executable ownership or mode is unsafe")
        subprocess.run(["/usr/bin/pacman", "-Q", "minisign"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        distribution.TrustedRoot.initial(decoded(trust["root"], distribution.MAX_ENVELOPE),
            pinned_public_key=trust["public_key"], pinned_root_sha256=trust["root_sha256"],
            minisign=distribution.Minisign(), clock=distribution.Clock(int(time.time())))

    def quiet(self):
        self.api._dir(self.root / "run")
        require(self.journal.inspect() is None, "release journal exists: use exact-target release recovery")
        record = self.api._record()
        require(not record or not record.get("distribution_initialized"),
                "signed updater has begun operation: updater-only preparation/rollback is unsafe")
        security_path = self.root / SECURITY
        require(not os.path.lexists(security_path),
                "distribution security state exists: use signed updater recovery")
        if self.root == Path("/"):
            self.prerequisites()
        for relative in GUARDS:
            path = self.root / relative
            require(self.api._parents(path) or not os.path.lexists(path), "unsafe transaction parent")
            if os.path.lexists(path):
                require(relative == STAGE_RELATIVE and path.is_dir() and not path.is_symlink(),
                        "incomplete system integration transaction")
                self.api._dir(path)
                require(not any(path.iterdir()), "retained release staging requires release recovery")
        require(not any((self.root / "run").glob("vanhyprarch-preview-*")),
                "existing updater preview staging requires review")
        # Discovery precedes the driver's lock. Never inspect process
        # environments, application arguments, or credentials; never signal PIDs.
        require(self.root != Path("/") or not updater_running(),
                "another updater process is running; close it before preparation")

    def identity(self):
        value = InstalledReleaseIdentity(self.root, uid=self.uid, gid=self.gid).validate()
        require(value["commit"] == ORIGINAL_COMMIT and value["version"] == "v1.0.0"
                and value["migration_level"] == 1 and value["channel"] == "stable",
                "only authentic stable v1.0.0 migration level 1 is supported")
        data = self.read(self.root / "usr/share/vanhyprarch/release.json", 0o644)
        require(digest(data) == ORIGINAL_IDENTITY, "installed release identity is not authentic v1.0.0")
        return data

    def receipt(self):
        if not os.path.lexists(self.backup):
            return None
        self.api._dir(self.backup, private=True)
        require({p.name for p in self.backup.iterdir()} == {
            "original-updater", "original-provenance", "original-release.json", "receipt.json"},
            "incomplete/unexplained backup: inspect it or revert VM snapshot")
        raw = self.read(self.backup / "receipt.json", 0o600, 8192)
        data = json.loads(raw, object_pairs_hook=pairs)
        expected = self.record()
        require(type(data) is dict and set(data) == set(expected) | {"direction"}
                and all(data[k] == v for k, v in expected.items())
                and data["direction"] in {"prepare", "restore"}
                and raw == encoded({**expected, "direction": data["direction"]}),
                "backup receipt differs from approval")
        for name, sha in (("original-updater", ORIGINAL_UPDATER),
                          ("original-provenance", digest(provenance(self.original()))),
                          ("original-release.json", ORIGINAL_IDENTITY)):
            require(digest(self.read(self.backup / name, 0o600)) == sha, "corrupt backup material")
        return data

    def original(self):
        data = self.read(self.backup / "original-updater", 0o600)
        require(digest(data) == ORIGINAL_UPDATER, "original updater backup checksum differs")
        return data

    def record(self):
        return {"schema": 1, "source_commit": self.commit, "bundle_sha256": self.bundle_hash,
                "metadata_sha256": self.metadata_hash,
                "updater_sha256": digest(self.payload), "provenance_sha256": digest(provenance(self.payload)),
                "original_updater_sha256": ORIGINAL_UPDATER, "original_identity_sha256": ORIGINAL_IDENTITY,
                "original_provenance_sha256": digest(encoded({"schema": 2, "sha256": ORIGINAL_UPDATER,
                                                               "update_protocol": 1})),
                "installed_metadata": {"uid": self.uid, "gid": self.gid,
                    "updater_mode": 0o755, "provenance_mode": 0o600, "identity_mode": 0o644}}

    def check(self):
        # An existing lock can be checked without creating any files. A missing
        # lock is only a snapshot observation; apply always acquires/rechecks it.
        lock = self.journal.lock
        with lock.acquire() if not lock.held and os.path.lexists(lock.path) else contextlib.nullcontext():
            self.quiet()
            self.identity()
            receipt = self.receipt()
            binary, state = self.api._installed(), self.api._state()
            old, new = ORIGINAL_UPDATER, digest(self.payload)
            require((binary, state) in ({(old, old)} if receipt is None else
                    ({(old, old), (new, old), (new, new)} if receipt["direction"] == "prepare"
                     else {(new, new), (old, new), (old, old)})),
                    "unrecognized updater/provenance pair: do not overwrite")
            actual_state = self.read(self.root / STATE, 0o600)
            require(actual_state == provenance(self.payload if state == new else
                    (self.original() if receipt else self.read(self.root / TARGET, 0o755))),
                    "noncanonical or mismatched provenance")
            action = (("restored" if binary == state == old else "restore-resume")
                      if receipt and receipt["direction"] == "restore" else
                      "prepared" if binary == state == new else
                      "resume" if binary != state else "replace")
            if not receipt or receipt["direction"] == "prepare":
                self.api.plan(lifecycle="upgrade")
            return {**self.record(), "status": action, "release_identity": "unchanged v1.0.0",
                    "components": ["/" + str(TARGET), "/" + str(STATE)]}

    def backup_original(self):
        original = self.read(self.root / TARGET, 0o755)
        prior = self.read(self.root / STATE, 0o600)
        identity = self.identity()
        require(digest(original) == ORIGINAL_UPDATER and prior == provenance(original),
                "original baseline changed before backup")
        # Never repair a half-written backup silently. Interruption here requires
        # inspecting/removing this unused backup or restoring the VM snapshot.
        self.api._dir(self.backup.parent)
        self.api._dir(self.backup, create=True, private=True)
        for name, data in (("original-updater", original), ("original-provenance", prior),
                           ("original-release.json", identity)):
            self.api._publish(self.backup / name, data, 0o600)
        self.api._publish(self.backup / "receipt.json", encoded({**self.record(), "direction": "prepare"}), 0o600)
        self.receipt()

    def apply(self, *, authorized=False, restore=False):
        require(authorized is True, "explicit --authorize is required; nothing changed")
        with self.journal.lock.acquire():
            self.check()
            receipt = self.receipt()
            require(receipt is not None or not restore, "no verified backup to restore")
            if receipt is None:
                self.backup_original()
                receipt = self.receipt()
            require(restore or receipt["direction"] == "prepare", "resume interrupted restoration with restore")
            if restore:
                if self.api._installed() != self.api._state() and receipt["direction"] == "prepare":
                    # Complete the recognized forward pair before beginning the
                    # reverse publication; no release payload is executed.
                    self.api.apply(lifecycle="upgrade")
                # Write intent durably before reversing publication order. This
                # recognizes old-binary/new-provenance only during restoration.
                self.api._publish(self.backup / "receipt.json", encoded({**self.record(), "direction": "restore"}), 0o600)
                api = FixedPayload(self.original(), self.root, self.uid, self.gid)
                api.plan(lifecycle="upgrade")
                api.apply(lifecycle="upgrade")
                api.validate()
            else:
                value, payload = payload_from_bundle(self.metadata, self.artifact, self.commit, self.bundle_hash)
                require(value == self.value and payload == self.payload,
                        "preparation source changed before publication")
                self.api.plan(lifecycle="upgrade")
                self.api.apply(lifecycle="upgrade")
                self.api.validate()
            self.quiet()
            self.identity()
            return self.check()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "check", "apply", "restore"))
    parser.add_argument("--approved-commit", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--target-user", help=argparse.SUPPRESS)
    parser.add_argument("--captured-context", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.operation == "build":
            require(os.getuid() != 0 and args.source is not None and args.output is not None,
                    "build as an ordinary user from an isolated checkout")
            result = build_bundle(args.source.resolve(), args.approved_commit, args.output.resolve())
        else:
            require(args.metadata is not None and args.artifact is not None and args.bundle_sha256,
                    "metadata, artifact and approved bundle SHA-256 are required")
            require(args.operation == "check" or args.authorize, "explicit --authorize is required; nothing changed")
            if os.getuid() != 0:
                require(args.target_user is None and args.captured_context is None,
                        "target context is captured automatically before sudo")
                account = pwd.getpwuid(os.getuid())
                context = captured_context(os.environ, account.pw_uid, Path(account.pw_dir))
                original = list(sys.argv[1:] if argv is None else argv)
                return subprocess.call(["/usr/bin/sudo", "--", "/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()),
                    *original, "--target-user", account.pw_name, "--captured-context", json.dumps(context)])
            require(args.target_user is not None and args.captured_context is not None,
                    "invoke from the target user's graphical terminal, not a root shell")
            # The administrative program and libraries must be an independently
            # verified, root-owned checkout, not mutable user-controlled code.
            protected_source()
            context = json.loads(args.captured_context, object_pairs_hook=pairs)
            require(type(context) is dict, "explicit invoking-user XDG context is required")
            target = TargetUser.resolve(args.target_user, provider_context=context.get("provider"))
            require(os.environ.get("SUDO_UID") == str(target.uid), "target differs from sudo invoking user")
            validate_context(context, target.uid, target.home)
            protected_bundle(args.metadata.absolute(), args.artifact.absolute())
            operation = Preparation(args.metadata.absolute(), args.artifact.absolute(),
                                    args.approved_commit, args.bundle_sha256)
            result = (operation.check() if args.operation == "check" else
                      operation.apply(authorized=args.authorize, restore=args.operation == "restore"))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        # Library diagnostics contain paths/state only; never print argv/context.
        print(f"updater preparation refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
