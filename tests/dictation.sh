#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
component_dir=$repository_dir/install/dictation
installer=$component_dir/install
uninstaller=$component_dir/uninstall
metadata=$component_dir/voxtype.conf
config=$component_dir/config.toml
service=$component_dir/vanhyprarch-voxtype.service
official_manifest=$repository_dir/packages/official.txt
aur_manifest=$repository_dir/packages/aur.txt
optional_manifest=$repository_dir/packages/optional-dictation-official.txt
hyprland_config=$repository_dir/home/.config/hypr/hyprland.lua
bindings=$repository_dir/home/.config/hypr/bindings.lua
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-dictation-test.XXXXXX")

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
    printf 'dictation test: %s\n' "$*" >&2
    exit 1
}

assert_line()
{
    grep -Fqx -- "$1" "$2" || fail "missing exact line in ${2##*/}: $1"
}

reject_install()
{
    if "$@" > "$test_dir/rejected.out" 2> "$test_dir/rejected.err"; then
        fail 'installer unexpectedly succeeded'
    fi
}

reject_uninstall()
{
    if "$@" > "$test_dir/rejected-uninstall.out" 2> "$test_dir/rejected-uninstall.err"; then
        fail 'uninstaller unexpectedly succeeded'
    fi
}

# Optional packaging and pinned release metadata.
! grep -Eq '^(voxtype|voxtype-bin|wtype|gnupg)$' "$official_manifest" ||
    fail 'dictation dependency leaked into the required official manifest'
! grep -Eq '^(voxtype|voxtype-bin)$' "$aur_manifest" ||
    fail 'Voxtype leaked into the AUR manifest'
[ "$(sed '/^[[:space:]]*$/d' "$optional_manifest" | wc -l)" -eq 2 ] ||
    fail 'optional dictation manifest has unexpected entries'
assert_line gnupg "$optional_manifest"
assert_line wtype "$optional_manifest"
assert_line VANHYPRARCH_VOXTYPE_VERSION=1.0.1 "$metadata"
assert_line VANHYPRARCH_VOXTYPE_ASSET=voxtype-1.0.1-linux-x86_64-avx2 "$metadata"
assert_line VANHYPRARCH_VOXTYPE_SHA256=cb3843a894ef47aca230b30bb1c45c2ef8e0d015adf2fa754d60e55123165fd0 "$metadata"
assert_line VANHYPRARCH_VOXTYPE_SIGNING_FINGERPRINT=9CCF7915B750CAE8B095ED1AA3FC9F33FD209279 "$metadata"
! grep -Eqi '(latest|nightly|rc[0-9])' "$metadata" || fail 'production metadata contains a floating or prerelease reference'
! grep -Eqi '(vulkan|cuda|rocm|onnx|gpu)' "$metadata" || fail 'production metadata selects a GPU artifact'

# Exact model metadata and stable upstream workflow.
assert_line VANHYPRARCH_VOXTYPE_MODEL=small.en "$metadata"
assert_line VANHYPRARCH_VOXTYPE_MODEL_FILENAME=ggml-small.en.bin "$metadata"
assert_line VANHYPRARCH_VOXTYPE_MODEL_SHA256=c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d "$metadata"
assert_line VANHYPRARCH_VOXTYPE_MODEL_SIZE=487614201 "$metadata"
grep -Fq 'setup --download --model "$VANHYPRARCH_VOXTYPE_MODEL"' "$installer" ||
    fail 'installer does not use Voxtype model setup'
grep -Fq 'rm -f -- "$model_path"' "$installer" || fail 'bad downloaded model is not removed'

# Stable 1.0.1 configuration, no input or UI side channel.
assert_line 'model = "small.en"' "$config"
assert_line 'language = "en"' "$config"
assert_line 'translate = false' "$config"
assert_line 'on_demand_loading = false' "$config"
assert_line 'theme = "default"' "$config"
assert_line 'volume = 1.0' "$config"
assert_line 'driver_order = ["wtype"]' "$config"
assert_line 'fallback_to_clipboard = false' "$config"
assert_line 'wait_for_modifier_release = false' "$config"
assert_line 'enabled = false' "$config"
! grep -Fq '["it", "en"]' "$config" || fail 'multilingual language list is the default'
! grep -Eqi '(evdev|ydotool|uinput|vulkan|cuda|rocm)' "$config" ||
    fail 'default config contains a forbidden input or GPU backend'
