# Vanilla HyprArch

> **Current stable release: [v1.0.1](https://github.com/vanhyprarch/vanilla-hyprarch/releases/tag/v1.0.1).**
> **Original v1.0.0 users: follow the [complete one-time updater preparation and
> upgrade guide](docs/upgrade-v1.0.0-to-v1.0.1.md) before using Update.**
> Fresh v1.0.1 installations and already prepared systems must not repeat the bridge.

Real v1.0.0 -> v1.0.1 upgrade and reboot acceptance passed on the existing Proxmox
VM: signed ServerPlan fallback with GitHub HTTP 404, exact-target recovery after
Arch mirror failure, zero migrations, preserved settings and working desktop.
Stable source/tag remains `83bfeaa627392817c21b29ce73557a32f5ad563e`; newer
documentation on `main` does not change its immutable archive.

Vanilla HyprArch is a small, incremental desktop configuration layer for a
standard Arch Linux installation. Its philosophy is **Arch vanilla + Hyprland
vanilla + small independent components**: it does not fork or patch Arch,
Hyprland, Quickshell, systemd, BlueZ, or other upstream projects.

## Architecture

The graphical session is direct:

```text
SDDM X11 greeter -> Vanilla password-only theme -> /usr/bin/start-hyprland -> Hyprland/Wayland
```

UWSM is not part of the architecture. Hyprland owns the session and starts the
required session processes. Quickshell provides the desktop UI. Power & Idle
state belongs to `vanhyprarch-idle`, while Hyprland directly owns one
`hypridle` process. Appearance state belongs to `vanhyprarch-appearance`, while
Hyprpaper is only its session-owned wallpaper renderer. Graphical XKB state
belongs to `systemd-localed`; the managed keyboard helper projects it into
Hyprland without owning active groups or per-device rules.

The graphical session prepends `$HOME/.local/bin` exactly once to its inherited
`PATH`. Public `vanhyprarch-*` session commands are installed there and invoked
by name; helpers private to Quickshell remain at
`Quickshell.shellDir/helpers`, while fixed system dependencies may use explicit
`/usr/bin/...` paths.

Optional screensaver rendering is delegated to the independent
[Vanilla HyprArch Zig Player](https://github.com/vanhyprarch/vanhyprarch-zig-player).
The baseline always provides `vanhyprarch-screensaver`, while the player is the
opt-in **Zig Screensaver** component. This repository provides pinned component
lifecycle control
for the separately released executable; it does not vendor or duplicate the
player's source. The player owns native layer-shell presentation and input
absorption. The pinned integration uses release `v0.1.1` and offers Color Mix,
Matrix, Doom, and Game of Life.

## Implemented

- per-screen dock and desktop frame with launchers, workspaces, tray, clock,
  theme and power controls;
- native Quickshell audio, NetworkManager Wi-Fi, and BlueZ Bluetooth controls;
- event-driven projection of systemd-localed's graphical XKB tuple into
  Hyprland, without owning active layout groups or per-device rules;
- DDC/CI brightness and development-machine scale presets;
- persistent Power & Idle preferences, Caffeine, automatic locking, display
  power-off and suspend/resume, with capability-aware support for the optional
  native screensaver;
- one Light/Dark Appearance preference coordinating the Vanilla palette,
  standard host application preference, and independently remembered Light and
  Dark wallpapers, with eight bundled 3840×2160 GPL-2.0-only Wolkenstein v2
  choices and an explicit pair-1 default;
- direct-session PolicyKit and clean Hyprland logout integration;
- Print Screen smart region/window/monitor screenshots saved under
  `Pictures/Screenshots` and copied as `image/png` for normal Ctrl+V pasting;
- keyboard-and-mouse Super+Space Apps, Install, Remove Package, Update,
  Additional system components, and Power workflows with native catalogs and
  visible terminal transactions;
- normalized package, component, ownership, and service-policy manifests plus a
  staged, rollback-capable deployment core for Vanilla-managed user files and a
  pinned, checksummed Zig Screensaver install/adopt/reinstall/uninstall lifecycle;
- required, unpinned Flatpak from the official Arch repositories, with an
  idempotent bootstrap component for the required system Flathub remote;
- optional, offline F9 push-to-talk dictation managed through Additional system
  components using verified upstream Voxtype 1.0.1, the default English-only
  `small.en` model, a two-minute recording maximum, and official-repository
  `wtype`.

## Install stable

On a fresh Arch Minimal x86_64 installation with Internet access, run these
commands as the normal target user, not root. The two downloads are the
published v1.0.1 release assets, also available on the operational ServerPlan mirror:

```bash
set -e
sudo pacman -Syu --needed curl
bundle_dir=$(mktemp -d "$HOME/vanhyprarch-v1.0.1.XXXXXXXX")
cd "$bundle_dir"
curl -fL --proto '=https' --proto-redir '=https' --tlsv1.2 -o release.json https://vanhyprarch.it/dist/v1/vanilla-hyprarch/releases/v1.0.1/assets/release.json
curl -fL --proto '=https' --proto-redir '=https' --tlsv1.2 -o vanhyprarch-v1.0.1.tar.gz https://vanhyprarch.it/dist/v1/vanilla-hyprarch/releases/v1.0.1/assets/vanhyprarch-v1.0.1.tar.gz
sha256sum -c <<'SHA256'
c5ddeeb07dfe6ceb40144a26a490df39a344940d9e9e60b18acbf8ad3885b7d1  release.json
8c349c35f1e01e57cce98d7247915742cf6c5e33dff395b7842963304b908aa5  vanhyprarch-v1.0.1.tar.gz
SHA256
tar -xzf vanhyprarch-v1.0.1.tar.gz
"$PWD/vanhyprarch-v1.0.1/install.sh" \
  --release-metadata "$PWD/release.json" \
  --release-artifact "$PWD/vanhyprarch-v1.0.1.tar.gz"
```

Authenticate the expected hashes through a trusted publisher record before
executing downloaded code; checksums from the same untrusted download do not
independently authenticate it. The installer can bootstrap Python when absent. It verifies the bundle
again before installation and commits the stable installed release identity
only after validation succeeds. Reboot afterward to enter the SDDM login.
For an existing original v1.0.0 installation, use the
[manual bridge guide](docs/upgrade-v1.0.0-to-v1.0.1.md), not these fresh-install
commands. The downloadable kit preserves the exact accepted administrative input;
its historical inner `rc1` filename does not make it a desktop release.

## Install development from main

Run this separate development command as the normal target user:

```bash
sudo pacman -Syu --needed curl && bash <(curl -fsSL https://raw.githubusercontent.com/vanhyprarch/vanilla-hyprarch/main/install.sh)
```

It resolves `main` to an exact commit, downloads that commit's source archive,
and delegates package/system integration, managed deployment, create-once
initialization, SDDM integration, and validation to their existing
authoritative stages. This path leaves installed release identity absent and
is not equivalent to the published stable installation. `install.sh --yes`
suppresses the single confirmation. `VANHYPRARCH_REF=<tag-or-commit>` selects
another simple ref; even a release tag remains a development installation when
used through this ref-based path. See [release engineering](docs/release-engineering.md).
Reruns select managed `install` or `update` through the deployment authority's
provenance-aware `reconcile` operation; create-once content remains no-clobber.

The optional archinstall entry point is not implemented. The installer does
not select hardware-specific drivers, disk layout, locale, or other base Arch
choices.

The repository now separates managed portable Hyprland configuration from
create-once machine configuration and a user-owned customization override.
The controlled live migration has placed that split architecture on the
current development machine. That migration remains separate from the
fresh-install bootstrap.
The tracked BlueZ `main.conf` is also a complete system-file replacement and
must not overwrite an existing administrator configuration without review and
rollback. See the
[deployment ownership contract](docs/deployment-ownership.md),
[managed-file deployment core](docs/managed-file-deployment.md),
[installation strategy](docs/installation-strategy.md), and
[system baseline](docs/system-baseline.md). The accepted DF2 package and
distribution decisions are summarized in
[Distribution Foundation 2](docs/distribution-foundation-2.md).

For development, public commands may be symlinked from `bin/` into
`$HOME/.local/bin`. The managed-file core can install regular executables and
complete configuration trees atomically into an isolated installed target
without retaining a source-checkout dependency. The public bootstrap
calls that core as one step in the larger installation lifecycle.

Dictation is a separate opt-in component, not part of the baseline. Its
installer, dependencies, exact verification chain, runtime activation, and
clean-uninstall procedure are documented in
[Local push-to-talk dictation](docs/dictation.md). The default uses CPU,
English-only, local/offline transcription: hold F9 to record and release it to
transcribe and type through `wtype`.
The independently deployed `vanhyprarch-dictation` manager remains available
when Voxtype is absent, so Super+Space can report state and offer installation.
It exposes ten reviewed Whisper models, true Automatic language detection or
one to three reviewed manual languages, and recording limits of 30, 60, 120,
or 300 seconds. SuperSpace offers explicit CPU and
Vulkan GPU choices through the same transactional backend. CPU remains the
public default, Vulkan is never selected automatically, and a Vulkan change
succeeds only after verified runtime evidence for the selected vendor.
Local Dictation uses clean uninstall semantics: removing it deletes Voxtype's
configuration and every downloaded speech model, but keeps the Vanilla manager
available so the component can be installed again later.

Zig Screensaver is a sibling of Local Dictation under **Additional system
components** and is not part of the baseline. Without it, Power & Idle contains
only Caffeine, Turn Off Display, Suspend, and Automatic Lock choices None,
Display Off, and Suspend. A validated installation additionally exposes Screen
Saver Effect, Screensaver, and the Screensaver lock stage. Missing or damaged
payload never generates a player invocation; its Check status and Repair
actions remain visible in Additional system components.

## Current limitations

The optional archinstall first-reboot entry point is still pending. User-owned
files remain protected by their ownership class.

The Appearance foundation and visual Background Picker are integrated with the
managed deployment path.
System keyboard synchronization and the supporting
direct-session lifecycle hardening are live-validated. The development machine
has no global keyboard fallback: localed is the persistent graphical authority
and the managed service is its sole global runtime projection into Hyprland.
The pinned player release is
x86_64-focused, physical multi-monitor acceptance and parts of the Bluetooth
hardware/pairing matrix remain pending. See
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
