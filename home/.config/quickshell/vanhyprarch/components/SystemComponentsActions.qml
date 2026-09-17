import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool checksEnabled: true
    property bool executionEnabled: true
    property string managerExecutable: "vanhyprarch-dictation"
    property bool statusLoading: false
    property string errorMessage: ""
    property string lifecycleErrorMessage: ""
    property var statusData: ({
        schema_version: 2,
        component: "local-dictation",
        state: "unknown",
        installed: false,
        errors: [],
        model: "small.en",
        model_integrity: "unknown",
        language_mode: "specific",
        languages: ["en"],
        acceleration: "cpu",
        max_duration: 120,
        service_state: "unknown",
        matches_defaults: true,
        vulkan: ({
            state: "unavailable", vendor: null, vendor_id: null, driver: null,
            render_node: null, render_node_accessible: false,
            loader_present: false, icd_manifest_present: false,
            required_packages: ["vulkan-icd-loader"], missing_packages: [],
            runtime_evidence: ({ collected: false, pid: null,
                executable_matches: false, vulkan_loader_mapped: false,
                vendor_icd_mapped: false, render_node_open: false,
                device_runtime_evidence_valid: null,
                device_runtime_evidence_rule: null })
        })
    })
    property var catalogData: null
    property string proposedModel: "small.en"
    property string proposedLanguageMode: "specific"
    property var proposedLanguages: ["en"]
    property string proposedAcceleration: "cpu"
    property int proposedMaxDuration: 120
    property string pendingOperationKind: ""
    property string pendingReloadOperationKind: ""
    readonly property bool operationRunning: operationProcess.running
        || hyprlandReloadProcess.running
    readonly property bool installed: statusData.installed === true
    readonly property bool proposalValid: validateProposal()
    readonly property bool proposalChanged: installed && (
        proposedModel !== statusData.model
        || proposedLanguageMode !== statusData.language_mode
        || proposedLanguages.join(",") !== statusData.languages.join(",")
        || proposedAcceleration !== statusData.acceleration
        || proposedMaxDuration !== statusData.max_duration)
    property string footExecutable: "/usr/bin/foot"
    property string terminalOperation:
        Quickshell.shellDir + "/helpers/vanhyprarch_terminal_operation"
    property string hyprctlExecutable: "/usr/bin/hyprctl"
    signal operationTerminalCompleted(string operationKind, int exitCode)
    signal hyprlandReloadRequested()
    signal hyprlandReloadCompleted(int exitCode)
    signal refreshRequested()

    function hasExactKeys(object: var, expected: var): bool {
        if (object === null || typeof object !== "object" || Array.isArray(object))
            return false
        const actual = Object.keys(object).sort()
        const wanted = expected.slice().sort()
        return actual.length === wanted.length
            && actual.every((key, index) => key === wanted[index])
    }

    function validStatus(document): bool {
        const exact = hasExactKeys(document, [
            "schema_version", "manager_version", "component", "state",
            "installed", "errors", "voxtype_version", "acceleration",
            "binary_sha256", "model", "model_integrity", "language_mode",
            "languages", "max_duration", "service_state",
            "missing_dependencies", "marker", "matches_defaults", "vulkan"
        ])
        const vulkanObject = exact && document.vulkan !== null
            && typeof document.vulkan === "object" && !Array.isArray(document.vulkan)
        const validEvidence = vulkanObject && hasExactKeys(document.vulkan.runtime_evidence, [
            "collected", "pid", "executable_matches", "vulkan_loader_mapped",
            "vendor_icd_mapped", "render_node_open",
            "device_runtime_evidence_valid", "device_runtime_evidence_rule"
        ]) && typeof document.vulkan.runtime_evidence.collected === "boolean"
            && (document.vulkan.runtime_evidence.pid === null
                || Number.isInteger(document.vulkan.runtime_evidence.pid))
            && ["executable_matches", "vulkan_loader_mapped", "vendor_icd_mapped",
                "render_node_open"].every(key =>
                    typeof document.vulkan.runtime_evidence[key] === "boolean")
            && (document.vulkan.runtime_evidence.device_runtime_evidence_valid === null
                || typeof document.vulkan.runtime_evidence.device_runtime_evidence_valid
                    === "boolean")
            && (document.vulkan.runtime_evidence.device_runtime_evidence_rule === null
                || ["drm-render-node", "not-established"].indexOf(
                    document.vulkan.runtime_evidence.device_runtime_evidence_rule) >= 0)
        const validVulkan = vulkanObject && hasExactKeys(document.vulkan, [
            "state", "vendor", "vendor_id", "driver", "render_node",
            "render_node_accessible", "loader_present", "icd_manifest_present",
            "required_packages", "missing_packages", "runtime_evidence"
        ]) && ["ready", "missing-prerequisites", "unavailable", "unsupported",
            "inaccessible", "ambiguous"].indexOf(document.vulkan.state) >= 0
            && (document.vulkan.vendor === null
                || ["amd", "intel", "nvidia"].indexOf(document.vulkan.vendor) >= 0)
            && (document.vulkan.vendor_id === null
                || /^0x[0-9a-f]{4}$/.test(document.vulkan.vendor_id))
            && (document.vulkan.driver === null || typeof document.vulkan.driver === "string")
            && (document.vulkan.render_node === null
                || typeof document.vulkan.render_node === "string")
            && typeof document.vulkan.render_node_accessible === "boolean"
            && typeof document.vulkan.loader_present === "boolean"
            && typeof document.vulkan.icd_manifest_present === "boolean"
            && Array.isArray(document.vulkan.required_packages)
            && Array.isArray(document.vulkan.missing_packages)
            && document.vulkan.required_packages.every(packageName =>
                ["vulkan-icd-loader", "vulkan-radeon", "vulkan-intel", "nvidia-utils"]
                    .indexOf(packageName) >= 0)
            && document.vulkan.missing_packages.every(packageName =>
                document.vulkan.required_packages.indexOf(packageName) >= 0)
            && validEvidence
        return exact
            && document.schema_version === 2
            && document.manager_version === 2
            && document.component === "local-dictation"
            && ["not-installed", "installed", "incomplete", "error"]
                .indexOf(document.state) >= 0
            && typeof document.installed === "boolean"
            && (document.state === "error"
                || document.installed === (document.state === "installed"))
            && Array.isArray(document.errors)
            && document.errors.every(error => typeof error === "string")
            && (document.voxtype_version === null
                || typeof document.voxtype_version === "string")
            && (document.binary_sha256 === null
                || /^[0-9a-f]{64}$/.test(document.binary_sha256))
            && (document.model === null || typeof document.model === "string")
            && (document.model_integrity === null
                || ["missing", "verified", "invalid"].indexOf(document.model_integrity) >= 0)
            && (document.language_mode === null
                || ["specific", "automatic", "selected"].indexOf(document.language_mode) >= 0)
            && (document.languages === null || (Array.isArray(document.languages)
                && document.languages.every(language => typeof language === "string")))
            && (document.acceleration === null
                || ["cpu", "vulkan"].indexOf(document.acceleration) >= 0)
            && (document.max_duration === null
                || [30, 60, 120, 300].indexOf(document.max_duration) >= 0)
            && ((document.state === "installed" || document.state === "not-installed")
                ? document.model !== null && document.model_integrity !== null
                    && document.language_mode !== null && document.languages !== null
                    && document.acceleration !== null && document.max_duration !== null
                : true)
            && typeof document.service_state === "string"
            && ["absent", "valid", "invalid"].indexOf(document.marker) >= 0
            && Array.isArray(document.missing_dependencies)
            && document.missing_dependencies.every(dependency =>
                dependency === "gnupg" || dependency === "wtype")
            && typeof document.matches_defaults === "boolean"
            && validVulkan
    }

    function validCatalog(document): bool {
        const exact = hasExactKeys(document, [
            "schema_version", "manager_version", "component", "defaults",
            "accelerations", "durations", "languages", "models",
            "ui_policy"
        ])
        const validModels = exact && Array.isArray(document.models)
            && document.models.length === 10
            && document.models.every(model => hasExactKeys(model, [
                "id", "label", "family", "filename", "size", "sha256",
                "transport_url", "provenance_url"
            ]) && typeof model.id === "string" && typeof model.label === "string"
                && ["english", "multilingual"].indexOf(model.family) >= 0
                && typeof model.filename === "string"
                && Number.isInteger(model.size) && model.size > 0
                && /^[0-9a-f]{64}$/.test(model.sha256)
                && typeof model.transport_url === "string"
                && typeof model.provenance_url === "string")
        const expectedModels = ["base", "base.en", "large-v3",
            "large-v3-turbo", "medium", "medium.en", "small", "small.en",
            "tiny", "tiny.en"]
        const expectedLanguages = ["ar", "de", "en", "es", "fr", "it",
            "ja", "ko", "nl", "pl", "pt", "ru", "zh"]
        return exact
            && document.schema_version === 2
            && document.manager_version === 2
            && document.component === "local-dictation"
            && hasExactKeys(document.defaults, ["model", "language_mode",
                "languages", "acceleration", "max_duration"])
            && document.defaults.model === "small.en"
            && document.defaults.language_mode === "specific"
            && Array.isArray(document.defaults.languages)
            && document.defaults.languages.join(",") === "en"
            && document.defaults.acceleration === "cpu"
            && document.defaults.max_duration === 120
            && validModels
            && document.models.map(model => model.id).sort().join(",")
                === expectedModels.join(",")
            && Array.isArray(document.languages) && document.languages.length === 13
            && document.languages.every(language => hasExactKeys(language,
                ["id", "label"]) && typeof language.id === "string"
                && typeof language.label === "string")
            && document.languages.map(language => language.id).sort().join(",")
                === expectedLanguages.join(",")
            && Array.isArray(document.durations) && document.durations.length === 4
            && document.durations.every(duration => hasExactKeys(duration,
                ["seconds", "label"]) && [30, 60, 120, 300]
                .indexOf(duration.seconds) >= 0 && typeof duration.label === "string")
            && document.durations.map(duration => duration.seconds).sort(
                (left, right) => left - right).join(",") === "30,60,120,300"
            && Array.isArray(document.accelerations)
            && document.accelerations.length === 2
            && document.accelerations.every(acceleration => hasExactKeys(acceleration,
                ["id", "label", "ui_selectable", "hardware_validation"])
                && ["cpu", "vulkan"].indexOf(acceleration.id) >= 0
                && typeof acceleration.label === "string"
                && typeof acceleration.ui_selectable === "boolean"
                && acceleration.hardware_validation === "complete")
            && document.accelerations[0].id === "cpu"
            && document.accelerations[0].label === "CPU"
            && document.accelerations[0].ui_selectable === true
            && document.accelerations[1].id === "vulkan"
            && document.accelerations[1].label === "Vulkan GPU"
            && document.accelerations[1].ui_selectable === true
            && document.accelerations[1].hardware_validation === "complete"
            && hasExactKeys(document.ui_policy, ["selectable_accelerations", "vulkan"])
            && Array.isArray(document.ui_policy.selectable_accelerations)
            && document.ui_policy.selectable_accelerations.join(",") === "cpu,vulkan"
            && document.ui_policy.vulkan === "supported-explicit-opt-in"
    }

    function acceptStatusJson(text: string): bool {
        try {
            const document = JSON.parse(text)
            if (!validStatus(document))
                throw new Error("unexpected status schema")
            statusData = document
            const statusError = (document.state === "error"
                || document.state === "incomplete")
                ? (document.errors || []).join("; ") : ""
            errorMessage = lifecycleErrorMessage !== ""
                ? lifecycleErrorMessage : statusError
            if (document.model !== null && document.language_mode !== null
                    && document.languages !== null && document.acceleration !== null
                    && document.max_duration !== null) {
                proposedModel = document.model
                proposedLanguageMode = document.language_mode
                proposedLanguages = document.languages.slice()
                proposedAcceleration = document.acceleration
                proposedMaxDuration = document.max_duration
            }
            return true
        } catch (error) {
            statusData = Object.assign({}, statusData, {
                state: "error",
                installed: false,
                errors: ["Could not read component status."],
                marker: "unknown",
                service_state: "unknown",
                missing_dependencies: []
            })
            errorMessage = "Could not read component status."
            return false
        }
    }

    function acceptCatalogJson(text: string): bool {
        try {
            const document = JSON.parse(text)
            if (!validCatalog(document))
                throw new Error("unexpected catalog schema")
            catalogData = document
            return true
        } catch (error) {
            catalogData = null
            errorMessage = "Could not read the dictation catalog."
            return false
        }
    }

    function model(modelId: string): var {
        if (!catalogData)
            return null
        for (const candidate of catalogData.models) {
            if (candidate.id === modelId)
                return candidate
        }
        return null
    }

    function languageLabel(code: string): string {
        if (!catalogData)
            return code
        for (const language of catalogData.languages) {
            if (language.id === code)
                return language.label
        }
        return code
    }

    function modelLabel(modelId: string): string {
        const candidate = model(modelId)
        return candidate ? candidate.label : modelId
    }

    function languageSummary(mode: string, languages: var): string {
        if (mode === "automatic")
            return "Automatic"
        const labels = languages.map(code => languageLabel(code))
        return labels.join(" + ")
    }

    function durationLabel(seconds: int): string {
        if (seconds === 60)
            return "1 minute"
        if (seconds === 120)
            return "2 minutes"
        if (seconds === 300)
            return "5 minutes"
        return seconds + " seconds"
    }

    function accelerationLabel(accelerationId: string): string {
        if (!catalogData)
            return accelerationId === "vulkan" ? "Vulkan GPU" : "CPU"
        for (const acceleration of catalogData.accelerations) {
            if (acceleration.id === accelerationId)
                return acceleration.label
        }
        return accelerationId
    }

    function acceleration(accelerationId: string): var {
        if (!catalogData)
            return null
        for (const candidate of catalogData.accelerations) {
            if (candidate.id === accelerationId)
                return candidate
        }
        return null
    }

    function accelerationReadiness(accelerationId: string): string {
        if (accelerationId === "cpu")
            return "Vanilla default"
        if (statusData.vulkan && statusData.vulkan.state === "ready")
            return "Ready"
        if (statusData.vulkan && statusData.vulkan.state === "missing-prerequisites")
            return "Requirements will be installed when applied"
        return "Supported accessible Vulkan device required"
    }

    function validateProposal(): bool {
        const selectedModel = model(proposedModel)
        const selectedAcceleration = acceleration(proposedAcceleration)
        if (!selectedModel || !selectedAcceleration
                || selectedAcceleration.ui_selectable !== true
                || [30, 60, 120, 300].indexOf(proposedMaxDuration) < 0)
            return false
        if (selectedModel.family === "english")
            return proposedLanguageMode === "specific"
                && proposedLanguages.length === 1
                && proposedLanguages[0] === "en"
        if (proposedLanguageMode === "automatic")
            return proposedLanguages.length === 0
        if (proposedLanguageMode === "specific")
            return proposedLanguages.length === 1
                && languageLabel(proposedLanguages[0]) !== proposedLanguages[0]
        if (proposedLanguageMode !== "selected"
                || proposedLanguages.length < 2 || proposedLanguages.length > 3)
            return false
        const seen = {}
        for (const code of proposedLanguages) {
            if (code === "auto" || languageLabel(code) === code || seen[code])
                return false
            seen[code] = true
        }
        return true
    }

    function selectModel(modelId: string): bool {
        const selectedModel = model(modelId)
        if (!selectedModel)
            return false
        proposedModel = modelId
        if (selectedModel.family === "english") {
            proposedLanguageMode = "specific"
            proposedLanguages = ["en"]
        }
        return true
    }

    function selectAcceleration(accelerationId: string): bool {
        const selectedAcceleration = acceleration(accelerationId)
        if (!selectedAcceleration || selectedAcceleration.ui_selectable !== true)
            return false
        proposedAcceleration = accelerationId
        return true
    }

    function commandForInstall(): var {
        return [terminalOperation, "--supervise-foot", footExecutable,
            "Vanilla HyprArch Local Dictation", "--",
            managerExecutable, "install"]
    }

    function commandForUninstall(): var {
        return [terminalOperation, "--supervise-foot", footExecutable,
            "Vanilla HyprArch Local Dictation", "--",
            managerExecutable, "uninstall"]
    }

    function commandForApply(): var {
        if (!proposalValid || !proposalChanged)
            return []
        const command = [terminalOperation, "--supervise-foot", footExecutable,
            "Vanilla HyprArch Local Dictation", "--",
            managerExecutable, "apply",
            "--model", proposedModel,
            "--language-mode", proposedLanguageMode]
        for (const language of proposedLanguages)
            command.push("--language", language)
        command.push("--acceleration", proposedAcceleration,
            "--max-duration", String(proposedMaxDuration))
        return command
    }

    function commandForHyprlandReload(): var {
        return [hyprctlExecutable, "reload"]
    }

    function execute(command: var, operationKind: string): bool {
        if (!executionEnabled || operationRunning || command.length === 0
                || ["install", "apply", "uninstall", "remove-model"]
                    .indexOf(operationKind) < 0)
            return false
        lifecycleErrorMessage = ""
        errorMessage = ""
        pendingOperationKind = operationKind
        operationProcess.exec(command)
        return true
    }

    function finishOperation(operationKind: string, exitCode: int): void {
        const needsReload = exitCode === 0
            && (operationKind === "install" || operationKind === "uninstall")
        if (needsReload) {
            if (executionEnabled) {
                pendingReloadOperationKind = operationKind
                hyprlandReloadProcess.exec(commandForHyprlandReload())
                return
            }
        }
        refreshAll()
    }

    function refreshStatus(): bool {
        if (!checksEnabled || statusProcess.running)
            return false
        statusLoading = true
        errorMessage = lifecycleErrorMessage
        statusProcess.begin()
        return true
    }

    function refreshCatalog(): bool {
        if (!checksEnabled || catalogProcess.running)
            return false
        catalogProcess.begin()
        return true
    }

    function refreshAll(): void {
        refreshRequested()
        refreshCatalog()
        refreshStatus()
    }

    Process {
        id: statusProcess
        property string outputText: ""
        property string errorText: ""
        property bool exited: false
        property bool stdoutDone: false
        property bool stderrDone: false
        property int exitCode: -1

        function begin(): void {
            outputText = ""; errorText = ""; exited = false
            stdoutDone = false; stderrDone = false; exitCode = -1
            command = [root.managerExecutable, "status", "--json"]
            running = true
        }
        function finish(): void {
            if (!exited || !stdoutDone || !stderrDone)
                return
            root.statusLoading = false
            if (exitCode !== 0 || !root.acceptStatusJson(outputText)) {
                if (root.errorMessage === "")
                    root.errorMessage = "Could not read component status."
            }
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            statusProcess.outputText = text; statusProcess.stdoutDone = true; statusProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            statusProcess.errorText = text; statusProcess.stderrDone = true; statusProcess.finish()
        }}
        onExited: function(code) { exitCode = code; exited = true; finish() }
    }

    Process {
        id: catalogProcess
        property string outputText: ""
        property bool exited: false
        property bool stdoutDone: false
        property bool stderrDone: false
        property int exitCode: -1
        function begin(): void {
            outputText = ""; exited = false; stdoutDone = false; stderrDone = false
            command = [root.managerExecutable, "catalog", "--json"]
            running = true
        }
        function finish(): void {
            if (!exited || !stdoutDone || !stderrDone)
                return
            if (exitCode !== 0 || !root.acceptCatalogJson(outputText))
                root.errorMessage = "Could not read the dictation catalog."
        }
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: {
            catalogProcess.outputText = text; catalogProcess.stdoutDone = true; catalogProcess.finish()
        }}
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: {
            catalogProcess.stderrDone = true; catalogProcess.finish()
        }}
        onExited: function(code) { exitCode = code; exited = true; finish() }
    }

    Process {
        id: operationProcess
        onExited: function(exitCode) {
            const operationKind = root.pendingOperationKind
            root.pendingOperationKind = ""
            root.operationTerminalCompleted(operationKind, exitCode)
            root.finishOperation(operationKind, exitCode)
        }
    }

    Process {
        id: hyprlandReloadProcess
        onStarted: root.hyprlandReloadRequested()
        onExited: function(exitCode) {
            root.pendingReloadOperationKind = ""
            root.hyprlandReloadCompleted(exitCode)
            if (exitCode !== 0) {
                root.lifecycleErrorMessage = "Local Dictation changed, but Hyprland could not reload its bindings."
                root.errorMessage = root.lifecycleErrorMessage
                console.warn(root.errorMessage)
            } else {
                root.lifecycleErrorMessage = ""
            }
            root.refreshAll()
        }
    }

    Component.onCompleted: {
        if (checksEnabled)
            refreshAll()
    }
}
