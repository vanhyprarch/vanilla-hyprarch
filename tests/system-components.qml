import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root
    property int reloadRequests: 0
    property int reloadCompletions: 0
    property int refreshRequests: 0
    property int lifecyclePhase: 0
    property var lifecycleEvents: []
    readonly property string successFixture:
        Quickshell.env("VANHYPRARCH_COMPONENT_PROCESS_SUCCESS")
    readonly property string failureFixture:
        Quickshell.env("VANHYPRARCH_COMPONENT_PROCESS_FAILURE")
    readonly property string managerSuccessFixture:
        Quickshell.env("VANHYPRARCH_COMPONENT_MANAGER_SUCCESS")
    readonly property string managerFailureFixture:
        Quickshell.env("VANHYPRARCH_COMPONENT_MANAGER_FAILURE")
    readonly property string terminalHelper:
        Quickshell.env("VANHYPRARCH_TERMINAL_HELPER")
    readonly property string footFixture:
        Quickshell.env("VANHYPRARCH_FOOT_FIXTURE")

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
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
        checksEnabled: false
        executionEnabled: false
    }
    ZigScreensaverActions {
        id: zigScreensaverActions
        checksEnabled: false
        executionEnabled: false
    }
    Connections {
        target: componentActions
        function onOperationTerminalCompleted(operationKind, exitCode) {
            root.lifecycleEvents = root.lifecycleEvents.concat(
                ["terminal:" + operationKind + ":" + exitCode])
        }
        function onHyprlandReloadRequested() {
            root.reloadRequests += 1
            root.lifecycleEvents = root.lifecycleEvents.concat(["reload-start"])
        }
        function onHyprlandReloadCompleted(exitCode) {
            root.reloadCompletions += 1
            root.lifecycleEvents = root.lifecycleEvents.concat(
                ["reload-exit:" + exitCode])
        }
        function onRefreshRequested() {
            root.refreshRequests += 1
            root.lifecycleEvents = root.lifecycleEvents.concat(["refresh"])
        }
    }
    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        systemComponentsActions: componentActions
        zigScreensaverActions: zigScreensaverActions
        powerActions: powerActions
    }
    SuperSpacePanelHarness {
        id: superSpacePanel
        controller: superSpace
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            const models = [
                ["tiny", "Tiny — Multilingual", "multilingual", 77691713],
                ["tiny.en", "Tiny — English", "english", 77704715],
                ["base", "Base — Multilingual", "multilingual", 147951465],
                ["base.en", "Base — English", "english", 147964211],
                ["small", "Small — Multilingual", "multilingual", 487601967],
                ["small.en", "Small — English", "english", 487614201],
                ["medium", "Medium — Multilingual", "multilingual", 1533763059],
                ["medium.en", "Medium — English", "english", 1533774781],
                ["large-v3", "Large v3 — Multilingual", "multilingual", 3095033483],
                ["large-v3-turbo", "Large v3 Turbo — Multilingual", "multilingual", 1624555275]
            ].map(item => ({
                id: item[0],
                label: item[1],
                family: item[2],
                filename: "ggml-" + item[0] + ".bin",
                size: item[3],
                sha256: "a".repeat(64),
                transport_url: "https://example.invalid/" + item[0],
                provenance_url: "https://example.invalid/revision/" + item[0]
            }))
            const languages = ["en", "fr", "de", "it", "es", "pt", "nl",
                "pl", "zh", "ja", "ko", "ru", "ar"].map(code => ({
                    id: code,
                    label: code === "en" ? "English" : code === "it" ? "Italian" : code.toUpperCase()
                }))
            const catalog = {
                schema_version: 2,
                manager_version: 2,
                component: "local-dictation",
                defaults: {
                    model: "small.en",
                    language_mode: "specific",
                    languages: ["en"],
                    acceleration: "cpu",
                    max_duration: 120
                },
                models: models,
                languages: languages,
                durations: [
                    { seconds: 30, label: "30 seconds" },
                    { seconds: 60, label: "1 minute" },
                    { seconds: 120, label: "2 minutes" },
                    { seconds: 300, label: "5 minutes" }
                ],
                accelerations: [
                    { id: "cpu", label: "CPU", ui_selectable: true,
                        hardware_validation: "complete" },
                    { id: "vulkan", label: "Vulkan GPU", ui_selectable: true,
                        hardware_validation: "complete" }
                ],
                ui_policy: {
                    selectable_accelerations: ["cpu", "vulkan"],
                    vulkan: "supported-explicit-opt-in"
                }
            }
            root.check(componentActions.acceptCatalogJson(JSON.stringify(catalog)),
                "valid catalog was rejected")
            const status = {
                schema_version: 2,
                manager_version: 2,
                component: "local-dictation",
                state: "installed",
                installed: true,
                errors: [],
                voxtype_version: "1.0.1",
                binary_sha256: "b".repeat(64),
                marker: "valid",
                model: "small.en",
                model_integrity: "verified",
                language_mode: "specific",
                languages: ["en"],
                acceleration: "cpu",
                max_duration: 120,
                service_state: "active",
                missing_dependencies: [],
                matches_defaults: true,
                vulkan: {
                    state: "ready",
                    vendor: "amd",
                    vendor_id: "0x1002",
                    driver: "amdgpu",
                    render_node: "/dev/dri/renderD128",
                    render_node_accessible: true,
                    loader_present: true,
                    icd_manifest_present: true,
                    required_packages: ["vulkan-icd-loader", "vulkan-radeon"],
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
            const absentStatus = Object.assign({}, status, {
                state: "not-installed",
                installed: false,
                voxtype_version: null,
                binary_sha256: null,
                model_integrity: "missing",
                service_state: "absent",
                marker: "absent"
            })
            root.check(componentActions.acceptStatusJson(JSON.stringify(absentStatus)),
                "valid not-installed status was rejected")
            superSpace.enterSection("components")
            superSpace.openComponent("local-dictation")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind !== "componentSeparator").map(entry => entry.label).join(",")
                    === "Local Dictation,Vanilla default,Install",
                "not-installed component page is wrong")
            superSpace.goBack()
            root.check(componentActions.acceptStatusJson(JSON.stringify(status)),
                "valid status was rejected")
            root.check(!componentActions.acceptStatusJson("{bad"),
                "malformed status was accepted")
            root.check(componentActions.statusData.state === "error"
                    && !componentActions.statusData.installed,
                "malformed status retained stale Installed state")
            const statusWithExtraField = Object.assign({}, status, { unexpected: true })
            root.check(!componentActions.acceptStatusJson(
                    JSON.stringify(statusWithExtraField)),
                "status with an unknown schema field was accepted")
            componentActions.acceptStatusJson(JSON.stringify(status))

            root.check(superSpace.sections.map(section => section.label).join(",")
                === "Apps,Install,Remove,Update,Additional system components,Power",
                "root order is wrong")
            root.check(superSpace.sections[4].label === "Additional system components",
                "component root label capitalization is wrong")
            root.check(superSpace.sections[4].detail
                    === "Install and configure optional Vanilla HyprArch components",
                "component root description is wrong")
            const zigAbsent = {
                schema_version: 1, manager_version: 1, component: "zig-screensaver",
                state: "not-installed", installed: false, capability: "absent",
                version: "v0.1.1", architecture: "x86_64", marker: "absent",
                cleanup_safe: true, errors: []
            }
            root.check(zigScreensaverActions.acceptStatus(JSON.stringify(zigAbsent)),
                "valid Zig Screensaver status was rejected")
            superSpace.enterSection("components")
            root.check(superSpace.currentSection === "components"
                    && superSpace.visibleEntries.length === 2
                    && superSpace.visibleEntries[0].componentId === "local-dictation"
                    && superSpace.visibleEntries[1].componentId === "zig-screensaver",
                "component catalog navigation failed")
            root.check(superSpace.visibleEntries.map(entry => entry.label).join(",")
                    === "Local Dictation,Zig Screensaver",
                "optional components are not explicit siblings in product order")
            superSpace.openComponent("zig-screensaver")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind !== "componentSeparator").map(entry => entry.label).join(",")
                    === "Zig Screensaver,Pinned release,Install",
                "not-installed Zig Screensaver page is wrong")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.selectable !== false).map(entry => entry.label).join(",")
                    === "Install",
                "not-installed Zig Screensaver actions are not exactly Install")
            const zigInstalled = Object.assign({}, zigAbsent, {
                state: "installed", installed: true, capability: "installed",
                marker: "valid", cleanup_safe: true
            })
            root.check(zigScreensaverActions.acceptStatus(JSON.stringify(zigInstalled)),
                "installed Zig Screensaver status was rejected")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.selectable !== false).map(entry => entry.label).join(",")
                    === "Check status,Uninstall",
                "installed Zig Screensaver actions are not exact")
            root.check(!superSpace.visibleEntries.some(entry =>
                    entry.label === "Refresh" || entry.label === "Reinstall"),
                "legacy Zig action wording remains on the installed page")
            root.check(!superSpace.visibleEntries.some(entry =>
                    entry.label === "Configure in Power & Idle"),
                "removed Power & Idle shortcut remains on the Zig page")
            const zigInfo = superSpace.visibleEntries[0]
            const zigSeparator = superSpace.visibleEntries[1]
            root.check(zigInfo.label === "Status" && zigInfo.informational === true
                    && zigInfo.selectable === false && zigInfo.enabled === true,
                "Zig Status is not normal non-selectable information")
            root.check(zigSeparator.kind === "componentSeparator"
                    && zigSeparator.selectable === false,
                "Zig information/action separator is missing or navigable")
            superSpace.enterSection("components")
            superSpace.openComponent("zig-screensaver")
            zigScreensaverActions.uninstallPlan = {
                schema_version: 1, component: "zig-screensaver",
                stored_lock: "screensaver", resulting_lock: "display",
                plan_token: "a".repeat(64)
            }
            zigScreensaverActions.uninstallPlanValid = true
            superSpace.componentSubview = "uninstall"
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind !== "componentSeparator").map(entry => entry.label).join(",")
                    === "Uninstall Zig Screensaver?,Automatic Lock after removal,Preserved settings,Cancel,Confirm uninstall"
                    && superSpace.visibleEntries[1].detail === "Display Off",
                "bound uninstall confirmation did not disclose the exact lock destination")
            superSpace.componentSubview = ""
            const zigIncomplete = Object.assign({}, zigAbsent, {
                state: "incomplete", capability: "incomplete", marker: "valid",
                cleanup_safe: false, errors: ["damaged player"]
            })
            root.check(zigScreensaverActions.acceptStatus(JSON.stringify(zigIncomplete)),
                "incomplete Zig Screensaver status was rejected")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind !== "componentSeparator").map(entry => entry.label).join(",")
                    === "Status,Details,Check status,Repair",
                "unsafe incomplete Zig Screensaver exposed Clean up")
            const zigErrorCleanable = Object.assign({}, zigIncomplete, {
                state: "error", marker: "invalid", cleanup_safe: true
            })
            root.check(zigScreensaverActions.acceptStatus(JSON.stringify(zigErrorCleanable)),
                "cleanable Zig Screensaver error status was rejected")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind !== "componentSeparator").map(entry => entry.label).join(",")
                    === "Status,Details,Check status,Repair,Clean up",
                "manager-proven Clean up action was not surfaced exactly")
            root.check(!superSpace.visibleEntries.some(entry =>
                    entry.label === "Refresh"
                        || String(entry.label || "").indexOf("Reinstall") >= 0),
                "legacy Zig recovery wording remains on the error page")
            root.check(zigScreensaverActions.commandFor("reinstall", "").length > 0,
                "technical reinstall API was removed with the user-facing action")
            root.check(zigScreensaverActions.commandFor("repair", "").slice(-2).join("=")
                    === "vanhyprarch-screensaver=repair",
                "Repair is not wired to the approved repair lifecycle")
            root.check(zigScreensaverActions.commandFor("uninstall", "").length === 0
                    && zigScreensaverActions.commandFor("uninstall", "a".repeat(64)).slice(-2).join("=")
                        === "--plan-token=" + "a".repeat(64),
                "uninstall command was not bound to its approved plan token")
            root.check(["install", "adopt", "reinstall", "uninstall", "repair", "clean-up"]
                    .map(operation => superSpace.zigBusyLabel(operation)).join(",")
                    === "Installing,Adopting,Reinstalling,Uninstalling,Repairing,Cleaning up",
                "Zig Screensaver busy-state labels are not exact")
            superSpace.goBack()
            superSpace.openComponent("local-dictation")
            root.check(superSpace.currentComponentId === "local-dictation",
                "Local Dictation page did not open")
            const dictationInfo = superSpace.visibleEntries.slice(0, 2)
            root.check(dictationInfo.map(entry => entry.label).join(",")
                    === "Current Settings,Status"
                    && dictationInfo.every(entry => entry.informational === true
                        && entry.selectable === false && entry.enabled === true),
                "Local Dictation information is not normal and non-selectable")
            root.check(superSpace.visibleEntries[2].kind === "componentSeparator"
                    && superSpace.visibleEntries[2].selectable === false,
                "Local Dictation information/action separator is missing or navigable")
            superSpacePanel.resetSelection()
            root.check(superSpace.visibleEntries[superSpacePanel.selectedEntryIndex].label
                    === "Acceleration",
                "component navigation did not skip information and separator rows")
            const vulkanStatus = Object.assign({}, status, {
                acceleration: "vulkan",
                matches_defaults: false
            })
            root.check(componentActions.acceptStatusJson(JSON.stringify(vulkanStatus)),
                "manually active Vulkan status was rejected")
            const accelerationEntry = superSpace.visibleEntries.find(entry =>
                entry.label === "Acceleration")
            root.check(accelerationEntry && accelerationEntry.detail === "Vulkan GPU",
                "manually active Vulkan acceleration is not displayed")
            root.check(accelerationEntry.kind === "dictationAccelerationView",
                "Acceleration did not become a nested selector")
            superSpace.componentSubview = "acceleration"
            root.check(!superSpace.visibleEntries[0].active
                    && superSpace.visibleEntries[1].active,
                "current Vulkan acceleration was not selected")
            superSpace.goBack()
            root.check(superSpace.componentSubview === "",
                "Acceleration selector Back did not return to Local Dictation")
            superSpace.componentSubview = "acceleration"
            superSpace.activate(superSpace.visibleEntries[0])
            root.check(componentActions.proposedAcceleration === "cpu"
                    && componentActions.statusData.acceleration === "vulkan",
                "selecting CPU mutated the current Vulkan state")
            root.check(componentActions.commandForApply()[
                    componentActions.commandForApply().indexOf("--acceleration") + 1]
                    === "cpu",
                "CPU proposal was not carried in Apply argv")
            componentActions.acceptStatusJson(JSON.stringify(vulkanStatus))
            componentActions.proposedMaxDuration = 60
            root.check(componentActions.commandForApply().indexOf("vulkan") >= 0,
                "settings Apply would silently replace a manually active Vulkan artifact")
            componentActions.acceptStatusJson(JSON.stringify(status))
            superSpace.componentSubview = "acceleration"
            root.check(superSpace.visibleEntries.map(entry => entry.label).join(",")
                    === "CPU,Vulkan GPU",
                "Acceleration selector does not contain exactly CPU and Vulkan GPU")
            root.check(!superSpace.visibleEntries.some(entry => entry.label === "Auto"),
                "Acceleration selector exposed an Auto choice")
            root.check(superSpace.visibleEntries[0].active
                    && !superSpace.visibleEntries[1].active,
                "current CPU acceleration was not selected")
            root.check(superSpace.visibleEntries[0].detail === "Vanilla default"
                    && superSpace.visibleEntries[1].detail === "Ready",
                "acceleration readiness copy is wrong")
            const liveAcceleration = componentActions.statusData.acceleration
            superSpace.activate(superSpace.visibleEntries[1])
            root.check(componentActions.proposedAcceleration === "vulkan"
                    && componentActions.statusData.acceleration === liveAcceleration,
                "selecting Vulkan mutated live state instead of proposed state")
            root.check(componentActions.proposalChanged,
                "Vulkan proposal did not enable Apply")
            const vulkanCommand = componentActions.commandForApply()
            root.check(vulkanCommand[vulkanCommand.indexOf("--acceleration") + 1]
                    === "vulkan",
                "Apply argv does not contain the proposed Vulkan acceleration")
            root.check(vulkanCommand.indexOf("sh") < 0
                    && vulkanCommand.indexOf("bash") < 0
                    && vulkanCommand.indexOf("eval") < 0,
                "Vulkan Apply uses shell evaluation")
            superSpace.componentSubview = "acceleration"
            superSpace.activate(superSpace.visibleEntries[0])
            root.check(componentActions.proposedAcceleration === "cpu"
                    && componentActions.statusData.acceleration === "cpu",
                "selecting CPU did not remain proposal-only")
            root.check(!componentActions.proposalChanged,
                "unchanged CPU proposal left Apply enabled")
            const missingVulkan = Object.assign({}, status, {
                vulkan: Object.assign({}, status.vulkan, {
                    state: "missing-prerequisites",
                    missing_packages: ["vulkan-radeon"]
                })
            })
            root.check(componentActions.acceptStatusJson(JSON.stringify(missingVulkan)),
                "missing-prerequisite Vulkan status was rejected")
            superSpace.componentSubview = "acceleration"
            root.check(superSpace.visibleEntries[1].detail
                    === "Requirements will be installed when applied",
                "missing Vulkan requirements are not explained")
            const missingLiveAcceleration = componentActions.statusData.acceleration
            superSpace.activate(superSpace.visibleEntries[1])
            root.check(componentActions.statusData.acceleration === missingLiveAcceleration
                    && componentActions.proposedAcceleration === "vulkan",
                "missing-prerequisite selection mutated live acceleration")
            componentActions.acceptStatusJson(JSON.stringify(status))
            superSpace.componentSubview = "uninstall"
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind !== "componentSeparator").map(entry => entry.label).join(",")
                    === "Uninstall Local Dictation?,Vanilla component manager,Cancel,Confirm uninstall",
                "uninstall confirmation entries are wrong")
            root.check(superSpace.visibleEntries[0].detail
                    === "This will remove Voxtype, its configuration, and all downloaded speech models.",
                "uninstall confirmation does not explain data deletion")
            root.check(superSpace.visibleEntries[1].detail
                    === "Will remain available so Local Dictation can be installed again later.",
                "uninstall confirmation does not explain manager retention")
            root.check(superSpace.visibleEntries.find(entry =>
                    entry.kind === "dictationUninstallConfirm").detail
                    === "Remove Local Dictation and all of its data",
                "uninstall confirmation action is not destructive-explicit")
            superSpace.goBack()
            superSpace.componentSubview = "model"
            root.check(superSpace.visibleEntries.length === 10,
                "model selector did not expose ten models")
            superSpace.goBack()
            root.check(superSpace.currentComponentId === "local-dictation"
                    && superSpace.componentSubview === "",
                "selector Back did not return to component")
            superSpace.goBack()
            root.check(superSpace.currentSection === "components"
                    && superSpace.currentComponentId === "",
                "component Back did not return to component list")
            superSpace.goBack()
            root.check(superSpace.currentSection === "root",
                "component-list Back did not return to root")
            superSpace.isOpen = true
            superSpace.goBack()
            root.check(!superSpace.isOpen, "root Back did not close SuperSpace")

            root.check(componentActions.selectModel("small"),
                "multilingual model selection failed")
            componentActions.proposedLanguageMode = "selected"
            componentActions.proposedLanguages = ["it", "en"]
            componentActions.proposedMaxDuration = 300
            root.check(componentActions.proposalValid
                    && componentActions.proposalChanged,
                "valid customized proposal was rejected")
            const command = componentActions.commandForApply()
            root.check(command.join("\n") === [
                componentActions.terminalOperation,
                "--supervise-foot",
                "/usr/bin/foot",
                "Vanilla HyprArch Local Dictation",
                "--",
                "vanhyprarch-dictation",
                "apply",
                "--model", "small",
                "--language-mode", "selected",
                "--language", "it",
                "--language", "en",
                "--acceleration", "cpu",
                "--max-duration", "300"
            ].join("\n"), "Apply command is not exact argv")
            for (const forbidden of ["sh", "bash", "eval", "vulkan"])
                root.check(command.indexOf(forbidden) < 0,
                    "forbidden Apply argument: " + forbidden)
            root.check(componentActions.commandForInstall().join("\n") === [
                componentActions.terminalOperation,
                "--supervise-foot",
                "/usr/bin/foot",
                "Vanilla HyprArch Local Dictation",
                "--",
                "vanhyprarch-dictation",
                "install"
            ].join("\n"), "Install command is not exact argv")
            root.check(componentActions.commandForUninstall().join("\n") === [
                componentActions.terminalOperation,
                "--supervise-foot",
                "/usr/bin/foot",
                "Vanilla HyprArch Local Dictation",
                "--",
                "vanhyprarch-dictation",
                "uninstall"
            ].join("\n"), "Uninstall command is not exact argv")
            root.check(componentActions.commandForHyprlandReload().join("\n") === [
                "/usr/bin/hyprctl",
                "reload"
            ].join("\n"), "Hyprland reload is not exact shell-free argv")

            componentActions.selectModel("small.en")
            root.check(componentActions.proposedLanguageMode === "specific"
                    && componentActions.proposedLanguages.join(",") === "en",
                ".en model did not force English")

            root.check(root.successFixture !== "" && root.failureFixture !== ""
                    && root.managerSuccessFixture !== ""
                    && root.managerFailureFixture !== ""
                    && root.terminalHelper !== "" && root.footFixture !== "",
                "process lifecycle fixtures are unavailable")
            componentActions.executionEnabled = true
            componentActions.checksEnabled = false
            componentActions.footExecutable = root.footFixture
            componentActions.hyprctlExecutable = root.successFixture
            componentActions.terminalOperation = root.terminalHelper
            componentActions.managerExecutable = root.managerSuccessFixture
            root.reloadRequests = 0
            root.reloadCompletions = 0
            root.refreshRequests = 0
            root.lifecycleEvents = []
            root.lifecyclePhase = 1
            root.check(componentActions.execute(
                    componentActions.commandForInstall(), "install"),
                "could not start the successful Install lifecycle test")
            root.check(root.lifecycleEvents.length === 0,
                "Install completion ran before the tracked terminal exited")
            lifecycleTimer.start()
        }
    }

    Timer {
        id: lifecycleTimer
        interval: 10
        repeat: true

        function expectEvents(expected, message): void {
            root.check(root.lifecycleEvents.join(",") === expected.join(","),
                message + ": " + root.lifecycleEvents.join(","))
        }

        onTriggered: {
            if (componentActions.operationRunning)
                return

            if (root.lifecyclePhase === 1) {
                expectEvents(["terminal:install:0", "reload-start",
                    "reload-exit:0", "refresh"],
                    "successful Install lifecycle order is wrong")
                root.check(root.reloadRequests === 1
                        && root.reloadCompletions === 1,
                    "successful Install did not execute exactly one reload")
                root.lifecycleEvents = []
                root.lifecyclePhase = 2
                root.check(componentActions.execute(
                        componentActions.commandForUninstall(), "uninstall"),
                    "could not start the successful Uninstall lifecycle test")
                return
            }

            if (root.lifecyclePhase === 2) {
                expectEvents(["terminal:uninstall:0", "reload-start",
                    "reload-exit:0", "refresh"],
                    "successful Uninstall lifecycle order is wrong")
                root.check(root.reloadRequests === 2
                        && root.reloadCompletions === 2,
                    "successful Uninstall did not execute exactly one reload")
                componentActions.managerExecutable = root.managerFailureFixture
                root.lifecycleEvents = []
                root.lifecyclePhase = 3
                root.check(componentActions.execute(
                        componentActions.commandForInstall(), "install"),
                    "could not start the failed Install lifecycle test")
                return
            }

            if (root.lifecyclePhase === 3) {
                expectEvents(["terminal:install:1", "refresh"],
                    "failed Install lifecycle order is wrong")
                root.check(root.reloadRequests === 2,
                    "failed Install executed a Hyprland reload")
                root.lifecycleEvents = []
                root.lifecyclePhase = 4
                root.check(componentActions.execute(
                        componentActions.commandForUninstall(), "uninstall"),
                    "could not start the failed Uninstall lifecycle test")
                return
            }

            if (root.lifecyclePhase === 4) {
                expectEvents(["terminal:uninstall:1", "refresh"],
                    "failed Uninstall lifecycle order is wrong")
                root.check(root.reloadRequests === 2,
                    "failed Uninstall executed a Hyprland reload")
                componentActions.managerExecutable = root.managerSuccessFixture
                root.lifecycleEvents = []
                root.lifecyclePhase = 5
                root.check(componentActions.selectModel("small"),
                    "could not prepare the Apply lifecycle test")
                root.check(componentActions.execute(
                        componentActions.commandForApply(), "apply"),
                    "could not start the Apply lifecycle test")
                return
            }

            if (root.lifecyclePhase === 5) {
                expectEvents(["terminal:apply:0", "refresh"],
                    "Apply lifecycle order is wrong")
                root.check(root.reloadRequests === 2,
                    "Apply executed a Hyprland reload")
                root.lifecycleEvents = []
                root.lifecyclePhase = 6
                root.check(componentActions.execute([
                    root.terminalHelper,
                    "--supervise-foot",
                    root.footFixture,
                    "Vanilla HyprArch Local Dictation",
                    "--",
                    root.managerSuccessFixture,
                    "remove-model"
                ], "remove-model"),
                    "could not start the remove-model lifecycle test")
                return
            }

            if (root.lifecyclePhase === 6) {
                expectEvents(["terminal:remove-model:0", "refresh"],
                    "remove-model lifecycle order is wrong")
                root.check(root.reloadRequests === 2,
                    "remove-model executed a Hyprland reload")
                const refreshBefore = root.refreshRequests
                root.lifecycleEvents = []
                componentActions.refreshAll()
                expectEvents(["refresh"], "explicit Refresh lifecycle is wrong")
                root.check(root.reloadRequests === 2
                        && root.refreshRequests === refreshBefore + 1,
                    "Refresh executed a reload or failed to refresh")
                componentActions.hyprctlExecutable = root.failureFixture
                root.lifecycleEvents = []
                root.lifecyclePhase = 7
                root.check(componentActions.execute(
                        componentActions.commandForInstall(), "install"),
                    "could not start the reload-failure lifecycle test")
                return
            }

            if (root.lifecyclePhase === 7) {
                expectEvents(["terminal:install:0", "reload-start",
                    "reload-exit:1", "refresh"],
                    "reload-failure lifecycle order is wrong")
                root.check(componentActions.errorMessage
                        === "Local Dictation changed, but Hyprland could not reload its bindings.",
                    "reload failure did not expose a concise controller error")
                lifecycleTimer.stop()
                console.log("vanhyprarch system-components self-check passed")
                Qt.quit()
            }
        }
    }
}
