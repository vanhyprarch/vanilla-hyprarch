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
    readonly property int contentPadding: root.metrics.overlayPadding
    readonly property int actionButtonWidth: Math.ceil(Math.max(
        revertLabel.implicitWidth, keepLabel.implicitWidth))
        + root.metrics.rowSidePadding * 2
    readonly property string titleText: "Keep these display settings?"
    readonly property string descriptionText: root.controller.confirmationDescription()
    readonly property string countdownText: "Reverting in " + Math.max(0,
        Math.ceil(root.controller.presentationRemainingSeconds)) + " seconds"
    readonly property real naturalContentWidth: Math.max(
        titleMeasure.implicitWidth, descriptionMeasure.implicitWidth,
        countdownMeasure.implicitWidth, actionRow.width)
    readonly property int maximumPanelWidth: Math.max(0, Math.min(
        root.metrics.standardPanelWidth, screenWidth - dockWidth - 48))
    readonly property int minimumPanelWidth: Math.min(
        root.metrics.compactActionSurfaceWidth, maximumPanelWidth)
    readonly property int idealPanelWidth: Math.ceil(naturalContentWidth)
        + contentPadding * 2

    persistentLeftInset: dockWidth
    implicitWidth: Math.max(minimumPanelWidth,
        Math.min(maximumPanelWidth, idealPanelWidth))
    implicitHeight: contentColumn.implicitHeight + contentPadding * 2
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

    Text {
        id: titleMeasure
        visible: false
        text: root.titleText
        font.pixelSize: root.metrics.panelTitleFontSize
        font.weight: root.metrics.panelTitleFontWeight
    }

    Text {
        id: descriptionMeasure
        visible: false
        text: root.descriptionText
        font.pixelSize: root.metrics.bodyFontSize
    }

    Text {
        id: countdownMeasure
        visible: false
        text: root.countdownText
        font.pixelSize: root.metrics.informationLabelFontSize
        font.weight: Font.DemiBold
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
                id: contentColumn
                objectName: "confirmationContent"

                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    topMargin: root.contentPadding
                    leftMargin: root.contentPadding
                    rightMargin: root.contentPadding
                }
                spacing: 16

                Text {
                    width: parent.width
                    text: root.titleText
                    color: root.theme.text
                    font.pixelSize: root.metrics.panelTitleFontSize
                    font.weight: root.metrics.panelTitleFontWeight
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    objectName: "confirmationDescription"
                    width: parent.width
                    text: root.descriptionText
                    color: root.theme.textMuted
                    font.pixelSize: root.metrics.bodyFontSize
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                Text {
                    width: parent.width
                    text: root.countdownText
                    color: root.theme.text
                    font.pixelSize: root.metrics.informationLabelFontSize
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                }

                Row {
                    id: actionRow
                    objectName: "confirmationActions"

                    anchors.horizontalCenter: parent.horizontalCenter
                    width: root.actionButtonWidth * 2 + spacing
                    height: root.metrics.compactControlHeight
                    spacing: root.metrics.rowSpacing

                    Rectangle {
                        id: revertButton
                        objectName: "confirmationRevertButton"

                        width: root.actionButtonWidth
                        height: parent.height
                        radius: root.metrics.rowRadius
                        color: revertMouse.pressed ? root.theme.pressedFill
                            : revertMouse.containsMouse ? root.theme.hoverFill
                                : root.theme.normalFill
                        opacity: root.controller.operationBusy
                            ? root.metrics.disabledInteractiveOpacity : 1

                        Text {
                            id: revertLabel
                            objectName: "confirmationRevertLabel"

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
                        id: keepButton
                        objectName: "confirmationKeepButton"

                        width: root.actionButtonWidth
                        height: parent.height
                        radius: root.metrics.rowRadius
                        color: keepMouse.pressed ? root.theme.pressedFill
                            : keepMouse.containsMouse ? root.theme.hoverFill
                                : root.theme.activeFill
                        opacity: root.controller.operationBusy
                            ? root.metrics.disabledInteractiveOpacity : 1

                        Text {
                            id: keepLabel
                            objectName: "confirmationKeepLabel"

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
