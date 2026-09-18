import QtQuick

Item {
    required property var metrics
    required property Item popupAnchorItem
    property int panelWidth: metrics.standardPanelWidth
    property int parallelOffset: metrics.dockPopupParallelOffset

    implicitWidth: panelWidth
}
