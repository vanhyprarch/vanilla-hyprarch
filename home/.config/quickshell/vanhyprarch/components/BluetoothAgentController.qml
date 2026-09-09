import QtQuick
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    readonly property int protocolVersion: 1
    property string state: "starting"
    property string errorMessage: ""
    property var currentPrompt: null
    property bool promptResponsePending: false
    property bool displayAcknowledged: false
    property bool displayCancellationPending: false
    property bool displayInitialPairStateKnown: false
    property bool displayDeviceInitiallyPaired: false
    property bool displayForgetPending: false
    property string promptScreenName: ""
    property var openPanelScreenNames: []
    property string lastActiveScreenName: ""
    property string pairIntentPath: ""
    property string pairIntentScreenName: ""
    property int pairIntentGeneration: -1
    property string pairIntentId: ""
    property bool pairIntentSawPairing: false
    property bool pairIntentWaitingForTrust: false
    property string actionError: ""
    property int agentSessionGeneration: 0
    property int pairIntentSequence: 0
    property bool sessionInvalidating: false
    property bool agentAutostart: true

    readonly property bool ready: state === "ready"
    readonly property bool promptActive: currentPrompt !== null
    readonly property bool displayPrompt: promptActive
        && (currentPrompt.kind === "displayPinCode"
            || currentPrompt.kind === "displayPasskey")
    readonly property var pairIntentDevice: deviceForPath(pairIntentPath)
    readonly property var promptDevice: promptActive
        ? deviceForPath(currentPrompt.devicePath) : null
    readonly property string agentScript:
        Quickshell.shellDir + "/helpers/vanhyprarch_bluetooth_agent.py"

    signal promptRaised()

    function devices(): var {
        return Bluetooth.devices ? Bluetooth.devices.values : []
    }

    function deviceForPath(path): var {
        const target = String(path || "")
        if (target === "")
            return null
        const deviceObjects = root.devices()
        for (const device of deviceObjects) {
            if (device && String(device.dbusPath || "") === target)
                return device
        }
        return null
    }

    function screenExists(name): bool {
        const target = String(name || "")
        for (const screen of Quickshell.screens) {
            if (screen && screen.name === target)
                return true
        }
        return false
    }

    function appropriateScreenName(excludedScreenName): string {
        const excluded = String(excludedScreenName || "")
        for (let index = root.openPanelScreenNames.length - 1; index >= 0; --index) {
            const openScreen = root.openPanelScreenNames[index]
            if (openScreen !== excluded && root.screenExists(openScreen))
                return openScreen
        }
        const focusedMonitor = Hyprland.focusedMonitor
        if (focusedMonitor && focusedMonitor.name !== excluded
                && root.screenExists(focusedMonitor.name))
            return focusedMonitor.name
        if (root.lastActiveScreenName !== excluded
                && root.screenExists(root.lastActiveScreenName))
            return root.lastActiveScreenName
        for (const screen of Quickshell.screens) {
            if (screen && screen.name !== excluded)
                return screen.name
        }
        return ""
    }

    function notePanelOpened(screenName: string): void {
        if (!root.screenExists(screenName))
            return
        const remaining = root.openPanelScreenNames.filter(name => name !== screenName)
        root.openPanelScreenNames = remaining.concat([screenName])
        root.lastActiveScreenName = screenName
    }

    function notePanelClosed(screenName: string): void {
        root.openPanelScreenNames = root.openPanelScreenNames.filter(
            name => name !== screenName)
        if (!root.promptActive || root.promptScreenName !== screenName)
            return

        if (root.displayPrompt) {
            root.cancelDisplayedPairing()
        } else {
            root.rejectPrompt()
        }
        if (!root.promptActive)
            return
        const replacementScreen = root.appropriateScreenName()
        if (replacementScreen === "") {
            root.invalidateAgentSession("Pairing prompt has no available screen", true)
            return
        }
        root.promptScreenName = replacementScreen
        root.promptRaised()
    }

    function notePanelDestroyed(screenName: string): void {
        root.openPanelScreenNames = root.openPanelScreenNames.filter(
            name => name !== screenName)
        if (!root.promptActive || root.promptScreenName !== screenName)
            return
        if (root.displayPrompt)
            root.cancelDisplayedPairing()
        else
            root.rejectPrompt()
        if (!root.promptActive)
            return
        const replacementScreen = root.appropriateScreenName(screenName)
        if (replacementScreen === "") {
            root.invalidateAgentSession("Pairing prompt has no available screen", true)
            return
        }
        root.promptScreenName = replacementScreen
        root.promptRaised()
    }

    function validRequestId(value): bool {
        return typeof value === "string" && value.length > 0 && value.length <= 128
    }

    function validDevicePath(value): bool {
        return typeof value === "string"
            && /^\/org\/bluez\/hci[0-9]+\/dev_(?:[0-9A-F]{2}_){5}[0-9A-F]{2}$/.test(value)
    }

    function deviceAddressFromPath(value): string {
        if (!root.validDevicePath(value))
            return ""
        const marker = "/dev_"
        const index = value.lastIndexOf(marker)
        return index >= 0 ? value.slice(index + marker.length).replace(/_/g, ":") : ""
    }

    function deviceIdentityForPath(value): string {
        if (!root.validDevicePath(value))
            return ""
        const device = root.deviceForPath(value)
        if (device) {
            const labels = [device.name, device.deviceName, device.address]
            for (const labelValue of labels) {
                const label = String(labelValue || "").trim()
                if (label !== "")
                    return label
            }
        }
        return root.deviceAddressFromPath(value)
    }

    function normalizeServiceUuid(value): string {
        if (typeof value !== "string")
            return ""
        if (/^[0-9A-Fa-f]{4}$/.test(value))
            return "0000" + value.toLowerCase() + "-0000-1000-8000-00805f9b34fb"
        if (/^[0-9A-Fa-f]{8}$/.test(value))
            return value.toLowerCase() + "-0000-1000-8000-00805f9b34fb"
        if (/^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$/.test(value))
            return value.toLowerCase()
        return ""
    }

    function validPasskey(value): bool {
        return typeof value === "number" && isFinite(value)
            && Math.floor(value) === value && value >= 0 && value <= 999999
    }

    function validatePrompt(message): bool {
        const requestKinds = [
            "requestPinCode", "requestPasskey", "requestConfirmation",
            "requestAuthorization", "authorizeService"
        ]
        const displayKinds = ["displayPinCode", "displayPasskey"]
        const expectedKinds = message.event === "request" ? requestKinds : displayKinds
        if (!root.validRequestId(message.id)
                || expectedKinds.indexOf(message.kind) < 0
                || !root.validDevicePath(message.devicePath))
            return false
        if ((message.kind === "requestConfirmation"
                || message.kind === "displayPasskey")
                && !root.validPasskey(message.passkey))
            return false
        if (message.kind === "displayPasskey"
                && (!root.validPasskey(message.entered) || message.entered > 6))
            return false
        if (message.kind === "displayPinCode"
                && (typeof message.pin !== "string"
                    || !/^[A-Za-z0-9]{1,16}$/.test(message.pin)))
            return false
        if (message.kind === "authorizeService"
                && (root.normalizeServiceUuid(message.uuid) === ""
                    || root.normalizeServiceUuid(message.uuid) !== message.uuid))
            return false
        return true
    }

    function sendMessage(message): bool {
        if (!agentProcess.running)
            return false
        try {
            agentProcess.write(JSON.stringify(message) + "\n")
            return true
        } catch (error) {
            return false
        }
    }

    function invalidateAgentSession(message: string, terminate: bool): void {
        if (root.sessionInvalidating)
            return
        root.sessionInvalidating = true
        root.state = "error"
        root.errorMessage = message
        const pairingDevice = root.pairIntentDevice
        if (pairingDevice && pairingDevice.pairing)
            pairingDevice.cancelPair()
        root.clearPairIntent("Pairing agent session ended")
        if (root.promptActive)
            root.clearPrompt(root.currentPrompt.id)
        if (terminate && agentProcess.running)
            agentProcess.signal(15)
    }

    function sendEventDecision(requestId: string, decision: string): bool {
        const sent = root.sendMessage({
            version: root.protocolVersion,
            id: requestId,
            decision: decision
        })
        if (!sent)
            root.invalidateAgentSession("Pairing agent communication failed", true)
        return sent
    }

    function sendDecision(decision: string, value): bool {
        if (!root.promptActive || root.displayPrompt || root.promptResponsePending)
            return false
        const message = {
            version: root.protocolVersion,
            id: root.currentPrompt.id,
            decision: decision
        }
        if (value !== undefined)
            message.value = value
        if (root.sendMessage(message)) {
            root.promptResponsePending = true
            return true
        } else {
            root.invalidateAgentSession("Pairing agent communication failed", true)
            return false
        }
    }

    function submitPrompt(value: string): void {
        if (!root.promptActive)
            return
        const kind = root.currentPrompt.kind
        if (kind === "requestPinCode") {
            if (!/^[A-Za-z0-9]{1,16}$/.test(value))
                return
        } else if (kind === "requestPasskey") {
            if (!/^[0-9]{1,6}$/.test(value))
                return
        } else {
            return
        }
        root.sendDecision("submit", value)
    }

    function acceptPrompt(): void {
        if (!root.promptActive)
            return
        const kind = root.currentPrompt.kind
        if (kind !== "requestConfirmation"
                && kind !== "requestAuthorization"
                && kind !== "authorizeService")
            return
        root.sendDecision("accept", undefined)
    }

    function rejectPrompt(): void {
        if (!root.promptActive || root.displayPrompt)
            return
        const promptPath = root.currentPrompt.devicePath
        if (root.sendDecision("reject", undefined)
                && root.pairIntentPath === promptPath)
            root.clearPairIntent("Pairing canceled")
    }

    function cancelDisplayedPairing(): void {
        if (!root.promptActive || !root.displayPrompt)
            return
        const promptPath = root.currentPrompt.devicePath
        if (root.pairIntentPath === promptPath)
            root.clearPairIntent("Pairing canceled")
        if (!root.displayAcknowledged) {
            if (root.sendEventDecision(root.currentPrompt.id, "reject"))
                root.promptResponsePending = true
            return
        }
        const device = root.promptDevice
        if (!device || !device.pairing) {
            root.invalidateAgentSession(
                "Pairing cancellation could not be confirmed", true)
            return
        }
        root.displayCancellationPending = true
        displayCancelTimeout.restart()
        device.cancelPair()
        root.promptRaised()
    }

    function acknowledgeDisplayedPrompt(screenName: string, requestId: string): void {
        if (!root.promptActive || !root.displayPrompt || root.displayAcknowledged
                || root.promptResponsePending || root.promptScreenName !== screenName
                || root.currentPrompt.id !== requestId || !root.screenExists(screenName)
                || root.deviceIdentityForPath(root.currentPrompt.devicePath) === "")
            return
        if (root.sendEventDecision(requestId, "displayed"))
            root.displayAcknowledged = true
    }

    function confirmDisplayedPairingCanceled(): void {
        if (!root.promptActive || !root.displayPrompt
                || !root.displayCancellationPending)
            return
        const device = root.promptDevice
        if (!device || device.pairing)
            return
        if (device.paired || device.bonded) {
            if (!root.displayInitialPairStateKnown
                    || root.displayDeviceInitiallyPaired) {
                root.invalidateAgentSession(
                    "Pairing cancellation could not be confirmed", true)
                return
            }
            if (!root.displayForgetPending) {
                root.displayForgetPending = true
                device.forget()
            }
            return
        }
        if (root.sendEventDecision(root.currentPrompt.id, "cancel"))
            root.promptResponsePending = true
    }

    function clearPrompt(requestId): void {
        if (!root.promptActive || root.currentPrompt.id !== requestId)
            return
        root.currentPrompt = null
        root.promptResponsePending = false
        root.displayAcknowledged = false
        root.displayCancellationPending = false
        root.displayInitialPairStateKnown = false
        root.displayDeviceInitiallyPaired = false
        root.displayForgetPending = false
        root.promptScreenName = ""
        displayCancelTimeout.stop()
    }

    function failAgentProtocol(message: string): void {
        root.invalidateAgentSession(message, true)
    }

    function handleAgentLine(line: string): void {
        let message = null
        try {
            message = JSON.parse(line)
        } catch (error) {
            console.warn("Rejected malformed Bluetooth agent output")
            root.failAgentProtocol("Pairing agent sent malformed data")
            return
        }
        if (!message || message.version !== root.protocolVersion
                || typeof message.event !== "string") {
            root.failAgentProtocol("Pairing agent protocol mismatch")
            return
        }

        if (message.event === "status") {
            if (message.state === "ready") {
                if (root.state !== "starting") {
                    root.failAgentProtocol("Pairing agent sent unexpected readiness")
                    return
                }
                root.state = "ready"
                root.errorMessage = ""
            } else if (message.state === "error") {
                root.invalidateAgentSession(typeof message.message === "string"
                    ? message.message : "Pairing agent unavailable", true)
            } else {
                root.failAgentProtocol("Pairing agent sent an invalid status")
            }
            return
        }
        if (message.event === "complete" || message.event === "cancel") {
            if (!root.validRequestId(message.id)) {
                root.failAgentProtocol("Pairing agent sent an invalid completion")
                return
            }
            if (message.event === "complete"
                    && ["accepted", "rejected", "canceled"].indexOf(
                        message.outcome) < 0) {
                root.failAgentProtocol("Pairing agent sent an invalid outcome")
                return
            }
            if (message.event === "cancel" && typeof message.reason !== "string") {
                root.failAgentProtocol("Pairing agent sent an invalid cancellation")
                return
            }
            if (!root.promptActive || root.currentPrompt.id !== message.id) {
                root.failAgentProtocol("Pairing agent sent an unexpected completion")
                return
            }
            const promptPath = root.currentPrompt.devicePath
            const pairingFailed = message.event === "complete"
                    ? message.outcome !== "accepted"
                    : (message.reason !== "updated" && message.reason !== "replaced")
            root.clearPrompt(message.id)
            if (pairingFailed && root.pairIntentPath === promptPath) {
                const device = root.pairIntentDevice
                if (device && device.pairing)
                    device.cancelPair()
                root.clearPairIntent("Pairing did not complete")
            }
            return
        }
        if ((message.event !== "request" && message.event !== "display")
                || !root.validatePrompt(message)) {
            if (message && message.event === "request"
                    && root.validRequestId(message.id)) {
                root.sendEventDecision(message.id, "reject")
            }
            root.failAgentProtocol("Pairing agent sent an invalid request")
            return
        }
        if (root.promptActive) {
            root.failAgentProtocol("Pairing agent sent a concurrent request")
            return
        }

        if (root.deviceIdentityForPath(message.devicePath) === "") {
            if (!root.sendEventDecision(message.id, "reject"))
                return
            if (message.event === "display")
                root.invalidateAgentSession("Pairing device could not be identified", true)
            return
        }

        const outgoingScreen = message.devicePath === root.pairIntentPath
            && root.screenExists(root.pairIntentScreenName)
            ? root.pairIntentScreenName : ""
        const screenName = outgoingScreen !== ""
            ? outgoingScreen : root.appropriateScreenName()
        if (screenName === "") {
            root.sendEventDecision(message.id, "reject")
            return
        }
        root.promptScreenName = screenName
        root.promptResponsePending = false
        root.displayAcknowledged = false
        root.displayCancellationPending = false
        const displayDevice = message.event === "display"
            ? root.deviceForPath(message.devicePath) : null
        root.displayInitialPairStateKnown = displayDevice !== null
        root.displayDeviceInitiallyPaired = Boolean(displayDevice
            && (displayDevice.paired || displayDevice.bonded))
        root.displayForgetPending = false
        root.currentPrompt = message
        root.promptRaised()
    }

    function pairDevice(device, screenName: string): void {
        if (!device || !root.ready || device.paired || device.bonded || device.pairing)
            return
        if (root.pairIntentPath !== "") {
            root.actionError = "Another Bluetooth pairing is already in progress"
            return
        }
        const path = String(device.dbusPath || "")
        if (!root.validDevicePath(path) || !root.screenExists(screenName))
            return
        root.actionError = ""
        root.pairIntentSequence += 1
        root.pairIntentPath = path
        root.pairIntentScreenName = screenName
        root.pairIntentGeneration = root.agentSessionGeneration
        root.pairIntentId = String(root.agentSessionGeneration)
            + ":" + String(root.pairIntentSequence)
        root.pairIntentSawPairing = Boolean(device.pairing)
        pairIntentTimeout.restart()
        device.pair()
    }

    function cancelPair(device): void {
        if (!device)
            return
        const path = String(device.dbusPath || "")
        if (device.pairing)
            device.cancelPair()
        if (root.promptActive && root.currentPrompt.devicePath === path
                && !root.displayPrompt)
            root.rejectPrompt()
        if (root.pairIntentPath === path)
            root.clearPairIntent("")
    }

    function evaluatePairIntent(expectedId, expectedGeneration): void {
        if (root.pairIntentPath === "" || root.pairIntentId === "")
            return
        if (expectedId !== undefined && (root.pairIntentId !== expectedId
                || root.pairIntentGeneration !== expectedGeneration))
            return
        const device = root.pairIntentDevice
        if (root.pairIntentGeneration !== root.agentSessionGeneration || !root.ready) {
            if (device && device.pairing)
                device.cancelPair()
            root.clearPairIntent("Pairing agent session changed")
            return
        }
        if (!device) {
            root.clearPairIntent("Pairing device is no longer available")
            return
        }
        if (device.pairing) {
            root.pairIntentSawPairing = true
            return
        }
        if (device.paired || device.bonded) {
            if (!root.pairIntentSawPairing) {
                root.clearPairIntent("Pairing transaction could not be verified")
                return
            }
            if (!device.trusted) {
                root.pairIntentWaitingForTrust = true
                device.trusted = true
                return
            }
            root.pairIntentWaitingForTrust = false
            if (!device.connected && device.state !== BluetoothDeviceState.Connecting)
                device.connect()
            root.clearPairIntent("")
            return
        }
        if (root.pairIntentSawPairing)
            root.clearPairIntent("Pairing did not complete")
    }

    function schedulePairIntentEvaluation(): void {
        const transactionId = root.pairIntentId
        const generation = root.pairIntentGeneration
        Qt.callLater(function() {
            root.evaluatePairIntent(transactionId, generation)
        })
    }

    function clearPairIntent(message: string): void {
        pairIntentTimeout.stop()
        root.pairIntentPath = ""
        root.pairIntentScreenName = ""
        root.pairIntentGeneration = -1
        root.pairIntentId = ""
        root.pairIntentSawPairing = false
        root.pairIntentWaitingForTrust = false
        root.actionError = message
    }

    Component.onCompleted: {
        if (root.agentAutostart)
            agentProcess.running = true
    }

    Component.onDestruction: {
        const device = root.pairIntentDevice
        if (device && device.pairing)
            device.cancelPair()
        root.clearPairIntent("")
        if (agentProcess.running)
            agentProcess.signal(15)
    }

    Connections {
        target: root.pairIntentDevice
        ignoreUnknownSignals: true

        function onPairingChanged(): void {
            if (root.pairIntentDevice && root.pairIntentDevice.pairing)
                root.pairIntentSawPairing = true
            root.schedulePairIntentEvaluation()
        }

        function onPairedChanged(): void {
            root.schedulePairIntentEvaluation()
        }

        function onBondedChanged(): void {
            root.schedulePairIntentEvaluation()
        }

        function onTrustedChanged(): void {
            root.schedulePairIntentEvaluation()
        }
    }

    Connections {
        target: root.promptDevice
        ignoreUnknownSignals: true

        function onPairingChanged(): void {
            Qt.callLater(root.confirmDisplayedPairingCanceled)
        }

        function onPairedChanged(): void {
            Qt.callLater(root.confirmDisplayedPairingCanceled)
        }

        function onBondedChanged(): void {
            Qt.callLater(root.confirmDisplayedPairingCanceled)
        }
    }

    Timer {
        id: pairIntentTimeout

        interval: 120000
        repeat: false
        onTriggered: {
            const device = root.pairIntentDevice
            if (device && device.pairing)
                device.cancelPair()
            root.clearPairIntent(device && (device.paired || device.bonded)
                ? "Paired, but could not trust device" : "Pairing timed out")
        }
    }

    Timer {
        id: displayCancelTimeout

        interval: 5000
        repeat: false
        onTriggered: root.invalidateAgentSession(
            "Pairing cancellation timed out", true)
    }

    Timer {
        id: restartTimer

        interval: 5000
        repeat: false
        onTriggered: {
            if (root.agentAutostart && !agentProcess.running) {
                root.state = "starting"
                root.errorMessage = ""
                agentProcess.running = true
            }
        }
    }

    Process {
        id: agentProcess

        command: ["/usr/bin/python", root.agentScript]
        stdinEnabled: true

        stdout: SplitParser {
            splitMarker: "\n"
            onRead: data => root.handleAgentLine(data)
        }

        stderr: SplitParser {
            splitMarker: "\n"
            onRead: data => {
                const message = String(data || "").trim()
                if (message !== "")
                    console.warn("Bluetooth pairing agent: " + message)
            }
        }

        onStarted: {
            root.agentSessionGeneration += 1
            root.sessionInvalidating = false
            root.state = "starting"
            root.errorMessage = ""
        }

        onExited: {
            const device = root.pairIntentDevice
            if (device && device.pairing)
                device.cancelPair()
            root.clearPairIntent("Pairing agent session ended")
            root.state = "error"
            root.errorMessage = "Pairing agent unavailable"
            if (root.promptActive)
                root.clearPrompt(root.currentPrompt.id)
            root.sessionInvalidating = false
            if (root.agentAutostart)
                restartTimer.restart()
        }
    }
}
