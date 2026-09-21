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

A later reproduced reboot exposed a separate Caffeine lifecycle defect. A
successful Caffeine ON transaction correctly used a runtime marker but also
persisted its zero-listener generated fragment under the user configuration
directory. Reboot removed the marker while the fragment survived, so the UI
reported Caffeine off even though the fresh hypridle had no automatic
screensaver, display, suspend, or associated lock actions. Manual ON then OFF
reconciled the daemon. Startup now invokes the backend's `session-start` path,
which forces Caffeine off, validates and atomically publishes the fragment from
durable preferences, explicitly closes its flock, and directly execs the
packaged hypridle. Deterministic tests cover the stale projection, all three
lock points, direct exec, manual transactions, and rollback.

The first controlled reboot of that lifecycle fix exposed a startup lookup
blocker before reconciliation could run: the interactive session PATH included
`$HOME/.local/bin`, but Hyprland's inherited `/proc` PATH did not, so its bare
`vanhyprarch-idle session-start` command never executed. The generated fragment
kept its old timestamp and no hypridle process existed. Startup now constructs
the installed backend path from the already validated `sessionHome` and invokes
`$HOME/.local/bin/vanhyprarch-idle session-start` without PATH lookup.

The second controlled reboot established that current `hl.exec_cmd` behavior
still places a transient `/bin/sh -c` between Hyprland and the backend. The
absolute user-local path resolved, but the backend correctly rejected the shell
as its immediate parent before publishing the fragment. The startup string now
begins with the shell builtin `exec`, replacing that transient shell in place
before backend ownership validation. The backend then replaces itself with
`/usr/bin/hypridle -v`, leaving Hyprland as the final daemon's direct parent and
no wrapper alive. Public commands remain under `$HOME/.local/bin`, and neither
session PATH policy nor the strict ownership checks changed. A separate live
parent probe proved that process chain. The third controlled reboot still
exited before fragment publication, isolating the remaining early-start
dependency: the `hyprland.start` callback can run before Hyprland has published
its runtime instance lock, so `hyprctl instances` can report no usable
instance. The startup-only ownership check now reads its real PPID from
`/proc`, requires the current user's exact
`/usr/bin/Hyprland`, and rechecks the parent's start time around executable and
UID validation. It uses no arbitrary delay and no global instance lookup;
later manual transactions keep the existing discovery path. Startup failures
overwrite a single runtime-only diagnostic line, which successful
reconciliation removes.

Final live acceptance then repeated the original failure scenario end to end.
Caffeine was enabled before reboot, its runtime marker contained `on`, and the
persistent generated fragment contained zero listeners. Immediately after the
new login, before Power & Idle was opened or Caffeine or any timeout was
touched, the marker and runtime error record were absent and the fragment had
been republished as Caffeine off with the durable 120-second screensaver,
300-second display/lock, and 600-second suspend listeners. Backend status
agreed with that state and reported three effective listeners. The single
`/usr/bin/hypridle -v` process had PID 762 and direct Hyprland parent PID 713;
both executables resolved to their packaged paths, while `hypridle.service`
remained disabled and inactive. Most importantly, the screensaver started at
120 seconds without opening the panel or applying any transaction. This live
reboot-with-Caffeine-ON result resolves the original security-relevant
lifecycle bug.

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

## 2026-09-17: Consistent scrolling and circular list navigation

Qt Quick's native Flickable wheel deceleration is now set to `10000` at shell
process start, applying one consistent tuning to the six project-owned vertical
lists while leaving input-device handling to Qt. A thin, project-owned
persistent right-side thumb makes overflow and position visible without adding
scrollbar interaction or changing row width as filtering crosses the overflow
threshold. Existing Up/Down selection in Super+Space and Shortcuts is circular,
skips disabled entries, and keeps the wrapped row visible; Shortcuts paging
remains clamped.

## 2026-09-18: Deployment ownership foundation

The first distribution-architecture milestone separated the tracked Hyprland
configuration into a small managed XDG-aware loader, portable managed core,
managed curated bindings, a create-once machine seed, and a header-only
user-owned override seed. Development-machine monitor and keyboard choices
were excluded from public managed content. Hyprland 0.56.2 source and
documentation established intentional absolute-path `require()` support and
required-file watch tracking.

The effective Power & Idle fragment left release ownership and is now
represented only as backend-generated state. A portable managed hyprlock
baseline, version-1 ownership manifest, Alpha compatibility contract, and
static ownership regression tests were added. No live migration or desktop
reload occurred; the Monitor panel remains unchanged for the controlled next
step.

