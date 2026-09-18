#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
idle=$repository_dir/bin/vanhyprarch-idle
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-idle-test.XXXXXX")

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
    printf 'vanhyprarch-idle test: %s\n' "$*" >&2
    exit 1
}

require_line()
{
    inspected_text=$1
    expected_line=$2
    printf '%s\n' "$inspected_text" | grep -Fx "$expected_line" >/dev/null ||
        fail "missing line: $expected_line"
}

reject_command()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail "command unexpectedly succeeded: $*"
    fi
}

idle_source=$(cat -- "$idle")
require_line "$idle_source" '        [ "$daemon_arguments" = '\''/usr/bin/hypridle -v'\'' ]'
require_line "$idle_source" '    daemon_path=$(tr '\''\0'\'' '\''\n'\'' < "/proc/$daemon_pid/environ" |'
require_line "$idle_source" '    PATH="$daemon_path" command -v hypridle >/dev/null'
require_line "$idle_source" '    PATH="$daemon_path" command -v vanhyprarch-idle >/dev/null'
require_line "$idle_source" '    PATH="$daemon_path" command -v vanhyprarch-screensaver >/dev/null'
require_line "$idle_source" '    launch_hypridle "$daemon_path" "$hypridle_log"'
require_line "$idle_source" '                if launch_hypridle "$daemon_path" "$rollback_log" &&'
require_line "$idle_source" '    launch_command="exec env PATH=$quoted_path hypridle -v > $quoted_log 2>&1"'
require_line "$idle_source" '    flock -u 8 || fail '\''could not release the Power & Idle backend lock'\'''
require_line "$idle_source" '    exec 8>&- || fail '\''could not close the Power & Idle backend lock descriptor'\'''
require_line "$idle_source" '    exec /usr/bin/hypridle -v'
require_line "$idle_source" '    [ "$session_uid" -ne 0 ] || fail '\''session-start must not run as root'\'''
require_line "$idle_source" '    [ "$parent_executable" = /usr/bin/Hyprland ] ||'
require_line "$idle_source" '    [ "$parent_uid" = "$current_uid" ] ||'
require_line "$idle_source" '    /usr/bin/stat -c '\''%u'\'' -- "/proc/$1"'
require_line "$idle_source" '    [ "$#" -eq 2 ] && [ "$2" = "$parent_start_before" ] ||'

session_start_source=$(sed -n \
    '/^validate_session_start_ownership()/,/^release_backend_lock()/p' "$idle")
if printf '%s\n' "$session_start_source" | grep -Fq 'get_hyprland_instance'; then
    fail 'session-start ownership still depends on global Hyprland instance discovery'
fi

mkdir -p "$test_dir/home/.config/vanhyprarch" \
    "$test_dir/home/.config/hypr" "$test_dir/runtime"
export HOME=$test_dir/home
export XDG_CONFIG_HOME=$HOME/.config
export XDG_RUNTIME_DIR=$test_dir/runtime
preferences=$XDG_CONFIG_HOME/vanhyprarch/power-idle.conf
managed_fragment=$XDG_CONFIG_HOME/hypr/vanhyprarch-idle.conf

cat > "$preferences" <<'EOF'
version=1
screensaver=120
display=300
suspend=600
lock=display
EOF
chmod 600 "$preferences"
"$idle" render 120 300 600 display off colormix > "$managed_fragment"
chmod 600 "$managed_fragment"

status=$($idle status)
require_line "$status" 'version=2'
require_line "$status" 'screensaver=120'
require_line "$status" 'display=300'
require_line "$status" 'suspend=600'
require_line "$status" 'lock=display'
require_line "$status" 'effect=colormix'
require_line "$status" 'caffeine=off'
require_line "$status" 'effective_listeners=3'
grep -Fqx 'version=1' "$preferences" ||
    fail 'observational status rewrote the legacy preference file'

for effect in colormix matrix doom gameoflife; do
    "$idle" set effect "$effect" >/dev/null
    require_line "$("$idle" status)" "effect=$effect"
    grep -Fqx 'version=2' "$preferences" || fail 'effect update did not migrate to version 2'
done

