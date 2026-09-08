# Current project state

Snapshot date: 2026-09-08.

This document distinguishes deployed behavior from accepted future work and
directions that still require validation.

Validated upstream-version behavior and workaround removal conditions are
tracked in the [compatibility register](compatibility.md).

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
- `home/.config/quickshell/vanhyprarch-screensaver/`

Live paths:

- `~/.config/hypr/hyprland.lua`
- `~/.config/hypr/bindings.lua`
- `~/.config/hypr/hypridle.conf`
- `~/.config/hypr/vanhyprarch-idle.conf`
- `~/.config/quickshell/vanhyprarch`
- `~/.config/quickshell/vanhyprarch-screensaver`

The live Quickshell path is a symlink to:

`$HOME/Projects/vanilla-hyprarch/home/.config/quickshell/vanhyprarch`

The dedicated screensaver named config uses the same development deployment
model and points to the tracked `vanhyprarch-screensaver` directory. It starts
only on demand and is not part of session autostart.

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

## Power and idle — IMPLEMENTED, INTEGRATED ACTION TESTING PENDING

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
Caffeine operations for the Quickshell UI.

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

The QML loads in the live named configuration. The panel, its Caffeine state,
timeout presentation, error-only feedback, and passive-refresh behavior have
passed manual visual review. Integrated screensaver, lock, DPMS, and suspend
actions still require controlled manual validation.

## Screensaver — IMPLEMENTED PRESENTATION, INTEGRATED ACTION TESTING PENDING

Ly's `colormix` animation remains the provisional visual. The isolated native
renderer and former Foot presentation remain at `experiments/colormix/` as
historical and algorithm references. Production now uses:

`vanhyprarch-screensaver -> separate Quickshell process -> layer-shell overlays`

Visual testing confirms that its 5, 16, and 33 millisecond render cadences now
retain approximately the same movement speed by normalizing animation time to
Ly's 5-millisecond reference. The current provisional default is 33
milliseconds, approximately 30 fps. On the development system that mode used
about 23.9% of one logical CPU across Foot and the renderer, versus about 42.4%
at 16 milliseconds (approximately 60 fps), roughly halving the combined CPU
cost. These measurements are observations, not universal performance claims.

The dedicated config creates one full-output overlay surface per live
`Quickshell.screens` entry. A native Canvas port retains the transform,
12-entry color structure, randomized offsets, 33-millisecond cadence, and
Ly-equivalent 5-millisecond motion reference without Foot, ANSI, or a compiled
production renderer.

`bin/vanhyprarch-screensaver` retains idempotent `start`, `stop`, and `status`.
Its runtime record now combines PID/start-time/PGID/SID checks with the exact
Quickshell instance ID, shell ID, named-config path, arguments, and startup
layer namespace. Cursor preservation and immediate stop-time restoration are
unchanged. Lifecycle, exact prior-cursor restoration, controlled crash
recovery, main-shell isolation, and one-layer-per-current-output startup have
passed runtime validation.

The presentation architecture is Accepted, while final visual acceptance and
real lock/DPMS/suspend integration remain Provisional. Current lifecycle design
and generated hypridle semantics are recorded in
`docs/screensaver-lifecycle.md`.

On Hyprland 0.56.2 with hypridle 0.1.8, the former Foot mapping changed an
intended 10/20/30-second marker timeline to approximately 10/30/40. The
Quickshell layer-shell proof of concept retained 10/20/30 twice, and the real
production controller path subsequently did so twice more without false
resume or timer rearm. Evidence and retest conditions are in the
[compatibility register](compatibility.md).

The first Canvas version used a coarse 96-by-36 sample grid on the development
output and appeared visibly zoomed compared with the Foot+C reference. The
corrected grid uses the reference terminal's measured logical cell pitch,
yielding approximately 320 by 77 samples on that output. An eight-second
offscreen Qt software-rendering check painted 242 frames, sustaining the
33-millisecond target at about 75% of one logical CPU and 74 MiB RSS for the
standalone `qmlscene` test process. Those figures are a deliberately
non-disruptive estimate, not a production Quickshell fullscreen measurement.
The corrected visual scale and production-process resource use still require
bounded manual validation.

## Known open work

### PLANNED

- Bring the required hyprlock and hyprpaper configuration into the repository
  in portable form.
- Build the shared bootstrap and thin optional archinstall integration defined
  in the [installation strategy](installation-strategy.md), supporting both a
  configured first reboot and post-install use on minimal Arch.
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

- Manually review the native layer-shell colormix appearance and resource
  tradeoff, including real multi-output and suspend/resume behavior.
- Manually validate production lock, DPMS, suspend, and Caffeine lifecycle
  combinations without turning test timings into defaults.
- Reassess whether the retained S-1 dismissal workaround can be simplified
  after a separate inhibitor and input-lifecycle regression.

### NOT IMPLEMENTED

- Bluetooth panel
- Shared bootstrap and optional archinstall integration
