# Current project state

Snapshot date: 2026-09-21.

This document distinguishes deployed behavior from accepted future work and
directions that still require validation.

Validated upstream-version behavior and workaround removal conditions are
tracked in the [compatibility register](compatibility.md).

## Repository and runtime identity — IMPLEMENTED

- Public name: **Vanilla HyprArch**
- Repository: `~/Projects/vanilla-hyprarch`
- Development branch: `main`
- Technical namespace and named Quickshell config: `vanhyprarch`
- Hyprland: 0.56.2 (`hyprland` package 0.56.2-3)
- Quickshell: 0.3.1 (`quickshell` package 0.3.1-1)
- Flatpak: required unpinned official package; locally validated with 1.18.2

At inspection time exactly one Quickshell instance was registered, launched
from the `vanhyprarch` named configuration.

## Configuration paths — IMPLEMENTED

Repository-managed sources:

- `assets/wallpapers/`
- `home/.config/hypr/hyprland.lua`
- `home/.config/hypr/vanhyprarch/core.lua`
- `home/.config/hypr/vanhyprarch/bindings.lua`
- `home/.config/hypr/hypridle.conf`
- `home/.config/hypr/hyprpaper.conf`
- `home/.config/hypr/hyprlock.conf`
- `home/.config/systemd/user/vanhyprarch-keyboard-sync.service`
- `home/.config/systemd/user/vanhyprarch-monitor-safe-apply.service`
- `home/.config/quickshell/vanhyprarch/`
- `bin/vanhyprarch-keyboard-sync`
- `bin/vanhyprarch-monitor`
- `install/configure-flatpak`
- `install/install-zig-player`
- `install/zig-screensaver/`
- `install/vanhyprarch-zig-player.conf`
- `install/dictation/`

Create-once sources:

- `seeds/home/.config/vanhyprarch/machine/hyprland.lua`
- `seeds/home/.config/vanhyprarch/overrides/hyprland.lua`

`deployment/ownership-v1.toml` records the first machine-readable ownership
contract. The Power & Idle fragment is no longer release-owned source; it is a
mode-0600 generated projection with no manifest `source`.

Live paths:

- `~/.config/hypr/hyprland.lua`
- `~/.config/hypr/vanhyprarch/core.lua`
- `~/.config/hypr/vanhyprarch/bindings.lua`
- `~/.config/vanhyprarch/machine/hyprland.lua`
- `~/.config/vanhyprarch/overrides/hyprland.lua`
- `~/.config/hypr/hypridle.conf`
- `~/.config/hypr/hyprpaper.conf`
- `~/.config/hypr/vanhyprarch-idle.conf`
- `~/.config/quickshell/vanhyprarch`

The live Quickshell path is a symlink to:

`$HOME/Projects/vanilla-hyprarch/home/.config/quickshell/vanhyprarch`

The Print Screen binding and graphical-session PATH policy were deployed and
validated after a full logout/login. New Foot and Quickshell processes both
received `$HOME/.local/bin` first, and the name-based screenshot command
resolved successfully.

The tracked Hyprland configuration is now a small managed loader followed by a
portable managed core, managed bindings, create-once machine configuration,
and a user-owned customization override. It contains no development-machine
connector, mode, scale, bit-depth, color-management, keyboard-layout, or
device rule. The loader resolves XDG configuration paths and uses four ordered
absolute `require()` calls.

The controlled live migration now runs the managed loader, core, and bindings
as regular files. Its machine-owned file preserves the development machine's
explicit `DP-1` profile but contains no global XKB preference. The user
override remains the exact header-only seed. The old root
`~/.config/hypr/bindings.lua` was removed only after validation and remains in
the migration recovery material.

The deployed Monitor UI no longer edits machine configuration directly.
Each per-screen panel maps its own `ShellScreen` through
`Hyprland.monitorFor(screen)` and sends display operations to the global
Monitor controller. The controller consumes the backend's normalized read-only
`inspect` projection and reconciles transaction status; it does not duplicate
Hyprland monitor parsing or claim optimistic display state.

A deliberately authored portable managed `hyprlock.conf` baseline now exists
in the repository. It was not copied from the live development configuration
and has not been deployed. A portable managed `hyprpaper.conf` now contains
only renderer policy; wallpaper preference belongs to Appearance. Neither file
has been deployed by this isolated milestone.

Mutable shell state is stored outside Git. Appearance uses
`${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/appearance.json`; the former
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/theme-mode` is read only as
a first-run migration input. Appearance asset provenance uses
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/appearance-assets.json` and
is not a second preference. Launcher order uses
`Quickshell.statePath("launchers.json")` under Quickshell's shell-ID state.
Global text size uses the versioned preference documented in
[Global text size](text-size.md); a missing preference means the 12-pixel
default without creating state.

## Session startup — IMPLEMENTED

The graphical session remains the direct
`Ly -> /usr/bin/start-hyprland -> Hyprland` path. UWSM is not part of the
Vanilla HyprArch architecture.

Before registering its startup children, the managed portable core reads
`HOME` and the inherited `PATH`, validates that `HOME` is non-empty, removes
any existing `$HOME/.local/bin` entries, and prepends exactly one such entry
while preserving every other entry and its order. Public session commands use
stable `vanhyprarch-*` names from that directory. A full logout/login validated
this propagated environment in new Foot and Quickshell processes. It does not
imply that Hyprland's own inherited `/proc` environment was retroactively
changed.

Hyprland starts these processes on `hyprland.start`:

1. `exec $HOME/.local/bin/vanhyprarch-appearance renderer-start`, which
   preserves one direct session-owned Hyprpaper process
2. `exec $HOME/.local/bin/vanhyprarch-polkit-session session-start`, which
   binds itself to the current instance directory, waits event-driven for the
   exact current Hyprland and Wayland sockets when necessary, publishes the
   current display environment, clears an inherited service failure only when
   one exists, and restarts one graphical PolicyKit agent
