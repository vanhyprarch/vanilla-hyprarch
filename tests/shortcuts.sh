#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
temporary=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-shortcuts-test.XXXXXX")

cleanup()
{
    status=$?
    trap - 0 HUP INT TERM
    rm -rf -- "$temporary"
    exit "$status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'shortcuts test: %s\n' "$*" >&2
    exit 1
}

/usr/bin/python "$test_dir/shortcut-bindings.py"

command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'
config_dir=$temporary/config
runtime_dir=$temporary/runtime
mkdir -m 0700 -p -- "$config_dir" "$runtime_dir"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
    "$config_dir/components"
sed 's#import "../home/.config/quickshell/vanhyprarch/components"#import "components"#' \
    "$test_dir/shortcuts.qml" > "$config_dir/shell.qml"

log=$temporary/quickshell.log
if ! env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
    XDG_RUNTIME_DIR=$runtime_dir timeout 10s qs --no-color -p "$config_dir" \
    > "$log" 2>&1
then
    cat "$log" >&2
    fail 'Quickshell shortcut parser/filter fixture failed'
fi
grep -Fq VANHYPRARCH_SHORTCUTS_TEST_PASS "$log" || {
    cat "$log" >&2
    fail 'Quickshell shortcut fixture did not report success'
}

printf '%s\n' 'Shortcut source/parser/filter tests: PASS'
