import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/CenteredOverlayGeometry.js" as Geometry

TestCase {
    name: "CenteredOverlayGeometry"

    function verifyCentered(surfaceName, monitor, dockWidth, surface, popup) {
        const usableOriginX = monitor.x + dockWidth
        const relativeLeft = Geometry.usableMargin(monitor.width, dockWidth,
            surface.width)
        const left = usableOriginX + relativeLeft
        const top = Geometry.coordinate(monitor.y, monitor.height, surface.height)
        const centerX = left + surface.width / 2
        const centerY = top + surface.height / 2
        const usableCenterX = monitor.x + dockWidth
            + (monitor.width - dockWidth) / 2

        compare(centerX, usableCenterX,
            surfaceName + " usable x center changed with " + popup.name)
        compare(centerY, monitor.y + monitor.height / 2,
            surfaceName + " y center changed with " + popup.name)
    }

    function test_monitorCenterIndependentOfDockPopup() {
        const surfaces = [
            { name: "Super+Space", width: 720, height: 620 },
            { name: "Keyboard Shortcuts", width: 900, height: 900 }
        ]
        const monitors = [
            { x: 0, y: 0, width: 1920, height: 1080, dockWidth: 56 },
            { x: -2560, y: 320, width: 2560, height: 1440, dockWidth: 72 },
            { x: 1920, y: -2160, width: 3840, height: 2160, dockWidth: 64 }
        ]
        const popupStates = [
            { name: "no dock popup", x: 0, y: 0, width: 0, height: 0 },
            { name: "Display-like popup", x: 64, y: 500, width: 360, height: 420 },
            { name: "Audio-like popup", x: 72, y: 620, width: 520, height: 310 },
            { name: "Network-like popup", x: -400, y: 80, width: 640, height: 760 }
        ]

        for (const surface of surfaces) {
            for (const monitor of monitors) {
                for (const popup of popupStates)
                    verifyCentered(surface.name, monitor, monitor.dockWidth,
                        surface, popup)
            }
        }
    }

    function test_marginUsesMonitorLocalGeometry() {
        compare(Geometry.usableMargin(1920, 56, 900), 482)
        compare(Geometry.usableMargin(2560, 72, 900), 794)
        compare(Geometry.usableMargin(3840, 64, 900), 1438)
        compare(Geometry.margin(1080, 620), 230)
        compare(Geometry.usableCoordinate(-2560, 2560, 72, 900), -1694)
        compare(Geometry.usableCoordinate(1920, 3840, 64, 900), 3422)
    }

    function test_measuredLogicalGeometryUsesRelativeMargins() {
        const monitorWidth = 3072
        const dockWidth = 56
        const usableOriginX = dockWidth
        const expectedCenterX = 1564
        const surfaces = [
            { name: "Super+Space", width: 840, expectedMargin: 1088 },
            { name: "Keyboard Shortcuts", width: 900, expectedMargin: 1058 }
        ]

        for (const surface of surfaces) {
            const margin = Geometry.usableMargin(monitorWidth, dockWidth,
                surface.width)
            compare(margin, surface.expectedMargin,
                surface.name + " relative margin is incorrect")
            compare(usableOriginX + margin + surface.width / 2,
                expectedCenterX, surface.name + " physical center is incorrect")
        }
    }

    function test_noDockFallsBackToFullMonitorCenter() {
        compare(Geometry.usableMargin(1920, 0, 900), 510)
        compare(Geometry.usableCenter(-1920, 1920, 0, 900), -960)
        compare(Geometry.usableCoordinate(2560, 2560, 0, 900),
            Geometry.coordinate(2560, 2560, 900))
    }
}