3. `exec $HOME/.local/bin/vanhyprarch-keyboard-sync session-start`, which
   imports only the new compositor's signature and display variables into the
   user manager before restarting the static service; the unit then performs
   one localed-to-Hyprland startup reconciliation and observes graphical XKB
   changes
4. `exec $HOME/.local/bin/vanhyprarch-idle session-start`, constructed from the
   validated `sessionHome`; the leading shell builtin replaces Hyprland's
   transient executor shell before the backend validates its parent, and the
   backend directly execs `/usr/bin/hypridle -v` after reconciliation
5. `qs -n -c vanhyprarch`
6. `vanhyprarch-voxtype.service`, only when the exact optional-component
   marker is installed

The official `hyprpolkitagent` package provides graphical PolicyKit
authentication for GUI applications that require privileged authorization.
Its packaged user service is not enabled as a separate login-time startup
owner. Vanilla's direct session helper owns ordered start and graceful stop,
while a managed drop-in conditions every package-service start on the current
compositor and slows failure recovery to one second. A fresh session resets
any old `start-limit-hit` before restart. An inactive package unit may already
have been garbage-collected by the user manager, so the helper first tests
whether it is actually failed and does not issue the non-idempotent named
`reset-failed` operation for an unloaded healthy unit. Each startup stage emits
concise durable journal evidence. The common Power logout path stops the
service synchronously before it execs `hyprshutdown`; a compositor crash instead
reaches one conditioned package restart and becomes inactive when no live
compositor remains. The packaged unit itself is not replaced.

Repeated controlled cold logout/login tests validated that the old PolicyKit
agent stops before compositor loss, no compositor-less restart storm occurs,
and one new official agent starts automatically with the new session
environment. The same tests proved that the Bluetooth pairing helper's parent
death binding removes the old helper and BlueZ client, the old logind scope
closes, and one helper returns as a child of the new Quickshell process.

The earlier shell wrapper was introduced after a real reboot showed that bare
hypridle lacked the public-command path. The unified session PATH remains
validated for normal launched session applications, including Quickshell,
which resolves `vanhyprarch-idle` by name. A later controlled reboot showed
that Hyprland's own inherited `/proc` environment still lacked
`$HOME/.local/bin`; the security-critical idle autostart therefore uses the
`sessionHome`-derived absolute public-command path without a per-process PATH
override. Current `hl.exec_cmd` execution passes the string through a transient
`/bin/sh -c`; the startup string intentionally begins with the shell builtin
`exec`, so that shell is replaced by the backend before its strict direct-parent
validation. The startup backend reconciles Caffeine OFF and then replaces
itself with the fixed packaged binary; no wrapper remains. The start callback
can precede publication of Hyprland's runtime instance lock, so this startup-only
path validates its actual parent through `/proc` instead of calling
`hyprctl instances`: PPID, exact `/usr/bin/Hyprland` executable, current-user
ownership, and a stable parent start time are required. Manual transactions
retain their later-session instance discovery, daemon-PATH capture, validation,
replacement, and rollback behavior. Startup failures leave one overwritten
mode-0600 line in the session-runtime `session-start-error.log`; a successful
reconciliation removes it.

`-n` prevents a duplicate instance of the named Quickshell configuration.
Managed bindings are loaded through Hyprland's tracked absolute-path
`require()` mechanism. The controlled live migration removed the old root
`~/.config/hypr/bindings.lua` after the new configuration passed isolated and
runtime validation.

Hyprland's existing input configuration sets `numlock_by_default = true`, so
Num Lock is enabled by default when the graphical session starts.

## System Keyboard Synchronization — IMPLEMENTED AND LIVE VALIDATED

`systemd-localed` is the graphical XKB preference authority. The managed
`vanhyprarch-keyboard-sync` Python/Gio helper reads its complete
layout/model/variant/options tuple, preflights it with `xkbcli`, compares the
current global Hyprland tuple, and applies all four changed values through one
shell-free `hyprctl eval` / `hl.config()` transaction. It verifies exact
readback and makes one bounded attempt to restore the captured prior tuple on
failure. An empty localed layout or invalid tuple leaves Hyprland unchanged;
the helper never substitutes `us`.

Relevant `PropertiesChanged` notifications cause a fresh complete localed read
and a current global Hyprland read; runtime drift is repaired even when the
localed tuple equals the helper's last successful tuple. One long-lived system
bus connection provides direct signal subscription, current unique-owner
tracking, sender authentication, and explicit `GetAll`; no proxy cache or
proxy signal lifecycle remains. Requests are serialized/coalesced through the
GLib event loop. Locale and vconsole-only reports are ignored without a
graphical state read. Every new localed owner forces reconciliation, while
ordinary idle disappearance preserves runtime state. An exact file monitor
reconciles when the Hyprland command socket appears or reappears without a
sleep, timer, or polling loop.

The static user unit has no install target. On `hyprland.start`, a one-shot
helper running in the new compositor environment imports only
`HYPRLAND_INSTANCE_SIGNATURE`, `WAYLAND_DISPLAY`, and `DISPLAY` into the user
manager, waits for success, and then restarts the service. This closes the race
in Hyprland 0.56.2's asynchronous built-in activation-environment publication
and ensures every fresh compositor launched by a normal Ly login selects its
own IPC path. `XDG_RUNTIME_DIR` remains user-manager-owned. Vanilla does not
expose a clean user-requested same-login compositor restart; upstream launcher
crash/safe-mode recovery is not a release gate. `config.reloaded` only requests
`systemctl --user reload`; its `SIGHUP` handler re-reads both authorities and
applies only when runtime state actually differs. The helper does not inspect
devices, write per-device rules, or read/store/switch active groups. See
[System keyboard synchronization](system-keyboard-synchronization.md).

