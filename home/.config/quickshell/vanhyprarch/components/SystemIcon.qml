import QtQuick
import QtQuick.Controls.impl as ControlsImpl

Item {
    id: root

    required property string iconName
    required property var theme
    required property var metrics

    readonly property int iconSize: root.metrics.dockSystemIconSize
    readonly property url assetSource: Qt.resolvedUrl(
        "../assets/system-icons/" + root.iconName + ".svg")
    readonly property bool ready: sourceImage.status === Image.Ready

    implicitWidth: iconSize
    implicitHeight: iconSize
    width: implicitWidth
    height: implicitHeight

    ControlsImpl.IconImage {
        id: sourceImage

        anchors.fill: parent
        source: root.assetSource
        color: root.theme.accent
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }
}
