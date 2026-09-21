import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    property bool checksEnabled: true
    property bool executionEnabled: true
    property var outputs: []
    property bool ready: false
    property bool statusReady: false
    property string errorMessage: ""
    property bool refreshPending: false
    property bool resetPendingOnNextInspect: false
    property var pendingByConnector: ({})
    property int pendingRevision: 0
    property string transactionId: ""
    property string transactionState: "idle"
    property int transactionSequence: -1
    property string transactionPolicy: ""
    property string transactionConnector: ""
    property var transactionCandidate: null
    property real backendRemainingSeconds: 0
    property real presentationRemainingSeconds: 0
    property double remainingSampleMs: 0
    property var registeredSurfaces: ({})
    property int surfaceRevision: 0
    property var lastRequestedCommand: []
    property string lastRequestedKind: ""

    readonly property string backendCommand: "vanhyprarch-monitor"
    readonly property bool operationBusy: actionProcess.active
    readonly property bool refreshing: inspectProcess.active || statusProcess.active
    readonly property bool confirmationActive:
        transactionState === "temporary-active" && transactionId !== ""
    readonly property bool transactionInFlight: ["preparing", "applying",
        "temporary-active", "committing", "reverting", "rollback-failed"].indexOf(
        transactionState) >= 0
    readonly property bool mutationsBlocked: operationBusy || refreshing
        || transactionInFlight || (checksEnabled && !statusReady)
    readonly property string confirmationScreenName: {
        root.surfaceRevision
        const names = Object.keys(root.registeredSurfaces).sort()
        for (const name of names) {
            if (root.registeredSurfaces[name] === root.transactionConnector)
                return name
        }
        return names.length > 0 ? names[0] : ""
    }

    Component.onCompleted: if (checksEnabled) {
        Qt.callLater(function() {
            root.refreshInspect(false)
            root.refreshStatus()
        })
    }

    function conciseError(output: string, fallback: string): string {
        const value = String(output || "").trim()
        if (value === "")
            return fallback
        const lines = value.split("\n")
        const message = String(lines[lines.length - 1]).trim()
        return message.length > 180 ? message.slice(0, 177) + "…" : message
    }

    function outputFor(connector: string): var {
        for (const output of root.outputs) {
            if (output.connector === connector)
                return output
        }
        return null
    }

    function registerSurface(screenName: string, connector: string): void {
        if (screenName === "")
            return
        const copy = Object.assign({}, root.registeredSurfaces)
        copy[screenName] = connector
        root.registeredSurfaces = copy
        root.surfaceRevision++
    }

    function unregisterSurface(screenName: string): void {
        if (root.registeredSurfaces[screenName] === undefined)
            return
        const copy = Object.assign({}, root.registeredSurfaces)
        delete copy[screenName]
        root.registeredSurfaces = copy
        root.surfaceRevision++
    }

    function validateMode(value: var): var {
        if (value === null || typeof value !== "object"
                || !Number.isInteger(value.width) || value.width <= 0
                || !Number.isInteger(value.height) || value.height <= 0
                || !Number.isInteger(value.refresh_millihz)
                || value.refresh_millihz <= 0)
            throw new Error("invalid normalized Mode")
        return {
            width: value.width,
            height: value.height,
            refresh_millihz: value.refresh_millihz
        }
    }

    function parseInspection(output: string): var {
        const value = JSON.parse(String(output || ""))
        if (value === null || typeof value !== "object" || value.version !== 1
                || typeof value.instance_signature !== "string"
                || !Array.isArray(value.outputs))
            throw new Error("invalid monitor inspection schema")
        const seen = ({})
        const normalized = []
        for (const item of value.outputs) {
            if (item === null || typeof item !== "object"
                    || typeof item.connector !== "string" || item.connector === ""
                    || typeof item.label !== "string"
                    || item.identity === null || typeof item.identity !== "object"
                    || typeof item.identity.make !== "string"
                    || typeof item.identity.model !== "string"
                    || typeof item.identity.serial !== "string"
                    || typeof item.active !== "boolean"
                    || typeof item.editable !== "boolean"
                    || (item.unavailable_reason !== null
                        && typeof item.unavailable_reason !== "string")
                    || !Array.isArray(item.available_modes)
                    || !Number.isInteger(item.scale_millionths)
                    || item.scale_millionths <= 0
                    || (item.effective_bitdepth !== null
                        && [8, 10].indexOf(item.effective_bitdepth) < 0)
                    || !Array.isArray(item.bitdepth_choices)
                    || item.effective === null || typeof item.effective !== "object"
                    || typeof item.effective.current_format !== "string"
                    || typeof item.effective.color_management_preset !== "string"
                    || seen[item.connector])
                throw new Error("invalid monitor inspection output")
            const currentMode = item.current_mode === null ? null
                : root.validateMode(item.current_mode)
            if (item.editable && currentMode === null)
                throw new Error("editable output omitted its current Mode")
            seen[item.connector] = true
            const modes = []
            const modeSeen = ({})
            for (const rawMode of item.available_modes) {
                const mode = root.validateMode(rawMode)
                const key = mode.width + "x" + mode.height + "@"
                    + mode.refresh_millihz
                if (modeSeen[key])
                    throw new Error("duplicate canonical Mode")
                modeSeen[key] = true
                modes.push(mode)
            }
            const choices = item.bitdepth_choices.slice()
            if (choices.some(choice => [8, 10].indexOf(choice) < 0))
                throw new Error("invalid bitdepth choice")
            normalized.push({
                connector: item.connector,
                label: item.label,
                identity: item.identity,
                active: item.active,
                editable: item.editable,
                unavailable_reason: item.unavailable_reason,
                current_mode: currentMode,
                available_modes: modes,
                scale_millionths: item.scale_millionths,
                effective_bitdepth: item.effective_bitdepth,
                bitdepth_choices: choices,
                effective: item.effective
            })
        }
        return normalized
    }

    function acceptInspectionJson(output: string, preserveError: bool): bool {
        try {
            const parsed = root.parseInspection(output)
            const previous = root.resetPendingOnNextInspect
                ? ({}) : root.pendingByConnector
            const preserved = ({})
            for (const item of parsed) {
                const pending = previous[item.connector]
                if (pending === undefined || item.current_mode === null
                        || !item.editable)
                    continue
                const modeValid = item.available_modes.some(mode =>
                    mode.width === pending.width
                    && mode.height === pending.height
                    && mode.refresh_millihz === pending.refresh_millihz)
                const bitdepthValid = pending.bitdepth === item.effective_bitdepth
                    || item.bitdepth_choices.indexOf(pending.bitdepth) >= 0
                if (modeValid && bitdepthValid)
                    preserved[item.connector] = Object.assign({}, pending)
            }
            root.outputs = parsed
            root.pendingByConnector = preserved
            root.pendingRevision++
            root.resetPendingOnNextInspect = false
            root.ready = true
            if (!preserveError)
                root.errorMessage = ""
            for (const item of root.outputs)
                root.ensurePending(item.connector)
            return true
        } catch (error) {
            root.outputs = []
            root.ready = false
            root.errorMessage = "Could not read display capabilities."
            console.warn("Failed to parse monitor inspection: " + error)
            return false
        }
    }

    function ensurePending(connector: string): var {
        root.pendingRevision
        let pending = root.pendingByConnector[connector]
        if (pending !== undefined)
            return pending
        const current = root.outputFor(connector)
        if (current === null || current.current_mode === null)
            return null
        pending = {
            width: current.current_mode.width,
            height: current.current_mode.height,
            refresh_millihz: current.current_mode.refresh_millihz,
            bitdepth: current.effective_bitdepth
        }
        const copy = Object.assign({}, root.pendingByConnector)
        copy[connector] = pending
        root.pendingByConnector = copy
        root.pendingRevision++
        return pending
    }

    function resetPending(connector: string): void {
        const copy = Object.assign({}, root.pendingByConnector)
        delete copy[connector]
        root.pendingByConnector = copy
        root.pendingRevision++
        root.ensurePending(connector)
    }

    function resetAllPending(): void {
        root.pendingByConnector = ({})
        root.pendingRevision++
        for (const item of root.outputs)
            root.ensurePending(item.connector)
    }

    function resolutionOptions(connector: string): var {
        const output = root.outputFor(connector)
        if (output === null)
            return []
        const result = []
        const seen = ({})
        for (const mode of output.available_modes) {
            const key = mode.width + "x" + mode.height
            if (!seen[key]) {
                seen[key] = true
                result.push({ width: mode.width, height: mode.height })
            }
        }
        return result
    }

    function refreshOptions(connector: string, width: int, height: int): var {
        const output = root.outputFor(connector)
        if (output === null)
            return []
        return output.available_modes.filter(mode =>
            mode.width === width && mode.height === height).map(mode =>
                mode.refresh_millihz)
    }

    function setPendingResolution(connector: string, width: int, height: int): bool {
        const pending = root.ensurePending(connector)
        const output = root.outputFor(connector)
        const refreshes = root.refreshOptions(connector, width, height)
        if (pending === null || output === null || refreshes.length === 0)
            return false
        let refresh = pending.refresh_millihz
        if (refreshes.indexOf(refresh) < 0)
            refresh = refreshes.indexOf(output.current_mode.refresh_millihz) >= 0
                ? output.current_mode.refresh_millihz
                : refreshes[refreshes.length - 1]
        const copy = Object.assign({}, root.pendingByConnector)
        copy[connector] = Object.assign({}, pending, {
            width: width, height: height, refresh_millihz: refresh
        })
        root.pendingByConnector = copy
        root.pendingRevision++
        return true
    }

    function setPendingRefresh(connector: string, refresh: int): bool {
        const pending = root.ensurePending(connector)
        if (pending === null || root.refreshOptions(connector,
                pending.width, pending.height).indexOf(refresh) < 0)
            return false
        const copy = Object.assign({}, root.pendingByConnector)
        copy[connector] = Object.assign({}, pending, { refresh_millihz: refresh })
        root.pendingByConnector = copy
        root.pendingRevision++
        return true
    }

    function setPendingBitdepth(connector: string, bitdepth: int): bool {
        const pending = root.ensurePending(connector)
        const output = root.outputFor(connector)
        if (pending === null || output === null
                || output.bitdepth_choices.indexOf(bitdepth) < 0)
            return false
        const copy = Object.assign({}, root.pendingByConnector)
        copy[connector] = Object.assign({}, pending, { bitdepth: bitdepth })
        root.pendingByConnector = copy
        root.pendingRevision++
        return true
    }

    function cycleResolution(connector: string, delta: int): void {
        const options = root.resolutionOptions(connector)
        const pending = root.ensurePending(connector)
        if (pending === null || options.length === 0)
            return
        let index = options.findIndex(option => option.width === pending.width
            && option.height === pending.height)
        index = (Math.max(0, index) + delta + options.length) % options.length
        root.setPendingResolution(connector, options[index].width, options[index].height)
    }

    function cycleRefresh(connector: string, delta: int): void {
        const pending = root.ensurePending(connector)
        if (pending === null)
            return
        const options = root.refreshOptions(connector, pending.width, pending.height)
        if (options.length === 0)
            return
        let index = options.indexOf(pending.refresh_millihz)
        index = (Math.max(0, index) + delta + options.length) % options.length
        root.setPendingRefresh(connector, options[index])
    }

    function cycleBitdepth(connector: string, delta: int): void {
        const output = root.outputFor(connector)
        const pending = root.ensurePending(connector)
        if (output === null || pending === null || output.bitdepth_choices.length === 0)
            return
        let index = output.bitdepth_choices.indexOf(pending.bitdepth)
        index = (Math.max(0, index) + delta + output.bitdepth_choices.length)
            % output.bitdepth_choices.length
        root.setPendingBitdepth(connector, output.bitdepth_choices[index])
    }

    function hasSafeChanges(connector: string): bool {
        root.pendingRevision
        const output = root.outputFor(connector)
        const pending = root.ensurePending(connector)
        return output !== null && pending !== null && (
            pending.width !== output.current_mode.width
            || pending.height !== output.current_mode.height
            || pending.refresh_millihz !== output.current_mode.refresh_millihz
            || pending.bitdepth !== output.effective_bitdepth)
    }

    function startAction(command: var, kind: string): bool {
        if (root.mutationsBlocked)
            return false
        root.errorMessage = ""
        root.lastRequestedCommand = command.slice()
        root.lastRequestedKind = kind
        if (!root.executionEnabled)
            return true
        actionProcess.startCommand(command, kind)
        return true
    }

    function requestSafeApply(connector: string): bool {
        const output = root.outputFor(connector)
        const pending = root.ensurePending(connector)
        if (output === null || pending === null || !output.editable
                || !root.hasSafeChanges(connector))
            return false
        const command = [root.backendCommand, "apply", "--connector", connector]
        if (pending.width !== output.current_mode.width
                || pending.height !== output.current_mode.height
                || pending.refresh_millihz !== output.current_mode.refresh_millihz) {
            command.push("--width", String(pending.width), "--height",
                String(pending.height), "--refresh",
                root.refreshArgument(pending.refresh_millihz))
        }
        if (pending.bitdepth !== output.effective_bitdepth)
            command.push("--bitdepth", String(pending.bitdepth))
        return root.startAction(command, "safe-apply")
    }

    function requestScale(connector: string, scaleText: string): bool {
        const output = root.outputFor(connector)
        if (output === null || !output.editable)
            return false
        return root.startAction([root.backendCommand, "scale", "--connector",
            connector, "--scale", scaleText], "scale")
    }

    function requestConfirm(): bool {
        if (!root.confirmationActive || root.operationBusy)
            return false
        return root.startTerminalAction("confirm")
    }

    function requestRevert(): bool {
        if (!root.confirmationActive || root.operationBusy)
            return false
        return root.startTerminalAction("revert")
    }

    function startTerminalAction(action: string): bool {
        const command = [root.backendCommand, action, root.transactionId]
        root.lastRequestedCommand = command.slice()
        root.lastRequestedKind = action
        if (!root.executionEnabled)
            return true
        root.errorMessage = ""
        actionProcess.startCommand(command, action)
        return true
    }

    function refreshArgument(millihz: int): string {
        const whole = Math.floor(millihz / 1000)
        const fraction = String(millihz % 1000).padStart(3, "0").replace(/0+$/, "")
        return fraction === "" ? String(whole) : whole + "." + fraction
    }

    function parseControlResponse(output: string): var {
        const value = JSON.parse(String(output || ""))
        if (value === null || typeof value !== "object" || value.version !== 2
                || typeof value.ok !== "boolean")
            throw new Error("invalid monitor control response")
        if (!value.ok)
            throw new Error(typeof value.error === "string" ? value.error
                : "monitor backend rejected the request")
        if (value.status === null || typeof value.status !== "object")
            throw new Error("monitor response omitted status")
        return value.status
    }

    function validateStatusCandidate(value: var, policy: string): var {
        if (value === null || typeof value !== "object"
                || typeof value.connector !== "string" || value.connector === ""
                || (value.bitdepth !== null
                    && [8, 10].indexOf(value.bitdepth) < 0)
                || (value.scale_millionths !== null
                    && (!Number.isInteger(value.scale_millionths)
                        || value.scale_millionths <= 0)))
            throw new Error("invalid transaction candidate")
        const mode = value.mode === null ? null : root.validateMode(value.mode)
        if (policy === "safe-confirmed") {
            if (value.scale_millionths !== null
                    || (mode === null && value.bitdepth === null))
                throw new Error("invalid Safe Apply candidate")
        } else if (mode !== null || value.bitdepth !== null
                || value.scale_millionths === null) {
            throw new Error("invalid immediate Scale candidate")
        }
        return {
            connector: value.connector,
            mode: mode,
            bitdepth: value.bitdepth,
            scale_millionths: value.scale_millionths
        }
    }

    function applyStatus(status: var, allowReplacement: bool): void {
        if (status.state === "idle") {
            if (!allowReplacement && root.transactionId !== ""
                    && ["preparing", "applying", "temporary-active", "committing",
                        "reverting"].indexOf(root.transactionState) >= 0)
                return
            root.transactionId = ""
            root.transactionState = "idle"
            root.transactionSequence = -1
            root.transactionPolicy = ""
            root.transactionConnector = ""
            root.transactionCandidate = null
            root.backendRemainingSeconds = 0
            root.presentationRemainingSeconds = 0
            return
        }
        const states = ["preparing", "applying", "temporary-active", "committing",
            "reverting", "committed", "reverted", "rollback-failed",
            "instance-vanished"]
        if (typeof status.transaction_id !== "string"
                || states.indexOf(status.state) < 0
                || (status.policy !== "safe-confirmed"
                    && status.policy !== "immediate-scale")
                || !Number.isInteger(status.sequence)
                || status.candidate === null || typeof status.candidate !== "object"
                || typeof status.candidate.connector !== "string"
                || (status.failure !== null && typeof status.failure !== "string")
                || typeof status.recovery_required !== "boolean")
            throw new Error("invalid transaction status")
        if (!allowReplacement && root.transactionId !== ""
                && status.transaction_id !== root.transactionId
                && ["preparing", "applying", "temporary-active", "committing",
                    "reverting"].indexOf(root.transactionState) >= 0)
            return
        if (status.transaction_id === root.transactionId
                && status.sequence < root.transactionSequence)
            return
        const candidate = root.validateStatusCandidate(status.candidate, status.policy)
        root.transactionId = status.transaction_id
        root.transactionState = status.state
        root.transactionSequence = status.sequence
        root.transactionPolicy = status.policy
        root.transactionConnector = candidate.connector
        root.transactionCandidate = candidate
        const remaining = Number(status.remaining_seconds)
        root.backendRemainingSeconds = isFinite(remaining) && remaining > 0
            ? remaining : 0
        root.presentationRemainingSeconds = root.backendRemainingSeconds
        root.remainingSampleMs = Date.now()
        if (status.state === "rollback-failed"
                || status.state === "instance-vanished") {
            root.errorMessage = status.failure || "Display recovery needs attention."
        } else if (status.state === "reverted" && status.failure !== null
                && status.failure !== "manual revert"
                && status.failure !== "confirmation deadline expired") {
            root.errorMessage = "Display settings were reverted: " + status.failure
        } else if (status.state === "committed") {
            root.errorMessage = ""
        }
        if (["committed", "reverted", "instance-vanished"].indexOf(
                status.state) >= 0) {
            if (status.policy === "safe-confirmed")
                root.resetPendingOnNextInspect = true
            root.refreshInspect(true)
            Hyprland.refreshMonitors()
        }
    }

    function acceptStatusJson(output: string, allowReplacement: bool): bool {
        try {
            root.applyStatus(root.parseControlResponse(output), allowReplacement || false)
            root.statusReady = true
            return true
        } catch (error) {
            root.statusReady = false
            root.errorMessage = "Could not reconcile the display transaction."
            console.warn("Failed to parse monitor status: " + error)
            return false
        }
    }

    function confirmationDescription(): string {
        const candidate = root.transactionCandidate
        if (candidate === null)
            return "Display settings"
        const parts = []
        if (candidate.mode !== null) {
            parts.push(candidate.mode.width + "×" + candidate.mode.height
                + " · " + root.refreshArgument(candidate.mode.refresh_millihz) + " Hz")
        }
        if (candidate.bitdepth !== null)
            parts.push(candidate.bitdepth + "-bit color")
        return parts.join(" · ")
    }

    function refreshInspect(preserveError: bool): void {
        if (!root.checksEnabled)
            return
        if (inspectProcess.active || actionProcess.active) {
            root.refreshPending = true
            return
        }
        if (!preserveError)
            root.errorMessage = ""
        root.refreshPending = false
        inspectProcess.startRead(preserveError)
    }

    function refreshStatus(): void {
        if (!root.checksEnabled || statusProcess.active)
            return
        statusProcess.startRead()
    }

    function actionFinished(): void {
        root.refreshStatus()
        root.refreshInspect(true)
        Hyprland.refreshMonitors()
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.transactionInFlight && root.checksEnabled
        onTriggered: root.refreshStatus()
    }

    Timer {
        interval: 250
        repeat: true
        running: root.confirmationActive
        onTriggered: {
            const elapsed = Math.max(0, (Date.now() - root.remainingSampleMs) / 1000)
            root.presentationRemainingSeconds = Math.max(0,
                root.backendRemainingSeconds - elapsed)
        }
    }

    Process {
        id: inspectProcess
        property bool active: false
        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property int lastExitCode: -1
        property bool preserveError: false
        function startRead(keepError: bool): void {
            active = true; outputText = ""; errorText = ""; exitReceived = false
            stdoutReceived = false; stderrReceived = false; lastExitCode = -1
            preserveError = keepError
            command = [root.backendCommand, "inspect"]; running = true
        }
        function finish(): void {
            if (!active || !exitReceived || !stdoutReceived || !stderrReceived)
                return
            active = false
            if (lastExitCode !== 0) {
                root.outputs = []; root.ready = false
                root.errorMessage = root.conciseError(errorText,
                    "Display settings backend is unavailable.")
            } else {
                root.acceptInspectionJson(outputText, preserveError)
            }
            if (root.refreshPending)
                Qt.callLater(function() { root.refreshInspect(true) })
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            inspectProcess.outputText = text; inspectProcess.stdoutReceived = true
            inspectProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            inspectProcess.errorText = text; inspectProcess.stderrReceived = true
            inspectProcess.finish()
        }}
        onExited: function(exitCode) {
            inspectProcess.lastExitCode = exitCode; inspectProcess.exitReceived = true
            inspectProcess.finish()
        }
    }

    Process {
        id: statusProcess
        property bool active: false
        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property int lastExitCode: -1
        function startRead(): void {
            active = true; outputText = ""; errorText = ""; exitReceived = false
            stdoutReceived = false; stderrReceived = false; lastExitCode = -1
            command = [root.backendCommand, "status"]; running = true
        }
        function finish(): void {
            if (!active || !exitReceived || !stdoutReceived || !stderrReceived)
                return
            active = false
            if (lastExitCode !== 0) {
                root.statusReady = false
                root.errorMessage = root.conciseError(errorText,
                    "Could not reconcile the display transaction.")
            } else {
                root.acceptStatusJson(outputText, false)
            }
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            statusProcess.outputText = text; statusProcess.stdoutReceived = true
            statusProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            statusProcess.errorText = text; statusProcess.stderrReceived = true
            statusProcess.finish()
        }}
        onExited: function(exitCode) {
            statusProcess.lastExitCode = exitCode; statusProcess.exitReceived = true
            statusProcess.finish()
        }
    }

    Process {
        id: actionProcess
        property bool active: false
        property string kind: ""
        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property int lastExitCode: -1
        function startCommand(nextCommand: var, nextKind: string): void {
            active = true; kind = nextKind; outputText = ""; errorText = ""
            exitReceived = false; stdoutReceived = false; stderrReceived = false
            lastExitCode = -1; command = nextCommand; running = true
        }
        function finish(): void {
            if (!active || !exitReceived || !stdoutReceived || !stderrReceived)
                return
            active = false
            if (lastExitCode !== 0 || !root.acceptStatusJson(outputText, true))
                root.errorMessage = root.conciseError(errorText,
                    "Display update failed.")
            root.actionFinished()
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            actionProcess.outputText = text; actionProcess.stdoutReceived = true
            actionProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            actionProcess.errorText = text; actionProcess.stderrReceived = true
            actionProcess.finish()
        }}
        onExited: function(exitCode) {
            actionProcess.lastExitCode = exitCode; actionProcess.exitReceived = true
            actionProcess.finish()
        }
    }
}
