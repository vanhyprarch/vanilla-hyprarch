import QtQuick
import Quickshell

Item {
    id: root

    property Item popupAnchorItem
    property color textColor: "#5A3525"
    property int contentWidth: 48
    property int iconSize: 28
    property int itemSpacing: 4
    property int systemControlGap: 8
    required property int popupRadius
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
        popupRadius: root.popupRadius
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

            Image {
                anchors.fill: parent
                source: "file:///usr/share/icons/Papirus/22x22/apps/calendar.svg"
                sourceSize: Qt.size(root.iconSize, root.iconSize)
                fillMode: Image.PreserveAspectFit
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
