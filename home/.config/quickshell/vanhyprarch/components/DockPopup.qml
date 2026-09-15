import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property var metrics
    required property Item popupAnchorItem
    property int panelWidth: root.metrics.standardPanelWidth
    property int parallelOffset: root.metrics.dockPopupParallelOffset

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: -Math.max(0,
            ((root.popupAnchorItem.parent
                ? root.popupAnchorItem.parent.width
                : root.metrics.dockWidth) - root.popupAnchorItem.width) / 2)
            - root.metrics.dockPopupGap
        margins.bottom: root.parallelOffset
    }

    implicitWidth: root.panelWidth
    color: "transparent"
    grabFocus: true
    visible: false
}
