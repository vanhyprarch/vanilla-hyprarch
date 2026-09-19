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
            property int actionCount: 0

            function dismissFromCoordinator(): void {
                dismissCount++
                requestedVisible = false
                visible = false
                coordinator.windowVisibilityChanged(this, role)
            }
        }
    }

    function fail(message): void {
        console.error("DOCK_DISMISSAL_TEST_FAILURE: " + message)
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
        window.requestedVisible = true
        window.visible = true
        coordinator.windowVisibilityChanged(window, window.role)
        if (window.role === "central")
            coordinator.releaseCentralPriority(window)
    }

    function syncDockVisibility(window): void {
        window.visible = window.requestedVisible
        coordinator.windowVisibilityChanged(window, "dock")
    }

    function toggleDock(window): void {
        coordinator.toggleDockWindow(window)
        syncDockVisibility(window)
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

    // Direct coordinator calls prove application state only. This test cannot
    // prove native stationary-pointer delivery from Wayland.
    function verifyApplicationToggle(panelName): void {
        const host = createWindow(panelName + " host", "host")
        host.visible = true
        const panel = createWindow(panelName, "dock", host)

        toggleDock(panel)
        verify(panel.requestedVisible && panel.visible,
            panelName + " did not open on its first click")
        toggleDock(panel)
        verify(!panel.requestedVisible && !panel.visible,
            panelName + " application toggle did not close on its second call")
        verify(panel.dismissCount === 0,
            panelName + " toggle was replaced by generic dismissal")
        verify(coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            panelName + " immediate toggle left stale focus ownership")
        destroyWindows()
    }

    function verifyPanelDismissesCentral(centralName, panelName): void {
        const host = createWindow(panelName + " host", "host")
        host.visible = true
        const panel = createWindow(panelName, "dock", host)
        const central = createWindow(centralName, "central")
        showWindow(panel)
        showWindow(central)

        panel.actionCount++
        coordinator.dockSurfaceInteracted()

        verify(panel.visible, panelName + " closed during its control action")
        verify(panel.actionCount === 1,
            panelName + " did not receive the central-dismissing click")
        verify(!central.visible && central.dismissCount === 1,
            centralName + " remained open after " + panelName + " interaction")
        verify(coordinator.focusWindows.length === 2
                && coordinator.focusWindows.indexOf(panel) >= 0
                && coordinator.focusWindows.indexOf(host) >= 0,
            panelName + " whitelist was not preserved after central dismissal")
        destroyWindows()
    }

    function run(): void {
        for (const panelName of ["Display", "Audio", "Network"])
            verifyApplicationToggle(panelName)

        for (const panelName of ["Display", "Audio", "Network"]) {
            for (const centralName of ["Super+Space", "Keyboard Shortcuts"])
                verifyPanelDismissesCentral(centralName, panelName)
        }

        let host = createWindow("Display host", "host")
        host.visible = true
        let display = createWindow("Display", "dock", host)
        showWindow(display)
        coordinator.dockBackgroundInteracted()
        verify(!display.visible && display.dismissCount === 1,
            "empty dock background did not dismiss the dock panel")
        verify(coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            "empty dock background left focus ownership")
        destroyWindows()

        host = createWindow("Display host", "host")
        host.visible = true
        display = createWindow("Display", "dock", host)
        let central = createWindow("Super+Space", "central")
        showWindow(display)
        showWindow(central)
        coordinator.dockBackgroundInteracted()
        verify(!display.visible && !central.visible,
            "empty dock background did not dismiss both transient surfaces")
        verify(display.dismissCount === 1 && central.dismissCount === 1,
            "empty dock background did not dismiss each surface exactly once")
        destroyWindows()

        host = createWindow("Display host", "host")
        host.visible = true
        display = createWindow("Display", "dock", host)
        central = createWindow("Keyboard Shortcuts", "central")
        showWindow(display)
        showWindow(central)
        toggleDock(display)
        verify(!display.visible && !central.visible,
            "same owning icon did not close both active transients")
        verify(display.dismissCount === 0 && central.dismissCount === 1,
            "generic dismissal raced the explicit same-icon toggle")
        destroyWindows()

        const hostA = createWindow("Display host", "host")
        const hostB = createWindow("Audio host", "host")
        hostA.visible = true
        hostB.visible = true
        display = createWindow("Display", "dock", hostA)
        const audio = createWindow("Audio", "dock", hostB)
        central = createWindow("Super+Space", "central")
        showWindow(display)
        showWindow(central)
        toggleDock(audio)
        verify(!display.visible && audio.visible && !central.visible,
            "different dock control did not replace the panel and dismiss central")
        verify(display.dismissCount === 1 && audio.dismissCount === 0,
            "different dock control changed the existing replacement semantics")
        destroyWindows()

        host = createWindow("Display host", "host")
        host.visible = true
        display = createWindow("Display", "dock", host)
        central = createWindow("Super+Space", "central")
        showWindow(display)
        showWindow(central)
        coordinator.handleGrabCleared()
        verify(!display.visible && !central.visible,
            "external outside clear did not dismiss every transient surface")
        verify(display.dismissCount === 1 && central.dismissCount === 1,
            "external outside clear did not dismiss each surface exactly once")
        verify(!coordinator.grabRequested,
            "external outside clear rearmed in the same event-loop turn")
        coordinator.rearmAfterClear()
        verify(coordinator.focusWindows.length === 0
                && !coordinator.grabRequested,
            "external outside clear left stale coordinator state")
        destroyWindows()

        host = createWindow("Network host", "host")
        host.visible = true
        const network = createWindow("Network", "dock", host)
        for (let cycle = 0; cycle < 8; ++cycle) {
            toggleDock(network)
            verify(network.visible && coordinator.grabRequested,
                "repeated open lost coordinator state")
            toggleDock(network)
            verify(!network.visible && !coordinator.grabRequested
                    && coordinator.focusWindows.length === 0,
                "repeated close retained stale coordinator state")
        }
        destroyWindows()

        console.log("DOCK_DISMISSAL_TEST_PASS checks=" + checks)
        Qt.quit()
    }

    Component.onCompleted: Qt.callLater(run)
}
