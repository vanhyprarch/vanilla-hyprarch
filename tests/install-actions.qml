import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    InstallActions {
        id: controller
    }

    PowerActions {
        id: powerActions
    }

    SuperSpace {
        id: superSpace
        installActions: controller
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
                "--hold",
                "--title=Vanilla HyprArch Install",
                "/usr/bin/yay",
                "-Y",
                "--",
                "--noconfirm",
                "firefox;",
                "touch",
                "/tmp/not-a-command"
            ].join("\n"), "search terms did not remain argv data")
            root.check(command[5] === "--",
                "yay option boundary is missing")

            root.check(superSpace.sections.map(section => section.label).join(",")
                === "Apps,Install,Power", "root section order changed")
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
