#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_bluetooth_agent.py
hardware_helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_bluetooth_hardware
power_test=$script_dir/vanhyprarch-bluetooth-power.sh
template=$script_dir/bluetooth-controller.qml
lifecycle_test=$script_dir/vanhyprarch-bluetooth-lifecycle.py
bluetooth_component=$repository_dir/home/.config/quickshell/vanhyprarch/components/Bluetooth.qml
bluetooth_panel=$repository_dir/home/.config/quickshell/vanhyprarch/components/BluetoothPanel.qml
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

fake_sysfs=$test_dir/sys/class/bluetooth
fake_bin=$test_dir/bin
bluetoothctl_marker=$test_dir/bluetoothctl-called
mkdir -p "$fake_sysfs" "$fake_bin"
cat > "$fake_bin/bluetoothctl" <<EOF
#!/bin/sh
: > "$bluetoothctl_marker"
exit 99
EOF
chmod 755 "$fake_bin/bluetoothctl"

hardware_status=$(PATH=$fake_bin:$PATH /bin/sh "$hardware_helper" status \
    "$test_dir/sys/class/missing")
[ "$hardware_status" = 'version=1
available=false' ] || fail 'missing Bluetooth sysfs path was not unavailable'
hardware_status=$(PATH=$fake_bin:$PATH /bin/sh "$hardware_helper" status \
    "$fake_sysfs")
[ "$hardware_status" = 'version=1
available=false' ] || fail 'empty Bluetooth sysfs path was not unavailable'
mkdir "$fake_sysfs/hci-not-a-controller"
hardware_status=$(PATH=$fake_bin:$PATH /bin/sh "$hardware_helper" status \
    "$fake_sysfs")
[ "$hardware_status" = 'version=1
available=false' ] || fail 'non-numeric hci entry was accepted as a controller'
mkdir "$fake_sysfs/hci0"
hardware_status=$(PATH=$fake_bin:$PATH /bin/sh "$hardware_helper" status \
    "$fake_sysfs")
[ "$hardware_status" = 'version=1
available=true' ] || fail 'hci controller was not available'
[ ! -e "$bluetoothctl_marker" ] ||
    fail 'hardware detection invoked bluetoothctl'
rm -r "$fake_sysfs/hci0" "$fake_sysfs/hci-not-a-controller"
printf '%s\n' 'vanhyprarch Bluetooth hardware self-check passed (no BlueZ activation)'

grep -Fq 'visible: root.hardwareAvailable' "$bluetooth_component" ||
    fail 'Bluetooth dock icon is not gated by hardware availability'
grep -Fq 'implicitWidth: visible ? buttonSize : 0' "$bluetooth_component" ||
    fail 'unavailable Bluetooth dock icon still reserves width'
grep -Fq 'implicitHeight: visible ? buttonSize : 0' "$bluetooth_component" ||
    fail 'unavailable Bluetooth dock icon still reserves height'
if grep -Eq '^[[:space:]]*opacity:' "$bluetooth_component"; then
    fail 'Bluetooth functional states must retain the normal dock foreground'
fi
grep -Fq 'const candidate = root.visible && root.adapterEnabled' "$bluetooth_panel" ||
    fail 'Bluetooth discovery is not gated by a visible enabled panel'
grep -Fq ': "Bluetooth is off")' "$bluetooth_panel" ||
    fail 'Bluetooth powered-off panel state changed'
printf '%s\n' 'vanhyprarch Bluetooth dock availability self-check passed'

PYTHONPYCACHEPREFIX=$test_dir/pycache python -m py_compile "$helper"
agent_log=$test_dir/agent-self-check.log
if ! python "$helper" --check > "$agent_log" 2>&1; then
    cat "$agent_log" >&2
    fail 'Bluetooth agent self-check failed'
fi
grep -Fq 'vanhyprarch Bluetooth agent self-check passed' "$agent_log" ||
    fail 'Bluetooth agent self-check did not report success'
printf '%s\n' 'vanhyprarch Bluetooth agent self-check passed (fail-closed paths exercised)'
PYTHONPYCACHEPREFIX=$test_dir/pycache python "$lifecycle_test"
"$power_test"

components_uri=components
sed "s|@COMPONENTS_URI@|$components_uri|" "$template" > "$test_dir/shell.qml"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
    "$test_dir/components"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/helpers" \
    "$test_dir/helpers"
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
