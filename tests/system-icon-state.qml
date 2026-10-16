import QtQuick
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Networking
import "components"

ShellRoot {
    id: test
    property int checks: 0

    component BluetoothState: Item {
        id: root
@BLUETOOTH_STATE@
    }
    component NetworkState: Item {
        id: root
@NETWORK_STATE@
    }
    component AudioState: Item {
        id: root
@AUDIO_STATE@
    }

    QtObject { id: device; property bool connected: false }
    QtObject {
        id: adapter
        property bool enabled: false
        property int state: BluetoothAdapterState.Disabled
        property bool discovering: false
        property var devices: ({ values: [device] })
    }
    BluetoothState { id: bluetooth; adapter: adapter }

    QtObject {
        id: wifiNetwork
        property bool connected: true
        property var signalStrength: 1.0
    }
    QtObject {
        id: wifi
        property int type: DeviceType.Wifi
        property bool connected: true
        property var networks: ({ values: [wifiNetwork] })
    }
    QtObject {
        id: ethernet
        property int type: DeviceType.Wired
        property bool connected: false
    }
    NetworkState { id: network; devices: [wifi, ethernet] }

    QtObject {
        id: output
        property bool muted: false
        property real volume: 1.0
    }
    QtObject { id: sink; property var audio: output }
    AudioState { id: audio; sink: sink }

    VisualMetrics { id: metrics }
    Theme { id: theme; metrics: metrics }
    QtObject {
        id: appearance
        property bool darkMode: false
        property bool ready: true
        property bool busy: false
        function toggleMode() { darkMode = !darkMode }
    }
    ThemeToggle { id: themeToggle; theme: theme; metrics: metrics; controller: appearance }

    IdleController { id: idleController; checksEnabled: false; ready: true }
    PowerIdle {
        id: powerIdle
        controller: idleController
        theme: theme
        metrics: metrics
        targetScreen: null
        focusCoordinator: null
    }

    function check(actual, expected, description) {
        checks++
        if (actual !== expected)
            throw new Error(description + ": " + actual + " != " + expected)
    }
    function themeIcon() {
        return themeToggle.children.find(child => child.iconName !== undefined).iconName
    }
    function idleIcon() {
        return powerIdle.children.find(child => child.iconName !== undefined)
    }

    Timer {
        interval: 0
        running: true
        onTriggered: {
            check(bluetooth.iconName, "bluetooth-off", "disabled")
            device.connected = true
            adapter.discovering = true
            check(bluetooth.iconName, "bluetooth-off", "power beats stale discovery/connection")
            adapter.enabled = true
            adapter.state = BluetoothAdapterState.Enabled
            check(bluetooth.iconName, "bluetooth-searching", "real discovery beats connected")
            adapter.discovering = false
            check(bluetooth.iconName, "bluetooth-connected", "connected")
            device.connected = false
            check(bluetooth.iconName, "bluetooth", "enabled idle")
            adapter.discovering = true
            check(bluetooth.iconName, "bluetooth-searching", "discovery without devices")
            adapter.discovering = false
            check(bluetooth.iconName, "bluetooth", "stopped discovery")
            bluetooth.adapter = null
            check(bluetooth.iconName, "bluetooth-off", "missing adapter")

            for (const sample of [[0, "wifi-low"], [33, "wifi-low"], [34, "wifi-high"],
                    [66, "wifi-high"], [67, "wifi"], [100, "wifi"]]) {
                wifiNetwork.signalStrength = sample[0] / 100
                check(network.iconName, sample[1], "Wi-Fi " + sample[0])
            }
            for (const unknown of [undefined, null, NaN, -1, Infinity]) {
                wifiNetwork.signalStrength = unknown
                check(network.iconName, "wifi", "connected with unknown signal")
                check(network.safeSignalStrength(wifiNetwork), -1, "unknown is not a measurement")
            }
            wifi.networks = ({ values: [] })
            check(network.iconName, "wifi", "connected device before access-point discovery")
            wifi.networks = ({ values: [wifiNetwork] })
            ethernet.connected = true
            check(network.iconName, "ethernet-port", "simultaneous wired/Wi-Fi prefers wired")
            wifi.connected = false
            check(network.iconName, "ethernet-port", "wired only")
            ethernet.connected = false
            check(network.iconName, "globe-off", "disconnected")
            network.backendAvailable = false
            check(network.iconName, "globe-off", "missing network backend")
            network.backendAvailable = true
            wifi.connected = true
            wifiNetwork.signalStrength = 0
            check(network.iconName, "wifi-low", "zero signal remains connected")

            for (const sample of [[0, "volume-off"], [1, "volume"], [33, "volume"],
                    [34, "volume-1"], [66, "volume-1"], [67, "volume-2"],
                    [100, "volume-2"], [150, "volume-2"]]) {
                output.volume = sample[0] / 100
                check(audio.iconName, sample[1], "audio " + sample[0])
            }
            output.muted = true
            check(audio.iconName, "volume-off", "mute beats amplification")
            output.muted = false
            audio.sink = null
            check(audio.iconName, "volume-off", "no sink")

            check(themeIcon(), "sun", "current Light mode")
            themeToggle.activate()
            check(themeIcon(), "moon", "reactive Dark mode")
            themeToggle.activate()
            check(themeIcon(), "sun", "reactive Light mode")
            appearance.ready = false
            themeToggle.activate()
            check(themeIcon(), "sun", "unready Appearance cannot toggle")
            appearance.ready = true
            appearance.busy = true
            themeToggle.activate()
            check(themeIcon(), "sun", "busy Appearance cannot toggle")

            check(idleIcon().iconName, "zap", "confirmed Caffeine off")
            check(idleIcon().width, metrics.dockSystemIconSize, "Power & Idle icon width")
            check(idleIcon().height, metrics.dockSystemIconSize, "Power & Idle icon height")
            check(powerIdle.width, metrics.dockSystemControlTarget, "Power & Idle target width")
            check(powerIdle.height, metrics.dockSystemControlTarget, "Power & Idle target height")
            idleController.caffeine = true
            check(idleIcon().iconName, "coffee", "immediate confirmed Caffeine on")
            idleController.ready = false
            check(idleIcon().iconName, "coffee", "retain last confirmed Caffeine state")
            check(idleIcon().opacity, metrics.disabledInteractiveOpacity, "unready opacity")
            idleController.ready = true
            check(idleIcon().opacity, 1.0, "ready opacity")
            idleController.caffeine = false
            check(idleIcon().iconName, "zap", "immediate confirmed Caffeine off")
            console.log("vanhyprarch system icon state self-check passed: " + checks + " checks")
            Qt.quit()
        }
    }
}
