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
        const preview = Layout.previewWidth(1344, 24, 952, 600, 32, 0.74)
        const adjacent = Layout.adjacentWidth(preview, 552)
        const step = Layout.cardStep(preview, 360, 48)
        compare(preview, 952)
        compare(Layout.previewHeight(preview), 536)
        compare(preview / 560, 1.7)
        compare(adjacent, 552)
        verify(preview > adjacent, "current card is not dominant")
        verify(step < adjacent, "adjacent cards no longer overlap")
        compare(Layout.compositionWidth(preview, adjacent, step), 1272)
        verify(Layout.compositionWidth(preview, adjacent, step) < 1344 - 48,
            "target composition exceeds the transparent surface")
        compare((Layout.compositionWidth(preview, adjacent, step)
            - preview) / 2, 160)
    }

    function test_small_surface_clamps_complete_composition() {
        const preview = Layout.previewWidth(620, 24, 952, 320, 32, 0.74)
        const adjacent = Layout.adjacentWidth(preview, 552)
        const step = Layout.cardStep(preview, 360, 48)
        compare(preview, 423)
        compare(Layout.previewHeight(preview), 238)
        verify(Layout.previewHeight(preview) <= 320 - 64,
            "small-surface preview exceeds vertical bounds")
        verify(Layout.compositionWidth(preview, adjacent, step) <= 620 - 48,
            "small-surface carousel exceeds horizontal bounds")
    }

    function test_one_item_slot_is_centered() {
        const surfaceWidth = 1344
        const step = 360
        compare(Layout.edgeSpacer(surfaceWidth, step) + step / 2,
            surfaceWidth / 2)
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
