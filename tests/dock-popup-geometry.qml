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

    function test_systemPanelKeepsPhysicalDockGap(): void {
        const dockWidth = 56
        const historicalGap = 9
        const monitorWidth = 1920
        const dockRight = dockWidth
        const consumers = ["Display", "Audio", "Network", "Bluetooth",
            "Clock", "Power & Idle", "Power Menu"]
        for (const consumer of consumers) {
            const margin = Geometry.horizontalMargin(historicalGap, 384,
                monitorWidth, dockWidth)
            const physicalLeft = dockRight + margin
            compare(physicalLeft - dockRight, historicalGap,
                consumer + " lost the historical physical dock gap")
        }
        compare(Geometry.aboveMargin(700, 36, -2, 420, 1080), 318)
        compare(Geometry.aboveMargin(540, 36, -2, 310, 900), 268)
    }

    function test_launcherPlacementKeepsPhysicalDockGap(): void {
        const dockWidth = 56
        const historicalGap = 9
        const dockRight = dockWidth
        for (const consumer of ["App Picker", "Launcher Context Menu"]) {
            const margin = Geometry.horizontalMargin(historicalGap, 384,
                1920, dockWidth)
            compare(dockRight + margin, dockRight + historicalGap,
                consumer + " lost its launcher-relative physical gap")
        }
        compare(Geometry.alignedTopMargin(240, 4, 180, 1080), 236)
    }

    function test_monitorOriginDoesNotEnterLocalMargins(): void {
        const dockWidth = 56
        const localMargin = Geometry.horizontalMargin(9, 384, 1920,
            dockWidth)
        compare(localMargin, 9)
        compare(-2560 + dockWidth + localMargin, -2495)
        compare(1920 + dockWidth + localMargin, 1985)
    }

    function test_popupSlidesInsideSmallLogicalScreen(): void {
        const margin = Geometry.horizontalMargin(9, 300, 360, 56)
        compare(margin, 4)
        compare(56 + margin, 60)
        compare(Geometry.aboveMargin(120, 36, -2, 220, 240), 0)
        compare(Geometry.alignedTopMargin(210, 4, 80, 240), 160)
    }

    function test_varyingLogicalDimensions(): void {
        compare(Geometry.horizontalMargin(12, 420, 1600, 72), 12)
        compare(Geometry.aboveMargin(850, 48, -4, 500, 900), 400)
        compare(Geometry.alignedTopMargin(32, 6, 260, 720), 26)
        compare(Geometry.clampMargin(-18, 200, 720), 0)
        compare(Geometry.clampMargin(900, 300, 1000), 700)
    }
}
