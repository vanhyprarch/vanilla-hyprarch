import QtQuick
import Quickshell

Item {
    id: root

    required property var controller
    required property var theme
    required property var metrics
    required property var targetScreen
    required property var focusCoordinator
    readonly property int buttonSize: root.metrics.dockSystemControlTarget

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    SystemIcon {
        anchors.centerIn: parent
        iconName: root.controller.caffeine ? "coffee" : "zap"
        theme: root.theme
        metrics: root.metrics
        opacity: root.controller.ready
            ? 1.0 : root.metrics.disabledInteractiveOpacity
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            root.focusCoordinator.toggleDockWindow(powerIdlePanel)
            if (powerIdlePanel.requestedVisible)
                root.controller.refreshStatus(false)
        }
    }

    PowerIdlePanel {
        id: powerIdlePanel

        controller: root.controller
        theme: root.theme
        metrics: root.metrics
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        popupAnchorItem: root
    }
}