Controlled live validation covered graphical Italian-to-US-to-Italian localed
changes, console-only isolation, repeated localed owner reincarnation, config
reload reconciliation, service restart, and fresh Ly login. The original proxy
signal-delivery defect was reproduced, replaced by the direct owner-aware
connection design above, and verified against a later owner before migration
continued.

The transitional private Italian machine block was then removed. A controlled
reload and a final cold login both exposed Hyprland's built-in `us` state before
the service projected localed's
`it / pc105 / "" / terminate:ctrl_alt_bksp` tuple. On the final login,
validation, one runtime apply, and exact readback completed about 123 ms after
the IPC socket became available; immediate human Italian typing passed. This
is one-machine evidence, not a performance SLA. The live machine and user
override contain no hidden global XKB fallback.

## Optional local dictation — IMPLEMENTED AND VALIDATED

The repository contains one opt-in component under `install/dictation/`; its
official-package deltas are `gnupg` and `wtype` in
`packages/optional-dictation-official.txt`. Neither package nor Voxtype is in
the normal baseline or AUR manifest. An immutable manifest pins the official
Voxtype 1.0.1 x86_64 AVX2 CPU and Vulkan binaries. A dedicated GPG home,
detached signature, full primary fingerprint, size, SHA-256, and exact version
gate the component-owned versioned cache and atomic publication of the active
regular file at `$HOME/.local/bin/voxtype`.

The component asks Voxtype itself to download `small.en`, then independently
requires the pinned size and SHA-256 for
`$XDG_DATA_HOME/voxtype/models/ggml-small.en.bin`. Its default configuration
is English-only local Whisper, CPU-default, built-in hotkeys off, and `wtype` as
the sole output driver. Hyprland registers F9 press/release bindings and starts
the non-enabled `vanhyprarch-voxtype.service` only when the exact managed
component marker exists. No evdev listener, input-group access, automatic GPU
selection, Quickshell indicator, OSD, or notification is part of the milestone.

The optional installer completed on the development machine with the verified
Voxtype 1.0.1 binary and pinned `small.en` model. Short and longer English
dictation passed through `wtype`; short transcription latency was approximately
1–2 seconds with the CPU backend. The approved `default` feedback theme at
volume `1.0` remained audible during concurrent desktop audio. A full
logout/login registered both F9 bindings, started exactly one service-owned
Voxtype daemon automatically, and required no manual service start. See [Local
push-to-talk dictation](dictation.md) for the installation and validation
contract.

The tracked `bin/vanhyprarch-dictation` command is now the single management
backend for installation, removal, state reporting, reviewed model downloads,
and transactional CPU model/language/maximum-duration changes. Its versioned
JSON status and catalog remain available when Voxtype is absent. The public
default is still `small.en`, English, and CPU AVX2; the maximum recording time
is now 120 seconds. Ten model digests and the curated language catalog are
tracked. The schema-2 manager can switch exact CPU/Vulkan artifacts through
the CLI or SuperSpace with binary/config/service rollback. Status derives
acceleration only from the active digest and separately reports sysfs/package
and required vendor-aware `/proc` runtime evidence. CPU remains the public
default; Vulkan GPU is an explicit selection and is never activated
automatically.

The Radeon 680M development machine passed repeated CPU-to-Vulkan and
Vulkan-to-CPU transactions. The verified Vulkan daemon retained its executable,
loader, RADV ICD, and render-node evidence before and after real F9 inference.
One `small.en` utterance had approximately 0.3 seconds perceived post-release
latency versus the earlier approximate 1–2 second CPU observation on this one
machine; this is validation evidence, not a general performance guarantee.
The same Vulkan machine successfully ran one constrained English/Italian
`small` multilingual profile and then `large-v3-turbo` with English and
Italian. Real F9 dictation passed in both languages for both profiles; the
larger model showed excellent observed accuracy and punctuation with slightly
higher but still competitive latency while the desktop remained responsive.
Those are personal development-machine results. The public default remains
`small.en`, English, CPU, and 120 seconds.
An installation now reloads the user-unit catalog, starts the non-enabled
service, validates bounded daemon health, and publishes the component marker
only after success. Model download runs with an isolated temporary XDG config
root because stable Voxtype setup otherwise creates its own `base.en` default;
the tracked `small.en`/English/120-second template is published only after model
verification. SuperSpace reloads Hyprland once after successful Install
or Uninstall so the current session's F9 bindings immediately match the marker;
failed operations and settings Apply never request that reload.
Local Dictation's explicit Uninstall action stops the managed service and then
removes Voxtype, `$XDG_CONFIG_HOME/voxtype`, and `$XDG_DATA_HOME/voxtype`
completely. The Vanilla manager and immutable component resources remain, so
SuperSpace returns to a clean not-installed state and can offer a fresh install.

## Shell architecture — IMPLEMENTED

`ShellRoot` owns global state and controllers, including the single
`LauncherStore`, typed Install, Remove, Update, Additional system components,
and Power actions, and the Super+Space controller. A `Variants`
instance models `Quickshell.screens`; each delegate owns its per-screen
`Launchers` presentation, permanent dock, Super+Space and Shortcuts popup
presentations, and transparent popup-anchor surface. This screen lifecycle
structure is the validated fix for dock loss after suspend and resume.

Current IPC targets are:

- `vanhyprarch.shell`, exposing `ping()`
- `vanhyprarch.shortcuts`, exposing `open()`, `close()`, and `toggle()`
- `vanhyprarch.superSpace`, exposing `open()`, `close()`, and `toggle()`
- `vanhyprarch.backgroundPicker`, exposing `open()`, `close()`, and `toggle()`
- `vanhyprarch.power`, exposing `lock()`
- `vanhyprarch.idle`, exposing the state-free `refresh()` invalidation

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
- a compact capability-aware Power & Idle panel backed by the project
  controller: Caffeine, Turn off display, Suspend, and Automatic lock are baseline;
  Screensaver and Screen saver effect exist only with validated Zig
  Screensaver capability;
