pragma ComponentBehavior: Bound

// SPDX-License-Identifier: GPL-2.0-only

import QtQuick

Item {
    id: root

    required property var sessionSource
    required property string targetFile
    readonly property bool valid: matchCount === 1 && sessionIndex >= 0
    property int matchCount: 0
    property int sessionIndex: -1

    visible: false
    width: 0
    height: 0

    function scheduleResolve(): void {
        resolveTimer.restart()
    }

    function resolveNow(): void {
        let matches = 0
        let matchingIndex = -1

        if (root.targetFile !== "") {
            for (let itemIndex = 0; itemIndex < sessionEntries.count; ++itemIndex) {
                const entry = sessionEntries.itemAt(itemIndex)
                // Repeater.itemAt() is statically an Item; these two
                // properties belong to the delegate immediately below.
                // qmllint disable missing-property
                if (entry !== null && entry.sessionFile === root.targetFile) {
                    matches += 1
                    matchingIndex = entry.sessionIndex
                }
                // qmllint enable missing-property
            }
        }

        root.matchCount = matches
        root.sessionIndex = matches === 1 ? matchingIndex : -1
    }

    onSessionSourceChanged: scheduleResolve()
    onTargetFileChanged: scheduleResolve()

    Timer {
        id: resolveTimer

        interval: 0
        repeat: false
        onTriggered: root.resolveNow()
    }

    Repeater {
        id: sessionEntries

        model: root.sessionSource

        delegate: Item {
            required property int index
            required property string file
            readonly property int sessionIndex: index
            readonly property string sessionFile: file

            visible: false
            width: 0
            height: 0

            Component.onCompleted: root.scheduleResolve()
            Component.onDestruction: root.scheduleResolve()
            onIndexChanged: root.scheduleResolve()
            onSessionFileChanged: root.scheduleResolve()
        }

        onItemAdded: root.scheduleResolve()
        onItemRemoved: root.scheduleResolve()
    }
}
