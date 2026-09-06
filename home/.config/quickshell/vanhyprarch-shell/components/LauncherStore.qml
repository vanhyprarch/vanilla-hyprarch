pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    readonly property var launchers: state.ready ? state.launchers : []
    readonly property bool ready: state.ready

    function contains(desktopId: string): bool {
        return launchers.some(launcher => launcher.desktopId === desktopId)
    }

    function addLauncher(desktopId: string): bool {
        if (!ready || contains(desktopId) || DesktopEntries.byId(desktopId) === null)
            return false

        state.launchers = launchers.concat([{ desktopId: desktopId, customIcon: "" }])
        persist()
        return true
    }

    function persist(): void {
        // FileView can replay a completed write into its adapter. Keep live state separate.
        jsonData.launchers = state.launchers
        stateFile.writeAdapter()
    }

    // Preserve unknown fields for future launcher metadata, and keep unresolved IDs.
    function normalizeLaunchers(value): var {
        if (!Array.isArray(value))
            return null

        const result = []
        for (const launcher of value) {
            if (!launcher || typeof launcher !== "object" || Array.isArray(launcher)
                    || typeof launcher.desktopId !== "string" || launcher.desktopId.trim() === "")
                continue
            if (result.some(item => item.desktopId === launcher.desktopId))
                continue
            result.push(Object.assign({}, launcher, {
                customIcon: typeof launcher.customIcon === "string" ? launcher.customIcon : ""
            }))
        }
        // An explicitly empty list is valid; a nonempty list with no valid entries is not.
        return value.length > 0 && result.length === 0 ? null : result
    }

    function loadConfiguration(): void {
        if (state.ready)
            return

        let saved = null
        try {
            saved = JSON.parse(stateFile.text())
        } catch (error) {
            // Invalid JSON is treated like an uninitialized configuration.
        }
        const normalized = normalizeLaunchers(saved ? saved.launchers : null)
        if (normalized === null) {
            state.needsSeed = true
            seedDefaults()
            return
        }

        state.launchers = normalized
        state.ready = true
        if (JSON.stringify(normalized) !== JSON.stringify(saved.launchers))
            persist()
    }

    function seedDefaults(): void {
        if (!state.needsSeed || state.ready)
            return

        const applications = DesktopEntries.applications.values
        if (applications.length === 0)
            return

        const names = [["Firefox"], ["Foot"], ["Thunar File Manager", "Thunar"]]
        const lookupNames = ["firefox", "foot", "thunar"]
        const defaults = []
        for (let i = 0; i < names.length; ++i) {
            let entry = applications.find(app => names[i].some(name => app.name.toLowerCase() === name.toLowerCase()))
            if (!entry)
                entry = DesktopEntries.heuristicLookup(lookupNames[i])
            if (entry && applications.includes(entry) && !defaults.some(item => item.desktopId === entry.id))
                defaults.push({ desktopId: entry.id, customIcon: "" })
        }

        state.launchers = defaults
        state.needsSeed = false
        state.ready = true
        persist()
    }

    QtObject {
        id: state
        property bool ready: false
        property bool needsSeed: false
        property var launchers: []
    }

    Connections {
        target: DesktopEntries.applications
        function onValuesChanged(): void {
            // The index emits changes for individual entries while scanning.
            Qt.callLater(root.seedDefaults)
        }
    }

    FileView {
        id: stateFile

        path: Quickshell.statePath("launchers.json")
        atomicWrites: true
        onLoaded: Qt.callLater(root.loadConfiguration)
        onLoadFailed: error => {
            if (error === FileViewError.FileNotFound) {
                state.needsSeed = true
                Qt.callLater(root.seedDefaults)
            } else {
                console.warn("Cannot load launcher configuration:", FileViewError.toString(error))
            }
        }
        onSaveFailed: error => console.warn("Cannot save launcher configuration:", FileViewError.toString(error))

        JsonAdapter {
            id: jsonData
            property var launchers: []
        }
    }
}
