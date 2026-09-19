pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root

    required property var theme
    required property var metrics
    required property PowerActions powerActions
    required property var targetScreen
    required property var focusCoordinator
    readonly property int buttonSize: root.metrics.dockPowerButtonTarget
    property int bottomMargin: root.metrics.dockOuterInset
    property color iconColor: root.theme.accent

    property string pendingAction: ""
    readonly property int confirmationButtonHeight: root.metrics.scaled(34)
    readonly property int confirmationButtonGap: root.metrics.scaled(10)

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight
    anchors.bottomMargin: bottomMargin

    function requestAction(action: string): void {
        if (powerActions.requiresConfirmation(action)) {
            pendingAction = action
            return
        }

        popup.requestedVisible = false
        powerActions.execute(action)
    }

    function actionLabel(action: string): string {
        const candidate = powerActions.action(action)
        return candidate ? candidate.label : ""
    }

    function confirmPendingAction(): void {
        const action = pendingAction
        popup.requestedVisible = false
        powerActions.execute(action)
    }

    function clearTransientMenuFocus(): void {
        popup.contentItem.forceActiveFocus()
    }

    onPendingActionChanged: root.clearTransientMenuFocus()

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
            onClicked: root.focusCoordinator.toggleDockWindow(popup)

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

    component CompactActionRow: PanelActionRow {
        width: parent ? parent.width : 0
        implicitHeight: root.metrics.compactActionRowHeight
        metrics: root.metrics
        theme: root.theme
        primaryFontSize: root.metrics.informationLabelFontSize
        primaryFontWeight: root.metrics.informationLabelFontWeight
        activeFocusOnTab: false
    }

    component ConfirmationButton: Rectangle {
        id: row

        required property string label
        property bool danger: false
        property real buttonWidth: 0
        signal activated()

        width: buttonWidth
        height: root.confirmationButtonHeight
        radius: root.metrics.rowRadius
        color: row.danger ? root.theme.danger
            : rowMouse.pressed ? root.theme.pressedFill
                : rowMouse.containsMouse
                    ? root.theme.hoverFill : root.theme.normalFill

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            visible: row.danger
            color: rowMouse.pressed ? root.theme.pressedFill
                : rowMouse.containsMouse
                    ? root.theme.hoverFill : "transparent"
        }

        Text {
            anchors {
                left: parent.left
                right: parent.right
                leftMargin: root.metrics.rowSidePadding
                rightMargin: root.metrics.rowSidePadding
                verticalCenter: parent.verticalCenter
            }
            text: row.label
            color: row.danger ? root.theme.onDanger : root.theme.text
            font.pixelSize: root.metrics.informationLabelFontSize
            font.weight: root.metrics.informationLabelFontWeight
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }

        MouseArea {
            id: rowMouse

            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: row.activated()
        }
    }

    DockPopup {
        id: popup

        metrics: root.metrics
        popupAnchorItem: root
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        panelWidth: root.metrics.compactActionSurfaceWidth
        implicitHeight: (root.pendingAction === ""
            ? actionMenu.implicitHeight : confirmationMenu.implicitHeight)
            + root.metrics.compactMenuPadding * 2

        onVisibleChanged: {
            if (!visible) {
                root.pendingAction = ""
                root.clearTransientMenuFocus()
            }
        }

        PanelSurface {
            anchors.fill: parent
            metrics: root.metrics
            theme: root.theme
            padding: root.metrics.compactMenuPadding

            Column {
                id: actionMenu

                width: parent.width
                spacing: root.metrics.rowSpacing
                visible: root.pendingAction === ""

                CompactActionRow {
                    primaryText: root.actionLabel("lock")
                    onActivated: root.requestAction("lock")
                }
                CompactActionRow {
                    primaryText: root.actionLabel("suspend")
                    onActivated: root.requestAction("suspend")
                }
                CompactActionRow {
                    primaryText: root.actionLabel("logout")
                    onActivated: root.requestAction("logout")
                }
                CompactActionRow {
                    primaryText: root.actionLabel("reboot")
                    onActivated: root.requestAction("reboot")
                }
                CompactActionRow {
                    primaryText: root.actionLabel("poweroff")
                    onActivated: root.requestAction("poweroff")
                }
            }

            Column {
                id: confirmationMenu

                width: parent.width
                spacing: root.confirmationButtonGap
                visible: root.pendingAction !== ""

                Text {
                    width: parent.width
                    height: root.metrics.compactActionRowHeight
                    text: root.actionLabel(root.pendingAction) + "?"
                    color: root.theme.text
                    font.pixelSize: root.metrics.informationLabelFontSize
                    font.weight: root.metrics.informationLabelFontWeight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.NoWrap
                }

                Row {
                    width: parent.width
                    height: root.confirmationButtonHeight
                    spacing: root.confirmationButtonGap

                    ConfirmationButton {
                        label: "Cancel"
                        buttonWidth: (parent.width - parent.spacing) / 2
                        onActivated: root.pendingAction = ""
                    }

                    ConfirmationButton {
                        label: "Confirm"
                        danger: true
                        buttonWidth: (parent.width - parent.spacing) / 2
                        onActivated: root.confirmPendingAction()
                    }
                }
            }
        }
    }
}
