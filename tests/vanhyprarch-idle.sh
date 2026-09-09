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
    printf '%s\n' "$inspected_text" | grep -Fqx "$expected_line" ||
        fail "missing line: $expected_line"
}

reject_command()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail "command unexpectedly succeeded: $*"
    fi
}

mkdir -p "$test_dir/home/.config/vanhyprarch" "$test_dir/runtime"
export HOME=$test_dir/home
export XDG_CONFIG_HOME=$HOME/.config
export XDG_RUNTIME_DIR=$test_dir/runtime
preferences=$XDG_CONFIG_HOME/vanhyprarch/power-idle.conf

cat > "$preferences" <<'EOF'
version=1
screensaver=120
display=300
suspend=600
lock=display
EOF
chmod 600 "$preferences"

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

printf 'vanhyprarch-idle tests: PASS\n'
