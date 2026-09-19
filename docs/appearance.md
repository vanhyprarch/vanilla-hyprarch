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

They are user-content locations. Vanilla may create missing directories but
never owns, renames, overwrites, or deletes their images.

Eight original Wolkenstein Light/Dark images ship as GPL-2.0-only managed
distribution assets under `assets/wallpapers/`. Deployment installs exact
managed copies below
`${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/wallpapers/`; the Appearance
manager non-destructively seeds them into the user-content directories. Pair 1,
`Wolkenstein_1_light.png` and `Wolkenstein_1_dark.png`, is the explicit default.

The mode-0600
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/appearance-assets.json`
receipt records only hashes that Appearance previously seeded. A missing
destination receives the exact reviewed bytes. An unchanged prior seed may be
updated when its managed source changes, and newly introduced assets may be
added. An unrelated file or a user-modified same-name file is preserved. The
operation never removes user content. `seed-assets` exposes this bounded step
to the future bootstrap; normal reconciliation also runs it idempotently.

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

`set-mode` first persists the desired mode, then applies and verifies the host
preference and the remembered wallpaper. Status keeps desired preference
separate from effective host, portal, process, and per-output wallpaper state.
Partial external failure therefore remains visible and can be repaired by an
idempotent `reconcile`; it never causes the dock to invent a second mode. If
Hyprpaper is absent or unavailable, shell and host appearance still reconcile,
while status reports the wallpaper capability failure.

The `catalog` and `set-wallpaper current PATH` boundaries expose only what the
next visual picker needs. This milestone deliberately includes no picker,
thumbnail cache, carousel, Style menu, or background shortcut.
