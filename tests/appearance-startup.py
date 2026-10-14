#!/usr/bin/python
"""Render the dock's startup visibility binding with a controlled backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


REPOSITORY = Path(__file__).resolve().parents[1]
SHELL = REPOSITORY / "home/.config/quickshell/vanhyprarch/shell.qml"
COMPONENTS = SHELL.parent / "components"


def wait_for(predicate, process, log):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        if process.poll() is not None:
            break
        time.sleep(0.02)
    raise AssertionError(f"startup fixture did not complete:\n{log.read_text()}")


def run_case(mode, reconcile_fails=False, invalid_status=False):
    # Exercise the actual production visibility expression, including the old
    # implicit PanelWindow default, so this test fails against the original bug.
    dock = SHELL.read_text().split("id: dockWindow", 1)[1].split("anchors {", 1)[0]
    binding = re.search(r"^\s*visible:\s*(.+)$", dock, re.MULTILINE)
    visible = binding.group(1) if binding else "true"
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-appearance-startup-") as temporary:
        root = Path(temporary)
        (root / "components").symlink_to(COMPONENTS)
        (root / "runtime").mkdir(mode=0o700)
        preference = root / "appearance.json"
        preference.write_text(json.dumps({"version": 1, "mode": mode,
            "light_wallpaper": None, "dark_wallpaper": None}))
        original = preference.read_bytes()
        gate = root / "gate"
        os.mkfifo(gate, 0o600)
        gate_fd = os.open(gate, os.O_RDWR | os.O_NONBLOCK)
        backend = root / "vanhyprarch-appearance"
        backend.write_text('''#!/usr/bin/python
import json, os, pathlib, sys
root = pathlib.Path(os.environ["APPEARANCE_TEST_ROOT"])
command = sys.argv[1]
if command == "reconcile":
    with (root / "gate").open() as gate:
        gate.readline()
    if os.environ["APPEARANCE_TEST_RECONCILE_FAILS"] == "1":
        print("fixture renderer unavailable", file=sys.stderr)
        sys.exit(1)
elif command == "set-mode":
    preference = json.loads((root / "appearance.json").read_text())
    preference["mode"] = sys.argv[2]
    (root / "appearance.json").write_text(json.dumps(preference))
elif command == "status":
    if os.environ["APPEARANCE_TEST_INVALID_STATUS"] == "1":
        print("{}")
        sys.exit(0)
    mode = json.loads((root / "appearance.json").read_text())["mode"]
    dark = mode == "dark"
    print(json.dumps(dict(version=1, initialized=True, mode=mode,
        current_wallpaper=None, wallpapers=dict(light=dict(path=None), dark=dict(path=None)),
        directories=dict(light="/pictures/Light", dark="/pictures/Dark"),
        host=dict(expected_portal=1 if dark else 2,
            expected_gsettings="prefer-dark" if dark else "prefer-light", expected_gtk3=dark,
            gsettings="prefer-dark" if dark else "prefer-light", portal=1 if dark else 2,
            gtk3_configured=dark, gtk3_effective=dark),
        renderer=dict(state="unavailable", matches=False, active={}),
        errors=["fixture renderer unavailable"])))
else:
    sys.exit(2)
''')
        backend.chmod(0o755)
        (root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "components"
ShellRoot {
    id: root
    property int frames: 0
    VisualMetrics { id: metrics }
    Theme { id: theme; metrics: metrics }
    AppearanceController { id: appearanceController; theme: theme }
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({ready: appearanceController.ready,
                visible: dock.visible, dark: theme.darkMode, frames: root.frames,
                busy: appearanceController.busy, error: appearanceController.errorMessage})
        }
        function switchMode(mode: string): void { appearanceController.requestMode(mode) }
    }
    Window {
        id: dock
        width: 64; height: 64
        visible: ''' + visible + '''
        Rectangle { anchors.fill: parent; color: theme.background }
        onFrameSwapped: {
            root.frames++
            console.log("DOCK_FRAME " + JSON.stringify({dark: theme.darkMode,
                ready: appearanceController.ready, color: theme.background.toString()}))
        }
    }
    // An independent frame proves the event loop/rendering ran while the
    // backend was held, even when the dock correctly remains unmapped.
    Window {
        width: 1; height: 1; visible: true
        onFrameSwapped: console.log("WITNESS_FRAME")
    }
}
''')
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
            QSG_RENDER_LOOP="basic", XDG_RUNTIME_DIR=str(root / "runtime"),
            XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state"),
            XDG_DATA_HOME=str(root / "data"), HOME=str(root),
            PATH=f"{root}:/usr/bin", APPEARANCE_TEST_ROOT=str(root),
            APPEARANCE_TEST_RECONCILE_FAILS=str(int(reconcile_fails)),
            APPEARANCE_TEST_INVALID_STATUS=str(int(invalid_status)))
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("DISPLAY", None)
        log = root / "quickshell.log"
        with log.open("w") as stream:
            process = subprocess.Popen(["qs", "--no-color", "-p", str(root)],
                env=env, stdout=stream, stderr=subprocess.STDOUT)
            def ipc(function, *args):
                return subprocess.run(["qs", "ipc", "-p", str(root), "call", "test",
                    function, *args], env=env, capture_output=True, text=True, timeout=3)
            def state():
                result = ipc("state")
                return json.loads(result.stdout) if result.returncode == 0 else None
            try:
                wait_for(lambda: "WITNESS_FRAME" in log.read_text(), process, log)
                initial = wait_for(state, process, log)
                assert not initial["ready"] and not initial["visible"] and initial["frames"] == 0, initial
                assert preference.read_bytes() == original
                os.write(gate_fd, b"continue\n")
                if invalid_status:
                    failed = wait_for(lambda: (s if (s := state()) and s["error"] else None), process, log)
                    assert not failed["ready"] and not failed["visible"] and failed["frames"] == 0, failed
                else:
                    ready = wait_for(lambda: (s if (s := state()) and s["ready"] and s["frames"] else None), process, log)
                    assert ready["visible"] and ready["dark"] == (mode == "dark"), ready
                    first = json.loads(re.search(r"DOCK_FRAME (.+)", log.read_text()).group(1))
                    assert first == dict(dark=mode == "dark", ready=True,
                        color="#1c1714" if mode == "dark" else "#fff8f5"), first
                    assert ready["error"] == "fixture renderer unavailable", ready
                    assert preference.read_bytes() == original
                    for next_mode in ("light", "dark", mode):
                        wait_for(lambda: (s := state()) and not s["busy"], process, log)
                        assert ipc("switchMode", next_mode).returncode == 0
                        switched = wait_for(lambda: (s if (s := state()) and not s["busy"]
                            and s["dark"] == (next_mode == "dark") else None), process, log)
                        assert switched["visible"] and switched["ready"], switched
                        assert json.loads(preference.read_text())["mode"] == next_mode
            finally:
                process.terminate()
                process.wait(timeout=5)
                os.close(gate_fd)
        print(f"Appearance startup: {mode}, reconcile_fails={reconcile_fails}, invalid_status={invalid_status}: PASS")


if __name__ == "__main__":
    run_case("dark")
    run_case("light")
    run_case("dark", reconcile_fails=True)
    run_case("dark", invalid_status=True)
