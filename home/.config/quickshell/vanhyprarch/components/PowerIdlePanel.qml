pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property var controller
    required property var theme
    required property Item popupAnchorItem
    required property int popupRadius
    property int panelWidth: 360
    property int panelPadding: 12
    property int popupHorizontalGap: -16
    property int popupVerticalOffset: -2
    property color backgroundColor: root.theme.background
    property color textColor: root.theme.text
    property color secondaryColor: root.theme.surface
    property color hoverColor: root.theme.hover
    property color accentColor: root.theme.accent

    readonly property var screensaverPresets: [
        { value: "never", label: "Never" },
        { value: "120", label: "2 min" },
        { value: "300", label: "5 min" },
        { value: "600", label: "10 min" },
        { value: "1200", label: "20 min" }
    ]
    readonly property var displayPresets: [
        { value: "never", label: "Never" },
        { value: "300", label: "5 min" },
        { value: "600", label: "10 min" },
        { value: "1200", label: "20 min" },
        { value: "1800", label: "30 min" }
    ]
    readonly property var suspendPresets: [
        { value: "never", label: "Never" },
        { value: "600", label: "10 min" },
        { value: "1200", label: "20 min" },
        { value: "1800", label: "30 min" },
        { value: "3600", label: "1 h" }
    ]
    readonly property var lockChoices: [
        { value: "none", label: "None" },
        { value: "screensaver", label: "Screen saver" },
        { value: "display", label: "Display off" },
        { value: "suspend", label: "Suspend" }
    ]

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: Math.max(0,
            ((root.popupAnchorItem.parent ? root.popupAnchorItem.parent.width
                : root.popupAnchorItem.width) - root.popupAnchorItem.width) / 2)
            + root.popupHorizontalGap
        margins.bottom: root.popupVerticalOffset
    }

    implicitWidth: panelWidth
    implicitHeight: content.implicitHeight + panelPadding * 2
    color: "transparent"
    visible: false
    grabFocus: true

    function lockChoiceEnabled(value: string): bool {
        return root.controller.canSetLock(value)
    }

    component PresetButton: Rectangle {
        id: presetButton

        required property string stage
        required property string value
        required property string label
        required property real buttonWidth
        readonly property bool selected:
            root.controller.stageValue(stage) === value
        readonly property bool available:
            root.controller.canSetStage(stage, value)

        width: buttonWidth
        height: 26
        radius: root.popupRadius / 2
        color: selected ? root.accentColor
            : presetMouse.containsMouse && available
                ? root.hoverColor : root.secondaryColor
        opacity: available || selected ? 1.0 : 0.35

        Text {
            id: presetLabel

            anchors.fill: parent
            text: presetButton.label
            color: presetButton.selected ? root.backgroundColor : root.textColor
            font.pixelSize: 12
            font.weight: presetButton.selected ? Font.Medium : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        MouseArea {
            id: presetMouse

            anchors.fill: parent
            enabled: presetButton.available
                && !presetButton.selected
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.controller.requestStage(
                presetButton.stage, presetButton.value)
        }
    }

    component StageSection: Column {
        id: stageSection

        required property string stage
        required property string title
        required property var presets

        width: content.width
        spacing: 5
        opacity: !root.controller.ready ? 0.45
            : root.controller.visualCaffeine ? 0.72 : 1.0

        Item {
            width: parent.width
            height: 18

            Text {
                anchors {
                    left: parent.left
                    verticalCenter: parent.verticalCenter
                }
                text: stageSection.title
                color: root.textColor
                font.pixelSize: 13
                font.weight: Font.Medium
                wrapMode: Text.NoWrap
            }

        }

        Row {
            id: presetRow

            width: parent.width
            height: childrenRect.height
            spacing: 4

            Repeater {
                model: stageSection.presets

                PresetButton {
                    required property var modelData

                    stage: stageSection.stage
                    value: String(modelData.value)
                    label: String(modelData.label)
                    buttonWidth: (presetRow.width - presetRow.spacing * 4) / 5
                }
            }
        }
    }

    component LockButton: Rectangle {
        id: lockButton

        required property string value
        required property string label
        readonly property bool selected:
            root.controller.lockPoint === value
        readonly property bool available: root.lockChoiceEnabled(value)

        width: Math.max(48, lockLabel.implicitWidth + 16)
        height: 26
        radius: root.popupRadius / 2
        color: selected ? root.accentColor
            : lockMouse.containsMouse && available
                ? root.hoverColor : root.secondaryColor
        opacity: available || selected ? 1.0 : 0.35

        Text {
            id: lockLabel

            anchors.fill: parent
            text: lockButton.label
            color: lockButton.selected ? root.backgroundColor : root.textColor
            font.pixelSize: 12
            font.weight: lockButton.selected ? Font.Medium : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        MouseArea {
            id: lockMouse

            anchors.fill: parent
            enabled: lockButton.available && !lockButton.selected
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.controller.requestLock(lockButton.value)
        }
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: 0
        topLeftRadius: 0
        topRightRadius: root.popupRadius
        bottomLeftRadius: 0
        bottomRightRadius: root.popupRadius

        Column {
            id: content

            x: root.panelPadding
            y: root.panelPadding
            width: root.panelWidth - root.panelPadding * 2
            spacing: 8

            Text {
                width: parent.width
                text: "Power & Idle"
                color: root.textColor
                font.pixelSize: 16
                font.bold: true
                wrapMode: Text.NoWrap
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
            }

            Item {
                width: parent.width
                height: 42

                Column {
                    anchors {
                        left: parent.left
                        right: caffeineToggle.left
                        rightMargin: 12
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: 2

                    Text {
                        width: parent.width
                        text: "Caffeine"
                        color: root.textColor
                        font.pixelSize: 13
                        font.weight: Font.Medium
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        width: parent.width
                        text: "Keep computer awake"
                        color: root.textColor
                        opacity: 0.72
                        font.pixelSize: 12
                        wrapMode: Text.NoWrap
                    }
                }

                Rectangle {
                    id: caffeineToggle

                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    width: 40
                    height: 22
                    radius: height / 2
                    color: root.controller.visualCaffeine
                        ? root.accentColor : root.secondaryColor
                    opacity: root.controller.ready ? 1.0 : 0.45

                    Rectangle {
                        width: 16
                        height: 16
                        radius: width / 2
                        y: 3
                        x: root.controller.visualCaffeine
                            ? caffeineToggle.width - width - 3 : 3
                        color: root.controller.visualCaffeine
                            ? root.backgroundColor : root.textColor

                        Behavior on x {
                            NumberAnimation { duration: 100 }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: root.controller.ready && !root.controller.busy
                        hoverEnabled: true
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.controller.requestCaffeine(
                            !root.controller.caffeine)
                    }
                }
            }

            StageSection {
                stage: "screensaver"
                title: "Screen saver"
                presets: root.screensaverPresets
            }

            StageSection {
                stage: "display"
                title: "Turn off display"
                presets: root.displayPresets
            }

            StageSection {
                stage: "suspend"
                title: "Suspend"
                presets: root.suspendPresets
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
            }

            Text {
                width: parent.width
                text: "Automatic lock"
                color: root.textColor
                font.pixelSize: 13
                font.weight: Font.Medium
                wrapMode: Text.NoWrap
            }

            Flow {
                width: parent.width
                height: childrenRect.height
                spacing: 4

                Repeater {
                    model: root.lockChoices

                    LockButton {
                        required property var modelData

                        value: String(modelData.value)
                        label: String(modelData.label)
                    }
                }
            }

            Text {
                width: parent.width
                visible: !root.controller.ready
                text: "Loading Power & Idle state…"
                color: root.textColor
                opacity: 0.72
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                visible: root.controller.errorMessage !== ""
                text: root.controller.errorMessage
                color: root.accentColor
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

        }
    }
}
