pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

DockPopup {
    id: root

    required property var theme
    property date currentDate
    property int monthOffset: 0
    readonly property int calendarColumnCount: 7
    readonly property int calendarRowCount: 6
    readonly property int calendarCellCount:
        calendarColumnCount * calendarRowCount
    readonly property int calendarCellSize: root.metrics.scaled(30)
    readonly property int weekdayCellHeight: root.metrics.scaled(22)
    readonly property int calendarColumnSpacing: root.metrics.scaled(3)
    readonly property int navigationButtonSize: root.metrics.textFieldHeight
    readonly property int calendarPanelWidth:
        root.metrics.panelPadding * 2
        + root.calendarCellSize * root.calendarColumnCount
        + root.calendarColumnSpacing * (root.calendarColumnCount - 1)

    readonly property var monthNames: ["January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"]
    readonly property var weekdayNames: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    readonly property date displayedDate: new Date(currentDate.getFullYear(), currentDate.getMonth() + monthOffset, 1)
    readonly property int displayedYear: displayedDate.getFullYear()
    readonly property int displayedMonth: displayedDate.getMonth()
    readonly property int daysInMonth: new Date(displayedYear, displayedMonth + 1, 0).getDate()
    readonly property date firstDay: new Date(displayedYear, displayedMonth, 1)
    readonly property int firstDayOffset: (firstDay.getDay() + 6) % 7
    panelWidth: root.calendarPanelWidth
    implicitHeight: content.implicitHeight + root.metrics.panelPadding * 2

    onVisibleChanged: {
        if (visible)
            root.monthOffset = 0
    }

    component NavigationButton: Rectangle {
        id: navigationButton

        required property string label
        signal activated()

        width: root.navigationButtonSize
        height: root.navigationButtonSize
        radius: root.metrics.rowRadius
        color: navigationMouse.pressed
            ? root.theme.pressedFill
            : navigationMouse.containsMouse
                ? root.theme.hoverFill : root.theme.normalFill

        Text {
            anchors.fill: parent
            text: navigationButton.label
            color: root.theme.text
            font.pixelSize: root.metrics.heroIconSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
        }

        MouseArea {
            id: navigationMouse

            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: navigationButton.activated()
        }
    }

    PanelSurface {
        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme

        Column {
            id: content

            width: parent.width
            spacing: root.metrics.contentGap

            Item {
                width: parent.width
                height: root.navigationButtonSize

                NavigationButton {
                    anchors.left: parent.left
                    label: "‹"
                    onActivated: root.monthOffset -= 1
                }

                Text {
                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: root.navigationButtonSize
                        rightMargin: root.navigationButtonSize
                        top: parent.top
                        bottom: parent.bottom
                    }
                    text: root.monthNames[root.displayedMonth] + " " + root.displayedYear
                    color: root.theme.text
                    font.pixelSize: root.metrics.panelTitleFontSize
                    font.weight: root.metrics.panelTitleFontWeight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.NoWrap
                }

                NavigationButton {
                    anchors.right: parent.right
                    label: "›"
                    onActivated: root.monthOffset += 1
                }
            }

            Row {
                spacing: root.calendarColumnSpacing

                Repeater {
                    model: root.weekdayNames

                    Text {
                        required property string modelData

                        width: root.calendarCellSize
                        height: root.weekdayCellHeight
                        text: modelData
                        color: root.theme.textMuted
                        font.pixelSize: root.metrics.sectionHeadingFontSize
                        font.weight: root.metrics.sectionHeadingFontWeight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.NoWrap
                    }
                }
            }

            Grid {
                columns: root.calendarColumnCount
                rows: root.calendarRowCount
                columnSpacing: root.calendarColumnSpacing

                Repeater {
                    model: root.calendarCellCount

                    Rectangle {
                        id: dayCell

                        required property int index
                        readonly property int dayNumber: index - root.firstDayOffset + 1
                        readonly property bool inMonth: dayNumber >= 1 && dayNumber <= root.daysInMonth
                        readonly property bool isToday: inMonth
                            && root.displayedYear === root.currentDate.getFullYear()
                            && root.displayedMonth === root.currentDate.getMonth()
                            && dayNumber === root.currentDate.getDate()

                        width: root.calendarCellSize
                        height: root.calendarCellSize
                        radius: root.metrics.rowRadius
                        color: isToday
                            ? root.theme.activeFill : "transparent"

                        Text {
                            anchors.fill: parent
                            text: dayCell.inMonth ? dayCell.dayNumber : ""
                            color: root.theme.text
                            font.pixelSize: root.metrics.bodyFontSize
                            font.weight: dayCell.isToday
                                ? root.metrics.informationLabelFontWeight
                                : root.metrics.informationValueFontWeight
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
