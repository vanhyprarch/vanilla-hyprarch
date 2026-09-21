import QtQuick
import Quickshell.Hyprland

CenteredOverlay {
    id: root

    required property MonitorController controller
    required property var metrics
    required property var theme
    required property string screenName
    required property int dockWidth

    readonly property var mappedMonitor: Hyprland.monitorFor(root.targetScreen)
    readonly property string mappedConnector: mappedMonitor
        ? String(mappedMonitor.name || "") : ""
    readonly property bool activeForScreen: controller.confirmationScreenName === screenName

    persistentLeftInset: dockWidth
    implicitWidth: Math.max(360, Math.min(520, screenWidth - dockWidth - 48))
    implicitHeight: 248
    color: "transparent"
    visible: controller.confirmationActive && activeForScreen

    Component.onCompleted: {
        controller.registerSurface(screenName, mappedConnector)
        syncFocus()
    }
    Component.onDestruction: controller.unregisterSurface(screenName)
    onMappedConnectorChanged: controller.registerSurface(screenName, mappedConnector)
    onDismissed: controller.requestRevert()
    onVisibleChanged: syncFocus()

    function syncFocus(): void {
        if (visible)
            Qt.callLater(function() { keyboardScope.forceActiveFocus() })
    }

    Rectangle {
        anchors.fill: parent
        radius: root.metrics.panelRadius
        color: root.theme.background
        border.width: root.metrics.panelOutlineThickness
        border.color: root.theme.panelOutline

        FocusScope {
            id: keyboardScope
            anchors.fill: parent
            focus: true
            Keys.priority: Keys.BeforeItem
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                    root.controller.requestRevert()
                    event.accepted = true
                } else if (event.key === Qt.Key_Return
                        || event.key === Qt.Key_Enter) {
                    root.controller.requestConfirm()
                    event.accepted = true
                }
            }

            Column {
                anchors {
                    fill: parent
                    margins: 24
                }
                spacing: 16

                Text {
                    width: parent.width
                    text: "Keep these display settings?"
                    color: root.theme.text
                    font.pixelSize: root.metrics.panelTitleFontSize
                    font.weight: root.metrics.panelTitleFontWeight
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    width: parent.width
                    text: root.controller.confirmationDescription()
                    color: root.theme.textMuted
                    font.pixelSize: root.metrics.bodyFontSize
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    width: parent.width
                    text: "Reverting in " + Math.max(0,
                        Math.ceil(root.controller.presentationRemainingSeconds))
                        + " seconds"
                    color: root.theme.text
                    font.pixelSize: root.metrics.informationLabelFontSize
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                }

                Row {
                    width: parent.width
                    height: root.metrics.compactControlHeight
                    spacing: root.metrics.rowSpacing

                    Rectangle {
                        width: (parent.width - parent.spacing) / 2
                        height: parent.height
                        radius: root.metrics.rowRadius
                        color: revertMouse.pressed ? root.theme.pressedFill
                            : revertMouse.containsMouse ? root.theme.hoverFill
                                : root.theme.normalFill
                        opacity: root.controller.operationBusy
                            ? root.metrics.disabledInteractiveOpacity : 1

                        Text {
                            anchors.centerIn: parent
                            text: "Revert · Esc"
                            color: root.theme.text
                            font.pixelSize: root.metrics.bodyFontSize
                        }

                        MouseArea {
                            id: revertMouse
                            anchors.fill: parent
                            enabled: !root.controller.operationBusy
                            hoverEnabled: true
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.controller.requestRevert()
                        }
                    }

                    Rectangle {
                        width: (parent.width - parent.spacing) / 2
                        height: parent.height
                        radius: root.metrics.rowRadius
                        color: keepMouse.pressed ? root.theme.pressedFill
                            : keepMouse.containsMouse ? root.theme.hoverFill
                                : root.theme.activeFill
                        opacity: root.controller.operationBusy
                            ? root.metrics.disabledInteractiveOpacity : 1

                        Text {
                            anchors.centerIn: parent
                            text: "Keep · Enter"
                            color: root.theme.text
                            font.pixelSize: root.metrics.bodyFontSize
                            font.weight: Font.DemiBold
                        }

                        MouseArea {
                            id: keepMouse
                            anchors.fill: parent
                            enabled: !root.controller.operationBusy
                            hoverEnabled: true
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.controller.requestConfirm()
                        }
                    }
                }
            }
        }
    }
}
