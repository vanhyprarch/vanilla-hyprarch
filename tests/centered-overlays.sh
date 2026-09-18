#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
components_dir=$repository_dir/home/.config/quickshell/vanhyprarch/components
shell_file=$repository_dir/home/.config/quickshell/vanhyprarch/shell.qml

fail()
{
    printf 'centered overlays test: %s\n' "$*" >&2
    exit 1
}

for panel in SuperSpacePanel.qml ShortcutsPanel.qml
do
    grep -Fq 'CenteredOverlay {' "$components_dir/$panel" \
        || fail "$panel does not use the shared centered surface"
    if grep -Fq 'PopupWindow {' "$components_dir/$panel"
    then
        fail "$panel still uses popup-relative window ownership"
    fi
    grep -Fq 'visible: false' "$components_dir/$panel" \
        || fail "$panel is not hidden when its controller is closed"
    grep -Fq 'onDismissed: controller.close()' "$components_dir/$panel" \
        || fail "$panel does not close after outside-focus dismissal"
    grep -Fq 'focusCoordinator: overlayFocusCoordinator' "$shell_file" \
        || fail "$panel does not share the shell focus coordinator"
done

[ "$(grep -F -c 'targetScreen: screenScope.modelData' "$shell_file")" -ge 2 ] \
    || fail 'central surfaces do not use their Variants delegate screen'
grep -Fq 'model: Quickshell.screens' "$shell_file" \
    || fail 'central surfaces are no longer created by the per-screen Variants model'
[ "$(grep -F -c '    ShortcutsPanel {' "$shell_file")" -eq 1 ] \
    || fail 'Keyboard Shortcuts must have exactly one declaration per screen delegate'
[ "$(grep -F -c '    SuperSpacePanel {' "$shell_file")" -eq 1 ] \
    || fail 'SuperSpace must have exactly one declaration per screen delegate'

if grep -Fq 'shortcutsAnchor' "$shell_file"
then
    fail 'obsolete popup anchor surface remains'
fi

grep -Fq 'exclusionMode: ExclusionMode.Ignore' "$components_dir/CenteredOverlay.qml" \
    || fail 'centered surfaces do not ignore dock exclusive geometry'
grep -Fq 'margins.top: OverlayGeometry.margin(root.screenHeight, root.implicitHeight)' \
    "$components_dir/CenteredOverlay.qml" \
    || fail 'vertical position is not derived from monitor-local geometry'
grep -Fq 'margins.left: OverlayGeometry.margin(root.screenWidth, root.implicitWidth)' \
    "$components_dir/CenteredOverlay.qml" \
    || fail 'horizontal position is not derived from monitor-local geometry'
grep -Fq 'focusable: true' "$components_dir/CenteredOverlay.qml" \
    || fail 'centered surfaces cannot receive keyboard focus'
grep -Fq 'exclusiveZone: 0' "$components_dir/CenteredOverlay.qml" \
    || fail 'centered surfaces unexpectedly reserve monitor space'
exclusive_zone_line=$(grep -Fn 'exclusiveZone: 0' \
    "$components_dir/CenteredOverlay.qml" | cut -d: -f1)
exclusion_mode_line=$(grep -Fn 'exclusionMode: ExclusionMode.Ignore' \
    "$components_dir/CenteredOverlay.qml" | cut -d: -f1)
[ "$exclusive_zone_line" -lt "$exclusion_mode_line" ] \
    || fail 'exclusiveZone assignment can override ExclusionMode.Ignore'
grep -Fq 'registerCentral(root)' "$components_dir/CenteredOverlay.qml" \
    || fail 'centered surfaces are not registered with shell focus ownership'
grep -Fq 'windowVisibilityChanged(root, "central")' \
    "$components_dir/CenteredOverlay.qml" \
    || fail 'centered visibility is not synchronized with focus ownership'

grep -Fq 'PanelWindow {' "$components_dir/DockPopup.qml" \
    || fail 'dock panels do not use independent layer surfaces'
if grep -Fq 'PopupWindow {' "$components_dir/DockPopup.qml" \
        "$components_dir/LauncherContextMenu.qml"
