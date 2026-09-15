import QtQuick

Item {
    id: root

    required property var metrics
    required property var theme
    property bool checked: false
    property bool interactive: true
    readonly property int knobOffX: root.metrics.toggleKnobInset
    readonly property int knobOnX: width - root.metrics.toggleKnobSize
        - root.metrics.toggleKnobInset
    readonly property int knobY: root.metrics.toggleKnobInset
    readonly property color trackColor: root.checked
        ? root.theme.activeFill : root.theme.normalFill
    readonly property color knobColor: root.theme.toggleKnob
    signal toggled()

    implicitWidth: root.metrics.toggleTrackWidth
    implicitHeight: root.metrics.toggleTrackHeight
    width: implicitWidth
    height: implicitHeight
    opacity: root.enabled ? 1.0 : root.metrics.disabledInteractiveOpacity

    Rectangle {
        id: track

        anchors.fill: parent
        radius: root.metrics.rowRadius
        color: root.trackColor
        border.width: 0

        Rectangle {
            width: root.metrics.toggleKnobSize
            height: root.metrics.toggleKnobSize
            x: root.checked ? root.knobOnX : root.knobOffX
            y: root.knobY
            radius: root.metrics.rowRadius
            color: root.knobColor

            Behavior on x {
                NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.interactive && root.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.toggled()
    }
}