[ "$(grep -Fc 'enabled = false' "$config")" -eq 2 ] ||
    fail 'hotkey and OSD are not both disabled'
[ "$(grep -Fc '= false' "$config")" -ge 8 ] || fail 'notification/output safeguards are incomplete'

# Service and compositor ownership.
assert_line 'ExecStart=%h/.local/bin/voxtype -q daemon' "$service"
! grep -Eq '^\[Install\]|WantedBy=|graphical-session|ydotool' "$service" ||
    fail 'service has an enable target or unrelated dependency'
grep -Fq 'vanhyprarch/components/dictation' "$hyprland_config" ||
    fail 'Hyprland startup lacks the managed component check'
grep -Fq 'systemctl --user start vanhyprarch-voxtype.service' "$hyprland_config" ||
    fail 'Hyprland does not conditionally start the service'
grep -Fq 'bind("F9", "Dictation", "Start recording"' "$bindings" ||
    fail 'F9 press binding is missing'
grep -Fq 'hl.dsp.exec_cmd("voxtype record start")' "$bindings" ||
    fail 'F9 press does not start recording'
grep -Fq 'hl.dsp.exec_cmd("voxtype record stop"), { release = true })' "$bindings" ||
    fail 'F9 release does not stop recording'
! grep -Eqi 'voxtype.*toggle|SUPER.*CTRL.*X' "$bindings" ||
    fail 'an unsupported dictation toggle binding exists'
grep -Fq 'hl.env("PATH", prependPathOnce(inheritedPath, sessionHome .. "/.local/bin"))' \
    "$hyprland_config" || fail 'existing session PATH policy changed'
git -C "$repository_dir" diff --quiet -- home/.config/quickshell ||
    fail 'dictation changed Quickshell'
git -C "$repository_dir" diff --quiet -- bin system home/.config/hypr/hypridle.conf \
    home/.config/hypr/vanhyprarch-idle.conf ||
    fail 'dictation changed screenshot, idle, power, or system behavior'

# Installer mechanisms are represented directly and no GPU setup is present.
for flag in avx2 fma bmi1 bmi2 f16c movbe; do
    grep -Fq "for required_flag in avx2 fma bmi1 bmi2 f16c movbe" "$installer" ||
        fail "CPU feature validation is missing $flag"
done
grep -Fq 'gpg_home=$work_dir/gnupg' "$installer" || fail 'dedicated GPG home is missing'
grep -Fq 'actual_binary_sha=$(sha256sum' "$installer" || fail 'binary hash verification is missing'
grep -Fq '$staged_binary --version' "$installer" || fail 'staged version validation is missing'
grep -Fq 'target_binary=$HOME/.local/bin/voxtype' "$installer" || fail 'binary target is wrong'
grep -Fq 'install_atomically "$staged_binary" "$target_binary" 0755' "$installer" ||
    fail 'binary is not atomically published with mode 0755'
! grep -Eqi 'setup[[:space:]]+gpu|--enable.*gpu|voxtype.*(vulkan|cuda|rocm)' "$installer" ||
    fail 'installer enables a GPU backend'

# Validate the vendored key itself in an isolated keyring.
key_check_home=$test_dir/key-check
mkdir -m 0700 "$key_check_home"
key_listing=$test_dir/key.listing
/usr/bin/gpg --batch --homedir "$key_check_home" --with-colons \
    --import-options show-only --import "$component_dir/voxtype-ci-signing-key.asc" \
    > "$key_listing" 2>/dev/null || fail 'could not inspect vendored signing key'
[ "$(awk -F: '$1 == "fpr" { print $10; exit }' "$key_listing")" = \
    9CCF7915B750CAE8B095ED1AA3FC9F33FD209279 ] ||
    fail 'vendored signing key fingerprint is wrong'

