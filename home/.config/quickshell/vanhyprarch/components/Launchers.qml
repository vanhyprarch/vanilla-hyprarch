pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland

Item {
    id: root

    required property var theme
    required property var metrics
    required property LauncherStore store
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
    property int dragIndicatorWidth: 24
    property int dragIndicatorHeight: 2

    readonly property var resolvedLaunchers: {
        // Re-resolve saved IDs when the installed application index changes.
        DesktopEntries.applications.values
        return store.launchers.map(launcher => ({
            config: launcher,
            desktopEntry: DesktopEntries.byId(launcher.desktopId)
        })).filter(launcher => launcher.desktopEntry !== null)
    }
    readonly property var openUnpinnedDesktopIds: collectOpenUnpinnedDesktopIds()
    readonly property var runtimeLaunchers: {
        // Re-resolve ephemeral IDs when the installed application index changes.
        DesktopEntries.applications.values
        return runtimeOrder.map(desktopId => DesktopEntries.byId(desktopId))
            .filter(desktopEntry => desktopEntry !== null)
    }

    function normalizeIdentifier(value): string {
        return value === null || value === undefined
            ? "" : String(value).trim().toLowerCase()
    }

    function desktopEntryCandidates(desktopEntry: DesktopEntry): var {
        if (!desktopEntry)
            return []

        const candidates = []
        const startupClass = normalizeIdentifier(desktopEntry.startupClass)
        const desktopId = normalizeIdentifier(desktopEntry.id)
        const desktopIdWithoutSuffix = desktopId.endsWith(".desktop")
            ? desktopId.slice(0, -8) : desktopId

        for (const candidate of [startupClass, desktopId, desktopIdWithoutSuffix]) {
            if (candidate !== "" && !candidates.includes(candidate))
                candidates.push(candidate)
        }
        return candidates
    }

    function runtimeIdentifiersForToplevel(toplevel): var {
        if (!toplevel)
            return []

        const ipcObject = toplevel.lastIpcObject
        const wayland = toplevel.wayland
        const identifiers = [
            normalizeIdentifier(ipcObject ? ipcObject["class"] : ""),
            normalizeIdentifier(wayland ? wayland.appId : "")
        ]
        return identifiers.filter((identifier, index) =>
            identifier !== "" && identifiers.indexOf(identifier) === index)
    }

    function resolveDesktopEntryForToplevel(toplevel): var {
        const runtimeIdentifiers = runtimeIdentifiersForToplevel(toplevel)
        if (runtimeIdentifiers.length === 0)
            return null

        const applications = DesktopEntries.applications.values
        for (const runtimeIdentifier of runtimeIdentifiers) {
            const exactMatch = applications.find(desktopEntry =>
                desktopEntryCandidates(desktopEntry).includes(runtimeIdentifier))
            if (exactMatch)
                return exactMatch
        }

        for (const runtimeIdentifier of runtimeIdentifiers) {
            const fallback = DesktopEntries.heuristicLookup(runtimeIdentifier)
            if (!fallback)
                continue
            const installedEntry = applications.find(desktopEntry => desktopEntry.id === fallback.id)
            if (installedEntry)
                return installedEntry
        }

        return null
    }

    function toplevelMatchesDesktopEntry(toplevel, desktopEntry: DesktopEntry): bool {
        if (!toplevel || !desktopEntry)
            return false

        const runtimeIdentifiers = runtimeIdentifiersForToplevel(toplevel)
        const candidates = desktopEntryCandidates(desktopEntry)
        if (runtimeIdentifiers.some(identifier => candidates.includes(identifier)))
            return true

        const resolvedEntry = resolveDesktopEntryForToplevel(toplevel)
        return resolvedEntry !== null && resolvedEntry.id === desktopEntry.id
    }

    function matchingToplevelsForDesktopEntry(desktopEntry: DesktopEntry): var {
        if (!desktopEntry)
            return []

        const matches = []
        for (const workspace of Hyprland.workspaces.values) {
            if (!workspace || !workspace.toplevels)
                continue

            for (const toplevel of workspace.toplevels.values) {
                if (toplevelMatchesDesktopEntry(toplevel, desktopEntry)
                        && !matches.some(match => match.toplevel === toplevel))
                    matches.push({ toplevel: toplevel, workspace: workspace })
            }
        }
        return matches
    }

    function workspaceIdsForDesktopEntry(desktopEntry: DesktopEntry): var {
        if (!desktopEntry)
            return []

        const workspaceIds = []
        for (const workspace of Hyprland.workspaces.values) {
            if (!workspace || workspace.id <= 0 || !workspace.toplevels)
                continue

            const matches = workspace.toplevels.values.some(toplevel =>
                toplevelMatchesDesktopEntry(toplevel, desktopEntry))

            if (matches && !workspaceIds.includes(workspace.id))
                workspaceIds.push(workspace.id)
        }

        return workspaceIds.sort((left, right) => left - right)
    }

    function collectOpenUnpinnedDesktopIds(): var {
        // Make application-index and persistent-store changes explicit dependencies.
        DesktopEntries.applications.values
        const pinnedIds = store.launchers.map(launcher => launcher.desktopId)
        const desktopIds = []

        for (const workspace of Hyprland.workspaces.values) {
            if (!workspace || !workspace.toplevels)
                continue

            for (const toplevel of workspace.toplevels.values) {
                const desktopEntry = resolveDesktopEntryForToplevel(toplevel)
                if (desktopEntry && !pinnedIds.includes(desktopEntry.id)
                        && !desktopIds.includes(desktopEntry.id))
                    desktopIds.push(desktopEntry.id)
            }
        }

        return desktopIds
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

    function activateExistingWindow(desktopEntry: DesktopEntry): void {
        const matches = matchingToplevelsForDesktopEntry(desktopEntry)
        if (matches.length === 0)
            return

        const focusedWorkspace = Hyprland.focusedWorkspace
        let match = matches.find(candidate => focusedWorkspace && candidate.workspace
            && candidate.workspace.id === focusedWorkspace.id)
        if (!match)
            match = matches[0]

        const wayland = match.toplevel ? match.toplevel.wayland : null
        if (wayland) {
            wayland.activate()
        } else if (match.workspace) {
            match.workspace.activate()
        }
    }

    function isDesktopEntryRunning(desktopEntry: DesktopEntry): bool {
        return matchingToplevelsForDesktopEntry(desktopEntry).length > 0
    }

    function activateOrLaunch(desktopEntry: DesktopEntry): void {
        if (!desktopEntry)
            return

        if (isDesktopEntryRunning(desktopEntry))
            activateExistingWindow(desktopEntry)
        else
            desktopEntry.execute()
    }

    function closeAllWindows(desktopEntry: DesktopEntry): void {
        // Snapshot the matches before close requests mutate the workspace models.
        const matches = matchingToplevelsForDesktopEntry(desktopEntry).slice()
        for (const match of matches) {
            const toplevel = match ? match.toplevel : null
            const handle = toplevel ? (toplevel.wayland || toplevel.handle) : null
            if (handle)
                handle.close()
        }
    }

    function beginPinnedDrag(desktopId: string): void {
        if (!store.contains(desktopId))
            return

        launcherContextMenu.visible = false
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
        launcherContextMenu.visible = false
        launcherContextMenu.desktopEntry = desktopEntry
        contextMenuSourceAnchor = anchorItem
        launcherContextMenu.pinned = pinned
        launcherContextMenu.running = running
        launcherContextMenu.visible = true
    }

    onOpenUnpinnedDesktopIdsChanged: reconcileRuntimeOrder()
    Component.onCompleted: reconcileRuntimeOrder()

    implicitWidth: contentWidth
    implicitHeight: content.implicitHeight
    width: implicitWidth
    height: implicitHeight

    Column {
        id: content

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
                workspaceIds: root.workspaceIdsForDesktopEntry(modelData.desktopEntry)
                onActivationRequested: root.activateOrLaunch(modelData.desktopEntry)
                onContextMenuRequested: root.openContextMenu(modelData.desktopEntry,
                    launcherButton, true, root.isDesktopEntryRunning(modelData.desktopEntry))
                onDragStarted: root.beginPinnedDrag(modelData.desktopEntry.id)
                onDragFinished: root.finishPinnedDrag(modelData.desktopEntry.id)
            }
        }

        Item {
            id: addButton

            anchors.horizontalCenter: parent.horizontalCenter
            width: root.buttonSize
            height: root.buttonSize

            Text {
                anchors.centerIn: parent
                text: "+"
                color: root.textColor
                font.pixelSize: root.metrics.heroIconSize
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: appPicker.visible = !appPicker.visible
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
                workspaceIds: root.workspaceIdsForDesktopEntry(modelData)
                onActivationRequested: root.activateOrLaunch(modelData)
                onContextMenuRequested: root.openContextMenu(modelData,
                    runtimeLauncherButton, false, root.isDesktopEntryRunning(modelData))
            }
        }
    }

    Repeater {
        model: root.resolvedLaunchers.length + 1

        DropArea {
            required property int index

            x: (root.width - root.buttonSize) / 2
            y: root.insertionTargetY(index)
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
        y: root.insertionIndicatorY(root.pendingDropIndex)
        width: root.dragIndicatorWidth
        height: root.dragIndicatorHeight
        z: 11
        radius: height / 2
        color: root.dragIndicatorColor
        visible: root.activeDragDesktopId !== "" && root.pendingDropIndex >= 0
    }

    Item {
        id: appPickerPopupAnchor

        parent: root.parent
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.y + addButton.y
        width: root.metrics.dockLauncherTarget
        height: root.metrics.dockLauncherTarget
    }

    Item {
        id: launcherContextPopupAnchor

        parent: root.parent
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.contextMenuSourceAnchor
            ? root.contextMenuSourceAnchor.mapToItem(parent, 0, 0).y : 0
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

    LauncherContextMenu {
        id: launcherContextMenu
        theme: root.theme
        metrics: root.metrics
        launcherStore: root.store
        popupAnchorItem: launcherContextPopupAnchor
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        onCloseAllRequested: root.closeAllWindows(launcherContextMenu.desktopEntry)
    }
}