then
    fail 'a dock-owned popup still creates an incompatible xdg_popup grab'
fi
grep -Fq 'exclusionMode: ExclusionMode.Ignore' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement reserves or follows exclusive geometry'
grep -Fq 'aboveWindows: true' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement does not retain above-window ordering'
grep -Fq 'focusable: true' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement cannot receive keyboard focus'
grep -Fq 'registerDock(root)' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement is outside coordinated focus ownership'

[ "$(grep -F -c '    OverlayFocusCoordinator {' "$shell_file")" -eq 1 ] \
    || fail 'the shell must own exactly one overlay focus coordinator'
coordinator_line=$(grep -Fn '    OverlayFocusCoordinator {' "$shell_file" \
    | cut -d: -f1)
variants_line=$(grep -Fn '    Variants {' "$shell_file" | cut -d: -f1)
[ "$coordinator_line" -lt "$variants_line" ] \
    || fail 'focus coordination must be shell-global, not duplicated per screen'
grep -Fq 'HyprlandFocusGrab {' "$components_dir/OverlayFocusCoordinator.qml" \
    || fail 'coordinator does not own the shell focus grab'
[ "$(grep -R -F -c 'HyprlandFocusGrab {' "$components_dir"/*.qml \
    | awk -F: '{ total += $2 } END { print total + 0 }')" -eq 1 ] \
    || fail 'focus-grab ownership is duplicated outside the coordinator'
grep -Fq '.concat(root.visibleDockWindows,' \
    "$components_dir/OverlayFocusCoordinator.qml" \
    || fail 'central and dock surfaces cannot coexist in the focus whitelist'
grep -Fq 'root.visibleDockCompanions' \
    "$components_dir/OverlayFocusCoordinator.qml" \
    || fail 'visible dock panels do not whitelist their dock host'
grep -Fq 'popupAnchorItem.QsWindow.window' "$components_dir/DockPopup.qml" \
    || fail 'dock panel focus ownership is not tied to its real parent window'
grep -Fq 'function onWindowTransformChanged()' "$components_dir/DockPopup.qml" \
    || fail 'dock placement does not react to window or output transforms'
grep -Fq 'function onDestroyed()' "$components_dir/DockPopup.qml" \
    || fail 'destroyed popup anchors can leave orphaned dock surfaces'
dock_zone_line=$(grep -Fn 'exclusiveZone: 0' \
    "$components_dir/DockPopup.qml" | cut -d: -f1)
dock_exclusion_line=$(grep -Fn 'exclusionMode: ExclusionMode.Ignore' \
    "$components_dir/DockPopup.qml" | cut -d: -f1)
[ "$dock_zone_line" -lt "$dock_exclusion_line" ] \
    || fail 'DockPopup exclusiveZone assignment can reset ExclusionMode.Ignore'
grep -Fq 'anchors {' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement has no bounded surface anchors'
grep -Fq 'top: true' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement is not top anchored'
grep -Fq 'left: true' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement is not left anchored'
grep -Fq 'visible: false' "$components_dir/DockPopup.qml" \
    || fail 'dock popup replacement is not hidden by default'