"$idle" render 120 300 600 display on gameoflife > "$managed_fragment"
reject_command "$idle" status
grep -Fq 'deployed hypridle configuration does not match current Power & Idle state' \
    "$test_dir/rejected.err" || fail 'status did not report an incoherent fragment'
"$idle" render 120 300 600 display off gameoflife > "$managed_fragment"

cp "$preferences" "$test_dir/preferences.before-invalid"
reject_command "$idle" set effect ''
reject_command "$idle" set effect 'matrix;touch-injected'
reject_command "$idle" set effect unknown
cmp -s "$preferences" "$test_dir/preferences.before-invalid" ||
    fail 'invalid effect changed preferences'

rendered=$($idle render 10 20 30 none off matrix)
[ "$(printf '%s\n' "$rendered" | grep -c '^listener {$')" -eq 3 ] ||
    fail 'expected one listener per enabled stage'
[ "$(printf '%s\n' "$rendered" | grep -c 'vanhyprarch-screensaver start')" -eq 1 ] ||
    fail 'screensaver start listener missing'
[ "$(printf '%s\n' "$rendered" | grep -c 'vanhyprarch-screensaver stop')" -eq 1 ] ||
    fail 'screensaver resume action missing'
if printf '%s\n' "$rendered" | grep -Eq 'ignore_inhibit|/usr/bin/true'; then
    fail 'obsolete input-only workaround remains in rendered output'
fi
require_line "$rendered" '    on-resume = hyprctl dispatch '\''hl.dsp.dpms({ action = "enable" })'\'''
require_line "$rendered" '    on-timeout = systemctl suspend'

locked=$($idle render 10 20 30 screensaver off colormix)
require_line "$locked" '    on-resume = loginctl lock-session'
[ "$(printf '%s\n' "$locked" | grep -c 'vanhyprarch-screensaver stop' || true)" -eq 0 ] ||
    fail 'screen-lock listener unexpectedly stops before unlock'

display_locked=$($idle render 10 20 30 display off colormix)
require_line "$display_locked" '    on-timeout = loginctl lock-session && hyprctl dispatch '\''hl.dsp.dpms({ action = "disable" })'\'''

caffeinated=$($idle render 10 20 30 none on doom)
[ "$(printf '%s\n' "$caffeinated" | grep -c '^listener {$' || true)" -eq 0 ] ||
    fail 'Caffeine output contains listeners'
require_line "$caffeinated" '# Automatic Power & Idle actions are disabled.'

"$idle" validate 1 never never none colormix >/dev/null
reject_command "$idle" validate 10 10 never none colormix
reject_command "$idle" validate 20 10 30 none colormix
reject_command "$idle" validate never never never screensaver colormix
reject_command "$idle" validate never never never none '$(touch injected)'

mkdir "$test_dir/bin"
cat > "$test_dir/bin/loginctl" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$MOCK_LOGINCTL_LOG"
EOF
chmod 755 "$test_dir/bin/loginctl"
export MOCK_LOGINCTL_LOG=$test_dir/loginctl.log
PATH=$test_dir/bin:$PATH
export PATH
cat > "$preferences" <<'EOF'
version=2
screensaver=120
display=300
suspend=600
lock=suspend
effect=colormix
EOF
"$idle" before-sleep
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 1 ] ||
    fail 'selected lock stage did not lock before sleep'
printf 'on\n' > "$XDG_RUNTIME_DIR/vanhyprarch/caffeine"
"$idle" before-sleep
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 1 ] ||
    fail 'Caffeine did not suppress before-sleep locking'

command -v bwrap >/dev/null 2>&1 ||
    fail 'bubblewrap is required for the session-start exec test'

session_root=$test_dir/session-start
session_home=$session_root/home
session_runtime=$session_root/runtime
session_bin=$session_root/bin
session_preferences=$session_home/.config/vanhyprarch/power-idle.conf
session_hypr_dir=$session_home/.config/hypr
session_fragment=$session_hypr_dir/vanhyprarch-idle.conf
session_exec_log=$session_root/exec.log
session_exec_probe=$session_root/hypridle-exec-probe
session_parent_probe=$session_root/Hyprland
session_parent_source=$session_root/Hyprland.c
session_identity_probe=$session_root/identity-change-probe
session_real_stat=$session_root/real-stat
session_hyprctl_log=$session_root/hyprctl.log
session_error_record=$session_runtime/vanhyprarch/session-start-error.log
mkdir -p "$session_home/.config/vanhyprarch" "$session_hypr_dir" \
    "$session_runtime" "$session_bin"

