import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool refreshAutostart: true
    property int refreshInterval: 5000
    property string sysfsBluetoothPath: "/sys/class/bluetooth"
    property bool availabilityKnown: false
    property bool hardwareAvailable: false
    property string errorMessage: ""

    readonly property bool busy: detectionProcess.running
    readonly property string detectionHelper:
        Quickshell.shellDir + "/helpers/vanhyprarch_bluetooth_hardware"

    function parseStatus(output: string): bool {
        const lines = String(output || "").trim().split("\n")
        if (lines.length !== 2 || lines[0] !== "version=1")
            throw new Error("invalid Bluetooth hardware status")
        if (lines[1] === "available=true")
            return true
        if (lines[1] === "available=false")
            return false
        throw new Error("invalid Bluetooth hardware availability")
    }

    function refresh(): void {
        if (!root.busy)
            detectionProcess.startCheck()
    }

    function finishCheck(exitCode: int, output: string): void {
        if (exitCode !== 0) {
            root.errorMessage = "Could not inspect Bluetooth hardware"
            return
        }
        try {
            root.hardwareAvailable = root.parseStatus(output)
            root.availabilityKnown = true
            root.errorMessage = ""
        } catch (error) {
            root.errorMessage = "Invalid Bluetooth hardware status"
        }
    }

    Component.onCompleted: {
        if (root.refreshAutostart)
            root.refresh()
    }

    Timer {
        interval: root.refreshInterval
        running: root.refreshAutostart
        repeat: true
        onTriggered: root.refresh()
    }

    Process {
        id: detectionProcess

        property string output: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property int lastExitCode: -1

        function startCheck(): void {
            if (running)
                return
            output = ""
            exitReceived = false
            stdoutReceived = false
            lastExitCode = -1
            command = ["/bin/sh", root.detectionHelper, "status",
                root.sysfsBluetoothPath]
            running = true
        }

        function maybeFinish(): void {
            if (!exitReceived || !stdoutReceived)
                return
            root.finishCheck(lastExitCode, output)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                detectionProcess.output = text
                detectionProcess.stdoutReceived = true
                detectionProcess.maybeFinish()
            }
        }

        onExited: function(exitCode, exitStatus) {
            detectionProcess.lastExitCode = exitCode
            detectionProcess.exitReceived = true
            detectionProcess.maybeFinish()
        }
    }
}
