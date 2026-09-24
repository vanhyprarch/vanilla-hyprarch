import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property string executable: "vanhyprarch-default-apps"
    property var effective: ({ browser: null, terminal: null, editor: null })
    property var candidates: ({ browser: [], terminal: [], editor: [] })
    property string errorMessage: ""
    property bool ready: false
    readonly property bool busy: operation.running
    property bool refreshPending: false

    function refresh(): void {
        if (busy) {
            refreshPending = true
            return
        }
        ready = false
        operation.startOperation([executable, "status"], "status")
    }

    function select(category: string, desktopId: string): bool {
        if (busy || ["browser", "terminal", "editor"].indexOf(category) < 0
                || candidates[category].indexOf(desktopId) < 0)
            return false
        errorMessage = ""
        operation.startOperation([executable, "select", category, desktopId], "select")
        return true
    }

    function finish(exitCode: int, output: string): void {
        ready = true
        if (exitCode !== 0) {
            if (operation.kind === "status") {
                effective = ({ browser: null, terminal: null, editor: null })
                candidates = ({ browser: [], terminal: [], editor: [] })
            }
            errorMessage = operation.errorOutput.trim().replace(
                /^vanhyprarch-default-apps:\s*/, "")
                || "Could not read or change the effective default"
        } else {
            try {
                const document = JSON.parse(output)
                if (document.version !== 1 || !document.effective
                        || !document.candidates
                        || ["browser", "terminal", "editor"].some(key =>
                            !Array.isArray(document.candidates[key])))
                    throw new Error("invalid Default Apps response")
                effective = document.effective
                candidates = document.candidates
                errorMessage = ""
            } catch (error) {
                errorMessage = "Invalid Default Apps status"
            }
        }
        if (refreshPending) {
            refreshPending = false
            Qt.callLater(root.refresh)
        }
    }

    Process {
        id: operation

        property string output: ""
        property string kind: ""
        property string errorOutput: ""
        property bool exited: false
        property bool collected: false
        property bool errorCollected: false
        property int code: -1

        function startOperation(argv: var, nextKind: string): void {
            output = ""
            kind = nextKind
            errorOutput = ""
            exited = false
            collected = false
            errorCollected = false
            code = -1
            command = argv
            running = true
        }

        function complete(): void {
            if (exited && collected && errorCollected)
                root.finish(code, output)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                operation.output = text
                operation.collected = true
                operation.complete()
            }
        }

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                operation.errorOutput = text
                operation.errorCollected = true
                operation.complete()
            }
        }

        onExited: function(exitCode) {
            operation.code = exitCode
            operation.exited = true
            operation.complete()
        }
    }
}
