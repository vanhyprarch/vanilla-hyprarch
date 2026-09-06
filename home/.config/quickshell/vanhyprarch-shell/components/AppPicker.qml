pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property LauncherStore launcherStore
    property int panelWidth: 300
    property int panelHeight: 360
    property int panelPadding: 8
    property int rowHeight: 40
    required property int popupRadius
    property int popupHorizontalOffset: 8
    property int popupVerticalOffset: 0
    property color backgroundColor: "#FFF8F5"
    property color textColor: "#5A3525"
    property color hoverColor: "#FAEAE3"

    anchor {
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        // The centered 40px button ends 8px before the 56px dock's right edge.
        margins.right: -root.popupHorizontalOffset
        margins.bottom: -root.popupVerticalOffset
    }
    implicitWidth: panelWidth
    implicitHeight: panelHeight
    color: "transparent"
    grabFocus: true
    visible: false

    onVisibleChanged: {
        if (visible)
            applicationsView.positionViewAtBeginning()
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: 0
        topLeftRadius: 0
        bottomLeftRadius: 0
        topRightRadius: root.popupRadius
        bottomRightRadius: root.popupRadius

        ListView {
            id: applicationsView

            anchors.fill: parent
            anchors.margins: root.panelPadding
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: DesktopEntries.applications

            delegate: Rectangle {
                id: appRow

                required property DesktopEntry modelData
                readonly property bool alreadyAdded: root.launcherStore.contains(modelData.id)
                readonly property bool canAdd: root.launcherStore.ready && !alreadyAdded

                width: applicationsView.width
                height: root.rowHeight
                radius: root.popupRadius
                color: rowMouse.containsMouse && canAdd ? root.hoverColor : "transparent"
                opacity: canAdd ? 1 : 0.45

                onModelDataChanged: appIcon.failed = false

                Image {
                    id: appIcon

                    property bool failed: false
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    height: 24
                    source: Quickshell.iconPath(!failed && appRow.modelData.icon
                        ? appRow.modelData.icon : "application-x-executable", "application-x-executable")
                    sourceSize: Qt.size(24, 24)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                    onStatusChanged: {
                        if (status === Image.Error && !failed)
                            failed = true
                    }
                }

                Text {
                    anchors.left: appIcon.right
                    anchors.leftMargin: 10
                    anchors.right: addedLabel.left
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: appRow.modelData.name
                    color: root.textColor
                    font.pixelSize: 13
                    elide: Text.ElideRight
                    wrapMode: Text.NoWrap
                }

                Text {
                    id: addedLabel

                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: appRow.alreadyAdded ? "Added" : ""
                    color: root.textColor
                    font.pixelSize: 11
                }

                MouseArea {
                    id: rowMouse

                    anchors.fill: parent
                    enabled: appRow.canAdd
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.launcherStore.addLauncher(appRow.modelData.id)
                        root.visible = false
                    }
                }
            }
        }
    }
}
