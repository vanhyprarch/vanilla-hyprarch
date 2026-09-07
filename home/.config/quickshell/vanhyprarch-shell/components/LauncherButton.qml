import QtQuick
import Quickshell

Item {
    id: root

    required property var theme
    required property DesktopEntry desktopEntry
    property int buttonSize: 40
    property int iconSize: 28
    property var workspaceIds: []
    property bool draggable: false
    property string dragDesktopId: desktopEntry ? desktopEntry.id : ""
    readonly property bool dragging: dragHandler.active

    signal activationRequested()
    signal contextMenuRequested()
    signal dragStarted()
    signal dragFinished()

    function finishDragOperation(wasCanceled) {
        if (!dragProxy.Drag.active)
            return

        if (wasCanceled)
            dragProxy.Drag.cancel()
        else
            dragProxy.Drag.drop()

        root.dragFinished()
        dragHandler.persistentTranslation = Qt.vector2d(0, 0)
        dragProxy.x = 0
        dragProxy.y = 0
    }

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    width: implicitWidth
    height: implicitHeight
    clip: true
    opacity: dragging ? 0.65 : 1

    Item {
        id: dragProxy

        width: root.width
        height: root.height
        opacity: 0

        Drag.source: root
        Drag.keys: ["pinned-launcher"]
        Drag.proposedAction: Qt.MoveAction
    }

    onDesktopEntryChanged: iconImage.failed = false

    Column {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 6
        spacing: -1

        Repeater {
            model: root.workspaceIds

            Text {
                required property var modelData

                width: 6
                height: 8
                text: modelData
                color: root.theme.text
                font.pixelSize: 8
                font.weight: Font.Normal
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
            }
        }
    }

    // Keep the icon separate from the full click target, leaving room at the left.
    Image {
        id: iconImage

        property bool failed: false
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: Quickshell.iconPath(!failed && root.desktopEntry && root.desktopEntry.icon
            ? root.desktopEntry.icon : "application-x-executable", "application-x-executable")
        sourceSize: Qt.size(root.iconSize, root.iconSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        onStatusChanged: {
            if (status === Image.Error && !failed)
                failed = true
        }
    }

    HoverHandler {
        enabled: root.desktopEntry !== null
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        enabled: root.desktopEntry !== null
        acceptedButtons: Qt.LeftButton
        gesturePolicy: TapHandler.DragThreshold
        onTapped: root.activationRequested()
    }

    TapHandler {
        enabled: root.desktopEntry !== null
        acceptedButtons: Qt.RightButton
        gesturePolicy: TapHandler.DragThreshold
        onTapped: root.contextMenuRequested()
    }

    DragHandler {
        id: dragHandler

        enabled: root.draggable && root.desktopEntry !== null
        acceptedButtons: Qt.LeftButton
        target: dragProxy

        onActiveChanged: {
            if (active) {
                dragProxy.Drag.hotSpot = centroid.pressPosition
                root.dragStarted()
                dragProxy.Drag.active = true
            } else if (dragProxy.Drag.active) {
                Qt.callLater(() => root.finishDragOperation(false))
            }
        }

        onCanceled: root.finishDragOperation(true)
    }
}
