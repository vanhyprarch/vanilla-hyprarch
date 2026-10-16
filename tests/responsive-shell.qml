pragma ComponentBehavior: Bound

import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components"
import "../home/.config/quickshell/vanhyprarch/components/DockPopupGeometry.js" as DockGeometry

TestCase {
    id: testCase

    name: "ResponsiveShell"
    when: windowShown
    visible: true
    width: 1200
    height: 800

    property int backgroundDismissCount: 0
    property int controlActivationCount: 0
    property bool fixturePanelOpen: false

    VisualMetrics {
        id: largeMetrics
        fontBaseSize: 14
        viewportWidth: 3072
        viewportHeight: 1728
        physicalPixelDensity: 5.101176470588235
    }

    VisualMetrics {
        id: hdMetrics
        viewportWidth: 1920
        viewportHeight: 1080
        physicalPixelDensity: 3.1882352941176473
    }

    VisualMetrics {
        id: scaledHdMetrics
        viewportWidth: 960
        viewportHeight: 540
        physicalPixelDensity: 1.5941176470588236
    }

    VisualMetrics {
        id: fallbackMetrics
        viewportWidth: 1920
        viewportHeight: 1080
    }

    VisualMetrics {
        id: boundedMetrics
        viewportWidth: 3072
        viewportHeight: 1728
        physicalPixelDensity: 20
    }

    VisualMetrics {
        id: compactMetrics
        fontBaseSize: 14
        viewportWidth: 960
        viewportHeight: 540
    }

    VisualMetrics {
        id: smallMetrics
        fontBaseSize: 14
        viewportWidth: 800
        viewportHeight: 600
    }

    QtObject {
        id: theme
        property color background: "#202020"
        property color panelOutline: "#606060"
        property color textMuted: "#a0a0a0"
    }

    ScrollablePanelSurface {
        id: compactPanel
        x: 10
        y: 10
        width: Math.min(compactMetrics.standardPanelWidth,
            compactMetrics.dockPanelMaximumWidth)
        height: Math.min(700, compactMetrics.dockPanelMaximumHeight)
        metrics: compactMetrics
        theme: theme

        Column {
            width: parent.width

            Text {
                width: parent.width
                text: "Responsive panel wrapping geometry ".repeat(12)
                wrapMode: Text.Wrap
                height: implicitHeight
            }

            Rectangle {
                width: parent.width
                height: 700
            }
        }
    }

    Item {
        id: dockInputFixture

        x: 1000
        y: 100
        width: 120
        height: 300

        Flickable {
            anchors.fill: parent
            contentWidth: width
            contentHeight: height

            MouseArea {
                width: dockInputFixture.width
                height: dockInputFixture.height
                z: -1
                acceptedButtons: Qt.LeftButton
                onPressed: {
                    testCase.backgroundDismissCount += 1
                    testCase.fixturePanelOpen = false
                }
            }

            Rectangle {
                id: dockControlFixture

                x: 30
                y: 120
                width: 60
                height: 48

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        testCase.controlActivationCount += 1
                        testCase.fixturePanelOpen = !testCase.fixturePanelOpen
                    }
                }
            }
        }
    }

    Item {
        id: launcherAnchorFixture

        x: 80
        y: 160
        width: 60
        height: 480
        property Item contextSource: firstLauncher

        Flickable {
            id: anchorViewport

            y: 8
            width: parent.width
            height: parent.height - 16
            contentWidth: width
            contentHeight: Math.max(height, anchorContent.implicitHeight)
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: anchorContent

                anchors.verticalCenter: parent.verticalCenter
                width: anchorViewport.width
                spacing: 4

                Item {
                    id: firstLauncher
                    width: 40
                    height: 40
                }

                Item {
                    id: fixtureAddButton
                    width: 40
                    height: 40
                }

                Item {
                    id: secondLauncher
                    width: 40
                    height: 40
                }
            }
        }

        Item {
            id: appPickerAnchor

            parent: launcherAnchorFixture.parent
            y: launcherAnchorFixture.y + anchorViewport.y + anchorContent.y
                + fixtureAddButton.y - anchorViewport.contentY
            width: 40
            height: 40
        }

        Item {
            id: contextMenuAnchor

            parent: launcherAnchorFixture.parent
            y: launcherAnchorFixture.contextSource
                ? launcherAnchorFixture.y + anchorViewport.y + anchorContent.y
                    + launcherAnchorFixture.contextSource.y - anchorViewport.contentY
                : 0
            width: 40
            height: launcherAnchorFixture.contextSource
                ? launcherAnchorFixture.contextSource.height : 40
        }
    }

    ScrollablePanelSurface {
        id: largePanel
        x: 500
        y: 10
        width: largeMetrics.standardPanelWidth
        height: 500
        metrics: largeMetrics
        theme: theme

        Column {
            width: parent.width

            Rectangle {
                width: parent.width
                height: 300
            }
        }
    }

    function regionGeometry(metrics, topDesired, systemDesired) {
        const topHeight = metrics.dockTopRegionHeight(topDesired)
        const systemHeight = metrics.dockSystemRegionHeight(
            topHeight, systemDesired)
        const launcherHeight = metrics.dockLauncherRegionHeight(
            topHeight, systemHeight)
        return {
            topY: 0,
            topHeight: topHeight,
            launcherY: topHeight,
            launcherHeight: launcherHeight,
            systemY: metrics.viewportHeight - systemHeight,
            systemHeight: systemHeight,
            systemDesired: systemDesired
        }
    }

    function topDesiredHeight(metrics) {
        return metrics.dockOuterInset
            + metrics.dockLogoSize
            + metrics.dockWorkspaceLogoGap
            + metrics.dockWorkspaceTarget * 5
            + metrics.dockWorkspaceGap * 4
    }

    function clockDesiredHeight(metrics) {
        const weekdayFontSize = metrics.fitted(11, 10)
        return metrics.applicationLauncherIconSize
            + weekdayFontSize + metrics.dockClockLinePadding
            + (metrics.dockWorkspaceFontSize
                + metrics.dockClockLinePadding) * 2
            + metrics.dockItemGap * 3
    }

    function trayDesiredHeight(metrics, itemCount) {
        return itemCount <= 0 ? 0
            : metrics.dockTrayTarget * itemCount
                + metrics.dockTrayGap * (itemCount - 1)
    }

    function bottomDesiredHeight(metrics, bluetoothVisible, trayItemCount) {
        const trayHeight = trayDesiredHeight(metrics, trayItemCount)
        const systemControlCount = 6 + (bluetoothVisible ? 1 : 0)
        return trayHeight
            + (trayHeight > 0 ? metrics.dockGroupGap : 0)
            + metrics.dockSystemControlTarget * systemControlCount
            + metrics.dockSystemControlGap * 6
            + metrics.dockGroupGap
            + clockDesiredHeight(metrics)
            + metrics.dockGroupGap
            + metrics.dockPowerButtonTarget
            + metrics.dockOuterInset
    }

    function resetInputFixture() {
        backgroundDismissCount = 0
        controlActivationCount = 0
        fixturePanelOpen = false
    }

    function init() {
        launcherAnchorFixture.height = 480
        firstLauncher.height = 40
        anchorViewport.contentY = 0
        launcherAnchorFixture.contextSource = firstLauncher
    }

    function verifyAnchorMatchesSource(anchor, source) {
        tryVerify(function() {
            return Math.abs(anchor.y
                - source.mapToItem(anchor.parent, 0, 0).y) < 0.001
        })
    }

    function verifyLauncherCentering() {
        compare(anchorContent.parent, anchorViewport.contentItem)
        tryCompare(anchorViewport.contentItem, "height", anchorViewport.contentHeight)
        tryVerify(function() {
            const expected = Math.max(0,
                (anchorViewport.height - anchorContent.height) / 2)
            return Math.abs(anchorContent.y - expected) <= 0.5
        })
        if (anchorContent.height <= anchorViewport.height) {
            const below = anchorViewport.height - anchorContent.y - anchorContent.height
            verify(Math.abs(anchorContent.y - below) <= 1,
                "fitting launchers have unequal free space")
        }
    }

    function test_launcher_centering_data() {
        return [
            { tag: "roomy", height: 480 },
            { tag: "compact", height: 260 },
            { tag: "exact-fit", height: 144 },
            { tag: "overflow", height: 100 },
            { tag: "zero-viewport", height: 16 }
        ]
    }

    function test_launcher_centering(data) {
        launcherAnchorFixture.height = data.height
        verifyLauncherCentering()
    }

    function test_launcher_dynamic_height_and_overflow_return_to_center() {
        verifyLauncherCentering()
        launcherAnchorFixture.height = 100
        verifyLauncherCentering()
        anchorViewport.contentY = anchorViewport.contentHeight - anchorViewport.height
        verify(anchorViewport.atYEnd)
        launcherAnchorFixture.height = 480
        tryCompare(anchorViewport, "contentY", 0)
        verifyLauncherCentering()
        firstLauncher.height = 80
        tryCompare(anchorContent, "height", 168)
        verifyLauncherCentering()
        firstLauncher.height = 40
        tryCompare(anchorContent, "height", 128)
        verifyLauncherCentering()
    }

    function test_appPicker_anchor_initial_wide_placement() {
        verify(anchorContent.y > 0, "launcher fixture is not centered")
        verifyAnchorMatchesSource(appPickerAnchor, fixtureAddButton)
        compare(appPickerAnchor.y, launcherAnchorFixture.y + anchorViewport.y
            + anchorContent.y + fixtureAddButton.y)
        const topMargin = DockGeometry.alignedTopMargin(appPickerAnchor.y,
            4, 360, 1728, 12)
        compare(topMargin, appPickerAnchor.y - 4)
        verify(topMargin !== DockGeometry.aboveMargin(appPickerAnchor.y,
            appPickerAnchor.height, -2, 360, 1728, 12),
            "picker still uses bottom alignment")
    }

    function test_appPicker_anchor_tracks_responsive_relayout() {
        const initialY = appPickerAnchor.y
        launcherAnchorFixture.height = 260
        verifyAnchorMatchesSource(appPickerAnchor, fixtureAddButton)
        verify(appPickerAnchor.y !== initialY,
            "recentered launcher did not move the picker anchor")

        launcherAnchorFixture.height = 100
        verifyAnchorMatchesSource(appPickerAnchor, fixtureAddButton)
        compare(anchorContent.y, 0)
    }

    function test_appPicker_anchor_tracks_scroll() {
        launcherAnchorFixture.height = 100
        anchorViewport.contentY = 20
        compare(anchorViewport.contentY, 20)
        verifyAnchorMatchesSource(appPickerAnchor, fixtureAddButton)
    }

    function test_popup_anchors_track_launcher_position_changes() {
        launcherAnchorFixture.contextSource = secondLauncher
        const initialPickerY = appPickerAnchor.y
        const initialContextY = contextMenuAnchor.y
        firstLauncher.height = 60
        tryVerify(function() {
            return appPickerAnchor.y !== initialPickerY
                && contextMenuAnchor.y !== initialContextY
        })
        verifyAnchorMatchesSource(appPickerAnchor, fixtureAddButton)
        verifyAnchorMatchesSource(contextMenuAnchor, secondLauncher)
    }

    function test_context_menu_anchor_tracks_source_and_retargeting() {
        verifyAnchorMatchesSource(contextMenuAnchor, firstLauncher)
        launcherAnchorFixture.contextSource = secondLauncher
        verifyAnchorMatchesSource(contextMenuAnchor, secondLauncher)
        compare(contextMenuAnchor.height, secondLauncher.height)
        launcherAnchorFixture.contextSource = null
        compare(contextMenuAnchor.y, 0)
    }

    function test_context_menu_anchor_tracks_relayout_and_scroll() {
        launcherAnchorFixture.contextSource = secondLauncher
        launcherAnchorFixture.height = 260
        verifyAnchorMatchesSource(contextMenuAnchor, secondLauncher)

        launcherAnchorFixture.height = 100
        anchorViewport.contentY = 20
        compare(anchorViewport.contentY, 20)
        verifyAnchorMatchesSource(contextMenuAnchor, secondLauncher)
    }

    function test_empty_region_dismisses_without_swallowing_controls() {
        resetInputFixture()
        fixturePanelOpen = true

        mouseClick(dockInputFixture, 10, 10, Qt.LeftButton)
        compare(backgroundDismissCount, 1)
        verify(!fixturePanelOpen)

        mouseClick(dockControlFixture,
            dockControlFixture.width / 2, dockControlFixture.height / 2,
            Qt.LeftButton)
        compare(controlActivationCount, 1)
        compare(backgroundDismissCount, 1)
        verify(fixturePanelOpen)

        mouseClick(dockControlFixture,
            dockControlFixture.width / 2, dockControlFixture.height / 2,
            Qt.LeftButton)
        compare(controlActivationCount, 2)
        compare(backgroundDismissCount, 1)
        verify(!fixturePanelOpen)
    }

    function test_large_viewport_preserves_standard_metrics() {
        compare(largeMetrics.shellFitFactor, 1)
        verify(Math.abs(largeMetrics.physicalShellScale - 1) < 0.003)
        compare(largeMetrics.dockWidth, 56)
        compare(largeMetrics.dockLauncherTarget, 40)
        compare(largeMetrics.dockSystemControlTarget, 36)
        compare(largeMetrics.dockPowerButtonTarget, 40)
        compare(largeMetrics.dockSystemIconSize, 20)
        compare(largeMetrics.applicationLauncherIconSize, 28)
        compare(largeMetrics.dockItemGap, 4)
        compare(largeMetrics.dockGroupGap, 8)
        compare(largeMetrics.dockOuterInset, 12)
        compare(largeMetrics.standardPanelWidth, 443)
        compare(largeMetrics.panelPadding, 16)
    }

    function test_same_monitor_mode_change_preserves_physical_width() {
        compare(hdMetrics.shellFitFactor, 1)
        compare(hdMetrics.dockWidth, 35)
        verify(Math.abs(largeMetrics.dockWidth
            / largeMetrics.physicalPixelDensity
            - hdMetrics.dockWidth / hdMetrics.physicalPixelDensity) < 0.1)
        compare(hdMetrics.dockLauncherTarget, 25)
        compare(hdMetrics.applicationLauncherIconSize, 18)
        compare(hdMetrics.dockSystemControlTarget, 23)
        compare(hdMetrics.dockWorkspaceTarget, 18)
        compare(hdMetrics.dockPopupGap, 6)
        compare(hdMetrics.dockPowerGlyphSize, 15)
        compare(hdMetrics.dockAddGlyphSize, 15)
        compare(hdMetrics.dockLauncherMarkerWidth, 4)
    }

    function test_scaled_hd_keeps_physical_sizing_before_compaction() {
        verify(Math.abs(scaledHdMetrics.physicalShellScale * 56 - 17.5) < 0.1)
        compare(scaledHdMetrics.shellFitFactor, 0.75)
        verify(scaledHdMetrics.dockWidth <= 18)
        verify(scaledHdMetrics.dockWidth >= 12)
        verify(scaledHdMetrics.dockLauncherTarget < hdMetrics.dockLauncherTarget)
        verify(scaledHdMetrics.dockSystemControlTarget
            < hdMetrics.dockSystemControlTarget)
        verify(scaledHdMetrics.dockWorkspaceTarget < hdMetrics.dockWorkspaceTarget)
        verify(scaledHdMetrics.dockContentWidth <= scaledHdMetrics.dockWidth)
        const geometry = regionGeometry(scaledHdMetrics,
            topDesiredHeight(scaledHdMetrics),
            bottomDesiredHeight(scaledHdMetrics, true, 2))
        verify(geometry.topHeight + geometry.systemHeight
            <= scaledHdMetrics.viewportHeight)
        compare(geometry.launcherY + geometry.launcherHeight,
            geometry.systemY)
        compare(geometry.systemY + geometry.systemHeight,
            scaledHdMetrics.viewportHeight)
    }

    function test_text_size_does_not_change_physical_dock() {
        const width = hdMetrics.dockWidth
        const target = hdMetrics.dockLauncherTarget
        const icon = hdMetrics.dockSystemIconSize
        const addGlyph = hdMetrics.dockAddGlyphSize
        hdMetrics.fontBaseSize = 20
        compare(hdMetrics.dockWidth, width)
        compare(hdMetrics.dockLauncherTarget, target)
        compare(hdMetrics.dockSystemIconSize, icon)
        compare(hdMetrics.dockAddGlyphSize, addGlyph)
        compare(hdMetrics.bodyFontSize, 20)
    }

    function test_density_fallback_and_bound() {
        const invalid = [0, -1, Number.NaN, Number.POSITIVE_INFINITY, 1000]
        for (const density of invalid) {
            fallbackMetrics.physicalPixelDensity = density
            compare(fallbackMetrics.physicalShellScale, 1)
            compare(fallbackMetrics.dockWidth, 56)
        }
        compare(boundedMetrics.physicalShellScale, 2)
        compare(boundedMetrics.dockWidth, 112)
        fallbackMetrics.viewportWidth = 960
        fallbackMetrics.viewportHeight = 540
        fallbackMetrics.physicalPixelDensity = 1
        compare(fallbackMetrics.physicalShellScale, 0.25)
        verify(fallbackMetrics.dockWidth < 56)
        fallbackMetrics.physicalPixelDensity = 1.5941176470588236
        verify(fallbackMetrics.dockWidth <= 18)
        fallbackMetrics.viewportWidth = 1920
        fallbackMetrics.viewportHeight = 1080
        fallbackMetrics.physicalPixelDensity = 3.1882352941176473
        compare(fallbackMetrics.dockWidth, 35)
    }

    function test_large_viewport_reserves_complete_bottom_stack() {
        const topDesired = topDesiredHeight(largeMetrics)
        const bottomDesired = bottomDesiredHeight(largeMetrics, true, 2)
        const geometry = regionGeometry(largeMetrics,
            topDesired, bottomDesired)

        compare(geometry.topHeight, topDesired)
        compare(geometry.systemHeight, bottomDesired)
        verify(geometry.systemHeight > 0)
        compare(geometry.systemY + geometry.systemHeight,
            largeMetrics.viewportHeight)

        const powerBottom = largeMetrics.viewportHeight
            - largeMetrics.dockOuterInset
        const powerTop = powerBottom - largeMetrics.dockPowerButtonTarget
        verify(powerTop >= geometry.systemY,
            "PowerMenu is outside the complete bottom viewport")
        verify(powerBottom <= largeMetrics.viewportHeight)

        const systemControlsTop = geometry.systemY
            + trayDesiredHeight(largeMetrics, 2)
            + largeMetrics.dockGroupGap
        verify(systemControlsTop >= geometry.systemY)
        verify(systemControlsTop
            + largeMetrics.dockSystemControlTarget * 7
            <= powerTop,
            "system controls are outside the complete bottom viewport")
        compare(geometry.launcherY + geometry.launcherHeight,
            geometry.systemY)
    }

    function test_960x540_regions_are_disjoint_and_bounded() {
        compare(compactMetrics.shellFitFactor, 0.75)
        const topDesired = topDesiredHeight(compactMetrics)
        const bottomDesired = bottomDesiredHeight(compactMetrics, true, 0)
        const geometry = regionGeometry(compactMetrics,
            topDesired, bottomDesired)

        compare(geometry.topHeight, topDesired)
        compare(geometry.systemHeight, bottomDesired)
        verify(geometry.launcherHeight > 0)
        verify(geometry.topY + geometry.topHeight
            <= geometry.launcherY)
        verify(geometry.launcherY + geometry.launcherHeight
            <= geometry.systemY)
        verify(geometry.systemY + geometry.systemHeight
            <= compactMetrics.viewportHeight)
    }

    function test_launcher_overflow_shrinks_before_bottom_region() {
        const topDesired = topDesiredHeight(compactMetrics)
        const bottomDesired = bottomDesiredHeight(compactMetrics, true, 0)
        const geometry = regionGeometry(compactMetrics,
            topDesired, bottomDesired)
        const launcherContentHeight = 900

        verify(geometry.launcherHeight > 0)
        compare(geometry.systemHeight, bottomDesired,
            "launcher demand reduced the complete bottom region")
        verify(launcherContentHeight > geometry.launcherHeight,
            "launcher fixture does not exercise overflow")
        verify(geometry.launcherY + geometry.launcherHeight
            <= geometry.systemY)
    }

    function test_extreme_bottom_overflow_remains_reachable() {
        const topDesired = topDesiredHeight(compactMetrics)
        const bottomDesired = bottomDesiredHeight(compactMetrics, true, 20)
        const geometry = regionGeometry(compactMetrics,
            topDesired, bottomDesired)

        verify(geometry.systemHeight > 0,
            "extreme viewport made the bottom region disappear")
        verify(geometry.systemHeight < bottomDesired,
            "fixture does not exercise bottom overflow")
        compare(geometry.launcherHeight, 0,
            "launcher did not yield before bottom overflow")
        compare(geometry.launcherY, geometry.systemY)
        compare(geometry.systemY + geometry.systemHeight,
            compactMetrics.viewportHeight)
    }

    function test_constrained_panel_is_bounded_and_scrollable() {
        compare(compactMetrics.dockPanelMaximumHeight, 522)
        verify(compactPanel.width
            <= compactMetrics.viewportWidth - compactMetrics.dockWidth)
        verify(compactPanel.height <= compactMetrics.dockPanelMaximumHeight)
        verify(compactPanel.contentScrollable,
            "overflowing dock panel did not enable internal scrolling")
    }

    function test_large_panel_keeps_normal_size_without_scrolling() {
        compare(largePanel.width, largeMetrics.standardPanelWidth)
        compare(largePanel.height, 500)
        verify(!largePanel.contentScrollable)
    }

    function test_text_size_is_not_changed_by_viewport_updates() {
        compare(smallMetrics.fontBaseSize, 14)
        smallMetrics.viewportWidth = 720
        smallMetrics.viewportHeight = 480
        compare(smallMetrics.fontBaseSize, 14)
        compare(smallMetrics.bodyFontSize, 14)
        compare(smallMetrics.shellFitFactor,
            smallMetrics.minimumShellFitFactor)
    }

    function test_compact_targets_keep_functional_minimums() {
        verify(compactMetrics.dockLauncherTarget >= 32)
        verify(compactMetrics.dockSystemControlTarget >= 28)
        verify(compactMetrics.dockPowerButtonTarget >= 32)
        verify(compactMetrics.dockSystemIconSize >= 16)
        verify(smallMetrics.dockSystemControlTarget >= 28)
    }
}
