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
python "$helper" --check
"$power_test"

components_uri=file:$repository_dir/home/.config/quickshell/vanhyprarch/components
sed "s|@COMPONENTS_URI@|$components_uri|" "$template" > "$test_dir/shell.qml"
mkdir -p "$test_dir/runtime"

QT_QPA_PLATFORM=offscreen \
XDG_RUNTIME_DIR=$test_dir/runtime \
timeout 10s qs --no-color -p "$test_dir/shell.qml"
