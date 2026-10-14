#!/usr/bin/env python3
"""Deterministic DF2 Phase 4/5 system-integration tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "install"))
SPEC = importlib.util.spec_from_file_location("system_integration", REPOSITORY / "install/system_integration.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

CommandResult = MODULE.CommandResult
IntegrationError = MODULE.IntegrationError
SystemIntegration = MODULE.SystemIntegration
TargetUser = MODULE.TargetUser


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def runner_home_path_is_authorized(value: str, *, source_root: Path, target_home: Path) -> bool:
    """Allow the resolved source and target roots, never an unrelated HOME."""
    if not value.startswith("/home/"):
        return True

    candidate = Path(os.path.normpath(value))
    allowed_roots = (source_root, target_home)
    return any(candidate == root or root in candidate.parents for root in allowed_roots)


class FakeRunner:
    """Persistent fake command boundary; no real integration command escapes."""

    def __init__(self, fixture: "Fixture") -> None:
        self.fixture = fixture

    def _state(self) -> dict:
        return load_json(self.fixture.runner_state)

    def _save(self, state: dict) -> None:
        save_json(self.fixture.runner_state, state)

    def run(self, argv, *, cwd=None, env=None, user=None):
        args = list(argv)
        state = self._state()
        state["log"].append({"argv": args, "cwd": str(cwd) if cwd else None, "user": user.name if user else None})
        fail = state.get("fail_once")
        if fail and " ".join(args).startswith(fail):
            state["fail_once"] = None
            self._save(state)
            return CommandResult(1, "", "fixture failure")
        command = args[0]
        if command == "/usr/bin/uname":
            result = CommandResult(0, state["architecture"] + "\n")
        elif command == "/usr/bin/pacman":
            result = self._pacman(args, state)
        elif command == "/usr/bin/systemctl":
            result = self._systemctl(args, state)
        elif command == "/usr/bin/flatpak":
            result = self._flatpak(args, state)
        elif command.endswith("/install/configure-flatpak"):
            if state.get("flatpak_helper_failure"):
                if state.get("flatpak_failure_after_add"):
                    state["flathub"] = MODULE.FLATHUB_URL
                result = CommandResult(1, "", "fixture flatpak failure")
            elif state["flathub"] is None:
                state["flathub"] = MODULE.FLATHUB_URL
                result = CommandResult(0, "configured system Flathub remote\n")
            elif state["flathub"] == MODULE.FLATHUB_URL:
                result = CommandResult(0, "system Flathub remote is already configured\n")
            else:
                result = CommandResult(1, "", "unexpected URL")
        elif command == "/usr/bin/git":
            result = self._git(args, state, cwd, user)
        elif command == "/usr/bin/makepkg":
            result = self._makepkg(args, state, Path(cwd), user)
        elif command == "/usr/bin/bsdtar":
            package_name = Path(args[2]).name
            metadata = state.get("built_metadata", state.get("built_metadata_by_file", {}).get(package_name))
            if metadata is None:
                if package_name.startswith("yay-debug-"):
                    metadata = "pkgname = yay-debug\npkgbase = yay\nxdata = pkgtype=debug\narch = x86_64\n"
                elif package_name.startswith("yay-"):
                    metadata = "pkgname = yay\npkgbase = yay\nxdata = pkgtype=pkg\narch = x86_64\n"
                else:
                    metadata = "pkgname = unexpected\npkgbase = unexpected\nxdata = pkgtype=pkg\narch = x86_64\n"
            result = CommandResult(0, metadata)
        else:
            raise AssertionError(f"real/unexpected command boundary reached: {args}")
        self._save(state)
        return result

    def _pacman(self, args: list[str], state: dict) -> CommandResult:
        installed = set(state["installed"])
        if args == ["/usr/bin/pacman", "-Qq"]:
            return CommandResult(0, "".join(f"{name}\n" for name in sorted(installed)))
        if args == ["/usr/bin/pacman", "-Qu"]:
            pending = state["pending"]
            return CommandResult(0 if pending else 1, "".join(f"{value}\n" for value in pending))
        if (args[1:3] == ["-Sp", "--print-format"]
                and args[3] in {"%n", "%n|%H|%R"}
                and args[4:6] == ["--needed", "--"]):
            requested = args[6:]
            missing = [name for name in requested if name not in state["official"]]
            if missing:
                return CommandResult(1, "", "target not found: " + ",".join(missing))
            resolved = [*requested, *state.get("transaction_extra", [])]
            if args[3] == "%n":
                return CommandResult(0, "".join(f"{name}\n" for name in resolved))
            conflicts = state.get("transaction_conflicts", {})
            replaces = state.get("transaction_replaces", {})
            return CommandResult(0, "".join(
                f"{name}|{conflicts.get(name, '')}|{replaces.get(name, '')}\n"
                for name in resolved
            ))
        if args[1:5] == ["-S", "--needed", "--noconfirm", "--"]:
            if state.get("package_failure"):
                return CommandResult(1, "", "fixture package transaction failure")
            installed.update([*args[5:], *state.get("transaction_extra", [])])
            if "sddm" in args[5:]:
                state["services"]["sddm.service"] = "disabled"
            state["installed"] = sorted(installed)
            return CommandResult(0)
        if args[1:4] == ["-Q", "--", "yay"]:
            return CommandResult(0, "yay 1.0-1\n") if "yay" in installed else CommandResult(1, "", "not found")
        if args[1:4] == ["-Qm", "--", "yay"]:
            return CommandResult(0, "yay 1.0-1\n") if "yay" in state["foreign"] else CommandResult(1)
        if args[1:4] == ["-Qqo", "--", "/usr/bin/yay"]:
            return CommandResult(0, state.get("yay_executable_owner", "yay") + "\n") if "yay" in installed else CommandResult(1)
        if args[1:4] == ["-Q", "--", "bluez"]:
            return CommandResult(0, f"bluez {state['bluez_version']}\n") if "bluez" in installed else CommandResult(1)
        if args[1:4] == ["-Qo", "--", "/etc/bluetooth/main.conf"]:
            if state.get("bluez_owned", True):
                return CommandResult(0, f"/etc/bluetooth/main.conf is owned by bluez {state['bluez_version']}\n")
            return CommandResult(1)
        if args[1:4] == ["-Qii", "--", "bluez"]:
            status = "unmodified" if state["bluez_pristine"] else "modified"
            return CommandResult(0, f"Name : bluez\nVersion : {state['bluez_version']}\nBackup Files :\n/etc/bluetooth/main.conf [{status}]\n")
        if args[1:3] == ["-Si", "--"]:
            dependency = args[3]
            return CommandResult(0, f"Name : {dependency}\n") if dependency in state["official"] else CommandResult(1)
        if args[1:4] == ["-U", "--noconfirm", "--"]:
            installed.add("yay")
            state["installed"] = sorted(installed)
            state["foreign"] = sorted(set(state["foreign"]) | {"yay"})
            executable = self.fixture.root / "usr/bin/yay"
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            return CommandResult(0)
        raise AssertionError(f"unexpected fake pacman argv: {args}")

    def _systemctl(self, args: list[str], state: dict) -> CommandResult:
        if args[1:] == ["get-default"]:
            return CommandResult(0, state["default_target"] + "\n")
        if args[1:3] == ["is-enabled", "--"]:
            value = state["services"].get(args[3], "not-found")
            return CommandResult(0 if value == "enabled" else 1, value + "\n")
        if args[1] in {"enable", "disable"} and args[2] == "--":
            unit = args[3]
            state["services"][unit] = "enabled" if args[1] == "enable" else "disabled"
            alias = self.fixture.root / MODULE.DISPLAY_MANAGER_ALIAS.lstrip("/")
            if unit == "sddm.service":
                if args[1] == "enable":
                    alias.parent.mkdir(parents=True, exist_ok=True)
                    if alias.exists() or alias.is_symlink():
                        alias.unlink()
                    alias.symlink_to(MODULE.SDDM_UNIT_TARGET)
                elif alias.is_symlink() and os.readlink(alias) == MODULE.SDDM_UNIT_TARGET:
                    alias.unlink()
            return CommandResult(0)
        raise AssertionError(f"unexpected fake systemctl argv: {args}")

    def _flatpak(self, args: list[str], state: dict) -> CommandResult:
        if args[1:] != ["remotes", "--system", "--columns=name,url"]:
            raise AssertionError(f"unexpected fake flatpak argv: {args}")
        if state.get("flatpak_inspect_failure"):
            return CommandResult(1, "", "fixture failure")
        if state["flathub"] is None:
            return CommandResult(0)
        if isinstance(state["flathub"], list):
            return CommandResult(0, "".join(f"flathub\t{url}\n" for url in state["flathub"]))
        return CommandResult(0, f"flathub\t{state['flathub']}\n")

    def _git(self, args: list[str], state: dict, cwd: Path | None, user) -> CommandResult:
        if user is None:
            raise AssertionError("git AUR operation was not delegated to target user")
        if args[1] == "clone":
            repository = Path(args[-1])
            repository.mkdir()
            (repository / "PKGBUILD").write_text("# fixture\n", encoding="utf-8")
            return CommandResult(0)
        if args[1] == "-C" and args[3:6] == ["remote", "get-url", "origin"]:
            return CommandResult(0, state["yay_origin"] + "\n")
        if args[1] == "-C" and args[3:5] == ["rev-parse", "HEAD"]:
            return CommandResult(0, state["yay_commit"] + "\n")
        raise AssertionError(f"unexpected fake git argv: {args}")

    def _makepkg(self, args: list[str], state: dict, cwd: Path, user) -> CommandResult:
        if user is None:
            raise AssertionError("makepkg was not delegated to target user")
        if args[1:] == ["--printsrcinfo"]:
            if "yay_srcinfo" in state:
                return CommandResult(0, state["yay_srcinfo"])
            pkgname = state.get("yay_pkgname", "yay")
            dependency = state.get("yay_dependency", "go")
            return CommandResult(
                0,
                f"pkgbase = yay\narch = x86_64\nmakedepends = {dependency}>=1\n"
                f"depends = pacman\npkgname = {pkgname}\n",
            )
        output_names = state.get("yay_output_files", ["yay-1.0-1-x86_64.pkg.tar.zst"])
        outputs = [Path(value) if Path(value).is_absolute() else cwd / value for value in output_names]
        if args[1:] == ["--packagelist"]:
            return CommandResult(0, "".join(f"{path}\n" for path in outputs))
        if args[1:] == ["--cleanbuild", "--clean", "--noconfirm"]:
            for output in outputs:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"fixture-yay-package")
            return CommandResult(0)
        raise AssertionError(f"unexpected fake makepkg argv: {args}")


class Fixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "root"
        for path, mode in (
            (self.root / "etc/bluetooth", 0o755),
            (self.root / "var/lib", 0o755),
            (self.root / "var/tmp", 0o1777),
            (self.root / "home/tester", 0o700),
            (self.root / "usr/bin", 0o755),
            (self.root / "usr/lib/systemd/system", 0o755),
            (self.root / "etc/systemd/system", 0o755),
        ):
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(mode)
        (self.root / "usr/lib").mkdir(parents=True, exist_ok=True)
        (self.root / "usr/lib/os-release").write_text(
            'NAME="Arch Linux"\nID=arch\n', encoding="utf-8"
        )
        self.bluez_target = self.root / "etc/bluetooth/main.conf"
        self.bluez_target.write_bytes(b"package-bluez-default\n")
        self.bluez_target.chmod(0o644)
        self.runner_state = self.base / "runner.json"
        manifest = MODULE.tomllib.loads((REPOSITORY / "packages/manifest-v1.toml").read_text())
        official = sorted(item["name"] for item in manifest["package"] if item["source"] == "official")
        defaults = sorted(item["name"] for item in manifest["package"] if item["source"] == "official" and item["default_install"] is True)
        save_json(
            self.runner_state,
            {
                "architecture": "x86_64",
                "installed": sorted(set(defaults) | {"pacman"}),
                "pending": [],
                "official": sorted(set(official) | {"go", "pacman"}),
                "foreign": [],
                "bluez_version": "5.87-2",
                "bluez_pristine": True,
                "bluez_owned": True,
                "services": {
                    "NetworkManager.service": "disabled",
                    "bluetooth.service": "disabled",
                    "sddm.service": "disabled",
                },
                "default_target": "graphical.target",
                "flathub": None,
                "yay_origin": MODULE.AUR_YAY_ORIGIN,
                "yay_commit": "a" * 40,
                "yay_dependency": "go",
                "log": [],
            },
        )
        self.user = TargetUser("tester", os.getuid(), os.getgid(), Path("/home/tester"))
        launcher = self.root / "usr/bin/start-hyprland"
        launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        launcher.chmod(0o755)

    def close(self) -> None:
        self.temporary.cleanup()

    def state(self) -> dict:
        return load_json(self.runner_state)

    def update(self, **values) -> None:
        state = self.state()
        state.update(values)
        save_json(self.runner_state, state)

    def engine(self, *, source_root: Path = REPOSITORY, target: str = "tester",
               lifecycle: str = "fresh") -> SystemIntegration:
        def resolve(name: str) -> TargetUser:
            if name != "tester":
                raise KeyError(name)
            return self.user

        return SystemIntegration(
            source_root=source_root,
            target_username=target,
            runner=FakeRunner(self),
            system_root=self.root,
            account_resolver=resolve,
            effective_uid=0,
            root_identity=(os.getuid(), os.getgid()),
            testing=True,
            lifecycle=lifecycle,
        )

    def install_existing_yay(self, *, foreign: bool = True) -> None:
        state = self.state()
        state["installed"] = sorted(set(state["installed"]) | {"yay"})
        if foreign:
            state["foreign"] = sorted(set(state["foreign"]) | {"yay"})
        save_json(self.runner_state, state)
        executable = self.root / "usr/bin/yay"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)

    def set_display_manager_alias(self, target: str) -> None:
        alias = self.root / MODULE.DISPLAY_MANAGER_ALIAS.lstrip("/")
        if alias.exists() or alias.is_symlink():
            alias.unlink()
        alias.symlink_to(target)

    def adopt_everything(self) -> SystemIntegration:
        engine = self.engine()
        engine.apply()
        return engine


class IntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_terminal_fallback_plan_apply_validate_and_preserve(self) -> None:
        engine = self.fixture.engine()
        target = self.fixture.root / MODULE.TERMINAL_FALLBACK_PATH.lstrip("/")
        self.assertEqual(engine._terminal_fallback_status().action, "terminal-fallback-create")
        self.assertFalse(target.exists())
        engine.apply()
        self.assertEqual(target.read_bytes(), b"foot.desktop\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        before = (target.stat().st_ino, target.stat().st_mtime_ns)
        engine.apply()
        self.assertEqual((target.stat().st_ino, target.stat().st_mtime_ns), before)
        target.unlink()
        with self.assertRaisesRegex(IntegrationError, "terminal fallback is missing"):
            engine.validate()

    def test_terminal_fallback_follows_package_and_rejects_conflicts(self) -> None:
        engine = self.fixture.engine()
        target = self.fixture.root / MODULE.TERMINAL_FALLBACK_PATH.lstrip("/")
        state = self.fixture.state()
        state["installed"].remove("xdg-terminal-exec")
        save_json(self.fixture.runner_state, state)
        original = engine._terminal_fallback_status

        def checked(*, create: bool = False):
            if create:
                self.assertIn("xdg-terminal-exec", self.fixture.state()["installed"])
            return original(create=create)

        with mock.patch.object(engine, "_terminal_fallback_status", side_effect=checked):
            engine.apply()
        self.assertTrue(target.is_file())
        target.unlink()
        target.symlink_to(self.fixture.root / "home/tester")
        self.assertIn("terminal-fallback-conflict", {item.action for item in engine.plan().items})
        with self.assertRaises(IntegrationError):
            engine.apply()
        target.unlink()
        parent = target.parent
        parent.rmdir()
        parent.write_bytes(b"not a directory")
        self.assertIn("terminal-fallback-conflict", {item.action for item in engine.plan().items})
        parent.unlink()
        parent.symlink_to(self.fixture.root / "home/tester", target_is_directory=True)
        with self.assertRaises(IntegrationError):
            engine.apply()

    def test_flatpak_export_scaffold_plan_apply_validate_and_preserve(self) -> None:
        engine = self.fixture.engine()
        destination = self.fixture.root / MODULE.FLATPAK_SYSTEM_EXPORT_PATH.lstrip("/")
        before = sorted((str(path.relative_to(self.fixture.root)), path.lstat().st_ino,
                         path.lstat().st_mtime_ns) for path in self.fixture.root.rglob("*"))
        self.assertEqual(engine._flatpak_exports_status().action, "flatpak-exports-create")
        self.assertIn("flatpak-exports-create", {item.action for item in engine.plan().items})
        self.assertEqual(before, sorted((str(path.relative_to(self.fixture.root)), path.lstat().st_ino,
                                         path.lstat().st_mtime_ns) for path in self.fixture.root.rglob("*")))
        engine._ensure_flatpak_exports()
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o755)
        self.assertEqual((destination.stat().st_uid, destination.stat().st_gid),
                         (engine.root_uid, engine.root_gid))
        exported = destination / "org.example.App.desktop"
        exported.write_bytes(b"[Desktop Entry]\nName=Example\n")
        link = destination / "org.example.Link.desktop"
        link.symlink_to(exported.name)
        saved = [(path.lstat().st_ino, path.lstat().st_mtime_ns, path.lstat().st_mode)
                 for path in (destination, exported, link)]
        engine._ensure_flatpak_exports()
        self.assertEqual(saved, [(path.lstat().st_ino, path.lstat().st_mtime_ns,
                                  path.lstat().st_mode) for path in (destination, exported, link)])
        self.assertEqual(exported.read_bytes(), b"[Desktop Entry]\nName=Example\n")
        self.assertEqual(link.readlink(), Path(exported.name))
        self.assertEqual(engine._flatpak_exports_status().action, "flatpak-exports-preserve")

    def test_flatpak_export_scaffold_is_required_for_full_validation(self) -> None:
        engine = self.fixture.adopt_everything()
        destination = self.fixture.root / MODULE.FLATPAK_SYSTEM_EXPORT_PATH.lstrip("/")
        destination.rmdir()
        with self.assertRaisesRegex(IntegrationError, "scaffolding"):
            engine.validate()

    def test_flatpak_export_scaffold_follows_package_install_before_sddm(self) -> None:
        engine = self.fixture.adopt_everything()
        destination = self.fixture.root / MODULE.FLATPAK_SYSTEM_EXPORT_PATH.lstrip("/")
        destination.rmdir()
        state = self.fixture.state()
        state["installed"].remove("flatpak")
        save_json(self.fixture.runner_state, state)
        calls: list[str] = []
        original_exports = engine._ensure_flatpak_exports
        original_sddm = engine._apply_sddm_login

        def ensure_exports() -> None:
            self.assertIn("flatpak", self.fixture.state()["installed"])
            self.assertEqual(engine._flatpak_status().action, "flathub-preserve")
            calls.append("exports")
            original_exports()

        def apply_sddm() -> None:
            self.assertTrue(destination.is_dir())
            calls.append("sddm")
            original_sddm()

        with mock.patch.object(engine, "_ensure_flatpak_exports", side_effect=ensure_exports), \
                mock.patch.object(engine, "_apply_sddm_login", side_effect=apply_sddm):
            engine.apply()
        self.assertEqual(calls, ["exports", "sddm"])

    def test_flatpak_export_scaffold_requires_package_and_rejects_unsafe_paths(self) -> None:
        engine = self.fixture.engine()
        destination = self.fixture.root / MODULE.FLATPAK_SYSTEM_EXPORT_PATH.lstrip("/")
        state = self.fixture.state()
        state["installed"].remove("flatpak")
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "must be installed"):
            engine._ensure_flatpak_exports()
        self.assertFalse(destination.exists())
        state["installed"].append("flatpak")
        save_json(self.fixture.runner_state, state)
        parent = destination.parent
        parent.mkdir(parents=True)
        destination.symlink_to(self.fixture.root / "home/tester")
        self.assertEqual(engine._flatpak_exports_status().action, "flatpak-exports-conflict")
        with self.assertRaises(IntegrationError):
            engine._ensure_flatpak_exports()
        destination.unlink()
        destination.write_text("not a directory")
        with self.assertRaises(IntegrationError):
            engine._ensure_flatpak_exports()
        destination.unlink()
        parent.rmdir()
        parent.write_text("not a directory")
        with self.assertRaises(IntegrationError):
            engine._ensure_flatpak_exports()
        parent.unlink()
        parent.symlink_to(self.fixture.root / "home/tester")
        with self.assertRaises(IntegrationError):
            engine._ensure_flatpak_exports()
        parent.unlink()
        engine.root_uid += 1
        self.assertEqual(engine._flatpak_exports_status().action, "flatpak-exports-conflict")

    def test_manifest_drives_default_and_excluded_packages(self) -> None:
        engine = self.fixture.engine()
        self.assertIn("pavucontrol", engine.official_default_packages)
        self.assertIn("bluez-utils", engine.official_default_packages)
        self.assertIn("base-devel", engine.official_default_packages)
        self.assertIn("git", engine.official_default_packages)
        self.assertEqual(engine.recommended_default_packages, ("bluez-utils", "pavucontrol"))
        self.assertTrue({"cups", "cups-pk-helper", "system-config-printer", "avahi", "gnupg", "wtype"}.isdisjoint(engine.official_default_packages))

    def test_plan_reports_missing_and_preserved_packages(self) -> None:
        state = self.fixture.state()
        state["installed"].remove("dunst")
        save_json(self.fixture.runner_state, state)
        actions = {(item.action, item.subject) for item in self.fixture.engine().plan().items}
        self.assertIn(("package-install", "dunst"), actions)
        self.assertIn(("package-preserve", "mpv"), actions)
        self.assertIn(("aur-bootstrap", "yay"), actions)

    def test_full_rerun_installs_new_default_applications(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        state["installed"] = sorted(set(state["installed"]) - {"bazaar", "gnome-text-editor"})
        save_json(self.fixture.runner_state, state)

        plan = engine.plan()
        install_items = {item.subject for item in plan.items if item.action == "package-install"}
        self.assertEqual(install_items, {"bazaar", "gnome-text-editor"})

        before = len(self.fixture.state()["log"])
        engine.apply()
        transactions = [
            entry["argv"]
            for entry in self.fixture.state()["log"][before:]
            if entry["argv"][:5] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--"]
        ]
        self.assertEqual(len(transactions), 1)
        self.assertEqual(set(transactions[0][5:]), {"bazaar", "gnome-text-editor"})
        self.assertTrue({"bazaar", "gnome-text-editor"} <= set(self.fixture.state()["installed"]))
        self.assertFalse(engine.plan().changes)

    def test_smb_backend_plan_install_validate_and_preserve(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        state["installed"].remove("gvfs-smb")
        save_json(self.fixture.runner_state, state)

        plan = engine.plan()
        self.assertFalse(plan.blockers)
        self.assertEqual(
            {item.subject for item in plan.items if item.action == "package-install"},
            {"gvfs-smb"},
        )
        self.assertIn(("package-preserve", "gvfs"),
                      {(item.action, item.subject) for item in plan.items})
        with self.assertRaisesRegex(IntegrationError, "gvfs-smb"):
            engine.validate()

        before = len(self.fixture.state()["log"])
        engine.apply()
        transactions = [entry["argv"] for entry in self.fixture.state()["log"][before:]
                        if entry["argv"][:5] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--"]]
        self.assertEqual(transactions,
                         [["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--", "gvfs-smb"]])
        self.assertFalse(engine.validate().blockers)
        self.assertFalse(engine.plan().changes)

    def test_mtp_backend_plan_install_validate_and_preserve(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        state["installed"].remove("gvfs-mtp")
        save_json(self.fixture.runner_state, state)

        plan = engine.plan()
        self.assertFalse(plan.blockers)
        self.assertEqual(
            {item.subject for item in plan.items if item.action == "package-install"},
            {"gvfs-mtp"},
        )
        self.assertIn(("package-preserve", "gvfs"),
                      {(item.action, item.subject) for item in plan.items})
        with self.assertRaisesRegex(IntegrationError, "gvfs-mtp"):
            engine.validate()

        before = len(self.fixture.state()["log"])
        engine.apply()
        commands = [entry["argv"] for entry in self.fixture.state()["log"][before:]]
        transactions = [argv for argv in commands
                        if argv[:5] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--"]]
        self.assertEqual(transactions,
                         [["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--", "gvfs-mtp"]])
        self.assertFalse(any("gvfs-mtp-volume-monitor.service" in argv for argv in commands))
        self.assertFalse(engine.validate().blockers)
        self.assertFalse(engine.plan().changes)

    def test_dex_plan_install_validate_and_preserve(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        state["installed"].remove("dex")
        save_json(self.fixture.runner_state, state)
        self.assertEqual(
            {item.subject for item in engine.plan().items if item.action == "package-install"},
            {"dex"},
        )
        with self.assertRaisesRegex(IntegrationError, "dex"):
            engine.validate()
        before = len(self.fixture.state()["log"])
        engine.apply()
        transactions = [entry["argv"] for entry in self.fixture.state()["log"][before:]
                        if entry["argv"][:5] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--"]]
        self.assertEqual(transactions,
                         [["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--", "dex"]])
        self.assertFalse(engine.validate().blockers)
        self.assertFalse(engine.plan().changes)

    def test_plan_is_zero_write_to_system_root(self) -> None:
        def snapshot() -> list[tuple[str, int, int, str]]:
            result = []
            for path in self.fixture.root.rglob("*"):
                details = path.lstat()
                digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
                result.append((str(path.relative_to(self.fixture.root)), details.st_mode, details.st_mtime_ns, digest))
            return sorted(result)
        before = snapshot()
        self.fixture.engine().plan()
        self.assertEqual(before, snapshot())
        self.assertFalse((self.fixture.root / "var/lib/vanhyprarch").exists())

    def test_pending_upgrades_block_apply_without_package_mutation(self) -> None:
        self.fixture.update(pending=["linux 1 -> 2"])
        plan = self.fixture.engine().plan()
        self.assertTrue(any(item.action == "prerequisite-block" for item in plan.items))
        with self.assertRaisesRegex(IntegrationError, "pacman -Syu"):
            self.fixture.engine().apply()
        self.assertFalse(any(entry["argv"][1:2] == ["-S"] for entry in self.fixture.state()["log"]))

    def test_wrong_architecture_and_non_arch_base_block(self) -> None:
        self.fixture.update(architecture="aarch64")
        with self.assertRaisesRegex(IntegrationError, "unsupported architecture"):
            self.fixture.engine().plan()
        self.fixture.update(architecture="x86_64")
        (self.fixture.root / "usr/lib/os-release").write_text("ID=other\n", encoding="utf-8")
        with self.assertRaisesRegex(IntegrationError, "requires Arch Linux"):
            self.fixture.engine().plan()

    def test_arch_identity_requires_safe_authoritative_os_release(self) -> None:
        release = self.fixture.root / "usr/lib/os-release"
        legacy = self.fixture.root / "etc/arch-release"
        legacy.write_text("", encoding="utf-8")

        release.write_text("ID=arch\n", encoding="utf-8")
        self.fixture.engine()._base_preflight()
        release.write_text('NAME="Arch Linux"\nID="arch"\n', encoding="utf-8")
        self.fixture.engine()._base_preflight()

        release.write_text("ID=other\n", encoding="utf-8")
        with self.assertRaisesRegex(IntegrationError, "requires Arch Linux"):
            self.fixture.engine()._base_preflight()

        release.unlink()
        with self.assertRaisesRegex(IntegrationError, "requires Arch Linux"):
            self.fixture.engine()._base_preflight()

        outside = self.fixture.root / "unsafe-os-release-target"
        outside.write_text("ID=arch\n", encoding="utf-8")
        release.symlink_to(outside)
        with self.assertRaisesRegex(IntegrationError, "requires Arch Linux"):
            self.fixture.engine()._base_preflight()

        self.assertEqual(legacy.read_bytes(), b"")

    def test_unusable_sync_database_blocks_preflight(self) -> None:
        state = self.fixture.state()
        state["official"].remove("pacman")
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "sync databases"):
            self.fixture.engine().plan()

    def test_official_package_failure_is_not_rolled_back(self) -> None:
        state = self.fixture.state()
        state["installed"].remove("dunst")
        state["package_failure"] = True
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "package transaction failed"):
            self.fixture.engine().apply()

    def test_package_apply_and_second_apply_use_no_sync_refresh(self) -> None:
        state = self.fixture.state()
        state["installed"].remove("dunst")
        save_json(self.fixture.runner_state, state)
        engine = self.fixture.adopt_everything()
        first_log = list(self.fixture.state()["log"])
        engine.apply()
        second_log = self.fixture.state()["log"][len(first_log):]
        self.assertFalse(any(entry["argv"][1:2] in (["-S"], ["-U"]) for entry in second_log))
        for entry in self.fixture.state()["log"]:
            self.assertNotIn("-Sy", entry["argv"])
            self.assertNotIn("-Syu", entry["argv"])

    def test_official_transaction_is_exactly_manifest_default_set(self) -> None:
        state = self.fixture.state()
        state["installed"] = []
        save_json(self.fixture.runner_state, state)
        engine = self.fixture.adopt_everything()
        package_transactions = [
            entry["argv"]
            for entry in self.fixture.state()["log"]
            if entry["argv"][:5] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--"]
        ]
        self.assertGreaterEqual(len(package_transactions), 1)
        self.assertEqual(set(package_transactions[0][5:]), set(engine.official_default_packages))
        self.assertTrue({"cups", "cups-pk-helper", "system-config-printer", "avahi", "p7zip"}.isdisjoint(package_transactions[0][5:]))

    def test_yay_build_is_non_root_metadata_driven_and_records_commit(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        delegated = [entry for entry in state["log"] if entry["argv"][0] in {"/usr/bin/git", "/usr/bin/makepkg"}]
        self.assertTrue(delegated)
        self.assertEqual({entry["user"] for entry in delegated}, {"tester"})
        self.assertIn("go", state["installed"])
        root_state = load_json(self.fixture.root / MODULE.STATE_FILE.lstrip("/"))
        self.assertEqual(root_state["yay"]["source_commit"], "a" * 40)
        self.assertEqual(root_state["yay"]["source_origin"], MODULE.AUR_YAY_ORIGIN)
        self.assertFalse(any((self.fixture.root / "var/tmp").iterdir()))
        self.assertEqual(engine._yay_status(set(state["installed"])).action, "aur-preserve")

    def test_current_real_yay_srcinfo_preserves_repeated_architectures(self) -> None:
        source = REPOSITORY / "tests/fixtures/yay-cb43f848.srcinfo"
        pkgbase, packages, architectures, dependencies = self.fixture.engine()._parse_srcinfo(
            source.read_text(encoding="utf-8")
        )
        self.assertEqual(pkgbase, "yay")
        self.assertEqual(packages, ("yay",))
        self.assertEqual(
            architectures,
            ("i686", "pentium4", "x86_64", "arm", "armv7h", "armv6h", "aarch64", "riscv64"),
        )
        self.assertEqual(dependencies, ("git", "go", "pacman"))

    def test_current_real_yay_srcinfo_completes_bootstrap(self) -> None:
        source = REPOSITORY / "tests/fixtures/yay-cb43f848.srcinfo"
        self.fixture.update(yay_srcinfo=source.read_text(encoding="utf-8"))
        self.fixture.engine()._bootstrap_yay()
        state = self.fixture.state()
        self.assertIn("yay", state["installed"])
        self.assertIn("go", state["installed"])

    def test_srcinfo_architecture_compatibility_is_strict(self) -> None:
        parser = self.fixture.engine()._parse_srcinfo

        for architecture in ("x86_64", "any"):
            with self.subTest(architecture=architecture):
                _base, _packages, architectures, _dependencies = parser(
                    f"pkgbase = yay\narch = {architecture}\npkgname = yay\n"
                )
                self.assertEqual(architectures, (architecture,))

        rejected = {
            "excluded": "pkgbase = yay\narch = aarch64\npkgname = yay\n",
            "mixed-any": "pkgbase = yay\narch = any\narch = x86_64\npkgname = yay\n",
            "missing": "pkgbase = yay\npkgname = yay\n",
            "duplicate": "pkgbase = yay\narch = x86_64\narch = x86_64\npkgname = yay\n",
        }
        for case, srcinfo in rejected.items():
            with self.subTest(case=case), self.assertRaisesRegex(IntegrationError, "architecture"):
                parser(srcinfo)

    def test_srcinfo_pkgname_arch_and_dependency_overrides_are_effective(self) -> None:
        _base, _packages, architectures, dependencies = self.fixture.engine()._parse_srcinfo(
            "pkgbase = yay\n"
            "arch = aarch64\n"
            "depends = inherited\n"
            "makedepends = builder\n"
            "makedepends_x86_64 = native-builder\n"
            "makedepends_aarch64 = foreign-builder\n"
            "pkgname = yay\n"
            "arch = x86_64\n"
            "depends = selected\n"
            "depends_x86_64 = selected-native\n"
            "depends_aarch64 = selected-foreign\n"
        )
        self.assertEqual(architectures, ("x86_64",))
        self.assertEqual(dependencies, ("builder", "native-builder", "selected", "selected-native"))

        _base, _packages, _architectures, extended = self.fixture.engine()._parse_srcinfo(
            "pkgbase = yay\n"
            "arch = x86_64\n"
            "depends = inherited\n"
            "pkgname = yay\n"
            "depends = inherited\n"
            "depends = extended\n"
        )
        self.assertEqual(extended, ("extended", "inherited"))

    def test_partial_official_package_apply_resumes_without_reinstall(self) -> None:
        state = self.fixture.state()
        state["installed"] = sorted(set(state["installed"]) | {"go"})
        save_json(self.fixture.runner_state, state)
        engine = self.fixture.engine()
        plan = engine.plan()
        self.assertTrue(
            all(
                item.action == "package-preserve"
                for item in plan.items
                if item.subject in engine.official_default_packages
            )
        )
        self.assertIn(("aur-bootstrap", "yay"), {(item.action, item.subject) for item in plan.items})

        before = len(self.fixture.state()["log"])
        engine.apply()
        transactions = [
            entry["argv"][5:]
            for entry in self.fixture.state()["log"][before:]
            if entry["argv"][:5] == ["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--"]
        ]
        self.assertEqual(transactions, [])
        self.assertFalse(engine.validate().blockers)

    def test_existing_valid_yay_is_preserved_without_build(self) -> None:
        self.fixture.install_existing_yay()
        engine = self.fixture.engine()
        self.assertEqual(engine._yay_status(set(self.fixture.state()["installed"])).action, "aur-preserve")
        engine._bootstrap_yay()
        self.assertFalse(any(entry["argv"][0] == "/usr/bin/makepkg" for entry in self.fixture.state()["log"]))

    def test_installed_nonforeign_yay_conflicts(self) -> None:
        self.fixture.install_existing_yay(foreign=False)
        status = self.fixture.engine()._yay_status(set(self.fixture.state()["installed"]))
        self.assertEqual(status.action, "conflict")

    def test_root_and_unknown_target_users_are_rejected(self) -> None:
        with self.assertRaisesRegex(IntegrationError, "non-root"):
            SystemIntegration(source_root=REPOSITORY, target_username="root", testing=True)
        with self.assertRaisesRegex(IntegrationError, "does not exist"):
            self.fixture.engine(target="missing")

    def test_full_plan_apply_and_validate_require_root(self) -> None:
        def resolve(_name: str) -> TargetUser:
            return self.fixture.user
        engine = SystemIntegration(
            source_root=REPOSITORY,
            target_username="tester",
            runner=FakeRunner(self.fixture),
            system_root=self.fixture.root,
            account_resolver=resolve,
            effective_uid=1234,
            root_identity=(os.getuid(), os.getgid()),
            testing=True,
        )
        for operation in (engine.plan, engine.apply, engine.validate):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(
                IntegrationError, "requires root privileges"
            ):
                operation()
        self.assertEqual(self.fixture.state()["log"], [])
        self.assertFalse((self.fixture.root / MODULE.STATE_DIRECTORY.lstrip("/")).exists())

    def test_subprocess_runner_uses_runuser_argv_without_shell(self) -> None:
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as invoked:
            MODULE.SubprocessRunner().run(
                ["/usr/bin/git", "rev-parse", "HEAD"],
                cwd=Path("/tmp"),
                user=self.fixture.user,
            )
        command = invoked.call_args.args[0]
        self.assertEqual(command[:4], ["/usr/bin/runuser", "--user", "tester", "--"])
        self.assertNotIn("shell", invoked.call_args.kwargs)
        self.assertEqual(command[-3:], ["/usr/bin/git", "rev-parse", "HEAD"])

    def test_unsafe_target_home_is_rejected(self) -> None:
        (self.fixture.root / "home/tester").chmod(0o777)
        with self.assertRaisesRegex(IntegrationError, "group/world writable"):
            self.fixture.engine()

    def test_unexpected_yay_origin_is_rejected_and_private_tree_removed(self) -> None:
        self.fixture.update(yay_origin="https://example.invalid/yay.git")
        with self.assertRaisesRegex(IntegrationError, "unexpected yay AUR origin"):
            self.fixture.engine()._bootstrap_yay()
        self.assertFalse(any((self.fixture.root / "var/tmp").iterdir()))

    def test_unexpected_yay_package_identity_is_rejected(self) -> None:
        self.fixture.update(yay_pkgname="other")
        with self.assertRaisesRegex(IntegrationError, "unexpected pkgbase/package"):
            self.fixture.engine()._bootstrap_yay()

    def test_nonofficial_yay_dependency_is_rejected(self) -> None:
        self.fixture.update(yay_dependency="aur-only-dependency")
        with self.assertRaisesRegex(IntegrationError, "non-official dependencies"):
            self.fixture.engine()._bootstrap_yay()

    def test_built_package_metadata_must_identify_yay(self) -> None:
        self.fixture.update(
            built_metadata="pkgname = other\npkgbase = yay\nxdata = pkgtype=pkg\narch = x86_64\n"
        )
        with self.assertRaisesRegex(IntegrationError, "unexpected package output"):
            self.fixture.engine()._bootstrap_yay()

    def test_built_package_architecture_is_checked_separately(self) -> None:
        self.fixture.update(
            built_metadata="pkgname = yay\npkgbase = yay\nxdata = pkgtype=pkg\narch = any\n"
        )
        self.fixture.engine()._bootstrap_yay()

        incompatible = Fixture()
        try:
            incompatible.update(
                built_metadata="pkgname = yay\npkgbase = yay\nxdata = pkgtype=pkg\narch = aarch64\n"
            )
            with self.assertRaisesRegex(IntegrationError, "incompatible architecture"):
                incompatible.engine()._bootstrap_yay()
        finally:
            incompatible.close()

    def test_makepkg_debug_output_fixture_selects_only_primary_regardless_of_order(self) -> None:
        fixture_directory = REPOSITORY / "tests/fixtures/yay-debug-output"
        output_names = fixture_directory.joinpath("packagelist.txt").read_text(encoding="utf-8").splitlines()
        metadata = {
            output_names[0]: fixture_directory.joinpath("yay.PKGINFO").read_text(encoding="utf-8"),
            output_names[1]: fixture_directory.joinpath("yay-debug.PKGINFO").read_text(encoding="utf-8"),
        }
        for names in (output_names, list(reversed(output_names))):
            with self.subTest(order=names):
                fixture = Fixture()
                try:
                    fixture.update(yay_output_files=names, built_metadata_by_file=metadata)
                    fixture.engine()._bootstrap_yay()
                    installs = [
                        entry["argv"]
                        for entry in fixture.state()["log"]
                        if entry["argv"][0:4] == ["/usr/bin/pacman", "-U", "--noconfirm", "--"]
                    ]
                    self.assertEqual(len(installs), 1)
                    self.assertEqual(Path(installs[0][4]).name, output_names[0])
                    self.assertFalse(any((fixture.root / "var/tmp").iterdir()))
                finally:
                    fixture.close()

    @unittest.skipUnless(shutil.which("makepkg"), "makepkg is unavailable")
    def test_real_makepkg_packagelist_includes_debug_companion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            root.joinpath("PKGBUILD").write_text(
                "pkgname=vanhyprarch-output-fixture\n"
                "pkgver=1\n"
                "pkgrel=1\n"
                "arch=('x86_64')\n"
                "options=('strip' 'debug')\n"
                "package() { :; }\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                ["/usr/bin/makepkg", "--packagelist"],
                cwd=root,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                [Path(line).name for line in completed.stdout.splitlines()],
                [
                    "vanhyprarch-output-fixture-1-1-x86_64.pkg.tar.zst",
                    "vanhyprarch-output-fixture-debug-1-1-x86_64.pkg.tar.zst",
                ],
            )

    def test_unexpected_extra_and_duplicate_primary_outputs_fail_closed(self) -> None:
        primary = "yay-1.0-1-x86_64.pkg.tar.zst"
        unrelated = "unrelated-1.0-1-x86_64.pkg.tar.zst"
        self.fixture.update(yay_output_files=[primary, unrelated])
        with self.assertRaisesRegex(IntegrationError, "unexpected package output"):
            self.fixture.engine()._bootstrap_yay()
        self.assertFalse(any((self.fixture.root / "var/tmp").iterdir()))

        duplicate = Fixture()
        try:
            second = "second-primary-1.0-1-x86_64.pkg.tar.zst"
            primary_metadata = "pkgname = yay\npkgbase = yay\nxdata = pkgtype=pkg\narch = x86_64\n"
            duplicate.update(
                yay_output_files=[primary, second],
                built_metadata_by_file={primary: primary_metadata, second: primary_metadata},
            )
            with self.assertRaisesRegex(IntegrationError, "exactly one primary"):
                duplicate.engine()._bootstrap_yay()
        finally:
            duplicate.close()

    def test_debug_without_primary_and_multiple_debug_outputs_fail_closed(self) -> None:
        debug_name = "yay-debug-1.0-1-x86_64.pkg.tar.zst"
        self.fixture.update(yay_output_files=[debug_name])
        with self.assertRaisesRegex(IntegrationError, "exactly one primary"):
            self.fixture.engine()._bootstrap_yay()

        ambiguous = Fixture()
        try:
            primary = "yay-1.0-1-x86_64.pkg.tar.zst"
            second_debug = "second-debug-1.0-1-x86_64.pkg.tar.zst"
            debug_metadata = "pkgname = yay-debug\npkgbase = yay\nxdata = pkgtype=debug\narch = x86_64\n"
            ambiguous.update(
                yay_output_files=[primary, debug_name, second_debug],
                built_metadata_by_file={debug_name: debug_metadata, second_debug: debug_metadata},
            )
            with self.assertRaisesRegex(IntegrationError, "multiple ambiguous debug"):
                ambiguous.engine()._bootstrap_yay()
        finally:
            ambiguous.close()

    def test_invalid_debug_metadata_and_malformed_archive_fail_closed(self) -> None:
        primary = "yay-1.0-1-x86_64.pkg.tar.zst"
        debug_name = "yay-debug-1.0-1-x86_64.pkg.tar.zst"
        self.fixture.update(
            yay_output_files=[primary, debug_name],
            built_metadata_by_file={
                debug_name: "pkgname = yay-debug\npkgbase = yay\nxdata = pkgtype=pkg\narch = x86_64\n"
            },
        )
        with self.assertRaisesRegex(IntegrationError, "debug package output has unexpected metadata"):
            self.fixture.engine()._bootstrap_yay()

        malformed = Fixture()
        try:
            malformed.update(built_metadata="not a PKGINFO assignment")
            with self.assertRaisesRegex(IntegrationError, "malformed metadata"):
                malformed.engine()._bootstrap_yay()
        finally:
            malformed.close()

        unreadable = Fixture()
        try:
            unreadable.update(fail_once="/usr/bin/bsdtar -xOf")
            with self.assertRaisesRegex(IntegrationError, "could not inspect"):
                unreadable.engine()._bootstrap_yay()
        finally:
            unreadable.close()

    def test_duplicate_and_outside_output_paths_fail_before_build(self) -> None:
        primary = "yay-1.0-1-x86_64.pkg.tar.zst"
        self.fixture.update(yay_output_files=[primary, primary])
        with self.assertRaisesRegex(IntegrationError, "duplicate path"):
            self.fixture.engine()._bootstrap_yay()

        outside = Fixture()
        try:
            outside_path = outside.base / "outside.pkg.tar.zst"
            outside.update(yay_output_files=[str(outside_path)])
            with self.assertRaisesRegex(IntegrationError, "outside the private build tree"):
                outside.engine()._bootstrap_yay()
            self.assertFalse(outside_path.exists())
        finally:
            outside.close()

    def test_bluez_package_pristine_adoption_backup_and_preserve(self) -> None:
        engine = self.fixture.engine()
        original = self.fixture.bluez_target.read_bytes()
        engine._apply_bluez()
        candidate = (REPOSITORY / "system/etc/bluetooth/main.conf").read_bytes()
        self.assertEqual(self.fixture.bluez_target.read_bytes(), candidate)
        backup = self.fixture.root / MODULE.BLUEZ_BACKUP.lstrip("/")
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(engine._bluez_classification().action, "bluez-preserve")
        before = self.fixture.bluez_target.stat().st_mtime_ns
        engine._apply_bluez()
        self.assertEqual(before, self.fixture.bluez_target.stat().st_mtime_ns)

    def test_bluez_customized_target_conflicts(self) -> None:
        self.fixture.update(bluez_pristine=False)
        item = self.fixture.engine()._bluez_classification()
        self.assertEqual(item.action, "bluez-conflict")
        with self.assertRaises(IntegrationError):
            self.fixture.engine()._apply_bluez()

    def test_bluez_symlink_wrong_type_mode_and_owner_fail_closed(self) -> None:
        target = self.fixture.bluez_target
        target.unlink()
        target.symlink_to(self.fixture.root / "usr/lib/os-release")
        self.assertEqual(self.fixture.engine()._bluez_classification().action, "bluez-conflict")
        target.unlink()
        target.mkdir()
        self.assertEqual(self.fixture.engine()._bluez_classification().action, "bluez-conflict")
        target.rmdir()
        target.write_bytes(b"package-bluez-default\n")
        target.chmod(0o600)
        self.assertEqual(self.fixture.engine()._bluez_classification().action, "bluez-conflict")

    def test_bluez_source_symlink_is_rejected(self) -> None:
        copied = self.fixture.base / "source"
        shutil.copytree(REPOSITORY, copied, ignore=shutil.ignore_patterns(".git"))
        source = copied / "system/etc/bluetooth/main.conf"
        source.unlink()
        source.symlink_to("/etc/passwd")
        with self.assertRaisesRegex(IntegrationError, "source symlink"):
            self.fixture.engine(source_root=copied)._bluez_source()

    def test_existing_unproven_bluez_backup_is_never_overwritten(self) -> None:
        engine = self.fixture.engine()
        state_directory = self.fixture.root / MODULE.STATE_DIRECTORY.lstrip("/")
        state_directory.mkdir(mode=0o700)
        bluez_directory = state_directory / "bluez"
        bluez_directory.mkdir(mode=0o700)
        backup = self.fixture.root / MODULE.BLUEZ_BACKUP.lstrip("/")
        backup.write_bytes(b"unknown backup\n")
        backup.chmod(0o600)
        with self.assertRaisesRegex(IntegrationError, "unproven backup"):
            engine._apply_bluez()
        self.assertEqual(backup.read_bytes(), b"unknown backup\n")
        self.assertEqual(self.fixture.bluez_target.read_bytes(), b"package-bluez-default\n")

    def test_bluez_wrong_owner_identity_fails_closed(self) -> None:
        def resolve(_name: str) -> TargetUser:
            return self.fixture.user
        engine = SystemIntegration(
            source_root=REPOSITORY,
            target_username="tester",
            runner=FakeRunner(self.fixture),
            system_root=self.fixture.root,
            account_resolver=resolve,
            effective_uid=0,
            root_identity=(os.getuid() + 1, os.getgid()),
            testing=True,
        )
        self.assertEqual(engine._bluez_classification().action, "bluez-conflict")

    def test_bluez_abrupt_crash_windows_recover_idempotently(self) -> None:
        checkpoints = (
            "bluez-before-backup-commit",
            "bluez-after-backup-commit",
            "bluez-after-config-publish",
            "bluez-before-state-commit",
            "bluez-after-state-commit",
        )
        for checkpoint in checkpoints:
            with self.subTest(checkpoint=checkpoint):
                fixture = Fixture()
                try:
                    pid = os.fork()
                    if pid == 0:
                        with mock.patch.dict(os.environ, {
                            "VANHYPRARCH_SYSTEM_INTEGRATION_TESTING": "1",
                            "VANHYPRARCH_SYSTEM_INTEGRATION_FAULT_AT": checkpoint,
                        }):
                            fixture.engine()._apply_bluez()
                        os._exit(0)
                    _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 197)
                    engine = fixture.engine()
                    engine.recover()
                    engine.recover()
                    self.assertFalse((fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).exists())
                    classification = engine._bluez_classification().action
                    expected = "bluez-preserve" if checkpoint == "bluez-after-state-commit" else "bluez-adopt"
                    self.assertEqual(classification, expected)
                finally:
                    fixture.close()

    def test_interrupted_bluez_manual_drift_is_not_recovered_over(self) -> None:
        pid = os.fork()
        if pid == 0:
            with mock.patch.dict(os.environ, {
                "VANHYPRARCH_SYSTEM_INTEGRATION_TESTING": "1",
                "VANHYPRARCH_SYSTEM_INTEGRATION_FAULT_AT": "bluez-after-config-publish",
            }):
                self.fixture.engine()._apply_bluez()
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 197)
        self.fixture.bluez_target.write_bytes(b"administrator changed this\n")
        self.fixture.bluez_target.chmod(0o644)
        with self.assertRaisesRegex(IntegrationError, "does not match expected"):
            self.fixture.engine().recover()
        self.assertEqual(self.fixture.bluez_target.read_bytes(), b"administrator changed this\n")
        self.assertTrue((self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).is_file())

    def test_plan_reports_incomplete_transaction_without_recovery_write(self) -> None:
        engine = self.fixture.engine()
        state_dir = self.fixture.root / MODULE.STATE_DIRECTORY.lstrip("/")
        state_dir.mkdir(mode=0o700)
        transaction = {
            "schema": 1,
            "id": "0" * 32,
            "kind": "service-policy",
            "phase": "prepared",
            "prior": {},
            "desired": {},
        }
        path = self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")
        path.write_bytes(MODULE._json_bytes(transaction))
        path.chmod(0o600)
        before = path.read_bytes(), path.stat().st_mtime_ns
        plan = engine.plan()
        self.assertEqual(plan.items[0].action, "recovery-required")
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        with self.assertRaisesRegex(IntegrationError, "requires recovery"):
            engine.validate()

    def test_concurrent_mutation_lock_fails_closed(self) -> None:
        first = self.fixture.engine()
        second = self.fixture.engine()
        with first._mutation_lock():
            with self.assertRaisesRegex(IntegrationError, "another system integration"):
                with second._mutation_lock():
                    self.fail("second mutation lock unexpectedly succeeded")

    def test_malformed_root_state_fails_closed(self) -> None:
        directory = self.fixture.root / MODULE.STATE_DIRECTORY.lstrip("/")
        directory.mkdir(mode=0o700)
        path = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        path.write_text("{", encoding="utf-8")
        path.chmod(0o600)
        with self.assertRaisesRegex(IntegrationError, "invalid system integration state"):
            self.fixture.engine()._read_state()
        path.write_bytes(MODULE._json_bytes({"schema": 1, "bluez": []}))
        self.assertEqual(self.fixture.engine()._bluez_classification().action, "bluez-conflict")

    def test_service_policy_is_manifest_derived_and_user_units_untouched(self) -> None:
        desired = self.fixture.engine().desired_system_services
        self.assertEqual(desired, {
            "NetworkManager.service": "enabled",
            "bluetooth.service": "enabled",
            "sddm.service": "enabled",
        })
        self.assertNotIn("hypridle.service", desired)
        self.assertNotIn("vanhyprarch-monitor-safe-apply.service", desired)

    def test_fresh_plan_installs_and_enables_only_baseline_display_manager(self) -> None:
        self.assertTrue(
            (self.fixture.root / MODULE.START_HYPRLAND_PATH.lstrip("/")).is_file()
        )
        state = self.fixture.state()
        state["installed"].remove("sddm")
        state["services"]["sddm.service"] = "not-found"
        save_json(self.fixture.runner_state, state)
        engine = self.fixture.engine()
        plan = engine.plan()
        pairs = {(item.action, item.subject) for item in plan.items}
        self.assertIn(("package-install", "sddm"), pairs)
        self.assertIn(("service-enable", "sddm.service"), pairs)
        inspected_units = {
            entry["argv"][3]
            for entry in self.fixture.state()["log"]
            if entry["argv"][:3] == ["/usr/bin/systemctl", "is-enabled", "--"]
        }
        self.assertEqual(inspected_units, set(engine.desired_system_services))
        self.assertFalse(plan.blockers)
        self.assertFalse(
            any(item.subject == "runtime-prerequisite" for item in plan.items)
        )

    def test_missing_launcher_is_prospective_when_hyprland_install_is_planned(self) -> None:
        (self.fixture.root / MODULE.START_HYPRLAND_PATH.lstrip("/")).unlink()
        state = self.fixture.state()
        state["installed"].remove("hyprland")
        save_json(self.fixture.runner_state, state)

        plan = self.fixture.engine().plan()

        self.assertFalse(plan.blockers)
        self.assertIn(
            ("package-install", "hyprland"),
            {(item.action, item.subject) for item in plan.items},
        )
        prospective = [
            item
            for item in plan.items
            if item.action == "sddm-prerequisite-planned"
        ]
        self.assertEqual(len(prospective), 1)
        self.assertEqual(prospective[0].subject, "runtime-prerequisite")
        self.assertIn(
            "after the planned hyprland package installation",
            prospective[0].detail,
        )

    def test_missing_launcher_blocks_when_hyprland_install_is_not_planned(self) -> None:
        (self.fixture.root / MODULE.START_HYPRLAND_PATH.lstrip("/")).unlink()

        plan = self.fixture.engine().plan()

        self.assertNotIn(
            ("package-install", "hyprland"),
            {(item.action, item.subject) for item in plan.items},
        )
        blockers = [
            item
            for item in plan.blockers
            if item.action == "sddm-conflict"
            and item.subject == "runtime-prerequisite"
        ]
        self.assertEqual(len(blockers), 1)
        self.assertIn("start-hyprland is missing", blockers[0].detail)

    def test_apply_blocks_if_planned_hyprland_install_does_not_supply_launcher(self) -> None:
        launcher = self.fixture.root / MODULE.START_HYPRLAND_PATH.lstrip("/")
        launcher.unlink()
        state = self.fixture.state()
        state["installed"].remove("hyprland")
        save_json(self.fixture.runner_state, state)

        with self.assertRaisesRegex(IntegrationError, "start-hyprland is missing"):
            self.fixture.engine().apply()

        self.assertIn("hyprland", self.fixture.state()["installed"])
        self.assertFalse(launcher.exists())
        self.assertEqual(self.fixture.state()["services"]["sddm.service"], "disabled")
        self.assertFalse(
            (self.fixture.root / "usr/share/sddm/themes/vanhyprarch").exists()
        )

    def test_unrelated_display_manager_alias_blocks_without_replacement(self) -> None:
        state = self.fixture.state()
        state["installed"].remove("sddm")
        state["services"]["sddm.service"] = "not-found"
        save_json(self.fixture.runner_state, state)
        self.fixture.set_display_manager_alias("/usr/lib/systemd/system/gdm.service")
        plan = self.fixture.engine().plan()
        self.assertTrue(plan.blockers)
        self.assertIn("unsupported pre-existing", plan.blockers[0].detail)
        with self.assertRaisesRegex(IntegrationError, "unsupported pre-existing"):
            self.fixture.engine().apply()
        self.assertEqual(
            os.readlink(self.fixture.root / MODULE.DISPLAY_MANAGER_ALIAS.lstrip("/")),
            "/usr/lib/systemd/system/gdm.service",
        )
        self.assertNotIn("sddm", self.fixture.state()["installed"])

    def test_non_graphical_default_target_blocks_without_mutation(self) -> None:
        self.fixture.update(default_target="multi-user.target")
        plan = self.fixture.engine().plan()
        self.assertTrue(plan.blockers)
        with self.assertRaisesRegex(IntegrationError, "expected graphical.target"):
            self.fixture.engine().apply()
        self.assertFalse(any(entry["argv"][1] in {"enable", "disable"} for entry in self.fixture.state()["log"] if entry["argv"][0] == "/usr/bin/systemctl"))

    def test_payload_failure_prevents_sddm_enablement(self) -> None:
        engine = self.fixture.engine()
        with mock.patch.object(engine, "_apply_sddm_login", side_effect=IntegrationError("fixture payload failure")):
            with self.assertRaisesRegex(IntegrationError, "fixture payload failure"):
                engine.apply()
        self.assertNotEqual(self.fixture.state()["services"]["sddm.service"], "enabled")
        self.assertFalse((self.fixture.root / MODULE.DISPLAY_MANAGER_ALIAS.lstrip("/")).exists())

    def test_payload_is_complete_before_sddm_enable_and_no_process_control_occurs(self) -> None:
        engine = self.fixture.engine()
        original = engine._apply_sddm_login

        def tracked_payload() -> None:
            original()
            state = self.fixture.state()
            state["log"].append({"argv": ["phase5-payload-ready"], "cwd": None, "user": None})
            save_json(self.fixture.runner_state, state)

        with mock.patch.object(engine, "_apply_sddm_login", side_effect=tracked_payload):
            engine.apply()
        commands = [entry["argv"] for entry in self.fixture.state()["log"]]
        payload_index = commands.index(["phase5-payload-ready"])
        enable_index = commands.index(["/usr/bin/systemctl", "enable", "--", "sddm.service"])
        self.assertLess(payload_index, enable_index)
        self.assertFalse(any(command[1:2] in (["start"], ["stop"], ["restart"], ["reload"], ["try-restart"]) for command in commands if command and command[0] == "/usr/bin/systemctl"))

    def test_service_apply_mixed_state_and_second_run_noop(self) -> None:
        engine = self.fixture.engine()
        engine._apply_services()
        self.assertEqual(
            {name: self.fixture.state()["services"][name] for name in engine.desired_system_services},
            engine.desired_system_services,
        )
        first_length = len(self.fixture.state()["log"])
        engine._apply_services()
        second = self.fixture.state()["log"][first_length:]
        self.assertFalse(any(entry["argv"][1] in {"enable", "disable"} for entry in second))

    def test_service_command_failure_rolls_back_prior_states(self) -> None:
        prior = dict(self.fixture.state()["services"])
        self.fixture.update(fail_once="/usr/bin/systemctl enable -- bluetooth.service")
        with self.assertRaisesRegex(IntegrationError, "could not enable"):
            self.fixture.engine()._apply_services()
        self.assertEqual(self.fixture.state()["services"], prior)
        self.assertFalse((self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).exists())

    def test_baseline_service_failure_preserves_proven_sddm_alias(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        state["services"]["bluetooth.service"] = "disabled"
        state["fail_once"] = "/usr/bin/systemctl enable -- bluetooth.service"
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "could not enable bluetooth"):
            engine._apply_services()
        self.assertEqual(
            engine._display_manager_alias(),
            MODULE.SDDM_UNIT_TARGET,
        )
        self.assertEqual(self.fixture.state()["services"]["bluetooth.service"], "disabled")
        self.assertFalse((self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).exists())

    def test_service_abrupt_crash_windows_recover_idempotently(self) -> None:
        checkpoints = (
            "services-before-first-change",
            "services-after-one-change",
            "services-before-state-commit",
            "services-after-state-commit",
        )
        for checkpoint in checkpoints:
            with self.subTest(checkpoint=checkpoint):
                fixture = Fixture()
                try:
                    prior = dict(fixture.state()["services"])
                    pid = os.fork()
                    if pid == 0:
                        with mock.patch.dict(os.environ, {
                            "VANHYPRARCH_SYSTEM_INTEGRATION_TESTING": "1",
                            "VANHYPRARCH_SYSTEM_INTEGRATION_FAULT_AT": checkpoint,
                        }):
                            fixture.engine()._apply_services()
                        os._exit(0)
                    _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 197)
                    engine = fixture.engine()
                    engine.recover()
                    engine.recover()
                    expected = engine.desired_system_services if checkpoint == "services-after-state-commit" else {
                        name: prior[name] for name in engine.desired_system_services
                    }
                    self.assertEqual(
                        {name: fixture.state()["services"][name] for name in engine.desired_system_services},
                        expected,
                    )
                    self.assertFalse((fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).exists())
                finally:
                    fixture.close()

    def test_interrupted_service_manual_drift_fails_closed(self) -> None:
        pid = os.fork()
        if pid == 0:
            with mock.patch.dict(os.environ, {
                "VANHYPRARCH_SYSTEM_INTEGRATION_TESTING": "1",
                "VANHYPRARCH_SYSTEM_INTEGRATION_FAULT_AT": "services-after-one-change",
            }):
                self.fixture.engine()._apply_services()
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 197)
        state = self.fixture.state()
        state["services"]["sddm.service"] = "masked"
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "drifted"):
            self.fixture.engine().recover()
        self.assertEqual(self.fixture.state()["services"]["sddm.service"], "masked")
        self.assertTrue((self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).is_file())

    def test_unsupported_service_state_fails_closed(self) -> None:
        state = self.fixture.state()
        state["services"]["sddm.service"] = "masked"
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "unsupported pre-existing"):
            self.fixture.engine()._apply_services()

    def test_flatpak_absent_correct_conflict_and_idempotence(self) -> None:
        engine = self.fixture.engine()
        self.assertEqual(engine._flatpak_status().action, "flathub-add")
        engine._apply_flatpak()
        self.assertEqual(engine._flatpak_status().action, "flathub-preserve")
        before = len(self.fixture.state()["log"])
        engine._apply_flatpak()
        self.assertFalse(any(entry["argv"][0].endswith("configure-flatpak") for entry in self.fixture.state()["log"][before:]))
        self.fixture.update(flathub="https://example.invalid/repo/")
        self.assertEqual(engine._flatpak_status().action, "flathub-conflict")
        with self.assertRaises(IntegrationError):
            engine._apply_flatpak()
        self.fixture.update(flathub=[MODULE.FLATHUB_URL, MODULE.FLATHUB_URL])
        self.assertEqual(engine._flatpak_status().action, "flathub-conflict")

    def test_flatpak_failure_and_ambiguous_success_are_distinguished(self) -> None:
        self.fixture.update(flatpak_helper_failure=True)
        with self.assertRaisesRegex(IntegrationError, "helper failed"):
            self.fixture.engine()._apply_flatpak()
        self.fixture.update(flatpak_failure_after_add=True)
        with self.assertRaisesRegex(IntegrationError, "became correct"):
            self.fixture.engine()._apply_flatpak()

    def test_flatpak_inspection_failure_blocks(self) -> None:
        self.fixture.update(flatpak_inspect_failure=True)
        self.assertEqual(self.fixture.engine()._flatpak_status().action, "prerequisite-block")

    def test_full_apply_validate_and_second_apply_converge(self) -> None:
        engine = self.fixture.adopt_everything()
        first_state = (self.fixture.root / MODULE.STATE_FILE.lstrip("/")).read_bytes()
        first_bluez = self.fixture.bluez_target.read_bytes()
        plan = engine.validate()
        self.assertFalse(plan.blockers)
        before = len(self.fixture.state()["log"])
        engine.apply()
        second_log = self.fixture.state()["log"][before:]
        self.assertEqual(first_state, (self.fixture.root / MODULE.STATE_FILE.lstrip("/")).read_bytes())
        self.assertEqual(first_bluez, self.fixture.bluez_target.read_bytes())
        self.assertFalse(any(entry["argv"][1:2] in (["-S"], ["-U"]) for entry in second_log))
        self.assertFalse(any(entry["argv"][1] in {"enable", "disable"} for entry in second_log if entry["argv"][0] == "/usr/bin/systemctl"))

    def test_completed_vm_state_has_authoritative_preserve_only_root_plan(self) -> None:
        engine = self.fixture.adopt_everything()
        plan = engine.plan()
        self.assertFalse(plan.blockers)
        self.assertFalse(plan.changes)
        self.assertTrue(plan.items)
        self.assertTrue(all(item.action.endswith("-preserve") for item in plan.items))
        self.assertIn(("aur-preserve", "yay"), {(item.action, item.subject) for item in plan.items})
        self.assertEqual(
            [item.action for item in plan.items if item.action == "bluez-preserve"],
            ["bluez-preserve"],
        )
        self.assertIn(("flathub-preserve", "flathub"), {(item.action, item.subject) for item in plan.items})
        service_items = [item for item in plan.items if item.action == "service-preserve"]
        self.assertEqual(
            {item.subject for item in service_items},
            set(engine.desired_system_services),
        )

    def test_root_system_state_stays_private_without_home_mirror(self) -> None:
        self.fixture.adopt_everything()
        state_directory = self.fixture.root / MODULE.STATE_DIRECTORY.lstrip("/")
        state_file = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        backup = self.fixture.root / MODULE.BLUEZ_BACKUP.lstrip("/")
        self.assertEqual(stat.S_IMODE(state_directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(backup.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        home = self.fixture.root / "home/tester"
        self.assertEqual(
            [path for path in home.rglob("*") if "system-integration" in path.name],
            [],
        )

    def test_validate_rejects_missing_package_and_service_drift(self) -> None:
        engine = self.fixture.adopt_everything()
        state = self.fixture.state()
        state["installed"].remove("mpv")
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "missing official"):
            engine.validate()
        state = self.fixture.state()
        state["installed"].append("mpv")
        state["services"]["bluetooth.service"] = "disabled"
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "service policy mismatch"):
            engine.validate()

    def test_no_shell_commands_or_host_paths_enter_runner(self) -> None:
        self.fixture.adopt_everything()
        for entry in self.fixture.state()["log"]:
            self.assertIsInstance(entry["argv"], list)
            self.assertNotIn("shell=True", entry["argv"])
            self.assertTrue(all(
                runner_home_path_is_authorized(
                    value,
                    source_root=REPOSITORY,
                    target_home=self.fixture.user.home,
                )
                for value in entry["argv"]
            ))

    def test_runner_path_guard_distinguishes_source_from_unrelated_home(self) -> None:
        source_root = Path("/home/tester/project")
        target_home = Path("/home/vanilla")
        self.assertTrue(runner_home_path_is_authorized(
            "/home/tester/project/install/configure-flatpak",
            source_root=source_root,
            target_home=target_home,
        ))
        self.assertTrue(runner_home_path_is_authorized(
            "/home/vanilla/.cache/yay",
            source_root=source_root,
            target_home=target_home,
        ))
        self.assertFalse(runner_home_path_is_authorized(
            "/home/unrelated/.config/vanhyprarch",
            source_root=source_root,
            target_home=target_home,
        ))

    def test_manifest_command_injection_name_is_rejected(self) -> None:
        copied = self.fixture.base / "source"
        shutil.copytree(REPOSITORY, copied, ignore=shutil.ignore_patterns(".git"))
        manifest = copied / "packages/manifest-v1.toml"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace('name = "7zip"', 'name = "bad;name"', 1), encoding="utf-8")
        with self.assertRaisesRegex(IntegrationError, "unsafe package name"):
            self.fixture.engine(source_root=copied)

    def test_unsafe_var_tmp_is_rejected_before_aur_build(self) -> None:
        (self.fixture.root / "var/tmp").chmod(0o777)
        with self.assertRaisesRegex(IntegrationError, "sticky bit"):
            self.fixture.engine()._bootstrap_yay()


class UpgradeSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        self.fixture.adopt_everything()

    def tearDown(self) -> None:
        self.fixture.close()

    def upgrade(self) -> SystemIntegration:
        return self.fixture.engine(lifecycle="upgrade")

    def add_target_package(self, engine: SystemIntegration) -> None:
        original = next(item for item in engine.package_manifest["package"]
                        if item["name"] == "dunst")
        engine.package_manifest["package"].append({**original, "name": "vanilla-extra"})
        state = self.fixture.state()
        state["official"].append("vanilla-extra")
        save_json(self.fixture.runner_state, state)

    def test_existing_target_is_preserved_without_arch_or_aur_update(self) -> None:
        engine = self.upgrade()
        self.assertFalse(engine.plan().changes)
        before = len(self.fixture.state()["log"])
        engine.apply()
        commands = [entry["argv"] for entry in self.fixture.state()["log"][before:]]
        self.assertFalse(any(command[0] == "/usr/bin/pacman" and command[1] in {
            "-S", "-Sy", "-Syu", "-U", "-R"} for command in commands))
        self.assertFalse(any(command[0] in {"/usr/bin/git", "/usr/bin/makepkg"}
                             for command in commands))
        self.assertFalse(engine.validate().blockers)

    def test_new_official_package_is_installed_without_full_upgrade(self) -> None:
        engine = self.upgrade()
        self.add_target_package(engine)
        self.assertIn(("package-install", "vanilla-extra"),
                      {(item.action, item.subject) for item in engine.plan().items})
        before = len(self.fixture.state()["log"])
        engine.apply()
        commands = [entry["argv"] for entry in self.fixture.state()["log"][before:]]
        self.assertIn(["/usr/bin/pacman", "-S", "--needed", "--noconfirm", "--",
                       "vanilla-extra"], commands)
        self.assertFalse(any(command[0] == "/usr/bin/pacman" and command[1] in {
            "-Sy", "-Syu", "-R", "-U"} for command in commands))
        self.assertIn("vanilla-extra", self.fixture.state()["installed"])
        self.assertFalse(engine.validate().blockers)

    def test_new_official_package_may_pull_in_new_dependency(self) -> None:
        engine = self.upgrade()
        self.add_target_package(engine)
        self.fixture.update(transaction_extra=["vanilla-dependency"])
        self.assertFalse(engine.plan().blockers)
        engine.apply()
        self.assertIn("vanilla-extra", self.fixture.state()["installed"])
        self.assertIn("vanilla-dependency", self.fixture.state()["installed"])
        self.assertFalse(engine.validate().blockers)

    def test_pending_arch_updates_block_package_change(self) -> None:
        engine = self.upgrade()
        self.add_target_package(engine)
        self.fixture.update(pending=["pacman 7 -> 8"])
        self.assertTrue(engine.plan().blockers)
        with self.assertRaises(IntegrationError):
            engine.apply()
        self.assertNotIn("vanilla-extra", self.fixture.state()["installed"])

    def test_package_preview_refuses_any_installed_dependency_change(self) -> None:
        engine = self.upgrade()
        self.add_target_package(engine)
        self.fixture.update(transaction_extra=["pacman"])
        with self.assertRaisesRegex(IntegrationError, "would change installed packages"):
            engine.plan()
        with self.assertRaises(IntegrationError):
            engine.apply()
        self.assertNotIn("vanilla-extra", self.fixture.state()["installed"])

    def test_package_preview_refuses_installed_package_downgrade(self) -> None:
        engine = self.upgrade()
        self.add_target_package(engine)
        # The no-change policy is name-based, so it also rejects an older sync
        # version without needing to compare pacman's version strings.
        self.fixture.update(transaction_extra=["pacman"])
        with self.assertRaisesRegex(IntegrationError, "would change installed packages"):
            engine.plan()
        with self.assertRaises(IntegrationError):
            engine.apply()
        self.assertNotIn("vanilla-extra", self.fixture.state()["installed"])

    def test_package_preview_refuses_conflict_removal_and_replacement(self) -> None:
        engine = self.upgrade()
        self.add_target_package(engine)
        state = self.fixture.state()
        state["installed"].append("legacy-package")
        save_json(self.fixture.runner_state, state)
        for field in ("transaction_conflicts", "transaction_replaces"):
            with self.subTest(field=field):
                relations = {"transaction_conflicts": {}, "transaction_replaces": {}}
                relations[field] = {"vanilla-extra": "legacy-package"}
                self.fixture.update(**relations)
                with self.assertRaisesRegex(IntegrationError, "conflicts or replacements"):
                    engine.plan()
                with self.assertRaises(IntegrationError):
                    engine.apply()
                self.assertIn("legacy-package", self.fixture.state()["installed"])
                self.assertNotIn("vanilla-extra", self.fixture.state()["installed"])

    def test_missing_old_package_is_drift_and_dropped_package_is_not_removed(self) -> None:
        state = self.fixture.state()
        state["installed"].remove("dunst")
        save_json(self.fixture.runner_state, state)
        engine = self.upgrade()
        self.assertIn("previously required official package is missing",
                      [item.detail for item in engine.plan().blockers])
        with self.assertRaises(IntegrationError):
            engine.apply()
        state["installed"].append("dunst")
        save_json(self.fixture.runner_state, state)
        engine = self.upgrade()
        engine.package_manifest["package"] = [item for item in engine.package_manifest["package"]
                                              if item["name"] != "dunst"]
        before = len(self.fixture.state()["log"])
        engine.apply()
        commands = [entry["argv"] for entry in self.fixture.state()["log"][before:]]
        self.assertIn("dunst", self.fixture.state()["installed"])
        self.assertFalse(any(command[0] == "/usr/bin/pacman" and command[1] == "-R"
                             for command in commands))

    def test_missing_old_system_file_is_drift(self) -> None:
        target = self.fixture.root / MODULE.TERMINAL_FALLBACK_PATH.lstrip("/")
        target.unlink()
        engine = self.upgrade()
        self.assertIn("previously managed system file is missing",
                      [item.detail for item in engine.plan().blockers])
        with self.assertRaises(IntegrationError):
            engine.apply()
        self.assertFalse(target.exists())

    def test_new_system_file_uses_prior_inventory_and_reruns(self) -> None:
        state_path = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        state = load_json(state_path)
        state["system_artifacts"] = {}
        save_json(state_path, state)
        target = self.fixture.root / MODULE.TERMINAL_FALLBACK_PATH.lstrip("/")
        target.unlink()
        engine = self.upgrade()
        self.assertIn("terminal-fallback-create", {item.action for item in engine.plan().items})
        engine.apply()
        before = (target.stat().st_ino, target.stat().st_mtime_ns)
        engine.apply()
        self.assertEqual((target.stat().st_ino, target.stat().st_mtime_ns), before)
        self.assertIn("terminal-fallback", load_json(state_path)["system_artifacts"])

    def test_new_system_file_preexisting_or_unsafe_is_conflict(self) -> None:
        state_path = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        state = load_json(state_path)
        state["system_artifacts"] = {}
        save_json(state_path, state)
        target = self.fixture.root / MODULE.TERMINAL_FALLBACK_PATH.lstrip("/")
        engine = self.upgrade()
        self.assertIn("pre-existing system file lacks Vanilla provenance",
                      [item.detail for item in engine.plan().blockers])
        target.chmod(0o600)
        self.assertTrue(engine.plan().blockers)
        target.unlink()
        target.symlink_to(self.fixture.root / "home/tester")
        self.assertTrue(engine.plan().blockers)
        with self.assertRaises(IntegrationError):
            engine.apply()

    def test_interrupted_new_system_file_publication_resumes(self) -> None:
        state_path = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        state = load_json(state_path)
        state["system_artifacts"] = {}
        engine = self.upgrade()
        state["pending_system_artifact"] = {
            "id": "terminal-fallback", **engine._target_system_artifacts()["terminal-fallback"]
        }
        save_json(state_path, state)
        target = self.fixture.root / MODULE.TERMINAL_FALLBACK_PATH.lstrip("/")
        before = (target.stat().st_ino, target.stat().st_mtime_ns)
        self.assertFalse(engine.plan().blockers)
        engine.apply()
        self.assertEqual((target.stat().st_ino, target.stat().st_mtime_ns), before)
        self.assertIsNone(load_json(state_path)["pending_system_artifact"])

    def test_declared_service_change_does_not_touch_unrelated_unit(self) -> None:
        engine = self.upgrade()
        for item in engine.service_manifest["service"]:
            if item["name"] == "NetworkManager.service":
                item["policy"] = "disabled"
        state = self.fixture.state()
        state["services"]["unrelated.service"] = "enabled"
        save_json(self.fixture.runner_state, state)
        self.assertIn(("service-disable", "NetworkManager.service"),
                      {(item.action, item.subject) for item in engine.plan().items})
        engine.apply()
        self.assertEqual(self.fixture.state()["services"]["unrelated.service"], "enabled")
        self.assertEqual(self.fixture.state()["services"]["NetworkManager.service"], "disabled")

    def test_new_declared_service_only_enables_that_unit(self) -> None:
        engine = self.upgrade()
        engine.service_manifest["service"].append({
            "name": "vanhyprarch-new.service", "scope": "system",
            "default_install": True, "policy": "enabled",
        })
        state = self.fixture.state()
        state["services"]["vanhyprarch-new.service"] = "disabled"
        state["services"]["unrelated.service"] = "enabled"
        save_json(self.fixture.runner_state, state)
        before = len(self.fixture.state()["log"])
        engine.apply()
        commands = [entry["argv"] for entry in self.fixture.state()["log"][before:]]
        changes = [command for command in commands if command[0] == "/usr/bin/systemctl"
                   and command[1] in {"enable", "disable"}]
        self.assertEqual(changes, [["/usr/bin/systemctl", "enable", "--",
                                    "vanhyprarch-new.service"]])
        self.assertEqual(self.fixture.state()["services"]["unrelated.service"], "enabled")

    def test_old_service_policy_drift_is_conflict(self) -> None:
        state = self.fixture.state()
        state["services"]["NetworkManager.service"] = "disabled"
        save_json(self.fixture.runner_state, state)
        engine = self.upgrade()
        self.assertIn("previously managed service policy drifted",
                      [item.detail for item in engine.plan().blockers])
        with self.assertRaises(IntegrationError):
            engine.apply()

    def test_missing_upgrade_inventory_fails_closed(self) -> None:
        state_path = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        state = load_json(state_path)
        state.pop("system_artifacts")
        save_json(state_path, state)
        with self.assertRaisesRegex(IntegrationError, "prior system integration provenance"):
            self.upgrade().plan()

    def test_upgrade_rejects_dangling_transaction_and_boolean_state_schema(self) -> None:
        transaction = self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")
        transaction.symlink_to(transaction.parent / "missing-transaction")
        with self.assertRaisesRegex(IntegrationError, "safe regular file"):
            self.upgrade().plan()
        transaction.unlink()
        state_path = self.fixture.root / MODULE.STATE_FILE.lstrip("/")
        state = load_json(state_path)
        state["schema"] = True
        save_json(state_path, state)
        with self.assertRaisesRegex(IntegrationError, "unsupported system integration state schema"):
            self.upgrade().plan()


if __name__ == "__main__":
    unittest.main()
