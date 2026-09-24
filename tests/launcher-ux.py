#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the dock launcher error affordance in an isolated offscreen shell."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time


COMPONENTS = Path(__file__).resolve().parents[1] / "home/.config/quickshell/vanhyprarch/components"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-launcher-ux-") as temporary:
        root = Path(temporary)
        config = root / "config/quickshell/launcher-ux-test"
        components = config / "components"
        components.mkdir(parents=True)
        for source in COMPONENTS.iterdir():
            if source.name not in {"DockPopup.qml", "LauncherStore.qml"}:
                (components / source.name).symlink_to(source)
        (components / "DockPopup.qml").write_text("""import QtQuick
Item {
    id: root
    required property var metrics
    required property var targetScreen
    required property var focusCoordinator
    required property Item popupAnchorItem
    property Item contentItem: root
    property int panelWidth: 0
    property int requestedPanelHeight: 0
    property bool alignToAnchorTop: false
    property int anchorTopOffset: 0
    property bool requestedVisible: false
    width: panelWidth
    height: requestedPanelHeight
    visible: requestedVisible
}
""", encoding="utf-8")
        (components / "LauncherStore.qml").write_text("""import QtQuick
QtObject {
    property bool ready: true
    property bool editable: true
    property string errorMessage: ""
    property var launchers: []
    property bool retrySucceeds: true
    function contains(desktopId: string): bool { return false }
    function addLauncher(desktopId: string): bool { return editable }
    function removeLauncher(desktopId: string): bool { return editable }
    function moveLauncher(desktopId: string, index: int): bool { return editable }
    function retry(): void {
        if (retrySucceeds) {
            errorMessage = ""
            ready = true
            editable = true
        }
    }
}
""", encoding="utf-8")
        (config / "shell.qml").write_text("""import QtQuick
import Quickshell
import "components"

ShellRoot {
    VisualMetrics { id: metrics; viewportWidth: 1000; viewportHeight: 800 }
    Theme { id: theme; metrics: metrics }
    LauncherStore { id: store }
    QtObject {
        id: coordinator
        property var lastWindow: null
        function toggleDockWindow(window): void {
            lastWindow = window
            window.requestedVisible = !window.requestedVisible
        }
    }
    Window {
        id: testWindow
        visible: true
        width: 120
        height: 800
        Launchers {
            id: launchers
            theme: theme
            metrics: metrics
            store: store
            targetScreen: Quickshell.screens[0]
            focusCoordinator: coordinator
            anchors.fill: parent
        }
    }
    function find(item, name) {
        if (item.objectName === name) return item
        for (const child of item.children) {
            const found = find(child, name)
            if (found) return found
        }
        return null
    }
    function fail(message) { console.error("LAUNCHER_UX_FAILURE:" + message) }
    Timer {
        interval: 200
        running: true
        repeat: false
        onTriggered: {
            const add = find(launchers, "launcherAddControl")
            const diagnostic = find(launchers, "launcherStateDiagnostic")
            if (!add || !diagnostic) { fail("missing launcher control or popup"); return }
            const glyph = add.children.find(item => item.text !== undefined)
            const click = add.children.find(item => item.clicked !== undefined)
            if (!glyph || !click || glyph.text !== "+") { fail("normal plus"); return }
            click.clicked(null)
            if (!coordinator.lastWindow || coordinator.lastWindow === diagnostic) {
                fail("plus did not open normal picker"); return
            }
            store.ready = false
            store.editable = false
            store.errorMessage = "Invalid launcher JSON"
            if (glyph.text !== "?" || coordinator.lastWindow.requestedVisible) {
                fail("error did not replace plus and close picker"); return
            }
            click.clicked(null)
            if (coordinator.lastWindow !== diagnostic || !diagnostic.requestedVisible) {
                fail("left click did not open diagnostic"); return
            }
            const title = find(diagnostic, "launcherStateErrorTitle")
            const preserved = find(diagnostic, "launcherStatePreservedMessage")
            const retry = find(diagnostic, "launcherStateRetry")
            if (!title || title.text !== "Launcher state could not be loaded."
                    || !preserved || preserved.text !== "Your file was preserved."
                    || !retry || retry.primaryText !== "Retry") {
                fail("diagnostic content"); return
            }
            store.retrySucceeds = false
            retry.activated()
            if (!diagnostic.requestedVisible || glyph.text !== "?") {
                fail("failed retry changed diagnostic state"); return
            }
            store.retrySucceeds = true
            retry.activated()
            if (diagnostic.requestedVisible || glyph.text !== "+") {
                fail("successful retry did not restore plus"); return
            }
            console.log("LAUNCHER_UX_PASS")
        }
    }
}
""", encoding="utf-8")
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                           XDG_CONFIG_HOME=str(root / "config"),
                           XDG_STATE_HOME=str(root / "state"),
                           XDG_DATA_HOME=str(root / "data"),
                           XDG_DATA_DIRS=str(root / "data-dirs"),
                           XDG_RUNTIME_DIR=str(root / "runtime"),
                           QS_NO_RELOAD_POPUP="1")
        (root / "runtime").mkdir(mode=0o700)
        (root / "data").mkdir()
        (root / "data-dirs").mkdir()
        environment.pop("WAYLAND_DISPLAY", None)
        environment.pop("DISPLAY", None)
        process = subprocess.Popen(["qs", "--no-color", "-p", str(config)],
                                   env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 10
            lines = []
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                import select
                if select.select([process.stdout], [], [], 0.2)[0]:
                    line = process.stdout.readline()
                    lines.append(line)
                    if "LAUNCHER_UX_PASS" in line:
                        print("Launcher diagnostic dock UX: PASS")
                        return
                    if "LAUNCHER_UX_FAILURE:" in line:
                        break
            raise AssertionError("".join(lines))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
