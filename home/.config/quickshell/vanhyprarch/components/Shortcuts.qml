import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Scope {
    id: root

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
        bindsProcess.startLoad()
    }

    function close(): void {
        isOpen = false
        searchText = ""
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
        const preferred = ["Apps", "Window", "Workspace", "Audio"]
        const index = preferred.indexOf(category)
        if (index >= 0)
            return index
        return category === "Other" ? 10000 : 100
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

            const description = binding.description.trim()
            if (description === "")
                continue

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

            const chord = displayChord(Number(binding.modmask) || 0,
                typeof binding.key === "string" ? binding.key.trim() : "",
                Number(binding.keycode) || 0)
            const groupKey = category + "\u0000" + action
            let group = grouped[groupKey]
            if (group === undefined) {
                group = {
                    category: category,
                    action: action,
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
            const searchable = normalizedSearch(entry.category + " "
                + entry.action + " " + entry.chords.join(" "))
            if (query !== "" && searchable.indexOf(query) < 0)
                continue

            result.push({
                category: entry.category,
                action: entry.action,
                chords: entry.chords,
                showCategory: entry.category !== previousCategory
            })
            previousCategory = entry.category
        }

        return result
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
        property int lastExitCode: -1

        function startLoad(): void {
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
