# Vanilla HyprArch architecture decisions

This file contains durable architectural and product decisions. It is not a
development diary; implementation status belongs in `current-state.md` and
historical milestones belong in `project-history.md`.

Validated upstream-version quirks and removable workarounds are registered in
the [compatibility register](compatibility.md) rather than duplicated in ADRs.

Statuses used here:

- **Accepted**: current project decision.
- **Provisional**: selected direction that still requires validation.
- **Superseded**: retained context for a decision that is no longer current.

## ADR-001: Project identity

**Status:** Accepted
**Date:** 2026-09-08

The public name is **Vanilla HyprArch**, the repository slug is
`vanilla-hyprarch`, and the technical namespace is `vanhyprarch`.

Public project content must not contain personal names, user-specific
identifiers, or hard-coded home-directory paths.

## ADR-002: Vanilla Arch and vanilla Hyprland

**Status:** Accepted
**Date:** 2026-09-08

Vanilla HyprArch is a configuration layer for a minimal, standard Arch Linux
installation, not a separate distribution. It uses upstream Hyprland without a
distribution-specific framework and follows normal Arch packaging, systemd,
updates, and documentation.

Official Arch packages are the default. AUR packages are acceptable only when
indispensable, no reasonable official alternative exists, and the reason and
maintenance burden are documented. `yay` is the explicit current exception and
is required in the final system/bootstrap; that exception does not grant broad
permission to add other AUR dependencies.

## ADR-003: Quickshell is the desktop UI layer

**Status:** Accepted
**Date:** 2026-09-08

Quickshell owns the project-specific desktop shell: dock, desktop frame,
launchers, system controls, popups, and shell IPC. Components should remain
small, readable, and native to Quickshell rather than recreating a full desktop
environment or adding external polling processes where a supported native API
exists.

Hyprland remains responsible for composition, window management, input, and
session-level bindings.

## ADR-004: The repository is canonical

**Status:** Accepted
**Date:** 2026-09-08

The Git repository is the canonical source of truth. Conversation history and
the state of one development machine must not be required to reconstruct the
project.

The repository should progressively contain configuration, package manifests,
architecture documentation, installation logic, defaults, and practical
upgrade or rollback guidance. Mutable user state remains outside Git.

## ADR-005: Installation must be reproducible

**Status:** Accepted
**Date:** 2026-09-08

The project will provide one understandable, auditable bootstrap with two
supported entry points: integration during archinstall so the first reboot can
enter a configured Vanilla HyprArch system, and independent execution after a
fresh minimal Arch installation with working Internet access.

Archinstall is a thin integration layer, not a second implementation. Both
entry points must invoke the same bootstrap logic for packages, configuration,
commands, services, defaults, and validation. Changes to archinstall must not
require rewriting the core bootstrap.

The installer must account for hardware-dependent choices rather than copying
development-machine monitor or GPU settings blindly.

The documented baseline is the installer's operational specification. A
feature is not fully integrated when it works only on the development machine;
its installation and migration requirements must also be represented in the
repository. Installation should be idempotent where practical and fail closed
when validation or deployment fails. The detailed design and unresolved
installation choices are maintained in the canonical
[installation strategy](installation-strategy.md).

## ADR-006: Use the `vanhyprarch` namespace

**Status:** Accepted
**Date:** 2026-09-08

The named Quickshell configuration and application state namespace are
`vanhyprarch`. Current IPC targets are:

- `vanhyprarch.shell`
- `vanhyprarch.shortcuts`
- `vanhyprarch.superSpace`
- `vanhyprarch.backgroundPicker`
- `vanhyprarch.power`
- `vanhyprarch.idle`

Future project-owned IPC targets use `vanhyprarch.<component>`. The intended
managed idle fragment name is `vanhyprarch-idle.conf`.

## ADR-007: Follow the Quickshell screen lifecycle

**Status:** Accepted
**Date:** 2026-09-08

Global controllers, file writers, and process owners live once under
`ShellRoot`. Screen-bound UI lives in a `Variants` delegate whose model is
`Quickshell.screens`, with each permanent surface assigned to the delegate's
screen.

This structure replaced permanent unbound `PanelWindow` instances, which could
retain invalid screen state and disappear after suspend/resume while the shell
process and IPC remained alive.

## ADR-008: Default applications and icon policy

**Status:** Accepted
**Date:** 2026-09-08

The deliberate defaults are:

- Firefox for web browsing
- Foot for the terminal
- Thunar for file management
- imv for image viewing
- mpv for media playback
- Papirus for shell icons

The shell declares Papirus through its root icon-theme pragma. System-control
icons use Papirus full-color assets where appropriate; tray icons may be tinted
with the shell accent. Missing icons should be addressed through the icon policy
rather than by embedding arbitrary unlicensed assets.

`xarchiver` is the selected lightweight archive frontend with Thunar's archive
plugin. `file-roller` remains excluded. BlueZ remains the Bluetooth backend;
`blueman` is excluded because the shell owns Bluetooth UX through native
Quickshell state and a narrow pairing agent.

## ADR-009: Prefer native audio and network integrations

**Status:** Accepted
**Date:** 2026-09-08

Audio controls use `Quickshell.Services.Pipewire`; hardware volume bindings use
WirePlumber's `wpctl`. Network status, Wi-Fi discovery, known-network handling,
and connection controls use `Quickshell.Networking` with NetworkManager.

The network core must not be replaced with `nmcli` polling or shell-process
state synchronization. External commands remain appropriate where Quickshell
has no native interface, such as DDC monitor control.

`network-manager-applet` is excluded from the baseline. It must not be restored
solely because it existed historically; the project deliberately owns network
UX through native Quickshell integration.

## ADR-010: Expose five numbered workspaces

**Status:** Accepted
**Date:** 2026-09-08

The numbered workspace UX is limited to workspaces 1 through 5. Bindings and the
shortcut viewer must not expose the former 6 through 10 shortcuts. Relative
workspace navigation and the special scratchpad remain available.

## ADR-011: Use Ly as the display manager

**Status:** Superseded by ADR-041
**Date:** 2026-09-08

Before Alpha, Ly was selected to run through `ly@tty2.service` on tty2, with
the competing getty disabled. This design was never released and was
superseded by ADR-041.

