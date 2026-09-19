import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    required property var appearance
    property bool isOpen: false
    property string activeScreenName: ""
    property string mode: "light"
    property var catalog: []
    property int currentIndex: -1
    property string appliedPath: ""
    property bool loading: false
    property bool applying: false
    property string errorMessage: ""
    property bool catalogRequestInFlight: false
    property int openGeneration: 0
    property int requestGeneration: -1
    property string pendingApplyPath: ""

    readonly property bool hasCandidate: currentIndex >= 0
        && currentIndex < catalog.length
    readonly property var candidate: hasCandidate ? catalog[currentIndex] : null
    readonly property string candidatePath: candidate ? candidate.path : ""
    readonly property string candidateFilename: candidate ? candidate.filename : ""
    readonly property string modeLabel: mode === "dark" ? "Dark" : "Light"

    function appliedForMode(nextMode: string): string {
        return nextMode === "dark"
            ? appearance.darkWallpaper : appearance.lightWallpaper
    }

    function selectInitialCandidate(entries: var): int {
        for (let index = 0; index < entries.length; ++index) {
            if (entries[index].selected)
                return index
        }
        for (let index = 0; index < entries.length; ++index) {
            if (entries[index].path === appliedPath)
                return index
        }
        return entries.length > 0 ? 0 : -1
    }

    function catalogAppliedPath(entries: var): string {
        for (const entry of entries) {
            if (entry.selected)
                return entry.path
        }
        return appliedForMode(mode)
    }

    function resolveActiveScreen(): void {
        const focusedMonitor = Hyprland.focusedMonitor
        if (focusedMonitor && focusedMonitor.name !== "")
            activeScreenName = focusedMonitor.name
        else if (Quickshell.screens.length > 0)
            activeScreenName = Quickshell.screens[0].name
        else
            activeScreenName = ""
    }

    function open(): void {
        if (isOpen)
            return
        openGeneration++
        resolveActiveScreen()
        isOpen = true
        reloadCatalog()
    }

    function close(): void {
        isOpen = false
        loading = false
        applying = false
        pendingApplyPath = ""
        errorMessage = ""
    }

    function toggle(): void {
        if (isOpen)
            close()
        else
            open()
    }

    function reloadCatalog(): void {
        mode = appearance.mode
        appliedPath = appliedForMode(mode)
        catalog = []
        currentIndex = -1
        errorMessage = ""
        loading = true
        requestCatalogWhenReady()
    }

    function requestCatalogWhenReady(): void {
        if (!isOpen || catalogRequestInFlight || appearance.catalogBusy)
            return
        if (!appearance.ready || appearance.busy)
            return
        catalogRequestInFlight = appearance.requestCatalog("current")
        if (catalogRequestInFlight)
            requestGeneration = openGeneration
        if (!catalogRequestInFlight) {
            loading = false
            errorMessage = "Could not request the background catalog."
        }
    }

    function move(offset: int): void {
        if (catalog.length === 0 || applying)
            return
        const start = currentIndex >= 0 ? currentIndex : 0
        currentIndex = (start + offset + catalog.length) % catalog.length
    }

    function select(index: int): void {
        if (!applying && index >= 0 && index < catalog.length)
            currentIndex = index
    }

    function applyCandidate(): void {
        if (!hasCandidate || applying)
            return
        errorMessage = ""
        if (candidatePath === appliedPath) {
            close()
            return
        }
        pendingApplyPath = candidatePath
        applying = appearance.setCurrentWallpaper(candidatePath)
        if (!applying) {
            pendingApplyPath = ""
            errorMessage = "Appearance is busy; the background was not changed."
        }
    }

    Connections {
        target: root.appearance

        function onCatalogReady(catalogMode, entries): void {
            root.catalogRequestInFlight = false
            if (!root.isOpen)
                return
            if (root.requestGeneration !== root.openGeneration
                    || catalogMode !== root.appearance.mode
                    || catalogMode !== root.mode) {
                root.reloadCatalog()
                return
            }
            root.mode = catalogMode
            root.catalog = entries
            root.appliedPath = root.catalogAppliedPath(entries)
            root.currentIndex = root.selectInitialCandidate(entries)
            root.loading = false
            root.errorMessage = ""
        }

        function onCatalogFailed(message): void {
            root.catalogRequestInFlight = false
            if (!root.isOpen)
                return
            if (root.requestGeneration !== root.openGeneration) {
                root.reloadCatalog()
                return
            }
            root.loading = false
            root.errorMessage = message
        }

        function onWallpaperRequestFinished(path, success, message): void {
            if (path !== root.pendingApplyPath)
                return
            root.applying = false
            root.pendingApplyPath = ""
            if (success) {
                root.appliedPath = path
                root.close()
            } else if (root.isOpen) {
                root.errorMessage = message || "The background could not be applied."
            }
        }

        function onModeChanged(): void {
            if (root.isOpen && root.mode !== root.appearance.mode)
                root.reloadCatalog()
        }

        function onReadyChanged(): void {
            if (root.isOpen && root.loading)
                root.requestCatalogWhenReady()
        }

        function onBusyChanged(): void {
            if (root.isOpen && root.loading)
                root.requestCatalogWhenReady()
        }

        function onCatalogBusyChanged(): void {
            if (root.isOpen && root.loading)
                root.requestCatalogWhenReady()
        }
    }

    IpcHandler {
        target: "vanhyprarch.backgroundPicker"

        function open(): void {
            root.open()
        }

        function close(): void {
            root.close()
        }

        function toggle(): void {
            root.toggle()
        }
    }
}
