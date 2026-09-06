pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland

Item {
    id: root

    property int contentWidth: 48
    property int buttonSize: 40
    property int iconSize: 28
    property int spacing: 4
    property color textColor: "#5A3525"

    readonly property var resolvedLaunchers: {
        // Re-resolve saved IDs when the installed application index changes.
        DesktopEntries.applications.values
        return store.launchers.map(launcher => ({
            config: launcher,
            desktopEntry: DesktopEntries.byId(launcher.desktopId)
        })).filter(launcher => launcher.desktopEntry !== null)
    }

    function workspaceIdsForDesktopEntry(desktopEntry: DesktopEntry): var {
        if (!desktopEntry)
            return []

        const normalize = value => value === null || value === undefined
            ? "" : String(value).trim().toLowerCase()

        const candidates = []
        const startupClass = normalize(desktopEntry.startupClass)
        const desktopId = normalize(desktopEntry.id)
        const desktopIdWithoutSuffix = desktopId.endsWith(".desktop")
            ? desktopId.slice(0, -8) : desktopId

        for (const candidate of [startupClass, desktopId, desktopIdWithoutSuffix]) {
            if (candidate !== "" && !candidates.includes(candidate))
                candidates.push(candidate)
        }

        const workspaceIds = []
        for (const workspace of Hyprland.workspaces.values) {
            if (!workspace || workspace.id <= 0 || !workspace.toplevels)
                continue

            const matches = workspace.toplevels.values.some(toplevel => {
                if (!toplevel)
                    return false

                const ipcObject = toplevel.lastIpcObject
                const wayland = toplevel.wayland
                const runtimeIdentifiers = [
                    normalize(ipcObject ? ipcObject["class"] : ""),
                    normalize(wayland ? wayland.appId : "")
                ]
                return runtimeIdentifiers.some(identifier =>
                    identifier !== "" && candidates.includes(identifier))
            })

            if (matches && !workspaceIds.includes(workspace.id))
                workspaceIds.push(workspace.id)
        }

        return workspaceIds.sort((left, right) => left - right)
    }

    implicitWidth: contentWidth
    implicitHeight: content.implicitHeight
    width: implicitWidth
    height: implicitHeight

    LauncherStore {
        id: store
    }

    Column {
        id: content

        width: root.width
        spacing: root.spacing

        Repeater {
            model: root.resolvedLaunchers

            LauncherButton {
                id: launcherButton

                required property var modelData

                x: (root.width - width) / 2
                desktopEntry: modelData.desktopEntry
                buttonSize: root.buttonSize
                iconSize: root.iconSize
                workspaceIds: root.workspaceIdsForDesktopEntry(modelData.desktopEntry)
                onContextMenuRequested: {
                    launcherContextMenu.visible = false
                    launcherContextMenu.desktopId = modelData.desktopEntry.id
                    launcherContextMenu.popupAnchorItem = launcherButton
                    launcherContextMenu.visible = true
                }
            }
        }

        Item {
            id: addButton

            anchors.horizontalCenter: parent.horizontalCenter
            width: root.buttonSize
            height: root.buttonSize

            Text {
                anchors.centerIn: parent
                text: "+"
                color: root.textColor
                font.pixelSize: 24
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: appPicker.visible = !appPicker.visible
            }
        }
    }

    AppPicker {
        id: appPicker
        anchor.item: addButton
        launcherStore: store
    }

    LauncherContextMenu {
        id: launcherContextMenu
        launcherStore: store
    }
}
