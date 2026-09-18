import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    property int refreshRequests: 0

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    function catalogDocument() {
        const models = [
            ["tiny", "Tiny — Multilingual", "multilingual"],
            ["tiny.en", "Tiny — English", "english"],
            ["base", "Base — Multilingual", "multilingual"],
            ["base.en", "Base — English", "english"],
            ["small", "Small — Multilingual", "multilingual"],
            ["small.en", "Small — English", "english"],
            ["medium", "Medium — Multilingual", "multilingual"],
            ["medium.en", "Medium — English", "english"],
            ["large-v3", "Large v3 — Multilingual", "multilingual"],
            ["large-v3-turbo", "Large v3 Turbo — Multilingual", "multilingual"]
        ].map(function(item, index) {
            return {
                id: item[0], label: item[1], family: item[2],
                filename: "ggml-" + item[0] + ".bin",
                size: 1000000 + index,
                sha256: "a".repeat(64),
                transport_url: "https://example.invalid/" + item[0],
                provenance_url: "https://example.invalid/revision/" + item[0]
            }
        })
        const labels = {
            en: "English", fr: "French", de: "German", it: "Italian",
            es: "Spanish", pt: "Portuguese", nl: "Dutch", pl: "Polish",
            zh: "Chinese", ja: "Japanese", ko: "Korean", ru: "Russian",
            ar: "Arabic"
        }
        const languages = ["en", "fr", "de", "it", "es", "pt", "nl",
            "pl", "zh", "ja", "ko", "ru", "ar"].map(function(code) {
                return { id: code, label: labels[code] }
            })
        return {
            schema_version: 2,
            manager_version: 2,
            component: "local-dictation",
            defaults: {
                model: "small.en", language_mode: "specific",
                languages: ["en"], acceleration: "cpu", max_duration: 120
            },
            accelerations: [
                { id: "cpu", label: "CPU", ui_selectable: true,
                    hardware_validation: "complete" },
                { id: "vulkan", label: "Vulkan GPU", ui_selectable: true,
                    hardware_validation: "complete" }
            ],
            durations: [
                { seconds: 30, label: "30 seconds" },
                { seconds: 60, label: "1 minute" },
                { seconds: 120, label: "2 minutes" },
                { seconds: 300, label: "5 minutes" }
            ],
            languages: languages,
            models: models,
            ui_policy: {
                selectable_accelerations: ["cpu", "vulkan"],
                vulkan: "supported-explicit-opt-in"
            }
        }
    }

    function statusDocument(model, mode, languages) {
        return {
            schema_version: 2,
            manager_version: 2,
            component: "local-dictation",
            state: "installed",
            installed: true,
            errors: [],
            voxtype_version: "1.0.1",
            acceleration: "cpu",
            binary_sha256: "b".repeat(64),
            model: model,
            model_integrity: "verified",
            language_mode: mode,
            languages: languages,
            max_duration: 120,
            service_state: "active",
            missing_dependencies: [],
            marker: "valid",
            matches_defaults: false,
            vulkan: {
                state: "ready", vendor: "amd", vendor_id: "0x1002",
                driver: "amdgpu", render_node: "/dev/dri/renderD128",
                render_node_accessible: true, loader_present: true,
                icd_manifest_present: true,
                required_packages: ["vulkan-icd-loader", "vulkan-radeon"],
                missing_packages: [],
                runtime_evidence: {
                    collected: false, pid: null, executable_matches: false,
                    vulkan_loader_mapped: false, vendor_icd_mapped: false,
                    render_node_open: false, device_runtime_evidence_valid: null,
                    device_runtime_evidence_rule: null
                }
            }
        }
    }

    function acceptStatus(model, mode, languages) {
        check(componentActions.acceptStatusJson(JSON.stringify(
            statusDocument(model, mode, languages))),
            "valid language status was rejected")
    }

    function enterLocalDictation() {
        superSpace.currentSection = "components"
        superSpace.currentComponentId = "local-dictation"
        superSpace.componentSubview = ""
    }

    function entryByKind(kind) {
        return superSpace.visibleEntries.find(entry => entry.kind === kind)
    }

    function languageEntry(code) {
        return superSpace.visibleEntries.find(entry =>
            entry.kind === "dictationLanguageToggle" && entry.languageId === code)
    }

    function openLanguages() {
        const entry = entryByKind("dictationLanguageView")
        check(entry && entry.label === "Languages", "Languages action is missing")
        superSpace.activate(entry)
        check(superSpace.componentSubview === "languages",
            "Languages did not open its unified page")
    }

    function commandValue(command, option) {
        const index = command.indexOf(option)
        return index >= 0 ? command[index + 1] : ""
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
        id: zigActions
        checksEnabled: false
        executionEnabled: false
    }
    Connections {
        target: componentActions
        function onRefreshRequested() { root.refreshRequests += 1 }
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
    SuperSpacePanelHarness {
        id: panelHarness
        controller: superSpace
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            root.check(componentActions.acceptCatalogJson(JSON.stringify(
                root.catalogDocument())), "authoritative catalog was rejected")

            root.acceptStatus("small", "automatic", [])
            root.enterLocalDictation()
            const mainLabels = superSpace.visibleEntries.map(entry => entry.label)
            root.check(mainLabels.indexOf("Languages") >= 0,
                "main page does not say exactly Languages")
            root.check(mainLabels.indexOf("Language") < 0,
                "old singular Language main label remains")
            root.openLanguages()

            const pageLabels = superSpace.visibleEntries.map(entry => entry.label)
            root.check(pageLabels[0] === "Automatic detection",
                "Automatic detection is not the first selectable mode")
            root.check(pageLabels.indexOf("Specific Language") < 0
                    && pageLabels.indexOf("Selected Languages") < 0
                    && pageLabels.indexOf("Done") < 0,
                "old language hierarchy remains")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind === "dictationLanguageToggle").length === 13,
                "unified page does not expose the authoritative 13-language catalog")
            root.check(superSpace.visibleEntries.filter(entry =>
                    entry.kind === "dictationLanguageToggle")
                    .map(entry => entry.languageId).join(",")
                    === componentActions.catalogData.languages
                        .map(language => language.id).join(","),
                "language page does not preserve authoritative catalog order")
            const hint = superSpace.visibleEntries.find(entry =>
                entry.label === "Manual selection")
            root.check(hint && hint.detail === "Choose up to 3 languages"
                    && hint.informational === true && hint.selectable === false,
                "manual-selection hint is not normal non-selectable information")
            root.check(root.entryByKind("dictationLanguageAutomatic").active,
                "authoritative Automatic did not initialize the page")
            root.check(!superSpace.visibleEntries.some(entry =>
                    entry.kind === "dictationLanguageToggle" && entry.active),
                "Automatic incorrectly selected reviewed manual languages")

            panelHarness.resetSelection()
            root.check(superSpace.visibleEntries[panelHarness.selectedEntryIndex].label
                    === "Automatic detection",
                "navigation did not begin on Automatic detection")
            panelHarness.moveSelection(1)
            root.check(superSpace.visibleEntries[panelHarness.selectedEntryIndex].label
                    === "English",
                "Down did not skip separator and informational hint")
            panelHarness.resetSelection()
            panelHarness.moveSelection(-1)
            root.check(superSpace.visibleEntries[panelHarness.selectedEntryIndex].label
                    === "Arabic",
                "Up navigation did not wrap through selectable language rows")

            superSpace.activate(root.languageEntry("it"))
            root.check(componentActions.proposedLanguageMode === "specific"
                    && componentActions.proposedLanguages.join(",") === "it",
                "one language did not become a specific/scalar draft")
            root.check(componentActions.statusData.language_mode === "automatic"
                    && componentActions.statusData.languages.length === 0,
                "language toggle mutated authoritative status")
            const scalarCommand = componentActions.commandForApply()
            root.check(root.commandValue(scalarCommand, "--language-mode") === "specific"
                    && scalarCommand.filter(value => value === "--language").length === 1
                    && root.commandValue(scalarCommand, "--language") === "it",
                "one-language Apply does not use the scalar/specific form")

            superSpace.goBack()
            root.check(componentActions.proposedLanguages.join(",") === "it",
                "Back discarded the language draft")
            root.openLanguages()
            root.check(root.languageEntry("it").active,
                "re-entering Languages did not show the Back-preserved draft")
            panelHarness.pressEscape()
            root.check(superSpace.componentSubview === ""
                    && componentActions.proposedLanguages.join(",") === "it",
                "Escape did not preserve the language draft")
            root.openLanguages()
            root.check(root.languageEntry("it").active,
                "re-entering Languages did not show the Escape-preserved draft")

            superSpace.activate(root.languageEntry("en"))
            root.check(componentActions.proposedLanguageMode === "selected"
                    && componentActions.proposedLanguages.join(",") === "it,en",
                "two languages did not become a constrained-array draft")
            let arrayCommand = componentActions.commandForApply()
            root.check(root.commandValue(arrayCommand, "--language-mode") === "selected"
                    && arrayCommand.filter(value => value === "--language").length === 2,
                "two-language Apply does not use the constrained-array form")
            superSpace.activate(root.languageEntry("fr"))
            root.check(componentActions.proposedLanguages.join(",") === "it,en,fr",
                "three-language draft is wrong")
            arrayCommand = componentActions.commandForApply()
            root.check(arrayCommand.filter(value => value === "--language").length === 3,
                "three-language Apply does not retain all selected languages")

            const beforeFourth = componentActions.proposedLanguages.join(",")
            superSpace.activate(root.languageEntry("de"))
            root.check(componentActions.proposedLanguages.join(",") === beforeFourth,
                "fourth-language attempt changed or reordered the existing draft")
            root.check(superSpace.languageDraftMessage
                    === "Maximum 3 languages selected"
                    && superSpace.visibleEntries.find(entry =>
                        entry.label === "Manual selection").detail
                        === "Maximum 3 languages selected",
                "fourth-language attempt did not provide minimal inline feedback")

            superSpace.activate(root.languageEntry("fr"))
            superSpace.activate(root.languageEntry("en"))
            root.check(componentActions.proposedLanguageMode === "specific"
                    && componentActions.proposedLanguages.join(",") === "it",
                "deselecting to one language did not restore scalar form")
            superSpace.activate(root.languageEntry("it"))
            root.check(componentActions.proposedLanguages.join(",") === "it"
                    && superSpace.languageDraftMessage.indexOf("Keep 1 language") === 0,
                "minimum-one rule changed the draft or omitted feedback")

            root.acceptStatus("small", "specific", ["it"])
            superSpace.activate(root.entryByKind("dictationLanguageAutomatic"))
            root.check(componentActions.proposedLanguageMode === "automatic"
                    && componentActions.proposedLanguages.length === 0
                    && componentActions.statusData.language_mode === "specific"
                    && componentActions.statusData.languages.join(",") === "it",
                "Automatic detection did not create a true Automatic draft")
            const automaticCommand = componentActions.commandForApply()
            root.check(root.commandValue(automaticCommand, "--language-mode")
                    === "automatic"
                    && automaticCommand.indexOf("--language") < 0,
                "Automatic Apply was emulated with reviewed language selections")

            root.acceptStatus("small", "specific", ["fr"])
            root.check(componentActions.proposedLanguageMode === "specific"
                    && componentActions.proposedLanguages.join(",") === "fr",
                "authoritative one-language form did not initialize")
            root.acceptStatus("small", "selected", ["fr", "de"])
            root.check(componentActions.proposedLanguages.join(",") === "fr,de",
                "authoritative two-language form did not initialize")
            root.acceptStatus("small", "selected", ["fr", "de", "it"])
            root.check(componentActions.proposedLanguages.join(",") === "fr,de,it",
                "authoritative three-language form did not initialize")

            componentActions.toggleProposedLanguage("fr")
            root.check(componentActions.proposedLanguages.join(",") === "de,it",
                "test draft setup failed")
            superSpace.goBack()
            const refreshBefore = root.refreshRequests
            superSpace.activate(root.entryByKind("dictationRefresh"))
            root.check(root.refreshRequests === refreshBefore + 1,
                "Local Dictation Refresh did not request authoritative state")
            root.acceptStatus("small", "selected", ["fr", "de", "it"])
            root.check(componentActions.proposedLanguageMode === "selected"
                    && componentActions.proposedLanguages.join(",") === "fr,de,it",
                "Refresh completion did not discard draft and restore authority")

            root.acceptStatus("small", "automatic", [])
            root.check(componentActions.selectModel("small.en"),
                "English-only model selection failed")
            root.check(componentActions.proposedLanguageMode === "specific"
                    && componentActions.proposedLanguages.join(",") === "en",
                "English-only model did not force specific English")
            root.enterLocalDictation()
            root.openLanguages()
            root.check(!root.entryByKind("dictationLanguageAutomatic").enabled
                    && root.languageEntry("en").active
                    && root.languageEntry("en").enabled
                    && superSpace.visibleEntries.filter(entry =>
                        entry.kind === "dictationLanguageToggle"
                            && entry.languageId !== "en")
                        .every(entry => entry.enabled === false),
                "English-only language page permits an invalid choice")
            root.check(componentActions.selectAutomaticLanguageDetection()
                    === "english-only"
                    && componentActions.toggleProposedLanguage("it") === "english-only"
                    && componentActions.proposedLanguageMode === "specific"
                    && componentActions.proposedLanguages.join(",") === "en",
                "English-only helpers permitted Automatic or non-English")
            root.check(componentActions.toggleProposedLanguage("en") === "changed"
                    && componentActions.proposalValid,
                "valid English-only English selection is unsupported")
            componentActions.proposedLanguageMode = "automatic"
            componentActions.proposedLanguages = []
            root.check(!componentActions.proposalValid
                    && componentActions.commandForApply().length === 0,
                "invalid English-only Automatic draft could be applied")
            componentActions.proposedLanguageMode = "specific"
            componentActions.proposedLanguages = ["it"]
            root.check(!componentActions.proposalValid
                    && componentActions.commandForApply().length === 0,
                "invalid English-only non-English draft could be applied")
            componentActions.selectModel("small.en")
            root.check(componentActions.proposalValid
                    && root.commandValue(componentActions.commandForApply(),
                        "--language-mode") === "specific"
                    && root.commandValue(componentActions.commandForApply(),
                        "--language") === "en",
                "valid English-only specific-English Apply is unavailable")

            root.check(!superSpace.visibleEntries.some(entry => entry.label === "Done"),
                "Languages requires a Done step")
            console.log("vanhyprarch Dictation Languages self-check passed")
            Qt.quit()
        }
    }
}
