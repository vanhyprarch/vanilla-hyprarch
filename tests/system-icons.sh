#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
shell_dir=$repository_dir/home/.config/quickshell/vanhyprarch
runtime_root=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-system-icons.XXXXXX")

cleanup()
{
    status=$?
    trap - 0 HUP INT TERM
    rm -rf -- "$runtime_root"
    exit "$status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'System icon test: %s\n' "$*" >&2
    exit 1
}

PYTHONPYCACHEPREFIX=$runtime_root/pycache python "$test_dir/system-icons.py"

config_dir=$runtime_root/config
render_dir=$runtime_root/render
mkdir -m 0700 -p -- "$config_dir" "$render_dir" "$runtime_root/runtime"
ln -s "$shell_dir/components" "$config_dir/components"
ln -s "$shell_dir/assets" "$config_dir/assets"
python -B "$test_dir/system-icons.py" --state-fixture "$config_dir/state.qml"
state_log=$runtime_root/state.log
if ! env -u WAYLAND_DISPLAY -u DISPLAY \
    QT_QPA_PLATFORM=offscreen XDG_RUNTIME_DIR=$runtime_root/runtime \
    timeout 10s qs --no-color -p "$config_dir/state.qml" >"$state_log" 2>&1
then
    cat "$state_log" >&2
    fail 'state fixture failed'
fi
grep -F 'vanhyprarch system icon state self-check passed' "$state_log" || {
    cat "$state_log" >&2
    fail 'state fixture did not complete'
}
ln -s "$test_dir/system-icon-render.qml" "$config_dir/shell.qml"

log=$runtime_root/quickshell.log
if ! env -u WAYLAND_DISPLAY \
    QT_QPA_PLATFORM=offscreen \
    XDG_RUNTIME_DIR=$runtime_root/runtime \
    VANHYPRARCH_SYSTEM_ICON_RENDER_DIR=$render_dir \
    timeout 10s qs --no-color -p "$config_dir" >"$log" 2>&1
then
    cat "$log" >&2
    fail 'offscreen render failed'
fi
grep -Fq 'vanhyprarch system icon render self-check passed' "$log" || {
    cat "$log" >&2
    fail 'offscreen render did not complete'
}

PYTHONPYCACHEPREFIX=$runtime_root/pycache \
    python "$test_dir/system-icons.py" --render-dir "$render_dir"

printf '%s\n' 'Vanilla system icon tests: PASS'
