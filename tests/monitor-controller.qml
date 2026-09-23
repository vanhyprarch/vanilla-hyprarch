import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    MonitorController {
        id: controller
        checksEnabled: false
        executionEnabled: false
    }

    Component {
        id: controllerComponent
        MonitorController {
            checksEnabled: false
            executionEnabled: false
        }
    }

    function check(condition, message): void {
        if (!condition) {
            console.error("MONITOR_CONTROLLER_TEST_FAILURE: " + message)
            Qt.quit()
            throw new Error(message)
        }
    }

    function inspection(fallbackEditable: bool): string {
        return JSON.stringify({
            version: 3,
            instance_signature: "fixture_123",
            automatic_hdr: {
                value: 0, label: "off", explicit: true, scope: "global",
                available: true, unavailable_reason: null
            },
            outputs: [{
                connector: "DP-1",
                label: "Example Panel",
                identity: { make: "Example", model: "Panel", serial: "ABC" },
                active: true,
                editable: true,
                profile_state: "explicit-editable",
                materializable: false,
                materialization_reason: null,
                unavailable_reason: null,
                current_mode: { width: 3840, height: 2160, refresh_millihz: 60000 },
                available_modes: [
                    { width: 800, height: 600, refresh_millihz: 60000 },
                    { width: 1920, height: 1080, refresh_millihz: 59940 },
                    { width: 1920, height: 1080, refresh_millihz: 60000 },
                    { width: 1366, height: 768, refresh_millihz: 60000 },
                    { width: 2560, height: 1080, refresh_millihz: 60000 },
                    { width: 2560, height: 1440, refresh_millihz: 59950 },
                    { width: 3840, height: 2160, refresh_millihz: 60000 }
                ],
                scale_millionths: 1250000,
                scale_automatic: false,
                effective_bitdepth: 10,
                bitdepth_choices: [8, 10],
                effective: {
                    current_format: "XRGB2101010",
                    color_management_preset: "wide"
                },
                hdr: {
                    capability: "supported", available: true,
                    unavailable_reason: null, mode: "off",
                    base_cm: { present: true, value: "auto" },
                    effective_live: "unknown"
                }
            }, {
                connector: "HDMI-A-1",
                label: "Inactive Panel",
                identity: { make: "Example", model: "Inactive", serial: "OFF" },
                active: false,
                editable: false,
                profile_state: "inactive",
                materializable: false,
                materialization_reason: "Output is inactive or unusable.",
                unavailable_reason: "Output is inactive or unusable.",
                current_mode: null,
                available_modes: [],
                scale_millionths: 1000000,
                scale_automatic: false,
                effective_bitdepth: 8,
                bitdepth_choices: [],
                effective: {
                    current_format: "XRGB8888",
                    color_management_preset: "srgb"
                },
                hdr: {
                    capability: "unknown", available: false,
                    unavailable_reason: "Output is inactive or unusable.", mode: "off",
                    base_cm: { present: false, value: "srgb" },
                    effective_live: "unknown"
                }
            }, {
                connector: "DP-2",
                label: "Fallback Panel",
                identity: { make: "Example", model: "Fallback", serial: "DEF" },
                active: true,
                editable: fallbackEditable || false,
                profile_state: fallbackEditable
                    ? "explicit-editable" : "fallback-only",
                materializable: !(fallbackEditable || false),
                materialization_reason: null,
                unavailable_reason: null,
                current_mode: { width: 1920, height: 1080, refresh_millihz: 60000 },
                available_modes: [
                    { width: 1920, height: 1080, refresh_millihz: 60000 }
                ],
                scale_millionths: 1000000,
                scale_automatic: false,
                effective_bitdepth: 8,
                bitdepth_choices: [8, 10],
                effective: {
                    current_format: "XRGB8888",
                    color_management_preset: "srgb"
                },
                hdr: {
                    capability: "supported", available: true,
                    unavailable_reason: null,
                    mode: "off", base_cm: { present: false, value: "srgb" },
                    effective_live: "unknown"
                }
            }]
        })
    }

    function inspectionWithScale(scaleMillionths: int, scaleAutomatic: bool): string {
        const value = JSON.parse(inspection(false))
        value.outputs[0].scale_millionths = scaleMillionths
        value.outputs[0].scale_automatic = scaleAutomatic
        return JSON.stringify(value)
    }

    function inspectionState(width: int, height: int, scaleMillionths: int,
            scaleAutomatic: bool): string {
        const value = JSON.parse(inspection(false))
        value.outputs[0].current_mode = {
            width: width, height: height, refresh_millihz: 60000
        }
        value.outputs[0].scale_millionths = scaleMillionths
        value.outputs[0].scale_automatic = scaleAutomatic
        return JSON.stringify(value)
    }

    function response(state, sequence, transactionId, candidate, remaining): string {
        const normalizedCandidate = Object.assign({ scale_automatic: false },
            candidate)
        return JSON.stringify({
            version: 5,
            ok: true,
            status: {
                transaction_id: transactionId,
                policy: "safe-confirmed",
                candidate: normalizedCandidate,
                state: state,
                sequence: sequence,
                deadline_monotonic: remaining === null ? null : 500,
                remaining_seconds: remaining,
                failure: null,
                recovery_required: state !== "reverted" && state !== "committed"
            }
        })
    }

    function failedResponse(state: string, sequence: int, transactionId: string,
            candidate: var, failure: string, recoveryRequired: bool): string {
        const normalizedCandidate = Object.assign({ scale_automatic: false },
            candidate)
        return JSON.stringify({
            version: 5,
            ok: true,
            status: {
                transaction_id: transactionId,
                policy: "safe-confirmed",
                candidate: normalizedCandidate,
                state: state,
                sequence: sequence,
                deadline_monotonic: null,
                remaining_seconds: null,
                failure: failure,
                recovery_required: recoveryRequired
            }
        })
    }

    function run(): void {
        check(controller.acceptInspectionJson(inspection(false), false),
            "valid inspection was rejected")
        check(controller.ready && controller.outputFor("DP-1") !== null,
            "inspection did not publish the output")
        check(controller.outputFor("DP-1").hdr.mode === "off"
                && controller.outputFor("DP-1").hdr.available,
            "per-monitor HDR policy did not map to Off")
        check(controller.automaticHdrValue === 0
                && controller.pendingAutomaticHdr === 0
                && controller.automaticHdrExplicit,
            "global Automatic HDR default did not map to Off")
        check(controller.outputFor("HDMI-A-1").current_mode === null
                && controller.ensurePending("HDMI-A-1") === null,
            "inactive output invalidated the normalized inspection model")
        check(controller.outputFor("DP-2").profile_state === "fallback-only"
                && controller.outputFor("DP-2").materializable
                && !controller.outputFor("DP-2").editable
                && controller.pendingFor("DP-2") !== null,
            "fallback-only output did not publish readable live state")
        check(controller.setPendingBitdepth("DP-2", 10)
                && controller.requestSafeApply("DP-2"),
            "fallback-only output rejected an ordinary display change")
        check(controller.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor apply --connector DP-2 --bitdepth 10"
                && controller.lastRequestedKind === "safe-apply",
            "fallback change did not enter the normal Safe Apply path")
        controller.resetPending("DP-2")
        check(controller.requestScale("DP-2", "1.50")
                && controller.lastRequestedCommand.join(" ")
                    === "vanhyprarch-monitor scale --connector DP-2 --scale 1.50",
            "fallback Scale did not enter the normal immediate path")
        check(controller.resolutionOptions("DP-1").length === 6,
            "resolution catalogue was not deduplicated by resolution")
        check(controller.refreshOptions("DP-1", 1920, 1080).length === 2,
            "refreshes were not filtered by resolution")

        check(controller.setPendingResolution("DP-1", 2560, 1080),
            "2560x1080 compatibility fixture was rejected")
        check(controller.scalePresetCompatible("DP-1", "1.00")
                && controller.scalePresetCompatible("DP-1", "1.25")
                && !controller.scalePresetCompatible("DP-1", "1.50")
                && controller.scalePresetCompatible("DP-1", "2.00"),
            "2560x1080 exposed the wrong Scale presets")
        const commandBeforeIncompatibleScale = controller.lastRequestedCommand.join(" ")
        check(!controller.requestScale("DP-1", "1.50")
                && controller.lastRequestedCommand.join(" ")
                    === commandBeforeIncompatibleScale,
            "2560x1080 Scale 1.5 reached the backend action path")

        check(controller.setPendingResolution("DP-1", 3840, 2160),
            "3840x2160 compatibility fixture was rejected")
        check(["1.00", "1.25", "1.50", "2.00"].every(scale =>
                controller.scalePresetCompatible("DP-1", scale)),
            "3840x2160 did not enable every Vanilla Scale preset")

        check(controller.setPendingResolution("DP-1", 1366, 768),
            "1366x768 compatibility fixture was rejected")
        check(controller.scalePresetCompatible("DP-1", "1.00")
                && !controller.scalePresetCompatible("DP-1", "1.25")
                && !controller.scalePresetCompatible("DP-1", "1.50")
                && controller.scalePresetCompatible("DP-1", "2.00"),
            "1366x768 exposed the wrong Scale presets")
        controller.resetPending("DP-1")

        const explicitOnePointFive = controllerComponent.createObject(root)
        check(explicitOnePointFive !== null
                && explicitOnePointFive.acceptInspectionJson(
                    inspectionWithScale(1500000, false), false)
                && explicitOnePointFive.setPendingResolution("DP-1", 2560, 1080),
            "explicit 1.5 Resolution draft was rejected")
        check(explicitOnePointFive.pendingFor("DP-1").scale_automatic
                && explicitOnePointFive.resolutionChangePending("DP-1")
                && !explicitOnePointFive.requestScale("DP-1", "1.25"),
            "Resolution draft did not switch to auto and lock Scale")
        check(explicitOnePointFive.requestSafeApply("DP-1"),
            "explicit 1.5 Resolution change was rejected")
        check(explicitOnePointFive.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor apply --connector DP-1 --width 2560 --height 1080 --refresh 60 --scale auto"
                && explicitOnePointFive.lastRequestedKind === "safe-apply"
                && explicitOnePointFive.lastRequestedCommand.filter(
                    part => part === "--scale").length === 1,
            "Resolution and auto Scale were not one Safe Apply request")

        const autoCandidate = {
            connector: "DP-1",
            mode: { width: 2560, height: 1080, refresh_millihz: 60000 },
            bitdepth: null,
            scale_millionths: null,
            scale_automatic: true,
            hdr_mode: null,
            automatic_hdr: null
        }
        check(explicitOnePointFive.acceptStatusJson(response("temporary-active", 2,
                "transaction-auto", autoCandidate, 8.2), false)
                && explicitOnePointFive.confirmationActive
                && explicitOnePointFive.pendingFor("DP-1").scale_automatic
                && !explicitOnePointFive.requestScale("DP-1", "1.25"),
            "Scale unlocked during automatic Resolution confirmation")
        check(explicitOnePointFive.acceptStatusJson(response("committed", 4,
                "transaction-auto", autoCandidate, null), false)
                && explicitOnePointFive.acceptInspectionJson(
                    inspectionState(2560, 1080, 1600000, true), false),
            "confirmed automatic Resolution state was rejected")
        check(!explicitOnePointFive.resolutionChangePending("DP-1")
                && explicitOnePointFive.pendingFor("DP-1").scale_automatic
                && explicitOnePointFive.pendingFor("DP-1").scale_millionths
                    === 1600000,
            "confirmed auto Scale did not unlock with effective readback")
        check(explicitOnePointFive.requestScale("DP-1", "1.25")
                && explicitOnePointFive.lastRequestedCommand.join(" ")
                    === "vanhyprarch-monitor scale --connector DP-1 --scale 1.25"
                && explicitOnePointFive.acceptInspectionJson(
                    inspectionState(2560, 1080, 1250000, false), false)
                && !explicitOnePointFive.pendingFor("DP-1").scale_automatic
                && explicitOnePointFive.pendingFor("DP-1").scale_millionths
                    === 1250000,
            "compatible explicit Scale did not replace confirmed auto ownership")
        explicitOnePointFive.destroy()

        const cancelledResolution = controllerComponent.createObject(root)
        check(cancelledResolution !== null
                && cancelledResolution.acceptInspectionJson(
                    inspectionWithScale(1500000, false), false)
                && cancelledResolution.setPendingResolution("DP-1", 2560, 1080)
                && cancelledResolution.pendingFor("DP-1").scale_automatic
                && cancelledResolution.setPendingResolution("DP-1", 3840, 2160)
                && !cancelledResolution.resolutionChangePending("DP-1")
                && !cancelledResolution.pendingFor("DP-1").scale_automatic
                && cancelledResolution.pendingFor("DP-1").scale_millionths
                    === 1500000,
            "cancelled Resolution draft did not restore explicit Scale")
        cancelledResolution.destroy()

        const discardedScale = controllerComponent.createObject(root)
        check(discardedScale !== null
                && discardedScale.acceptInspectionJson(
                    inspectionWithScale(1500000, false), false),
            "pending Scale precedence fixture was rejected")
        const scaleDraft = discardedScale.pendingFor("DP-1")
        scaleDraft.scale_millionths = 1250000
        scaleDraft.scale_automatic = false
        check(discardedScale.setPendingResolution("DP-1", 2560, 1080)
                && discardedScale.pendingFor("DP-1").scale_automatic
                && discardedScale.pendingFor("DP-1").scale_millionths
                    === 1500000
                && discardedScale.resolutionChangePending("DP-1"),
            "Resolution did not discard a pending manual Scale draft")
        discardedScale.destroy()

        check(controller.setPendingResolution("DP-1", 1920, 1080),
            "pending resolution was rejected")
        check(controller.ensurePending("DP-1").refresh_millihz === 60000,
            "current refresh was not preserved when available")
        check(controller.setPendingBitdepth("DP-1", 8),
            "pending bitdepth was rejected")
        check(controller.requestSafeApply("DP-1"),
            "combined Safe Apply request was rejected")
        check(controller.lastRequestedKind === "safe-apply",
            "combined request used the wrong policy")
        check(controller.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor apply --connector DP-1 --width 1920 --height 1080 --refresh 60 --scale auto --bitdepth 8",
            "combined request did not contain exactly changed Mode and bitdepth")
        check(controller.lastRequestedCommand.indexOf("--scale") >= 0,
            "automatic Scale transition was absent from the Resolution transaction")
        check(controller.outputFor("DP-1").current_mode.width === 3840
                && controller.outputFor("DP-1").effective_bitdepth === 10,
            "pending request optimistically replaced authoritative current state")

        controller.resetPending("DP-1")
        check(controller.setPendingBitdepth("DP-1", 8)
                && controller.setPendingHdr("DP-1", "always-on"),
            "illegal HDR fixture could not be constructed")
        check(controller.validationMessage("DP-1")
                === "Forced HDR On requires selecting 10-bit Color Depth in the same Apply."
                && !controller.requestSafeApply("DP-1"),
            "8-bit plus forced HDR was not blocked with a clear validation")

        controller.resetPending("DP-1")
        check(controller.setPendingHdr("DP-1", "always-on")
                && controller.setPendingAutomaticHdr(2)
                && controller.requestSafeApply("DP-1"),
            "combined HDR/global request was rejected")
        check(controller.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor apply --connector DP-1 --hdr always-on --automatic-hdr 2",
            "combined HDR/global request did not remain one exact Safe Apply")
        check(controller.outputFor("DP-1").hdr.mode === "off"
                && controller.automaticHdrValue === 0,
            "pending HDR request optimistically changed authoritative state")

        controller.resetPending("DP-1")
        controller.pendingAutomaticHdr = controller.automaticHdrValue
        check(controller.requestScale("DP-1", "1.50"),
            "immediate Scale request was rejected")
        check(controller.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor scale --connector DP-1 --scale 1.50",
            "Scale did not use the immediate backend path")
        check(!controller.confirmationActive,
            "Scale opened Safe Apply confirmation")

        const candidate = {
            connector: "DP-1",
            mode: { width: 1920, height: 1080, refresh_millihz: 60000 },
            bitdepth: null,
            scale_millionths: null, hdr_mode: null, automatic_hdr: null
        }
        check(controller.acceptStatusJson(response("temporary-active", 2,
            "transaction-new", candidate, 8.4), true),
            "temporary status was rejected")
        check(controller.confirmationActive
                && controller.transactionConnector === "DP-1",
            "Mode did not reconstruct confirmation")
        controller.registerSurface("target-screen", "DP-1")
        controller.registerSurface("fallback-screen", "HDMI-A-1")
        check(controller.confirmationScreenName === "target-screen",
            "confirmation did not prefer its target connector screen")
        controller.unregisterSurface("target-screen")
        check(controller.confirmationScreenName === "fallback-screen",
            "confirmation did not fall back when the target screen disappeared")
        check(controller.requestConfirm(), "Keep request was rejected")
        check(controller.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor confirm transaction-new",
            "Keep used the wrong transaction ID")
        check(controller.requestRevert(), "Revert request was rejected")
        check(controller.lastRequestedCommand.join(" ")
                === "vanhyprarch-monitor revert transaction-new",
            "Revert used the wrong transaction ID")

        check(controller.acceptStatusJson(response("applying", 1,
            "stale-transaction", candidate, null), false),
            "stale response parser failed")
        check(controller.transactionId === "transaction-new"
                && controller.transactionState === "temporary-active",
            "stale transaction response replaced the active authority")

        const reloaded = controllerComponent.createObject(root)
        check(reloaded !== null, "reload controller could not be created")
        check(reloaded.acceptInspectionJson(inspection(false), false),
            "reload controller rejected inspection")
        check(reloaded.acceptStatusJson(response("temporary-active", 2,
            "transaction-new", candidate, 5.1), false),
            "reload controller rejected active status")
        check(reloaded.confirmationActive
                && reloaded.presentationRemainingSeconds > 5,
            "reload did not reconstruct the backend countdown")
        reloaded.destroy()

        const bitdepthController = controllerComponent.createObject(root)
        check(bitdepthController !== null
                && bitdepthController.acceptInspectionJson(inspection(false), false),
            "bitdepth controller setup failed")
        check(bitdepthController.acceptStatusJson(response("temporary-active", 2,
            "transaction-depth", {
                connector: "DP-1", mode: null, bitdepth: 8,
                scale_millionths: null, hdr_mode: null, automatic_hdr: null
            }, 7.2), false) && bitdepthController.confirmationActive,
            "bitdepth-only transaction did not open confirmation")
        check(bitdepthController.confirmationDescription() === "Color Depth: 8-bit",
            "bitdepth confirmation description is not normalized")
        bitdepthController.destroy()

        const combinedController = controllerComponent.createObject(root)
        check(combinedController !== null
                && combinedController.acceptInspectionJson(inspection(false), false),
            "combined controller setup failed")
        check(combinedController.acceptStatusJson(response("temporary-active", 2,
            "transaction-combined", {
                connector: "DP-1",
                mode: { width: 1920, height: 1080, refresh_millihz: 60000 },
                bitdepth: 8,
                scale_millionths: null, hdr_mode: null, automatic_hdr: null
            }, 6.8), false) && combinedController.confirmationActive,
            "combined transaction did not open one confirmation")
        check(combinedController.confirmationDescription()
                === "1920×1080 · 60 Hz · Color Depth: 8-bit",
            "combined confirmation description is not normalized")
        combinedController.destroy()

        const hdrController = controllerComponent.createObject(root)
        check(hdrController !== null
                && hdrController.acceptInspectionJson(inspection(false), false),
            "HDR controller setup failed")
        check(hdrController.acceptStatusJson(response("temporary-active", 2,
            "transaction-hdr", {
                connector: "DP-1", mode: null, bitdepth: 10,
                scale_millionths: null, hdr_mode: "always-on", automatic_hdr: 0
            }, 6.4), false) && hdrController.confirmationActive,
            "combined HDR transaction did not open one confirmation")
        check(hdrController.confirmationDescription()
                === "Color Depth: 10-bit · Forced HDR: On · Automatic HDR (all displays): Off",
            "HDR confirmation description exposed backend names or lost fields")
        hdrController.destroy()

        controller.statusTransportError = true
        controller.errorMessage = "vanhyprarch-monitor: [Errno 104] Connection reset by peer"
        check(controller.acceptStatusJson(response("reverted", 4,
            "transaction-new", candidate, null), false),
            "reverted status was rejected")
        check(!controller.confirmationActive,
            "terminal rollback left confirmation visible")
        check(!controller.statusTransportError && controller.errorMessage === "",
            "safe terminal reconciliation retained a stale transport error")
        check(controller.resetPendingOnNextInspect,
            "terminal Safe Apply did not defer reset to authoritative inspection")
        check(controller.acceptInspectionJson(inspection(false), false)
                && !controller.resetPendingOnNextInspect
                && controller.ensurePending("DP-1").width === 3840,
            "terminal reconciliation retained stale pending state")

        const raceController = controllerComponent.createObject(root)
        check(raceController !== null
                && raceController.acceptInspectionJson(inspection(false), false),
            "status-race controller setup failed")
        raceController.statusTransportError = true
        raceController.errorMessage = "fixture status transport reset"
        check(raceController.acceptStatusJson(response("temporary-active", 2,
            "transaction-race", candidate, 5), false)
                && raceController.errorMessage === "fixture status transport reset"
                && raceController.statusTransportError,
            "nonterminal status incorrectly suppressed a transport error")
        check(raceController.acceptStatusJson(failedResponse("reverted", 3,
            "transaction-race", candidate, "fixture backend failure", false), false)
                && raceController.errorMessage
                    === "Display settings were reverted: fixture backend failure"
                && !raceController.statusTransportError,
            "actual backend failure was hidden by terminal reconciliation")
        raceController.destroy()

        const committedRaceController = controllerComponent.createObject(root)
        check(committedRaceController !== null
                && committedRaceController.acceptInspectionJson(
                    inspection(false), false),
            "committed-race controller setup failed")
        committedRaceController.statusTransportError = true
        committedRaceController.errorMessage = "fixture committed transport reset"
        check(committedRaceController.acceptStatusJson(response("committed", 4,
            "transaction-committed", candidate, null), false)
                && committedRaceController.errorMessage === ""
                && !committedRaceController.statusTransportError,
            "committed reconciliation retained a stale transport error")
        committedRaceController.destroy()

        controller.transactionState = "applying"
        check(!controller.requestScale("DP-1", "1.50"),
            "Scale started during a Safe Apply operation")
        controller.transactionState = "reverted"
        check(!controller.acceptInspectionJson("{}", false) && !controller.ready,
            "backend inspection failure did not fail closed")
        check(!controller.acceptStatusJson("{}", false) && !controller.statusReady,
            "backend status failure did not fail closed")

        console.log("MONITOR_CONTROLLER_TEST_PASS")
        Qt.quit()
    }

    Component.onCompleted: Qt.callLater(run)
}
