#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
controller=$repository_dir/bin/vanhyprarch-screensaver
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-screensaver-test.XXXXXX")
owned_test_pids=

cleanup()
{
    cleanup_status=$?
    trap - 0 HUP INT TERM
    for cleanup_pid in $owned_test_pids; do
        kill -TERM "$cleanup_pid" 2>/dev/null || true
    done
    rm -rf -- "$test_dir"
    exit "$cleanup_status"
}
trap cleanup 0 HUP INT TERM

fail()
{
    printf 'vanhyprarch-screensaver test: %s\n' "$*" >&2
    exit 1
}

reject_command()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail "command unexpectedly succeeded: $*"
    fi
}

process_start_time()
{
    awk '{ print $22 }' "/proc/$1/stat"
}

write_state()
{
    state_pid=$1
    state_start=$2
    state_executable=$3
    state_effect=$4
    cat > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" <<EOF
version=1
pid=$state_pid
start_time=$state_start
executable=$state_executable
effect=$state_effect
EOF
    chmod 600 "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state"
}

mkdir -p "$test_dir/bin" "$test_dir/runtime/vanhyprarch"
export XDG_RUNTIME_DIR=$test_dir/runtime
export HOME=$test_dir/home
mkdir -p "$HOME"
export VANHYPRARCH_ALLOW_TEST_OVERRIDES=1
export VANHYPRARCH_ZIG_SCREENSAVER_MANAGER=$test_dir/bin/zig-component-manager
export MOCK_CURSOR_STATE=$test_dir/cursor
export MOCK_EFFECT=$test_dir/effect
printf 'false\n' > "$MOCK_CURSOR_STATE"
printf 'colormix\n' > "$MOCK_EFFECT"

cat > "$VANHYPRARCH_ZIG_SCREENSAVER_MANAGER" <<'EOF'
#!/bin/sh
[ "$#" -eq 1 ] && [ "$1" = component-capability ] || exit 2
printf 'installed\n'
EOF
chmod 755 "$VANHYPRARCH_ZIG_SCREENSAVER_MANAGER"

cat > "$test_dir/bin/hyprctl" <<'EOF'
#!/bin/sh
if [ "${1-}" = getoption ]; then
    printf 'bool: '
    cat "$MOCK_CURSOR_STATE"
    exit 0
fi
[ ! -e "${MOCK_CURSOR_FAILURE:-/nonexistent}" ] || exit 1
case $* in
    *'invisible = true'*) printf 'true\n' > "$MOCK_CURSOR_STATE" ;;
    *'invisible = false'*) printf 'false\n' > "$MOCK_CURSOR_STATE" ;;
    *) exit 1 ;;
esac
EOF
cat > "$test_dir/bin/vanhyprarch-idle" <<'EOF'
#!/bin/sh
case ${1-} in
    screensaver-effect) cat "$MOCK_EFFECT" ;;
    screensaver-resume-lock) printf '%s\n' "${MOCK_RESUME_LOCK:-off}" ;;
    *) exit 2 ;;
esac
EOF
cat > "$test_dir/bin/loginctl" <<'EOF'
#!/bin/sh
[ "$#" -eq 1 ] && [ "$1" = lock-session ] || exit 2
printf 'lock-session\n' >> "$MOCK_LOGINCTL_LOG"
EOF
export MOCK_LOGINCTL_LOG=$test_dir/loginctl.log
: > "$MOCK_LOGINCTL_LOG"
chmod 755 "$test_dir/bin/hyprctl" "$test_dir/bin/vanhyprarch-idle"
chmod 755 "$test_dir/bin/loginctl"
export PATH=$test_dir/bin:/usr/bin

ln -s "$test_dir/lock-target" "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.lock"
reject_command "$controller" status
grep -Fq 'lock must not be a symbolic link' "$test_dir/rejected.err" ||
    fail 'symlinked runtime lock was not rejected'
rm -f "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.lock"
mkdir "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.lock"
reject_command "$controller" status
grep -Fq 'lock must be a regular file' "$test_dir/rejected.err" ||
    fail 'wrong-type runtime lock was not rejected'
