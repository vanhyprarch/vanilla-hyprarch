#!/bin/sh

set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$test_dir/.." && pwd)
temporary=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-idle-sync.XXXXXX")

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
    printf 'Power & Idle synchronization test: %s\n' "$*" >&2
    exit 1
}

command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'

"$test_dir/idle-ipc-registration.sh"

controller=$repository_dir/home/.config/quickshell/vanhyprarch/components/IdleController.qml
dock=$repository_dir/home/.config/quickshell/vanhyprarch/components/PowerIdle.qml
panel=$repository_dir/home/.config/quickshell/vanhyprarch/components/PowerIdlePanel.qml
shell=$repository_dir/home/.config/quickshell/vanhyprarch/shell.qml

grep -Fq 'interval: 30000' "$controller" ||
    fail 'the reconciliation timer is not exactly 30000 ms'
[ "$(grep -F -c 'interval: 30000' "$controller")" -eq 1 ] ||
    fail 'the controller does not contain exactly one 30000 ms timer'
if grep -Eq 'interval:[[:space:]]*([0-9]{1,4}|[12][0-9]{4})$' "$controller"
then
    fail 'a faster numeric polling timer was introduced'
fi
if grep -RIn -E 'pendingCaffeine|visualCaffeine' "$controller" "$dock" "$panel"
then
    fail 'unconfirmed Caffeine state still drives presentation'
fi
grep -Fq 'root.controller.caffeine' "$dock" ||
    fail 'dock icon is not driven by confirmed controller state'
[ "$(grep -F -c 'root.controller.caffeine' "$panel")" -ge 2 ] ||
    fail 'panel presentation is not driven by confirmed controller state'
grep -Fq 'target: "vanhyprarch.idle"' "$shell" ||
    fail 'ShellRoot does not expose the authoritative refresh IPC target'
grep -Fq 'function refresh(): void' "$shell" ||
    fail 'ShellRoot does not expose the refresh IPC method'
grep -Fq 'idleController.refreshStatus(true)' "$shell" ||
    fail 'refresh IPC does not request authoritative status'
if grep -Eq 'setCaffeine|caffeineChanged|idleController\.caffeine[[:space:]]*=' \
    "$shell"; then
    fail 'refresh IPC can assign Caffeine presentation state'
fi
if grep -Eq 'FileView|managedFragment|watchChanges' "$controller"; then
    fail 'rejected Caffeine FileView transport remains in IdleController'
fi
grep -Fq 'IdleController {' "$shell" ||
    fail 'the IPC-owning IdleController is not instantiated by ShellRoot'
run_controller_scenario()
{
    name=$1
    initial=$2
    target=$3
    origin=$4
    outcome=$5
    scenario=$temporary/$name
    config=$scenario/quickshell
    config_home=$scenario/config-home
    runtime=$scenario/runtime
    fixture_root=$scenario/fixture
    fixture_bin=$scenario/bin
    mkdir -m 0700 -p -- "$config" "$config_home/hypr" "$runtime" \
        "$fixture_root" "$fixture_bin"
    ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
        "$config/components"
    ln -s "$test_dir/idle-controller-sync.qml" "$config/shell.qml"
    ln -s "$test_dir/idle-sync-fixture-backend" \
        "$fixture_bin/vanhyprarch-idle"
    printf '%s\n' "$initial" > "$fixture_root/state"
    : > "$fixture_root/status.log"
    printf '# fixture\n# Caffeine: %s\n' "$initial" \
        > "$config_home/hypr/vanhyprarch-idle.conf"
    chmod 600 -- "$config_home/hypr/vanhyprarch-idle.conf"
    log=$scenario/quickshell.log
    if ! env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
        HOME="$scenario/home" \
        XDG_CONFIG_HOME="$config_home" \
        XDG_RUNTIME_DIR="$runtime" \
        PATH="$fixture_bin:$PATH" \
        IDLE_SYNC_ROOT="$fixture_root" \
        IDLE_SYNC_INITIAL="$initial" \
        IDLE_SYNC_TARGET="$target" \
        IDLE_SYNC_ORIGIN="$origin" \
        IDLE_SYNC_OUTCOME="$outcome" \
        IDLE_SYNC_BACKEND="$test_dir/idle-sync-fixture-backend" \
        IDLE_SYNC_ACTION_OUTCOME="$outcome" \
        timeout 12s qs --no-color -p "$config" > "$log" 2>&1
    then
        cat "$log" >&2
        fail "$name controller fixture failed"
    fi
    grep -Fq VANHYPRARCH_IDLE_CONTROLLER_PASS "$log" || {
        cat "$log" >&2
        fail "$name did not report controller success"
    }
}

run_controller_scenario external-off-on off on external success
run_controller_scenario external-on-off on off external success
run_controller_scenario controller-off-on off on controller success
run_controller_scenario controller-on-off on off controller success
run_controller_scenario controller-off-on-rollback off on controller rollback
run_controller_scenario controller-on-off-rollback on off controller rollback
run_controller_scenario fragment-burst off on burst success
run_controller_scenario rapid-external-transactions off on rapid success
run_controller_scenario status-error-recovery off off status-recovery success

printf '%s\n' 'Power & Idle IPC/static synchronization tests: PASS'
