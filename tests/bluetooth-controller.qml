import QtQuick
import Quickshell
import Quickshell.Bluetooth
import "@COMPONENTS_URI@"

ShellRoot {
    id: root

    property int firstPairCalls: 0
    property int secondPairCalls: 0
    property var disabledAdapter: ({
        enabled: false,
        state: BluetoothAdapterState.Disabled
    })
    property var enabledAdapter: ({
        enabled: true,
        state: BluetoothAdapterState.Enabled
    })
    property var blockedAdapter: ({
        enabled: false,
        state: BluetoothAdapterState.Blocked
    })
    property var firstRunAdapter: ({
        enabled: false,
        state: BluetoothAdapterState.Disabled
    })
    property var firstDevice: ({
        dbusPath: "/org/bluez/hci0/dev_01_23_45_67_89_AB",
        paired: false,
        bonded: false,
        pairing: false,
        pair: function() { root.firstPairCalls += 1 },
        cancelPair: function() {},
        trusted: false,
        connected: false,
        state: 0
    })
    property var secondDevice: ({
        dbusPath: "/org/bluez/hci0/dev_10_20_30_40_50_60",
        paired: false,
        bonded: false,
        pairing: false,
        pair: function() { root.secondPairCalls += 1 },
        cancelPair: function() {},
        trusted: false,
        connected: false,
        state: 0
    })

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    BluetoothAgentController {
        id: controller
        agentAutostart: false
    }

    BluetoothPowerController {
        id: powerController
        persistenceAutostart: false
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            root.check(powerController.parseStatus("version=1\npower=on\n") === "on",
                "power preference parsing failed")
            let invalidPowerStatusAccepted = false
            try {
                powerController.parseStatus("version=1\npower=enabled\n")
                invalidPowerStatusAccepted = true
            } catch (error) {
            }
            root.check(!invalidPowerStatusAccepted,
                "invalid power preference was accepted")
            root.check(powerController.applyPreferenceTo(
                [root.disabledAdapter, root.blockedAdapter], "on") === 1,
                "saved on preference was not applied exactly once")
            root.check(root.disabledAdapter.enabled,
                "saved on preference did not enable an available adapter")
            root.check(!root.blockedAdapter.enabled,
                "saved on preference changed a blocked adapter")
            root.check(powerController.applyPreferenceTo(
                [root.enabledAdapter, root.blockedAdapter], "off") === 1,
                "saved off preference was not applied exactly once")
            root.check(!root.enabledAdapter.enabled,
                "saved off preference did not disable an available adapter")
            root.check(powerController.applyPreferenceTo(
                [root.firstRunAdapter, root.blockedAdapter], "unset") === 1,
                "missing preference did not apply the default on state")
            root.check(root.firstRunAdapter.enabled,
                "missing preference did not enable an available adapter")
            root.check(!root.blockedAdapter.enabled,
                "missing preference changed a blocked adapter")
            powerController.finishOperation("set", "off", 1, "")
            root.check(powerController.preference === "unset",
                "failed persistence changed the saved preference")
            powerController.finishOperation("set", "off", 0,
                "version=1\npower=off\n")
            root.check(powerController.preference === "off",
                "explicit off did not commit the preference")
            powerController.finishOperation("set", "on", 0,
                "version=1\npower=on\n")
            root.check(powerController.preference === "on",
                "explicit on did not commit the preference")

            const path = root.firstDevice.dbusPath
            root.check(controller.validDevicePath(path), "canonical device path rejected")
            root.check(!controller.validDevicePath("/org/bluez/hci0/dev_bad"),
                "malformed device path accepted")
            root.check(controller.deviceAddressFromPath(path) === "01:23:45:67:89:AB",
                "device address fallback failed")
            root.check(controller.deviceIdentityForPath(path) === "01:23:45:67:89:AB",
                "native-device fallback identity failed")
            root.check(controller.deviceIdentityForPath("/org/bluez/hci0") === "",
                "unusable device identity was accepted")
            root.check(controller.normalizeServiceUuid("110B")
                === "0000110b-0000-1000-8000-00805f9b34fb",
                "16-bit service UUID normalization failed")
            root.check(controller.normalizeServiceUuid("not-a-uuid") === "",
                "malformed service UUID accepted")

            root.check(Quickshell.screens.length > 0,
                "windowless test has no synthetic screen")
            const screenName = Quickshell.screens[0].name
            controller.state = "ready"
            controller.agentSessionGeneration = 7
            controller.pairDevice(root.firstDevice, screenName)
            root.check(root.firstPairCalls === 1, "first pairing intent did not start")
            const firstIntent = controller.pairIntentId
            controller.pairDevice(root.secondDevice, screenName)
            root.check(root.secondPairCalls === 0, "second pairing intent started")
            root.check(controller.pairIntentId === firstIntent,
                "second pairing overwrote the first transaction")
            controller.agentSessionGeneration = 8
            controller.evaluatePairIntent()
            root.check(controller.pairIntentPath === "",
                "stale agent generation retained pairing intent")

            controller.sessionInvalidating = false
            controller.state = "ready"
            controller.currentPrompt = ({
                id: "synthetic-request",
                kind: "requestAuthorization",
                devicePath: path
            })
            controller.promptScreenName = screenName
            controller.pairIntentPath = path
            controller.pairIntentGeneration = controller.agentSessionGeneration
            controller.pairIntentId = "synthetic-intent"
            controller.sendDecision("accept", undefined)
            root.check(controller.state === "error", "IPC failure did not fail session")
            root.check(controller.currentPrompt === null,
                "IPC failure left prompt pending")
            root.check(controller.pairIntentPath === "",
                "IPC failure retained pairing intent")

            console.log("vanhyprarch Bluetooth controller self-check passed")
            Qt.quit()
        }
    }
}
