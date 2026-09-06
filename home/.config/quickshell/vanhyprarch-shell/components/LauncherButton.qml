import QtQuick
import Quickshell

Item {
    id: root

    required property DesktopEntry desktopEntry
    property int buttonSize: 40
    property int iconSize: 28
    property var workspaceIds: []

    signal contextMenuRequested()

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight
    clip: true

    onDesktopEntryChanged: iconImage.failed = false

    Column {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 6
        spacing: -1

        Repeater {
            model: root.workspaceIds

            Text {
                required property var modelData

                width: 6
                height: 8
                text: modelData
                color: "#8D4C2B"
                font.pixelSize: 8
                font.weight: Font.Normal
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }
        }
    }

    // Keep the icon separate from the full click target, leaving room at the left.
    Image {
        id: iconImage

        property bool failed: false
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath(!failed && root.desktopEntry && root.desktopEntry.icon
            ? root.desktopEntry.icon : "application-x-executable", "application-x-executable")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        onStatusChanged: {
            if (status === Image.Error && !failed)
                failed = true
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.desktopEntry !== null
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: mouse => {
            if (mouse.button === Qt.LeftButton)
                root.desktopEntry.execute()
            else if (mouse.button === Qt.RightButton)
                root.contextMenuRequested()
        }
    }
}
