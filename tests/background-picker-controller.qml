import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    QtObject {
        id: appearance

        signal catalogReady(string mode, var entries)
        signal catalogFailed(string message)
        signal wallpaperRequestFinished(string path, bool success, string message)

        property bool ready: true
        property bool busy: false
        property bool catalogBusy: false
        property string mode: "light"
        property string lightWallpaper: "/pictures/Wallpapers/Light/Light 2.png"
        property string darkWallpaper: "/pictures/Wallpapers/Dark/Dark 1.png"
        property int catalogRequests: 0
        property string lastCatalogMode: ""
        property int wallpaperRequests: 0
        property string lastWallpaperPath: ""

        function requestCatalog(requestedMode) {
            catalogRequests++
            lastCatalogMode = requestedMode
            catalogBusy = true
            return true
        }

        function setCurrentWallpaper(path) {
            wallpaperRequests++
            lastWallpaperPath = path
            busy = true
            return true
        }

        function deliverCatalog(entries) {
            catalogBusy = false
            catalogReady(mode, entries)
        }

        function finishWallpaper(success, message) {
            busy = false
            wallpaperRequestFinished(lastWallpaperPath, success, message || "")
        }
    }

    BackgroundPickerController {
        id: picker
        appearance: appearance
    }

    function entry(mode, number, selected) {
        const modeLabel = mode === "dark" ? "Dark" : "Light"
        const filename = modeLabel + " " + number + ".png"
        const path = "/pictures/Wallpapers/" + modeLabel + "/" + filename
        return {
            filename: filename,
            path: path,
            uri: "file://" + path.replace(/ /g, "%20"),
            selected: selected
        }
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            const lightEntries = [
                root.entry("light", 1, false),
                root.entry("light", 2, true),
                root.entry("light", 3, false),
                root.entry("light", 4, false)
            ]

            picker.open()
            root.check(picker.isOpen && appearance.catalogRequests === 1
                    && appearance.lastCatalogMode === "current",
                "opening did not query the current Appearance catalog")
            appearance.deliverCatalog(lightEntries)
            root.check(picker.currentIndex === 1
                    && picker.candidatePath === appearance.lightWallpaper
                    && picker.appliedPath === appearance.lightWallpaper,
                "opening did not focus the applied wallpaper")

            picker.select(0)
            picker.move(-1)
            root.check(picker.currentIndex === 3
                    && appearance.wallpaperRequests === 0,
                "Left did not wrap without applying")
            picker.move(1)
            root.check(picker.currentIndex === 0
                    && appearance.wallpaperRequests === 0,
                "Right did not wrap without applying")
            picker.select(1)
            picker.move(1)
            root.check(picker.currentIndex === 2
                    && appearance.wallpaperRequests === 0,
                "candidate navigation changed the real wallpaper")
            picker.close()
            root.check(appearance.wallpaperRequests === 0,
                "cancel mutated Appearance")

            picker.open()
            appearance.deliverCatalog(lightEntries)
            picker.move(1)
            const failedCandidate = picker.candidatePath
            picker.applyCandidate()
            root.check(appearance.wallpaperRequests === 1 && picker.applying
                    && picker.isOpen,
                "Enter-equivalent apply did not issue exactly one request")
            picker.applyCandidate()
            root.check(appearance.wallpaperRequests === 1,
                "an apply in flight issued a duplicate request")
            appearance.finishWallpaper(false, "renderer fixture failed")
            root.check(picker.isOpen && !picker.applying
                    && picker.candidatePath === failedCandidate
                    && picker.errorMessage === "renderer fixture failed",
                "failed apply did not retain the picker and candidate")

            picker.applyCandidate()
            picker.applyCandidate()
            root.check(appearance.wallpaperRequests === 2,
                "a retried apply issued more than one request")
            appearance.finishWallpaper(true, "")
            root.check(!picker.isOpen && appearance.wallpaperRequests === 2,
                "successful apply did not close after one authority response")

            picker.open()
            const updatedLightEntries = [
                root.entry("light", 1, false),
                root.entry("light", 2, false),
                root.entry("light", 3, true),
                root.entry("light", 4, false)
            ]
            appearance.deliverCatalog(updatedLightEntries)
            root.check(picker.currentIndex === 2
                    && picker.appliedPath === updatedLightEntries[2].path,
                "fresh catalog selection did not override stale controller status")
            appearance.mode = "dark"
            root.check(picker.mode === "dark" && picker.catalog.length === 0
                    && picker.loading
                    && appearance.lastCatalogMode === "current",
                "mode change left a stale Light catalog visible")
            appearance.deliverCatalog([
                root.entry("dark", 1, true),
                root.entry("dark", 4, false)
            ])
            root.check(picker.currentIndex === 0
                    && picker.appliedPath === appearance.darkWallpaper,
                "Dark catalog did not reset to its applied wallpaper")

            picker.close()
            picker.open()
            appearance.deliverCatalog([])
            root.check(picker.currentIndex === -1 && !picker.hasCandidate,
                "empty catalog created an invalid candidate")
            picker.applyCandidate()
            root.check(appearance.wallpaperRequests === 2,
                "empty catalog attempted an apply")

            picker.close()
            picker.open()
            appearance.deliverCatalog([root.entry("dark", 1, true)])
            picker.move(-1)
            root.check(picker.currentIndex === 0,
                "one-item navigation left the only candidate")
            picker.applyCandidate()
            root.check(!picker.isOpen && appearance.wallpaperRequests === 2,
                "reapplying the current sole item should close without mutation")

            console.log("vanhyprarch Background Picker controller self-check passed")
            Qt.quit()
        }
    }
}
