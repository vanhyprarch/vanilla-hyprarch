import QtQuick

QtObject {
    required property var metrics
    property bool darkMode: false

    readonly property color background: darkMode ? "#1C1714" : "#FFF8F5"
    readonly property color surface: darkMode ? "#302E2D" : "#ECEAE9"
    readonly property color text: darkMode ? "#F4F4F3" : "#3A3A3A"
    readonly property color control: text
    readonly property color brandAccent: darkMode ? "#C07A52" : "#8D4C2B"
    // Legacy callers remain neutral until they consume the explicit roles.
    readonly property color accent: control
    readonly property color danger: darkMode ? "#E06C5F" : "#A33A32"

    function withAlpha(color, alpha): color {
        return Qt.rgba(color.r, color.g, color.b, alpha)
    }

    function mixOpaque(base, foreground, strength): color {
        const inverse = 1.0 - strength
        return Qt.rgba(base.r * inverse + foreground.r * strength,
            base.g * inverse + foreground.g * strength,
            base.b * inverse + foreground.b * strength, 1.0)
    }

    readonly property color textMuted: withAlpha(text,
        metrics.informationalMutedOpacity)
    readonly property color secondaryControl: withAlpha(text, darkMode
        ? metrics.secondaryControlDarkOpacity
        : metrics.secondaryControlLightOpacity)
    readonly property color toggleKnob: secondaryControl
    readonly property color onAccent: background
    readonly property color separator: withAlpha(text,
        metrics.separatorStrength)
    readonly property color panelOutline: mixOpaque(surface, text, darkMode
        ? metrics.panelOutlineDarkMixStrength
        : metrics.panelOutlineLightMixStrength)
    readonly property color focus: withAlpha(text, metrics.focusStrength)
    readonly property color disabled: withAlpha(text,
        metrics.disabledInteractiveOpacity)
    readonly property color onDanger: background

    readonly property color normalFill: withAlpha(text,
        metrics.normalFillStrength)
    readonly property color hoverFill: withAlpha(text, metrics.hoverStrength)
    readonly property color activeFill: withAlpha(text, metrics.activeStrength)
    readonly property color pressedFill: withAlpha(text,
        metrics.pressedStrength)
    readonly property color dangerFill: withAlpha(danger,
        metrics.pressedStrength)
    readonly property color navigationFill: activeFill
    readonly property color selectionFill: hoverFill

    // Retained until legacy surfaces consume the state roles directly.
    readonly property color hover: hoverFill
}