command -v cc >/dev/null 2>&1 ||
    fail 'a C compiler is required for the session-start parent fixture'

cat > "$session_parent_source" <<'EOF'
#include <errno.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

int
main(int argc, char **argv)
{
    int status;
    pid_t child;

    if (argc != 2)
        return 64;
    child = fork();
    if (child == -1)
        return 70;
    if (child == 0) {
        execl("/bin/sh", "sh", "-c", "exec \"$1\" session-start",
            "session-start-launch", argv[1], (char *)0);
        return 71;
    }
    while (waitpid(child, &status, 0) == -1) {
        if (errno != EINTR)
            return 72;
    }
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    if (WIFSIGNALED(status))
        return 128 + WTERMSIG(status);
    return 73;
}
EOF
cc -std=c99 -Wall -Wextra -Werror -o "$session_parent_probe" \
    "$session_parent_source"
cp -- /usr/bin/stat "$session_real_stat"
chmod 755 "$session_real_stat"

{
    printf '%s\n' '#!/bin/sh' 'set -u'
    sed -n '/^validate_session_start_ownership()/,/^}/p' "$idle"
    cat <<'EOF'
fail()
{
    printf '%s\n' "$*" >&2
    exit 1
}
is_unsigned_integer()
{
    case ${1-} in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}
read_process_identity()
{
    identity_count=0
    if [ -f "$IDENTITY_COUNT_FILE" ]; then
        identity_count=$(cat "$IDENTITY_COUNT_FILE")
    fi
    identity_count=$((identity_count + 1))
    printf '%s\n' "$identity_count" > "$IDENTITY_COUNT_FILE"
    case $identity_count in
        1) printf '%s 100\n' "$PPID" ;;
        2) printf '1 111\n' ;;
        *) printf '1 222\n' ;;
    esac
}
read_process_uid()
{
    /usr/bin/id -u
}
current_uid=$(/usr/bin/id -u)
validate_session_start_ownership
EOF
} > "$session_identity_probe"
chmod 755 "$session_identity_probe"

cat > "$session_hypr_dir/hypridle.conf" <<'EOF'
general {
    before_sleep_cmd = vanhyprarch-idle before-sleep
}
source = ./vanhyprarch-idle.conf
EOF

cat > "$session_bin/hyprctl" <<'EOF'
#!/bin/sh
if [ "${1-}" = instances ]; then
    printf 'instances\n' >> "$MOCK_HYPRCTL_LOG"
    if [ "${MOCK_ALLOW_INSTANCES:-false}" = true ]; then
        printf 'instance test-signature:\n'
        printf '\tpid: 4242\n'
        exit 0
    fi
    exit 97
fi
if [ "${1-}" = -i ] && [ "${3-}" = eval ]; then
    /usr/bin/sleep 300 &
    replacement_pid=$!
    printf '%s\n' "$replacement_pid" > "$MOCK_DAEMON_PID_FILE"
    printf '0\n' > "$MOCK_PGREP_COUNT_FILE"
    printf '2\n' > "$MOCK_PGREP_LIMIT_FILE"
    launch_count=0
    if [ -f "$MOCK_LAUNCH_COUNT_FILE" ]; then
        launch_count=$(cat "$MOCK_LAUNCH_COUNT_FILE")
    fi
    launch_count=$((launch_count + 1))
    printf '%s\n' "$launch_count" > "$MOCK_LAUNCH_COUNT_FILE"
    listener_count=$(grep -c '^listener {$' \
        "$XDG_CONFIG_HOME/hypr/vanhyprarch-idle.conf" 2>/dev/null || true)
    for launch_log in "$MOCK_MANAGED_LOG" \
        "$XDG_RUNTIME_DIR"/vanhyprarch/hypridle-rollback.*.log; do
        [ -e "$launch_log" ] || continue
        if [ "${MOCK_FAIL_FIRST_LAUNCH:-false}" = true ] && \
            [ "$launch_count" -eq 1 ]; then
            printf 'found %s rules\nfound %s rules\n' \
                "$listener_count" "$listener_count" > "$launch_log"
        else
            printf 'found %s rules\n' "$listener_count" > "$launch_log"
            if [ "$listener_count" -eq 0 ]; then
                printf 'Config has errors:\nNo rules configured\nProceeding ignoring faulty entries\n' \
                    >> "$launch_log"
            fi
        fi
    done
    exit 0
