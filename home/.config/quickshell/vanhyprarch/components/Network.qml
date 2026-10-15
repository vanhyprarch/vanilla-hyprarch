import QtQuick
import Quickshell
import Quickshell.Networking

Item {
    id: root

    required property var theme
    required property var metrics
    required property var targetScreen
    required property var focusCoordinator
    readonly property int buttonSize: root.metrics.dockSystemControlTarget

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
    readonly property var connectedWifiNetworks: root.connectedWifiDevices.map(device =>
        root.connectedWifiNetwork(device)).filter(network => network !== null)
    readonly property var strongestWifiNetwork: {
        let strongest = null
        let strongestSignal = -1
        for (const network of root.connectedWifiNetworks) {
            const signal = root.safeSignalStrength(network)
            if (signal > strongestSignal) {
                strongest = network
                strongestSignal = signal
            }
        }
        return strongest
    }
    readonly property string iconName: {
        if (!root.backendAvailable)
            return "globe-off"

        // Preserve the existing Ethernet-first preference for simultaneous links.
        // Connectivity checks describe Internet reachability, not link presence.
        if (root.connectedWiredDevices.length > 0)
            return "ethernet-port"

        if (root.connectedWifiDevices.length > 0) {
            const signal = root.safeSignalStrength(root.strongestWifiNetwork)
            // Unknown strength stays connected without inventing a percentage.
            if (signal < 0)
                return "wifi"
            const percent = Math.round(signal * 100)
            if (percent <= 33)
                return "wifi-low"
            if (percent <= 66)
                return "wifi-high"
            return "wifi"
        }

        return "globe-off"
    }

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

    function safeSignalStrength(network): real {
        if (!network || typeof network.signalStrength !== "number")
            return -1
        const signal = network.signalStrength
        return isFinite(signal) && signal >= 0 && signal <= 1 ? signal : -1
    }

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    SystemIcon {
        anchors.centerIn: parent
        iconName: root.iconName
        theme: root.theme
        metrics: root.metrics
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.focusCoordinator.toggleDockWindow(networkPanel)
    }

    NetworkPanel {
        id: networkPanel

        theme: root.theme
        metrics: root.metrics
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
        popupAnchorItem: root
    }
}
