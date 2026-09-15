#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/home/.config/quickshell/vanhyprarch/helpers/vanhyprarch_text_size
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-text-size-test.XXXXXX")

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
    printf 'vanhyprarch text-size test: %s\n' "$*" >&2
    exit 1
}

reject_command()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail "command unexpectedly succeeded: $*"
    fi
}

mkdir -p "$test_dir/home" "$test_dir/config/foot" "$test_dir/mock-bin"
real_foot=$(command -v foot) || fail 'Foot is unavailable'
export HOME=$test_dir/home
export XDG_CONFIG_HOME=$test_dir/config
export PATH=$test_dir/mock-bin:/usr/bin
export MOCK_GSETTINGS_STATE=$test_dir/gsettings-factor
export REAL_FOOT_COMMAND=$real_foot
printf '1.0\n' > "$MOCK_GSETTINGS_STATE"

cat > "$test_dir/mock-bin/gsettings" <<'EOF'
#!/bin/sh
set -eu
case $1:$2:$3 in
    get:org.gnome.desktop.interface:font-name)
        printf "'Adwaita Sans 11'\n"
        ;;
    get:org.gnome.desktop.interface:text-scaling-factor)
        cat "$MOCK_GSETTINGS_STATE"
        ;;
    set:org.gnome.desktop.interface:text-scaling-factor)
        [ "${MOCK_GSETTINGS_FAIL:-0}" = 0 ] || exit 1
        printf '%s\n' "$4" > "$MOCK_GSETTINGS_STATE"
        ;;
    *) exit 2 ;;
esac
EOF
cat > "$test_dir/mock-bin/foot" <<'EOF'
#!/bin/sh
exec "$REAL_FOOT_COMMAND" "$@"
EOF
chmod 755 "$test_dir/mock-bin/gsettings" "$test_dir/mock-bin/foot"

preference_dir=$XDG_CONFIG_HOME/vanhyprarch
preference_file=$preference_dir/text-size.conf
foot_file=$XDG_CONFIG_HOME/foot/foot.ini
cat > "$foot_file" <<'EOF'
[main]
font=Iosevka:size=12
pad=8x8
EOF

status=$(sh "$helper" status)
printf '%s\n' "$status" | grep -Fxq 'size=12' || fail 'missing preference did not use 12'
printf '%s\n' "$status" | grep -Fxq 'explicit=no' || fail 'default was reported as explicit'
[ ! -e "$preference_file" ] || fail 'status created a preference file'

reject_command sh "$helper" set 8
reject_command sh "$helper" set 21
reject_command sh "$helper" set 12.5
[ ! -e "$preference_file" ] || fail 'invalid input created a preference file'

for requested_size in 9 10 11 12 13 14 15 16 17 18 19 20; do
    result=$(sh "$helper" set "$requested_size")
    printf '%s\n' "$result" | grep -Fxq "size=$requested_size" ||
        fail "accepted size was not reported: $requested_size"
    printf '%s\n' "$result" | grep -Fxq 'foot=updated' ||
        fail "Foot was not updated for size $requested_size"
    grep -Fxq "font=Iosevka:size=$requested_size" "$foot_file" ||
        fail "Foot point size did not preserve the Vanilla baseline for $requested_size"
    [ "$(cat "$preference_file")" = "version=1
size=$requested_size" ] || fail "preference did not persist size $requested_size"
    case $requested_size in
        12)
            [ "$(cat "$MOCK_GSETTINGS_STATE")" = 1.0000 ] ||
                fail 'Text Size 12 did not preserve the GTK 1.0 baseline'
            ;;
        16)
            [ "$(cat "$MOCK_GSETTINGS_STATE")" = 1.3636 ] ||
                fail 'Text Size 16 did not use the expected GTK projection'
            ;;
    esac
done

# GTK projection is intentionally consumer-specific. With the fixture's
# 11-point GTK font, Text Size 16 quantizes to 15/11.
result=$(sh "$helper" set 16)
[ "$(cat "$MOCK_GSETTINGS_STATE")" = 1.3636 ] ||
    fail 'GTK factor was not quantized independently'
grep -Fxq 'font=Iosevka:size=16' "$foot_file" ||
    fail 'Text Size 16 did not project to Foot 16 pt'
grep -Fxq 'pad=8x8' "$foot_file" || fail 'unrelated Foot configuration changed'
[ "$(cat "$preference_file")" = "version=1
size=16" ] || fail 'preference contents are invalid'
[ "$(stat -c '%a' "$preference_dir")" = 700 ] || fail 'preference directory is not private'
[ "$(stat -c '%a' "$preference_file")" = 600 ] || fail 'preference file is not private'

cp "$preference_file" "$test_dir/preference.before-failure"
cp "$foot_file" "$test_dir/foot.before-failure"
printf '1.3636\n' > "$MOCK_GSETTINGS_STATE"
export MOCK_GSETTINGS_FAIL=1
reject_command sh "$helper" set 17
unset MOCK_GSETTINGS_FAIL
cmp -s "$preference_file" "$test_dir/preference.before-failure" ||
    fail 'failed GTK projection changed the preference'
cmp -s "$foot_file" "$test_dir/foot.before-failure" ||
    fail 'failed GTK projection changed Foot'

rm -f "$foot_file"
cat > "$foot_file" <<'EOF'
include=~/.config/foot/private.ini
EOF
result=$(sh "$helper" set 12)
printf '%s\n' "$result" | grep -Fxq 'foot=unmanaged' ||
    fail 'an indirect Foot configuration was not left unmanaged'
[ "$(cat "$foot_file")" = 'include=~/.config/foot/private.ini' ] ||
    fail 'an indirect Foot configuration was modified'

rm -f "$preference_file"
ln -s "$test_dir/outside" "$preference_file"
reject_command sh "$helper" set 12
[ ! -e "$test_dir/outside" ] || fail 'preference symlink target was written'

[ -z "$(find "$XDG_CONFIG_HOME" -type f -name '.*.text-size.*' -o -name '.text-size.*')" ] ||
    fail 'temporary files remained after the test'

command -v qs >/dev/null 2>&1 || fail 'Quickshell is unavailable'
cp "$script_dir/text-size-controller.qml" "$test_dir/shell.qml"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" \
    "$test_dir/components"
mkdir -m 700 "$test_dir/runtime"
qml_log=$test_dir/quickshell.log
if ! env -u WAYLAND_DISPLAY \
    QT_QPA_PLATFORM=offscreen \
    XDG_RUNTIME_DIR=$test_dir/runtime \
    timeout 10s qs --no-color -p "$test_dir/shell.qml" \
        > "$qml_log" 2>&1
then
    cat "$qml_log" >&2
    fail 'offscreen text-size controller self-check failed'
fi
grep -Fq 'vanhyprarch text-size controller self-check passed' "$qml_log" || {
    cat "$qml_log" >&2
    fail 'text-size controller self-check did not report success'
}
unexpected_diagnostics=$(
    grep -E '(^|[[:space:]])(WARN|ERROR)([[:space:]]|:)' "$qml_log" |
        grep -Fv 'quickshell.ipc: Failed to start IPC server' || true
)
[ -z "$unexpected_diagnostics" ] || {
    cat "$qml_log" >&2
    fail 'text-size controller self-check emitted unexpected diagnostics'
}

printf '%s\n' 'vanhyprarch text-size self-check passed'
