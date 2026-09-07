pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

PopupWindow {
    id: root

    required property var controller
    required property var theme
    required property Item anchorItem
    required property string screenName
    required property int screenWidth
    required property int screenHeight
    required property int dockWidth
    required property int popupRadius

    readonly property bool activeForScreen: controller.activeScreenName === screenName
    property int panelWidth: Math.max(320,
        Math.min(900, screenWidth - dockWidth - 48))
    property int panelHeight: Math.max(280,
        Math.min(900, screenHeight - 64))
    property int panelPadding: 18
    property int searchHeight: 44
    property int rowHeight: 48
    property int categoryHeight: 28

    function syncVisibility(): void {
        const shouldShow = controller.isOpen && activeForScreen
        if (visible !== shouldShow)
            visible = shouldShow
    }

    anchor {
        item: root.anchorItem
        edges: Edges.Right | Edges.Bottom
        gravity: Edges.Right | Edges.Top
        margins.right: Math.max(0,
            ((root.anchorItem.parent ? root.anchorItem.parent.width : root.anchorItem.width)
                - root.anchorItem.width) / 2) - 8
        margins.bottom: -16
    }
    implicitWidth: panelWidth
    implicitHeight: panelHeight
    color: "transparent"
    grabFocus: true
    visible: false

    Component.onCompleted: syncVisibility()

    onVisibleChanged: {
        if (visible) {
            searchInput.text = root.controller.searchText
            shortcutsView.currentIndex = shortcutsView.count > 0 ? 0 : -1
            shortcutsView.positionViewAtBeginning()
            Qt.callLater(function() { searchInput.forceActiveFocus() })
        } else if (root.controller.isOpen && root.activeForScreen) {
            root.controller.close()
        }
    }

    Connections {
        target: root.controller

        function onIsOpenChanged(): void {
            root.syncVisibility()
        }

        function onActiveScreenNameChanged(): void {
            root.syncVisibility()
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: root.popupRadius
        color: root.theme.background
        border.width: 1
        border.color: root.theme.accent

        Text {
            id: titleText

            anchors {
                top: parent.top
                left: parent.left
                right: escapeHint.left
                topMargin: root.panelPadding
                leftMargin: root.panelPadding
                rightMargin: 12
            }
            height: 28
            text: "Keyboard shortcuts"
            textFormat: Text.PlainText
            color: root.theme.text
            font.pixelSize: 20
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            id: escapeHint

            anchors {
                top: titleText.top
                right: parent.right
                rightMargin: root.panelPadding
            }
            height: titleText.height
            text: "Esc to close"
            textFormat: Text.PlainText
            color: root.theme.text
            opacity: 0.65
            font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter
        }

        Rectangle {
            id: searchBox

            anchors {
                top: titleText.bottom
                left: parent.left
                right: parent.right
                topMargin: 14
                leftMargin: root.panelPadding
                rightMargin: root.panelPadding
            }
            height: root.searchHeight
            radius: root.popupRadius
            color: root.theme.surface
            border.width: searchInput.activeFocus ? 2 : 1
            border.color: root.theme.accent

            Text {
                anchors {
                    left: parent.left
                    leftMargin: 14
                    verticalCenter: parent.verticalCenter
                }
                visible: searchInput.text.length === 0
                text: "Search shortcuts"
                textFormat: Text.PlainText
                color: root.theme.text
                opacity: 0.55
                font.pixelSize: 14
            }

            TextInput {
                id: searchInput

                anchors {
                    fill: parent
                    leftMargin: 14
                    rightMargin: 14
                }
                color: root.theme.text
                selectionColor: root.theme.accent
                selectedTextColor: root.theme.background
                font.pixelSize: 14
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                Keys.priority: Keys.BeforeItem

                onTextChanged: {
                    if (root.controller.searchText !== text)
                        root.controller.searchText = text
                    shortcutsView.currentIndex = shortcutsView.count > 0 ? 0 : -1
                    shortcutsView.positionViewAtBeginning()
                }

                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape) {
                        root.controller.close()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up) {
                        shortcutsView.moveSelection(-1)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Down) {
                        shortcutsView.moveSelection(1)
                        event.accepted = true
                    } else if (event.key === Qt.Key_PageUp) {
                        shortcutsView.moveSelection(-shortcutsView.pageStep())
                        event.accepted = true
                    } else if (event.key === Qt.Key_PageDown) {
                        shortcutsView.moveSelection(shortcutsView.pageStep())
                        event.accepted = true
                    }
                }
            }
        }

        ListView {
            id: shortcutsView

            function pageStep(): int {
                return Math.max(1, Math.floor(height / root.rowHeight) - 1)
            }

            function moveSelection(offset: int): void {
                if (count === 0)
                    return
                const start = currentIndex < 0 ? 0 : currentIndex
                currentIndex = Math.max(0, Math.min(count - 1, start + offset))
                positionViewAtIndex(currentIndex, ListView.Contain)
            }

            anchors {
                top: searchBox.bottom
                bottom: resultCount.top
                left: parent.left
                right: parent.right
                topMargin: 12
                bottomMargin: 8
                leftMargin: root.panelPadding
                rightMargin: root.panelPadding
            }
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: root.controller.filteredEntries
            visible: !root.controller.loading
                && root.controller.errorMessage === ""

            onCountChanged: {
                if (count === 0)
                    currentIndex = -1
                else if (currentIndex < 0 || currentIndex >= count)
                    currentIndex = 0
            }

            delegate: Item {
                id: shortcutDelegate

                required property var modelData
                required property int index

                width: shortcutsView.width
                height: root.rowHeight
                    + (modelData.showCategory ? root.categoryHeight : 0)

                Text {
                    visible: shortcutDelegate.modelData.showCategory
                    width: parent.width
                    height: root.categoryHeight
                    text: shortcutDelegate.modelData.category
                    textFormat: Text.PlainText
                    color: root.theme.accent
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    verticalAlignment: Text.AlignVCenter
                }

                Rectangle {
                    id: shortcutRow

                    anchors {
                        left: parent.left
                        right: parent.right
                        bottom: parent.bottom
                    }
                    height: root.rowHeight
                    radius: root.popupRadius
                    color: shortcutDelegate.index === shortcutsView.currentIndex
                        || rowMouse.containsMouse
                        ? root.theme.hover : "transparent"

                    Text {
                        anchors {
                            left: parent.left
                            right: chordText.left
                            leftMargin: 12
                            rightMargin: 16
                            verticalCenter: parent.verticalCenter
                        }
                        text: shortcutDelegate.modelData.action
                        textFormat: Text.PlainText
                        color: root.theme.text
                        font.pixelSize: 14
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                    }

                    Text {
                        id: chordText

                        anchors {
                            right: parent.right
                            rightMargin: 12
                            verticalCenter: parent.verticalCenter
                        }
                        width: Math.min(430, shortcutRow.width * 0.56)
                        text: shortcutDelegate.modelData.chords.join("   •   ")
                        textFormat: Text.PlainText
                        color: root.theme.text
                        opacity: 0.82
                        font.pixelSize: 13
                        horizontalAlignment: Text.AlignRight
                        elide: Text.ElideLeft
                        wrapMode: Text.NoWrap
                    }

                    MouseArea {
                        id: rowMouse

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: shortcutsView.currentIndex = shortcutDelegate.index
                    }
                }
            }
        }

        Text {
            anchors {
                fill: shortcutsView
                margins: 24
            }
            visible: root.controller.loading
                || root.controller.errorMessage !== ""
                || root.controller.filteredEntries.length === 0
            text: root.controller.loading ? "Loading shortcuts…"
                : root.controller.errorMessage !== ""
                    ? root.controller.errorMessage : "No matching shortcuts"
            textFormat: Text.PlainText
            color: root.theme.text
            opacity: 0.72
            font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
        }

        Text {
            id: resultCount

            anchors {
                bottom: parent.bottom
                left: parent.left
                right: parent.right
                bottomMargin: 10
                leftMargin: root.panelPadding
                rightMargin: root.panelPadding
            }
            height: 20
            text: root.controller.loading ? ""
                : root.controller.filteredEntries.length + " shortcuts"
            textFormat: Text.PlainText
            color: root.theme.text
            opacity: 0.55
            font.pixelSize: 11
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter
        }
    }
}
