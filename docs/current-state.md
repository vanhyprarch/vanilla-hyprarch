# Current project state

Snapshot date: 2026-09-15.

This document distinguishes deployed behavior from accepted future work and
directions that still require validation.

Validated upstream-version behavior and workaround removal conditions are
tracked in the [compatibility register](compatibility.md).

## Repository and runtime identity — IMPLEMENTED

- Public name: **Vanilla HyprArch**
- Repository: `~/Projects/vanilla-hyprarch`
- Development branch: `visual-foundation`
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

The tracked `hyprland.lua` is the current development-machine profile, not a
portable Vanilla HyprArch default. It contains the development system's
`DP-1`, `3840x2160@60`, scale `1.25`, 10-bit/color-management, and Italian
keyboard choices. The Monitor panel's persistent scale presets intentionally
edit the single `dp1Scale` declaration and are currently enabled only for
`DP-1`. Users must review these values rather than deploy the file unchanged;
general monitor and input overrides belong to the planned update-safe
customization layer.

The following live configuration files exist but are not yet represented in
the repository:

- `~/.config/hypr/hyprlock.conf`
- `~/.config/hypr/hyprpaper.conf`

This is a known source-of-truth gap for future installer work, not permission to
copy hardware- or user-specific settings blindly.

Mutable shell state is stored outside Git. Theme mode uses
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/theme-mode`; launcher order
uses `Quickshell.statePath("launchers.json")` under Quickshell's shell-ID state.
Global text size uses the versioned preference documented in
[Global text size](text-size.md); a missing preference means the 12-pixel
default without creating state.

## Session startup — IMPLEMENTED

The graphical session remains the direct
`Ly -> /usr/bin/start-hyprland -> Hyprland` path. UWSM is not part of the
Vanilla HyprArch architecture.

Hyprland starts these processes on `hyprland.start`:

1. `hyprpaper`
2. `systemctl --user start hyprpolkitagent`
3. `sh -lc 'export PATH="$HOME/.local/bin:$PATH"; exec hypridle -v'`
4. `qs -n -c vanhyprarch`

The official `hyprpolkitagent` package provides graphical PolicyKit
authentication for GUI applications that require privileged authorization.
Its packaged user service is started by the direct Hyprland session and is not
enabled as a separate login-time startup owner.

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
`Quickshell.screens`; each delegate owns the permanent dock and transparent
shortcut-anchor surfaces for one screen. This screen lifecycle structure is
the validated fix for dock loss after suspend and resume.

Current IPC targets are:

- `vanhyprarch.shell`, exposing `ping()`
- `vanhyprarch.shortcuts`, exposing `open()`, `close()`, and `toggle()`

## User interface — IMPLEMENTED

The current Quickshell UI includes:

- a 56-pixel vertical dock, without a decorative desktop frame;
- five numbered workspaces, relative navigation, and a special scratchpad;
- persistent, drag-reorderable application launchers with running-workspace
  indicators, add/remove controls, and context actions;
- a native Quickshell system tray;
- native PipeWire output/input volume, mute, and device selection;
- native Quickshell/NetworkManager network status, Wi-Fi scanning, connection,
  password, known-network, and forget flows;
- native Quickshell/BlueZ Bluetooth power, discovery, device, pairing,
  connection, trust, and forget flows, with complete PIN, passkey,
  confirmation, and authorization prompts supplied by a narrow pairing agent;
- DDC/CI brightness control, fixed monitor-scale presets, and a global text-size
  control supporting every integer from 9 through 20 with a project default of
  12;
- a compact Power & Idle panel backed by the project controller, with Caffeine,
  timeout presets, screensaver-effect selection, and one automatic-lock
  selection;
- a persistent light/dark shell theme using Papirus icons;
- clock and calendar;
- lock, suspend, logout through `hyprshutdown`, reboot, and power-off actions;
- a searchable, read-only shortcut viewer populated from described Hyprland
  bindings.

The desktop uses 5-pixel inner and 10-pixel outer Hyprland gaps with square
application windows. Network, Bluetooth, Audio, and Display use the centralized
square panel foundation, including a nine-pixel dock gap, complete opaque
three-pixel exterior outlines, and one-pixel internal separators. Other panels
retain their legacy visual treatment until their scheduled normalization.

PowerMenu may show a very brief oversized-text first frame when opening; QML
geometry, font-size, and scale measurements were correct from the first visible
event, the root cause is not proven, and the issue is currently non-blocking.

From bottom to top, the dock's lower status/control area is Power,
Clock/calendar, Theme, Power & Idle, Display, Audio, Network, Bluetooth, and
System tray.

Firefox, Foot, and Thunar are the selected browser, terminal, and file manager.
Hibernate is deliberately absent.

The Bluetooth pairing agent is one global Quickshell-supervised Python child.
It implements only BlueZ `org.bluez.Agent1`, becomes the default
`KeyboardDisplay` agent, and uses versioned newline-delimited JSON over its
private stdin/stdout pipes. The per-screen Bluetooth panels remain inside the
validated screen `Variants`; incoming prompts are routed to the focused or
last-active appropriate screen. Displayed PIN/passkey callbacks receive their
D-Bus reply only after a panel confirms that the challenge is visible. Pairing
intent is limited to one agent-session-bound transaction, and the agent fails
closed if its authenticated BlueZ owner, UI, IPC, or process owner disappears.
No `bluetoothctl` polling, listing, or interactive-prompt parsing is used.
An explicit panel power choice is stored as `on` or `off` in
`${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/bluetooth-power.conf`. One
global controller restores that choice through native Quickshell adapter
objects when adapters appear or recover from a transient state; observed
adapter state never rewrites the preference. The global choice applies to all
adapters. A missing preference is treated in memory as the Vanilla HyprArch
default of ON without creating a preference file.

The tracked minimal BlueZ configuration is a complete `main.conf` replacement
that sets `[Policy] AutoEnable=false`; BlueZ 5.87 does not provide a
`main.conf.d` drop-in mechanism. It is deployed on the development machine, but
current users must not copy it blindly over an existing customized file. The
future bootstrap must validate and preserve administrator configuration for
rollback before installing the project file ahead of the first session.

Synthetic validation covers static QML, controller state, fail-closed agent
callbacks, power-preference behavior, and an isolated
register/default/unregister lifecycle without changing real adapter power or
starting discovery. This is not counted as hardware validation.

Real-hardware validation covers dock integration, panel-owned discovery and
cleanup, discovery of an Android phone, successful outgoing pairing through
the Vanilla HyprArch UI, and both saved OFF-to-OFF and ON-to-ON restoration
across real reboots with discovery inactive. Persistent-profile
Connect/Disconnect with suitable headphones, mouse, or keyboard; Forget and
re-pair; incoming pairing while the panel is closed; the full PIN, passkey,
display-passkey, and service-authorization matrix; multi-monitor incoming
prompt routing; and shell reload during active pairing remain pending
real-hardware validation.

## Power and idle — IMPLEMENTED, POWER/LOCK LIFECYCLE VALIDATED

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
display off at 5 minutes, suspend at 10 minutes, and normal resume.

Controlled manual lifecycle tests additionally validated:

- automatic lock at the Screen saver stage;
- automatic lock at the Display stage;
- dismissing the saver before its later Display lock stage without a password;
- manual lock through the Power Menu and password unlock through `hyprlock`;
- real display-off, suspend, and resume;
- cleanup with no residual `hyprlock`, Zig Player process, or layer;
- no observed double-lock and exact cursor restoration;
- cold-start hypridle ownership and behavior.

These results validate the tested single-output paths; they do not claim the
remaining physical multi-monitor or every lock-at-suspend/Caffeine combination.

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
chain is validated. Real display-off, suspend/resume, manual lock, password
unlock, and automatic locking at the Screen saver and Display stages have
passed controlled manual testing. Physical multi-monitor acceptance and
untested combinations remain separate work.

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
- Develop the light/dark wallpaper selection system.
- Build the reserved Super+Space main menu and screenshot-to-clipboard
  workflow as separate features.
- Add local F9 push-to-talk dictation without introducing a hosted dependency.
- Design an update-safe customization/override layer rather than asking users
  to edit future managed defaults in place.

### PROVISIONAL

- Validate the external player's physical multi-output and suspend/resume
  behavior.
- Validate remaining lock-at-suspend and Caffeine lifecycle combinations
  without turning test timings into defaults.

### NOT IMPLEMENTED

- Shared bootstrap and optional archinstall integration
- Super+Space main menu
- Screenshot-to-clipboard workflow
- Local F9 push-to-talk dictation
