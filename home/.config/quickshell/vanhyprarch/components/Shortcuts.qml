import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

    required property var systemComponentsActions
    property bool isOpen: false
    property bool loading: false
    property string activeScreenName: ""
    property string searchText: ""
    property string errorMessage: ""
    property var entries: []
    readonly property var filteredEntries: filterEntries()

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

        searchText = ""
        entries = []
        errorMessage = ""
        loading = true
        isOpen = true
        systemComponentsActions.refreshStatus()
        bindsProcess.startLoad()
    }

    function close(): void {
        isOpen = false
        searchText = ""
        bindsProcess.reloadPending = false
    }

    function toggle(): void {
        if (isOpen)
            close()
        else
            open()
    }

    function normalizedSearch(value: string): string {
        return value.toLowerCase().replace(/\+/g, " ")
            .replace(/\s+/g, " ").trim()
    }

    function displayKey(key: string, keycode: int): string {
        const names = {
            "RETURN": "Return",
            "LEFT": "Left",
            "RIGHT": "Right",
            "UP": "Up",
            "DOWN": "Down",
            "TAB": "Tab",
            "XF86AudioRaiseVolume": "Volume Up",
            "XF86AudioLowerVolume": "Volume Down",
            "XF86AudioMute": "Volume Mute",
            "XF86AudioMicMute": "Microphone Mute",
            "mouse:272": "Mouse Left",
            "mouse:273": "Mouse Right",
            "mouse_up": "Wheel Up",
            "mouse_down": "Wheel Down"
        }

        if (key !== "") {
            if (names[key] !== undefined)
                return names[key]
            if (key.length === 1)
                return key.toUpperCase()
            return key.charAt(0).toUpperCase()
                + key.slice(1).replace(/_/g, " ")
        }

        return keycode > 0 ? "Keycode " + keycode : "Unknown"
    }

    function displayChord(modmask: int, key: string, keycode: int): string {
        const parts = []
        if ((modmask & 64) !== 0)
            parts.push("Super")
        if ((modmask & 4) !== 0)
            parts.push("Ctrl")
        if ((modmask & 1) !== 0)
            parts.push("Shift")
        if ((modmask & 8) !== 0)
            parts.push("Alt")

        const knownMask = 64 | 4 | 1 | 8
        const unknownMask = modmask & ~knownMask
        if (unknownMask !== 0)
            parts.push("Mod 0x" + unknownMask.toString(16).toUpperCase())

        parts.push(displayKey(key, keycode))
        return parts.join(" + ")
    }

    function categoryRank(category: string): int {
        const preferred = ["Apps", "Shell", "System", "Capture",
            "Dictation", "Window", "Workspace", "Audio"]
        const index = preferred.indexOf(category)
        if (index >= 0)
            return index
        return category === "Other" ? 10000 : 100
    }

    function decodeMetadataDescription(value: string): var {
        const metadataStart = String.fromCodePoint(0xE0001)
        const metadataEnd = String.fromCodePoint(0xE007F)
        const start = value.indexOf(metadataStart)
        const strayEnd = value.indexOf(metadataEnd)
        if (start < 0)
            return strayEnd < 0 ? { visible: value, availability: "" } : null
        if (!value.endsWith(metadataEnd) || strayEnd < start)
            return null

        const bodyStart = start + metadataStart.length
        const bodyEnd = value.length - metadataEnd.length
        let payload = ""
        for (let index = bodyStart; index < bodyEnd;) {
            const point = value.codePointAt(index)
            if (point < 0xE0020 || point > 0xE007E)
                return null
            payload += String.fromCharCode(point - 0xE0000)
            index += point > 0xFFFF ? 2 : 1
        }

        const match = /^vh1;availability=([a-z0-9-]+)$/.exec(payload)
        if (match === null)
            return null
        return {
            visible: value.slice(0, start),
            availability: match[1]
        }
    }

    function parseDescription(value: string): var {
        const decoded = decodeMetadataDescription(value)
        if (decoded === null)
            return null

        const description = decoded.visible.trim()
        if (description === "")
            return null
        const separator = description.indexOf("|")
        let category = "Other"
        let action = description
        if (separator >= 0) {
            category = description.slice(0, separator).trim()
            action = description.slice(separator + 1).trim()
            if (category === "")
                category = "Other"
            if (action === "")
                action = description.replace("|", "").trim()
        }
        if (action === "")
            action = "Unnamed shortcut"
        return {
            category: category,
            action: action,
            availability: decoded.availability
        }
    }

    function entryIdentity(category: string, action: string,
        availability: string): string {
        return category + "\u0000" + action + "\u0000" + availability
    }

    function availabilityIsSatisfied(availability: string): bool {
        switch (availability) {
        case "": return true
        case "local-dictation": return systemComponentsActions.installed
        default: return false
        }
    }

    function selectionIndex(visibleEntries: var, selectedId: string,
        previousIndex: int): int {
        if (!Array.isArray(visibleEntries) || visibleEntries.length === 0)
            return -1
        if (selectedId !== "") {
            const retained = visibleEntries.findIndex(entry => entry.id === selectedId)
            if (retained >= 0)
                return retained
        }
        return Math.min(Math.max(previousIndex, 0), visibleEntries.length - 1)
    }

    function parseBindings(output: string): var {
        const bindings = JSON.parse(output)
        if (!Array.isArray(bindings))
            throw new Error("Hyprland returned a non-array binding list")

        const grouped = {}
        const parsed = []

        for (let index = 0; index < bindings.length; ++index) {
            const binding = bindings[index]
            if (!binding || binding.has_description !== true
                    || typeof binding.description !== "string")
                continue

            const description = parseDescription(binding.description)
            if (description === null)
                continue

            const chord = displayChord(Number(binding.modmask) || 0,
                typeof binding.key === "string" ? binding.key.trim() : "",
                Number(binding.keycode) || 0)
            const groupKey = entryIdentity(description.category,
                description.action, description.availability)
            let group = grouped[groupKey]
            if (group === undefined) {
                group = {
                    id: groupKey,
                    category: description.category,
                    action: description.action,
                    availability: description.availability,
                    chords: [],
                    firstIndex: index
                }
                grouped[groupKey] = group
                parsed.push(group)
            }
            if (group.chords.indexOf(chord) < 0)
                group.chords.push(chord)
        }

        parsed.sort(function(left, right) {
            const leftRank = categoryRank(left.category)
            const rightRank = categoryRank(right.category)
            if (leftRank !== rightRank)
                return leftRank - rightRank
            if (leftRank === 100) {
                const categoryOrder = left.category.localeCompare(right.category)
                if (categoryOrder !== 0)
                    return categoryOrder
            }
            return left.firstIndex - right.firstIndex
        })

        return parsed
    }

    function filterEntries(): var {
        const query = normalizedSearch(searchText)
        const result = []
        let previousCategory = ""

        for (let index = 0; index < entries.length; ++index) {
            const entry = entries[index]
            if (!availabilityIsSatisfied(entry.availability))
                continue
            const searchable = normalizedSearch(entry.category + " "
                + entry.action + " " + entry.chords.join(" "))
            if (query !== "" && searchable.indexOf(query) < 0)
                continue

            result.push({
                id: entry.id,
                category: entry.category,
                action: entry.action,
                availability: entry.availability,
                chords: entry.chords,
                showCategory: entry.category !== previousCategory
            })
            previousCategory = entry.category
        }

        return result
    }

    Connections {
        target: root.systemComponentsActions

        function onHyprlandReloadCompleted(exitCode): void {
            if (exitCode === 0 && root.isOpen)
                bindsProcess.startLoad()
        }
    }

    IpcHandler {
        target: "vanhyprarch.shortcuts"

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

    Process {
        id: bindsProcess

        property string outputText: ""
        property bool exitReceived: false
        property bool stdoutReceived: false
        property bool resultHandled: false
        property bool reloadPending: false
        property int lastExitCode: -1

        function startLoad(): void {
            if (running) {
                reloadPending = true
                return
            }
            outputText = ""
            exitReceived = false
            stdoutReceived = false
            resultHandled = false
            lastExitCode = -1
            command = ["hyprctl", "-j", "binds"]
            running = true
        }

        function maybeFinish(): void {
            if (resultHandled || !exitReceived || !stdoutReceived)
                return

            resultHandled = true
            root.loading = false
            if (lastExitCode !== 0) {
                root.errorMessage = "Could not load shortcuts (hyprctl exit "
                    + lastExitCode + ")."
                root.entries = []
                outputText = ""
                reloadPending = false
                return
            }

            try {
                root.entries = root.parseBindings(outputText)
                root.errorMessage = ""
            } catch (error) {
                root.entries = []
                root.errorMessage = "Could not read Hyprland shortcuts."
                console.warn("Failed to parse hyprctl binds JSON: " + error)
            }

            outputText = ""
            const shouldReload = reloadPending && root.isOpen
            reloadPending = false
            if (shouldReload)
                Qt.callLater(startLoad)
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                bindsProcess.outputText = text
                bindsProcess.stdoutReceived = true
                bindsProcess.maybeFinish()
            }
        }

        onExited: function(exitCode, exitStatus) {
            bindsProcess.lastExitCode = exitCode
            bindsProcess.exitReceived = true
            bindsProcess.maybeFinish()
        }
    }
}
