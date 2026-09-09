#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
installer=$repository_dir/install/install-zig-player
canonical_metadata=$repository_dir/install/vanhyprarch-zig-player.conf
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-installer-test.XXXXXX")

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
    printf 'install-zig-player test: %s\n' "$*" >&2
    exit 1
}

reject_install()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail 'installer unexpectedly succeeded'
    fi
}

grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_VERSION=v0.1.1' "$canonical_metadata" ||
    fail 'canonical version metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_ARCHITECTURE=x86_64' "$canonical_metadata" ||
    fail 'canonical architecture metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_ASSET=vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz' \
    "$canonical_metadata" || fail 'canonical asset metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_SHA256=9bd759283aa823aba124c94d64b9696df670551a1d6418ca1a32194ea0b1a887' \
    "$canonical_metadata" || fail 'canonical checksum metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_REPOSITORY_URL=https://github.com/vanhyprarch/vanhyprarch-zig-player' \
    "$canonical_metadata" || fail 'canonical repository URL metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_RELEASE_URL=https://github.com/vanhyprarch/vanhyprarch-zig-player/releases/tag/v0.1.1' \
    "$canonical_metadata" || fail 'canonical release URL metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_DOWNLOAD_URL=https://github.com/vanhyprarch/vanhyprarch-zig-player/releases/download/v0.1.1/vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz' \
    "$canonical_metadata" || fail 'canonical download URL metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_SOURCE_TAG_URL=https://github.com/vanhyprarch/vanhyprarch-zig-player/tree/v0.1.1' \
    "$canonical_metadata" || fail 'canonical source-tag URL metadata is wrong'
grep -Fqx 'VANHYPRARCH_ZIG_PLAYER_SOURCE_ARCHIVE_URL=https://github.com/vanhyprarch/vanhyprarch-zig-player/archive/refs/tags/v0.1.1.tar.gz' \
    "$canonical_metadata" || fail 'canonical source-archive URL metadata is wrong'
if grep -Fq '/latest/' "$canonical_metadata"; then
    fail 'canonical metadata uses a latest URL'
fi

fixture_root=vanhyprarch-zig-player-v0.0.0-linux-x86_64
fixture_source=$test_dir/$fixture_root
fixture_archive=$test_dir/$fixture_root.tar.gz
mkdir "$fixture_source"
printf '#!/bin/sh\nprintf "fixture player\\n"\n' > \
    "$fixture_source/vanhyprarch-zig-player"
printf 'fixture GPL license\n' > "$fixture_source/LICENSE"
printf 'fixture notices\n' > "$fixture_source/THIRD_PARTY_NOTICES.md"
printf 'fixture readme and source tag\n' > "$fixture_source/README.md"
chmod 755 "$fixture_source/vanhyprarch-zig-player"
tar -czf "$fixture_archive" -C "$test_dir" "$fixture_root"
fixture_sha=$(sha256sum "$fixture_archive" | awk '{ print $1 }')

test_metadata=$test_dir/player.conf
cat > "$test_metadata" <<EOF
VANHYPRARCH_ZIG_PLAYER_VERSION=v0.0.0
VANHYPRARCH_ZIG_PLAYER_ARCHITECTURE=x86_64
VANHYPRARCH_ZIG_PLAYER_ASSET=$fixture_root.tar.gz
VANHYPRARCH_ZIG_PLAYER_SHA256=$fixture_sha
VANHYPRARCH_ZIG_PLAYER_REPOSITORY_URL=https://example.invalid/repository
VANHYPRARCH_ZIG_PLAYER_RELEASE_URL=https://example.invalid/release/v0.0.0
VANHYPRARCH_ZIG_PLAYER_DOWNLOAD_URL=https://example.invalid/download/$fixture_root.tar.gz
VANHYPRARCH_ZIG_PLAYER_SOURCE_TAG_URL=https://example.invalid/source/v0.0.0
VANHYPRARCH_ZIG_PLAYER_SOURCE_ARCHIVE_URL=https://example.invalid/source/v0.0.0.tar.gz
EOF

reject_install env HOME="$test_dir/home" DESTDIR="$test_dir/wrong-arch-root" \
    VANHYPRARCH_TARGET_ARCHITECTURE=aarch64 "$installer"
[ ! -e "$test_dir/wrong-arch-root" ] ||
    fail 'wrong architecture created an installation root'

bad_metadata=$test_dir/bad-player.conf
sed 's/^VANHYPRARCH_ZIG_PLAYER_SHA256=.*/VANHYPRARCH_ZIG_PLAYER_SHA256=0000000000000000000000000000000000000000000000000000000000000000/' \
    "$test_metadata" > "$bad_metadata"
reject_install env HOME="$test_dir/home" DESTDIR="$test_dir/bad-root" \
    VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_ZIG_PLAYER_METADATA="$bad_metadata" \
    VANHYPRARCH_TEST_ARCHIVE="$fixture_archive" "$installer"
[ ! -e "$test_dir/bad-root$test_dir/home/.local/bin/vanhyprarch-zig-player" ] ||
    fail 'checksum mismatch installed an executable'

destination=$test_dir/destination
install_home=/home/test-user
env HOME="$test_dir/home" DESTDIR="$destination" \
    VANHYPRARCH_INSTALL_HOME="$install_home" \
    VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_ZIG_PLAYER_METADATA="$test_metadata" \
    VANHYPRARCH_TEST_ARCHIVE="$fixture_archive" "$installer" >/dev/null

installed_root=$destination$install_home/.local
installed_player=$installed_root/bin/vanhyprarch-zig-player
[ -f "$installed_player" ] || fail 'player was not installed'
[ "$(stat -c '%a' "$installed_player")" = 755 ] ||
    fail 'player mode is not 0755'
cmp -s "$fixture_source/vanhyprarch-zig-player" "$installed_player" ||
    fail 'installed player differs from verified archive'
[ -f "$installed_root/share/licenses/vanhyprarch-zig-player/LICENSE" ] ||
    fail 'LICENSE was not installed'
[ -f "$installed_root/share/licenses/vanhyprarch-zig-player/THIRD_PARTY_NOTICES.md" ] ||
    fail 'THIRD_PARTY_NOTICES.md was not installed'
cmp -s "$test_metadata" \
    "$installed_root/share/doc/vanhyprarch-zig-player/vanhyprarch-zig-player.conf" ||
    fail 'pinned source metadata was not installed'

printf 'install-zig-player tests: PASS\n'
