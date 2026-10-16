pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

Item {
    id: root

    required property var theme
    required property var metrics
    required property LauncherStore store
    required property LauncherController controller
    required property var targetScreen
    required property var focusCoordinator
    readonly property int contentWidth: root.metrics.dockContentWidth
    readonly property int buttonSize: root.metrics.dockLauncherTarget
    readonly property int iconSize: root.metrics.applicationLauncherIconSize
    readonly property int spacing: root.metrics.dockItemGap
    property color textColor: root.theme.text
    property var runtimeOrder: []
    property string activeDragDesktopId: ""
    property int pendingDropIndex: -1
    property Item contextMenuSourceAnchor: null
    property color dragIndicatorColor: root.theme.accent
    readonly property int dragIndicatorWidth: root.metrics.dockLauncherDragIndicatorWidth
    readonly property int dragIndicatorHeight: root.metrics.dockLauncherDragIndicatorHeight
    signal emptySpacePressed()

    readonly property var resolvedLaunchers: {
        // Re-resolve saved IDs when the installed application index changes.
        DesktopEntries.applications.values
        return store.launchers.map(launcher => ({
            config: launcher,
            desktopEntry: DesktopEntries.byId(launcher.desktopId)
        })).filter(launcher => launcher.desktopEntry !== null)
    }
    readonly property var openUnpinnedDesktopIds: {
        const pinnedIds = store.launchers.map(launcher => launcher.desktopId)
        return controller.openDesktopIds.filter(desktopId => !pinnedIds.includes(desktopId))
    }
    readonly property var runtimeLaunchers: {
        // Re-resolve ephemeral IDs when the installed application index changes.
        DesktopEntries.applications.values
        return runtimeOrder.map(desktopId => DesktopEntries.byId(desktopId))
            .filter(desktopEntry => desktopEntry !== null)
    }

    function reconcileRuntimeOrder(): void {
        const openIds = openUnpinnedDesktopIds
        const retainedIds = runtimeOrder.filter(desktopId => openIds.includes(desktopId))
        const newIds = openIds.filter(desktopId => !retainedIds.includes(desktopId))
        const nextOrder = retainedIds.concat(newIds)

        if (nextOrder.length !== runtimeOrder.length
                || nextOrder.some((desktopId, index) => desktopId !== runtimeOrder[index]))
            runtimeOrder = nextOrder
    }

    function beginPinnedDrag(desktopId: string): void {
        if (!store.contains(desktopId))
            return

        launcherContextMenu.requestedVisible = false
        activeDragDesktopId = desktopId
        pendingDropIndex = -1
    }

    function finishPinnedDrag(desktopId: string): void {
        if (activeDragDesktopId !== desktopId)
            return

        activeDragDesktopId = ""
        pendingDropIndex = -1
    }

    function isPinnedDragSource(source): bool {
        return source && source.draggable && source.dragDesktopId
            && store.contains(source.dragDesktopId)
    }

    function insertionTargetY(insertionIndex: int): real {
        if (insertionIndex === 0)
            return 0
        return (insertionIndex - 1) * (buttonSize + spacing) + buttonSize / 2
    }

    function insertionTargetHeight(insertionIndex: int): real {
        if (insertionIndex === 0)
            return buttonSize / 2
        if (insertionIndex === resolvedLaunchers.length)
            return buttonSize / 2 + spacing
        return buttonSize + spacing
    }

    function insertionIndicatorY(insertionIndex: int): real {
        if (insertionIndex === 0)
            return 0
        return insertionIndex * (buttonSize + spacing) - spacing / 2
            - dragIndicatorHeight / 2
    }

    function storeTargetIndexForInsertion(desktopId: string, insertionIndex: int): int {
        const visibleIds = resolvedLaunchers.map(launcher => launcher.desktopEntry.id)
        const sourceVisibleIndex = visibleIds.indexOf(desktopId)
        const sourceStoreIndex = store.launchers.findIndex(launcher =>
            launcher.desktopId === desktopId)
        if (sourceVisibleIndex < 0 || sourceStoreIndex < 0
                || insertionIndex < 0 || insertionIndex > visibleIds.length)
            return -1

        // The slots immediately before and after the source both represent its
        // existing final position.
        if (insertionIndex === sourceVisibleIndex
                || insertionIndex === sourceVisibleIndex + 1)
            return sourceStoreIndex

        const finalVisibleIndex = insertionIndex > sourceVisibleIndex
            ? insertionIndex - 1 : insertionIndex
        const remainingLaunchers = store.launchers.filter(launcher =>
            launcher.desktopId !== desktopId)
        const remainingVisibleIds = visibleIds.filter(id => id !== desktopId)

        if (finalVisibleIndex < remainingVisibleIds.length) {
            const targetDesktopId = remainingVisibleIds[finalVisibleIndex]
            return remainingLaunchers.findIndex(launcher =>
                launcher.desktopId === targetDesktopId)
        }

        if (remainingVisibleIds.length === 0)
            return sourceStoreIndex

        const lastVisibleId = remainingVisibleIds[remainingVisibleIds.length - 1]
        const lastVisibleStoreIndex = remainingLaunchers.findIndex(launcher =>
            launcher.desktopId === lastVisibleId)
        return lastVisibleStoreIndex < 0 ? -1 : lastVisibleStoreIndex + 1
    }

    function dropPinnedLauncher(drop, insertionIndex: int): void {
        const source = drop.source
        if (!isPinnedDragSource(source))
            return

        const desktopId = source.dragDesktopId
        const sourceIndex = store.launchers.findIndex(launcher =>
            launcher.desktopId === desktopId)
        const targetIndex = storeTargetIndexForInsertion(desktopId, insertionIndex)
        if (sourceIndex < 0 || targetIndex < 0)
            return

        drop.acceptProposedAction()
        pendingDropIndex = -1
        if (sourceIndex !== targetIndex)
            Qt.callLater(() => store.moveLauncher(desktopId, targetIndex))
    }

    function openContextMenu(desktopEntry: DesktopEntry, anchorItem: Item,
            pinned: bool, running: bool): void {
        launcherContextMenu.requestedVisible = false
        launcherContextMenu.desktopEntry = desktopEntry
        contextMenuSourceAnchor = anchorItem
        launcherContextMenu.pinned = pinned
        launcherContextMenu.running = running
        launcherContextMenu.requestedVisible = true
    }

    onContextMenuSourceAnchorChanged: {
        if (!root.contextMenuSourceAnchor)
            launcherContextMenu.requestedVisible = false
    }
    onOpenUnpinnedDesktopIdsChanged: reconcileRuntimeOrder()
    Component.onCompleted: reconcileRuntimeOrder()
    onVisibleChanged: {
        if (!visible)
            launcherStateDiagnostic.requestedVisible = false
    }

    Connections {
        target: root.store
        function onErrorMessageChanged(): void {
            if (root.store.errorMessage !== "") {
                appPicker.requestedVisible = false
                launcherContextMenu.requestedVisible = false
            }
        }
    }

    implicitWidth: contentWidth
    implicitHeight: content.implicitHeight
    width: implicitWidth
    height: implicitHeight

    Flickable {
        id: launcherViewport

        anchors.fill: parent
        contentWidth: width
        contentHeight: Math.max(height, content.implicitHeight)
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        MouseArea {
            width: launcherViewport.width
            height: launcherViewport.contentHeight
            z: -1
            acceptedButtons: Qt.LeftButton
            onPressed: root.emptySpacePressed()
        }

        Column {
            id: content

            anchors.verticalCenter: parent.verticalCenter
            width: root.width
            spacing: root.spacing

            Repeater {
                model: root.resolvedLaunchers

                LauncherButton {
                    id: launcherButton

                    required property var modelData

                    theme: root.theme
                    metrics: root.metrics
                    x: (root.width - width) / 2
                    desktopEntry: modelData.desktopEntry
                    draggable: true
                    workspaceIds: root.controller.workspaceIdsForDesktopEntry(modelData.desktopEntry)
                    onActivationRequested: root.controller.activateOrLaunch(modelData.desktopEntry)
                    onContextMenuRequested: root.openContextMenu(modelData.desktopEntry,
                        launcherButton, true, root.controller.isDesktopEntryRunning(modelData.desktopEntry))
                    onDragStarted: root.beginPinnedDrag(modelData.desktopEntry.id)
                    onDragFinished: root.finishPinnedDrag(modelData.desktopEntry.id)
                }
            }

            Item {
                id: addButton
                objectName: "launcherAddControl"

                anchors.horizontalCenter: parent.horizontalCenter
                width: root.buttonSize
                height: root.buttonSize

                Text {
                    anchors.centerIn: parent
                    text: root.store.errorMessage !== "" ? "?" : "+"
                    color: root.textColor
                    font.pixelSize: root.metrics.dockAddGlyphSize
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (root.store.errorMessage !== "")
                            root.focusCoordinator.toggleDockWindow(launcherStateDiagnostic)
                        else
                            root.focusCoordinator.toggleDockWindow(appPicker)
                    }
                }
            }

            Repeater {
                model: root.runtimeLaunchers

                LauncherButton {
                    id: runtimeLauncherButton

                    required property DesktopEntry modelData

                    theme: root.theme
                    metrics: root.metrics
                    x: (root.width - width) / 2
                    desktopEntry: modelData
                    draggable: false
                    workspaceIds: root.controller.workspaceIdsForDesktopEntry(modelData)
                    onActivationRequested: root.controller.activateOrLaunch(modelData)
                    onContextMenuRequested: root.openContextMenu(modelData,
                        runtimeLauncherButton, false, root.controller.isDesktopEntryRunning(modelData))
                }
            }
        }

        Repeater {
            model: root.resolvedLaunchers.length + 1

            DropArea {
                required property int index

                x: (root.width - root.buttonSize) / 2
                y: content.y + root.insertionTargetY(index)
                width: root.buttonSize
                height: root.insertionTargetHeight(index)
                z: 10
                keys: ["pinned-launcher"]

                onEntered: drag => {
                    if (root.isPinnedDragSource(drag.source))
                        root.pendingDropIndex = index
                }
                onExited: {
                    if (root.pendingDropIndex === index)
                        root.pendingDropIndex = -1
                }
                onDropped: drop => root.dropPinnedLauncher(drop, index)
            }
        }

        Rectangle {
            x: (root.width - width) / 2
            y: content.y + root.insertionIndicatorY(root.pendingDropIndex)
            width: root.dragIndicatorWidth
            height: root.dragIndicatorHeight
            z: 11
            radius: height / 2
            color: root.dragIndicatorColor
            visible: root.activeDragDesktopId !== ""
                && root.pendingDropIndex >= 0
        }

        VerticalScrollIndicator {
            view: launcherViewport
            metrics: root.metrics
            theme: root.theme
        }
    }

    Item {
        id: appPickerPopupAnchor

        parent: root.parent
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.y + launcherViewport.y + content.y + addButton.y
            - launcherViewport.contentY
        width: root.metrics.dockLauncherTarget
        height: root.metrics.dockLauncherTarget
    }

    Item {
        id: launcherContextPopupAnchor

        parent: root.parent
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.contextMenuSourceAnchor
            ? root.y + launcherViewport.y + content.y
                + root.contextMenuSourceAnchor.y - launcherViewport.contentY
            : 0
        width: root.metrics.dockLauncherTarget
        height: root.contextMenuSourceAnchor
            ? root.contextMenuSourceAnchor.height
            : root.metrics.dockLauncherTarget
    }

    AppPicker {
        id: appPicker
        theme: root.theme
        metrics: root.metrics
        popupAnchorItem: appPickerPopupAnchor
        launcherStore: root.store
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
    }

    LauncherStateDiagnostic {
        id: launcherStateDiagnostic
        theme: root.theme
        metrics: root.metrics
        launcherStore: root.store
        popupAnchorItem: appPickerPopupAnchor
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
    }

    LauncherContextMenu {
        id: launcherContextMenu
        controller: root.controller
        theme: root.theme
        metrics: root.metrics
        launcherStore: root.store
        popupAnchorItem: launcherContextPopupAnchor
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        onCloseAllRequested: root.controller.closeAllWindows(launcherContextMenu.desktopEntry)
    }
}
