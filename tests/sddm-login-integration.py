#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY / "install/sddm_login_integration.py"
SPEC = importlib.util.spec_from_file_location("sddm_login_integration", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SddmLoginIntegration = MODULE.SddmLoginIntegration
TargetUser = MODULE.TargetUser
IntegrationError = MODULE.IntegrationError
ConflictError = MODULE.ConflictError
ValidationError = MODULE.ValidationError


class SimulatedCrash(BaseException):
    pass


class Fixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.root = self.base / "root"
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.accounts = {
            "alice": TargetUser("alice", 1001, 1001),
            "alice-alias": TargetUser("alice", 1001, 1001),
            "bob": TargetUser("bob", 1002, 1002),
            "root": TargetUser("root", 0, 0),
        }
        self._copy_source()
        self._build_root()

    def cleanup(self) -> None:
        self.temporary.cleanup()

    def _copy_source(self) -> None:
        paths = (
            "deployment/ownership-v2.toml",
            "system/usr/share/sddm/themes/vanhyprarch",
            "system/usr/share/wayland-sessions/vanhyprarch.desktop",
            "system/etc/sddm.conf.d/10-vanhyprarch.conf",
            "home/.config/quickshell/vanhyprarch/assets/logo.svg",
        )
        for relative in paths:
            source = REPOSITORY / relative
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)

    def _mkdir(self, relative: str, mode: int) -> Path:
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, mode)
        return path

    def _build_root(self) -> None:
        self.root.mkdir(mode=0o700)
        self._mkdir("usr", 0o755)
        self._mkdir("usr/share", 0o755)
        self._mkdir("usr/share/sddm", 0o755)
        self._mkdir("usr/share/sddm/themes", 0o755)
        self._mkdir("usr/share/wayland-sessions", 0o755)
        self._mkdir("usr/local", 0o755)
        self._mkdir("usr/local/share", 0o755)
        self._mkdir("usr/local/share/wayland-sessions", 0o755)
        self._mkdir("usr/bin", 0o755)
        self._mkdir("etc", 0o755)
        self._mkdir("var", 0o755)
        self._mkdir("var/lib", 0o755)
        self._mkdir("var/lib/vanhyprarch", 0o700)
        launcher = self.root / "usr/bin/start-hyprland"
        launcher.write_bytes(b"#!/bin/sh\nexit 0\n")
        os.chmod(launcher, 0o755)

    def resolve(self, name: str) -> TargetUser:
        if name not in self.accounts:
            raise KeyError(name)
        return self.accounts[name]

    def integration(
        self,
        user: str = "alice",
        *,
        source: bool = True,
        release_id: str = "test-v1",
        fault_hook=None,
        effective_uid: int = 0,
    ) -> SddmLoginIntegration:
        return SddmLoginIntegration(
            source_root=self.source if source else None,
            target_username=user,
            release_id=release_id,
            system_root=self.root,
            account_resolver=self.resolve,
            effective_uid=effective_uid,
            root_identity=(self.uid, self.gid),
            testing=True,
            fault_hook=fault_hook,
        )

    def installed(self, absolute: str) -> Path:
        return self.root / absolute.removeprefix("/")


class SddmLoginIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.cleanup()

    def test_clean_plan_apply_and_independent_validate(self) -> None:
        integration = self.fixture.integration()
        plan = integration.plan()
        self.assertFalse(plan.blockers)
        self.assertFalse(self.fixture.installed(MODULE.STATE_DIRECTORY).exists())
        self.assertFalse(self.fixture.installed(MODULE.THEME_PATH).exists())
        self.assertFalse(self.fixture.installed(MODULE.SESSION_PATH).exists())
        self.assertEqual(
            [item.action for item in plan.items],
            [
                "system-create",
                "system-create",
                "system-create",
                "generated-create",
                "state-create",
            ],
        )
        integration.apply()
        validated = self.fixture.integration(source=False).validate()
        self.assertEqual(
            [item.action for item in validated.items],
            [
                "system-preserve",
                "system-preserve",
                "generated-preserve",
                "system-preserve",
                "state-preserve",
            ],
        )

        theme = self.fixture.installed(MODULE.THEME_PATH)
        self.assertEqual(
            sorted(path.name for path in theme.iterdir()),
            sorted(MODULE.THEME_INSTALLED_FILES),
        )
        self.assertFalse(any(path.is_symlink() for path in theme.iterdir()))
        self.assertEqual(stat.S_IMODE(theme.stat().st_mode), 0o755)
        for path in theme.iterdir():
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual((path.stat().st_uid, path.stat().st_gid), (self.fixture.uid, self.fixture.gid))
        state = self.fixture.installed(MODULE.STATE_DIRECTORY)
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
        provenance = self.fixture.installed(MODULE.PROVENANCE_PATH)
        self.assertEqual(stat.S_IMODE(provenance.stat().st_mode), 0o600)
        self.assertFalse(self.fixture.installed(MODULE.TRANSACTION_PATH).exists())

    def test_generated_binding_is_exact_and_contains_no_secret_or_machine_path(self) -> None:
        self.fixture.integration("alice-alias").apply()
        binding = self.fixture.installed(MODULE.BINDING_PATH).read_text(encoding="utf-8")
        self.assertEqual(
            binding,
            "[General]\n"
            "targetUser=alice\n"
            "targetSessionFile=/usr/share/wayland-sessions/vanhyprarch.desktop\n",
        )
        self.assertNotIn("password", binding.lower())
        self.assertNotIn("/home/", binding)
        self.assertNotIn(str(self.fixture.source), binding)

    def test_sddm_drop_in_is_exact_x11_policy_and_provenance_owned(self) -> None:
        self.fixture.integration().apply()
        config = self.fixture.installed(MODULE.CONFIG_PATH)
        self.assertEqual(
            config.read_text(encoding="utf-8"),
            "[General]\nDisplayServer=x11\n\n"
            "[Theme]\nCurrent=vanhyprarch\nEnableAvatars=false\n\n"
            "[Users]\nRememberLastUser=false\nRememberLastSession=false\nReuseSession=false\n",
        )
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o644)
        provenance = json.loads(
            self.fixture.installed(MODULE.PROVENANCE_PATH).read_text(encoding="utf-8")
        )
        self.assertEqual(
            provenance["artifacts"]["sddm-vanilla-config"]["target"],
            MODULE.CONFIG_PATH,
        )

    def test_unproven_or_modified_sddm_drop_in_fails_closed(self) -> None:
        config = self.fixture.installed(MODULE.CONFIG_PATH)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("[General]\nDisplayServer=wayland\n", encoding="utf-8")
        self.assertTrue(self.fixture.integration().plan().blockers)

        fixture = Fixture()
        try:
            fixture.integration().apply()
            installed = fixture.installed(MODULE.CONFIG_PATH)
            installed.write_text("[General]\nDisplayServer=wayland\n", encoding="utf-8")
            with self.assertRaises(ValidationError):
                fixture.integration(source=False).validate()
        finally:
            fixture.cleanup()

    def test_second_apply_is_substantive_noop(self) -> None:
        integration = self.fixture.integration()
        integration.apply()
        observed = {}
        for absolute in (
            MODULE.THEME_PATH,
            MODULE.BINDING_PATH,
            MODULE.SESSION_PATH,
            MODULE.CONFIG_PATH,
            MODULE.PROVENANCE_PATH,
        ):
            details = self.fixture.installed(absolute).stat()
            observed[absolute] = (details.st_ino, details.st_mtime_ns)
        second = integration.apply()
        self.assertFalse(second.changes)
        self.assertEqual(
            [item.action for item in second.items],
            [
                "system-preserve",
                "system-preserve",
                "generated-preserve",
                "system-preserve",
                "state-preserve",
            ],
        )
        for absolute, expected in observed.items():
            details = self.fixture.installed(absolute).stat()
            self.assertEqual((details.st_ino, details.st_mtime_ns), expected)
        self.fixture.integration(source=False).validate()
        for absolute, expected in observed.items():
            details = self.fixture.installed(absolute).stat()
            self.assertEqual((details.st_ino, details.st_mtime_ns), expected)

    def test_target_rebinding_fails_closed(self) -> None:
        self.fixture.integration("alice").apply()
        plan = self.fixture.integration("bob").plan()
        self.assertTrue(plan.blockers)
        self.assertIn("future migration", plan.blockers[0].detail)
        with self.assertRaises(ConflictError):
            self.fixture.integration("bob").apply()
        self.fixture.integration("alice", source=False).validate()

    def test_target_account_resolution_rejects_root_missing_and_invalid_canonical(self) -> None:
        with self.assertRaises(IntegrationError):
            self.fixture.integration("root")
        with self.assertRaises(IntegrationError):
            self.fixture.integration("missing")
        self.fixture.accounts["invalid"] = TargetUser("Bad User", 1003, 1003)
        with self.assertRaises(IntegrationError):
            self.fixture.integration("invalid")
        with self.assertRaisesRegex(IntegrationError, "release identity"):
            self.fixture.integration(release_id="/srv/releases/test-v1")

    def test_every_authoritative_operation_requires_root(self) -> None:
        integration = self.fixture.integration(effective_uid=1000)
        for operation in (integration.plan, integration.apply, integration.validate):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(IntegrationError, "requires root privileges"):
                    operation()

    def test_preexisting_unproven_targets_are_conflicts_even_when_bytes_match(self) -> None:
        cases = (
            MODULE.THEME_PATH,
            MODULE.SESSION_PATH,
        )
        for absolute in cases:
            with self.subTest(target=absolute):
                fixture = Fixture()
                try:
                    target = fixture.installed(absolute)
                    if absolute == MODULE.THEME_PATH:
                        shutil.copytree(fixture.source / MODULE.THEME_SOURCE, target)
                    else:
                        shutil.copyfile(fixture.source / MODULE.SESSION_SOURCE, target)
                    plan = fixture.integration().plan()
                    self.assertTrue(plan.blockers)
                finally:
                    fixture.cleanup()

    def test_preexisting_unproven_binding_inside_theme_conflicts(self) -> None:
        theme = self.fixture.installed(MODULE.THEME_PATH)
        shutil.copytree(self.fixture.source / MODULE.THEME_SOURCE, theme)
        (theme / "theme.conf.user").write_text("[General]\ntargetUser=alice\n", encoding="utf-8")
        plan = self.fixture.integration().plan()
        self.assertTrue(plan.blockers)
        self.assertTrue(any(item.subject == "sddm-target-binding" for item in plan.items))

    def test_absent_approved_parents_are_created_with_fixed_modes(self) -> None:
        self.fixture.installed("/usr/share/sddm/themes").rmdir()
        self.fixture.installed("/usr/share/sddm").rmdir()
        self.fixture.installed("/var/lib/vanhyprarch").rmdir()
        self.fixture.integration().apply()
        self.fixture.integration(source=False).validate()
        self.assertEqual(
            stat.S_IMODE(self.fixture.installed("/usr/share/sddm/themes").stat().st_mode),
            0o755,
        )
        self.assertEqual(
            stat.S_IMODE(self.fixture.installed("/var/lib/vanhyprarch").stat().st_mode),
            0o700,
        )

    def test_shadowing_local_session_is_a_conflict(self) -> None:
        shadow = self.fixture.installed(MODULE.SHADOW_SESSION_PATH)
        shadow.write_text("shadow\n", encoding="utf-8")
        plan = self.fixture.integration().plan()
        self.assertTrue(any(item.subject == "session-shadow" for item in plan.blockers))
        with self.assertRaises(ConflictError):
            self.fixture.integration().apply()

    def test_symlink_parent_attack_fails_closed(self) -> None:
        sddm = self.fixture.installed("/usr/share/sddm")
        themes = sddm / "themes"
        themes.rmdir()
        sddm.rmdir()
        outside = self.fixture.base / "outside"
        outside.mkdir()
        sddm.symlink_to(outside, target_is_directory=True)
        plan = self.fixture.integration().plan()
        self.assertTrue(plan.blockers)
        self.assertEqual(plan.blockers[0].subject, "path-safety")
        self.assertEqual(list(outside.iterdir()), [])

    def test_wrong_target_type_and_target_symlink_fail_closed(self) -> None:
        theme = self.fixture.installed(MODULE.THEME_PATH)
        theme.write_text("wrong type\n", encoding="utf-8")
        self.assertTrue(self.fixture.integration().plan().blockers)
        theme.unlink()
        theme.symlink_to(self.fixture.source / MODULE.THEME_SOURCE, target_is_directory=True)
        self.assertTrue(self.fixture.integration().plan().blockers)

    def test_manual_edit_and_mode_drift_are_never_silently_overwritten(self) -> None:
        self.fixture.integration().apply()
        main = self.fixture.installed(f"{MODULE.THEME_PATH}/Main.qml")
        main.write_text(main.read_text(encoding="utf-8") + "// administrator edit\n", encoding="utf-8")
        plan = self.fixture.integration().plan()
        self.assertTrue(plan.blockers)
        with self.assertRaises(ConflictError):
            self.fixture.integration().apply()

        fixture = Fixture()
        try:
            fixture.integration().apply()
            session = fixture.installed(MODULE.SESSION_PATH)
            os.chmod(session, 0o600)
            with self.assertRaises(ValidationError):
                fixture.integration(source=False).validate()
            self.assertTrue(fixture.integration().plan().blockers)
        finally:
            fixture.cleanup()

    def test_source_update_is_transactional_and_preserves_target_user(self) -> None:
        integration = self.fixture.integration(release_id="v1")
        integration.apply()
        main = self.fixture.source / MODULE.THEME_SOURCE / "Main.qml"
        main.write_text(main.read_text(encoding="utf-8") + "\n// release v2\n", encoding="utf-8")
        update = self.fixture.integration(release_id="v2")
        plan = update.plan()
        actions = {item.subject: item.action for item in plan.items}
        self.assertEqual(actions["sddm-vanilla-theme"], "system-update")
        self.assertEqual(actions["vanhyprarch-wayland-session"], "system-preserve")
        self.assertEqual(actions["sddm-target-binding"], "generated-update")
        self.assertEqual(actions["sddm-login-state"], "state-update")
        update.apply()
        self.fixture.integration(source=False).validate()
        self.assertIn("targetUser=alice\n", self.fixture.installed(MODULE.BINDING_PATH).read_text())
        state = json.loads(self.fixture.installed(MODULE.PROVENANCE_PATH).read_text())
        self.assertEqual(state["release"]["id"], "v2")

    def test_release_identity_only_update_does_not_rewrite_payload(self) -> None:
        self.fixture.integration(release_id="v1").apply()
        theme = self.fixture.installed(MODULE.THEME_PATH)
        session = self.fixture.installed(MODULE.SESSION_PATH)
        before = (theme.stat().st_ino, session.stat().st_ino)
        plan = self.fixture.integration(release_id="v2").apply()
        actions = {item.subject: item.action for item in plan.items}
        self.assertEqual(actions["sddm-vanilla-theme"], "system-preserve")
        self.assertEqual(actions["vanhyprarch-wayland-session"], "system-preserve")
        self.assertEqual(actions["sddm-login-state"], "state-update")
        self.assertEqual((theme.stat().st_ino, session.stat().st_ino), before)

    def test_validate_requires_runtime_but_not_sddm_package(self) -> None:
        self.fixture.integration().apply()
        self.assertFalse(self.fixture.installed("/usr/bin/sddm").exists())
        self.fixture.integration(source=False).validate()
        self.fixture.installed(MODULE.START_HYPRLAND_PATH).unlink()
        with self.assertRaisesRegex(ValidationError, "start-hyprland"):
            self.fixture.integration(source=False).validate()

    def test_provenance_is_private_complete_and_source_independent(self) -> None:
        self.fixture.integration().apply()
        provenance_path = self.fixture.installed(MODULE.PROVENANCE_PATH)
        raw = provenance_path.read_text(encoding="utf-8")
        value = json.loads(raw)
        self.assertEqual(value["schema"], 1)
        self.assertEqual(value["integration_version"], 1)
        self.assertEqual(value["target_user"], "alice")
        self.assertEqual(value["target_session"], MODULE.SESSION_PATH)
        self.assertEqual(
            set(value["artifacts"]),
            {
                "sddm-vanilla-theme",
                "vanhyprarch-wayland-session",
                "sddm-target-binding",
                "sddm-vanilla-config",
            },
        )
        self.assertNotIn(str(self.fixture.source), raw)
        self.assertNotIn("password", raw.lower())
        moved = self.base_move_source()
        self.fixture.integration(source=False).validate()
        self.assertTrue(moved.is_dir())

    def base_move_source(self) -> Path:
        moved = self.fixture.base / "source-retained-for-diagnostics"
        self.fixture.source.rename(moved)
        return moved

    def test_source_contract_rejects_logo_and_generic_config_divergence(self) -> None:
        logo = self.fixture.source / MODULE.THEME_SOURCE / "logo.svg"
        logo.write_bytes(logo.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValidationError, "canonical"):
            self.fixture.integration().plan()

        fixture = Fixture()
        try:
            generic = fixture.source / MODULE.THEME_SOURCE / "theme.conf"
            generic.write_text("[General]\ntargetUser=alice\ntargetSessionFile=\n", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "reusable"):
                fixture.integration().plan()
        finally:
            fixture.cleanup()

    def test_source_symlink_is_rejected(self) -> None:
        main = self.fixture.source / MODULE.THEME_SOURCE / "Main.qml"
        copy = self.fixture.base / "main-copy"
        shutil.copyfile(main, copy)
        main.unlink()
        main.symlink_to(copy)
        with self.assertRaisesRegex(IntegrationError, "symlink"):
            self.fixture.integration().plan()

    def test_state_collision_is_not_adopted(self) -> None:
        state = self.fixture.installed(MODULE.STATE_DIRECTORY)
        state.mkdir(mode=0o700)
        (state / "foreign").write_text("unrelated\n", encoding="utf-8")
        plan = self.fixture.integration().plan()
        self.assertTrue(plan.blockers)
        self.assertEqual(plan.blockers[0].subject, "provenance")

    def test_interrupted_transaction_is_read_only_in_plan_and_recovers_on_apply(self) -> None:
        def crash(point: str) -> None:
            if point == "after-transaction-intent":
                raise SimulatedCrash(point)

        with self.assertRaises(SimulatedCrash):
            self.fixture.integration(fault_hook=crash).apply()
        transaction = self.fixture.installed(MODULE.TRANSACTION_PATH)
        self.assertTrue(transaction.exists())
        before = transaction.read_bytes()
        plan = self.fixture.integration().plan()
        self.assertEqual(plan.blockers[0].action, "recovery-required")
        self.assertEqual(transaction.read_bytes(), before)
        self.fixture.integration().apply()
        self.fixture.integration(source=False).validate()
        self.assertFalse(transaction.exists())

    def test_precommit_recovery_does_not_require_valid_source_payload(self) -> None:
        def crash(point: str) -> None:
            if point == "after-first-publication":
                raise SimulatedCrash(point)

        with self.assertRaises(SimulatedCrash):
            self.fixture.integration(fault_hook=crash).apply()
        logo = self.fixture.source / MODULE.THEME_SOURCE / "logo.svg"
        logo.write_bytes(b"not the canonical logo\n")
        plan = self.fixture.integration().plan()
        self.assertEqual(plan.blockers[0].action, "recovery-required")
        self.fixture.integration(source=False).recover()
        self.assertFalse(self.fixture.installed(MODULE.THEME_PATH).exists())
        self.assertFalse(self.fixture.installed(MODULE.SESSION_PATH).exists())
        self.assertFalse(self.fixture.installed(MODULE.PROVENANCE_PATH).exists())
        self.assertFalse(self.fixture.installed(MODULE.TRANSACTION_PATH).exists())

    def test_all_first_install_fault_points_recover_to_complete_candidate(self) -> None:
        points = (
            "before-transaction-intent",
            "after-transaction-intent",
            "during-theme-staging",
            "after-theme-staging",
            "after-session-staging",
            "after-config-staging",
            "after-generated-binding-staging",
            "after-first-publication",
            "before-final-publication",
            "after-live-verification",
            "before-provenance-commit",
            "after-provenance-commit",
            "during-cleanup",
        )
        for point in points:
            with self.subTest(point=point):
                fixture = Fixture()
                try:
                    def crash(current: str, selected: str = point) -> None:
                        if current == selected:
                            raise SimulatedCrash(selected)

                    with self.assertRaises(SimulatedCrash):
                        fixture.integration(fault_hook=crash).apply()
                    binding = fixture.installed(MODULE.BINDING_PATH)
                    session = fixture.installed(MODULE.SESSION_PATH)
                    theme = fixture.installed(MODULE.THEME_PATH)
                    if binding.exists():
                        self.assertTrue(session.is_file())
                    if theme.exists():
                        self.assertEqual(
                            sorted(path.name for path in theme.iterdir()),
                            sorted(MODULE.THEME_INSTALLED_FILES),
                        )
                    transaction = fixture.installed(MODULE.TRANSACTION_PATH)
                    if transaction.exists():
                        self.assertEqual(stat.S_IMODE(transaction.stat().st_mode), 0o600)
                    for parent in (
                        fixture.installed("/usr/share/sddm/themes"),
                        fixture.installed("/usr/share/wayland-sessions"),
                        fixture.installed("/etc/sddm.conf.d"),
                    ):
                        for container in parent.glob(".vanhyprarch-sddm-login-*"):
                            self.assertEqual(stat.S_IMODE(container.stat().st_mode), 0o700)
                    fixture.integration().apply()
                    fixture.integration(source=False).validate()
                    self.assertFalse(fixture.installed(MODULE.TRANSACTION_PATH).exists())
                    self.assertEqual(
                        list(fixture.installed("/usr/share/sddm/themes").glob(".vanhyprarch-sddm-login-*")),
                        [],
                    )
                    self.assertEqual(
                        list(fixture.installed("/usr/share/wayland-sessions").glob(".vanhyprarch-sddm-login-*")),
                        [],
                    )
                finally:
                    fixture.cleanup()

    def test_update_faults_restore_old_or_retain_committed_new_then_converge(self) -> None:
        points = (
            "during-theme-staging",
            "before-final-publication",
            "after-live-verification",
            "after-provenance-commit",
            "during-cleanup",
        )
        for point in points:
            with self.subTest(point=point):
                fixture = Fixture()
                try:
                    fixture.integration(release_id="v1").apply()
                    main = fixture.source / MODULE.THEME_SOURCE / "Main.qml"
                    main.write_text(main.read_text(encoding="utf-8") + "\n// v2\n", encoding="utf-8")

                    def crash(current: str, selected: str = point) -> None:
                        if current == selected:
                            raise SimulatedCrash(selected)

                    with self.assertRaises(SimulatedCrash):
                        fixture.integration(release_id="v2", fault_hook=crash).apply()
                    fixture.integration(release_id="v2").apply()
                    fixture.integration(source=False).validate()
                    state = json.loads(fixture.installed(MODULE.PROVENANCE_PATH).read_text())
                    self.assertEqual(state["release"]["id"], "v2")
                finally:
                    fixture.cleanup()

    def test_abrupt_process_exit_recovers_on_both_sides_of_commit(self) -> None:
        program = """
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from sddm_login_integration import SddmLoginIntegration, TargetUser

def resolve(name):
    if name != "alice":
        raise KeyError(name)
    return TargetUser("alice", 1001, 1001)

SddmLoginIntegration(
    source_root=Path(sys.argv[2]),
    target_username="alice",
    release_id="test-v1",
    system_root=Path(sys.argv[3]),
    account_resolver=resolve,
    effective_uid=0,
    root_identity=(int(sys.argv[4]), int(sys.argv[5])),
    testing=True,
).apply()
"""
        for point in ("after-first-publication", "after-provenance-commit"):
            with self.subTest(point=point):
                fixture = Fixture()
                try:
                    environment = os.environ.copy()
                    environment[MODULE.TEST_MODE_ENV] = "1"
                    environment[MODULE.TEST_FAULT_ENV] = point
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            program,
                            str(REPOSITORY / "install"),
                            str(fixture.source),
                            str(fixture.root),
                            str(fixture.uid),
                            str(fixture.gid),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                        env=environment,
                    )
                    self.assertEqual(result.returncode, 197, result.stderr)
                    fixture.integration().apply()
                    fixture.integration(source=False).validate()
                finally:
                    fixture.cleanup()

    def test_apply_source_does_not_name_package_service_or_pam_mutators(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "pacman",
            "systemctl",
            "ly@tty2",
            "/etc/pam.d",
            "display-manager.service",
            "subprocess.run",
        ):
            self.assertNotIn(forbidden, source)

    def test_cli_non_root_refusal_precedes_source_or_account_work(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("CLI non-root boundary requires a non-root test process")
        for operation in ("plan", "apply"):
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    operation,
                    "--target-user",
                    "account-that-need-not-exist",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(
                result.stderr,
                "SDDM login integration: SDDM login integration requires root "
                "privileges; rerun with sudo\n",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