## 2026-09-18: Controlled Hyprland ownership migration

The separately reviewed live migration created the machine and user-override
layers before changing the symlinked Quickshell source. The development
machine's active output and keyboard choices moved into its machine-owned file.
An isolated prospective tree passed Hyprland 0.56.2 verification before the
managed loader, core, and bindings were deployed as regular files.

One controlled reload preserved monitor and keyboard behavior with no config
errors. The Monitor panel scale writer moved from the old managed `dp1Scale`
declaration to the explicit output profile's narrow machine-owned
`vanhyprarchMonitorScale` field and now fails closed on unexpected structure.
The old root bindings file was removed only after its recovery copy and lack of
live references were verified. System Keyboard Synchronization and Monitor
Control & Safe Apply were recorded as future milestones and were not
implemented by this migration.

## Zig Screensaver optional-component repository milestone

The native player moved from an assumed baseline payload to the explicit Zig
Screensaver sibling of Local Dictation in Additional system components. The
baseline manager now owns pinned install, adoption, repair, reinstall,
uninstall, marker publication, runtime process identity, and cursor recovery.
Power & Idle gained authoritative capability projection and distinct
unexpected-damage versus deliberate-uninstall preference semantics.

The historical manual-start hazard was closed by rejecting plain `start`,
using explicit `start --idle` from generated hypridle configuration, and adding
a five-second bounded `test`. Exact process termination no longer depends on
successful cursor restoration; retained cursor state can be completed by a
later idempotent stop, including after unexpected player exit. This work was
implemented and tested in an isolated repository worktree. It did not adopt,
reload, reinstall, or otherwise change the current live desktop.

## 2026-09-19: Appearance foundation candidate

An isolated candidate replaced the dock button's private theme-file shell code
with one global Appearance authority. The new public manager owns a versioned
preference, standard host color-scheme publication and portal readback, one
remembered wallpaper per mode, strict XDG Pictures containment, and Hyprpaper
startup and per-output IPC. The accepted shell palettes did not change.

Exact installed portal and Hyprpaper versions were audited before design.
Deterministic tests use temporary homes and mocked GSettings, D-Bus, process,
and renderer boundaries. The candidate did not deploy, reload Quickshell,
change live GSettings, alter wallpaper, or touch user images. The visual picker,
Style menu, thumbnails, and shortcut remain the next milestone.

The product wallpaper convention was corrected before deployment to plural
`Pictures/Wallpapers/{Light,Dark}`. Eight reviewed original Wolkenstein images
became GPL-2.0-only managed distribution assets; pair 1 is the explicit default.
A hash receipt supports non-destructive, idempotent seeding while preserving
user-added and modified same-name files. The live source library was inspected
read-only and remained unchanged.

Controlled deployment then exposed two installed-version boundaries:
Hyprpaper 0.8.4 treats the empty monitor as a fallback behind a pre-existing
explicit DP-1 target, and Hyprland 0.56.2 requires one comma-delimited wallpaper
argument rather than separate argv fields. One authorized explicit DP-1 request
changed the live wallpaper without replacing the renderer process. A follow-up
isolated correction now discovers active monitors through JSON and addresses
each explicitly; human toggle verification remains paused until that correction
is deployed.

## 2026-09-19: Style / visual background picker candidate

An isolated `background-picker` candidate added `Style -> Choose background`
and the conflict-free `Super+Ctrl+Space` binding. Both reach one global picker
controller, while its per-screen surface reuses the centered usable-desktop
geometry and sole focus coordinator. No live QML, Hyprland binding, Appearance
mode, wallpaper, or user wallpaper directory was changed during development.

The existing Appearance manager remains authoritative. Its compatible
version-1 catalog gained natural filename ordering and additive filename, URI,
and selected metadata; QML performs no filesystem discovery or validation.
Browsing changes only the candidate. Explicit Enter or a second click applies
through `AppearanceController`, preserving independent Light/Dark selections
and all renderer reconciliation. Asynchronous original-image previews are
limited to nearby carousel entries, with no thumbnail pipeline.

Human functional verification approved the interaction model. The first
follow-up visual pass removed normal-state outer chrome and copy, enlarged and
responsively clamped the floating preview composition, and retained only the
card-attached `Applied` marker. A subsequent live Wayland review showed that
the earlier synthetic pointer-scroll assumption did not describe useful
runtime behavior, so the product contract became explicitly keyboard- and
click-driven rather than adding custom input handling. The final isolated
polish added symmetric distance-based scale, position, and z-order for two real
neighbors per side while preserving the approved current-card size. Live review
then removed translucent/animated tier changes, retained a fixed bounded image
decode through depth changes, and constrained the existing surface input mask
to painted cards so transparent space dismisses correctly. Controller,
Appearance, focus, apply, cancel, shortcut, and SuperSpace behavior remain
unchanged.

