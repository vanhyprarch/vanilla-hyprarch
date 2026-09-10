#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_bluetooth_agent.py
power_test=$script_dir/vanhyprarch-bluetooth-power.sh
template=$script_dir/bluetooth-controller.qml
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-bluetooth-test.XXXXXX")

cleanup()
{
    cleanup_status=$?
    trap - 0 HUP INT TERM
    rm -rf -- "$test_dir"
    exit "$cleanup_status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'vanhyprarch Bluetooth test: %s\n' "$*" >&2
    exit 1
}

command -v python >/dev/null 2>&1 || fail 'python is unavailable'
command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'

PYTHONPYCACHEPREFIX=$test_dir/pycache python -m py_compile "$helper"
agent_log=$test_dir/agent-self-check.log
if ! python "$helper" --check > "$agent_log" 2>&1; then
    cat "$agent_log" >&2
    fail 'Bluetooth agent self-check failed'
fi
grep -Fq 'vanhyprarch Bluetooth agent self-check passed' "$agent_log" ||
    fail 'Bluetooth agent self-check did not report success'
printf '%s\n' 'vanhyprarch Bluetooth agent self-check passed (fail-closed paths exercised)'
"$power_test"

components_uri=components
sed "s|@COMPONENTS_URI@|$components_uri|" "$template" > "$test_dir/shell.qml"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
    "$test_dir/components"
install -d -m 0700 "$test_dir/runtime"

qml_log=$test_dir/quickshell.log
if ! env -u WAYLAND_DISPLAY \
    QT_QPA_PLATFORM=offscreen \
    XDG_RUNTIME_DIR=$test_dir/runtime \
    timeout 10s qs --no-color -p "$test_dir/shell.qml" > "$qml_log" 2>&1
then
    cat "$qml_log" >&2
    fail 'offscreen Quickshell self-check failed'
fi

grep -Fq 'vanhyprarch Bluetooth controller self-check passed' "$qml_log" || {
    cat "$qml_log" >&2
    fail 'offscreen Quickshell self-check did not report success'
}

unexpected_diagnostics=$(
    grep -E '(^|[[:space:]])(WARN|ERROR)([[:space:]]|:)' "$qml_log" |
        grep -Fv 'quickshell.ipc: Failed to start IPC server' |
        grep -Fv 'quickshell.bluetooth: Could not connect to DBus' || true
)
[ -z "$unexpected_diagnostics" ] || {
    cat "$qml_log" >&2
    fail 'offscreen Quickshell self-check emitted unexpected diagnostics'
}

printf '%s\n' \
    'vanhyprarch Bluetooth controller self-check passed (isolated IPC/DBus warnings expected)'
