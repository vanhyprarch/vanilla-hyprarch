pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
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
    readonly property int surfaceWidth: Math.max(1,
        Math.min(metrics.backgroundPickerMaximumWidth,
            screenWidth - dockWidth - metrics.scaled(48)))
    readonly property int surfaceHeight: Math.max(1,
        Math.min(metrics.backgroundPickerMaximumHeight,
            screenHeight - metrics.scaled(64)))
    readonly property int previewWidth: PickerLayout.previewWidth(surfaceWidth,
        metrics.backgroundPickerHorizontalPadding,
        metrics.backgroundPreviewMaximumWidth, surfaceHeight,
        metrics.backgroundPickerVerticalPadding,
        metrics.backgroundPreviewDistanceTwoScale,
        metrics.backgroundPreviewDistanceTwoOffsetScale)
    readonly property int previewHeight:
        PickerLayout.previewHeight(previewWidth)
    readonly property int cardStep: PickerLayout.cardStep(previewWidth,
        metrics.backgroundPreviewLogicalStep, metrics.scaled(48))

    persistentLeftInset: dockWidth
    implicitWidth: surfaceWidth
    implicitHeight: surfaceHeight
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

    function cardGeometry(index: int): var {
        return PickerLayout.cardRect(index, controller.currentIndex,
            controller.catalog.length, surfaceWidth, surfaceHeight,
            previewWidth, metrics.backgroundPreviewDistanceOneScale,
            metrics.backgroundPreviewDistanceTwoScale,
            metrics.backgroundPreviewDistanceOneOffsetScale,
            metrics.backgroundPreviewDistanceTwoOffsetScale)
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

    mask: Region {
        Region {
            readonly property var geometry: root.cardGeometry(
                root.controller.currentIndex - 2)
            x: geometry.x
            y: geometry.y
            width: geometry.visible ? geometry.width : 0
            height: geometry.visible ? geometry.height : 0
        }
        Region {
            readonly property var geometry: root.cardGeometry(
                root.controller.currentIndex - 1)
            x: geometry.x
            y: geometry.y
            width: geometry.visible ? geometry.width : 0
            height: geometry.visible ? geometry.height : 0
        }
        Region {
            readonly property var geometry: root.cardGeometry(
                root.controller.currentIndex)
            x: geometry.x
            y: geometry.y
            width: geometry.visible ? geometry.width : 0
            height: geometry.visible ? geometry.height : 0
        }
        Region {
            readonly property var geometry: root.cardGeometry(
                root.controller.currentIndex + 1)
            x: geometry.x
            y: geometry.y
            width: geometry.visible ? geometry.width : 0
            height: geometry.visible ? geometry.height : 0
        }
        Region {
            readonly property var geometry: root.cardGeometry(
                root.controller.currentIndex + 2)
            x: geometry.x
            y: geometry.y
            width: geometry.visible ? geometry.width : 0
            height: geometry.visible ? geometry.height : 0
        }

        Region {
            x: exceptionalMessage.x
            y: exceptionalMessage.y
            width: exceptionalMessage.visible ? exceptionalMessage.width : 0
            height: exceptionalMessage.visible ? exceptionalMessage.height : 0
        }
    }

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

    FocusScope {
        id: keyboardScope

        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: event => root.handleKey(event)

        ListView {
            id: carousel

            anchors.fill: parent
            model: root.controller.catalog
            orientation: ListView.Horizontal
            clip: true
            interactive: false
            boundsBehavior: Flickable.StopAtBounds
            cacheBuffer: root.cardStep * 3
            reuseItems: true
            currentIndex: -1

            header: Item {
                width: PickerLayout.edgeSpacer(carousel.width, root.cardStep)
                height: 1
            }

            footer: Item {
                width: PickerLayout.edgeSpacer(carousel.width, root.cardStep)
                height: 1
            }

            onCurrentIndexChanged: {
                if (currentIndex >= 0
                        && root.controller.currentIndex !== currentIndex)
                    root.controller.select(currentIndex)
            }

            delegate: Item {
                id: cardSlot

                required property int index
                required property var modelData

                readonly property bool navigationCurrent:
                    index === root.controller.currentIndex
                readonly property bool applied:
                    modelData.path === root.controller.appliedPath
                readonly property int visualDistance:
                    PickerLayout.visualDistance(index,
                        root.controller.currentIndex,
                        root.controller.catalog.length)
                readonly property var visualGeometry:
                    root.cardGeometry(index)
                readonly property bool sourceActive:
                    PickerLayout.sourceActive(index,
                        root.controller.currentIndex,
                        root.controller.catalog.length)

                width: root.cardStep
                height: carousel.height
                z: visualGeometry.z

                Rectangle {
                    id: previewCard

                    x: cardSlot.visualGeometry.x - cardSlot.x
                        + carousel.contentX
                    y: cardSlot.visualGeometry.y
                    visible: cardSlot.visualGeometry.visible
                    width: cardSlot.visualGeometry.width
                    height: cardSlot.visualGeometry.height
                    radius: 0
                    color: root.theme.surface
                    opacity: 1.0
                    border.width: cardSlot.navigationCurrent
                        ? root.metrics.backgroundPreviewOutlineThickness
                        : root.metrics.controlOutlineThickness
                    border.color: cardSlot.navigationCurrent
                        ? root.theme.secondaryControl
                        : cardSlot.applied ? root.theme.focus
                            : root.theme.panelOutline
                    clip: true

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
                            rightMargin: root.metrics.scaled(10)
                            bottomMargin: root.metrics.scaled(10)
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

        Rectangle {
            id: exceptionalMessage

            anchors.centerIn: parent
            visible: root.controller.loading
                || root.controller.errorMessage !== ""
                || root.controller.catalog.length === 0
            width: Math.max(1, Math.min(
                root.width - root.metrics.scaled(48),
                messageText.implicitWidth + root.metrics.rowSidePadding * 2))
            height: messageText.implicitHeight + root.metrics.scaled(12)
            color: root.theme.background
            border.width: root.metrics.controlOutlineThickness
            border.color: root.theme.panelOutline

            Text {
                id: messageText

                anchors {
                    fill: parent
                    margins: root.metrics.scaled(6)
                }
                text: root.controller.errorMessage !== ""
                    ? root.controller.errorMessage
                    : root.controller.loading
                        ? "Loading backgrounds…"
                        : "No backgrounds available."
                textFormat: Text.PlainText
                color: root.controller.errorMessage !== ""
                    ? root.theme.danger : root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.Wrap
            }
        }
    }
}
