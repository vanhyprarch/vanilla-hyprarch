#!/usr/bin/python
"""Exercise AppPicker teardown through same-process Quickshell config reloads."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time


COMPONENTS = Path(__file__).resolve().parents[1] / "home/.config/quickshell/vanhyprarch/components"


def wait_for_load(process: subprocess.Popen, log: Path, count: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        output = log.read_text(encoding="utf-8", errors="replace")
        if output.count("APP_PICKER_RELOAD_READY") >= count:
            return
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise AssertionError(f"AppPicker did not survive reload {count - 1}:\n{log.read_text()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-picker-source", type=Path, default=COMPONENTS / "AppPicker.qml")
    source = parser.parse_args().app_picker_source
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-app-picker-reload-") as temporary:
        root = Path(temporary)
        config = root / "config/quickshell/app-picker-reload-test"
        components = config / "components"
        components.mkdir(parents=True)
        for component in COMPONENTS.iterdir():
            if component.name not in {"AppPicker.qml", "DockPopup.qml", "LauncherStore.qml"}:
                (components / component.name).symlink_to(component)
        (components / "AppPicker.qml").write_bytes(source.read_bytes())
        (components / "DockPopup.qml").write_text(
            """import QtQuick
Item {
    id: root
    required property var metrics
    required property Item popupAnchorItem
    property Item contentItem: root
    property int panelWidth: 0
    property int requestedPanelHeight: 0
    property bool alignToAnchorTop: false
    property int anchorTopOffset: 0
    property bool requestedVisible: false
}
""", encoding="utf-8")
        (components / "LauncherStore.qml").write_text(
            """import QtQuick
QtObject {
    property bool ready: true
    property bool editable: true
    function contains(desktopId: string): bool { return false }
    function addLauncher(desktopId: string): bool { return true }
}
""", encoding="utf-8")
        shell = config / "shell.qml"
        shell.write_text(
            """import QtQuick
import Quickshell
import "components"

ShellRoot {
    VisualMetrics { id: metrics; viewportWidth: 1000; viewportHeight: 800 }
    Theme { id: theme; metrics: metrics }
    LauncherStore { id: launcherStore }
    Window {
        visible: true
        width: 400
        height: 400
        Item { id: anchor }
        AppPicker {
            width: 320
            height: 320
            metrics: metrics
            theme: theme
            launcherStore: launcherStore
            popupAnchorItem: anchor
        }
    }
    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: console.log("APP_PICKER_RELOAD_READY")
    }
}
""", encoding="utf-8")
        applications = root / "data-home/applications"
        applications.mkdir(parents=True)
        for desktop_id, name in (("z-last", "Zebra"), ("a-first", "alpha")):
            (applications / f"{desktop_id}.desktop").write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name={name}\nExec=/usr/bin/true\n", encoding="utf-8")
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        (root / "data-dirs").mkdir()
        (root / "home").mkdir()
        environment = dict(os.environ)
        environment.update({
            "HOME": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(applications.parent),
            "XDG_DATA_DIRS": str(root / "data-dirs"),
            "XDG_RUNTIME_DIR": str(runtime),
            "QT_QPA_PLATFORM": "offscreen",
            "QS_NO_RELOAD_POPUP": "1",
        })
        environment.pop("WAYLAND_DISPLAY", None)
        environment.pop("DISPLAY", None)
        log = root / "quickshell.log"
        with log.open("wb") as stream:
            process = subprocess.Popen(["qs", "--no-color", "-p", str(config)],
                                       env=environment, stdout=stream,
                                       stderr=subprocess.STDOUT)
            try:
                wait_for_load(process, log, 1)
                for reload_number in range(1, 4):
                    with shell.open("a", encoding="utf-8") as output:
                        output.write(f"// AppPicker teardown probe {reload_number}\n")
                    wait_for_load(process, log, reload_number + 1)
                if process.poll() is not None:
                    raise AssertionError("Quickshell exited during the reload probe")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        output = log.read_text(encoding="utf-8", errors="replace")
        if "__cxa_pure_virtual" in output or "pure virtual method called" in output:
            raise AssertionError(f"AppPicker teardown hit a pure virtual call:\n{output}")
    print("AppPicker same-process configuration reload and teardown: PASS")


if __name__ == "__main__":
    main()
