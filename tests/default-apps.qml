import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition) throw new Error(message)
    }

    InstallActions { id: installActions }
    RemoveActions { id: removeActions; enumerationEnabled: false }
    UpdateActions { id: updateActions; availabilityChecksEnabled: false; executionEnabled: false }
    PowerActions { id: powerActions }
    SystemComponentsActions { id: componentActions; checksEnabled: false; executionEnabled: false }
    ZigScreensaverActions { id: zigActions; checksEnabled: false; executionEnabled: false }
    DefaultAppsActions { id: defaultActions; executable: "/usr/bin/false" }
    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        systemComponentsActions: componentActions
        zigScreensaverActions: zigActions
        powerActions: powerActions
        defaultAppsActions: defaultActions
    }
    SuperSpacePanelHarness { id: panel; controller: superSpace }

    Timer {
        interval: 100
        running: true
        repeat: true
        onTriggered: {
            if (DesktopEntries.applications.values.length < 3)
                return
            stop()
            const sections = superSpace.sections.map(entry => entry.label)
            const style = sections.indexOf("Style")
            root.check(sections[style + 1] === "Default Apps"
                && sections[style + 2] === "Additional system components",
                "Default Apps root order is wrong")
            superSpace.enterSection("default-apps")
            defaultActions.effective = ({
                browser: "firefox.desktop", terminal: "foot.desktop",
                editor: "org.gnome.TextEditor.desktop"
            })
            defaultActions.candidates = ({
                browser: ["firefox.desktop", "zeta.desktop", "alpha.desktop"],
                terminal: ["foot.desktop"],
                editor: ["org.gnome.TextEditor.desktop"]
            })
            defaultActions.ready = true
            let entries = superSpace.visibleEntries
            root.check(entries.length === 3 && entries[0].label === "Browser"
                && entries[1].label === "Terminal" && entries[2].label === "Text Editor",
                "Default Apps must have exactly three ordered categories")
            root.check(entries[0].detail === "Firefox" && entries[1].detail === "Foot"
                && entries[2].detail === "Text Editor",
                "effective application names are wrong")
            defaultActions.effective = ({ browser: "mixed", terminal: null, editor: null })
            entries = superSpace.visibleEntries
            root.check(entries[0].detail === "Mixed"
                && entries[1].detail === "No available default",
                "mixed/unavailable presentation is wrong")
            superSpace.activate(entries[0])
            root.check(superSpace.currentDefaultCategory === "browser"
                && superSpace.visibleEntries.map(entry => entry.desktopId).join(",")
                    === "alpha.desktop,zeta.desktop,firefox.desktop",
                "Browser candidate view is wrong")
            superSpace.searchText = "fire"
            root.check(superSpace.visibleEntries.length === 1
                && superSpace.visibleEntries[0].desktopId === "firefox.desktop",
                "Browser candidate search is wrong")
            panel.pressEscape()
            root.check(superSpace.currentDefaultCategory === "", "Escape did not go back")
            for (const category of ["terminal", "editor"]) {
                const row = superSpace.visibleEntries.find(entry => entry.categoryId === category)
                superSpace.activate(row)
                root.check(superSpace.visibleEntries.length === 1
                    && superSpace.visibleEntries[0].categoryId === category,
                    category + " candidate view is wrong")
                superSpace.goBack()
            }
            superSpace.searchText = "browser"
            root.check(superSpace.visibleEntries.length === 1
                && superSpace.visibleEntries[0].label === "Browser",
                "category search is wrong")
            finishTimer.start()
        }
    }

    Timer {
        id: finishTimer
        interval: 50
        repeat: true
        property int attempts: 0
        onTriggered: {
            attempts += 1
            if (defaultActions.errorMessage !== "") {
                stop()
                console.log("vanhyprarch Default Apps UI self-check passed")
                Qt.quit()
            } else if (attempts > 40) {
                throw new Error("Default Apps process result did not complete")
            }
        }
    }
}
