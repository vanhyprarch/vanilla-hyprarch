# Vanilla HyprArch

> **Status: Alpha / Work in progress.** The repository is currently for
> development and testing; it is not yet a copy-and-run installer payload.

Vanilla HyprArch is a small, incremental desktop configuration layer for a
standard Arch Linux installation. Its philosophy is **Arch vanilla + Hyprland
vanilla + small independent components**: it does not fork or patch Arch,
Hyprland, Quickshell, systemd, BlueZ, or other upstream projects.

## Architecture

The graphical session is direct:

```text
Ly -> /usr/bin/start-hyprland -> Hyprland
```

UWSM is not part of the architecture. Hyprland owns the session and starts the
required session processes. Quickshell provides the desktop UI. Power & Idle
state belongs to `vanhyprarch-idle`, while Hyprland directly owns one
`hypridle` process.

The graphical session prepends `$HOME/.local/bin` exactly once to its inherited
`PATH`. Public `vanhyprarch-*` session commands are installed there and invoked
by name; helpers private to Quickshell remain at
`Quickshell.shellDir/helpers`, while fixed system dependencies may use explicit
`/usr/bin/...` paths.

Screensaver rendering is delegated to the independent
[Vanilla HyprArch Zig Player](https://github.com/vanhyprarch/vanhyprarch-zig-player).
This repository provides a pinned installer component and lifecycle control
for the separately released executable; it does not vendor or duplicate the
player's source. The player owns native layer-shell presentation and input
absorption. The pinned integration uses release `v0.1.1` and offers ColorMix,
Matrix, Doom, and Game of Life.

## Implemented

- per-screen dock and desktop frame with launchers, workspaces, tray, clock,
  theme and power controls;
- native Quickshell audio, NetworkManager Wi-Fi, and BlueZ Bluetooth controls;
- DDC/CI brightness and development-machine scale presets;
- persistent Power & Idle preferences, Caffeine, automatic locking, display
  power-off, suspend/resume, and the independent native screensaver;
- direct-session PolicyKit and clean Hyprland logout integration;
- Print Screen smart region/window/monitor screenshots saved under
  `Pictures/Screenshots` and copied as `image/png` for normal Ctrl+V pasting;
- keyboard-and-mouse Super+Space Apps, Install, Remove Package, Update, and
  Power workflows with native catalogs and interactive package-manager
  transactions;
- official Arch package manifests and a pinned, checksummed Zig Player
  installer component.
- required, unpinned Flatpak from the official Arch repositories, with an
  idempotent bootstrap component for the required system Flathub remote.

## Installation status

The shared automated bootstrap and optional archinstall entry point are not
finished. Development starts from a working minimal Arch installation and the
package manifests in [`packages/`](packages/), but tracked configuration must
currently be reviewed and deployed manually.

In particular, the tracked Hyprland monitor and keyboard configuration is a
development-machine profile, not a portable default. The tracked BlueZ
`main.conf` is also a complete system-file replacement and must not overwrite
an existing administrator configuration without review and rollback. See the
[installation strategy](docs/installation-strategy.md) and
[system baseline](docs/system-baseline.md).

For development, public commands may be symlinked from `bin/` into
`$HOME/.local/bin`. The future production bootstrap will install regular
executables there atomically and will not depend on a Git checkout.

## Alpha limitations

Clean-install and first-reboot validation, portable monitor/Hyprlock/Hyprpaper
configuration, final light/dark wallpaper integration, and an update-safe user
override layer remain future work. The pinned Zig Player release is currently
x86_64-focused, physical multi-monitor acceptance and parts of the Bluetooth
hardware/pairing matrix remain pending, while Super+Space Remove Application
and Vanilla HyprArch self-update and local F9 push-to-talk dictation are not
implemented. Physical multi-monitor screenshot behavior remains pending.
Project self-update remains unavailable until a MANAGED / USER OVERRIDE / STATE
deployment architecture exists. The detailed status and roadmap are in
[current state](docs/current-state.md).

Architecture decisions, compatibility evidence, and version-specific retest
conditions are maintained under [`docs/`](docs/). Arch package versions there
are tested rolling-release snapshots, not dependency locks; explicitly pinned
external artifacts are the exception.

## License

Project-authored Vanilla HyprArch material in this repository, including
historical project-authored revisions, is licensed under GPL-2.0-only. Files or
material explicitly carrying separate third-party licensing or attribution
remain under those terms. The external player is an independent GPL-2.0-only
project with its own license and third-party notices.
