#!/bin/sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime=$(mktemp -d)
trap 'rm -rf -- "$runtime"' EXIT HUP INT TERM
config=$runtime/config/logo-test
mkdir -p "$config/assets"
cp "$repository/tests/final-logo.qml" "$config/shell.qml"
cp "$repository/home/.config/quickshell/vanhyprarch/assets/logo.svg" \
    "$config/assets/logo.svg"
output=$runtime/output.log

if ! XDG_CONFIG_HOME=$runtime/config XDG_RUNTIME_DIR=$runtime \
    QT_QPA_PLATFORM=offscreen timeout 10s \
    qs --no-color -p "$config" >"$output" 2>&1
then
    cat "$output" >&2
    exit 1
fi

if ! grep -Fq 'FINAL_LOGO_TEST_PASS' "$output"; then
    cat "$output" >&2
    exit 1
fi
if grep -Eq 'FINAL_LOGO_TEST_FAILURE|Cannot open:|SVG resource failed' "$output"; then
    cat "$output" >&2
    exit 1
fi

printf '%s\n' 'Final logo offscreen render: PASS'
