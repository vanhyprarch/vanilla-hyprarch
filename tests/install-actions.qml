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
        id: controller
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

    SuperSpace {
        id: superSpace
        installActions: controller
        removeActions: removeActions
        updateActions: updateActions
        powerActions: powerActions
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            root.check(controller.commandForSearch("").length === 0,
                "empty search produced a command")
            root.check(controller.commandForSearch("   \t ").length === 0,
                "whitespace-only search produced a command")

            const command = controller.commandForSearch(
                "--noconfirm firefox; touch /tmp/not-a-command")
            root.check(command.join("\n") === [
                "/usr/bin/foot",
                "--title=Vanilla HyprArch Install",
                controller.terminalOperation,
                "/usr/bin/yay",
                "-Y",
                "--",
                "--noconfirm",
                "firefox;",
                "touch",
                "/tmp/not-a-command"
            ].join("\n"), "search terms did not remain argv data")
            root.check(controller.terminalOperation
                    === removeActions.terminalOperation,
                "Install and Remove do not share the terminal wrapper")
            root.check(command[2] === controller.terminalOperation
                    && command[3] === "/usr/bin/yay"
                    && command[4] === "-Y",
                "Install did not place the exact yay argv after the wrapper")
            root.check(command[5] === "--",
                "yay option boundary is missing")
            for (const forbidden of ["--hold", "/bin/sh", "/usr/bin/sh", "sh",
                    "/bin/bash", "/usr/bin/bash", "bash", "eval"])
                root.check(command.indexOf(forbidden) < 0,
                    "unsafe Install argument present: " + forbidden)

            root.check(superSpace.sections.map(section => section.label).join(",")
                === "Apps,Install,Remove,Update,Power",
                "root section order changed")
            superSpace.enterSection("install")
            root.check(superSpace.currentSection === "install",
                "Install section was rejected")
            root.check(superSpace.visibleEntries.length === 0,
                "empty Install search exposed an action")
            superSpace.searchText = "firefox developer"
            root.check(superSpace.visibleEntries.length === 1
                    && superSpace.visibleEntries[0].kind === "installSearch"
                    && superSpace.visibleEntries[0].searchText
                        === "firefox developer",
                "Install search action was not generated")
            superSpace.currentSection = "root"
            for (const keyword of ["install", "package", "software", "yay"]) {
                superSpace.searchText = keyword
                root.check(superSpace.visibleEntries.some(entry =>
                        entry.kind === "section"
                            && entry.sectionId === "install"),
                    keyword + " keyword did not find the Install section")
            }

            console.log("vanhyprarch Install action self-check passed")
            Qt.quit()
        }
    }
}
