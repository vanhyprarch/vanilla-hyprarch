# Current project state

Snapshot date: 2026-09-18.

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

- `home/.config/hypr/hyprland.lua`
- `home/.config/hypr/vanhyprarch/core.lua`
- `home/.config/hypr/vanhyprarch/bindings.lua`
- `home/.config/hypr/hypridle.conf`
- `home/.config/hypr/hyprlock.conf`
- `home/.config/quickshell/vanhyprarch/`
- `install/configure-flatpak`
- `install/install-zig-player`
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
explicit `DP-1` profile and transitional Italian keyboard setting; neither is
a public default. The user override remains the exact header-only seed. The old
root `~/.config/hypr/bindings.lua` was removed only after validation and
remains in the migration recovery material.

The Monitor panel now resolves `XDG_CONFIG_HOME`, targets only the regular
user-owned machine file, matches the focused connector to its explicit output
profile, and edits only that profile's documented
`vanhyprarchMonitorScale` declaration. It fails closed on missing, ambiguous,
symlinked, non-user-owned, or unexpected file structure and never edits the
portable catch-all monitor rule or managed configuration. This is the narrow
single-explicit-profile Alpha boundary, not a general multi-monitor schema.

A deliberately authored portable managed `hyprlock.conf` baseline now exists
in the repository. It was not copied from the live development configuration
and has not been deployed. The live `hyprpaper.conf` and wallpaper remain
unrepresented source-of-truth gaps; that is not permission to copy personal or
machine-specific settings blindly.

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

Before registering its startup children, the managed portable core reads
`HOME` and the inherited `PATH`, validates that `HOME` is non-empty, removes
any existing `$HOME/.local/bin` entries, and prepends exactly one such entry
while preserving every other entry and its order. Public session commands use
stable `vanhyprarch-*` names from that directory. A full logout/login validated
this propagated environment in new Foot and Quickshell processes. It does not
imply that Hyprland's own inherited `/proc` environment was retroactively
changed.

Hyprland starts these processes on `hyprland.start`:

1. `hyprpaper`
2. `systemctl --user start hyprpolkitagent`
3. `exec $HOME/.local/bin/vanhyprarch-idle session-start`, constructed from the
   validated `sessionHome`; the leading shell builtin replaces Hyprland's
   transient executor shell before the backend validates its parent, and the
   backend directly execs `/usr/bin/hypridle -v` after reconciliation
4. `qs -n -c vanhyprarch`
5. `vanhyprarch-voxtype.service`, only when the exact optional-component
   marker is installed

The official `hyprpolkitagent` package provides graphical PolicyKit
authentication for GUI applications that require privileged authorization.
Its packaged user service is started by the direct Hyprland session and is not
enabled as a separate login-time startup owner.

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
- direct dock access to Super+Space from the logo and to the shortcut viewer
  from a system-sized `dialog-information` control;
- clock and calendar;
- lock, suspend, logout through `hyprshutdown`, reboot, and power-off actions;
- a keyboard-and-mouse Super+Space surface with Apps, Install, Remove, Update,
  Additional system components, and Power sections, in-process search over
  `DesktopEntries.applications` and typed action metadata, and confirmation for
  logout, reboot, power off, and optional-component removal;
- a Local Dictation component page with nested reviewed model, language, and
  maximum-recording selectors backed by the public management command;
- a searchable, read-only shortcut viewer populated from described Hyprland
  bindings;
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

Flatpak is an unpinned required entry in the official package manifest. The
development machine has a correct system `flathub` remote. The reusable
`install/configure-flatpak` bootstrap component accepts that state without a
write, adds the system remote idempotently when absent, and fails closed rather
than changing a same-named remote with an unexpected URL. It never installs a
Flatpak application.

The surface opens on the focused monitor through Super+Space or the named IPC
target, supports pointer activation plus Up, Down, Enter, and Escape, and uses
the shared panel, row, theme, metric, and global text-size foundations. The
live named configuration loaded cleanly and exposes the expected IPC methods;
visual and interaction validation remain pending.

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
Caffeine operations for the Quickshell UI.

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

- Bring portable hyprpaper and wallpaper configuration into the repository.
- Build the shared bootstrap and thin optional archinstall integration defined
  in the [installation strategy](installation-strategy.md), supporting both a
  configured first reboot and post-install use on minimal Arch.
- Define optional/recommended packages separately from the core baseline;
  `file-roller` is a candidate convenience, not a core requirement.
- Develop the light/dark wallpaper selection system.
- Implement System Keyboard Synchronization: graphical XKB state from
  `systemd-localed` is the source of truth, synchronized at session start and
  on relevant property changes. The current Italian machine-file block is
  transitional; device-specific rules remain machine configuration.
- Implement Monitor Control & Safe Apply for per-output resolution, refresh
  rate, scale, color depth, and supported brightness. Risky changes must be
  applied temporarily and confirmed within 10 seconds before persistence;
  failure or timeout restores the known-good runtime configuration. Text Size
  remains global.
- Move the Zig Screensaver into optional Additional system component ownership
  without constraining the baseline when it is absent.

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
