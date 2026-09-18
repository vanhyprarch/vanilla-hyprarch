pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

DockPopup {
    id: root

    required property var theme
    required property LauncherStore launcherStore
    readonly property int maximumPanelHeight: root.metrics.scaled(360)

    panelWidth: root.metrics.actionSurfaceWidth
    implicitHeight: Math.min(root.maximumPanelHeight,
        applicationsView.contentHeight + root.metrics.panelPadding * 2)

    onVisibleChanged: {
        if (visible)
            applicationsView.positionViewAtBeginning()
        else
            root.contentItem.forceActiveFocus()
    }

    PanelSurface {
        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme
        padding: root.metrics.panelPadding

        ListView {
            id: applicationsView

            anchors.fill: parent
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: DesktopEntries.applications

            VerticalScrollIndicator {
                view: applicationsView
                metrics: root.metrics
                theme: root.theme
            }

            delegate: PanelActionRow {
                id: appRow

                required property DesktopEntry modelData
                readonly property bool alreadyAdded:
                    root.launcherStore.contains(modelData.id)
                readonly property bool canAdd:
                    root.launcherStore.ready && !alreadyAdded

                width: applicationsView.width
                    - root.metrics.scrollIndicatorGutter
                metrics: root.metrics
                theme: root.theme
                primaryText: modelData.name
                primaryFontSize: root.metrics.informationLabelFontSize
                primaryFontWeight: root.metrics.informationLabelFontWeight
                leading: appIconComponent
                trailing: alreadyAdded ? addedLabelComponent : null
                enabled: canAdd
                activeFocusOnTab: false
                onActivated: {
                    if (!appRow.canAdd)
                        return
                    root.launcherStore.addLauncher(appRow.modelData.id)
                    root.requestedVisible = false
                }

                Component {
                    id: appIconComponent

                    Image {
                        id: appIcon

                        property bool failed: false
                        readonly property string iconName:
                            appRow.modelData.icon || ""

                        width: root.metrics.heroIconSize
                        height: root.metrics.heroIconSize
                        source: Quickshell.iconPath(!failed && iconName !== ""
                            ? iconName : "application-x-executable",
                            "application-x-executable")
                        sourceSize: Qt.size(width, height)
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                        onIconNameChanged: failed = false
                        onStatusChanged: {
                            if (status === Image.Error && !failed)
                                failed = true
                        }
                    }
                }

                Component {
                    id: addedLabelComponent

                    Text {
                        text: "Added"
                        color: root.theme.textMuted
                        font.pixelSize: root.metrics.detailFontSize
                        wrapMode: Text.NoWrap
                    }
                }
            }
        }
    }
}
