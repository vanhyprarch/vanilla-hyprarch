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
    property bool requestedVisible: false
    readonly property var anchorWindow: root.popupAnchorItem
        ? root.popupAnchorItem.QsWindow.window : null
    readonly property var focusCompanion: root.anchorWindow
    readonly property bool anchorReady: DockGeometry.anchorReady(
        root.popupAnchorItem, root.anchorWindow, root.targetScreen)
    readonly property var anchorRect: {
        const item = root.popupAnchorItem
        const window = root.anchorWindow
        // windowTransform is the reactive invalidation source for itemRect().
        if (window)
            window.windowTransform
        if (item) {
            // itemRect() is intentionally non-reactive. These dependencies
            // cover launcher changes and dock relayout.
            item.x
            item.y
            item.width
            item.height
        }

        return DockGeometry.mapAnchorRect(item, window,
            root.targetScreen, function(candidate) {
                return candidate.QsWindow.itemRect(candidate)
            })
    }
    readonly property bool placementReady: root.anchorReady
        && root.anchorRect !== null
    readonly property int anchorParentWidth:
        root.popupAnchorItem && root.popupAnchorItem.parent
            ? root.popupAnchorItem.parent.width : root.metrics.dockWidth

    function dismissFromCoordinator(): void {
        root.requestedVisible = false
    }

    screen: root.targetScreen
    anchors {
        top: true
        left: true
    }
    margins.left: root.placementReady
        ? DockGeometry.horizontalMargin(root.anchorRect.x,
            root.anchorRect.width, root.anchorParentWidth,
            root.metrics.dockPopupGap, root.implicitWidth,
            root.targetScreen.width)
        : 0
    margins.top: root.placementReady
        ? (root.alignToAnchorTop
            ? DockGeometry.alignedTopMargin(root.anchorRect.y,
                root.anchorTopOffset, root.implicitHeight,
                root.targetScreen.height)
            : DockGeometry.aboveMargin(root.anchorRect.y,
                root.anchorRect.height, root.parallelOffset,
                root.implicitHeight, root.targetScreen.height))
        : 0

    implicitWidth: root.panelWidth
    color: "transparent"
    aboveWindows: true
    exclusiveZone: 0
    exclusionMode: ExclusionMode.Ignore
    focusable: true
    visible: DockGeometry.surfaceVisible(root.requestedVisible,
        root.placementReady)

    Component.onCompleted: root.focusCoordinator.registerDock(root)
    Component.onDestruction: root.focusCoordinator.unregisterDock(root)

    Connections {
        target: root
        function onVisibleChanged(): void {
            root.focusCoordinator.windowVisibilityChanged(root, "dock")
        }
    }

    Connections {
        target: root.popupAnchorItem
        ignoreUnknownSignals: true
        function onDestroyed(): void {
            root.requestedVisible = false
        }
    }
}