- one persistent Light/Dark Appearance mode coordinating the accepted shell
  palette, standard host preference, and remembered per-mode wallpaper;
- direct dock access to Super+Space from the logo and to the shortcut viewer
  from a system-sized `dialog-information` control;
- clock and calendar;
- lock, suspend, logout through `hyprshutdown`, reboot, and power-off actions;
- a keyboard-and-mouse Super+Space surface with Apps, Install, Remove, Update,
  Style, Additional system components, and Power sections, in-process search over
  `DesktopEntries.applications` and typed action metadata, and confirmation for
  logout, reboot, power off, and optional-component removal;
- a Local Dictation component page with reviewed model and maximum-recording
  selectors plus one unified Languages page: real Automatic detection or one
  to three reviewed manual languages, with no language-specific Done step;
- a searchable, read-only shortcut viewer populated from described Hyprland
  bindings. `bindings.lua` remains the shortcut-definition and display-metadata
  authority: versioned invisible description metadata can name an optional
  capability, and the viewer filters that row through the existing authoritative
  component controller without a QML shortcut catalog, marker check, or polling;
- consistent long-list navigation: Qt Quick's native Flickable wheel tuning is
  configured process-wide with `QT_QUICK_FLICKABLE_WHEEL_DECELERATION=10000`,
  scrollable views retain a thin project-owned persistent position indicator,
  and existing Up/Down selection in Super+Space and Shortcuts wraps circularly.
  Shortcuts Page Up/Page Down remain clamped. The wheel value is process-start
  configuration, so live validation requires a full Quickshell process restart;
  hot reload is insufficient.

Super+Space uses `DesktopEntries.applications` directly and launches through
the native `DesktopEntry.execute()` API. It has no project-owned application
catalog and starts no search subprocess. One global `PowerActions` controller
now supplies both Super+Space and the existing PowerMenu with the validated
commands and confirmation policy; the PowerMenu presentation is unchanged.
Install accepts package search terms only after the user enters its section
and explicitly activates the typed action. It closes Super+Space and launches
the installed yay 13.0.1 workflow visibly in Foot 1.28.0 with a direct argument
vector and an option boundary. One shared executable Python helper inherits the
terminal streams while yay runs, then reports completion and waits for Enter
before Foot closes; Foot itself does not use `--hold`. No result-ordering
option is supplied, so yay retains the user's configured or default ordering.
Empty searches are rejected, user text never enters a shell command, and yay
retains all interactive selection, review, authentication, cancellation, and
confirmation prompts. Install maintains no package catalog or yay-output
parser.
Remove refreshes a transient installed-package catalog by running
`/usr/bin/pacman -Q` whenever its section is entered. Package name and version
are parsed into in-memory objects and filtered without another subprocess. Only
an activated object from that catalog can start removal; search text is never
a removal target. Activation closes Super+Space and visibly starts
`/usr/bin/yay -Rns -- <selected-package>` through that same terminal helper and
a direct argument vector. The selected clean-uninstall policy removes the
target, recursively removes dependencies that become unnecessary according to
pacman, and does not retain `.pacsave` files. Yay/pacman still presents the
complete transaction and normal confirmation prompt; after completion or
cancellation, Enter closes the terminal. Remove Application is deliberately
absent because Quickshell's `DesktopEntry` does not expose enough source-path
provenance to prove package ownership safely.

Update contains the fixed typed actions System and Flatpak. Entering the
section only presents those actions. Explicit System activation starts
`/usr/bin/yay -Syu`; explicit Flatpak activation starts
`/usr/bin/flatpak update`. Both use direct argument vectors through the shared
Foot terminal-operation helper, preserve normal interactive prompts, and add
no forced ordering, noninteractive confirmation, database-force, downgrade,
or shell option. One startup-time executable check reports a missing required
Flatpak command in the panel and blocks that activation. There is no Everything
action and no Vanilla HyprArch self-update action.

Local Dictation Install, Apply, and Uninstall use a supervised form of that
terminal helper. A private runtime result carries the manager child's status,
and the supervisor remains alive until the real Foot process exits. Successful
Install and Uninstall then run exactly one direct `hyprctl reload` and refresh
component status only after reload completion; failures, Apply, Refresh, and
model removal never reload bindings.

The two Additional system components controllers perform one asynchronous
authoritative refresh when the shell initializes and retain that last-known
session state. Opening, closing, entering, or reopening the catalog and its
detail pages reads the cache and starts no manager command. Explicit Local
Dictation Refresh, Zig Check status, and every completed lifecycle operation
request authoritative state again; Local Dictation also refreshes its reviewed
catalog. Its Back and Esc navigation preserves the in-memory settings draft,
Apply Changes commits that complete draft, and Local Dictation Refresh discards
unapplied choices before rebuilding from authoritative status. Status updates
preserve the selected component or action by stable identity. Component-page
status and settings rows are normal non-interactive information, separated
from actions with the shared panel separator. Zig Screensaver's installed
actions are Check status and Uninstall; incomplete/error state offers Check
status, Repair, and manager-proven Clean up when safe. The technical reinstall
manager operation remains available without being promoted as a normal
user-facing action.

Flatpak is an unpinned required entry in the official package manifest. The
development machine has a correct system `flathub` remote. The reusable
`install/configure-flatpak` bootstrap component accepts that state without a
write, adds the system remote idempotently when absent, and fails closed rather
than changing a same-named remote with an unexpected URL. It never installs a
Flatpak application.

