import QtQuick

Rectangle {
    id: root

    required property var metrics
    required property var theme
    property string primaryText: ""
    property string secondaryText: ""
    property Component leading: null
    property Component trailing: null
    property bool keyboardSelected: false
    property bool active: false
    property bool danger: false
    property int primaryFontSize: root.metrics.overlayFontSize
    property int primaryFontWeight: root.metrics.overlayFontWeight
    readonly property bool highlighted: root.keyboardSelected
        || root.activeFocus || pointer.containsMouse
    signal activated()

    activeFocusOnTab: root.enabled
    implicitHeight: root.secondaryText === ""
        ? root.metrics.navigationRowHeight
        : root.metrics.detailedNavigationRowHeight
    radius: root.metrics.rowRadius
    opacity: root.enabled ? 1.0 : root.metrics.disabledInteractiveOpacity
    color: pointer.pressed
        ? (root.danger ? root.theme.dangerFill : root.theme.pressedFill)
        : root.highlighted
            ? root.theme.hoverFill
            : root.active ? root.theme.activeFill : "transparent"
    border.width: root.activeFocus ? root.metrics.controlOutlineThickness : 0
    border.color: root.theme.focus

    Keys.onReturnPressed: root.activated()
    Keys.onEnterPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    Loader {
        id: leadingLoader

        anchors.left: parent.left
        anchors.leftMargin: root.metrics.rowSidePadding
        anchors.verticalCenter: parent.verticalCenter
        sourceComponent: root.leading
        visible: root.leading !== null
    }

    Column {
        anchors.left: root.leading !== null ? leadingLoader.right : parent.left
        anchors.leftMargin: root.leading !== null
            ? root.metrics.iconTextGap : root.metrics.rowSidePadding
        anchors.right: root.trailing !== null ? trailingLoader.left : parent.right
        anchors.rightMargin: root.trailing !== null
            ? root.metrics.iconTextGap : root.metrics.rowSidePadding
        anchors.verticalCenter: parent.verticalCenter
        spacing: root.metrics.rowSpacing

        Text {
            width: parent.width
            text: root.primaryText
            textFormat: Text.PlainText
            color: root.danger ? root.theme.danger
                : root.theme.text
            font.pixelSize: root.primaryFontSize
            font.weight: root.primaryFontWeight
            elide: Text.ElideRight
        }

        Text {
            visible: root.secondaryText !== ""
            width: parent.width
            text: root.secondaryText
            textFormat: Text.PlainText
            color: root.theme.textMuted
            font.pixelSize: root.metrics.detailFontSize
            elide: Text.ElideRight
        }
    }

    Loader {
        id: trailingLoader

        anchors.right: parent.right
        anchors.rightMargin: root.metrics.rowSidePadding
        anchors.verticalCenter: parent.verticalCenter
        sourceComponent: root.trailing
        visible: root.trailing !== null
    }

    MouseArea {
        id: pointer

        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            root.forceActiveFocus()
            root.activated()
        }
    }
}
