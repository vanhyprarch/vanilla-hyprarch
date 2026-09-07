pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Services.SystemTray as TrayService

Item {
    id: root

    required property var theme
    property int contentWidth: 48
    property int buttonSize: 32
    property int iconSize: 22
    property int spacing: 2
    property int clockGap: 8
    property color iconColor: root.theme.accent

    implicitWidth: contentWidth
    implicitHeight: trayColumn.implicitHeight
    width: implicitWidth
    height: implicitHeight

    Column {
        id: trayColumn

        width: root.width
        spacing: root.spacing

        Repeater {
            model: TrayService.SystemTray.items

            Item {
                id: trayButton

                required property var modelData

                x: (root.width - width) / 2
                width: root.buttonSize
                height: root.buttonSize

                function openMenu() {
                    if (modelData && modelData.hasMenu && modelData.menu)
                        menuAnchor.open()
                }

                Image {
                    id: trayIconSource

                    anchors.centerIn: parent
                    width: root.iconSize
                    height: root.iconSize
                    source: trayButton.modelData.icon
                    sourceSize: Qt.size(root.iconSize, root.iconSize)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                    visible: false
                }

                MultiEffect {
                    anchors.fill: trayIconSource
                    source: trayIconSource
                    colorization: 1.0
                    colorizationColor: root.iconColor
                }

                QsMenuAnchor {
                    id: menuAnchor

                    menu: trayButton.modelData.hasMenu ? trayButton.modelData.menu : null
                    anchor {
                        item: trayButton
                        edges: Edges.Right | Edges.Top
                        gravity: Edges.Right | Edges.Bottom
                        margins.right: -Math.max(0,
                            ((root.parent ? root.parent.width : root.width) - trayButton.width) / 2)
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor

                    onClicked: mouse => {
                        if (mouse.button === Qt.LeftButton) {
                            if (trayButton.modelData.onlyMenu && trayButton.modelData.hasMenu)
                                trayButton.openMenu()
                            else
                                trayButton.modelData.activate()
                        } else if (mouse.button === Qt.RightButton) {
                            if (trayButton.modelData.hasMenu)
                                trayButton.openMenu()
                        } else if (mouse.button === Qt.MiddleButton) {
                            trayButton.modelData.secondaryActivate()
                        }
                    }
                }
            }
        }
    }
}
