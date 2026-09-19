import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: testRoot

    property int checks: 0
    property var createdWindows: []

    OverlayFocusCoordinator {
        id: coordinator
        focusGrabEnabled: false
    }

    Component {
        id: windowComponent

        QtObject {
            property string windowName: ""
            property string role: "dock"
            property var coordinator: null
            property var focusCompanion: null
            property bool requestedVisible: false
            property bool visible: false
            property int dismissCount: 0

            function dismissFromCoordinator(): void {
                dismissCount++
                visible = false
                coordinator.windowVisibilityChanged(this, role)
            }
        }
    }

    function fail(message): void {
        console.error("OVERLAY_FOCUS_TEST_FAILURE: " + message)
        Qt.quit()
        throw new Error(message)
    }

    function verify(condition, message): void {
        checks++
        if (!condition)
            fail(message)
    }

    function createWindow(windowName, role, focusCompanion): var {
        const window = windowComponent.createObject(testRoot, {
            windowName: windowName,
            role: role,
            coordinator: coordinator,
            focusCompanion: focusCompanion || null
        })
        verify(window !== null, "could not create " + windowName)
        createdWindows.push(window)
        if (role === "central")
            coordinator.registerCentral(window)
        else if (role === "dock")
            coordinator.registerDock(window)
        return window
    }

    function showWindow(window): void {
        window.visible = true
        coordinator.windowVisibilityChanged(window, window.role)
    }

    function destroyWindows(): void {
        for (const window of createdWindows) {
            if (window.role === "central")
                coordinator.unregisterCentral(window)
            else if (window.role === "dock")
                coordinator.unregisterDock(window)
            window.destroy()
        }
        createdWindows = []
    }

    function verifyFirstActivation(dockName, centralName): void {
        const dockHost = createWindow(dockName + " dock host", "host")
        dockHost.visible = true
        const dock = createWindow(dockName, "dock", dockHost)
        const central = createWindow(centralName, "central")
        showWindow(dock)
        verify(dock.visible, dockName + " did not open")
        verify(coordinator.focusWindows.length === 2,
            dockName + " and its host were not the initial focus windows")
        verify(coordinator.focusWindows[0] === dock,
            dockName + " was not initially focused")
        verify(coordinator.focusWindows[1] === dockHost,
            dockName + " host was not whitelisted")

        showWindow(central)
        verify(dock.visible,
            dockName + " closed during " + centralName + " activation")
        verify(central.visible,
            centralName + " missed its first activation")
        verify(coordinator.focusWindows.length === 1,
            centralName + " was not initially prioritized")
        verify(coordinator.focusWindows[0] === central,
            centralName + " was not the priority focus surface")

        coordinator.releaseCentralPriority(central)
        verify(dock.visible && central.visible,
            dockName + " and " + centralName + " cannot coexist")
        verify(coordinator.focusWindows.indexOf(central) >= 0,
            centralName + " is absent from the shared grab")
        verify(coordinator.focusWindows.indexOf(dock) >= 0,
            dockName + " is absent from the shared grab")
        verify(coordinator.focusWindows.indexOf(dockHost) >= 0,
            dockName + " host is absent from the shared grab")
        destroyWindows()
    }

    function run(): void {
        const docks = [
            "App picker",
            "Audio",
            "Bluetooth",
            "Clock",
            "Launcher context",
            "Display",
            "Network",
            "Power & Idle",
            "Power menu"
        ]
        const centrals = ["Super+Space", "Keyboard Shortcuts"]
        for (const dockName of docks) {
            for (const centralName of centrals)
                verifyFirstActivation(dockName, centralName)
        }

        const dockHost = createWindow("Display dock host", "host")
        dockHost.visible = true
        const dock = createWindow("Display", "dock", dockHost)
        const central = createWindow("Super+Space", "central")
        showWindow(dock)
        showWindow(central)
        coordinator.releaseCentralPriority(central)
        coordinator.handleGrabCleared()
        verify(!central.visible, "outside clear did not dismiss central")
        verify(central.dismissCount === 1,
            "central was not dismissed exactly once")
        verify(!dock.visible, "outside clear did not dismiss dock")
        verify(dock.dismissCount === 1,
            "dock was not dismissed exactly once")
        verify(!coordinator.grabRequested,
            "cleared grab was rearmed in the same event-loop turn")
        coordinator.rearmAfterClear()
        verify(!coordinator.grabRequested
                && coordinator.focusWindows.length === 0,
            "outside clear left stale coordinated focus ownership")

        showWindow(dock)

        const shortcuts = createWindow("Keyboard Shortcuts", "central")
        showWindow(central)
        coordinator.releaseCentralPriority(central)
        showWindow(shortcuts)
        verify(!central.visible && central.dismissCount === 2,
            "opening another central surface left a duplicate visible")
        verify(shortcuts.visible && dock.visible,
            "central replacement closed the dock or missed activation")
        shortcuts.dismissFromCoordinator()

        for (let cycle = 0; cycle < 3; ++cycle) {
            showWindow(central)
            verify(dock.visible && central.visible,
                "repeated open missed first activation")
            coordinator.releaseCentralPriority(central)
            central.dismissFromCoordinator()
            verify(!central.visible && dock.visible,
                "repeated close changed dock visibility")
            verify(coordinator.visibleCentralWindows.length === 0,
                "stale visible central surface remains")
            verify(coordinator.visibleDockWindows.length === 1,
                "dock registration was lost")
        }

        destroyWindows()

        const pendingHost = createWindow("pending dock host", "host")
        pendingHost.visible = true
        const pendingDock = createWindow("pending anchor dock", "dock",
            pendingHost)
        pendingDock.requestedVisible = true
        coordinator.windowVisibilityChanged(pendingDock, "dock")
        verify(coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            "unplaceable requested dock entered the focus whitelist")
        showWindow(pendingDock)
        verify(pendingDock.requestedVisible
                && coordinator.focusWindows.indexOf(pendingDock) >= 0
                && coordinator.focusWindows.indexOf(pendingHost) >= 0,
            "placeable pending dock did not acquire focus ownership")
        pendingDock.visible = false
        coordinator.windowVisibilityChanged(pendingDock, "dock")
        verify(pendingDock.requestedVisible
                && coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            "windowless dock retained focus ownership or lost its request")
        destroyWindows()

        const centralOnly = createWindow("Super+Space only", "central")
        coordinator.registerCentral(centralOnly)
        verify(coordinator.centralWindows.length === 1,
            "duplicate central registration accumulated")
        showWindow(centralOnly)
        coordinator.releaseCentralPriority(centralOnly)
        verify(coordinator.focusWindows.length === 1
                && coordinator.focusWindows[0] === centralOnly,
            "central-only state has an invalid whitelist")
        centralOnly.dismissFromCoordinator()
        verify(coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            "both-dismissed state retained a stale grab")
        destroyWindows()

        const hostA = createWindow("monitor A dock host", "host")
        const hostB = createWindow("monitor B dock host", "host")
        hostA.visible = true
        hostB.visible = true
        const dockA = createWindow("monitor A Display", "dock", hostA)
        coordinator.registerDock(dockA)
        verify(coordinator.dockWindows.length === 1,
            "duplicate dock registration accumulated")
        const superA = createWindow("monitor A Super+Space", "central")
        const shortcutsB = createWindow("monitor B Shortcuts", "central")
        showWindow(dockA)
        showWindow(superA)
        coordinator.releaseCentralPriority(superA)
        showWindow(shortcutsB)
        coordinator.releaseCentralPriority(shortcutsB)
        verify(!superA.visible && shortcutsB.visible && dockA.visible,
            "monitor-B central replacement disturbed monitor-A dock")
        verify(coordinator.focusWindows.indexOf(shortcutsB) >= 0
                && coordinator.focusWindows.indexOf(dockA) >= 0
                && coordinator.focusWindows.indexOf(hostA) >= 0
                && coordinator.focusWindows.indexOf(hostB) < 0,
            "multi-monitor whitelist used the wrong dock host")

        showWindow(superA)
        coordinator.releaseCentralPriority(superA)
        verify(!shortcutsB.visible && superA.visible && dockA.visible,
            "Shortcuts-to-SuperSpace switch lost activation or dock")

        dockA.dismissFromCoordinator()
        verify(superA.visible && !dockA.visible,
            "dock dismissal also dismissed the central surface")
        verify(coordinator.focusWindows.length === 1
                && coordinator.focusWindows[0] === superA,
            "central state retained a dismissed dock or host")

        showWindow(dockA)
        coordinator.unregisterDock(dockA)
        dockA.visible = false
        hostA.visible = false
        verify(coordinator.dockWindows.length === 0
                && coordinator.focusWindows.length === 1
                && coordinator.focusWindows[0] === superA,
            "monitor removal left stale dock focus references")

        const dockB = createWindow("monitor B Audio", "dock", hostB)
        showWindow(dockB)
        verify(coordinator.focusWindows.indexOf(superA) >= 0
                && coordinator.focusWindows.indexOf(dockB) >= 0
                && coordinator.focusWindows.indexOf(hostB) >= 0
                && coordinator.focusWindows.indexOf(hostA) < 0,
            "recreated monitor dock has stale or missing companions")

        for (let cycle = 0; cycle < 5; ++cycle) {
            superA.dismissFromCoordinator()
            verify(!superA.visible && dockB.visible,
                "rapid central close dismissed dock")
            showWindow(superA)
            verify(superA.visible && dockB.visible,
                "rapid central open lost first activation")
            coordinator.releaseCentralPriority(superA)
        }
        superA.dismissFromCoordinator()
        dockB.dismissFromCoordinator()
        verify(coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            "final both-dismissed state retained focus ownership")

        destroyWindows()
        console.log("OVERLAY_FOCUS_TEST_PASS checks=" + checks)
        Qt.quit()
    }

    Component.onCompleted: Qt.callLater(run)
}
