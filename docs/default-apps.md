# Default Apps

Super+Space places Default Apps between Style and Additional system components.
Its first version exposes exactly Browser, Terminal, and Text Editor. The panel
does not save a Vanilla preference registry: it reads the effective desktop
defaults each time the section is opened, and opening it writes nothing.

Browser uses the MIME Apps defaults for `text/html`, `x-scheme-handler/http`,
and `x-scheme-handler/https` as one choice. Differing effective handlers appear
as Mixed. Text Editor controls only `text/plain`. GIO resolves effective MIME
defaults and desktop-entry MIME declarations. Candidate IDs are intersected
with Quickshell `DesktopEntries.applications` for visible names and icons.

Terminal uses the official Arch `xdg-terminal-exec` implementation of the
proposed Default Terminal Execution specification. `--print-id` supplies the
effective selection. Vanilla's managed, low-priority
`/usr/local/share/xdg-terminal-exec/hyprland-xdg-terminals.list` contains
`foot.desktop`; user and administrator lists take precedence. Foot currently
requires the resolver's default compatibility mode, documented in
[Compatibility](compatibility.md).

Fresh create-once MIME bytes select Firefox for the three browser types and
GNOME Text Editor for `text/plain`. Existing MIME configuration is never
migrated to match new seed bytes. An explicit user selection narrowly edits the
user's `mimeapps.list`, or a controlling higher-priority desktop-specific user
file. Terminal selection similarly edits a user `xdg-terminals.list` file.
Comments and unrelated settings are preserved. Symlink, non-regular,
ambiguous, and unexpectedly owned paths fail closed. The backend publishes
atomically and verifies effective readback, rolling back on failure.

The backend command is `vanhyprarch-default-apps status` for read-only JSON
and `vanhyprarch-default-apps select browser|terminal|editor DESKTOP_ID` for an
explicit choice. Both responses use schema version 1 with `effective` IDs and
eligible `candidates` IDs. Existing explicit Firefox and Foot shortcuts and
supervised Foot package-operation windows keep their current behavior.

Real-host acceptance confirmed the three effective names and eligible
candidates, zero-write opening, the installed resolver and Foot fallback,
explicit Browser, Terminal, and Text Editor selections, and standards-aware
`xdg-open` behavior for HTTPS and a text file. Managed deployment validation
reported 22 valid artifacts.