# Generate an isolated signing key and tiny mock payload/model. No network or
# real Voxtype code is used by these integration tests.
fixture_gpg_home=$test_dir/fixture-gnupg
mkdir -m 0700 "$fixture_gpg_home"
/usr/bin/gpg --batch --homedir "$fixture_gpg_home" --pinentry-mode loopback \
    --passphrase '' --quick-generate-key 'Vanilla Dictation Test <test@example.invalid>' \
    ed25519 sign 0 >/dev/null 2>&1 || fail 'could not generate fixture signing key'
fixture_fingerprint=$(/usr/bin/gpg --batch --homedir "$fixture_gpg_home" --with-colons \
    --list-keys | awk -F: '$1 == "fpr" { print $10; exit }')
fixture_key=$test_dir/fixture-key.asc
/usr/bin/gpg --batch --homedir "$fixture_gpg_home" --armor \
    --export "$fixture_fingerprint" > "$fixture_key"

fixture_model=$test_dir/ggml-small.en.bin
printf 'fixture ggml small.en model\n' > "$fixture_model"
fixture_model_sha=$(sha256sum "$fixture_model" | awk '{ print $1 }')
fixture_model_size=$(wc -c < "$fixture_model" | tr -d '[:space:]')
fixture_binary=$test_dir/voxtype-0.0.0-linux-x86_64-avx2
cat > "$fixture_binary" <<'EOF'
#!/bin/sh
printf '%s|%s\n' "$0" "$*" >> "$VOXTYPE_FIXTURE_LOG"
case $1 in
    --version)
        printf 'voxtype 0.0.0\n'
        ;;
    setup)
        [ "$*" = 'setup --download --model small.en --quiet --no-post-install' ] || exit 64
        mkdir -p "$XDG_DATA_HOME/voxtype/models"
        cp "$VOXTYPE_FIXTURE_MODEL" "$XDG_DATA_HOME/voxtype/models/ggml-small.en.bin"
        ;;
    *) exit 64 ;;
esac
EOF
chmod 0755 "$fixture_binary"
fixture_binary_sha=$(sha256sum "$fixture_binary" | awk '{ print $1 }')
fixture_signature=$fixture_binary.asc
/usr/bin/gpg --batch --homedir "$fixture_gpg_home" --pinentry-mode loopback \
    --passphrase '' --armor --detach-sign --local-user "$fixture_fingerprint" \
    --output "$fixture_signature" "$fixture_binary" || fail 'could not sign fixture binary'

test_metadata=$test_dir/voxtype.conf
cat > "$test_metadata" <<EOF
VANHYPRARCH_VOXTYPE_VERSION=0.0.0
VANHYPRARCH_VOXTYPE_ARCHITECTURE=x86_64
VANHYPRARCH_VOXTYPE_ASSET=voxtype-0.0.0-linux-x86_64-avx2
VANHYPRARCH_VOXTYPE_SHA256=$fixture_binary_sha
VANHYPRARCH_VOXTYPE_SIGNING_FINGERPRINT=$fixture_fingerprint
VANHYPRARCH_VOXTYPE_RELEASE_URL=https://example.invalid/releases/tag/v0.0.0
VANHYPRARCH_VOXTYPE_DOWNLOAD_URL=https://example.invalid/releases/download/v0.0.0/voxtype-0.0.0-linux-x86_64-avx2
VANHYPRARCH_VOXTYPE_SIGNATURE_URL=https://example.invalid/releases/download/v0.0.0/voxtype-0.0.0-linux-x86_64-avx2.asc
VANHYPRARCH_VOXTYPE_MODEL=small.en
VANHYPRARCH_VOXTYPE_MODEL_FILENAME=ggml-small.en.bin
VANHYPRARCH_VOXTYPE_MODEL_SHA256=$fixture_model_sha
VANHYPRARCH_VOXTYPE_MODEL_SIZE=$fixture_model_size
VANHYPRARCH_VOXTYPE_MODEL_SOURCE_URL=https://example.invalid/ggml-small.en.bin
VANHYPRARCH_VOXTYPE_MODEL_PROVENANCE_URL=https://example.invalid/model-commit/ggml-small.en.bin
EOF

