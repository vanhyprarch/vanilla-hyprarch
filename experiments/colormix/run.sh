#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
renderer="$script_dir/colormix"
fullscreen=false

if [ "${1-}" = "--fullscreen" ]; then
    fullscreen=true
    shift
fi

if ! command -v foot >/dev/null 2>&1; then
    echo "run.sh: foot is not installed or not on PATH" >&2
    exit 1
fi

if [ ! -x "$renderer" ]; then
    echo "run.sh: renderer is not built; run: make -C $script_dir" >&2
    exit 1
fi

if [ "$fullscreen" = true ]; then
    exec foot \
        --app-id=vanhyprarch-colormix-poc \
        --title="Vanilla HyprArch - colormix PoC" \
        --fullscreen \
        -- "$renderer" "$@"
fi

exec foot \
    --app-id=vanhyprarch-colormix-poc \
    --title="Vanilla HyprArch - colormix PoC" \
    -- "$renderer" "$@"
