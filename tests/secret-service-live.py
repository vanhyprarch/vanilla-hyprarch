#!/usr/bin/python
"""Read only acceptance metadata; never fetch secrets or dump user attributes."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("secret_service", str(ROOT / "install/secret_service_preflight.py"))
spec = importlib.util.spec_from_loader(loader.name, loader)
MODULE = importlib.util.module_from_spec(spec)
loader.exec_module(MODULE)


def inspect(audit):
    status = audit.preflight()
    ready = status["current_owner"] == "gnome-keyring"
    result = {"gnome_keyring_owner": ready}
    if not ready:
        return result
    owner = audit.bus("GetNameOwner", "s", MODULE.NAME)[0]

    def call(method, signature, *args):
        argv = ["/usr/bin/busctl", f"--address=unix:path={audit.runtime}/bus",
                "--auto-start=no", "--json=short", "--timeout=10", "call", owner,
                "/org/freedesktop/secrets", "org.freedesktop.Secret.Service", method, signature, *args]
        return json.loads(audit.run(argv))["data"]

    login = call("ReadAlias", "s", "login")[0]
    default = call("ReadAlias", "s", "default")[0]
    result["default_is_login"] = login != "/" and default == login
    if login == "/":
        result["login_unlocked"] = False
    else:
        result["login_unlocked"] = json.loads(audit.run([
            "/usr/bin/busctl", f"--address=unix:path={audit.runtime}/bus", "--auto-start=no",
            "--json=short", "--timeout=10", "get-property", owner, login,
            "org.freedesktop.Secret.Collection", "Locked"]))["data"] is False
    keyring = audit.path(audit.data / "keyrings/login.keyring")
    try:
        info = keyring.lstat()
        result["persistent_login_file"] = (stat.S_ISREG(info.st_mode) and info.st_uid == audit.uid
                                           and not info.st_mode & 0o077)
    except FileNotFoundError:
        result["persistent_login_file"] = False
    count = 0
    for process in audit.path(Path("/proc")).iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid == audit.uid and (process / "exe").resolve() == audit.path(Path(MODULE.DAEMON)).resolve():
                count += 1
        except OSError:
            continue
    result["gnome_keyring_processes"] = count
    # Search only by the public application identifier; print counts, no paths,
    # labels, accounts, user attribute values, or secret material.
    unlocked, locked = call("SearchItems", "a{ss}", "1", "server", "Nextcloud")
    result["nextcloud_login_items_unlocked"] = sum(p.startswith(login + "/") for p in unlocked) if login != "/" else 0
    result["nextcloud_items_locked"] = len(locked)
    if audit.bus("GetNameOwner", "s", MODULE.NAME)[0] != owner:
        raise MODULE.ProviderError("provider changed during metadata inspection")
    return result


if __name__ == "__main__":
    try:
        result = inspect(MODULE.ProviderAudit())
        print(json.dumps(result, sort_keys=True))
        ok = (all(result.get(key) is True for key in ("gnome_keyring_owner", "default_is_login",
                                                      "login_unlocked", "persistent_login_file"))
              and result.get("gnome_keyring_processes") == 1)
        raise SystemExit(0 if ok else 1)
    except (MODULE.ProviderError, OSError, ValueError, KeyError, IndexError):
        print('{"metadata_verification_failed": true}')
        raise SystemExit(1)