## 2026-09-19: Official Wallpaper Set v2 candidate

The official fresh-install starter artwork was replaced with eight original
project-owner 3840×2160 RGB PNGs: four Light and four Dark images. Exact
reviewed source bytes were mapped from numbered 01–04 pairs onto the unchanged
managed `Wolkenstein_1` through `Wolkenstein_4` filenames, preserving pair 1 as
the deterministic default. Asset hashes, validation fixtures, and provenance
documentation were updated without changing the deployment manifest.

The one-shot ownership boundary remains unchanged. Fresh installations receive
the v2 source set, while initialized users receive no additions, replacements,
or restorations. Development used temporary fixtures for both fresh and
initialized states; the live main checkout, Appearance state, and user-owned
wallpaper directories were not deployed or modified.

## 2026-09-20: System keyboard synchronization prototype

The accepted localed authority direction gained a repository-only Python/Gio
prototype. A static user service observes only graphical locale1 properties,
re-reads complete tuples, validates them through xkbcommon, and projects changed
state through one verified Hyprland Lua runtime transaction with one-shot
rollback. GLib D-Bus, idle dispatch, name-owner tracking, and exact socket file
monitoring provide event-driven lifecycle recovery without polling.

Hyprland owns service startup and asks the existing daemon to reconcile after
config reload. The helper never owns active groups or per-device rules. Core,
event, reload, IPC recovery, service, ownership, and package behavior are
covered by deterministic tests. No helper or unit was deployed, and the live
Italian machine fallback remains in place pending controlled D-Bus, reload,
service-lifecycle, and cold-login validation.

Pre-live review found two lifecycle defects in the initial prototype. An
ordinary relevant event could treat the last-successful tuple as authoritative
and skip repairing unrelated Hyprland runtime drift. Relevant reports now
always compare a complete fresh localed tuple with current global compositor
state; console-only reports remain ignored. Review also found that Hyprland
0.56.2 asynchronously schedules its own user-manager environment import before
the start event, leaving a race with the service restart. The managed
`session-start` action now imports only the new signature/display variables and
waits for success before restarting the service. Deterministic tests cover
runtime drift, console isolation, coalescing, command ordering, import failure,
and old/new signature socket paths. The repository remains undeployed.

The first controlled live deployment reconciled correctly at startup, then
exposed a localed lifecycle defect: after repeated normal idle exits and new
unique owners, the GDBusProxy path observed ownership transitions but missed a
later graphical `PropertiesChanged` signal. The test stopped, restored the
Italian localed/Hyprland state, and left the service inactive. The follow-up
implementation removes proxy event ownership in favor of one system-bus
connection with a direct filtered subscription, current-owner sender
authentication, explicit owner-bracketed `GetAll`, and fresh reconciliation on
each appearance. It also replaces deprecated `GLib.unix_signal_add()` with
`GLibUnix.signal_add()`. Deterministic tests reproduce owner A disappearing,
owner B appearing, and owner B's later signal driving an actual newest-state
apply; stale-owner, activation, read-race, console-only, and warning-free
SIGHUP cases are covered. The corrected helper is not yet redeployed.

## 2026-09-20: Keyboard synchronization and session lifecycle closure

The corrected direct D-Bus implementation was deployed and passed graphical
Italian-to-US-to-Italian changes, console-only isolation, localed owner
reincarnation, config-reload reconciliation, service restart, and a cold Ly
login. Runtime drift was always compared against fresh authoritative state, and
the new daemon inherited the current compositor signature and exact IPC path.

The supporting session lifecycle work also passed repeated real logouts.
Linux parent-death signaling removed each old Bluetooth pairing helper with its
Quickshell parent and allowed the old logind scope to close. Vanilla's direct
PolicyKit helper stopped the official package service before compositor loss,
published the next session environment, skipped `reset-failed` for an unloaded
non-failed unit, and started exactly one healthy official agent without a
restart storm. Caffeine remained same-session runtime state and reset OFF on
fresh login. The package-owned PolicyKit unit was never replaced or edited.