fi
exit 1
EOF

cat > "$session_bin/ps" <<'EOF'
#!/bin/sh
case $* in
    *'ppid='*) printf '4242\n' ;;
    *'args='*) printf 'hypridle -v\n' ;;
    *) exit 1 ;;
esac
EOF

cat > "$session_bin/systemctl" <<'EOF'
#!/bin/sh
case $* in
    '--user is-enabled hypridle.service') printf 'disabled\n' ;;
    '--user is-active hypridle.service') printf 'inactive\n' ;;
    *) exit 1 ;;
esac
EOF

cat > "$session_bin/stat" <<'EOF'
#!/bin/sh
case ${MOCK_WRONG_PARENT_UID:-false}:$* in
    true:'-c %u -- /proc/'[0-9]*)
        current_uid=$(/usr/bin/id -u)
        printf '%s\n' "$((current_uid + 1))"
        ;;
    *) "$MOCK_REAL_STAT" "$@" ;;
esac
EOF

cat > "$session_bin/hypridle" <<'EOF'
#!/bin/sh
if [ "${MOCK_VALIDATION_FAIL:-false}" = true ]; then
    printf 'forced validation failure\n'
    exit 1
fi
count=$(grep -c '^listener {$' ./vanhyprarch-idle.conf 2>/dev/null || true)
index=0
while [ "$index" -lt "$count" ]; do
    printf 'Registered timeout rule for test\n'
    index=$((index + 1))
done
if [ "$count" -eq 0 ]; then
    printf 'Config has errors:\n'
    printf 'No rules configured\n'
    printf 'Proceeding ignoring faulty entries\n'
fi
EOF

cat > "$session_bin/pgrep" <<'EOF'
#!/bin/sh
if [ -f "$MOCK_DAEMON_PID_FILE" ]; then
    daemon_pid=$(cat "$MOCK_DAEMON_PID_FILE")
    pgrep_count=$(cat "$MOCK_PGREP_COUNT_FILE")
    pgrep_limit=$(cat "$MOCK_PGREP_LIMIT_FILE")
    pgrep_count=$((pgrep_count + 1))
    printf '%s\n' "$pgrep_count" > "$MOCK_PGREP_COUNT_FILE"
    if [ "$pgrep_count" -le "$pgrep_limit" ]; then
        printf '%s\n' "$daemon_pid"
        exit 0
    fi
fi
exit 1
EOF

cat > "$session_bin/readlink" <<'EOF'
#!/bin/sh
case ${1-} in
    /proc/[0-9]*/exe) printf '/usr/bin/hypridle\n' ;;
    *) /usr/bin/readlink "$@" ;;
esac
EOF

cat > "$session_bin/vanhyprarch-idle" <<'EOF'
#!/bin/sh
exit 0
EOF

cat > "$session_bin/vanhyprarch-screensaver" <<'EOF'
#!/bin/sh
exit 0
EOF

cat > "$session_exec_probe" <<'EOF'
#!/bin/sh
{
    printf 'argv=%s\n' "$*"
    printf 'path=%s\n' "$PATH"
    if [ -e /proc/$$/fd/8 ]; then
        printf 'fd8=open\n'
    else
        printf 'fd8=closed\n'
    fi
    error_fd=closed
    for inspected_fd in /proc/$$/fd/*; do
        fd_target=$(/usr/bin/readlink "$inspected_fd" 2>/dev/null || true)
        case $fd_target in
            *session-start-error.log*) error_fd=open ;;
        esac
    done
    printf 'error_fd=%s\n' "$error_fd"
    parent_pid=$(sed -n 's/^[0-9][0-9]* ([^)]*) [A-Z] \([0-9][0-9]*\) .*/\1/p' \
        "/proc/$$/stat")
    printf 'parent_executable=%s\n' \
        "$(/usr/bin/readlink -f "/proc/$parent_pid/exe")"
    exec 9> "$XDG_RUNTIME_DIR/vanhyprarch/idle.lock"
    if flock -n 9; then
        printf 'lock=released\n'
    else
        printf 'lock=held\n'
    fi
} > "$MOCK_EXEC_LOG"
EOF
chmod 755 "$session_bin/hyprctl" "$session_bin/ps" \
    "$session_bin/systemctl" "$session_bin/stat" "$session_bin/hypridle" \
    "$session_bin/pgrep" "$session_bin/readlink" \
    "$session_bin/vanhyprarch-idle" \
    "$session_bin/vanhyprarch-screensaver" "$session_exec_probe"