The Super+Space and Keyboard Shortcuts surfaces open centered in the focused
monitor's usable desktop region to the right of its persistent dock, as
independent per-screen layer surfaces. Dock-owned panels use monitor-bound
layer surfaces too, and one shell-level focus coordinator keeps a central
surface and the existing dock panel in the same Hyprland focus whitelist.
Their positions remain independent. Interaction and containment are separate
from that compositor whitelist: a click delivered to a dock panel dismisses a
visible central overlay without consuming the panel action, while a click on
non-actionable persistent-dock background dismisses both kinds of transient
surface. An owning dock control remains an explicit toggle, and opening a
different dock panel retains the existing one-panel replacement behavior.

The described binding set also exposes `Super+Ctrl+L` as **Lock system** and
`Super+Ctrl+I` as **Toggle Caffeine** in the System shortcut category. Lock
uses the shared `PowerActions` lock implementation through its named shell IPC
endpoint. Caffeine uses the backend's serialized atomic toggle; it does not
compose separate status and on/off calls.
An outside compositor clear dismisses every visible transient shell surface.
These application-level transitions are covered offscreen; native Wayland
delivery is recorded in the compatibility register. Hyprland 0.56.2 still
routes the first stationary same-icon re-click to the newly mapped dock-panel
surface before correcting native pointer focus back to the dock; Vanilla does
not synthesize recovery for that compositor-side limitation. Super+Space opens
through its shortcut, dock logo, or named IPC target, supports pointer
activation plus Up, Down, Enter, and Escape, and uses the shared panel, row,
theme, metric, and global text-size foundations. Its light rectangular
navigation cursor is distinct from the darker persistent-selection fill;
Keyboard Shortcuts uses the same navigation cursor. Static and offscreen checks
cover geometry, first-activation coexistence, focus/dismissal state, repeated
cycles, and named IPC ownership. Controlled live Wayland validation passed the
shared focus and dismissal behavior; the usable-desktop centering refinement
still requires its final visual check.

The desktop uses 5-pixel inner and 10-pixel outer Hyprland gaps with square
application windows. Network, Bluetooth, Audio, and Display use the centralized
square panel foundation, including a nine-pixel dock gap, complete opaque
three-pixel exterior outlines, and one-pixel internal separators. Other panels
retain their legacy visual treatment until their scheduled normalization.

PowerMenu may show a very brief oversized-text first frame when opening; QML
geometry, font-size, and scale measurements were correct from the first visible
event, the root cause is not proven, and the issue is currently non-blocking.

From bottom to top, the dock's lower status/control area is Power,
Clock/calendar, Info/Shortcuts, Theme, Power & Idle, Display, Audio, Network,
Bluetooth, and System tray.
Manual pointer and visual validation of the two new dock affordances remains
pending.

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
Normal component teardown sends SIGTERM and pipe closure remains a protocol
fallback. The helper also arms Linux `PR_SET_PDEATHSIG` before registering with
BlueZ and verifies that its original parent survived that operation. This
kernel-enforced final layer bounds the helper lifetime to its owning
Quickshell process even when the shell exits without running QML destruction.
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

## Appearance foundation — REPOSITORY IMPLEMENTED / LIVE ADOPTION PENDING

`bin/vanhyprarch-appearance` is the preference and reconciliation authority for
Light/Dark mode, the standard host color-scheme preference, and one remembered
wallpaper per mode. Its version-1 JSON preference is a mode-0600
`PERSISTENT_STATE_PREFERENCE`; wallpaper names are stored relative to the
matching XDG Pictures `Wallpapers/Light` or `Wallpapers/Dark` directory. The
global Quickshell `AppearanceController` owns shell projection and startup
reconciliation. Each per-screen Theme button calls only that controller and
has no persistence or private theme state. The accepted `Theme.qml` palettes
are unchanged.

The validated host write target is writable
`org.gnome.desktop.interface color-scheme`. The active GTK Settings portal
provider maps `prefer-dark` to `org.freedesktop.appearance/color-scheme` 1 and
`prefer-light` to 2 and emits the standardized change signal from the
GSettings notification. The backend reads the portal after every write and
reports mismatches. It does not write to the portal, alter `gtk-theme`, set Qt
style overrides, edit Firefox or other application configuration, or restart
applications.

Hyprpaper remains a required official package and is renderer only. Hyprland's
direct session startup now enters it through `vanhyprarch-appearance
renderer-start`; multiple exact executable identities fail closed. Normal
reconciliation discovers active output names from Hyprland JSON, applies one
fallback plus an explicit installed 0.8.4 `wallpaper` request to each current
output, rejects monitor-set races, and verifies every output through
`listactive`. The managed renderer config has IPC on, splash off, and no user
wallpaper. Missing or failed rendering does not block shell or host mode and is
represented in strict versioned status.

The managed Hyprland core explicitly disables its native logo/default
background while Appearance owns wallpaper presentation. A controlled runtime
test on Hyprland 0.56.2 proved that `misc.disable_hyprland_logo = true` removes
the packaged anime image that was briefly visible beneath Hyprpaper during a
target replacement. Four alternating Light/Dark transitions showed no foreign,
black, or blank frame. No Hyprpaper sequencing change is needed; the shell
palette continues to update immediately after external reconciliation.

Official Wallpaper Set v2 consists of eight reviewed original 3840×2160 RGB
Wolkenstein PNGs under `assets/wallpapers/`, retaining the established managed
filenames and pair-1 default. They ship as GPL-2.0-only managed distribution
content. Appearance copies them non-destructively only during a true first
wallpaper initialization and records completion in the private version-2
`appearance-assets.json` state. Existing initialized users do not receive the
replacement artwork; version-1 receipts migrate without directory writes.
Afterward the plural Light/Dark directories and all their contents are
user-owned: updates and reconciliation never add, replace, restore, or delete
wallpapers. Pair 1 is the explicit Light/Dark default for a fresh preference.
First-run migration
preserves a valid legacy shell theme value and adopts a uniform active
wallpaper already in its mode directory; otherwise both selections use the
seeded pair-1 defaults. Existing Appearance preferences are never replaced by
defaults. `catalog` returns the real current-mode directory in stable natural
filename order with additive entry metadata, and `set-wallpaper current`
remains the only picker apply boundary. See [Appearance foundation](appearance.md).

