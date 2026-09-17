import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property string screensaver: "never"
    property string display: "never"
    property string suspend: "never"
    property string lockPoint: "none"
    property string effect: "colormix"
    property bool caffeine: false
    property int effectiveListeners: 0
    property bool ready: false
    property string errorMessage: ""
    property string pendingCaffeine: ""
    property var queuedAction: null

    readonly property bool busy: actionProcess.running || queuedAction !== null
    readonly property bool visualCaffeine: pendingCaffeine !== ""
        ? pendingCaffeine === "on" : caffeine
    readonly property string backendCommand: "vanhyprarch-idle"
    readonly property var timeoutPresets: ({
        screensaver: ["never", "120", "300", "600", "1200"],
        display: ["never", "300", "600", "1200", "1800"],
        suspend: ["never", "600", "1200", "1800", "3600"]
    })
    readonly property var lockPoints: ["none", "screensaver", "display", "suspend"]
    readonly property var effects: ["colormix", "matrix", "doom", "gameoflife"]

    Component.onCompleted: Qt.callLater(function() { root.refreshStatus(false) })

    function timeoutIsValid(value: string): bool {
        if (value === "never")
            return true
        if (!/^[1-9][0-9]*$/.test(value))
            return false

        const seconds = Number(value)
        if (!isFinite(seconds) || seconds > 2147483647)
            return false
        return true
    }

    function configurationIsValid(screenValue: string, displayValue: string,
        suspendValue: string, lockValue: string): bool {
        if (!root.timeoutIsValid(screenValue)
                || !root.timeoutIsValid(displayValue)
                || !root.timeoutIsValid(suspendValue)
                || root.lockPoints.indexOf(lockValue) < 0)
            return false

        if (lockValue === "screensaver" && screenValue === "never")
            return false
        if (lockValue === "display" && displayValue === "never")
            return false
        if (lockValue === "suspend" && suspendValue === "never")
            return false

        if (screenValue !== "never" && displayValue !== "never"
                && Number(screenValue) >= Number(displayValue))
            return false
        if (screenValue !== "never" && suspendValue !== "never"
                && Number(screenValue) >= Number(suspendValue))
            return false
        if (displayValue !== "never" && suspendValue !== "never"
                && Number(displayValue) >= Number(suspendValue))
            return false
        return true
    }

    function isKnownPreset(stage: string, value: string): bool {
        const presets = root.timeoutPresets[stage]
        return presets !== undefined && presets.indexOf(value) >= 0
    }

    function stageValue(stage: string): string {
        switch (stage) {
        case "screensaver": return root.screensaver
        case "display": return root.display
        case "suspend": return root.suspend
        default: return "never"
        }
    }

    function canSetStage(stage: string, value: string): bool {
        if (!root.ready || root.busy || !root.isKnownPreset(stage, value))
            return false

        let nextScreensaver = root.screensaver
        let nextDisplay = root.display
        let nextSuspend = root.suspend
        let nextLock = root.lockPoint
        switch (stage) {
        case "screensaver": nextScreensaver = value; break
        case "display": nextDisplay = value; break
        case "suspend": nextSuspend = value; break
        default: return false
        }
        if (value === "never" && nextLock === stage)
            nextLock = "none"
        return root.configurationIsValid(nextScreensaver, nextDisplay,
            nextSuspend, nextLock)
    }

    function canSetLock(lockValue: string): bool {
        if (!root.ready || root.busy || root.lockPoints.indexOf(lockValue) < 0)
            return false
        return root.configurationIsValid(root.screensaver, root.display,
            root.suspend, lockValue)
    }

    function requestStage(stage: string, value: string): void {
        if (!root.isKnownPreset(stage, value)) {
            root.errorMessage = "Rejected an unknown timeout preset."
            return
        }
        if (!root.canSetStage(stage, value)) {
            root.errorMessage = "That timeout would break the required stage order."
            return
        }

        let nextScreensaver = root.screensaver
        let nextDisplay = root.display
        let nextSuspend = root.suspend
        let nextLock = root.lockPoint
        switch (stage) {
        case "screensaver": nextScreensaver = value; break
        case "display": nextDisplay = value; break
        case "suspend": nextSuspend = value; break
        }

        if (value === "never" && nextLock === stage)
            nextLock = "none"
        root.startAction([
            root.backendCommand, "configure", nextScreensaver,
            nextDisplay, nextSuspend, nextLock
        ])
    }

    function requestLock(lockValue: string): void {
        if (root.lockPoints.indexOf(lockValue) < 0) {
            root.errorMessage = "Rejected an unknown automatic lock point."
            return
        }
        if (!root.canSetLock(lockValue)) {
            root.errorMessage = "Enable that stage before assigning automatic lock."
            return
        }
        if (lockValue === root.lockPoint)
            return

        root.startAction([
            root.backendCommand, "configure", root.screensaver,
            root.display, root.suspend, lockValue
        ])
    }

    function requestCaffeine(enabled: bool): void {
        if (!root.ready || root.busy)
            return

        const requested = enabled ? "on" : "off"
        if (requested === (root.caffeine ? "on" : "off"))
            return

        root.pendingCaffeine = requested
        root.startAction([root.backendCommand, "caffeine", requested])
    }

    function requestEffect(value: string): void {
        if (!root.ready || root.busy || root.effects.indexOf(value) < 0) {
            root.errorMessage = "Rejected an unknown screensaver effect."
            return
        }
        if (value === root.effect)
            return
        root.startAction([root.backendCommand, "set", "effect", value])
    }

    function startAction(command: var): void {
        if (root.busy)
            return

        root.errorMessage = ""
        if (statusProcess.running) {
            root.queuedAction = command
            return
        }
        actionProcess.startCommand(command)
    }

    function startQueuedAction(): void {
        if (root.queuedAction === null)
            return

        const command = root.queuedAction
        root.queuedAction = null
        root.errorMessage = ""
        actionProcess.startCommand(command)
    }

    function refreshStatus(preserveError: bool): void {
        if (root.busy || statusProcess.running)
            return
        if (!preserveError) {
            root.errorMessage = ""
        }
        statusProcess.preserveError = preserveError
        statusProcess.startRead()
    }

    function refreshAfterAction(): void {
        if (statusProcess.running)
            return
        statusProcess.preserveError = false
        statusProcess.startRead()
    }

    function parseStatus(output: string): var {
        const values = {}
        const expectedKeys = [
            "version", "screensaver", "display", "suspend",
            "lock", "effect", "caffeine", "effective_listeners"
        ]
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
            if (expectedKeys.indexOf(key) < 0 || values[key] !== undefined)
                throw new Error("unknown or duplicate status key")
            values[key] = value
        }
        for (const key of expectedKeys) {
            if (values[key] === undefined)
                throw new Error("missing status key")
        }
        if (values.version !== "2"
                || (values.caffeine !== "on" && values.caffeine !== "off")
                || root.effects.indexOf(values.effect) < 0
                || !/^[0-9]+$/.test(values.effective_listeners)
                || !root.configurationIsValid(values.screensaver,
                    values.display, values.suspend, values.lock))
            throw new Error("invalid backend status values")

        const expectedListeners = values.caffeine === "on" ? 0
            : (values.screensaver === "never" ? 0 : 1)
                + (values.display === "never" ? 0 : 1)
                + (values.suspend === "never" ? 0 : 1)
        if (Number(values.effective_listeners) !== expectedListeners)
            throw new Error("inconsistent listener count")

        return {
            screensaver: values.screensaver,
            display: values.display,
            suspend: values.suspend,
            lockPoint: values.lock,
            effect: values.effect,
            caffeine: values.caffeine === "on",
            effectiveListeners: expectedListeners
        }
    }

    function conciseError(output: string, fallback: string): string {
        const text = String(output || "").trim()
        if (text === "")
            return fallback
        const lines = text.split("\n")
        const message = String(lines[lines.length - 1]).trim()
        return message.length > 180 ? message.slice(0, 177) + "…" : message
    }

    Timer {
        interval: 30000
        repeat: true
        running: true
        onTriggered: root.refreshStatus(true)
    }

    Process {
        id: statusProcess

        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property bool resultHandled: false
        property bool preserveError: false
        property int lastExitCode: -1

        function startRead(): void {
            outputText = ""
            errorText = ""
            exitReceived = false
            stdoutReceived = false
            stderrReceived = false
            resultHandled = false
            lastExitCode = -1
            command = [root.backendCommand, "status"]
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stdoutReceived || !stderrReceived)
                return

            resultHandled = true
            if (root.queuedAction === null && !actionProcess.running)
                root.pendingCaffeine = ""
            if (lastExitCode !== 0) {
                root.errorMessage = root.conciseError(errorText,
                    "Could not read Power & Idle status.")
                Qt.callLater(root.startQueuedAction)
                return
            }

            try {
                const state = root.parseStatus(outputText)
                if (root.screensaver !== state.screensaver)
                    root.screensaver = state.screensaver
                if (root.display !== state.display)
                    root.display = state.display
                if (root.suspend !== state.suspend)
                    root.suspend = state.suspend
                if (root.lockPoint !== state.lockPoint)
                    root.lockPoint = state.lockPoint
                if (root.effect !== state.effect)
                    root.effect = state.effect
                if (root.caffeine !== state.caffeine)
                    root.caffeine = state.caffeine
                if (root.effectiveListeners !== state.effectiveListeners)
                    root.effectiveListeners = state.effectiveListeners
                if (!root.ready)
                    root.ready = true
                if (!preserveError)
                    root.errorMessage = ""
            } catch (error) {
                root.errorMessage = "Could not parse Power & Idle status."
                console.warn("Failed to parse vanhyprarch-idle status: " + error)
            }
            Qt.callLater(root.startQueuedAction)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                statusProcess.outputText = text
                statusProcess.stdoutReceived = true
                statusProcess.maybeFinish()
            }
        }

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                statusProcess.errorText = text
                statusProcess.stderrReceived = true
                statusProcess.maybeFinish()
            }
        }

        onExited: function(exitCode, exitStatus) {
            statusProcess.lastExitCode = exitCode
            statusProcess.exitReceived = true
            statusProcess.maybeFinish()
        }
    }

    Process {
        id: actionProcess

        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property bool resultHandled: false
        property int lastExitCode: -1

        function startCommand(nextCommand: var): void {
            outputText = ""
            errorText = ""
            exitReceived = false
            stdoutReceived = false
            stderrReceived = false
            resultHandled = false
            lastExitCode = -1
            command = nextCommand
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stdoutReceived || !stderrReceived)
                return

            resultHandled = true
            if (lastExitCode !== 0) {
                root.pendingCaffeine = ""
                root.errorMessage = root.conciseError(errorText,
                    "Power & Idle update failed.")
                Qt.callLater(function() { root.refreshStatus(true) })
                return
            }
            Qt.callLater(function() { root.refreshAfterAction() })
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                actionProcess.outputText = text
                actionProcess.stdoutReceived = true
                actionProcess.maybeFinish()
            }
        }

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                actionProcess.errorText = text
                actionProcess.stderrReceived = true
                actionProcess.maybeFinish()
            }
        }

        onExited: function(exitCode, exitStatus) {
            actionProcess.lastExitCode = exitCode
            actionProcess.exitReceived = true
            actionProcess.maybeFinish()
        }
    }
}
