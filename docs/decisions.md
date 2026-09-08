# Vanilla HyprArch architecture decisions

This file contains durable architectural and product decisions. It is not a
development diary; implementation status belongs in `current-state.md` and
historical milestones belong in `project-history.md`.

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

Official Arch packages are preferred. AUR packages are acceptable only when a
required capability has no suitable official package and the reason is
documented.

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

The project will provide an understandable, auditable bootstrap path from a
fresh minimal Arch installation. The future installer should install the
declared packages, deploy project configuration, enable only required services,
and validate the resulting Hyprland session.

The installer must account for hardware-dependent choices rather than copying
development-machine monitor or GPU settings blindly.

## ADR-006: Use the `vanhyprarch` namespace

**Status:** Accepted
**Date:** 2026-09-08

The named Quickshell configuration and application state namespace are
`vanhyprarch`. Current IPC targets are:

- `vanhyprarch.shell`
- `vanhyprarch.shortcuts`

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
- Papirus for shell icons

The shell declares Papirus through its root icon-theme pragma. System-control
icons use Papirus full-color assets where appropriate; tray icons may be tinted
with the shell accent. Missing icons should be addressed through the icon policy
rather than by embedding arbitrary unlicensed assets.

`file-roller` is a desktop convenience, not a core shell or runtime dependency.
It is excluded from the core baseline and may be reconsidered only as part of a
future optional or recommended package set. BlueZ remains the Bluetooth backend;
`blueman` is excluded from the core baseline while the future Bluetooth UX
remains undecided.

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

**Status:** Accepted
**Date:** 2026-09-08

Ly is the selected display manager and runs through `ly@tty2.service` on tty2.
The competing getty on tty2 is disabled. Ly's validator is `ly-dm`.

The display manager is session infrastructure; its animation implementation is
not itself a user-session screensaver.

## ADR-012: Exclude hibernate from the UX

**Status:** Accepted
**Date:** 2026-09-08

Hibernate is not a supported user-facing power action. The current power menu
offers lock, suspend, reboot, and power off. Future Power & Idle work must not
reintroduce hibernate as an idle stage or menu action without a new decision.

## ADR-013: Power & Idle has three ordered stages

**Status:** Accepted
**Date:** 2026-09-08
**Implementation:** Pending

The future Power & Idle control has three independently selectable stages:

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
**Implementation:** Pending

One radio-style selection associates automatic session locking with the screen
saver, display-off, or suspend stage. A stage set to `Never` cannot own locking.
This supersedes the earlier idea of a separate lock timeout or independent lock
toggles.

- Lock at screen saver: leaving the saver requires `hyprlock` authentication.
- Lock at display-off: the saver is dismissible, but wake from display-off
  presents `hyprlock`.
- Lock at suspend: earlier stages remain unlocked; resume presents `hyprlock`.

## ADR-015: Generate a managed hypridle fragment

**Status:** Provisional
**Date:** 2026-09-08
**Implementation:** Static source structure and Phase 2B test fragment prepared;
production generation pending

The preferred direction is a mostly static `hypridle.conf` that sources a
generated `vanhyprarch-idle.conf`. The generated fragment, not parallel JSON,
would be the source of truth for selected listeners. Phase 2B uses this
structure with temporary 9- and 10-second, no-lock listeners only to validate
hypridle lifecycle calls; it does not establish production defaults.

Updates must be atomic and followed by restart and verification, with rollback
on failure. A systemd user service is the preferred candidate for making one
process the unambiguous owner of hypridle.

This remains provisional because the complete listener model must be reviewed
against the final lock semantics and the real screensaver lifecycle before
implementation.

## ADR-016: Prototype Ly colormix as the screensaver

**Status:** Provisional
**Date:** 2026-09-08
**Implementation:** Isolated PoC and Phase 1 controller implemented; Phase 2B
test integration prepared

Ly's `colormix` animation is the preferred screensaver candidate, but it is not
accepted as the production screensaver yet. An isolated proof of concept has
validated this candidate architecture:

`Hyprland -> fullscreen Foot window -> lightweight standalone colormix renderer`

The renderer reproduces the relevant Ly algorithm while respecting its license
and attribution requirements. Its current PoC default is 33 milliseconds,
approximately 30 fps, with animation movement normalized to Ly's 5-millisecond
reference. This is a measured PoC choice, not an immutable architectural
requirement.

Production lifecycle, input exit, fullscreen presentation, and process cleanup
must still be validated in their integrated context. The Phase 2B hypridle
listeners are temporary, have no locking behavior, and are not a production
integration. No Quickshell integration has been implemented.

The provisional lifecycle boundary is a single
`vanhyprarch-screensaver start|stop|status` interface. Its controller owns only
a dedicated Foot process, validates ephemeral XDG runtime state against Linux
process identity before signalling, and leaves the command API open to future
multi-output ownership.

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
