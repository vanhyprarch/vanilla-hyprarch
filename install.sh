#!/bin/sh

# SPDX-License-Identifier: GPL-2.0-only

set -eu
PATH=/usr/bin:/bin
export PATH
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

program_name=${0##*/}
repository=vanhyprarch/vanilla-hyprarch
source_ref=${VANHYPRARCH_REF-main}
temporary_root=
release_metadata_input=
release_artifact_input=
release_mode=false

usage() {
    printf 'usage: %s [--yes] [--release-metadata FILE --release-artifact FILE]\n' "$program_name" >&2
    exit 2
}

fail() {
    printf '%s: %s\n' "$program_name" "$1" >&2
    exit 1
}

cleanup() {
    if [ -n "$temporary_root" ]; then
        case "$temporary_root" in
            /tmp/vanhyprarch.*) /usr/bin/rm -rf -- "$temporary_root" ;;
            *) printf '%s: refusing unsafe temporary cleanup path\n' "$program_name" >&2 ;;
        esac
    fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

assume_yes=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes)
            assume_yes=true
            shift
            ;;
        --release-metadata)
            [ "$#" -ge 2 ] && [ -z "$release_metadata_input" ] || usage
            release_metadata_input=$2
            shift 2
            ;;
        --release-artifact)
            [ "$#" -ge 2 ] && [ -z "$release_artifact_input" ] || usage
            release_artifact_input=$2
            shift 2
            ;;
        -h|--help) usage ;;
        *) usage ;;
    esac
done

if [ -n "$release_metadata_input" ] || [ -n "$release_artifact_input" ]; then
    [ -n "$release_metadata_input" ] && [ -n "$release_artifact_input" ] || usage
    release_mode=true
fi

case "$source_ref" in
    ''|*[!A-Za-z0-9._-]*)
        fail "VANHYPRARCH_REF must be a simple tag, branch, or commit name"
        ;;
esac

id_command=/usr/bin/id
stat_command=/usr/bin/stat
getent_command=/usr/bin/getent
pacman_command=/usr/bin/pacman
sudo_command=/usr/bin/sudo
curl_command=/usr/bin/curl
python_command=/usr/bin/python
os_release=/usr/lib/os-release
actual_uid=$($id_command -u)
case "$actual_uid" in
    ''|*[!0-9]*) fail "effective uid is invalid" ;;
esac
[ "$actual_uid" -ne 0 ] || fail "run this installer as the normal target user, not root"
effective_uid=$actual_uid
target_home=${HOME-}
resolved_home=
runtime_directory=${XDG_RUNTIME_DIR-}
python_test_state=
target_user_override=
target_uid_override=

if [ "${VANHYPRARCH_INSTALL_TESTING-}" = 1 ]; then
    test_root=${VANHYPRARCH_INSTALL_TEST_ROOT-}
    [ -n "$test_root" ] || fail "test root is required"
    [ -f "$test_root/.vanhyprarch-install-test-root" ] && \
        [ ! -L "$test_root/.vanhyprarch-install-test-root" ] || \
        fail "test root marker is missing or unsafe"
    test_marker=
    IFS= read -r test_marker < "$test_root/.vanhyprarch-install-test-root" || \
        fail "test root marker is missing"
    [ "$test_marker" = VANHYPRARCH_INSTALL_TEST_ROOT_V1 ] || \
        fail "test root marker is invalid"
    effective_uid=${VANHYPRARCH_INSTALL_TEST_EFFECTIVE_UID-$effective_uid}
    os_release=${VANHYPRARCH_INSTALL_TEST_OS_RELEASE-$os_release}
    curl_command=${VANHYPRARCH_INSTALL_TEST_CURL-$curl_command}
    sudo_command=${VANHYPRARCH_INSTALL_TEST_SUDO-$sudo_command}
    python_command=${VANHYPRARCH_INSTALL_TEST_PYTHON-$python_command}
    pacman_command=${VANHYPRARCH_INSTALL_TEST_PACMAN-$pacman_command}
    target_home=${VANHYPRARCH_INSTALL_TEST_HOME-$target_home}
    resolved_home=${VANHYPRARCH_INSTALL_TEST_RESOLVED_HOME-}
    runtime_directory=${VANHYPRARCH_INSTALL_TEST_RUNTIME-$runtime_directory}
    python_test_state=${VANHYPRARCH_INSTALL_TEST_PYTHON_PRESENT-}
    target_user_override=${VANHYPRARCH_INSTALL_TEST_TARGET_USER-}
    target_uid_override=${VANHYPRARCH_INSTALL_TEST_TARGET_UID-}
fi

case "$effective_uid" in
    ''|*[!0-9]*) fail "effective uid is invalid" ;;
