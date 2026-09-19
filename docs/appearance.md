# Appearance foundation

Appearance is the single Vanilla HyprArch authority for Light/Dark preference.
The global Quickshell `AppearanceController` consumes the strict status from
`vanhyprarch-appearance`; the dock icon requests a mode change only through
that controller. `Theme.qml` remains the visual palette projection and does not
persist a separate choice.

The durable version-1 preference is
`${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/appearance.json`. It records the
current mode plus one relative wallpaper selection for Light and one for Dark.
Relative names are resolved beneath the current XDG Pictures directory. The
content directories are:

```text
<XDG Pictures>/Wallpapers/Light
<XDG Pictures>/Wallpapers/Dark
```

They are user-content locations. Vanilla may create and populate them during
first initialization only; afterward it never owns, renames, overwrites,
restores, or deletes their contents.

Eight original Wolkenstein Light/Dark images ship as GPL-2.0-only managed
distribution assets under `assets/wallpapers/`. Deployment installs exact
managed copies below
`${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/wallpapers/`; the Appearance
manager seeds them non-destructively as starter content only when wallpaper
bootstrap has never completed for the user. Pair 1,
`Wolkenstein_1_light.png` and `Wolkenstein_1_dark.png`, is the explicit default
for that fresh initialization.

The mode-0600
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/appearance-assets.json`
version-2 receipt is the durable completion marker for this one-shot bootstrap.
On a true first initialization, Appearance creates the Light and Dark
directories, verifies every managed source, copies only absent destinations,
and records completion only after the whole operation succeeds. An unrelated
file or any same-name collision is preserved.

A version-1 hash receipt is durable evidence that an earlier release already
initialized the user, so it is migrated to version 2 without reading or
changing wallpaper-directory contents. An existing `appearance.json` is the
same conservative migration evidence when the older receipt is absent. The
legacy per-file hashes are retained for historical compatibility but no longer
authorize replacement, restoration, or addition. Normal `seed-assets`,
reconciliation, mode changes, and wallpaper changes all become content no-ops
after initialization. Deleting one starter, deleting all starters, leaving a
mode directory empty, or replacing everything with personal images is a valid
user-owned state. A future managed starter set therefore affects only users
whose bootstrap has never completed. A future restore-defaults action would
need a separate explicit user request; it is not part of reconciliation.

The host preference is the writable
`org.gnome.desktop.interface color-scheme` GSettings key. Dark maps to
`prefer-dark`; Light maps to `prefer-light`. The GTK Settings portal provider
projects that value as `org.freedesktop.appearance/color-scheme` values 1 and 2
respectively. Appearance verifies that portal readback and does not write to
the portal, edit application profiles, force toolkit themes, or restart
applications. Applications that choose their own theme remain in control.

Hyprpaper is a required renderer, not a preference authority. Hyprland starts
one session-owned instance through `vanhyprarch-appearance renderer-start`.
The managed Hyprpaper configuration enables IPC and contains no wallpaper
choice. Reconciliation reads current outputs from `hyprctl -j monitors`, sends
the installed comma-delimited `wallpaper` request explicitly for every output
with `cover` fit, and verifies the unchanged monitor set plus every
`listactive` entry. It also installs an empty-monitor fallback for a newly
appearing output, but never treats that fallback as proof that an existing
explicit target changed. One selection is intentionally used across all
outputs in this foundation; per-monitor preference is future work.

The managed Hyprland core sets `misc.disable_hyprland_logo = true`. Appearance
owns wallpaper presentation, so Hyprland's native logo/default background must
not become visible beneath Hyprpaper while an output target is replaced. A
controlled Hyprland 0.56.2 and Hyprpaper 0.8.4 runtime test proved that this
single setting removes the foreign frame without exposing a black or blank
frame; no renderer sequencing workaround is required. The shell palette still
updates after the manager has reconciled and verified external Appearance
state.

Wallpaper paths are canonicalized and must resolve to a regular file beneath
the matching mode directory. A symlink whose target remains inside is accepted;
an escaping symlink is rejected. The installed renderer stack was verified for
PNG, JPEG, BMP, WebP, SVG, and JPEG XL. The manager uses content MIME detection,
not a filename-extension filter, and still treats renderer rejection as a
reported effective-state failure. The installed comma-delimited IPC cannot
represent a filename containing a comma, so that case fails closed; spaces,
Unicode, and shell metacharacters remain literal process arguments.

On first reconciliation, a valid legacy shell `theme-mode` value preserves the
existing Vanilla palette choice; otherwise the current host preference is used,
falling back deterministically to Light. Both wallpaper selections start at the
explicit pair-1 defaults after successful asset seeding. A uniform current
wallpaper already inside a required mode directory overrides that mode's
default during first-run adoption. Existing `appearance.json` selections,
including an intentional unset selection, are preserved. No directory entry is
chosen by enumeration. A missing selection does not block shell or host mode.

If a remembered wallpaper is later deleted, Appearance leaves both the missing
file and the stored selection alone. Host mode reconciliation still proceeds,
but wallpaper application and status report the invalid selection and send no
Hyprpaper request. If the preference is unset and the directory is empty, the
existing safe unselected/empty-catalog state is used. The user may select any
remaining catalog item explicitly; Appearance never manufactures an official
fallback after bootstrap.

`set-mode` first persists the desired mode, then applies and verifies the host
preference and the remembered wallpaper. Status keeps desired preference
separate from effective host, portal, process, and per-output wallpaper state.
Partial external failure therefore remains visible and can be repaired by an
idempotent `reconcile`; it never causes the dock to invent a second mode. If
Hyprpaper is absent or unavailable, shell and host appearance still reconcile,
while status reports the wallpaper capability failure.

`catalog current` is the visual picker's machine-readable source. It resolves
only the current mode directory, validates entries through the same containment
and MIME boundary as selection, and returns deterministic natural filename
order plus filename, canonical path, file URI, and selected state. The original
version-1 `wallpapers` path array remains for compatible consumers. Catalog
queries neither seed assets nor mutate preferences.

Super+Space exposes `Style` directly below `Update`; its only current action is
`Choose background`. The same global Background Picker controller is reached
through that action and `Super+Ctrl+Space`. It refreshes the catalog on every
open, shows only the current Light or Dark directory, and resets to that mode's
remembered selection. A mode change while open clears the old previews and
loads the new mode catalog. The normal dock Light/Dark click first closes a
central overlay under the established coordinator boundary, so that path
closes the picker before changing mode instead of creating a ThemeToggle
exception.

The normal picker is a minimal floating horizontal carousel: the responsive
current card remains dominant while up to two real neighbors on either side
become progressively smaller, further outward, and visually behind it. Cards
remain fully opaque; depth comes only from scale, position, overlap, and
z-order. They sit directly over the desktop without a visible outer panel,
title, filename, controls, or instructions. The only normal-state label is the
small `Applied` marker attached to the remembered wallpaper. Exceptional
loading, empty, decode-failure, and apply-error states retain only the concise
feedback needed to diagnose them.

Picker navigation is intentionally keyboard- and click-driven. Left and Right
or a first card click move only the navigation candidate; they do not persist a
preference or contact Hyprpaper. Enter or a second click on the current card
calls the global Appearance controller, which invokes
`set-wallpaper current PATH`; success closes the picker, while failure
preserves the candidate and displays the backend error. Escape and outside
dismissal close without mutation. Preview images use asynchronous,
aspect-preserving crop from the original files and one fixed bounded decode
size, so a loaded texture remains present while its card changes depth. Sources
remain active only for the current card and its two nearest neighbors per side;
there is no thumbnail cache or worker pipeline.
