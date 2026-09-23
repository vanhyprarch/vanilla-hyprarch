import QtQuick
import QtQuick.Window
import Quickshell
import "components"

ShellRoot {
    id: root

    readonly property string outputDirectory:
        Quickshell.env("VANHYPRARCH_SYSTEM_ICON_RENDER_DIR")

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
        height: 28
        visible: true
        color: "transparent"

        SystemIcon {
            id: darkIcon
            parent: renderWindow.contentItem
            x: 4
            y: 4
            iconName: "information"
            theme: darkTheme
            metrics: metrics
        }

        SystemIcon {
            id: lightIcon
            parent: renderWindow.contentItem
            x: 28
            y: 4
            iconName: "information"
            theme: lightTheme
            metrics: metrics
        }
    }

    Timer {
        interval: 50
        running: true
        repeat: true
        onTriggered: {
            if (!darkIcon.ready || !lightIcon.ready)
                return
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
