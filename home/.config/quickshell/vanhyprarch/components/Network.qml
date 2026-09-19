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
    readonly property int iconSize: root.metrics.dockSystemIconSize

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
        if (!root.backendAvailable
                || Networking.connectivity === NetworkConnectivity.None)
            return "network-disconnected"

        if (Networking.connectivity === NetworkConnectivity.Portal
                || Networking.connectivity === NetworkConnectivity.Limited)
            return "network-limited"

        if (root.connectedWiredDevices.length > 0)
            return "network-wired"

        if (root.strongestWifiNetwork) {
            const signal = root.safeSignalStrength(root.strongestWifiNetwork)
            if (signal <= 0.20)
                return "network-wireless-signal-none"
            if (signal <= 0.40)
                return "network-wireless-signal-low"
            if (signal <= 0.60)
                return "network-wireless-signal-ok"
            if (signal <= 0.80)
                return "network-wireless-signal-good"
            return "network-wireless-signal-excellent"
        }

        return "network-wireless-offline"
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
        if (!network)
            return 0
        const signal = Number(network.signalStrength)
        return isFinite(signal) ? Math.max(0, Math.min(1, signal)) : 0
    }

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath(root.iconName)
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
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
