#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parent.parent
HELPER = REPOSITORY / "bin/vanhyprarch-keyboard-sync"
UNIT = REPOSITORY / "home/.config/systemd/user/vanhyprarch-keyboard-sync.service"
CORE = REPOSITORY / "home/.config/hypr/vanhyprarch/core.lua"
PACKAGES = REPOSITORY / "packages/official.txt"
OWNERSHIP = REPOSITORY / "deployment/ownership-v1.toml"
MACHINE_SEED = REPOSITORY / "seeds/home/.config/vanhyprarch/machine/hyprland.lua"

LOADER = importlib.machinery.SourceFileLoader("vanhyprarch_keyboard_sync", str(HELPER))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
if SPEC is None:
    raise RuntimeError("could not load keyboard synchronizer")
keyboard_sync = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = keyboard_sync
LOADER.exec_module(keyboard_sync)


XkbTuple = keyboard_sync.XkbTuple
CommandResult = keyboard_sync.CommandResult


class FakeHyprland:
    def __init__(self, current: XkbTuple) -> None:
        self.current = current
        self.apply_calls: list[XkbTuple] = []
        self.read_calls = 0
        self.apply_failures: list[Exception | None] = []
        self.read_overrides: list[XkbTuple | Exception] = []

    def read_tuple(self) -> XkbTuple:
        self.read_calls += 1
        if self.read_overrides:
            value = self.read_overrides.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        return self.current

    def apply_tuple(self, value: XkbTuple) -> None:
        self.apply_calls.append(value)
        failure = self.apply_failures.pop(0) if self.apply_failures else None
        if failure is not None:
            raise failure
        self.current = value


class FakeValidator:
    def __init__(self, invalid: set[XkbTuple] | None = None) -> None:
        self.invalid = invalid or set()
        self.calls: list[XkbTuple] = []

    def __call__(self, value: XkbTuple) -> tuple[bool, str]:
        self.calls.append(value)
        if value in self.invalid:
            return False, "fixture invalid tuple"
        return True, ""


class QueueScheduler:
    def __init__(self) -> None:
        self.queue: list[object] = []

    def __call__(self, callback: object) -> int:
        self.queue.append(callback)
        return len(self.queue)

    def run_one(self) -> None:
        callback = self.queue.pop(0)
        callback()

    def run_all(self) -> None:
        while self.queue:
            self.run_one()


class FakeCoordinator:
    def __init__(self) -> None:
        self.requests: list[bool] = []

    def request(self, *, force: bool = False) -> None:
        self.requests.append(force)