The display manager is session infrastructure; its animation implementation is
not itself a user-session screensaver.

## ADR-012: Exclude hibernate from the UX

**Status:** Accepted
**Date:** 2026-09-08

Hibernate is not a supported user-facing power action. The current power menu
offers lock, suspend, logout through `hyprshutdown`, reboot, and power off.
Future Power & Idle work must not reintroduce hibernate as an idle stage or
menu action without a new decision.

## ADR-013: Power & Idle has three ordered stages

**Status:** Accepted
**Date:** 2026-09-08
**Implementation:** Backend and Quickshell UI implemented; real screensaver,
display-off, suspend/resume, and tested lock-stage actions manually validated

The Power & Idle control has three independently selectable stages:

1. Screen saver
2. Turn off display
3. Suspend

Enabled stages must have strictly increasing timeouts. `Never` omits a stage;
it must not be encoded as a zero-second listener. The UI must reject incoherent
combinations instead of silently changing other selected values. Initial
migration preserves `Never / Never / Never` until the user chooses otherwise.

The controller and persistence owner are global; the dock control and panel are
screen-bound UI.

## ADR-014: Exactly one idle stage owns locking

**Status:** Accepted
**Date:** 2026-09-08
**Implementation:** Backend and Quickshell UI implemented; manual lock and
automatic locking at the Screen saver and Display stages manually validated.
Remaining combinations are tracked in `current-state.md`

One radio-style selection associates automatic session locking with the screen
saver, display-off, or suspend stage. A stage set to `Never` cannot own locking.
This supersedes the earlier idea of a separate lock timeout or independent lock
toggles.

- Lock at screen saver: leaving the saver requires `hyprlock` authentication.
- Lock at display-off: the saver is dismissible, but wake from display-off
  presents `hyprlock`.
- Lock at suspend: earlier stages remain unlocked; resume presents `hyprlock`.

## ADR-015: Generate a managed hypridle fragment

**Status:** Accepted
**Date:** 2026-09-08
**Implementation:** Backend, production generation, and first Quickshell UI
implemented

Use a mostly static `hypridle.conf` that sources a generated
`vanhyprarch-idle.conf`. A strict project-owned preference file is the durable
source of truth; the fragment is its generated runtime projection. The
screensaver stage uses one inhibitor-aware listener with timeout and resume
actions. Player v0.1.1 was measured not to reset the idle clock, so no separate
input-only helper is generated.

The effective fragment is not a release-owned source file. First-session
startup and later backend transactions create it from preserved preferences;
normal project updates do not ship or overwrite generated bytes.

Updates must be atomic and followed by restart and verification, with rollback
on failure. Hyprland remains the single direct owner of hypridle; the packaged
systemd user service stays disabled and inactive. The backend validates this
ownership before replacing the daemon.

Version-specific limitations affecting generated listener timing are tracked
in the [compatibility register](compatibility.md) and must be retested when
Hyprland or hypridle changes.

## ADR-016: Use Ly colormix as the screensaver visual

**Status:** Superseded by ADR-021
**Date:** 2026-09-08

The former repository-local ColorMix translations and Foot/Quickshell
presentations established the lifecycle boundary and exposed a timer-reset
problem. They are no longer production or retained reference implementations;
Git history preserves that investigation.

## ADR-017: Respect third-party licenses

**Status:** Accepted
**Date:** 2026-09-08

Distributed code and assets must permit redistribution. Derived work retains
required notices and attribution. An asset present on the development machine
is not automatically suitable for inclusion in the public repository.

## ADR-018: Separate decisions, state, and history

**Status:** Accepted
**Date:** 2026-09-08

`decisions.md` records durable choices and their rationale.
`current-state.md` records the current implementation and open work.
`project-history.md` records concise milestones and architecturally relevant
abandoned approaches. Together, the sanitized project documentation is the
canonical project record. Raw conversational handoffs containing personal
identifiers are private migration inputs and must not be tracked or published.

When a direction changes, mark the old decision Superseded rather than silently
rewriting history. Promote a Provisional decision to Accepted only after its
validation criteria have been met.

## ADR-019: Caffeine is a runtime override

**Status:** Accepted
**Date:** 2026-09-08
**Implementation:** Backend and Quickshell control implemented and reviewed;
runtime suppression and reboot reconciliation are regression-tested and live
validated; remaining manual combinations are tracked in `current-state.md`

Caffeine temporarily suppresses every automatic Power & Idle action without
altering the user's stored timeouts or lock point. Its marker is session-scoped
under `XDG_RUNTIME_DIR` and can be reconciled idempotently by reapplying either
state. Every fresh Hyprland session must authoritatively remove the marker and
regenerate the Caffeine-off fragment from durable preferences before directly
execing hypridle. Marker disappearance alone is insufficient because the
generated fragment persists across reboot.

The startup callback is not required to wait for Hyprland's global instance
registry. Its leading shell `exec` establishes a direct parent relationship,
and the startup-only backend path proves that parent's exact executable, UID,
and stable `/proc` start time. Later manual daemon transactions continue to use
normal Hyprland instance discovery for targeted replacement.

Caffeine's shortcut calls one backend `caffeine toggle` operation. The backend
decides ON or OFF only after acquiring its existing exclusive lock and uses the
same marker, fragment deployment, and rollback transaction as explicit ON/OFF;
the shell does not race a separate status read against a later write.

After a Caffeine transaction has validated and committed the complete backend
state, it releases its exclusive lock and issues one bounded best-effort call to
the eagerly registered `vanhyprarch.idle refresh()` IPC method. The message
carries no Caffeine value and cannot assign presentation state; the global
controller immediately requests authoritative backend status. A coalesced
follow-up prevents lost invalidations without replacing the conservative
periodic reconciliation timer. Missing, failed, or hung IPC never changes the
successful backend result, and the direct shortcut remains fully operational
without Quickshell.

Caffeine does not disable manual locking or other explicit power actions.
Listeners that perform screensaver, display, lock, or suspend actions remain
inhibitor-aware.

## ADR-020: Present the screensaver as a separate Quickshell layer-shell process

**Status:** Superseded by ADR-021
**Date:** 2026-09-08
**Historical implementation:** Controller lifecycle and absolute-timer
regression validated; lock, DPMS, and suspend had not yet been tested before
this renderer was superseded. Current native-chain status is in
`current-state.md`

