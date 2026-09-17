import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    InstallActions {
        id: installActions
    }

    RemoveActions {
        id: removeActions
        enumerationEnabled: false
    }

    UpdateActions {
        id: updateActions
        availabilityChecksEnabled: false
        executionEnabled: false
        flatpakAvailable: true
    }

    PowerActions {
        id: powerActions
    }

    SystemComponentsActions {
        id: systemComponentsActions
        checksEnabled: false
        executionEnabled: false
    }

    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        systemComponentsActions: systemComponentsActions
        powerActions: powerActions
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            root.check(superSpace.sections.map(section => section.label).join(",")
                === "Apps,Install,Remove,Update,Additional system components,Power",
                "root section order is wrong")
            root.check(updateActions.actions.map(action => action.label).join(",")
                === "System,Flatpak", "Update action order is wrong")

            const systemCommand = updateActions.commandForAction("system")
            root.check(systemCommand.join("\n") === [
                "/usr/bin/foot",
                "--title=Vanilla HyprArch Update System",
                updateActions.terminalOperation,
                "/usr/bin/yay",
                "-Syu"
            ].join("\n"), "System update argv is wrong")

            const flatpakCommand = updateActions.commandForAction("flatpak")
            root.check(flatpakCommand.join("\n") === [
                "/usr/bin/foot",
                "--title=Vanilla HyprArch Update Flatpak",
                updateActions.terminalOperation,
                "/usr/bin/flatpak",
                "update"
            ].join("\n"), "Flatpak update argv is wrong")
            root.check(updateActions.terminalOperation
                    === installActions.terminalOperation
                    && updateActions.terminalOperation
                        === removeActions.terminalOperation,
                "Update does not share the terminal wrapper")

            for (const command of [systemCommand, flatpakCommand]) {
                for (const forbidden of ["--noconfirm", "-yy", "-uu",
                        "--assumeyes", "--noninteractive", "--hold",
                        "/bin/sh", "/usr/bin/sh", "sh", "/bin/bash",
                        "/usr/bin/bash", "bash", "eval"])
                    root.check(command.indexOf(forbidden) < 0,
                        "unsafe Update argument present: " + forbidden)
            }

            root.check(updateActions.errorMessage === "",
                "Update controller began with an error")
            superSpace.enterSection("update")
            root.check(superSpace.currentSection === "update",
                "Update section was rejected")
            root.check(superSpace.visibleEntries.length === 2
                    && superSpace.visibleEntries[0].actionId === "system"
                    && superSpace.visibleEntries[1].actionId === "flatpak",
                "Update section does not contain System then Flatpak")
            root.check(updateActions.errorMessage === "",
                "entering Update attempted to execute an action")

            updateActions.flatpakAvailable = false
            root.check(updateActions.commandForAction("flatpak").length === 0,
                "missing Flatpak produced a command")
            root.check(!updateActions.execute("flatpak")
                    && updateActions.errorMessage.indexOf(
                        "/usr/bin/flatpak is unavailable") >= 0,
                "missing Flatpak did not fail safely")
            root.check(updateActions.commandForAction("everything").length === 0,
                "an unsupported Everything action produced a command")

            console.log("vanhyprarch Update action self-check passed")
            Qt.quit()
        }
    }
}
