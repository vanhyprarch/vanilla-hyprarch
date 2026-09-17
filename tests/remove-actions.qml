import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    property bool waitingForLiveCatalog: false

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

    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        powerActions: powerActions
    }

    Connections {
        target: removeActions

        function onLoadingChanged(): void {
            if (!root.waitingForLiveCatalog || removeActions.loading)
                return

            catalogTimeout.stop()
            root.check(removeActions.errorMessage === "",
                "live pacman catalog load failed: "
                    + removeActions.errorMessage)
            root.check(removeActions.packages.length > 0,
                "live pacman catalog was empty")
            root.check(removeActions.commandForPackage(
                    removeActions.packages[0]).length === 7,
                "live pacman object was not accepted as a removal target")
            console.log("vanhyprarch Remove action self-check passed")
            Qt.quit()
        }
    }

    Timer {
        id: catalogTimeout

        interval: 5000
        repeat: false
        onTriggered: {
            root.check(false, "live pacman catalog load timed out")
            Qt.quit()
        }
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            removeActions.finishCatalogLoad(1, "", "pacman query failed\n")
            root.check(removeActions.packages.length === 0
                    && removeActions.errorMessage === "pacman query failed",
                "package enumeration failure did not fail closed")
            removeActions.finishCatalogLoad(0,
                "firefox 155.0.1-1\nfoot 1.28.0-2\nyay 13.0.1-1\n", "")
            root.check(removeActions.packages.length === 3,
                "installed package catalog was not parsed")

            const firefox = removeActions.packages[0]
            const command = removeActions.commandForPackage(firefox)
            root.check(command.join("\n") === [
                "/usr/bin/foot",
                "--title=Vanilla HyprArch Remove Package",
                removeActions.terminalOperation,
                "/usr/bin/yay",
                "-Rns",
                "--",
                "firefox"
            ].join("\n"), "removal argv changed")
            root.check(removeActions.terminalOperation
                    === installActions.terminalOperation,
                "Install and Remove do not share the terminal wrapper")
            root.check(command[2] === removeActions.terminalOperation,
                "Remove did not place the shared wrapper before yay")
            root.check(command[3] === "/usr/bin/yay"
                    && command[4] === "-Rns"
                    && command[5] === "--"
                    && command[6] === firefox.name,
                "yay operation, option boundary, or package target is wrong")

            for (const forbidden of ["-c", "--cascade", "--nodeps",
                    "--noconfirm", "--hold", "/bin/sh", "/usr/bin/sh", "sh",
                    "/bin/bash", "/usr/bin/bash", "bash", "eval"])
                root.check(command.indexOf(forbidden) < 0,
                    "unsafe removal argument present: " + forbidden)

            root.check(removeActions.commandForPackage("firefox").length === 0,
                "raw search text produced a removal command")
            root.check(removeActions.commandForPackage({
                name: "firefox",
                version: "155.0.1-1"
            }).length === 0, "a copied package object was accepted")
            root.check(removeActions.commandForPackage({
                name: "--noconfirm",
                version: "1"
            }).length === 0, "option-like input became a yay target")

            root.check(superSpace.sections.map(section => section.label).join(",")
                === "Apps,Install,Remove,Update,Power",
                "root section order is wrong")

            for (const section of ["apps", "install", "update", "power"]) {
                superSpace.enterSection(section)
                root.check(superSpace.currentSection === section,
                    section + " navigation was not preserved")
            }

            superSpace.enterSection("remove")
            root.check(superSpace.currentSection === "remove",
                "Remove section was rejected")
            root.check(superSpace.visibleEntries.length === 3,
                "Remove did not expose the loaded installed packages")
            superSpace.searchText = "fire"
            root.check(superSpace.visibleEntries.length === 1
                    && superSpace.visibleEntries[0].kind === "removePackage"
                    && superSpace.visibleEntries[0].packageObject === firefox,
                "installed package filtering did not preserve the stored object")
            root.check(removeActions.commandForPackage(superSpace.searchText).length
                    === 0, "Remove accepted search text as a target")
            superSpace.searchText = "--noconfirm"
            root.check(superSpace.visibleEntries.length === 0,
                "option-like search text created a package result")

            let optionPackageAccepted = false
            try {
                removeActions.parsePackages("--noconfirm 1\n")
                optionPackageAccepted = true
            } catch (error) {
            }
            root.check(!optionPackageAccepted,
                "option-like pacman output was accepted as a package")

            root.waitingForLiveCatalog = true
            removeActions.enumerationEnabled = true
            catalogTimeout.start()
            root.check(removeActions.refreshPackages(),
                "live pacman catalog refresh did not start")
            root.check(removeActions.loading
                    && removeActions.packages.length === 0,
                "catalog refresh retained stale package targets")
        }
    }
}
