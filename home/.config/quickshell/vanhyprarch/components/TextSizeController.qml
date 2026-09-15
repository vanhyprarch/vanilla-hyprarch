import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool persistenceAutostart: true
    readonly property int minimumSize: 9
    readonly property int maximumSize: 20
    readonly property int defaultSize: 12
    readonly property int stepSize: 1
    readonly property var values: {
        const result = []
        for (let size = root.minimumSize; size <= root.maximumSize;
                size += root.stepSize)
            result.push(size)
        return result
    }
    property int baseSize: defaultSize
    property bool explicitPreference: false
    property bool ready: false
    property string errorMessage: ""
    property bool footRestartRequired: false

    readonly property bool busy: persistenceProcess.running
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") !== ""
        ? Quickshell.env("XDG_CONFIG_HOME")
        : Quickshell.env("HOME") + "/.config"
    readonly property string preferenceHelper:
        Quickshell.shellDir + "/helpers/vanhyprarch_text_size"

    function validSize(value): bool {
        const numericValue = Number(value)
        return Number.isInteger(numericValue)
            && numericValue >= root.minimumSize
            && numericValue <= root.maximumSize
            && (numericValue - root.minimumSize) % root.stepSize === 0
    }

    function parseStatus(output: string): var {
        const values = {}
        const allowed = ["version", "size", "explicit", "gtk", "foot",
            "foot_restart"]
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
            if (allowed.indexOf(key) < 0 || values[key] !== undefined)
                throw new Error("unknown or duplicate status key")
            values[key] = value
        }

        const parsedSize = Number(values.size)
        if (values.version !== "1" || !Number.isInteger(parsedSize)
                || !root.validSize(parsedSize)
                || ["yes", "no"].indexOf(values.explicit) < 0
                || ["unchanged", "updated"].indexOf(values.gtk) < 0
                || ["unchanged", "updated", "unmanaged"].indexOf(values.foot) < 0
                || ["yes", "no", "required"].indexOf(values.foot_restart) < 0)
            throw new Error("invalid text-size status")

        return {
            size: parsedSize,
            explicitPreference: values.explicit === "yes",
            gtk: values.gtk,
            foot: values.foot,
            footRestartRequired: values.foot_restart === "required"
        }
    }

    function requestSize(size): bool {
        if (!root.validSize(size) || root.busy)
            return false
        root.errorMessage = ""
        persistenceProcess.startOperation("set", String(size))
        return true
    }

    function refresh(): void {
        if (!root.busy)
            persistenceProcess.startOperation("status", "")
    }

    function finishOperation(operation: string, exitCode: int,
            output: string): void {
        root.ready = true
        if (exitCode !== 0) {
            root.errorMessage = operation === "set"
                ? "Text size was not changed; check GTK, Foot, and preference-file access"
                : "Could not load the text-size preference; check preference-file access"
            return
        }

        let status
        try {
            status = root.parseStatus(output)
        } catch (error) {
            root.errorMessage = "Invalid text-size preference status"
            return
        }

        root.baseSize = status.size
        root.explicitPreference = status.explicitPreference
        root.footRestartRequired = status.footRestartRequired
        root.errorMessage = ""
    }

    Component.onCompleted: {
        if (root.persistenceAutostart)
            root.refresh()
    }

    Process {
        id: persistenceProcess

        property string operation: ""
        property string requested: ""
        property string output: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property int lastExitCode: -1

        function startOperation(nextOperation: string, nextValue: string): void {
            if (running)
                return
            operation = nextOperation
            requested = nextValue
            output = ""
            exitReceived = false
            stdoutReceived = false
            lastExitCode = -1
            command = nextOperation === "set"
                ? ["/bin/sh", root.preferenceHelper, "set", nextValue]
                : ["/bin/sh", root.preferenceHelper, "status"]
            running = true
        }

        function maybeFinish(): void {
            if (operation === "" || !exitReceived || !stdoutReceived)
                return
            const completedOperation = operation
            const completedExitCode = lastExitCode
            const completedOutput = output
            operation = ""
            requested = ""
            root.finishOperation(completedOperation, completedExitCode,
                completedOutput)
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

    FileView {
        path: root.configHome + "/vanhyprarch/text-size.conf"
        watchChanges: true
        printErrors: false
        onFileChanged: Qt.callLater(root.refresh)
    }
}
