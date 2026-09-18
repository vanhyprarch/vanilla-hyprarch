pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

DockPopup {
    id: root

    required property var controller
    required property var theme

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
        { value: "screensaver", label: "Screensaver" },
        { value: "display", label: "Display Off" },
        { value: "suspend", label: "Suspend" }
    ]
    readonly property var lockChoicesWithoutScreensaver: [
        { value: "none", label: "None" },
        { value: "display", label: "Display Off" },
        { value: "suspend", label: "Suspend" }
    ]
    readonly property var effectChoices: [
        { value: "colormix", label: "Color Mix" },
        { value: "matrix", label: "Matrix" },
        { value: "doom", label: "Doom" },
        { value: "gameoflife", label: "Game of Life" }
    ]
    readonly property int minimumLockChoiceWidth: root.metrics.scaled(48)
    readonly property var effectiveLockChoices: root.controller.screensaverAvailable
        ? root.lockChoices : root.lockChoicesWithoutScreensaver
    readonly property bool screensaverControlsVisible:
        effectSection.visible && screensaverSection.visible
    readonly property int automaticLockChoiceCount: lockChoiceRepeater.count
    readonly property var orderedSections: [caffeineSection, effectSection,
        screensaverSection, displaySection, suspendSection, automaticLockSection]
    readonly property var visibleSectionLabels: root.orderedSections
        .filter(section => section.visible).map(section => section.sectionLabel)
    readonly property var visibleLockChoiceLabels:
        root.effectiveLockChoices.map(choice => choice.label)
    readonly property real optionalLayoutContribution:
        (effectSection.visible ? effectSection.implicitHeight + content.spacing : 0)
        + (screensaverSection.visible
            ? screensaverSection.implicitHeight + content.spacing : 0)

    implicitHeight: content.implicitHeight + root.metrics.panelPadding * 2

    function lockChoiceEnabled(value: string): bool {
        return root.controller.canSetLock(value)
    }

    component ChoiceButton: Rectangle {
        id: choiceButton

        required property string label
        required property bool selected
        required property bool available
        property real controlWidth: Math.max(root.minimumLockChoiceWidth,
            choiceLabel.implicitWidth + root.metrics.rowSidePadding * 2)
        readonly property bool actionable: available && !selected
        signal activated()

        width: controlWidth
        height: root.metrics.compactControlHeight
        radius: root.metrics.rowRadius
        color: choiceMouse.pressed && actionable
            ? root.theme.pressedFill
            : selected ? root.theme.activeFill
                : choiceMouse.containsMouse && actionable
                    ? root.theme.hoverFill : root.theme.normalFill
        opacity: available || selected
            ? 1.0 : root.metrics.disabledInteractiveOpacity

        Text {
            id: choiceLabel

            anchors.fill: parent
            text: choiceButton.label
            color: root.theme.text
            font.pixelSize: root.metrics.bodyFontSize
            font.weight: choiceButton.selected
                ? root.metrics.overlayFontWeight : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        MouseArea {
            id: choiceMouse

            anchors.fill: parent
            enabled: choiceButton.actionable
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: choiceButton.activated()
        }
    }

    component StageSection: Column {
        id: stageSection

        required property string stage
        required property string title
        required property var presets
        readonly property string sectionLabel: title

        width: content.width
        spacing: root.metrics.contentGap
        opacity: !root.controller.ready
            ? root.metrics.disabledInteractiveOpacity
            : root.controller.visualCaffeine
                ? root.metrics.informationalMutedOpacity : 1.0

        Item {
            width: parent.width
            height: root.metrics.compactControlHeight

            Text {
                anchors {
                    left: parent.left
                    verticalCenter: parent.verticalCenter
                }
                text: stageSection.title
                color: root.theme.text
                font.pixelSize: root.metrics.informationLabelFontSize
                font.weight: root.metrics.informationLabelFontWeight
                wrapMode: Text.NoWrap
            }
        }

        Row {
            id: presetRow

            width: parent.width
            height: childrenRect.height
            spacing: root.metrics.rowSpacing

            Repeater {
                model: stageSection.presets

                ChoiceButton {
                    required property var modelData

                    label: String(modelData.label)
                    selected: root.controller.stageValue(stageSection.stage)
                        === String(modelData.value)
                    available: root.controller.canSetStage(stageSection.stage,
                        String(modelData.value))
                    controlWidth: (presetRow.width
                        - presetRow.spacing * (stageSection.presets.length - 1))
                        / stageSection.presets.length
                    onActivated: root.controller.requestStage(stageSection.stage,
                        String(modelData.value))
                }
            }
        }
    }

    PanelSurface {
        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme

        Column {
            id: content

            width: parent.width
            spacing: root.metrics.sectionGap

            Text {
                width: parent.width
                text: "Power & Idle"
                color: root.theme.text
                font.pixelSize: root.metrics.panelTitleFontSize
                font.weight: root.metrics.panelTitleFontWeight
                wrapMode: Text.NoWrap
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
            }

            Item {
                id: caffeineSection
                readonly property string sectionLabel: "Caffeine"
                width: parent.width
                height: root.metrics.twoLineRowHeight

                Column {
                    anchors {
                        left: parent.left
                        right: caffeineControl.left
                        rightMargin: root.metrics.contentGap
                        verticalCenter: parent.verticalCenter
                    }
                    spacing: root.metrics.rowSpacing

                    Text {
                        width: parent.width
                        text: "Caffeine"
                        color: root.theme.text
                        font.pixelSize: root.metrics.informationLabelFontSize
                        font.weight: root.metrics.informationLabelFontWeight
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        width: parent.width
                        text: "Keep computer awake"
                        color: root.theme.textMuted
                        font.pixelSize: root.metrics.detailFontSize
                        wrapMode: Text.NoWrap
                    }
                }

                Item {
                    id: caffeineControl

                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    width: root.metrics.toggleTrackWidth
                    height: root.metrics.twoLineRowHeight

                    ToggleSwitch {
                        anchors.centerIn: parent
                        metrics: root.metrics
                        theme: root.theme
                        checked: root.controller.visualCaffeine
                        interactive: false
                        enabled: root.controller.ready && !root.controller.busy
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: root.controller.ready && !root.controller.busy
                        hoverEnabled: true
                        cursorShape: enabled
                            ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.controller.requestCaffeine(
                            !root.controller.caffeine)
                    }
                }
            }

            Column {
                id: effectSection
                readonly property string sectionLabel: "Screen Saver Effect"
                width: parent.width
                visible: root.controller.screensaverAvailable
                spacing: root.metrics.contentGap
                opacity: root.controller.ready
                    ? 1.0 : root.metrics.disabledInteractiveOpacity

                Text {
                    width: parent.width
                    text: "Screen Saver Effect"
                    color: root.theme.text
                    font.pixelSize: root.metrics.informationLabelFontSize
                    font.weight: root.metrics.informationLabelFontWeight
                    wrapMode: Text.NoWrap
                }

                Row {
                    id: effectRow

                    width: parent.width
                    height: childrenRect.height
                    spacing: root.metrics.rowSpacing

                    Repeater {
                        model: root.effectChoices

                        ChoiceButton {
                            required property var modelData

                            label: String(modelData.label)
                            selected: root.controller.effect
                                === String(modelData.value)
                            available: root.controller.ready
                                && !root.controller.busy
                            controlWidth: (effectRow.width
                                - effectRow.spacing
                                    * (root.effectChoices.length - 1))
                                / root.effectChoices.length
                            onActivated: root.controller.requestEffect(
                                String(modelData.value))
                        }
                    }
                }
            }

            StageSection {
                id: screensaverSection
                visible: root.controller.screensaverAvailable
                stage: "screensaver"
                title: "Screensaver"
                presets: root.screensaverPresets
            }

            StageSection {
                id: displaySection
                stage: "display"
                title: "Turn Off Display"
                presets: root.displayPresets
            }

            StageSection {
                id: suspendSection
                stage: "suspend"
                title: "Suspend"
                presets: root.suspendPresets
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
            }

            Text {
                id: automaticLockSection
                readonly property string sectionLabel: "Automatic Lock"
                width: parent.width
                text: "Automatic Lock"
                color: root.theme.text
                font.pixelSize: root.metrics.informationLabelFontSize
                font.weight: root.metrics.informationLabelFontWeight
                wrapMode: Text.NoWrap
            }

            Flow {
                width: parent.width
                height: childrenRect.height
                spacing: root.metrics.rowSpacing

                Repeater {
                    id: lockChoiceRepeater
                    model: root.effectiveLockChoices

                    ChoiceButton {
                        required property var modelData

                        label: String(modelData.label)
                        selected: root.controller.lockPoint
                            === String(modelData.value)
                        available: root.lockChoiceEnabled(String(modelData.value))
                        onActivated: root.controller.requestLock(
                            String(modelData.value))
                    }
                }
            }

            Text {
                width: parent.width
                visible: !root.controller.ready
                text: "Loading Power & Idle state…"
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                wrapMode: Text.WordWrap
            }

            Text {
                width: parent.width
                visible: root.controller.errorMessage !== ""
                text: root.controller.errorMessage
                color: root.theme.danger
                font.pixelSize: root.metrics.detailFontSize
                wrapMode: Text.WordWrap
            }
        }
    }
}