esac
[ "$effective_uid" -ne 0 ] || fail "run this installer as the normal target user, not root"

printf '%s\n' 'Vanilla HyprArch installer'
printf '%s\n' 'Checking Arch...'
[ -f "$os_release" ] && [ ! -L "$os_release" ] || \
    fail "supported base requires Arch Linux"
arch_identity=
while IFS= read -r release_line || [ -n "$release_line" ]; do
    case "$release_line" in
        ID=arch|ID=\"arch\"|ID=\'arch\') arch_identity=arch ;;
    esac
done < "$os_release"
[ "$arch_identity" = arch ] || fail "supported base requires Arch Linux"
[ -x "$pacman_command" ] || fail "pacman is required"

target_user=${target_user_override:-$($id_command -un)} || \
    fail "could not resolve the target user"
target_uid=${target_uid_override:-$($id_command -u)} || \
    fail "could not resolve the target uid"
case "$target_user" in
    ''|*[!A-Za-z0-9._-]*) fail "target username is unsafe" ;;
esac
case "$target_uid" in
    ''|*[!0-9]*) fail "target uid is invalid" ;;
esac
[ "$target_uid" -ne 0 ] || fail "the target user must not be root"

case "$target_home" in
    /*) ;;
    *) fail "HOME must be an absolute path" ;;
esac
[ "$target_home" != / ] || fail "HOME must not be the filesystem root"
[ -d "$target_home" ] && [ ! -L "$target_home" ] || \
    fail "HOME must be a real directory"
canonical_home=$(CDPATH= cd -- "$target_home" && pwd -P) || \
    fail "HOME could not be resolved safely"
[ "$canonical_home" = "$target_home" ] || fail "HOME must be canonical"
home_owner=$($stat_command -c %u -- "$target_home") || fail "HOME owner could not be inspected"
[ "$home_owner" = "$target_uid" ] || fail "HOME is not owned by the target user"
home_mode=$($stat_command -c %a -- "$target_home") || fail "HOME mode could not be inspected"
home_other=${home_mode#${home_mode%?}}
home_without_other=${home_mode%?}
home_group=${home_without_other#${home_without_other%?}}
case "$home_group$home_other" in
    *[2367]*) fail "HOME must not be group- or world-writable" ;;
esac

if [ -z "$resolved_home" ]; then
    resolved_home=$($getent_command passwd "$target_user" | /usr/bin/cut -d: -f6) || \
        fail "target account could not be resolved"
fi
[ "$resolved_home" = "$target_home" ] || \
    fail "HOME does not match the target account"

if [ -z "$runtime_directory" ]; then
    runtime_directory=/run/user/$target_uid
fi
case "$runtime_directory" in
    /*) ;;
    *) fail "XDG_RUNTIME_DIR must be an absolute path" ;;
esac
[ -d "$runtime_directory" ] && [ ! -L "$runtime_directory" ] || \
    fail "XDG_RUNTIME_DIR is unavailable or unsafe"
runtime_owner=$($stat_command -c %u -- "$runtime_directory") || \
    fail "XDG_RUNTIME_DIR owner could not be inspected"
runtime_mode=$($stat_command -c %a -- "$runtime_directory") || \
    fail "XDG_RUNTIME_DIR mode could not be inspected"
[ "$runtime_owner" = "$target_uid" ] && [ "$runtime_mode" = 700 ] || \
    fail "XDG_RUNTIME_DIR must be target-user-owned mode 0700"
XDG_RUNTIME_DIR=$runtime_directory
export XDG_RUNTIME_DIR

printf '%s\n' 'Checking sudo...'
[ -x "$sudo_command" ] || fail "sudo is required"
"$sudo_command" -v || fail "sudo authorization failed"
installed_release=/usr/share/vanhyprarch/release.json
if "$sudo_command" /usr/bin/test -e "$installed_release" || \
   "$sudo_command" /usr/bin/test -L "$installed_release"; then
    fail "an installed release identity already exists; fresh reinstall or development-over-release is unsupported"
fi

temporary_root=$(/usr/bin/mktemp -d /tmp/vanhyprarch.XXXXXXXX) || \
    fail "could not create a secure temporary directory"
extract_root=$temporary_root/source
/usr/bin/mkdir -m 700 -- "$extract_root" || fail "could not prepare source extraction"
if [ "$release_mode" = true ]; then
    case "$0" in
        /*) ;;
        *) fail "release mode requires install.sh from a verified extracted release tree" ;;
    esac
    [ -f "$0" ] && [ ! -L "$0" ] || \
        fail "release installer must be a regular file"
    verified_source_root=$(CDPATH= cd -- "${0%/*}" && pwd -P) || \
        fail "release source root could not be resolved"
    release_verifier=$verified_source_root/release/build.py
    [ -f "$release_verifier" ] && [ ! -L "$release_verifier" ] || \
        fail "verified release source lacks its contract verifier"
    source_root=$verified_source_root
    case "$release_artifact_input" in
        /*) ;;
        *) fail "release artifact path must be absolute" ;;
    esac
    case "$release_metadata_input" in
        /*) ;;
        *) fail "release metadata path must be absolute" ;;
    esac
    [ -f "$release_artifact_input" ] && [ ! -L "$release_artifact_input" ] || \
        fail "release artifact input must be a regular file"
    [ -f "$release_metadata_input" ] && [ ! -L "$release_metadata_input" ] || \
        fail "release metadata input must be a regular file"
    archive=$temporary_root/${release_artifact_input##*/}
    metadata=$temporary_root/release.json
    /usr/bin/cp --no-dereference -- "$release_artifact_input" "$archive" || \
        fail "could not copy release artifact into private staging"
    /usr/bin/cp --no-dereference -- "$release_metadata_input" "$metadata" || \
        fail "could not copy release metadata into private staging"
    printf '%s\n' 'Using supplied verified release bundle.'