class TupleAndCommandTests(unittest.TestCase):
    def test_localed_client_uses_one_coherent_getall_call(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[object, ...]] = []

            def call_sync(self, *arguments: object) -> object:
                self.calls.append(arguments)
                return keyboard_sync.GLib.Variant(
                    "(a{sv})",
                    (
                        {
                            "X11Layout": keyboard_sync.GLib.Variant("s", "us,it"),
                            "X11Model": keyboard_sync.GLib.Variant("s", "pc105"),
                            "X11Variant": keyboard_sync.GLib.Variant("s", ","),
                            "X11Options": keyboard_sync.GLib.Variant(
                                "s", "grp:alt_shift_toggle"
                            ),
                        },
                    ),
                )

        connection = Connection()
        client = keyboard_sync.LocaledClient(connection)
        self.assertEqual(
            client.read_tuple(),
            XkbTuple("us,it", "pc105", ",", "grp:alt_shift_toggle"),
        )
        self.assertEqual(len(connection.calls), 1)
        call = connection.calls[0]
        self.assertEqual(call[0], keyboard_sync.LOCALED_SERVICE)
        self.assertEqual(call[1], keyboard_sync.LOCALED_PATH)
        self.assertEqual(call[2], keyboard_sync.PROPERTIES_INTERFACE)
        self.assertEqual(call[3], "GetAll")
        self.assertEqual(call[4].unpack(), (keyboard_sync.LOCALED_INTERFACE,))

    def test_localed_property_mapping_preserves_exact_strings(self) -> None:
        properties = {
            "X11Layout": "us,it",
            "X11Model": "",
            "X11Variant": ",",
            "X11Options": "grp:alt_shift_toggle,terminate:ctrl_alt_bksp",
        }
        self.assertEqual(
            XkbTuple.from_localed(properties),
            XkbTuple(
                "us,it",
                "",
                ",",
                "grp:alt_shift_toggle,terminate:ctrl_alt_bksp",
            ),
        )

    def test_missing_or_non_string_property_is_rejected(self) -> None:
        complete = {
            "X11Layout": "it",
            "X11Model": "pc105",
            "X11Variant": "",
            "X11Options": "",
        }
        for name in keyboard_sync.X11_PROPERTIES:
            with self.subTest(missing=name):
                broken = dict(complete)
                del broken[name]
                with self.assertRaises(keyboard_sync.LocaledUnavailable):
                    XkbTuple.from_localed(broken)
        broken = dict(complete)
        broken["X11Layout"] = ["it"]
        with self.assertRaises(keyboard_sync.LocaledUnavailable):
            XkbTuple.from_localed(broken)

    def test_xkbcli_argv_is_exact_and_preserves_empty_values(self) -> None:
        value = XkbTuple("us,it", "", ",", "grp:alt_shift_toggle,terminate:ctrl_alt_bksp")
        self.assertEqual(
            keyboard_sync.xkbcli_argv(value),
            [
                "/usr/bin/xkbcli",
                "compile-keymap",
                "--test",
                "--rules",
                "evdev",
                "--model",
                "",
                "--layout",
                "us,it",
                "--variant",
                ",",
                "--options",
                "grp:alt_shift_toggle,terminate:ctrl_alt_bksp",
            ],
        )

    def test_known_single_and_multiple_layouts_pass_real_preflight(self) -> None:
        for value in (
            XkbTuple("it", "pc105", "", ""),
            XkbTuple("us", "", "", ""),
            XkbTuple("us,it", "pc105", ",", "grp:alt_shift_toggle,terminate:ctrl_alt_bksp"),
        ):
            with self.subTest(value=value):
                valid, diagnostic = keyboard_sync.validate_tuple(value)
                self.assertTrue(valid, diagnostic)

    def test_malformed_layout_fails_real_preflight(self) -> None:
        valid, diagnostic = keyboard_sync.validate_tuple(
            XkbTuple("__vanhyprarch_invalid__", "pc105", "", "")
        )
        self.assertFalse(valid)
        self.assertIn("Couldn't", diagnostic)

    def test_lua_escaping_is_byte_exact_and_shell_independent(self) -> None:
        original = 'a"b\\c\nè'
        literal = keyboard_sync.lua_string(original)
        self.assertEqual(
            literal,
            '"a\\x22b\\x5cc\\x0a\\xc3\\xa8"',
        )
        result = subprocess.run(
            ["/usr/bin/lua", "-"],
            input=f"io.write({literal})\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, original)

    def test_eval_argv_assigns_exactly_four_fields_once(self) -> None:
        value = XkbTuple("us,it", "pc105", ",", "grp:alt_shift_toggle")
        argv = keyboard_sync.hyprland_eval_argv(value)
        self.assertEqual(argv[:2], ["/usr/bin/hyprctl", "eval"])
        self.assertEqual(len(argv), 3)
        source = argv[2]
        for field in ("kb_layout", "kb_model", "kb_variant", "kb_options"):
            self.assertEqual(source.count(field), 1)
        self.assertNotIn("kb_rules", source)
        self.assertNotIn("switchxkblayout", source)

    def test_hyprland_readback_uses_global_options_only(self) -> None:
        values = {
            "kb_layout": "us,it",
            "kb_model": "pc105",
            "kb_variant": ",",
            "kb_options": "grp:alt_shift_toggle",
        }
        calls: list[list[str]] = []

        def runner(argv: object) -> CommandResult:
            command = list(argv)
            calls.append(command)
            option = command[-1].removeprefix("input:")
            return CommandResult(0, json.dumps({"str": values[option]}), "")

        client = keyboard_sync.HyprlandClient(runner)
        self.assertEqual(client.read_tuple(), XkbTuple(*values.values()))
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(call[:3] == ["/usr/bin/hyprctl", "-j", "getoption"] for call in calls))