The separate Quickshell layer-shell process replaced Foot and validated native
layer-shell timing, but it duplicated rendering code and imposed
Quickshell-specific lifecycle validation. The independent native player now
owns this responsibility.

## ADR-021: Delegate screensaver rendering to Vanilla HyprArch Zig Player

**Status:** Accepted
**Date:** 2026-09-09
**Implementation:** Pinned v0.1.1 production chain, input routing, idle
continuity, real DPMS, suspend/resume, and tested automatic-lock paths
validated; physical multi-output acceptance remains pending

Vanilla HyprArch installs and controls the independent GPL-2.0-only
`vanhyprarch-zig-player`; it does not copy, vendor, or recreate its Zig source.
The player owns Wayland, layer-shell surfaces, output geometry and scaling,
rendering, and the four built-in effects. The project controller retains only
`start|stop|status`, exact native-process ownership, and cursor restoration.

Release v0.1.1 is pinned by tag, architecture, asset, checksum, release URL, and
source URL. Updates are explicit reviewed changes. The prebuilt x86_64 binary
requires glibc and the Wayland client runtime, not Zig. Other architectures fail
closed until a release asset is deliberately added.

The final production chain started ColorMix through hypridle and the controller
at +10.034 seconds and fired the next listener at +20.036 seconds, 10.002
seconds later. Genuine input caused resume at +23.291 seconds, stopped the
player, and did not leak the first key to the underlying Foot instance. Manual
click and scroll tests also passed. The single inhibitor-aware listener is
therefore the current architecture, with input absorption wholly owned by the
player. Physical two-monitor behavior remains a live acceptance item.

## ADR-022: License Vanilla HyprArch under GPL-2.0-only

**Status:** Accepted
**Date:** 2026-09-09

Project-authored Vanilla HyprArch material is licensed under GPL-2.0-only as
stated in the root `LICENSE` and README. This does not relicense independent
software or erase third-party notices. If the project distributes an external
GPL binary, its own license, notices, and corresponding-source obligations must
remain satisfied independently.

## ADR-023: Use native Quickshell Bluetooth with a narrow pairing agent

**Status:** Accepted
**Date:** 2026-09-09
**Implementation:** First complete shell integration implemented; outgoing
Android-phone discovery and pairing validated, broader device and incoming-flow
validation pending

Quickshell's native Bluetooth module owns adapter power, discovery, device
state, pairing, connection, removal, and trust. Vanilla HyprArch does not poll
or parse `bluetoothctl` and does not maintain a second Bluetooth device model.

Quickshell 0.3.1 does not expose BlueZ's complete `org.bluez.Agent1` pairing
callbacks. One Quickshell-supervised GPL-2.0-only Python helper therefore owns
only that interface, registers as the default `KeyboardDisplay` agent, and
exchanges versioned pairing requests over private newline-delimited JSON pipes.
It uses the official `python`, `python-dbus`, and `python-gobject` packages and
fails closed if its BlueZ owner, UI, IPC, or process owner disappears. Display
callbacks are acknowledged to BlueZ only after the target panel reports them
visible, and automatic trust/connect is scoped to one user transaction in the
current agent session. QML SIGTERM teardown and private-pipe closure are the
cooperative lifecycle layers. Linux `PR_SET_PDEATHSIG` plus an immediate parent
PID recheck is the final guarantee when the owning Quickshell process dies
without cleanup; no additional runtime dependency is required. Retest and
remove the helper if a future Quickshell release exposes equivalent complete
pairing-agent functionality.

Repeated real cold logout/login tests verified that the old helper and BlueZ
client disappear with Quickshell, no PPID-1 orphan remains, the old logind
scope closes, and exactly one helper returns under the new Quickshell session.

## ADR-024: Persist one explicit Bluetooth power preference

**Status:** Accepted
**Date:** 2026-09-10
**Implementation:** User preference, restore controller, and system
configuration implemented; OFF-to-OFF and ON-to-ON reboot restoration validated

The Bluetooth panel is the only writer of a versioned `on` or `off` preference
under the user's XDG configuration directory. One global Quickshell controller
applies it to every native Bluetooth adapter, including adapters that appear
after shell startup or return after BlueZ restart or rfkill blocking. Adapter
events never become preferences. An absent preference restores the first-run
default of ON without writing a preference file.

BlueZ `AutoEnable` is disabled in the project-owned minimal `main.conf` so an
OFF preference does not incur an automatic ON followed by a session-level OFF.
An ON preference is restored when the shell and adapter are available. This
keeps BlueZ and Quickshell upstream, does not poll, and treats multiple
adapters as one user-facing Bluetooth radio policy.

## ADR-025: Build Super+Space from native catalogs and typed actions

**Status:** Accepted
**Date:** 2026-09-17
**Implementation:** Apps, Install, Remove Package, Update, and Power implemented;
visual and interaction behavior pending manual validation

Super+Space has one global navigation/search controller and one presentation
surface per Quickshell screen. Installed applications come directly from
`DesktopEntries.applications` and launch through `DesktopEntry.execute()`;
Vanilla HyprArch does not persist or wrap a second application catalog.

Power operations are explicit project actions shared with PowerMenu. Lock and
Suspend execute immediately. Logout, Reboot, and Power off require
confirmation. The commands remain `loginctl lock-session`, `systemctl
suspend`, `vanhyprarch-polkit-session logout`, `systemctl reboot`, and
`systemctl poweroff`; the logout helper stops graphical authorization before
it execs `hyprshutdown`.

The same `PowerActions` controller exposes a narrow named `lock` IPC method for
the described `Super+Ctrl+L` binding. The endpoint delegates to the controller's
existing Lock action, so the Power Menu, Super+Space, and keyboard shortcut do
not duplicate lock semantics.

Filtering is synchronous and in-process over native objects and typed action
metadata. It does not invoke a subprocess per keystroke or turn search results
into arbitrary shell command strings.

Install is an explicit typed action which accepts non-empty search terms only.
Activation closes Super+Space and starts `/usr/bin/yay -Y -- <terms>` inside
Foot through one direct argument vector. Foot does not use `--hold`; a shared
executable Python terminal-operation helper runs yay with inherited terminal
streams, reports its final status, and waits for Enter before returning so Foot
closes normally. No result-ordering option is supplied, so yay retains the
user's configured or default ordering. No shell parses user text, `--`
prevents yay option injection, and yay retains its normal package selection,
PKGBUILD, provider, dependency, conflict, authentication, cancellation, and
confirmation prompts. Super+Space neither parses yay output nor owns a
persistent package catalog.

