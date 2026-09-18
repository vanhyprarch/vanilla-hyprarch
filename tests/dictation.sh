#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
component_dir=$repository_dir/install/dictation
manager=$repository_dir/bin/vanhyprarch-dictation
config=$component_dir/config.toml
service=$component_dir/vanhyprarch-voxtype.service
binary_manifest=$component_dir/binaries.toml
official_manifest=$repository_dir/packages/official.txt
aur_manifest=$repository_dir/packages/aur.txt
optional_manifest=$repository_dir/packages/optional-dictation-official.txt
bindings=$repository_dir/home/.config/hypr/vanhyprarch/bindings.lua
hyprland_config=$repository_dir/home/.config/hypr/vanhyprarch/core.lua
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-dictation-static.XXXXXX")

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
    printf 'dictation test: %s\n' "$*" >&2
    exit 1
}

assert_line()
{
    grep -Fqx -- "$1" "$2" || fail "missing exact line in ${2##*/}: $1"
}

[ -x "$manager" ] || fail 'public dictation manager is not executable'
python -m py_compile "$manager"
sh -n "$component_dir/install" "$component_dir/uninstall"

! grep -Eq '^(voxtype|voxtype-bin|wtype|gnupg)$' "$official_manifest" ||
    fail 'dictation dependency leaked into the required official manifest'
! grep -Eq '^(voxtype|voxtype-bin)$' "$aur_manifest" ||
    fail 'Voxtype leaked into the AUR manifest'
assert_line gnupg "$optional_manifest"
assert_line wtype "$optional_manifest"
[ "$(sed '/^[[:space:]]*$/d' "$optional_manifest" | wc -l)" -eq 2 ] ||
    fail 'optional dictation manifest has unexpected entries'

assert_line 'max_duration_secs = 120' "$config"
assert_line 'model = "small.en"' "$config"
assert_line 'language = "en"' "$config"
assert_line 'translate = false' "$config"
assert_line 'driver_order = ["wtype"]' "$config"
assert_line 'enabled = false' "$config"
! grep -Eqi '(evdev|ydotool|uinput|vulkan|cuda|rocm)' "$config" ||
    fail 'default config contains a forbidden input or GPU backend'

assert_line 'ExecStart=%h/.local/bin/voxtype -q daemon' "$service"
! grep -Eq '^\[Install\]|WantedBy=|graphical-session|ydotool' "$service" ||
    fail 'service has an enable target or unrelated dependency'
grep -Fq 'systemctl --user start vanhyprarch-voxtype.service' "$hyprland_config" ||
    fail 'Hyprland no longer starts the optional service'
grep -Fq 'bind("F9", "Dictation", "Start recording"' "$bindings" ||
    fail 'F9 press binding is missing'
grep -Fq 'hl.dsp.exec_cmd("voxtype record stop"), { release = true })' "$bindings" ||
    fail 'F9 release binding is missing'
grep -Fq 'hl.env("PATH", prependPathOnce(inheritedPath, sessionHome .. "/.local/bin"))' \
    "$hyprland_config" || fail 'session PATH policy changed'

grep -Fq 'voxtype-1.0.1-linux-x86_64-avx2' "$binary_manifest" ||
    fail 'binary manifest does not pin the AVX2 asset'
grep -Fq 'cb3843a894ef47aca230b30bb1c45c2ef8e0d015adf2fa754d60e55123165fd0' "$binary_manifest" ||
    fail 'binary manifest does not pin the CPU digest'
grep -Fq 'voxtype-1.0.1-linux-x86_64-vulkan' "$binary_manifest" ||
    fail 'binary manifest does not pin the Vulkan asset'
grep -Fq 'c569d038057464aa60290296794bcbd79b928ee0efd038e33062a4c015558ed8' "$binary_manifest" ||
    fail 'binary manifest does not pin the Vulkan digest'
grep -Fq 'size = 64913912' "$binary_manifest" ||
    fail 'binary manifest does not pin the Vulkan asset size'
grep -Fq '9CCF7915B750CAE8B095ED1AA3FC9F33FD209279' "$binary_manifest" ||
    fail 'binary manifest does not pin the signing fingerprint'
grep -Fq 'required_cpu_features = ["avx2", "fma", "bmi1", "bmi2", "f16c", "movbe"]' "$binary_manifest" ||
    fail 'binary manifest does not enforce the x86-64-v3 feature floor'
! grep -Fiq latest "$binary_manifest" || fail 'binary manifest contains a floating URL'
grep -Fq '"setup", "--download", "--model"' "$manager" ||
    fail 'manager does not use the stable Voxtype model downloader'
grep -Fq 'os.replace(candidate, path_map["config"])' "$manager" ||
    fail 'manager does not atomically publish candidate config'
grep -Fq 'acceleration_identity(path_map["binary"], binaries)' "$manager" ||
    fail 'manager does not derive acceleration from the active digest'
grep -Fq 'Local Dictation service is running and healthy.' "$manager" ||
    fail 'successful installation does not report healthy service state'
! grep -Fq 'The service was not enabled or started' "$manager" ||
    fail 'obsolete inactive-service installation guidance remains'
! grep -Fq 'document.get("backend"' "$manager" ||
    fail 'daemon health still depends on Voxtype backend labeling'
grep -Fq 'path_map["marker"].unlink(missing_ok=True)' "$manager" ||
    fail 'uninstall does not remove the marker before runtime payloads'
grep -Fq 'remove_voxtype_tree(path_map["config_home"], path_map["config_dir"]' "$manager" ||
    fail 'uninstall does not remove the complete Voxtype config directory'
grep -Fq 'remove_voxtype_tree(path_map["data_home"], path_map["data_dir"]' "$manager" ||
    fail 'uninstall does not remove the complete Voxtype data directory'
! grep -Eqi 'setup[[:space:]]+gpu|--enable.*gpu|cuda|rocm|onnx' "$manager" "$binary_manifest" ||
    fail 'manager contains a forbidden upstream GPU setup or unrelated backend'

if grep -RFiq --exclude-dir=.git \
    -e 'Normal uninstall preserves' \
    -e 'normal uninstall still preserves' \
    -e 'preserve config and models' \
    -e 'future explicit purge may remove' \
    "$repository_dir/README.md" "$repository_dir/docs" \
    "$repository_dir/home/.config/quickshell/vanhyprarch/components"
then
    fail 'obsolete Local Dictation uninstall-preservation wording remains'
fi

key_home=$test_dir/key-home
mkdir -m 0700 "$key_home"
/usr/bin/gpg --batch --homedir "$key_home" --with-colons --import-options show-only \
    --import "$component_dir/voxtype-ci-signing-key.asc" > "$test_dir/key-list" 2>/dev/null ||
    fail 'could not inspect vendored signing key'
[ "$(awk -F: '$1 == "fpr" { print $10; exit }' "$test_dir/key-list")" = \
    9CCF7915B750CAE8B095ED1AA3FC9F33FD209279 ] ||
    fail 'vendored signing key fingerprint changed'

PYTHONPYCACHEPREFIX=$test_dir/pycache python "$script_dir/vanhyprarch-dictation.py"

printf '%s\n' 'vanhyprarch dictation self-check passed'
