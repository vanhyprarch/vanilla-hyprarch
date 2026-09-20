import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    property var parsedEntries: []
    property string terminalId: ""
    property string closeId: ""
    property string startDictationId: ""

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    function tagged(payload) {
        let result = String.fromCodePoint(0xE0001)
        for (let index = 0; index < payload.length; ++index)
            result += String.fromCodePoint(0xE0000 + payload.charCodeAt(index))
        return result + String.fromCodePoint(0xE007F)
    }

    function binding(description, modmask, key, keycode, release) {
        return {
            has_description: true,
            description: description,
            modmask: modmask || 0,
            key: key || "",
            keycode: keycode || 0,
            release: release === true
        }
    }

    SystemComponentsActions {
        id: componentActions
        checksEnabled: false
        executionEnabled: false
    }

    Shortcuts {
        id: shortcuts
        systemComponentsActions: componentActions
    }

    function firstPhase() {
        const dictationMetadata = tagged("vh1;availability=local-dictation")
        const fixtures = [
            binding("Window | Close window", 64, "W"),
            binding("Dictation | Start recording" + dictationMetadata, 0, "F9"),
            binding("Apps | Terminal", 64, "RETURN"),
            binding("Dictation | Stop and transcribe" + dictationMetadata,
                0, "F9", 0, true),
            binding("Apps | Terminal", 65, "RETURN"),
            binding("Unknown | Keycode action", 0, "", 42),
            binding("Shell | Open command center", 68, "SPACE"),
            binding("System | Core action", 68, "I"),
            binding("Capture | Screenshot", 0, "PRINT"),
            binding("Workspace | Workspace 1", 64, "1"),
            binding("Audio | Volume up", 0, "XF86AudioRaiseVolume")
        ]
        parsedEntries = shortcuts.parseBindings(JSON.stringify(fixtures))
        shortcuts.entries = parsedEntries

        check(parsedEntries.map(entry => entry.category).join(",")
            === "Apps,Shell,System,Capture,Dictation,Dictation,Window,Workspace,Audio,Unknown",
            "preferred category order is wrong")
        const terminal = parsedEntries.find(entry => entry.action === "Terminal")
        const close = parsedEntries.find(entry => entry.action === "Close window")
        const start = parsedEntries.find(entry => entry.action === "Start recording")
        check(terminal.chords.join(",") === "Super + Return,Super + Shift + Return",
            "aliases did not group by logical action")
        check(start.availability === "local-dictation"
                && start.action === "Start recording"
                && start.category === "Dictation",
            "metadata did not strip to the original visible description")
        check(parsedEntries.filter(entry => entry.category === "Dictation").length === 2,
            "F9 press and release actions were merged")
        check(parsedEntries.find(entry => entry.action === "Keycode action")
                .chords[0] === "Keycode 42",
            "keycode fallback is wrong")
        check(shortcuts.displayChord(68, "RETURN", 0) === "Super + Ctrl + Return",
            "modifier/key display is wrong")
        check(shortcuts.filteredEntries.every(entry => entry.category !== "Dictation"),
            "unavailable Dictation rows remained visible")
        check(shortcuts.filteredEntries.every((entry, index, entries) =>
                entry.showCategory === (index === 0
                    || entry.category !== entries[index - 1].category)),
            "category headers contain an empty or duplicate gap")

        const malformed = "Dictation | Broken" + String.fromCodePoint(0xE0001)
        const unknownVersion = "Dictation | Future"
            + tagged("vh2;availability=local-dictation")
        check(shortcuts.parseBindings(JSON.stringify([
                binding(malformed, 0, "F8"), binding(unknownVersion, 0, "F7")
            ])).length === 0,
            "malformed or unknown metadata did not fail closed")

        const unknownCapability = shortcuts.parseBindings(JSON.stringify([
            binding("Future | Hidden" + tagged("vh1;availability=unknown-capability"),
                0, "F6")
        ]))
        shortcuts.entries = unknownCapability
        check(unknownCapability.length === 1 && shortcuts.filteredEntries.length === 0,
            "unknown availability did not fail closed for display")

        shortcuts.entries = parsedEntries
        terminalId = terminal.id
        closeId = close.id
        startDictationId = start.id
        shortcuts.isOpen = true
        Qt.callLater(secondPhase)
    }

    function secondPhase() {
        check(shortcuts.filteredEntries.every(entry => entry.category !== "Dictation"),
            "Dictation became visible without installed state")
        componentActions.statusData = Object.assign({}, componentActions.statusData, {
            state: "installed", installed: true
        })
        Qt.callLater(thirdPhase)
    }

    function thirdPhase() {
        const installedEntries = shortcuts.filteredEntries
        check(installedEntries.filter(entry => entry.category === "Dictation").length === 2,
            "installed Dictation rows are not visible")
        check(shortcuts.isOpen, "availability change dismissed Super+K")

        const closeIndex = shortcuts.selectionIndex(installedEntries, closeId, 1)
        check(installedEntries[closeIndex].id === closeId,
            "unrelated selected row was not retained after insertion")

        shortcuts.searchText = "recording"
        Qt.callLater(fourthPhase)
    }

    function fourthPhase() {
        check(shortcuts.filteredEntries.length === 1
                && shortcuts.filteredEntries[0].id === startDictationId,
            "search and availability filters do not compose")
        shortcuts.searchText = ""
        componentActions.statusData = Object.assign({}, componentActions.statusData, {
            state: "not-installed", installed: false
        })
        Qt.callLater(finalPhase)
    }

    function finalPhase() {
        const absentEntries = shortcuts.filteredEntries
        check(absentEntries.every(entry => entry.category !== "Dictation"),
            "Dictation category did not disappear")
        const nearest = shortcuts.selectionIndex(absentEntries,
            startDictationId, 2)
        check(nearest === Math.min(2, absentEntries.length - 1),
            "removed optional selection did not choose the nearest row")
        check(shortcuts.selectionIndex([], terminalId, 0) === -1,
            "empty results did not select index -1")
        check(shortcuts.isOpen, "filter update dismissed Super+K")
        console.log("VANHYPRARCH_SHORTCUTS_TEST_PASS")
        Qt.quit()
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: root.firstPhase()
    }
}
