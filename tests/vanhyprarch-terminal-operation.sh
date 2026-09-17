#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_terminal_operation
pty_test=$script_dir/vanhyprarch-terminal-operation-pty.py
foot_fixture=$script_dir/terminal-operation-foot-fixture.py
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-terminal-operation-test.XXXXXX")
test_runtime_dir=$test_dir/runtime
mkdir -m 0700 -- "$test_runtime_dir"
export XDG_RUNTIME_DIR=$test_runtime_dir

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
    printf 'vanhyprarch terminal-operation test: %s\n' "$*" >&2
    exit 1
}

command -v python >/dev/null 2>&1 || fail 'python is unavailable'
[ -x "$helper" ] || fail 'helper is not executable'
[ -x "$foot_fixture" ] || fail 'Foot supervision fixture is not executable'

PYTHONPYCACHEPREFIX=$test_dir/pycache python -m py_compile \
    "$helper" "$foot_fixture"

success_log=$test_dir/success.log
printf '\n' | "$helper" /usr/bin/true > "$success_log" 2>&1 ||
    fail 'successful child did not preserve status 0'
grep -Fxq 'Operation finished.' "$success_log" ||
    fail 'successful child completion was not reported'
grep -Fxq 'Press Enter to close.' "$success_log" ||
    fail 'final Enter prompt was not reported'

failure_log=$test_dir/failure.log
set +e
printf '\n' | "$helper" /usr/bin/false > "$failure_log" 2>&1
failure_status=$?
set -e
[ "$failure_status" -eq 1 ] || fail 'failing child status was not preserved'
grep -Fxq 'Operation finished with status 1.' "$failure_log" ||
    fail 'failing child completion was not reported'
grep -Fxq 'Press Enter to close.' "$failure_log" ||
    fail 'failing child did not reach the final Enter prompt'

missing_log=$test_dir/missing.log
set +e
"$helper" > "$missing_log" 2>&1
missing_status=$?
set -e
[ "$missing_status" -eq 64 ] || fail 'empty child command was not rejected'
grep -Fq 'missing child command' "$missing_log" ||
    fail 'empty child command rejection was not explained'

argv_log=$test_dir/argv.log
unevaluated_argument="value; /usr/bin/touch $test_dir/should-not-exist"
printf '\n' | "$helper" /usr/bin/python -c \
    'import sys; print("ARGV=" + repr(sys.argv[1:]))' \
    --noconfirm "$unevaluated_argument" > "$argv_log" 2>&1 ||
    fail 'argv-data child failed'
grep -Fq "ARGV=['--noconfirm', '$unevaluated_argument']" "$argv_log" ||
    fail 'option-like or metacharacter argv data changed'
[ ! -e "$test_dir/should-not-exist" ] ||
    fail 'shell metacharacters were evaluated'

cancel_log=$test_dir/cancel.log
set +e
printf '\n' | "$helper" /usr/bin/python -c \
    'import os, signal; os.kill(os.getpid(), signal.SIGINT)' \
    > "$cancel_log" 2>&1
cancel_status=$?
set -e
[ "$cancel_status" -eq 130 ] || fail 'cancelled child status was not preserved'
grep -Fxq 'Operation cancelled.' "$cancel_log" ||
    fail 'cancelled child completion was not reported'
grep -Fxq 'Press Enter to close.' "$cancel_log" ||
    fail 'cancelled child did not reach the final Enter prompt'

PYTHONPYCACHEPREFIX=$test_dir/pycache python "$pty_test" "$helper"

reported_result=$test_dir/reported-result
printf '\n' | "$helper" --result-file "$reported_result" -- /usr/bin/true \
    > "$test_dir/reported-result.log" 2>&1 ||
    fail 'reported child result did not preserve status 0'
[ "$(cat "$reported_result")" = 0 ] ||
    fail 'reported child result content is invalid'
[ "$(stat -c '%a' "$reported_result")" = 600 ] ||
    fail 'reported child result is not private'

supervised_success_log=$test_dir/supervised-success.log
VANHYPRARCH_TEST_FOOT_STATUS=23 "$helper" --supervise-foot \
    "$foot_fixture" 'Lifecycle test' -- /usr/bin/true \
    > "$supervised_success_log" 2>&1 ||
    fail 'supervisor trusted Foot status instead of successful child result'
grep -Fxq 'Operation finished.' "$supervised_success_log" ||
    fail 'supervised terminal did not retain the normal completion experience'

supervised_failure_log=$test_dir/supervised-failure.log
set +e
VANHYPRARCH_TEST_FOOT_STATUS=0 "$helper" --supervise-foot \
    "$foot_fixture" 'Lifecycle test' -- /usr/bin/false \
    > "$supervised_failure_log" 2>&1
supervised_failure_status=$?
set -e
[ "$supervised_failure_status" -eq 1 ] ||
    fail 'supervisor trusted Foot status instead of failing child result'

missing_result_log=$test_dir/missing-result.log
set +e
VANHYPRARCH_TEST_FOOT_SKIP_CHILD=1 "$helper" --supervise-foot \
    "$foot_fixture" 'Lifecycle test' -- /usr/bin/true \
    > "$missing_result_log" 2>&1
missing_result_status=$?
set -e
[ "$missing_result_status" -ne 0 ] ||
    fail 'supervisor accepted a launcher exit without an operation result'
grep -Fq 'Terminal closed before the operation result was available.' \
    "$missing_result_log" ||
    fail 'missing supervised operation result was not explained'

if grep -Eq 'shell[[:space:]]*=[[:space:]]*True|(/bin|/usr/bin)/(ba)?sh' "$helper"; then
    fail 'helper contains a forbidden shell invocation'
fi

printf '%s\n' 'vanhyprarch terminal-operation self-check passed'
