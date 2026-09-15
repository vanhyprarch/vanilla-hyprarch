import QtQuick
import Quickshell

Item {
    id: root

    required property var theme
    required property var metrics
    property color textColor: root.theme.text
    readonly property int contentWidth: root.metrics.dockContentWidth
    property int iconSize: 28
    readonly property int itemSpacing: root.metrics.dockItemGap
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

    Item {
        id: calendarPopupAnchor

        parent: root.parent
        anchors {
            top: root.top
            horizontalCenter: root.horizontalCenter
        }
        width: root.metrics.dockSystemControlTarget
        height: root.iconSize
    }

    MonthCalendar {
        id: monthCalendar
        theme: root.theme
        metrics: root.metrics
        currentDate: clock.date
        popupAnchorItem: calendarPopupAnchor
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
