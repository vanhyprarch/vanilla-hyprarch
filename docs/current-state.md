# Current project state

Snapshot date: 2026-09-08.

This document distinguishes deployed behavior from accepted future work and
directions that still require validation.

## Repository and runtime identity — IMPLEMENTED

- Public name: **Vanilla HyprArch**
- Repository: `~/Projects/vanilla-hyprarch`
- Branch: `dock-prototype`
- Technical namespace and named Quickshell config: `vanhyprarch`
- Hyprland: 0.56.2 (`hyprland` package 0.56.2-2)
- Quickshell: 0.3.1 (`quickshell` package 0.3.1-1)

At inspection time exactly one Quickshell instance was registered, launched
from the `vanhyprarch` named configuration.

## Configuration paths — IMPLEMENTED

Repository-managed sources:

- `home/.config/hypr/hyprland.lua`
- `home/.config/hypr/bindings.lua`
- `home/.config/hypr/hypridle.conf`
- `home/.config/hypr/vanhyprarch-idle.conf`
- `home/.config/quickshell/vanhyprarch/`

Live paths:

- `~/.config/hypr/hyprland.lua`
- `~/.config/hypr/bindings.lua`
- `~/.config/hypr/hypridle.conf`
- `~/.config/hypr/vanhyprarch-idle.conf`
- `~/.config/quickshell/vanhyprarch`

The live Quickshell path is a symlink to:

`$HOME/Projects/vanilla-hyprarch/home/.config/quickshell/vanhyprarch`

The two live Hyprland Lua files were byte-identical to their repository copies
when this snapshot was prepared.

The following live configuration files exist but are not yet represented in
the repository:

- `~/.config/hypr/hyprlock.conf`
- `~/.config/hypr/hyprpaper.conf`

This is a known source-of-truth gap for future installer work, not permission to
copy hardware- or user-specific settings blindly.

