# Global text size

Vanilla HyprArch has one global text-size preference. The default is 12 pixels;
a missing preference means 12 without creating a file. Explicit choices are
stored as a strict version-1 file at:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/text-size.conf
```

`TextSizeController.qml` is the single shell authority. It reads and writes the
preference through `helpers/vanhyprarch_text_size`, then supplies the selected
base size to `VisualMetrics.qml`. The helper, controller, and Display panel all
accept every integer from 9 through 20 pixels.

## Shell geometry

All shared typography derives from the base size. Shared panel widths, padding,
spacing, rows, icons, fields, sliders, and toggles scale by the same ratio, with
12 pixels as the reference. The dock contract does not scale: its width remains
56 pixels; launcher and Power targets remain 40 pixels; system-control targets
remain 36 pixels; and launcher and system icon sizes remain 28 and 20 pixels.
The three-pixel exterior panel outline, one-pixel
internal separators/control outlines, and nine-pixel dock-to-popup gap also
remain fixed.

Panels not yet migrated to `VisualMetrics` retain their old local typography
until their scheduled visual-foundation migration. They must not create another
text-size preference.

## GTK and Foot projections

The helper projects a successful choice to the standard
`org.gnome.desktop.interface text-scaling-factor` GSettings key. The factor is
anchored at 12 pixels = 1.0 and quantized against the configured GTK interface
font's point size. `gsettings-desktop-schemas` is already present through the
tracked `xdg-desktop-portal-gtk` baseline; no GNOME session component is added.

Foot points are derived from Vanilla's validated baseline as
`round(12 points × base pixels / 12)`. With the current integer range this is
a one-to-one projection: Text Size 12 preserves Foot's existing 12-point
baseline. The helper edits only
one directly declared `font=` key in the user-owned `[main]` section, preserving
the family and every unrelated setting. It refuses symlinks and foreign-owned
files. If the font comes only from includes, the file is absent, or its ownership
is ambiguous, Foot is reported as unmanaged and is not changed. This avoids
inventing or overriding a user's font configuration before the update-safe
managed/default/user layers exist.

Foot 1.28 has no signal for reloading font configuration. Existing terminals
keep their startup size; newly launched terminals use the projected value. GTK
applications may likewise need to be relaunched if they do not react to the
GSettings change.

## Failure contract

Candidates are prepared and validated before state changes. The helper verifies
the GTK write, validates a managed Foot candidate with `foot --check-config`,
uses same-directory atomic replacement for file updates, and writes the
authoritative preference last. If a later step fails, it restores the previous
GTK factor and Foot file on a best-effort basis and leaves the old preference in
place. The controller changes the live shell base size only after parsing a
successful helper result, so a failed operation does not leave QML with an
optimistic second state.

This small preference and projection boundary is intended to move unchanged
behind the future managed/default/user configuration architecture. A future
bootstrap can establish a dedicated Foot override layer; it must not turn the
current conservative editor into permission to overwrite arbitrary user files.
