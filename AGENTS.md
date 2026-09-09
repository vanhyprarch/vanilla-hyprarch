# Vanilla HyprArch

## Project purpose

Vanilla HyprArch is a minimal, incremental configuration layer for a standard
Arch Linux installation using upstream Hyprland and Quickshell as its desktop
UI. It is not a separate distribution. Prefer small, understandable changes,
official Arch packages, and few dependencies. The repository is the canonical
source of truth; every project workaround should remain auditable and
removable.

## Read before modifying

Start with [current state](docs/current-state.md), then read only the deeper
documents relevant to the task:

- [Architecture decisions](docs/decisions.md)
- [System baseline](docs/system-baseline.md)
- [Installation strategy](docs/installation-strategy.md)
- [Compatibility and upstream workarounds](docs/compatibility.md)
- [Power & Idle backend](docs/power-idle-backend.md)
- [Screensaver lifecycle](docs/screensaver-lifecycle.md)
- [Project history](docs/project-history.md)

Do not copy whole sections between documents or rewrite unrelated records.

## Critical architecture invariants

- Hyprland configuration is Lua, not legacy `.conf` syntax. Use locally
  verified Hyprland Lua APIs where required; do not assume legacy `hyprctl`
  keyword or dispatcher forms work.
- Quickshell screen-bound UI stays under
  `Variants { model: Quickshell.screens }` with a per-screen `Scope`. This fixed
  dock/frame disappearance after suspend and resume and must not regress.
- The Power & Idle backend is the state authority. QML presents and invokes it;
  QML does not persist a second copy of its state.
- Hyprland directly owns and launches exactly one hypridle process. The
  packaged `hypridle.service` remains disabled and inactive.
- Caffeine is XDG runtime state. It suppresses automatic actions without
  overwriting saved Power & Idle preferences.
- Screensaver rendering and keyboard/pointer input absorption belong to the
  independent GPL-2.0-only `vanhyprarch-zig-player` executable. Do not
  recreate, copy, or vendor its Zig implementation here, add a local input
  workaround, or patch an upstream package to integrate it.
- `vanhyprarch-screensaver` owns only the exact native player process it started
  and the cursor state it changed. Preserve PID, start-time, executable,
  argument, runtime-owner, and cursor validation; never signal by process name.
  The main Quickshell must remain independent.
- Player release versions, assets, source links, architectures, and checksums
  are pinned installation inputs. Update them only as one deliberate, reviewed
  change with matching validation.
- Do not put personal names or absolute `/home/USERNAME` paths in tracked
  content. Use `$HOME`, `~`, XDG paths, or installer-resolved locations.
- Do not add `jq` merely for convenience. Official Arch repositories are the
  default. `yay` is the one explicit AUR/bootstrap exception; its presence does
  not authorize other AUR dependencies. Any additional exception must be
  indispensable and explicitly justified.

## Installation reproducibility

The canonical docs and manifests are the operational specification for one
future bootstrap with two entry points: during archinstall, for a configured
first reboot, and after a fresh minimal Arch installation. Keep the archinstall
integration thin; do not duplicate bootstrap logic or encode machine-specific
devices, users, homes, graphics choices, or secrets in a public preset. A
feature is not fully integrated if its packages, configuration, services,
commands, deployment, startup ownership, defaults, ordering, migration, and
validation are not represented in the repository. Consult the
[installation strategy](docs/installation-strategy.md) and
[system baseline](docs/system-baseline.md). Official repositories remain the
default; `yay` remains the sole explicit AUR exception unless another
indispensable dependency is approved and documented.

## Workflow rules

- Inspect the relevant code, documentation, live ownership, and version facts
  before editing.
- Make the smallest scoped change and one architectural change at a time.
- Preserve known-good live state during diagnostics. Prefer isolated,
  runtime-only probes with harmless actions.
- Never run fullscreen or input-sensitive screensaver tests on an active
  desktop without explicit approval and an independent bounded failsafe.
- Do not stage or commit unless the user explicitly requests it.
- Run `git --no-pager diff --check` before proposing a commit.
- Never silently rewrite unrelated user settings to make a requested value fit.
- Live configuration changes must fail closed, preserve exact rollback
  material, validate targets and ownership before signalling, and verify the
  replacement state.
- Document version-specific workarounds with evidence and a condition for
  retesting or removing them.

## Validation expectations

Validation should be proportional to the change. Relevant checks include:

- native Quickshell reload and final log health when main-shell QML changes;
- named IPC calls when IPC changes;
- deterministic `vanhyprarch-idle status` output;
- exactly one direct Hyprland-owned hypridle and expected listener counts;
- owned native-player status and exact cursor restoration;
- shell syntax, parser, render, and safe mock tests;
- `git --no-pager diff --check` and a scoped status/diff review.

Do not trigger DPMS, suspend, locking, or fullscreen UI merely to validate an
unrelated edit.

## Compatibility and upstream workarounds

Consult [docs/compatibility.md](docs/compatibility.md) before changing code
around known upstream-version behavior. Every workaround must record:

- affected component and validated version;
- observed behavior;
- evidence or a reproducible test;
- the local mitigation and its scope;
- the upgrade or upstream condition that permits removal or requires retest.

Do not leave compatibility code undocumented or carry an obsolete workaround
forward without retesting it.
