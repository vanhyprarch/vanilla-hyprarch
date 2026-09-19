import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/BackgroundPickerLayout.js" as Layout

TestCase {
    name: "BackgroundPickerLayout"
    when: windowShown
    visible: true
    width: 420
    height: 180

    readonly property real distanceOneScale: 0.76
    readonly property real distanceTwoScale: 0.58
    readonly property real distanceOneOffsetScale: 0.40
    readonly property real distanceTwoOffsetScale: 0.655
    readonly property real distanceOneOpacity: 0.88
    readonly property real distanceTwoOpacity: 0.78

    function preview(surfaceWidth, surfaceHeight) {
        return Layout.previewWidth(surfaceWidth, 24, 952, surfaceHeight, 32,
            distanceTwoScale, distanceTwoOffsetScale)
    }

    function widthAt(previewWidth, distance) {
        return Layout.cardWidth(previewWidth, distance, distanceOneScale,
            distanceTwoScale)
    }

    function offsetAt(index, currentIndex, count, previewWidth) {
        return Layout.cardCenterOffset(index, currentIndex, count,
            previewWidth, distanceOneOffsetScale,
            distanceTwoOffsetScale)
    }

    function visibleIndices(count, currentIndex) {
        const result = []
        for (let index = 0; index < count; ++index) {
            if (Layout.visible(index, currentIndex, count))
                result.push(index)
        }
        return result
    }

    function test_reference_depth_geometry() {
        const dominant = preview(1856, 600)
        const distanceOne = widthAt(dominant, 1)
        const distanceTwo = widthAt(dominant, 2)
        const nearOffset = Math.abs(offsetAt(3, 2, 6, dominant))
        const farOffset = Math.abs(offsetAt(4, 2, 6, dominant))

        compare(dominant, 952)
        compare(Layout.previewHeight(dominant), 536)
        compare(distanceOne, 724)
        compare(Layout.previewHeight(distanceOne), 407)
        compare(distanceTwo, 552)
        compare(Layout.previewHeight(distanceTwo), 311)
        verify(dominant > distanceOne)
        verify(distanceOne > distanceTwo)
        verify(distanceOne / dominant >= 0.70
            && distanceOne / dominant <= 0.78)
        verify(distanceTwo / dominant >= 0.55
            && distanceTwo / dominant <= 0.62)

        compare(nearOffset, 381)
        compare(farOffset, 624)
        verify(nearOffset < farOffset)
        verify(farOffset - nearOffset < nearOffset,
            "neighbor centers retained a linear row instead of stacked depth")
        compare(Layout.compositionWidth(dominant, distanceTwo, farOffset),
            1800)
        verify(Layout.compositionWidth(dominant, distanceTwo, farOffset)
            <= 1856 - 48)
    }

    function test_depth_order_and_opacity() {
        compare(Layout.cardZ(0), 30)
        compare(Layout.cardZ(1), 20)
        compare(Layout.cardZ(2), 10)
        verify(Layout.cardZ(0) > Layout.cardZ(1))
        verify(Layout.cardZ(1) > Layout.cardZ(2))

        compare(Layout.cardOpacity(0, distanceOneOpacity,
            distanceTwoOpacity), 1.0)
        compare(Layout.cardOpacity(1, distanceOneOpacity,
            distanceTwoOpacity), distanceOneOpacity)
        compare(Layout.cardOpacity(2, distanceOneOpacity,
            distanceTwoOpacity), distanceTwoOpacity)
        verify(distanceOneOpacity > distanceTwoOpacity)
    }

    function test_left_and_right_geometry_is_symmetric() {
        const dominant = preview(1856, 600)
        const step = Layout.cardStep(dominant, 360, 48)
        const count = 7
        const current = 3

        compare(offsetAt(2, current, count, dominant),
            -offsetAt(4, current, count, dominant))
        compare(offsetAt(1, current, count, dominant),
            -offsetAt(5, current, count, dominant))
        compare(Layout.visualDistance(2, current, count), 1)
        compare(Layout.visualDistance(4, current, count), 1)
        compare(Layout.visualDistance(1, current, count), 2)
        compare(Layout.visualDistance(5, current, count), 2)

        for (const index of [1, 2, 3, 4, 5]) {
            const translation = Layout.cardTranslation(index, current, count,
                step, dominant, distanceOneOffsetScale,
                distanceTwoOffsetScale)
            compare((index - current) * step + translation,
                offsetAt(index, current, count, dominant))
        }
    }

    function test_catalog_boundaries_have_real_unique_cards_only() {
        compare(visibleIndices(0, -1).length, 0)
        compare(visibleIndices(1, 0).join(","), "0")
        compare(visibleIndices(2, 0).join(","), "0,1")
        compare(visibleIndices(2, 1).join(","), "0,1")
        compare(visibleIndices(3, 0).join(","), "0,1,2")
        compare(visibleIndices(3, 1).join(","), "0,1,2")
        compare(visibleIndices(4, 0).join(","), "0,1,2")
        compare(visibleIndices(4, 1).join(","), "0,1,2,3")
        compare(visibleIndices(4, 2).join(","), "0,1,2,3")
        compare(visibleIndices(4, 3).join(","), "1,2,3")
        compare(visibleIndices(12, 6).join(","), "4,5,6,7,8")
        verify(!Layout.visible(-1, 0, 4))
        verify(!Layout.visible(4, 0, 4))
        compare(Layout.visualDistance(0, -1, 4), -1)
    }

    function test_responsive_composition_clamps_at_several_widths() {
        for (const surfaceWidth of [480, 620, 1024, 1366, 1856]) {
            const dominant = preview(surfaceWidth, 600)
            const farWidth = widthAt(dominant, 2)
            const farOffset = Math.abs(offsetAt(4, 2, 6, dominant))
            const nearWidth = widthAt(dominant, 1)
            const composition = Layout.compositionWidth(dominant, farWidth,
                farOffset)

            verify(dominant > nearWidth)
            verify(nearWidth > farWidth)
            verify(composition <= surfaceWidth - 48,
                "composition overflow at width " + surfaceWidth)
        }

        const small = preview(620, 320)
        compare(small, 302)
        compare(Layout.previewHeight(small), 170)
        verify(Layout.previewHeight(small) <= 320 - 64)
    }

    function test_one_item_slot_is_centered() {
        const surfaceWidth = 1856
        const step = 360
        compare(Layout.edgeSpacer(surfaceWidth, step) + step / 2,
            surfaceWidth / 2)
        compare(widthAt(952, 0), 952)
        compare(offsetAt(0, 0, 1, 952), 0)
    }

    function test_lazy_sources_match_visible_depth() {
        verify(!Layout.sourceActive(0, -1, 0))
        verify(Layout.sourceActive(0, 0, 1))
        verify(Layout.sourceActive(1, 0, 2))
        for (let index = 0; index < 4; ++index)
            verify(Layout.sourceActive(index, 2, 4))

        let active = 0
        for (let index = 0; index < 40; ++index) {
            if (Layout.sourceActive(index, 20, 40))
                active++
        }
        compare(active, 5)
        verify(!Layout.sourceActive(17, 20, 40))
        verify(!Layout.sourceActive(23, 20, 40))
    }
}
