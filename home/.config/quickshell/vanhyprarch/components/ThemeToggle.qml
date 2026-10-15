import QtQuick

Item {
    id: root

    required property var controller
    required property var theme
    required property var metrics
    readonly property int buttonSize: root.metrics.dockSystemControlTarget

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    function activate(): void {
        if (root.controller.ready && !root.controller.busy)
            root.controller.toggleMode()
    }

    SystemIcon {
        anchors.centerIn: parent
        iconName: root.controller.darkMode ? "moon" : "sun"
        theme: root.theme
        metrics: root.metrics
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        enabled: root.controller.ready && !root.controller.busy
        onClicked: root.activate()
    }
}
