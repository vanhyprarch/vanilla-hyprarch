pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Networking

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
    property color hoverColor: root.theme.hover

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

    component SectionHeading: Text {
        width: content.width
        color: root.textColor
        font.pixelSize: 13
        font.weight: Font.Medium
        wrapMode: Text.NoWrap
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
                text: "Network"
                color: root.textColor
                font.pixelSize: 16
                font.bold: true
                wrapMode: Text.NoWrap
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
            }

            Item {
                width: parent.width
                height: root.rowHeight

                Text {
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    text: "Status"
                    color: root.textColor
                    font.pixelSize: 13
                    font.weight: Font.Medium
                }

                Text {
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    text: root.connectivityLabel()
                    color: root.textColor
                    font.pixelSize: 13
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
                visible: root.wiredDevices.length > 0
            }

            SectionHeading {
                visible: root.wiredDevices.length > 0
                height: visible ? root.rowHeight : 0
                text: "Wired"
                verticalAlignment: Text.AlignVCenter
            }

            Column {
                width: parent.width
                spacing: 4
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
                        height: root.rowHeight + 12
                        radius: root.popupRadius / 2
                        color: root.secondaryColor

                        Text {
                            anchors {
                                left: parent.left
                                right: wiredState.left
                                top: parent.top
                                leftMargin: 8
                                rightMargin: 8
                                topMargin: 6
                            }
                            text: wiredRow.deviceConnected
                                ? root.wiredConnectionName(wiredRow.modelData) : "Ethernet"
                            color: root.textColor
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            id: wiredState

                            anchors {
                                right: parent.right
                                top: parent.top
                                rightMargin: 8
                                topMargin: 6
                            }
                            text: wiredRow.deviceConnected
                                ? root.linkSpeedLabel(wiredRow.modelData)
                                : (wiredRow.linkAvailable ? "Link available" : "Disconnected")
                            color: root.textColor
                            font.pixelSize: 12
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            anchors {
                                left: parent.left
                                right: parent.right
                                bottom: parent.bottom
                                leftMargin: 8
                                rightMargin: 8
                                bottomMargin: 5
                            }
                            text: root.cleanText(wiredRow.modelData
                                ? wiredRow.modelData.name : "", "Unknown device")
                            color: root.textColor
                            opacity: 0.75
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.secondaryColor
            }

            Item {
                width: parent.width
                height: root.rowHeight

                Text {
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                    }
                    text: "Wi-Fi"
                    color: root.textColor
                    font.pixelSize: 13
                    font.weight: Font.Medium
                }

                Rectangle {
                    id: wifiToggle

                    width: root.wifiControlAvailable ? 52 : 104
                    height: 24
                    anchors {
                        right: parent.right
                        verticalCenter: parent.verticalCenter
                    }
                    radius: root.popupRadius / 2
                    color: root.wifiControlAvailable && Networking.wifiEnabled
                        ? root.accentColor
                        : (wifiToggleMouse.containsMouse && root.wifiControlAvailable
                            ? root.hoverColor : root.secondaryColor)
                    opacity: root.wifiControlAvailable ? 1.0 : 0.55

                    Text {
                        anchors.fill: parent
                        text: root.wifiControlAvailable
                            ? (Networking.wifiEnabled ? "On" : "Off") : "Unavailable"
                        color: root.wifiControlAvailable && Networking.wifiEnabled
                            ? root.backgroundColor : root.textColor
                        font.pixelSize: 12
                        font.weight: root.wifiControlAvailable && Networking.wifiEnabled
                            ? Font.Medium : Font.Normal
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.NoWrap
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
                height: visible ? 18 : 0
                text: root.backendAvailable
                    ? "No Wi-Fi device" : "NetworkManager unavailable"
                color: root.textColor
                opacity: 0.75
                font.pixelSize: 12
                wrapMode: Text.NoWrap
            }

            Column {
                width: parent.width
                spacing: 4
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
                        height: root.rowHeight + 12
                        radius: root.popupRadius / 2
                        color: root.secondaryColor

                        Text {
                            anchors {
                                left: parent.left
                                right: wifiState.left
                                top: parent.top
                                leftMargin: 8
                                rightMargin: 8
                                topMargin: 6
                            }
                            text: wifiRow.deviceConnected
                                ? root.cleanText(wifiRow.currentNetwork.name, "Connected")
                                : "Not connected"
                            color: root.textColor
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            id: wifiState

                            anchors {
                                right: parent.right
                                top: parent.top
                                rightMargin: 8
                                topMargin: 6
                            }
                            text: wifiRow.deviceConnected
                                ? root.signalPercent(wifiRow.currentNetwork) + "%" : ""
                            color: root.textColor
                            font.pixelSize: 12
                            wrapMode: Text.NoWrap
                        }

                        Text {
                            anchors {
                                left: parent.left
                                right: parent.right
                                bottom: parent.bottom
                                leftMargin: 8
                                rightMargin: 8
                                bottomMargin: 5
                            }
                            text: root.cleanText(wifiRow.modelData
                                ? wifiRow.modelData.name : "", "Unknown device")
                            color: root.textColor
                            opacity: 0.75
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                        }
                    }
                }
            }
        }
    }
}
