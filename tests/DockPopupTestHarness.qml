import QtQuick

Item {
    required property var metrics
    required property Item popupAnchorItem
    property int panelWidth: metrics.standardPanelWidth
    property int requestedPanelHeight: 0
    property int parallelOffset: metrics.dockPopupParallelOffset
    property bool requestedVisible: false

    implicitWidth: panelWidth
    implicitHeight: requestedPanelHeight
}
