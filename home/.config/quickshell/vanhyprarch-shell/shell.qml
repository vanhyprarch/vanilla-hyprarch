import QtQuick
import Quickshell

ShellRoot {
    PanelWindow {
        anchors {
            top: true
            left: true
            right: true
        }

        implicitHeight: 40
        exclusiveZone: 40
        color: "#1e1e1e"

        Text {
            anchors.centerIn: parent
            text: "Vanilla HyprArch Quickshell Test"
            color: "#ffffff"
        }
    }
}
