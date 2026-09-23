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
    required property var targetScreen
    required property var focusCoordinator
    required property bool hardwareAvailable
    readonly property int buttonSize: root.metrics.dockSystemControlTarget

    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property bool adapterEnabled: adapter
        && adapter.state === BluetoothAdapterState.Enabled && adapter.enabled

    visible: root.hardwareAvailable
    implicitWidth: visible ? buttonSize : 0
    implicitHeight: visible ? buttonSize : 0
    width: implicitWidth
    height: implicitHeight

    SystemIcon {
        anchors.centerIn: parent
        iconName: "bluetooth"
        theme: root.theme
        metrics: root.metrics
        opacity: root.adapterEnabled ? 1.0 : 0.45
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.focusCoordinator.toggleDockWindow(bluetoothPanel)
    }

    onHardwareAvailableChanged: {
        if (!root.hardwareAvailable)
            bluetoothPanel.requestedVisible = false
    }

    BluetoothPanel {
        id: bluetoothPanel

        controller: root.controller
        powerController: root.powerController
        theme: root.theme
        metrics: root.metrics
        popupAnchorItem: root
        screenName: root.screenName
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
    }
}
