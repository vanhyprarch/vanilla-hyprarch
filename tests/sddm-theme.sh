#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
theme=$repository/system/usr/share/sddm/themes/vanhyprarch
runtime=$(mktemp -d /tmp/vanhyprarch-sddm-theme.XXXXXX)
trap 'rm -rf -- "$runtime"' EXIT HUP INT TERM

python "$repository/tests/sddm-theme.py"

if [ -x /usr/lib/qt6/bin/qmllint ]; then
    /usr/lib/qt6/bin/qmllint --ignore-settings \
        "$theme/Main.qml" \
        "$theme/LoginScene.qml" \
        "$theme/SessionResolver.qml" \
        "$repository/tests/tst_sddm_theme.qml"
    printf '%s\n' 'SDDM Qt 6 QML lint: PASS'
else
    printf '%s\n' 'SDDM Qt 6 QML lint: SKIP (qmllint unavailable)'
fi

if [ -x /usr/lib/qt6/bin/qmltestrunner ]; then
    QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner \
        -input "$repository/tests/tst_sddm_theme.qml" -o -,txt
else
    printf '%s\n' 'SDDM mocked QML behavior: SKIP (qmltestrunner unavailable)'
fi

if [ -x /usr/bin/sddm-greeter-qt6 ]; then
    greeter_log=$runtime/sddm-greeter.log
    set +e
    QT_QPA_PLATFORM=offscreen timeout 3s /usr/bin/sddm-greeter-qt6 \
        --test-mode --theme "$theme" >"$greeter_log" 2>&1
    greeter_status=$?
    set -e
    case "$greeter_status" in
        0|124) ;;
        *)
            sed -n '1,240p' "$greeter_log" >&2
            printf '%s\n' "SDDM Qt 6 greeter test failed: $greeter_status" >&2
            exit 1
            ;;
    esac
    if grep -Eiq \
        'error loading|failed to load|is not a type|referenceerror|typeerror|cannot assign|module .* not installed|no such file' \
        "$greeter_log"; then
        sed -n '1,240p' "$greeter_log" >&2
        printf '%s\n' 'SDDM Qt 6 greeter reported a theme load error' >&2
        exit 1
    fi
    printf '%s\n' 'SDDM Qt 6 offscreen greeter load: PASS'
else
    printf '%s\n' 'SDDM Qt 6 offscreen greeter load: SKIP (greeter unavailable)'
fi