After those gates passed, the private transitional Italian machine block was
removed. Both a controlled config reload and the final no-fallback cold login
observed Hyprland's built-in `us` state before keyboard synchronization
restored localed's `it / pc105 / "" / terminate:ctrl_alt_bksp` tuple. The
final startup used one validation/apply/readback cycle, completed about 123 ms
after IPC availability, and passed immediate human Italian typing. No global
machine or override fallback remains. The repeatable Aquamarine 0.15.1
teardown SIGSEGV remains an upstream compatibility record; it did not prevent
logout or session closure.

## 2026-09-20: Shortcut availability architecture

The shortcut coverage review preserved the original binding ownership instead
of creating a QML catalog. `bindings.lua` now carries optional capability
metadata in the same described binding that defines the real shortcut, and
Super+K continues to ingest only active `hyprctl -j binds` output. The first
consumer is existing F9 hold-to-dictate: its real binding remains marker-gated,
while authoritative component health supplies an additional display guard.

The versioned metadata transport uses default-ignorable Unicode tag characters
after unchanged visible description text. Lua, JSON, QML parsing, legacy text
width, malformed data, unknown versions, category ordering, search composition,
and stable selection behavior gained deterministic coverage. Manual/on-demand
Screensaver invocation was explicitly rejected; the Zig component remains part
of automatic Power & Idle behavior only.

Phase 1 also added actual described System bindings for direct Lock and
Caffeine toggle. Lock reaches the existing shared `PowerActions` implementation
through a narrow named IPC method. Caffeine gained one atomic backend toggle,
so its state decision occurs under the same lock and rollback transaction as
marker and generated-fragment changes; the established fresh-session OFF
contract and durable preferences remain unchanged.

## 2026-09-20: Caffeine confirmed-state synchronization

The first UI synchronization candidate removed optimistic Caffeine presentation
and added bounded authoritative refresh coalescing. Controlled live measurement
proved the backend had already committed coherent ON state about 312 ms after
fragment publication while the dock remained stale; opening Power & Idle fixed
the icon only because panel open requested status explicitly. Two later live
checks found no fragment or parent-directory inotify registration even after a
healthy stable same-PID Quickshell load, so `FileView` was rejected as this
feature's invalidation transport.

The replacement uses the existing Quickshell IPC architecture. Only after a
successful Caffeine transaction has validated its replacement daemon and
released the backend lock does it issue one bounded, nonfatal, state-free
`vanhyprarch.idle refresh()` call. An eager root handler asks the single global
controller to read authoritative backend status. Deterministic tests cover IPC
absence, errors and timeout, eager registration before UI interaction,
same-process reload, rollback suppression, confirmed-only presentation, and
coalescing. Corrected controlled live timing remains pending.

## 2026-09-21: Monitor Safe Apply Phase B1 backend foundation

An isolated repository-only milestone added `vanhyprarch-monitor` as the sole
authority for temporary display transactions and a static, bounded systemd
user service with `ExecStopPost` recovery. The strict runtime journal binds a
transaction to one compositor process and physical connector identity, stores
the complete protected monitor snapshot plus exact machine/override recovery
bytes, and publishes only a small versioned local control protocol.

Mode and scale are the only v1 editable fields. Apply success requires fresh
full-topology readback; normal rollback sends a connector-specific
`hl.monitor()` restoring those fields and verifies readback instead of reloading
all Hyprland configuration. Deterministic fixtures cover wrong readback,
protected drift, hotplug, process and physical-identity replacement, timeout,
crash recovery, strict journal/locking, and byte-preserving persistence races.
Production persistence remains deliberately disabled, no UI was changed, and
no live deployment or monitor mutation occurred. The catch-all-only fresh
install still requires a safe explicit-profile materialization design before
Alpha release.

## 2026-09-21: Monitor transaction policy realignment

The schema-v2 engine subsequently passed controlled no-op, timeout, explicit
revert, supervisor-death recovery, and a visible temporary Scale 1.25-to-1.50
test. That Scale test was deliberately the lower-risk vehicle for proving the
rollback engine and was not the intended final interaction.

The final policy assigns the confirmation deadline only to Mode and bitdepth;
Scale now follows one immediate runtime-readback-persistence transaction with
technical rollback and no human confirmation. Schema v3 separates those
candidate types, verifies bitdepth through effective DRM format while
preserving color intent, and shares the hardened persistence and recovery
machinery. Text Size and DDC/CI Brightness remain separate. This policy-aligned
generation is repository-only pending separate schema deployment and live
acceptance.

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
- Watching the generated Caffeine fragment with Quickshell `FileView` was
  rejected after repeated live instances had no target or parent watch despite
  healthy configuration loads; backend-completion IPC now carries invalidation
  only, while status remains authoritative.