rmdir "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.lock"

reject_command "$controller" status
[ "$(stat -c '%a' "$XDG_RUNTIME_DIR/vanhyprarch")" = 700 ] ||
    fail 'runtime root was not protected with mode 0700'
reject_command "$controller" start
grep -Fq 'plain start is intentionally disabled' "$test_dir/rejected.err" ||
    fail 'plain interactive start was not rejected'
reject_command "$controller" start --idle
grep -Fq 'not installed or not on PATH' "$test_dir/rejected.err" ||
    fail "missing-player error was not clear: $(cat "$test_dir/rejected.err")"
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'missing player changed the cursor'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'missing player left ownership state'

mock_player_source=$(command -v cat) || fail 'cat is required for this test'
cp -- "$mock_player_source" "$test_dir/bin/vanhyprarch-zig-player"
for effect in colormix matrix doom gameoflife; do
    mkfifo "$XDG_RUNTIME_DIR/vanhyprarch/$effect"
done

printf 'matrix\n' > "$MOCK_EFFECT"
"$controller" start --idle > "$test_dir/concurrent-one.out" &
concurrent_one=$!
"$controller" start --idle > "$test_dir/concurrent-two.out" &
concurrent_two=$!
wait "$concurrent_one"
wait "$concurrent_two"
concurrent_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
[ -n "$concurrent_pid" ] || fail 'concurrent starts did not publish one owner'
[ "$(grep -h -c '^started (pid\|^running (pid' \
    "$test_dir/concurrent-one.out" "$test_dir/concurrent-two.out" | awk '{ total += $1 } END { print total }')" -eq 2 ] ||
    fail 'concurrent starts were not serialized into start plus idempotent result'
"$controller" stop >/dev/null

export VANHYPRARCH_SCREENSAVER_TEST_SECONDS=1
export MOCK_RESUME_LOCK=on
printf 'colormix\n' > "$MOCK_EFFECT"
test_output=$("$controller" test)
printf '%s\n' "$test_output" | grep -Fq 'stopping automatically after 1 seconds' ||
    fail 'bounded manual test did not disclose its timeout'
reject_command "$controller" status
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'bounded manual test did not restore the cursor'
[ ! -s "$MOCK_LOGINCTL_LOG" ] ||
    fail 'bounded manual test armed Automatic Lock'
export MOCK_RESUME_LOCK=off

ln -s "$test_dir/log-target" "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.log"
reject_command "$controller" start --idle
grep -Fq 'log must not be a symbolic link' "$test_dir/rejected.err" ||
    fail 'symlinked runtime log was not rejected'
rm -f "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.log"
mkdir "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.log"
reject_command "$controller" start --idle
grep -Fq 'log must be a regular file' "$test_dir/rejected.err" ||
    fail 'wrong-type runtime log was not rejected'
rmdir "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.log"

export MOCK_CURSOR_FAILURE=$test_dir/cursor-failure
printf 'colormix\n' > "$MOCK_EFFECT"
"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
: > "$MOCK_CURSOR_FAILURE"
reject_command "$controller" stop
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'cursor failure prevented exact process-state cleanup'
[ -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ] ||
    fail 'cursor failure discarded pending restoration state'
kill -0 "$player_pid" 2>/dev/null &&
    fail 'cursor failure prevented owned process termination'
rm -f "$MOCK_CURSOR_FAILURE"
"$controller" stop >/dev/null
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'later idempotent stop did not finish cursor restoration'

printf 'matrix;touch injected\n' > "$MOCK_EFFECT"
reject_command "$controller" start --idle
grep -Fq 'invalid configured screensaver effect' "$test_dir/rejected.err" ||
    fail 'invalid effect was not rejected'
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'invalid effect changed the cursor'

