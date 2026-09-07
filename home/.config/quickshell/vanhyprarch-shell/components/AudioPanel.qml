pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

PopupWindow {
    id: root

    required property var theme
    required property Item popupAnchorItem
    required property int popupRadius
    property int panelWidth: 260
    property int panelPadding: 12
    property int rowHeight: 32
    property int popupHorizontalGap: -16
    property int popupVerticalOffset: -2
    property color backgroundColor: root.theme.background
    property color textColor: root.theme.text
    property color secondaryColor: root.theme.surface
    property color accentColor: root.theme.accent

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
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

    PwObjectTracker {
        objects: [root.sink, root.source].filter(node => node !== null)
    }

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: Math.max(0,
            ((root.popupAnchorItem.parent ? root.popupAnchorItem.parent.width : root.popupAnchorItem.width)
                - root.popupAnchorItem.width) / 2) + root.popupHorizontalGap
        margins.bottom: root.popupVerticalOffset
    }

    implicitWidth: panelWidth
    implicitHeight: content.implicitHeight + panelPadding * 2
    color: "transparent"
    visible: false
    grabFocus: true

    component VolumeSection: Column {
        id: volumeSection

        required property string title
        required property string deviceLabel
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
        spacing: 6

        Item {
            width: parent.width
            height: root.rowHeight

            Text {
                anchors {
                    left: parent.left
                    verticalCenter: parent.verticalCenter
                }
                text: volumeSection.title
                color: root.textColor
                font.pixelSize: 13
                font.weight: Font.Medium
            }

            Text {
                anchors {
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                }
                text: volumeSection.available
                    ? Math.round(volumeSection.volume * 100) + "%" : "—"
                color: root.textColor
                font.pixelSize: 13
                font.weight: Font.Medium
            }
        }

        Text {
            width: parent.width
            height: 18
            text: volumeSection.deviceLabel
            color: root.textColor
            font.pixelSize: 12
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        Item {
            id: volumeSlider

            readonly property real progress: volumeSection.volume

            width: parent.width
            height: 20
            opacity: volumeSection.available ? 1.0 : 0.35

            Rectangle {
                id: volumeTrack

                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                }
                height: 4
                radius: height / 2
                color: root.secondaryColor
            }

            Rectangle {
                anchors {
                    left: volumeTrack.left
                    verticalCenter: volumeTrack.verticalCenter
                }
                width: volumeTrack.width * volumeSlider.progress
                height: volumeTrack.height
                radius: height / 2
                color: root.accentColor
            }

            Rectangle {
                width: 14
                height: 14
                radius: width / 2
                x: Math.max(0, Math.min(volumeTrack.width - width,
                    volumeTrack.width * volumeSlider.progress - width / 2))
                anchors.verticalCenter: volumeTrack.verticalCenter
                color: root.accentColor
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
            height: 24

            Rectangle {
                width: 72
                height: parent.height
                anchors.right: parent.right
                radius: root.popupRadius / 2
                color: volumeSection.muted ? root.accentColor : root.secondaryColor
                opacity: volumeSection.available ? 1.0 : 0.35

                Text {
                    anchors.fill: parent
                    text: volumeSection.muted ? "Unmute" : "Mute"
                    color: volumeSection.muted
                        ? root.backgroundColor : root.textColor
                    font.pixelSize: 12
                    font.weight: volumeSection.muted
                        ? Font.Medium : Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.NoWrap
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
            spacing: 6

            Text {
                width: parent.width
                text: "Audio"
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

            VolumeSection {
                title: "Output"
                deviceLabel: root.nodeLabel(root.sink, "No output")
                audio: root.outputAudio
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
            }

            VolumeSection {
                title: "Input"
                deviceLabel: root.nodeLabel(root.source, "No input")
                audio: root.inputAudio
            }
        }
    }
}
