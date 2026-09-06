import QtQuick
import Quickshell

Item {
    id: root

    property Item popupAnchorItem
    property color iconColor: "#8D4C2B"
    property color textColor: "#5A3525"
    property int contentWidth: 48
    property int iconSize: 22
    property int itemSpacing: 4
    property int powerButtonGap: 8
    property int weekdayFontSize: 11
    property int dateFontSize: 13
    property int timeFontSize: 13

    readonly property var weekdays: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    implicitWidth: contentWidth
    implicitHeight: content.implicitHeight
    width: implicitWidth
    height: implicitHeight

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    MonthCalendar {
        id: monthCalendar
        currentDate: clock.date
        popupAnchorItem: root.popupAnchorItem
    }

    Column {
        id: content

        width: root.width
        spacing: root.itemSpacing

        Item {
            id: calendarIcon

            width: root.iconSize
            height: root.iconSize
            anchors.horizontalCenter: parent.horizontalCenter

            Rectangle {
                x: 1
                y: 3
                width: parent.width - 2
                height: parent.height - 3
                radius: 3
                color: "transparent"
                border.width: 1
                border.color: root.iconColor
            }

            Rectangle {
                x: 1
                y: 8
                width: parent.width - 2
                height: 1
                color: root.iconColor
            }

            Rectangle {
                x: 5
                width: 2
                height: 6
                radius: 1
                color: root.iconColor
            }

            Rectangle {
                x: parent.width - 7
                width: 2
                height: 6
                radius: 1
                color: root.iconColor
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: monthCalendar.visible = !monthCalendar.visible
            }
        }

        Text {
            width: parent.width
            height: root.weekdayFontSize + 4
            text: root.weekdays[clock.date.getDay()]
            color: root.textColor
            font.pixelSize: root.weekdayFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        Text {
            width: parent.width
            height: root.dateFontSize + 4
            text: Qt.formatDateTime(clock.date, "dd/MM")
            color: root.textColor
            font.pixelSize: root.dateFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        Text {
            width: parent.width
            height: root.timeFontSize + 4
            text: Qt.formatDateTime(clock.date, "HH:mm")
            color: root.textColor
            font.pixelSize: root.timeFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }
    }
}
