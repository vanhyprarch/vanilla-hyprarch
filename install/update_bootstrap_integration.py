"""Root-owned, provenance-gated installation of the standalone updater zipapp."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

# system_integration.py imports this authority as a direct-script sibling.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TARGET = Path("usr/local/bin/vanhyprarch-update")
STATE = Path("var/lib/vanhyprarch/update-bootstrap-v1.json")
SECURITY_STATE = Path("var/lib/vanhyprarch/distribution-security-v1.json")
FILES = (
    "install/update_bootstrap.py", "install/release_update.py",
    "install/release_identity.py", "install/update_journal.py",
    "install/release_migrations.py", "release/build.py",
    "install/secret_service_preflight.py",
    "release/distribution.py", "release/trust.json", "install/signed_distribution.py",
    "install/update_bootstrap_integration.py",
)
SHEBANG = b"#!/usr/bin/python3\n"
STATE_SCHEMA = 3
UPDATE_PROTOCOL = 1
MAX_PROVENANCE = 20 * 1024  # A pending publication also retains the bounded journal.


class BootstrapIntegrationError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapIntegrationError("duplicate bootstrap state key")
        result[key] = value
    return result


def payload_trust(payload: bytes) -> dict | None:
    """Read public anchor data only; never execute downloaded updater code."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if "release/trust.json" not in archive.namelist():
                return None  # Authentic historical updater/backup.
            info = archive.getinfo("release/trust.json")
            if info.file_size > 384 * 1024:
                raise BootstrapIntegrationError("oversized updater trust record")
            data = archive.read(info)
        value = json.loads(data, object_pairs_hook=_pairs)
        if (type(value) is not dict or set(value) != {"schema", "public_key", "root_sha256", "root"}
                or type(value["schema"]) is not int or value["schema"] != 1
                or (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode() != data):
            raise BootstrapIntegrationError("invalid updater trust record")
        if all(value[name] is None for name in ("public_key", "root_sha256", "root")):
            return value  # Development only; acquisition refuses unconfigured trust.
        if (not all(type(value[name]) is str for name in ("public_key", "root_sha256", "root"))
                or len(value["root_sha256"]) != 64
                or any(ch not in "0123456789abcdef" for ch in value["root_sha256"])):
            raise BootstrapIntegrationError("incomplete updater trust record")
        return value
    except (ValueError, KeyError, zipfile.BadZipFile) as error:
        raise BootstrapIntegrationError("invalid packaged updater trust") from error


def provenance_bytes(payload: bytes, previous: dict | None = None) -> bytes:
    trust = payload_trust(payload)
    value = {"schema": 2 if trust is None else STATE_SCHEMA,
             "sha256": hashlib.sha256(payload).hexdigest(), "update_protocol": UPDATE_PROTOCOL}
    if trust is not None:
        anchor = trust["root_sha256"]
        initialized = False
        if previous and previous["schema"] == STATE_SCHEMA:
            if (previous["distribution_anchor_sha256"] != anchor
                    and (previous["distribution_anchor_sha256"] is not None
                         or previous["distribution_initialized"])):
                raise BootstrapIntegrationError("initial trust-anchor replacement requires explicit trust recovery")
            initialized = previous["distribution_initialized"]
        value.update(distribution_anchor_sha256=anchor, distribution_initialized=initialized)
    elif previous and previous.get("distribution_initialized"):
        raise BootstrapIntegrationError("cannot replace initialized signed updater with an unsigned updater")
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class BootstrapIntegration:
    def __init__(self, source: Path, root: Path = Path("/"), *,
                 uid: int = 0, gid: int = 0) -> None:
        self.source, self.root, self.uid, self.gid = source, root, uid, gid
        self.target, self.state = root / TARGET, root / STATE

    def _dir(self, path: Path, *, create: bool = False, private: bool = False) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            if not create:
                raise BootstrapIntegrationError(f"required directory is absent: {path}") from None
            path.mkdir(mode=0o700 if private else 0o755)
            os.chown(path, self.uid, self.gid)
            path.chmod(0o700 if private else 0o755)
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or info.st_mode & 0o022 or (private and stat.S_IMODE(info.st_mode) != 0o700)):
            raise BootstrapIntegrationError(f"unsafe bootstrap parent: {path}")

    def _parents(self, path: Path, *, create: bool = False, private: bool = False) -> bool:
        current = self.root
        self._dir(current)
        for component in path.relative_to(self.root).parts[:-1]:
            current = current / component
            try:
                self._dir(current, create=create, private=private and current == self.state.parent)
            except BootstrapIntegrationError:
                if not create and not current.exists():
                    return False
                raise
        return True

    def build(self) -> bytes:
        contents = {}
        for name in FILES:
            path = self.source / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                raise BootstrapIntegrationError(f"unsafe updater source: {name}")
            for parent in path.relative_to(self.source).parents:
                if parent == Path("."):
                    break
                if (self.source / parent).is_symlink():
                    raise BootstrapIntegrationError(f"symlinked updater source: {name}")
            contents[name] = path.read_bytes()
        return self.package_files(contents)

    @staticmethod
    def package_files(sources: dict[str, bytes]) -> bytes:
        """Same deterministic zipapp, also usable from a verified release archive."""
        if (set(sources) != set(FILES)
                or any(type(data) is not bytes or len(data) > 1024 * 1024
                       for data in sources.values())):
            raise BootstrapIntegrationError("invalid updater source set")
        output = io.BytesIO()
        output.write(SHEBANG)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            contents = {"__main__.py": b"from install.update_bootstrap import main\nraise SystemExit(main())\n",
                        "install/__init__.py": b"", "release/__init__.py": b""}
            contents.update(sources)
            # Phase 4 modules have direct-script imports; include those names as
            # top-level aliases without changing their installed release APIs.
            contents["release_identity.py"] = contents["install/release_identity.py"]
            contents["update_journal.py"] = contents["install/update_journal.py"]
            for name, data in sorted(contents.items()):
                item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                item.external_attr = 0o100644 << 16
                archive.writestr(item, data)
        return output.getvalue()

    def _record(self, *, allow_legacy: bool = False) -> dict | None:
        if not self._parents(self.state):
            return None
        try:
            info = self.state.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > MAX_PROVENANCE):
            raise BootstrapIntegrationError("unsafe updater provenance")
        descriptor = os.open(self.state, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            with os.fdopen(descriptor, "rb") as source:
                value = json.loads(source.read(MAX_PROVENANCE + 1), object_pairs_hook=_pairs)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise BootstrapIntegrationError(f"invalid updater provenance: {error}") from error
        legacy = (
            type(value) is dict
            and set(value) == {"schema", "sha256"}
            and type(value.get("schema")) is int
            and value["schema"] == 1
        )
        version_two = (
            type(value) is dict
            and set(value) == {"schema", "sha256", "update_protocol"}
            and type(value.get("schema")) is int
            and value["schema"] == 2
            and type(value.get("update_protocol")) is int
            and value["update_protocol"] == UPDATE_PROTOCOL
        )
        current_keys = {
            "schema", "sha256", "update_protocol", "distribution_anchor_sha256", "distribution_initialized"}
        current = (type(value) is dict and set(value) in (current_keys, current_keys | {"publication"})
            and type(value["schema"]) is int and value["schema"] == STATE_SCHEMA
            and type(value["update_protocol"]) is int and value["update_protocol"] == UPDATE_PROTOCOL
            and type(value["distribution_initialized"]) is bool)
        if current:
            anchor = value["distribution_anchor_sha256"]
            if (anchor is not None and (type(anchor) is not str or len(anchor) != 64
                                       or any(ch not in "0123456789abcdef" for ch in anchor))
                    or anchor is None and value["distribution_initialized"]):
                raise BootstrapIntegrationError("invalid distribution initialization provenance")
            if "publication" in value:
                from install.update_journal import validate_record
                publication = value["publication"]
                if (not value["distribution_initialized"] or type(publication) is not dict
                        or set(publication) != {"journal", "replacement_sha256"}
                        or type(publication["replacement_sha256"]) is not str
                        or len(publication["replacement_sha256"]) != 64
                        or any(ch not in "0123456789abcdef" for ch in publication["replacement_sha256"])):
                    raise BootstrapIntegrationError("invalid updater publication intent")
                snapshot = validate_record(publication["journal"])
                if (snapshot["phase"] != "applying" or snapshot["checkpoint"] != "system-integration"
                        or snapshot["pending_migration"] is not None
                        or len(snapshot["completed_migrations"]) != (
                            snapshot["target"]["migration_level"] - snapshot["source"]["migration_level"])):
                    raise BootstrapIntegrationError("updater publication is outside its transaction stage")
        if legacy and not allow_legacy:
            raise BootstrapIntegrationError("legacy updater provenance requires migration")
        digest = value.get("sha256") if legacy or version_two or current else None
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise BootstrapIntegrationError("invalid updater provenance")
        return value

    def _state(self, *, allow_legacy: bool = False) -> str | None:
        value = self._record(allow_legacy=allow_legacy)
        return value["sha256"] if value else None

    def _installed(self) -> str | None:
        if not self._parents(self.target):
            return None
        try:
            info = self.target.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or stat.S_IMODE(info.st_mode) != 0o755 or info.st_nlink != 1
                or info.st_size > 1024 * 1024):
            raise BootstrapIntegrationError("unsafe installed updater")
        descriptor = os.open(self.target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as source:
            return hashlib.sha256(source.read(1024 * 1024 + 1)).hexdigest()

    def plan(self, *, lifecycle: str) -> str:
        payload = self.build()
        desired = hashlib.sha256(payload).hexdigest()
        record = self._record(allow_legacy=(lifecycle == "upgrade"))
        provenance_bytes(payload, record)  # Trust conflicts precede package mutation.
        if (record is None or record["schema"] != STATE_SCHEMA) and os.path.lexists(self.root / SECURITY_STATE):
            raise BootstrapIntegrationError("unexplained distribution security state requires explicit recovery")
        prior = self._state(allow_legacy=(lifecycle == "upgrade"))
        installed = self._installed()
        if record and "publication" in record:
            if (lifecycle != "upgrade" or desired != record["publication"]["replacement_sha256"]
                    or installed not in {prior, desired}
                    or self._publication_context() != record["publication"]["journal"]):
                raise BootstrapIntegrationError("updater publication differs from its exact transaction")
            return "preserve" if installed == desired else "replace"
        if record and record.get("distribution_initialized") and installed == prior:
            previous_payload = self.target.read_bytes()
            if (hashlib.sha256(previous_payload).hexdigest() != installed
                    or payload_trust(previous_payload) != payload_trust(payload)):
                raise BootstrapIntegrationError("initial trust anchor is immutable; use signed root rotation")
        if installed == desired:
            if prior is None and lifecycle == "upgrade":
                raise BootstrapIntegrationError("upgrade lacks installed updater provenance")
            return "preserve"
        if prior is None:
            if lifecycle == "upgrade" or installed is not None:
                raise BootstrapIntegrationError("unproven installed updater")
            return "create"
        if installed is None:
            raise BootstrapIntegrationError("previously managed updater is missing")
        if installed != prior:
            raise BootstrapIntegrationError("installed updater differs from prior provenance")
        return "replace"

    def _publication_context(self) -> dict:
        """Only the locked, retained target's system-integration stage may publish.

        The target driver holds the release lock while its authority runs in a
        child process. Recovery holds that same lock in the installed bootstrap.
        Reading retained source here never imports or executes target modules.
        """
        from install.update_journal import UpdateJournal, JournalError, _compact_source, _compact_target
        from install.release_update import BundleStore
        journal = UpdateJournal(self.root, uid=self.uid, gid=self.gid)
        try:
            with journal.lock.acquire():
                raise BootstrapIntegrationError("updater publication requires the held release-update lock")
        except JournalError as error:
            if not isinstance(error.__cause__, BlockingIOError):
                raise
        snapshot = journal.inspect()
        if (snapshot is None or snapshot["phase"] != "applying"
                or snapshot["checkpoint"] != "system-integration"
                or snapshot["pending_migration"] is not None
                or len(snapshot["completed_migrations"]) != (
                    snapshot["target"]["migration_level"] - snapshot["source"]["migration_level"])
                or _compact_source(journal.identity.validate()) != snapshot["source"]):
            raise BootstrapIntegrationError("updater publication requires the exact active system-integration stage")
        retained = BundleStore(self.root, uid=self.uid, gid=self.gid).resume(snapshot["target"]["artifact_sha256"])
        if retained.tree != self.source or _compact_target(retained.metadata) != snapshot["target"]:
            raise BootstrapIntegrationError("updater source differs from the retained transaction target")
        return snapshot

    def _publish(self, path: Path, data: bytes, mode: int) -> None:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".vanhyprarch-update-",
                                         delete=False) as output:
            temporary = Path(output.name)
            try:
                os.fchown(output.fileno(), self.uid, self.gid)
                os.fchmod(output.fileno(), mode)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                published = os.fstat(output.fileno())
                if (published.st_uid, published.st_gid) != (self.uid, self.gid):
                    raise BootstrapIntegrationError("updater publication has unsafe ownership")
                os.replace(temporary, path)
                descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                temporary.unlink(missing_ok=True)

    def apply(self, *, lifecycle: str) -> None:
        action = self.plan(lifecycle=lifecycle)
        payload = self.build()
        record = self._record(allow_legacy=lifecycle == "upgrade")
        data = provenance_bytes(payload, record)
        if action != "preserve" and record and record.get("distribution_initialized") and "publication" not in record:
            # Write-ahead evidence survives death before, between, or after the
            # two atomic component publications. Never infer it from a mismatch.
            snapshot = self._publication_context()
            pending = {**record, "publication": {"journal": snapshot,
                                                "replacement_sha256": hashlib.sha256(payload).hexdigest()}}
            self._publish(self.state, (json.dumps(pending, sort_keys=True) + "\n").encode(), 0o600)
            if self._record() != pending:
                raise BootstrapIntegrationError("published updater intent differs")
        if action != "preserve":
            self._parents(self.target, create=True)
            self._publish(self.target, payload, 0o755)
        self._parents(self.state, create=True, private=True)
        desired = hashlib.sha256(self.build()).hexdigest()
        if self._installed() != desired:
            raise BootstrapIntegrationError("installed updater publication differs")
        if self._record() != json.loads(data):
            self._publish(self.state, data, 0o600)
        self.validate()

    def validate(self) -> None:
        desired = hashlib.sha256(self.build()).hexdigest()
        if self._state() != desired or self._installed() != desired:
            raise BootstrapIntegrationError("installed updater or provenance differs from target")
        if self._record() != json.loads(provenance_bytes(self.build(), self._record())):
            raise BootstrapIntegrationError("updater security provenance differs from target")
