import QtQuick
import Quickshell

Item {
    id: root

    required property var controller
    required property var theme
    required property var metrics
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
        source: Quickshell.iconPath(root.controller.visualCaffeine
            ? "caffeine" : "preferences-system-power")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        opacity: root.controller.ready
            ? 1.0 : root.metrics.disabledInteractiveOpacity
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            powerIdlePanel.visible = !powerIdlePanel.visible
            if (powerIdlePanel.visible)
                root.controller.refreshStatus(false)
        }
    }

    PowerIdlePanel {
        id: powerIdlePanel

        controller: root.controller
        theme: root.theme
        metrics: root.metrics
        popupAnchorItem: root
    }
}
