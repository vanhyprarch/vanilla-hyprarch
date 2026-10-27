pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.impl as ControlsImpl
import Quickshell
import Quickshell.Services.SystemTray as TrayService

Item {
    id: root

    required property var theme
    required property var metrics
    readonly property int contentWidth: root.metrics.dockContentWidth
    readonly property int buttonSize: root.metrics.dockTrayTarget
    readonly property int iconSize: root.metrics.dockTrayIconSize
    readonly property int spacing: root.metrics.dockTrayGap
    readonly property int clockGap: root.metrics.dockGroupGap
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
                // Pixmap/composite handles expose no symbolic metadata.
                readonly property bool symbolic: /^image:\/\/icon\/[^?]*-symbolic(?:\.(?:svg|png|xpm))?(?:\?|$)/.test(
                    modelData.icon)

                x: (root.width - width) / 2
                width: root.buttonSize
                height: root.buttonSize

                function openMenu() {
                    if (modelData && modelData.hasMenu && modelData.menu)
                        menuAnchor.open()
                }

                // Plain Image keeps aspect-fit: IconImage can override it with
                // Pad and crop rounded pixmaps at fractional device scales.
                Image {
                    id: trayIconSource

                    anchors.centerIn: parent
                    width: root.iconSize
                    height: root.iconSize
                    source: trayButton.symbolic ? "" : trayButton.modelData.icon
                    visible: !trayButton.symbolic
                    sourceSize: Qt.size(root.iconSize, root.iconSize)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }

                ControlsImpl.IconImage {
                    anchors.fill: trayIconSource
                    source: trayButton.symbolic ? trayButton.modelData.icon : ""
                    visible: trayButton.symbolic
                    color: root.iconColor
                    sourceSize: Qt.size(root.iconSize, root.iconSize)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
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
