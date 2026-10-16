pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    // Shared runtime state; LauncherStore remains the preference authority.
    property var compositor: Hyprland
    property var catalog: DesktopEntries
    property var snapshotQuery: clientQuery
    property var clock: () => Date.now()
    property var focusExactWindow: client => Quickshell.execDetached(focusCommand(client))
    property var lastSelected: Object.create(null)
    property var pendingLaunches: Object.create(null)
    property var requests: []
    property bool refreshQueued: false
    readonly property int pendingLaunchMilliseconds: 5000
    readonly property var openDesktopIds: collectOpenDesktopIds()

    function normalizeIdentifier(value): string {
        return value === null || value === undefined
            ? "" : String(value).trim().toLowerCase()
    }

    function desktopEntryCandidates(desktopEntry): var {
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
            normalizeIdentifier(ipcObject ? ipcObject.initialClass : ""),
            normalizeIdentifier(wayland ? wayland.appId : "")
        ]
        return identifiers.filter((identifier, index) =>
            identifier !== "" && identifiers.indexOf(identifier) === index)
    }

    function resolveDesktopEntryForToplevel(toplevel): var {
        const runtimeIdentifiers = runtimeIdentifiersForToplevel(toplevel)
        if (runtimeIdentifiers.length === 0)
            return null

        const applications = catalog.applications.values
        for (const runtimeIdentifier of runtimeIdentifiers) {
            const exactMatch = applications.find(desktopEntry =>
                desktopEntryCandidates(desktopEntry).includes(runtimeIdentifier))
            if (exactMatch)
                return exactMatch
        }

        for (const runtimeIdentifier of runtimeIdentifiers) {
            const fallback = catalog.heuristicLookup(runtimeIdentifier)
            if (!fallback)
                continue
            const installedEntry = applications.find(desktopEntry => desktopEntry.id === fallback.id)
            if (installedEntry)
                return installedEntry
        }

        return null
    }

    function toplevelMatchesDesktopEntry(toplevel, desktopEntry): bool {
        if (!toplevel || !desktopEntry)
            return false

        const runtimeIdentifiers = runtimeIdentifiersForToplevel(toplevel)
        const candidates = desktopEntryCandidates(desktopEntry)
        if (runtimeIdentifiers.some(identifier => candidates.includes(identifier)))
            return true

        const resolvedEntry = resolveDesktopEntryForToplevel(toplevel)
        return resolvedEntry !== null && resolvedEntry.id === desktopEntry.id
    }

    function matchingToplevelsForDesktopEntry(desktopEntry): var {
        if (!desktopEntry)
            return []

        const matches = []
        for (const workspace of compositor.workspaces.values) {
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

    function workspaceIdsForDesktopEntry(desktopEntry): var {
        if (!desktopEntry)
            return []

        const workspaceIds = []
        for (const workspace of compositor.workspaces.values) {
            if (!workspace || workspace.id <= 0 || !workspace.toplevels)
                continue

            const matches = workspace.toplevels.values.some(toplevel =>
                toplevelMatchesDesktopEntry(toplevel, desktopEntry))

            if (matches && !workspaceIds.includes(workspace.id))
                workspaceIds.push(workspace.id)
        }

        return workspaceIds.sort((left, right) => left - right)
    }

    function collectOpenDesktopIds(): var {
        catalog.applications.values
        const ids = []
        for (const workspace of compositor.workspaces.values) {
            if (!workspace || !workspace.toplevels)
                continue
            for (const toplevel of workspace.toplevels.values) {
                const entry = resolveDesktopEntryForToplevel(toplevel)
                if (entry && !ids.includes(entry.id))
                    ids.push(entry.id)
            }
        }
        return ids
    }

    function isDesktopEntryRunning(entry): bool {
        return matchingToplevelsForDesktopEntry(entry).length > 0
    }

    function stableId(value): string {
        if (typeof value !== "string" || !/^(0x)?[0-9a-f]{1,16}$/i.test(value))
            return ""
        return value.toLowerCase().replace(/^0x/, "").replace(/^0+/, "")
    }

    function compareIds(left: string, right: string): int {
        return left.length !== right.length ? left.length - right.length
            : left < right ? -1 : left > right ? 1 : 0
    }

    function toplevelForClient(client): var {
        const identity = stableId(client.stableId)
        if (identity === "")
            return null
        return compositor.toplevels.values.find(toplevel => toplevel
            && stableId(toplevel.address) === stableId(client.address)
            && toplevel.lastIpcObject
            && stableId(toplevel.lastIpcObject.stableId) === identity) || null
    }

    function matchingClients(clients, entry): var {
        return clients.filter(client => client.mapped
            && toplevelMatchesDesktopEntry({ lastIpcObject: client,
                wayland: toplevelForClient(client)?.wayland }, entry))
    }

    function reconcileState(clients): void {
        const hasWindows = desktopId => {
            const entry = catalog.byId(desktopId)
            return entry && (clients === undefined
                ? matchingToplevelsForDesktopEntry(entry)
                : matchingClients(clients, entry)).length > 0
        }
        for (const desktopId of Object.keys(lastSelected)) {
            if (!hasWindows(desktopId))
                delete lastSelected[desktopId]
        }
        const now = clock()
        for (const desktopId of Object.keys(pendingLaunches)) {
            const age = now - pendingLaunches[desktopId]
            if (hasWindows(desktopId) || age < 0 || age >= pendingLaunchMilliseconds)
                delete pendingLaunches[desktopId]
        }
    }

    function activateOrLaunch(entry): void {
        if (!entry)
            return
        requests = requests.concat([entry.id])
        snapshotQuery.start()
    }

    function finishSnapshot(success: bool, output: string): void {
        const queued = requests
        requests = []
        let clients
        try {
            clients = JSON.parse(output)
            if (!success || !Array.isArray(clients)
                    || clients.some(client => !client || typeof client !== "object"
                        || typeof client.mapped !== "boolean"))
                throw new Error("invalid client snapshot")
        } catch (error) {
            console.warn("Could not inspect application windows; launcher request skipped.")
            return
        }
        reconcileState(clients)
        for (const desktopId of queued) {
            const entry = catalog.byId(desktopId)
            if (!entry)
                continue
            const matches = matchingClients(clients, entry)
            if (matches.length === 0) {
                const now = clock()
                const since = pendingLaunches[desktopId]
                if (since !== undefined && now >= since
                        && now - since < pendingLaunchMilliseconds)
                    continue
                pendingLaunches[desktopId] = now
                entry.execute()
                continue
            }
            delete pendingLaunches[desktopId]
            const ordered = matches.filter(client => stableId(client.stableId) !== ""
                && stableId(client.address) !== "").sort((left, right) =>
                    compareIds(stableId(left.stableId), stableId(right.stableId)))
            if (ordered.length === 0) {
                // Metadata may still be arriving. Never launch over a known match.
                console.warn("Application window identity is not ready; activation skipped.")
                continue
            }
            const previous = lastSelected[desktopId] || ""
            const client = ordered.find(candidate =>
                compareIds(stableId(candidate.stableId), previous) > 0) || ordered[0]
            lastSelected[desktopId] = stableId(client.stableId)
            const handle = toplevelForClient(client)?.wayland
            if (handle && typeof handle.activate === "function") {
                try {
                    handle.activate()
                    continue
                } catch (error) {
                    console.warn("Native application activation failed; trying exact focus.")
                }
            }
            focusExactWindow(client)
        }
    }

    function focusCommand(client): var {
        const identity = stableId(client.stableId)
        const address = stableId(client.address)
        if (identity === "" || address === "")
            return []
        // Both interpolated values are validated hexadecimal integers. Recheck
        // identity inside the compositor, atomically with the focus operation.
        const source = 'local w = hl.get_window("address:0x' + address + '"); '
            + 'if w and w.mapped and w.stable_id == 0x' + identity
            + ' then hl.dispatch(hl.dsp.focus({ window = w })) end'
        return ["/usr/bin/hyprctl", "eval", source]
    }

    function openNewWindow(entry): void {
        if (!entry)
            return
        const actions = entry.actions || []
        const preferredIds = ["new-window", "newwindow", "new_window"]
        const action = actions.find(candidate => candidate
            && preferredIds.includes(normalizeIdentifier(candidate.id)))
            || actions.find(candidate => candidate
                && normalizeIdentifier(candidate.name) === "new window")
        if (action)
            action.execute()
        else
            entry.execute()
    }

    function closeAllWindows(entry): void {
        // Handles identify their window directly, including during closure.
        const matches = matchingToplevelsForDesktopEntry(entry).slice()
        for (const match of matches) {
            const handle = match.toplevel?.wayland || match.toplevel?.handle
            if (handle && typeof handle.close === "function")
                handle.close()
        }
    }

    function refreshWindows(): void {
        if (refreshQueued)
            return
        refreshQueued = true
        Qt.callLater(() => {
            refreshQueued = false
            compositor.refreshToplevels()
        })
    }

    onOpenDesktopIdsChanged: reconcileState()
    Component.onCompleted: {
        if (Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE"))
            refreshWindows()
    }

    Connections {
        target: root.compositor
        function onRawEvent(event): void {
            if (["openwindow", "closewindow", "movewindowv2", "windowtitlev2",
                    "configreloaded"].includes(event.name))
                root.refreshWindows()
        }
    }

    Connections {
        target: root.snapshotQuery
        function onFinished(success: bool, output: string): void {
            root.finishSnapshot(success, output)
        }
    }

    Process {
        id: clientQuery
        command: ["/usr/bin/hyprctl", "-j", "clients"]
        property string output: ""
        property bool exited: false
        property bool collected: false
        property bool handled: true
        property bool timedOut: false
        property int code: -1
        signal finished(bool success, string output)

        function start(): void {
            if (!handled)
                return
            output = ""
            exited = false
            collected = false
            handled = false
            timedOut = false
            code = -1
            running = true
        }

        function complete(): void {
            if (handled || !exited || !collected)
                return
            handled = true
            finished(code === 0 && !timedOut, output)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                clientQuery.output = text
                clientQuery.collected = true
                clientQuery.complete()
            }
        }
        onExited: function(exitCode) {
            code = exitCode
            exited = true
            complete()
        }
    }

    Timer {
        interval: 3000
        running: clientQuery.running
        onTriggered: {
            clientQuery.timedOut = true
            clientQuery.running = false
        }
    }
}
