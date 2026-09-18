import QtQuick
import Quickshell
import "DockPopupGeometry.js" as DockGeometry

PanelWindow {
    id: root

    required property var metrics
    required property var targetScreen
    required property var focusCoordinator
    required property Item popupAnchorItem
    property int panelWidth: root.metrics.standardPanelWidth
    property int parallelOffset: root.metrics.dockPopupParallelOffset
    property bool alignToAnchorTop: false
    property int anchorTopOffset: 0
    property int anchorGeometryRevision: 0
    readonly property var focusCompanion: root.popupAnchorItem
        ? root.popupAnchorItem.QsWindow.window : null
    readonly property rect anchorRect: {
        root.anchorGeometryRevision
        const item = root.popupAnchorItem
        if (!item)
            return Qt.rect(0, 0, 0, 0)

        // itemRect() is intentionally non-reactive. These dependencies cover
        // launcher changes, dock relayout, scale, and output transforms.
        item.x
        item.y
        item.width
        item.height
        return item.QsWindow.itemRect(item)
    }
    readonly property int anchorParentWidth:
        root.popupAnchorItem && root.popupAnchorItem.parent
            ? root.popupAnchorItem.parent.width : root.metrics.dockWidth

    function dismissFromCoordinator(): void {
        root.visible = false
    }

    screen: root.targetScreen
    anchors {
        top: true
        left: true
    }
    margins.left: DockGeometry.horizontalMargin(root.anchorRect.x,
        root.anchorRect.width, root.anchorParentWidth,
        root.metrics.dockPopupGap, root.implicitWidth,
        root.targetScreen ? root.targetScreen.width : root.implicitWidth)
    margins.top: root.alignToAnchorTop
        ? DockGeometry.alignedTopMargin(root.anchorRect.y,
            root.anchorTopOffset, root.implicitHeight,
            root.targetScreen ? root.targetScreen.height : root.implicitHeight)
        : DockGeometry.aboveMargin(root.anchorRect.y,
            root.anchorRect.height, root.parallelOffset, root.implicitHeight,
            root.targetScreen ? root.targetScreen.height : root.implicitHeight)

    implicitWidth: root.panelWidth
    color: "transparent"
    aboveWindows: true
    exclusiveZone: 0
    exclusionMode: ExclusionMode.Ignore
    focusable: true
    visible: false

    Component.onCompleted: root.focusCoordinator.registerDock(root)
    Component.onDestruction: root.focusCoordinator.unregisterDock(root)

    Connections {
        target: root
        function onVisibleChanged(): void {
            root.focusCoordinator.windowVisibilityChanged(root, "dock")
        }
    }

    Connections {
        target: root.focusCompanion
        ignoreUnknownSignals: true
        function onWindowTransformChanged(): void {
            root.anchorGeometryRevision++
        }
    }

    Connections {
        target: root.popupAnchorItem
        ignoreUnknownSignals: true
        function onDestroyed(): void {
            root.visible = false
        }
    }
}
