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
- keyboard-and-mouse Super+Space Apps, Install, Remove Package, Update,
  Additional system components, and Power workflows with native catalogs and
  visible terminal transactions;
- official Arch package manifests and a pinned, checksummed Zig Player
  installer component;
- required, unpinned Flatpak from the official Arch repositories, with an
  idempotent bootstrap component for the required system Flathub remote;
- optional, offline F9 push-to-talk dictation managed through Additional system
  components using verified upstream Voxtype 1.0.1, the default English-only
  `small.en` model, a two-minute recording maximum, and official-repository
  `wtype`.

## Installation status

The shared automated bootstrap and optional archinstall entry point are not
finished. Development starts from a working minimal Arch installation and the
package manifests in [`packages/`](packages/), but tracked configuration must
currently be reviewed and deployed manually.

The repository now separates managed portable Hyprland configuration from
create-once machine configuration and a user-owned customization override.
That repository structure has not yet been migrated onto the development
machine. The tracked BlueZ `main.conf` is also a complete system-file
replacement and must not overwrite an existing administrator configuration
without review and rollback. See the
[deployment ownership contract](docs/deployment-ownership.md),
[installation strategy](docs/installation-strategy.md), and
[system baseline](docs/system-baseline.md).

For development, public commands may be symlinked from `bin/` into
`$HOME/.local/bin`. The future production bootstrap will install regular
executables there atomically and will not depend on a Git checkout.

Dictation is a separate opt-in component, not part of the baseline. Its
installer, dependencies, exact verification chain, runtime activation, and
clean-uninstall procedure are documented in
[Local push-to-talk dictation](docs/dictation.md). The default uses CPU,
English-only, local/offline transcription: hold F9 to record and release it to
transcribe and type through `wtype`.
The independently deployed `vanhyprarch-dictation` manager remains available
when Voxtype is absent, so Super+Space can report state and offer installation.
It exposes ten reviewed Whisper models, curated language choices, and recording
limits of 30, 60, 120, or 300 seconds. SuperSpace offers explicit CPU and
Vulkan GPU choices through the same transactional backend. CPU remains the
public default, Vulkan is never selected automatically, and a Vulkan change
succeeds only after verified runtime evidence for the selected vendor.
Local Dictation uses clean uninstall semantics: removing it deletes Voxtype's
configuration and every downloaded speech model, but keeps the Vanilla manager
available so the component can be installed again later.

## Alpha limitations

Vanilla HyprArch Alpha releases are for testing and feedback, not
production-stable use. Ownership boundaries now exist, but clean installation,
first-reboot deployment, live migration, project self-update, and complete
rollback machinery do not. User-owned files are preserved by ownership class;
their Alpha interfaces may still change with release-note disclosure and
practical migration guidance.

Portable Hyprpaper and wallpaper integration remain future work. The Zig
Screensaver's move to an optional Additional system component is also deferred;
current runtime behavior still expects it. The pinned player release is
x86_64-focused, physical multi-monitor acceptance and parts of the Bluetooth
hardware/pairing matrix remain pending, while Super+Space Remove Application
and Vanilla HyprArch self-update are not implemented. See
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
