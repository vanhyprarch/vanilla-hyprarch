import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    required property InstallActions installActions
    required property RemoveActions removeActions
    required property PowerActions powerActions

    property bool isOpen: false
    property string activeScreenName: ""
    property string currentSection: "root"
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
        searchText = ""
        pendingPowerAction = ""
        isOpen = true
    }

    function close(): void {
        isOpen = false
        currentSection = "root"
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
        } else if (currentSection !== "root") {
            currentSection = "root"
            searchText = ""
        } else {
            close()
        }
    }

    function enterSection(sectionId: string): void {
        if (sectionId !== "apps" && sectionId !== "install"
                && sectionId !== "remove" && sectionId !== "power")
            return
        currentSection = sectionId
        searchText = ""
        if (sectionId === "remove")
            removeActions.refreshPackages()
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
        if (!entry)
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
