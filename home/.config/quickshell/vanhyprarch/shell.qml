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

    IdleController {
        id: idleController
    }

    BluetoothAgentController {
        id: bluetoothAgentController
    }

    BluetoothPowerController {
        id: bluetoothPowerController
    }

    readonly property var globalTextSizeController: textSizeController
    property int dockWidth: 56
    property int cornerRadius: 10
    property url logoSource: Qt.resolvedUrl("assets/logo.svg")
    property int logoSize: 40
    property int logoTopMargin: 12

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
            theme: shellTheme
            popupRadius: root.cornerRadius
            anchors.verticalCenter: parent.verticalCenter
            anchors.horizontalCenter: parent.horizontalCenter
        }

        PowerMenu {
            id: powerMenu
            theme: shellTheme
            popupRadius: root.cornerRadius

            anchors {
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
            }
        }

        Clock {
            id: dockClock
            theme: shellTheme
            popupAnchorItem: powerMenu
            popupRadius: root.cornerRadius

            anchors {
                bottom: powerMenu.top
                bottomMargin: dockClock.systemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        ThemeToggle {
            id: dockThemeToggle
            theme: shellTheme

            anchors {
                bottom: dockClock.top
                bottomMargin: dockClock.systemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        PowerIdle {
            id: dockPowerIdle
            controller: idleController
            theme: shellTheme
            popupRadius: root.cornerRadius

            anchors {
                bottom: dockThemeToggle.top
                bottomMargin: dockClock.systemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Monitor {
            id: dockMonitor
            theme: shellTheme
            popupRadius: root.cornerRadius

            anchors {
                bottom: dockPowerIdle.top
                bottomMargin: dockClock.systemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Audio {
            id: dockAudio
            theme: shellTheme
            popupRadius: root.cornerRadius

            anchors {
                bottom: dockMonitor.top
                bottomMargin: dockClock.systemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Network {
            id: dockNetwork
            theme: shellTheme
            popupRadius: root.cornerRadius

            anchors {
                bottom: dockAudio.top
                bottomMargin: dockClock.systemControlGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        Bluetooth {
            id: dockBluetooth
            controller: bluetoothAgentController
            powerController: bluetoothPowerController
            theme: shellTheme
            popupRadius: root.cornerRadius
            screenName: screenScope.modelData.name

            anchors {
                bottom: dockNetwork.top
                bottomMargin: dockClock.systemControlGap
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
        controller: shortcuts
        theme: shellTheme
        anchorItem: shortcutsAnchor
        screenName: screenScope.modelData.name
        screenWidth: screenScope.modelData.width
        screenHeight: screenScope.modelData.height
        dockWidth: root.dockWidth
        popupRadius: root.cornerRadius
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