Remove Package refreshes installed package names and versions from the local
pacman database with `/usr/bin/pacman -Q` whenever the section is entered. The
transient objects are filtered in-process. Activation is possible only from a
stored catalog object, never from raw search text, and starts the fixed command
`/usr/bin/yay -Rns -- <selected-package>` through the same terminal helper and
a direct argument vector. The `-Rns` policy intentionally removes the target,
dependencies that become unnecessary under pacman semantics, and retained
`.pacsave` files while keeping normal transaction review and confirmation
visible. No shell, cascade, dependency bypass, or noninteractive confirmation
option is permitted.

Update is one global typed controller with exactly two fixed actions. System
starts `/usr/bin/yay -Syu`; Flatpak starts `/usr/bin/flatpak update`. Both run
through the shared terminal-operation helper as direct argument vectors and
retain their normal interactive prompts. Entering Update performs neither
operation. There is no Everything action, arbitrary command runner, or project
self-update action.

Remove Application remains unimplemented and must not be exposed as a
placeholder. Application display names, desktop IDs, Exec fields, and
executable names are not package-ownership evidence.

## ADR-026: Require unpinned Flatpak and the system Flathub remote

**Status:** Accepted
**Date:** 2026-09-17

`flatpak` is a required package from the official Arch repositories. The
manifest intentionally contains only the package name: clean installation uses
the currently available official version, and normal full system upgrades keep
it current. Flatpak is not an AUR or version-pinned dependency.

The system-wide `flathub` remote is also required. The reusable bootstrap
component uses `remote-add --system --if-not-exists`, preserves an existing
correct remote without a write, verifies the resulting canonical repository
URL, and fails closed on a same-named conflicting URL. It does not alter user
remotes, reset Flatpak state, or install applications.

Vanilla HyprArch self-update remains intentionally unavailable. Repository
ownership boundaries are now defined, but updates must still wait for a
transactional deployment and rollback design; `git pull` is not a deployment
mechanism.

## ADR-027: Put public session commands in the user-local PATH

**Status:** Accepted
**Date:** 2026-09-17

Public Vanilla HyprArch session commands use stable `vanhyprarch-*` names and
are deployed as regular executables under `$HOME/.local/bin`. Hyprland prepends
that directory exactly once to the inherited graphical-session `PATH` before
starting session children. Development deployments may use symlinks; the
installed-mode deployment used by the public bootstrap installs commands
atomically without depending on its temporary source tree.

This child-environment policy is distinct from Hyprland's own inherited process
environment. Controlled reboot evidence showed that Hyprland's `/proc` PATH can
lack `$HOME/.local/bin` even while normal launched applications receive the
configured session PATH. Security-critical Hyprland autostart of a user-local
project command therefore uses the absolute installed path constructed from the
validated `sessionHome`; it does not move the command into a system PATH or add
a per-process PATH override. Current `hl.exec_cmd` behavior uses a transient
`/bin/sh -c`, so this security-sensitive idle startup begins its command string
with the shell builtin `exec`. That replaces the executor shell before the
backend validates direct Hyprland ownership. This is not a general requirement
for every autostart command.

Quickshell-private helpers remain beneath `Quickshell.shellDir/helpers` and are
invoked by their resolved configuration-relative paths rather than being
exported as public commands. Fixed or sensitive system dependencies may use
explicit `/usr/bin/...` paths. Independently managed systemd user units must not
rely on Hyprland having started early enough to supply their command path.

## ADR-028: Make local dictation an optional verified upstream component

**Status:** Accepted
**Date:** 2026-09-17

Push-to-talk dictation is optional and outside the required package baseline.
Vanilla installs the pinned official Voxtype 1.0.1 x86_64 AVX2 CPU binary
directly under `$HOME/.local/bin`, after independent SHA-256, detached OpenPGP
signature, full primary-fingerprint, and version checks. It does not use an AUR
Voxtype package or a floating release URL. `gnupg` and `wtype` are explicit
optional official-repository dependencies.

The default model is English-only `small.en`; model transport remains
Voxtype-owned and Vanilla independently verifies the resulting model digest.
GPU acceleration is never selected automatically. Hyprland owns only F9 press
and release bindings and conditionally starts a fixed, non-enabled project user
service. Voxtype's evdev hotkey is disabled, so dictation requires neither the
`input` group nor uinput/ydotool. Local Dictation uses an explicit clean-
uninstall contract: removing the component deletes Voxtype configuration and
all downloaded models, while leaving the Vanilla manager and its immutable
resources available for reinstall. Future model/language or GPU customization
must preserve this binding and service architecture.

## ADR-029: Manage optional components through a stable backend and SuperSpace

**Status:** Accepted
**Date:** 2026-09-17

SuperSpace exposes one root-level `Additional system components` catalog. The
catalog is deliberately small and explicit rather than a plugin framework;
Local Dictation is its first component. QML presents state and selections, but
does not download, verify, edit configuration, or control services itself.

The independently deployed `vanhyprarch-dictation` command is the state and
transaction authority. It consumes immutable resources from the project XDG
data directory, provides versioned strict JSON for readers, and remains
installed when Voxtype is removed. Model identity, byte size, digest, and
pinned provenance are one reviewed manifest. User changes to model, language,
and bounded recording duration preserve unrelated Voxtype configuration and
are published only after model, config, daemon, and rollback checks succeed.

The public default remains CPU AVX2, `small.en`, English, and a 120-second
maximum. CPU and Vulkan are exact signed-artifact identities selected only by
the active binary digest. The manager and SuperSpace switch them
transactionally after explicit user selection; there is no automatic
acceleration. Vulkan success additionally requires vendor-aware runtime proof
from the managed daemon. AMD and Intel require the selected DRM render node;
NVIDIA requires common executable/loader/vendor-ICD proof but does not assume
a DRM-render-node fd until a reliable NVIDIA-specific invariant is reviewed.
Local Dictation uninstall removes the complete Voxtype config and data roots,
including verified binary caches; generic packages such as `gnupg`, `wtype`,
the Vulkan loader, and vendor ICDs are not automatically removed.

