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
import threading
import time
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
        "serial": serial,
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
        "sdrBrightness": 1,
        "sdrSaturation": 1,
        "sdrMinLuminance": 0.2,
        "sdrMaxLuminance": 80,
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


def captured_hyprland_0562_output() -> dict[str, object]:
    return {
        "id": 1,
        "name": "DP-1",
        "description": "LG Electronics LG ULTRAFINE 301MALFM3V64",
        "make": "LG Electronics",
        "model": "LG ULTRAFINE",
        "serial": "301MALFM3V64",
        "width": 3840,
        "height": 2160,
        "physicalWidth": 600,
        "physicalHeight": 340,
        "refreshRate": 60.0,
        "x": 0,
        "y": 0,
        "activeWorkspace": {"id": 1, "name": "1"},
        "specialWorkspace": {"id": 0, "name": ""},
        "reserved": [56, 0, 0, 0],
        "scale": 1.25,
        "transform": 0,
        "focused": True,
        "dpmsStatus": True,
        "vrr": False,
        "solitary": "0",
        "solitaryBlockedBy": ["WINDOWED", "CANDIDATE"],
        "activelyTearing": False,
        "tearingBlockedBy": ["NOT_TORN", "USER", "CANDIDATE", "HW_CURSOR"],
        "directScanoutTo": "0",
        "directScanoutBlockedBy": ["USER", "CANDIDATE"],
        "disabled": False,
        "currentFormat": "XRGB2101010",
        "mirrorOf": "none",
        "availableModes": [
            "3840x2160@60.00Hz",
            "3840x2160@29.98Hz",
            "2560x1440@59.95Hz",
            "1920x1080@60.00Hz",
            "1920x1080@60.00Hz",
            "1920x1080@59.94Hz",
            "1280x720@60.00Hz",
            "1280x720@59.94Hz",
            "1024x768@60.00Hz",
            "800x600@60.32Hz",
            "720x480@60.00Hz",
            "720x480@59.94Hz",
            "640x480@60.00Hz",
            "640x480@59.94Hz",
            "640x480@59.94Hz",
        ],
        "colorManagementPreset": "wide",
        "sdrBrightness": 1,
        "sdrSaturation": 1,
        "sdrMinLuminance": 0.2,
        "sdrMaxLuminance": 80,
        "hardwareCursorsInUse": True,
    }


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


class RecordingVerifier:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[object, bytes]] = []
        self.error = error

    def __call__(self, journal: object, content: bytes) -> None:
        self.calls.append((journal, content))
        if self.error is not None:
            raise self.error


class FakeReloadWatch:
    def __init__(self, events: list[bool] | None = None) -> None:
        self.events = list(events if events is not None else [True])
        self.closed = False

    def wait(self, timeout: float) -> bool:
        if not self.events:
            return False
        return self.events.pop(0)

    def close(self) -> None:
        self.closed = True


class ControlledReloadWatch:
    def __init__(self) -> None:
        self.pending = 0
        self.closed = False

    def emit(self) -> None:
        self.pending += 1

    def wait(self, timeout: float) -> bool:
        if self.pending == 0:
            return False
        self.pending -= 1
        return True

    def close(self) -> None:
        self.closed = True


class ControlledReloadEventSource:
    def __init__(self) -> None:
        self.watches: list[ControlledReloadWatch] = []

    def arm(self, journal: object) -> ControlledReloadWatch:
        watch = ControlledReloadWatch()
        self.watches.append(watch)
        return watch

    @property
    def current(self) -> ControlledReloadWatch:
        return self.watches[-1]


class FakeReloadCoordinator:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.watches: list[FakeReloadWatch] = []
        self.arm_phases: list[str] = []
        self.reconciliations: list[str] = []

    def arm(self, journal: object) -> FakeReloadWatch:
        self.arm_phases.append(journal.persistence_phase)
        watch = FakeReloadWatch()
        self.watches.append(watch)
        return watch

    def reconcile(
        self, journal: object, client: object, watch: FakeReloadWatch,
    ) -> None:
        self.reconciliations.append(journal.persistence_phase)
        if self.error is not None:
            raise self.error


class SequenceReloadCoordinator(FakeReloadCoordinator):
    def __init__(self, outcomes: list[Exception | None]) -> None:
        super().__init__()
        self.outcomes = list(outcomes)

    def reconcile(
        self, journal: object, client: object, watch: FakeReloadWatch,
    ) -> None:
        self.reconciliations.append(journal.persistence_phase)
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome


