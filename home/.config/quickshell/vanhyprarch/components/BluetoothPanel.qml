pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Bluetooth

DockPopup {
    id: root

    required property var controller
    required property var powerController
    required property var theme
    required property string screenName
    property color textColor: root.theme.text
    property var discoveryAdapter: null
    property bool discoveryOwnedByPanel: false
    property string confirmForgetPath: ""
    property string promptValue: ""

    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property bool adapterAvailable: adapter !== null
    readonly property bool adapterBlocked: adapterAvailable
        && adapter.state === BluetoothAdapterState.Blocked
    readonly property bool adapterEnabled: adapterAvailable
        && adapter.enabled && adapter.state === BluetoothAdapterState.Enabled
    readonly property bool adapterChanging: adapterAvailable
        && (adapter.state === BluetoothAdapterState.Enabling
            || adapter.state === BluetoothAdapterState.Disabling)
    readonly property var deviceObjects: adapterAvailable && adapter.devices
        ? adapter.devices.values : []
    // BlueZ removes discovery-only device objects asynchronously after the
    // adapter powers down. Detach the hidden views immediately so those late
    // model removals cannot keep invalidating a collapsed native popup.
    readonly property var visibleDeviceObjects: root.adapterEnabled
        ? root.deviceObjects : []
    readonly property var pairedDevices: root.sortedDevices(
        root.visibleDeviceObjects.filter(device =>
            device && (device.paired || device.bonded)))
    readonly property var availableDevices: root.sortedDevices(
        root.visibleDeviceObjects.filter(device =>
            device && !device.paired && !device.bonded))
    readonly property bool promptForScreen: root.controller.promptActive
        && root.controller.promptScreenName === root.screenName
    readonly property var prompt: promptForScreen ? root.controller.currentPrompt : null
    readonly property var promptDevice: prompt
        ? root.controller.deviceForPath(prompt.devicePath) : null
    readonly property string promptIdentity: prompt
        ? root.controller.deviceIdentityForPath(prompt.devicePath) : ""

    function cleanText(value, fallback: string): string {
        const text = String(value || "").trim()
        return text !== "" ? text : fallback
    }

    function deviceName(device): string {
        if (!device)
            return "Unknown Bluetooth device"
        const values = [device.name, device.deviceName, device.address]
        for (const value of values) {
            const label = String(value || "").trim()
            if (label !== "")
                return label
        }
        return "Unknown Bluetooth device"
    }

    function deviceIcon(device): string {
        const icon = device ? String(device.icon || "").trim() : ""
        return icon !== "" ? icon : "preferences-system-bluetooth"
    }

    function deviceBusy(device): bool {
        return Boolean(device && (device.pairing
            || device.state === BluetoothDeviceState.Connecting
            || device.state === BluetoothDeviceState.Disconnecting
            || root.controller.pairIntentPath === String(device.dbusPath || "")))
    }

    function sortedDevices(devices): var {
        const result = devices.slice()
        result.sort(function(left, right) {
            if (Boolean(left.connected) !== Boolean(right.connected))
                return left.connected ? -1 : 1
            const leftBusy = root.deviceBusy(left)
            const rightBusy = root.deviceBusy(right)
            if (leftBusy !== rightBusy)
                return leftBusy ? -1 : 1
            const leftPaired = Boolean(left.paired || left.bonded)
            const rightPaired = Boolean(right.paired || right.bonded)
            if (leftPaired !== rightPaired)
                return leftPaired ? -1 : 1
            const nameOrder = root.deviceName(left).localeCompare(root.deviceName(right))
            if (nameOrder !== 0)
                return nameOrder
            return String(left.address || "").localeCompare(String(right.address || ""))
        })
        return result
    }

    function stateLabel(device): string {
        if (!device)
            return "Unavailable"
        const path = String(device.dbusPath || "")
        let state = "Available"
        if (root.controller.pairIntentPath === path
                && root.controller.pairIntentWaitingForTrust)
            state = "Trusting…"
        else if (device.pairing || root.controller.pairIntentPath === path)
            state = device.pairing ? "Pairing…" : "Starting pairing…"
        else if (device.state === BluetoothDeviceState.Connecting)
            state = "Connecting…"
        else if (device.state === BluetoothDeviceState.Disconnecting)
            state = "Disconnecting…"
        else if (device.connected)
            state = "Connected"
        else if (device.paired || device.bonded)
            state = "Paired"
        if (device.batteryAvailable) {
            const battery = Number(device.battery)
            if (isFinite(battery))
                state += " · " + Math.round(Math.max(0, Math.min(1, battery)) * 100) + "%"
        }
        return state
    }

    function mainActionLabel(device): string {
        if (!device)
            return ""
        const path = String(device.dbusPath || "")
        if (root.controller.pairIntentPath === path && !device.pairing)
            return root.controller.pairIntentWaitingForTrust ? "Trusting…" : "Pairing…"
        if (device.pairing)
            return "Cancel"
        if (device.state === BluetoothDeviceState.Connecting)
            return "Connecting…"
        if (device.state === BluetoothDeviceState.Disconnecting)
            return "Disconnecting…"
        if (device.connected)
            return "Disconnect"
        if (device.paired || device.bonded)
            return "Connect"
        return root.controller.ready ? "Pair" : "Agent unavailable"
    }

    function mainActionEnabled(device): bool {
        if (!device || device.blocked)
            return false
        if (root.controller.pairIntentPath === String(device.dbusPath || "")
                && !device.pairing)
            return false
        if (device.pairing)
            return true
        if (device.state === BluetoothDeviceState.Connecting
                || device.state === BluetoothDeviceState.Disconnecting)
            return false
        if (device.paired || device.bonded)
            return true
        return root.controller.ready
    }

    function activateDevice(device): void {
        if (!root.mainActionEnabled(device))
            return
        root.confirmForgetPath = ""
        if (device.pairing) {
            root.controller.cancelPair(device)
        } else if (device.connected) {
            device.disconnect()
        } else if (device.paired || device.bonded) {
            device.connect()
        } else {
            root.controller.pairDevice(device, root.screenName)
        }
    }

    function requestForget(device): void {
        if (!device || !(device.paired || device.bonded) || device.pairing)
            return
        const path = String(device.dbusPath || "")
        if (root.confirmForgetPath !== path) {
            root.confirmForgetPath = path
            return
        }
        root.confirmForgetPath = ""
        if (root.controller.pairIntentPath === path)
            root.controller.clearPairIntent("")
        device.forget()
    }

    function adapterStatus(): string {
        if (!root.adapterAvailable)
            return "Unavailable"
        switch (root.adapter.state) {
        case BluetoothAdapterState.Blocked: return "Blocked"
        case BluetoothAdapterState.Enabling: return "Turning on…"
        case BluetoothAdapterState.Disabling: return "Turning off…"
        case BluetoothAdapterState.Enabled: return root.adapter.enabled ? "On" : "Unavailable"
        default: return "Off"
        }
    }

    function toggleAdapter(): void {
        if (!root.adapterAvailable || root.adapterBlocked || root.adapterChanging
                || !root.powerController.ready || root.powerController.busy)
            return
        if (root.adapterEnabled)
            root.releaseDiscovery()
        root.powerController.requestEnabled(!root.adapterEnabled)
    }

    function acquireDiscovery(): void {
        root.releaseDiscovery()
        const candidate = root.visible && root.adapterEnabled ? root.adapter : null
        if (!candidate)
            return
        root.discoveryAdapter = candidate
        if (candidate.discovering)
            return
        root.discoveryOwnedByPanel = true
        candidate.discovering = true
    }

    function releaseDiscovery(): void {
        const candidate = root.discoveryAdapter
        const owned = root.discoveryOwnedByPanel
        root.discoveryAdapter = null
        root.discoveryOwnedByPanel = false
        if (candidate && owned && candidate.discovering)
            candidate.discovering = false
    }

    function formatPasskey(value): string {
        let text = String(Math.max(0, Math.min(999999, Number(value) || 0)))
        while (text.length < 6)
            text = "0" + text
        return text
    }

    function serviceName(uuid): string {
        const names = {
            "00001101-0000-1000-8000-00805f9b34fb": "Serial Port",
            "0000110a-0000-1000-8000-00805f9b34fb": "Audio Source",
            "0000110b-0000-1000-8000-00805f9b34fb": "Audio Sink",
            "0000110e-0000-1000-8000-00805f9b34fb": "Media Remote Control",
            "0000110f-0000-1000-8000-00805f9b34fb": "Media Remote Control Target",
            "00001112-0000-1000-8000-00805f9b34fb": "Headset Audio Gateway",
            "00001115-0000-1000-8000-00805f9b34fb": "Personal Area Network",
            "00001116-0000-1000-8000-00805f9b34fb": "Network Access Point",
            "0000111e-0000-1000-8000-00805f9b34fb": "Hands-Free Audio",
            "0000111f-0000-1000-8000-00805f9b34fb": "Hands-Free Audio Gateway",
            "00001124-0000-1000-8000-00805f9b34fb": "Human Interface Device",
            "0000180f-0000-1000-8000-00805f9b34fb": "Battery Service"
        }
        return names[String(uuid || "")] || ""
    }

    function promptTitle(): string {
        if (!root.prompt)
            return "Pairing request"
        switch (root.prompt.kind) {
        case "requestPinCode": return "Enter PIN"
        case "requestPasskey": return "Enter passkey"
        case "displayPinCode": return "Bluetooth PIN"
        case "displayPasskey": return "Bluetooth passkey"
        case "requestConfirmation": return "Confirm passkey"
        case "requestAuthorization": return "Allow pairing?"
        case "authorizeService": return "Allow Bluetooth service?"
        default: return "Pairing request"
        }
    }

    function promptDescription(): string {
        if (!root.prompt)
            return ""
        const name = root.promptIdentity
        switch (root.prompt.kind) {
        case "requestPinCode":
            return "Enter the PIN shown by or documented for " + name + "."
        case "requestPasskey":
            return "Enter the numeric passkey for " + name + "."
        case "displayPinCode":
            return "Enter this PIN on " + name + "."
        case "displayPasskey":
            return "Enter this passkey on " + name + "."
        case "requestConfirmation":
            return "Does this passkey match the one shown on " + name + "?"
        case "requestAuthorization":
            return "Allow " + name + " to pair with this computer?"
        case "authorizeService": {
            const uuid = root.prompt.uuid
            const service = root.serviceName(uuid)
            return "Allow " + name + " to use "
                + (service !== "" ? service + " (" + uuid + ")" : uuid) + "?"
        }
        default:
            return "Review this request for " + name + "."
        }
    }

    function syncPromptVisibility(): void {
        if (root.promptForScreen && !root.visible)
            root.visible = true
        if (root.promptForScreen && root.visible && root.controller.displayPrompt
                && !root.controller.displayAcknowledged
                && !root.controller.promptResponsePending) {
            const requestId = root.prompt.id
            Qt.callLater(function() {
                if (root.visible && root.promptForScreen && root.prompt
                        && root.prompt.id === requestId)
                    root.controller.acknowledgeDisplayedPrompt(
                        root.screenName, requestId)
            })
        }
    }

    onVisibleChanged: {
        if (visible) {
            root.controller.notePanelOpened(root.screenName)
            root.acquireDiscovery()
            if (root.prompt && (root.prompt.kind === "requestPinCode"
                    || root.prompt.kind === "requestPasskey"))
                Qt.callLater(function() { promptInput.forceActiveFocus() })
        } else {
            root.releaseDiscovery()
            root.confirmForgetPath = ""
            root.promptValue = ""
            root.controller.notePanelClosed(root.screenName)
            if (root.promptForScreen)
                Qt.callLater(root.syncPromptVisibility)
        }
    }

    onAdapterChanged: {
        root.releaseDiscovery()
        root.acquireDiscovery()
    }

    onPromptChanged: {
        root.promptValue = ""
        root.syncPromptVisibility()
        if (root.prompt && root.visible
                && (root.prompt.kind === "requestPinCode"
                    || root.prompt.kind === "requestPasskey"))
            Qt.callLater(function() { promptInput.forceActiveFocus() })
    }

    Component.onCompleted: root.syncPromptVisibility()

    Component.onDestruction: {
        root.releaseDiscovery()
        root.controller.notePanelDestroyed(root.screenName)
    }

    Connections {
        target: root.adapter
        ignoreUnknownSignals: true

        function onEnabledChanged(): void {
            if (root.adapterEnabled)
                root.acquireDiscovery()
            else
                root.releaseDiscovery()
        }

        function onStateChanged(): void {
            if (root.adapterEnabled)
                root.acquireDiscovery()
            else
                root.releaseDiscovery()
        }
    }

    Connections {
        target: root.controller

        function onPromptRaised(): void {
            root.syncPromptVisibility()
        }

        function onPromptScreenNameChanged(): void {
            root.syncPromptVisibility()
        }
    }

    implicitHeight: content.implicitHeight + root.metrics.panelPadding * 2

    component DeviceRow: Rectangle {
        id: deviceRow

        required property var device
        required property bool pairedSection
        readonly property string path: String(device.dbusPath || "")
        readonly property bool forgetPending: root.confirmForgetPath === path

        width: content.width
        height: root.metrics.twoLineRowHeight
        radius: root.metrics.rowRadius
        color: mainMouse.containsMouse && root.mainActionEnabled(device)
            ? root.theme.hoverFill
            : device.connected ? root.theme.activeFill : "transparent"

        Image {
            id: deviceIcon

            anchors {
                left: parent.left
                leftMargin: root.metrics.rowSidePadding
                verticalCenter: parent.verticalCenter
            }
            width: root.metrics.standardIconSize
            height: root.metrics.standardIconSize
            source: Quickshell.iconPath(root.deviceIcon(deviceRow.device),
                "preferences-system-bluetooth")
            sourceSize: Qt.size(width, height)
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }

        Text {
            anchors {
                left: deviceIcon.right
                right: actionLabel.left
                top: parent.top
                leftMargin: root.metrics.contentGap
                rightMargin: root.metrics.contentGap
                topMargin: root.metrics.contentGap
            }
            text: root.deviceName(deviceRow.device)
            textFormat: Text.PlainText
            color: root.textColor
            font.pixelSize: root.metrics.bodyFontSize
            font.weight: root.metrics.overlayFontWeight
            elide: Text.ElideRight
            wrapMode: Text.NoWrap
        }

        Text {
            anchors {
                left: deviceIcon.right
                right: actionLabel.left
                bottom: parent.bottom
                leftMargin: root.metrics.contentGap
                rightMargin: root.metrics.contentGap
                bottomMargin: root.metrics.contentGap
            }
            text: root.stateLabel(deviceRow.device)
            textFormat: Text.PlainText
            color: root.theme.textMuted
            font.pixelSize: root.metrics.captionFontSize
            elide: Text.ElideRight
            wrapMode: Text.NoWrap
        }

        Text {
            id: actionLabel

            anchors {
                right: forgetAction.visible ? forgetAction.left : parent.right
                rightMargin: forgetAction.visible
                    ? root.metrics.contentGap : root.metrics.rowSidePadding
                verticalCenter: parent.verticalCenter
            }
            width: forgetAction.visible
                ? root.metrics.scaled(57) : root.metrics.scaled(78)
            text: root.mainActionLabel(deviceRow.device)
            color: root.textColor
            opacity: root.mainActionEnabled(deviceRow.device)
                ? 1.0 : root.metrics.disabledInteractiveOpacity
            font.pixelSize: root.metrics.captionFontSize
            font.weight: root.metrics.overlayFontWeight
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideRight
            wrapMode: Text.NoWrap
        }

        Rectangle {
            id: forgetAction

            visible: deviceRow.pairedSection && !deviceRow.device.pairing
            z: 2
            width: visible ? (deviceRow.forgetPending
                ? root.metrics.inlineConfirmationActionWidth
                : root.metrics.inlineTextActionWidth) : 0
            height: root.metrics.inlineActionButtonSize
            anchors {
                right: parent.right
                rightMargin: root.metrics.contentGap
                verticalCenter: parent.verticalCenter
            }
            radius: root.metrics.rowRadius
            color: forgetMouse.containsMouse
                ? root.theme.dangerFill : "transparent"

            Text {
                anchors.fill: parent
                text: deviceRow.forgetPending ? "Confirm" : "Forget"
                color: root.theme.danger
                font.pixelSize: root.metrics.captionFontSize
                font.weight: deviceRow.forgetPending
                    ? root.metrics.overlayFontWeight : Font.Normal
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }

            MouseArea {
                id: forgetMouse

                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.requestForget(deviceRow.device)
            }
        }

        MouseArea {
            id: mainMouse

            z: 1
            anchors {
                left: parent.left
                top: parent.top
                bottom: parent.bottom
                right: forgetAction.visible ? forgetAction.left : parent.right
            }
            enabled: root.mainActionEnabled(deviceRow.device)
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.activateDevice(deviceRow.device)
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
                text: "Bluetooth"
                color: root.textColor
                font.pixelSize: root.metrics.panelTitleFontSize
                font.weight: root.metrics.panelTitleFontWeight
                wrapMode: Text.NoWrap
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
            }

            Item {
                width: parent.width
                height: root.metrics.compactRowHeight

                Text {
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    text: "Bluetooth"
                    color: root.textColor
                    font.pixelSize: root.metrics.bodyFontSize
                    font.weight: root.metrics.overlayFontWeight
                }

                Item {
                    id: adapterToggle

                    readonly property bool actionable: root.adapterAvailable
                        && !root.adapterBlocked && !root.adapterChanging
                        && root.powerController.ready && !root.powerController.busy

                    width: adapterToggleContent.implicitWidth
                    height: root.metrics.compactRowHeight
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    opacity: actionable
                        ? 1.0 : root.metrics.disabledInteractiveOpacity

                    Row {
                        id: adapterToggleContent

                        anchors.centerIn: parent
                        spacing: root.metrics.contentGap

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.adapterStatus()
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.detailFontSize
                        }

                        ToggleSwitch {
                            metrics: root.metrics
                            theme: root.theme
                            checked: root.adapterEnabled
                            interactive: false
                            enabled: adapterToggle.actionable
                        }
                    }

                    MouseArea {
                        id: adapterToggleMouse

                        anchors.fill: parent
                        enabled: adapterToggle.actionable
                        hoverEnabled: true
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.toggleAdapter()
                    }
                }
            }

            Text {
                visible: root.powerController.errorMessage !== ""
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: root.powerController.errorMessage
                textFormat: Text.PlainText
                color: root.theme.danger
                font.pixelSize: root.metrics.detailFontSize
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
            }

            Text {
                visible: root.controller.state !== "ready"
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: root.controller.state === "starting"
                    ? "Pairing agent starting…"
                    : root.cleanText(root.controller.errorMessage,
                        "Pairing agent unavailable")
                textFormat: Text.PlainText
                color: root.theme.danger
                font.pixelSize: root.metrics.detailFontSize
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
            }

            Rectangle {
                id: pairingPrompt

                visible: root.promptForScreen
                width: parent.width
                height: visible ? promptContent.implicitHeight
                    + root.metrics.overlayPadding : 0
                radius: root.metrics.rowRadius
                color: root.theme.normalFill

                Column {
                    id: promptContent

                    anchors {
                        left: parent.left
                        right: parent.right
                        top: parent.top
                        margins: root.metrics.rowSidePadding
                    }
                    spacing: root.metrics.contentGap

                    Text {
                        width: parent.width
                        text: root.promptTitle()
                        textFormat: Text.PlainText
                        color: root.textColor
                        font.pixelSize: root.metrics.bodyFontSize
                        font.weight: root.metrics.overlayFontWeight
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        width: parent.width
                        text: root.promptDescription()
                        textFormat: Text.PlainText
                        color: root.theme.textMuted
                        font.pixelSize: root.metrics.detailFontSize
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        visible: root.prompt && (root.prompt.kind === "displayPinCode"
                            || root.prompt.kind === "displayPasskey"
                            || root.prompt.kind === "requestConfirmation")
                        width: parent.width
                        height: visible ? root.metrics.prominentValueHeight : 0
                        text: {
                            if (!root.prompt)
                                return ""
                            if (root.prompt.kind === "displayPinCode")
                                return root.prompt.pin
                            return root.formatPasskey(root.prompt.passkey)
                        }
                        textFormat: Text.PlainText
                        color: root.theme.control
                        font.pixelSize: root.metrics.prominentValueFontSize
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        visible: root.prompt && root.prompt.kind === "displayPasskey"
                        width: parent.width
                        height: visible ? root.metrics.captionLineHeight : 0
                        text: root.prompt
                            ? String(root.prompt.entered) + " of 6 digits entered" : ""
                        textFormat: Text.PlainText
                        color: root.theme.textMuted
                        font.pixelSize: root.metrics.captionFontSize
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.NoWrap
                    }

                    Rectangle {
                        visible: root.prompt && (root.prompt.kind === "requestPinCode"
                            || root.prompt.kind === "requestPasskey")
                        width: parent.width
                        height: visible ? root.metrics.textFieldHeight : 0
                        radius: root.metrics.rowRadius
                        color: promptInput.activeFocus
                            ? root.theme.hoverFill : root.theme.normalFill
                        border.width: root.metrics.controlOutlineThickness
                        border.color: promptInput.activeFocus
                            ? root.theme.focus : root.theme.separator

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.metrics.rowSidePadding
                                verticalCenter: parent.verticalCenter
                            }
                            visible: promptInput.text.length === 0
                                && !promptInput.activeFocus
                            text: root.prompt && root.prompt.kind === "requestPasskey"
                                ? "Numeric passkey" : "PIN"
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.bodyFontSize
                        }

                        TextInput {
                            id: promptInput

                            anchors {
                                fill: parent
                                leftMargin: root.metrics.rowSidePadding
                                rightMargin: root.metrics.rowSidePadding
                            }
                            text: root.promptValue
                            color: root.textColor
                            selectionColor: root.theme.activeFill
                            selectedTextColor: root.theme.text
                            font.pixelSize: root.metrics.bodyFontSize
                            verticalAlignment: TextInput.AlignVCenter
                            echoMode: TextInput.Password
                            clip: true
                            maximumLength: root.prompt
                                && root.prompt.kind === "requestPasskey" ? 6 : 16
                            inputMethodHints: root.prompt
                                && root.prompt.kind === "requestPasskey"
                                ? Qt.ImhDigitsOnly : Qt.ImhNoPredictiveText

                            onTextChanged: {
                                if (text !== root.promptValue)
                                    root.promptValue = text
                            }
                            Keys.onEscapePressed: root.controller.rejectPrompt()
                        }
                    }

                    Row {
                        width: parent.width
                        height: root.metrics.compactControlHeight
                        spacing: root.metrics.contentGap

                        Rectangle {
                            width: root.controller.displayPrompt
                                ? parent.width : (parent.width - parent.spacing) / 2
                            height: parent.height
                            radius: root.metrics.rowRadius
                            color: promptRejectMouse.containsMouse
                                ? root.theme.dangerFill : root.theme.normalFill

                            Text {
                                anchors.fill: parent
                                text: root.controller.displayCancellationPending
                                    ? "Canceling…"
                                    : (root.controller.displayPrompt ? "Cancel pairing" : "Reject")
                                color: root.theme.danger
                                font.pixelSize: root.metrics.bodyFontSize
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.NoWrap
                            }

                            MouseArea {
                                id: promptRejectMouse

                                anchors.fill: parent
                                enabled: root.controller.displayPrompt
                                    ? (!root.controller.displayCancellationPending
                                        && !root.controller.promptResponsePending)
                                    : !root.controller.promptResponsePending
                                hoverEnabled: true
                                cursorShape: enabled
                                    ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    if (root.controller.displayPrompt)
                                        root.controller.cancelDisplayedPairing()
                                    else
                                        root.controller.rejectPrompt()
                                }
                            }
                        }

                        Rectangle {
                            readonly property bool entryPrompt: root.prompt
                                && (root.prompt.kind === "requestPinCode"
                                    || root.prompt.kind === "requestPasskey")
                            readonly property bool validEntry: root.prompt
                                && ((root.prompt.kind === "requestPinCode"
                                        && /^[A-Za-z0-9]{1,16}$/.test(root.promptValue))
                                    || (root.prompt.kind === "requestPasskey"
                                        && /^[0-9]{1,6}$/.test(root.promptValue)))
                            readonly property bool canAccept: !root.controller.displayPrompt
                                && !root.controller.promptResponsePending
                                && root.promptIdentity !== ""
                                && (!root.prompt || root.prompt.kind !== "authorizeService"
                                    || root.controller.normalizeServiceUuid(
                                        root.prompt.uuid) === root.prompt.uuid)
                                && (!entryPrompt || validEntry)

                            visible: !root.controller.displayPrompt
                            width: visible ? (parent.width - parent.spacing) / 2 : 0
                            height: parent.height
                            radius: root.metrics.rowRadius
                            color: canAccept
                                ? root.theme.activeFill : root.theme.normalFill
                            opacity: canAccept ? 1.0
                                : root.metrics.disabledInteractiveOpacity

                            Text {
                                anchors.fill: parent
                                text: parent.entryPrompt ? "Submit" : "Allow"
                                color: root.textColor
                                font.pixelSize: root.metrics.bodyFontSize
                                font.weight: parent.canAccept
                                    ? root.metrics.overlayFontWeight : Font.Normal
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.NoWrap
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: parent.canAccept
                                hoverEnabled: true
                                cursorShape: enabled
                                    ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    if (parent.entryPrompt)
                                        root.controller.submitPrompt(root.promptValue)
                                    else
                                        root.controller.acceptPrompt()
                                }
                            }
                        }
                    }
                }
            }

            Text {
                visible: root.controller.actionError !== ""
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: root.controller.actionError
                textFormat: Text.PlainText
                color: root.theme.danger
                font.pixelSize: root.metrics.detailFontSize
                elide: Text.ElideRight
                wrapMode: Text.NoWrap
            }

            Text {
                // Keep one inactive-status row present throughout transitional
                // power states. Removing it during Disabling made the native
                // popup shrink and then grow again when Disabled was reached.
                visible: !root.adapterEnabled
                width: parent.width
                height: root.metrics.compactControlHeight
                text: !root.adapterAvailable ? "No Bluetooth adapter"
                    : (root.adapterBlocked ? "Bluetooth is blocked"
                        : "Bluetooth is off")
                color: root.theme.textMuted
                font.pixelSize: root.metrics.informationValueFontSize
                font.weight: root.metrics.informationValueFontWeight
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }

            PanelSeparator {
                visible: root.adapterEnabled
                metrics: root.metrics
                theme: root.theme
            }

            SectionHeading {
                metrics: root.metrics
                theme: root.theme
                visible: root.adapterEnabled
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: "PAIRED DEVICES"
                verticalAlignment: Text.AlignVCenter
            }

            ListView {
                id: pairedList

                readonly property int displayedRows:
                    Math.min(4, root.pairedDevices.length)

                visible: root.adapterEnabled && root.pairedDevices.length > 0
                width: parent.width
                height: visible ? displayedRows * root.metrics.twoLineRowHeight
                    + Math.max(0, displayedRows - 1) * spacing : 0
                spacing: root.metrics.rowSpacing
                clip: true
                interactive: contentHeight > height
                boundsBehavior: Flickable.StopAtBounds
                model: root.pairedDevices

                delegate: DeviceRow {
                    required property var modelData
                    device: modelData
                    pairedSection: true
                }
            }

            Text {
                visible: root.adapterEnabled && root.pairedDevices.length === 0
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: "No paired devices"
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                wrapMode: Text.NoWrap
            }

            PanelSeparator {
                visible: root.adapterEnabled
                metrics: root.metrics
                theme: root.theme
            }

            Item {
                visible: root.adapterEnabled
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0

                SectionHeading {
                    metrics: root.metrics
                    theme: root.theme
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    text: "AVAILABLE DEVICES"
                }

                Text {
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    text: root.adapter && root.adapter.discovering ? "Scanning…" : ""
                    color: root.theme.textMuted
                    font.pixelSize: root.metrics.captionFontSize
                    wrapMode: Text.NoWrap
                }
            }

            ListView {
                id: availableList

                readonly property int displayedRows:
                    Math.min(4, root.availableDevices.length)

                visible: root.adapterEnabled && root.availableDevices.length > 0
                width: parent.width
                height: visible ? displayedRows * root.metrics.twoLineRowHeight
                    + Math.max(0, displayedRows - 1) * spacing : 0
                spacing: root.metrics.rowSpacing
                clip: true
                interactive: contentHeight > height
                boundsBehavior: Flickable.StopAtBounds
                model: root.availableDevices

                delegate: DeviceRow {
                    required property var modelData
                    device: modelData
                    pairedSection: false
                }
            }

            Text {
                visible: root.adapterEnabled && root.availableDevices.length === 0
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: root.adapter && root.adapter.discovering
                    ? "Searching for devices…" : "No devices found"
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                wrapMode: Text.NoWrap
            }
        }
    }
}
