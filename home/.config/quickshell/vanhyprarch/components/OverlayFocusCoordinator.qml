import QtQuick
import Quickshell
import Quickshell.Hyprland

Scope {
    id: root

    property bool focusGrabEnabled: true
    property bool grabRequested: false
    property var priorityCentralWindow: null
    property var dockWindows: []
    property var centralWindows: []
    property int visibilityRevision: 0

    readonly property var visibleDockWindows:
        root.visibleWindows(root.dockWindows)
    readonly property var visibleCentralWindows:
        root.visibleWindows(root.centralWindows)
    readonly property var visibleDockCompanions:
        root.dockCompanions(root.visibleDockWindows)
    readonly property var focusWindows: {
        root.visibilityRevision
        if (root.priorityCentralWindow
                && root.priorityCentralWindow.visible)
            return [root.priorityCentralWindow]
        if (root.visibleCentralWindows.length > 0)
            return root.uniqueWindows(root.visibleCentralWindows
                .concat(root.visibleDockWindows,
                    root.visibleDockCompanions))
        return root.uniqueWindows(root.visibleDockWindows
            .concat(root.visibleDockCompanions))
    }

    function visibleWindows(windows): var {
        root.visibilityRevision
        return windows.filter(window => window && window.visible)
    }

    function uniqueWindows(windows): var {
        const unique = []
        for (const window of windows) {
            if (window && unique.indexOf(window) < 0)
                unique.push(window)
        }
        return unique
    }

    function dockCompanions(windows): var {
        const companions = []
        for (const window of windows) {
            const companion = window ? window.focusCompanion : null
            if (companion && companion.visible
                    && companions.indexOf(companion) < 0)
                companions.push(companion)
        }
        return companions
    }

    function registerDock(window): void {
        if (root.dockWindows.indexOf(window) < 0)
            root.dockWindows = root.dockWindows.concat([window])
        root.visibilityRevision++
        root.refreshGrabRequest()
    }

    function unregisterDock(window): void {
        root.dockWindows = root.dockWindows.filter(candidate =>
            candidate !== window)
        root.visibilityRevision++
        root.refreshGrabRequest()
    }

    function registerCentral(window): void {
        if (root.centralWindows.indexOf(window) < 0)
            root.centralWindows = root.centralWindows.concat([window])
        root.visibilityRevision++
        root.refreshGrabRequest()
    }

    function unregisterCentral(window): void {
        root.centralWindows = root.centralWindows.filter(candidate =>
            candidate !== window)
        if (root.priorityCentralWindow === window)
            root.priorityCentralWindow = null
        root.visibilityRevision++
        root.refreshGrabRequest()
    }

    function dismissWindow(window): void {
        if (window && typeof window.dismissFromCoordinator === "function")
            window.dismissFromCoordinator()
    }

    function dismissVisibleWindows(windows): void {
        for (const window of windows) {
            if (window && window.visible)
                root.dismissWindow(window)
        }
    }

    function dockSurfaceInteracted(): void {
        // Dock surfaces remain inside the compositor focus whitelist so the
        // original pointer event reaches them. They are nevertheless outside
        // the central overlay's application-level dismissal boundary.
        root.dismissVisibleWindows(root.visibleCentralWindows)
    }

    function dockBackgroundInteracted(): void {
        // The persistent dock is not transient content. Its non-actionable
        // background is outside both kinds of transient surface.
        root.dismissVisibleWindows(root.visibleCentralWindows)
        root.dismissVisibleWindows(root.visibleDockWindows)
    }

    function toggleDockWindow(window): void {
        if (!window)
            return

        // An owning control's toggle is explicit and must not be folded into
        // generic dock-background dismissal.
        root.dismissVisibleWindows(root.visibleCentralWindows)
        window.requestedVisible = !window.requestedVisible
    }

    function closeOtherWindows(window, windows): void {
        for (const candidate of windows) {
            if (candidate && candidate !== window && candidate.visible)
                root.dismissWindow(candidate)
        }
    }

    function windowVisibilityChanged(window, role): void {
        if (window.visible) {
            if (role === "central") {
                root.closeOtherWindows(window, root.centralWindows)
                root.priorityCentralWindow = window
            } else {
                root.closeOtherWindows(window, root.dockWindows)
            }
        } else if (root.priorityCentralWindow === window) {
            root.priorityCentralWindow = null
        }

        root.visibilityRevision++
        root.refreshGrabRequest()

        if (role === "central" && window.visible) {
            Qt.callLater(function() {
                root.releaseCentralPriority(window)
            })
        }
    }

    function releaseCentralPriority(window): void {
        if (root.priorityCentralWindow === window) {
            root.priorityCentralWindow = null
            root.visibilityRevision++
            root.refreshGrabRequest()
        }
    }

    function refreshGrabRequest(): void {
        root.grabRequested = root.focusWindows.length > 0
    }

    function handleGrabCleared(): void {
        root.grabRequested = false
        root.priorityCentralWindow = null

        // A compositor clear is a real outside-shell interaction, not an
        // interaction transfer between whitelisted shell surfaces.
        root.dismissVisibleWindows(root.visibleCentralWindows)
        root.dismissVisibleWindows(root.visibleDockWindows)

        // Visibility callbacks above may observe another still-visible window.
        // Keep the cleared grab inactive until the next event-loop turn.
        root.grabRequested = false
        root.visibilityRevision++
        Qt.callLater(root.rearmAfterClear)
    }

    function rearmAfterClear(): void {
        root.refreshGrabRequest()
    }

    HyprlandFocusGrab {
        active: root.focusGrabEnabled && root.grabRequested
            && root.focusWindows.length > 0
        windows: root.focusWindows
        onCleared: root.handleGrabCleared()
    }
}
