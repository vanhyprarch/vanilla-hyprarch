pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property var theme
    required property var metrics
    required property LauncherStore launcherStore
    property DesktopEntry desktopEntry
    property Item popupAnchorItem
    property bool pinned: true
    property bool running: false
    property int popupVerticalOffset: 4

    signal closeAllRequested()

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Top
        gravity: Edges.Right | Edges.Bottom
        margins.right: -Math.max(0,
            ((root.popupAnchorItem && root.popupAnchorItem.parent
                ? root.popupAnchorItem.parent.width
                : root.metrics.dockWidth)
                - (root.popupAnchorItem
                    ? root.popupAnchorItem.width
                    : root.metrics.dockLauncherTarget)) / 2)
            - root.metrics.dockPopupGap
        margins.top: -root.popupVerticalOffset
    }
    implicitWidth: root.metrics.compactActionSurfaceWidth
    implicitHeight: actionsColumn.implicitHeight
        + root.metrics.compactMenuPadding * 2
    color: "transparent"
    grabFocus: true
    visible: false

    onVisibleChanged: {
        if (!visible)
            root.contentItem.forceActiveFocus()
    }

    function normalizeActionIdentifier(value): string {
        return value === null || value === undefined
            ? "" : String(value).trim().toLowerCase()
    }

    function openNewWindow(): void {
        if (!desktopEntry)
            return

        const actions = desktopEntry.actions || []
        const preferredIds = ["new-window", "newwindow", "new_window"]
        let newWindowAction = null

        for (const action of actions) {
            if (action && preferredIds.includes(normalizeActionIdentifier(action.id))) {
                newWindowAction = action
                break
            }
        }

        if (!newWindowAction) {
            for (const action of actions) {
                if (action && normalizeActionIdentifier(action.name) === "new window") {
                    newWindowAction = action
                    break
                }
            }
        }

        if (newWindowAction)
            newWindowAction.execute()
        else
            desktopEntry.execute()
    }

    component ContextActionRow: PanelActionRow {
        width: parent ? parent.width : 0
        implicitHeight: root.metrics.compactActionRowHeight
        metrics: root.metrics
        theme: root.theme
        primaryFontSize: root.metrics.informationLabelFontSize
        primaryFontWeight: root.metrics.informationLabelFontWeight
        activeFocusOnTab: false
    }

    PanelSurface {
        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme
        padding: root.metrics.compactMenuPadding

        Column {
            id: actionsColumn

            width: parent.width
            spacing: root.metrics.rowSpacing

            ContextActionRow {
                visible: root.running
                enabled: root.desktopEntry !== null
                primaryText: "Open new window"
                onActivated: {
                    root.openNewWindow()
                    root.visible = false
                }
            }

            ContextActionRow {
                enabled: root.desktopEntry !== null
                primaryText: root.pinned ? "Remove from dock" : "Pin to dock"
                onActivated: {
                    if (root.pinned)
                        root.launcherStore.removeLauncher(root.desktopEntry.id)
                    else
                        root.launcherStore.addLauncher(root.desktopEntry.id)
                    root.visible = false
                }
            }

            ContextActionRow {
                visible: root.running
                enabled: root.desktopEntry !== null
                primaryText: "Close all windows"
                danger: true
                onActivated: {
                    root.closeAllRequested()
                    root.visible = false
                }
            }
        }
    }
}