A controlled local deployment migrated legacy shell mode Light, created the
new preference and provenance files, and reconciled the host and portal. It
exposed a Hyprpaper 0.8.4 boundary: an empty-monitor fallback cannot replace an
adopted process's legacy explicit target, and Hyprland 0.56.2 requires monitor,
path, and fit mode in one comma-delimited argument. The explicit-output
correction was deployed locally without replacing the existing renderer.
Human Light/Dark verification then identified the native-background frame
described above; the isolated managed-policy correction follows the successful
runtime proof. The eight existing user files retained their hashes and mtimes.

## Style / visual background picker — REPOSITORY IMPLEMENTED / LIVE ADOPTION PENDING

Super+Space now places `Style` exactly between `Update` and `Additional system
components`; its only current row is `Choose background`. `Super+Ctrl+Space`
opens the same shell-global Background Picker controller through the named IPC
target. The complete managed and active binding inventories had no prior
`Super+Ctrl+Space` conflict.

One per-screen `CenteredOverlay` presentation follows the existing
`Variants { model: Quickshell.screens }` lifecycle and is centered in the
monitor area to the right of the persistent dock. It registers as another
central surface with the existing shell-global `OverlayFocusCoordinator`; no
focus grab was added. SuperSpace, Shortcuts, and the picker replace one another,
while dock-panel coexistence and outside dismissal retain their established
semantics.

The picker queries `vanhyprarch-appearance catalog current` on every open and
never discovers files in QML. It displays only the active mode, focuses that
mode's applied selection when present, and deterministically starts at the
first manager-ordered entry otherwise. An external mode change while the picker
remains open clears stale previews before requesting the other catalog. A dock
Light/Dark click retains the established dock-to-central dismissal boundary and
therefore closes the picker before changing mode. Empty and one-item catalogs
are safe; large catalogs instantiate lightweight delegates while activating
image sources only around the current item.

Previews are large, responsive, widescreen rectangular cards floating directly
over the desktop in a restrained depth-scaled carousel. The current card is
dominant; up to two real neighbors per side become progressively smaller,
further outward, and visually behind it. Every visible image remains fully
opaque; scale, position, overlap, and z-order alone communicate depth. The
transparent central surface retains focus and dismissal ownership but draws no
outer panel, title, filename, controls, instructions, or footer. Its input mask
matches the actual painted cards, so visually empty space remains outside the
picker. In normal operation `Applied` is the only label; concise loading, empty,
preview, and apply-error feedback remains available only for exceptional
states. Asynchronous original-image loads use one fixed bounded decode size,
`PreserveAspectCrop`, and distance-two source activation, retaining an already
loaded texture when its card changes tier.

Picker navigation is intentionally keyboard- and click-driven. Left/Right move
the candidate without applying, and a first click selects. Enter or a second
click on the current card applies through
`AppearanceController`. Success closes; failure leaves the picker and candidate
visible with a concise error; Escape and outside dismissal make no Appearance
or renderer request. Applied and navigation-current state remain visually
distinct.

## Screenshot workflow — IMPLEMENTED, RUNTIME VALIDATED

Print Screen invokes the project-owned `vanhyprarch-screenshot` Python helper
through the described Hyprland binding architecture. The helper uses fixed
argument vectors and no shell evaluation. It parses `hyprctl monitors -j` and
`clients -j` with the Python standard library, filters out hidden, unmapped,
and non-visible clients, removes duplicate rectangles, and supplies visible
window rectangles followed by monitor rectangles to unrestricted `slurp`.
Dragging therefore remains freeform, while a click can select a visible window
or the monitor behind wallpaper, gaps, and layer-shell bars. Invalid or
unavailable Hyprland JSON degrades to ordinary unrestricted region selection.

The canonical deployment target for the tracked
`bin/vanhyprarch-screenshot` source is
`$HOME/.local/bin/vanhyprarch-screenshot`. Development may use a symlink;
production bootstrap will publish a regular executable there atomically.

After a valid selection, `grim` writes PNG data to a temporary file under the
final directory. The helper validates the PNG signature, publishes it without
overwriting an existing filename, and passes the saved bytes to
`/usr/bin/wl-copy --type image/png`. The directory is the safely resolved XDG
Pictures directory, falling back to `$HOME/Pictures`, with `Screenshots`
appended. Names use `screenshot-YYYY-MM-DD_HH-MM-SS.png` and a numeric suffix
on collision. Escape cancellation creates no screenshot and does not invoke
the clipboard command; a clipboard failure preserves the completed PNG and
reports the saved path.

The first milestone deliberately has no screen freeze, notification, editor,
additional capture shortcuts, or Quickshell image-processing responsibility.
A nonblocking XDG runtime lock rejects concurrent selections. Deterministic
tests cover geometry, fractional scale, transformed monitors, client filters,
selection construction, cancellation, capture and clipboard arguments,
collisions, locking, and clipboard-failure preservation without opening a
real graphical picker.

`grim`, `slurp`, and `wl-clipboard` are installed on the development machine.
The deployed name-based binding and complete screenshot workflow passed runtime
testing after a full logout/login: the command resolved through the session
PATH, saved the PNG, and published it to the clipboard as `image/png`. Testing
also exposed a `wl-copy` lifecycle bug: a daemonized clipboard provider
inherited a captured stderr pipe, so the helper retained its runtime lock until the
clipboard changed. The helper now gives `wl-copy` an anonymous temporary file
for stderr, allowing its launcher to return while its normal background
provider continues serving repeated paste requests. A deterministic lifecycle
test verifies that a second screenshot session can acquire the lock while the
first provider remains alive. Physical multi-output behavior remains a separate
manual acceptance item.

