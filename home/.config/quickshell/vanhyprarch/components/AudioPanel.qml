pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

DockPopup {
    id: root

    required property var theme
    property color textColor: root.theme.text

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
    readonly property var nodes: Pipewire.nodes ? Pipewire.nodes.values : []
    readonly property var outputDevices: root.nodes.filter(node => root.isAudioOutput(node))
    readonly property var inputDevices: root.nodes.filter(node => root.isAudioInput(node))
    readonly property var outputAudio: root.sink && root.sink.audio
        ? root.sink.audio : null
    readonly property var inputAudio: root.source && root.source.audio
        ? root.source.audio : null

    function nodeLabel(node, fallback: string): string {
        if (!node)
            return fallback

        const values = [node.nickname, node.description, node.name]
        for (const value of values) {
            const label = String(value || "").trim()
            if (label !== "")
                return label
        }
        return fallback
    }

    function hasNodeType(node, type): bool {
        const nodeType = Number(node.type)
        const typeMask = Number(type)
        return (nodeType & typeMask) === typeMask
    }

    function isAudioOutput(node): bool {
        return Boolean(node && node.isSink && !node.isStream
            && (root.hasNodeType(node, PwNodeType.AudioSink)
                || root.hasNodeType(node, PwNodeType.AudioDuplex)))
    }

    function isAudioInput(node): bool {
        return Boolean(node && !node.isStream
            && (root.hasNodeType(node, PwNodeType.AudioSource)
                || root.hasNodeType(node, PwNodeType.AudioDuplex)))
    }

    function isDefaultNode(node, defaultNode): bool {
        return Boolean(node && defaultNode && Number(node.id) === Number(defaultNode.id))
    }

    function selectOutput(node): void {
        if (node)
            Pipewire.preferredDefaultAudioSink = node
    }

    function selectInput(node): void {
        if (node)
            Pipewire.preferredDefaultAudioSource = node
    }

    PwObjectTracker {
        objects: [root.sink, root.source].filter(node => node !== null)
    }

    PwObjectTracker {
        objects: root.outputDevices.concat(root.inputDevices)
    }

    implicitHeight: content.implicitHeight + root.metrics.panelPadding * 2

    component VolumeSection: Column {
        id: volumeSection

        required property string title
        required property string deviceLabel
        required property var devices
        required property var defaultNode
        required property bool outputSection
        required property var audio
        readonly property bool available: audio !== null
        readonly property real volume: {
            if (!available)
                return 0
            const value = Number(audio.volume)
            return isFinite(value) ? Math.max(0, Math.min(1, value)) : 0
        }
        readonly property bool muted: available ? Boolean(audio.muted) : false

        function setVolume(value: real): void {
            if (!volumeSection.audio)
                return
            volumeSection.audio.volume = Math.max(0, Math.min(1, value))
        }

        function toggleMute(): void {
            if (!volumeSection.audio)
                return
            volumeSection.audio.muted = !volumeSection.audio.muted
        }

        width: content.width
        spacing: root.metrics.contentGap

        Item {
            width: parent.width
            height: root.metrics.compactRowHeight

            Text {
                anchors {
                    left: parent.left
                    verticalCenter: parent.verticalCenter
                }
                text: volumeSection.title
                color: root.textColor
                font.pixelSize: root.metrics.informationLabelFontSize
                font.weight: root.metrics.informationLabelFontWeight
            }

            Text {
                anchors {
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                }
                text: volumeSection.available
                    ? Math.round(volumeSection.volume * 100) + "%" : "—"
                color: root.theme.textMuted
                font.pixelSize: root.metrics.informationValueFontSize
                font.weight: root.metrics.informationValueFontWeight
            }
        }

        Column {
            width: parent.width
            spacing: root.metrics.rowSpacing

            Repeater {
                model: volumeSection.devices

                Rectangle {
                    id: deviceRow

                    required property var modelData
                    readonly property bool selected: root.isDefaultNode(
                        modelData, volumeSection.defaultNode)

                    width: volumeSection.width
                    height: root.metrics.compactRowHeight
                    radius: root.metrics.rowRadius
                    color: selected ? root.theme.activeFill
                        : (deviceMouse.containsMouse
                            ? root.theme.hoverFill : "transparent")

                    Text {
                        anchors {
                            fill: parent
                            leftMargin: root.metrics.rowSidePadding
                            rightMargin: root.metrics.rowSidePadding
                        }
                        text: root.nodeLabel(deviceRow.modelData, "Unknown device")
                        color: root.textColor
                        font.pixelSize: root.metrics.bodyFontSize
                        font.weight: deviceRow.selected
                            ? root.metrics.overlayFontWeight : Font.Normal
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.NoWrap
                    }

                    MouseArea {
                        id: deviceMouse

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (volumeSection.outputSection)
                                root.selectOutput(deviceRow.modelData)
                            else
                                root.selectInput(deviceRow.modelData)
                        }
                    }
                }
            }

            Text {
                visible: volumeSection.devices.length === 0
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: volumeSection.deviceLabel
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }
        }

        Item {
            id: volumeSlider

            readonly property real progress: volumeSection.volume

            width: parent.width
            height: root.metrics.sliderHitHeight
            opacity: volumeSection.available
                ? 1.0 : root.metrics.disabledInteractiveOpacity

            Rectangle {
                id: volumeTrack

                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                }
                height: root.metrics.sliderTrackThickness
                radius: root.metrics.sliderTrackRadius
                color: root.theme.normalFill
            }

            Rectangle {
                anchors {
                    left: volumeTrack.left
                    verticalCenter: volumeTrack.verticalCenter
                }
                width: volumeTrack.width * volumeSlider.progress
                height: volumeTrack.height
                radius: root.metrics.sliderTrackRadius
                color: root.theme.control
            }

            Rectangle {
                width: root.metrics.sliderThumbSize
                height: root.metrics.sliderThumbSize
                radius: root.metrics.sliderThumbRadius
                x: Math.max(0, Math.min(volumeTrack.width - width,
                    volumeTrack.width * volumeSlider.progress - width / 2))
                anchors.verticalCenter: volumeTrack.verticalCenter
                color: root.theme.control
            }

            MouseArea {
                anchors.fill: parent
                enabled: volumeSection.available
                hoverEnabled: true
                preventStealing: true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor

                function volumeFromX(position: real): real {
                    if (width <= 0)
                        return 0
                    return Math.max(0, Math.min(1, position / width))
                }

                onPressed: mouse => volumeSection.setVolume(volumeFromX(mouse.x))
                onPositionChanged: mouse => {
                    if (pressed)
                        volumeSection.setVolume(volumeFromX(mouse.x))
                }
            }
        }

        Item {
            width: parent.width
            height: root.metrics.compactRowHeight

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: root.metrics.contentGap
                opacity: volumeSection.available
                    ? 1.0 : root.metrics.disabledInteractiveOpacity

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: volumeSection.muted ? "Muted" : "Enabled"
                    color: root.theme.textMuted
                    font.pixelSize: root.metrics.detailFontSize
                }

                ToggleSwitch {
                    metrics: root.metrics
                    theme: root.theme
                    checked: volumeSection.muted
                    interactive: false
                    enabled: volumeSection.available
                }
            }

            MouseArea {
                anchors.fill: parent
                enabled: volumeSection.available
                hoverEnabled: true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: volumeSection.toggleMute()
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
                text: "Audio"
                color: root.textColor
                font.pixelSize: root.metrics.panelTitleFontSize
                font.weight: root.metrics.panelTitleFontWeight
                wrapMode: Text.NoWrap
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
            }

            VolumeSection {
                title: "Output"
                deviceLabel: root.nodeLabel(root.sink, "No output")
                devices: root.outputDevices
                defaultNode: root.sink
                outputSection: true
                audio: root.outputAudio
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
            }

            VolumeSection {
                title: "Input"
                deviceLabel: root.nodeLabel(root.source, "No input")
                devices: root.inputDevices
                defaultNode: root.source
                outputSection: false
                audio: root.inputAudio
            }
        }
    }
}