session_path=$session_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

write_session_preferences()
{
    session_lock=$1
    cat > "$session_preferences" <<EOF
version=2
screensaver=37
display=91
suspend=143
lock=$session_lock
effect=matrix
EOF
    chmod 600 "$session_preferences"
}

write_stale_session_fragment()
{
    cat > "$session_fragment" <<'EOF'
# Generated by vanhyprarch-idle. Do not edit.
# Stored: screensaver=37 display=91 suspend=143 lock=display effect=matrix
# Caffeine: on
# Automatic Power & Idle actions are disabled.
EOF
    chmod 600 "$session_fragment"
}

run_session_start()
{
    validation_failure=${1:-false}
    parent_mode=${2:-hyprland}
    wrong_parent_uid=${3:-false}
    if [ "$parent_mode" = hyprland ]; then
        parent_bind="--ro-bind $session_parent_probe /usr/bin/Hyprland"
        parent_command=/usr/bin/Hyprland
    else
        parent_bind=
        parent_command=$session_parent_probe
    fi
    # Word splitting is intentional for the fixed, test-owned bwrap bind tuple.
    # shellcheck disable=SC2086
    bwrap --ro-bind / / --proc /proc --dev /dev --unshare-pid --die-with-parent \
        --bind "$session_root" "$session_root" \
        --ro-bind "$session_exec_probe" /usr/bin/hypridle \
        --ro-bind "$session_bin/stat" /usr/bin/stat \
        $parent_bind \
        /usr/bin/env -i \
            HOME="$session_home" \
            XDG_CONFIG_HOME="$session_home/.config" \
            XDG_RUNTIME_DIR="$session_runtime" \
            PATH="$session_path" \
            MOCK_EXEC_LOG="$session_exec_log" \
            MOCK_VALIDATION_FAIL="$validation_failure" \
            MOCK_WRONG_PARENT_UID="$wrong_parent_uid" \
            MOCK_REAL_STAT="$session_real_stat" \
            MOCK_HYPRCTL_LOG="$session_hyprctl_log" \
            MOCK_DAEMON_PID_FILE="$session_root/daemon.pid" \
            MOCK_PGREP_COUNT_FILE="$session_root/pgrep-count" \
            MOCK_PGREP_LIMIT_FILE="$session_root/pgrep-limit" \
            MOCK_LAUNCH_COUNT_FILE="$session_root/launch-count" \
            MOCK_MANAGED_LOG="$session_runtime/vanhyprarch/hypridle-managed.log" \
            "$parent_command" "$idle"
}

if bwrap --ro-bind / / --proc /proc --dev /dev --unshare-user --uid 0 \
    /usr/bin/env -i PATH=/usr/bin:/bin \
    /bin/sh "$idle" session-start > "$session_root/root.out" \
    2> "$session_root/root.err"; then
    fail 'session-start unexpectedly accepted root'
fi
grep -Fq 'session-start must not run as root' "$session_root/root.err" ||
    fail 'session-start root rejection was not reported clearly'

write_session_preferences display
write_stale_session_fragment
mkdir -p "$session_runtime/vanhyprarch"
printf 'obsolete startup failure\n' > "$session_error_record"
chmod 600 "$session_error_record"
rm -f "$session_hyprctl_log"
run_session_start
[ ! -e "$session_runtime/vanhyprarch/caffeine" ] ||
    fail 'session-start created a Caffeine marker in a fresh runtime directory'