Install starts and health-validates the non-enabled service before its marker
becomes authoritative. SuperSpace, not the compositor-independent manager,
reloads Hyprland after successful Install or Uninstall so current-session F9
bindings follow the marker. The shared terminal helper records the manager
child's status in a private runtime directory, and a supervising process waits
for the real Foot process to exit before that status drives reload and refresh;
Foot's own exit status is not treated as the manager result. Apply does not
reload Hyprland. Model acquisition isolates stable Voxtype 1.0.1's
setup-generated config under a temporary
`XDG_CONFIG_HOME`; only the reviewed Vanilla config may become the live fresh-
install configuration. Rollback removes a whole newly created Voxtype tree only
after hardened path, ownership, entry-type, and symlink validation.

## ADR-030: Establish deployment ownership and configuration boundaries

**Status:** Accepted
**Date:** 2026-09-18

The historical version-1 manifest grew to ten descriptive ownership classes,
including later `PERSISTENT_STATE_PROVENANCE` and `USER_CONTENT` additions.
DF2 ownership v2 normalizes those boundaries into explicit deployability,
install, and update semantics without implementing an installer, updater,
deployment ledger, rollback engine, or migration framework.

Hyprland loads a managed portable core, managed curated bindings, create-once
machine configuration, and a user-owned override in that order. The managed
entrypoint resolves `XDG_CONFIG_HOME` with a `$HOME/.config` fallback and uses
Hyprland 0.56.2's intentional absolute-path `require()` support. Monitor,
connector, mode, scale, bit depth, color management, keyboard layout, and
device-specific rules do not belong in the managed core. The machine seed has
a portable catch-all rule with preferred mode, automatic position, and Scale 1.
That fallback exposes no Monitor panel write field. The
controlled live migration established one narrowly documented Scale field in a
specific explicit output profile. The repository Monitor UI now submits Scale
to the transaction backend so runtime readback, prospective validation,
persistence, reload, and technical rollback remain one operation. The backend
never edits the fallback block; on the first real change it may clone a
strictly supported fallback into an identity-validated connector profile.
Neither policy guesses a profile or exposes a general multi-monitor schema
during Alpha. The deployed UI and backend have
completed controlled single-monitor live acceptance; physical multi-monitor
acceptance remains a separate hardware-dependent boundary.

Create-once seeds are never normal managed-update payloads. Machine files and
override files are preserved, but preservation of an override file does not
promise Alpha stability for every Lua symbol, property, format, or internal
interface it references. Persistent preferences remain owned by their backend,
and generated effective files remain replaceable by their generator.

Zig Screensaver now uses optional-component ownership. The baseline manager and
immutable verification metadata are managed payload; the player and its exact
ancillary files exist only with a validated component marker.

## ADR-031: Synchronize graphical keyboard state from systemd-localed

**Status:** Accepted
**Date:** 2026-09-18
**Implementation:** Implemented and live validated

The system graphical/XKB configuration exposed by `systemd-localed` is the
source of truth for the Hyprland keyboard layout. Vanilla HyprArch synchronizes
the relevant graphical properties at session start and subscribes to localed
property changes without polling. External changes
made through normal `localectl`/localed configuration must therefore propagate
to Hyprland.

The synchronizer must distinguish graphical XKB changes from console-only
changes: an explicit `localectl --no-convert` console-keymap operation must not
be misread as a graphical-layout update. A future Vanilla keyboard UI will
write the system source of truth instead of changing only Hyprland.
Device-specific keyboard rules remain `CREATE_ONCE_MACHINE`. The managed
helper projects the complete graphical tuple through one validated Hyprland
Lua runtime transaction, verifies readback, and performs one bounded rollback
on failure. Every relevant graphical event compares fresh localed state with
actual global Hyprland state; cached success cannot suppress runtime-drift
repair, while console-only events remain ignored. The session-start action
publishes the new compositor identity to the systemd user manager before it
restarts the static service. It never owns the active layout group. The Italian
layout is not duplicated in the validated development-machine file or public
seed; neither contains a global XKB fallback. See
[System keyboard synchronization](system-keyboard-synchronization.md).

## ADR-032: Match monitor persistence policy to setting risk

**Status:** Accepted
**Date:** 2026-09-18
**Implementation:** Schema-v5/protocol-v4 backend and UI published;
single-monitor runtime, persistence, confirmation, dismissal,
Quickshell-reload, forced-HDR, and Automatic-HDR paths live-accepted. Optional
minimal-profile materialization is published. The repository's
schema-v6/protocol-v5 follow-up couples explicit Resolution changes to
configured Scale `auto` inside the same confirmed transaction; renewed
deployment acceptance is pending. Physical acceptance on a
genuinely fallback-managed output remains deferred.

Monitor control is per explicit output profile. Resolution/refresh is one Mode
tuple, bitdepth is 8 or 10 bpc, forced HDR is per output, and Scale is per
output. Automatic HDR is explicitly global because `render:cm_auto_hdr` applies
to every display. Text Size remains one global preference. Brightness remains
an independent DDC/CI control.

Safety-critical Mode, bitdepth, forced-HDR, and Automatic-HDR changes follow one invariant:

`known-good configuration -> temporary runtime apply -> 10-second confirmation
-> persist only on confirmation`

Application failure or confirmation timeout automatically restores the
known-good runtime configuration. An unconfirmed safe candidate is never
persisted. Any valid combination of Mode, bitdepth, per-monitor HDR, and global
Automatic HDR is one transaction and one confirmation overlay. A user-selected
Resolution also owns configured Scale `auto` in that transaction. The Scale
draft and controls remain locked until the Resolution draft is cancelled or the
transaction is resolved; cancellation and rollback restore prior ownership.

**HDR Off** means restore the exact base non-HDR CM intent, not force sRGB or
disable global Automatic HDR. **Always On** forces `cm = "hdr"` and requires
10-bit; the backend refuses illegal 8-bit combinations rather than silently
coupling another change. The config-local forced-HDR marker retains exact base
CM presence/value across Keep and reboot. External HDR/EDID-HDR intent,
unsupported syntax, ICC ownership, and uncertain EDID capability remain
unmanaged. The separate global Off/HDR/HDR (EDID) choice maps to
`render:cm_auto_hdr` 0/1/2. UI state represents policy only: Hyprland 0.56.2
does not expose authoritative generic live `inHDR()` state.

