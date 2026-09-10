import QtQuick
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Io

Scope {
    id: root

    property bool persistenceAutostart: true
    property bool ready: false
    property string preference: "unset"
    property string errorMessage: ""
    property bool restoreScheduled: false

    readonly property bool busy: persistenceProcess.running
    readonly property string preferenceHelper:
        Quickshell.shellDir + "/helpers/vanhyprarch_bluetooth_power"

    function adapters(): var {
        return Bluetooth.adapters ? Bluetooth.adapters.values : []
    }

    function parseStatus(output: string): string {
        const values = {}
        const lines = String(output || "").split("\n")
        for (const rawLine of lines) {
            const line = String(rawLine).trim()
            if (line === "")
                continue
            const separator = line.indexOf("=")
            if (separator <= 0)
                throw new Error("invalid status line")
            const key = line.slice(0, separator)
            const value = line.slice(separator + 1)
            if ((key !== "version" && key !== "power")
                    || values[key] !== undefined)
                throw new Error("unknown or duplicate status key")
            values[key] = value
        }
        if (values.version !== "1"
                || ["on", "off", "unset"].indexOf(values.power) < 0)
            throw new Error("invalid Bluetooth power status")
        return values.power
    }

    function applyPreferenceTo(adapterObjects, value: string): int {
        if (value !== "on" && value !== "off" && value !== "unset")
            return 0

        const targetEnabled = value !== "off"
        let changed = 0
        for (const adapter of adapterObjects) {
            if (!adapter || adapter.state === BluetoothAdapterState.Blocked
                    || adapter.state === BluetoothAdapterState.Enabling
                    || adapter.state === BluetoothAdapterState.Disabling
                    || Boolean(adapter.enabled) === targetEnabled)
                continue
            adapter.enabled = targetEnabled
            changed += 1
        }
        return changed
    }

    function applyPreference(): void {
        if (!root.ready || root.busy)
            return
        root.applyPreferenceTo(root.adapters(), root.preference)
    }

    function scheduleRestore(): void {
        if (root.restoreScheduled)
            return
        root.restoreScheduled = true
        Qt.callLater(function() {
            root.restoreScheduled = false
            root.applyPreference()
        })
    }

    function requestEnabled(enabled: bool): bool {
        if (!root.ready || root.busy)
            return false

        const requested = enabled ? "on" : "off"
        root.errorMessage = ""
        if (root.preference === requested) {
            root.applyPreference()
            return true
        }
        persistenceProcess.startOperation("set", requested)
        return true
    }

    function finishOperation(operation: string, requested: string,
            exitCode: int, output: string): void {
        if (exitCode !== 0) {
            root.ready = true
            root.errorMessage = operation === "set"
                ? "Could not save Bluetooth power preference"
                : "Could not load Bluetooth power preference"
            return
        }

        let loadedPreference = "unset"
        try {
            loadedPreference = root.parseStatus(output)
        } catch (error) {
            root.ready = true
            root.errorMessage = "Invalid Bluetooth power preference"
            return
        }
        if (operation === "set" && loadedPreference !== requested) {
            root.ready = true
            root.errorMessage = "Bluetooth power preference was not saved"
            return
        }

        root.preference = loadedPreference
        root.ready = true
        root.errorMessage = ""
        root.scheduleRestore()
    }

    Component.onCompleted: {
        if (root.persistenceAutostart)
            persistenceProcess.startOperation("status", "")
    }

    Connections {
        target: Bluetooth.adapters

        function onValuesChanged(): void {
            root.scheduleRestore()
        }
    }

    Instantiator {
        model: Bluetooth.adapters

        delegate: Connections {
            required property var modelData

            target: modelData
            ignoreUnknownSignals: true

            function onEnabledChanged(): void {
                root.scheduleRestore()
            }

            function onStateChanged(): void {
                root.scheduleRestore()
            }
        }
    }

    Process {
        id: persistenceProcess

        property string operation: ""
        property string requested: ""
        property string output: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property int lastExitCode: -1

        function startOperation(nextOperation: string, nextPreference: string): void {
            if (running)
                return
            operation = nextOperation
            requested = nextPreference
            output = ""
            exitReceived = false
            stdoutReceived = false
            lastExitCode = -1
            command = nextOperation === "set"
                ? ["/bin/sh", root.preferenceHelper, "set", nextPreference]
                : ["/bin/sh", root.preferenceHelper, "status"]
            running = true
        }

        function maybeFinish(): void {
            if (operation === "" || !exitReceived || !stdoutReceived)
                return
            const completedOperation = operation
            const completedRequest = requested
            const completedExitCode = lastExitCode
            const completedOutput = output
            operation = ""
            requested = ""
            root.finishOperation(completedOperation, completedRequest,
                completedExitCode, completedOutput)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                persistenceProcess.output = text
                persistenceProcess.stdoutReceived = true
                persistenceProcess.maybeFinish()
            }
        }

        onExited: function(exitCode, exitStatus) {
            persistenceProcess.lastExitCode = exitCode
            persistenceProcess.exitReceived = true
            persistenceProcess.maybeFinish()
        }
    }
}
