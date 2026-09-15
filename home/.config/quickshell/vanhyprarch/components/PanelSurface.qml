import QtQuick

Rectangle {
    id: root

    required property var metrics
    required property var theme
    property int padding: root.metrics.panelPadding
    readonly property int outlineThickness: root.metrics.panelOutlineThickness
    readonly property color outlineColor: root.theme.panelOutline
    readonly property int verticalEdgeTopInset: root.outlineThickness
    readonly property int verticalEdgeBottomInset: root.outlineThickness
    default property alias contentData: contentItem.data

    radius: root.metrics.panelRadius
    color: root.theme.background

    Item {
        id: contentItem

        anchors.fill: parent
        anchors.margins: root.padding
    }

    Rectangle {
        objectName: "panelOutlineTop"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: root.outlineThickness
        color: root.outlineColor
    }

    Rectangle {
        objectName: "panelOutlineRight"
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.topMargin: root.verticalEdgeTopInset
        anchors.bottomMargin: root.verticalEdgeBottomInset
        width: root.outlineThickness
        color: root.outlineColor
    }

    Rectangle {
        objectName: "panelOutlineBottom"
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: root.outlineThickness
        color: root.outlineColor
    }

    Rectangle {
        objectName: "panelOutlineLeft"
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.topMargin: root.verticalEdgeTopInset
        anchors.bottomMargin: root.verticalEdgeBottomInset
        width: root.outlineThickness
        color: root.outlineColor
    }
}
