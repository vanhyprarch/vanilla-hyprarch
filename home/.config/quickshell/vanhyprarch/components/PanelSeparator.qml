import QtQuick

Rectangle {
    id: root

    required property var metrics
    required property var theme

    width: parent ? parent.width : 0
    implicitHeight: root.metrics.separatorThickness
    height: implicitHeight
    color: root.theme.separator
}
