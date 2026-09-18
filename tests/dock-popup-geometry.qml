import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/DockPopupGeometry.js" as Geometry

TestCase {
    name: "DockPopupGeometry"

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
