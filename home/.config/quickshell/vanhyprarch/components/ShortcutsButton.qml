import QtQuick

Item {
    id: root

    required property Shortcuts controller
    required property var theme
    required property var metrics
    readonly property int buttonSize: root.metrics.dockSystemControlTarget

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    SystemIcon {
        anchors.centerIn: parent
        iconName: "information"
        theme: root.theme
        metrics: root.metrics
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.controller.toggle()
    }
}
