# Project history

This is a maintainer-oriented milestone history, not a transcript. Commit hashes
refer to the `dock-prototype` branch.

## 2026-09-04: Minimal system and first shell

The development system began as a minimal Arch Linux installation. Commit
`b0938c1` established the baseline vanilla Hyprland Lua configuration, and
`0f0b00b` added the first working Quickshell configuration.

The initial shell quickly evolved into a configurable vertical dock
(`e9ab956`) and a rounded desktop frame (`a087506`). Subsequent commits refined
the shell palette, dock/frame geometry, layered inner shadow, and vector logo.

## 2026-09-06: Dock becomes a working desktop shell

The dock gained its core interactive features:

- power menu;
- clock and calendar;
- workspace switcher;
- configurable application launchers;
- running-workspace indicators and launcher context actions;
- persistent drag reordering;
- native system tray.

The extra strip of chrome once placed beside the dock was abandoned because it
made the left edge too wide. The frame and dock instead converged on one shared
corner-radius model.

## 2026-09-07: Native controls and centralized presentation

Monitor controls added DDC/CI brightness and scale presets. Theme colors moved
into one shared component, followed by persistent light/dark shell state and a
Papirus-based icon policy.

Audio moved to Quickshell's native PipeWire integration, including input/output
controls and device selection. Networking moved to `Quickshell.Networking`,
first for status and toggling, then for Wi-Fi discovery, connection,
authentication retry, known-network handling, and forget operations. An
`nmcli`-driven network core was rejected in favor of native state and signals.

## 2026-09-07: Bindings, IPC, and shortcut viewer

Commit `259e65f` established the current described Hyprland binding structure.
Commit `a4dcd2f` added named Quickshell autostart and the shell IPC foundation.
The searchable shortcut viewer followed in `39e384a`, reading described active
bindings without executing them. `4993907` refined its final layout.

The original ten numbered workspace shortcuts were reduced to five in
`62c8f3d`. Relative navigation and the scratchpad remained available.

## 2026-09-07: Suspend/resume lifecycle fix

An important failure appeared after suspend/resume: the Quickshell process and
IPC remained alive, but the dock and frame disappeared when output objects were
recreated. Restarting Quickshell was considered only as a workaround.

Commit `ba8b65f` fixed the structure instead. Permanent per-monitor surfaces now
live under `Variants { model: Quickshell.screens }` and bind explicitly to each
delegate screen. Suspend/resume testing passed without a restart hook. This
global-controller/per-screen-UI split is now a preserved architectural rule.

## 2026-09-08: Vanilla HyprArch identity

Commit `44aec1f` migrated the prototype Quickshell configuration from the
historical `vanhyprarch-shell` namespace, along with its IPC targets, theme
state, Hyprland autostart, and shortcut binding, to the accepted `vanhyprarch`
namespace. The repository directory was subsequently renamed to
`~/Projects/vanilla-hyprarch`, and the live Quickshell symlink was updated and
validated against the new root.

The public identity is now Vanilla HyprArch, the future GitHub slug is
`vanilla-hyprarch`, and tracked project configuration contains no personal
namespace.

## Screensaver lifecycle and Power & Idle backend

The Ly `colormix` direction first advanced through a repository-local C
renderer presented by fullscreen Foot. Mapping that xdg-toplevel exposed a
Hyprland 0.56.2 inhibitor re-evaluation that reset pending idle clocks and
temporarily required a split dismissal listener.

The subsequent Power & Idle backend implemented strict persistent preferences,
runtime-only Caffeine state, ordered-stage and lock-point validation, generated
hypridle configuration, and transactional restart/rollback. Migration defaults
remain zero listeners. The later Quickshell panel and its passive synchronization
behavior passed manual visual review.

A separate Quickshell layer-shell renderer proved that native layer surfaces
avoid that reset, but duplicated presentation code inside this repository. It
was superseded by the independently released GPL-2.0-only Vanilla HyprArch Zig
Player. Release v0.1.0 established the native boundary and exposed first-input
leakage. Release v0.1.1 fixed that through native layer-shell input routing. A
direct real-player test retained the later listener deadline, while keyboard,
click, and scroll tests confirmed that input did not reach the underlying Foot
instance. This permitted removal of the temporary S-1 workaround without
adding an input workaround to Vanilla HyprArch.

The final production-chain validation started ColorMix through hypridle and the
project controller at +10.034 seconds, retained the harmless +20.036-second
deadline, and dismissed at +23.291 seconds on genuine input without leaking the
first key. Cleanup restored the normal zero-listener daemon and left the main
Quickshell unchanged. Git history preserves the detailed experiments; the
current result is maintained in the [compatibility register](compatibility.md).

A subsequent real reboot exposed one cold-start mismatch: Hyprland was launching
bare `hypridle` without `$HOME/.local/bin` in its environment. Startup was
changed to construct that PATH and `exec hypridle -v`, preserving direct
Hyprland ownership. A second reboot then passed the normal Power & Idle UI apply
and the complete 2-minute screensaver / 5-minute display-off / 10-minute suspend
sequence with normal resume.

## Project maintenance contract

A concise root `AGENTS.md` now directs future coding agents to the appropriate
canonical documents and preserves operational invariants. The compatibility
register centralizes validated component versions, upstream evidence, local
mitigations, and explicit retest/removal conditions so workarounds do not
silently become permanent architecture.

## Architecturally relevant abandoned approaches

- Ten numbered workspace shortcuts were superseded by five.
- Hibernate was removed from the supported power UX.
- Shell-driven `nmcli` polling was superseded by native Quickshell networking.
- Restarting Quickshell after resume was rejected once screen lifecycle was
  fixed structurally.
- Fullscreen Foot was superseded as the screensaver presentation after its
  xdg-toplevel mapping was proven to rearm later inhibitor-aware idle clocks.
- The repository-local Quickshell/Canvas screensaver was superseded by the
  independent native Zig Player; Vanilla HyprArch now owns only installation,
  preferences, and lifecycle control.
- A parallel JSON representation of hypridle settings was rejected. A strict
  project preference file is the durable source, and the hypridle fragment is
  generated from it.
- A separate lock timeout and multiple independent lock toggles were superseded
  by one selectable lock-owning idle stage.
- Inferring Lua-backed binding commands from opaque `hyprctl -j binds` arguments
  was rejected; runtime description and deployed source must be verified
  separately.
