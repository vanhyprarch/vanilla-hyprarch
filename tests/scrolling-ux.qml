pragma ComponentBehavior: Bound

import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components"

TestCase {
    id: testCase

    name: "ScrollingUx"
    when: windowShown
    visible: true
    width: 760
    height: 620

    property int indicatorAreaClicks: 0
    property int activatedIndex: -1

    VisualMetrics {
        id: metrics
    }

    QtObject {
        id: theme
        property color textMuted: "#888888"
    }

    Flickable {
        id: indicatorView

        x: 350
        y: 0
        width: 300
        height: 200
        contentWidth: width
        contentHeight: 400
        boundsBehavior: Flickable.StopAtBounds

        MouseArea {
            width: indicatorView.width
            height: indicatorView.height
            onClicked: testCase.indicatorAreaClicks += 1
        }

        Item {
            id: gutterRow
            width: indicatorView.width - indicator.reservedWidth
            height: 20
        }

        VerticalScrollIndicator {
            id: indicator
            view: indicatorView
            metrics: metrics
            theme: theme
        }
    }

    ListModel {
        id: navigationModel
    }

    ListView {
        id: navigationView

        x: 350
        y: 300
        width: 240
        height: 60
        clip: true
        model: navigationModel
        currentIndex: 0
        focus: true

        Keys.onReturnPressed: testCase.activatedIndex = currentIndex

        delegate: Rectangle {
            required property int index
            width: navigationView.width
            height: 30
        }

        WrappedListNavigation {
            id: navigation
            view: navigationView
            isSelectable: function(index) {
                return navigationModel.get(index).selectable
            }
        }
    }

    function populateNavigation(selectableValues) {
        navigationModel.clear()
        for (let index = 0; index < selectableValues.length; ++index) {
            navigationModel.append({
                label: "Row " + index,
                selectable: selectableValues[index]
            })
        }
        wait(0)
    }

    function resetIndicator() {
        metrics.fontBaseSize = 12
        indicatorView.height = 200
        indicatorView.contentHeight = 400
        indicatorView.contentY = 0
        indicatorAreaClicks = 0
        wait(0)
    }

    function init() {
        resetIndicator()
        populateNavigation([true, true, true, true, true])
        navigationView.currentIndex = 0
        navigationView.positionViewAtBeginning()
        activatedIndex = -1
        wait(0)
    }

    function fuzzyCompare(actual, expected, message) {
        verify(Math.abs(actual - expected) < 0.01,
            message + ": expected " + expected + ", got " + actual)
    }

    function test_indicator_visibility_and_proportional_height() {
        verify(indicator.visible, "visible=" + indicator.visible
            + " scrollable=" + indicator.scrollable
            + " contentHeight=" + indicatorView.contentHeight
            + " viewHeight=" + indicatorView.height
            + " indicatorHeight=" + indicator.height)
        fuzzyCompare(indicator.thumbHeight, 98,
            "half-visible content should use half the track")

        indicatorView.contentHeight = 200.4
        wait(0)
        verify(!indicator.visible)

        indicatorView.contentHeight = 200.6
        wait(0)
        verify(indicator.visible, "visible=" + indicator.visible
            + " scrollable=" + indicator.scrollable
            + " contentHeight=" + indicatorView.contentHeight
            + " viewHeight=" + indicatorView.height
            + " indicatorHeight=" + indicator.height)
    }

    function test_indicator_top_middle_and_bottom_positions() {
        indicatorView.contentY = 0
        wait(0)
        fuzzyCompare(indicator.thumbY, 2, "top thumb position")

        indicatorView.contentY = 100
        wait(0)
        fuzzyCompare(indicator.thumbY, 51, "middle thumb position")

        indicatorView.contentY = 200
        wait(0)
        fuzzyCompare(indicator.thumbY, 100, "bottom thumb position")
    }

    function test_indicator_minimum_and_dynamic_sizes() {
        indicatorView.contentHeight = 10000
        wait(0)
        compare(indicator.thumbHeight,
            metrics.scrollIndicatorMinimumThumbHeight)

        indicatorView.contentHeight = 400
        wait(0)
        fuzzyCompare(indicator.thumbHeight, 98,
            "content-size update did not update thumb")

        indicatorView.height = 250
        wait(0)
        fuzzyCompare(indicator.thumbHeight, 153.75,
            "viewport-size update did not update thumb")

        indicatorView.contentHeight = 10000
        metrics.fontBaseSize = 18
        wait(0)
        compare(indicator.thumbHeight, 36)
        compare(indicator.reservedWidth, 17)
    }

    function test_indicator_is_input_transparent_and_gutter_is_stable() {
        const rowWidth = gutterRow.width
        indicatorView.contentHeight = indicatorView.height
        wait(0)
        compare(gutterRow.width, rowWidth)
        verify(!indicator.visible)

        indicatorView.contentHeight = 400
        wait(0)
        compare(gutterRow.width, rowWidth)
        verify(indicator.visible)

        mouseClick(indicatorView, indicatorView.width - 2, 10,
            Qt.LeftButton)
        compare(indicatorAreaClicks, 1)
    }

    function test_navigation_wraps_and_moves_normally() {
        navigationView.currentIndex = 0
        verify(navigation.move(-1))
        compare(navigationView.currentIndex, 4)
        verify(navigationView.contentY > navigationView.originY)

        verify(navigation.move(1))
        compare(navigationView.currentIndex, 0)

        navigationView.currentIndex = 2
        verify(navigation.move(1))
        compare(navigationView.currentIndex, 3)
        verify(navigation.move(-1))
        compare(navigationView.currentIndex, 2)
    }

    function test_navigation_zero_one_and_disabled_rows() {
        populateNavigation([])
        verify(!navigation.move(1))
        compare(navigationView.currentIndex, -1)

        populateNavigation([true])
        navigationView.currentIndex = 0
        verify(navigation.move(-1))
        compare(navigationView.currentIndex, 0)
        verify(navigation.move(1))
        compare(navigationView.currentIndex, 0)

        populateNavigation([true, false, false, true])
        navigationView.currentIndex = 0
        verify(navigation.move(1))
        compare(navigationView.currentIndex, 3)
        verify(navigation.move(1))
        compare(navigationView.currentIndex, 0)

        populateNavigation([false, false])
        navigationView.currentIndex = 0
        verify(!navigation.move(1))
        compare(navigationView.currentIndex, -1)
    }

    function test_navigation_invalid_index_and_filtered_results() {
        navigationView.currentIndex = -1
        verify(navigation.move(1))
        compare(navigationView.currentIndex, 0)

        navigationView.currentIndex = -1
        verify(navigation.move(-1))
        compare(navigationView.currentIndex, 4)

        // Replacing the model represents the currently visible filtered set.
        populateNavigation([true, true, true])
        navigationView.currentIndex = 0
        verify(navigation.move(-1))
        compare(navigationView.currentIndex, 2)
    }

    function test_navigation_activation_after_wrap_and_page_clamping() {
        navigationView.currentIndex = 0
        verify(navigation.move(-1))
        navigationView.forceActiveFocus()
        keyClick(Qt.Key_Return)
        compare(activatedIndex, 4)

        verify(navigation.moveClamped(-100))
        compare(navigationView.currentIndex, 0)
        verify(navigation.moveClamped(100))
        compare(navigationView.currentIndex, 4)
    }
}
