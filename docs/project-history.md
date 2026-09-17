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
References to Caelestia in that history describe visual inspiration only; no
Caelestia code or assets were copied.

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

The Omarchy comparison in the binding milestone describes keyboard/UX
inspiration only; no Omarchy code or assets were copied.

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

The later unified graphical-session PATH prepended `$HOME/.local/bin` exactly
once and passed a full logout/login test in Foot and Quickshell. The public
screenshot command resolved by name and its workflow passed runtime testing;
hypridle continued to operate, with the old wrapper visibly duplicating the
same PATH entry. That evidence allowed startup to return to direct
`/usr/bin/hypridle -v` and IdleController to use `vanhyprarch-idle` by name,
while retaining the backend's captured-daemon-PATH restart and rollback
transaction.

Later controlled tests validated manual lock and password unlock, automatic
lock at both the Screen saver and Display stages, dismissal before a later
Display lock without a password, and cleanup without residual lock/player
state or a double-lock. The current scope and remaining combinations are kept
in `current-state.md`.

## 2026-09-17: Typed Super+Space actions

Super+Space first shipped Apps, Install, and Power using one global controller,
one presentation per screen, native desktop entries, and typed action metadata.
Install retained yay's complete interactive workflow without turning search
text into shell syntax.

Remove Package then added a transient installed-package catalog read directly
from pacman's local database on every section entry. Search remains in-process,
and only the exact stored package object can launch the deliberate clean
uninstall command `yay -Rns -- <package>`. Pacman retains final
transaction review and confirmation. Remove Application remains absent because
a desktop entry is not sufficient package-ownership evidence.

The initial Foot `--hold` integration preserved output but left no interactive
process after yay exited. Install and Remove now share one Python terminal
operation helper: it keeps yay attached to the terminal, retains the final
output, and lets Enter close Foot cleanly after success, failure, or
cancellation.

The next Super+Space milestone added Update with exactly System and Flatpak.
Both are fixed typed actions using the same terminal helper: System runs the
full interactive `yay -Syu` repository/AUR workflow, and Flatpak runs the
interactive `flatpak update` application/runtime workflow. Entering the section
does not execute either action. Everything and Vanilla HyprArch self-update are
deliberately absent.

Flatpak simultaneously became an unpinned required official package, with the
system Flathub remote as required bootstrap state. A reusable bootstrap
component leaves an existing correct remote untouched, creates a missing remote
with `--if-not-exists`, and fails closed on a conflicting URL without modifying
user remotes or installing applications.

## 2026-09-17: Screenshot capture

Print Screen gained one project-owned Python workflow using official `grim`,
`slurp`, and `wl-clipboard` packages. Hyprland monitor and client JSON supplies
optional smart rectangles without adding `jq`: dragging remains unrestricted,
visible windows can be selected by their logical rectangle, and wallpaper,
bar, or gap clicks can resolve to the containing monitor. Invalid smart-target
state falls back to ordinary region selection.

Successful captures are validated as PNG, atomically published under
`Pictures/Screenshots` with collision-safe names, and copied explicitly as
`image/png`. Cancellation changes neither screenshots nor clipboard state, and
clipboard failure preserves the saved image. The deliberately small first
milestone has no screen freeze, editor, notifications, temporary picker
keybindings, or Quickshell image processing.

The graphical session now prepends `$HOME/.local/bin` exactly once before
starting its children. This establishes the canonical command location needed
by the name-based Print Screen binding. Existing Power & Idle PATH safeguards
remain pending a separate cold-start cleanup and validation pass.

## 2026-09-17: Optional local push-to-talk dictation

Vanilla HyprArch gained a deliberately separate dictation component built on
the signed upstream Voxtype 1.0.1 CPU AVX2 executable. The component verifies a
pinned binary digest, detached signature, exact signing fingerprint and
version, delegates resumable `small.en` transport to Voxtype, then independently
verifies the model before publishing its marker. `gnupg` and `wtype` remain
optional official-package deltas; Voxtype is not sourced from the AUR.

