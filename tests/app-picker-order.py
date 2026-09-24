#!/usr/bin/python
"""Check AppPicker order, delegate identity, activation, and live updates."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time


COMPONENTS = Path(__file__).resolve().parents[1] / "home/.config/quickshell/vanhyprarch/components"

FIXTURES = (
    ("z-last", "zebra"),
    ("z-same", "Same"),
    ("b-alpha", "Alpha"),
    ("c-beta", "beta"),
    ("a-same", "Same"),
    ("a-alpha", "alpha"),
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-app-picker-order-") as temporary:
        root = Path(temporary)
        config = root / "config/quickshell/app-picker-order-test"
        components = config / "components"
        components.mkdir(parents=True)
        for source in COMPONENTS.iterdir():
            if source.name not in {"DockPopup.qml", "LauncherStore.qml"}:
                (components / source.name).symlink_to(source)

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
""",
            encoding="utf-8",
        )
        (components / "LauncherStore.qml").write_text(
            """import QtQuick
QtObject {
    property bool ready: true
    property string addedId: ""
    function contains(desktopId: string): bool { return false }
    function addLauncher(desktopId: string): bool {
        addedId = desktopId
        return true
    }
}
""",
            encoding="utf-8",
        )
        (config / "shell.qml").write_text(
            """import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    VisualMetrics { id: metrics; viewportWidth: 1000; viewportHeight: 800 }
    Theme { id: theme; metrics: metrics }
    LauncherStore { id: launcherStore }
    Window {
        id: testWindow
        visible: true
        width: 400
        height: 400
        Item { id: anchor }
        AppPicker {
            id: picker
            parent: testWindow.contentItem
            width: 320
            height: 320
            metrics: metrics
            theme: theme
            launcherStore: launcherStore
            popupAnchorItem: anchor
        }
    }

    function fail(message) {
        console.error("APP_PICKER_ORDER_FAILURE: " + message)
    }

    function findItem(item, name) {
        if (item.objectName === name)
            return item
        for (const child of item.children) {
            const found = findItem(child, name)
            if (found)
                return found
        }
        return null
    }

    Timer {
        interval: 50
        running: true
        repeat: true
        property int stage: 0
        onTriggered: {
            const expectedCount = stage === 1 ? 7 : 6
            if (DesktopEntries.applications.values.length !== expectedCount)
                return
            const view = root.findItem(picker, "appPickerApplicationsView")
            if (!view || view.count !== expectedCount)
                return

            const expectedIds = stage === 0
                ? ["a-alpha", "b-alpha", "c-beta", "a-same", "z-same", "z-last"]
                : stage === 1
                ? ["aa-new", "a-alpha", "b-alpha", "c-beta", "a-same", "z-same", "z-last"]
                : ["aa-new", "a-alpha", "b-alpha", "c-beta", "a-same", "z-same"]
            const expectedNames = stage === 0
                ? ["alpha", "Alpha", "beta", "Same", "Same", "zebra"]
                : stage === 1
                ? ["aardvark", "alpha", "Alpha", "beta", "Same", "Same", "zebra"]
                : ["aardvark", "alpha", "Alpha", "beta", "Same", "Same"]
            const sourceIds = DesktopEntries.applications.values.map(
                entry => entry.id)
            if (stage === 0 && sourceIds.join(",") === expectedIds.join(",")) {
                root.fail("desktop-entry fixture arrived already sorted")
                stop()
                return
            }
            for (let index = 0; index < expectedIds.length; ++index) {
                const row = view.itemAtIndex(index)
                if (!row)
                    return
                const nativeEntry = DesktopEntries.byId(expectedIds[index])
                if (row.modelData !== nativeEntry
                        || row.modelData.id !== expectedIds[index]
                        || row.modelData.name !== expectedNames[index]
                        || row.primaryText !== expectedNames[index]) {
                    root.fail("wrong row at " + index + ": "
                        + (row.modelData ? row.modelData.id : "missing"))
                    return
                }
            }

            if (stage === 0) {
                stage = 1
                console.log("APP_PICKER_INITIAL_PASS")
                return
            }
            if (stage === 1) {
                stage = 2
                console.log("APP_PICKER_ADD_PASS")
                return
            }

            picker.requestedVisible = true
            view.itemAtIndex(3).activated()
            if (launcherStore.addedId !== "c-beta" || picker.requestedVisible)
                root.fail("activation lost the sorted row's desktop ID")
            else
                console.log("APP_PICKER_ORDER_PASS")
            stop()
        }
    }
}
""",
            encoding="utf-8",
        )

        applications = root / "data-home/applications"
        applications.mkdir(parents=True)
        for desktop_id, name in FIXTURES:
            (applications / f"{desktop_id}.desktop").write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name={name}\nExec=/usr/bin/true\nIcon=application-x-executable\n",
                encoding="utf-8",
            )

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
            "LANG": "C.UTF-8",
        })
        environment.pop("WAYLAND_DISPLAY", None)
        environment.pop("DISPLAY", None)

        log = root / "quickshell.log"
        with log.open("wb") as stream:
            process = subprocess.Popen(
                ["qs", "--no-color", "-p", str(config)],
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 15
                added = False
                removed = False
                while time.monotonic() < deadline:
                    output = log.read_text(encoding="utf-8", errors="replace")
                    if "APP_PICKER_INITIAL_PASS" in output and not added:
                        (applications / "aa-new.desktop").write_text(
                            "[Desktop Entry]\nType=Application\nName=aardvark\n"
                            "Exec=/usr/bin/true\nIcon=application-x-executable\n",
                            encoding="utf-8",
                        )
                        added = True
                    if "APP_PICKER_ADD_PASS" in output and not removed:
                        (applications / "z-last.desktop").unlink()
                        removed = True
                    if "APP_PICKER_ORDER_PASS" in output or "APP_PICKER_ORDER_FAILURE" in output:
                        break
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        output = log.read_text(encoding="utf-8", errors="replace")
        if "APP_PICKER_ORDER_PASS" not in output or "APP_PICKER_ORDER_FAILURE" in output:
            raise AssertionError(f"AppPicker order test failed:\n{output}")
        if "critical" in output.lower() or "FATAL" in output:
            raise AssertionError(f"AppPicker emitted an error:\n{output}")
    print("AppPicker order, modelData, activation, and live updates: PASS")


if __name__ == "__main__":
    main()
