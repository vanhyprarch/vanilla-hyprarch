import QtQuick
import Quickshell
import "components"

ShellRoot {
    property int dockWidth: 56
    property int borderThickness: 10
    property int cornerRadius: 22
    property int innerShadowLayerWidth: 2
    property url logoSource: Qt.resolvedUrl("assets/logo.svg")
    property int logoSize: 40
    property int logoTopMargin: 12
    property color dockColor: "#FFF8F5"
    property color borderColor: "#FFF8F5"
    property color cornerMaskColor: "#FFF8F5"
    property color innerShadow1Color: "#50000000"
    property color innerShadow2Color: "#3A000000"
    property color innerShadow3Color: "#28000000"
    property color innerShadow4Color: "#18000000"
    property color innerShadow5Color: "#0C000000"
    property color innerShadow6Color: "#06000000"
    property color innerShadow7Color: "#03000000"

    PanelWindow {
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
            color: dockColor
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

            anchors {
                top: dockLogo.bottom
                topMargin: dockWorkspaces.logoGap
                horizontalCenter: parent.horizontalCenter
            }
        }

        PowerMenu {
            id: powerMenu

            anchors {
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
            }
        }

        Clock {
            id: dockClock
            popupAnchorItem: powerMenu

            anchors {
                bottom: powerMenu.top
                bottomMargin: dockClock.powerButtonGap
                horizontalCenter: parent.horizontalCenter
            }
        }
    }

    PanelWindow {
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
            color: borderColor
        }

        Rectangle {
            height: borderThickness
            anchors {
                bottom: parent.bottom
                left: parent.left
                right: parent.right
                leftMargin: dockWidth
            }
            color: borderColor
        }

        Rectangle {
            width: borderThickness
            anchors {
                top: parent.top
                bottom: parent.bottom
                right: parent.right
            }
            color: borderColor
        }

        Canvas {
            width: cornerRadius
            height: cornerRadius
            anchors.top: parent.top
            anchors.topMargin: borderThickness
            anchors.left: parent.left
            anchors.leftMargin: dockWidth

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = cornerMaskColor
                context.beginPath()
                context.moveTo(0, 0)
                context.lineTo(width, 0)
                context.arc(width, height, cornerRadius, -Math.PI / 2, -Math.PI, true)
                context.closePath()
                context.fill()
            }
        }

        Canvas {
            width: cornerRadius
            height: cornerRadius
            anchors.top: parent.top
            anchors.topMargin: borderThickness
            anchors.right: parent.right
            anchors.rightMargin: borderThickness

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = cornerMaskColor
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
            width: cornerRadius
            height: cornerRadius
            anchors.bottom: parent.bottom
            anchors.bottomMargin: borderThickness
            anchors.left: parent.left
            anchors.leftMargin: dockWidth

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = cornerMaskColor
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
            width: cornerRadius
            height: cornerRadius
            anchors.bottom: parent.bottom
            anchors.bottomMargin: borderThickness
            anchors.right: parent.right
            anchors.rightMargin: borderThickness

            onPaint: {
                const context = getContext("2d")
                context.clearRect(0, 0, width, height)
                context.fillStyle = cornerMaskColor
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
            radius: cornerRadius
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow1Color
        }

        Rectangle {
            x: dockWidth + innerShadowLayerWidth
            y: borderThickness + innerShadowLayerWidth
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 2)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 2)
            radius: cornerRadius - innerShadowLayerWidth
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow2Color
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 2)
            y: borderThickness + (innerShadowLayerWidth * 2)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 4)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 4)
            radius: cornerRadius - (innerShadowLayerWidth * 2)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow3Color
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 3)
            y: borderThickness + (innerShadowLayerWidth * 3)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 6)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 6)
            radius: cornerRadius - (innerShadowLayerWidth * 3)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow4Color
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 4)
            y: borderThickness + (innerShadowLayerWidth * 4)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 8)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 8)
            radius: cornerRadius - (innerShadowLayerWidth * 4)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow5Color
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 5)
            y: borderThickness + (innerShadowLayerWidth * 5)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 10)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 10)
            radius: cornerRadius - (innerShadowLayerWidth * 5)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow6Color
        }

        Rectangle {
            x: dockWidth + (innerShadowLayerWidth * 6)
            y: borderThickness + (innerShadowLayerWidth * 6)
            width: parent.width - dockWidth - borderThickness - (innerShadowLayerWidth * 12)
            height: parent.height - (borderThickness * 2) - (innerShadowLayerWidth * 12)
            radius: cornerRadius - (innerShadowLayerWidth * 6)
            color: "transparent"
            border.width: innerShadowLayerWidth
            border.color: innerShadow7Color
        }
    }
}
