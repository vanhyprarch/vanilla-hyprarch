#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from dataclasses import replace
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND = REPOSITORY / "bin/vanhyprarch-monitor"
UNIT = REPOSITORY / "home/.config/systemd/user/vanhyprarch-monitor-safe-apply.service"

loader = importlib.machinery.SourceFileLoader("vanhyprarch_monitor", str(BACKEND))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
monitor = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = monitor
loader.exec_module(monitor)


def output(
    *,
    name: str = "DP-1",
    width: int = 2560,
    height: int = 1440,
    refresh: float = 59.95,
    scale: float = 1.25,
    make: str = "Example",
    model: str = "Panel",
    serial: str = "ABC123",
    disabled: bool = False,
    x: int = 0,
    available: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": 0,
        "name": name,
        "description": f"{make} {model} {serial}",
        "make": make,
        "model": model,
        "serialNumber": serial,
        "width": width,
        "height": height,
        "refreshRate": refresh,
        "x": x,
        "y": 0,
        "scale": scale,
        "transform": 0,
        "disabled": disabled,
        "dpmsStatus": not disabled,
        "mirrorOf": "none",
        "currentFormat": "XRGB8888",
        "vrr": False,
        "reserved": [0, 0, 0, 0],
        "colorManagementPreset": "srgb",
        "sdrBrightness": 1.0,
        "availableModes": available
        if available is not None
        else ["2560x1440@59.95Hz", "1920x1080@60.00Hz"],
    }


def inactive_output() -> dict[str, object]:
    return output(
        name="HDMI-A-1",
        width=0,
        height=0,
        refresh=0,
        scale=1.0,
        make="Spare",
        model="Inactive",
        serial="INACTIVE1",
        disabled=True,
        available=[],
    )


def candidate_output() -> dict[str, object]:
    return output(width=1920, height=1080, refresh=60.00001, scale=1.5)


def machine_configuration(connector: str = "DP-1") -> bytes:
    return f'''-- machine prologue and comments must survive
hl.monitor({{
    output = "",
    mode = "preferred",
    position = "auto",
    scale = "auto",
}})

local vanhyprarchMonitorScale = 1.25

hl.monitor({{
    output = "{connector}",
    mode = "2560x1440@59.95",
    position = "0x0",
    scale = vanhyprarchMonitorScale,
    bitdepth = 10,
    cm = "auto",
}})

-- unrelated machine content
hl.device({{
    name = "example-device",
    sensitivity = -0.25,
}})
'''.encode()


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        # Make a failed convergence deterministic without forty fixture reads.
        self.value += max(seconds, monitor.APPLY_SETTLE_SECONDS)

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeInstanceProvider:
    def __init__(self, identity: object) -> None:
        self.identity = identity

    def current(self, signature: str) -> object:
        if isinstance(self.identity, Exception):
            raise self.identity
        if self.identity is None:
            raise monitor.InstanceReplaced("fixture compositor disappeared")
        return self.identity


class QueueRunner:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, argv: object) -> object:
        self.calls.append(list(argv))
        if not self.responses:
            raise AssertionError(f"unexpected command: {argv}")
        response = self.responses.pop(0)
        if isinstance(response, list):
            return monitor.CommandResult(0, json.dumps(response), "")
        return response


OK = monitor.CommandResult(0, "ok\n", "")


class MonitorBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.config = self.root / "config"
        machine_dir = self.config / "vanhyprarch/machine"
        override_dir = self.config / "vanhyprarch/overrides"
        machine_dir.mkdir(parents=True)
        override_dir.mkdir(parents=True)
        self.machine = machine_dir / "hyprland.lua"
        self.override = override_dir / "hyprland.lua"
        self.machine.write_bytes(machine_configuration())
        self.override.write_bytes(b"-- user override\n")
        self.machine.chmod(0o600)
        self.override.chmod(0o600)
        self.paths = monitor.ConfigPaths(self.machine, self.override)
        self.instance = monitor.InstanceIdentity("fixture_123", 500, 9000, 10, 20)
        self.provider = FakeInstanceProvider(self.instance)
        self.clock = FakeClock()
        self.store = monitor.RuntimeStore(self.runtime)
        self.store.acquire()
        self.addCleanup(self.store.release)
        self.candidate = monitor.Candidate.create("DP-1", 1920, 1080, "60.00", "1.50")

    def authority(
        self,
        responses: list[object],
        *,
        persister: object | None = None,
    ) -> tuple[object, QueueRunner]:
        runner = QueueRunner(responses)
        authority = monitor.TransactionAuthority(
            self.store,
            self.provider,
            self.paths,
            runner=runner,
            clock=self.clock,
            persister=persister,
        )
        return authority, runner

    def begin_success(
        self, *, persister: object | None = None
    ) -> tuple[object, QueueRunner, object]:
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]], persister=persister
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(journal.state, "temporary-active")
        return authority, runner, journal

    def test_monitor_json_parsing_and_duplicate_advertised_modes(self) -> None:
        raw = output(
            available=[
                "2560x1440@59.95Hz",
                "2560x1440@59.95Hz",
                "1920x1080@60.00Hz",
            ]
        )
        topology = monitor.parse_monitor_payload([raw, inactive_output()])
        active = topology.target("DP-1")
        self.assertEqual(active.mode, monitor.Mode(2560, 1440, 59950))
        self.assertEqual(len(active.advertised_modes), 3)
        self.assertEqual(len(active.canonical_advertised_modes()), 2)
        self.assertFalse(topology.target("HDMI-A-1").usable)
        self.assertEqual(topology.target("HDMI-A-1").refresh_millihz, 0)

    def test_nested_observable_color_state_is_protected(self) -> None:
        raw = output()
        raw["lastIpcObject"] = {
            "cm": "wide",
            "bitdepth": 10,
            "icc": "/example/profile.icc",
            "unrelated": "ignored",
        }
        parsed = monitor.parse_monitor_payload([raw]).target("DP-1")
        self.assertEqual(parsed.color_state["lastIpcObject.cm"], "wide")
        self.assertEqual(parsed.color_state["lastIpcObject.bitdepth"], 10)
        self.assertEqual(
            parsed.color_state["lastIpcObject.icc"], "/example/profile.icc"
        )
        self.assertNotIn("lastIpcObject.unrelated", parsed.color_state)

    def test_malformed_monitor_data_fails_closed(self) -> None:
        cases = [
            {},
            {**output(), "refreshRate": "fast"},
            {**output(), "availableModes": ["not-a-mode"]},
            {**output(), "make": "", "model": "", "serialNumber": "", "description": ""},
        ]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(monitor.ValidationError):
                    monitor.parse_monitor_payload([value])

    def test_mode_tuple_validation_rejects_unadvertised_combination(self) -> None:
        topology = monitor.parse_monitor_payload([output()])
        monitor.validate_candidate(
            monitor.Candidate.create("DP-1", 1920, 1080, "60", "1.25"), topology
        )
        with self.assertRaisesRegex(monitor.ValidationError, "advertised"):
            monitor.validate_candidate(
                monitor.Candidate.create("DP-1", 1920, 1080, "59.95", "1.25"),
                topology,
            )

    def test_scale_validation_uses_range_and_120th_preflight(self) -> None:
        for value in ("0.5", "1", "1.2", "1.25", "4"):
            monitor.Candidate.create("DP-1", 1920, 1080, "60", value)
        for value in ("0.49", "4.01", "1.234", "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(monitor.ValidationError):
                    monitor.Candidate.create("DP-1", 1920, 1080, "60", value)

    def test_refresh_matching_respects_two_decimal_catalogue_precision(self) -> None:
        mode_6000 = monitor.Mode(1920, 1080, 60000)
        mode_5994 = monitor.Mode(1920, 1080, 59940)
        mode_5995 = monitor.Mode(1920, 1080, 59950)
        self.assertTrue(monitor._selected_refresh_matches(60000, mode_6000, (mode_6000,)))
        self.assertTrue(monitor._selected_refresh_matches(59940, mode_5994, (mode_5994,)))
        self.assertTrue(
            monitor._selected_refresh_matches(59944, mode_5994, (mode_5994, mode_5995))
        )
        self.assertFalse(
            monitor._selected_refresh_matches(59945, mode_5994, (mode_5994, mode_5995))
        )
        self.assertFalse(
            monitor._selected_refresh_matches(59945, mode_5995, (mode_5994, mode_5995))
        )
        self.assertFalse(
            monitor._selected_refresh_matches(59990, mode_6000, (mode_6000,))
        )

    def test_duplicate_catalogue_entries_are_one_selectable_mode(self) -> None:
        topology = monitor.parse_monitor_payload(
            [
                output(
                    width=1920,
                    height=1080,
                    refresh=59.943,
                    available=[
                        "1920x1080@59.94Hz",
                        "1920x1080@59.94Hz",
                    ],
                )
            ]
        )
        target = topology.target("DP-1")
        requested = monitor.Mode(1920, 1080, 59940)
        self.assertEqual(target.canonical_advertised_modes(), (requested,))
        self.assertTrue(
            monitor._selected_refresh_matches(
                target.refresh_millihz, requested, target.advertised_modes
            )
        )

    def test_production_command_runner_has_explicit_timeout(self) -> None:
        timeout = monitor.subprocess.TimeoutExpired([monitor.HYPRCTL], 5)
        with mock.patch.object(monitor.subprocess, "run", side_effect=timeout) as run:
            result = monitor.run_command([monitor.HYPRCTL, "--help"])
        self.assertEqual(result.returncode, monitor.COMMAND_TIMEOUT_RETURN_CODE)
        self.assertIn("timed out after 5 seconds", result.stderr)
        self.assertEqual(run.call_args.kwargs["timeout"], monitor.COMMAND_TIMEOUT_SECONDS)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_candidate_protocol_rejects_out_of_scope_fields(self) -> None:
        request = {
            "version": 1,
            "command": "begin",
            "signature": "fixture_123",
            "candidate": {
                "connector": "DP-1",
                "width": 1920,
                "height": 1080,
                "refresh": "60",
                "scale": "1.5",
                "position": "0x0",
            },
        }
        authority, _ = self.authority([])
        with self.assertRaises(monitor.JournalError):
            monitor.handle_control(authority, request)

    def test_journal_is_strict_versioned_atomic_and_private(self) -> None:
        _, _, journal = self.begin_success()
        metadata = self.store.journal_path.stat()
        self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
        self.assertEqual(self.store.read(), journal)
        leftovers = list(self.store.directory.glob(".transaction.json.vanhyprarch-monitor.*"))
        self.assertEqual(leftovers, [])

        payload = json.loads(self.store.journal_path.read_text())
        payload["unknown"] = True
        self.store.journal_path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(monitor.JournalError, "schema mismatch"):
            self.store.read()

    def test_unknown_and_malformed_journal_versions_fail_closed(self) -> None:
        self.begin_success()
        original = json.loads(self.store.journal_path.read_text())
        cases = [
            {**original, "schema_version": 2},
            {**original, "state": "surprise"},
            {**original, "mutation_attempted": "yes"},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.store.journal_path.write_text(json.dumps(payload))
                self.store.journal_path.chmod(0o600)
                with self.assertRaises(monitor.JournalError):
                    self.store.read()

    def test_truncated_journal_fails_closed(self) -> None:
        self.begin_success()
        self.store.journal_path.write_text('{"schema_version":1')
        self.store.journal_path.chmod(0o600)
        with self.assertRaisesRegex(monitor.JournalError, "cannot read"):
            self.store.read()

    def test_journal_with_broad_permissions_fails_closed(self) -> None:
        self.begin_success()
        self.store.journal_path.chmod(0o644)
        with self.assertRaisesRegex(monitor.JournalError, "0600"):
            self.store.read()

    def test_single_transaction_locking(self) -> None:
        other = monitor.RuntimeStore(self.runtime)
        with self.assertRaises(monitor.ConcurrentTransaction):
            other.acquire()
        self.store.release()
        other.acquire()
        other.release()

    def test_stale_nonterminal_transaction_rejects_new_begin(self) -> None:
        authority, _, _ = self.begin_success()
        with self.assertRaises(monitor.StaleTransaction):
            authority.begin(self.candidate, self.instance.signature)

    def test_connector_identity_validation_and_inactive_target(self) -> None:
        topology = monitor.parse_monitor_payload([output(), inactive_output()])
        with self.assertRaisesRegex(monitor.ValidationError, "inactive"):
            monitor.validate_candidate(
                monitor.Candidate.create("HDMI-A-1", 1920, 1080, "60", "1"),
                topology,
            )
        with self.assertRaisesRegex(monitor.ValidationError, "does not exist"):
            monitor.validate_candidate(
                monitor.Candidate.create("DP-9", 1920, 1080, "60", "1"),
                topology,
            )

    def test_service_bound_signature_rejects_another_instance(self) -> None:
        runner = QueueRunner([])
        authority = monitor.TransactionAuthority(
            self.store,
            self.provider,
            self.paths,
            runner=runner,
            clock=self.clock,
            bound_signature=self.instance.signature,
        )
        with self.assertRaisesRegex(monitor.ValidationError, "service-bound"):
            authority.begin(self.candidate, "different_instance")
        self.assertEqual(runner.calls, [])

    def test_successful_apply_requires_authoritative_readback(self) -> None:
        _, runner, journal = self.begin_success()
        self.assertTrue(journal.runtime_verified)
        self.assertAlmostEqual(journal.deadline_monotonic, 110.0)
        self.assertEqual(runner.calls[1][:4], [monitor.HYPRCTL, "--instance", "fixture_123", "eval"])
        self.assertIn('output = "DP-1"', runner.calls[1][-1])
        self.assertIn('mode = "1920x1080@60"', runner.calls[1][-1])
        self.assertIn("scale = 1.5", runner.calls[1][-1])
        fields = set(
            re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=", runner.calls[1][-1])
        )
        self.assertEqual(fields, {"output", "mode", "scale"})
        self.assertEqual(runner.calls[2][-3:], ["-j", "monitors", "all"])

    def test_catch_all_only_profile_cannot_reach_runtime_apply(self) -> None:
        self.machine.write_bytes(
            b'''hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = "auto",
})
'''
        )
        self.machine.chmod(0o600)
        authority, runner = self.authority([[output()]])
        with self.assertRaisesRegex(monitor.ValidationError, "existing explicit"):
            authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 0)

    def test_desc_only_profile_cannot_reach_runtime_apply(self) -> None:
        self.machine.write_bytes(
            machine_configuration().replace(
                b'output = "DP-1"', b'output = "desc:Example"'
            )
        )
        self.machine.chmod(0o600)
        authority, runner = self.authority([[output()]])
        with self.assertRaisesRegex(monitor.ValidationError, "description-addressed"):
            authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 0)

    def assert_failed_apply_rolls_back(self, wrong: dict[str, object]) -> None:
        authority, runner = self.authority(
            [[output()], OK, [wrong], [wrong], [wrong], OK, [output()]]
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(journal.state, "reverted", journal.failure)
        eval_calls = [call for call in runner.calls if "eval" in call]
        self.assertEqual(len(eval_calls), 2)
        self.assertIn('mode = "2560x1440@59.95"', eval_calls[-1][-1])
        self.assertIn("scale = 1.25", eval_calls[-1][-1])

    def test_ok_followed_by_wrong_mode_rolls_back(self) -> None:
        self.assert_failed_apply_rolls_back(output(scale=1.5))

    def test_ok_followed_by_wrong_scale_rolls_back(self) -> None:
        self.assert_failed_apply_rolls_back(
            output(width=1920, height=1080, refresh=60.0, scale=1.25)
        )

    def test_failed_apply_command_still_attempts_bounded_rollback(self) -> None:
        rejected = monitor.CommandResult(1, "", "invalid monitor rule")
        authority, runner = self.authority(
            [[output()], rejected, [output()], OK, [output()]]
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(journal.state, "reverted")
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 2)

    def test_timed_out_apply_enters_verified_rollback(self) -> None:
        timed_out = monitor.CommandResult(
            monitor.COMMAND_TIMEOUT_RETURN_CODE,
            "",
            "command timed out after 5 seconds",
        )
        authority, runner = self.authority(
            [[output()], timed_out, [output()], OK, [output()]]
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(journal.state, "reverted")
        self.assertIn("timed out", journal.failure)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 2)

    def test_unexpected_protected_field_drift_rolls_back(self) -> None:
        drift = candidate_output()
        drift["transform"] = 1
        self.assert_failed_apply_rolls_back(drift)

    def test_reserved_area_drift_rolls_back(self) -> None:
        drift = candidate_output()
        drift["reserved"] = [0, 0, 32, 0]
        self.assert_failed_apply_rolls_back(drift)

    def test_reordered_equivalent_mode_catalogue_is_not_drift(self) -> None:
        original = output(
            available=[
                "2560x1440@59.95Hz",
                "1920x1080@60.00Hz",
                "1920x1080@60.00Hz",
            ]
        )
        applied = candidate_output()
        applied["availableModes"] = [
            "1920x1080@60.00Hz",
            "2560x1440@59.95Hz",
        ]
        snapshot = monitor.parse_monitor_payload([original])
        readback = monitor.parse_monitor_payload([applied])
        monitor.verify_candidate_readback(
            snapshot,
            self.candidate,
            readback,
            snapshot.target("DP-1").identity,
        )

    def test_genuinely_changed_mode_catalogue_is_protected_drift(self) -> None:
        snapshot = monitor.parse_monitor_payload([output()])
        applied = candidate_output()
        applied["availableModes"] = ["1920x1080@60.00Hz"]
        readback = monitor.parse_monitor_payload([applied])
        with self.assertRaisesRegex(monitor.ValidationError, "protected"):
            monitor.verify_candidate_readback(
                snapshot,
                self.candidate,
                readback,
                snapshot.target("DP-1").identity,
            )

    def test_topology_change_and_hotplug_roll_back(self) -> None:
        extra = output(name="DP-2", make="Second", model="Panel", serial="SECOND", x=2560)
        wrong = [candidate_output(), extra]
        authority, _ = self.authority(
            [[output()], OK, wrong, wrong, wrong, OK, [output()]]
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(journal.state, "reverted")
        self.assertIn("topology changed", journal.failure)

    def test_multi_output_snapshot_preserves_unselected_output(self) -> None:
        second = output(
            name="DP-2", make="Second", model="Panel", serial="SECOND", x=2560
        )
        second["id"] = 1
        candidate = candidate_output()
        authority, runner = self.authority(
            [[output(), second], OK, [candidate, second]]
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(journal.state, "temporary-active")
        self.assertEqual(len(journal.snapshot.monitors), 2)
        runner.responses.extend([[candidate, second], OK, [output(), second]])
        reverted = authority.rollback(journal.transaction_id)
        self.assertEqual(reverted.state, "reverted")

    def test_topology_comparison_ignores_array_order_and_monitor_ids(self) -> None:
        first = output()
        second = output(
            name="DP-2", make="Second", model="Panel", serial="SECOND", x=2560
        )
        second["id"] = 1
        applied = candidate_output()
        applied["id"] = 9
        reordered_second = dict(second)
        reordered_second["id"] = 4
        snapshot = monitor.parse_monitor_payload([first, second])
        readback = monitor.parse_monitor_payload([reordered_second, applied])
        monitor.verify_candidate_readback(
            snapshot,
            self.candidate,
            readback,
            snapshot.target("DP-1").identity,
        )

    def test_manual_rollback_uses_targeted_eval_and_verifies(self) -> None:
        authority, runner, journal = self.begin_success()
        runner.responses.extend([[candidate_output()], OK, [output()]])
        reverted = authority.rollback(journal.transaction_id)
        self.assertEqual(reverted.state, "reverted")
        self.assertFalse(reverted.recovery_required)
        self.assertIn('output = "DP-1"', runner.calls[-2][-1])
        self.assertNotIn("reload", " ".join(runner.calls[-2]))
        fields = set(
            re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=", runner.calls[-2][-1])
        )
        self.assertEqual(fields, {"output", "mode", "scale"})

    def test_timeout_is_backend_monotonic_rollback(self) -> None:
        authority, runner, journal = self.begin_success()
        runner.responses.extend([[candidate_output()], OK, [output()]])
        self.clock.advance(11)
        reverted = authority.status()
        self.assertIsNotNone(reverted)
        self.assertEqual(reverted.state, "reverted")
        self.assertIn("deadline expired", reverted.failure)

    def test_rollback_verification_failure_remains_recoverable(self) -> None:
        authority, runner, journal = self.begin_success()
        runner.responses.extend(
            [[candidate_output()], OK, [candidate_output()], [candidate_output()]]
        )
        failed = authority.rollback(journal.transaction_id)
        self.assertEqual(failed.state, "rollback-failed")
        self.assertTrue(failed.recovery_required)

    def test_connector_name_reuse_never_receives_snapshot(self) -> None:
        authority, runner, journal = self.begin_success()
        replacement = candidate_output()
        replacement.update(
            {
                "make": "Other",
                "model": "Replacement",
                "serialNumber": "DIFFERENT",
                "description": "Other Replacement DIFFERENT",
            }
        )
        runner.responses.append([replacement])
        failed = authority.rollback(journal.transaction_id)
        self.assertEqual(failed.state, "rollback-failed")
        eval_calls = [call for call in runner.calls if "eval" in call]
        self.assertEqual(len(eval_calls), 1)

    def test_hyprland_instance_replacement_is_not_followed(self) -> None:
        authority, runner, journal = self.begin_success()
        self.provider.identity = replace(self.instance, pid=999)
        vanished = authority.rollback(journal.transaction_id)
        self.assertEqual(vanished.state, "instance-vanished")
        self.assertFalse(vanished.recovery_required)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 1)

    def test_disappeared_bound_instance_is_terminal_and_not_retried(self) -> None:
        authority, runner, journal = self.begin_success()
        self.provider.identity = monitor.HyprlandUnavailable("gone")
        vanished = authority.rollback(journal.transaction_id)
        self.assertEqual(vanished.state, "instance-vanished")
        self.assertFalse(vanished.recovery_required)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 1)

    def test_crash_recovery_entry_point_and_idempotence(self) -> None:
        authority, runner, journal = self.begin_success()
        runner.responses.extend([[candidate_output()], OK, [output()]])
        recovered = authority.recover()
        self.assertEqual(recovered.state, "reverted")
        call_count = len(runner.calls)
        repeated = authority.recover()
        self.assertEqual(repeated.state, "reverted")
        self.assertEqual(len(runner.calls), call_count)

    def test_timed_out_recovery_remains_armed_and_can_retry(self) -> None:
        authority, runner, journal = self.begin_success()
        timed_out = monitor.CommandResult(
            monitor.COMMAND_TIMEOUT_RETURN_CODE,
            "",
            "command timed out after 5 seconds",
        )
        runner.responses.append(timed_out)
        failed = authority.recover()
        self.assertEqual(failed.state, "rollback-failed")
        self.assertTrue(failed.recovery_required)
        runner.responses.extend([[candidate_output()], OK, [output()]])
        recovered = authority.recover()
        self.assertEqual(recovered.state, "reverted")
        self.assertFalse(recovered.recovery_required)

    def test_recover_is_no_op_after_committed_terminal_state(self) -> None:
        persister = monitor.MachineConfigPersister(lambda content: None)
        authority, runner, journal = self.begin_success(persister=persister)
        runner.responses.extend([[candidate_output()], [candidate_output()]])
        committed = authority.confirm(journal.transaction_id)
        self.assertEqual(committed.state, "committed")
        call_count = len(runner.calls)
        repeated = authority.recover()
        self.assertEqual(repeated.state, "committed")
        self.assertEqual(len(runner.calls), call_count)

    def test_pre_mutation_crash_recovery_needs_no_runtime_command(self) -> None:
        authority, runner, journal = self.begin_success()
        preparing = replace(
            journal,
            state="preparing",
            sequence=0,
            mutation_attempted=False,
            runtime_verified=False,
            deadline_monotonic=None,
        )
        self.store.write(preparing)
        call_count = len(runner.calls)
        recovered = authority.recover()
        self.assertEqual(recovered.state, "reverted")
        self.assertEqual(len(runner.calls), call_count)

    def test_confirm_state_transition_with_fixture_persistence(self) -> None:
        verified: list[bytes] = []
        persister = monitor.MachineConfigPersister(verified.append)
        authority, runner, journal = self.begin_success(persister=persister)
        runner.responses.extend([[candidate_output()], [candidate_output()]])
        committed = authority.confirm(journal.transaction_id)
        self.assertEqual(committed.state, "committed")
        self.assertTrue(committed.persistence_verified)
        self.assertFalse(committed.recovery_required)
        self.assertEqual(len(verified), 1)
        after = self.machine.read_text()
        self.assertIn('mode = "1920x1080@60"', after)
        self.assertIn("local vanhyprarchMonitorScale = 1.5", after)
        self.assertEqual(stat.S_IMODE(self.machine.stat().st_mode), 0o600)

    def test_production_confirm_boundary_reverts_instead_of_persisting(self) -> None:
        authority, runner, journal = self.begin_success()
        runner.responses.extend(
            [[candidate_output()], [candidate_output()], OK, [output()]]
        )
        before = self.machine.read_bytes()
        reverted = authority.confirm(journal.transaction_id)
        self.assertEqual(reverted.state, "reverted")
        self.assertEqual(self.machine.read_bytes(), before)
        self.assertIn("deferred to Phase B2", reverted.failure)

    def test_persistence_detects_external_machine_hash_race(self) -> None:
        persister = monitor.MachineConfigPersister(lambda content: None)
        _, _, journal = self.begin_success(persister=persister)
        self.machine.write_bytes(self.machine.read_bytes() + b"-- external edit\n")
        with self.assertRaisesRegex(monitor.PersistenceError, "changed"):
            persister.prepare(journal)

    def test_persistence_detects_external_override_hash_race(self) -> None:
        persister = monitor.MachineConfigPersister(lambda content: None)
        _, _, journal = self.begin_success(persister=persister)
        self.override.write_bytes(b"-- externally changed override\n")
        with self.assertRaisesRegex(monitor.PersistenceError, "override changed"):
            persister.prepare(journal)

    def test_persistence_preserves_unrelated_machine_bytes_and_catch_all(self) -> None:
        before = self.machine.read_bytes()
        snapshot = monitor.snapshot_file(self.machine)
        topology = monitor.parse_monitor_payload([output()])
        journal = monitor.TransactionJournal(
            1,
            "fixture",
            "temporary-active",
            1,
            1.0,
            1.0,
            10.0,
            None,
            True,
            True,
            False,
            True,
            None,
            self.instance,
            topology.target("DP-1").identity,
            self.candidate,
            topology,
            snapshot,
            monitor.snapshot_file(self.override),
        )
        persister = monitor.MachineConfigPersister(lambda content: None)
        changed, _ = persister.prepare(journal)
        self.assertIn(b'output = ""', changed)
        self.assertIn(b'mode = "preferred"', changed)
        self.assertIn(b'scale = "auto"', changed)
        self.assertIn(b"-- unrelated machine content", changed)
        restored_owned = changed.replace(b'"1920x1080@60"', b'"2560x1440@59.95"').replace(
            b"vanhyprarchMonitorScale = 1.5", b"vanhyprarchMonitorScale = 1.25"
        )
        self.assertEqual(restored_owned, before)

    def test_no_catch_all_modification_or_automatic_profile_creation(self) -> None:
        catch_all_only = b'''hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = "auto",
})
'''
        with self.assertRaisesRegex(monitor.ValidationError, "existing explicit"):
            monitor.rewrite_existing_profile(catch_all_only, self.candidate)
        self.assertEqual(
            catch_all_only,
            b'''hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = "auto",
})
''',
        )

    def test_ambiguous_explicit_profile_is_rejected(self) -> None:
        duplicate = machine_configuration() + machine_configuration()
        with self.assertRaisesRegex(monitor.ValidationError, "ambiguous"):
            monitor.require_explicit_profile(duplicate, "DP-1")

    def test_user_override_cannot_supersede_transaction_profile(self) -> None:
        self.override.write_bytes(
            b'''hl.monitor({
    output = "DP-1",
    mode = "preferred",
    scale = 1,
})
'''
        )
        self.override.chmod(0o600)
        authority, runner = self.authority([[output()]])
        with self.assertRaisesRegex(monitor.ValidationError, "supersedes"):
            authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 0)

    def test_machine_and_override_exact_bytes_are_in_journal(self) -> None:
        _, _, journal = self.begin_success()
        self.assertEqual(journal.machine_file.content, machine_configuration())
        self.assertEqual(journal.override_file.content, b"-- user override\n")
        self.assertEqual(journal.machine_file.mode, 0o600)
        self.assertGreater(journal.machine_file.inode, 0)

    def test_service_is_static_bounded_and_has_recovery_hook(self) -> None:
        unit = UNIT.read_text()
        self.assertNotIn("[Install]", unit)
        self.assertIn("RuntimeMaxSec=90s", unit)
        self.assertIn("ExecStopPost=%h/.local/bin/vanhyprarch-monitor recover", unit)
        self.assertIn("TimeoutStopSec=30s", unit)
        self.assertIn("UMask=0077", unit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
