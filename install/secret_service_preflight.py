#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only
"""Installer-only read-only Secret Service compatibility preflight.

Never reads keyring contents, changes provider settings, enables units, or
handles a password. Runs as the target user before package provisioning;
never on session startup.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import pwd
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET


NAME = "org.freedesktop.secrets"
DAEMON = "/usr/bin/gnome-keyring-daemon"
MAX_BYTES = 1024 * 1024


class ProviderError(RuntimeError):
    pass


CONTEXT_KEYS = {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_DATA_DIRS", "KPXC_CONFIG"}


def capture_context(environment, uid, home):
    """Capture only provider discovery paths in the invoking user's context."""
    runtime = f"/run/user/{uid}"
    if (environment.get("XDG_RUNTIME_DIR", runtime) != runtime
            or environment.get("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus") != f"unix:path={runtime}/bus"):
        raise ProviderError("nonstandard target-user runtime/bus context requires review")
    values = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": environment.get("XDG_CONFIG_HOME") or str(home / ".config"),
        "XDG_DATA_HOME": environment.get("XDG_DATA_HOME") or str(home / ".local/share"),
        "XDG_DATA_DIRS": environment.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share",
    }
    if environment.get("KPXC_CONFIG"):
        values["KPXC_CONFIG"] = environment["KPXC_CONFIG"]
    context = {"uid": uid, "environment": values}
    context_environment(context, uid, home)
    return context


