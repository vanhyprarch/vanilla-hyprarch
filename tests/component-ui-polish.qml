import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    property int phase: 0
    property int initialDictationStatusRefreshes: 0
    property int initialDictationCatalogRefreshes: 0
    property int initialZigStatusRefreshes: 0

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    function dictationStatus(model, matchesDefaults) {
        return {
            schema_version: 2,
            manager_version: 2,
            component: "local-dictation",
            state: "installed",
            installed: true,
            errors: [],
            voxtype_version: "1.0.1",
            binary_sha256: "b".repeat(64),
            marker: "valid",
            model: model,
            model_integrity: "verified",
            language_mode: "specific",
            languages: ["en"],
            acceleration: "cpu",
            max_duration: 120,
            service_state: "active",
            missing_dependencies: [],
            matches_defaults: matchesDefaults,
            vulkan: {
                state: "unavailable",
                vendor: null,
                vendor_id: null,
                driver: null,
                render_node: null,
                render_node_accessible: false,
                loader_present: false,
                icd_manifest_present: false,
                required_packages: ["vulkan-icd-loader"],
                missing_packages: [],
                runtime_evidence: {
                    collected: false,
                    pid: null,
                    executable_matches: false,
                    vulkan_loader_mapped: false,
                    vendor_icd_mapped: false,
                    render_node_open: false,
                    device_runtime_evidence_valid: null,
                    device_runtime_evidence_rule: null
                }
            }
        }
    }

    function zigStatus(state) {
        const installed = state === "installed"
        return {
            schema_version: 1,
            manager_version: 1,
            component: "zig-screensaver",
            state: state,
            installed: installed,
            capability: installed ? "installed" : "absent",
            version: "v0.1.1",
            architecture: "x86_64",
            marker: installed ? "valid" : "absent",
            cleanup_safe: installed,
            errors: []
        }
    }

    InstallActions { id: installActions }
    RemoveActions { id: removeActions; enumerationEnabled: false }
    UpdateActions {
        id: updateActions
        availabilityChecksEnabled: false
        executionEnabled: false
    }
    PowerActions { id: powerActions }

    SystemComponentsActions {
        id: componentActions
        managerExecutable: "/bin/false"
        executionEnabled: false
    }

    ZigScreensaverActions {
        id: zigActions
        managerExecutable: "/bin/false"
        executionEnabled: false
    }

    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        systemComponentsActions: componentActions
        zigScreensaverActions: zigActions
        powerActions: powerActions
    }

    VisualMetrics { id: metrics }
    Theme { id: theme; metrics: metrics }
    Item { id: anchor }

    SuperSpacePanel {
        id: panel
        controller: superSpace
        metrics: metrics
        theme: theme
        anchorItem: anchor
        screenName: "component-ui-test"
        screenWidth: 1920
        screenHeight: 1080
        dockWidth: 56
    }

    Timer {
        id: startupTimer
        interval: 10
        running: true
        repeat: true
        onTriggered: {
            if (componentActions.statusLoading || zigActions.statusLoading)
                return
            stop()

            root.check(componentActions.statusRefreshSerial === 1
                    && componentActions.catalogRefreshSerial === 1
                    && zigActions.statusRefreshSerial === 1,
                "controllers did not perform exactly one initialization refresh")
            root.initialDictationStatusRefreshes = componentActions.statusRefreshSerial
            root.initialDictationCatalogRefreshes = componentActions.catalogRefreshSerial
            root.initialZigStatusRefreshes = zigActions.statusRefreshSerial

            root.check(componentActions.acceptStatusJson(JSON.stringify(
                    root.dictationStatus("small.en", true))),
                "initial Dictation fixture was rejected")
            root.check(zigActions.acceptStatus(JSON.stringify(
                    root.zigStatus("installed"))),
                "initial Zig fixture was rejected")

            superSpace.open()
            superSpace.enterSection("components")
            root.check(componentActions.statusRefreshSerial
                    === root.initialDictationStatusRefreshes
                    && componentActions.catalogRefreshSerial
                        === root.initialDictationCatalogRefreshes
                    && zigActions.statusRefreshSerial
                        === root.initialZigStatusRefreshes,
                "opening the component catalog launched an authoritative refresh")

            Qt.callLater(function() {
                panel.resetSelection()
                root.check(panel.selectedEntryIdentity
                        === "component:local-dictation",
                    "component catalog did not initially select Local Dictation")
                panel.moveSelection(1)
                root.check(panel.selectedEntryIdentity
                        === "component:zig-screensaver",
                    "Down did not select Zig Screensaver")
                delayedDictationStatus.start()
            })
        }
    }

    Timer {
        id: delayedDictationStatus
        interval: 20
        repeat: false
        onTriggered: {
            root.check(componentActions.acceptStatusJson(JSON.stringify(
                    root.dictationStatus("small", false))),
                "delayed Dictation fixture was rejected")
            Qt.callLater(function() {
                root.check(panel.selectedEntryIdentity
                        === "component:zig-screensaver",
                    "Dictation status completion moved selection away from Zig")
                root.check(superSpace.visibleEntries[0].detail
                        === "Installed · small",
                    "Dictation status completion did not update displayed state")
                panel.activateSelection()
                root.check(superSpace.currentComponentId === "zig-screensaver",
                    "Enter targeted a different component after Dictation completion")

                superSpace.goBack()
                panel.resetSelection()
                root.check(panel.selectEntryAt(1),
                    "mouse-style Zig selection failed")
                root.check(zigActions.acceptStatus(JSON.stringify(
                        root.zigStatus("not-installed"))),
                    "delayed Zig fixture was rejected")
                root.check(panel.selectedEntryIdentity
                        === "component:zig-screensaver",
                    "Zig status completion moved catalog selection")
                panel.moveSelection(-1)
                root.check(panel.selectedEntryIdentity
                        === "component:local-dictation",
                    "keyboard selection diverged after mouse-style selection")
                panel.moveSelection(1)
                root.check(panel.selectedEntryIdentity
                        === "component:zig-screensaver",
                    "keyboard selection did not return coherently to Zig")

                superSpace.close()
                superSpace.open()
                superSpace.enterSection("components")
                root.check(componentActions.statusRefreshSerial
                        === root.initialDictationStatusRefreshes
                        && componentActions.catalogRefreshSerial
                            === root.initialDictationCatalogRefreshes
                        && zigActions.statusRefreshSerial
                            === root.initialZigStatusRefreshes,
                    "close/reopen launched a component refresh")
                panel.resetSelection()
                panel.moveSelection(1)
                componentActions.refreshAll()
                root.check(componentActions.statusRefreshSerial
                        === root.initialDictationStatusRefreshes + 1
                        && componentActions.catalogRefreshSerial
                            === root.initialDictationCatalogRefreshes + 1,
                    "explicit Dictation Refresh did not launch authoritative checks")
                root.phase = 1
                completionTimer.start()
            })
        }
    }

    Timer {
        id: completionTimer
        interval: 10
        repeat: true
        onTriggered: {
            if (root.phase === 1) {
                if (componentActions.statusLoading)
                    return
                root.check(panel.selectedEntryIdentity
                        === "component:zig-screensaver",
                    "failed Dictation refresh reset Zig selection")
                panel.activateSelection()
                root.check(superSpace.currentComponentId === "zig-screensaver",
                    "Enter did not open Zig after explicit Dictation refresh")
                root.check(zigActions.acceptStatus(JSON.stringify(
                        root.zigStatus("installed"))),
                    "installed Zig fixture was rejected after reopen")
                panel.resetSelection()
                root.check(panel.selectedEntryIdentity === "zigRefresh:Refresh",
                    "Zig information or separator entered action navigation")
                zigActions.refreshAll()
                root.check(zigActions.statusRefreshSerial
                        === root.initialZigStatusRefreshes + 1,
                    "explicit Zig Refresh did not launch authoritative status")
                root.phase = 2
                return
            }

            if (root.phase === 2) {
                if (zigActions.statusLoading)
                    return
                root.check(panel.selectedEntryIdentity === "zigRefresh:Refresh",
                    "Zig status completion moved the selected Refresh action")
                stop()
                console.log("vanhyprarch component UI polish self-check passed")
                Qt.quit()
            }
        }
    }
}
