import QtQuick

QtObject {
    // One global controller supplies the user preference. Screen-bound
    // instances size dock structure from physical density, then compact it
    // when the logical viewport cannot hold the normal layout. Typography
    // follows the preference and is not rewritten by either layout layer.
    property int fontBaseSize: 12
    property int viewportWidth: 0
    property int viewportHeight: 0
    property real physicalPixelDensity: 0
    readonly property int fontReferenceSize: 12
    readonly property real fontScale: Math.max(1 / fontReferenceSize,
        fontBaseSize / fontReferenceSize)
    // 11 mm preserves the approved 56-unit dock at 3840x2160, scale 1.25
    // on the measured host. No host density or mode is embedded here.
    readonly property real dockWidthMillimeters: 11
    readonly property int dockDesignWidth: 56
    readonly property real minimumPhysicalShellScale: 0.25
    readonly property real maximumPhysicalShellScale: 2
    readonly property real physicalShellScale: {
        const density = physicalPixelDensity
        if (!Number.isFinite(density) || density <= 0
                || viewportWidth <= 0 || viewportHeight <= 0)
            return 1

        // Qt's physical DPI is in device-independent units. Inferring the
        // monitor dimensions catches missing or clearly broken EDID data.
        const widthMm = viewportWidth / density
        const heightMm = viewportHeight / density
        if (!Number.isFinite(widthMm) || !Number.isFinite(heightMm)
                || widthMm < 100 || widthMm > 3000
                || heightMm < 60 || heightMm > 2000)
            return 1

        return Math.max(minimumPhysicalShellScale,
            Math.min(maximumPhysicalShellScale,
                dockWidthMillimeters * density / dockDesignWidth))
    }
    readonly property int normalShellMinimumWidth: 960
    readonly property int normalShellMinimumHeight: 720
    readonly property real minimumShellFitFactor: 0.75
    readonly property real shellFitFactor: {
        const widthFactor = viewportWidth > 0
            ? viewportWidth / normalShellMinimumWidth : 1
        const heightFactor = viewportHeight > 0
            ? viewportHeight / normalShellMinimumHeight : 1
        return Math.max(minimumShellFitFactor,
            Math.min(1, widthFactor, heightFactor))
    }

    function scaled(baseValue: real): int {
        return Math.max(1, Math.round(baseValue * fontScale))
    }

    function fontPixels(multiplier: real): int {
        return Math.max(1, Math.round(fontBaseSize * multiplier))
    }

    function fitted(baseValue: real, minimumValue: real): int {
        return Math.max(1, Math.round(minimumValue * physicalShellScale),
            Math.round(baseValue * physicalShellScale * shellFitFactor))
    }

    function physical(baseValue: real): int {
        return Math.max(1, Math.round(baseValue * physicalShellScale))
    }

    function dockTopRegionHeight(desiredHeight: real): int {
        return Math.min(Math.max(0, Math.round(desiredHeight)),
            Math.max(0, viewportHeight - dockEmergencySystemViewport))
    }

    function dockSystemRegionHeight(topHeight: real,
            desiredHeight: real): int {
        const maximumHeight = Math.max(0, viewportHeight
            - Math.max(0, topHeight))
        return Math.min(Math.max(0, Math.round(desiredHeight)), maximumHeight)
    }

    function dockLauncherRegionHeight(topHeight: real,
            systemHeight: real): int {
        return Math.max(0, viewportHeight - Math.max(0, topHeight)
            - Math.max(0, systemHeight))
    }

    // Dock geometry.
    readonly property int dockWidth: fitted(dockDesignWidth, 48)
    readonly property int dockLauncherTarget: fitted(40, 32)
    readonly property int dockSystemControlTarget: fitted(36, 28)
    readonly property int dockPowerButtonTarget: fitted(40, 32)
    readonly property int dockSystemIconSize: fitted(20, 16)
    readonly property int applicationLauncherIconSize: fitted(28, 22)
    readonly property int dockContentWidth: fitted(48, 40)
    readonly property int dockItemGap: fitted(4, 2)
    readonly property int dockGroupGap: fitted(8, 5)
    readonly property int dockSystemControlGap: 0
    readonly property int dockOuterInset: fitted(12, 8)
    readonly property int dockLogoSize: fitted(40, 30)
    readonly property int dockWorkspaceWidth: fitted(40, 34)
    readonly property int dockWorkspaceTarget: fitted(28, 21)
    readonly property int dockWorkspaceGap: fitted(1, 1)
    readonly property int dockWorkspaceLogoGap: fitted(13, 9)
    readonly property int dockWorkspaceFontSize: fitted(13, 11)
    readonly property int dockTrayTarget: fitted(32, 24)
    readonly property int dockTrayIconSize: fitted(22, 17)
    readonly property int dockTrayGap: fitted(2, 1)
    readonly property int dockPowerGlyphSize: fitted(24, 18)
    readonly property int dockAddGlyphSize: fitted(24, 18)
    readonly property int dockPowerGlyphHorizontalOffset: physical(1)
    readonly property int dockPowerGlyphVerticalOffset: physical(4)
    readonly property int dockLauncherMarkerWidth: physical(6)
    readonly property int dockLauncherMarkerHeight: physical(8)
    readonly property int dockLauncherMarkerFontSize: physical(8)
    readonly property int dockLauncherMarkerOverlap: physical(1)
    readonly property int dockLauncherDragIndicatorWidth: physical(24)
    readonly property int dockLauncherDragIndicatorHeight: physical(2)
    readonly property int dockClockLinePadding: physical(4)
    // Only used when the viewport cannot contain the complete top and bottom
    // stacks. It leaves one power-sized scroll viewport; it is not an estimate
    // of the normal bottom-region height.
    readonly property int dockEmergencySystemViewport: dockPowerButtonTarget
        + dockItemGap * 2

    // Surface size classes.
    readonly property int standardPanelWidth: scaled(380)
    readonly property int actionSurfaceWidth: scaled(300)
    readonly property int compactActionSurfaceWidth: scaled(200)
    readonly property int wideOverlayMaximum: scaled(720)
    readonly property int backgroundPickerMaximumWidth: scaled(1856)
    readonly property int backgroundPickerMaximumHeight: scaled(600)
    readonly property int backgroundPickerHorizontalPadding: scaled(24)
    readonly property int backgroundPickerVerticalPadding: scaled(32)
    readonly property int backgroundPreviewMaximumWidth: scaled(952)
    readonly property real backgroundPreviewDistanceOneScale: 0.76
    readonly property real backgroundPreviewDistanceTwoScale: 0.58
    readonly property real backgroundPreviewDistanceOneOffsetScale: 0.40
    readonly property real backgroundPreviewDistanceTwoOffsetScale: 0.655
    readonly property int backgroundPreviewLogicalStep: scaled(360)
    readonly property int backgroundPreviewOutlineThickness: 3

    // Shared surface geometry.
    readonly property int panelRadius: 0
    readonly property int rowRadius: 0
    readonly property int panelPadding: Math.max(scaled(9),
        Math.round(scaled(14) * shellFitFactor))
    readonly property int overlayPadding: scaled(18)
    readonly property int compactMenuPadding: scaled(10)
    readonly property int sectionGap: scaled(14)
    readonly property int contentGap: scaled(6)
    readonly property int rowSidePadding: scaled(10)
    readonly property int rowSpacing: scaled(3)
    readonly property int iconTextGap: scaled(10)
    readonly property int dockPopupGap: physical(9)
    readonly property int dockPopupParallelOffset: -physical(2)
    readonly property int panelViewportMargin: fitted(12, 8)
    readonly property int dockPanelMaximumWidth: viewportWidth > 0
        ? Math.max(1, viewportWidth - dockWidth - dockPopupGap
            - panelViewportMargin) : 16777215
    readonly property int dockPanelMaximumHeight: viewportHeight > 0
        ? Math.max(1, viewportHeight - panelViewportMargin * 2) : 16777215
    readonly property int panelOutlineThickness: 3
    readonly property int controlOutlineThickness: 1
    readonly property int separatorThickness: 1

    // Persistent vertical scroll position indicator.
    readonly property int scrollIndicatorWidth: scaled(3)
    readonly property int scrollIndicatorInset: scaled(2)
    readonly property int scrollIndicatorMinimumThumbHeight: scaled(24)
    readonly property int scrollIndicatorContentGap: scaled(6)
    readonly property int scrollIndicatorGutter: scrollIndicatorWidth
        + scrollIndicatorInset + scrollIndicatorContentGap
    readonly property real scrollOverflowTolerance: 0.5

    // Typography. The application keeps Qt's current system/default family.
    readonly property int captionFontSize: fontPixels(0.833)
    readonly property int detailFontSize: fontPixels(0.917)
    readonly property int bodyFontSize: fontPixels(1.0)
    readonly property int panelTitleFontSize: fontPixels(1.167)
    readonly property int overlayFontSize: fontPixels(1.333)
    readonly property int prominentValueFontSize: fontPixels(1.667)
    readonly property int sectionHeadingFontSize: captionFontSize
    readonly property int informationLabelFontSize: bodyFontSize
    readonly property int informationValueFontSize: bodyFontSize
    readonly property int panelTitleFontWeight: Font.Bold
    readonly property int overlayFontWeight: Font.Medium
    readonly property int sectionHeadingFontWeight: Font.Bold
    readonly property int informationLabelFontWeight: overlayFontWeight
    readonly property int informationValueFontWeight: Font.Normal

    // Rows and controls.
    readonly property int compactRowHeight: scaled(32)
    readonly property int compactActionRowHeight: scaled(40)
    readonly property int twoLineRowHeight: scaled(42)
    readonly property int navigationRowHeight: scaled(50)
    readonly property int detailedNavigationRowHeight: scaled(58)
    readonly property int compactControlHeight: scaled(28)
    readonly property int standardIconSize: scaled(18)
    readonly property int heroIconSize: scaled(24)
    readonly property int inlineActionButtonSize: scaled(22)
    readonly property int inlineActionIconSize: scaled(14)
    readonly property int inlineTextActionWidth: scaled(42)
    readonly property int inlineConfirmationActionWidth: scaled(49)
    readonly property int sliderHitHeight: scaled(20)
    readonly property int sliderTrackThickness: scaled(4)
    readonly property int sliderThumbSize: scaled(14)
    readonly property int sliderTrackRadius: Math.round(sliderTrackThickness / 2)
    readonly property int sliderThumbRadius: Math.round(sliderThumbSize / 2)
    readonly property int sliderNotchHeight: sliderTrackThickness * 2
    readonly property int toggleTrackWidth: scaled(42)
    readonly property int toggleKnobSize: scaled(16)
    readonly property int toggleKnobInset: scaled(3)
    readonly property int toggleTrackHeight: toggleKnobSize + toggleKnobInset * 2
    readonly property int textFieldHeight: scaled(30)
    readonly property int prominentValueHeight: scaled(34)
    readonly property int captionLineHeight: scaled(16)

    // State strengths. Theme owns the palette and derives the actual colors.
    readonly property real normalFillStrength: 0.04
    readonly property real hoverStrength: 0.08
    readonly property real activeStrength: 0.18
    readonly property real pressedStrength: 0.22
    readonly property real focusStrength: 0.25
    readonly property real separatorStrength: 0.12
    readonly property real disabledInteractiveOpacity: 0.40
    readonly property real informationalMutedOpacity: 0.60
    readonly property real secondaryControlDarkOpacity: 0.80
    readonly property real secondaryControlLightOpacity: 0.90
    readonly property real panelOutlineDarkMixStrength: 0.18
    readonly property real panelOutlineLightMixStrength: 0.50
}
