#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
components_dir=$repository_dir/home/.config/quickshell/vanhyprarch/components
shell_file=$repository_dir/home/.config/quickshell/vanhyprarch/shell.qml
runtime_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-appearance-qml.XXXXXX")

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
    printf 'Appearance test: %s\n' "$*" >&2
    exit 1
}

[ "$(grep -F -c '    AppearanceController {' "$shell_file")" -eq 1 ] \
    || fail 'shell does not own exactly one global Appearance controller'
grep -Fq 'controller: appearanceController' "$shell_file" \
    || fail 'dock toggle does not consume the global Appearance controller'
grep -Fq 'model: Quickshell.screens' "$shell_file" \
    || fail 'screen-bound UI left the required Variants lifecycle'
grep -Fq 'onClicked: root.activate()' "$components_dir/ThemeToggle.qml" \
    || fail 'dock click does not call the controller-only activation path'
if grep -Eq 'theme\.darkMode[[:space:]]*=|XDG_STATE_HOME|sh", "-c"' \
    "$components_dir/ThemeToggle.qml"
then
    fail 'dock toggle retains private theme state or persistence'
fi

config_dir=$runtime_dir/config
mkdir -m 0700 -p -- "$config_dir"
ln -s "$components_dir" "$config_dir/components"
ln -s "$test_dir/appearance-controller.qml" "$config_dir/shell.qml"
log=$runtime_dir/quickshell.log
if ! env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
    XDG_RUNTIME_DIR=$runtime_dir timeout 10s qs --no-color -p "$config_dir" \
    >"$log" 2>&1
then
    cat "$log" >&2
    fail 'controller fixture failed'
fi
grep -Fq 'vanhyprarch Appearance controller self-check passed' "$log" || {
    cat "$log" >&2
    fail 'controller fixture did not report success'
}

printf '%s\n' 'Appearance manager/controller tests: PASS'