class ReconciliationTests(unittest.TestCase):
    PRIOR = XkbTuple("it", "", "", "")
    DESIRED = XkbTuple("us", "pc105", "", "terminate:ctrl_alt_bksp")

    def synchronizer(
        self,
        desired: XkbTuple,
        hyprland: FakeHyprland,
        validator: FakeValidator | None = None,
        reads: list[XkbTuple] | None = None,
    ) -> keyboard_sync.KeyboardSynchronizer:
        def read_localed() -> XkbTuple:
            if reads is not None:
                return reads.pop(0)
            return desired

        return keyboard_sync.KeyboardSynchronizer(
            read_localed,
            hyprland,
            validator or FakeValidator(),
        )

    def test_empty_layout_keeps_current_state_without_apply(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)
        validator = FakeValidator()
        sync = self.synchronizer(XkbTuple("", "pc105", "", "option"), hyprland, validator)
        self.assertEqual(sync.reconcile(), "empty-layout")
        self.assertEqual(hyprland.read_calls, 0)
        self.assertEqual(hyprland.apply_calls, [])
        self.assertEqual(validator.calls, [])

    def test_malformed_tuple_is_rejected_before_apply(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)
        validator = FakeValidator({self.DESIRED})
        sync = self.synchronizer(self.DESIRED, hyprland, validator)
        self.assertEqual(sync.reconcile(), "invalid")
        self.assertEqual(hyprland.read_calls, 1)
        self.assertEqual(hyprland.apply_calls, [])

    def test_identical_current_tuple_suppresses_eval(self) -> None:
        hyprland = FakeHyprland(self.DESIRED)
        validator = FakeValidator()
        sync = self.synchronizer(self.DESIRED, hyprland, validator)
        self.assertEqual(sync.reconcile(), "unchanged")
        self.assertEqual(hyprland.read_calls, 1)
        self.assertEqual(hyprland.apply_calls, [])
        self.assertEqual(validator.calls, [])
        self.assertEqual(sync.last_successful, self.DESIRED)

    def test_changed_tuple_applies_once_and_verifies(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)
        sync = self.synchronizer(self.DESIRED, hyprland)
        self.assertEqual(sync.reconcile(), "applied")
        self.assertEqual(hyprland.apply_calls, [self.DESIRED])
        self.assertEqual(hyprland.read_calls, 2)
        self.assertEqual(sync.last_successful, self.DESIRED)

    def test_verification_mismatch_rolls_back_once(self) -> None:
        mismatch = XkbTuple("de", "pc105", "", "")
        hyprland = FakeHyprland(self.PRIOR)
        hyprland.read_overrides = [self.PRIOR, mismatch, self.PRIOR]
        sync = self.synchronizer(self.DESIRED, hyprland)
        self.assertEqual(sync.reconcile(), "rolled-back")
        self.assertEqual(hyprland.apply_calls, [self.DESIRED, self.PRIOR])
        self.assertIsNone(sync.last_successful)

    def test_apply_failure_rolls_back_once(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)
        hyprland.apply_failures = [keyboard_sync.ApplyFailed("fixture failure"), None]
        sync = self.synchronizer(self.DESIRED, hyprland)
        self.assertEqual(sync.reconcile(), "rolled-back")
        self.assertEqual(hyprland.apply_calls, [self.DESIRED, self.PRIOR])

    def test_rollback_failure_is_loud_and_does_not_loop(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)
        hyprland.apply_failures = [
            keyboard_sync.ApplyFailed("apply failed"),
            keyboard_sync.ApplyFailed("rollback failed"),
        ]
        sync = self.synchronizer(self.DESIRED, hyprland)
        with self.assertLogs("vanhyprarch-keyboard-sync", level="ERROR") as logs:
            self.assertEqual(sync.reconcile(), "rollback-failed")
        self.assertEqual(hyprland.apply_calls, [self.DESIRED, self.PRIOR])
        self.assertTrue(any("rollback failed" in line for line in logs.output))

    def test_localed_and_hyprland_unavailable_fail_closed(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)

        def unavailable() -> XkbTuple:
            raise keyboard_sync.LocaledUnavailable("fixture unavailable")

        sync = keyboard_sync.KeyboardSynchronizer(unavailable, hyprland, FakeValidator())
        self.assertEqual(sync.reconcile(), "localed-unavailable")
        hyprland.read_overrides = [keyboard_sync.HyprlandUnavailable("fixture unavailable")]
        sync = self.synchronizer(self.DESIRED, hyprland)
        self.assertEqual(sync.reconcile(), "hyprland-unavailable")
        self.assertEqual(hyprland.apply_calls, [])

    def test_forced_reconcile_rereads_both_authority_and_runtime(self) -> None:
        hyprland = FakeHyprland(self.PRIOR)
        reads = [self.DESIRED]
        sync = self.synchronizer(self.DESIRED, hyprland, reads=reads)
        sync.last_successful = self.DESIRED
        self.assertEqual(sync.reconcile(force=True), "applied")
        self.assertEqual(reads, [])
        self.assertEqual(hyprland.read_calls, 2)
        self.assertEqual(hyprland.apply_calls, [self.DESIRED])

    def test_forced_reconcile_matching_runtime_skips_eval(self) -> None:
        hyprland = FakeHyprland(self.DESIRED)
        reads = [self.DESIRED]
        sync = self.synchronizer(self.DESIRED, hyprland, reads=reads)
        sync.last_successful = self.DESIRED
        self.assertEqual(sync.reconcile(force=True), "unchanged")
        self.assertEqual(reads, [])
        self.assertEqual(hyprland.apply_calls, [])


