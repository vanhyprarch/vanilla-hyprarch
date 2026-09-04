import QtQuick
import Quickshell

ShellRoot {
    property int dockWidth: 48

    PanelWindow {
        anchors {
            top: true
            bottom: true
            left: true
        }

        implicitWidth: dockWidth
        exclusiveZone: dockWidth
        color: "#1e1e1e"
    }
}