for effect in colormix matrix doom gameoflife; do
    printf '%s\n' "$effect" > "$MOCK_EFFECT"
    start_output=$($controller start --idle)
    printf '%s\n' "$start_output" | grep -Fq "effect $effect" ||
        fail "start did not report $effect"
    state_file=$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state
    player_pid=$(sed -n 's/^pid=//p' "$state_file")
    owned_test_pids="$owned_test_pids $player_pid"
    status_output=$($controller status)
    printf '%s\n' "$status_output" | grep -Fq "effect $effect" ||
        fail "status did not report $effect"
    repeated_output=$($controller start --idle)
    printf '%s\n' "$repeated_output" | grep -Fq "pid $player_pid" ||
        fail 'repeated start did not retain the owned PID'
    [ "$(cat "$MOCK_CURSOR_STATE")" = true ] || fail 'start did not hide cursor'
    "$controller" stop >/dev/null
    [ "$(cat "$MOCK_CURSOR_STATE")" = false ] || fail 'stop did not restore cursor'
    "$controller" stop >/dev/null
    reject_command "$controller" status
done

printf 'true\n' > "$MOCK_CURSOR_STATE"
printf 'colormix\n' > "$MOCK_EFFECT"
"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
"$controller" stop >/dev/null
[ "$(cat "$MOCK_CURSOR_STATE")" = true ] ||
    fail 'pre-existing invisible cursor state was not restored exactly'
printf 'false\n' > "$MOCK_CURSOR_STATE"

export MOCK_RESUME_LOCK=on
"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
[ ! -s "$MOCK_LOGINCTL_LOG" ] ||
    fail 'protected Screensaver locked immediately at timeout'
"$controller" resume-lock
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 1 ] ||
    fail 'normal Screensaver resume did not request authentication exactly once'
kill -0 "$player_pid" ||
    fail 'resume authentication stopped the visible Screensaver before unlock'
grep -Fq 'protected=off' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ||
    fail 'resume authentication did not disarm duplicate protected-exit locking'
"$controller" stop >/dev/null
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 1 ] ||
    fail 'post-authentication cleanup requested a duplicate session lock'
export MOCK_RESUME_LOCK=off

"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
kill -TERM "$player_pid"
wait "$player_pid" 2>/dev/null || true
recovery_attempt=0
while [ "$recovery_attempt" -lt 40 ] &&
    [ -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ]; do
    sleep 0.05
    recovery_attempt=$((recovery_attempt + 1))
done
reject_command "$controller" status
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'unexpected player exit did not restore cursor automatically'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ] ||
    fail 'unexpected player exit left cursor recovery pending'

export MOCK_RESUME_LOCK=on
"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
kill -TERM "$player_pid"
wait "$player_pid" 2>/dev/null || true
recovery_attempt=0
while [ "$recovery_attempt" -lt 40 ] &&
    [ -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ]; do
    sleep 0.05
    recovery_attempt=$((recovery_attempt + 1))
done
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 2 ] ||
    fail 'protected unexpected exit did not arm authentication before recovery'
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'protected unexpected exit did not restore cursor after locking'
export MOCK_RESUME_LOCK=off

export MOCK_RESUME_LOCK=on
"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
"$controller" stop >/dev/null
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 3 ] ||
    fail 'explicit protected stop did not secure the session before cleanup'
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'explicit protected stop did not restore the cursor after locking'
export MOCK_RESUME_LOCK=off

printf 'invalid-state\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state"
printf 'false\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
reject_command "$controller" resume-lock
[ "$(grep -Fxc 'lock-session' "$MOCK_LOGINCTL_LOG")" -eq 4 ] ||
    fail 'invalid resume ownership state did not fail closed with authentication'
"$controller" stop >/dev/null
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'malformed state was not removed'

