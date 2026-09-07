import QtQuick
import Quickshell

Item {
    id: root

    property int buttonSize: 40
    property int iconSize: 28
    required property int popupRadius

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
        onClicked: monitorPanel.visible = !monitorPanel.visible
    }

    MonitorPanel {
        id: monitorPanel

        popupAnchorItem: root
        popupRadius: root.popupRadius
    }
}
