//@ pragma UseQApplication
//@ pragma IconTheme Papirus
//@ pragma Env QT_QUICK_FLICKABLE_WHEEL_DECELERATION=10000

import QtQuick
import QtQuick.VectorImage
import Quickshell
import Quickshell.Io
import "components"

ShellRoot {
    id: root

    TextSizeController {
        id: textSizeController
    }

    VisualMetrics {
        id: visualMetrics
        fontBaseSize: textSizeController.baseSize
    }

    IpcHandler {
        target: "vanhyprarch.shell"

        function ping(): string {
            return "pong"
        }
    }

    Theme {
        id: shellTheme
        metrics: visualMetrics
    }

    AppearanceController {
        id: appearanceController
        theme: shellTheme
    }

    BackgroundPickerController {
        id: backgroundPicker
        appearance: appearanceController
    }

    Shortcuts {
        id: shortcuts
        systemComponentsActions: systemComponentsActions
    }

    PowerActions {
        id: powerActions
    }

    InstallActions {
        id: installActions
    }

    RemoveActions {
        id: removeActions
    }

    UpdateActions {
        id: updateActions
    }

    SystemComponentsActions {
        id: systemComponentsActions
    }

    DefaultAppsActions {
        id: defaultAppsActions
    }

    ZigScreensaverActions {
        id: zigScreensaverActions

        onOperationTerminalCompleted: function(operationKind, exitCode) {
            if (exitCode === 0)
                idleController.refreshStatus(false)
        }
    }

    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        updateActions: updateActions
        systemComponentsActions: systemComponentsActions
        defaultAppsActions: defaultAppsActions
        zigScreensaverActions: zigScreensaverActions
        powerActions: powerActions
        onBackgroundPickerRequested: backgroundPicker.open()
    }

    IdleController {
        id: idleController
    }

    IpcHandler {
        target: "vanhyprarch.idle"

        function refresh(): void {
            idleController.refreshStatus(true)
        }
    }

    BluetoothHardwareController {
        id: bluetoothHardwareController
    }

    BluetoothAgentController {
        id: bluetoothAgentController
        hardwareAvailable: bluetoothHardwareController.hardwareAvailable
    }

    BluetoothPowerController {
        id: bluetoothPowerController
    }

    LauncherStore {
        id: launcherStore
    }

    LauncherController {
        id: launcherController
    }

    readonly property var globalTextSizeController: textSizeController
    readonly property var globalMonitorController: monitorController
    readonly property PowerActions globalPowerActions: powerActions
    property url logoSource: Qt.resolvedUrl("assets/logo.svg")

    OverlayFocusCoordinator {
        id: overlayFocusCoordinator
    }

    MonitorController {
        id: monitorController
    }

    Variants {
        model: Quickshell.screens

        delegate: Scope {
            id: screenScope

            required property var modelData

    VisualMetrics {
        id: screenMetrics
        fontBaseSize: textSizeController.baseSize
        viewportWidth: screenScope.modelData.width
        viewportHeight: screenScope.modelData.height
        physicalPixelDensity: screenScope.modelData.physicalPixelDensity
    }

    PanelWindow {
        id: dockWindow

        // Appearance applies the authoritative palette before setting ready.
        visible: appearanceController.ready
        screen: screenScope.modelData

        anchors {
            top: true
            bottom: true
            left: true
        }

        implicitWidth: screenMetrics.dockWidth
        exclusiveZone: screenMetrics.dockWidth
        color: "transparent"

        Rectangle {
            anchors.fill: parent
            color: shellTheme.background
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            onPressed: overlayFocusCoordinator.dockBackgroundInteracted()
        }

        Item {
            id: dockTopRegion

            readonly property int desiredHeight: screenMetrics.dockOuterInset
                + screenMetrics.dockLogoSize + dockWorkspaces.logoGap
                + dockWorkspaces.implicitHeight

            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: screenMetrics.dockTopRegionHeight(desiredHeight)
            clip: true

            // Keep the exact SVG curves in the Qt Quick scene. CurveRenderer
            // avoids Image's SVG-to-pixmap rasterization for the static mark.
            VectorImage {
                id: dockLogo

                anchors {
                    top: parent.top
                    horizontalCenter: parent.horizontalCenter
                    topMargin: screenMetrics.dockOuterInset
                }
                source: logoSource
                width: screenMetrics.dockLogoSize
                height: screenMetrics.dockLogoSize
                fillMode: VectorImage.PreserveAspectFit
                preferredRendererType: VectorImage.CurveRenderer

                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: superSpace.toggle()
                }
            }

            Workspaces {
                id: dockWorkspaces
                theme: shellTheme
                metrics: screenMetrics

                anchors {
                    top: dockLogo.bottom
                    topMargin: dockWorkspaces.logoGap
                    horizontalCenter: parent.horizontalCenter
                }
            }
        }

        Item {
            id: dockLauncherRegion

            readonly property int contentInset: height
                > screenMetrics.dockItemGap * 2
                ? screenMetrics.dockItemGap : 0

            anchors.left: parent.left
            anchors.right: parent.right
            y: dockTopRegion.height
            height: screenMetrics.dockLauncherRegionHeight(
                dockTopRegion.height, dockSystemRegion.height)
            clip: true

            Launchers {
                id: dockLaunchers

                store: launcherStore
                controller: launcherController
                theme: shellTheme
                metrics: screenMetrics
                targetScreen: screenScope.modelData
                focusCoordinator: overlayFocusCoordinator
                anchors.fill: parent
                anchors.topMargin: dockLauncherRegion.contentInset
                anchors.bottomMargin: dockLauncherRegion.contentInset
                onEmptySpacePressed:
                    overlayFocusCoordinator.dockBackgroundInteracted()
            }
        }

        Flickable {
            id: dockSystemRegion

            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: screenMetrics.dockSystemRegionHeight(
                dockTopRegion.height, dockBottomContent.implicitHeight)
            contentWidth: width
            contentHeight: dockBottomContent.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            function keepBottomVisible(): void {
                if (!dragging && !moving)
                    contentY = Math.max(0, contentHeight - height)
            }

            onHeightChanged: Qt.callLater(keepBottomVisible)
            onContentHeightChanged: Qt.callLater(keepBottomVisible)

            Item {
                id: dockBottomContent

                width: dockSystemRegion.width
                implicitHeight: dockSystemTray.implicitHeight
                    + (dockSystemTray.implicitHeight > 0
                        ? dockSystemTray.clockGap : 0)
                    + dockBluetooth.implicitHeight
                    + dockNetwork.implicitHeight
                    + dockAudio.implicitHeight
                    + dockMonitor.implicitHeight
                    + dockPowerIdle.implicitHeight
                    + dockThemeToggle.implicitHeight
                    + dockShortcutsButton.implicitHeight
                    + screenMetrics.dockSystemControlGap * 6
                    + screenMetrics.dockGroupGap
                    + dockClock.implicitHeight
                    + screenMetrics.dockGroupGap
                    + powerMenu.implicitHeight
                    + screenMetrics.dockOuterInset
                height: implicitHeight

                MouseArea {
                    anchors.fill: parent
                    z: -1
                    acceptedButtons: Qt.LeftButton
                    onPressed:
                        overlayFocusCoordinator.dockBackgroundInteracted()
                }

                SystemTray {
                    id: dockSystemTray
                    theme: shellTheme
                    metrics: screenMetrics

                    anchors {
                        bottom: dockBluetooth.top
                        bottomMargin: implicitHeight > 0 ? clockGap : 0
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                Bluetooth {
                    id: dockBluetooth
                    controller: bluetoothAgentController
                    powerController: bluetoothPowerController
                    theme: shellTheme
                    metrics: screenMetrics
                    screenName: screenScope.modelData.name
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator
                    hardwareAvailable: bluetoothHardwareController.hardwareAvailable

                    anchors {
                        bottom: dockNetwork.top
                        bottomMargin: screenMetrics.dockSystemControlGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                Network {
                    id: dockNetwork
                    theme: shellTheme
                    metrics: screenMetrics
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator

                    anchors {
                        bottom: dockAudio.top
                        bottomMargin: screenMetrics.dockSystemControlGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                Audio {
                    id: dockAudio
                    theme: shellTheme
                    metrics: screenMetrics
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator

                    anchors {
                        bottom: dockMonitor.top
                        bottomMargin: screenMetrics.dockSystemControlGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                Monitor {
                    id: dockMonitor
                    theme: shellTheme
                    metrics: screenMetrics
                    textSizeController: root.globalTextSizeController
                    monitorController: root.globalMonitorController
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator

                    anchors {
                        bottom: dockPowerIdle.top
                        bottomMargin: screenMetrics.dockSystemControlGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                PowerIdle {
                    id: dockPowerIdle
                    controller: idleController
                    theme: shellTheme
                    metrics: screenMetrics
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator

                    anchors {
                        bottom: dockThemeToggle.top
                        bottomMargin: screenMetrics.dockSystemControlGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                ThemeToggle {
                    id: dockThemeToggle
                    controller: appearanceController
                    theme: shellTheme
                    metrics: screenMetrics

                    anchors {
                        bottom: dockShortcutsButton.top
                        bottomMargin: screenMetrics.dockSystemControlGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                ShortcutsButton {
                    id: dockShortcutsButton
                    controller: shortcuts
                    theme: shellTheme
                    metrics: screenMetrics

                    anchors {
                        bottom: dockClock.top
                        bottomMargin: screenMetrics.dockGroupGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                Clock {
                    id: dockClock
                    theme: shellTheme
                    metrics: screenMetrics
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator

                    anchors {
                        bottom: powerMenu.top
                        bottomMargin: screenMetrics.dockGroupGap
                        horizontalCenter: parent.horizontalCenter
                    }
                }

                PowerMenu {
                    id: powerMenu
                    theme: shellTheme
                    metrics: screenMetrics
                    powerActions: root.globalPowerActions
                    targetScreen: screenScope.modelData
                    focusCoordinator: overlayFocusCoordinator

                    anchors {
                        bottom: parent.bottom
                        bottomMargin: screenMetrics.dockOuterInset
                        horizontalCenter: parent.horizontalCenter
                    }
                }
            }

            VerticalScrollIndicator {
                view: dockSystemRegion
                metrics: screenMetrics
                theme: shellTheme
            }
        }

        TapHandler {
            parent: dockWindow.contentItem
            acceptedButtons: Qt.LeftButton
            gesturePolicy: TapHandler.DragThreshold
            onTapped: overlayFocusCoordinator.dockSurfaceInteracted()
        }
    }

    ShortcutsPanel {
        metrics: screenMetrics
        controller: shortcuts
        theme: shellTheme
        focusCoordinator: overlayFocusCoordinator
        targetScreen: screenScope.modelData
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: screenMetrics.dockWidth
    }

    SuperSpacePanel {
        metrics: screenMetrics
        controller: superSpace
        theme: shellTheme
        focusCoordinator: overlayFocusCoordinator
        targetScreen: screenScope.modelData
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: screenMetrics.dockWidth
    }

    BackgroundPickerPanel {
        metrics: screenMetrics
        controller: backgroundPicker
        theme: shellTheme
        focusCoordinator: overlayFocusCoordinator
        targetScreen: screenScope.modelData
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: screenMetrics.dockWidth
    }

    MonitorConfirmationPanel {
        controller: monitorController
        metrics: screenMetrics
        theme: shellTheme
        focusCoordinator: overlayFocusCoordinator
        targetScreen: screenScope.modelData
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: screenMetrics.dockWidth
    }

        }
    }
}
