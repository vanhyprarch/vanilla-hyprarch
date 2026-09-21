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
grep -Fq 'interval: 1000' "$controller" \
    || fail 'active transaction reconciliation lacks bounded polling'
grep -Fq 'running: root.transactionInFlight && root.checksEnabled' "$controller" \
    || fail 'status polling is not limited to an active backend transaction'
grep -Fq 'Hyprland.refreshMonitors()' "$controller" \
    || fail 'terminal operations do not refresh Quickshell monitor projections'
grep -Fq 'id: displayReadouts' "$panel" \
    || fail 'top monitor readouts are not grouped independently'
grep -A4 -F 'id: displayReadouts' "$panel" | grep -Fq 'spacing: 0' \
    || fail 'top monitor readouts still inherit section-sized gaps'

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
