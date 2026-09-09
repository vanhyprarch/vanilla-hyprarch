# Current project state

Snapshot date: 2026-09-09.

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
- `install/install-zig-player`

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
2. `sh -lc 'export PATH="$HOME/.local/bin:$PATH"; exec hypridle -v'`
3. `qs -n -c vanhyprarch`

The temporary shell only constructs the user-local `PATH`; `exec` replaces it
with `/usr/bin/hypridle`, so the final daemon remains directly parented by
Hyprland while being able to resolve Vanilla HyprArch executables from
`$HOME/.local/bin`.

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
  timeout presets, screensaver-effect selection, and one automatic-lock
  selection;
- a persistent light/dark shell theme using Papirus icons;
- clock and calendar;
- lock, suspend, reboot, and power-off actions;
- a searchable, read-only shortcut viewer populated from described Hyprland
  bindings.

Firefox, Foot, and Thunar are the selected browser, terminal, and file manager.
Hibernate is deliberately absent. No Bluetooth panel is implemented.

## Power and idle — IMPLEMENTED, SCREENSAVER CHAIN VALIDATED

`bin/vanhyprarch-idle` owns persistent preferences, validation, managed
hypridle generation, runtime Caffeine state, and transactional daemon restart.
The accepted model has ordered Screen saver, Turn off display, and Suspend
stages plus one selectable stage that owns automatic locking and one persisted
screensaver effect. The default version-2 state is `Never / Never / Never`,
Lock `None`, effect `colormix`, and Caffeine off, producing zero listeners until
the user enables one or more stages. Existing version-1
preferences remain readable as `effect=colormix`; their next preference write
migrates them to version 2 without losing prior settings.

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

When Screen saver is enabled, one inhibitor-aware listener starts the
controller at its timeout and stops it on genuine-input resume. If Screen saver
owns locking, resume requests the existing lock transition instead. No S-1,
`ignore_inhibit`, or input-only helper is generated.

Display-off generation uses Hyprland's native Lua DPMS dispatcher. Suspend uses
`systemctl suspend`; conditional `before-sleep` locking preserves the selected
lock point while allowing Lock `None` and Caffeine to suppress automatic lock.
The generated screensaver path has passed production integration testing.
A real cold-boot idle sequence also passed with Screen saver at 2 minutes,
display off at 5 minutes, suspend at 10 minutes, and normal resume. Automatic
lock remains intentionally untested.

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
timeout presentation, effect persistence, error-only feedback, and
passive-refresh behavior have passed manual review. The complete screensaver
chain is validated. Real display-off and suspend behavior also passed a
cold-boot 2/5/10-minute test with normal resume; automatic lock still requires
separate controlled validation.

## Screensaver — NATIVE PLAYER PRODUCTION CHAIN VALIDATED

Production now uses:

`vanhyprarch-screensaver -> vanhyprarch-zig-player <effect> -> wlr-layer-shell`

Rendering is delegated to the independent GPL-2.0-only Zig Player at pinned
release `v0.1.1`; its implementation is not vendored here. Available effects
are ColorMix, Matrix, Doom, and Game of Life. The versioned installer verifies
the x86_64 release archive and deploys the binary, upstream license, notices,
README, and pinned metadata to per-user XDG locations. Zig is not a runtime
dependency.

`bin/vanhyprarch-screensaver` retains idempotent `start`, `stop`, and `status`,
exact cursor restoration, serialized lifecycle operations, failed-start
cleanup, and stale-state handling. It records only the native PID, Linux start
time, exact executable path, and effect argument and never signals a process
that fails those checks. All Quickshell-specific screensaver ownership and
presentation logic has been removed; the main shell is independent.

The final production test exercised `hypridle -> vanhyprarch-screensaver ->`
`vanhyprarch-zig-player v0.1.1`. The controller started ColorMix at +10.034
seconds, a harmless second listener fired at +20.036 seconds, and their 10.002
second separation proved that startup did not reset the idle clock. Genuine
keyboard input emitted resume at +23.291 seconds and stopped the owned player.
The first `x` did not reach the Foot terminal underneath; no process, layer, or
cursor state remained afterward, and the normal zero-listener configuration
was restored.

Separate manual tests also confirmed pointer-click and scroll absorption.
Input routing is owned by the player; Vanilla HyprArch carries no input
workaround. Physical two-monitor validation remains pending.

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

- Validate the external player's physical multi-output and suspend/resume
  behavior.
- Manually validate production lock, DPMS, suspend, and Caffeine lifecycle
  combinations without turning test timings into defaults.

### NOT IMPLEMENTED

- Bluetooth panel
- Shared bootstrap and optional archinstall integration
