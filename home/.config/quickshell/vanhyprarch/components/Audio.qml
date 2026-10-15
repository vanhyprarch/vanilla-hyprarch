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

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property string iconName: {
        const audio = root.sink && root.sink.audio ? root.sink.audio : null
        if (!audio || audio.muted)
            return "volume-off"

        const volume = Number(audio.volume)
        if (!isFinite(volume) || volume <= 0)
            return "volume-off"
        if (volume <= 0.33)
            return "volume"
        if (volume <= 0.66)
            return "volume-1"
        return "volume-2"
    }

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    PwObjectTracker {
        objects: root.sink ? [root.sink] : []
    }

    SystemIcon {
        anchors.centerIn: parent
        iconName: root.iconName
        theme: root.theme
        metrics: root.metrics
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.focusCoordinator.toggleDockWindow(audioPanel)
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
