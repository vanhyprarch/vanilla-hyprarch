#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
components_dir=$repository_dir/home/.config/quickshell/vanhyprarch/components
shell_file=$repository_dir/home/.config/quickshell/vanhyprarch/shell.qml
bindings_file=$repository_dir/home/.config/hypr/vanhyprarch/bindings.lua
runtime_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-background-picker.XXXXXX")

cleanup()
{
    status=$?
    trap - 0 HUP INT TERM
    rm -rf -- "$runtime_dir"
    exit "$status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'Background Picker test: %s\n' "$*" >&2
    exit 1
}

command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'

grep -Fq 'vanhyprarch.backgroundPicker toggle' "$bindings_file" \
    || fail 'Super+Ctrl+Space does not use the shared picker IPC target'
[ "$(grep -F -c 'mainMod .. " + CTRL + SPACE"' "$bindings_file")" -eq 1 ] \
    || fail 'Super+Ctrl+Space is missing or duplicated'
[ "$(grep -F -c '    BackgroundPickerController {' "$shell_file")" -eq 1 ] \
    || fail 'shell does not own exactly one Background Picker controller'
[ "$(grep -F -c '    BackgroundPickerPanel {' "$shell_file")" -eq 1 ] \
    || fail 'picker presentation is not declared once per screen delegate'
grep -Fq 'onBackgroundPickerRequested: backgroundPicker.open()' "$shell_file" \
    || fail 'Style does not open the shared picker controller'
grep -Fq 'CenteredOverlay {' "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'picker does not use the shared central-overlay surface'
if grep -Eq 'hyprctl[[:space:]]+hyprpaper|hyprpaper[[:space:]]+wallpaper' \
    "$components_dir/BackgroundPickerController.qml" \
    "$components_dir/BackgroundPickerPanel.qml"
then
    fail 'picker bypasses the Appearance authority'
fi
if grep -Fq 'WheelHandler {' "$components_dir/BackgroundPickerPanel.qml"
then
    fail 'picker reintroduced a custom wheel handler'
fi
grep -Fq 'orientation: ListView.Horizontal' \
    "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'picker does not use native horizontal Flickable navigation'
grep -Fq 'asynchronous: true' "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'preview images are not asynchronous'
grep -Fq 'fillMode: Image.PreserveAspectCrop' \
    "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'preview images are not aspect-preserving crops'
grep -Fq 'previewImage.status === Image.Error' \
    "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'failed or missing previews have no fallback state'
grep -Fq 'cardSlot.navigationCurrent' \
    "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'navigation-current cards have no distinct visual state'
grep -Fq 'cardSlot.applied' "$components_dir/BackgroundPickerPanel.qml" \
    || fail 'applied wallpapers have no persistent visual state'
grep -Fq 'mainMod .. " + K"' "$bindings_file" \
    || fail 'existing Super+K shortcut changed unexpectedly'
grep -Fq 'mainMod .. " + SPACE"' "$bindings_file" \
    || fail 'existing Super+Space shortcut changed unexpectedly'

run_qml()
{
    fixture=$1
    success=$2
    config_dir=$runtime_dir/$fixture
    fixture_runtime=$config_dir/runtime
    mkdir -m 0700 -p -- "$fixture_runtime"
    ln -s "$components_dir" "$config_dir/components"
    ln -s "$test_dir/$fixture.qml" "$config_dir/shell.qml"
    log=$config_dir/quickshell.log
    if ! env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
        XDG_RUNTIME_DIR=$fixture_runtime timeout 10s \
        qs --no-color -p "$config_dir" >"$log" 2>&1
    then
        cat "$log" >&2
        fail "$fixture failed"
    fi
    grep -Fq "$success" "$log" || {
        cat "$log" >&2
        fail "$fixture did not report success"
    }
}

run_qml background-picker-controller \
    'vanhyprarch Background Picker controller self-check passed'

run_qml_test()
{
    fixture=$1
    fixture_runtime=$runtime_dir/$fixture-runtime
    mkdir -m 0700 -p -- "$fixture_runtime"
    if ! env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
        XDG_RUNTIME_DIR=$fixture_runtime /usr/lib/qt6/bin/qmltestrunner \
        -input "$test_dir/$fixture.qml" \
        >"$runtime_dir/$fixture.log" 2>&1
    then
        cat "$runtime_dir/$fixture.log" >&2
        fail "$fixture failed"
    fi
}

run_qml_test background-picker-layout
run_qml_test background-picker-images

printf '%s\n' 'Background Picker tests: PASS'
