#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
installer=$repository_dir/install/install-zig-player
metadata=$repository_dir/install/vanhyprarch-zig-player.conf
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-installer-wrapper.XXXXXX")

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
    printf 'install-zig-player test: %s\n' "$*" >&2
    exit 1
}

for field in VERSION ARCHITECTURE ASSET SHA256 BINARY_SHA256 LICENSE_SHA256 \
    NOTICES_SHA256 README_SHA256 REPOSITORY_URL RELEASE_URL DOWNLOAD_URL \
    SOURCE_TAG_URL SOURCE_ARCHIVE_URL; do
    grep -Eq "^VANHYPRARCH_ZIG_PLAYER_${field}=.+" "$metadata" ||
        fail "canonical metadata is missing $field"
done
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_VERSION=v0.1.1' "$metadata" ||
    fail 'canonical version changed'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_ARCHITECTURE=x86_64' "$metadata" ||
    fail 'canonical architecture changed'
if grep -Fq '/latest/' "$metadata"; then
    fail 'canonical metadata uses floating latest release discovery'
fi

mkdir -p "$test_dir/home/.local/bin"
manager=$test_dir/home/.local/bin/vanhyprarch-screensaver
operation_log=$test_dir/operation.log
export OPERATION_LOG=$operation_log
{
    printf '%s\n' '#!/bin/sh'
    printf '%s\n' 'printf "%s\n" "$*" > "$OPERATION_LOG"'
} > "$manager"
chmod 755 "$manager"

HOME=$test_dir/home "$installer" >/dev/null 2> "$test_dir/warning"
[ "$(cat "$operation_log")" = install ] ||
    fail 'compatibility installer did not delegate exact install operation'
grep -Fq 'compatibility entry point' "$test_dir/warning" ||
    fail 'compatibility delegation was not disclosed'

production_home=$test_dir/production-home
production_data=$test_dir/production-data
production_runtime=$test_dir/production-runtime
mkdir -p "$production_home/.local/bin" \
    "$production_home/.local/install/zig-screensaver" \
    "$production_data" "$production_runtime"
cp -- "$repository_dir/bin/vanhyprarch-screensaver" \
    "$production_home/.local/bin/vanhyprarch-screensaver"
printf '#!/bin/sh\nprintf "unsafe fallback\\n"\n' > \
    "$production_home/.local/install/zig-screensaver/manager.py"
chmod 755 "$production_home/.local/bin/vanhyprarch-screensaver" \
    "$production_home/.local/install/zig-screensaver/manager.py"
if HOME=$production_home XDG_DATA_HOME=$production_data \
    XDG_RUNTIME_DIR=$production_runtime \
    "$production_home/.local/bin/vanhyprarch-screensaver" component-status --json \
    > "$test_dir/production-missing.out" 2> "$test_dir/production-missing.err"; then
    fail 'regular production controller used a source-looking sibling fallback'
fi
grep -Fq 'manager resources are unavailable' "$test_dir/production-missing.err" ||
    fail 'missing production resources did not fail clearly'

dev_home=$test_dir/dev-home
dev_data=$test_dir/dev-data
dev_runtime=$test_dir/dev-runtime
mkdir -p "$dev_home" "$dev_data" "$dev_runtime"
HOME=$dev_home XDG_DATA_HOME=$dev_data XDG_RUNTIME_DIR=$dev_runtime \
    "$repository_dir/bin/vanhyprarch-screensaver" component-status --json \
    > "$test_dir/dev-status.json"
grep -Fq '"state":"not-installed"' "$test_dir/dev-status.json" ||
    fail 'proven source-tree development fallback did not work'

mkdir -p "$production_data/vanhyprarch/zig-screensaver"
cp -- "$repository_dir/install/zig-screensaver/manager.py" \
    "$production_data/vanhyprarch/zig-screensaver/manager.py"
cp -- "$repository_dir/install/vanhyprarch-zig-player.conf" \
    "$production_data/vanhyprarch/zig-screensaver/vanhyprarch-zig-player.conf"
chmod 755 "$production_data/vanhyprarch/zig-screensaver/manager.py"
HOME=$production_home XDG_DATA_HOME=$production_data \
    XDG_RUNTIME_DIR=$production_runtime \
    "$production_home/.local/bin/vanhyprarch-screensaver" component-status --json \
    > "$test_dir/production-status.json"
grep -Fq '"state":"not-installed"' "$test_dir/production-status.json" ||
    fail 'production managed resources required a Git checkout'

printf 'install-zig-player tests: PASS\n'
