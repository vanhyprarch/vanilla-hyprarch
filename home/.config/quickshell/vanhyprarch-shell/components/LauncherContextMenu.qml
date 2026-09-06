pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property LauncherStore launcherStore
    property string desktopId: ""
    property Item popupAnchorItem
    property int panelWidth: 150
    property int panelPadding: 6
    property int rowHeight: 36
    property int popupRadius: 14
    property int popupHorizontalOffset: 8
    property int popupVerticalOffset: 0
    property color backgroundColor: "#FFF8F5"
    property color textColor: "#5A3525"
    property color hoverColor: "#F3D8CC"

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: -root.popupHorizontalOffset
        margins.bottom: -root.popupVerticalOffset
    }
    implicitWidth: panelWidth
    implicitHeight: rowHeight + panelPadding * 2
    color: "transparent"
    grabFocus: true
    visible: false

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: 0
        topLeftRadius: 0
        bottomLeftRadius: 0
        topRightRadius: root.popupRadius
        bottomRightRadius: root.popupRadius

        Column {
            anchors.fill: parent
            anchors.margins: root.panelPadding

            Rectangle {
                width: parent.width
                height: root.rowHeight
                radius: 6
                color: removeMouse.containsMouse ? root.hoverColor : "transparent"

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Remove from dock"
                    color: root.textColor
                    font.pixelSize: 13
                    wrapMode: Text.NoWrap
                }

                MouseArea {
                    id: removeMouse

                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.launcherStore.removeLauncher(root.desktopId)
                        root.visible = false
                    }
                }
            }
        }
    }
}
