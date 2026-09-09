# SPDX-License-Identifier: GPL-2.0-only

"""BlueZ pairing agent for the Vanilla HyprArch Quickshell UI.

Bluetooth state and device operations intentionally remain in
Quickshell.Bluetooth. This process implements only org.bluez.Agent1 and
exchanges pairing prompts with Quickshell as newline-delimited JSON.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import uuid
from collections import deque
from typing import Any, Callable

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib


PROTOCOL_VERSION = 1
BLUEZ_SERVICE = "org.bluez"
BLUEZ_MANAGER_PATH = "/org/bluez"
AGENT_INTERFACE = "org.bluez.Agent1"
AGENT_MANAGER_INTERFACE = "org.bluez.AgentManager1"
AGENT_PATH = "/org/vanhyprarch/BluetoothAgent"
AGENT_CAPABILITY = "KeyboardDisplay"
REQUEST_TIMEOUT_SECONDS = 120
DISPLAY_ACK_TIMEOUT_SECONDS = 10
DISPLAY_LIFETIME_SECONDS = 120
MAX_INPUT_BUFFER = 65_536
MAX_REQUEST_ID_LENGTH = 128
PIN_PATTERN = re.compile(r"^[A-Za-z0-9]{1,16}$")
PASSKEY_PATTERN = re.compile(r"^[0-9]{1,6}$")
DEVICE_PATH_PATTERN = re.compile(
    r"^/org/bluez/hci[0-9]+/dev_(?:[0-9A-F]{2}_){5}[0-9A-F]{2}$"
)
UUID16_PATTERN = re.compile(r"^[0-9A-Fa-f]{4}$")
UUID32_PATTERN = re.compile(r"^[0-9A-Fa-f]{8}$")
UUID128_PATTERN = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
BLUETOOTH_BASE_UUID_SUFFIX = "-0000-1000-8000-00805f9b34fb"

REQUEST_KINDS = {
    "requestPinCode",
    "requestPasskey",
    "requestConfirmation",
    "requestAuthorization",
    "authorizeService",
}
DISPLAY_KINDS = {"displayPinCode", "displayPasskey"}


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class Canceled(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Canceled"


def valid_request_id(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= MAX_REQUEST_ID_LENGTH


def valid_pin(value: Any) -> bool:
    return isinstance(value, str) and PIN_PATTERN.fullmatch(value) is not None


def parse_passkey(value: Any) -> int | None:
    if not isinstance(value, str) or PASSKEY_PATTERN.fullmatch(value) is None:
        return None
    parsed = int(value, 10)
    return parsed if 0 <= parsed <= 999_999 else None


def valid_device_path(value: Any) -> bool:
    return isinstance(value, (str, dbus.ObjectPath)) and (
        DEVICE_PATH_PATTERN.fullmatch(str(value)) is not None
    )


def normalize_service_uuid(value: Any) -> str | None:
    if not isinstance(value, (str, dbus.String)):
        return None
    text = str(value)
    if UUID16_PATTERN.fullmatch(text):
        return "0000" + text.lower() + BLUETOOTH_BASE_UUID_SUFFIX
    if UUID32_PATTERN.fullmatch(text):
        return text.lower() + BLUETOOTH_BASE_UUID_SUFFIX
    if UUID128_PATTERN.fullmatch(text):
        return text.lower()
    return None


class BluetoothAgent(dbus.service.Object):
    def __init__(self, bus: dbus.SystemBus, loop: GLib.MainLoop) -> None:
        super().__init__(bus, AGENT_PATH)
        self.bus = bus
        self.loop = loop
        self.manager: dbus.Interface | None = None
        self.bluez_owner = ""
        self.registered = False
        self.shutting_down = False
        self.exit_code = 0
        self.pending: dict[str, Any] | None = None
        self.display: dict[str, Any] | None = None
        self.completed_ids: deque[str] = deque(maxlen=128)
        self.input_buffer = b""
        self.stdin_watch = 0

    def start(self) -> None:
        self._establish_bluez_registration()
        os.set_blocking(sys.stdin.fileno(), False)
        self.stdin_watch = GLib.io_add_watch(
            sys.stdin,
            GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR | GLib.IO_NVAL,
            self._read_stdin,
        )
        self._emit_status("ready", "")

    def _establish_bluez_registration(self) -> None:
        self.bus.add_signal_receiver(
            self._name_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            bus_name="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            arg0=BLUEZ_SERVICE,
        )
        initial_owner = str(self.bus.get_name_owner(BLUEZ_SERVICE))
        self.bluez_owner = initial_owner
        manager_object = self.bus.get_object(BLUEZ_SERVICE, BLUEZ_MANAGER_PATH)
        self.manager = self._manager_interface(manager_object)
        try:
            self.manager.RegisterAgent(dbus.ObjectPath(AGENT_PATH), AGENT_CAPABILITY)
            self.registered = True
            self.manager.RequestDefaultAgent(dbus.ObjectPath(AGENT_PATH))
            current_owner = str(self.bus.get_name_owner(BLUEZ_SERVICE))
            if current_owner != initial_owner:
                raise RuntimeError("BlueZ owner changed during agent registration")
        except Exception:
            self._emit_status("error", "Could not register the Bluetooth pairing agent")
            self._unregister()
            raise

    def _manager_interface(self, manager_object: Any) -> dbus.Interface:
        return dbus.Interface(manager_object, AGENT_MANAGER_INTERFACE)

    def _emit(self, event: dict[str, Any]) -> bool:
        if self.shutting_down:
            return False
        message = {"version": PROTOCOL_VERSION, **event}
        try:
            sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
            sys.stdout.flush()
            return True
        except (BrokenPipeError, OSError):
            GLib.idle_add(self.shutdown, "Quickshell output pipe closed", 0)
            return False

    def _emit_status(self, state: str, message: str) -> None:
        self._emit({"event": "status", "state": state, "message": message})

    def _valid_bluez_sender(self, sender: Any) -> bool:
        return bool(self.bluez_owner) and str(sender or "") == self.bluez_owner

    def _valid_device_path(self, device: Any) -> bool:
        return valid_device_path(device)

    def _require_bluez_sender(self, sender: Any) -> None:
        if not self._valid_bluez_sender(sender):
            raise Rejected("Request did not originate from BlueZ")

    def _new_id(self) -> str:
        return uuid.uuid4().hex

    def _begin_request(
        self,
        kind: str,
        device: Any,
        success: Callable[..., None],
        error: Callable[[Exception], None],
        sender: Any,
        **fields: Any,
    ) -> None:
        if not self._valid_bluez_sender(sender):
            error(Rejected("Request did not originate from BlueZ"))
            return
        if kind not in REQUEST_KINDS or not self._valid_device_path(device):
            error(Rejected("Invalid pairing request"))
            return
        if self.pending is not None:
            error(Rejected("Another pairing request is already active"))
            return
        if self.display is not None:
            compatible_display = (
                self.display["acknowledged"]
                and self.display["devicePath"] == str(device)
            )
            if not compatible_display:
                error(Rejected("Another pairing request is already active"))
                return

        self._clear_display("replaced")
        request_id = self._new_id()
        timeout_source = GLib.timeout_add_seconds(
            REQUEST_TIMEOUT_SECONDS, self._request_timed_out, request_id
        )
        self.pending = {
            "id": request_id,
            "kind": kind,
            "devicePath": str(device),
            "success": success,
            "error": error,
            "timeoutSource": timeout_source,
        }
        event = {
            "event": "request",
            "id": request_id,
            "kind": kind,
            "devicePath": str(device),
            **fields,
        }
        if not self._emit(event):
            self._settle_error(Canceled("Pairing UI is unavailable"), "canceled")

    def _begin_display(
        self,
        kind: str,
        device: Any,
        success: Callable[..., None],
        error: Callable[[Exception], None],
        sender: Any,
        **fields: Any,
    ) -> None:
        if not self._valid_bluez_sender(sender):
            error(Rejected("Request did not originate from BlueZ"))
            return
        if kind not in DISPLAY_KINDS or not self._valid_device_path(device):
            error(Rejected("Invalid pairing display request"))
            return
        if self.pending is not None:
            error(Rejected("Another pairing request is already active"))
            return
        if self.display is not None:
            same_display = (
                self.display["acknowledged"]
                and self.display["kind"] == kind
                and self.display["devicePath"] == str(device)
            )
            if not same_display:
                error(Rejected("Another pairing display is already active"))
                return
            self._clear_display("updated")

        display_id = self._new_id()
        ack_timeout_source = GLib.timeout_add_seconds(
            DISPLAY_ACK_TIMEOUT_SECONDS, self._display_ack_timed_out, display_id
        )
        self.display = {
            "id": display_id,
            "kind": kind,
            "devicePath": str(device),
            "success": success,
            "error": error,
            "acknowledged": False,
            "ackTimeoutSource": ack_timeout_source,
            "lifetimeSource": 0,
        }
        if not self._emit(
            {
                "event": "display",
                "id": display_id,
                "kind": kind,
                "devicePath": str(device),
                **fields,
            }
        ):
            self._fail_display(Canceled("Pairing UI is unavailable"), "uiUnavailable")

    def _request_timed_out(self, request_id: str) -> bool:
        if self.pending is None or self.pending["id"] != request_id:
            return GLib.SOURCE_REMOVE
        self.pending["timeoutSource"] = 0
        self._settle_error(Rejected("Pairing request timed out"), "rejected")
        return GLib.SOURCE_REMOVE

    def _display_ack_timed_out(self, display_id: str) -> bool:
        if self.display is None or self.display["id"] != display_id:
            return GLib.SOURCE_REMOVE
        self.display["ackTimeoutSource"] = 0
        self._fail_display(Rejected("Pairing display was not presented"), "uiTimeout")
        self.shutdown("Bluetooth pairing display acknowledgement timed out", 1)
        return GLib.SOURCE_REMOVE

    def _display_lifetime_timed_out(self, display_id: str) -> bool:
        if self.display is None or self.display["id"] != display_id:
            return GLib.SOURCE_REMOVE
        self.display["lifetimeSource"] = 0
        self.shutdown("Bluetooth pairing display timed out", 1)
        return GLib.SOURCE_REMOVE

    def _take_pending(self) -> dict[str, Any] | None:
        pending = self.pending
        self.pending = None
        if pending is None:
            return None
        timeout_source = int(pending.get("timeoutSource", 0))
        if timeout_source:
            GLib.source_remove(timeout_source)
        self.completed_ids.append(pending["id"])
        return pending

    def _settle_success(self, value: Any = None) -> None:
        pending = self._take_pending()
        if pending is None:
            return
        try:
            if pending["kind"] in {"requestPinCode", "requestPasskey"}:
                pending["success"](value)
            else:
                pending["success"]()
        except Exception:
            print("Bluetooth agent could not send a success reply", file=sys.stderr)
            self.shutdown("Bluetooth agent delayed reply failed", 1)
            return
        self._emit({"event": "complete", "id": pending["id"], "outcome": "accepted"})

    def _settle_error(self, exception: Exception, outcome: str) -> None:
        pending = self._take_pending()
        if pending is None:
            return
        try:
            pending["error"](exception)
        except Exception:
            print("Bluetooth agent could not send an error reply", file=sys.stderr)
            self.shutdown("Bluetooth agent delayed error reply failed", 1)
            return
        self._emit({"event": "complete", "id": pending["id"], "outcome": outcome})

    def _take_display(self) -> dict[str, Any] | None:
        display = self.display
        self.display = None
        if display is None:
            return None
        for source_name in ("ackTimeoutSource", "lifetimeSource"):
            source = int(display.get(source_name, 0))
            if source:
                GLib.source_remove(source)
        self.completed_ids.append(display["id"])
        return display

    def _acknowledge_display(self) -> None:
        display = self.display
        if display is None or display["acknowledged"]:
            return
        source = int(display.get("ackTimeoutSource", 0))
        if source:
            GLib.source_remove(source)
        display["ackTimeoutSource"] = 0
        display["acknowledged"] = True
        success = display.pop("success")
        display.pop("error")
        try:
            success()
        except Exception:
            self.shutdown("Bluetooth agent could not acknowledge the display", 1)
            return
        display["lifetimeSource"] = GLib.timeout_add_seconds(
            DISPLAY_LIFETIME_SECONDS,
            self._display_lifetime_timed_out,
            display["id"],
        )

    def _fail_display(self, exception: Exception, reason: str) -> None:
        display = self._take_display()
        if display is None:
            return
        error = display.get("error")
        if error is not None:
            try:
                error(exception)
            except Exception:
                print("Bluetooth agent could not reject a display request", file=sys.stderr)
                self.shutdown("Bluetooth agent display error reply failed", 1)
                return
        self._emit({"event": "cancel", "id": display["id"], "reason": reason})

    def _clear_display(self, reason: str) -> None:
        display = self._take_display()
        if display is None:
            return
        error = display.get("error")
        if error is not None:
            try:
                error(Canceled("Pairing display was canceled"))
            except Exception:
                print("Bluetooth agent could not cancel a display request", file=sys.stderr)
                self.shutdown("Bluetooth agent display cancellation reply failed", 1)
                return
        self._emit({"event": "cancel", "id": display["id"], "reason": reason})

    def _protocol_failure(self, diagnostic: str) -> None:
        print(diagnostic, file=sys.stderr)
        if self.pending is not None:
            self._settle_error(Rejected("Invalid pairing UI response"), "rejected")
        if self.display is not None and not self.display["acknowledged"]:
            self._fail_display(Rejected("Invalid pairing UI response"), "protocolError")
        self.shutdown("Bluetooth pairing IPC session failed", 1)

    def _handle_response_line(self, raw_line: bytes) -> None:
        try:
            message = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._protocol_failure("Bluetooth agent rejected malformed UI JSON")
            return

        if not isinstance(message, dict) or message.get("version") != PROTOCOL_VERSION:
            self._protocol_failure("Bluetooth agent rejected an invalid UI protocol message")
            return

        request_id = message.get("id")
        if not valid_request_id(request_id):
            self._protocol_failure("Bluetooth agent rejected an invalid request ID")
            return

        pending = self.pending
        display = self.display
        if pending is not None and request_id == pending["id"]:
            decision = message.get("decision")
            kind = pending["kind"]
            if decision == "reject":
                self._settle_error(Rejected("Pairing rejected by the user"), "rejected")
                return
            if decision == "accept" and kind in {
                "requestConfirmation",
                "requestAuthorization",
                "authorizeService",
            }:
                self._settle_success()
                return
            if decision == "submit" and kind == "requestPinCode":
                value = message.get("value")
                if valid_pin(value):
                    self._settle_success(dbus.String(value))
                    return
            if decision == "submit" and kind == "requestPasskey":
                value = parse_passkey(message.get("value"))
                if value is not None:
                    self._settle_success(dbus.UInt32(value))
                    return
            self._protocol_failure("Bluetooth agent rejected an invalid UI decision")
            return

        if display is not None and request_id == display["id"]:
            decision = message.get("decision")
            if decision == "displayed" and not display["acknowledged"]:
                self._acknowledge_display()
                return
            if decision == "reject" and not display["acknowledged"]:
                self._fail_display(Rejected("Pairing display was rejected"), "rejected")
                return
            if decision == "cancel" and display["acknowledged"]:
                self._clear_display("nativeCanceled")
                return
            self._protocol_failure("Bluetooth agent rejected an invalid display decision")
            return

        if request_id in self.completed_ids:
            print("Bluetooth agent ignored a stale or duplicate response", file=sys.stderr)
            return
        self._protocol_failure("Bluetooth agent rejected an unknown request ID")

    def _read_stdin(self, _source: Any, condition: GLib.IOCondition) -> bool:
        if condition & (GLib.IO_ERR | GLib.IO_NVAL):
            self.stdin_watch = 0
            self.shutdown("Quickshell input pipe failed", 0)
            return GLib.SOURCE_REMOVE
        try:
            chunk = os.read(sys.stdin.fileno(), 4096)
        except BlockingIOError:
            return GLib.SOURCE_CONTINUE
        except OSError:
            self.stdin_watch = 0
            self.shutdown("Quickshell input pipe failed", 0)
            return GLib.SOURCE_REMOVE

        if chunk:
            self.input_buffer += chunk
            if len(self.input_buffer) > MAX_INPUT_BUFFER:
                self.stdin_watch = 0
                self._protocol_failure("Bluetooth agent rejected an oversized UI message")
                return GLib.SOURCE_REMOVE
            while b"\n" in self.input_buffer:
                raw_line, self.input_buffer = self.input_buffer.split(b"\n", 1)
                if not raw_line:
                    self._protocol_failure("Bluetooth agent rejected an empty UI message")
                else:
                    self._handle_response_line(raw_line)
                if self.shutting_down:
                    self.stdin_watch = 0
                    return GLib.SOURCE_REMOVE

        if not chunk or condition & GLib.IO_HUP:
            self.stdin_watch = 0
            self.shutdown("Quickshell input pipe closed", 0)
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _name_owner_changed(self, _name: str, old_owner: str, new_owner: str) -> None:
        if self.shutting_down:
            return
        if self.bluez_owner and (
            str(old_owner) == self.bluez_owner or str(new_owner) != self.bluez_owner
        ):
            self.shutdown("BlueZ restarted or stopped", 1)

    def _unregister(self) -> None:
        if not self.registered or self.manager is None:
            return
        self.registered = False
        try:
            self.manager.UnregisterAgent(dbus.ObjectPath(AGENT_PATH))
        except Exception:
            print("Bluetooth agent could not unregister cleanly", file=sys.stderr)

    def shutdown(self, reason: str, exit_code: int = 0) -> bool:
        if self.shutting_down:
            return GLib.SOURCE_REMOVE
        self.shutting_down = True
        self.exit_code = exit_code
        if self.pending is not None:
            self._settle_error(Canceled("Pairing agent is shutting down"), "canceled")
        self._clear_display("agentUnavailable")
        if self.stdin_watch:
            GLib.source_remove(self.stdin_watch)
            self.stdin_watch = 0
        self._unregister()
        print(reason, file=sys.stderr)
        self.loop.quit()
        return GLib.SOURCE_REMOVE

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="o",
        out_signature="s",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def RequestPinCode(
        self, device: dbus.ObjectPath, success: Callable[..., None],
        error: Callable[[Exception], None], sender: str | None = None
    ) -> None:
        self._begin_request("requestPinCode", device, success, error, sender)

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="os",
        out_signature="",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def DisplayPinCode(
        self, device: dbus.ObjectPath, pincode: str,
        success: Callable[..., None], error: Callable[[Exception], None],
        sender: str | None = None,
    ) -> None:
        pin = str(pincode)
        if not valid_pin(pin):
            error(Rejected("Invalid PIN display request"))
            return
        self._begin_display(
            "displayPinCode", device, success, error, sender, pin=pin
        )

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="o",
        out_signature="u",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def RequestPasskey(
        self, device: dbus.ObjectPath, success: Callable[..., None],
        error: Callable[[Exception], None], sender: str | None = None
    ) -> None:
        self._begin_request("requestPasskey", device, success, error, sender)

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="ouq",
        out_signature="",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def DisplayPasskey(
        self, device: dbus.ObjectPath, passkey: int, entered: int,
        success: Callable[..., None], error: Callable[[Exception], None],
        sender: str | None = None,
    ) -> None:
        passkey_value = int(passkey)
        entered_value = int(entered)
        if not 0 <= passkey_value <= 999_999 or not 0 <= entered_value <= 6:
            error(Rejected("Invalid passkey display request"))
            return
        self._begin_display(
            "displayPasskey",
            device,
            success,
            error,
            sender,
            passkey=passkey_value,
            entered=entered_value,
        )

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="ou",
        out_signature="",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def RequestConfirmation(
        self, device: dbus.ObjectPath, passkey: int,
        success: Callable[..., None], error: Callable[[Exception], None],
        sender: str | None = None
    ) -> None:
        passkey_value = int(passkey)
        if not 0 <= passkey_value <= 999_999:
            error(Rejected("Invalid passkey confirmation request"))
            return
        self._begin_request(
            "requestConfirmation",
            device,
            success,
            error,
            sender,
            passkey=passkey_value,
        )

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="o",
        out_signature="",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def RequestAuthorization(
        self, device: dbus.ObjectPath, success: Callable[..., None],
        error: Callable[[Exception], None], sender: str | None = None
    ) -> None:
        self._begin_request("requestAuthorization", device, success, error, sender)

    @dbus.service.method(
        AGENT_INTERFACE,
        in_signature="os",
        out_signature="",
        async_callbacks=("success", "error"),
        sender_keyword="sender",
    )
    def AuthorizeService(
        self, device: dbus.ObjectPath, service_uuid: str,
        success: Callable[..., None], error: Callable[[Exception], None],
        sender: str | None = None
    ) -> None:
        uuid_text = normalize_service_uuid(service_uuid)
        if uuid_text is None:
            error(Rejected("Invalid service authorization request"))
            return
        self._begin_request(
            "authorizeService",
            device,
            success,
            error,
            sender,
            uuid=uuid_text,
        )

    @dbus.service.method(
        AGENT_INTERFACE, in_signature="", out_signature="", sender_keyword="sender"
    )
    def Cancel(self, sender: str | None = None) -> None:
        self._require_bluez_sender(sender)
        if self.pending is not None:
            self._settle_error(Canceled("Pairing canceled by BlueZ"), "canceled")
        self._clear_display("bluezCanceled")

    @dbus.service.method(
        AGENT_INTERFACE, in_signature="", out_signature="", sender_keyword="sender"
    )
    def Release(self, sender: str | None = None) -> None:
        self._require_bluez_sender(sender)
        GLib.idle_add(self.shutdown, "BlueZ released the pairing agent", 0)


def run_self_check() -> int:
    canonical_path = "/org/bluez/hci0/dev_01_23_45_67_89_AB"

    class FakeLoop:
        def __init__(self) -> None:
            self.quit_count = 0

        def quit(self) -> None:
            self.quit_count += 1

    def harness(events: list[dict[str, Any]]) -> BluetoothAgent:
        agent = BluetoothAgent.__new__(BluetoothAgent)
        agent.bus = None
        agent.loop = FakeLoop()
        agent.manager = None
        agent.bluez_owner = ":1.50"
        agent.registered = False
        agent.shutting_down = False
        agent.exit_code = 0
        agent.pending = None
        agent.display = None
        agent.completed_ids = deque(maxlen=128)
        agent.input_buffer = b""
        agent.stdin_watch = 0
        agent._emit = lambda event: events.append(event) or True
        return agent

    assert valid_request_id("a")
    assert not valid_request_id(1)
    assert not valid_request_id("")
    assert valid_pin("A1b2")
    assert not valid_pin("contains space")
    assert not valid_pin("12345678901234567")
    assert parse_passkey("000000") == 0
    assert parse_passkey("999999") == 999_999
    assert parse_passkey("1000000") is None
    assert parse_passkey(123456) is None
    assert valid_device_path(canonical_path)
    assert not valid_device_path("/org/bluez/hci0")
    assert not valid_device_path("/org/bluez/hci0/dev_01_23_45_67_89_ab")
    assert normalize_service_uuid("110B") == (
        "0000110b-0000-1000-8000-00805f9b34fb"
    )
    assert normalize_service_uuid("0000110B") == (
        "0000110b-0000-1000-8000-00805f9b34fb"
    )
    assert normalize_service_uuid(
        "0000110B-0000-1000-8000-00805F9B34FB"
    ) == "0000110b-0000-1000-8000-00805f9b34fb"
    assert normalize_service_uuid("not-a-uuid") is None

    expected_methods = {
        "Release": ("", ""),
        "RequestPinCode": ("o", "s"),
        "DisplayPinCode": ("os", ""),
        "RequestPasskey": ("o", "u"),
        "DisplayPasskey": ("ouq", ""),
        "RequestConfirmation": ("ou", ""),
        "RequestAuthorization": ("o", ""),
        "AuthorizeService": ("os", ""),
        "Cancel": ("", ""),
    }
    for method_name, signatures in expected_methods.items():
        method = getattr(BluetoothAgent, method_name)
        assert method._dbus_interface == AGENT_INTERFACE
        assert method._dbus_in_signature == signatures[0]
        assert method._dbus_out_signature == signatures[1]
    for method_name in {
        "RequestPinCode",
        "DisplayPinCode",
        "RequestPasskey",
        "DisplayPasskey",
        "RequestConfirmation",
        "RequestAuthorization",
        "AuthorizeService",
    }:
        assert getattr(BluetoothAgent, method_name)._dbus_async_callbacks == (
            "success", "error"
        )

    events: list[dict[str, Any]] = []
    successes: list[Any] = []
    errors: list[Exception] = []
    agent = harness(events)
    agent.pending = {
        "id": "pin-request",
        "kind": "requestPinCode",
        "success": lambda value: successes.append(value),
        "error": lambda error: errors.append(error),
        "timeoutSource": 0,
    }
    agent._handle_response_line(
        b'{"version":1,"id":"pin-request","decision":"submit","value":"A123"}'
    )
    assert [str(value) for value in successes] == ["A123"]
    assert not errors
    assert events == [
        {"event": "complete", "id": "pin-request", "outcome": "accepted"}
    ]

    # A Display* callback must be rejected while an interactive callback is pending.
    events = []
    concurrent_errors: list[Exception] = []
    agent = harness(events)
    agent.pending = {"id": "active-request"}
    agent._begin_display(
        "displayPasskey",
        canonical_path,
        lambda: None,
        concurrent_errors.append,
        ":1.50",
        passkey=123456,
        entered=0,
    )
    assert len(concurrent_errors) == 1
    assert isinstance(concurrent_errors[0], Rejected)
    assert agent.display is None
    assert not events

    # Display D-Bus success is delayed until the UI acknowledges visibility.
    events = []
    display_successes: list[bool] = []
    display_errors: list[Exception] = []
    agent = harness(events)
    agent._begin_display(
        "displayPinCode",
        canonical_path,
        lambda: display_successes.append(True),
        display_errors.append,
        ":1.50",
        pin="A123",
    )
    display_id = agent.display["id"]
    assert not display_successes and not display_errors
    agent._handle_response_line(
        json.dumps(
            {"version": 1, "id": display_id, "decision": "displayed"}
        ).encode()
    )
    assert display_successes == [True]
    assert agent.display is not None and agent.display["acknowledged"]
    assert agent.display["lifetimeSource"]
    cross_device_errors: list[Exception] = []
    agent._begin_request(
        "requestAuthorization",
        "/org/bluez/hci0/dev_10_20_30_40_50_60",
        lambda: None,
        cross_device_errors.append,
        ":1.50",
    )
    assert len(cross_device_errors) == 1
    assert isinstance(cross_device_errors[0], Rejected)
    agent._clear_display("selfCheck")
    assert agent.display is None

    # UI rejection before acknowledgement fails the delayed Display* call.
    events = []
    display_errors = []
    agent = harness(events)
    agent._begin_display(
        "displayPinCode",
        canonical_path,
        lambda: None,
        display_errors.append,
        ":1.50",
        pin="A123",
    )
    display_id = agent.display["id"]
    agent._handle_response_line(
        json.dumps(
            {"version": 1, "id": display_id, "decision": "reject"}
        ).encode()
    )
    assert len(display_errors) == 1 and isinstance(display_errors[0], Rejected)
    assert agent.display is None

    # A display acknowledgement timeout rejects and terminates the session.
    events = []
    display_errors = []
    agent = harness(events)
    agent._begin_display(
        "displayPinCode",
        canonical_path,
        lambda: None,
        display_errors.append,
        ":1.50",
        pin="A123",
    )
    display_id = agent.display["id"]
    GLib.source_remove(agent.display["ackTimeoutSource"])
    agent.display["ackTimeoutSource"] = 0
    agent._display_ack_timed_out(display_id)
    assert len(display_errors) == 1 and isinstance(display_errors[0], Rejected)
    assert agent.shutting_down and agent.loop.quit_count == 1

    # An acknowledged display still has a bounded total lifetime.
    events = []
    agent = harness(events)
    agent._begin_display(
        "displayPinCode",
        canonical_path,
        lambda: None,
        lambda _error: None,
        ":1.50",
        pin="A123",
    )
    display_id = agent.display["id"]
    agent._handle_response_line(
        json.dumps(
            {"version": 1, "id": display_id, "decision": "displayed"}
        ).encode()
    )
    GLib.source_remove(agent.display["lifetimeSource"])
    agent.display["lifetimeSource"] = 0
    agent._display_lifetime_timed_out(display_id)
    assert agent.shutting_down and agent.display is None
    assert agent.loop.quit_count == 1

    # BlueZ cancellation removes an acknowledged display exactly once.
    events = []
    agent = harness(events)
    agent._begin_display(
        "displayPasskey",
        canonical_path,
        lambda: None,
        lambda _error: None,
        ":1.50",
        passkey=123456,
        entered=0,
    )
    display_id = agent.display["id"]
    agent._handle_response_line(
        json.dumps(
            {"version": 1, "id": display_id, "decision": "displayed"}
        ).encode()
    )
    agent.Cancel(sender=":1.50")
    assert agent.display is None
    assert sum(event.get("event") == "cancel" for event in events) == 1

    # Unknown IDs invalidate the session and reject outstanding work.
    events = []
    unknown_errors: list[Exception] = []
    agent = harness(events)
    agent.pending = {
        "id": "known-request",
        "kind": "requestAuthorization",
        "success": lambda: None,
        "error": unknown_errors.append,
        "timeoutSource": 0,
    }
    agent._handle_response_line(
        b'{"version":1,"id":"unknown-request","decision":"accept"}'
    )
    assert len(unknown_errors) == 1 and isinstance(unknown_errors[0], Rejected)
    assert agent.shutting_down and agent.pending is None

    # Shutdown cancels a pending delayed callback.
    events = []
    shutdown_errors: list[Exception] = []
    agent = harness(events)
    agent.pending = {
        "id": "shutdown-request",
        "kind": "requestAuthorization",
        "success": lambda: None,
        "error": shutdown_errors.append,
        "timeoutSource": 0,
    }
    agent.shutdown("self-check shutdown", 0)
    assert len(shutdown_errors) == 1 and isinstance(shutdown_errors[0], Canceled)
    assert agent.pending is None and agent.loop.quit_count == 1

    # Startup monitors the owner first and refuses readiness after owner replacement.
    class FakeManager:
        def __init__(self, actions: list[str]) -> None:
            self.actions = actions

        def RegisterAgent(self, _path: dbus.ObjectPath, _capability: str) -> None:
            self.actions.append("register")

        def RequestDefaultAgent(self, _path: dbus.ObjectPath) -> None:
            self.actions.append("default")

        def UnregisterAgent(self, _path: dbus.ObjectPath) -> None:
            self.actions.append("unregister")

    class FakeBus:
        def __init__(self, owners: list[str], manager: FakeManager,
                     actions: list[str]) -> None:
            self.owners = deque(owners)
            self.manager = manager
            self.actions = actions

        def add_signal_receiver(self, *_args: Any, **_kwargs: Any) -> None:
            self.actions.append("monitor")

        def get_name_owner(self, _name: str) -> str:
            self.actions.append("owner")
            return self.owners.popleft()

        def get_object(self, _service: str, _path: str) -> FakeManager:
            self.actions.append("manager")
            return self.manager

    actions: list[str] = []
    events = []
    agent = harness(events)
    agent.bus = FakeBus([":1.50", ":1.51"], FakeManager(actions), actions)
    agent._manager_interface = lambda manager: manager
    try:
        agent._establish_bluez_registration()
        raise AssertionError("owner replacement was not rejected")
    except RuntimeError:
        pass
    assert actions == [
        "monitor", "owner", "manager", "register", "default", "owner", "unregister"
    ]
    assert not agent.registered

    actions = []
    events = []
    agent = harness(events)
    agent.bus = FakeBus([":1.50", ":1.50"], FakeManager(actions), actions)
    agent._manager_interface = lambda manager: manager
    agent._establish_bluez_registration()
    assert actions == ["monitor", "owner", "manager", "register", "default", "owner"]
    assert agent.registered and agent.bluez_owner == ":1.50"
    agent._unregister()

    owner_shutdowns: list[tuple[str, int]] = []
    agent = harness([])
    agent.shutdown = lambda reason, code=0: owner_shutdowns.append((reason, code))
    agent._name_owner_changed(BLUEZ_SERVICE, ":1.50", ":1.51")
    assert owner_shutdowns == [("BlueZ restarted or stopped", 1)]

    print("vanhyprarch Bluetooth agent self-check passed", file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        return run_self_check()
    if len(sys.argv) != 1:
        print("usage: vanhyprarch_bluetooth_agent.py [--check]", file=sys.stderr)
        return 2

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    try:
        bus = dbus.SystemBus()
        agent = BluetoothAgent(bus, loop)
        agent.start()
    except Exception as error:
        print(
            "Bluetooth pairing agent startup failed: " + error.__class__.__name__,
            file=sys.stderr,
        )
        return 1

    def handle_signal(_signum: int, _frame: Any) -> None:
        GLib.idle_add(agent.shutdown, "Bluetooth pairing agent terminated", 0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        loop.run()
    finally:
        agent.shutdown("Bluetooth pairing agent exited", agent.exit_code)
        agent.remove_from_connection()
    return agent.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
