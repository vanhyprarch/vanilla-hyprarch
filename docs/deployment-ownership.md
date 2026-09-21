# Deployment ownership

This document defines the first Vanilla HyprArch deployment ownership
contract. It describes who may change an artifact and what normal project
updates must preserve. It does not define an installer, updater, deployment
ledger, rollback engine, or migration framework.

The machine-readable representation is
`deployment/ownership-v1.toml`. Its target strings are descriptive XDG path
expressions, not shell commands.

## Ownership classes

| Class | Authority and update rule |
| --- | --- |
| `MANAGED` | Vanilla HyprArch supplies the authoritative bytes and may replace them during a reviewed project update. Users are not expected to edit deployed copies. |
| `MACHINE_CONFIGURATION` | The file describes actual hardware or user-environment reality. Vanilla HyprArch may initialize it once, but normal updates preserve it. Users may edit it; project UI may edit only explicitly documented fields. |
| `USER_CUSTOMIZATION_OVERRIDE` | An optional advanced escape hatch owned by the user. It is unnecessary for the curated default experience and is preserved by normal updates. |
| `PERSISTENT_STATE_PREFERENCE` | Durable user selection or backend state. Its owning backend, not release payloads, controls its format and writes. It is not a configuration override. |
| `PERSISTENT_STATE_PROVENANCE` | Durable backend-owned initialization/provenance state. It may retain historical seed hashes for migration, but is not a user preference or release payload. |
| `GENERATED` | An effective projection derived from managed policy and preserved preferences. Release payloads do not own its bytes; its generator may replace it. |
| `RUNTIME` | Session- or process-lifetime state. It is neither a release payload nor durable preference. |
| `USER_CONTENT` | User-owned content that Vanilla may seed non-destructively. Updates preserve user additions and modifications and never manage the containing directory wholesale. |
| `OPTIONAL_COMPONENT_PAYLOAD` | Files present only when the named optional component is installed. They are not unconditional baseline payloads. |
| `SYSTEM_ADOPTED_MANAGED` | A system-level file that becomes managed only through an explicit administrator adoption boundary with separate validation and rollback work. |

`MACHINE_CONFIGURATION`, `USER_CUSTOMIZATION_OVERRIDE`, and
`PERSISTENT_STATE_PREFERENCE` are intentionally distinct. Machine
configuration records facts and choices such as connectors, modes, scale,
color handling, keyboard layout, and device rules. A customization override
allows an advanced user to supersede selected curated project behavior. A
persistent preference records a user selection such as an idle timeout and is
written through its owning backend.

## Create-once seeds

Files below `seeds/` are installation inputs, not normal managed-update
payloads. A future deployment step may copy a seed only when its target does
not exist. Once created, the target takes the ownership class declared in the
manifest and normal updates preserve it. The live machine and override files
are private user configuration with mode `0600`.

The Hyprland machine seed contains one portable catch-all monitor rule. Any
output without a more specific machine rule uses its preferred mode, automatic
position, and automatic scale. This fallback is machine-owned and is not a
Monitor panel write target. It is a valid configuration indefinitely and is
never materialized by installation, session start, hotplug, inspection, or
panel open.

The integrated Monitor panel writes no configuration itself. Its backend may,
only after the explicit **Enable advanced display settings** action, clone one
supported fallback block into a connector-specific rule while changing only
the empty output selector. That persistence-only transaction preserves the
fallback and its `preferred`/`auto`/`auto` intent, proves complete topology
equality, and rolls back exact bytes on failure. Later Mode, Scale, or bitdepth
edits specialize only their owned field in that explicit rule. The public seed
contains no connector, fixed mode or scale, keyboard layout, bit depth, color
profile, device rule, or UI-owned scale field. No general multi-monitor schema
is promised during Alpha. The override seed contains only its administrative
header.

Monitor transaction journals are versioned same-boot recovery material, not
managed deployment payloads. Never replace `vanhyprarch-monitor` while an
older-schema transaction is nonterminal or recovery-required. A schema upgrade
must use the old deployed helper to establish a terminal, recovery-disarmed
journal, an unheld lock, and no active control listener. Controlled deployment
may then remove that old terminal runtime journal before installing the new
helper into clean runtime state. Unknown journal schemas otherwise fail closed;
normal deployment must not infer compatibility or delete active recovery data.

## Hyprland configuration order

The managed entrypoint resolves `HOME`, then resolves `XDG_CONFIG_HOME` with
the `$HOME/.config` fallback. A non-empty `XDG_CONFIG_HOME` must be absolute.
It uses Hyprland's explicit absolute-path `require()` support in this order:

1. managed portable core;
2. managed curated bindings;
3. machine configuration;
4. user customization override.

Each file is a separate Lua chunk. Locals remain private to their chunk;
undeclared globals can still leak and therefore are avoided. Vanilla HyprArch
does not expose a project-global Lua API for overrides.

## Generated and runtime Power & Idle files

`power-idle.conf` is the persistent preference authority.
`vanhyprarch-idle.conf` is a mode-0600 generated projection and has no release
source. `vanhyprarch-idle session-start` creates or replaces that projection
from preserved preferences with Caffeine off before directly executing
hypridle. Caffeine itself remains session runtime state under
`XDG_RUNTIME_DIR` and never overwrites the preference.

## Appearance preference and renderer ownership

