import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: testRoot

    property int checks: 0

    VisualMetrics { id: metrics }

    Theme {
        id: theme
        metrics: metrics
        darkMode: true
    }

    PanelActionRow {
        id: superSpaceRow
        width: 400
        metrics: metrics
        theme: theme
        primaryText: "Italian"
        navigationFill: theme.navigationFill
        selectionFill: theme.selectionFill
    }

    PanelActionRow {
        id: informationalRow
        width: 400
        metrics: metrics
        theme: theme
        primaryText: "Choose up to 3 languages"
        informational: true
    }

    PanelActionRow {
        id: disabledRow
        width: 400
        metrics: metrics
        theme: theme
        primaryText: "Unavailable"
        enabled: false
    }

    function fail(message): void {
        console.error("ROW_VISUALS_TEST_FAILURE: " + message)
        Qt.quit()
        throw new Error(message)
    }

    function verify(condition, message): void {
        checks++
        if (!condition)
            fail(message)
    }

    function equalColor(left, right): bool {
        return left.toString() === right.toString()
    }

    function run(): void {
        superSpaceRow.active = true
        superSpaceRow.keyboardSelected = true
        verify(equalColor(superSpaceRow.resolvedFill, theme.navigationFill),
            "navigation cursor does not override persistent selection")
        verify(equalColor(superSpaceRow.color, theme.navigationFill),
            "rendered row does not use navigation fill")
        verify(equalColor(superSpaceRow.fillForState(false, true, true,
                true, false), theme.navigationFill),
            "current state does not override hover and selection")
        verify(equalColor(superSpaceRow.fillForState(false, false, true,
                true, false), theme.hoverFill),
            "hover state does not override persistent selection")

        superSpaceRow.keyboardSelected = false
        verify(equalColor(superSpaceRow.resolvedFill, theme.selectionFill),
            "persistent selection was not revealed after cursor moved")
        verify(equalColor(superSpaceRow.color, theme.selectionFill),
            "rendered row does not use selection fill")

        superSpaceRow.active = false
        verify(superSpaceRow.resolvedFill.a === 0,
            "ordinary row has an unexpected fill")
        informationalRow.keyboardSelected = true
        disabledRow.keyboardSelected = true
        verify(!informationalRow.navigationCurrent,
            "informational row became navigable")
        verify(!disabledRow.navigationCurrent,
            "disabled row became navigable")
        verify(informationalRow.resolvedFill.a === 0,
            "informational row became highlighted")
        verify(disabledRow.resolvedFill.a === 0,
            "disabled row became highlighted")
        verify(disabledRow.opacity === metrics.disabledInteractiveOpacity,
            "disabled opacity changed")

        verify(metrics.rowRadius === 0,
            "navigation row radius is not rectangular")
        verify(superSpaceRow.radius === 0,
            "SuperSpace cursor is not rectangular")
        verify(equalColor(theme.navigationFill, theme.activeFill),
            "navigation role does not reuse the light active token")
        verify(equalColor(theme.selectionFill, theme.hoverFill),
            "selection role does not reuse the darker hover token")

        console.log("ROW_VISUALS_TEST_PASS checks=" + checks)
        Qt.quit()
    }

    Component.onCompleted: Qt.callLater(run)
}