Mutable shell state is stored outside Git. Theme mode uses
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/theme-mode`; launcher order
uses `Quickshell.statePath("launchers.json")` under Quickshell's shell-ID state.

## Session startup — IMPLEMENTED

Hyprland starts these processes on `hyprland.start`:

1. `hyprpaper`
2. `hypridle`
3. `qs -n -c vanhyprarch`

`-n` prevents a duplicate instance of the named Quickshell configuration.
Bindings are loaded from `~/.config/hypr/bindings.lua` with Lua `dofile()`, so a
change only to that file requires an explicit `hyprctl reload`.

Hyprland's existing input configuration sets `numlock_by_default = true`, so
Num Lock is enabled by default when the graphical session starts.

## Shell architecture — IMPLEMENTED

`ShellRoot` owns global state and controllers. A `Variants` instance models
`Quickshell.screens`; each delegate owns the permanent dock and desktop-frame
surfaces for one screen. This screen lifecycle structure is the validated fix
for dock/frame loss after suspend and resume.

Current IPC targets are:

- `vanhyprarch.shell`, exposing `ping()`
- `vanhyprarch.shortcuts`, exposing `open()`, `close()`, and `toggle()`

## User interface — IMPLEMENTED

The current Quickshell UI includes:

- a 56-pixel vertical dock and a desktop frame with rounded inner corners;
- five numbered workspaces, relative navigation, and a special scratchpad;
- persistent, drag-reorderable application launchers with running-workspace
  indicators, add/remove controls, and context actions;
- a native Quickshell system tray;
- native PipeWire output/input volume, mute, and device selection;
- native Quickshell/NetworkManager network status, Wi-Fi scanning, connection,
  password, known-network, and forget flows;
- DDC/CI brightness control and fixed monitor-scale presets;
- a compact Power & Idle panel backed by the project controller, with Caffeine,
  timeout presets, and one automatic-lock selection;
- a persistent light/dark shell theme using Papirus icons;
- clock and calendar;
- lock, suspend, reboot, and power-off actions;
- a searchable, read-only shortcut viewer populated from described Hyprland
  bindings.

Firefox, Foot, and Thunar are the selected browser, terminal, and file manager.
Hibernate is deliberately absent. No Bluetooth panel is implemented.

## Power and idle — IMPLEMENTED, MANUAL UI REVIEW PENDING

`bin/vanhyprarch-idle` owns persistent preferences, validation, managed
hypridle generation, runtime Caffeine state, and transactional daemon restart.
The accepted model has ordered Screen saver, Turn off display, and Suspend
stages plus one selectable stage that owns automatic locking. The current
stored/default state is `Never / Never / Never`, Lock `None`, and Caffeine off,
so the production fragment contains zero listeners and introduces no idle
behavior.

Preferences use a strict `key=value` file at
`${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/power-idle.conf`. Caffeine is a
session-only marker under `${XDG_RUNTIME_DIR}/vanhyprarch/`; enabling it
generates no automatic actions without changing stored preferences. The CLI
provides deterministic status output and atomic configure, set, apply, and
Caffeine operations for the future Quickshell UI.

## hypridle — PRODUCTION BACKEND, ZERO LISTENERS

The canonical static `hypridle.conf` retains
`lock_cmd = pidof hyprlock || hyprlock`, delegates conditional pre-sleep locking
to `vanhyprarch-idle before-sleep`, stops an owned saver after unlock, and
sources the generated `vanhyprarch-idle.conf`.

When Screen saver is enabled, generation preserves the manually validated
Hyprland 0.56.2 workaround: an inhibitor-aware start listener has no resume
action, while an input-only dismiss listener arms one second earlier and uses
`ignore_inhibit = true` only for a harmless timeout plus genuine-input resume.
The earlier 9/10-second values were test-only; they are not production
defaults.

Display-off generation uses Hyprland's native Lua DPMS dispatcher. Suspend uses
`systemctl suspend`; conditional `before-sleep` locking preserves the selected
lock point while allowing Lock `None` and Caffeine to suppress automatic lock.
These generated non-default paths have passed parser and backend tests but
still require integrated manual validation before the Power & Idle work is
considered complete.

Hyprland continues to own exactly one direct hypridle daemon. The backend
validates that ownership and requires the packaged systemd user service to
remain disabled and inactive. It parses a candidate configuration before an
atomic replacement and verifies exact listener counts after restart, restoring
the previous fragment and daemon on failure.

The first Quickshell panel is implemented between Monitor and Theme. One global
`IdleController` reads the backend at shell startup, on panel open, after every
operation, and at a conservative 30-second interval. Per-screen buttons and
popups consume that shared state. The panel exposes the documented presets,
disables choices that would violate stage ordering, clears automatic lock to
`None` atomically when its stage is changed to `Never`, and shows backend errors
without retaining failed optimistic state. The dock icon changes between
Papirus `preferences-system-power` and `caffeine`.

The QML loads in the live named configuration and external Caffeine on/off
synchronization has been exercised with zero listeners. Click behavior,
presentation, and the complete control flow still require manual visual review.

## Screensaver — PROVISIONAL

Ly's `colormix` animation has been investigated and is the preferred candidate.
An isolated proof-of-concept renderer is implemented and manually tested at
`experiments/colormix/` with this candidate architecture:

`Hyprland -> fullscreen Foot window -> lightweight standalone colormix renderer`

Visual testing confirms that its 5, 16, and 33 millisecond render cadences now
retain approximately the same movement speed by normalizing animation time to
Ly's 5-millisecond reference. The current provisional default is 33
milliseconds, approximately 30 fps. On the development system that mode used
about 23.9% of one logical CPU across Foot and the renderer, versus about 42.4%
at 16 milliseconds (approximately 60 fps), roughly halving the combined CPU
cost. These measurements are observations, not universal performance claims.

The PoC is not a production screensaver and has no Quickshell integration.
Phase 1 of lifecycle work provides the tracked
`bin/vanhyprarch-screensaver` controller with idempotent `start`, `stop`, and
`status` commands, XDG runtime ownership state, and process-identity validation.
Manual testing validated start, status, repeated-start idempotency, stop,
repeated-stop idempotency, and isolation from ordinary Foot terminals.
The controller also saves the current Hyprland `cursor:invisible` boolean in a
separate runtime-only record, hides the cursor before launching Foot, and
restores the exact prior value after stop, stale-process cleanup, or failed and
interrupted startup. Static and non-GUI mock-process validation has passed;
fullscreen lifecycle, genuine-input dismissal, cursor hiding, immediate exact
cursor restoration, and isolation from ordinary Foot processes were also
manually validated.

The candidate remains Provisional until its production lifecycle and
integration are implemented and validated. Current lifecycle design and the
intended future hypridle semantics are recorded in
`docs/screensaver-lifecycle.md`.

## Known open work

### PLANNED

- Bring the required hyprlock and hyprpaper configuration into the repository
  in portable form.
- Build an auditable installer from the package manifests and documented
  service ownership.
- Define optional/recommended packages separately from the core baseline;
  `file-roller` is a candidate convenience, not a core requirement.
- Design future Bluetooth UX without presuming `blueman`; BlueZ remains the
  current backend and no shell Bluetooth panel exists.
- Choose and validate an explicit PolicyKit authentication-agent startup owner
  for the plain Hyprland session.
- Develop the light/dark wallpaper selection system.
- Consider the reserved main-menu, power-menu, clipboard, and Bluetooth-panel
  UX only as separate future work.

### PROVISIONAL

- Evaluate multi-output coverage and Foot presentation before promoting the
  colormix work beyond Provisional.
- Manually validate production lock, DPMS, suspend, and Caffeine lifecycle
  combinations without turning test timings into defaults.

### NOT IMPLEMENTED

- Production screensaver
- Bluetooth panel
- Reproducible installer