class EventTests(unittest.TestCase):
    def test_only_graphical_x11_properties_trigger(self) -> None:
        for name in keyboard_sync.X11_PROPERTIES:
            with self.subTest(name=name):
                self.assertTrue(
                    keyboard_sync.signal_requires_reconcile(
                        keyboard_sync.LOCALED_INTERFACE, [name], []
                    )
                )
        for names in (["VConsoleKeymap"], ["VConsoleKeymapToggle"], ["Locale"]):
            with self.subTest(names=names):
                self.assertFalse(
                    keyboard_sync.signal_requires_reconcile(
                        keyboard_sync.LOCALED_INTERFACE, names, []
                    )
                )
        self.assertFalse(
            keyboard_sync.signal_requires_reconcile("org.example.Other", ["X11Layout"], [])
        )

    def test_invalidated_graphical_property_triggers_full_reconcile(self) -> None:
        self.assertTrue(
            keyboard_sync.signal_requires_reconcile(
                keyboard_sync.LOCALED_INTERFACE, [], ["X11Options"]
            )
        )

    def test_duplicate_events_coalesce_to_one_final_state_apply(self) -> None:
        scheduler = QueueScheduler()
        final = XkbTuple("us,it", "pc105", ",", "grp:alt_shift_toggle")
        authoritative = [XkbTuple("it", "", "", "")]
        fetches = 0

        def read_localed() -> XkbTuple:
            nonlocal fetches
            fetches += 1
            return authoritative[0]

        hyprland = FakeHyprland(XkbTuple("de", "pc105", "", ""))
        synchronizer = keyboard_sync.KeyboardSynchronizer(
            read_localed, hyprland, FakeValidator()
        )
        coordinator = keyboard_sync.ReconcileCoordinator(
            synchronizer.reconcile, scheduler
        )
        keyboard_sync.dispatch_properties_changed(
            keyboard_sync.LOCALED_INTERFACE,
            ["X11Layout"],
            [],
            coordinator.request,
        )
        keyboard_sync.dispatch_properties_changed(
            keyboard_sync.LOCALED_INTERFACE,
            ["X11Options"],
            [],
            coordinator.request,
        )
        authoritative[0] = final
        self.assertEqual(len(scheduler.queue), 1)
        scheduler.run_all()
        self.assertEqual(fetches, 1)
        self.assertEqual(hyprland.apply_calls, [final])

    def test_relevant_signal_fetches_complete_tuple_and_applies_once(self) -> None:
        scheduler = QueueScheduler()
        desired = XkbTuple("us,it", "pc105", ",", "grp:alt_shift_toggle")
        hyprland = FakeHyprland(XkbTuple("it", "", "", ""))
        fetches = 0

        def read_localed() -> XkbTuple:
            nonlocal fetches
            fetches += 1
            return desired

        synchronizer = keyboard_sync.KeyboardSynchronizer(
            read_localed, hyprland, FakeValidator()
        )
        coordinator = keyboard_sync.ReconcileCoordinator(
            synchronizer.reconcile, scheduler
        )
        self.assertTrue(
            keyboard_sync.dispatch_properties_changed(
                keyboard_sync.LOCALED_INTERFACE,
                ["X11Variant"],
                [],
                coordinator.request,
            )
        )
        scheduler.run_all()
        self.assertEqual(fetches, 1)
        self.assertEqual(hyprland.apply_calls, [desired])

    def test_relevant_signal_matching_runtime_reads_and_skips_eval(self) -> None:
        scheduler = QueueScheduler()
        desired = XkbTuple("it", "pc105", "", "")
        hyprland = FakeHyprland(desired)
        fetches = 0

        def read_localed() -> XkbTuple:
            nonlocal fetches
            fetches += 1
            return desired

        synchronizer = keyboard_sync.KeyboardSynchronizer(
            read_localed, hyprland, FakeValidator()
        )
        synchronizer.last_successful = desired
        coordinator = keyboard_sync.ReconcileCoordinator(
            synchronizer.reconcile, scheduler
        )
        keyboard_sync.dispatch_properties_changed(
            keyboard_sync.LOCALED_INTERFACE,
            ["X11Model"],
            [],
            coordinator.request,
        )
        scheduler.run_all()
        self.assertEqual(fetches, 1)
        self.assertEqual(hyprland.read_calls, 1)
        self.assertEqual(hyprland.apply_calls, [])

    def test_event_during_reconcile_runs_newest_state_afterward(self) -> None:
        scheduler = QueueScheduler()
        states = ["first", "newest"]
        seen: list[str] = []
        coordinator: keyboard_sync.ReconcileCoordinator

        def worker(*, force: bool = False) -> None:
            seen.append(states.pop(0))
            if seen == ["first"]:
                coordinator.request()

        coordinator = keyboard_sync.ReconcileCoordinator(worker, scheduler)
        coordinator.request()
        scheduler.run_all()
        self.assertEqual(seen, ["first", "newest"])

    def test_console_only_signal_does_not_repair_runtime_drift(self) -> None:
        scheduler = QueueScheduler()
        desired = XkbTuple("it", "pc105", "", "")
        hyprland = FakeHyprland(XkbTuple("de", "pc105", "", ""))
        fetches = 0

        def read_localed() -> XkbTuple:
            nonlocal fetches
            fetches += 1
            return desired

        synchronizer = keyboard_sync.KeyboardSynchronizer(
            read_localed, hyprland, FakeValidator()
        )
        synchronizer.last_successful = desired
        coordinator = keyboard_sync.ReconcileCoordinator(
            synchronizer.reconcile, scheduler
        )
        self.assertFalse(
            keyboard_sync.dispatch_properties_changed(
                keyboard_sync.LOCALED_INTERFACE,
                ["VConsoleKeymap", "Locale"],
                [],
                coordinator.request,
            )
        )
        scheduler.run_all()
        self.assertEqual(fetches, 0)
        self.assertEqual(hyprland.read_calls, 0)
        self.assertEqual(hyprland.apply_calls, [])

    def test_relevant_event_repairs_drift_even_when_authority_cache_matches(self) -> None:
        scheduler = QueueScheduler()
        desired = XkbTuple("it", "pc105", "", "")
        drifted = XkbTuple("de", "pc105", "", "")
        hyprland = FakeHyprland(desired)
        validator = FakeValidator()
        fetches = 0

        def read_localed() -> XkbTuple:
            nonlocal fetches
            fetches += 1
            return desired

        synchronizer = keyboard_sync.KeyboardSynchronizer(
            read_localed, hyprland, validator
        )
        self.assertEqual(synchronizer.reconcile(), "unchanged")
        hyprland.current = drifted
        coordinator = keyboard_sync.ReconcileCoordinator(
            synchronizer.reconcile, scheduler
        )
        keyboard_sync.dispatch_properties_changed(
            keyboard_sync.LOCALED_INTERFACE,
            ["VConsoleKeymap", "X11Layout"],
            [],
            coordinator.request,
        )
        scheduler.run_all()
        self.assertEqual(fetches, 2)
        self.assertEqual(hyprland.read_calls, 3)
        self.assertEqual(validator.calls, [desired])
        self.assertEqual(hyprland.apply_calls, [desired])
        self.assertEqual(hyprland.current, desired)


