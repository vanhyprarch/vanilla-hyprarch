import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool enumerationEnabled: true
    property bool loading: false
    property string errorMessage: ""
    readonly property var packages: catalogState.packageStore
    readonly property string pacmanExecutable: "/usr/bin/pacman"
    readonly property string footExecutable: "/usr/bin/foot"
    readonly property string yayExecutable: "/usr/bin/yay"
    readonly property string terminalOperation:
        Quickshell.shellDir + "/helpers/vanhyprarch_terminal_operation"

    function parsePackages(output: string): var {
        const result = []
        const seen = {}
        const lines = String(output || "").split("\n")

        for (const rawLine of lines) {
            const line = String(rawLine).trim()
            if (line === "")
                continue

            const separator = line.indexOf(" ")
            if (separator <= 0 || line.indexOf(" ", separator + 1) >= 0)
                throw new Error("invalid pacman package line")

            const name = line.slice(0, separator)
            const version = line.slice(separator + 1)
            if (name.startsWith("-") || /\s/.test(name)
                    || version === "" || /\s/.test(version)
                    || seen[name] === true)
                throw new Error("invalid or duplicate pacman package")

            seen[name] = true
            result.push({
                name: name,
                version: version
            })
        }

        return result
    }

    function conciseError(output: string): string {
        const text = String(output || "").trim()
        if (text === "")
            return "Could not load installed packages with pacman."
        const lines = text.split("\n")
        const message = String(lines[lines.length - 1]).trim()
        return message.length > 180 ? message.slice(0, 177) + "…" : message
    }

    function finishCatalogLoad(exitCode: int, output: string,
            errorOutput: string): void {
        if (exitCode !== 0) {
            catalogState.packageStore = []
            errorMessage = conciseError(errorOutput)
        } else {
            try {
                catalogState.packageStore = parsePackages(output)
                errorMessage = ""
            } catch (error) {
                catalogState.packageStore = []
                errorMessage = "Could not parse the installed package list."
                console.warn("Failed to parse pacman -Q output: " + error)
            }
        }
        loading = false

        if (catalogProcess.refreshQueued) {
            catalogProcess.refreshQueued = false
            Qt.callLater(root.refreshPackages)
        }
    }

    function refreshPackages(): bool {
        if (!enumerationEnabled)
            return false
        if (catalogProcess.running) {
            catalogProcess.refreshQueued = true
            return false
        }

        loading = true
        errorMessage = ""
        catalogState.packageStore = []
        catalogProcess.startLoad()
        return true
    }

    function isLoadedPackage(packageObject): bool {
        if (packageObject === null || packageObject === undefined
                || typeof packageObject !== "object")
            return false

        for (const loadedPackage of catalogState.packageStore) {
            if (loadedPackage === packageObject)
                return true
        }
        return false
    }

    function commandForPackage(packageObject): var {
        if (!isLoadedPackage(packageObject))
            return []

        return [
            footExecutable,
            "--title=Vanilla HyprArch Remove Package",
            terminalOperation,
            yayExecutable,
            "-Rns",
            "--",
            packageObject.name
        ]
    }

    function executePackage(packageObject): bool {
        const command = commandForPackage(packageObject)
        if (command.length === 0) {
            console.warn("Refusing package removal without a loaded package")
            return false
        }

        Quickshell.execDetached(command)
        return true
    }

    QtObject {
        id: catalogState

        property var packageStore: []
    }

    Process {
        id: catalogProcess

        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property bool resultHandled: false
        property bool refreshQueued: false
        property int lastExitCode: -1

        function startLoad(): void {
            outputText = ""
            errorText = ""
            exitReceived = false
            stdoutReceived = false
            stderrReceived = false
            resultHandled = false
            lastExitCode = -1
            command = [root.pacmanExecutable, "-Q"]
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stdoutReceived
                    || !stderrReceived)
                return

            resultHandled = true
            root.finishCatalogLoad(lastExitCode, outputText, errorText)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                catalogProcess.outputText = text
                catalogProcess.stdoutReceived = true
                catalogProcess.maybeFinish()
            }
        }

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                catalogProcess.errorText = text
                catalogProcess.stderrReceived = true
                catalogProcess.maybeFinish()
            }
        }

        onExited: function(exitCode) {
            catalogProcess.lastExitCode = exitCode
            catalogProcess.exitReceived = true
            catalogProcess.maybeFinish()
        }
    }
}