class StubCandidatePersister:
    def __init__(self, state: str = "candidate") -> None:
        self.state = state

    def prepare(self, journal: object) -> tuple[bytes, str]:
        raise AssertionError("recovery must not prepare a new candidate")

    def persist(self, journal: object, content: bytes, guard=None) -> None:
        raise AssertionError("recovery must not rewrite the candidate")

    def machine_state(self, journal: object) -> str:
        return self.state

    def recover_original(self, journal: object) -> bool:
        self.state = "original"
        return True


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
        reload_coordinator: object | None = None,
        reload_event_source: object | None = None,
    ) -> tuple[object, QueueRunner]:
        runner = QueueRunner(responses)
        authority = monitor.TransactionAuthority(
            self.store,
            self.provider,
            self.paths,
            runner=runner,
            clock=self.clock,
            persister=persister,
            reload_coordinator=reload_coordinator
            or (FakeReloadCoordinator() if persister is not None else None),
            reload_event_source=reload_event_source,
        )
        return authority, runner

    def begin_success(
        self, *, persister: object | None = None,
        reload_event_source: object | None = None,
    ) -> tuple[object, QueueRunner, object]:
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_event_source=reload_event_source,
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

    def test_exact_observable_color_state_is_protected_and_extras_are_ignored(self) -> None:
        raw = output()
        raw["colorManagementPreset"] = "wide"
        raw["sdrBrightness"] = 1.2
        raw["sdrSaturation"] = 0.9
        raw["sdrMinLuminance"] = 0.1
        raw["sdrMaxLuminance"] = 120.0
        raw["futureUnrelatedField"] = {"may": "be ignored"}
        parsed = monitor.parse_monitor_payload([raw]).target("DP-1")
        self.assertEqual(
            parsed.color_state,
            {
                "colorManagementPreset": "wide",
                "sdrBrightness": 1.2,
                "sdrSaturation": 0.9,
                "sdrMinLuminance": 0.1,
                "sdrMaxLuminance": 120.0,
            },
        )

    def test_captured_hyprland_0562_schema_parses_and_validates_read_only(self) -> None:
        runner = QueueRunner([[captured_hyprland_0562_output()]])
        client = monitor.HyprlandClient(
            self.instance.signature,
            self.instance,
            self.provider,
            runner=runner,
            clock=self.clock,
        )
        topology = client.read_topology()
        target = topology.target("DP-1")
        self.assertEqual(target.identity.serial, "301MALFM3V64")
        self.assertEqual(target.identity.make, "LG Electronics")
        self.assertEqual(target.identity.model, "LG ULTRAFINE")
        self.assertEqual(target.reserved, [56, 0, 0, 0])
        self.assertEqual(len(target.canonical_advertised_modes()), 13)
        candidate = monitor.Candidate.create(
            "DP-1", 3840, 2160, "60.00", "1.25"
        )
        self.assertEqual(monitor.validate_candidate(candidate, topology), target)
        self.assertEqual(runner.calls, [monitor.monitors_argv(self.instance.signature)])
        self.assertNotIn("eval", runner.calls[0])

    def test_v0562_serial_contract_is_strict(self) -> None:
        missing = output()
        del missing["serial"]
        invented = {**missing, "serialNumber": "ABC123"}
        malformed = {**output(), "serial": 123}
        for value in (missing, invented, malformed):
            with self.subTest(value=value):
                with self.assertRaises(monitor.ValidationError):
                    monitor.parse_monitor_payload([value])

    def test_safety_critical_monitor_fields_are_strictly_typed(self) -> None:
        cases = [
            {**output(), "vrr": 0},
            {**output(), "reserved": [0, 0, 0]},
            {**output(), "reserved": [False, 0, 0, 0]},
            {**output(), "mirrorOf": "DP-2"},
            {**output(), "colorManagementPreset": None},
            {**output(), "sdrBrightness": "bright"},
            {key: value for key, value in output().items() if key != "dpmsStatus"},
            {key: value for key, value in output().items() if key != "sdrMaxLuminance"},
        ]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(monitor.ValidationError):
                    monitor.parse_monitor_payload([value])

    def test_malformed_monitor_data_fails_closed(self) -> None:
        cases = [
            {},
            {**output(), "refreshRate": "fast"},
            {**output(), "availableModes": ["not-a-mode"]},
            {**output(), "make": "", "model": "", "serial": "", "description": ""},
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

        with mock.patch.object(
            monitor.subprocess, "run", side_effect=timeout
        ) as verify_run:
            verify_result = monitor.run_verify_command(["/usr/bin/Hyprland"])
        self.assertEqual(
            verify_result.returncode, monitor.COMMAND_TIMEOUT_RETURN_CODE
        )
        self.assertEqual(
            verify_run.call_args.kwargs["timeout"],
            monitor.VERIFY_CONFIG_TIMEOUT_SECONDS,
        )

    def test_real_unix_control_socket_accepts_pathlike_runtime_address(self) -> None:
        runtime = self.root / "socket-runtime"
        runtime.mkdir(mode=0o700)
        store = monitor.RuntimeStore(runtime)
        store.acquire()
        clock = FakeClock()
        runner = QueueRunner([])
        authority = monitor.TransactionAuthority(
            store,
            self.provider,
            self.paths,
            runner=runner,
            clock=clock,
        )
        result: list[int] = []
        errors: list[BaseException] = []

        def run_server() -> None:
            try:
                result.append(monitor.serve())
            except BaseException as error:
                errors.append(error)

        self.assertIsInstance(store.socket_path, Path)
        with (
            mock.patch.object(
                monitor, "build_production_authority", return_value=authority
            ),
            mock.patch.dict(
                monitor.os.environ, {"XDG_RUNTIME_DIR": str(runtime)}, clear=False
            ),
        ):
            server = threading.Thread(target=run_server)
            server.start()
            try:
                readiness_deadline = time.monotonic() + 2.0
                while (
                    not store.socket_path.exists()
                    and time.monotonic() < readiness_deadline
                ):
                    time.sleep(0.01)
                self.assertTrue(
                    store.socket_path.is_socket(),
                    f"server did not create socket: errors={errors!r}, result={result!r}",
                )
                self.assertEqual(stat.S_IMODE(store.socket_path.stat().st_mode), 0o600)
                response = monitor.send_control({"version": 1, "command": "status"})
                self.assertEqual(
                    response,
                    {"version": 1, "ok": True, "status": {"state": "idle"}},
                )
                self.assertEqual(runner.calls, [])
            finally:
                clock.advance(16.0)
                server.join(timeout=2.0)

        self.assertFalse(server.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result, [0])
        self.assertFalse(store.socket_path.exists())

    def test_socket_reload_watch_supports_nonblocking_event_poll(self) -> None:
        path = self.root / "reload-events.sock"
        server = monitor.socket.socket(monitor.socket.AF_UNIX, monitor.socket.SOCK_STREAM)
        server.bind(os.fspath(path))
        server.listen(1)
        watch = monitor.SocketReloadWatch(path)
        connection, _ = server.accept()
        try:
            self.assertFalse(watch.wait(0.0))
            connection.sendall(b"configreloaded>>\n")
            self.assertTrue(watch.wait(0.0))
        finally:
            connection.close()
            watch.close()
            server.close()

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
            {**original, "schema_version": 3},
            {**original, "state": "surprise"},
            {**original, "mutation_attempted": "yes"},
            {**original, "persistence_phase": "invented"},
            {
                **original,
                "state": "committing",
                "deadline_monotonic": None,
                "persistence_phase": "original",
            },
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.store.journal_path.write_text(json.dumps(payload))
                self.store.journal_path.chmod(0o600)
                with self.assertRaises(monitor.JournalError):
                    self.store.read()

    def test_terminal_schema_v1_journal_is_not_reinterpreted_by_v2(self) -> None:
        _, _, journal = self.begin_success()
        legacy = monitor.journal_to_dict(
            replace(
                journal,
                state="reverted",
                deadline_monotonic=None,
                runtime_verified=True,
                recovery_required=False,
            )
        )
        legacy["schema_version"] = 1
        del legacy["persistence_phase"]
        self.store.journal_path.write_text(json.dumps(legacy))
        self.store.journal_path.chmod(0o600)
        authority, runner = self.authority([])
        for operation in (authority.status, authority.recover):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(monitor.JournalError, "schema mismatch"):
                    operation()
        self.assertEqual(runner.calls, [])

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

    def test_external_reload_while_applying_invalidates_and_rolls_back(self) -> None:
        events = ControlledReloadEventSource()
        queued = QueueRunner(
            [[output()], OK, [candidate_output()], OK, [output()]]
        )

        def emitting_runner(argv: object) -> object:
            result = queued(argv)
            if "eval" in argv and len([call for call in queued.calls if "eval" in call]) == 1:
                events.current.emit()
            return result

        authority = monitor.TransactionAuthority(
            self.store,
            self.provider,
            self.paths,
            runner=emitting_runner,
            clock=self.clock,
            reload_event_source=events,
        )
        reverted = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(reverted.state, "reverted")
        self.assertIn("config reload invalidated", reverted.failure)
        self.assertEqual(len([call for call in queued.calls if "eval" in call]), 2)
        self.assertTrue(events.current.closed)

    def test_reload_observer_failure_prevents_runtime_apply(self) -> None:
        class FailingReloadEventSource:
            def arm(inner_self, journal):
                raise monitor.PersistenceError("fixture socket unavailable")

        authority, runner = self.authority(
            [[output()]], reload_event_source=FailingReloadEventSource()
        )
        reverted = authority.begin(self.candidate, self.instance.signature)
        self.assertEqual(reverted.state, "reverted")
        self.assertFalse(reverted.mutation_attempted)
        self.assertIn("reload observation failed", reverted.failure)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 0)

    def test_external_reload_while_temporary_active_invalidates_even_if_readback_matches(self) -> None:
        events = ControlledReloadEventSource()
        current_candidate = monitor.Candidate.create(
            "DP-1", 2560, 1440, "59.95", "1.25"
        )
        authority, runner = self.authority(
            [[output()], OK, [output()]], reload_event_source=events
        )
        active = authority.begin(current_candidate, self.instance.signature)
        self.assertEqual(active.state, "temporary-active")
        events.current.emit()
        runner.responses.extend([[output()], OK, [output()]])
        reverted = authority.status()
        self.assertIsNotNone(reverted)
        self.assertEqual(reverted.state, "reverted")
        self.assertIn("config reload invalidated", reverted.failure)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 2)

    def test_reload_immediately_before_confirm_cannot_persist(self) -> None:
        events = ControlledReloadEventSource()
        verifier = RecordingVerifier()
        persister = monitor.MachineConfigPersister(verifier)
        authority, runner, active = self.begin_success(
            persister=persister, reload_event_source=events
        )
        events.current.emit()
        runner.responses.extend([[candidate_output()], OK, [output()]])
        with self.assertRaisesRegex(monitor.ValidationError, "cannot confirm from reverted"):
            authority.confirm(active.transaction_id)
        reverted = self.store.read()
        self.assertIsNotNone(reverted)
        self.assertEqual(reverted.state, "reverted")
        self.assertIn("config reload invalidated", reverted.failure)
        self.assertEqual(verifier.calls, [])
        self.assertEqual(self.machine.read_bytes(), active.machine_file.content)

    def test_confirm_revalidates_transaction_id_and_deadline_before_persistence(self) -> None:
        verifier = RecordingVerifier()
        persister = monitor.MachineConfigPersister(verifier)
        authority, runner, active = self.begin_success(persister=persister)
        with self.assertRaisesRegex(monitor.ValidationError, "transaction ID"):
            authority.confirm("00000000-0000-0000-0000-000000000000")
        self.clock.advance(11.0)
        runner.responses.extend([[candidate_output()], OK, [output()]])
        with self.assertRaisesRegex(monitor.ValidationError, "cannot confirm from reverted"):
            authority.confirm(active.transaction_id)
        self.assertEqual(verifier.calls, [])
        self.assertEqual(self.store.read().state, "reverted")

    def test_reload_after_confirm_request_before_replace_aborts_write(self) -> None:
        events = ControlledReloadEventSource()
        before = self.machine.read_bytes()

        class EmitBeforeReplace(monitor.MachineConfigPersister):
            def persist(inner_self, journal, content, guard=None):
                events.current.emit()
                return super().persist(journal, content, guard)

        persister = EmitBeforeReplace(lambda journal, content: None)
        authority, runner, active = self.begin_success(
            persister=persister, reload_event_source=events
        )
        runner.responses.extend([[candidate_output()], [candidate_output()], OK, [output()]])
        reverted = authority.confirm(active.transaction_id)
        self.assertEqual(reverted.state, "reverted")
        self.assertIn("config reload invalidated", reverted.failure)
        self.assertEqual(self.machine.read_bytes(), before)

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
                "serial": "DIFFERENT",
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
        persister = monitor.MachineConfigPersister(lambda journal, content: None)
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
        verifier = RecordingVerifier()
        persister = monitor.MachineConfigPersister(verifier)
        coordinator = FakeReloadCoordinator()
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_coordinator=coordinator,
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        runner.responses.extend([[candidate_output()], [candidate_output()]])
        committed = authority.confirm(journal.transaction_id)
        self.assertEqual(committed.state, "committed")
        self.assertTrue(committed.persistence_verified)
        self.assertFalse(committed.recovery_required)
        self.assertEqual(len(verifier.calls), 1)
        self.assertEqual(
            coordinator.arm_phases,
            ["candidate-installed"],
        )
        self.assertEqual(
            coordinator.reconciliations,
            ["candidate-installed"],
        )
        self.assertEqual(committed.persistence_phase, "candidate-verified")
        after = self.machine.read_text()
        self.assertIn('mode = "1920x1080@60"', after)
        self.assertIn("local vanhyprarchMonitorScale = 1.5", after)
        self.assertEqual(stat.S_IMODE(self.machine.stat().st_mode), 0o600)

    def test_sandboxed_verifier_stages_complete_import_tree(self) -> None:
        hypr = self.config / "hypr"
        managed = hypr / "vanhyprarch"
        managed.mkdir(parents=True)
        (hypr / "hyprland.lua").write_text(
            'require(os.getenv("XDG_CONFIG_HOME") .. "/hypr/vanhyprarch/core.lua")\n'
            'require(os.getenv("XDG_CONFIG_HOME") .. "/vanhyprarch/machine/hyprland.lua")\n'
            'require(os.getenv("XDG_CONFIG_HOME") .. "/vanhyprarch/overrides/hyprland.lua")\n'
        )
        (managed / "core.lua").write_text("-- managed fixture\n")
        captured: dict[str, object] = {}

        def runner(argv: object) -> object:
            arguments = list(argv)
            stage = Path(arguments[arguments.index("/config") - 1])
            captured["argv"] = arguments
            captured["machine"] = (
                stage / "vanhyprarch/machine/hyprland.lua"
            ).read_bytes()
            captured["override"] = (
                stage / "vanhyprarch/overrides/hyprland.lua"
            ).read_bytes()
            captured["managed"] = (
                stage / "hypr/vanhyprarch/core.lua"
            ).read_bytes()
            return monitor.CommandResult(0, "config ok\n", "")

        _, _, journal = self.begin_success()
        candidate = monitor.rewrite_existing_profile(
            journal.machine_file.content, journal.candidate
        )
        verifier = monitor.SandboxedHyprlandVerifier(self.config, runner=runner)
        verifier(journal, candidate)
        self.assertEqual(captured["machine"], candidate)
        self.assertEqual(captured["override"], journal.override_file.content)
        self.assertEqual(captured["managed"], b"-- managed fixture\n")
        argv = captured["argv"]
        self.assertIn("--unshare-all", argv)
        self.assertIn("--die-with-parent", argv)
        self.assertIn("--new-session", argv)
        self.assertIn("--clearenv", argv)
        self.assertEqual(
            [argv[index + 1] for index, value in enumerate(argv) if value == "--setenv"],
            [
                "HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_RUNTIME_DIR",
                "PATH",
                "LANG",
            ],
        )
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", argv)
        self.assertNotIn("HYPRLAND_INSTANCE_SIGNATURE", argv)
        self.assertNotIn("WAYLAND_DISPLAY", argv)
        self.assertNotIn("DISPLAY", argv)
        self.assertEqual(argv[-4:], ["/usr/bin/Hyprland", "--verify-config", "--config", "/config/hypr/hyprland.lua"])

    def test_real_bubblewrap_verifier_blocks_live_session_channels(self) -> None:
        self.assertTrue(Path("/usr/bin/bwrap").is_file())
        self.assertTrue(Path("/usr/bin/Hyprland").is_file())
        hypr = self.config / "hypr"
        managed = hypr / "vanhyprarch"
        managed.mkdir(parents=True)
        (hypr / "hyprland.lua").write_text(
            'require(os.getenv("XDG_CONFIG_HOME") .. "/hypr/vanhyprarch/core.lua")\n'
        )
        marker = Path(
            f"/tmp/vanhyprarch-monitor-containment-{os.getpid()}-{time.time_ns()}"
        )
        marker.write_text("host-original\n")
        self.addCleanup(marker.unlink, missing_ok=True)
        signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "fixture_123")
        self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9_.-]+", signature))
        probe = f'''
for _, name in ipairs({{
    "DBUS_SESSION_BUS_ADDRESS",
    "HYPRLAND_INSTANCE_SIGNATURE",
    "WAYLAND_DISPLAY",
    "DISPLAY",
}}) do
    if os.getenv(name) ~= nil then
        error("LIVE_ENV_EXPOSED_" .. name)
    end
end
local marker = assert(io.open("{marker}", "w"))
marker:write("sandbox-only\\n")
marker:close()
local configWrite = io.open("/config/containment-write", "w")
if configWrite ~= nil then
    configWrite:close()
    error("STAGED_CONFIG_WRITABLE")
end
local busOk = os.execute("/usr/bin/systemctl --user show-environment >/tmp/bus-probe 2>&1")
if busOk == true or busOk == 0 then
    error("USER_BUS_REACHABLE")
end
local ipcOk = os.execute("/usr/bin/hyprctl --instance {signature} -j monitors all >/tmp/ipc-probe 2>&1")
if ipcOk == true or ipcOk == 0 then
    error("HYPRLAND_IPC_REACHABLE")
end
error("VANHYPRARCH_CONTAINMENT_PROBE_COMPLETE")
'''
        (managed / "core.lua").write_text(probe)
        _, _, journal = self.begin_success()
        verifier = monitor.SandboxedHyprlandVerifier(self.config)
        with self.assertRaisesRegex(
            monitor.PersistenceError, "VANHYPRARCH_CONTAINMENT_PROBE_COMPLETE"
        ):
            verifier(journal, journal.machine_file.content)
        self.assertEqual(marker.read_text(), "host-original\n")
        self.assertFalse((self.config / "containment-write").exists())

    def test_prospective_verifier_nonzero_and_timeout_fail_closed(self) -> None:
        hypr = self.config / "hypr"
        managed = hypr / "vanhyprarch"
        managed.mkdir(parents=True)
        (hypr / "hyprland.lua").write_text("-- loader\n")
        (managed / "core.lua").write_text("-- core\n")
        _, _, journal = self.begin_success()
        for result, message in (
            (monitor.CommandResult(1, "", "syntax error"), "syntax error"),
            (
                monitor.CommandResult(
                    monitor.COMMAND_TIMEOUT_RETURN_CODE, "", "timed out"
                ),
                "timed out after 5 seconds",
            ),
        ):
            with self.subTest(result=result):
                verifier = monitor.SandboxedHyprlandVerifier(
                    self.config, runner=lambda argv, result=result: result
                )
                with self.assertRaisesRegex(monitor.PersistenceError, message):
                    verifier(journal, journal.machine_file.content)

    def test_reload_event_observed_avoids_explicit_reload(self) -> None:
        runner = QueueRunner([monitor.CommandResult(0, "", "")])
        coordinator = monitor.HyprlandReloadCoordinator(self.runtime, runner)
        client = mock.Mock()
        watch = FakeReloadWatch([True])
        _, _, journal = self.begin_success()
        coordinator.reconcile(journal, client, watch)
        self.assertEqual(runner.calls, [monitor.configerrors_argv(self.instance.signature)])
        self.assertGreaterEqual(client.check_instance.call_count, 2)

    def test_extra_reload_event_during_owned_reconciliation_is_harmless(self) -> None:
        class ExtraReloadCoordinator(FakeReloadCoordinator):
            def arm(inner_self, journal):
                inner_self.arm_phases.append(journal.persistence_phase)
                watch = FakeReloadWatch([True, True])
                inner_self.watches.append(watch)
                return watch

            def reconcile(inner_self, journal, client, watch):
                inner_self.reconciliations.append(journal.persistence_phase)
                self.assertTrue(watch.wait(monitor.RELOAD_EVENT_WAIT_SECONDS))
                self.assertTrue(watch.wait(0.0))

        coordinator = ExtraReloadCoordinator()
        persister = monitor.MachineConfigPersister(lambda journal, content: None)
        authority, runner, active = self.begin_success(persister=persister)
        authority.reload_coordinator = coordinator
        runner.responses.extend([[candidate_output()], [candidate_output()]])
        committed = authority.confirm(active.transaction_id)
        self.assertEqual(committed.state, "committed")
        self.assertEqual(coordinator.arm_phases, ["candidate-installed"])
        self.assertEqual(coordinator.reconciliations, ["candidate-installed"])

    def test_reload_event_absent_uses_bounded_ordinary_reload(self) -> None:
        runner = QueueRunner([OK, monitor.CommandResult(0, "", "")])
        coordinator = monitor.HyprlandReloadCoordinator(self.runtime, runner)
        client = mock.Mock()
        watch = FakeReloadWatch([False, True])
        _, _, journal = self.begin_success()
        coordinator.reconcile(journal, client, watch)
        self.assertEqual(runner.calls[0], monitor.reload_argv(self.instance.signature))
        self.assertNotIn("full-reset", runner.calls[0])
        self.assertEqual(runner.calls[1], monitor.configerrors_argv(self.instance.signature))

    def test_reload_configerrors_and_missing_event_fail_closed(self) -> None:
        _, _, journal = self.begin_success()
        cases = (
            (
                QueueRunner([OK]),
                FakeReloadWatch([False, False]),
                "not observed",
            ),
            (
                QueueRunner([monitor.CommandResult(0, "bad option\n", "")]),
                FakeReloadWatch([True]),
                "configuration errors",
            ),
        )
        for runner, watch, message in cases:
            with self.subTest(message=message):
                coordinator = monitor.HyprlandReloadCoordinator(self.runtime, runner)
                with self.assertRaisesRegex(monitor.PersistenceError, message):
                    coordinator.reconcile(journal, mock.Mock(), watch)

    def test_atomic_write_failure_leaves_original_authoritative(self) -> None:
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        _, _, journal = self.begin_success(persister=persister)
        content, planned = persister.prepare(journal)
        committing = replace(
            journal,
            state="committing",
            deadline_monotonic=None,
            planned_machine_sha256=planned,
            persistence_phase="candidate-planned",
        )
        before = self.machine.read_bytes()
        with mock.patch.object(
            monitor,
            "atomic_replace",
            side_effect=monitor.PersistenceError("fixture write failure"),
        ):
            with self.assertRaisesRegex(monitor.PersistenceError, "write failure"):
                persister.persist(committing, content)
        self.assertEqual(self.machine.read_bytes(), before)
        self.assertEqual(persister.machine_state(committing), "original")

    def test_candidate_restoration_refuses_external_edit(self) -> None:
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        _, _, journal = self.begin_success(persister=persister)
        content, planned = persister.prepare(journal)
        committing = replace(
            journal,
            state="committing",
            deadline_monotonic=None,
            planned_machine_sha256=planned,
            persistence_phase="candidate-planned",
        )
        persister.persist(committing, content)
        self.assertEqual(persister.machine_state(committing), "candidate")
        self.machine.write_bytes(self.machine.read_bytes() + b"-- external\n")
        with self.assertRaisesRegex(monitor.PersistenceError, "external edit"):
            persister.recover_original(committing)

    def test_validation_failure_before_write_rolls_runtime_back(self) -> None:
        before = self.machine.read_bytes()
        persister = monitor.MachineConfigPersister(
            RecordingVerifier(monitor.PersistenceError("invalid prospective config"))
        )
        authority, runner, journal = self.begin_success(persister=persister)
        runner.responses.extend([[candidate_output()], [candidate_output()], OK, [output()]])
        reverted = authority.confirm(journal.transaction_id)
        self.assertEqual(reverted.state, "reverted")
        self.assertIn("invalid prospective config", reverted.failure)
        self.assertEqual(self.machine.read_bytes(), before)

    def test_reload_failure_restores_persistent_and_runtime_state(self) -> None:
        before = self.machine.read_bytes()
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        coordinator = SequenceReloadCoordinator(
            [monitor.PersistenceError("reload failed"), None]
        )
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_coordinator=coordinator,
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        runner.responses.extend([[candidate_output()], [candidate_output()], OK, [output()]])
        reverted = authority.confirm(journal.transaction_id)
        self.assertEqual(reverted.state, "reverted", reverted.failure)
        self.assertEqual(self.machine.read_bytes(), before)
        self.assertEqual(reverted.persistence_phase, "original-reloaded")

    def test_wrong_post_reload_state_restores_candidate_file(self) -> None:
        before = self.machine.read_bytes()
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        coordinator = SequenceReloadCoordinator([None, None])
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_coordinator=coordinator,
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        runner.responses.extend(
            [
                [candidate_output()],
                [output()],
                [output()],
                [output()],
                OK,
                [output()],
            ]
        )
        reverted = authority.confirm(journal.transaction_id)
        self.assertEqual(reverted.state, "reverted", reverted.failure)
        self.assertIn("did not converge", reverted.failure)
        self.assertEqual(self.machine.read_bytes(), before)

    def test_post_reload_physical_identity_change_never_receives_snapshot(self) -> None:
        before = self.machine.read_bytes()
        replacement = candidate_output()
        replacement.update(
            make="Other",
            model="Replacement",
            serial="DIFFERENT",
            description="Other Replacement DIFFERENT",
        )
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        coordinator = SequenceReloadCoordinator([None, None])
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_coordinator=coordinator,
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        runner.responses.extend(
            [[candidate_output()], [replacement], [replacement], [replacement]]
        )
        failed = authority.confirm(journal.transaction_id)
        self.assertEqual(failed.state, "rollback-failed")
        self.assertTrue(failed.recovery_required)
        self.assertEqual(self.machine.read_bytes(), before)
        eval_calls = [call for call in runner.calls if "eval" in call]
        self.assertEqual(len(eval_calls), 1)

    def test_compositor_replacement_during_persistence_restores_file_without_following(self) -> None:
        before = self.machine.read_bytes()
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )

        class ReplaceDuringReload(FakeReloadCoordinator):
            def reconcile(inner_self, journal, client, watch):
                inner_self.reconciliations.append(journal.persistence_phase)
                if len(inner_self.reconciliations) == 1:
                    if not watch.wait(monitor.RELOAD_EVENT_WAIT_SECONDS):
                        raise AssertionError("fixture expected configreloaded")
                    self.provider.identity = replace(self.instance, pid=999)
                client.check_instance()

        coordinator = ReplaceDuringReload()
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_coordinator=coordinator,
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        runner.responses.append([candidate_output()])
        vanished = authority.confirm(journal.transaction_id)
        self.assertEqual(vanished.state, "instance-vanished")
        self.assertFalse(vanished.recovery_required)
        self.assertEqual(self.machine.read_bytes(), before)
        self.assertEqual(len([call for call in runner.calls if "eval" in call]), 1)

    def test_persistence_restoration_failure_remains_armed(self) -> None:
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        coordinator = SequenceReloadCoordinator(
            [monitor.PersistenceError("candidate reload failed")]
        )
        authority, runner = self.authority(
            [[output()], OK, [candidate_output()]],
            persister=persister,
            reload_coordinator=coordinator,
        )
        journal = authority.begin(self.candidate, self.instance.signature)
        runner.responses.append([candidate_output()])
        original_atomic_replace = monitor.atomic_replace
        machine_calls = 0

        def replace_then_fail(*args, **kwargs):
            nonlocal machine_calls
            if Path(args[0]) == self.machine:
                machine_calls += 1
                if machine_calls > 1:
                    raise monitor.PersistenceError("fixture restoration failed")
            return original_atomic_replace(*args, **kwargs)

        with mock.patch.object(monitor, "atomic_replace", side_effect=replace_then_fail):
            failed = authority.confirm(journal.transaction_id)
        self.assertEqual(failed.state, "rollback-failed")
        self.assertTrue(failed.recovery_required)
        self.assertIn("restoration failed", failed.failure)
        self.assertEqual(persister.machine_state(failed), "candidate")

    def test_external_edit_during_persistence_remains_recovery_armed(self) -> None:
        persister = monitor.MachineConfigPersister(
            lambda journal, content: None
        )
        authority, runner, journal = self.begin_success(persister=persister)
        content, planned = persister.prepare(journal)
        committing = authority._transition(
            journal,
            "committing",
            planned_machine_sha256=planned,
            persistence_phase="candidate-planned",
            deadline_monotonic=None,
        )
        persister.persist(committing, content)
        self.machine.write_bytes(self.machine.read_bytes() + b"-- external\n")
        failed = authority.recover()
        self.assertEqual(failed.state, "rollback-failed")
        self.assertTrue(failed.recovery_required)
        self.assertIn("external edit", failed.failure)

    def test_commit_recovery_rolls_back_every_nonterminal_candidate_milestone(self) -> None:
        _, _, active = self.begin_success()
        phases = (
            ("candidate-planned", False),
            ("candidate-installed", False),
            ("candidate-reloaded", False),
            ("candidate-verified", True),
        )
        for phase, verified in phases:
            with self.subTest(phase=phase):
                journal = replace(
                    active,
                    state="committing",
                    sequence=active.sequence + 1,
                    deadline_monotonic=None,
                    planned_machine_sha256="a" * 64,
                    persistence_phase=phase,
                    persistence_verified=verified,
                    recovery_required=True,
                )
                self.store.write(journal)
                coordinator = FakeReloadCoordinator()
                runner = QueueRunner([[candidate_output()], OK, [output()]])
                authority = monitor.TransactionAuthority(
                    self.store,
                    self.provider,
                    self.paths,
                    runner=runner,
                    clock=self.clock,
                    persister=StubCandidatePersister(),
                    reload_coordinator=coordinator,
                )
                reverted = authority.recover()
                self.assertEqual(reverted.state, "reverted")
                self.assertEqual(reverted.persistence_phase, "original-reloaded")
                self.assertFalse(reverted.recovery_required)
                self.assertEqual(coordinator.reconciliations[-1], "original-restored")
                call_count = len(runner.calls)
                self.assertEqual(authority.recover(), reverted)
                self.assertEqual(len(runner.calls), call_count)

    def test_recovery_is_idempotent_across_restore_crash_milestones(self) -> None:
        _, _, active = self.begin_success()
        cases = (
            ("candidate-planned", "original"),
            ("restore-pending", "candidate"),
            ("original-restored", "original"),
            ("original-reloaded", "original"),
        )
        for phase, file_state in cases:
            with self.subTest(phase=phase, file_state=file_state):
                journal = replace(
                    active,
                    state="reverting",
                    sequence=active.sequence + 1,
                    deadline_monotonic=None,
                    planned_machine_sha256="b" * 64,
                    persistence_phase=phase,
                    persistence_verified=False,
                    recovery_required=True,
                )
                self.store.write(journal)
                coordinator = FakeReloadCoordinator()
                runner = QueueRunner([[candidate_output()], OK, [output()]])
                authority = monitor.TransactionAuthority(
                    self.store,
                    self.provider,
                    self.paths,
                    runner=runner,
                    clock=self.clock,
                    persister=StubCandidatePersister(file_state),
                    reload_coordinator=coordinator,
                )
                reverted = authority.recover()
                self.assertEqual(reverted.state, "reverted")
                self.assertFalse(reverted.recovery_required)
                call_count = len(runner.calls)
                self.assertEqual(authority.recover(), reverted)
                self.assertEqual(len(runner.calls), call_count)

    def test_production_authority_wires_validated_persistence_components(self) -> None:
        production_runtime = self.root / "production-runtime"
        production_runtime.mkdir(mode=0o700)
        with (
            mock.patch.object(monitor, "runtime_root", return_value=production_runtime),
            mock.patch.object(monitor, "default_config_paths", return_value=self.paths),
            mock.patch.dict(
                monitor.os.environ,
                {"HYPRLAND_INSTANCE_SIGNATURE": self.instance.signature},
                clear=False,
            ),
        ):
            authority = monitor.build_production_authority()
        try:
            self.assertIsInstance(authority.persister, monitor.MachineConfigPersister)
            self.assertIsInstance(
                authority.persister.verifier, monitor.SandboxedHyprlandVerifier
            )
            self.assertEqual(authority.persister.verifier.config_home, self.config)
            self.assertIsInstance(
                authority.reload_coordinator, monitor.HyprlandReloadCoordinator
            )
            self.assertEqual(authority.reload_coordinator.runtime_root, production_runtime)
            self.assertIsInstance(
                authority.reload_event_source, monitor.SocketReloadEventSource
            )
            self.assertEqual(authority.config_paths, self.paths)
            self.assertEqual(authority.bound_signature, self.instance.signature)
        finally:
            authority.store.release()

    def test_persistence_detects_external_machine_hash_race(self) -> None:
        persister = monitor.MachineConfigPersister(lambda journal, content: None)
        _, _, journal = self.begin_success(persister=persister)
        self.machine.write_bytes(self.machine.read_bytes() + b"-- external edit\n")
        with self.assertRaisesRegex(monitor.PersistenceError, "changed"):
            persister.prepare(journal)

    def test_persistence_detects_external_override_hash_race(self) -> None:
        persister = monitor.MachineConfigPersister(lambda journal, content: None)
        _, _, journal = self.begin_success(persister=persister)
        self.override.write_bytes(b"-- externally changed override\n")
        with self.assertRaisesRegex(monitor.PersistenceError, "override changed"):
            persister.prepare(journal)

    def test_persistence_preserves_unrelated_machine_bytes_and_catch_all(self) -> None:
        before = self.machine.read_bytes()
        snapshot = monitor.snapshot_file(self.machine)
        topology = monitor.parse_monitor_payload([output()])
        journal = monitor.TransactionJournal(
            monitor.SCHEMA_VERSION,
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
            "original",
            self.instance,
            topology.target("DP-1").identity,
            self.candidate,
            topology,
            snapshot,
            monitor.snapshot_file(self.override),
        )
        persister = monitor.MachineConfigPersister(lambda journal, content: None)
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
