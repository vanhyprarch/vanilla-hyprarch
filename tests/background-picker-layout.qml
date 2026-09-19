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

    function rectAt(index, currentIndex, count) {
        return Layout.cardRect(index, currentIndex, count, 1856, 600, 952,
            distanceOneScale, distanceTwoScale, distanceOneOffsetScale,
            distanceTwoOffsetScale)
    }

    function topmostAt(x, y, currentIndex, count) {
        return Layout.topmostCardAt(x, y, currentIndex, count, 1856, 600,
            952, distanceOneScale, distanceTwoScale,
            distanceOneOffsetScale, distanceTwoOffsetScale)
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

    function test_depth_order() {
        compare(Layout.cardZ(0), 30)
        compare(Layout.cardZ(1), 20)
        compare(Layout.cardZ(2), 10)
        verify(Layout.cardZ(0) > Layout.cardZ(1))
        verify(Layout.cardZ(1) > Layout.cardZ(2))
    }

    function test_painted_rectangles_and_pointer_hit_regions_match() {
        const current = rectAt(2, 2, 6)
        const near = rectAt(3, 2, 6)
        const far = rectAt(4, 2, 6)

        compare(current.x, 452)
        compare(current.y, 32)
        compare(current.width, 952)
        compare(current.height, 536)
        compare(near.x, 947)
        compare(near.y, 97)
        compare(near.width, 724)
        compare(near.height, 407)
        compare(far.x, 1276)
        compare(far.y, 145)
        compare(far.width, 552)
        compare(far.height, 311)

        compare(topmostAt(900, 300, 2, 6), 2,
            "current visible card is not an inside target")
        compare(topmostAt(1500, 100, 2, 6), 3,
            "exposed distance-1 card is not an inside target")
        compare(topmostAt(1750, 300, 2, 6), 4,
            "exposed distance-2 card is not an inside target")

        compare(topmostAt(1450, 50, 2, 6), -1,
            "space above distance 1 retained an invisible hit rectangle")
        compare(topmostAt(1450, 550, 2, 6), -1,
            "space below distance 1 retained an invisible hit rectangle")
        compare(topmostAt(1700, 100, 2, 6), -1,
            "space above distance 2 retained an invisible hit rectangle")
        compare(topmostAt(1700, 500, 2, 6), -1,
            "space below distance 2 retained an invisible hit rectangle")
        compare(topmostAt(10, 10, 2, 6), -1,
            "transparent carousel space remained an inside target")

        compare(topmostAt(1000, 300, 2, 6), 2,
            "current did not win its overlap with distance 1")
        compare(topmostAt(1500, 300, 2, 6), 3,
            "distance 1 did not win its overlap with distance 2")

        compare(topmostAt(300, 100, 2, 6), 1,
            "exposed left distance-1 card is not an inside target")
        compare(topmostAt(50, 300, 2, 6), 0,
            "exposed left distance-2 card is not an inside target")
        compare(topmostAt(400, 50, 2, 6), -1,
            "space above left distance 1 retained an invisible hit rectangle")
        compare(topmostAt(300, 300, 2, 6), 1,
            "left distance 1 did not win its overlap with distance 2")
    }

    function test_visible_sources_survive_every_depth_transition() {
        const uri = "file:///wallpaper.png"
        const sourceFor = function(index, currentIndex) {
            return Layout.sourceActive(index, currentIndex, 7) ? uri : ""
        }

        compare(sourceFor(2, 0), uri)
        compare(sourceFor(2, 1), uri)
        compare(sourceFor(2, 2), uri)
        compare(sourceFor(2, 3), uri)
        compare(sourceFor(2, 4), uri)

        for (const transition of [[0, 1], [1, 2], [2, 1], [1, 0]]) {
            const oldCurrent = transition[0]
            const newCurrent = transition[1]
            for (let index = 0; index < 5; ++index) {
                if (Layout.sourceActive(index, oldCurrent, 7)
                        && Layout.sourceActive(index, newCurrent, 7)) {
                    compare(sourceFor(index, oldCurrent), uri)
                    compare(sourceFor(index, newCurrent), uri)
                }
            }
        }
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
