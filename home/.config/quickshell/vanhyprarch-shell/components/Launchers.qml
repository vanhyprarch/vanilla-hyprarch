pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland

Item {
    id: root

    property int contentWidth: 48
    property int buttonSize: 40
    property int iconSize: 28
    property int spacing: 4
    property color textColor: "#5A3525"
    property var runtimeOrder: []

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

    function openContextMenu(desktopEntry: DesktopEntry, anchorItem: Item,
            pinned: bool, running: bool): void {
        launcherContextMenu.visible = false
        launcherContextMenu.desktopEntry = desktopEntry
        launcherContextMenu.popupAnchorItem = anchorItem
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

    LauncherStore {
        id: store
    }

    Column {
        id: content

        width: root.width
        spacing: root.spacing

        Repeater {
            model: root.resolvedLaunchers

            LauncherButton {
                id: launcherButton

                required property var modelData

                x: (root.width - width) / 2
                desktopEntry: modelData.desktopEntry
                buttonSize: root.buttonSize
                iconSize: root.iconSize
                workspaceIds: root.workspaceIdsForDesktopEntry(modelData.desktopEntry)
                onActivationRequested: root.activateOrLaunch(modelData.desktopEntry)
                onContextMenuRequested: root.openContextMenu(modelData.desktopEntry,
                    launcherButton, true, root.isDesktopEntryRunning(modelData.desktopEntry))
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
                font.pixelSize: 24
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

                x: (root.width - width) / 2
                desktopEntry: modelData
                buttonSize: root.buttonSize
                iconSize: root.iconSize
                workspaceIds: root.workspaceIdsForDesktopEntry(modelData)
                onActivationRequested: root.activateOrLaunch(modelData)
                onContextMenuRequested: root.openContextMenu(modelData,
                    runtimeLauncherButton, false, root.isDesktopEntryRunning(modelData))
            }
        }
    }

    AppPicker {
        id: appPicker
        anchor.item: addButton
        launcherStore: store
    }

    LauncherContextMenu {
        id: launcherContextMenu
        launcherStore: store
    }
}
