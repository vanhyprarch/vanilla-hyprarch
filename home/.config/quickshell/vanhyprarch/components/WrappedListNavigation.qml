import QtQuick

QtObject {
    id: root

    required property var view
    property var isSelectable: function(index) { return true }

    function selectable(index: int): bool {
        return index >= 0 && index < root.view.count
            && Boolean(root.isSelectable(index))
    }

    function move(direction: int): bool {
        const count = root.view.count
        if (count <= 0) {
            root.view.currentIndex = -1
            return false
        }

        const step = direction < 0 ? -1 : 1
        let candidate = root.view.currentIndex
        if (candidate < 0 || candidate >= count)
            candidate = step > 0 ? -1 : 0

        for (let attempts = 0; attempts < count; ++attempts) {
            candidate = (candidate + step + count) % count
            if (root.selectable(candidate)) {
                root.view.currentIndex = candidate
                root.view.positionViewAtIndex(candidate, ListView.Contain)
                return true
            }
        }

        root.view.currentIndex = -1
        return false
    }

    function moveClamped(offset: int): bool {
        const count = root.view.count
        if (count <= 0) {
            root.view.currentIndex = -1
            return false
        }
        const start = root.view.currentIndex < 0
            || root.view.currentIndex >= count ? 0 : root.view.currentIndex
        const candidate = Math.max(0, Math.min(count - 1, start + offset))
        root.view.currentIndex = candidate
        root.view.positionViewAtIndex(candidate, ListView.Contain)
        return true
    }
}
