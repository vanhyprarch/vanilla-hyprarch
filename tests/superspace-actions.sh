#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-superspace-test.XXXXXX")
process_fixture=$repository_dir/tests/system-components-process-fixture.py
terminal_helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_terminal_operation
foot_fixture=$repository_dir/tests/terminal-operation-foot-fixture.py

cleanup()
{
    status=$?
    trap - 0 HUP INT TERM
    rm -rf -- "$test_dir"
    exit "$status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'SuperSpace test: %s\n' "$*" >&2
    exit 1
}

command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'
[ -x "$process_fixture" ] || fail 'system-component process fixture is not executable'
[ -x "$terminal_helper" ] || fail 'terminal-operation helper is not executable'
[ -x "$foot_fixture" ] || fail 'Foot process fixture is not executable'

ln -s "$process_fixture" "$test_dir/component-process-success"
ln -s "$process_fixture" "$test_dir/component-process-failure"
ln -s "$process_fixture" "$test_dir/component-manager-success"
ln -s "$process_fixture" "$test_dir/component-manager-failure"

grep -Fq 'onClicked: superSpace.toggle()' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/shell.qml" ||
    fail 'dock logo no longer uses the shared SuperSpace controller'
grep -Fq 'vanhyprarch.superSpace toggle' \
    "$repository_dir/home/.config/hypr/vanhyprarch/bindings.lua" ||
    fail 'Super+Space no longer uses the shared SuperSpace IPC controller'
grep -Fq 'root.refreshAll()' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SystemComponentsActions.qml" ||
    fail 'component status is not refreshed after terminal operations'
grep -Fq 'return [hyprctlExecutable, "reload"]' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SystemComponentsActions.qml" ||
    fail 'component lifecycle does not use exact shell-free Hyprland reload argv'
grep -Fq 'label: "Additional system components"' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpace.qml" ||
    fail 'Additional system components root label is not exact'
grep -Fq 'detail: "Install and configure optional Vanilla HyprArch components"' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpace.qml" ||
    fail 'Additional system components description is not exact'
grep -Fq ': "Additional system components"' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpacePanel.qml" ||
    fail 'Additional system components heading is not exact'
if grep -Fq 'Additional System Components' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpace.qml" \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpacePanel.qml"
then
    fail 'old Additional System Components capitalization remains in UI paths'
fi
grep -Fq 'This will remove Voxtype, its configuration, and all downloaded speech models.' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpace.qml" ||
    fail 'Local Dictation uninstall confirmation does not disclose data deletion'
grep -Fq 'Will remain available so Local Dictation can be installed again later.' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpace.qml" ||
    fail 'Local Dictation uninstall confirmation does not disclose manager retention'
grep -Fq 'root.controller.componentSubview === "uninstall" ? "Uninstall Local Dictation?"' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpacePanel.qml" ||
    fail 'Local Dictation uninstall heading is not exact'
if grep -Eqi 'preserv(e|ing).*(config|model)|(config|model).*preserv' \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components/SuperSpace.qml"
then
    fail 'old config/model preservation wording remains in Local Dictation UI'
fi

run_qml_test()
{
    test_name=$1
    success_message=$2
    config_dir=$test_dir/$test_name
    runtime_dir=$config_dir/runtime
    mkdir -m 0700 -p -- "$runtime_dir"
    ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
        "$config_dir/components"
    sed 's#import "../home/.config/quickshell/vanhyprarch/components"#import "components"#' \
        "$script_dir/$test_name.qml" > "$config_dir/shell.qml"
    log=$config_dir/quickshell.log
    if ! env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
        XDG_RUNTIME_DIR=$runtime_dir \
        VANHYPRARCH_COMPONENT_PROCESS_SUCCESS=$test_dir/component-process-success \
        VANHYPRARCH_COMPONENT_PROCESS_FAILURE=$test_dir/component-process-failure \
        VANHYPRARCH_COMPONENT_MANAGER_SUCCESS=$test_dir/component-manager-success \
        VANHYPRARCH_COMPONENT_MANAGER_FAILURE=$test_dir/component-manager-failure \
        VANHYPRARCH_TERMINAL_HELPER=$terminal_helper \
        VANHYPRARCH_FOOT_FIXTURE=$foot_fixture \
        timeout 10s qs --no-color -p "$config_dir" \
        > "$log" 2>&1
    then
        cat "$log" >&2
        fail "$test_name failed"
    fi
    grep -Fq "$success_message" "$log" || {
        cat "$log" >&2
        fail "$test_name did not report success"
    }
}

run_qml_test install-actions 'vanhyprarch Install action self-check passed'
run_qml_test remove-actions 'vanhyprarch Remove action self-check passed'
run_qml_test update-actions 'vanhyprarch Update action self-check passed'
run_qml_test system-components 'vanhyprarch system-components self-check passed'

printf '%s\n' 'SuperSpace action/controller tests: PASS'
