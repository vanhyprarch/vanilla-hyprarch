pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property var theme
    property date currentDate
    property int monthOffset: 0
    property Item popupAnchorItem
    property int panelWidth: 252
    property int panelPadding: 12
    property int cellSize: 30
    required property int popupRadius
    property color backgroundColor: root.theme.background
    property color textColor: root.theme.text
    property color accentColor: root.theme.accent
    property color todayColor: root.theme.surface

    property int popupHorizontalGap: -16
    property int popupVerticalOffset: -2

    readonly property var monthNames: ["January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"]
    readonly property var weekdayNames: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    readonly property date displayedDate: new Date(currentDate.getFullYear(), currentDate.getMonth() + monthOffset, 1)
    readonly property int displayedYear: displayedDate.getFullYear()
    readonly property int displayedMonth: displayedDate.getMonth()
    readonly property int daysInMonth: new Date(displayedYear, displayedMonth + 1, 0).getDate()
    readonly property date firstDay: new Date(displayedYear, displayedMonth, 1)
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

    onVisibleChanged: {
        if (visible)
            root.monthOffset = 0
    }

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

            Item {
                width: parent.width
                height: 24

                Item {
                    id: previousMonth

                    anchors.left: parent.left
                    width: 30
                    height: parent.height

                    Text {
                        anchors.centerIn: parent
                        text: "‹"
                        color: previousMouse.containsMouse ? root.accentColor : root.textColor
                        font.pixelSize: 24
                    }

                    MouseArea {
                        id: previousMouse

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.monthOffset -= 1
                    }
                }

                Text {
                    anchors {
                        left: previousMonth.right
                        right: nextMonth.left
                        top: parent.top
                        bottom: parent.bottom
                    }
                    text: root.monthNames[root.displayedMonth] + " " + root.displayedYear
                    color: root.textColor
                    font.pixelSize: 14
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.NoWrap
                }

                Item {
                    id: nextMonth

                    anchors.right: parent.right
                    width: 30
                    height: parent.height

                    Text {
                        anchors.centerIn: parent
                        text: "›"
                        color: nextMouse.containsMouse ? root.accentColor : root.textColor
                        font.pixelSize: 24
                    }

                    MouseArea {
                        id: nextMouse

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.monthOffset += 1
                    }
                }
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
                        readonly property bool isToday: inMonth
                            && root.displayedYear === root.currentDate.getFullYear()
                            && root.displayedMonth === root.currentDate.getMonth()
                            && dayNumber === root.currentDate.getDate()

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