## Power and idle — CAFFEINE REBOOT-SYNC LIVE VALIDATED / RESOLVED

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
Caffeine operations for the Quickshell UI and the direct shortcut. The
`caffeine toggle` operation reads and changes runtime state while holding the
same backend lock used for marker and fragment deployment; it leaves durable
preferences untouched.

Status version 3 separates stored from effective screensaver values. Unexpected
component damage preserves stored timeout, effect, and lock choice while
projecting Screensaver to Never and a safe effective lock of Display, Suspend,
or None. Deliberate uninstall instead persists Screensaver Never, Color Mix,
and that disclosed lock fallback before removing the marker and optional
payload.

A reproduced reboot exposed a security-relevant mismatch: Caffeine's runtime
marker disappeared as intended, but its persistent generated zero-listener
fragment survived. The UI therefore reported Caffeine off while the fresh
hypridle had no screensaver, display, suspend, or selected automatic-lock
listener. Manual Caffeine ON then OFF repaired it by reapplying the fragment.

Hyprland now starts the `sessionHome`-derived
`exec $HOME/.local/bin/vanhyprarch-idle session-start`. Before the first hypridle
parses configuration, that path rejects root, removes any runtime marker,
renders Caffeine off from the current durable preferences, validates and
atomically publishes the fragment, verifies pre-start ownership and service
state, explicitly releases and closes its flock descriptor, and directly execs
`/usr/bin/hypridle -v`. Deterministic namespace tests cover fresh and retained
runtime markers, an old zero-listener fragment, idempotence, all three lock
points, exact exec arguments and PATH, descriptor closure, validation failure,
manual ON/OFF, and rollback. The first controlled reboot exposed the bare-name
lookup blocker before reconciliation ran. The second proved the absolute path
resolved but exposed the transient executor shell as the backend's immediate
parent, so strict ownership validation correctly rejected startup. The third
reboot still failed after a separate live parent probe had proved the leading
`exec` chain. That isolated an earlier-callback race: `hyprctl instances` could
not discover Hyprland before its runtime lock was published. Startup ownership
now uses the already-established direct `/proc` parent identity and has no
instance-registry, IPC, sleep, or retry dependency.

Final live acceptance reproduced the original case by enabling Caffeine and
rebooting while its runtime marker contained `on` and the persistent generated
fragment had zero listeners. Immediately after login, before opening Power &
Idle or toggling Caffeine, the marker and startup-error record were absent, the
fragment had been republished with Caffeine off and the configured 120/300/600
second screensaver, display/lock, and suspend listeners, and backend status
reported three effective listeners. Exactly one `/usr/bin/hypridle -v` ran as
a direct child of `/usr/bin/Hyprland`; the packaged service remained disabled
and inactive. With no settings interaction, the screensaver then started at
120 seconds. The original security-relevant reboot mismatch is resolved.

Backend status also rejects a deployed fragment that disagrees with the
current preferences and runtime Caffeine marker instead of reporting a logical
listener count that is not represented on disk. It does not parse live daemon
logs. The existing status path still prepares and locks the runtime directory;
that broader observational-side-effect issue was not refactored here.

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
operation, and at a conservative 30-second reconciliation interval. After a
successful Caffeine transaction has fully validated its fragment, replacement
hypridle, listener count, and ownership, the backend releases its lock and makes
one bounded best-effort call to `vanhyprarch.idle refresh()`. That message carries
no state: the eagerly instantiated global controller runs `vanhyprarch-idle
status`, and only the parsed authoritative result changes presentation. Refresh
requests arriving during an action or status read coalesce into one bounded
follow-up. The direct shortcut and manual backend commands remain successful
when Quickshell or its IPC target is unavailable. Startup and the unchanged
30-second timer provide missed-notification, drift, capability, and status-error
recovery rather than normal transaction feedback.

Per-screen buttons and popups consume that shared confirmed state. The panel
exposes the documented presets, disables choices that would violate stage
ordering, clears automatic lock to `None` atomically when its stage is changed
to `Never`, and shows backend errors without presenting a requested Caffeine
value before a successful status confirmation. The dock icon changes between
Papirus `preferences-system-power` and `caffeine`. Repository-native tests cover
eager IPC registration and same-process reload, both Caffeine directions,
rollback, unavailable and hung IPC, external transactions, refresh coalescing,
and stale status-error recovery; corrected controlled live timing validation
remains pending.

The QML loads in the live named configuration. The panel, its Caffeine state,
timeout presentation, effect persistence, error-only feedback, and
passive-refresh behavior have passed manual review. The complete screensaver
chain is validated. Real display-off, suspend/resume, manual lock, password
unlock, and automatic locking at the Screen saver and Display stages have
passed controlled manual testing. Physical multi-monitor acceptance and
untested combinations remain separate work.

## Zig Screensaver optional component — IMPLEMENTED AND LIVE ADOPTED

When the optional component is installed, production uses:

`vanhyprarch-screensaver -> vanhyprarch-zig-player <effect> -> wlr-layer-shell`

Rendering is delegated to the independent GPL-2.0-only Zig Player at pinned
release `v0.1.1`; its implementation is not vendored here. Available effects
are Color Mix, Matrix, Doom, and Game of Life. The component manager verifies
the x86_64 release archive and deploys the binary, upstream license, notices,
README, and pinned metadata to per-user XDG locations. Zig is not a runtime
dependency.

The baseline remains complete without the player. Super+Space lists Local
Dictation and Zig Screensaver as explicit siblings. `component-status --json`
requires the exact marker plus the complete canonical payload; absent or
incomplete capability removes every screensaver control and listener while
Display, Suspend, Automatic Lock, and Caffeine remain operational. The current
development machine reports the pinned v0.1.1 x86_64 component installed, its
marker valid, its complete payload clean-up safe, and capability `installed`.

