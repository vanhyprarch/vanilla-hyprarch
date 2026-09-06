pragma ComponentBehavior: Bound

import QtQuick
import Quickshell.Hyprland

Item {
    id: root

    property int contentWidth: 40
    property int buttonHeight: 28
    property int spacing: 1
    property int logoGap: 13
    property int fontSize: 13
    property color textColor: "#5A3525"

    implicitWidth: contentWidth
    implicitHeight: content.implicitHeight
    width: implicitWidth
    height: implicitHeight

    function focusWorkspace(workspaceNumber: int): void {
        if (Hyprland.usingLua)
            Hyprland.dispatch('hl.dsp.focus({ workspace = "' + workspaceNumber + '" })')
        else
            Hyprland.dispatch("workspace " + workspaceNumber)
    }

    Column {
        id: content

        width: root.width
        spacing: root.spacing

        Repeater {
            model: 5

            Item {
                id: workspaceButton

                required property int index
                readonly property int workspaceNumber: index + 1
                readonly property bool isActive: Hyprland.focusedWorkspace !== null
                    && Hyprland.focusedWorkspace.id === workspaceNumber

                width: root.width
                height: root.buttonHeight

                Text {
                    anchors.fill: parent
                    text: workspaceButton.workspaceNumber
                    color: root.textColor
                    font.pixelSize: root.fontSize
                    font.weight: workspaceButton.isActive ? Font.Bold : Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.NoWrap
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.focusWorkspace(workspaceButton.workspaceNumber)
                }
            }
        }
    }
}