Manual Scale selection instead follows immediate validation: validate, apply
runtime Scale, authoritatively read it back, prospectively verify and atomically
persist only Scale, reconcile reload, then verify again. Any technical failure
restores the previous durable bytes and runtime Scale. Scale has no human
confirmation dialog or confirmation deadline.

Normal rollback uses connector-specific runtime `hl.monitor()` restoration of
only the fields owned by that operation followed by authoritative full-topology
readback; full Hyprland configuration reload is not the primary runtime
rollback path. Both policy classes use the same supervised persistence,
reconciliation, and crash-recovery quality.

Quickshell is a non-authoritative client. One global Monitor controller reads a
small normalized backend inspection contract, while each panel selects its
connector with `Hyprland.monitorFor(screen)`. Mode, bitdepth, forced HDR, and
the one controller-global Automatic HDR value are pending input until one
combined Apply request; Scale invokes its separate
immediate operation except for the Resolution-owned automatic transition
described above. The controller reconstructs an active confirmation from
backend status after shell reload. Its countdown never owns expiry. The
per-screen confirmation surface uses the shared centered-overlay/focus
architecture, prefers the transaction target screen, and falls back to another
registered screen without affecting backend transaction survival.
Escape and outside dismissal both request backend Revert. A Quickshell reload
reconstructs the overlay from backend status with the same transaction ID and
remaining deadline; it neither cancels nor extends the transaction.

Monitor runtime transactions require an existing unambiguous explicit connector
profile in machine configuration. The portable fallback remains a valid
Hyprland configuration and inspection exposes its authoritative live state
without writing it. On the first actual display mutation, the backend first runs
a dedicated persistence-only transaction: it clones one supported fallback block,
changes only its empty output selector to the connector, verifies complete
pre/post topology equality, and uses the existing prospective-validation,
atomic-persistence, reload and recovery engine. It does not call
`hl.monitor()`, create a confirmation deadline, infer current effective values,
or normalize an existing explicit profile.

For the public fallback, the explicit clone retains `preferred` Mode,
automatic position, Scale 1, and omitted bitdepth/color fields. Subsequent Mode
or Scale edits replace only their fallback value; the first
bitdepth preference inserts only that field. Installation, session start,
hotplug, inspection, and panel open never materialize automatically. DF2 may
send normal mutation requests through the same backend and must not grow a
second monitor parser or persister. Existing `scale = "auto"` state remains a
supported read/replace source. Brightness and Text Size are not routed through
this backend.

Single-monitor acceptance is complete. Physical multi-monitor behavior remains
architecturally covered and fixture-tested but has not been accepted with two
real simultaneously connected outputs.

## ADR-033: Make Zig Screensaver an explicit capability

**Status:** Accepted
**Date:** 2026-09-18
**Implementation:** Repository implemented; controlled live adoption pending

Local Dictation and Zig Screensaver are explicit sibling entries under
Additional system components. No generic plugin registry is introduced.
`vanhyprarch-screensaver` remains the single baseline runtime and lifecycle
authority. Its marker is published only after the pinned v0.1.1 x86_64 payload
is fully validated and before installed-capability idle configuration is
published.

Power & Idle consumes backend capability rather than inspecting files. Absent
or incomplete capability removes Screen Saver Effect, Screensaver, and the
Screensaver Automatic Lock choice and prevents listener generation. Unexpected
damage preserves durable screensaver preferences and projects a safe effective
fallback. Deliberate uninstall resets Screensaver and effect and persistently
maps a Screensaver lock to Display, else Suspend, else None after disclosure.
Automatic Lock remains a stage selector, not an independent timeout.
For the Screensaver stage, the native saver remains visible while idle and
normal resume requests lock before desktop access; hyprlock is not placed over
the saver at its timeout. The controller's resume operation records a successful
lock request before allowing later cleanup; direct protected stop and unexpected
protected-player exit request the same lock before cursor recovery, while
bounded manual `test` never arms it.

Idle invocation is explicit `start --idle`; manual testing uses a bounded
`test`. Exact player termination is completed independently of cursor
restoration, and pending cursor ownership remains recoverable by later stop.
The product has no manual/on-demand screensaver shortcut or unbounded manual
start operation. Screensaver invocation remains owned by automatic Power &
Idle behavior unless a future explicit decision reopens that scope.

## ADR-034: Make Appearance the Light/Dark authority

**Status:** Accepted
**Date:** 2026-09-19

`vanhyprarch-appearance` owns one durable Light/Dark preference, independent
Light and Dark wallpaper selections, host color-scheme publication, and
Hyprpaper reconciliation. The global Quickshell `AppearanceController` is its
shell projection. Per-screen dock buttons invoke that authority and retain no
private persistence or theme state. The accepted Vanilla palettes remain
unchanged.

The writable host source is `org.gnome.desktop.interface color-scheme`.
Appearance sets `prefer-dark` or `prefer-light` and requires corresponding
`org.freedesktop.appearance/color-scheme` portal readback of 1 or 2. The portal
is a read interface, not a write target. No application profile, GTK theme,
Qt override, or application lifecycle is modified. GTK3's user-owned
`settings.ini` receives only the derived `gtk-application-prefer-dark-theme`
preference; its theme name and unrelated settings remain outside Vanilla's
write scope.

Hyprpaper is the required session-owned renderer and never the preference
authority. Hyprland starts one instance through the public Appearance manager;
the managed renderer config carries no wallpaper selection. Appearance uses
Hyprland's JSON monitor inventory and explicitly applies one selected wallpaper
to each active output. An empty-monitor request is retained only as a fallback
for newly appearing unassigned outputs because Hyprpaper 0.8.4 gives explicit
targets precedence. Monitor-set changes during application require another
reconciliation. Desired preference and effective shell, host, portal,
renderer-process, and per-output wallpaper state remain distinguishable.

Preferences use a versioned mode-0600 JSON file in XDG configuration state.
Wallpaper selections are relative to the matching
`<XDG Pictures>/Wallpapers/{Light,Dark}` directory. User images are never
managed payload. Canonical containment and content-type checks reject path
escapes and unsupported files. First-run migration preserves a valid legacy
shell mode and adopts an active wallpaper only when it is already contained in
the appropriate directory; it never guesses from directory order.