class IpcRecoveryTests(unittest.TestCase):
    def test_unavailable_start_appearance_and_reappearance_are_event_driven(self) -> None:
        coordinator = FakeCoordinator()
        gate = keyboard_sync.RuntimeRequestGate(coordinator)
        gate.request(force=True)
        self.assertEqual(coordinator.requests, [])
        gate.update_ipc(True)
        self.assertEqual(coordinator.requests, [True])
        gate.update_ipc(True)
        self.assertEqual(coordinator.requests, [True])
        gate.update_ipc(False)
        gate.update_ipc(True)
        self.assertEqual(coordinator.requests, [True, True])

    def test_newest_authoritative_state_is_read_when_socket_appears(self) -> None:
        scheduler = QueueScheduler()
        authoritative = [XkbTuple("it", "", "", "")]
        seen: list[XkbTuple] = []

        def worker(*, force: bool = False) -> None:
            seen.append(authoritative[0])

        coordinator = keyboard_sync.ReconcileCoordinator(worker, scheduler)
        gate = keyboard_sync.RuntimeRequestGate(coordinator)
        gate.request()
        authoritative[0] = XkbTuple("us", "pc105", "", "")
        gate.request()
        gate.update_ipc(True)
        scheduler.run_all()
        self.assertEqual(seen, [authoritative[0]])

    def test_socket_path_is_rebuilt_from_each_process_environment(self) -> None:
        old_environment = {
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "HYPRLAND_INSTANCE_SIGNATURE": "old_signature",
        }
        new_environment = dict(old_environment)
        new_environment["HYPRLAND_INSTANCE_SIGNATURE"] = "new_signature"
        self.assertEqual(
            keyboard_sync.hyprland_socket_path(old_environment),
            Path("/run/user/1000/hypr/old_signature/.socket.sock"),
        )
        self.assertEqual(
            keyboard_sync.hyprland_socket_path(new_environment),
            Path("/run/user/1000/hypr/new_signature/.socket.sock"),
        )
        new_environment["HYPRLAND_INSTANCE_SIGNATURE"] = "../wrong"
        with self.assertRaises(RuntimeError):
            keyboard_sync.hyprland_socket_path(new_environment)