`appearance.json` is a `PERSISTENT_STATE_PREFERENCE` written only by
`vanhyprarch-appearance`. It stores the desired mode and relative Light/Dark
wallpaper selections. The managed `hyprpaper.conf` contains renderer policy but
no user selection. Hyprpaper's process, IPC state, and active wallpaper are
effective external state, not preference storage. Appearance runtime locking,
bounded restart suppression, and renderer logging stay under
`XDG_RUNTIME_DIR/vanhyprarch`.

The eight GPL-2.0-only files under `assets/wallpapers/` and their deployed XDG
data copies are `MANAGED` distribution payload. The copies seeded beneath
`<XDG Pictures>/Wallpapers/Light` and `Dark` are `USER_CONTENT`; their parent
directories and every file in them become user-owned immediately after the
one-shot bootstrap. Normal updates never manage those directories wholesale or
inject, replace, restore, or remove their contents.

The private mode-0600 `appearance-assets.json` record is
`PERSISTENT_STATE_PROVENANCE`, not an Appearance preference. Its version-2
schema records that starter content initialization completed and may retain
historical version-1 seed hashes solely for compatibility and audit. A
version-1 receipt, or an existing Appearance preference when that receipt is
absent, migrates to initialized without touching user content. Only a user with
no such durable evidence receives the currently distributed starter set.

## System keyboard synchronization ownership

`$HOME/.local/bin/vanhyprarch-keyboard-sync` and its static systemd user unit
are `MANAGED` payload. Hyprland owns service startup and reload reconciliation;
the unit is not enabled independently. `systemd-localed` owns the durable
graphical XKB tuple, while the helper owns only its validated runtime projection
into Hyprland.

The project does not own `/etc/vconsole.conf`,
`/etc/X11/xorg.conf.d/00-keyboard.conf`, locale1 state, active layout groups, or
per-device input rules. The create-once machine file remains
`MACHINE_CONFIGURATION`; the validated development-machine file contains no
global XKB fallback. Explicit per-device exceptions may remain machine- or
user-owned without becoming synchronizer state.

## Monitor Safe Apply ownership

`$HOME/.local/bin/vanhyprarch-monitor` and the static, non-enabled
`vanhyprarch-monitor-safe-apply.service` are `MANAGED`. The helper is the sole
authority for one bounded transaction; Quickshell is a deployed client and owns
no duplicate countdown or candidate state. Its journal, lock, and control
socket are private `RUNTIME` recovery material under `XDG_RUNTIME_DIR`, not a
persistent preference.

Confirmed monitor preference belongs only in the existing
`MACHINE_CONFIGURATION` file. The production Confirm path uses the tested
exact-byte replacement, prospective verification, reload reconciliation, and
recovery machinery. Mode and bitdepth durable Confirm plus immediate Scale
persistence have completed controlled single-monitor live acceptance through
the deployed UI. Forced HDR retains its base CM intent in one adjacent,
strictly owned machine-profile marker; global Automatic HDR uses one narrowly
owned machine block. Neither uses the user override or a second preference
database. The helper never changes the create-once seed, portable
fallback block, managed Hyprland files, or user override. The optional
materialization capability is published and explicit-profile deployment is
accepted, but real fallback materialization is not yet physically accepted;
physical multi-monitor acceptance also remains deferred.

## PolicyKit session lifecycle ownership

`$HOME/.local/bin/vanhyprarch-polkit-session` and the
`hyprpolkitagent.service.d/10-vanhyprarch-session-lifecycle.conf` user drop-in
are `MANAGED` payload. They own ordered start and graceful logout stop for the
real direct Hyprland session. The official package continues to own the base
`/usr/lib/systemd/user/hyprpolkitagent.service` unit and agent executable;
Vanilla neither copies nor edits that package file.

## Zig Screensaver ownership

`$HOME/.local/bin/vanhyprarch-screensaver`, its private Python implementation,
and canonical v0.1.1 verification metadata are baseline `MANAGED` artifacts.
The player binary, license, notices, README, installed release record, and
mode-0644 marker are `OPTIONAL_COMPONENT_PAYLOAD`. Their sole lifecycle and
marker authority is `vanhyprarch-screensaver`; QML only consumes its strict
status. Runtime PID, cursor, log, and component lock records remain under
`$XDG_RUNTIME_DIR/vanhyprarch/` and are not deployment payload.

A Zig-specific mode-0600 install receipt may exist there only while recovering
an interrupted fresh publication. It proves cleanup authority solely for
canonical objects created by that operation, is not a durable deployment
ledger, and is removed after success or handled rollback.

The player remains at the intentional public-command location
`$HOME/.local/bin`. All optional data paths and the immutable resource directory
respect `XDG_DATA_HOME`, falling back to `$HOME/.local/share`; preferences and
the generated idle fragment independently respect `XDG_CONFIG_HOME`.

## Alpha compatibility contract

Vanilla HyprArch is Alpha. Public Alpha releases are intended for testing and
feedback and are not production-stable releases. User-owned files are
preserved according to this ownership contract. Preserving an override file
does not promise stability for every symbol, property, format, or internal
interface referenced by that file.

Justified breaking changes remain possible during Alpha. Known breaking
changes should be identified in release notes, with migration guidance where
reasonably practical. Alpha is not permission for careless changes: evidence,
small reviewed changes, explicit ownership, and avoidance of unnecessary
breakage remain project principles. Compatibility expectations may become
stricter in Beta. Future architectural quality takes priority over preserving
immature Alpha interfaces indefinitely.
