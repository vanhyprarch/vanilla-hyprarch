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
done

[ "$(grep -F -c 'targetScreen: screenScope.modelData' "$shell_file")" -eq 2 ] \
    || fail 'both central surfaces must use their Variants delegate screen'
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
grep -Fq 'active: root.visible' "$components_dir/CenteredOverlay.qml" \
    || fail 'focus grab is not bounded to visible overlay lifetime'
grep -Fq 'windows: [root]' "$components_dir/CenteredOverlay.qml" \
    || fail 'focus grab does not own the independent overlay surface'
grep -Fq 'onCleared: if (root.visible) root.dismissed()' \
    "$components_dir/CenteredOverlay.qml" \
    || fail 'outside click/focus loss does not dismiss the visible overlay'

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

QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner \
    -input "$test_dir/centered-overlay-geometry.qml"

printf '%s\n' 'Centered overlay geometry tests: PASS'
