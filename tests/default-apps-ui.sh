#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/vanhyprarch-default-apps-ui.XXXXXX")
trap 'rm -rf -- "$test_dir"' EXIT HUP INT TERM
mkdir -m 0700 -p "$test_dir/runtime" "$test_dir/data/applications" "$test_dir/userdata"
ln -s "$repository_dir/home/.config/quickshell/vanhyprarch/components" "$test_dir/components"
ln -s "$script_dir/SuperSpacePanelHarness.qml" "$test_dir/SuperSpacePanelHarness.qml"
sed 's#import "../home/.config/quickshell/vanhyprarch/components"#import "components"#' \
    "$script_dir/default-apps.qml" > "$test_dir/shell.qml"
cat > "$test_dir/data/applications/firefox.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Firefox
Exec=/usr/bin/true
Categories=Network;WebBrowser;
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;
EOF
cat > "$test_dir/data/applications/zeta.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Alpha
Exec=/usr/bin/true
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;
EOF
cat > "$test_dir/data/applications/alpha.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=alpha
Exec=/usr/bin/true
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;
EOF
cat > "$test_dir/data/applications/foot.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Foot
Exec=/usr/bin/true
Categories=System;TerminalEmulator;
EOF
cat > "$test_dir/data/applications/org.gnome.TextEditor.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Text Editor
Exec=/usr/bin/true
Categories=Utility;TextEditor;
MimeType=text/plain;
EOF
env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=offscreen \
    XDG_RUNTIME_DIR="$test_dir/runtime" XDG_DATA_HOME="$test_dir/userdata" \
    XDG_DATA_DIRS="$test_dir/data" \
    timeout 10s qs --no-color -p "$test_dir" > "$test_dir/quickshell.log" 2>&1 || {
        cat "$test_dir/quickshell.log" >&2
        exit 1
    }
grep -Fq 'vanhyprarch Default Apps UI self-check passed' "$test_dir/quickshell.log" || {
    cat "$test_dir/quickshell.log" >&2
    exit 1
}
printf '%s\n' 'Default Apps UI: PASS'
