pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

Item {
    id: root

    required property var theme
    required property var metrics
    readonly property int buttonSize: root.metrics.dockPowerButtonTarget
    property int bottomMargin: root.metrics.dockOuterInset
    property color buttonColor: root.theme.surface
    property color buttonHoverColor: root.theme.hover
    property color iconColor: root.theme.accent
    property color popupColor: root.theme.background
    property color textColor: root.theme.text
    property int popupWidth: 150
    required property int popupRadius
    property int popupHorizontalGap: -16
    property int popupVerticalOffset: -2

    property string pendingAction: ""

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight
    anchors.bottomMargin: bottomMargin

    function runAction(action: string): void {
        popup.visible = false
        switch (action) {
        case "lock":
            Quickshell.execDetached(["loginctl", "lock-session"])
            break
        case "suspend":
            Quickshell.execDetached(["systemctl", "suspend"])
            break
        case "logout":
            Quickshell.execDetached(["hyprshutdown"])
            break
        case "reboot":
            Quickshell.execDetached(["systemctl", "reboot"])
            break
        case "poweroff":
            Quickshell.execDetached(["systemctl", "poweroff"])
            break
        }
    }

    Rectangle {
        id: powerButton

        anchors.fill: parent
        radius: width / 2
        color: "transparent"

        Text {
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: 1
            anchors.verticalCenterOffset: 4
            text: "⏻"
            color: root.iconColor
            font.pixelSize: 24
        }

        MouseArea {
            id: buttonMouse

            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: popup.visible = !popup.visible

            containmentMask: QtObject {
                function contains(point: point): bool {
                    const radius = buttonMouse.width / 2
                    const dx = point.x - buttonMouse.width / 2
                    const dy = point.y - buttonMouse.height / 2
                    return dx * dx + dy * dy <= radius * radius
                }
            }
        }
    }

    component ActionRow: Rectangle {
        id: row

        required property string label
        signal activated()

        width: root.popupWidth - 16
        height: 36
        radius: root.popupRadius
        color: rowMouse.containsMouse ? root.buttonHoverColor : "transparent"

        Text {
            anchors {
                left: parent.left
                leftMargin: 12
                verticalCenter: parent.verticalCenter
            }
            text: row.label
            color: root.textColor
            font.pixelSize: 14
        }

        MouseArea {
            id: rowMouse

            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: row.activated()
        }
    }

    PopupWindow {
        id: popup

        anchor {
            item: powerButton
            edges: Edges.Right | Edges.Bottom
            gravity: Edges.Right | Edges.Top
            // Include the space between the centered button and the dock edge.
            margins.right: Math.max(0, (root.parent.width - root.width) / 2) + root.popupHorizontalGap
            margins.bottom: root.popupVerticalOffset
        }
        implicitWidth: root.popupWidth
        implicitHeight: (root.pendingAction === "" ? actionMenu.implicitHeight : confirmationMenu.implicitHeight) + 16
        color: "transparent"
        visible: false
        grabFocus: true

        onVisibleChanged: {
            if (!visible)
                root.pendingAction = ""
        }

        Rectangle {
            anchors.fill: parent
            radius: 0
            topLeftRadius: 0
            topRightRadius: root.popupRadius
            bottomLeftRadius: 0
            bottomRightRadius: 0
            color: root.popupColor

            Column {
                id: actionMenu

                x: 8
                y: 8
                spacing: 4
                visible: root.pendingAction === ""

                ActionRow {
                    label: "Lock"
                    onActivated: root.runAction("lock")
                }
                ActionRow {
                    label: "Suspend"
                    onActivated: root.runAction("suspend")
                }
                ActionRow {
                    label: "Logout"
                    onActivated: root.pendingAction = "logout"
                }
                ActionRow {
                    label: "Reboot"
                    onActivated: root.pendingAction = "reboot"
                }
                ActionRow {
                    label: "Power off"
                    onActivated: root.pendingAction = "poweroff"
                }
            }

            Column {
                id: confirmationMenu

                x: 8
                y: 8
                spacing: 4
                visible: root.pendingAction !== ""

                Text {
                    width: root.popupWidth - 16
                    height: 36
                    text: root.pendingAction === "logout" ? "Logout?"
                        : root.pendingAction === "reboot" ? "Reboot?" : "Power off?"
                    color: root.textColor
                    font.pixelSize: 14
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                ActionRow {
                    label: "Confirm"
                    onActivated: root.runAction(root.pendingAction)
                }
                ActionRow {
                    label: "Cancel"
                    onActivated: root.pendingAction = ""
                }
            }
        }
    }
}
