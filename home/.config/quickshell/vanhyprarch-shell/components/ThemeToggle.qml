import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: root

    required property var theme
    property int buttonSize: 40
    property int iconSize: 28

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    function toggleTheme(): void {
        if (persistenceProcess.operation === "write")
            return

        root.theme.darkMode = !root.theme.darkMode
        const mode = root.theme.darkMode ? "dark" : "light"

        if (persistenceProcess.running) {
            persistenceProcess.pendingMode = mode
            return
        }

        persistenceProcess.startWrite(mode)
    }

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath(root.theme.darkMode
            ? "weather-clear-night"
            : "weather-clear")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggleTheme()
    }

    Process {
        id: persistenceProcess

        property string operation: ""
        property string pendingMode: ""
        property string readOutput: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool resultHandled: false
        property int lastExitCode: -1

        function startRead(): void {
            operation = "read"
            readOutput = ""
            exitReceived = false
            stdoutReceived = false
            resultHandled = false
            lastExitCode = -1
            command = ["sh", "-c",
                "state_file=\"${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch-shell/theme-mode\"; "
                    + "if [ -r \"$state_file\" ]; then cat -- \"$state_file\" 2>/dev/null || true; fi"]
            running = true
        }

        function startWrite(mode: string): void {
            if (running)
                return

            operation = "write"
            command = ["sh", "-c",
                "set -eu; umask 077; "
                    + "state_dir=\"${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch-shell\"; "
                    + "mkdir -p -- \"$state_dir\"; "
                    + "temporary_file=$(mktemp \"$state_dir/.theme-mode.XXXXXX\"); "
                    + "trap 'rm -f -- \"$temporary_file\"' EXIT HUP INT TERM; "
                    + "printf '%s' \"$1\" > \"$temporary_file\"; "
                    + "mv -f -- \"$temporary_file\" \"$state_dir/theme-mode\"; "
                    + "trap - EXIT HUP INT TERM",
                "vanhyprarch-shell-theme", mode]
            running = true
        }

        function maybeFinishRead(): void {
            if (operation !== "read" || resultHandled
                    || !exitReceived || !stdoutReceived)
                return

            resultHandled = true
            if (pendingMode === "" && lastExitCode === 0) {
                if (readOutput === "dark")
                    root.theme.darkMode = true
                else if (readOutput === "light")
                    root.theme.darkMode = false
            }

            operation = ""
            if (pendingMode !== "") {
                Qt.callLater(function() {
                    const mode = persistenceProcess.pendingMode
                    persistenceProcess.pendingMode = ""
                    persistenceProcess.startWrite(mode)
                })
            }
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                persistenceProcess.readOutput = text
                persistenceProcess.stdoutReceived = true
                persistenceProcess.maybeFinishRead()
            }
        }

        onExited: function(exitCode, exitStatus) {
            if (persistenceProcess.operation === "read") {
                persistenceProcess.lastExitCode = exitCode
                persistenceProcess.exitReceived = true
                persistenceProcess.maybeFinishRead()
            } else if (persistenceProcess.operation === "write") {
                if (exitCode !== 0)
                    console.warn("Failed to save shell theme (exit " + exitCode + ")")
                persistenceProcess.operation = ""
            }
        }

        Component.onCompleted: startRead()
    }
}
