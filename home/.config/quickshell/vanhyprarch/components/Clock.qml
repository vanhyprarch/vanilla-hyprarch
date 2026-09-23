import QtQuick
import Quickshell

Item {
    id: root

    required property var theme
    required property var metrics
    required property var targetScreen
    required property var focusCoordinator
    property color textColor: root.theme.text
    readonly property int contentWidth: root.metrics.dockContentWidth
    readonly property int iconSize: root.metrics.applicationLauncherIconSize
    readonly property int itemSpacing: root.metrics.dockItemGap
    readonly property int weekdayFontSize: root.metrics.fitted(11, 10)
    readonly property int dateFontSize: root.metrics.dockWorkspaceFontSize
    readonly property int timeFontSize: root.metrics.dockWorkspaceFontSize

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
        targetScreen: root.targetScreen
        focusCoordinator: root.focusCoordinator
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
                onClicked: root.focusCoordinator.toggleDockWindow(monthCalendar)
            }
        }

        Text {
            width: parent.width
            height: root.weekdayFontSize + root.metrics.dockClockLinePadding
            text: root.weekdays[clock.date.getDay()]
            color: root.textColor
            font.pixelSize: root.weekdayFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        Text {
            width: parent.width
            height: root.dateFontSize + root.metrics.dockClockLinePadding
            text: Qt.formatDateTime(clock.date, "dd/MM")
            color: root.textColor
            font.pixelSize: root.dateFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        Text {
            width: parent.width
            height: root.timeFontSize + root.metrics.dockClockLinePadding
            text: Qt.formatDateTime(clock.date, "HH:mm")
            color: root.textColor
            font.pixelSize: root.timeFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }
    }
}
