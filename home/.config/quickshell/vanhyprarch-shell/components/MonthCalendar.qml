pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    property date currentDate
    property Item popupAnchorItem
    property int panelWidth: 252
    property int panelPadding: 12
    property int cellSize: 30
    property int popupRadius: 14
    property color backgroundColor: "#FFF8F5"
    property color textColor: "#5A3525"
    property color accentColor: "#8D4C2B"
    property color todayColor: "#FAEAE3"

    property int popupHorizontalGap: -16
    property int popupVerticalOffset: -2

    readonly property var monthNames: ["January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"]
    readonly property var weekdayNames: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    readonly property int currentYear: currentDate.getFullYear()
    readonly property int currentMonth: currentDate.getMonth()
    readonly property int daysInMonth: new Date(currentYear, currentMonth + 1, 0).getDate()
    readonly property date firstDay: new Date(currentYear, currentMonth, 1)
    readonly property int firstDayOffset: (firstDay.getDay() + 6) % 7
    readonly property real columnSpacing: Math.max(0, (panelWidth - panelPadding * 2 - cellSize * 7) / 6)

    anchor {
        item: root.popupAnchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: Math.max(0, (root.popupAnchorItem.parent.width - root.popupAnchorItem.width) / 2) + root.popupHorizontalGap
        margins.bottom: root.popupVerticalOffset
    }

    implicitWidth: panelWidth
    implicitHeight: content.implicitHeight + panelPadding * 2
    grabFocus: true
    color: "transparent"
    visible: false

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: 0
        topLeftRadius: 0
        topRightRadius: root.popupRadius
        bottomLeftRadius: 0
        bottomRightRadius: 0

        Column {
            id: content

            x: root.panelPadding
            y: root.panelPadding
            width: root.panelWidth - root.panelPadding * 2
            spacing: 6

            Text {
                width: parent.width
                height: 24
                text: root.monthNames[root.currentMonth] + " " + root.currentYear
                color: root.textColor
                font.pixelSize: 14
                font.weight: Font.Medium
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }

            Row {
                spacing: root.columnSpacing

                Repeater {
                    model: root.weekdayNames

                    Text {
                        required property string modelData

                        width: root.cellSize
                        height: 22
                        text: modelData
                        color: root.accentColor
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.NoWrap
                    }
                }
            }

            Grid {
                columns: 7
                rows: 6
                columnSpacing: root.columnSpacing

                Repeater {
                    model: 42

                    Rectangle {
                        id: dayCell

                        required property int index
                        readonly property int dayNumber: index - root.firstDayOffset + 1
                        readonly property bool inMonth: dayNumber >= 1 && dayNumber <= root.daysInMonth
                        readonly property bool isToday: inMonth && dayNumber === root.currentDate.getDate()

                        width: root.cellSize
                        height: root.cellSize
                        radius: 8
                        color: isToday ? root.todayColor : "transparent"

                        Text {
                            anchors.fill: parent
                            text: dayCell.inMonth ? dayCell.dayNumber : ""
                            color: dayCell.isToday ? root.accentColor : root.textColor
                            font.pixelSize: 12
                            font.weight: dayCell.isToday ? Font.Medium : Font.Normal
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.NoWrap
                        }
                    }
                }
            }
        }
    }
}