class SessionEnvironmentTests(unittest.TestCase):
    ENVIRONMENT = {
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "HYPRLAND_INSTANCE_SIGNATURE": "new_signature",
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":0",
        "UNRELATED_SECRET": "must-not-be-imported",
    }

    def test_publication_completes_before_service_restart(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: object) -> CommandResult:
            calls.append(list(argv))
            return CommandResult(0, "", "")

        self.assertEqual(
            keyboard_sync.publish_session_environment_and_restart(
                dict(self.ENVIRONMENT), runner
            ),
            0,
        )
        self.assertEqual(
            calls,
            [
                [
                    "/usr/bin/systemctl",
                    "--user",
                    "import-environment",
                    "HYPRLAND_INSTANCE_SIGNATURE",
                    "WAYLAND_DISPLAY",
                    "DISPLAY",
                ],
                [
                    "/usr/bin/systemctl",
                    "--user",
                    "restart",
                    "vanhyprarch-keyboard-sync.service",
                ],
            ],
        )
        self.assertNotIn("XDG_RUNTIME_DIR", calls[0])
        self.assertNotIn("UNRELATED_SECRET", calls[0])

    def test_failed_publication_never_restarts_with_stale_environment(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: object) -> CommandResult:
            calls.append(list(argv))
            return CommandResult(1, "", "fixture failure")

        self.assertEqual(
            keyboard_sync.publish_session_environment_and_restart(
                dict(self.ENVIRONMENT), runner
            ),
            1,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], "import-environment")

    def test_missing_session_identity_fails_before_any_systemctl_call(self) -> None:
        calls: list[list[str]] = []
        environment = dict(self.ENVIRONMENT)
        del environment["HYPRLAND_INSTANCE_SIGNATURE"]

        def runner(argv: object) -> CommandResult:
            calls.append(list(argv))
            return CommandResult(0, "", "")

        self.assertEqual(
            keyboard_sync.publish_session_environment_and_restart(environment, runner),
            1,
        )
        self.assertEqual(calls, [])


