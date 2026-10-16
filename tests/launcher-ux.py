#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise production launcher geometry and diagnostics in an offscreen shell."""

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
    property int editRequests: 0
    function contains(desktopId: string): bool {
        return launchers.some(launcher => launcher.desktopId === desktopId)
    }
    function addLauncher(desktopId: string): bool { editRequests++; return editable }
    function removeLauncher(desktopId: string): bool { editRequests++; return editable }
    function moveLauncher(desktopId: string, index: int): bool { editRequests++; return editable }
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
    VisualMetrics { id: metrics; viewportWidth: 1000; viewportHeight: testWindow.height }
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
        Item {
            id: topRegion
            width: parent.width
            height: metrics.dockTopRegionHeight(80)
        }
        Item {
            id: bottomRegion
            property int trayCount: 0
            anchors.bottom: parent.bottom
            width: parent.width
            height: metrics.dockSystemRegionHeight(topRegion.height,
                200 + tray.implicitHeight
                    + (tray.implicitHeight > 0 ? metrics.dockGroupGap : 0))
            Column {
                id: tray
                spacing: metrics.dockTrayGap
                Repeater {
                    model: bottomRegion.trayCount
                    Item { width: metrics.dockTrayTarget; height: width }
                }
            }
        }
        Item {
            id: middleRegion
            width: parent.width
            y: topRegion.height
            height: metrics.dockLauncherRegionHeight(topRegion.height, bottomRegion.height)
            clip: true
            readonly property int inset: height > metrics.dockItemGap * 2
                ? metrics.dockItemGap : 0
            Launchers {
                id: launchers
                theme: theme
                metrics: metrics
                store: store
                targetScreen: Quickshell.screens[0]
                focusCoordinator: coordinator
                anchors.fill: parent
                anchors.topMargin: middleRegion.inset
                anchors.bottomMargin: middleRegion.inset
            }
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
    function check(condition, message) {
        if (!condition) throw new Error(message)
    }
    function near(actual, expected, message) {
        check(Math.abs(actual - expected) <= 0.5,
            message + ": " + actual + " != " + expected)
    }
    function setPins(count) {
        store.launchers = Array.from({ length: count }, (_, index) =>
            ({ desktopId: "dock-fixture-" + String(index).padStart(2, "0") }))
    }
    function viewport() {
        return find(launchers, "launcherAddControl").parent.parent.parent
    }
    function geometry(pinnedCount, runtimeCount) {
        const add = find(launchers, "launcherAddControl")
        const content = add.parent
        const view = viewport()
        check(content.parent === view.contentItem, "unexpected Column parent")
        near(view.contentItem.height, view.contentHeight, "contentItem height")
        check(launchers.resolvedLaunchers.length === pinnedCount, "favorite count")
        check(launchers.runtimeLaunchers.length === runtimeCount, "unpinned count")
        const count = pinnedCount + runtimeCount + 1
        near(content.height, count * launchers.buttonSize + (count - 1) * launchers.spacing,
            "natural launcher stack height")
        near(content.y, Math.max(0, (view.height - content.height) / 2), "content center")
        const position = content.mapToItem(middleRegion, 0, 0)
        if (content.height <= view.height) {
            check(Math.abs(position.y
                - (middleRegion.height - position.y - content.height)) <= 1,
                "free gaps exceed normal center rounding")
            near(view.contentY, 0, "fitting scroll position")
        }
        near(topRegion.y + topRegion.height, middleRegion.y, "top boundary")
        near(middleRegion.y + middleRegion.height, bottomRegion.y, "bottom boundary")
        check(view.clip && middleRegion.clip, "overflow clipping")

        const diagnostic = find(launchers, "launcherStateDiagnostic")
        const pickerAnchor = diagnostic.popupAnchorItem
        near(pickerAnchor.y, add.mapToItem(pickerAnchor.parent, 0, 0).y, "picker anchor")
        const first = content.children.find(item => item.desktopEntry !== undefined)
        if (first) {
            launchers.contextMenuSourceAnchor = first
            const menu = launchers.children.find(item => item.pinned !== undefined)
            const anchor = menu.popupAnchorItem
            near(anchor.y, first.mapToItem(anchor.parent, 0, 0).y, "context anchor")
        }
        const targets = view.contentItem.children.filter(item =>
            item.keys !== undefined && item.keys[0] === "pinned-launcher")
        check(targets.length === pinnedCount + 1, "drag target count")
        for (const target of targets) {
            near(target.mapToItem(content, 0, 0).y,
                launchers.insertionTargetY(target.index), "reactive drag target")
        }
        if (pinnedCount > 0) {
            launchers.activeDragDesktopId = store.launchers[0].desktopId
            launchers.pendingDropIndex = 1
            const indicator = view.contentItem.children.find(item => item.z === 11)
            near(indicator.y, content.y + launchers.insertionIndicatorY(1), "drag indicator")
            launchers.activeDragDesktopId = ""
            launchers.pendingDropIndex = -1
        }
        check(store.editRequests === 0, "geometry requested a launcher-state edit")
        return middleRegion.y + position.y + content.height / 2
    }
    Timer {
        interval: 50
        running: true
        repeat: true
        property int phase: 0
        property real previousCenter: 0
        onTriggered: {
            if (DesktopEntries.applications.values.length !== 24) return
            try {
                if (phase === 0) {
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
                    setPins(0)
                } else if (phase === 1) {
                    geometry(0, 0); setPins(3)
                } else if (phase === 2) {
                    geometry(3, 0)
                    launchers.runtimeOrder = ["dock-fixture-20", "dock-fixture-21"]
                } else if (phase === 3) {
                    geometry(3, 2); launchers.runtimeOrder = []
                } else if (phase === 4) {
                    previousCenter = geometry(3, 0); bottomRegion.trayCount = 3
                } else if (phase === 5) {
                    check(geometry(3, 0) < previousCenter, "tray growth did not move launchers up")
                    setPins(20)
                } else if (phase === 6) {
                    geometry(20, 0)
                    check(viewport().contentHeight > viewport().height, "missing launcher overflow")
                    check(viewport().atYBeginning, "overflow did not start at beginning")
                    viewport().contentY = viewport().contentHeight - viewport().height
                } else if (phase === 7) {
                    geometry(20, 0); check(viewport().atYEnd, "end is unreachable")
                    viewport().contentY = 0
                } else if (phase === 8) {
                    check(viewport().atYBeginning, "beginning is unreachable"); setPins(1)
                } else if (phase === 9) {
                    geometry(1, 0); setPins(3); testWindow.height = 240
                } else if (phase === 10) {
                    geometry(3, 0); check(viewport().height === 0, "zero-height policy changed")
                    testWindow.height = 540; bottomRegion.trayCount = 0
                } else if (phase === 11) {
                    geometry(3, 0); testWindow.height = 800; bottomRegion.trayCount = 2
                } else if (phase === 12) {
                    geometry(3, 0); setPins(12)
                } else if (phase === 13) {
                    geometry(12, 0)
                    viewport().contentY = viewport().contentHeight - viewport().height
                } else if (phase === 14) {
                    geometry(12, 0); check(viewport().atYEnd, "resized end is unreachable")
                    testWindow.height = 1200
                } else if (phase === 15) {
                    geometry(12, 0); setPins(0)
                } else {
                    geometry(0, 0)
                    running = false
                    console.log("LAUNCHER_UX_PASS")
                }
                phase += 1
            } catch (error) {
                running = false
                fail("phase " + phase + ": " + error.message)
            }
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
        (root / "home").mkdir()
        environment["HOME"] = str(root / "home")
        environment["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(root / "runtime/no-bus")
        applications = root / "data/applications"
        applications.mkdir()
        icon = root / "data/fixture.svg"
        icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28">'
                        '<rect width="28" height="28" fill="blue"/></svg>\n', encoding="utf-8")
        for index in range(24):
            (applications / f"dock-fixture-{index:02d}.desktop").write_text(
                f"[Desktop Entry]\nType=Application\nName=Dock fixture {index}\n"
                f"Exec=/usr/bin/true\nIcon={icon}\nTerminal=false\n", encoding="utf-8")
        environment.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
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
                        print("Production launcher geometry, popup/drag anchors, and diagnostic UX: PASS")
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