else
    printf '%s\n' 'Downloading Vanilla development source...'
    [ -x "$curl_command" ] || fail "curl is required"
    archive=$temporary_root/source.tar.gz
    resolved_revision=$("$curl_command" --fail --silent --show-error --location \
        --proto '=https' --tlsv1.2 \
        --header 'Accept: application/vnd.github.sha' \
        "https://api.github.com/repos/$repository/commits/$source_ref") || \
        fail "could not resolve source ref '$source_ref'"
    case "$resolved_revision" in
        *[!0-9a-f]*|'') fail "source ref did not resolve to a commit SHA" ;;
    esac
    [ "${#resolved_revision}" -eq 40 ] || fail "source ref did not resolve to a commit SHA"
    "$curl_command" --fail --silent --show-error --location \
        --proto '=https' --tlsv1.2 --output "$archive" \
        "https://codeload.github.com/$repository/tar.gz/$resolved_revision" || \
        fail "source archive download failed for '$source_ref'"
    [ -s "$archive" ] || fail "downloaded source archive is empty"
    archive_sha256=$(/usr/bin/sha256sum -- "$archive") || fail "source archive could not be hashed"
    archive_sha256=${archive_sha256%% *}
    /usr/bin/tar -xzf "$archive" -C "$extract_root" --no-same-owner --no-same-permissions || \
        fail "source archive extraction failed"
    set -- "$extract_root"/*
    [ "$#" -eq 1 ] && [ -d "$1" ] && [ ! -L "$1" ] || \
        fail "source archive has an unexpected root layout"
    source_root=$(CDPATH= cd -- "$1" && pwd -P) || fail "source root could not be resolved"
fi
bootstrap=$source_root/install/bootstrap
managed_deploy=$source_root/install/managed_deploy.py
create_once=$source_root/install/create_once.py
for entrypoint in "$bootstrap" "$managed_deploy" "$create_once"; do
    [ -f "$entrypoint" ] && [ ! -L "$entrypoint" ] || \
        fail "source archive is missing an authoritative installer entry point"
done
[ -x "$bootstrap" ] || fail "authoritative Python bootstrap is not executable"

python_installed=false
if [ -n "$python_test_state" ]; then
    case "$python_test_state" in
        0) python_installed=false ;;
        1) python_installed=true ;;
        *) fail "test Python state is invalid" ;;
    esac
elif "$pacman_command" -Q -- python >/dev/null 2>&1; then
    python_installed=true
fi

if [ "$python_installed" = false ]; then
    "$bootstrap" plan --target-user "$target_user" >/dev/null || \
        fail "preliminary Python bootstrap plan failed"
fi

printf '%s\n' 'Planning installation...'
if [ "$release_mode" = true ]; then
    printf '%s\n' '  Source: supplied verified release bundle'
    printf '%s\n' '  Identity: commit only after final validation'
else
    printf '  Source: %s ref %s\n' "$repository" "$source_ref"
    printf '  Commit: %s\n' "$resolved_revision"
    printf '  Archive SHA-256: %s\n' "$archive_sha256"
    printf '%s\n' '  Identity: unreleased/development (no installed record)'
fi
if [ "$python_installed" = false ]; then
    printf '%s\n' '  Python: bootstrap through install/bootstrap'
else
    printf '%s\n' '  Python: preserve installed interpreter'
fi
printf '%s\n' '  System: packages, yay, BlueZ, Flathub, SDDM, services'
printf '%s\n' '  User: managed deployment, then create-once initialization'
printf '%s\n' '  Validation: managed, create-once, system including SDDM'

if [ "$assume_yes" = false ]; then
    printf 'Proceed? [Y/n] '
    reply=
    IFS= read -r reply || fail "confirmation input closed"
    case "$reply" in
        ''|y|Y|yes|YES|Yes) ;;
        *) printf '%s\n' 'Installation cancelled.'; exit 0 ;;
    esac
fi

system_stage() {
    if [ "$1" = bootstrap-python ] || [ ! -f "$source_root/install/secret_service_preflight.py" ]; then
        "$sudo_command" "$bootstrap" "$1" --target-user "$target_user"
    else
        target_context=$("$python_command" -B "$source_root/install/secret_service_preflight.py" context) || \
            fail "target-user provider context capture failed"
        "$sudo_command" "$bootstrap" "$1" --target-user "$target_user" \
            --target-context-json "$target_context"
    fi
}

managed_stage() {
    "$python_command" "$managed_deploy" \
        --source-root "$source_root" --release-id "$resolved_revision" "$@"
}

create_once_stage() {
    "$python_command" "$create_once" --source-root "$source_root" "$@"
}

run_plan() {
    plan_label=$1
    plan_output=$2
    shift 2
    if "$@" >"$plan_output"; then
        printf '  %s: ready\n' "$plan_label"
    else
        plan_status=$?
        printf '%s: %s plan failed\n' "$program_name" "$plan_label" >&2
        /usr/bin/cat -- "$plan_output" >&2
        exit "$plan_status"
    fi
}

if [ "$python_installed" = false ]; then
    system_stage bootstrap-python || fail "Python bootstrap failed"
fi
[ -x "$python_command" ] || fail "installed Python interpreter is unavailable"
"$python_command" -c 'import sys' || fail "installed Python interpreter could not start"

if [ "$release_mode" = true ]; then
    "$python_command" "$release_verifier" verify "$metadata" "$archive" || \
        fail "release artifact verification failed before extraction"
    /usr/bin/tar -xzf "$archive" -C "$extract_root" --no-same-owner --no-same-permissions || \
        fail "verified release extraction failed"
    set -- "$extract_root"/*
    [ "$#" -eq 1 ] && [ -d "$1" ] && [ ! -L "$1" ] || \
        fail "verified release has an unexpected root layout"
    source_root=$(CDPATH= cd -- "$1" && pwd -P) || fail "release source root could not be resolved"
    /usr/bin/cmp -s -- "$verified_source_root/install.sh" "$source_root/install.sh" || \
        fail "release installer does not match verified artifact"
    /usr/bin/cmp -s -- "$release_verifier" "$source_root/release/build.py" || \
        fail "release verifier does not match verified artifact"
    bootstrap=$source_root/install/bootstrap
    managed_deploy=$source_root/install/managed_deploy.py
    create_once=$source_root/install/create_once.py
    release_identity=$source_root/install/release_identity.py
    [ -f "$release_identity" ] && [ ! -L "$release_identity" ] || \
        fail "release archive lacks identity publisher"
    resolved_revision=$("$sudo_command" "$python_command" -B "$release_identity" preflight \
        --metadata "$metadata" --artifact "$archive" --source-root "$source_root") || \
        fail "release identity preflight failed"
    case "$resolved_revision" in
        *[!0-9a-f]*|'') fail "release identity preflight returned an invalid commit" ;;
    esac
    [ "${#resolved_revision}" -eq 40 ] || \
        fail "release identity preflight returned an invalid commit"
fi

printf '%s\n' 'Checking and applying authoritative stages...'
run_plan 'system integration' "$temporary_root/system-plan" system_stage plan
system_stage apply || fail "system integration apply failed"
run_plan 'managed deployment' "$temporary_root/managed-plan" managed_stage plan reconcile
managed_stage reconcile || fail "managed deployment failed"
run_plan 'create-once initialization' "$temporary_root/create-once-plan" create_once_stage plan
create_once_stage initialize || fail "create-once initialization failed"

printf '%s\n' 'Validating installation...'
managed_stage validate || fail "managed deployment validation failed"
create_once_stage validate || fail "create-once validation failed"
system_stage validate || fail "system integration validation failed"

if [ "$release_mode" = true ]; then
    "$sudo_command" "$python_command" -B "$release_identity" commit \
        --metadata "$metadata" --artifact "$archive" --source-root "$source_root" || \
        fail "release identity commit failed; installation is not complete"
    "$sudo_command" "$python_command" -B "$release_identity" validate || \
        fail "installed release identity validation failed"
fi

printf '%s\n' 'Vanilla HyprArch installation validated successfully.'
printf '%s\n' 'Reboot to enter SDDM.'
