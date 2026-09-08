pragma ComponentBehavior: Bound

//@ pragma UseQApplication

import QtQuick
import Quickshell
import Quickshell.Wayland

ShellRoot {
    id: root

    readonly property int renderDelayMs: 33
    readonly property real lyReferenceDelayMs: 5.0
    property real animationFrames: 0.0

    Timer {
        interval: root.renderDelayMs
        repeat: true
        running: true

        onTriggered: {
            root.animationFrames += root.renderDelayMs / root.lyReferenceDelayMs
        }
    }

    Variants {
        model: Quickshell.screens

        delegate: Scope {
            id: screenScope

            required property var modelData

            PanelWindow {
                screen: screenScope.modelData

                anchors {
                    top: true
                    bottom: true
                    left: true
                    right: true
                }

                exclusionMode: ExclusionMode.Ignore
                exclusiveZone: 0
                color: "#000000"

                WlrLayershell.layer: WlrLayer.Overlay
                WlrLayershell.namespace: "vanhyprarch-screensaver"
                WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

                Colormix {
                    anchors.fill: parent
                    animationFrames: root.animationFrames
                }
            }
        }
    }
}