fake_wtype=$test_dir/wtype
fake_curl=$test_dir/curl
fake_systemctl=$test_dir/systemctl
printf '#!/bin/sh\nexit 0\n' > "$fake_wtype"
printf '#!/bin/sh\nexit 99\n' > "$fake_curl"
cat > "$fake_systemctl" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$SYSTEMCTL_FIXTURE_LOG"
if [ "${SYSTEMCTL_FIXTURE_FAIL_STOP:-}" = 1 ] &&
    [ "$*" = '--user stop vanhyprarch-voxtype.service' ]; then
    exit 1
fi
EOF
chmod 0755 "$fake_wtype" "$fake_curl" "$fake_systemctl"

fixture_log=$test_dir/voxtype.log
systemctl_log=$test_dir/systemctl.log
cpu_flags='avx2 fma bmi1 bmi2 f16c movbe'

# CPU rejection occurs before any install/download work.
wrong_cpu_home=$test_dir/wrong-cpu-home
mkdir "$wrong_cpu_home"
reject_install env HOME="$wrong_cpu_home" XDG_CONFIG_HOME="$wrong_cpu_home/config" \
    XDG_DATA_HOME="$wrong_cpu_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$test_metadata" \
    VANHYPRARCH_VOXTYPE_SIGNING_KEY="$fixture_key" VANHYPRARCH_CPU_FLAGS='avx2 fma' \
    VANHYPRARCH_TEST_BINARY="$fixture_binary" VANHYPRARCH_TEST_SIGNATURE="$fixture_signature" \
    VANHYPRARCH_CURL_EXECUTABLE="$fake_curl" VANHYPRARCH_GPG_EXECUTABLE=/usr/bin/gpg \
    VANHYPRARCH_WTYPE_EXECUTABLE="$fake_wtype" "$installer"
[ ! -e "$wrong_cpu_home/.local/bin/voxtype" ] || fail 'wrong CPU installed Voxtype'

# Hash, fingerprint, signature, and version failures preserve an old binary.
for failure in hash fingerprint version; do
    failure_home=$test_dir/failure-$failure
    mkdir -p "$failure_home/.local/bin"
    printf 'known-good sentinel\n' > "$failure_home/.local/bin/voxtype"
    failure_metadata=$test_dir/$failure.conf
    case $failure in
        hash)
            sed 's/^VANHYPRARCH_VOXTYPE_SHA256=.*/VANHYPRARCH_VOXTYPE_SHA256=0000000000000000000000000000000000000000000000000000000000000000/' \
                "$test_metadata" > "$failure_metadata"
            ;;
        fingerprint)
            sed 's/^VANHYPRARCH_VOXTYPE_SIGNING_FINGERPRINT=.*/VANHYPRARCH_VOXTYPE_SIGNING_FINGERPRINT=0000000000000000000000000000000000000000/' \
                "$test_metadata" > "$failure_metadata"
            ;;
        version)
            sed 's/^VANHYPRARCH_VOXTYPE_VERSION=.*/VANHYPRARCH_VOXTYPE_VERSION=9.9.9/' \
                "$test_metadata" > "$failure_metadata"
            ;;
    esac
    reject_install env HOME="$failure_home" XDG_CONFIG_HOME="$failure_home/config" \
        XDG_DATA_HOME="$failure_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
        VANHYPRARCH_VOXTYPE_METADATA="$failure_metadata" \
        VANHYPRARCH_VOXTYPE_SIGNING_KEY="$fixture_key" VANHYPRARCH_CPU_FLAGS="$cpu_flags" \
        VANHYPRARCH_TEST_BINARY="$fixture_binary" VANHYPRARCH_TEST_SIGNATURE="$fixture_signature" \
        VANHYPRARCH_CURL_EXECUTABLE="$fake_curl" VANHYPRARCH_GPG_EXECUTABLE=/usr/bin/gpg \
        VANHYPRARCH_WTYPE_EXECUTABLE="$fake_wtype" VOXTYPE_FIXTURE_LOG="$fixture_log" \
        VOXTYPE_FIXTURE_MODEL="$fixture_model" "$installer"
    assert_line 'known-good sentinel' "$failure_home/.local/bin/voxtype"
done

