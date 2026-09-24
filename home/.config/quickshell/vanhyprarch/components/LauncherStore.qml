pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    readonly property var launchers: state.ready ? state.launchers : []
    readonly property bool ready: state.ready
    readonly property bool editable: state.ready && !storage.running
    readonly property string errorMessage: state.errorMessage
    readonly property string statePath: Quickshell.statePath("launchers.json")
    readonly property string helper: Quickshell.shellDir
        + "/helpers/vanhyprarch_launcher_state"

    function contains(desktopId: string): bool {
        return launchers.some(launcher => launcher.desktopId === desktopId)
    }

    function addLauncher(desktopId: string): bool {
        if (!editable || contains(desktopId) || DesktopEntries.byId(desktopId) === null)
            return false
        storage.startOperation("edit", [state.revision, "add", desktopId])
        return true
    }

    function removeLauncher(desktopId: string): bool {
        if (!editable || !contains(desktopId))
            return false
        storage.startOperation("edit", [state.revision, "remove", desktopId])
        return true
    }

    function moveLauncher(desktopId: string, targetIndex: int): bool {
        if (!editable || targetIndex < 0 || targetIndex >= launchers.length)
            return false
        const sourceIndex = launchers.findIndex(launcher => launcher.desktopId === desktopId)
        if (sourceIndex < 0 || sourceIndex === targetIndex)
            return false
        storage.startOperation("edit", [state.revision, "move", desktopId,
            String(targetIndex)])
        return true
    }

    function inspectState(allowSeed: bool): void {
        if (storage.running)
            return
        state.ready = false
        state.needsSeed = false
        storage.allowSeed = allowSeed
        storage.startOperation("inspect", [])
    }

    function retry(): void { inspectState(false) }

    function seedDefaults(): void {
        if (!state.needsSeed || state.ready || storage.running)
            return
        const applications = DesktopEntries.applications.values
        if (applications.length === 0)
            return
        for (const desktopId of ["firefox", "foot", "thunar", "io.github.kolunmi.Bazaar"]) {
            const entry = DesktopEntries.byId(desktopId)
            // A missing entry may still be loading. Never save a partial first seed.
            if (!entry || entry.id !== desktopId || !applications.includes(entry))
                return
        }
        state.needsSeed = false
        storage.startOperation("seed", [])
    }

    function finishOperation(kind: string, allowSeed: bool,
            exitCode: int, output: string): void {
        let result
        try {
            result = JSON.parse(output)
            if (exitCode !== 0 || !result || typeof result.status !== "string")
                throw new Error("invalid helper response")
        } catch (error) {
            state.ready = false
            state.errorMessage = "Could not inspect launcher state"
            return
        }

        if (result.status === "valid" && Array.isArray(result.launchers)
                && typeof result.revision === "string") {
            state.launchers = result.launchers
            state.revision = result.revision
            state.needsSeed = false
            state.errorMessage = ""
            state.ready = true
            return
        }
        state.ready = false
        state.revision = ""
        if (result.status === "absent" && kind === "inspect") {
            if (allowSeed) {
                state.errorMessage = ""
                state.needsSeed = true
                Qt.callLater(root.seedDefaults)
            } else {
                state.errorMessage = "Launcher state file is missing"
            }
        } else if (result.status === "conflict" && kind === "seed") {
            // The seed is no-clobber. Classify the file that won the race.
            state.needsSeed = false
            Qt.callLater(() => root.inspectState(true))
        } else {
            state.needsSeed = false
            state.errorMessage = typeof result.message === "string"
                ? result.message : "Launcher state could not be loaded"
        }
    }

    QtObject {
        id: state
        property bool ready: false
        property bool needsSeed: false
        property string revision: ""
        property string errorMessage: ""
        property var launchers: []
    }

    Connections {
        target: DesktopEntries.applications
        function onValuesChanged(): void { Qt.callLater(root.seedDefaults) }
    }

    Component.onCompleted: inspectState(true)

    Process {
        id: storage
        property string kind: ""
        property string output: ""
        property bool exited: false
        property bool collected: false
        property int code: -1
        property bool allowSeed: false

        function startOperation(nextKind: string, arguments: var): void {
            if (running)
                return
            kind = nextKind
            output = ""
            exited = false
            collected = false
            code = -1
            command = [root.helper, nextKind, root.statePath].concat(arguments)
            running = true
        }

        function complete(): void {
            if (!exited || !collected)
                return
            const completedKind = kind
            kind = ""
            root.finishOperation(completedKind, allowSeed, code, output)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                storage.output = text
                storage.collected = true
                storage.complete()
            }
        }

        onExited: function(exitCode) {
            storage.code = exitCode
            storage.exited = true
            storage.complete()
        }
    }
}