The GPL-2.0-only Wolkenstein images are managed distribution assets, while
their Pictures copies are one-time starter content. Official Wallpaper Set v2
replaces the distribution source with eight 3840×2160 RGB PNGs while retaining
the existing filenames and pair-1 default. A private version-2 receipt records
that bootstrap completed. Version-1 per-file hash receipts are migration
evidence and their hashes remain historical only; neither old hashes nor
missing destinations authorize later writes. After initialization, updates do
not add, replace, restore, or delete anything in the user-owned Light/Dark
directories, including when the distributed starter set changes. Existing
selections remain authoritative.

The visual Background Picker is one global controller with one screen-bound
presentation per `Variants` delegate. Both `Style -> Choose background` and
`Super+Ctrl+Space` enter that controller. It queries the manager on every open,
keeps candidate navigation separate from the applied selection, and routes an
explicit apply back through the global `AppearanceController`; QML never calls
Hyprpaper. It uses the existing centered-overlay role and sole shell-global
focus grab, so SuperSpace, Shortcuts, and the picker remain mutually exclusive
while retaining the established dock-panel coexistence semantics.

## ADR-035: Own PolicyKit around the direct graphical session

**Status:** Accepted
**Date:** 2026-09-20
**Implementation:** Implemented and live validated

The inactive `graphical-session.target` in the direct
`start-hyprland -> Hyprland` architecture cannot own the packaged
`hyprpolkitagent.service` lifecycle. Vanilla therefore owns the session edge
explicitly without replacing the package unit or introducing a new session
target.

At `hyprland.start`, `vanhyprarch-polkit-session session-start` validates the
current compositor and Wayland sockets, synchronously imports the current
signature and display environment, resets inherited failure state only when
the service is actually failed, and restarts the package service. The shared
graceful logout action stops that service before it execs `hyprshutdown`; a
failed stop prevents the logout from proceeding without its required ordering.

A managed package drop-in adds an `ExecCondition` that revalidates the current
compositor before every initial or automatic service start, plus a one-second
restart interval. The package's `Restart=on-failure` therefore still recovers
an agent-only active-session crash. Once the compositor is absent, the next
restart is skipped cleanly instead of creating an abort loop. Direct manual
compositor termination has no universal pre-exit callback, so it relies on
that condition; reboot and poweroff terminate the user manager. Clean
same-login compositor restart is not a supported product lifecycle.

Repeated real cold logout/login tests verified stop-before-compositor-loss,
automatic fresh-session startup of exactly one official agent, current
environment inheritance, and absence of compositor-less restart or start-limit
storms. The package-owned unit remained unchanged.

## ADR-036: Keep described bindings authoritative for shortcut discovery

**Status:** Accepted
**Date:** 2026-09-20
**Implementation:** Availability metadata and Dictation filtering implemented

`home/.config/hypr/vanhyprarch/bindings.lua` remains the one definition of
ordinary user-facing shortcuts, including keys, action labels, categories,
dispatchers, and optional availability. Super+K reads the active described
bindings from `hyprctl -j binds`; QML does not maintain a parallel shortcut
catalog.

Legacy descriptions remain exact `Category | Action` text. Conditional binds
append a versioned internal payload encoded with Unicode tag characters, which
are default-ignorable in legacy presentation. Project-only options are removed
before `hl.bind`. Super+K decodes the payload, rejects malformed or unknown
versions, and fails closed for unknown capabilities. The `local-dictation`
capability consumes the already-validated `SystemComponentsActions.installed`
projection and performs no marker inspection, per-row process launch, or poll.

## ADR-037: Normalize DF2 distribution manifests without an installer

**Status:** Accepted
**Date:** 2026-09-22
**Implementation:** Phase 1 manifests and deterministic validation; the later
managed-file executor is recorded separately in ADR-038

Package role, default-install policy, component membership, artifact ownership,
and service activation policy are separate machine-readable concerns. The
versioned TOML manifests under `packages/` and `deployment/` are their canonical
authorities. They contain intent rather than package versions or dependency
resolution; pacman remains authoritative for dependencies.

The default Alpha includes required packages, the `base-devel` and `git`
bootstrap prerequisites, the sole approved AUR exception `yay`, and the
recommended `pavucontrol` and `bluez-utils`. Printing is a non-default
recommended component. Dictation and the native Zig Screensaver payload remain
optional, while their project managers are baseline managed content.

Ownership v2 makes future executor permission explicit. Vanilla-managed bytes
may be replaced only after staging and validation. Machine and user seeds are
create-once. User, backend, generated, runtime, package-owned, optional-payload,
and adopted privileged state each retain separate semantics. Development may
use repository symlinks; installed mode requires regular files and no runtime
checkout dependency.

Initial Alpha supports a documented fresh Arch Linux x86_64 or
archinstall-derived base, not arbitrary desktop adoption. A local Git clone is
the initial source acquisition path, but installed runtime layout remains
compatible with future release archives. Vanilla update never silently runs a
full Arch upgrade or an unsupported partial upgrade.

The future mpv and MIME configuration files are
create-once user-owned seeds and are not created in Phase 1. Exact seed content
and deployment remain Phase 3 work.

## ADR-038: Deploy managed user files through staged generations

**Status:** Accepted
**Date:** 2026-09-22
**Implementation:** DF2 Phase 2 managed-file core

The first executable distribution layer consumes `ownership-v2.toml` and may
act only on `VANILLA_MANAGED` user artifacts. An internal standard-library
Python command provides shared plan, install, update, and validate behavior;
it is not a public session command or a full installer.

Installed content uses regular files, explicit manifest modes, private
same-filesystem staging, fsync, and Linux atomic rename exchange for updates.
A minimal mode-0600 backend-owned JSON record stores declarative managed
targets, exact entry modes/hashes, and optional release identity. This evidence
allows safe replacement and stale removal without treating matching unknown
content as owned. It contains no preferences or runtime state.

