import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/CenteredOverlayGeometry.js" as Geometry

TestCase {
    name: "CenteredOverlayGeometry"

    function verifyCentered(surfaceName, monitor, surface, popup) {
        const left = Geometry.coordinate(monitor.x, monitor.width, surface.width)
        const top = Geometry.coordinate(monitor.y, monitor.height, surface.height)
        const centerX = left + surface.width / 2
        const centerY = top + surface.height / 2

        compare(centerX, monitor.x + monitor.width / 2,
            surfaceName + " x center changed with " + popup.name)
        compare(centerY, monitor.y + monitor.height / 2,
            surfaceName + " y center changed with " + popup.name)
    }

    function test_monitorCenterIndependentOfDockPopup() {
        const surfaces = [
            { name: "Super+Space", width: 900, height: 620 },
            { name: "Keyboard Shortcuts", width: 900, height: 900 }
        ]
        const monitors = [
            { x: 0, y: 0, width: 1920, height: 1080 },
            { x: -2560, y: 320, width: 2560, height: 1440 },
            { x: 1920, y: -2160, width: 3840, height: 2160 }
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
                    verifyCentered(surface.name, monitor, surface, popup)
            }
        }
    }

    function test_marginUsesMonitorLocalGeometry() {
        compare(Geometry.margin(1920, 900), 510)
        compare(Geometry.margin(1080, 620), 230)
        compare(Geometry.coordinate(-2560, 2560, 900), -1730)
        compare(Geometry.coordinate(1920, 3840, 900), 3390)
    }
}
