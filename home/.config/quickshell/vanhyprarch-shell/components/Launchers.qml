pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

Item {
    id: root

    property int contentWidth: 48
    property int buttonSize: 40
    property int iconSize: 28
    property int spacing: 4
    property color textColor: "#5A3525"

    readonly property var resolvedLaunchers: {
        // Re-resolve saved IDs when the installed application index changes.
        DesktopEntries.applications.values
        return store.launchers.map(launcher => ({
            config: launcher,
            desktopEntry: DesktopEntries.byId(launcher.desktopId)
        })).filter(launcher => launcher.desktopEntry !== null)
    }

    implicitWidth: contentWidth
    implicitHeight: content.implicitHeight
    width: implicitWidth
    height: implicitHeight

    LauncherStore {
        id: store
    }

    Column {
        id: content

        width: root.width
        spacing: root.spacing

        Repeater {
            model: root.resolvedLaunchers

            LauncherButton {
                required property var modelData

                anchors.horizontalCenter: parent.horizontalCenter
                desktopEntry: modelData.desktopEntry
                buttonSize: root.buttonSize
                iconSize: root.iconSize
            }
        }

        Item {
            id: addButton

            anchors.horizontalCenter: parent.horizontalCenter
            width: root.buttonSize
            height: root.buttonSize

            Text {
                anchors.centerIn: parent
                text: "+"
                color: root.textColor
                font.pixelSize: 24
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: appPicker.visible = !appPicker.visible
            }
        }
    }

    AppPicker {
        id: appPicker
        anchor.item: addButton
        launcherStore: store
    }
}