Rollback is local to the current artifact and its provenance transition.
Earlier successful artifacts may remain recorded as a resumable partial
deployment; no global machine transaction is introduced. Unknown content,
drift, symlinks, source/destination overlap, unsupported ownership classes,
and unsafe paths fail closed. Package operations, create-once initialization,
service integration, privileged adoption, and optional payload lifecycles stay
in later phases.

The provenance record also carries one minimal durable transaction intent.
Pre-commit `staging`/`prepared` recovery restores the prior generation;
post-commit `committed`/`cleaning` recovery keeps the candidate and completes
cleanup. This ordering distinguishes a killed Vanilla operation from manual
drift without weakening destination checks or introducing a general journal.
Read-only planning reports recovery as required; mutating operations recover
before starting new work.

## ADR-039: Initialize durable user state through no-clobber seeds and owners

**Status:** Accepted
**Date:** 2026-09-22
**Implementation:** DF2 Phase 3 create-once initialization core

Create-once state is not managed-release content. The internal standard-library
initializer consumes ownership v2, publishes only implemented
`CREATE_ONCE_MACHINE` and `CREATE_ONCE_USER` files with atomic no-clobber
semantics, and treats any safe existing regular file as user authority. It never
compares an existing file to a seed as permission to overwrite, merge, repair,
or delete it.

A minimal durable intent exists only during one seed publication. It permits
safe candidate cleanup and restart after abrupt termination but stores no
preferences and grants no future overwrite authority. Read-only planning
reports incomplete intent; initialization recovers before new mutation.

XDG user directories remain owned by `xdg-user-dirs-update`. Appearance owns
its preference, starter-wallpaper completion receipt, and user copies. Power &
Idle owns its preference and generated fragment. Phase 3 calls narrow offline
owner interfaces rather than duplicating those schemas or contacting live
Hyprland/hypridle. Text Size, Bluetooth power, and launcher state remain lazy
because their fresh-state behavior already has safe defaults.

The mpv and MIME seeds become user-owned immediately. MIME seeding is also
suppressed by existing user configuration in any standards-defined XDG user
location. Package installation, system services, privileged adoption, optional
components, and complete installer orchestration remain later phases.

## ADR-040: Integrate the fresh Arch system through explicit root and user boundaries

**Status:** Accepted
**Date:** 2026-09-22
**Implementation:** DF2 Phase 4; deterministic and disposable GNOME Boxes VM
acceptance complete

The installer-internal system stage consumes the package, service, and
ownership manifests and exposes plan, apply, and validate without becoming the
full installer. Production plan, apply, and validate run as root with one
explicit non-root target user so private system provenance remains
authoritative. Official package, adopted `/etc`, system Flatpak, and systemd
enablement operations stay privileged; the approved yay Git/makepkg path always
runs as that target user through a fixed argument-vector privilege drop.

Arch sync databases are never refreshed independently. Pending upgrades from
the current database block provisioning and defer the full `pacman -Syu` to the
administrator. Pacman owns package transactions and PKGBUILD metadata owns
yay-specific dependency discovery; no Vanilla package rollback or recursive
AUR resolver is introduced.

BlueZ adoption requires pacman-native proof of an unmodified package backup
file, an exact private root backup, and durable provenance. Unknown
administrator content fails closed. Service changes have their own prior-state
transaction and recovery; packages, BlueZ, Flatpak, and services deliberately
do not share a fictitious global rollback.

The existing Flatpak helper remains the system-Flathub mutation owner. Phase 4
changes only manifest-declared system-unit enablement and neither starts units
nor touches user-unit state. Destructive acceptance belongs only in a
user-created, snapshotted disposable Arch x86_64 VM, never the development
host.

## ADR-041: Use an explicit single-user SDDM theme for first login

**Status:** Accepted
**Date:** 2026-09-22
**Implementation:** DF2 Phase 5 Slices 1–3; fresh-install VM acceptance passed

Ly 1.4.1 cannot provide the accepted password-only scene without a maintained
custom package: its username and session rows are structurally present, and
its terminal renderer cannot display the canonical SVG as a graphical asset.
The baseline therefore uses SDDM's normal X11 greeter with a
Vanilla-owned Qt 6 theme to launch one direct Hyprland Wayland session. UWSM,
autologin, PAM customization, and SDDM's experimental Wayland greeter remain
out of scope.

The v1 theme receives an installer-resolved target username and exact Vanilla
session desktop-file path through SDDM's adjacent user theme configuration.
It never renders the username or a session chooser and does not depend on
remembered SDDM state. Session selection resolves exactly one absolute `file`
role from SDDM's session model before calling `sddm.login`; missing or
ambiguous configuration fails closed.

Slice 1 establishes generic theme and desktop-entry sources. Slice 2 adds the
root-only provenance-backed publisher and generated machine binding under the
new `VANILLA_MANAGED_SYSTEM` ownership boundary. Slice 3 extends that payload
to the X11/theme drop-in and makes SDDM the sole package/service baseline.
Unsupported pre-existing display-manager state fails closed.
The detailed contract and remaining integration boundaries are documented in
[DF2 Phase 5 SDDM login](phase-5-sddm-login.md).

## ADR-042: Keep public installation a thin exact-source orchestrator

**Status:** Accepted
**Date:** 2026-09-23
**Implementation:** repository-root `install.sh`; focused mocked orchestration tests

The public post-install entry point runs as the normal target user and acquires
an exact-commit GitHub source archive with curl, so a fresh Arch Minimal system
does not need Git merely to obtain Vanilla. The moving `main` ref is permitted
only for Alpha development; release instructions must use a pinned tag. The
wrapper reports the requested ref, resolved commit, and archive digest, then
removes its private temporary source after completion.

The wrapper contains no package, artifact, service, create-once, SDDM, yay,
BlueZ, or Flatpak inventory. It delegates in dependency order to the existing
pre-Python bootstrap, privileged system integration, non-root managed
deployment, and create-once initializer. One confirmation authorizes the
complete plan/apply chain; `--yes` suppresses only that prompt. Success requires
the authoritative managed, create-once, and privileged system validations,
with SDDM validation retained inside the system contract. Reboot is never
automatic.

Managed deployment exposes the `reconcile` boundary used by the wrapper:
absence of provenance selects fresh `install`, valid complete provenance
selects `update`, and partial provenance retains its recorded operation. The
shell never parses or guesses provenance, while malformed or drifted ownership
continues to fail closed in the Python authority.
