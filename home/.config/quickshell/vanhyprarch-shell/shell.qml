//@ pragma UseQApplication
//@ pragma IconTheme Papirus

import QtQuick
import Quickshell
import Quickshell.Io
import "components"

ShellRoot {
    id: root

    IpcHandler {
        target: "vanhyprarch.shell"

        function ping(): string {
            return "pong"
        }
    }

    Theme {
        id: shellTheme
    }

    property int dockWidth: 56
    property int borderThickness: 10
    property int cornerRadius: 10
    property int innerShadowLayerWidth: 2
    property url logoSource: Qt.resolvedUrl("assets/logo.svg")
    property int logoSize: 40
    property int logoTopMargin: 12

    function shadowRadius(layerIndex: int): int {
        return Math.max(0, cornerRadius - innerShadowLayerWidth * layerIndex)
    }

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

        Monitor {
            id: dockMonitor
            theme: shellTheme
            popupRadius: root.cornerRadius

            anchors {
                bottom: dockThemeToggle.top
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

        SystemTray {
            id: dockSystemTray
            theme: shellTheme

            anchors {
                bottom: dockNetwork.top
                bottomMargin: dockSystemTray.clockGap
                horizontalCenter: parent.horizontalCenter
            }
        }
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

        Rectangle {
            height: borderThickness
            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                leftMargin: dockWidth
            }
            color: shellTheme.background
        }

        Rectangle {
            height: borderThickness
            anchors {
                bottom: parent.bottom
                left: parent.left
                right: parent.right
                leftMargin: dockWidth
            }
            color: shellTheme.background
        }

        Rectangle {
            width: borderThickness
            anchors {
                top: parent.top
                bottom: parent.bottom
                right: parent.right
            }
            color: shellTheme.background
        }

        Connections {
            target: shellTheme

            function onBackgroundChanged(): void {
                topLeftCorner.requestPaint()
                topRightCorner.requestPaint()
                bottomLeftCorner.requestPaint()
                bottomRightCorner.requestPaint()
            }
        }

        Canvas {
            id: topLeftCorner

            width: cornerRadius
            height: cornerRadius
            anchors.top: parent.top
            anchors.topMargin: borderThickness
            anchors.left: parent.left
            anchors.leftMargin: dockWidth

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = shellTheme.background
                context.beginPath()
                context.moveTo(0, 0)
                context.lineTo(width, 0)
                context.arc(width, height, cornerRadius, -Math.PI / 2, -Math.PI, true)
                context.closePath()
                context.fill()
            }
        }

        Canvas {
            id: topRightCorner

            width: cornerRadius
            height: cornerRadius
            anchors.top: parent.top
            anchors.topMargin: borderThickness
            anchors.right: parent.right
            anchors.rightMargin: borderThickness

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = shellTheme.background
                context.beginPath()
                context.moveTo(0, 0)
                context.lineTo(width, 0)
                context.lineTo(width, height)
                context.arc(0, height, cornerRadius, 0, -Math.PI / 2, true)
                context.closePath()
                context.fill()
            }
        }

        Canvas {
            id: bottomLeftCorner

            width: cornerRadius
            height: cornerRadius
            anchors.bottom: parent.bottom
            anchors.bottomMargin: borderThickness
            anchors.left: parent.left
            anchors.leftMargin: dockWidth

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = shellTheme.background
                context.beginPath()
                context.moveTo(0, 0)
                context.lineTo(0, height)
                context.lineTo(width, height)
                context.arc(width, 0, cornerRadius, Math.PI / 2, Math.PI, false)
                context.closePath()
                context.fill()
            }
        }

        Canvas {
            id: bottomRightCorner

            width: cornerRadius
            height: cornerRadius
            anchors.bottom: parent.bottom
            anchors.bottomMargin: borderThickness
            anchors.right: parent.right
            anchors.rightMargin: borderThickness

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = shellTheme.background
                context.beginPath()
                context.moveTo(width, 0)
                context.lineTo(width, height)
                context.lineTo(0, height)
                context.arc(0, 0, cornerRadius, Math.PI / 2, 0, true)
                context.closePath()
                context.fill()
            }
        }

        Rectangle {
            x: dockWidth
            y: borderThickness
            width: parent.width - dockWidth - borderThickness
            height: parent.height - (borderThickness * 2)
            radius: shadowRadius(0)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowDarkest
        }

        Rectangle {
            x: dockWidth + innerShadowLayerWidth
            y: borderThickness + innerShadowLayerWidth
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 2)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 2)
            radius: shadowRadius(1)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowDarker
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 2)
            y: borderThickness + (innerShadowLayerWidth * 2)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 4)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 4)
            radius: shadowRadius(2)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowDark
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 3)
            y: borderThickness + (innerShadowLayerWidth * 3)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 6)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 6)
            radius: shadowRadius(3)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowMedium
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 4)
            y: borderThickness + (innerShadowLayerWidth * 4)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 8)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 8)
            radius: shadowRadius(4)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowLight
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 5)
            y: borderThickness + (innerShadowLayerWidth * 5)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 10)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 10)
            radius: shadowRadius(5)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowLighter
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 6)
            y: borderThickness + (innerShadowLayerWidth * 6)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 12)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 12)
            radius: shadowRadius(6)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: shellTheme.innerShadowLightest
        }
    }
        }
    }
}