require_line "$(cat "$session_exec_log")" 'argv=-v'
require_line "$(cat "$session_exec_log")" "path=$session_path"
require_line "$(cat "$session_exec_log")" 'fd8=closed'
require_line "$(cat "$session_exec_log")" 'error_fd=closed'
require_line "$(cat "$session_exec_log")" 'parent_executable=/usr/bin/Hyprland'
require_line "$(cat "$session_exec_log")" 'lock=released'
[ ! -e "$session_error_record" ] ||
    fail 'successful session-start retained a stale runtime error record'
[ ! -e "$session_hyprctl_log" ] ||
    fail 'early session-start invoked hyprctl instances'
require_line "$(cat "$session_fragment")" '# Caffeine: off'
require_line "$(cat "$session_fragment")" '# Stored: screensaver=37 display=91 suspend=143 lock=display effect=matrix'
[ "$(grep -c '^listener {$' "$session_fragment")" -eq 3 ] ||
    fail 'session-start did not restore all configured listeners'
require_line "$(cat "$session_fragment")" '    on-timeout = loginctl lock-session && hyprctl dispatch '\''hl.dsp.dpms({ action = "disable" })'\'''

first_session_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
run_session_start
second_session_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
[ "$first_session_digest" = "$second_session_digest" ] ||
    fail 'session-start was not idempotent for an already coherent session'

write_stale_session_fragment
mkdir -p "$session_runtime/vanhyprarch"
printf 'on\n' > "$session_runtime/vanhyprarch/caffeine"
run_session_start
[ ! -e "$session_runtime/vanhyprarch/caffeine" ] ||
    fail 'session-start did not remove a prior Caffeine marker'
require_line "$(cat "$session_fragment")" '# Caffeine: off'

for session_lock_point in screensaver display suspend; do
    write_session_preferences "$session_lock_point"
    write_stale_session_fragment
    printf 'on\n' > "$session_runtime/vanhyprarch/caffeine"
    run_session_start
    [ "$(grep -c '^listener {$' "$session_fragment")" -eq 3 ] ||
        fail "session-start omitted a listener for lock=$session_lock_point"
    case $session_lock_point in
        screensaver)
            require_line "$(cat "$session_fragment")" \
                '    on-resume = loginctl lock-session'
            ;;
        display)
            require_line "$(cat "$session_fragment")" \
                '    on-timeout = loginctl lock-session && hyprctl dispatch '\''hl.dsp.dpms({ action = "disable" })'\'''
            ;;
        suspend)
            require_line "$(cat "$session_fragment")" \
                '    on-timeout = systemctl suspend'
            grep -Fq 'before_sleep_cmd = vanhyprarch-idle before-sleep' \
                "$session_hypr_dir/hypridle.conf" ||
                fail 'suspend lock path lost the conditional pre-sleep hook'
            ;;
    esac
done

write_session_preferences display
write_stale_session_fragment
printf 'on\n' > "$session_runtime/vanhyprarch/caffeine"
stale_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
rm -f "$session_exec_log"
if run_session_start true > "$session_root/failure.out" \
    2> "$session_root/failure.err"; then
    fail 'session-start unexpectedly succeeded after candidate validation failed'
fi
[ ! -e "$session_exec_log" ] ||
    fail 'session-start executed hypridle after candidate validation failed'
[ ! -e "$session_runtime/vanhyprarch/caffeine" ] ||
    fail 'failed session-start retained a prior-session Caffeine marker'
[ "$stale_digest" = "$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')" ] ||
    fail 'session-start published a fragment that failed validation'
[ -z "$(find "$session_hypr_dir" -maxdepth 1 \
    -name '.vanhyprarch-idle.conf.*' -print -quit)" ] ||
    fail 'session-start left a failed candidate behind'
grep -Fq 'generated hypridle configuration did not parse as expected' \
    "$session_root/failure.err" ||
    fail 'session-start validation failure was not reported clearly'
[ "$(wc -l < "$session_error_record")" -eq 1 ] ||
    fail 'session-start failure record was not exactly one line'
[ "$(stat -c '%a' "$session_error_record")" = 600 ] ||
    fail 'session-start failure record did not have mode 0600'
