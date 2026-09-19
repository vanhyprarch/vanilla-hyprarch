import QtQuick
import Quickshell

Item {
    id: root

    required property var controller
    required property var metrics
    readonly property int buttonSize: root.metrics.dockSystemControlTarget
    readonly property int iconSize: root.metrics.dockSystemIconSize

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    function activate(): void {
        if (root.controller.ready && !root.controller.busy)
            root.controller.toggleMode()
    }

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath(root.controller.darkMode
            ? "weather-clear-night"
            : "weather-clear")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        enabled: root.controller.ready && !root.controller.busy
        onClicked: root.activate()
    }
}
