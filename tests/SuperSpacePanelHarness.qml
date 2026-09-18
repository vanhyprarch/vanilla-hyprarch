import QtQuick

Item {
    id: root

    visible: false

    required property var controller
    property string selectedEntryIdentity: ""
    property int selectedEntryIndex: -1

    function entrySelectable(index) {
        return index >= 0 && index < controller.visibleEntries.length
            && controller.visibleEntries[index].selectable !== false
            && controller.visibleEntries[index].enabled !== false
    }

    function selectEntryAt(index) {
        if (!entrySelectable(index))
            return false
        selectedEntryIndex = index
        selectedEntryIdentity = controller.entryIdentity(
            controller.visibleEntries[index])
        return true
    }

    function resetSelection() {
        selectedEntryIdentity = ""
        selectedEntryIndex = -1
        for (let index = 0; index < controller.visibleEntries.length; ++index) {
            if (selectEntryAt(index))
                return
        }
    }

    function preserveSelection() {
        const identity = selectedEntryIdentity
        if (identity !== "") {
            for (let index = 0; index < controller.visibleEntries.length; ++index) {
                if (entrySelectable(index)
                        && controller.entryIdentity(controller.visibleEntries[index])
                            === identity) {
                    selectedEntryIndex = index
                    return
                }
            }
        }
        resetSelection()
    }

    function moveSelection(offset) {
        const count = controller.visibleEntries.length
        if (count === 0) {
            resetSelection()
            return
        }
        const step = offset < 0 ? -1 : 1
        let candidate = selectedEntryIndex
        if (candidate < 0 || candidate >= count)
            candidate = step > 0 ? -1 : 0
        for (let attempts = 0; attempts < count; ++attempts) {
            candidate = (candidate + step + count) % count
            if (selectEntryAt(candidate))
                return
        }
        resetSelection()
    }

    function activateSelection() {
        if (selectedEntryIndex >= 0
                && selectedEntryIndex < controller.visibleEntries.length)
            controller.activate(controller.visibleEntries[selectedEntryIndex])
    }

    function pressEscape() {
        controller.goBack()
    }

    Connections {
        target: root.controller
        function onVisibleEntriesChanged() { root.preserveSelection() }
    }
}
