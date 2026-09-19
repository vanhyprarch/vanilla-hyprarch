import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    VisualMetrics { id: metrics }
    Theme { id: theme; metrics: metrics }
    AppearanceController {
        id: controller
        theme: theme
        checksEnabled: false
    }

    QtObject {
        id: toggleFixture
        property bool ready: true
        property bool busy: false
        property bool darkMode: false
        property int activations: 0
        function toggleMode() { activations++ }
    }

    ThemeToggle {
        id: toggle
        controller: toggleFixture
        metrics: metrics
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            const darkMismatch = JSON.stringify({
                version: 1,
                initialized: true,
                mode: "dark",
                current_wallpaper: "/pictures/Wallpapers/Dark/dark.png",
                wallpapers: {
                    light: {path: "/pictures/Wallpapers/Light/light.png"},
                    dark: {path: "/pictures/Wallpapers/Dark/dark.png"}
                },
                directories: {
                    pictures: "/pictures",
                    light: "/pictures/Wallpapers/Light",
                    dark: "/pictures/Wallpapers/Dark"
                },
                host: {
                    expected_gsettings: "prefer-dark",
                    expected_portal: 1,
                    gsettings: "prefer-light",
                    portal: 2,
                    matches: false,
                    error: null
                },
                renderer: {
                    state: "mismatch",
                    matches: false,
                    active: {"DP-1": "/pictures/Wallpapers/Light/light.png"},
                    error: "active wallpaper does not match"
                },
                consistent: false,
                errors: ["active wallpaper does not match"]
            })
            const dark = controller.parseStatus(darkMismatch)
            controller.applyStatus(dark, false)
            root.check(controller.mode === "dark" && controller.darkMode,
                "desired dark mode was not consumed")
            root.check(theme.darkMode,
                "Appearance authority did not apply the Vanilla dark palette")
            root.check(controller.effectiveShellMode === "dark",
                "effective Vanilla theme was not exposed")
            root.check(controller.effectiveHostMode === "light"
                    && controller.effectivePortalValue === 2,
                "effective host mismatch was hidden")
            root.check(controller.rendererState === "mismatch"
                    && !controller.rendererMatches,
                "effective wallpaper mismatch was hidden")
            root.check(controller.errorMessage !== "",
                "backend capability error was not retained")

            toggle.activate()
            root.check(toggleFixture.activations === 1,
                "dock icon did not invoke the shared Appearance authority")
            toggleFixture.busy = true
            toggle.activate()
            root.check(toggleFixture.activations === 1,
                "dock icon invoked Appearance while busy")

            let invalidAccepted = false
            try {
                controller.parseStatus('{"version":1,"mode":"sepia"}')
                invalidAccepted = true
            } catch (error) {
            }
            root.check(!invalidAccepted, "unknown Appearance mode was accepted")

            const lightReady = JSON.stringify({
                version: 1,
                initialized: true,
                mode: "light",
                current_wallpaper: null,
                wallpapers: {light: {path: null}, dark: {path: null}},
                directories: {
                    pictures: "/pictures",
                    light: "/pictures/Wallpapers/Light",
                    dark: "/pictures/Wallpapers/Dark"
                },
                host: {
                    expected_gsettings: "prefer-light",
                    expected_portal: 2,
                    gsettings: "prefer-light",
                    portal: 2,
                    matches: true,
                    error: null
                },
                renderer: {
                    state: "unselected",
                    matches: false,
                    active: {},
                    error: null
                },
                consistent: true,
                errors: []
            })
            controller.applyStatus(controller.parseStatus(lightReady), false)
            root.check(controller.mode === "light" && !theme.darkMode,
                "Appearance authority did not restore the Vanilla light palette")
            root.check(controller.currentWallpaper === ""
                    && controller.lightDirectory.endsWith("/Wallpapers/Light")
                    && controller.darkDirectory.endsWith("/Wallpapers/Dark"),
                "future picker contract is incomplete")

            console.log("vanhyprarch Appearance controller self-check passed")
            Qt.quit()
        }
    }
}
