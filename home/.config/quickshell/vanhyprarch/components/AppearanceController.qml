import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    signal catalogReady(string mode, var entries)
    signal catalogFailed(string message)
    signal wallpaperRequestFinished(string path, bool success, string message)

    required property var theme
    property bool checksEnabled: true
    property string mode: "light"
    property bool ready: false
    property string errorMessage: ""
    property string currentWallpaper: ""
    property string lightWallpaper: ""
    property string darkWallpaper: ""
    property string lightDirectory: ""
    property string darkDirectory: ""
    property string effectiveHostMode: "unknown"
    property int effectivePortalValue: -1
    property var configuredGtk3Preference: null
    property var effectiveGtk3Preference: null
    property string rendererState: "unknown"
    property bool rendererMatches: false
    property var effectiveWallpapers: ({})

    readonly property string backendCommand: "vanhyprarch-appearance"
    readonly property bool busy: actionProcess.running || statusProcess.running
    readonly property bool catalogBusy: catalogProcess.running
    readonly property bool darkMode: mode === "dark"
    readonly property string effectiveShellMode: theme.darkMode ? "dark" : "light"
    readonly property bool externallyConsistent: ready
        && effectiveShellMode === mode && effectiveHostMode === mode
        && effectivePortalValue === (darkMode ? 1 : 2)
        && configuredGtk3Preference === darkMode
        && effectiveGtk3Preference === darkMode
        && (currentWallpaper === "" || rendererMatches)

    Component.onCompleted: if (checksEnabled)
        Qt.callLater(function() { root.startAction([root.backendCommand, "reconcile"]) })

    function toggleMode(): void {
        requestMode(root.darkMode ? "light" : "dark")
    }

    function requestMode(requestedMode: string): void {
        if (!root.ready || root.busy)
            return
        if (requestedMode !== "light" && requestedMode !== "dark") {
            root.errorMessage = "Rejected an unknown Appearance mode."
            return
        }
        if (requestedMode === root.mode)
            return
        root.startAction([root.backendCommand, "set-mode", requestedMode])
    }

    function setCurrentWallpaper(path: string): bool {
        if (!root.ready || root.busy || path === "")
            return false
        root.errorMessage = ""
        actionProcess.startCommand(
            [root.backendCommand, "set-wallpaper", "current", path],
            "wallpaper", path)
        return true
    }

    function requestCatalog(requestedMode: string): bool {
        if (!root.ready || root.busy || root.catalogBusy)
            return false
        if (["current", "light", "dark"].indexOf(requestedMode) < 0) {
            root.catalogFailed("Rejected an unknown Appearance catalog mode.")
            return false
        }
        catalogProcess.startRead(requestedMode)
        return true
    }

    function startAction(command: var): void {
        if (root.busy)
            return
        root.errorMessage = ""
        actionProcess.startCommand(command, "", "")
    }

    function refreshStatus(preserveError: bool): void {
        if (!root.checksEnabled || root.busy)
            return
        if (!preserveError)
            root.errorMessage = ""
        statusProcess.preserveError = preserveError
        statusProcess.startRead()
    }

    function conciseError(output: string, fallback: string): string {
        const value = String(output || "").trim()
        if (value === "")
            return fallback
        const lines = value.split("\n")
        const message = String(lines[lines.length - 1]).trim()
        return message.length > 180 ? message.slice(0, 177) + "…" : message
    }

    function parseStatus(output: string): var {
        const value = JSON.parse(String(output || ""))
        if (value === null || typeof value !== "object" || value.version !== 1
                || (value.mode !== "light" && value.mode !== "dark")
                || typeof value.initialized !== "boolean"
                || (value.current_wallpaper !== null
                    && typeof value.current_wallpaper !== "string")
                || value.directories === null || typeof value.directories !== "object"
                || typeof value.directories.light !== "string"
                || typeof value.directories.dark !== "string"
                || value.wallpapers === null || typeof value.wallpapers !== "object"
                || value.host === null || typeof value.host !== "object"
                || value.renderer === null || typeof value.renderer !== "object")
            throw new Error("invalid Appearance status schema")

        const expectedPortal = value.mode === "dark" ? 1 : 2
        const expectedHost = value.mode === "dark" ? "prefer-dark" : "prefer-light"
        if (value.host.expected_portal !== expectedPortal
                || value.host.expected_gsettings !== expectedHost
                || value.host.expected_gtk3 !== (value.mode === "dark")
                || (value.host.gtk3_configured !== null
                    && typeof value.host.gtk3_configured !== "boolean")
                || (value.host.gtk3_effective !== null
                    && typeof value.host.gtk3_effective !== "boolean")
                || (value.host.portal !== null
                    && [0, 1, 2].indexOf(value.host.portal) < 0)
                || (value.host.gsettings !== null
                    && ["default", "prefer-light", "prefer-dark"].indexOf(
                        value.host.gsettings) < 0)
                || typeof value.renderer.state !== "string"
                || typeof value.renderer.matches !== "boolean"
                || value.renderer.active === null
                || typeof value.renderer.active !== "object"
                || !Array.isArray(value.errors))
            throw new Error("invalid Appearance effective state")

        function selectedPath(mode) {
            const entry = value.wallpapers[mode]
            if (entry === null || typeof entry !== "object"
                    || (entry.path !== null && typeof entry.path !== "string"))
                throw new Error("invalid Appearance wallpaper state")
            return entry.path === null ? "" : entry.path
        }

        const errors = value.errors
        return {
            mode: value.mode,
            currentWallpaper: value.current_wallpaper === null
                ? "" : String(value.current_wallpaper),
            lightWallpaper: selectedPath("light"),
            darkWallpaper: selectedPath("dark"),
            lightDirectory: value.directories.light,
            darkDirectory: value.directories.dark,
            effectiveHostMode: value.host.gsettings === "prefer-dark" ? "dark"
                : value.host.gsettings === "prefer-light" ? "light" : "unknown",
            effectivePortalValue: value.host.portal === null ? -1 : value.host.portal,
            configuredGtk3Preference: value.host.gtk3_configured,
            effectiveGtk3Preference: value.host.gtk3_effective,
            rendererState: value.renderer.state,
            rendererMatches: value.renderer.matches,
            effectiveWallpapers: value.renderer.active,
            error: errors.length > 0 ? String(errors.join("; ")) : ""
        }
    }

    function parseCatalog(output: string): var {
        const value = JSON.parse(String(output || ""))
        if (value === null || typeof value !== "object" || value.version !== 1
                || (value.mode !== "light" && value.mode !== "dark")
                || typeof value.directory !== "string"
                || !Array.isArray(value.entries))
            throw new Error("invalid Appearance catalog schema")

        const entries = []
        const paths = ({})
        for (const entry of value.entries) {
            if (entry === null || typeof entry !== "object"
                    || typeof entry.filename !== "string"
                    || typeof entry.path !== "string"
                    || typeof entry.uri !== "string"
                    || typeof entry.selected !== "boolean"
                    || entry.filename === "" || entry.path === ""
                    || entry.uri === "" || paths[entry.path])
                throw new Error("invalid Appearance catalog entry")
            paths[entry.path] = true
            entries.push({
                filename: entry.filename,
                path: entry.path,
                uri: entry.uri,
                selected: entry.selected
            })
        }
        return { mode: value.mode, entries: entries }
    }

    function applyStatus(state: var, preserveError: bool): void {
        root.mode = state.mode
        root.theme.darkMode = state.mode === "dark"
        root.currentWallpaper = state.currentWallpaper
        root.lightWallpaper = state.lightWallpaper
        root.darkWallpaper = state.darkWallpaper
        root.lightDirectory = state.lightDirectory
        root.darkDirectory = state.darkDirectory
        root.effectiveHostMode = state.effectiveHostMode
        root.effectivePortalValue = state.effectivePortalValue
        root.configuredGtk3Preference = state.configuredGtk3Preference
        root.effectiveGtk3Preference = state.effectiveGtk3Preference
        root.rendererState = state.rendererState
        root.rendererMatches = state.rendererMatches
        root.effectiveWallpapers = state.effectiveWallpapers
        root.ready = true
        if (!preserveError)
            root.errorMessage = state.error
    }

    Process {
        id: statusProcess

        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property bool resultHandled: false
        property bool preserveError: false
        property int lastExitCode: -1

        function startRead(): void {
            outputText = ""
            errorText = ""
            exitReceived = false
            stdoutReceived = false
            stderrReceived = false
            resultHandled = false
            lastExitCode = -1
            command = [root.backendCommand, "status"]
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stdoutReceived || !stderrReceived)
                return
            resultHandled = true
            if (lastExitCode !== 0) {
                root.errorMessage = root.conciseError(errorText,
                    "Could not read Appearance status.")
                return
            }
            try {
                root.applyStatus(root.parseStatus(outputText), preserveError)
            } catch (error) {
                root.errorMessage = "Could not parse Appearance status."
                console.warn("Failed to parse vanhyprarch-appearance status: " + error)
            }
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                statusProcess.outputText = text
                statusProcess.stdoutReceived = true
                statusProcess.maybeFinish()
            }
        }
        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                statusProcess.errorText = text
                statusProcess.stderrReceived = true
                statusProcess.maybeFinish()
            }
        }
        onExited: function(exitCode) {
            statusProcess.lastExitCode = exitCode
            statusProcess.exitReceived = true
            statusProcess.maybeFinish()
        }
    }

    Process {
        id: actionProcess

        property string errorText: ""
        property bool exitReceived: false
        property bool stderrReceived: false
        property bool resultHandled: false
        property int lastExitCode: -1
        property string actionKind: ""
        property string actionPath: ""

        function startCommand(nextCommand: var, nextKind: string,
                nextPath: string): void {
            errorText = ""
            exitReceived = false
            stderrReceived = false
            resultHandled = false
            lastExitCode = -1
            actionKind = nextKind || ""
            actionPath = nextPath || ""
            command = nextCommand
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stderrReceived)
                return
            resultHandled = true
            const message = lastExitCode === 0 ? "" : root.conciseError(
                errorText, "Appearance update did not fully reconcile.")
            if (message !== "")
                root.errorMessage = message
            if (actionKind === "wallpaper")
                root.wallpaperRequestFinished(actionPath,
                    lastExitCode === 0, message)
            actionKind = ""
            actionPath = ""
            Qt.callLater(function() { root.refreshStatus(lastExitCode !== 0) })
        }

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                actionProcess.errorText = text
                actionProcess.stderrReceived = true
                actionProcess.maybeFinish()
            }
        }
        onExited: function(exitCode) {
            actionProcess.lastExitCode = exitCode
            actionProcess.exitReceived = true
            actionProcess.maybeFinish()
        }
    }

    Process {
        id: catalogProcess

        property string outputText: ""
        property string errorText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool stderrReceived: false
        property bool resultHandled: false
        property int lastExitCode: -1

        function startRead(requestedMode: string): void {
            outputText = ""
            errorText = ""
            exitReceived = false
            stdoutReceived = false
            stderrReceived = false
            resultHandled = false
            lastExitCode = -1
            command = [root.backendCommand, "catalog", requestedMode]
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stdoutReceived
                    || !stderrReceived)
                return
            resultHandled = true
            if (lastExitCode !== 0) {
                root.catalogFailed(root.conciseError(errorText,
                    "Could not read the background catalog."))
                return
            }
            try {
                const result = root.parseCatalog(outputText)
                root.catalogReady(result.mode, result.entries)
            } catch (error) {
                console.warn("Failed to parse vanhyprarch-appearance catalog: "
                    + error)
                root.catalogFailed("Could not parse the background catalog.")
            }
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
