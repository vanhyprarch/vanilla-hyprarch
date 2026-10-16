pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root
    property int checks: 0
    property double now: 10000
    property var clients: []
    property var activated: []
    property var focused: []
    property var launches: ({})
    property int actions: 0
    property int nativePhase: 0

    function check(condition, message): void {
        checks++
        if (!condition) throw new Error(message)
    }
    function equal(actual, expected, message): void {
        check(JSON.stringify(actual) === JSON.stringify(expected),
            message + ": " + JSON.stringify(actual))
    }
    function entry(id, startupClass) {
        return { id: id, startupClass: startupClass, actions: [],
            execute: () => { launches[id] = (launches[id] || 0) + 1 } }
    }
    function client(identity, appClass, workspace = 1, address = identity) {
        return { stableId: identity, address: "0x" + address, mapped: true,
            class: appClass, initialClass: appClass, workspace: { id: workspace },
            monitor: 0, xwayland: false }
    }
    function setWindows(rows, foreign = true): void {
        clients = rows
        const windows = rows.map(row => ({ address: row.address, lastIpcObject: row,
            wayland: foreign ? { appId: row.class,
                activate: () => { activated.push(row.stableId) },
                close: () => { actions++ } } : null }))
        manager.toplevels.values = windows
        const ids = Array.from(new Set(rows.map(row => row.workspace.id))).reverse()
        manager.workspaces.values = ids.map(id => ({ id: id,
            toplevels: { values: windows.filter(window =>
                window.lastIpcObject.workspace.id === id) } }))
    }
    function click(application): void {
        controller.activateOrLaunch(application)
        query.reply(clients)
    }
    function reset(): void {
        setWindows([])
        controller.lastSelected = Object.create(null)
        controller.pendingLaunches = Object.create(null)
        activated = []; focused = []; launches = ({})
    }

    QtObject {
        id: catalog
        property QtObject applications: QtObject {
            property var values: [root.entry("foot", "foot"),
                root.entry("firefox", "Firefox"), root.entry("plex", "Plex"),
                root.entry("org.telegram.desktop", "TelegramDesktop")]
        }
        function byId(id) { return applications.values.find(entry => entry.id === id) || null }
        function heuristicLookup(id) { return byId(id) }
    }
    QtObject {
        id: manager
        property QtObject toplevels: QtObject { property var values: [] }
        property QtObject workspaces: QtObject { property var values: [] }
        property var focusedWorkspace: null
        property int refreshes: 0
        signal rawEvent(var event)
        function refreshToplevels(): void { refreshes++ }
    }
    QtObject {
        id: query
        property bool running: false
        property int starts: 0
        signal finished(bool success, string output)
        function start(): void { if (!running) { running = true; starts++ } }
        function reply(rows, success = true): void {
            running = false
            finished(success, JSON.stringify(rows))
        }
    }
    LauncherController {
        id: controller
        compositor: manager
        catalog: catalog
        snapshotQuery: query
        clock: () => root.now
        focusExactWindow: client => { root.focused.push(client.stableId) }
    }
    LauncherController {
        id: nativeController
        compositor: manager
        clock: () => root.now
        focusExactWindow: client => {
            root.focused.push(client.stableId)
            console.log("FOCUS_COMMAND:" + JSON.stringify(focusCommand(client)))
        }
    }
    Connections {
        target: nativeController.snapshotQuery
        function onFinished(success, output): void { Qt.callLater(root.afterNativeQuery) }
    }

    VisualMetrics { id: metrics; viewportWidth: 1000; viewportHeight: 800 }
    Theme { id: theme; metrics: metrics }
    LauncherStore { id: store }
    QtObject {
        id: coordinator
        function toggleDockWindow(window): void { window.requestedVisible = !window.requestedVisible }
    }
    Window {
        visible: true
        width: 120; height: 800
        Launchers {
            id: firstDock
            theme: theme; metrics: metrics; store: store; controller: controller
            targetScreen: Quickshell.screens[0]; focusCoordinator: coordinator
            width: 56; height: 800
        }
        Launchers {
            id: secondDock
            theme: theme; metrics: metrics; store: store; controller: controller
            targetScreen: Quickshell.screens[0]; focusCoordinator: coordinator
            x: 60; width: 56; height: 800
        }
    }

    function mockChecks(): void {
        try {
            const foot = catalog.byId("foot")
            const firefox = catalog.byId("firefox")
            reset()
            click(foot); click(foot); click(foot)
            equal(launches.foot, 1, "rapid primary launches")
            now += 4999; click(foot)
            equal(launches.foot, 1, "guard expires early")
            now++; click(foot)
            equal(launches.foot, 2, "guard did not expire at five seconds")
            now -= 10000; click(foot)
            equal(launches.foot, 3, "clock rollback permanently blocked launch")

            setWindows([client("2", "foot")]); click(foot)
            equal(activated, ["2"], "one local window")
            equal(firstDock.runtimeLaunchers.map(entry => entry.id), ["foot"], "running unpinned launcher")
            store.launchers = [{ desktopId: "foot" }]
            equal(firstDock.runtimeLaunchers.length, 0, "pinned launcher duplicated as unpinned")
            equal(firstDock.resolvedLaunchers.length, 1, "favorite no longer resolves")
            firstDock.beginPinnedDrag("foot")
            equal(firstDock.activeDragDesktopId, "foot", "pinned drag no longer starts")
            firstDock.finishPinnedDrag("foot")
            equal(firstDock.activeDragDesktopId, "", "pinned drag no longer finishes")
            store.launchers = []
            check(controller.pendingLaunches.foot === undefined, "mapped window kept guard")
            setWindows([client("2", "foot", 4)]); click(foot)
            equal(activated, ["2", "2"], "one remote workspace window")
            equal(controller.workspaceIdsForDesktopEntry(foot), [4], "workspace markers")

            reset()
            setWindows([client("10", "foot", 3), client("2", "foot", 1), client("f", "foot", 2)])
            click(foot); manager.focusedWorkspace = { id: 3 }; click(foot)
            manager.focusedWorkspace = { id: 1 }; click(foot); click(foot)
            equal(activated, ["2", "f", "10", "2"], "creation order, focus independence, wrap")
            equal(controller.workspaceIdsForDesktopEntry(foot), [1, 2, 3], "cross-workspace markers")
            setWindows([client("10", "foot", 3), client("f", "foot", 2)]); click(foot)
            equal(activated[activated.length - 1], "f", "closed selection did not advance to successor")
            setWindows([])
            check(controller.lastSelected.foot === undefined, "all closed retained cursor")
            click(foot); equal(launches.foot, 1, "all closed did not relaunch")

            reset()
            setWindows([client("20000000000002", "foot"), client("20000000000001", "foot")])
            click(foot); click(foot)
            equal(activated, ["20000000000001", "20000000000002"], "64-bit identity precision")
            setWindows([client("20000000000001", "foot")]); click(foot)
            equal(activated[activated.length - 1], "20000000000001", "closed final selection did not wrap")
            reset()
            setWindows([client("3", "foot"), client("1", "foot")])
            firstDock.controller.activateOrLaunch(foot)
            secondDock.controller.activateOrLaunch(foot)
            query.reply(clients)
            equal(activated, ["1", "3"], "shared docks and queued rapid cycling")

            reset()
            setWindows([client("1", "foot", 1, "abc")])
            controller.activateOrLaunch(foot)
            query.reply([client("2", "foot", 1, "abc")])
            equal(activated, [], "stale foreign handle reused address")
            equal(focused, ["2"], "fresh replacement identity not used")
            equal(controller.lastSelected.foot, "2", "fresh stable identity not remembered")
            const command = controller.focusCommand(client("2", "foot", 1, "abc"))
            console.log("FOCUS_COMMAND:" + JSON.stringify(command))
            equal(controller.focusCommand(client('2; error("bad")', "foot")), [], "unsafe stable identity")
            equal(controller.focusCommand(client("2", "foot", 1, 'abc"); error("bad")')), [], "unsafe address")
            check(controller.stableId("0") === "", "zero identity")
            check(controller.stableId("0X000A") === "a", "hex normalization")

            reset()
            const delayed = client("2", "foot")
            delete delayed.stableId
            setWindows([delayed]); click(foot)
            equal(launches, {}, "incomplete identity launched duplicate")
            equal(activated, [], "incomplete identity activated")
            setWindows([client("2", "foot")]); click(foot)
            equal(activated, ["2"], "delayed identity did not recover")

            reset()
            const initial = client("2", "changed-class")
            initial.initialClass = "Foot"
            setWindows([initial]); click(foot)
            equal(activated, ["2"], "initialClass matching")
            setWindows([client("3", "org.telegram.desktop")]); click(catalog.byId("org.telegram.desktop"))
            equal(activated[activated.length - 1], "3", "Flatpak desktop ID")
            const xwayland = client("4", "PLEX"); xwayland.xwayland = true
            setWindows([xwayland]); click(catalog.byId("plex"))
            equal(activated[activated.length - 1], "4", "XWayland StartupWMClass")
            setWindows([client("5", "unrelated")])
            manager.toplevels.values[0].wayland.appId = "firefox"
            click(firefox); equal(activated[activated.length - 1], "5", "Wayland appId")
            reset()
            const titled = client("1", "unrelated"); titled.title = "Firefox"
            setWindows([titled]); click(firefox)
            equal(launches.firefox, 1, "title must not match")

            reset()
            setWindows([client("1", "foot")])
            manager.toplevels.values[0].wayland.activate = () => { throw new Error("refused") }
            click(foot); equal(focused, ["1"], "foreign activation fallback")
            setWindows([client("2", "foot", 5)], false); click(foot)
            equal(focused, ["1", "2"], "missing handle exact fallback")
            const floating = client("4", "foot", 3); floating.floating = true
            setWindows([floating]); click(foot)
            equal(activated, ["4"], "floating application window did not activate")
            const unmapped = client("3", "foot"); unmapped.mapped = false
            setWindows([unmapped], false); click(foot)
            equal(focused, ["1", "2"], "unmapped window focused")

            reset()
            foot.actions = [{ id: "new-window", execute: () => { actions++ } }]
            click(foot)
            const before = actions
            controller.openNewWindow(foot); controller.openNewWindow(foot)
            equal(actions, before + 2, "explicit new-window guard bypass")
            equal(launches.foot, 1, "explicit action replaced with ordinary launch")
            setWindows([client("1", "foot")])
            controller.openNewWindow(foot)
            equal(activated, [], "single-instance new-window request became activation")
            controller.closeAllWindows(foot)
            equal(actions, before + 4, "close-all routing")
            foot.actions = [{ id: "other", name: "New Window", execute: () => { actions++ } }]
            controller.openNewWindow(foot); equal(actions, before + 5, "named desktop action")
            foot.actions = []
            controller.openNewWindow(foot); equal(launches.foot, 2, "main desktop-entry fallback")
            equal(store.editRequests, 0, "controller modified preferences")

            reset()
            controller.activateOrLaunch(foot); query.reply([], false)
            equal(launches, {}, "query failure launched application")
            controller.activateOrLaunch(foot); query.reply({ bad: true })
            equal(launches, {}, "invalid snapshot launched application")
            controller.activateOrLaunch(foot); query.reply([null])
            equal(launches, {}, "invalid client launched application")
            click(foot); equal(launches.foot, 1, "query failure prevented recovery")
            manager.rawEvent({ name: "openwindow" })
            manager.rawEvent({ name: "movewindowv2" })
            Qt.callLater(() => {
                try {
                    equal(manager.refreshes, 2, "one lifecycle refresh per test controller")
                    runNativeQuery()
                } catch (error) { fail(error) }
            })
        } catch (error) { fail(error) }
    }

    function fail(error): void { console.error("LAUNCHER_ACTIVATION_FAILURE:" + error.message) }
    function nativeEntry() { return DesktopEntries.byId("dock-fixture-00") }
    function runNativeQuery(): void {
        const code = nativePhase === 2 ? "import sys; sys.exit(7)"
            : nativePhase === 3 ? "print('null')"
            : nativePhase === 4 ? "print('[null]')"
            : nativePhase === 5 ? "import time; time.sleep(8)"
            : nativePhase === 6 ? "print('" + JSON.stringify([client("2", "NativeFixture", 4, "abc")]) + "')"
            : "print('[]')"
        nativeController.snapshotQuery.command = ["/usr/bin/python", "-c", code]
        nativeController.activateOrLaunch(nativeEntry())
    }
    function afterNativeQuery(): void {
        try {
            check(nativeEntry() !== null, "native desktop catalog")
            if (nativePhase === 1) {
                // Exercise the actual menu route, while the primary-launch guard is armed.
                const menu = firstDock.children.find(child => typeof child.openNewWindow === "function")
                check(menu !== undefined, "context menu disappeared")
                menu.desktopEntry = nativeEntry()
                menu.openNewWindow()
            }
            if (nativePhase === 6) {
                equal(nativeController.lastSelected[nativeEntry().id], "2", "native query result not activated")
                console.log("LAUNCHER_ACTIVATION_PASS:" + checks + " activation checks: PASS")
                return
            }
            nativePhase++
            runNativeQuery()
        } catch (error) { fail(error) }
    }
    Component.onCompleted: Qt.callLater(mockChecks)
}
