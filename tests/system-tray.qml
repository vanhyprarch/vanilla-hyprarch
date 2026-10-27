//@ pragma UseQApplication
//@ pragma IconTheme Papirus
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Effects
import QtQuick.Controls.impl as ControlsImpl
import QtTest
import Quickshell
import Quickshell.Io
import Quickshell.Services.SystemTray as TrayService
import "components"

ShellRoot {
    id: root
    readonly property string output: Quickshell.env("TRAY_TEST_OUTPUT")
    readonly property string fixtures: Quickshell.env("TRAY_TEST_FIXTURES")
    readonly property int itemCount: Number(Quickshell.env("TRAY_TEST_COUNT"))
    readonly property int canvasHeight: 150 + (itemCount - 4) * 34
    property int pendingCaptures: 0
    property int phase: 0
    readonly property var phases: ["light", "dark", "light-return", "pixmap-update",
        "symbolic-update", "dark-update", "path-symbolic", "overlay", "attention",
        "named-color", "symbolic-return"]

    VisualMetrics { id: metrics }
    Theme { id: theme; metrics: metrics }
    QsMenuOpener { id: menuContents }

    // Untinted originals provide pixel references at the production icon size.
    FloatingWindow {
        id: reference
        implicitWidth: 176
        implicitHeight: 22
        color: "transparent"
        visible: true
        Row {
            id: originals
            Repeater {
                model: ["application.svg", "grayscale.svg", "cloud-symbolic.svg",
                    "pixmap0.png", "pixmap1.png", "overlay.png"]
                Image {
                    required property string modelData
                    width: 22; height: 22
                    source: root.fixtures + "/" + modelData
                    sourceSize: Qt.size(22, 22)
                }
            }
            // Keep the previous production pipeline as a root-cause control.
            Repeater {
                model: ["#3a3a3a", "#f4f4f3"]
                Item {
                    required property string modelData
                    width: 22; height: 22
                    Image {
                        id: oldSource
                        anchors.fill: parent
                        source: root.fixtures + "/application.svg"
                        sourceSize: Qt.size(22, 22)
                        visible: false
                    }
                    MultiEffect {
                        anchors.fill: oldSource
                        source: oldSource
                        colorization: 1.0
                        colorizationColor: parent.modelData
                    }
                }
            }
        }
    }

    FloatingWindow {
        id: window
        implicitWidth: 56
        implicitHeight: root.canvasHeight
        color: "transparent"
        visible: true
        Item {
            id: canvas
            anchors.fill: parent
            SystemTray { id: tray; x: 4; theme: theme; metrics: metrics }
        }
        TestEvent { id: events }
    }

    // Independent controls share the source URL and placement with production.
    // The application reference always fits the complete image; it never pads.
    FloatingWindow {
        implicitWidth: 56
        implicitHeight: root.canvasHeight
        color: "transparent"
        visible: true
        Item {
            id: fitReference
            width: 56; height: root.canvasHeight
            Repeater {
                model: TrayService.SystemTray.items
                Image {
                    required property var modelData
                    required property int index
                    x: 17; y: index * 34 + 5
                    width: 22; height: 22
                    source: modelData.icon
                    sourceSize: Qt.size(22, 22)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }
            }
        }
    }

    FloatingWindow {
        implicitWidth: 56
        implicitHeight: root.canvasHeight
        color: "transparent"
        visible: true
        Item {
            id: symbolicReference
            width: 56; height: root.canvasHeight
            Repeater {
                model: TrayService.SystemTray.items
                ControlsImpl.IconImage {
                    required property var modelData
                    required property int index
                    x: 17; y: index * 34 + 5
                    width: 22; height: 22
                    source: modelData.icon
                    color: theme.accent
                    sourceSize: Qt.size(22, 22)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }
            }
        }
    }

    function buttons() {
        return tray.children[0].children.filter(child => child.modelData !== undefined)
    }
    function button(id) {
        return buttons().find(child => child.modelData.id === id)
    }
    function image(item) {
        return item.children.find(child => child.source !== undefined && child.visible)
    }
    function menu(item) {
        return item.resources.find(child => child.open !== undefined)
    }
    function check(value, description) {
        if (!value)
            throw new Error(description)
    }

    function captureItem(item, suffix) {
        const filename = root.output + "/" + root.phases[root.phase] + suffix + ".png"
        // grabToImage applies the window DPR itself; keep the logical size.
        item.grabToImage(result => {
            root.check(result.saveToFile(filename), "capture failed: " + filename)
            if (--root.pendingCaptures === 0) {
                root.phase++
                if (root.phase < root.phases.length)
                    step.running = true
                else
                    interactions.start()
            }
        })
    }

    Process {
        id: step
        command: ["busctl", "--user", "call", "org.vanhyprarch.TrayFixture", "/Fixture",
            "org.vanhyprarch.TrayFixture", "Step", "i", String(root.phase)]
        onExited: (code, status) => {
            root.check(code === 0, "fixture step failed")
            if (root.phase < root.phases.length)
                settle.restart()
        }
    }

    Timer {
        interval: 50
        running: true
        repeat: true
        onTriggered: {
            if (root.buttons().length !== root.itemCount || root.buttons().some(
                    child => root.image(child).status !== Image.Ready))
                return
            stop()
            originals.grabToImage(result => {
                root.check(result.saveToFile(root.output + "/reference.png"), "reference capture")
                settle.start()
            })
        }
    }

    Timer {
        id: settle
        interval: 300
        onTriggered: {
            theme.darkMode = root.phase === 1 || root.phase === 5
            capture.restart()
        }
    }
    Timer {
        id: capture
        interval: 150
        onTriggered: {
            root.check(tray.width === metrics.dockContentWidth, "tray width")
            root.check(tray.height === root.itemCount * metrics.dockTrayTarget
                + (root.itemCount - 1) * metrics.dockTrayGap, "tray height/spacing")
            const metadata = root.buttons().map((child, index) => {
                const icon = root.image(child)
                root.check(child.width === 32 && child.height === 32, "click target")
                root.check(child.x === 8 && child.y === index * 34, "tray placement")
                root.check(icon.width === 22 && icon.height === 22, "icon size")
                root.check(icon.x === 5 && icon.y === 5, "icon centering")
                root.check(icon.status === Image.Ready, "image load")
                if (!child.symbolic)
                    root.check(icon.fillMode === Image.PreserveAspectFit, "application aspect-fit")
                return { id: child.modelData.id, x: tray.x + child.x + icon.x,
                    y: child.y + icon.y, buttonX: tray.x + child.x, buttonY: child.y,
                    source: String(icon.source), symbolic: child.symbolic,
                    fillMode: icon.fillMode, painted: [icon.paintedWidth, icon.paintedHeight] }
            })
            console.log("TRAY_METADATA " + JSON.stringify({
                phase: root.phases[root.phase], dpr: window.devicePixelRatio, icons: metadata }))
            root.pendingCaptures = 3
            root.captureItem(canvas, "")
            root.captureItem(fitReference, "-fit")
            root.captureItem(symbolicReference, "-symbolic")
        }
    }

    Timer {
        id: interactions
        interval: 100
        property int stage: 0
        repeat: true
        onTriggered: {
            const item = root.button("color")
            const anchor = root.menu(item)
            if (stage === 0) {
                const area = item.children.find(child => child.acceptedButtons !== undefined)
                root.check(area.hoverEnabled && area.cursorShape === Qt.PointingHandCursor,
                    "hover/cursor policy")
                root.check(events.mouseMove(item, 16, 16, 0, 0, 0), "hover event")
                root.check(area.containsMouse, "hover hit target")
                root.check(events.mouseClick(item, 16, 16, Qt.LeftButton, 0, 0), "left click")
                root.check(events.mouseClick(item, 16, 16, Qt.MiddleButton, 0, 0), "middle click")
                root.check(events.mouseClick(item, 16, 16, Qt.RightButton, 0, 0), "right click")
                menuContents.menu = item.modelData.menu
            } else if (stage === 1) {
                root.check(anchor.visible, "application context menu did not open")
                const action = menuContents.children.values[0]
                root.check(action && action.text === "Fixture action" && action.enabled,
                    "application context menu contents")
                action.triggered()
                anchor.close()
                root.phase = root.phases.length
                step.running = true
            } else if (stage === 2) {
                root.check(item.modelData.onlyMenu, "menu-only update")
                root.check(events.mouseClick(item, 16, 16, Qt.LeftButton, 0, 0), "menu-only click")
            } else {
                root.check(anchor.visible, "menu-only left click did not open menu")
                anchor.close()
                console.log("vanhyprarch system tray self-check passed")
                Qt.quit()
                stop()
            }
            stage++
        }
    }
    Timer {
        interval: 12000
        running: true
        onTriggered: { console.error("TRAY_FAILURE: timed out"); Qt.quit() }
    }
}
