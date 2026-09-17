import QtQuick
import Quickshell

Scope {
    id: root

    readonly property var actions: [
        {
            id: "lock",
            label: "Lock",
            icon: "system-lock-screen",
            keywords: ["lock", "screen", "session"],
            requiresConfirmation: false
        },
        {
            id: "suspend",
            label: "Suspend",
            icon: "system-suspend",
            keywords: ["suspend", "sleep"],
            requiresConfirmation: false
        },
        {
            id: "logout",
            label: "Logout",
            icon: "system-log-out",
            keywords: ["logout", "log out", "sign out", "session"],
            requiresConfirmation: true
        },
        {
            id: "reboot",
            label: "Reboot",
            icon: "system-reboot",
            keywords: ["reboot", "restart"],
            requiresConfirmation: true
        },
        {
            id: "poweroff",
            label: "Power off",
            icon: "system-shutdown",
            keywords: ["power off", "poweroff", "shutdown", "shut down"],
            requiresConfirmation: true
        }
    ]

    function action(actionId: string): var {
        return actions.find(candidate => candidate.id === actionId) || null
    }

    function requiresConfirmation(actionId: string): bool {
        const candidate = action(actionId)
        return candidate !== null && candidate.requiresConfirmation
    }

    function execute(actionId: string): bool {
        switch (actionId) {
        case "lock":
            Quickshell.execDetached(["loginctl", "lock-session"])
            return true
        case "suspend":
            Quickshell.execDetached(["systemctl", "suspend"])
            return true
        case "logout":
            Quickshell.execDetached(["hyprshutdown"])
            return true
        case "reboot":
            Quickshell.execDetached(["systemctl", "reboot"])
            return true
        case "poweroff":
            Quickshell.execDetached(["systemctl", "poweroff"])
            return true
        default:
            console.warn("Refusing unknown power action: " + actionId)
            return false
        }
    }
}
