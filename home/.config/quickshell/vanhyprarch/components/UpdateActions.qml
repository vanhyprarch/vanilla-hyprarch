import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool availabilityChecksEnabled: true
    property bool executionEnabled: true
    property bool flatpakAvailable: false
    property bool flatpakCheckComplete: false
    property string errorMessage: ""
    readonly property string footExecutable: "/usr/bin/foot"
    readonly property string yayExecutable: "/usr/bin/yay"
    readonly property string flatpakExecutable: "/usr/bin/flatpak"
    readonly property string terminalOperation:
        Quickshell.shellDir + "/helpers/vanhyprarch_terminal_operation"
    readonly property var actions: [
        {
            id: "system",
            label: "System",
            detail: "Update Arch repository and AUR packages with yay",
            icon: "system-software-update",
            keywords: ["system", "arch", "aur", "packages", "yay"]
        },
        {
            id: "flatpak",
            label: "Flatpak",
            detail: "Update installed Flatpak apps and runtimes",
            icon: "package-x-generic",
            keywords: ["flatpak", "applications", "apps", "runtimes"]
        }
    ]

    function action(actionId: string): var {
        for (const candidate of actions) {
            if (candidate.id === actionId)
                return candidate
        }
        return null
    }

    function commandForAction(actionId: string): var {
        if (actionId === "system") {
            return [
                footExecutable,
                "--title=Vanilla HyprArch Update System",
                terminalOperation,
                yayExecutable,
                "-Syu"
            ]
        }

        if (actionId === "flatpak") {
            if (!flatpakCheckComplete || !flatpakAvailable)
                return []
            return [
                footExecutable,
                "--title=Vanilla HyprArch Update Flatpak",
                terminalOperation,
                flatpakExecutable,
                "update"
            ]
        }

        return []
    }

    function execute(actionId: string): bool {
        errorMessage = ""
        if (actionId === "flatpak"
                && (!flatpakCheckComplete || !flatpakAvailable)) {
            errorMessage = flatpakCheckComplete
                ? "Required /usr/bin/flatpak is unavailable."
                : "Still checking the required Flatpak executable."
            return false
        }

        const command = commandForAction(actionId)
        if (command.length === 0) {
            errorMessage = "Unknown update action."
            console.warn(errorMessage)
            return false
        }
        if (!executionEnabled) {
            errorMessage = "Update execution is disabled."
            return false
        }

        Quickshell.execDetached(command)
        return true
    }

    function refreshAvailability(): bool {
        if (!availabilityChecksEnabled || availabilityProcess.running)
            return false
        flatpakAvailable = false
        flatpakCheckComplete = false
        errorMessage = ""
        availabilityProcess.running = true
        return true
    }

    Process {
        id: availabilityProcess

        command: ["/usr/bin/test", "-x", root.flatpakExecutable]
        onExited: function(exitCode) {
            root.flatpakAvailable = exitCode === 0
            root.flatpakCheckComplete = true
            root.errorMessage = exitCode === 0 ? ""
                : "Required /usr/bin/flatpak is unavailable."
        }
    }

    Component.onCompleted: {
        if (availabilityChecksEnabled)
            refreshAvailability()
        else
            flatpakCheckComplete = true
    }
}
