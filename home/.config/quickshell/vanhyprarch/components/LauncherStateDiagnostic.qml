pragma ComponentBehavior: Bound

import QtQuick

DockPopup {
    id: root
    objectName: "launcherStateDiagnostic"

    required property var theme
    required property LauncherStore launcherStore

    panelWidth: root.metrics.scaled(248)
    requestedPanelHeight: content.implicitHeight
        + root.metrics.compactMenuPadding * 2
    alignToAnchorTop: true
    anchorTopOffset: 4

    onVisibleChanged: {
        if (!visible)
            root.contentItem.forceActiveFocus()
    }

    Connections {
        target: root.launcherStore
        function onReadyChanged(): void {
            if (root.launcherStore.ready)
                root.requestedVisible = false
        }
    }

    PanelSurface {
        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme
        padding: root.metrics.compactMenuPadding

        Column {
            id: content
            width: parent.width
            spacing: root.metrics.rowSpacing

            Text {
                objectName: "launcherStateErrorTitle"
                width: parent.width
                text: "Launcher state could not be loaded."
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.theme.text
                font.pixelSize: root.metrics.informationLabelFontSize
            }

            Text {
                objectName: "launcherStatePreservedMessage"
                width: parent.width
                text: "Your file was preserved."
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.theme.textMuted
                font.pixelSize: root.metrics.informationLabelFontSize
            }

            PanelActionRow {
                objectName: "launcherStateRetry"
                width: parent.width
                implicitHeight: root.metrics.compactActionRowHeight
                metrics: root.metrics
                theme: root.theme
                primaryText: "Retry"
                primaryFontSize: root.metrics.informationLabelFontSize
                primaryFontWeight: root.metrics.informationLabelFontWeight
                onActivated: root.launcherStore.retry()
            }
        }
    }
}
