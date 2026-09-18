import QtQuick
import Quickshell
import "CenteredOverlayGeometry.js" as OverlayGeometry

PanelWindow {
    id: root

    property var targetScreen: null
    required property var focusCoordinator
    required property int screenWidth
    required property int screenHeight
    property int persistentLeftInset: 0
    signal dismissed()

    function dismissFromCoordinator(): void {
        if (root.visible)
            root.dismissed()
    }

    screen: targetScreen
    anchors {
        top: true
        left: true
    }
    margins.top: OverlayGeometry.margin(root.screenHeight, root.implicitHeight)
    margins.left: OverlayGeometry.usableMargin(root.screenWidth,
        root.persistentLeftInset, root.implicitWidth)
    aboveWindows: true
    exclusiveZone: 0
    exclusionMode: ExclusionMode.Ignore
    focusable: true

    Component.onCompleted: root.focusCoordinator.registerCentral(root)
    Component.onDestruction: root.focusCoordinator.unregisterCentral(root)

    Connections {
        target: root
        function onVisibleChanged(): void {
            root.focusCoordinator.windowVisibilityChanged(root, "central")
        }
    }
}
