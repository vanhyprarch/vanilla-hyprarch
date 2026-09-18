import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

Item {
    id: root

    required property var theme
    required property var metrics
    required property var targetScreen
    required property var focusCoordinator
    readonly property int buttonSize: root.metrics.dockSystemControlTarget
    readonly property int iconSize: root.metrics.dockSystemIconSize

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property string iconName: {
        const audio = root.sink && root.sink.audio ? root.sink.audio : null
        if (!audio || audio.muted)
            return "audio-volume-muted"

        const volume = Number(audio.volume)
        if (!isFinite(volume) || volume <= 0)
            return "audio-volume-muted"
        if (volume <= 0.33)
            return "audio-volume-low"
        if (volume <= 0.66)
            return "audio-volume-medium"
        return "audio-volume-high"
    }

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    PwObjectTracker {
        objects: root.sink ? [root.sink] : []
    }

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath(root.iconName)
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: audioPanel.requestedVisible = !audioPanel.requestedVisible
    }

    AudioPanel {
        id: audioPanel

        theme: root.theme
        metrics: root.metrics
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        popupAnchorItem: root
    }
}
