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
| `GENERATED` | An effective projection derived from managed policy and preserved preferences. Release payloads do not own its bytes; its generator may replace it. |
| `RUNTIME` | Session- or process-lifetime state. It is neither a release payload nor durable preference. |
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
manifest and normal updates preserve it.

The Hyprland machine seed contains one portable catch-all monitor rule. Any
output without a more specific machine rule uses its preferred mode, automatic
position, and automatic scale. This fallback is machine-owned and is not a
Monitor panel write target; it exposes no project-owned scale token.

A future Monitor panel may edit only an explicitly documented scale field in a
specific explicit output profile in the machine-owned file. The controlled
development-machine migration will establish that profile separately; the
public seed contains no connector, fixed mode or scale, keyboard layout, bit
depth, color profile, or device rule. No general multi-monitor schema is
promised during Alpha. The override seed contains only its administrative
header.

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
