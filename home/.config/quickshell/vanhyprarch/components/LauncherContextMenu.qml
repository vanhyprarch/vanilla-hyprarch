pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

DockPopup {
    id: root

    required property var theme
    required property LauncherStore launcherStore
    required property LauncherController controller
    property DesktopEntry desktopEntry
    property bool pinned: true
    property bool running: false
    property int popupVerticalOffset: 4

    signal closeAllRequested()

    panelWidth: root.metrics.compactActionSurfaceWidth
    requestedPanelHeight: actionsColumn.implicitHeight
        + root.metrics.compactMenuPadding * 2
    alignToAnchorTop: true
    anchorTopOffset: root.popupVerticalOffset

    onVisibleChanged: {
        if (!visible)
            root.contentItem.forceActiveFocus()
    }

    function openNewWindow(): void {
        controller.openNewWindow(desktopEntry)
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
                    root.requestedVisible = false
                }
            }

            ContextActionRow {
                enabled: root.desktopEntry !== null && root.launcherStore.editable
                primaryText: root.pinned ? "Remove from dock" : "Pin to dock"
                onActivated: {
                    if (root.pinned)
                        root.launcherStore.removeLauncher(root.desktopEntry.id)
                    else
                        root.launcherStore.addLauncher(root.desktopEntry.id)
                    root.requestedVisible = false
                }
            }

            ContextActionRow {
                visible: root.running
                enabled: root.desktopEntry !== null
                primaryText: "Close all windows"
                danger: true
                onActivated: {
                    root.closeAllRequested()
                    root.requestedVisible = false
                }
            }
        }
    }
}
