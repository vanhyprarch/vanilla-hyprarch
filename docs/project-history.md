# Project history

This is a maintainer-oriented milestone history, not a transcript. Commit hashes
refer to the `dock-prototype` branch.

## 2026-09-04: Minimal system and first shell

The development system began as a minimal Arch Linux installation. Commit
`8e4dd67` established the baseline vanilla Hyprland Lua configuration, and
`1142429` added the first working Quickshell configuration.

The initial shell quickly evolved into a configurable vertical dock
(`4ae5946`) and a rounded desktop frame (`75dd7fb`). Subsequent commits refined
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

Commit `64c586b` established the current described Hyprland binding structure.
Commit `937ac2a` added named Quickshell autostart and the shell IPC foundation.
The searchable shortcut viewer followed in `13ff6e6`, reading described active
bindings without executing them. `739b03f` refined its final layout.

The original ten numbered workspace shortcuts were reduced to five in
`37a922b`. Relative navigation and the scratchpad remained available.

## 2026-09-07: Suspend/resume lifecycle fix

An important failure appeared after suspend/resume: the Quickshell process and
IPC remained alive, but the dock and frame disappeared when output objects were
recreated. Restarting Quickshell was considered only as a workaround.

Commit `b7ec6b0` fixed the structure instead. Permanent per-monitor surfaces now
live under `Variants { model: Quickshell.screens }` and bind explicitly to each
delegate screen. Suspend/resume testing passed without a restart hook. This
global-controller/per-screen-UI split is now a preserved architectural rule.

## 2026-09-08: Vanilla HyprArch identity

Commit `3f5803f` migrated the personal Quickshell configuration, IPC targets,
theme state namespace, Hyprland autostart, and shortcut binding to the accepted
`vanhyprarch` namespace. The repository directory was subsequently renamed to
`~/Projects/vanilla-hyprarch`, and the live Quickshell symlink was updated and
validated against the new root.

The public identity is now Vanilla HyprArch, the future GitHub slug is
`vanilla-hyprarch`, and tracked project configuration contains no personal
namespace.

## Screensaver lifecycle and Power & Idle backend

The Ly `colormix` direction advanced from exploration to an isolated native
renderer presented by fullscreen Foot. The renderer, owned-process controller,
input dismissal, and cursor lifecycle passed manual testing while the overall
screensaver decision remained Provisional.

A Hyprland v0.56.2 false resume on fullscreen window mapping invalidated the
original single-listener approach. Phase 2B validated a two-listener design:
the inhibitor-aware listener starts the saver, while an input-only listener
arms one second earlier and owns genuine-input dismissal.

The subsequent Power & Idle backend implemented strict persistent preferences,
runtime-only Caffeine state, ordered-stage and lock-point validation, generated
hypridle configuration, and transactional restart/rollback. Migration defaults
remain zero listeners. The Quickshell panel is the next phase and was not part
of the backend implementation.

## Architecturally relevant abandoned approaches

- Ten numbered workspace shortcuts were superseded by five.
- Hibernate was removed from the supported power UX.
- Shell-driven `nmcli` polling was superseded by native Quickshell networking.
- Restarting Quickshell after resume was rejected once screen lifecycle was
  fixed structurally.
- A parallel JSON representation of hypridle settings was rejected. A strict
  project preference file is the durable source, and the hypridle fragment is
  generated from it.
- A separate lock timeout and multiple independent lock toggles were superseded
  by one selectable lock-owning idle stage.
- Inferring Lua-backed binding commands from opaque `hyprctl -j binds` arguments
  was rejected; runtime description and deployed source must be verified
  separately.
