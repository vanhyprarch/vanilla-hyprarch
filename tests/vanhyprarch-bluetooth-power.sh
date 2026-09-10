#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_bluetooth_power
bluez_config=$repository_dir/system/etc/bluetooth/main.conf
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-bluetooth-power-test.XXXXXX")

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
    printf 'vanhyprarch Bluetooth power test: %s\n' "$*" >&2
    exit 1
}

reject_command()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail "command unexpectedly succeeded: $*"
    fi
}

require_status()
{
    expected=$1
    actual=$(sh "$helper" status)
    [ "$actual" = "version=1
power=$expected" ] || fail "unexpected status: $actual"
}

mkdir -p "$test_dir/home" "$test_dir/config"
export HOME=$test_dir/home
export XDG_CONFIG_HOME=$test_dir/config
preference_dir=$XDG_CONFIG_HOME/vanhyprarch
preference_file=$preference_dir/bluetooth-power.conf

require_status unset
[ ! -e "$preference_file" ] || fail 'observational status created a preference'

sh "$helper" set off >/dev/null
require_status off
[ "$(stat -c '%a' "$preference_dir")" = 700 ] ||
    fail 'preference directory permissions are not 700'
[ "$(stat -c '%a' "$preference_file")" = 600 ] ||
    fail 'preference file permissions are not 600'

sh "$helper" set on >/dev/null
require_status on
[ "$(find "$preference_dir" -maxdepth 1 -name '.bluetooth-power.*' | wc -l)" -eq 0 ] ||
    fail 'temporary preference file remained'

cp "$preference_file" "$test_dir/preference.before-invalid"
reject_command sh "$helper" set enabled
cmp -s "$preference_file" "$test_dir/preference.before-invalid" ||
    fail 'invalid power value changed the preference'

printf 'version=1\npower=on\npower=off\n' > "$preference_file"
reject_command sh "$helper" status

rm -f "$preference_file"
ln -s "$test_dir/outside" "$preference_file"
reject_command sh "$helper" set off
[ ! -e "$test_dir/outside" ] || fail 'symlink target was written'

active_bluez_config=$(grep -Ev '^[[:space:]]*(#|$)' "$bluez_config")
[ "$active_bluez_config" = "[Policy]
AutoEnable=false" ] || fail 'managed BlueZ policy is not minimal and explicit'

printf '%s\n' 'vanhyprarch Bluetooth power self-check passed'
