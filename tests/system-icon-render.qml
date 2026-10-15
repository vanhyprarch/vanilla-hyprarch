pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import Quickshell
import "components"

ShellRoot {
    id: root

    readonly property string outputDirectory:
        Quickshell.env("VANHYPRARCH_SYSTEM_ICON_RENDER_DIR")
    readonly property var icons: ["bluetooth", "bluetooth-searching", "bluetooth-off",
        "bluetooth-connected", "ethernet-port", "wifi", "wifi-high", "wifi-low",
        "globe-off", "volume-2", "volume-1", "volume", "volume-off", "monitor-cog",
        "zap", "sun", "moon", "info"]

    VisualMetrics {
        id: metrics
    }

    Theme {
        id: darkTheme
        metrics: metrics
        darkMode: true
    }

    Theme {
        id: lightTheme
        metrics: metrics
        darkMode: false
    }

    Window {
        id: renderWindow

        width: 52
        height: 28 * root.icons.length
        visible: true
        color: "transparent"

        Repeater {
            id: rows
            parent: renderWindow.contentItem
            model: root.icons
            Item {
                required property int index
                required property string modelData
                readonly property bool ready: darkIcon.ready && lightIcon.ready
                y: index * 28
                width: 52
                height: 28
                SystemIcon {
                    id: darkIcon
                    x: 4; y: 4
                    iconName: parent.modelData
                    theme: darkTheme
                    metrics: metrics
                }
                SystemIcon {
                    id: lightIcon
                    x: 28; y: 4
                    iconName: parent.modelData
                    theme: lightTheme
                    metrics: metrics
                }
            }
        }
    }

    Timer {
        interval: 50
        running: true
        repeat: true
        onTriggered: {
            for (let index = 0; index < rows.count; index++) {
                if (!rows.itemAt(index) || !rows.itemAt(index).ready)
                    return
            }
            stop()
            captureTimer.start()
        }
    }

    Timer {
        id: captureTimer

        interval: 250
        repeat: false
        onTriggered: {
            renderWindow.contentItem.grabToImage(function(result) {
                if (!result.saveToFile(root.outputDirectory + "/icons.png")) {
                    console.error("SYSTEM_ICON_RENDER_FAILURE: save failed")
                    Qt.quit()
                    return
                }
                console.log("vanhyprarch system icon render self-check passed")
                Qt.quit()
            })
        }
    }

    Timer {
        interval: 5000
        running: true
        repeat: false
        onTriggered: {
            console.error("SYSTEM_ICON_RENDER_FAILURE: render timed out")
            Qt.quit()
        }
    }
}
