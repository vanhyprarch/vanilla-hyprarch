import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool checksEnabled: true
    property bool executionEnabled: true
    property string managerExecutable: "vanhyprarch-screensaver"
    property string footExecutable: "/usr/bin/foot"
    property string terminalOperation:
        Quickshell.shellDir + "/helpers/vanhyprarch_terminal_operation"
    property bool statusLoading: false
    property bool planLoading: false
    property bool uninstallPlanValid: false
    property string errorMessage: ""
    property string pendingOperationKind: ""
    property var statusData: ({
        schema_version: 1, manager_version: 1, component: "zig-screensaver",
        state: "not-installed", installed: false, capability: "absent",
        version: "v0.1.1", architecture: "x86_64", marker: "absent",
        cleanup_safe: false, errors: []
    })
    property var uninstallPlan: ({ stored_lock: "none", resulting_lock: "none", plan_token: "" })
    readonly property bool operationRunning: operationProcess.running
    signal operationTerminalCompleted(string operationKind, int exitCode)
    signal refreshRequested()

    function exactKeys(object: var, expected: var): bool {
        if (object === null || typeof object !== "object" || Array.isArray(object))
            return false
        const actual = Object.keys(object).sort()
        const wanted = expected.slice().sort()
        return actual.length === wanted.length
            && actual.every((key, index) => key === wanted[index])
    }

    function acceptStatus(text: string): bool {
        try {
            const value = JSON.parse(text)
            if (!exactKeys(value, ["schema_version", "manager_version", "component",
                    "state", "installed", "capability", "version", "architecture",
                    "marker", "cleanup_safe", "errors"])
                    || value.schema_version !== 1 || value.manager_version !== 1
                    || value.component !== "zig-screensaver"
                    || ["not-installed", "installed", "incomplete", "error"]
                        .indexOf(value.state) < 0
                    || typeof value.installed !== "boolean"
                    || value.installed !== (value.state === "installed")
                    || ["installed", "absent", "incomplete"].indexOf(value.capability) < 0
                    || value.capability !== (value.installed ? "installed"
                        : value.state === "not-installed" ? "absent" : "incomplete")
                    || value.version !== "v0.1.1" || value.architecture !== "x86_64"
                    || ["absent", "valid", "invalid"].indexOf(value.marker) < 0
                    || typeof value.cleanup_safe !== "boolean" || !Array.isArray(value.errors)
                    || !value.errors.every(item => typeof item === "string"))
                throw new Error("unexpected Zig Screensaver status")
            statusData = value
            errorMessage = (value.state === "incomplete" || value.state === "error")
                ? value.errors.join("; ") : ""
            return true
        } catch (error) {
            statusData = Object.assign({}, statusData, {
                state: "error", installed: false, capability: "incomplete",
                marker: "invalid", cleanup_safe: false,
                errors: ["Could not read Zig Screensaver component status."]
            })
            errorMessage = "Could not read Zig Screensaver component status."
            return false
        }
    }

    function commandFor(operation: string, planToken: string): var {
        if (["install", "adopt", "reinstall", "repair", "uninstall", "clean-up"]
                .indexOf(operation) < 0)
            return []
        const command = [terminalOperation, "--supervise-foot", footExecutable,
            "Vanilla HyprArch Zig Screensaver", "--", managerExecutable, operation]
        if (operation === "uninstall") {
            if (!planToken)
                return []
            command.push("--plan-token", planToken)
        }
        return command
    }

    function execute(operation: string, planToken: string): bool {
        const command = commandFor(operation, planToken || "")
        if (!executionEnabled || operationRunning || command.length === 0)
            return false
        pendingOperationKind = operation
        errorMessage = ""
        operationProcess.exec(command)
        return true
    }

    function refreshStatus(): void {
        if (!checksEnabled || statusProcess.running)
            return
        statusLoading = true
        statusProcess.begin()
    }

    function refreshUninstallPlan(): void {
        if (!checksEnabled || planProcess.running)
            return
        planLoading = true
        uninstallPlanValid = false
        planProcess.begin()
    }

    function refreshAll(): void {
        refreshRequested()
        refreshStatus()
    }

    Process {
        id: statusProcess
        property string output: ""
        property bool exited: false
        property bool stdoutDone: false
        property bool stderrDone: false
        property int exitCode: -1
        function begin(): void {
            output = ""; exited = false; stdoutDone = false; stderrDone = false; exitCode = -1
            command = [root.managerExecutable, "component-status", "--json"]
            running = true
        }
        function finish(): void {
            if (!exited || !stdoutDone || !stderrDone)
                return
            root.statusLoading = false
            if (exitCode !== 0) {
                root.statusData = Object.assign({}, root.statusData, {
                    state: "error", installed: false, capability: "incomplete",
                    marker: "invalid", cleanup_safe: false,
                    errors: ["Could not read Zig Screensaver component status."]
                })
                root.errorMessage = "Could not read Zig Screensaver component status."
            } else {
                root.acceptStatus(output)
            }
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            statusProcess.output = text; statusProcess.stdoutDone = true; statusProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            statusProcess.stderrDone = true; statusProcess.finish()
        }}
        onExited: function(code) { exitCode = code; exited = true; finish() }
    }

    Process {
        id: planProcess
        property string output: ""
        property bool exited: false
        property bool stdoutDone: false
        property bool stderrDone: false
        property int exitCode: -1
        function begin(): void {
            output = ""; exited = false; stdoutDone = false; stderrDone = false; exitCode = -1
            command = [root.managerExecutable, "uninstall-plan", "--json"]
            running = true
        }
        function finish(): void {
            if (!exited || !stdoutDone || !stderrDone)
                return
            root.planLoading = false
            try {
                const value = JSON.parse(output)
                if (exitCode !== 0 || !root.exactKeys(value,
                        ["schema_version", "component", "stored_lock", "resulting_lock", "plan_token"])
                        || value.schema_version !== 1 || value.component !== "zig-screensaver"
                        || ["none", "screensaver", "display", "suspend"]
                            .indexOf(value.stored_lock) < 0
                        || ["none", "display", "suspend"].indexOf(value.resulting_lock) < 0
                        || !/^[0-9a-f]{64}$/.test(value.plan_token))
                    throw new Error("invalid plan")
                root.uninstallPlan = value
                root.uninstallPlanValid = true
            } catch (error) {
                root.uninstallPlanValid = false
                root.errorMessage = "Could not calculate the uninstall preference transaction."
            }
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            planProcess.output = text; planProcess.stdoutDone = true; planProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            planProcess.stderrDone = true; planProcess.finish()
        }}
        onExited: function(code) { exitCode = code; exited = true; finish() }
    }

    Process {
        id: operationProcess
        onExited: function(exitCode) {
            const operation = root.pendingOperationKind
            root.pendingOperationKind = ""
            root.operationTerminalCompleted(operation, exitCode)
            root.refreshAll()
        }
    }

    Component.onCompleted: if (checksEnabled) refreshAll()
}
