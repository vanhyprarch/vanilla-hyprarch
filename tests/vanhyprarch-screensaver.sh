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
export MOCK_CURSOR_STATE=$test_dir/cursor
export MOCK_EFFECT=$test_dir/effect
printf 'false\n' > "$MOCK_CURSOR_STATE"
printf 'colormix\n' > "$MOCK_EFFECT"

cat > "$test_dir/bin/hyprctl" <<'EOF'
#!/bin/sh
if [ "${1-}" = getoption ]; then
    printf 'bool: '
    cat "$MOCK_CURSOR_STATE"
    exit 0
fi
case $* in
    *'invisible = true'*) printf 'true\n' > "$MOCK_CURSOR_STATE" ;;
    *'invisible = false'*) printf 'false\n' > "$MOCK_CURSOR_STATE" ;;
    *) exit 1 ;;
esac
EOF
cat > "$test_dir/bin/vanhyprarch-idle" <<'EOF'
#!/bin/sh
[ "$#" -eq 1 ] && [ "$1" = screensaver-effect ] || exit 2
cat "$MOCK_EFFECT"
EOF
chmod 755 "$test_dir/bin/hyprctl" "$test_dir/bin/vanhyprarch-idle"
export PATH=$test_dir/bin:/usr/bin

reject_command "$controller" status
reject_command "$controller" start
grep -Fq 'not installed or not on PATH' "$test_dir/rejected.err" ||
    fail 'missing-player error was not clear'
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'missing player changed the cursor'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'missing player left ownership state'

mock_player_source=$(command -v cat) || fail 'cat is required for this test'
cp -- "$mock_player_source" "$test_dir/bin/vanhyprarch-zig-player"
for effect in colormix matrix doom gameoflife; do
    mkfifo "$XDG_RUNTIME_DIR/vanhyprarch/$effect"
done

printf 'matrix;touch injected\n' > "$MOCK_EFFECT"
reject_command "$controller" start
grep -Fq 'invalid configured screensaver effect' "$test_dir/rejected.err" ||
    fail 'invalid effect was not rejected'
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'invalid effect changed the cursor'

for effect in colormix matrix doom gameoflife; do
    printf '%s\n' "$effect" > "$MOCK_EFFECT"
    start_output=$($controller start)
    printf '%s\n' "$start_output" | grep -Fq "effect $effect" ||
        fail "start did not report $effect"
    state_file=$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state
    player_pid=$(sed -n 's/^pid=//p' "$state_file")
    owned_test_pids="$owned_test_pids $player_pid"
    status_output=$($controller status)
    printf '%s\n' "$status_output" | grep -Fq "effect $effect" ||
        fail "status did not report $effect"
    repeated_output=$($controller start)
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
"$controller" start >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
"$controller" stop >/dev/null
[ "$(cat "$MOCK_CURSOR_STATE")" = true ] ||
    fail 'pre-existing invisible cursor state was not restored exactly'
printf 'false\n' > "$MOCK_CURSOR_STATE"

"$controller" start >/dev/null
player_pid=$(sed -n 's/^pid=//p' "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state")
owned_test_pids="$owned_test_pids $player_pid"
kill -TERM "$player_pid"
wait "$player_pid" 2>/dev/null || true
reject_command "$controller" status
"$controller" stop >/dev/null
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'dead-process cleanup did not restore cursor'

printf 'invalid-state\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state"
printf 'false\n' > "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor"
"$controller" stop >/dev/null
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'malformed state was not removed'

/bin/sleep 60 &
unrelated_pid=$!
owned_test_pids="$owned_test_pids $unrelated_pid"
unrelated_start=$(process_start_time "$unrelated_pid")
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
"$controller" start >/dev/null
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
reject_command "$controller" start
[ "$(cat "$MOCK_CURSOR_STATE")" = false ] ||
    fail 'failed startup did not restore cursor'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.state" ] ||
    fail 'failed startup left ownership state'
[ ! -e "$XDG_RUNTIME_DIR/vanhyprarch/screensaver.cursor" ] ||
    fail 'failed startup left cursor ownership state'

printf 'vanhyprarch-screensaver tests: PASS\n'
