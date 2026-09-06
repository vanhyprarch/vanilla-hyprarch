pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property LauncherStore launcherStore
    property DesktopEntry desktopEntry
    property Item popupAnchorItem
    property bool pinned: true
    property bool running: false
    property int panelWidth: 150
    property int panelPadding: 6
    property int rowHeight: 36
    property int popupRadius: 14
    property int popupHorizontalOffset: 8
    property int popupVerticalOffset: 4
    property color backgroundColor: "#FFF8F5"
    property color textColor: "#5A3525"
    property color hoverColor: "#F3D8CC"

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Top
        gravity: Edges.Right | Edges.Bottom
        margins.right: -root.popupHorizontalOffset
        margins.top: -root.popupVerticalOffset
    }
    implicitWidth: panelWidth
    implicitHeight: actionsColumn.implicitHeight + panelPadding * 2
    color: "transparent"
    grabFocus: true
    visible: false

    function normalizeActionIdentifier(value): string {
        return value === null || value === undefined
            ? "" : String(value).trim().toLowerCase()
    }

    function openNewWindow(): void {
        if (!desktopEntry)
            return

        const actions = desktopEntry.actions || []
        const preferredIds = ["new-window", "newwindow", "new_window"]
        let newWindowAction = null

        for (const action of actions) {
            if (action && preferredIds.includes(normalizeActionIdentifier(action.id))) {
                newWindowAction = action
                break
            }
        }

        if (!newWindowAction) {
            for (const action of actions) {
                if (action && normalizeActionIdentifier(action.name) === "new window") {
                    newWindowAction = action
                    break
                }
            }
        }

        if (newWindowAction)
            newWindowAction.execute()
        else
            desktopEntry.execute()
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: 0
        topLeftRadius: 0
        bottomLeftRadius: 0
        topRightRadius: root.popupRadius
        bottomRightRadius: root.popupRadius

        Column {
            id: actionsColumn

            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: root.panelPadding
            spacing: 0

            Rectangle {
                width: parent.width
                height: root.rowHeight
                visible: root.running
                radius: 6
                color: newWindowMouse.containsMouse ? root.hoverColor : "transparent"

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Open New Window"
                    color: root.textColor
                    font.pixelSize: 13
                    wrapMode: Text.NoWrap
                }

                MouseArea {
                    id: newWindowMouse

                    anchors.fill: parent
                    enabled: root.desktopEntry !== null
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.openNewWindow()
                        root.visible = false
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: root.rowHeight
                radius: 6
                color: removeMouse.containsMouse ? root.hoverColor : "transparent"

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.pinned ? "Remove from dock" : "Pin to dock"
                    color: root.textColor
                    font.pixelSize: 13
                    wrapMode: Text.NoWrap
                }

                MouseArea {
                    id: removeMouse

                    anchors.fill: parent
                    enabled: root.desktopEntry !== null
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (root.pinned)
                            root.launcherStore.removeLauncher(root.desktopEntry.id)
                        else
                            root.launcherStore.addLauncher(root.desktopEntry.id)
                        root.visible = false
                    }
                }
            }
        }
    }
}