def context_environment(context, uid, home):
    """Validate an explicit invocation input, never inherited sudo variables."""
    if (not isinstance(context, dict) or set(context) != {"uid", "environment"}
            or type(context["uid"]) is not int or context["uid"] != uid):
        raise ProviderError("target-user context identity is unverified")
    values = context["environment"]
    if (not isinstance(values, dict) or set(values) - CONTEXT_KEYS
            or not {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_DATA_DIRS"} <= set(values)
            or values["HOME"] != str(home)):
        raise ProviderError("target-user XDG context is incomplete or ambiguous")
    for name, value in values.items():
        if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
            raise ProviderError("target-user XDG context contains an invalid value")
        for part in value.split(":") if name == "XDG_DATA_DIRS" else [value]:
            ProviderAudit.absolute(part)
    return {**values, "XDG_RUNTIME_DIR": f"/run/user/{uid}"}


def run(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                                stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProviderError("provider command unavailable or timed out") from error
    if result.returncode:
        # Do not forward arbitrary command output or user configuration.
        raise ProviderError("provider command failed")
    return result.stdout


class ProviderAudit:
    def __init__(self, *, environment=None, root=Path("/"), uid=None, runner=run):
        self.env = os.environ if environment is None else environment
        self.root = root
        self.uid = os.getuid() if uid is None else uid
        self.run = runner
        self.home = self.absolute(self.env.get("HOME", ""))
        self.config = self.absolute(self.env.get("XDG_CONFIG_HOME") or str(self.home / ".config"))
        self.data = self.absolute(self.env.get("XDG_DATA_HOME") or str(self.home / ".local/share"))
        self.runtime = self.absolute(self.env.get("XDG_RUNTIME_DIR") or f"/run/user/{self.uid}")

    @staticmethod
    def absolute(value):
        path = Path(value)
        if not value or not path.is_absolute() or ".." in path.parts:
            raise ProviderError("ambiguous XDG path")
        return path

    def path(self, path):
        return self.root / path.relative_to("/")

    def read(self, path, *, registration=False):
        target = self.path(path)
        try:
            # Symlinked or inaccessible provider inputs require manual review.
            for parent in [target, *target.parents]:
                if parent == self.root.parent:
                    break
                if parent.is_symlink() and not (registration and parent == target):
                    raise ProviderError("ambiguous symlink in provider configuration")
            info = target.lstat()
        except FileNotFoundError:
            return None
        if registration and stat.S_ISLNK(info.st_mode):
            info = target.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ProviderError("ambiguous provider configuration file")
        return target.read_text(encoding="utf-8")

    def directory(self, path, pattern):
        target = self.path(path)
        if target.is_symlink():
            raise ProviderError("ambiguous provider directory")
        if not target.exists():
            return []
        if not target.is_dir():
            raise ProviderError("ambiguous provider directory")
        return [path / entry.name for entry in sorted(target.glob(pattern))]

    def configured_providers(self):
        config = self.absolute(self.env.get("KPXC_CONFIG") or str(self.config / "keepassxc/keepassxc.ini"))
        text = self.read(config)
        if text is None:
            return
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(text)
        if parser.getboolean("FdoSecrets", "Enabled", fallback=False):
            raise ProviderError("competing configured KeePassXC Secret Service; preserve user settings")
        return

    def service_directories(self):
        paths = {self.runtime / "dbus-1/services", self.data / "dbus-1/services",
                 Path("/usr/local/share/dbus-1/services"), Path("/usr/share/dbus-1/services")}
        for value in (self.env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
            paths.add(self.absolute(value) / "dbus-1/services")
        visited = set()

        def config(path):
            if path in visited:
                return
            visited.add(path)
            text = self.read(path)
            if text is None:
                return
            tree = ET.fromstring(text)
            for node in tree:
                value = (node.text or "").strip()
                if node.tag == "servicedir":
                    paths.add(self.absolute(value))
                elif node.tag in {"include", "includedir"}:
                    if node.attrib.get("if_selinux_enabled"):
                        continue
                    child = Path(value)
                    if not child.is_absolute():
                        child = path.parent / child
                    if node.tag == "include":
                        config(child)
                    else:
                        for entry in self.directory(child, "*.conf"):
                            config(entry)
        config(Path("/usr/share/dbus-1/session.conf"))
        return sorted(paths)

    def registrations(self):
        found = 0
        for directory in self.service_directories():
            for path in self.directory(directory, "*.service"):
                text = self.read(path, registration=True)
                if text is None:
                    raise ProviderError("provider registration changed during inspection")
                if NAME not in text and path.name != NAME + ".service":
                    continue
                if self.path(path).is_symlink():
                    raise ProviderError("ambiguous symlinked Secret Service registration")
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(text)
                section = parser["D-BUS Service"]
                if section.get("Name") != NAME:
                    raise ProviderError("ambiguous Secret Service registration")
                command = shlex.split(section.get("Exec", ""))
                if (not command or command[0] != DAEMON or "--start" not in command
                        or "--components=secrets" not in command
                        or set(command[1:]) - {"--start", "--foreground", "--components=secrets"}
                        or section.get("SystemdService")):
                    raise ProviderError("competing Secret Service registration; preserve provider")
                found += 1
        return found

    def bus(self, method, signature="", *arguments):
        argv = ["/usr/bin/busctl", f"--address=unix:path={self.runtime}/bus",
                "--auto-start=no", "--timeout=10", "--json=short", "call",
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", method]
        if signature:
            argv.extend([signature, *arguments])
        return json.loads(self.run(argv))["data"]

    def owner(self, *, registrations=0):
        address = self.env.get("DBUS_SESSION_BUS_ADDRESS")
        if address and address != f"unix:path={self.runtime}/bus":
            raise ProviderError("ambiguous nonstandard user bus; review provider manually")
        socket = self.path(self.runtime / "bus")
        runtime = self.path(self.runtime)
        if runtime.exists():
            info = runtime.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != self.uid
                    or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
                raise ProviderError("unsafe user runtime directory")
        try:
            info = socket.lstat()
        except FileNotFoundError:
            return "no-session"
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != self.uid:
            raise ProviderError("unsafe user bus")
        if not self.bus("NameHasOwner", "s", NAME)[0]:
            if NAME in self.bus("ListActivatableNames")[0] and not registrations:
                raise ProviderError("ambiguous activatable Secret Service without inspected registration")
            return "none"
        owner = self.bus("GetNameOwner", "s", NAME)[0]
        pid = self.bus("GetConnectionUnixProcessID", "s", owner)[0]
        uid = self.bus("GetConnectionUnixUser", "s", owner)[0]
        process = self.path(Path(f"/proc/{pid}"))
        before = (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
        if (uid != self.uid or process.stat().st_uid != self.uid
                or (process / "exe").resolve() != self.path(Path(DAEMON)).resolve()):
            raise ProviderError("competing current Secret Service owner; preserve provider")
        if (before != (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
                or self.bus("GetNameOwner", "s", NAME)[0] != owner):
            raise ProviderError("Secret Service identity changed during inspection")
        package = self.run(["/usr/bin/pacman", "-Qqo", "--", DAEMON]).strip()
        if package != "gnome-keyring":
            raise ProviderError("ambiguous Secret Service executable ownership")
        return "gnome-keyring"

    def preflight(self):
        self.configured_providers()
        registrations = self.registrations()
        owner = self.owner(registrations=registrations)
        return {"provider": "gnome-keyring" if registrations or owner == "gnome-keyring" else "none",
                "current_owner": owner, "configured_provider": "none"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("context", "preflight"))
    parser.add_argument("--context-json")
    args = parser.parse_args(argv)
    try:
        account = pwd.getpwuid(os.getuid())
        if args.operation == "context":
            if os.getuid() == 0:
                raise ProviderError("capture context in the target user's normal session")
            print(json.dumps(capture_context(os.environ, account.pw_uid, Path(account.pw_dir)), sort_keys=True))
        else:
            if args.context_json is None:
                raise ProviderError("explicit target-user context required")
            environment = context_environment(json.loads(args.context_json), account.pw_uid, Path(account.pw_dir))
            print(json.dumps(ProviderAudit(environment=environment).preflight(), sort_keys=True))
        return 0
    except ProviderError as error:
        print(f"Secret Service: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, IndexError, configparser.Error, ET.ParseError):
        # Stable diagnostics only; parser errors can contain personal data.
        print("Secret Service preflight blocked; preserve existing provider and review configuration", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
