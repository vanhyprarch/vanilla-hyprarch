pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

DockPopup {
    id: root

    required property var theme
    required property var textSizeController
    required property var monitorController
    property color textColor: root.theme.text
    property int textSizePreviewIndex: -1
    property bool brightnessAvailable: false
    property int brightnessPercent: 0
    property int confirmedBrightnessPercent: 0
    property int brightnessRawCurrent: 0
    property int brightnessRawMaximum: 0
    property bool brightnessWritePending: false
    property int pendingBrightnessPercent: 0
    property string cachedDdcConnector: ""
    property string cachedDdcBus: ""
    property bool componentReady: false
    property bool startupWarmupPending: true
    property int brightnessWriteRetriesRemaining: 0
    readonly property var scalePresets: ["1.00", "1.25", "1.50", "2.00"]
    readonly property bool monitorControllerReady: root.monitorController !== null
        && root.monitorController !== undefined
    readonly property var monitor: Hyprland.monitorFor(root.targetScreen)
    readonly property string connectorName: monitor ? String(monitor.name || "") : ""
    readonly property var inspectedOutput:
        root.monitorControllerReady
            ? root.monitorController.outputFor(root.connectorName) : null
    readonly property var pendingState:
        root.monitorControllerReady
            ? root.monitorController.pendingFor(root.connectorName) : null
    readonly property string monitorDescription: {
        if (root.inspectedOutput !== null)
            return root.inspectedOutput.label
        return root.monitor ? String(root.monitor.description || "").trim()
            : "No display"
    }
    readonly property bool displayEditable: root.inspectedOutput !== null
        && (root.inspectedOutput.editable || root.inspectedOutput.materializable)
        && root.monitorControllerReady
        && !root.monitorController.mutationsBlocked
    readonly property bool scaleControlsEditable: root.displayEditable
        && !root.monitorController.resolutionChangePending(root.connectorName)

    Component.onCompleted: {
        root.componentReady = true
        root.startStartupWarmup()
    }

    onConnectorNameChanged: {
        brightnessDebounce.stop()
        root.brightnessWritePending = false
        root.cachedDdcConnector = ""
        root.cachedDdcBus = ""
        root.setBrightnessUnavailable()
        if (ddcProcess.completionPending) {
            ddcProcess.cancelled = true
            if (ddcProcess.running)
                ddcProcess.running = false
        }
        if (!ddcProcess.running && !ddcProcess.completionPending) {
            if (root.visible)
                root.refreshBrightness(false)
            else
                root.startStartupWarmup()
        }
    }

    onVisibleChanged: {
        if (visible) {
            root.refreshBrightness(false)
            if (root.monitorControllerReady) {
                root.monitorController.refreshInspect(false)
                root.monitorController.refreshStatus()
            }
        } else {
            brightnessDebounce.stop()
            root.brightnessWritePending = false
            root.brightnessWriteRetriesRemaining = 0
            if (ddcProcess.completionPending && ddcProcess.phase === "write") {
                ddcProcess.cancelled = true
                if (ddcProcess.running)
                    ddcProcess.running = false
            }
        }
    }

    function setBrightnessUnavailable() {
        root.brightnessAvailable = false
        root.brightnessPercent = 0
        root.confirmedBrightnessPercent = 0
        root.brightnessRawCurrent = 0
        root.brightnessRawMaximum = 0
        root.brightnessWriteRetriesRemaining = 0
    }

    function connectorMatches(candidate: string, connector: string): bool {
        if (candidate === "" || connector === "")
            return false
        return candidate === connector || candidate.endsWith("-" + connector)
    }

    function parseDdcBus(output: string, connector: string): string {
        const lines = String(output || "").split("\n")
        let inDisplayBlock = false
        let blockBus = ""
        let blockConnector = ""

        for (const rawLine of lines) {
            const line = String(rawLine)
            if (/^\s*Display\s+\d+/i.test(line)) {
                inDisplayBlock = true
                blockBus = ""
                blockConnector = ""
                continue
            }
            if (!inDisplayBlock)
                continue

            const busMatch = line.match(/^\s*I2C bus:\s*\/dev\/i2c-([0-9]+)\b/i)
            if (busMatch)
                blockBus = busMatch[1]

            const connectorMatch = line.match(/^\s*DRM[_ ]connector:\s*(\S+)/i)
            if (connectorMatch)
                blockConnector = connectorMatch[1]

            if (blockBus !== "" && root.connectorMatches(blockConnector, connector))
                return blockBus
        }

        return ""
    }

    function parseBrightness(output: string): var {
        const match = String(output || "").match(
            /current value\s*=\s*([0-9]+)\s*,\s*max value\s*=\s*([0-9]+)/i)
        if (!match)
            return null

        const current = Number(match[1])
        const maximum = Number(match[2])
        if (!isFinite(current) || !isFinite(maximum) || current < 0 || maximum <= 0)
            return null

        if (current > maximum)
            return null

        return {
            current: current,
            maximum: maximum,
            percent: Math.max(1, Math.min(100, Math.round(current * 100 / maximum)))
        }
    }

    function clampBrightness(value: real): int {
        return Math.max(1, Math.min(100, Math.round(value)))
    }

    function previewBrightness(value: real) {
        if (!root.visible || !root.brightnessAvailable)
            return

        const percent = root.clampBrightness(value)
        brightnessDebounce.stop()
        root.brightnessPercent = percent
        root.pendingBrightnessPercent = percent
        root.brightnessWritePending = true
        root.brightnessWriteRetriesRemaining = 1
    }

    function debouncePendingBrightness() {
        if (root.visible && root.brightnessWritePending && !sliderMouse.pressed)
            brightnessDebounce.restart()
    }

    function processPendingBrightness() {
        if (!root.visible || sliderMouse.pressed || !root.brightnessWritePending)
            return
        if (ddcProcess.running || ddcProcess.completionPending)
            return
        if (root.cachedDdcConnector !== root.connectorName
                || !/^\d+$/.test(root.cachedDdcBus)
                || root.brightnessRawMaximum <= 0) {
            root.brightnessWritePending = false
            root.setBrightnessUnavailable()
            return
        }

        const percent = root.clampBrightness(root.pendingBrightnessPercent)
        root.brightnessWritePending = false
        root.startBrightnessWrite(percent, root.cachedDdcBus, root.connectorName)
    }

    function startStartupWarmup() {
        if (!root.componentReady || !root.startupWarmupPending
                || root.connectorName === "")
            return

        root.startupWarmupPending = false
        if (ddcProcess.running || ddcProcess.completionPending)
            return
        root.refreshBrightness(true)
    }

    function refreshBrightness(allowHidden: bool) {
        if (root.connectorName === "") {
            if (root.visible)
                root.setBrightnessUnavailable()
            return
        }
        if (!root.visible && !allowHidden)
            return

        if (ddcProcess.running || ddcProcess.completionPending)
            return

        if (root.cachedDdcConnector === root.connectorName && root.cachedDdcBus !== "") {
            root.startBrightnessRead(root.cachedDdcBus, root.connectorName, allowHidden)
            return
        }

        ddcProcess.phase = "detect"
        ddcProcess.queryConnector = root.connectorName
        ddcProcess.requestedPercent = 0
        ddcProcess.requestedRawValue = 0
        ddcProcess.resetCompletion()
        ddcProcess.command = ["ddcutil", "detect"]
        ddcProcess.running = true
    }

    function startBrightnessRead(bus: string, connector: string, allowHidden: bool) {
        if ((!root.visible && !allowHidden) || connector !== root.connectorName
                || ddcProcess.running || ddcProcess.completionPending)
            return

        ddcProcess.phase = "read"
        ddcProcess.queryConnector = connector
        ddcProcess.requestedPercent = 0
        ddcProcess.requestedRawValue = 0
        ddcProcess.resetCompletion()
        ddcProcess.command = ["ddcutil", "getvcp", "10", "--bus", bus]
        ddcProcess.running = true
    }

    function startBrightnessWrite(percent: int, bus: string, connector: string) {
        if (!root.visible || sliderMouse.pressed || connector !== root.connectorName
                || ddcProcess.running || ddcProcess.completionPending)
            return

        const maximum = root.brightnessRawMaximum
        if (maximum <= 0)
            return

        const rawValue = Math.max(0, Math.min(maximum,
            Math.round(root.clampBrightness(percent) * maximum / 100)))
        ddcProcess.phase = "write"
        ddcProcess.queryConnector = connector
        ddcProcess.requestedPercent = root.clampBrightness(percent)
        ddcProcess.requestedRawValue = rawValue
        ddcProcess.resetCompletion()
        ddcProcess.command = ["ddcutil", "setvcp", "10", String(rawValue),
            "--bus", bus]
        ddcProcess.running = true
    }

    function handleDdcResult(phase: string, connector: string, exitCode: int,
        output: string, requestedPercent: int, requestedRawValue: int) {
        if (!root.visible && phase === "write")
            return
        if (connector !== root.connectorName) {
            if (root.visible)
                Qt.callLater(function() { root.refreshBrightness(false) })
            return
        }

        if (phase === "write") {
            if (exitCode !== 0) {
                const bus = root.cachedDdcBus
                brightnessDebounce.stop()
                if (!root.brightnessWritePending
                        && root.brightnessWriteRetriesRemaining > 0) {
                    root.pendingBrightnessPercent = requestedPercent
                    root.brightnessWritePending = true
                    root.brightnessWriteRetriesRemaining = 0
                }
                if (/^\d+$/.test(bus)) {
                    Qt.callLater(function() { root.startBrightnessRead(bus, connector, true) })
                } else {
                    root.cachedDdcConnector = ""
                    root.cachedDdcBus = ""
                    Qt.callLater(function() { root.refreshBrightness(true) })
                }
                return
            }

            root.brightnessRawCurrent = requestedRawValue
            root.confirmedBrightnessPercent = requestedPercent
            root.brightnessAvailable = true
            if (!root.brightnessWritePending)
                root.brightnessWriteRetriesRemaining = 0
            if (!root.brightnessWritePending)
                root.brightnessPercent = requestedPercent
            root.debouncePendingBrightness()
            return
        }

        if (exitCode !== 0) {
            if (phase === "read") {
                root.cachedDdcConnector = ""
                root.cachedDdcBus = ""
                root.brightnessWritePending = false
            }
            root.setBrightnessUnavailable()
            return
        }

        if (phase === "detect") {
            const bus = root.parseDdcBus(output, connector)
            if (bus === "") {
                root.setBrightnessUnavailable()
                return
            }

            root.cachedDdcConnector = connector
            root.cachedDdcBus = bus
            Qt.callLater(function() { root.startBrightnessRead(bus, connector, true) })
            return
        }

        const reading = root.parseBrightness(output)
        if (reading === null) {
            root.cachedDdcConnector = ""
            root.cachedDdcBus = ""
            root.brightnessWritePending = false
            root.setBrightnessUnavailable()
            return
        }

        root.brightnessRawCurrent = reading.current
        root.brightnessRawMaximum = reading.maximum
        root.confirmedBrightnessPercent = reading.percent
        if (!root.visible || !sliderMouse.pressed) {
            root.brightnessPercent = root.brightnessWritePending
                ? root.pendingBrightnessPercent : reading.percent
        }
        root.brightnessAvailable = true
        root.debouncePendingBrightness()
    }

    function formatNumber(value: real, decimals: int): string {
        if (!isFinite(value))
            return "—"
        return String(Number(value.toFixed(decimals)))
    }

    function monitorSubtitle(): string {
        if (!root.monitor)
            return root.monitorDescription
        return root.connectorName !== ""
            ? root.monitorDescription + " · " + root.connectorName
            : root.monitorDescription
    }

    function scaleTextFor(output: var): string {
        if (output === null || output === undefined)
            return "—"
        const scale = output.scale_millionths / 1000000
        return isFinite(scale) && scale > 0 ? root.formatNumber(scale, 6) + "×" : "—"
    }

    function scaleText(): string {
        return root.scaleTextFor(root.inspectedOutput)
    }

    function scaleMatchesOutput(output: var, preset: real): bool {
        if (output === null || output === undefined || output.scale_automatic)
            return false
        const currentScale = output.scale_millionths / 1000000
        return isFinite(currentScale) && Math.abs(currentScale - preset) < 0.01
    }

    function scaleMatches(preset: real): bool {
        return root.scaleMatchesOutput(root.pendingState, preset)
    }

    function requestScalePreset(preset: string) {
        if (root.scalePresets.indexOf(preset) === -1) {
            console.warn("Rejected invalid monitor scale preset: " + preset)
            return
        }
        if (root.connectorName === "") {
            console.warn("Monitor scale update requires a screen-mapped output profile")
            return
        }
        if (!root.scaleControlsEditable || root.scaleMatches(Number(preset)))
            return
        if (root.monitorControllerReady)
            root.monitorController.requestScale(root.connectorName, preset)
    }

    function pendingResolutionText(): string {
        if (root.monitorControllerReady)
            root.monitorController.pendingRevision
        return root.pendingState === null ? "—"
            : root.pendingState.width + " × " + root.pendingState.height
    }

    function pendingRefreshText(): string {
        if (root.monitorControllerReady)
            root.monitorController.pendingRevision
        return root.pendingState === null ? "—"
            : root.formatNumber(root.pendingState.refresh_millihz / 1000, 2) + " Hz"
    }

    function pendingBitdepthText(): string {
        if (root.monitorControllerReady)
            root.monitorController.pendingRevision
        return root.pendingState === null || root.pendingState.bitdepth === null
            ? "Unavailable" : root.pendingState.bitdepth + "-bit"
    }

    function pendingHdrText(): string {
        if (root.monitorControllerReady)
            root.monitorController.pendingRevision
        if (root.pendingState === null)
            return "Unavailable"
        return root.pendingState.hdr_mode === "always-on" ? "On" : "Off"
    }

    function pendingAutomaticHdrText(): string {
        if (!root.monitorControllerReady)
            return "Unavailable"
        root.monitorController.pendingRevision
        const labels = ["Off", "On", "On (EDID)"]
        const value = root.monitorController.pendingAutomaticHdr
        return labels[value] === undefined ? "Unavailable" : labels[value]
    }

    function nearestTextSizeIndex(size: int): int {
        let bestIndex = 0
        let bestDistance = Number.MAX_VALUE
        for (let index = 0; index < root.textSizeController.values.length; index++) {
            const distance = Math.abs(root.textSizeController.values[index] - size)
            if (distance < bestDistance) {
                bestDistance = distance
                bestIndex = index
            }
        }
        return bestIndex
    }

    function currentTextSizeIndex(): int {
        return root.textSizePreviewIndex >= 0
            ? root.textSizePreviewIndex
            : root.nearestTextSizeIndex(root.textSizeController.baseSize)
    }

    function displayedTextSize(): int {
        return root.textSizePreviewIndex >= 0
            ? root.textSizeController.values[root.textSizePreviewIndex]
            : root.textSizeController.baseSize
    }

    function previewTextSize(position: real, width: real): void {
        if (width <= 0 || root.textSizeController.busy)
            return
        const lastIndex = root.textSizeController.values.length - 1
        root.textSizePreviewIndex = Math.max(0, Math.min(lastIndex,
            Math.round(Math.max(0, Math.min(width, position)) / width * lastIndex)))
    }

    function applyTextSizePreview(): void {
        if (root.textSizePreviewIndex < 0)
            return
        const requested = root.textSizeController.values[root.textSizePreviewIndex]
        if (!root.textSizeController.requestSize(requested))
            root.textSizePreviewIndex = -1
    }

    implicitHeight: content.implicitHeight + root.metrics.panelPadding * 2

    component InfoRow: Item {
        required property string label
        required property string value

        width: content.width
        height: root.metrics.compactRowHeight

        Text {
            anchors {
                left: parent.left
                verticalCenter: parent.verticalCenter
            }
            text: parent.label
            color: root.textColor
            font.pixelSize: root.metrics.informationLabelFontSize
            font.weight: root.metrics.informationLabelFontWeight
        }

        Text {
            anchors {
                right: parent.right
                verticalCenter: parent.verticalCenter
            }
            text: parent.value
            color: root.theme.textMuted
            font.pixelSize: root.metrics.informationValueFontSize
            font.weight: root.metrics.informationValueFontWeight
        }
    }

    component ChoiceRow: Item {
        required property string label
        required property string value
        property string detailLabel: ""
        property bool interactive: true
        property bool changed: false
        signal previousRequested()
        signal nextRequested()

        width: content.width
        height: root.metrics.compactControlHeight
        opacity: interactive ? 1 : root.metrics.disabledInteractiveOpacity

        Column {
            anchors {
                left: parent.left
                verticalCenter: parent.verticalCenter
            }
            width: parent.width * 0.34

            Text {
                text: parent.parent.label
                color: root.textColor
                font.pixelSize: root.metrics.informationLabelFontSize
                font.weight: root.metrics.informationLabelFontWeight
            }

            Text {
                visible: text !== ""
                text: parent.parent.detailLabel
                color: root.theme.textMuted
                font.pixelSize: root.metrics.captionFontSize
            }
        }

        Rectangle {
            id: previousButton
            anchors {
                right: choiceValue.left
                rightMargin: root.metrics.rowSpacing
                verticalCenter: parent.verticalCenter
            }
            width: height
            height: parent.height
            radius: root.metrics.rowRadius
            color: previousMouse.containsMouse ? root.theme.hoverFill
                : root.theme.normalFill
            Text { anchors.centerIn: parent; text: "‹"; color: root.textColor }
            MouseArea {
                id: previousMouse
                anchors.fill: parent
                enabled: parent.parent.interactive
                hoverEnabled: true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: parent.parent.previousRequested()
            }
        }

        Text {
            id: choiceValue
            anchors {
                right: nextButton.left
                rightMargin: root.metrics.rowSpacing
                verticalCenter: parent.verticalCenter
            }
            width: parent.width * 0.34
            text: parent.value
            color: parent.changed ? root.theme.control : root.theme.textMuted
            font.pixelSize: root.metrics.informationValueFontSize
            font.weight: parent.changed ? Font.DemiBold
                : root.metrics.informationValueFontWeight
            horizontalAlignment: Text.AlignHCenter
        }

        Rectangle {
            id: nextButton
            anchors {
                right: parent.right
                verticalCenter: parent.verticalCenter
            }
            width: height
            height: parent.height
            radius: root.metrics.rowRadius
            color: nextMouse.containsMouse ? root.theme.hoverFill
                : root.theme.normalFill
            Text { anchors.centerIn: parent; text: "›"; color: root.textColor }
            MouseArea {
                id: nextMouse
                anchors.fill: parent
                enabled: parent.parent.interactive
                hoverEnabled: true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: parent.parent.nextRequested()
            }
        }
    }

    Timer {
        id: brightnessDebounce

        interval: 500
        repeat: false
        onTriggered: root.processPendingBrightness()
    }

    Process {
        id: ddcProcess

        property string phase: ""
        property string queryConnector: ""
        property string outputText: ""
        property int requestedPercent: 0
        property int requestedRawValue: 0
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool resultHandled: true
        property bool completionPending: false
        property bool cancelled: false
        property int lastExitCode: -1

        function resetCompletion() {
            ddcProcess.exitReceived = false
            ddcProcess.stdoutReceived = false
            ddcProcess.resultHandled = false
            ddcProcess.completionPending = true
            ddcProcess.cancelled = false
            ddcProcess.lastExitCode = -1
            ddcProcess.outputText = ""
        }

        function maybeFinish() {
            if (ddcProcess.resultHandled || !ddcProcess.exitReceived
                    || !ddcProcess.stdoutReceived)
                return

            ddcProcess.resultHandled = true
            ddcProcess.completionPending = false
            if (ddcProcess.cancelled) {
                if (root.visible)
                    Qt.callLater(function() { root.refreshBrightness(false) })
                return
            }
            root.handleDdcResult(ddcProcess.phase, ddcProcess.queryConnector,
                ddcProcess.lastExitCode, ddcProcess.outputText,
                ddcProcess.requestedPercent, ddcProcess.requestedRawValue)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                ddcProcess.outputText = text
                ddcProcess.stdoutReceived = true
                ddcProcess.maybeFinish()
            }
        }

        onExited: function(exitCode, exitStatus) {
            ddcProcess.lastExitCode = exitCode
            ddcProcess.exitReceived = true
            ddcProcess.maybeFinish()
        }
    }

    Connections {
        target: root.textSizeController

        function onBusyChanged(): void {
            if (!root.textSizeController.busy)
                root.textSizePreviewIndex = -1
        }

        function onBaseSizeChanged(): void {
            root.textSizePreviewIndex = -1
        }

        function onErrorMessageChanged(): void {
            if (root.textSizeController.errorMessage !== "")
                root.textSizePreviewIndex = -1
        }
    }

    PanelSurface {
        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme

        Column {
            id: content

            width: parent.width
            spacing: root.metrics.sectionGap

            Text {
                width: parent.width
                text: "Display"
                color: root.textColor
                font.pixelSize: root.metrics.panelTitleFontSize
                font.weight: root.metrics.panelTitleFontWeight
                wrapMode: Text.NoWrap
            }

            Text {
                width: parent.width
                text: root.monitorSubtitle()
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
            }

            ChoiceRow {
                label: "Resolution"
                value: root.pendingResolutionText()
                interactive: root.displayEditable
                    && root.monitorControllerReady
                    && root.monitorController.resolutionOptions(
                        root.connectorName).length > 1
                changed: root.pendingState !== null
                    && root.inspectedOutput !== null
                    && (root.pendingState.width
                        !== root.inspectedOutput.current_mode.width
                        || root.pendingState.height
                        !== root.inspectedOutput.current_mode.height)
                onPreviousRequested:
                    root.monitorController.cycleResolution(root.connectorName, -1)
                onNextRequested:
                    root.monitorController.cycleResolution(root.connectorName, 1)
            }

            ChoiceRow {
                label: "Refresh rate"
                value: root.pendingRefreshText()
                interactive: root.displayEditable && root.monitorControllerReady
                    && root.pendingState !== null
                    && root.monitorController.refreshOptions(root.connectorName,
                        root.pendingState.width, root.pendingState.height).length > 1
                changed: root.pendingState !== null
                    && root.inspectedOutput !== null
                    && root.pendingState.refresh_millihz
                        !== root.inspectedOutput.current_mode.refresh_millihz
                onPreviousRequested:
                    root.monitorController.cycleRefresh(root.connectorName, -1)
                onNextRequested:
                    root.monitorController.cycleRefresh(root.connectorName, 1)
            }

            ChoiceRow {
                label: "Color depth"
                value: root.pendingBitdepthText()
                interactive: root.displayEditable
                    && root.inspectedOutput !== null
                    && root.inspectedOutput.bitdepth_choices.length > 1
                changed: root.pendingState !== null
                    && root.inspectedOutput !== null
                    && root.pendingState.bitdepth
                        !== root.inspectedOutput.effective_bitdepth
                onPreviousRequested:
                    root.monitorController.cycleBitdepth(root.connectorName, -1)
                onNextRequested:
                    root.monitorController.cycleBitdepth(root.connectorName, 1)
            }

            ChoiceRow {
                label: "Forced HDR"
                value: root.pendingHdrText()
                interactive: root.displayEditable
                    && root.inspectedOutput !== null
                    && root.inspectedOutput.hdr.available
                changed: root.pendingState !== null
                    && root.inspectedOutput !== null
                    && root.pendingState.hdr_mode !== root.inspectedOutput.hdr.mode
                onPreviousRequested:
                    root.monitorController.cycleHdr(root.connectorName, -1)
                onNextRequested:
                    root.monitorController.cycleHdr(root.connectorName, 1)
            }

            ChoiceRow {
                label: "Automatic HDR"
                detailLabel: "All displays"
                value: root.pendingAutomaticHdrText()
                interactive: root.displayEditable
                    && root.monitorControllerReady
                    && root.monitorController.automaticHdrAvailable
                changed: root.monitorControllerReady
                    && root.monitorController.pendingAutomaticHdr
                        !== root.monitorController.automaticHdrValue
                onPreviousRequested:
                    root.monitorController.cycleAutomaticHdr(-1)
                onNextRequested:
                    root.monitorController.cycleAutomaticHdr(1)
            }

            Rectangle {
                width: parent.width
                height: root.metrics.compactControlHeight
                radius: root.metrics.rowRadius
                color: applyMouse.pressed ? root.theme.pressedFill
                    : applyMouse.containsMouse ? root.theme.hoverFill
                        : root.theme.activeFill
                opacity: applyMouse.enabled ? 1
                    : root.metrics.disabledInteractiveOpacity

                Text {
                    anchors.centerIn: parent
                    text: root.monitorControllerReady
                        && root.monitorController.operationBusy
                        ? "Applying…" : "Apply display changes"
                    color: root.textColor
                    font.pixelSize: root.metrics.bodyFontSize
                    font.weight: Font.DemiBold
                }

                MouseArea {
                    id: applyMouse
                    anchors.fill: parent
                    enabled: root.displayEditable
                        && root.monitorControllerReady
                        && root.monitorController.hasSafeChanges(root.connectorName)
                        && root.monitorController.validationMessage(
                            root.connectorName) === ""
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: root.monitorController.requestSafeApply(
                        root.connectorName)
                }
            }

            Text {
                visible: (root.monitorControllerReady
                        && root.monitorController.errorMessage !== "")
                    || (root.monitorControllerReady
                        && root.monitorController.validationMessage(
                            root.connectorName) !== "")
                    || (root.displayEditable
                        && root.inspectedOutput !== null
                        && !root.inspectedOutput.hdr.available)
                    || (root.displayEditable
                        && root.monitorControllerReady
                        && !root.monitorController.automaticHdrAvailable)
                    || (root.inspectedOutput !== null
                        && !root.inspectedOutput.editable
                        && !root.inspectedOutput.materializable)
                width: parent.width
                text: root.monitorControllerReady
                    && root.monitorController.errorMessage !== ""
                    ? root.monitorController.errorMessage
                    : root.monitorControllerReady
                        && root.monitorController.validationMessage(
                            root.connectorName) !== ""
                        ? root.monitorController.validationMessage(
                            root.connectorName)
                    : root.displayEditable && root.inspectedOutput !== null
                        && !root.inspectedOutput.hdr.available
                        ? root.inspectedOutput.hdr.unavailable_reason
                    : root.displayEditable && root.monitorControllerReady
                        && !root.monitorController.automaticHdrAvailable
                        ? root.monitorController.automaticHdrUnavailableReason
                    : root.inspectedOutput !== null
                        ? root.inspectedOutput.unavailable_reason : ""
                color: root.theme.danger
                font.pixelSize: root.metrics.captionFontSize
                wrapMode: Text.WordWrap
            }

            InfoRow {
                label: "Scale"
                value: root.scaleText()
            }

            Row {
                id: scalePresetsRow

                width: parent.width
                height: root.metrics.compactControlHeight
                spacing: root.metrics.rowSpacing

                Repeater {
                    model: root.scalePresets

                    Rectangle {
                        id: scalePresetButton

                        required property string modelData
                        readonly property string preset: modelData
                        readonly property bool selected: root.scaleMatches(Number(preset))
                        readonly property bool compatible: root.monitorControllerReady
                            && root.monitorController.scalePresetCompatible(
                                root.connectorName, preset)

                        width: (scalePresetsRow.width
                            - scalePresetsRow.spacing * (root.scalePresets.length - 1))
                            / root.scalePresets.length
                        height: scalePresetsRow.height
                        radius: root.metrics.rowRadius
                        color: selected ? root.theme.activeFill
                            : (presetMouse.containsMouse
                                ? root.theme.hoverFill : root.theme.normalFill)
                        opacity: root.scaleControlsEditable && compatible ? 1.0
                            : root.metrics.disabledInteractiveOpacity

                        Text {
                            anchors.fill: parent
                            text: String(Number(scalePresetButton.preset))
                            color: root.textColor
                            font.pixelSize: root.metrics.bodyFontSize
                            font.weight: scalePresetButton.selected
                                ? root.metrics.overlayFontWeight : Font.Normal
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.NoWrap
                        }

                        MouseArea {
                            id: presetMouse

                            anchors.fill: parent
                            enabled: root.scaleControlsEditable
                                && scalePresetButton.compatible
                            hoverEnabled: true
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.requestScalePreset(scalePresetButton.preset)
                        }
                    }
                }
            }

            Item {
                width: parent.width
                height: root.metrics.compactRowHeight
                    + root.metrics.compactControlHeight

                InfoRow {
                    label: "Text size"
                    value: root.displayedTextSize() + " px"
                }

                Item {
                    id: textSizeSlider

                    readonly property int currentIndex: root.currentTextSizeIndex()
                    readonly property int lastIndex:
                        root.textSizeController.values.length - 1
                    readonly property real progress: lastIndex > 0
                        ? currentIndex / lastIndex : 0

                    x: 0
                    y: root.metrics.compactRowHeight
                    width: parent.width
                    height: root.metrics.sliderHitHeight
                    opacity: root.textSizeController.ready
                        && !root.textSizeController.busy
                        ? 1.0 : root.metrics.disabledInteractiveOpacity

                    Rectangle {
                        id: textSizeTrack

                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: parent.verticalCenter
                        }
                        height: root.metrics.sliderTrackThickness
                        radius: root.metrics.sliderTrackRadius
                        color: root.theme.normalFill
                    }

                    Rectangle {
                        anchors {
                            left: textSizeTrack.left
                            verticalCenter: textSizeTrack.verticalCenter
                        }
                        width: textSizeTrack.width * textSizeSlider.progress
                        height: textSizeTrack.height
                        radius: root.metrics.sliderTrackRadius
                        color: root.theme.control
                    }

                    Repeater {
                        model: root.textSizeController.values

                        Rectangle {
                            required property int index

                            x: textSizeTrack.x + (textSizeTrack.width - width)
                                * index / Math.max(1, textSizeSlider.lastIndex)
                            anchors.verticalCenter: textSizeTrack.verticalCenter
                            width: root.metrics.separatorThickness
                            height: root.metrics.sliderNotchHeight
                            color: root.theme.control
                        }
                    }

                    Rectangle {
                        width: root.metrics.sliderThumbSize
                        height: root.metrics.sliderThumbSize
                        radius: root.metrics.sliderThumbRadius
                        x: Math.max(0, Math.min(textSizeTrack.width - width,
                            textSizeTrack.width * textSizeSlider.progress - width / 2))
                        anchors.verticalCenter: textSizeTrack.verticalCenter
                        color: root.theme.control
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: root.textSizeController.ready
                            && !root.textSizeController.busy
                        hoverEnabled: true
                        preventStealing: true
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onPressed: mouse => root.previewTextSize(mouse.x, width)
                        onPositionChanged: mouse => {
                            if (pressed)
                                root.previewTextSize(mouse.x, width)
                        }
                        onReleased: root.applyTextSizePreview()
                        onCanceled: root.textSizePreviewIndex = -1
                    }
                }
            }

            Text {
                visible: root.textSizeController.busy
                    || root.textSizeController.errorMessage !== ""
                width: parent.width
                text: root.textSizeController.errorMessage !== ""
                    ? root.textSizeController.errorMessage
                    : "Applying…"
                color: root.textSizeController.errorMessage !== ""
                    ? root.theme.danger : root.theme.textMuted
                font.pixelSize: root.metrics.captionFontSize
                wrapMode: Text.WordWrap
            }

            Item {
                width: parent.width
                height: root.metrics.compactRowHeight
                    + root.metrics.compactControlHeight

                InfoRow {
                    label: "Brightness"
                    value: root.brightnessAvailable
                        ? root.brightnessPercent + "%" : "Unavailable"
                }

                Item {
                    id: brightnessSlider

                    readonly property real progress: Math.max(0, Math.min(1,
                        (root.brightnessPercent - 1) / 99))

                    x: 0
                    y: root.metrics.compactRowHeight
                    width: parent.width
                    height: root.metrics.sliderHitHeight
                    opacity: root.brightnessAvailable
                        ? 1.0 : root.metrics.disabledInteractiveOpacity

                    Rectangle {
                        id: brightnessTrack

                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: parent.verticalCenter
                        }
                        height: root.metrics.sliderTrackThickness
                        radius: root.metrics.sliderTrackRadius
                        color: root.theme.normalFill
                    }

                    Rectangle {
                        anchors {
                            left: brightnessTrack.left
                            verticalCenter: brightnessTrack.verticalCenter
                        }
                        width: brightnessTrack.width * brightnessSlider.progress
                        height: brightnessTrack.height
                        radius: root.metrics.sliderTrackRadius
                        color: root.theme.control
                    }

                    Rectangle {
                        width: root.metrics.sliderThumbSize
                        height: root.metrics.sliderThumbSize
                        radius: root.metrics.sliderThumbRadius
                        x: Math.max(0, Math.min(brightnessTrack.width - width,
                            brightnessTrack.width * brightnessSlider.progress - width / 2))
                        anchors.verticalCenter: brightnessTrack.verticalCenter
                        color: root.theme.control
                    }

                    MouseArea {
                        id: sliderMouse

                        anchors.fill: parent
                        enabled: root.brightnessAvailable
                        hoverEnabled: true
                        preventStealing: true
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor

                        function percentFromX(position: real): int {
                            if (width <= 0)
                                return 1
                            return root.clampBrightness(1
                                + Math.max(0, Math.min(width, position)) / width * 99)
                        }

                        onPressed: mouse => root.previewBrightness(percentFromX(mouse.x))
                        onPositionChanged: mouse => {
                            if (pressed)
                                root.previewBrightness(percentFromX(mouse.x))
                        }
                        onReleased: {
                            if (root.visible && root.brightnessAvailable) {
                                root.pendingBrightnessPercent = root.clampBrightness(
                                    root.brightnessPercent)
                                root.brightnessWritePending = true
                                root.brightnessWriteRetriesRemaining = 1
                                brightnessDebounce.restart()
                            }
                        }
                    }
                }
            }
        }
    }
}
