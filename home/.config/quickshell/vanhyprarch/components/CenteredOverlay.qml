import QtQuick
import Quickshell
import Quickshell.Hyprland
import "CenteredOverlayGeometry.js" as OverlayGeometry

PanelWindow {
    id: root

    property var targetScreen: null
    required property int screenWidth
    required property int screenHeight
    signal dismissed()

    screen: targetScreen
    anchors {
        top: true
        left: true
    }
    margins.top: OverlayGeometry.margin(root.screenHeight, root.implicitHeight)
    margins.left: OverlayGeometry.margin(root.screenWidth, root.implicitWidth)
    exclusiveZone: 0
    exclusionMode: ExclusionMode.Ignore
    focusable: true

    HyprlandFocusGrab {
        active: root.visible
        windows: [root]
        onCleared: if (root.visible) root.dismissed()
    }
}
