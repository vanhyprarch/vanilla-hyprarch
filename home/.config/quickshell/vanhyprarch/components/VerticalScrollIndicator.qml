import QtQuick

Item {
    id: root

    required property var view
    required property var metrics
    required property var theme

    readonly property int reservedWidth: metrics.scrollIndicatorGutter
    readonly property real trackHeight: Math.max(0,
        height - metrics.scrollIndicatorInset * 2)
    readonly property real heightRatio: {
        const ratio = Number(view.visibleArea.heightRatio)
        return isFinite(ratio) ? Math.max(0, Math.min(1, ratio)) : 1
    }
    readonly property bool scrollable: view.height > 0 && view.contentHeight
        > view.height + metrics.scrollOverflowTolerance
    readonly property real thumbHeight: Math.min(trackHeight,
        Math.max(metrics.scrollIndicatorMinimumThumbHeight,
            trackHeight * heightRatio))
    readonly property real scrollProgress: {
        if (view.atYBeginning)
            return 0
        if (view.atYEnd)
            return 1
        const range = 1 - heightRatio
        const position = Number(view.visibleArea.yPosition)
        return range > 0
                && isFinite(position)
            ? Math.max(0, Math.min(1, position / range))
            : 0
    }
    readonly property real thumbY: metrics.scrollIndicatorInset
        + (trackHeight - thumbHeight) * scrollProgress

    parent: view
    anchors {
        top: parent.top
        right: parent.right
        bottom: parent.bottom
    }
    width: reservedWidth
    visible: scrollable

    Rectangle {
        x: root.width - root.metrics.scrollIndicatorInset
            - root.metrics.scrollIndicatorWidth
        y: root.thumbY
        width: root.metrics.scrollIndicatorWidth
        height: root.thumbHeight
        radius: 0
        color: root.theme.textMuted
    }
}