`bin/vanhyprarch-screensaver` provides explicit `start --idle`, bounded `test`,
idempotent `stop` and runtime `status`, plus install/adopt/reinstall/repair/
uninstall lifecycle commands. It preserves
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

Screensaver invocation remains automatic Power & Idle behavior. There is no
manual/on-demand screensaver shortcut, no Super+K Screensaver row, and no
unbounded manual start operation; adding one is rejected unless a future
explicit product decision reopens it.

## Monitor backend and UI — SINGLE-MONITOR LIVE-ACCEPTED

The project now contains the independently supervised, fixture-tested
`vanhyprarch-monitor` transaction authority and its static user service. The
backend owns a strict private runtime journal, lock, versioned control socket,
exact compositor/output identity, full topology snapshot, candidate
verification, and targeted owned-field rollback. A backend-monotonic
approximately ten-second confirmation deadline is used only for Mode and
bitdepth. Normal rollback restores only the connector-specific owned runtime
fields through `hl.monitor()` and verifies fresh `monitors all` readback; a
full config reload is not the normal rollback path.

The earlier schema-v2 runtime path passed no-op, timeout, explicit-revert,
crash-recovery, and deliberately different scale validation. Scale 1.50 was
authoritatively observed and the automatic deadline restored 1.25, with visual
confirmation and no persistent change. That was a low-risk validation of the
transaction engine, not the final Scale product behavior.

Phase B3A adds repository-only prospective full-config verification, durable
persistence milestones, watched reload plus bounded ordinary-reload fallback,
post-reload `configerrors` and monitor readback, and transaction-owned durable
rollback. Verification runs the installed Hyprland 0.56.2 in an isolated
Bubblewrap tree because its Lua verifier executes configuration callbacks.
The B3A.1 hardening boundary adds real containment probes, invalidates an armed
temporary candidate on an unexpected external config reload, and accepts a
persistence reload only after the candidate file and durable journal milestone
prove transaction ownership. The completed schema-v2 deployment required the
old helper to prove its schema-v1 journal terminal and recovery-disarmed before
controlled removal and replacement; no legacy journal was guessed or migrated.

The deployed schema-v3 backend implements the final policy: Mode
(resolution plus refresh) and bitdepth (8 or 10 bpc) are safe-confirmed; Scale
is immediate-validated and automatically persists only after runtime readback.
Both policies share prospective verification, atomic persistence, reload
reconciliation, and crash recovery. Bitdepth verification uses the effective
DRM format rather than a requested-state flag and permits only the documented
`cm="auto"` dependent effective color transition. Controlled live acceptance
has passed for Mode-only and bitdepth-only timeout rollback and durable Keep,
explicit Mode Revert, and an immediate Scale 1.25→1.50→1.25 durable round
trip. Every persistence round trip restored the known-good machine
configuration exactly.

The deployed UI adds a read-only `inspect` projection, one global
`MonitorController`, pending Mode/bitdepth controls, immediate Scale routing,
and a per-screen confirmation surface using the shared centered-overlay focus
architecture. Backend status reconstructs an active confirmation after a
Quickshell reload; the displayed countdown is presentation-only and the
backend deadline remains authoritative. The panel's output authority is its
own `ShellScreen`, not the focused monitor. QML does not parse raw Hyprland
monitor JSON or machine configuration.

Real UI acceptance covered timeout, explicit Revert, durable Keep, Escape and
outside dismissal as Revert, immediate Scale without a confirmation overlay,
and a same-process Quickshell reload while a Mode transaction was
`temporary-active`. The reloaded controller reconstructed the overlay with the
same transaction ID and remaining backend deadline, and the original deadline
performed rollback. Brightness remains the existing DDC/CI path and global
Text Size remains separate.

Single-monitor acceptance is complete on the development machine's LG `DP-1`
output. Physical multi-monitor acceptance remains deferred because two real
outputs were not simultaneously available; this is an untested hardware
boundary, not a known failure. Deterministic tests cover multi-output ordering,
identity, protected-topology, and target-screen semantics.

An isolated, undeployed schema-4/protocol-3 follow-up implements optional
minimal-intent profile materialization for a fallback-managed output. The
fallback remains a valid working configuration and Vanilla does not materialize
it during installation, session start, hotplug, inspection, or panel open. Only
the explicit **Enable advanced display settings** action clones a supported
fallback rule for one connector, preserving `preferred` Mode, automatic
position, automatic Scale, and omitted optional fields. It uses the existing
prospective verification, atomic persistence, reload reconciliation, complete
topology equality, and recovery engine without `hl.monitor()`, a confirmation
deadline, or runtime correction. Subsequent edits specialize only the field the
user changes. Controlled deployment and fresh-install acceptance remain
pending. See [Monitor Safe Apply backend](monitor-safe-apply.md).

## Known open work

### PLANNED

- Build the shared bootstrap and thin optional archinstall integration defined
  in the [installation strategy](installation-strategy.md), supporting both a
  configured first reboot and post-install use on minimal Arch.
- Define optional/recommended packages separately from the core baseline;
  `file-roller` is a candidate convenience, not a core requirement.
- Deploy and accept the explicit opt-in minimal monitor-profile materialization
  path. DF2 must retain the create-once fallback seed and must not materialize
  connected displays automatically.
- Perform physical multi-monitor acceptance when two suitable outputs are
  simultaneously available; deterministic multi-output coverage already
  exists and no failure is currently known.

### PROVISIONAL

- Validate the external player's physical multi-output and suspend/resume
  behavior.
- Validate remaining lock-at-suspend and Caffeine lifecycle combinations
  without turning test timings into defaults.

### NOT IMPLEMENTED

- Shared bootstrap and optional archinstall integration
- Remove Application ownership mapping
- Vanilla HyprArch self-update; ownership boundaries now exist, but no updater,
  deployment ledger, release staging, or rollback engine has been designed