expected_consumers='AppPicker.qml
AudioPanel.qml
BluetoothPanel.qml
LauncherContextMenu.qml
MonitorPanel.qml
MonthCalendar.qml
NetworkPanel.qml
PowerIdlePanel.qml
PowerMenu.qml'
actual_consumers=$(grep -l -E '^[[:space:]]*DockPopup[[:space:]]*\{' \
    "$components_dir"/*.qml | sed 's|.*/||' | sort)
[ "$actual_consumers" = "$expected_consumers" ] \
    || fail 'the production DockPopup consumer inventory changed unexpectedly'

grep -Fq 'alignToAnchorTop: true' \
    "$components_dir/LauncherContextMenu.qml" \
    || fail 'launcher context menu lost launcher-adjacent placement'
grep -Fq 'launcherContextMenu.visible = false' \
    "$components_dir/Launchers.qml" \
    || fail 'reopening the launcher context menu does not close the old target'
grep -Fq 'launcherContextMenu.visible = true' \
    "$components_dir/Launchers.qml" \
    || fail 'launcher context menu cannot be opened after retargeting'
grep -Fq 'root.visible = false' "$components_dir/LauncherContextMenu.qml" \
    || fail 'launcher context actions do not close their menu'

if grep -Fq 'Timer {' "$components_dir/OverlayFocusCoordinator.qml"
then
    fail 'focus coordination uses a time-based debounce'
fi
grep -Fq 'Component.onDestruction: root.focusCoordinator.unregisterDock(root)' \
    "$components_dir/DockPopup.qml" \
    || fail 'destroyed dock surfaces can leave stale coordinator references'
grep -Fq 'Component.onDestruction: root.focusCoordinator.unregisterCentral(root)' \
    "$components_dir/CenteredOverlay.qml" \
    || fail 'destroyed central surfaces can leave stale coordinator references'
grep -Fq 'root.focusWindows.length > 0' \
    "$components_dir/OverlayFocusCoordinator.qml" \
    || fail 'focus grab can remain active with an empty whitelist'

grep -Fq 'event.key === Qt.Key_Escape' "$components_dir/SuperSpacePanel.qml" \
    || fail 'SuperSpace no longer handles Escape'
grep -Fq 'controller.goBack()' "$components_dir/SuperSpacePanel.qml" \
    || fail 'SuperSpace Escape no longer follows Back/close navigation'
grep -Fq 'event.key === Qt.Key_Escape' "$components_dir/ShortcutsPanel.qml" \
    || fail 'Keyboard Shortcuts no longer handles Escape'
grep -Fq 'root.controller.close()' "$components_dir/ShortcutsPanel.qml" \
    || fail 'Keyboard Shortcuts Escape no longer closes the controller'

if grep -Eqi 'dock|popup' "$components_dir/CenteredOverlayGeometry.js"
then
    fail 'center calculation depends on dock-popup geometry'
fi

grep -Fq 'navigationFill: root.theme.navigationFill' \
    "$components_dir/SuperSpacePanel.qml" \
    || fail 'SuperSpace rows do not use the navigation cursor role'
grep -Fq 'selectionFill: root.theme.selectionFill' \
    "$components_dir/SuperSpacePanel.qml" \
    || fail 'SuperSpace persistent selections do not use the selection role'
grep -Fq '? root.theme.navigationFill' "$components_dir/ShortcutsPanel.qml" \
    || fail 'Shortcuts does not share the navigation cursor role'
grep -Fq 'radius: root.metrics.rowRadius' "$components_dir/ShortcutsPanel.qml" \
    || fail 'Shortcuts navigation cursor is not rectangular'

QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner \
    -input "$test_dir/centered-overlay-geometry.qml"
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner \
    -input "$test_dir/dock-popup-geometry.qml"

run_quickshell_test()
{
    test_file=$1
    expected_marker=$2
    runtime_dir=$(mktemp -d)
    config_dir=$runtime_dir/config
    mkdir -p "$config_dir/test"
    cp -R "$components_dir" "$config_dir/test/components"
    cp "$test_file" "$config_dir/test/shell.qml"
    output_file=$runtime_dir/output.log
    if ! XDG_CONFIG_HOME=$config_dir XDG_RUNTIME_DIR=$runtime_dir \
        QT_QPA_PLATFORM=offscreen timeout 15s \
        qs --no-color -p "$config_dir/test" \
        >"$output_file" 2>&1
    then
        cat "$output_file" >&2
        rm -rf "$runtime_dir"
        fail "$(basename "$test_file") failed"
    fi
    if ! grep -Fq "$expected_marker" "$output_file"
    then
        cat "$output_file" >&2
        rm -rf "$runtime_dir"
        fail "$(basename "$test_file") did not report success"
    fi
    rm -rf "$runtime_dir"
}

run_quickshell_test "$test_dir/overlay-focus-coordinator.qml" \
    OVERLAY_FOCUS_TEST_PASS
run_quickshell_test "$test_dir/row-visuals.qml" \
    ROW_VISUALS_TEST_PASS

printf '%s\n' 'Centered overlay geometry/focus/visual tests: PASS'
