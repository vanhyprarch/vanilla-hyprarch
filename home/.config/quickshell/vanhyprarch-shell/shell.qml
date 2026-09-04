import QtQuick
import Quickshell

ShellRoot {
    property int dockWidth: 48
    property int borderThickness: 2
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
            topLeftRadius: cornerRadius
            bottomLeftRadius: cornerRadius
            topRightRadius: 0
            bottomRightRadius: 0
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

        Canvas {
            width: cornerRadius
            height: cornerRadius
            anchors.top: parent.top
            anchors.left: parent.left

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
            anchors.right: parent.right

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
            anchors.left: parent.left

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
            anchors.right: parent.right

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
            anchors.fill: parent
            color: "transparent"
            border.width: borderThickness
            border.color: borderColor
            radius: cornerRadius
        }
    }
}
