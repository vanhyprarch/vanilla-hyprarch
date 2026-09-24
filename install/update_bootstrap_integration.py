"""Root-owned, provenance-gated installation of the standalone updater zipapp."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path

TARGET = Path("usr/local/bin/vanhyprarch-update")
STATE = Path("var/lib/vanhyprarch/update-bootstrap-v1.json")
FILES = (
    "install/update_bootstrap.py", "install/release_update.py",
    "install/release_identity.py", "install/update_journal.py",
    "install/release_migrations.py", "release/build.py",
)
SHEBANG = b"#!/usr/bin/python3\n"


class BootstrapIntegrationError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapIntegrationError("duplicate bootstrap state key")
        result[key] = value
    return result


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
        output = io.BytesIO()
        output.write(SHEBANG)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            contents = {"__main__.py": b"from install.update_bootstrap import main\nraise SystemExit(main())\n",
                        "install/__init__.py": b"", "release/__init__.py": b""}
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
            # Phase 4 modules have direct-script imports; include those names as
            # top-level aliases without changing their installed release APIs.
            contents["release_identity.py"] = contents["install/release_identity.py"]
            contents["update_journal.py"] = contents["install/update_journal.py"]
            for name, data in sorted(contents.items()):
                item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                item.external_attr = 0o100644 << 16
                archive.writestr(item, data)
        return output.getvalue()

    def _state(self) -> str | None:
        if not self._parents(self.state):
            return None
        try:
            info = self.state.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid) != (self.uid, self.gid)
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 256):
            raise BootstrapIntegrationError("unsafe updater provenance")
        descriptor = os.open(self.state, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            with os.fdopen(descriptor, "rb") as source:
                value = json.loads(source.read(257), object_pairs_hook=_pairs)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise BootstrapIntegrationError(f"invalid updater provenance: {error}") from error
        digest = value.get("sha256") if (type(value) is dict
                                         and set(value) == {"schema", "sha256"}
                                         and type(value.get("schema")) is int
                                         and value["schema"] == 1) else None
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise BootstrapIntegrationError("invalid updater provenance")
        return digest

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
        desired = hashlib.sha256(self.build()).hexdigest()
        prior, installed = self._state(), self._installed()
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
        if action != "preserve":
            self._parents(self.target, create=True)
            self._publish(self.target, self.build(), 0o755)
        self._parents(self.state, create=True, private=True)
        desired = hashlib.sha256(self.build()).hexdigest()
        if self._installed() != desired:
            raise BootstrapIntegrationError("installed updater publication differs")
        if self._state() != desired:
            data = (json.dumps({"schema": 1, "sha256": desired}, sort_keys=True) + "\n").encode()
            self._publish(self.state, data, 0o600)
        self.validate()

    def validate(self) -> None:
        desired = hashlib.sha256(self.build()).hexdigest()
        if self._state() != desired or self._installed() != desired:
            raise BootstrapIntegrationError("installed updater or provenance differs from target")
