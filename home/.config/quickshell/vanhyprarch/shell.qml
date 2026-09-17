//@ pragma UseQApplication
//@ pragma IconTheme Papirus

import QtQuick
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

    Shortcuts {
        id: shortcuts
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

    SuperSpace {
        id: superSpace
        installActions: installActions
        removeActions: removeActions
        powerActions: powerActions
    }

    IdleController {
        id: idleController
    }

    BluetoothAgentController {
        id: bluetoothAgentController
    }

    BluetoothPowerController {
        id: bluetoothPowerController
    }

    LauncherStore {
        id: launcherStore
    }

    readonly property var globalTextSizeController: textSizeController
    readonly property PowerActions globalPowerActions: powerActions
    readonly property int dockWidth: visualMetrics.dockWidth
    readonly property int cornerRadius: visualMetrics.legacyPopupRadius
    property url logoSource: Qt.resolvedUrl("assets/logo.svg")
    property int logoSize: 40
    readonly property int logoTopMargin: visualMetrics.dockOuterInset

    Variants {
        model: Quickshell.screens

        delegate: Scope {
            id: screenScope

            required property var modelData

    PanelWindow {
        screen: screenScope.modelData

        anchors {
            top: true
            bottom: true
            left: true
        }

        implicitWidth: dockWidth
        exclusiveZone: dockWidth
        color: "transparent"

        Rectangle {
            anchors.fill: parent
            color: shellTheme.background
        }

        Image {
            id: dockLogo

            anchors {
                top: parent.top
                horizontalCenter: parent.horizontalCenter
                topMargin: logoTopMargin
            }
            source: logoSource
            width: logoSize
            height: logoSize
            fillMode: Image.PreserveAspectFit
            smooth: true
        }

        Workspaces {
            id: dockWorkspaces
            theme: shellTheme

            anchors {
                top: dockLogo.bottom
                topMargin: dockWorkspaces.logoGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Launchers {
            store: launcherStore
            theme: shellTheme
            metrics: visualMetrics
            anchors.verticalCenter: parent.verticalCenter
            anchors.horizontalCenter: parent.horizontalCenter
        }

        PowerMenu {
            id: powerMenu
            theme: shellTheme
            metrics: visualMetrics
            powerActions: root.globalPowerActions

            anchors {
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
            }
        }

        Clock {
            id: dockClock
            theme: shellTheme
            metrics: visualMetrics

            anchors {
                bottom: powerMenu.top
                bottomMargin: visualMetrics.dockGroupGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        ThemeToggle {
            id: dockThemeToggle
            theme: shellTheme
            metrics: visualMetrics

            anchors {
                bottom: dockClock.top
                bottomMargin: visualMetrics.dockGroupGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        PowerIdle {
            id: dockPowerIdle
            controller: idleController
            theme: shellTheme
            metrics: visualMetrics

            anchors {
                bottom: dockThemeToggle.top
                bottomMargin: visualMetrics.dockSystemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Monitor {
            id: dockMonitor
            theme: shellTheme
            metrics: visualMetrics
            textSizeController: root.globalTextSizeController

            anchors {
                bottom: dockPowerIdle.top
                bottomMargin: visualMetrics.dockSystemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Audio {
            id: dockAudio
            theme: shellTheme
            metrics: visualMetrics

            anchors {
                bottom: dockMonitor.top
                bottomMargin: visualMetrics.dockSystemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Network {
            id: dockNetwork
            theme: shellTheme
            metrics: visualMetrics

            anchors {
                bottom: dockAudio.top
                bottomMargin: visualMetrics.dockSystemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Bluetooth {
            id: dockBluetooth
            controller: bluetoothAgentController
            powerController: bluetoothPowerController
            theme: shellTheme
            metrics: visualMetrics
            screenName: screenScope.modelData.name

            anchors {
                bottom: dockNetwork.top
                bottomMargin: visualMetrics.dockSystemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        SystemTray {
            id: dockSystemTray
            theme: shellTheme

            anchors {
                bottom: dockBluetooth.top
                bottomMargin: dockSystemTray.clockGap
                horizontalCenter: parent.horizontalCenter
            }
        }
    }

    ShortcutsPanel {
        metrics: visualMetrics
        controller: shortcuts
        theme: shellTheme
        anchorItem: shortcutsAnchor
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: root.dockWidth
        popupRadius: root.cornerRadius
    }

    SuperSpacePanel {
        metrics: visualMetrics
        controller: superSpace
        theme: shellTheme
        anchorItem: shortcutsAnchor
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: root.dockWidth
    }

    PanelWindow {
        screen: screenScope.modelData

        anchors {
            top: true
            bottom: true
            left: true
            right: true
        }

        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        focusable: false
        mask: Region {}

        Item {
            id: shortcutsAnchor

            anchors.fill: parent
        }
    }
        }
    }
}