grep -Fq 'generated hypridle configuration did not parse as expected' \
    "$session_error_record" ||
    fail 'session-start failure record did not contain the reported error'

write_stale_session_fragment
stale_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
if run_session_start false wrong-executable > "$session_root/wrong-parent.out" \
    2> "$session_root/wrong-parent.err"; then
    fail 'session-start accepted a same-name parent at the wrong executable path'
fi
[ "$stale_digest" = "$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')" ] ||
    fail 'wrong-parent rejection published a candidate fragment'
grep -Fq 'session-start parent executable is not /usr/bin/Hyprland' \
    "$session_error_record" ||
    fail 'later session-start failure did not overwrite the runtime record'
if grep -Fq 'generated hypridle configuration did not parse as expected' \
    "$session_error_record"; then
    fail 'session-start failure record was appended instead of overwritten'
fi

write_stale_session_fragment
stale_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
if run_session_start false hyprland true > "$session_root/wrong-uid.out" \
    2> "$session_root/wrong-uid.err"; then
    fail 'session-start accepted a Hyprland parent owned by another user'
fi
[ "$stale_digest" = "$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')" ] ||
    fail 'wrong-parent-UID rejection published a candidate fragment'
grep -Fq 'session-start parent is not owned by the current user' \
    "$session_root/wrong-uid.err" ||
    fail 'wrong-parent-UID rejection was not reported clearly'

write_stale_session_fragment
stale_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
if bwrap --ro-bind / / --proc /proc --dev /dev --unshare-pid --die-with-parent \
    --bind "$session_root" "$session_root" \
    --ro-bind "$session_exec_probe" /usr/bin/hypridle \
    --ro-bind "$session_bin/stat" /usr/bin/stat \
    /usr/bin/env -i \
        HOME="$session_home" XDG_CONFIG_HOME="$session_home/.config" \
        XDG_RUNTIME_DIR="$session_runtime" PATH="$session_path" \
        MOCK_EXEC_LOG="$session_exec_log" \
        MOCK_REAL_STAT="$session_real_stat" \
        MOCK_HYPRCTL_LOG="$session_hyprctl_log" \
        MOCK_DAEMON_PID_FILE="$session_root/daemon.pid" \
        MOCK_PGREP_COUNT_FILE="$session_root/pgrep-count" \
        MOCK_PGREP_LIMIT_FILE="$session_root/pgrep-limit" \
        /bin/sh "$idle" session-start > "$session_root/invalid-parent.out" \
        2> "$session_root/invalid-parent.err"; then
    fail 'session-start accepted an invalid init-like parent'
fi
[ "$stale_digest" = "$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')" ] ||
    fail 'invalid-parent rejection published a candidate fragment'

rm -f "$session_root/identity-count"
if bwrap --ro-bind / / --proc /proc --dev /dev --unshare-pid --die-with-parent \
    --bind "$session_root" "$session_root" \
    --ro-bind "$session_parent_probe" /usr/bin/Hyprland \
    /usr/bin/env -i PATH="$session_path" \
        IDENTITY_COUNT_FILE="$session_root/identity-count" \
        MOCK_DAEMON_PID_FILE="$session_root/nonexistent-daemon" \
        /usr/bin/Hyprland "$session_identity_probe" \
        > "$session_root/identity-change.out" \
        2> "$session_root/identity-change.err"; then
    fail 'session-start ownership accepted a changed parent start time'
fi
grep -Fq 'session-start parent identity changed during validation' \
    "$session_root/identity-change.err" ||
    fail 'changed parent start time was not rejected clearly'

transaction_runner=$session_root/transaction-runner
cat > "$transaction_runner" <<'EOF'
#!/bin/sh
set -u

cleanup_transaction_daemon()
{
    cleanup_status=$?
    trap - 0 HUP INT TERM
    if [ -f "$MOCK_DAEMON_PID_FILE" ]; then
        cleanup_pid=$(cat "$MOCK_DAEMON_PID_FILE")
        kill "$cleanup_pid" 2>/dev/null || true
    fi
    exit "$cleanup_status"
}
trap cleanup_transaction_daemon 0 HUP INT TERM

