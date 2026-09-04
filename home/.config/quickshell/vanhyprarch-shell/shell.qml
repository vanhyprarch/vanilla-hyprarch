import QtQuick
import Quickshell

ShellRoot {
    property int dockWidth: 56
    property int borderThickness: 6
    property int cornerRadius: 18
    property color dockColor: "#FFF8F5"
    property color borderColor: "#FFF8F5"
    property color cornerMaskColor: "#FFF8F5"

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
    }
}
