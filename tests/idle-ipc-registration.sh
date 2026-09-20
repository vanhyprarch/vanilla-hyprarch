#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
temporary=$(mktemp -d /tmp/vanhyprarch-idle-ipc.XXXXXX)
runtime=$(mktemp -d /tmp/vanhyprarch-idle-ipc-runtime.XXXXXX)
quickshell_pid=
launcher_pid=

cleanup()
{
    status=$?
    trap - 0 HUP INT TERM
    if [ -n "$quickshell_pid" ] && kill -0 "$quickshell_pid" 2>/dev/null; then
        kill "$quickshell_pid" 2>/dev/null || true
    fi
    if [ -n "$launcher_pid" ]; then
        wait "$launcher_pid" 2>/dev/null || true
    fi
    rm -rf -- "$temporary" "$runtime"
    exit "$status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'Idle IPC registration test: %s\n' "$*" >&2
    if [ -f "$log" ]; then
        sed -n '1,240p' "$log" >&2
    fi
    if [ -f "$temporary/ipc-before" ]; then
        printf '%s\n' 'IPC before reload:' >&2
        cat "$temporary/ipc-before" >&2
    fi
    if [ -f "$temporary/ipc-after" ]; then
        printf '%s\n' 'IPC after reload:' >&2
        cat "$temporary/ipc-after" >&2
    fi
    exit 1
}

wait_for_log_count()
{
    pattern=$1
    expected=$2
    attempts=0
    while [ "$attempts" -lt 100 ]; do
        actual=$(grep -F -c "$pattern" "$log" 2>/dev/null || true)
        [ "$actual" -ge "$expected" ] && return 0
        kill -0 "${quickshell_pid:-$launcher_pid}" 2>/dev/null ||
            fail 'Quickshell exited while waiting for fixture output'
        attempts=$((attempts + 1))
        sleep 0.05
    done
    fail "timed out waiting for $expected occurrences of $pattern"
}

wait_for_status_count()
{
    expected=$1
    attempts=0
    while [ "$attempts" -lt 100 ]; do
        actual=$(wc -l < "$fixture_root/status.log")
        [ "$actual" -ge "$expected" ] && return 0
        kill -0 "${quickshell_pid:-$launcher_pid}" 2>/dev/null ||
            fail 'Quickshell exited while waiting for authoritative status'
        attempts=$((attempts + 1))
        sleep 0.05
    done
    fail "timed out waiting for authoritative status read $expected"
}

wait_for_ipc_target()
{
    output=$1
    attempts=0
    while [ "$attempts" -lt 100 ]; do
        if run_qs ipc -c vanhyprarch show > "$output" 2>/dev/null &&
            grep -Fq 'target vanhyprarch.idle' "$output" &&
            grep -Fq 'function refresh(): void' "$output"; then
            return 0
        fi
        kill -0 "${quickshell_pid:-$launcher_pid}" 2>/dev/null ||
            fail 'Quickshell exited while waiting for IPC registration'
        attempts=$((attempts + 1))
        sleep 0.05
    done
    fail 'idle IPC target did not register'
}

run_qs()
{
    env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
        QS_NO_RELOAD_POPUP=1 \
        HOME="$temporary/home" \
        XDG_CONFIG_HOME="$config_home" \
        XDG_RUNTIME_DIR="$runtime" \
        PATH="$fixture_bin:$PATH" \
        IDLE_SYNC_ROOT="$fixture_root" \
        qs "$@"
}

command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'

config_home=$temporary/config-home
config=$config_home/quickshell/vanhyprarch
fixture_root=$temporary/fixture
fixture_bin=$temporary/bin
log=$temporary/quickshell.log
mkdir -m 0700 -p -- "$config" "$config_home/hypr" "$fixture_root" \
    "$fixture_bin" "$temporary/home"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
    "$config/components"
cp -- "$test_dir/idle-ipc-registration.qml" "$config/shell.qml"
ln -s "$test_dir/idle-sync-fixture-backend" \
    "$fixture_bin/vanhyprarch-idle"
printf '%s\n' on > "$fixture_root/state"
: > "$fixture_root/status.log"
printf '# fixture\n# Caffeine: on\n' \
    > "$config_home/hypr/vanhyprarch-idle.conf"

run_qs -n --no-color --log-times \
    --log-rules 'quickshell.ipchandler.debug=true' \
    -c vanhyprarch > "$log" 2>&1 &
launcher_pid=$!

wait_for_log_count 'Configuration Loaded' 1
wait_for_log_count VANHYPRARCH_IDLE_IPC_READY 1
wait_for_status_count 1
grep -Fq 'VANHYPRARCH_IDLE_IPC_READY caffeine=on' "$log" ||
    fail 'startup did not project authoritative state changed while shell was down'
quickshell_pid=$(run_qs list --all |
    sed -n 's/^  Process ID: \([0-9][0-9]*\)$/\1/p')
[ -n "$quickshell_pid" ] || fail 'could not resolve the registered Quickshell PID'

wait_for_ipc_target "$temporary/ipc-before"

statuses=$(wc -l < "$fixture_root/status.log")
run_qs ipc -c vanhyprarch call vanhyprarch.idle refresh >/dev/null
wait_for_status_count "$((statuses + 1))"

loaded=$(grep -F -c 'Configuration Loaded' "$log")
ready=$(grep -F -c VANHYPRARCH_IDLE_IPC_READY "$log")
printf '%s\n' '// same-process IPC registration reload' >> "$config/shell.qml"
wait_for_log_count 'Configuration Loaded' "$((loaded + 1))"
wait_for_log_count VANHYPRARCH_IDLE_IPC_READY "$((ready + 1))"

kill -0 "$quickshell_pid" 2>/dev/null ||
    fail 'same-process reload replaced the Quickshell process'
[ "$(run_qs list --all | grep -F -c 'Instance ')" -eq 1 ] ||
    fail 'reload did not retain exactly one Quickshell instance'
run_qs list --all | grep -Fq "Process ID: $quickshell_pid" ||
    fail 'reload did not retain the original Quickshell PID'

wait_for_ipc_target "$temporary/ipc-after"

statuses=$(wc -l < "$fixture_root/status.log")
run_qs ipc -c vanhyprarch call vanhyprarch.idle refresh >/dev/null
wait_for_status_count "$((statuses + 1))"
sleep 0.1
[ "$(wc -l < "$fixture_root/status.log")" -eq "$((statuses + 1))" ] ||
    fail 'one IPC refresh caused multiple authoritative status reads'

printf '%s\n' 'Idle IPC eager-registration tests: PASS'