/usr/bin/sleep 300 &
printf '%s\n' "$!" > "$MOCK_DAEMON_PID_FILE"
printf '0\n' > "$MOCK_PGREP_COUNT_FILE"
printf '1\n' > "$MOCK_PGREP_LIMIT_FILE"
"$IDLE_UNDER_TEST" caffeine "$CAFFEINE_OPERATION"
EOF
chmod 755 "$transaction_runner"

run_caffeine_transaction()
{
    caffeine_operation=$1
    fail_first_launch=${2:-false}
    rm -f "$session_root/daemon.pid" "$session_root/launch-count"
    bwrap --ro-bind / / --proc /proc --dev /dev --unshare-pid --die-with-parent \
        --bind "$session_root" "$session_root" \
        /usr/bin/env -i \
            HOME="$session_home" \
            XDG_CONFIG_HOME="$session_home/.config" \
            XDG_RUNTIME_DIR="$session_runtime" \
            PATH="$session_path" \
            HYPRLAND_INSTANCE_SIGNATURE=test-signature \
            IDLE_UNDER_TEST="$idle" \
            CAFFEINE_OPERATION="$caffeine_operation" \
            MOCK_DAEMON_PID_FILE="$session_root/daemon.pid" \
            MOCK_PGREP_COUNT_FILE="$session_root/pgrep-count" \
            MOCK_PGREP_LIMIT_FILE="$session_root/pgrep-limit" \
            MOCK_LAUNCH_COUNT_FILE="$session_root/launch-count" \
            MOCK_MANAGED_LOG="$session_runtime/vanhyprarch/hypridle-managed.log" \
            MOCK_FAIL_FIRST_LAUNCH="$fail_first_launch" \
            MOCK_REAL_STAT="$session_real_stat" \
            MOCK_ALLOW_INSTANCES=true \
            MOCK_HYPRCTL_LOG="$session_hyprctl_log" \
            /bin/sh "$transaction_runner"
}

write_session_preferences display
"$idle" render 37 91 143 display off matrix > "$session_fragment"
rm -f "$session_runtime/vanhyprarch/caffeine"
if ! run_caffeine_transaction on > "$session_root/caffeine-on.out" \
    2> "$session_root/caffeine-on.err"; then
    sed -n '1,160p' "$session_root/caffeine-on.err" >&2
    if [ -f "$session_runtime/vanhyprarch/hypridle-managed.log" ]; then
        sed -n '1,160p' "$session_runtime/vanhyprarch/hypridle-managed.log" >&2
    fi
    fail 'manual Caffeine ON transaction failed'
fi
require_line "$(cat "$session_fragment")" '# Caffeine: on'
[ "$(grep -c '^listener {$' "$session_fragment" || true)" -eq 0 ] ||
    fail 'manual Caffeine ON retained automatic listeners'
require_line "$(cat "$session_runtime/vanhyprarch/caffeine")" 'on'

run_caffeine_transaction off >/dev/null
require_line "$(cat "$session_fragment")" '# Caffeine: off'
[ "$(grep -c '^listener {$' "$session_fragment")" -eq 3 ] ||
    fail 'manual Caffeine OFF did not restore configured listeners'
[ ! -e "$session_runtime/vanhyprarch/caffeine" ] ||
    fail 'manual Caffeine OFF retained its runtime marker'

rollback_fragment_digest=$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')
if run_caffeine_transaction on true > "$session_root/rollback.out" \
    2> "$session_root/rollback.err"; then
    fail 'manual Caffeine transaction unexpectedly survived a bad replacement'
fi
[ "$rollback_fragment_digest" = \
    "$(sha256sum "$session_fragment" | sed 's/[[:space:]].*$//')" ] ||
    fail 'manual Caffeine rollback did not restore the prior fragment'
[ ! -e "$session_runtime/vanhyprarch/caffeine" ] ||
    fail 'manual Caffeine rollback did not restore the prior OFF marker state'
[ "$(cat "$session_root/launch-count")" -eq 2 ] ||
    fail 'manual Caffeine rollback did not launch exactly one rollback daemon'
grep -Fq 'restored previous hypridle configuration' \
    "$session_root/rollback.err" ||
    fail 'manual Caffeine rollback did not report restored daemon state'

printf 'vanhyprarch-idle tests: PASS\n'
