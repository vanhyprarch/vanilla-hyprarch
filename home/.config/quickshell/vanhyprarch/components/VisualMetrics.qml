import QtQuick

QtObject {
    // One global controller supplies the user preference. The fixed dock
    // remains 56 px; panel and control geometry scales with shell text.
    property int fontBaseSize: 12
    readonly property int fontReferenceSize: 12
    readonly property real fontScale: Math.max(1 / fontReferenceSize,
        fontBaseSize / fontReferenceSize)

    function scaled(baseValue: real): int {
        return Math.max(1, Math.round(baseValue * fontScale))
    }

    function fontPixels(multiplier: real): int {
        return Math.max(1, Math.round(fontBaseSize * multiplier))
    }

    // Dock geometry.
    readonly property int dockWidth: 56
    readonly property int dockLauncherTarget: 40
    readonly property int dockSystemControlTarget: 36
    readonly property int dockPowerButtonTarget: 40
    readonly property int dockSystemIconSize: 20
    readonly property int applicationLauncherIconSize: 28
    readonly property int dockContentWidth: 48
    readonly property int dockItemGap: 4
    readonly property int dockGroupGap: 8
    readonly property int dockSystemControlGap: 0
    readonly property int dockOuterInset: 12

    // Surface size classes.
    readonly property int standardPanelWidth: scaled(380)
    readonly property int actionSurfaceWidth: scaled(300)
    readonly property int compactActionSurfaceWidth: scaled(200)
    readonly property int wideOverlayMaximum: scaled(720)

    // Transitional value for surfaces that have not joined the square visual
    // foundation yet. Remove it after the later panel-normalization phases.
    readonly property int legacyPopupRadius: 10

    // Shared surface geometry.
    readonly property int panelRadius: 0
    readonly property int rowRadius: 0
    readonly property int panelPadding: scaled(14)
    readonly property int overlayPadding: scaled(18)
    readonly property int compactMenuPadding: scaled(10)
    readonly property int sectionGap: scaled(14)
    readonly property int contentGap: scaled(6)
    readonly property int rowSidePadding: scaled(10)
    readonly property int rowSpacing: scaled(3)
    readonly property int iconTextGap: scaled(10)
    readonly property int dockPopupGap: 9
    readonly property int dockPopupParallelOffset: -2
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
