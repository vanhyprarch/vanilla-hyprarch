import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    property int backgroundPickerRequests: 0
    property var launchedCommands: []

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
        flatpakAvailable: true
        commandLauncher: function(command) { root.launchedCommands.push(command) }
    }

    PowerActions {
        id: powerActions
    }

    SystemComponentsActions {
        id: systemComponentsActions
        checksEnabled: false
        executionEnabled: false
    }

    ZigScreensaverActions { id: zigScreensaverActions; checksEnabled: false; executionEnabled: false }

    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        systemComponentsActions: systemComponentsActions
        zigScreensaverActions: zigScreensaverActions
        powerActions: powerActions
        onBackgroundPickerRequested: root.backgroundPickerRequests++
    }

    SuperSpacePanelHarness {
        id: panelHarness
        controller: superSpace
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            root.check(superSpace.sections.map(section => section.label).join(",")
                === "Apps,Install,Remove,Update,Style,Default Apps,Additional system components,Power",
                "root section order is wrong")
            root.check(updateActions.actions.map(action => action.label).join(",")
                === "System,Flatpak,Vanilla HyprArch", "Update action order is wrong")

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
            const vanillaCommand = updateActions.commandForAction("vanilla")
            root.check(vanillaCommand.join("\n") === [
                updateActions.terminalOperation,
                "--supervise-foot",
                "/usr/bin/foot",
                "Vanilla HyprArch Update",
                "--",
                "/usr/local/bin/vanhyprarch-update"
            ].join("\n"), "Vanilla update argv is wrong")
            root.check(updateActions.terminalOperation
                    === installActions.terminalOperation
                    && updateActions.terminalOperation
                        === removeActions.terminalOperation,
                "Update does not share the terminal wrapper")

            for (const command of [systemCommand, flatpakCommand, vanillaCommand]) {
                for (const forbidden of ["--noconfirm", "-yy", "-uu",
                        "--assumeyes", "--noninteractive", "--hold",
                        "/bin/sh", "/usr/bin/sh", "sh", "/bin/bash",
                        "/usr/bin/bash", "bash", "eval", "sudo",
                        "/usr/bin/sudo"])
                    root.check(command.indexOf(forbidden) < 0,
                        "unsafe Update argument present: " + forbidden)
            }

            root.check(updateActions.errorMessage === "",
                "Update controller began with an error")

            superSpace.enterSection("style")
            root.check(superSpace.currentSection === "style"
                    && superSpace.visibleEntries.length === 1,
                "Style did not open with exactly one action")
            const styleEntry = superSpace.visibleEntries[0]
            root.check(styleEntry.kind === "chooseBackground"
                    && styleEntry.actionId === "choose-background"
                    && styleEntry.label === "Choose background",
                "Style contains an unexpected or unstable action")
            root.check(superSpace.entryIdentity(styleEntry)
                    === "chooseBackground:choose-background",
                "Style action has no stable selection identity")
            superSpace.isOpen = true
            superSpace.activate(styleEntry)
            root.check(root.backgroundPickerRequests === 1
                    && !superSpace.isOpen,
                "Style action did not transfer away from SuperSpace")

            superSpace.enterSection("update")
            root.check(superSpace.currentSection === "update",
                "Update section was rejected")
            root.check(superSpace.visibleEntries.length === 3
                    && superSpace.visibleEntries[0].actionId === "system"
                    && superSpace.visibleEntries[1].actionId === "flatpak"
                    && superSpace.visibleEntries[2].actionId === "vanilla",
                "Update section order is wrong")
            root.check(updateActions.errorMessage === "",
                "entering Update attempted to execute an action")
            root.check(root.launchedCommands.length === 0,
                "opening Update launched an updater")

            panelHarness.resetSelection()
            root.check(panelHarness.selectedEntryIndex === 0,
                "Update keyboard selection did not start at System")
            panelHarness.moveSelection(1)
            panelHarness.moveSelection(1)
            root.check(panelHarness.selectedEntryIndex === 2,
                "keyboard navigation cannot reach Vanilla HyprArch")
            panelHarness.pressEscape()
            root.check(superSpace.currentSection === "root"
                    && root.launchedCommands.length === 0,
                "Escape did not return without launching")

            superSpace.enterSection("update")
            superSpace.isOpen = true
            panelHarness.resetSelection()
            panelHarness.moveSelection(1)
            panelHarness.moveSelection(1)
            panelHarness.activateSelection()
            root.check(root.launchedCommands.length === 1
                    && root.launchedCommands[0].join("\n")
                        === vanillaCommand.join("\n")
                    && !superSpace.isOpen,
                "keyboard activation did not launch exactly one supervised operation")

            superSpace.enterSection("update")
            superSpace.isOpen = true
            root.check(panelHarness.selectEntryAt(2),
                "mouse selection cannot reach Vanilla HyprArch")
            panelHarness.activateSelection()
            root.check(root.launchedCommands.length === 2
                    && root.launchedCommands[1].join("\n")
                        === vanillaCommand.join("\n")
                    && !superSpace.isOpen,
                "mouse activation did not launch exactly one supervised operation")

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
