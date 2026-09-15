import QtQuick
import Quickshell
import Quickshell.Bluetooth

Item {
    id: root

    required property var controller
    required property var powerController
    required property var theme
    required property var metrics
    required property string screenName
    readonly property int buttonSize: root.metrics.dockSystemControlTarget
    readonly property int iconSize: root.metrics.dockSystemIconSize

    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property bool adapterEnabled: adapter
        && adapter.state === BluetoothAdapterState.Enabled && adapter.enabled

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight

    Image {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath("preferences-system-bluetooth")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        opacity: root.adapterEnabled ? 1.0 : 0.45
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: bluetoothPanel.visible = !bluetoothPanel.visible
    }

    BluetoothPanel {
        id: bluetoothPanel

        controller: root.controller
        powerController: root.powerController
        theme: root.theme
        metrics: root.metrics
        popupAnchorItem: root
        screenName: root.screenName
    }
}
