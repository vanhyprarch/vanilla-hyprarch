#!/bin/sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
components=$repository/home/.config/quickshell/vanhyprarch/components
panel=$components/MonitorPanel.qml
controller=$components/MonitorController.qml
confirmation=$components/MonitorConfirmationPanel.qml
shell=$repository/home/.config/quickshell/vanhyprarch/shell.qml

fail()
{
    printf '%s\n' "Monitor UI test failure: $1" >&2
    exit 1
}

grep -Fq 'Hyprland.monitorFor(root.targetScreen)' "$panel" \
    || fail 'panel does not map its own ShellScreen'
if grep -Fq 'Hyprland.focusedMonitor' "$panel"; then
    fail 'focusedMonitor still selects the edited output'
fi
if grep -Fq 'lastIpcObject' "$panel"; then
    fail 'panel duplicates raw Hyprland monitor parsing'
fi
if grep -Eq 'scaleEditScript|quickshell-scale-edit|machine/hyprland.lua' "$panel"; then
    fail 'legacy inline Scale persistence remains in QML'
fi
grep -Fq '[root.backendCommand, "inspect"]' "$controller" \
    || fail 'controller has no read-only inspection client'
grep -Fq '[root.backendCommand, "scale", "--connector"' "$controller" \
    || fail 'Scale does not use the immediate backend path'
grep -Fq '[root.backendCommand, "materialize", "--connector"' "$controller" \
    || fail 'advanced display enablement lacks a dedicated backend operation'
grep -Fq 'Enable advanced display settings' "$panel" \
    || fail 'fallback-managed output lacks explicit advanced-settings action'
grep -Fq 'Your current display settings should not change.' "$panel" \
    || fail 'materialization copy implies the working display needs initialization'
grep -Fq 'label: "Forced HDR"' "$panel" \
    || fail 'per-monitor HDR policy row is missing'
grep -Fq 'label: "Automatic HDR"' "$panel" \
    || fail 'Automatic HDR label is missing from the panel'
grep -Fq 'detailLabel: "All displays"' "$panel" \
    || fail 'global Automatic HDR scope is not visible beneath its label'
grep -Fq 'font.pixelSize: root.metrics.captionFontSize' "$panel" \
    || fail 'global Automatic HDR scope does not use the smaller caption size'
grep -Fq 'const labels = ["Off", "On", "On (EDID)"]' "$panel" \
    || fail 'Automatic HDR labels do not match the approved product language'
grep -Fq 'command.push("--hdr", pending.hdr_mode)' "$controller" \
    || fail 'pending forced HDR is absent from combined Safe Apply'
grep -Fq 'command.push("--automatic-hdr", String(root.pendingAutomaticHdr))' \
    "$controller" \
    || fail 'pending global Automatic HDR is absent from combined Safe Apply'
grep -Fq 'Forced HDR On requires selecting 10-bit Color Depth' "$controller" \
    || fail 'controller does not block illegal 8-bit forced HDR'
grep -Fq 'interval: 1000' "$controller" \
    || fail 'active transaction reconciliation lacks bounded polling'
grep -Fq 'running: root.transactionInFlight && root.checksEnabled' "$controller" \
    || fail 'status polling is not limited to an active backend transaction'
grep -Fq 'Hyprland.refreshMonitors()' "$controller" \
    || fail 'terminal operations do not refresh Quickshell monitor projections'
if grep -Fq 'id: displayReadouts' "$panel"; then
    fail 'duplicate read-only Monitor summary is still present'
fi
for label in 'Resolution' 'Refresh rate' 'Color depth'; do
    if [ "$(grep -F -c "label: \"$label\"" "$panel")" -ne 1 ]; then
        fail "$label does not have exactly one editable row"
    fi
done
grep -Fq 'value: root.pendingResolutionText()' "$panel" \
    || fail 'Resolution no longer projects pending/current selection'
grep -Fq 'value: root.pendingRefreshText()' "$panel" \
    || fail 'Refresh rate no longer projects pending/current selection'
grep -Fq 'value: root.pendingBitdepthText()' "$panel" \
    || fail 'Color depth no longer projects pending/current selection'

grep -Fq 'CenteredOverlay {' "$confirmation" \
    || fail 'confirmation bypasses the central overlay architecture'
grep -Fq 'event.key === Qt.Key_Escape' "$confirmation" \
    || fail 'Escape is not handled'
grep -Fq 'root.controller.requestRevert()' "$confirmation" \
    || fail 'Escape/outside dismissal does not Revert'
grep -Fq 'root.controller.requestConfirm()' "$confirmation" \
    || fail 'Keep does not Confirm'
