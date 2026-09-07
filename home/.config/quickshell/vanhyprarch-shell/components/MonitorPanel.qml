pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

PopupWindow {
    id: root

    required property var theme
    required property Item popupAnchorItem
    required property int popupRadius
    property int panelWidth: 260
    property int panelPadding: 12
    property int rowHeight: 32
    property int popupHorizontalGap: -16
    property int popupVerticalOffset: -2
    property color backgroundColor: root.theme.background
    property color textColor: root.theme.text
    property color secondaryColor: root.theme.surface
    property color accentColor: root.theme.accent
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
    readonly property string scaleEditScript: [
        "set -eu",
        "target=\"$HOME/.config/hypr/hyprland.lua\"",
        "value=\"$1\"",
        "case \"$value\" in",
        "    1.00|1.25|1.50|2.00) ;;",
        "    *) exit 64 ;;",
        "esac",
        "[ -f \"$target\" ] || exit 66",
        "pattern='^[[:space:]]*local[[:space:]]+dp1Scale[[:space:]]*=[[:space:]]*[0-9]+([.][0-9]+)?[[:space:]]*$'",
        "grepStatus=0",
        "count=$(grep -Ec \"$pattern\" \"$target\") || grepStatus=$?",
        "[ \"$grepStatus\" -le 1 ] || exit \"$grepStatus\"",
        "[ \"$count\" -eq 1 ] || exit 65",
        "tmp=$(mktemp \"${target}.tmp.XXXXXX\")",
        "trap 'rm -f -- \"$tmp\"' EXIT HUP INT TERM",
        "sed -E \"s|$pattern|local dp1Scale = $value|\" \"$target\" > \"$tmp\"",
        "verifyStatus=0",
        "count=$(grep -Fxc \"local dp1Scale = $value\" \"$tmp\") || verifyStatus=$?",
        "[ \"$verifyStatus\" -le 1 ] || exit \"$verifyStatus\"",
        "[ \"$count\" -eq 1 ] || exit 67",
        "chmod --reference=\"$target\" \"$tmp\"",
        "mv -- \"$tmp\" \"$target\"",
        "trap - EXIT HUP INT TERM"
    ].join("\n")

    readonly property var monitor: Hyprland.focusedMonitor
    readonly property var monitorData: monitor ? monitor.lastIpcObject : null
    readonly property string connectorName: monitor ? String(monitor.name || "") : ""
    readonly property string monitorDescription: {
        if (!monitor)
            return "No focused monitor"

        const model = monitorData ? String(monitorData["model"] || "").trim() : ""
        if (model !== "")
            return model

        const description = String(monitor.description || "").trim()
        return description !== "" ? description : "Unknown display"
    }
    readonly property real refreshRate: monitorData ? Number(monitorData["refreshRate"]) : NaN
    readonly property string currentFormat: monitorData ? String(monitorData["currentFormat"] || "") : ""
    readonly property bool isTenBit: currentFormat.indexOf("2101010") !== -1

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

    function modeText(): string {
        if (!root.monitor)
            return "—"

        const width = Number(root.monitor.width)
        const height = Number(root.monitor.height)
        const dimensions = width > 0 && height > 0
            ? width + " × " + height
            : "Unknown resolution"
        const refresh = root.formatNumber(root.refreshRate, 2)
        return refresh !== "—" ? dimensions + " @ " + refresh + " Hz" : dimensions
    }

    function scaleText(): string {
        if (!root.monitor)
            return "—"

        const scale = Number(root.monitor.scale)
        return isFinite(scale) && scale > 0 ? root.formatNumber(scale, 2) + "×" : "—"
    }

    function scaleMatches(preset: real): bool {
        if (!root.monitor)
            return false

        const currentScale = Number(root.monitor.scale)
        return isFinite(currentScale) && Math.abs(currentScale - preset) < 0.01
    }

    function requestScalePreset(preset: string) {
        if (root.scalePresets.indexOf(preset) === -1) {
            console.warn("Rejected invalid monitor scale preset: " + preset)
            return
        }
        if (root.connectorName !== "DP-1") {
            console.warn("Monitor scale presets are only configured for DP-1")
            return
        }
        if (scaleWriteProcess.running || root.scaleMatches(Number(preset)))
            return

        scaleWriteProcess.requestedScale = preset
        scaleWriteProcess.command = ["sh", "-c", root.scaleEditScript,
            "quickshell-scale-edit", preset]
        scaleWriteProcess.running = true
    }

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: Math.max(0,
            ((root.popupAnchorItem.parent ? root.popupAnchorItem.parent.width : root.popupAnchorItem.width)
                - root.popupAnchorItem.width) / 2) + root.popupHorizontalGap
        margins.bottom: root.popupVerticalOffset
    }

    implicitWidth: panelWidth
    implicitHeight: content.implicitHeight + panelPadding * 2
    color: "transparent"
    visible: false
    grabFocus: true

    component InfoRow: Item {
        required property string label
        required property string value

        width: content.width
        height: root.rowHeight

        Text {
            anchors {
                left: parent.left
                verticalCenter: parent.verticalCenter
            }
            text: parent.label
            color: root.textColor
            font.pixelSize: 13
        }

        Text {
            anchors {
                right: parent.right
                verticalCenter: parent.verticalCenter
            }
            text: parent.value
            color: root.textColor
            font.pixelSize: 13
            font.weight: Font.Medium
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

    Process {
        id: scaleWriteProcess

        property string requestedScale: ""

        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0) {
                console.warn("Monitor scale update failed for "
                    + scaleWriteProcess.requestedScale + "× (exit " + exitCode + ")")
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: 0
        topLeftRadius: 0
        topRightRadius: root.popupRadius
        bottomLeftRadius: 0
        bottomRightRadius: root.popupRadius

        Column {
            id: content

            x: root.panelPadding
            y: root.panelPadding
            width: root.panelWidth - root.panelPadding * 2
            spacing: 6

            Text {
                width: parent.width
                text: "Display"
                color: root.textColor
                font.pixelSize: 16
                font.bold: true
                wrapMode: Text.NoWrap
            }

            Text {
                width: parent.width
                text: root.monitorSubtitle()
                color: root.textColor
                font.pixelSize: 12
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
            }

            Text {
                width: parent.width
                height: root.rowHeight
                text: root.modeText()
                color: root.textColor
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }

            InfoRow {
                label: "Scale"
                value: root.scaleText()
            }

            Row {
                id: scalePresetsRow

                width: parent.width
                height: 24
                spacing: 4

                Repeater {
                    model: root.scalePresets

                    Rectangle {
                        id: scalePresetButton

                        required property string modelData
                        readonly property string preset: modelData
                        readonly property bool selected: root.scaleMatches(Number(preset))

                        width: (scalePresetsRow.width
                            - scalePresetsRow.spacing * (root.scalePresets.length - 1))
                            / root.scalePresets.length
                        height: scalePresetsRow.height
                        radius: root.popupRadius / 2
                        color: selected ? root.accentColor : root.secondaryColor

                        Text {
                            anchors.fill: parent
                            text: String(Number(scalePresetButton.preset))
                            color: scalePresetButton.selected
                                ? root.backgroundColor : root.textColor
                            font.pixelSize: 12
                            font.weight: scalePresetButton.selected
                                ? Font.Medium : Font.Normal
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.NoWrap
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !scaleWriteProcess.running
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.requestScalePreset(scalePresetButton.preset)
                        }
                    }
                }
            }

            InfoRow {
                visible: root.isTenBit
                height: visible ? root.rowHeight : 0
                label: "Color depth"
                value: "10-bit"
            }

            Item {
                width: parent.width
                height: root.rowHeight + 28

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
                    y: root.rowHeight
                    width: parent.width
                    height: 20
                    opacity: root.brightnessAvailable ? 1.0 : 0.35

                    Rectangle {
                        id: brightnessTrack

                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: parent.verticalCenter
                        }
                        height: 4
                        radius: height / 2
                        color: root.secondaryColor
                    }

                    Rectangle {
                        anchors {
                            left: brightnessTrack.left
                            verticalCenter: brightnessTrack.verticalCenter
                        }
                        width: brightnessTrack.width * brightnessSlider.progress
                        height: brightnessTrack.height
                        radius: height / 2
                        color: root.accentColor
                    }

                    Rectangle {
                        width: 14
                        height: 14
                        radius: width / 2
                        x: Math.max(0, Math.min(brightnessTrack.width - width,
                            brightnessTrack.width * brightnessSlider.progress - width / 2))
                        anchors.verticalCenter: brightnessTrack.verticalCenter
                        color: root.accentColor
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
