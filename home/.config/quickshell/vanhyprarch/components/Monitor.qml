import QtQuick
import Quickshell

Item {
    id: root

    required property var theme
    required property var metrics
    required property var textSizeController
    required property var targetScreen
    required property var focusCoordinator
    readonly property int buttonSize: root.metrics.dockSystemControlTarget
    readonly property int iconSize: root.metrics.dockSystemIconSize

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath("preferences-desktop-display")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.focusCoordinator.toggleDockWindow(monitorPanel)
    }

    MonitorPanel {
        id: monitorPanel

        theme: root.theme
        metrics: root.metrics
        textSizeController: root.textSizeController
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        popupAnchorItem: root
    }
}