grep -Fq 'Math.ceil(root.controller.presentationRemainingSeconds)' "$confirmation" \
    || fail 'countdown is not backend-sampled presentation state'
if grep -Fq 'implicitHeight: 248' "$confirmation"; then
    fail 'confirmation still reserves an unexplained fixed height'
fi
grep -Fq 'implicitHeight: contentColumn.implicitHeight + contentPadding * 2' \
    "$confirmation" \
    || fail 'confirmation height does not follow content with symmetric padding'
grep -Fq 'wrapMode: Text.WordWrap' "$confirmation" \
    || fail 'realistic long confirmation descriptions cannot grow the overlay'
grep -Fq 'anchors.horizontalCenter: parent.horizontalCenter' "$confirmation" \
    || fail 'confirmation actions are not centered'
grep -Fq 'width: root.actionButtonWidth * 2 + spacing' "$confirmation" \
    || fail 'confirmation action row does not follow the two compact buttons'
[ "$(grep -Ec '^[[:space:]]+width: root\.actionButtonWidth$' \
    "$confirmation")" -eq 2 ] \
    || fail 'confirmation actions do not share one label-derived width'
if grep -Fq 'width: (parent.width - parent.spacing) / 2' "$confirmation"; then
    fail 'confirmation actions still stretch across the content width'
fi
if grep -Fq 'Math.max(360, Math.min(520' "$confirmation"; then
    fail 'confirmation still forces the former broad screen-based width'
fi
grep -Fq 'Math.min(maximumPanelWidth, idealPanelWidth)' "$confirmation" \
    || fail 'confirmation width is not content-driven within readable bounds'
grep -Fq 'root.metrics.compactActionSurfaceWidth' "$confirmation" \
    || fail 'confirmation lacks the shared minimum sensible width'
grep -Fq 'root.metrics.standardPanelWidth' "$confirmation" \
    || fail 'confirmation lacks the shared maximum readable width'

[ "$(grep -F -c '    MonitorController {' "$shell")" -eq 1 ] \
    || fail 'shell does not own exactly one global MonitorController'
grep -Fq 'monitorController: root.globalMonitorController' "$shell" \
    || fail 'per-screen Monitor uses an ambiguous controller binding'
grep -Fq 'readonly property bool monitorControllerReady:' "$panel" \
    || fail 'Monitor panel lacks a soft-reload controller guard'
grep -Fq '? root.monitorController.pendingFor(root.connectorName) : null' "$panel" \
    || fail 'Monitor panel binding mutates pending controller state'
if grep -Fq 'color: root.text }' "$panel"; then
    fail 'Monitor selector uses an undefined root text color'
fi
grep -Fq '    MonitorConfirmationPanel {' "$shell" \
    || fail 'per-screen confirmation surface is missing from Variants'
grep -Fq 'textSizeController: root.globalTextSizeController' "$shell" \
    || fail 'Text Size ownership changed'
grep -Fq '["ddcutil", "setvcp", "10"' "$panel" \
    || fail 'Brightness DDC/CI ownership changed'

runtime=$(mktemp -d)
trap 'rm -rf -- "$runtime"' EXIT HUP INT TERM
config=$runtime/config
mkdir -p "$config/test"
cp -R "$components" "$config/test/components"
cp "$repository/tests/monitor-controller.qml" "$config/test/shell.qml"
output=$runtime/output.log
if ! XDG_CONFIG_HOME=$config XDG_RUNTIME_DIR=$runtime \
    QT_QPA_PLATFORM=offscreen timeout 15s \
    qs --no-color -p "$config/test" >"$output" 2>&1
then
    cat "$output" >&2
    fail 'MonitorController Quickshell harness failed'
fi
grep -Fq 'MONITOR_CONTROLLER_TEST_PASS' "$output" || {
    cat "$output" >&2
    fail 'MonitorController harness did not report success'
}

cp "$repository/tests/monitor-ui-stubs/DockPopup.qml" \
    "$config/test/components/DockPopup.qml"
cp "$repository/tests/monitor-ui-stubs/CenteredOverlay.qml" \
    "$config/test/components/CenteredOverlay.qml"
cp "$repository/tests/monitor-ui-types.qml" "$config/test/shell.qml"
if ! XDG_CONFIG_HOME=$config XDG_RUNTIME_DIR=$runtime \
    QT_QPA_PLATFORM=offscreen timeout 15s \
    qs --no-color -p "$config/test" >"$output" 2>&1
then
    cat "$output" >&2
    fail 'Monitor QML type harness failed'
fi
grep -Fq 'MONITOR_UI_TYPES_TEST_PASS' "$output" || {
    cat "$output" >&2
    fail 'Monitor QML type harness did not report success'
}

printf '%s\n' 'Monitor UI/controller tests: PASS'
