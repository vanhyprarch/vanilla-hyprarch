pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Networking

DockPopup {
    id: root

    required property var theme
    property color textColor: root.theme.text

    readonly property bool backendAvailable:
        Networking.backend === NetworkBackendType.NetworkManager
    readonly property var devices: root.backendAvailable && Networking.devices
        ? Networking.devices.values : []
    readonly property var wifiDevices: root.devices.filter(device =>
        device && device.type === DeviceType.Wifi)
    readonly property var wiredDevices: root.devices.filter(device =>
        device && device.type === DeviceType.Wired)
    readonly property var connectedWifiDevices: root.wifiDevices.filter(device =>
        Boolean(device.connected))
    readonly property var connectedWiredDevices: root.wiredDevices.filter(device =>
        Boolean(device.connected))
    readonly property bool wifiControlAvailable: root.backendAvailable
        && root.wifiDevices.length > 0 && Networking.wifiHardwareEnabled
    readonly property var selectedWifiDevice: {
        for (const device of root.wifiDevices) {
            if (device.connected)
                return device
        }
        return root.wifiDevices.length > 0 ? root.wifiDevices[0] : null
    }
    readonly property var wifiNetworkObjects: root.selectedWifiDevice
        && root.selectedWifiDevice.networks
        ? root.selectedWifiDevice.networks.values : []
    readonly property var wifiNetworks:
        root.snapshotWifiNetworks(root.wifiNetworkObjects)
    property var scannerDevice: null
    property bool scannerOwnedByPanel: false
    property string passwordSsid: ""
    property string passwordText: ""
    property bool passwordUpdatesKnownPsk: false
    property string actionSsid: ""
    property bool actionSawStateChanging: false
    property string failureSsid: ""
    property string failureText: ""
    property bool failureNeedsPassword: false

    function connectedWifiNetwork(device): var {
        if (!device || !device.networks)
            return null
        const networks = device.networks.values
        for (const network of networks) {
            if (network && network.connected)
                return network
        }
        return null
    }

    function cleanText(value, fallback: string): string {
        const text = String(value || "").trim()
        return text !== "" ? text : fallback
    }

    function snapshotWifiNetworks(networks): var {
        const rows = []
        const rowsBySsid = Object.create(null)

        for (let index = 0; index < networks.length; index++) {
            const network = networks[index]
            if (!network)
                continue

            const ssid = String(network.name || "")
            if (ssid === "")
                continue

            const signal = root.signalPercent(network)
            const key = "ssid:" + ssid
            const candidate = {
                ssid: ssid,
                signal: signal,
                security: Number(network.security),
                known: Boolean(network.known),
                connected: Boolean(network.connected),
                order: index
            }
            const existing = rowsBySsid[key]

            if (!existing) {
                rowsBySsid[key] = candidate
                rows.push(candidate)
                continue
            }

            const candidatePreferred = (candidate.connected && !existing.connected)
                || (!existing.connected && candidate.known && !existing.known)
                || (candidate.connected === existing.connected
                    && candidate.known === existing.known
                    && candidate.signal > existing.signal)
            if (candidatePreferred) {
                existing.security = candidate.security
            }
            existing.signal = Math.max(existing.signal, candidate.signal)
            existing.connected = existing.connected || candidate.connected
            existing.known = existing.known || candidate.known
        }

        rows.sort((left, right) => {
            if (left.connected !== right.connected)
                return left.connected ? -1 : 1
            if (left.known !== right.known)
                return left.known ? -1 : 1
            if (left.signal !== right.signal)
                return right.signal - left.signal
            const nameOrder = left.ssid.localeCompare(right.ssid)
            return nameOrder !== 0 ? nameOrder : left.order - right.order
        })
        return rows
    }

    function networkForSsid(ssid): var {
        if (!root.selectedWifiDevice || !root.selectedWifiDevice.networks)
            return null

        const targetSsid = String(ssid || "")
        const networks = root.selectedWifiDevice.networks.values
        let best = null
        let bestScore = -1

        for (const network of networks) {
            if (!network || String(network.name || "") !== targetSsid)
                continue
            if (network.connected)
                return network

            const score = (network.known ? 2 : 0)
                + Math.max(0, Math.min(1, Number(network.signalStrength) || 0))
            if (!best || score > bestScore) {
                best = network
                bestScore = score
            }
        }
        return best
    }

    function isPasswordlessSecurity(security): bool {
        return security === WifiSecurityType.Open
            || security === WifiSecurityType.Owe
    }

    function isPskSecurity(security): bool {
        return security === WifiSecurityType.WpaPsk
            || security === WifiSecurityType.Wpa2Psk
            || security === WifiSecurityType.Sae
    }

    function isEnterpriseSecurity(security): bool {
        return security === WifiSecurityType.WpaEap
            || security === WifiSecurityType.Wpa2Eap
            || security === WifiSecurityType.Wpa3SuiteB192
    }

    function securityLabel(security): string {
        if (root.isPasswordlessSecurity(security))
            return security === WifiSecurityType.Owe ? "Enhanced open" : "Open"
        if (root.isEnterpriseSecurity(security))
            return "Enterprise"
        if (root.isPskSecurity(security))
            return "Secured"
        return "Unsupported"
    }

    function signalIconName(signal: int): string {
        if (signal <= 20)
            return "network-wireless-signal-none"
        if (signal <= 40)
            return "network-wireless-signal-low"
        if (signal <= 60)
            return "network-wireless-signal-ok"
        if (signal <= 80)
            return "network-wireless-signal-good"
        return "network-wireless-signal-excellent"
    }

    function acquireScanner(): void {
        const device = root.visible && root.wifiControlAvailable
            && Networking.wifiEnabled ? root.selectedWifiDevice : null
        root.releaseScanner()
        if (!device)
            return

        root.scannerDevice = device
        if (root.scannerDevice.scannerEnabled)
            return

        root.scannerDevice.scannerEnabled = true
        root.scannerOwnedByPanel = true
    }

    function releaseScanner(): void {
        const device = root.scannerDevice
        const ownedByPanel = root.scannerOwnedByPanel
        root.scannerDevice = null
        root.scannerOwnedByPanel = false
        if (device && ownedByPanel)
            device.scannerEnabled = false
    }

    function cancelPasswordPrompt(): void {
        root.passwordText = ""
        root.passwordSsid = ""
        root.passwordUpdatesKnownPsk = false
    }

    function clearTransientConnectionState(): void {
        root.cancelPasswordPrompt()
        root.actionSsid = ""
        root.actionSawStateChanging = false
        root.failureSsid = ""
        root.failureText = ""
        root.failureNeedsPassword = false
    }

    function openPasswordPrompt(ssid, updateKnownPsk: bool): void {
        const targetSsid = String(ssid || "")
        if (targetSsid === "")
            return
        if (root.passwordSsid !== targetSsid)
            root.passwordText = ""
        root.failureSsid = ""
        root.failureText = ""
        root.failureNeedsPassword = false
        root.passwordUpdatesKnownPsk = updateKnownPsk
        root.passwordSsid = targetSsid
    }

    function setInlineFailure(ssid, message): void {
        root.actionSsid = ""
        root.actionSawStateChanging = false
        root.failureSsid = String(ssid || "")
        root.failureText = String(message || "Failed to connect")
        root.failureNeedsPassword = false
    }

    function beginConnection(network, usePsk: bool, passphrase): void {
        if (!network || root.actionSsid !== "")
            return

        const ssid = String(network.name || "")
        if (ssid === "" || network.connected)
            return

        root.failureSsid = ""
        root.failureText = ""
        root.failureNeedsPassword = false
        root.actionSsid = ssid
        root.actionSawStateChanging = Boolean(network.stateChanging)

        if (usePsk)
            network.connectWithPsk(passphrase)
        else
            network.connect()
    }

    function activateNetwork(ssid): void {
        if (root.actionSsid !== "")
            return

        const targetSsid = String(ssid || "")
        if (root.passwordSsid === targetSsid) {
            passwordInput.forceActiveFocus()
            return
        }
        const retryNeedsPassword = root.failureSsid === targetSsid
            && root.failureNeedsPassword
        root.cancelPasswordPrompt()

        const network = root.networkForSsid(targetSsid)
        if (!network) {
            root.setInlineFailure(targetSsid, "Network unavailable")
            return
        }
        if (network.connected)
            return

        const security = Number(network.security)
        if (retryNeedsPassword && root.isPskSecurity(security)) {
            root.openPasswordPrompt(targetSsid, true)
        } else if (network.known || root.isPasswordlessSecurity(security)) {
            root.beginConnection(network, false, "")
        } else if (root.isPskSecurity(security)) {
            root.openPasswordPrompt(targetSsid, false)
        } else {
            root.setInlineFailure(targetSsid, root.isEnterpriseSecurity(security)
                ? "Enterprise Wi-Fi unsupported" : "Unsupported security")
        }
    }

    function forgetNetwork(ssid): void {
        const targetSsid = String(ssid || "")
        const network = root.networkForSsid(targetSsid)
        if (!network || !network.known)
            return

        if (root.passwordSsid === targetSsid)
            root.cancelPasswordPrompt()
        if (root.failureSsid === targetSsid) {
            root.failureSsid = ""
            root.failureText = ""
            root.failureNeedsPassword = false
        }
        if (root.actionSsid === targetSsid) {
            root.actionSsid = ""
            root.actionSawStateChanging = false
        }

        network.forget()
    }

    function submitPassword(): void {
        if (root.actionSsid !== "" || root.passwordSsid === ""
                || root.passwordText.length === 0)
            return

        const ssid = root.passwordSsid
        const passphrase = root.passwordText
        const replaceStoredPsk = root.passwordUpdatesKnownPsk
        root.cancelPasswordPrompt()

        const network = root.networkForSsid(ssid)
        if (!network) {
            root.setInlineFailure(ssid, "Network unavailable")
            return
        }
        if (network.connected)
            return
        if (network.known && !replaceStoredPsk) {
            root.beginConnection(network, false, "")
            return
        }
        if (!root.isPskSecurity(Number(network.security))) {
            root.setInlineFailure(ssid, "Unsupported security")
            return
        }
        root.beginConnection(network, true, passphrase)
    }

    function failureMessage(reason): string {
        if (reason === ConnectionFailReason.NoSecrets)
            return "Password required"
        if (reason === ConnectionFailReason.WifiAuthTimeout)
            return "Wrong password"
        if (reason === ConnectionFailReason.WifiNetworkLost)
            return "Network lost"
        if (reason === ConnectionFailReason.WifiClientDisconnected)
            return "Disconnected"
        if (reason === ConnectionFailReason.WifiClientFailed)
            return "Connection failed"
        return "Failed to connect"
    }

    function failConnection(reason): void {
        const ssid = root.actionSsid
        if (ssid === "")
            return

        const network = root.networkForSsid(ssid)
        const security = network ? Number(network.security) : WifiSecurityType.Unknown
        const needsPassword = root.isPskSecurity(security)
            && (reason === ConnectionFailReason.NoSecrets
                || reason === ConnectionFailReason.WifiAuthTimeout)
        root.setInlineFailure(ssid, root.failureMessage(reason))
        root.failureNeedsPassword = needsPassword
        if (needsPassword && root.visible) {
            root.passwordText = ""
            root.passwordUpdatesKnownPsk = true
            root.passwordSsid = ssid
        }
    }

    function finishConnection(): void {
        root.cancelPasswordPrompt()
        root.actionSsid = ""
        root.actionSawStateChanging = false
        root.failureSsid = ""
        root.failureText = ""
        root.failureNeedsPassword = false
    }

    function validateTransientTargets(): void {
        if (root.passwordSsid !== "" && !root.networkForSsid(root.passwordSsid))
            root.cancelPasswordPrompt()
        if (root.actionSsid !== "" && !root.networkForSsid(root.actionSsid))
            root.setInlineFailure(root.actionSsid, "Network unavailable")
    }

    function connectivityLabel(): string {
        if (!root.backendAvailable)
            return "Unknown"
        if (Networking.connectivity === NetworkConnectivity.Full)
            return "Connected"
        if (Networking.connectivity === NetworkConnectivity.Limited)
            return "Limited"
        if (Networking.connectivity === NetworkConnectivity.Portal)
            return "Captive portal"
        if (Networking.connectivity === NetworkConnectivity.None)
            return "Offline"
        return "Unknown"
    }

    function signalPercent(network): int {
        if (!network)
            return 0
        const signal = Number(network.signalStrength)
        if (!isFinite(signal))
            return 0
        return Math.round(Math.max(0, Math.min(1, signal)) * 100)
    }

    function wiredConnectionName(device): string {
        if (!device || !device.network)
            return "Ethernet"
        return root.cleanText(device.network.name, "Ethernet")
    }

    function linkSpeedLabel(device): string {
        if (!device)
            return ""
        const speed = Number(device.linkSpeed)
        return isFinite(speed) && speed > 0 ? Math.round(speed) + " Mb/s" : ""
    }

    function toggleWifi(): void {
        if (root.wifiControlAvailable)
            Networking.wifiEnabled = !Networking.wifiEnabled
    }

    onVisibleChanged: {
        if (visible) {
            root.acquireScanner()
            if (root.passwordSsid !== "")
                Qt.callLater(function() { passwordInput.forceActiveFocus() })
        } else {
            root.releaseScanner()
            root.cancelPasswordPrompt()
        }
    }

    onSelectedWifiDeviceChanged: {
        root.releaseScanner()
        root.clearTransientConnectionState()
        root.acquireScanner()
    }

    onWifiNetworkObjectsChanged:
        Qt.callLater(root.validateTransientTargets)

    onPasswordSsidChanged: {
        if (passwordSsid !== "" && root.visible)
            Qt.callLater(function() { passwordInput.forceActiveFocus() })
    }

    Component.onDestruction: {
        root.releaseScanner()
        root.cancelPasswordPrompt()
    }

    Connections {
        target: Networking

        function onWifiEnabledChanged(): void {
            if (Networking.wifiEnabled)
                root.acquireScanner()
            else {
                root.releaseScanner()
                root.clearTransientConnectionState()
            }
        }

        function onWifiHardwareEnabledChanged(): void {
            if (Networking.wifiHardwareEnabled)
                root.acquireScanner()
            else {
                root.releaseScanner()
                root.clearTransientConnectionState()
            }
        }
    }

    Connections {
        id: actionConnectionSignals

        target: root.actionSsid !== ""
            ? root.networkForSsid(root.actionSsid) : null

        function onConnectionFailed(reason): void {
            root.failConnection(reason)
        }

        function onConnectedChanged(): void {
            const network = root.networkForSsid(root.actionSsid)
            if (network && network.connected)
                root.finishConnection()
        }

        function onStateChangingChanged(): void {
            const network = root.networkForSsid(root.actionSsid)
            if (!network)
                return
            if (network.stateChanging)
                root.actionSawStateChanging = true
        }

        function onStateChanged(): void {
            const network = root.networkForSsid(root.actionSsid)
            if (network && network.state === ConnectionState.Connected)
                root.finishConnection()
        }
    }

    implicitHeight: content.implicitHeight + root.metrics.panelPadding * 2

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
                text: "Network"
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
                    text: "Status"
                    color: root.textColor
                    font.pixelSize: root.metrics.informationLabelFontSize
                    font.weight: root.metrics.informationLabelFontWeight
                }

                Text {
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    text: root.connectivityLabel()
                    color: root.theme.textMuted
                    font.pixelSize: root.metrics.informationValueFontSize
                    font.weight: root.metrics.informationValueFontWeight
                }
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
                visible: root.wiredDevices.length > 0
            }

            SectionHeading {
                metrics: root.metrics
                theme: root.theme
                visible: root.wiredDevices.length > 0
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: "WIRED"
                verticalAlignment: Text.AlignVCenter
            }

            Column {
                width: parent.width
                spacing: root.metrics.rowSpacing
                visible: root.wiredDevices.length > 0

                Repeater {
                    model: root.wiredDevices

                    Rectangle {
                        id: wiredRow

                        required property var modelData
                        readonly property bool deviceConnected:
                            Boolean(wiredRow.modelData && wiredRow.modelData.connected)
                        readonly property bool linkAvailable:
                            Boolean(wiredRow.modelData && wiredRow.modelData.hasLink)

                        width: content.width
                        height: root.metrics.twoLineRowHeight
                        radius: root.metrics.rowRadius
                        color: root.theme.normalFill

                        Text {
                            anchors {
                                left: parent.left
                                right: wiredState.left
                                top: parent.top
                                leftMargin: root.metrics.rowSidePadding
                                rightMargin: root.metrics.rowSidePadding
                                topMargin: root.metrics.contentGap
                            }
                            text: wiredRow.deviceConnected
                                ? root.wiredConnectionName(wiredRow.modelData) : "Ethernet"
                            color: root.textColor
                            font.pixelSize: root.metrics.bodyFontSize
                            font.weight: root.metrics.overlayFontWeight
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            id: wiredState

                            anchors {
                                right: parent.right
                                top: parent.top
                                rightMargin: root.metrics.rowSidePadding
                                topMargin: root.metrics.contentGap
                            }
                            text: wiredRow.deviceConnected
                                ? root.linkSpeedLabel(wiredRow.modelData)
                                : (wiredRow.linkAvailable ? "Link available" : "Disconnected")
                            color: root.textColor
                            font.pixelSize: root.metrics.bodyFontSize
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            anchors {
                                left: parent.left
                                right: parent.right
                                bottom: parent.bottom
                                leftMargin: root.metrics.rowSidePadding
                                rightMargin: root.metrics.rowSidePadding
                                bottomMargin: root.metrics.contentGap
                            }
                            text: root.cleanText(wiredRow.modelData
                                ? wiredRow.modelData.name : "", "Unknown device")
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.detailFontSize
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                    }
                }
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
                    text: "Wi-Fi"
                    color: root.textColor
                    font.pixelSize: root.metrics.bodyFontSize
                    font.weight: root.metrics.overlayFontWeight
                }

                Item {
                    id: wifiToggle

                    width: wifiToggleContent.implicitWidth
                    height: root.metrics.compactRowHeight
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    opacity: root.wifiControlAvailable
                        ? 1.0 : root.metrics.disabledInteractiveOpacity

                    Row {
                        id: wifiToggleContent

                        anchors.centerIn: parent
                        spacing: root.metrics.contentGap

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.wifiControlAvailable
                                ? (Networking.wifiEnabled ? "On" : "Off") : "Unavailable"
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.detailFontSize
                        }

                        ToggleSwitch {
                            metrics: root.metrics
                            theme: root.theme
                            checked: root.wifiControlAvailable
                                && Networking.wifiEnabled
                            interactive: false
                            enabled: root.wifiControlAvailable
                        }
                    }

                    MouseArea {
                        id: wifiToggleMouse

                        anchors.fill: parent
                        enabled: root.wifiControlAvailable
                        hoverEnabled: true
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.toggleWifi()
                    }
                }
            }

            Text {
                visible: root.wifiDevices.length === 0
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: root.backendAvailable
                    ? "No Wi-Fi device" : "NetworkManager unavailable"
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                wrapMode: Text.NoWrap
            }

            Column {
                width: parent.width
                spacing: root.metrics.rowSpacing
                visible: root.wifiDevices.length > 0

                Repeater {
                    model: root.wifiDevices

                    Rectangle {
                        id: wifiRow

                        required property var modelData
                        readonly property var currentNetwork:
                            root.connectedWifiNetwork(wifiRow.modelData)
                        readonly property bool deviceConnected:
                            Boolean(wifiRow.modelData && wifiRow.modelData.connected
                                && wifiRow.currentNetwork)

                        width: content.width
                        height: root.metrics.twoLineRowHeight
                        radius: root.metrics.rowRadius
                        color: root.theme.normalFill

                        Text {
                            anchors {
                                left: parent.left
                                right: wifiState.left
                                top: parent.top
                                leftMargin: root.metrics.rowSidePadding
                                rightMargin: root.metrics.rowSidePadding
                                topMargin: root.metrics.contentGap
                            }
                            text: wifiRow.deviceConnected
                                ? root.cleanText(wifiRow.currentNetwork.name, "Connected")
                                : "Not connected"
                            color: root.textColor
                            font.pixelSize: root.metrics.bodyFontSize
                            font.weight: root.metrics.overlayFontWeight
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            id: wifiState

                            anchors {
                                right: parent.right
                                top: parent.top
                                rightMargin: root.metrics.rowSidePadding
                                topMargin: root.metrics.contentGap
                            }
                            text: wifiRow.deviceConnected
                                ? root.signalPercent(wifiRow.currentNetwork) + "%" : ""
                            color: root.textColor
                            font.pixelSize: root.metrics.bodyFontSize
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            anchors {
                                left: parent.left
                                right: parent.right
                                bottom: parent.bottom
                                leftMargin: root.metrics.rowSidePadding
                                rightMargin: root.metrics.rowSidePadding
                                bottomMargin: root.metrics.contentGap
                            }
                            text: root.cleanText(wifiRow.modelData
                                ? wifiRow.modelData.name : "", "Unknown device")
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.detailFontSize
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                    }
                }
            }

            PanelSeparator {
                metrics: root.metrics
                theme: root.theme
                visible: root.wifiControlAvailable && Networking.wifiEnabled
            }

            SectionHeading {
                metrics: root.metrics
                theme: root.theme
                visible: root.wifiControlAvailable && Networking.wifiEnabled
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: "AVAILABLE NETWORKS"
                verticalAlignment: Text.AlignVCenter
            }

            ListView {
                id: wifiNetworkList

                readonly property int displayedRows:
                    Math.min(6, root.wifiNetworks.length)

                visible: root.wifiControlAvailable && Networking.wifiEnabled
                    && root.wifiNetworks.length > 0
                width: parent.width
                height: visible ? displayedRows * root.metrics.compactRowHeight
                    + Math.max(0, displayedRows - 1) * spacing : 0
                spacing: root.metrics.rowSpacing
                clip: true
                interactive: contentHeight > height
                boundsBehavior: Flickable.StopAtBounds
                model: root.wifiNetworks

                delegate: Rectangle {
                    id: networkRow

                    required property var modelData
                    readonly property bool selected:
                        Boolean(networkRow.modelData.connected)
                    readonly property bool actionable: !networkRow.selected
                        && (networkRow.modelData.known
                            || root.isPasswordlessSecurity(networkRow.modelData.security)
                            || root.isPskSecurity(networkRow.modelData.security))
                    readonly property bool connecting: root.actionSsid !== ""
                        && root.actionSsid === networkRow.modelData.ssid
                    readonly property bool failed: root.failureText !== ""
                        && root.failureSsid === networkRow.modelData.ssid

                    width: wifiNetworkList.width
                    height: root.metrics.compactRowHeight
                    radius: root.metrics.rowRadius
                    color: networkRow.selected ? root.theme.activeFill
                        : (networkRowMouse.containsMouse
                            ? root.theme.hoverFill : "transparent")

                    Image {
                        id: networkSignalIcon

                        anchors {
                            left: parent.left
                            leftMargin: root.metrics.rowSidePadding
                            verticalCenter: parent.verticalCenter
                        }
                        width: root.metrics.standardIconSize
                        height: root.metrics.standardIconSize
                        source: Quickshell.iconPath(
                            root.signalIconName(networkRow.modelData.signal))
                        sourceSize: Qt.size(width, height)
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                    }

                    Text {
                        anchors {
                            left: networkSignalIcon.right
                            right: networkRowStatus.left
                            leftMargin: root.metrics.contentGap
                            rightMargin: root.metrics.contentGap
                            verticalCenter: parent.verticalCenter
                        }
                        text: networkRow.modelData.ssid
                        textFormat: Text.PlainText
                        color: networkRow.failed ? root.theme.danger
                            : root.textColor
                        font.pixelSize: root.metrics.bodyFontSize
                        font.weight: networkRow.selected
                            ? root.metrics.overlayFontWeight : Font.Normal
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        id: networkRowStatus

                        anchors {
                            right: forgetAction.visible
                                ? forgetAction.left : parent.right
                            rightMargin: forgetAction.visible
                                ? root.metrics.contentGap : root.metrics.rowSidePadding
                            verticalCenter: parent.verticalCenter
                        }
                        width: forgetAction.visible ? root.metrics.scaled(82)
                            : (networkRow.connecting || networkRow.failed
                                ? root.metrics.scaled(94) : root.metrics.scaled(88))
                        text: {
                            if (networkRow.connecting)
                                return "Connecting…"
                            if (networkRow.failed)
                                return root.failureText
                            if (networkRow.selected)
                                return "Connected"
                            return networkRow.modelData.signal + "% · "
                                + root.securityLabel(networkRow.modelData.security)
                        }
                        textFormat: Text.PlainText
                        color: networkRow.failed ? root.theme.danger
                            : root.textColor
                        opacity: networkRow.connecting || networkRow.failed
                            || networkRow.selected ? 1.0
                                : root.metrics.informationalMutedOpacity
                        font.pixelSize: root.metrics.captionFontSize
                        font.weight: networkRow.connecting || networkRow.selected
                            ? root.metrics.overlayFontWeight : Font.Normal
                        horizontalAlignment: Text.AlignRight
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }

                    Rectangle {
                        id: forgetAction

                        visible: Boolean(networkRow.modelData.known)
                        z: 2
                        width: visible ? root.metrics.inlineTextActionWidth : 0
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
                            text: "Forget"
                            color: root.theme.danger
                            font.pixelSize: root.metrics.captionFontSize
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.NoWrap
                        }

                        MouseArea {
                            id: forgetMouse

                            anchors.fill: parent
                            enabled: root.actionSsid === ""
                            hoverEnabled: true
                            cursorShape: enabled
                                ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.forgetNetwork(networkRow.modelData.ssid)
                        }
                    }

                    MouseArea {
                        id: networkRowMouse

                        z: 1
                        anchors.fill: parent
                        enabled: root.actionSsid === ""
                        hoverEnabled: true
                        cursorShape: networkRow.actionable
                            ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: root.activateNetwork(networkRow.modelData.ssid)
                    }
                }
            }

            Text {
                visible: root.wifiControlAvailable && Networking.wifiEnabled
                    && root.wifiNetworks.length === 0
                width: parent.width
                height: visible ? root.metrics.compactControlHeight : 0
                text: "No networks found"
                color: root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                wrapMode: Text.NoWrap
            }

            Rectangle {
                id: passwordPrompt

                visible: root.passwordSsid !== ""
                width: parent.width
                height: visible ? passwordContent.implicitHeight
                    + root.metrics.overlayPadding : 0
                radius: root.metrics.rowRadius
                color: root.theme.normalFill

                Column {
                    id: passwordContent

                    anchors {
                        left: parent.left
                        right: parent.right
                        top: parent.top
                        margins: root.metrics.rowSidePadding
                    }
                    spacing: root.metrics.contentGap

                    Text {
                        width: parent.width
                        text: "Password for " + root.passwordSsid
                        textFormat: Text.PlainText
                        color: root.textColor
                        font.pixelSize: root.metrics.bodyFontSize
                        font.weight: root.metrics.overlayFontWeight
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        visible: root.failureSsid === root.passwordSsid
                            && root.failureText !== ""
                        width: parent.width
                        text: root.failureText
                        textFormat: Text.PlainText
                        color: root.theme.danger
                        font.pixelSize: root.metrics.detailFontSize
                        wrapMode: Text.NoWrap
                    }

                    Rectangle {
                        width: parent.width
                        height: root.metrics.textFieldHeight
                        radius: root.metrics.rowRadius
                        color: passwordInput.activeFocus
                            ? root.theme.hoverFill : root.theme.normalFill
                        border.width: root.metrics.controlOutlineThickness
                        border.color: passwordInput.activeFocus
                            ? root.theme.focus : root.theme.separator

                        Text {
                            anchors {
                                left: parent.left
                                leftMargin: root.metrics.rowSidePadding
                                verticalCenter: parent.verticalCenter
                            }
                            visible: passwordInput.text.length === 0
                                && !passwordInput.activeFocus
                            text: "Password"
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.bodyFontSize
                        }

                        TextInput {
                            id: passwordInput

                            anchors {
                                fill: parent
                                leftMargin: root.metrics.rowSidePadding
                                rightMargin: root.metrics.rowSidePadding
                            }
                            text: root.passwordSsid !== ""
                                ? root.passwordText : ""
                            color: root.textColor
                            selectionColor: root.theme.activeFill
                            selectedTextColor: root.theme.text
                            font.pixelSize: root.metrics.bodyFontSize
                            verticalAlignment: TextInput.AlignVCenter
                            echoMode: TextInput.Password
                            clip: true
                            enabled: root.actionSsid === ""

                            onTextChanged: {
                                if (root.passwordSsid !== ""
                                        && text !== root.passwordText)
                                    root.passwordText = text
                            }
                            onAccepted: root.submitPassword()
                            Keys.onEscapePressed: root.cancelPasswordPrompt()
                        }
                    }

                    Row {
                        width: parent.width
                        height: root.metrics.compactControlHeight
                        spacing: root.metrics.contentGap

                        Rectangle {
                            width: (parent.width - parent.spacing) / 2
                            height: parent.height
                            radius: root.metrics.rowRadius
                            color: cancelMouse.containsMouse
                                ? root.theme.hoverFill : root.theme.normalFill

                            Text {
                                anchors.fill: parent
                                text: "Cancel"
                                color: root.textColor
                                font.pixelSize: root.metrics.bodyFontSize
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.NoWrap
                            }

                            MouseArea {
                                id: cancelMouse

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.cancelPasswordPrompt()
                            }
                        }

                        Rectangle {
                            readonly property bool canSubmit:
                                root.passwordText.length > 0
                                && root.actionSsid === ""

                            width: (parent.width - parent.spacing) / 2
                            height: parent.height
                            radius: root.metrics.rowRadius
                            color: canSubmit
                                ? root.theme.activeFill : root.theme.normalFill
                            opacity: canSubmit ? 1.0
                                : root.metrics.disabledInteractiveOpacity

                            Text {
                                anchors.fill: parent
                                text: "Connect"
                                color: root.textColor
                                font.pixelSize: root.metrics.bodyFontSize
                                font.weight: parent.canSubmit
                                    ? root.metrics.overlayFontWeight : Font.Normal
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.NoWrap
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: parent.canSubmit
                                hoverEnabled: true
                                cursorShape: enabled
                                    ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: root.submitPassword()
                            }
                        }
                    }
                }
            }
        }
    }
}