The first milestone is English-only and CPU-only. A fixed non-enabled systemd
user service owns the daemon after Hyprland conditionally starts it. F9 press
starts recording and F9 release stops, transcribes, and types. Voxtype's evdev
hotkey, input-group access, GPU setup, ydotool, clipboard fallback, OSD,
notifications, and Quickshell UI are absent. The initial removal policy kept
user configuration and the large downloaded model. That policy was later
superseded by Local Dictation's clean-uninstall contract: explicit Uninstall
now removes Voxtype configuration and every downloaded model.

Live validation then confirmed the verified installer and model, short and
longer English dictation through `wtype`, approximately 1–2 second short-input
latency, audible `default` feedback at volume `1.0`, and a cold logout/login
with both F9 bindings, automatic service startup, and exactly one daemon.

## 2026-09-17: Additional system components and managed dictation settings

SuperSpace gained `Additional system components` between Update and Power,
with Local Dictation as its first explicit catalog entry. A public
`vanhyprarch-dictation` backend now owns versioned status/catalog JSON and all
installation, configuration, model-integrity, service, and rollback
transactions; it remains available after Voxtype is uninstalled.

The CPU-only settings milestone exposes ten manifest-pinned models, a curated
13-language catalog, explicit/automatic/two-or-three-language detection for
multilingual models, and bounded recording limits of 30, 60, 120, or 300
seconds. English-only models force English. The public default changed to a
120-second maximum while remaining `small.en`, English, CPU AVX2. Settings
preserve unrelated manual configuration while the component is installed, and
unused models remain cached until explicitly removed or the component is
uninstalled. Uninstall now deletes the complete Voxtype config and data roots;
the Vanilla manager remains available for a fresh reinstall. Vulkan selection
and Radeon 680M performance validation were deferred to the next milestone.

Fresh-install validation then confirmed destructive removal and a clean
default reinstall, while exposing that installation left the service inactive.
The manager now starts and health-validates the non-enabled service before
publishing success. SuperSpace reloads Hyprland only after successful Install
or Uninstall completion, immediately synchronizing F9 bindings with the marker.

A following live fresh install exposed a stable-1.0.1 setup side effect: model
download created upstream's `base.en`/60-second default config before Vanilla
could publish its `small.en` template, so the daemon requested a model that had
not been downloaded. Setup now receives a private temporary `XDG_CONFIG_HOME`
while retaining the final model data root. Fresh rollback also validates and
removes complete transaction-created config, data, and safely stopped runtime
trees instead of requiring a new config directory to be empty.

## 2026-09-17: Vulkan backend foundation and diagnostic gate

The dictation manager gained a reviewed two-artifact Voxtype 1.0.1 manifest,
component-owned verified CPU/Vulkan cache, exact-digest acceleration identity,
official Arch Vulkan prerequisite detection, and transactional CLI switching
with executable/config/service rollback. Schema version 2 reports Vulkan
hardware capability and non-authoritative runtime evidence from the daemon's
executable, mapped loader/vendor ICD, and open DRM render node.

CPU remains the public default. SuperSpace can display a manually active
Vulkan artifact but cannot select it. Radeon 680M inference, persistence of the
reported `/proc` evidence, latency, and memory behavior must pass controlled
live validation before Vulkan becomes a user-facing choice; no performance
recommendation is recorded yet.

## 2026-09-17: Explicit Vulkan acceleration validated and enabled

Repeated Radeon 680M tests validated signed CPU-to-Vulkan and Vulkan-to-CPU
transactions, verified-cache reuse, retained AMD loader/ICD/render-node
evidence, and correct real F9 inference. SuperSpace now offers CPU and Vulkan
GPU as explicit acceleration choices while keeping CPU as the Vanilla default
and providing no Auto mode. Vulkan health promotes common executable, loader,
and vendor-ICD evidence to a transaction requirement; AMD and Intel also
require the selected DRM render node. NVIDIA remains portable by not treating
the DRM fd as universal before a reviewed NVIDIA-specific rule exists. One
`small.en` Radeon 680M test observed about 0.3 seconds perceived post-release
latency; this is a machine-specific observation, not a general recommendation.
Subsequent SuperSpace tests also validated constrained English/Italian
dictation with the multilingual `small` and `large-v3-turbo` models on Vulkan.
Both languages worked without profile changes; the larger model delivered
excellent observed accuracy and competitive latency while keeping the desktop
responsive. These personal validation results do not change the tracked
`small.en`/English/CPU/120-second public default.

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
