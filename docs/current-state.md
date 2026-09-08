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
- `home/.config/quickshell/vanhyprarch/`

Live paths:

- `~/.config/hypr/hyprland.lua`
- `~/.config/hypr/bindings.lua`
- `~/.config/quickshell/vanhyprarch`

The live Quickshell path is a symlink to:

`$HOME/Projects/vanilla-hyprarch/home/.config/quickshell/vanhyprarch`

The two live Hyprland Lua files were byte-identical to their repository copies
when this snapshot was prepared.

The following live configuration files exist but are not yet represented in
the repository:

- `~/.config/hypr/hypridle.conf`
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
- a persistent light/dark shell theme using Papirus icons;
- clock and calendar;
- lock, suspend, reboot, and power-off actions;
- a searchable, read-only shortcut viewer populated from described Hyprland
  bindings.

Firefox, Foot, and Thunar are the selected browser, terminal, and file manager.
Hibernate is deliberately absent. No Bluetooth panel is implemented.

## Power and idle — PLANNED

The existing power menu is implemented, but the Power & Idle settings UI and
controller do not exist. The accepted design has ordered Screen saver, Turn off
display, and Suspend stages, plus one selectable stage that owns automatic
locking. Initial values remain effectively `Never / Never / Never` until the
user makes a choice.

## hypridle — IMPLEMENTED CURRENT BASE, PLANNED MANAGEMENT

The live `hypridle.conf` currently contains only:

- `lock_cmd = pidof hyprlock || hyprlock`
- `before_sleep_cmd = loginctl lock-session`

It has zero idle listeners. There is therefore no current idle-triggered screen
saver, DPMS-off, lock, or suspend timeout. Hyprland is configured to start
hypridle directly; the packaged systemd user service is disabled and inactive.

Generating a managed `vanhyprarch-idle.conf`, restarting safely, verifying the
new daemon, rolling back failures, and possibly assigning ownership to a
systemd user service are not implemented. That architecture remains
provisional until reviewed with the final lock and screensaver lifecycle.

## Screensaver — PROVISIONAL

Ly's `colormix` animation has been investigated and is the preferred candidate.
The next task is an isolated proof of concept:

`Hyprland -> fullscreen Foot window -> lightweight standalone colormix renderer`

No renderer has been implemented. There is no production screensaver, no
hypridle listener for one, and no Quickshell integration. The candidate becomes
an accepted project component only after visual, lifecycle, input-exit,
licensing, and resource-use validation.

## Known open work

### PLANNED

- Build the Power & Idle controller and per-screen UI after its backend design
  is finalized.
- Bring the required hyprlock, hyprpaper, and static hypridle configuration into
  the repository in portable form.
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

- Build and review the isolated colormix proof of concept.
- Finalize hypridle configuration generation, restart/rollback behavior, and
  single-process ownership after screensaver validation.

### NOT IMPLEMENTED

- Power & Idle settings UI
- Generated `vanhyprarch-idle.conf`
- Production screensaver
- Bluetooth panel
- Reproducible installer
