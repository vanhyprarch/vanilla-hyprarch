#!/usr/bin/env python3
"""Deterministic DF2 Phase 4 system-integration tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
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
            metadata = state.get("built_metadata", "pkgname = yay\npkgbase = yay\narch = x86_64\n")
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
        if args[1:5] == ["-Sp", "--print-format", "%n", "--needed"]:
            requested = args[6:]
            missing = [name for name in requested if name not in state["official"]]
            if missing:
                return CommandResult(1, "", "target not found: " + ",".join(missing))
            return CommandResult(0, "".join(f"{name}\n" for name in requested))
        if args[1:5] == ["-S", "--needed", "--noconfirm", "--"]:
            if state.get("package_failure"):
                return CommandResult(1, "", "fixture package transaction failure")
            installed.update(args[5:])
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
        if args[1:3] == ["is-enabled", "--"]:
            value = state["services"].get(args[3], "not-found")
            return CommandResult(0 if value == "enabled" else 1, value + "\n")
        if args[1] in {"enable", "disable"} and args[2] == "--":
            unit = args[3]
            state["services"][unit] = "enabled" if args[1] == "enable" else "disabled"
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
            pkgname = state.get("yay_pkgname", "yay")
            dependency = state.get("yay_dependency", "go")
            return CommandResult(0, f"pkgbase = yay\npkgname = {pkgname}\narch = x86_64\nmakedepends = {dependency}>=1\ndepends = pacman\n")
        package = cwd / "yay-1.0-1-x86_64.pkg.tar.zst"
        if args[1:] == ["--packagelist"]:
            outputs = [package]
            if state.get("yay_split_output"):
                outputs.append(cwd / "yay-debug-1.0-1-x86_64.pkg.tar.zst")
            return CommandResult(0, "".join(f"{path}\n" for path in outputs))
        if args[1:] == ["--cleanbuild", "--clean", "--noconfirm"]:
            package.write_bytes(b"fixture-yay-package")
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
                "installed": defaults,
                "pending": [],
                "official": sorted(set(official) | {"go", "pacman"}),
                "foreign": [],
                "bluez_version": "5.87-2",
                "bluez_pristine": True,
                "bluez_owned": True,
                "services": {
                    "NetworkManager.service": "disabled",
                    "bluetooth.service": "disabled",
                    "ly@tty2.service": "disabled",
                    "getty@tty2.service": "enabled",
                },
                "flathub": None,
                "yay_origin": MODULE.AUR_YAY_ORIGIN,
                "yay_commit": "a" * 40,
                "yay_dependency": "go",
                "log": [],
            },
        )
        self.user = TargetUser("tester", os.getuid(), os.getgid(), Path("/home/tester"))

    def close(self) -> None:
        self.temporary.cleanup()

    def state(self) -> dict:
        return load_json(self.runner_state)

    def update(self, **values) -> None:
        state = self.state()
        state.update(values)
        save_json(self.runner_state, state)

    def engine(self, *, source_root: Path = REPOSITORY, target: str = "tester") -> SystemIntegration:
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

    def adopt_everything(self) -> SystemIntegration:
        engine = self.engine()
        engine.apply()
        return engine


class IntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

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

    def test_apply_requires_root_but_plan_does_not(self) -> None:
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
        engine.plan()
        with self.assertRaisesRegex(IntegrationError, "must run as root"):
            engine.apply()

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

    def test_unexpected_yay_package_identity_and_split_output_are_rejected(self) -> None:
        self.fixture.update(yay_pkgname="other")
        with self.assertRaisesRegex(IntegrationError, "unexpected pkgbase/package"):
            self.fixture.engine()._bootstrap_yay()
        self.fixture.update(yay_pkgname="yay", yay_split_output=True)
        with self.assertRaisesRegex(IntegrationError, "exactly one"):
            self.fixture.engine()._bootstrap_yay()

    def test_nonofficial_yay_dependency_is_rejected(self) -> None:
        self.fixture.update(yay_dependency="aur-only-dependency")
        with self.assertRaisesRegex(IntegrationError, "non-official dependencies"):
            self.fixture.engine()._bootstrap_yay()

    def test_built_package_metadata_must_identify_yay(self) -> None:
        self.fixture.update(built_metadata="pkgname = other\npkgbase = yay\narch = x86_64\n")
        with self.assertRaisesRegex(IntegrationError, "built package metadata"):
            self.fixture.engine()._bootstrap_yay()

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
        transaction = {"schema": 1, "kind": "service-policy", "phase": "prepared", "prior": {}, "desired": {}}
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
            "getty@tty2.service": "disabled",
            "ly@tty2.service": "enabled",
        })
        self.assertNotIn("hypridle.service", desired)
        self.assertNotIn("vanhyprarch-monitor-safe-apply.service", desired)

    def test_service_apply_mixed_state_and_second_run_noop(self) -> None:
        engine = self.fixture.engine()
        engine._apply_services()
        self.assertEqual(self.fixture.state()["services"], engine.desired_system_services)
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
                    expected = engine.desired_system_services if checkpoint == "services-after-state-commit" else prior
                    self.assertEqual(fixture.state()["services"], expected)
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
        state["services"]["ly@tty2.service"] = "masked"
        save_json(self.fixture.runner_state, state)
        with self.assertRaisesRegex(IntegrationError, "drifted"):
            self.fixture.engine().recover()
        self.assertEqual(self.fixture.state()["services"]["ly@tty2.service"], "masked")
        self.assertTrue((self.fixture.root / MODULE.TRANSACTION_FILE.lstrip("/")).is_file())

    def test_unsupported_service_state_fails_closed(self) -> None:
        state = self.fixture.state()
        state["services"]["ly@tty2.service"] = "masked"
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
            self.assertTrue(all(not value.startswith("/home/") or value.startswith("/home/tester") for value in entry["argv"]))

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


if __name__ == "__main__":
    unittest.main()