bad_signature=$test_dir/bad-signature.asc
cp "$fixture_signature" "$bad_signature"
printf 'damaged\n' >> "$bad_signature"
signature_home=$test_dir/failure-signature
mkdir -p "$signature_home/.local/bin"
printf 'known-good sentinel\n' > "$signature_home/.local/bin/voxtype"
reject_install env HOME="$signature_home" XDG_CONFIG_HOME="$signature_home/config" \
    XDG_DATA_HOME="$signature_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$test_metadata" VANHYPRARCH_VOXTYPE_SIGNING_KEY="$fixture_key" \
    VANHYPRARCH_CPU_FLAGS="$cpu_flags" VANHYPRARCH_TEST_BINARY="$fixture_binary" \
    VANHYPRARCH_TEST_SIGNATURE="$bad_signature" VANHYPRARCH_CURL_EXECUTABLE="$fake_curl" \
    VANHYPRARCH_GPG_EXECUTABLE=/usr/bin/gpg VANHYPRARCH_WTYPE_EXECUTABLE="$fake_wtype" \
    "$installer"
assert_line 'known-good sentinel' "$signature_home/.local/bin/voxtype"

# A newly downloaded model with a wrong digest is removed and no component is published.
bad_model_metadata=$test_dir/bad-model.conf
sed 's/^VANHYPRARCH_VOXTYPE_MODEL_SHA256=.*/VANHYPRARCH_VOXTYPE_MODEL_SHA256=0000000000000000000000000000000000000000000000000000000000000000/' \
    "$test_metadata" > "$bad_model_metadata"
bad_model_home=$test_dir/bad-model-home
mkdir "$bad_model_home"
reject_install env HOME="$bad_model_home" XDG_CONFIG_HOME="$bad_model_home/config" \
    XDG_DATA_HOME="$bad_model_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$bad_model_metadata" \
    VANHYPRARCH_VOXTYPE_SIGNING_KEY="$fixture_key" VANHYPRARCH_CPU_FLAGS="$cpu_flags" \
    VANHYPRARCH_TEST_BINARY="$fixture_binary" VANHYPRARCH_TEST_SIGNATURE="$fixture_signature" \
    VANHYPRARCH_CURL_EXECUTABLE="$fake_curl" VANHYPRARCH_GPG_EXECUTABLE=/usr/bin/gpg \
    VANHYPRARCH_WTYPE_EXECUTABLE="$fake_wtype" VOXTYPE_FIXTURE_LOG="$fixture_log" \
    VOXTYPE_FIXTURE_MODEL="$fixture_model" "$installer"
[ ! -e "$bad_model_home/data/voxtype/models/ggml-small.en.bin" ] ||
    fail 'invalid downloaded model was retained'
[ ! -e "$bad_model_home/data/vanhyprarch/components/dictation" ] ||
    fail 'bad model published the component marker'
[ ! -e "$bad_model_home/.local/bin/voxtype" ] || fail 'failed install retained a new binary'

# Successful install exercises the full mocked signature/model path.
install_home=$test_dir/install-home
mkdir "$install_home"
: > "$fixture_log"
env HOME="$install_home" XDG_CONFIG_HOME="$install_home/config" \
    XDG_DATA_HOME="$install_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$test_metadata" VANHYPRARCH_VOXTYPE_SIGNING_KEY="$fixture_key" \
    VANHYPRARCH_CPU_FLAGS="$cpu_flags" VANHYPRARCH_TEST_BINARY="$fixture_binary" \
    VANHYPRARCH_TEST_SIGNATURE="$fixture_signature" VANHYPRARCH_CURL_EXECUTABLE="$fake_curl" \
    VANHYPRARCH_GPG_EXECUTABLE=/usr/bin/gpg VANHYPRARCH_WTYPE_EXECUTABLE="$fake_wtype" \
    VOXTYPE_FIXTURE_LOG="$fixture_log" VOXTYPE_FIXTURE_MODEL="$fixture_model" \
    "$installer" >/dev/null

