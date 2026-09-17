import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    required property InstallActions installActions
    required property RemoveActions removeActions
    required property UpdateActions updateActions
    required property SystemComponentsActions systemComponentsActions
    required property PowerActions powerActions

    property bool isOpen: false
    property string activeScreenName: ""
    property string currentSection: "root"
    property string currentComponentId: ""
    property string componentSubview: ""
    property var selectedLanguageDraft: []
    property string searchText: ""
    property string pendingPowerAction: ""
    readonly property var sections: [
        {
            kind: "section",
            sectionId: "apps",
            label: "Apps",
            detail: "Launch an installed application",
            icon: "view-app-grid-symbolic"
        },
        {
            kind: "section",
            sectionId: "install",
            label: "Install",
            detail: "Find and install software with yay",
            icon: "system-software-install",
            keywords: ["install", "package", "packages", "software", "yay"]
        },
        {
            kind: "section",
            sectionId: "remove",
            label: "Remove",
            detail: "Cleanly uninstall an installed package",
            icon: "edit-delete",
            keywords: ["remove", "uninstall", "package", "packages", "yay"]
        },
        {
            kind: "section",
            sectionId: "update",
            label: "Update",
            detail: "Update system and Flatpak packages",
            icon: "system-software-update",
            keywords: ["update", "upgrade", "system", "flatpak", "yay"]
        },
        {
            kind: "section",
            sectionId: "components",
            label: "Additional system components",
            detail: "Install and configure optional Vanilla HyprArch components",
            icon: "applications-system",
            keywords: ["additional", "system", "components", "optional", "dictation"]
        },
        {
            kind: "section",
            sectionId: "power",
            label: "Power",
            detail: "Lock, suspend, or end the session",
            icon: "system-shutdown"
        }
    ]
    readonly property var visibleEntries: buildVisibleEntries()

    function open(): void {
        if (isOpen)
            return

        const focusedMonitor = Hyprland.focusedMonitor
        if (focusedMonitor && focusedMonitor.name !== "")
            activeScreenName = focusedMonitor.name
        else if (Quickshell.screens.length > 0)
            activeScreenName = Quickshell.screens[0].name
        else
            activeScreenName = ""

        currentSection = "root"
        currentComponentId = ""
        componentSubview = ""
        searchText = ""
        pendingPowerAction = ""
        systemComponentsActions.refreshAll()
        isOpen = true
    }

    function close(): void {
        isOpen = false
        currentSection = "root"
        currentComponentId = ""
        componentSubview = ""
        searchText = ""
        pendingPowerAction = ""
    }

    function toggle(): void {
        if (isOpen)
            close()
        else
            open()
    }

    function goBack(): void {
        if (pendingPowerAction !== "") {
            pendingPowerAction = ""
        } else if (componentSubview !== "") {
            componentSubview = ""
            selectedLanguageDraft = []
        } else if (currentComponentId !== "") {
            currentComponentId = ""
            searchText = ""
        } else if (currentSection !== "root") {
            currentSection = "root"
            searchText = ""
        } else {
            close()
        }
    }

    function enterSection(sectionId: string): void {
        if (sectionId !== "apps" && sectionId !== "install"
                && sectionId !== "remove" && sectionId !== "update"
                && sectionId !== "components" && sectionId !== "power")
            return
        currentSection = sectionId
        searchText = ""
        if (sectionId === "remove")
            removeActions.refreshPackages()
        else if (sectionId === "components")
            systemComponentsActions.refreshAll()
    }

    function openComponent(componentId: string): void {
        if (currentSection !== "components" || componentId !== "local-dictation")
            return
        currentComponentId = componentId
        componentSubview = ""
        searchText = ""
        systemComponentsActions.refreshAll()
    }

    function normalize(value): string {
        return value === null || value === undefined
            ? "" : String(value).toLowerCase().replace(/\s+/g, " ").trim()
    }

    function matchRank(label: string, searchable: string, query: string): int {
        const normalizedLabel = normalize(label)
        if (normalizedLabel === query)
            return 0
        if (normalizedLabel.startsWith(query))
            return 1
        if (normalizedLabel.indexOf(query) >= 0)
            return 2
        return searchable.indexOf(query) >= 0 ? 3 : -1
    }

    function applicationEntries(query: string): var {
        const result = []
        const applications = DesktopEntries.applications.values

        for (let index = 0; index < applications.length; ++index) {
            const desktopEntry = applications[index]
            if (!desktopEntry)
                continue

            const searchable = normalize([
                desktopEntry.name,
                desktopEntry.genericName,
                desktopEntry.comment,
                desktopEntry.id,
                (desktopEntry.keywords || []).join(" ")
            ].join(" "))
            const rank = query === "" ? 0
                : matchRank(desktopEntry.name, searchable, query)
            if (rank < 0)
                continue

            result.push({
                kind: "application",
                label: desktopEntry.name,
                detail: desktopEntry.genericName || desktopEntry.comment
                    || "Application",
                icon: desktopEntry.icon || "application-x-executable",
                desktopEntry: desktopEntry,
                rank: rank,
                sourceIndex: index
            })
        }

        result.sort(function(left, right) {
            if (left.rank !== right.rank)
                return left.rank - right.rank
            const labelOrder = left.label.localeCompare(right.label)
            return labelOrder !== 0 ? labelOrder
                : left.sourceIndex - right.sourceIndex
        })
        return result
    }

    function powerEntries(query: string): var {
        const result = []
        const actions = powerActions.actions

        for (let index = 0; index < actions.length; ++index) {
            const action = actions[index]
            const searchable = normalize(action.label + " "
                + action.keywords.join(" "))
            const rank = query === "" ? 0
                : matchRank(action.label, searchable, query)
            if (rank < 0)
                continue

            result.push({
                kind: "power",
                actionId: action.id,
                label: action.label,
                detail: action.requiresConfirmation
                    ? "Confirmation required" : "Runs immediately",
                icon: action.icon,
                rank: rank,
                sourceIndex: index
            })
        }

        return result
    }

    function matchingSections(query: string): var {
        const result = []

        for (let index = 0; index < sections.length; ++index) {
            const section = sections[index]
            if (!section.keywords)
                continue

            const searchable = normalize(section.label + " "
                + section.keywords.join(" "))
            const rank = matchRank(section.label, searchable, query)
            if (rank < 0)
                continue

            result.push(Object.assign({}, section, {
                rank: rank,
                sourceIndex: index
            }))
        }

        return result
    }

    function installEntries(query: string): var {
        if (query === "")
            return []

        return [
            {
                kind: "installSearch",
                label: "Install with yay",
                detail: "Search repositories and AUR for “"
                    + searchText.trim() + "”",
                icon: "system-software-install",
                searchText: searchText
            }
        ]
    }

    function removeEntries(query: string): var {
        const result = []
        if (removeActions.loading || removeActions.errorMessage !== "")
            return result
        const packages = removeActions.packages

        for (let index = 0; index < packages.length; ++index) {
            const packageObject = packages[index]
            const searchable = normalize(packageObject.name + " "
                + packageObject.version)
            const rank = query === "" ? 0
                : matchRank(packageObject.name, searchable, query)
            if (rank < 0)
                continue

            result.push({
                kind: "removePackage",
                label: packageObject.name,
                detail: "Installed " + packageObject.version,
                icon: "package-x-generic",
                packageObject: packageObject,
                danger: true,
                rank: rank,
                sourceIndex: index
            })
        }

        result.sort(function(left, right) {
            if (left.rank !== right.rank)
                return left.rank - right.rank
            const labelOrder = left.label.localeCompare(right.label)
            return labelOrder !== 0 ? labelOrder
                : left.sourceIndex - right.sourceIndex
        })
        return result
    }

    function updateEntries(query: string): var {
        const result = []
        const actions = updateActions.actions

        for (let index = 0; index < actions.length; ++index) {
            const action = actions[index]
            const searchable = normalize(action.label + " "
                + action.keywords.join(" "))
            const rank = query === "" ? 0
                : matchRank(action.label, searchable, query)
            if (rank < 0)
                continue

            let detail = action.detail
            let danger = false
            if (action.id === "flatpak") {
                if (updateActions.errorMessage !== "") {
                    detail = updateActions.errorMessage
                    danger = true
                } else if (!updateActions.flatpakCheckComplete) {
                    detail = "Checking required Flatpak executable…"
                } else if (!updateActions.flatpakAvailable) {
                    detail = "Required /usr/bin/flatpak is unavailable."
                    danger = true
                }
            }

            result.push({
                kind: "update",
                actionId: action.id,
                label: action.label,
                detail: detail,
                icon: action.icon,
                danger: danger,
                rank: rank,
                sourceIndex: index
            })
        }

        return result
    }

    function componentCatalogEntries(query: string): var {
        const status = systemComponentsActions.statusData
        const label = "Local Dictation"
        const searchable = normalize(label + " voice speech F9 voxtype local offline")
        if (query !== "" && matchRank(label, searchable, query) < 0)
            return []
        let detail = "Local/offline push-to-talk dictation using F9"
        if (systemComponentsActions.statusLoading)
            detail = "Checking component status…"
        else if (status.state === "installed")
            detail = "Installed · " + systemComponentsActions.modelLabel(status.model)
        else if (status.state === "error" || status.state === "incomplete")
            detail = "Needs attention · " + systemComponentsActions.errorMessage
        return [{
            kind: "component",
            componentId: "local-dictation",
            label: label,
            detail: detail,
            icon: "audio-input-microphone"
        }]
    }

    function infoEntry(label: string, detail: string, danger: bool): var {
        return {
            kind: "componentInfo",
            label: label,
            detail: detail,
            icon: danger ? "dialog-error" : "dialog-information",
            enabled: false,
            danger: danger
        }
    }

    function actionEntry(kind: string, label: string, detail: string,
            icon: string, enabled: bool, danger: bool): var {
        return {
            kind: kind,
            label: label,
            detail: detail,
            icon: icon,
            enabled: enabled,
            danger: danger
        }
    }

    function dictationDetailEntries(): var {
        const actions = systemComponentsActions
        const status = actions.statusData
        if (actions.statusLoading)
            return [infoEntry("Status", "Checking component status…", false)]
        if (!status.installed && status.state === "not-installed") {
            return [
                infoEntry("Local Dictation",
                    "Local/offline push-to-talk dictation using F9.", false),
                infoEntry("Vanilla default",
                    "Small — English · English · CPU · 2 minutes", false),
                actionEntry("dictationInstall", "Install",
                    "Install optional official dependencies and verified Voxtype",
                    "system-software-install", !actions.operationRunning, false)
            ]
        }
        if (status.state === "error" || status.state === "incomplete") {
            return [
                infoEntry("Status", status.state === "error" ? "Error" : "Incomplete", true),
                infoEntry("Details", actions.errorMessage || (status.errors || []).join("; "), true),
                actionEntry("dictationRefresh", "Refresh", "Read component state again",
                    "view-refresh", !actions.operationRunning, false),
                actionEntry("dictationUninstallView", "Uninstall",
                    "Remove Voxtype, its configuration, and all speech models",
                    "edit-delete", !actions.operationRunning, true)
            ]
        }
        const model = actions.model(actions.proposedModel)
        const languageLocked = model && model.family === "english"
        return [
            infoEntry("Current settings",
                status.matches_defaults ? "Matches the Vanilla default" : "Customized for this user", false),
            infoEntry("Status", "Installed · service " + status.service_state, false),
            actionEntry("dictationAccelerationView", "Acceleration",
                actions.accelerationLabel(actions.proposedAcceleration), "video-display",
                !actions.operationRunning && actions.catalogData !== null, false),
            actionEntry("dictationModelView", "Model",
                actions.modelLabel(actions.proposedModel), "audio-input-microphone",
                !actions.operationRunning && actions.catalogData !== null, false),
            actionEntry("dictationLanguageView", "Language",
                actions.languageSummary(actions.proposedLanguageMode, actions.proposedLanguages)
                    + (languageLocked ? " · locked by English-only model" : ""),
                "preferences-desktop-locale", !actions.operationRunning && !languageLocked, false),
            actionEntry("dictationDurationView", "Maximum recording",
                actions.durationLabel(actions.proposedMaxDuration), "appointment-soon",
                !actions.operationRunning, false),
            actionEntry("dictationApply", "Apply Changes",
                actions.proposalChanged ? "Validate, publish, and restart the daemon" : "No pending changes",
                "document-save", actions.proposalValid && actions.proposalChanged
                    && !actions.operationRunning, false),
            actionEntry("dictationRefresh", "Refresh", "Discard pending choices and reread live state",
                "view-refresh", !actions.operationRunning, false),
            actionEntry("dictationUninstallView", "Uninstall",
                "Remove Voxtype, its configuration, and all downloaded speech models",
                "edit-delete", !actions.operationRunning, true)
        ]
    }

    function modelSelectorEntries(): var {
        const result = []
        const catalog = systemComponentsActions.catalogData
        if (!catalog)
            return [infoEntry("Models unavailable", "Could not read the reviewed model catalog.", true)]
        for (const model of catalog.models) {
            const sizeMiB = Math.round(model.size / 1048576)
            result.push({
                kind: "dictationModelSelect",
                modelId: model.id,
                label: model.label,
                detail: (model.family === "english" ? "English-only" : "Multilingual")
                    + " · approximately " + sizeMiB + " MiB",
                icon: "audio-input-microphone",
                active: systemComponentsActions.proposedModel === model.id,
                enabled: true
            })
        }
        return result
    }

    function languageModeEntries(): var {
        return [
            actionEntry("dictationLanguageSpecificView", "Specific Language",
                "Use one language for every transcription", "preferences-desktop-locale", true, false),
            actionEntry("dictationLanguageAutomatic", "Automatic",
                "Detect from all Whisper languages", "system-search", true, false),
            actionEntry("dictationLanguageSelectedView", "Selected Languages",
                "Constrain detection to two or three languages", "view-list-symbolic", true, false)
        ]
    }

    function specificLanguageEntries(): var {
        const result = []
        const catalog = systemComponentsActions.catalogData
        if (!catalog)
            return [infoEntry("Languages unavailable", "Could not read the language catalog.", true)]
        for (const language of catalog.languages) {
            result.push({
                kind: "dictationLanguageSpecificSelect",
                languageId: language.id,
                label: language.label,
                detail: language.id,
                icon: "preferences-desktop-locale",
                active: systemComponentsActions.proposedLanguageMode === "specific"
                    && systemComponentsActions.proposedLanguages[0] === language.id,
                enabled: true
            })
        }
        return result
    }

    function selectedLanguageEntries(): var {
        const result = []
        const catalog = systemComponentsActions.catalogData
        if (!catalog)
            return [infoEntry("Languages unavailable", "Could not read the language catalog.", true)]
        for (const language of catalog.languages) {
            const selected = selectedLanguageDraft.indexOf(language.id) >= 0
            result.push({
                kind: "dictationLanguageToggle",
                languageId: language.id,
                label: language.label,
                detail: selected ? "Selected" : "Not selected",
                icon: selected ? "checkbox-checked" : "checkbox",
                active: selected,
                enabled: selected || selectedLanguageDraft.length < 3
            })
        }
        result.push(actionEntry("dictationLanguageSelectedDone", "Done",
            selectedLanguageDraft.length + " selected · two or three required",
            "dialog-ok", selectedLanguageDraft.length >= 2
                && selectedLanguageDraft.length <= 3, false))
        return result
    }

    function durationSelectorEntries(): var {
        const result = []
        const catalog = systemComponentsActions.catalogData
        if (!catalog)
            return [infoEntry("Durations unavailable", "Could not read duration choices.", true)]
        for (const duration of catalog.durations) {
            result.push({
                kind: "dictationDurationSelect",
                duration: duration.seconds,
                label: duration.label,
                detail: duration.seconds === 120 ? "Vanilla default" : "Maximum recording length",
                icon: "appointment-soon",
                active: systemComponentsActions.proposedMaxDuration === duration.seconds,
                enabled: true
            })
        }
        return result
    }

    function accelerationSelectorEntries(): var {
        const result = []
        const actions = systemComponentsActions
        const catalog = actions.catalogData
        if (!catalog)
            return [infoEntry("Acceleration choices unavailable",
                "Could not read the reviewed acceleration catalog.", true)]
        for (const acceleration of catalog.accelerations) {
            if (!acceleration.ui_selectable)
                continue
            result.push({
                kind: "dictationAccelerationSelect",
                accelerationId: acceleration.id,
                label: acceleration.label,
                detail: actions.accelerationReadiness(acceleration.id),
                icon: acceleration.id === "vulkan" ? "video-display" : "computer",
                active: actions.proposedAcceleration === acceleration.id,
                enabled: true
            })
        }
        return result
    }

    function uninstallConfirmationEntries(): var {
        return [
            infoEntry("Uninstall Local Dictation?",
                "This will remove Voxtype, its configuration, and all downloaded speech models.", true),
            infoEntry("Vanilla component manager",
                "Will remain available so Local Dictation can be installed again later.", false),
            actionEntry("dictationUninstallCancel", "Cancel",
                "Return without removing Local Dictation", "dialog-cancel", true, false),
            actionEntry("dictationUninstallConfirm", "Confirm uninstall",
                "Remove Local Dictation and all of its data",
                "edit-delete", true, true)
        ]
    }

    function dictationEntries(): var {
        if (componentSubview === "model")
            return modelSelectorEntries()
        if (componentSubview === "language-mode")
            return languageModeEntries()
        if (componentSubview === "language-specific")
            return specificLanguageEntries()
        if (componentSubview === "language-selected")
            return selectedLanguageEntries()
        if (componentSubview === "duration")
            return durationSelectorEntries()
        if (componentSubview === "acceleration")
            return accelerationSelectorEntries()
        if (componentSubview === "uninstall")
            return uninstallConfirmationEntries()
        return dictationDetailEntries()
    }

    function buildVisibleEntries(): var {
        // Keep the upstream model as a direct binding dependency while it scans.
        DesktopEntries.applications.values

        if (pendingPowerAction !== "") {
            const pending = powerActions.action(pendingPowerAction)
            if (!pending)
                return []
            return [
                {
                    kind: "cancelPower",
                    label: "Cancel",
                    detail: "Return without " + pending.label.toLowerCase(),
                    icon: "dialog-cancel"
                },
                {
                    kind: "confirmPower",
                    label: "Confirm " + pending.label.toLowerCase(),
                    detail: "This action will run immediately",
                    icon: pending.icon,
                    danger: true
                }
            ]
        }

        const query = normalize(searchText)
        if (currentSection === "apps")
            return applicationEntries(query)
        if (currentSection === "install")
            return installEntries(query)
        if (currentSection === "remove")
            return removeEntries(query)
        if (currentSection === "update")
            return updateEntries(query)
        if (currentSection === "components") {
            if (currentComponentId === "local-dictation")
                return dictationEntries()
            return componentCatalogEntries(query)
        }
        if (currentSection === "power")
            return powerEntries(query)
        if (query === "")
            return sections

        const combined = matchingSections(query)
            .concat(applicationEntries(query), powerEntries(query))
        combined.sort(function(left, right) {
            if (left.rank !== right.rank)
                return left.rank - right.rank
            if (left.kind !== right.kind)
                return left.kind === "section" ? -1
                    : right.kind === "section" ? 1
                        : left.kind === "application" ? -1 : 1
            const labelOrder = left.label.localeCompare(right.label)
            return labelOrder !== 0 ? labelOrder
                : left.sourceIndex - right.sourceIndex
        })
        return combined
    }

    function activate(entry): void {
        if (!entry || entry.enabled === false)
            return

        switch (entry.kind) {
        case "section":
            enterSection(entry.sectionId)
            break
        case "application":
            if (!entry.desktopEntry)
                return
            close()
            entry.desktopEntry.execute()
            break
        case "installSearch": {
            const search = entry.searchText
            if (installActions.commandForSearch(search).length === 0)
                return
            close()
            installActions.executeSearch(search)
            break
        }
        case "removePackage": {
            const packageObject = entry.packageObject
            if (removeActions.commandForPackage(packageObject).length === 0)
                return
            close()
            removeActions.executePackage(packageObject)
            break
        }
        case "update":
            if (updateActions.execute(entry.actionId))
                close()
            break
        case "component":
            openComponent(entry.componentId)
            break
        case "componentInfo":
            break
        case "dictationInstall":
            if (systemComponentsActions.execute(
                    systemComponentsActions.commandForInstall(), "install"))
                close()
            break
        case "dictationModelView":
            componentSubview = "model"
            break
        case "dictationModelSelect":
            if (systemComponentsActions.selectModel(entry.modelId))
                componentSubview = ""
            break
        case "dictationLanguageView":
            componentSubview = "language-mode"
            break
        case "dictationLanguageSpecificView":
            componentSubview = "language-specific"
            break
        case "dictationLanguageSpecificSelect":
            systemComponentsActions.proposedLanguageMode = "specific"
            systemComponentsActions.proposedLanguages = [entry.languageId]
            componentSubview = ""
            break
        case "dictationLanguageAutomatic":
            systemComponentsActions.proposedLanguageMode = "automatic"
            systemComponentsActions.proposedLanguages = []
            componentSubview = ""
            break
        case "dictationLanguageSelectedView":
            selectedLanguageDraft = systemComponentsActions.proposedLanguageMode === "selected"
                ? systemComponentsActions.proposedLanguages.slice() : []
            componentSubview = "language-selected"
            break
        case "dictationLanguageToggle": {
            const draft = selectedLanguageDraft.slice()
            const index = draft.indexOf(entry.languageId)
            if (index >= 0)
                draft.splice(index, 1)
            else if (draft.length < 3)
                draft.push(entry.languageId)
            selectedLanguageDraft = draft
            break
        }
        case "dictationLanguageSelectedDone":
            if (selectedLanguageDraft.length >= 2 && selectedLanguageDraft.length <= 3) {
                systemComponentsActions.proposedLanguageMode = "selected"
                systemComponentsActions.proposedLanguages = selectedLanguageDraft.slice()
                componentSubview = ""
            }
            break
        case "dictationDurationView":
            componentSubview = "duration"
            break
        case "dictationDurationSelect":
            systemComponentsActions.proposedMaxDuration = entry.duration
            componentSubview = ""
            break
        case "dictationAccelerationView":
            componentSubview = "acceleration"
            break
        case "dictationAccelerationSelect":
            if (systemComponentsActions.selectAcceleration(entry.accelerationId))
                componentSubview = ""
            break
        case "dictationApply":
            if (systemComponentsActions.execute(
                    systemComponentsActions.commandForApply(), "apply"))
                close()
            break
        case "dictationRefresh":
            systemComponentsActions.refreshAll()
            break
        case "dictationUninstallView":
            componentSubview = "uninstall"
            break
        case "dictationUninstallCancel":
            componentSubview = ""
            break
        case "dictationUninstallConfirm":
            if (systemComponentsActions.execute(
                    systemComponentsActions.commandForUninstall(), "uninstall"))
                close()
            break
        case "power":
            if (powerActions.requiresConfirmation(entry.actionId))
                pendingPowerAction = entry.actionId
            else {
                close()
                powerActions.execute(entry.actionId)
            }
            break
        case "cancelPower":
            pendingPowerAction = ""
            break
        case "confirmPower": {
            const actionId = pendingPowerAction
            close()
            powerActions.execute(actionId)
            break
        }
        }
    }

    IpcHandler {
        target: "vanhyprarch.superSpace"

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
