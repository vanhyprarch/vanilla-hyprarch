import QtQuick
import Quickshell

Scope {
    id: root

    readonly property string footExecutable: "/usr/bin/foot"
    readonly property string yayExecutable: "/usr/bin/yay"

    function searchTerms(searchText: string): var {
        const trimmed = searchText.trim()
        return trimmed === "" ? [] : trimmed.split(/\s+/)
    }

    function commandForSearch(searchText: string): var {
        const terms = searchTerms(searchText)
        if (terms.length === 0)
            return []

        const command = [
            footExecutable,
            "--hold",
            "--title=Vanilla HyprArch Install",
            yayExecutable,
            "-Y",
            "--"
        ]
        return command.concat(terms)
    }

    function executeSearch(searchText: string): bool {
        const command = commandForSearch(searchText)
        if (command.length === 0) {
            console.warn("Refusing empty package search")
            return false
        }

        Quickshell.execDetached(command)
        return true
    }
}