installed_binary=$install_home/.local/bin/voxtype
installed_model=$install_home/data/voxtype/models/ggml-small.en.bin
installed_config=$install_home/config/voxtype/config.toml
installed_service=$install_home/config/systemd/user/vanhyprarch-voxtype.service
installed_marker=$install_home/data/vanhyprarch/components/dictation
[ "$(stat -c '%a' "$installed_binary")" = 755 ] || fail 'installed binary mode is not 0755'
cmp -s "$fixture_binary" "$installed_binary" || fail 'installed binary differs from verified fixture'
cmp -s "$fixture_model" "$installed_model" || fail 'installed model differs from verified fixture'
cmp -s "$config" "$installed_config" || fail 'default config was not installed'
cmp -s "$service" "$installed_service" || fail 'managed service was not installed'
assert_line vanhyprarch-dictation-v1 "$installed_marker"
[ "$(wc -l < "$fixture_log" | tr -d '[:space:]')" -eq 2 ] ||
    fail 'staged or installed mock binary had an unexpected invocation'
[ "$(grep -Fc '|--version' "$fixture_log")" -eq 1 ] || fail 'staged binary version check count is wrong'
grep -Fq "$installed_binary|setup --download --model small.en --quiet --no-post-install" \
    "$fixture_log" || fail 'installed binary did not run the exact stable model workflow'

# Reinstallation preserves a customized config and reuses the verified model.
printf '# user customization\n' > "$installed_config"
env HOME="$install_home" XDG_CONFIG_HOME="$install_home/config" \
    XDG_DATA_HOME="$install_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$test_metadata" VANHYPRARCH_VOXTYPE_SIGNING_KEY="$fixture_key" \
    VANHYPRARCH_CPU_FLAGS="$cpu_flags" VANHYPRARCH_TEST_BINARY="$fixture_binary" \
    VANHYPRARCH_TEST_SIGNATURE="$fixture_signature" VANHYPRARCH_CURL_EXECUTABLE="$fake_curl" \
    VANHYPRARCH_GPG_EXECUTABLE=/usr/bin/gpg VANHYPRARCH_WTYPE_EXECUTABLE="$fake_wtype" \
    VOXTYPE_FIXTURE_LOG="$fixture_log" VOXTYPE_FIXTURE_MODEL="$fixture_model" \
    "$installer" >/dev/null
assert_line '# user customization' "$installed_config"
[ "$(grep -Fc '|setup --download --model small.en --quiet --no-post-install' "$fixture_log")" -eq 1 ] ||
    fail 'reinstall downloaded an already verified model'

# A failed service stop leaves all managed integration in place.
: > "$systemctl_log"
reject_uninstall env HOME="$install_home" XDG_CONFIG_HOME="$install_home/config" \
    XDG_DATA_HOME="$install_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$test_metadata" \
    VANHYPRARCH_SYSTEMCTL_EXECUTABLE="$fake_systemctl" \
    SYSTEMCTL_FIXTURE_LOG="$systemctl_log" SYSTEMCTL_FIXTURE_FAIL_STOP=1 \
    "$uninstaller"
[ -e "$installed_binary" ] || fail 'failed service stop removed the managed binary'
[ -e "$installed_service" ] || fail 'failed service stop removed the managed service'
[ -e "$installed_marker" ] || fail 'failed service stop removed the component marker'

# Normal uninstall removes only managed integration and preserves user assets.
: > "$systemctl_log"
env HOME="$install_home" XDG_CONFIG_HOME="$install_home/config" \
    XDG_DATA_HOME="$install_home/data" VANHYPRARCH_ALLOW_TEST_OVERRIDES=1 \
    VANHYPRARCH_VOXTYPE_METADATA="$test_metadata" \
    VANHYPRARCH_SYSTEMCTL_EXECUTABLE="$fake_systemctl" \
    SYSTEMCTL_FIXTURE_LOG="$systemctl_log" "$uninstaller" >/dev/null
[ ! -e "$installed_binary" ] || fail 'uninstall retained managed binary'
[ ! -e "$installed_service" ] || fail 'uninstall retained managed service'
[ ! -e "$installed_marker" ] || fail 'uninstall retained component marker'
assert_line '# user customization' "$installed_config"
cmp -s "$fixture_model" "$installed_model" || fail 'uninstall removed or changed the model'
assert_line '--user stop vanhyprarch-voxtype.service' "$systemctl_log"
assert_line '--user daemon-reload' "$systemctl_log"

printf 'dictation tests: PASS\n'
