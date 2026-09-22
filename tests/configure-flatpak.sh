#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
helper=$repository_dir/install/configure-flatpak
package_manifest=$repository_dir/packages/manifest-v1.toml
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

python - "$package_manifest" <<'PY' || fail 'flatpak package policy is invalid'
import sys
import tomllib
from pathlib import Path

with Path(sys.argv[1]).open("rb") as stream:
    packages = tomllib.load(stream)["package"]
flatpak = [item for item in packages if item["name"] == "flatpak"]
assert len(flatpak) == 1
assert flatpak[0]["source"] == "official"
assert flatpak[0]["role"] == "required"
assert flatpak[0]["default_install"] is True
assert "version" not in flatpak[0]
PY

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
