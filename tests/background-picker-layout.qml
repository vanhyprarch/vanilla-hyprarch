import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/BackgroundPickerLayout.js" as Layout

TestCase {
    name: "BackgroundPickerLayout"
    when: windowShown
    visible: true
    width: 420
    height: 180

    ListView {
        id: wheelView
        width: 300
        height: 100
        model: 12
        orientation: ListView.Horizontal
        boundsBehavior: Flickable.StopAtBounds
        snapMode: ListView.SnapToItem
        highlightRangeMode: ListView.StrictlyEnforceRange
        preferredHighlightBegin: 100
        preferredHighlightEnd: 200
        currentIndex: 0
        delegate: Rectangle {
            required property int index
            width: 100
            height: 100
        }
    }

    function init() {
        wheelView.currentIndex = 0
        wheelView.positionViewAtBeginning()
        wait(0)
    }

    function test_widescreen_preview_geometry() {
        compare(Layout.previewWidth(1040, 80, 560, 620, 160), 560)
        compare(Layout.previewHeight(560), 315)
        compare(Layout.previewWidth(620, 80, 560, 620, 160), 460)
        compare(Layout.previewHeight(460), 259)
        compare(Layout.previewWidth(1040, 80, 560, 420, 160), 462)
        compare(Layout.previewHeight(462), 260)
        verify(Layout.cardStep(560, 190, 120) < 300,
            "adjacent cards no longer overlap")
        verify(Layout.cardStep(462, 190, 120) < 300,
            "narrow-panel cards no longer overlap")
    }

    function test_lazy_source_window_for_catalog_sizes() {
        verify(!Layout.sourceActive(0, -1, 0, 2))
        verify(Layout.sourceActive(0, 0, 1, 2))
        verify(Layout.sourceActive(1, 0, 2, 2))
        for (let index = 0; index < 4; ++index)
            verify(Layout.sourceActive(index, 2, 4, 2))

        let active = 0
        for (let index = 0; index < 40; ++index) {
            if (Layout.sourceActive(index, 20, 40, 2))
                active++
        }
        compare(active, 5)
    }

    function test_native_vertical_wheel_moves_horizontal_candidate() {
        mouseMove(wheelView, 150, 50)
        wait(1)
        mouseWheel(wheelView, 150, 50, 0, -120)
        tryCompare(wheelView, "moving", false, 1000)
        verify(wheelView.currentIndex > 0,
            "native horizontal ListView did not map vertical wheel navigation")
    }
}
