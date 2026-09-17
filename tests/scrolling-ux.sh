#!/bin/sh
set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
config_dir="$repo_dir/home/.config/quickshell/vanhyprarch"
components_dir="$config_dir/components"
shell_file="$config_dir/shell.qml"

fail() {
    echo "scrolling-ux: $*" >&2
    exit 1
}

setting_count=$(grep -R -h --include='*.qml' \
    -F 'QT_QUICK_FLICKABLE_WHEEL_DECELERATION' "$config_dir" \
    | wc -l)
[ "$setting_count" -eq 1 ] \
    || fail "expected exactly one Flickable wheel deceleration setting"

exact_setting_count=$(grep -F -x -c \
    '//@ pragma Env QT_QUICK_FLICKABLE_WHEEL_DECELERATION=10000' \
    "$shell_file" || true)
[ "$exact_setting_count" -eq 1 ] \
    || fail "expected the native wheel deceleration value to be 10000"

[ ! -e "$components_dir/VerticalWheelScroll.qml" ] \
    || fail "obsolete VerticalWheelScroll.qml still exists"

if grep -R -n --include='*.qml' -E \
    'VerticalWheelScroll|WheelHandler|onWheel[[:space:]]*:|discreteWheel(Step|ViewportCap)' \
    "$config_dir"; then
    fail "custom wheel interception or diagnostics remain in production QML"
fi

diagnostic_tag='VANHYPRARCH_WHEEL_''DIAGNOSTIC'
if grep -R -n --include='*.qml' -F "$diagnostic_tag" "$config_dir"; then
    fail "temporary wheel diagnostic logging remains in production QML"
fi

list_count=$(grep -R -h --include='*.qml' -F 'ListView {' \
    "$components_dir" | wc -l)
[ "$list_count" -eq 6 ] \
    || fail "expected all six production vertical ListViews"

indicator_count=$(grep -R -h --include='*.qml' \
    -F 'VerticalScrollIndicator {' "$components_dir" | wc -l)
[ "$indicator_count" -eq 6 ] \
    || fail "expected an indicator on all six production vertical ListViews"

navigation_count=$(grep -R -h --include='*.qml' \
    -F 'WrappedListNavigation {' "$components_dir" | wc -l)
[ "$navigation_count" -eq 2 ] \
    || fail "expected wrapped navigation only in SuperSpace and Shortcuts"

check_integrations() {
    expected=$1
    file=$2
    list_count=$(grep -F -c 'ListView {' "$file" || true)
    indicator_count=$(grep -F -c 'VerticalScrollIndicator {' "$file" || true)
    [ "$list_count" -eq "$expected" ] \
        || fail "unexpected ListView count in $file"
    [ "$indicator_count" -eq "$expected" ] \
        || fail "missing indicator integration in $file"
}

check_integrations 1 "$components_dir/SuperSpacePanel.qml"
check_integrations 1 "$components_dir/ShortcutsPanel.qml"
check_integrations 1 "$components_dir/AppPicker.qml"
check_integrations 1 "$components_dir/NetworkPanel.qml"
check_integrations 2 "$components_dir/BluetoothPanel.qml"

QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner \
    -input "$test_dir/scrolling-ux.qml"
