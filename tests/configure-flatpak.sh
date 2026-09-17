#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/install/configure-flatpak
official_packages=$repository_dir/packages/official.txt
aur_packages=$repository_dir/packages/aur.txt
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-flatpak-test.XXXXXX")

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
    printf 'configure-flatpak test: %s\n' "$*" >&2
    exit 1
}

[ "$(grep -Fxc flatpak "$official_packages")" -eq 1 ] ||
    fail 'flatpak is not exactly once in the official package manifest'
if grep -Eq '^flatpak[^[:alpha:]-]|^flatpak-' "$official_packages"; then
    fail 'flatpak is version-pinned or malformed in the official manifest'
fi
if grep -Eq '^flatpak($|[^[:alpha:]-])' "$aur_packages"; then
    fail 'flatpak was added to the AUR package manifest'
fi

mock_flatpak=$test_dir/flatpak
cat > "$mock_flatpak" <<'EOF'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$VANHYPRARCH_TEST_LOG"
case ${1:-} in
remotes)
    if [ -f "$VANHYPRARCH_TEST_STATE" ]; then
        state=$(cat "$VANHYPRARCH_TEST_STATE")
        case $state in
        correct) printf 'flathub\thttps://dl.flathub.org/repo/\n' ;;
        wrong) printf 'flathub\thttps://example.invalid/repo/\n' ;;
        esac
    fi
    ;;
remote-add)
    [ "$*" = 'remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo' ] ||
        exit 64
    printf '%s\n' correct > "$VANHYPRARCH_TEST_STATE"
    ;;
*) exit 64 ;;
esac
EOF
chmod 755 "$mock_flatpak"

run_helper()
{
    env VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
        VANHYPRARCH_FLATPAK_EXECUTABLE="$mock_flatpak" \
        VANHYPRARCH_TEST_LOG="$test_dir/flatpak.log" \
        VANHYPRARCH_TEST_STATE="$test_dir/flatpak.state" \
        "$helper"
}

: > "$test_dir/flatpak.log"
printf '%s\n' correct > "$test_dir/flatpak.state"
run_helper > "$test_dir/existing.out"
[ "$(wc -l < "$test_dir/flatpak.log")" -eq 1 ] ||
    fail 'existing correct Flathub remote was modified'
grep -Fxq 'remotes --system --columns=name,url' "$test_dir/flatpak.log" ||
    fail 'system remotes were not inspected'

: > "$test_dir/flatpak.log"
rm -f -- "$test_dir/flatpak.state"
run_helper > "$test_dir/created.out"
[ "$(sed -n '2p' "$test_dir/flatpak.log")" = \
    'remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo' ] ||
    fail 'Flathub was not added with the required argv'
[ "$(sed -n '3p' "$test_dir/flatpak.log")" = \
    'remotes --system --columns=name,url' ] ||
    fail 'created Flathub remote was not verified'

: > "$test_dir/flatpak.log"
printf '%s\n' wrong > "$test_dir/flatpak.state"
if run_helper > "$test_dir/wrong.out" 2> "$test_dir/wrong.err"; then
    fail 'conflicting Flathub URL was accepted'
fi
[ "$(wc -l < "$test_dir/flatpak.log")" -eq 1 ] ||
    fail 'conflicting Flathub remote was modified'
grep -Fq 'unexpected URL' "$test_dir/wrong.err" ||
    fail 'conflicting Flathub URL failure was not explained'

printf '%s\n' 'configure-flatpak tests: PASS'