class StaticIntegrationTests(unittest.TestCase):
    def test_active_group_is_outside_helper_ownership(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("switchxkblayout", source)
        self.assertNotIn("active_layout_index", source)
        self.assertNotIn("active_keymap", source)
        self.assertNotIn("hyprctl keyword", source)

    def test_helper_contains_no_polling_or_text_monitor(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        for forbidden in (
            "dbus-monitor",
            "busctl monitor",
            "GLib.timeout_add",
            "GLib.timeout_add_seconds",
            "time.sleep",
            "localectl",
            "pkexec",
            "sudo",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('monitor_directory(', source)
        self.assertIn('"g-properties-changed"', source)
        self.assertIn('"notify::g-name-owner"', source)

    def test_unit_is_static_session_owned_and_restart_on_failure(self) -> None:
        unit = UNIT.read_text(encoding="utf-8")
        self.assertIn("Type=simple", unit)
        self.assertIn("ExecStart=%h/.local/bin/vanhyprarch-keyboard-sync", unit)
        self.assertIn("ExecReload=/usr/bin/kill -HUP $MAINPID", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertNotIn("[Install]", unit)
        self.assertNotIn("graphical-session.target", unit)
        self.assertNotIn("network", unit.lower())

    def test_hyprland_has_exactly_one_start_and_reload_hook(self) -> None:
        core = CORE.read_text(encoding="utf-8")
        start = "/.local/bin/vanhyprarch-keyboard-sync session-start"
        reload = "systemctl --user reload vanhyprarch-keyboard-sync.service"
        self.assertEqual(core.count(start), 1)
        self.assertEqual(core.count(reload), 1)
        self.assertNotIn(
            "systemctl --user restart vanhyprarch-keyboard-sync.service", core
        )
        self.assertNotIn("import-environment", core)
        self.assertEqual(core.count('hl.on("config.reloaded"'), 1)
        self.assertEqual(core.count('hl.on("hyprland.start"'), 1)
        self.assertNotIn("uwsm", core.lower())

    def test_packages_and_ownership_are_explicit(self) -> None:
        packages = PACKAGES.read_text(encoding="utf-8").splitlines()
        self.assertIn("python", packages)
        self.assertIn("python-gobject", packages)
        self.assertIn("libxkbcommon", packages)
        self.assertIn("xkeyboard-config", packages)
        ownership = OWNERSHIP.read_text(encoding="utf-8")
        self.assertIn('source = "bin/vanhyprarch-keyboard-sync"', ownership)
        self.assertIn(
            'source = "home/.config/systemd/user/vanhyprarch-keyboard-sync.service"',
            ownership,
        )
        self.assertNotIn('target = "/etc/vconsole.conf"', ownership)
        self.assertNotIn('target = "/etc/X11/xorg.conf.d/00-keyboard.conf"', ownership)

    def test_machine_seed_remains_keyboard_neutral(self) -> None:
        seed = MACHINE_SEED.read_text(encoding="utf-8")
        self.assertNotIn("kb_layout", seed)
        self.assertNotIn("kb_model", seed)
        self.assertNotIn("kb_variant", seed)
        self.assertNotIn("kb_options", seed)

    def test_helper_compiles(self) -> None:
        compile_result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(HELPER)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)


if __name__ == "__main__":
    unittest.main()