ln -s /dev/null "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state"
reject_command "$controller" status
"$controller" stop >/dev/null
[ ! -L "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'symlink runtime state was not rejected and removed safely'
ln -s /dev/null "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
reject_command "$controller" stop
[ -L "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ] ||
    fail 'ambiguous cursor symlink was deleted automatically'
rm -f "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"

/bin/sleep 60 &
unrelated_pid=$!
owned_test_pids="$owned_test_pids $unrelated_pid"
unrelated_start=$(process_start_time "$unrelated_pid")
write_state "$unrelated_pid" "$unrelated_start" \
    "$test_dir/bin/vanhyprarch-zig-player" colormix
printf 'false\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
"$controller" recover-exit 999999 1 \
    "$test_dir/bin/vanhyprarch-zig-player" matrix off
[ -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] &&
    [ -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ] ||
    fail 'an obsolete watcher removed newer runtime ownership state'
kill -0 "$unrelated_pid" || fail 'an obsolete watcher affected a newer process'
"$controller" stop >/dev/null

write_state "$unrelated_pid" "$((unrelated_start + 1))" \
    "$test_dir/bin/vanhyprarch-zig-player" colormix
printf 'false\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
"$controller" stop >/dev/null
kill -0 "$unrelated_pid" || fail 'PID-reuse defense signalled an unrelated process'

write_state "$unrelated_pid" "$unrelated_start" \
    "$test_dir/bin/vanhyprarch-zig-player" colormix
printf 'false\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
"$controller" stop >/dev/null
kill -0 "$unrelated_pid" || fail 'executable mismatch signalled an unrelated process'

(
    cd "$XDG_RUNTIME_DIR/vanhyprarch"
    exec setsid "$test_dir/bin/vanhyprarch-zig-player" matrix
) &
mismatch_pid=$!
owned_test_pids="$owned_test_pids $mismatch_pid"
mismatch_attempt=0
while [ "$mismatch_attempt" -lt 40 ]; do
    observed_executable=$(readlink "/proc/$mismatch_pid/exe" 2>/dev/null || true)
    [ "$observed_executable" = "$test_dir/bin/vanhyprarch-zig-player" ] && break
    sleep 0.05
    mismatch_attempt=$((mismatch_attempt + 1))
done
[ "$observed_executable" = "$test_dir/bin/vanhyprarch-zig-player" ] ||
    fail 'argument-mismatch fixture did not start'
mismatch_start=$(process_start_time "$mismatch_pid")
write_state "$mismatch_pid" "$mismatch_start" \
    "$test_dir/bin/vanhyprarch-zig-player" colormix
printf 'false\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
"$controller" stop >/dev/null
kill -0 "$mismatch_pid" || fail 'argument mismatch signalled the player process'

rm -f "$test_dir/bin/vanhyprarch-zig-player" \
    "$XDG_RUNTIME_DIR/vanhyprarch/colormix"
[ -x /usr/bin/bash ] || fail '/usr/bin/bash is required for this test'
cp -- /usr/bin/bash "$test_dir/bin/vanhyprarch-zig-player"
export MOCK_PLAYER_READY=$test_dir/force-stop.ready
cat > "$XDG_RUNTIME_DIR/vanhyprarch/colormix" <<'EOF'
trap '' TERM
printf 'ready\n' > "$MOCK_PLAYER_READY"
read ignored < force-stop-block
EOF
mkfifo "$XDG_RUNTIME_DIR/vanhyprarch/force-stop-block"
printf 'colormix\n' > "$MOCK_EFFECT"
"$controller" start --idle >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
ready_attempt=0
while [ "$ready_attempt" -lt 40 ] && [ ! -f "$MOCK_PLAYER_READY" ]; do
    sleep 0.05
    ready_attempt=$((ready_attempt + 1))
done
[ -f "$MOCK_PLAYER_READY" ] || fail 'force-stop fixture did not become ready'
stop_output=$("$controller" stop)
printf '%s\n' "$stop_output" | grep -Fq 'stopped forcibly' ||
    fail 'SIGKILL fallback was not used after the graceful timeout'

rm -f "$test_dir/bin/vanhyprarch-zig-player"
[ -x /usr/bin/false ] || fail '/usr/bin/false is required for this test'
cp -- /usr/bin/false "$test_dir/bin/vanhyprarch-zig-player"
printf 'false\n' > "$MOCK_CURSOR_STATE"
reject_command "$controller" start --idle
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'failed startup did not restore cursor'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'failed startup left ownership state'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ] ||
    fail 'failed startup left cursor ownership state'

printf 'vanhyprarch-screensaver tests: PASS\n'
