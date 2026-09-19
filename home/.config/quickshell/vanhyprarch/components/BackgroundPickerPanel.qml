pragma ComponentBehavior: Bound

import QtQuick
import "BackgroundPickerLayout.js" as PickerLayout

CenteredOverlay {
    id: root

    required property BackgroundPickerController controller
    required property var metrics
    required property var theme
    required property string screenName
    required property int dockWidth

    readonly property bool activeForScreen:
        controller.activeScreenName === screenName
    readonly property int panelWidth: Math.max(1,
        Math.min(metrics.backgroundPickerMaximumWidth,
            screenWidth - dockWidth - metrics.scaled(48)))
    readonly property int panelHeight: Math.max(1,
        Math.min(metrics.backgroundPickerMaximumHeight,
            screenHeight - metrics.scaled(64)))
    readonly property int previewWidth: PickerLayout.previewWidth(panelWidth,
        metrics.scaled(80), metrics.backgroundPreviewMaximumWidth,
        panelHeight, metrics.backgroundPickerVerticalChrome)
    readonly property int previewHeight:
        PickerLayout.previewHeight(previewWidth)
    readonly property int adjacentWidth: Math.min(
        metrics.backgroundPreviewAdjacentWidth,
        Math.round(previewWidth * 0.64))
    readonly property int adjacentHeight:
        PickerLayout.previewHeight(adjacentWidth)
    readonly property int cardStep: PickerLayout.cardStep(previewWidth,
        metrics.backgroundPreviewCardStep, metrics.scaled(120))

    persistentLeftInset: dockWidth
    implicitWidth: panelWidth
    implicitHeight: panelHeight
    color: "transparent"
    visible: false

    function syncVisibility(): void {
        const shouldShow = controller.isOpen && activeForScreen
        if (visible !== shouldShow)
            visible = shouldShow
    }

    function syncCurrentIndex(): void {
        if (carousel.currentIndex !== controller.currentIndex) {
            carousel.currentIndex = controller.currentIndex
            if (controller.currentIndex >= 0)
                carousel.positionViewAtIndex(controller.currentIndex,
                    ListView.Center)
        }
    }

    function handleKey(event): void {
        if (event.key === Qt.Key_Escape) {
            controller.close()
            event.accepted = true
        } else if (event.key === Qt.Key_Left) {
            controller.move(-1)
            event.accepted = true
        } else if (event.key === Qt.Key_Right) {
            controller.move(1)
            event.accepted = true
        } else if (event.key === Qt.Key_Return
                || event.key === Qt.Key_Enter) {
            controller.applyCandidate()
            event.accepted = true
        }
    }

    onDismissed: controller.close()
    Component.onCompleted: syncVisibility()

    onVisibleChanged: {
        if (visible) {
            syncCurrentIndex()
            Qt.callLater(function() { keyboardScope.forceActiveFocus() })
        } else if (controller.isOpen && activeForScreen) {
            controller.close()
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

        function onCurrentIndexChanged(): void {
            root.syncCurrentIndex()
        }

        function onCatalogChanged(): void {
            Qt.callLater(root.syncCurrentIndex)
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: root.metrics.panelRadius
        color: root.theme.background
        border.width: root.metrics.panelOutlineThickness
        border.color: root.theme.panelOutline

        FocusScope {
            id: keyboardScope

            anchors.fill: parent
            focus: true
            Keys.priority: Keys.BeforeItem
            Keys.onPressed: event => root.handleKey(event)

            Text {
                id: title

                anchors {
                    top: parent.top
                    left: parent.left
                    topMargin: root.metrics.overlayPadding
                    leftMargin: root.metrics.overlayPadding
                }
                text: "Choose background · " + root.controller.modeLabel
                textFormat: Text.PlainText
                color: root.theme.text
                font.pixelSize: root.metrics.overlayFontSize
                font.weight: root.metrics.panelTitleFontWeight
            }

            Rectangle {
                id: closeAction

                anchors {
                    top: title.top
                    right: parent.right
                    rightMargin: root.metrics.overlayPadding
                }
                width: closeLabel.implicitWidth
                    + root.metrics.rowSidePadding * 2
                height: title.height
                color: closeMouse.pressed ? root.theme.pressedFill
                    : closeMouse.containsMouse ? root.theme.hoverFill
                        : "transparent"

                Text {
                    id: closeLabel

                    anchors.centerIn: parent
                    text: "Close · Esc"
                    textFormat: Text.PlainText
                    color: closeMouse.containsMouse
                        ? root.theme.text : root.theme.textMuted
                    font.pixelSize: root.metrics.detailFontSize
                }

                MouseArea {
                    id: closeMouse

                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.controller.close()
                }
            }

            ListView {
                id: carousel

                anchors {
                    top: title.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.metrics.sectionGap
                    leftMargin: root.metrics.overlayPadding
                    rightMargin: root.metrics.overlayPadding
                }
                height: root.previewHeight + root.metrics.scaled(18)
                model: root.controller.catalog
                orientation: ListView.Horizontal
                clip: true
                interactive: count > 1 && !root.controller.applying
                boundsBehavior: Flickable.StopAtBounds
                flickDeceleration: 10000
                snapMode: ListView.SnapToItem
                highlightRangeMode: ListView.StrictlyEnforceRange
                preferredHighlightBegin: width / 2 - root.cardStep / 2
                preferredHighlightEnd: width / 2 + root.cardStep / 2
                cacheBuffer: root.cardStep * 3
                reuseItems: true
                currentIndex: -1

                header: Item {
                    width: Math.max(0, (carousel.width - root.cardStep) / 2)
                    height: 1
                }

                footer: Item {
                    width: Math.max(0, (carousel.width - root.cardStep) / 2)
                    height: 1
                }

                onCurrentIndexChanged: {
                    if (currentIndex >= 0
                            && root.controller.currentIndex !== currentIndex)
                        root.controller.select(currentIndex)
                }

                onMovementEnded: {
                    const centered = indexAt(contentX + width / 2, height / 2)
                    if (centered >= 0)
                        currentIndex = centered
                }

                delegate: Item {
                    id: cardSlot

                    required property int index
                    required property var modelData

                    readonly property bool navigationCurrent:
                        index === root.controller.currentIndex
                    readonly property bool applied:
                        modelData.path === root.controller.appliedPath
                    readonly property bool sourceActive:
                        PickerLayout.sourceActive(index,
                            root.controller.currentIndex,
                            root.controller.catalog.length, 2)
                    readonly property int visualWidth: navigationCurrent
                        ? root.previewWidth : root.adjacentWidth
                    readonly property int visualHeight: navigationCurrent
                        ? root.previewHeight : root.adjacentHeight

                    width: root.cardStep
                    height: carousel.height
                    z: navigationCurrent ? 100 : 10 - Math.abs(
                        index - root.controller.currentIndex)

                    Rectangle {
                        id: previewCard

                        x: Math.round((parent.width - width) / 2)
                        anchors.verticalCenter: parent.verticalCenter
                        width: cardSlot.visualWidth
                        height: cardSlot.visualHeight
                        radius: 0
                        color: root.theme.surface
                        opacity: cardSlot.navigationCurrent ? 1.0 : 0.76
                        border.width: cardSlot.navigationCurrent
                            ? root.metrics.backgroundPreviewOutlineThickness
                            : cardSlot.applied
                                ? root.metrics.controlOutlineThickness : 0
                        border.color: cardSlot.navigationCurrent
                            ? root.theme.secondaryControl : root.theme.focus
                        clip: true

                        Behavior on width {
                            NumberAnimation { duration: 120 }
                        }
                        Behavior on height {
                            NumberAnimation { duration: 120 }
                        }

                        Image {
                            id: previewImage

                            anchors {
                                fill: parent
                                margins: previewCard.border.width
                            }
                            source: cardSlot.sourceActive
                                ? cardSlot.modelData.uri : ""
                            sourceSize.width: root.previewWidth
                            sourceSize.height: root.previewHeight
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            cache: true
                            smooth: true
                        }

                        Text {
                            anchors.centerIn: parent
                            width: parent.width - root.metrics.scaled(24)
                            visible: previewImage.status === Image.Error
                            text: "Preview unavailable"
                            textFormat: Text.PlainText
                            color: root.theme.textMuted
                            font.pixelSize: root.metrics.detailFontSize
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                        }

                        Rectangle {
                            anchors {
                                right: parent.right
                                bottom: parent.bottom
                                rightMargin: root.metrics.scaled(8)
                                bottomMargin: root.metrics.scaled(8)
                            }
                            visible: cardSlot.applied
                            width: appliedLabel.implicitWidth
                                + root.metrics.rowSidePadding
                            height: appliedLabel.implicitHeight
                                + root.metrics.scaled(6)
                            color: root.theme.selectionFill

                            Text {
                                id: appliedLabel

                                anchors.centerIn: parent
                                text: "Applied"
                                textFormat: Text.PlainText
                                color: root.theme.text
                                font.pixelSize: root.metrics.captionFontSize
                                font.weight: Font.DemiBold
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !root.controller.applying
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (cardSlot.navigationCurrent)
                                    root.controller.applyCandidate()
                                else
                                    root.controller.select(cardSlot.index)
                                keyboardScope.forceActiveFocus()
                            }
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: carousel
                visible: !root.controller.loading
                    && root.controller.catalog.length === 0
                    && root.controller.errorMessage === ""
                width: carousel.width - root.metrics.scaled(48)
                text: "No backgrounds are available for "
                    + root.controller.modeLabel + " mode."
                textFormat: Text.PlainText
                color: root.theme.textMuted
                font.pixelSize: root.metrics.bodyFontSize
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            Text {
                anchors.centerIn: carousel
                visible: root.controller.loading
                text: "Loading backgrounds…"
                textFormat: Text.PlainText
                color: root.theme.textMuted
                font.pixelSize: root.metrics.bodyFontSize
            }

            Text {
                id: filename

                anchors {
                    top: carousel.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.metrics.contentGap
                    leftMargin: root.metrics.overlayPadding
                    rightMargin: root.metrics.overlayPadding
                }
                text: root.controller.candidateFilename
                textFormat: Text.PlainText
                color: root.theme.text
                font.pixelSize: root.metrics.bodyFontSize
                font.weight: root.metrics.overlayFontWeight
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideMiddle
            }

            Text {
                id: statusText

                anchors {
                    top: filename.bottom
                    left: parent.left
                    right: parent.right
                    topMargin: root.metrics.contentGap
                    leftMargin: root.metrics.overlayPadding
                    rightMargin: root.metrics.overlayPadding
                }
                text: root.controller.errorMessage !== ""
                    ? root.controller.errorMessage
                    : root.controller.applying
                        ? "Applying background…"
                        : "Left/Right or wheel to browse · "
                            + "Enter or second click to apply · Esc to cancel"
                textFormat: Text.PlainText
                color: root.controller.errorMessage !== ""
                    ? root.theme.danger : root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }
        }
    }
}
