import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/DockPopupGeometry.js" as Geometry

TestCase {
    name: "DockPopupGeometry"

    QtObject {
        id: screenA
    }

    QtObject {
        id: screenB
    }

    QtObject {
        id: windowA
        property var screen: screenA
    }

    QtObject {
        id: windowB
        property var screen: screenB
    }

    Component {
        id: detachedAnchorComponent

        Item {
            property string marker: "detached"
        }
    }

    function mappedRect(anchor): rect {
        return anchor.marker === "replacement"
            ? Qt.rect(40, 50, 60, 70)
            : Qt.rect(10, 20, 30, 40)
    }

    function test_detachedAnchorDoesNotMap(): void {
        const anchor = detachedAnchorComponent.createObject(null)
        verify(anchor !== null)
        let mapCalls = 0
        const result = Geometry.mapAnchorRect(anchor, null, screenA,
            function(candidate) {
                mapCalls++
                return mappedRect(candidate)
            })
        compare(result, null)
        compare(mapCalls, 0)
        anchor.destroy()
    }

    function test_anchorWindowLifecycle(): void {
        const anchor = detachedAnchorComponent.createObject(null)
        let mapCalls = 0
        const mapper = function(candidate) {
            mapCalls++
            return mappedRect(candidate)
        }

        compare(Geometry.mapAnchorRect(anchor, null, screenA, mapper), null)
        compare(mapCalls, 0)

        const attached = Geometry.mapAnchorRect(anchor, windowA, screenA,
            mapper)
        compare(attached, Qt.rect(10, 20, 30, 40))
        compare(mapCalls, 1)

        compare(Geometry.mapAnchorRect(anchor, null, screenA, mapper), null)
        compare(mapCalls, 1)

        compare(Geometry.mapAnchorRect(anchor, windowA, screenB, mapper), null)
        compare(mapCalls, 1)

        const moved = Geometry.mapAnchorRect(anchor, windowB, screenB,
            mapper)
        compare(moved, Qt.rect(10, 20, 30, 40))
        compare(mapCalls, 2)
        anchor.destroy()
    }

    function test_requestedOpenWaitsForPlacement(): void {
        const requestedVisible = true
        compare(Geometry.surfaceVisible(requestedVisible, false), false)
        compare(Geometry.surfaceVisible(requestedVisible, true), true)
        compare(Geometry.surfaceVisible(requestedVisible, false), false)
        compare(requestedVisible, true)
    }

    function test_launcherRetargetDoesNotReuseOldGeometry(): void {
        const oldAnchor = detachedAnchorComponent.createObject(null)
        const replacement = detachedAnchorComponent.createObject(null,
            { "marker": "replacement" })
        let mapCalls = 0
        const mapper = function(candidate) {
            mapCalls++
            return mappedRect(candidate)
        }

        compare(Geometry.mapAnchorRect(oldAnchor, windowA, screenA, mapper),
            Qt.rect(10, 20, 30, 40))
        compare(Geometry.mapAnchorRect(replacement, null, screenA, mapper),
            null)
        compare(mapCalls, 1)
        compare(Geometry.mapAnchorRect(replacement, windowA, screenA, mapper),
            Qt.rect(40, 50, 60, 70))
        compare(mapCalls, 2)

        oldAnchor.destroy()
        replacement.destroy()
    }

    function test_monitorDelegateRecreationRequiresMatchingWindow(): void {
        const anchor = detachedAnchorComponent.createObject(null)
        let mapCalls = 0
        const mapper = function(candidate) {
            mapCalls++
            return mappedRect(candidate)
        }

        verify(Geometry.anchorReady(anchor, windowA, screenA))
        verify(!Geometry.anchorReady(anchor, windowA, screenB))
        verify(!Geometry.anchorReady(anchor, null, screenB))
        verify(Geometry.anchorReady(anchor, windowB, screenB))
        compare(Geometry.mapAnchorRect(null, windowB, screenB, mapper), null)
        compare(mapCalls, 0)
        anchor.destroy()
    }

    function test_systemPanelPlacementMatchesPopupAnchor(): void {
        compare(Geometry.horizontalMargin(10, 36, 56, 9, 384, 1920), 64)
        compare(Geometry.aboveMargin(700, 36, -2, 420, 1080), 318)
        compare(Geometry.aboveMargin(540, 36, -2, 310, 900), 268)
    }

    function test_launcherPlacementMatchesPopupAnchor(): void {
        compare(Geometry.horizontalMargin(8, 40, 56, 9, 384, 1920), 64)
        compare(Geometry.alignedTopMargin(240, 4, 180, 1080), 236)
    }

    function test_monitorOriginDoesNotEnterLocalMargins(): void {
        const localMargin = Geometry.horizontalMargin(10, 36, 56, 9,
            384, 1920)
        compare(localMargin, 64)
        compare(-2560 + localMargin, -2496)
        compare(1920 + localMargin, 1984)
    }

    function test_popupSlidesInsideSmallLogicalScreen(): void {
        compare(Geometry.horizontalMargin(10, 36, 56, 9, 300, 360), 60)
        compare(Geometry.aboveMargin(120, 36, -2, 220, 240), 0)
        compare(Geometry.alignedTopMargin(210, 4, 80, 240), 160)
    }

    function test_varyingLogicalDimensions(): void {
        compare(Geometry.horizontalMargin(22, 48, 72, 12, 420, 1600), 93)
        compare(Geometry.aboveMargin(850, 48, -4, 500, 900), 400)
        compare(Geometry.alignedTopMargin(32, 6, 260, 720), 26)
        compare(Geometry.clampMargin(-18, 200, 720), 0)
        compare(Geometry.clampMargin(900, 300, 1000), 700)
    }
}
