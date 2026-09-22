# Vanilla HyprArch system baseline

This document defines the reusable Vanilla HyprArch base system. It describes
project requirements, not a complete snapshot of every package installed on the
development machine. Package names were revalidated against the available Arch
repository metadata on 2026-09-22.

The starting point is a working minimal Arch Linux installation with systemd,
network access, a suitable kernel, firmware, and GPU drivers. Kernel, firmware,
Vulkan driver, monitor, and input-device choices are hardware-specific and are
therefore outside the generic package manifest.

## Package policy

`packages/manifest-v1.toml` is the sole machine-readable package authority. It
separates source, role, component membership, and default-install policy.
Pacman resolves transitive dependencies; the manifest is not a lockfile,
dependency solver, or export of the development system.

Official Arch packages remain the default. Every AUR entry requires an
explicit requirement and maintenance rationale.

`yay` is the sole current exception. It is intentionally required in the final
Vanilla HyprArch system and bootstrap, even though it is not a desktop runtime
dependency. Its inclusion does not authorize the installer or future agents to
select other AUR packages freely.

All official package names in the current manifest were verified as available
from the local Arch repository databases. The manifest is deliberately not an
installed-package snapshot.

`wayland` is independently fundamental to the baseline Wayland desktop rather
than being retained for the optional player. `curl` is explicit because the
pinned component manager invokes its command-line client; neither dependency
is left implicit merely because it is also present transitively on the
development system. Zig is not a runtime or baseline package.

`flatpak` is a required, unpinned official Arch package. Clean installations
install the version currently available from the enabled official repositories,
and administrator-owned Arch upgrades keep it current. Vanilla update does not
silently run a full distribution upgrade. Flatpak is not sourced from the AUR
and its locally validated version is not an installation pin.

Component packages are never inferred from role. The structured manifest marks
`gnupg` and `wtype` as non-default members of the optional `dictation`
component. GnuPG verifies the detached upstream Voxtype signature; `wtype` is
Voxtype's sole configured Wayland typing driver. The Voxtype executable itself
is a pinned, verified upstream release artifact, not an Arch or AUR package.

The official `file` package is explicit because the Appearance manager invokes
its MIME detector to validate user wallpaper content against the installed
Hyprpaper decoder contract. Filename extensions are not trusted as image
evidence.

`libxkbcommon` and `xkeyboard-config` are explicit because the managed keyboard
synchronizer directly invokes `xkbcli` and requires the corresponding XKB data;
they are not left implicit through Hyprland. Python and PyGObject were already
explicit baseline packages. systemd and its localed service remain part of the
minimal Arch starting system rather than a desktop-package delta.

## Installation reproducibility

One future bootstrap will consume this baseline, the package manifests, and
tracked configuration. It must support both an archinstall-time entry point and
independent execution after a fresh minimal Arch installation. The shared
bootstrap does not exist yet. Its responsibilities, public-preset boundaries,
and unresolved choices are maintained in the canonical
[installation strategy](installation-strategy.md).

## Graphical and shell stack

| Role | Packages | Ownership |
| --- | --- | --- |
| Compositor and window manager | `hyprland` | Hyprland owns composition, windows, input, bindings, and session autostart. |
| Project shell | `quickshell`, `qt6-svg` | Quickshell owns the main desktop shell. |
| Graphical authorization | `hyprpolkitagent` | Hyprland invokes the managed direct-session lifecycle helper, which publishes the display environment and owns ordered start/stop around the packaged systemd user service. |
| Session logout | `hyprshutdown` | The Power Menu stops the graphical PolicyKit agent and then execs Hyprland's graceful shutdown utility. |
| Screenshot capture | `python`, `grim`, `slurp`, `wl-clipboard` | Hyprland owns Print Screen; `vanhyprarch-screenshot` selects, saves, and publishes PNG clipboard data without Quickshell image processing. |
| Optional screensaver renderer | baseline `python` and `wayland`, external `vanhyprarch-zig-player` v0.1.1 | `python` and Wayland are independently required, so the component adds no official package. `vanhyprarch-screensaver` and immutable pinned metadata are baseline; the native player, license, notices, README/release record, and marker exist only when Zig Screensaver is installed. |
| Optional dictation | optional `gnupg`, `wtype`, external Voxtype 1.0.1; conditional official Vulkan loader/vendor ICD | CPU is the public local-Whisper default. Vulkan GPU is an explicit signed-artifact choice in SuperSpace and is never selected automatically. Hyprland supplies F9 press/release and starts the project user service only when installed. |
| Appearance and wallpaper | `hyprpaper`, `file` | `vanhyprarch-appearance` owns Light/Dark and wallpaper preference. Hyprland starts one Hyprpaper renderer through that manager; Hyprpaper owns no preference. |
| System keyboard projection | `python`, `python-gobject`, `libxkbcommon`, `xkeyboard-config`, `systemd`, `hyprland` | `systemd-localed` owns the graphical XKB tuple; the static user service projects it into Hyprland without owning active groups or per-device rules. |
| Monitor transactions | `python`, `hyprland`, `bubblewrap`, `systemd` | The static authority owns confirmed Safe Apply for mode/bitdepth and immediate validated Scale. Bubblewrap isolates prospective full-config verification from the live session; schema v3 and its UI have completed single-monitor live acceptance. |
| Generic graphics runtime | `mesa` | Hardware-neutral Mesa userspace. The installer must select any hardware-specific Vulkan package separately. |

The project uses upstream Hyprland and Quickshell rather than a downstream
desktop distribution layer.

## Session command path

Hyprland constructs the graphical-session `PATH` before starting children by
reading `HOME` and the inherited `PATH`, then prepending `$HOME/.local/bin`
exactly once. Public project commands use stable `vanhyprarch-*` names and are
deployed as regular executable files in that directory. Quickshell-private
helpers remain under `Quickshell.shellDir/helpers`; fixed or sensitive packaged
tools may be addressed through `/usr/bin/...`.

Development may symlink public commands from the repository into
`$HOME/.local/bin`. Production bootstrap must create the user-owned directory
when needed and atomically install regular files without requiring the source
checkout, then validate their ownership and executable mode. After logout/login
validation of the unified session PATH, normal launched session applications
receive the user-local command directory and Quickshell resolves
`vanhyprarch-idle` by name. Controlled reboot evidence showed that Hyprland's
own inherited `/proc` PATH can still lack that directory. The critical idle
autostart therefore launches the `sessionHome`-derived absolute path
with `exec $HOME/.local/bin/vanhyprarch-idle session-start`. Current
`hl.exec_cmd` behavior creates a transient `/bin/sh -c`; the leading shell
builtin replaces it with the backend before ownership validation. That command
validates the direct current-user `/usr/bin/Hyprland` parent and stable process
start time through `/proc`, without requiring the early Hyprland instance
registry to exist. It reconciles Caffeine off from durable preferences,
explicitly releases its backend lock, and directly execs
`/usr/bin/hypridle -v`; the resulting daemon remains Hyprland's direct child
with no surviving wrapper or per-process PATH override. Public project commands
remain under `$HOME/.local/bin`. A failed initializer writes one bounded
session-runtime diagnostic; success removes any stale record.
Power & Idle still captures the validated daemon's exact PATH and reuses it for
transactional replacement and rollback.

This startup contract passed a controlled reboot with Caffeine enabled and a
persisted zero-listener fragment. The new session republished the configured
three-listener Caffeine-off fragment before starting one direct
Hyprland-owned hypridle, and the 120-second screensaver fired without any panel
interaction or manual reapplication.

The future shared bootstrap will deploy the `vanhyprarch` named Quickshell
configuration for the main shell. It will install `vanhyprarch-idle`,
`vanhyprarch-appearance`, `vanhyprarch-screensaver`, `vanhyprarch-screenshot`, and the independently
available `vanhyprarch-dictation` manager from `bin/` under `$HOME/.local/bin`;
it will also install `vanhyprarch-monitor` and its static, non-enabled user
service. The published schema-v5/protocol-v4 generation is the accepted
single-monitor runtime; any future journal schema requires its own controlled
deployment boundary and must never replace a backend that owns nonterminal
recovery material.
It will deploy immutable dictation metadata under
`${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/dictation/`, then invoke the
Zig Screensaver manager resources under the corresponding
`vanhyprarch/zig-screensaver/` data directory. It does not baseline-install the
separately released `vanhyprarch-zig-player`; SuperSpace offers that explicit
optional transaction. Production screensaver
presentation does not use Quickshell or Foot.

## Flatpak applications

The system-wide `flathub` remote is required and must resolve to
`https://dl.flathub.org/repo/`. The reusable `install/configure-flatpak`
component inspects system remotes, leaves an existing correct Flathub remote
unchanged, and otherwise adds it with `--system --if-not-exists` from the
canonical Flathub repository descriptor. A conflicting remote with the same
name fails closed instead of being rewritten. User remotes and installed
Flatpak applications are outside bootstrap ownership; the bootstrap neither
removes them nor installs any application automatically.

## Keyboard and session defaults

Hyprland's native `input.numlock_by_default` option is enabled. Num Lock is
therefore on by default when the graphical session starts. This is a compositor
input default; it does not require `numlockx`, `setleds`, an autostart command,
or an external script.

The graphical layout/model/variant/options tuple belongs to `systemd-localed`.
The managed `vanhyprarch-keyboard-sync` helper validates and projects it into
Hyprland at session start and on relevant D-Bus changes. Active groups remain
Hyprland/user runtime state, while device-specific input rules remain machine
configuration. The public machine seed and validated development-machine file
both leave the global XKB tuple unset; explicit per-device exceptions may still
belong in machine configuration.

## Deliberate default applications

| Role | Package |
| --- | --- |
| Browser | `firefox` |
| Terminal | `foot` |
| File manager | `thunar` |
| Image viewer | `imv` |
| Media player | `mpv` |
| Graphical audio control | `pavucontrol` (recommended, installed by default) |

`dunst` is the required package/D-Bus-activated notification daemon, so a fresh
install does not depend on accidental host software. Phase 3 will add minimal
create-once mpv and MIME seeds. Existing `$XDG_CONFIG_HOME/mpv/mpv.conf` and
`$XDG_CONFIG_HOME/mimeapps.list` files are always preserved without automatic
merge.

Thunar integration uses `gvfs` for trash and normal session mounting,
`tumbler` for image thumbnails, and `thunar-archive-plugin` with `xarchiver`
for archive actions. `7zip`, `zip`, `unzip`, and `zstd` complete the explicit
archive engines; Arch base supplies tar, gzip, bzip2, and xz. `p7zip` is
forbidden, while RAR, `thunar-volman`, `gvfs-mtp`, and video thumbnails remain
optional/later.

## Audio

The audio baseline is PipeWire with WirePlumber:

- `pipewire`
- `pipewire-audio`
- `pipewire-alsa`
- `pipewire-pulse`
- `pipewire-jack`
- `wireplumber`
- `pavucontrol`

The shell uses Quickshell's native PipeWire service. Hyprland media-key bindings
call WirePlumber's `wpctl`. `pipewire-jack` is intentionally direct because
Vanilla chooses PipeWire as the provider for mpv's current JACK requirement.

## Networking

`networkmanager` owns network connections and is enabled as the system
`NetworkManager.service`. The shell uses `Quickshell.Networking` directly for
status, Wi-Fi scanning, known networks, connection, and forget operations.

`network-manager-applet` is not installed and is not required by the current
native shell implementation. It is deliberately excluded from the baseline and
must not be reinstalled merely because it existed historically.

## Bluetooth

The Bluetooth baseline is:

- `bluez`
- `bluez-utils`
- `python`
- `python-dbus`
- `python-gobject`

`bluetooth.service` is enabled and active. The shell uses native
`Quickshell.Bluetooth` objects for adapter power, discovery, device state,
pairing, connections, removal, and trust. A small Python/dbus-python/PyGObject
child implements only the complete BlueZ pairing-agent callbacks missing from
Quickshell 0.3.1. It is supervised by the main shell and is not a permanent
service. `bluetoothctl` polling and prompt parsing are not used. `blueman` and
other complete Bluetooth GUIs remain excluded.

The tracked `system/etc/bluetooth/main.conf` sets only
`[Policy] AutoEnable=false`; other BlueZ behavior uses upstream defaults. The
shell stores the last explicit global power choice in
`${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/bluetooth-power.conf` and
restores it through native adapter objects. If no preference file exists, the
shell uses ON as its in-memory first-run default without writing the file or
inferring a choice from transient adapter state.

For the validated BlueZ 5.87 baseline this is a complete `main.conf`
replacement, because BlueZ does not load a `main.conf.d` drop-in directory.
Users must not copy it blindly over an existing customized administrator file.
The future bootstrap must validate the target, preserve exact rollback
material, and fail closed rather than overwrite unknown configuration.

## Desktop portals and authorization

The Wayland portal stack is:

- `xdg-desktop-portal`
- `xdg-desktop-portal-hyprland`
- `xdg-desktop-portal-gtk`

Vanilla HyprArch uses the direct
`Ly -> /usr/bin/start-hyprland -> Hyprland` session path; UWSM is not part of
the project architecture. The required official `hyprpolkitagent` package
provides graphical PolicyKit authentication for GUI applications that need
privileged authorization. Hyprland invokes the managed direct-session
lifecycle helper from the existing `hyprland.start` callback with:

```text
exec $HOME/.local/bin/vanhyprarch-polkit-session session-start
```

The helper validates the current Hyprland and Wayland sockets, synchronously
imports the current display environment, clears a prior service failure, and
restarts exactly one packaged agent. The project does not enable the unit
separately. Its managed user drop-in adds a compositor-aware `ExecCondition`
and a one-second restart delay without replacing `/usr/lib` package content.
The shared Power action synchronously stops the service before replacing
itself with `/usr/bin/hyprshutdown`; compositor crashes are handled by the
drop-in's conditioned package restart instead of a graceful-exit callback.

The GTK portal backend supplies `org.freedesktop.impl.portal.Settings` because
the Hyprland backend does not implement that interface. Appearance writes only
the writable `org.gnome.desktop.interface color-scheme` host key and verifies
the brokered `org.freedesktop.appearance/color-scheme` result. Dark is portal
value 1 and Light is value 2. No toolkit theme name or application-specific
configuration is part of this contract.

## Appearance and wallpapers

The durable preference is
`${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/appearance.json`. XDG Pictures
resolution uses `XDG_PICTURES_DIR` from `user-dirs.dirs`, with
`$HOME/Pictures` as the standards-compatible fallback when no configuration is
available. User images live beneath `Wallpapers/Light` and `Wallpapers/Dark`
and remain user content rather than managed deployment payload.

Official Wallpaper Set v2 ships eight GPL-2.0-only 3840×2160 RGB Wolkenstein
PNGs as managed, offline distribution assets under the project XDG data
directory. Their established filenames and pair-1 default are unchanged.
Appearance seeds exact copies non-destructively into the user directories once
for a fresh initialization. Existing initialized users do not receive later
starter-set replacements. A durable version-2
completion record prevents normal updates and reconciliation from adding,
restoring, or replacing files afterward; the directories and their contents
are user-owned. Version-1 hash receipts migrate to completed without touching
the wallpaper directories.

The managed `hyprpaper.conf` enables IPC, disables the splash, and declares no
wallpaper. The manager applies one selected file to the installed renderer's
fallback and explicitly to every output discovered through Hyprland's JSON
monitor inventory, then checks the monitor set and all `listactive` entries.
Hyprpaper absence or IPC failure is reported without disabling Vanilla shell
colors or host preference.

## Fonts and icons

The baseline font set is:

- `noto-fonts`
- `noto-fonts-emoji`
- `ttf-liberation`
- `ttf-dejavu`

The icon package is `papirus-icon-theme`. Quickshell declares Papirus as its
icon theme and uses it for project UI controls.

## Display manager

`ly` is the selected display manager. `ly@tty2.service` is enabled and active;
`getty@tty2.service` is disabled so Ly owns tty2. SDDM is installed only as a
disabled rollback artifact on the current machine and is not part of the
Vanilla HyprArch package manifest.

The current Ly configuration uses its own login animation. User-session
screensaver rendering is instead delegated to the independent native Zig
Player; Ly itself is not run inside the graphical session.

## Locking and idle

- `hyprlock` provides session locking.
- `hypridle` provides idle and pre-sleep event handling.

The repository provides a minimal portable managed `hyprlock.conf` with no
connector, wallpaper, locale, font, or development-machine assumptions. It has
not yet replaced the current live configuration.

Hyprland starts the backend's session initialization command, which atomically
reconciles Caffeine off and then directly execs hypridle. The packaged
`hypridle.service` user unit is disabled and inactive. The static configuration
has a `pidof hyprlock || hyprlock` lock command, delegates conditional
pre-sleep locking to `vanhyprarch-idle`, and sources the project-generated
listener fragment. A baseline without Zig Screensaver cannot render a
screensaver listener even if dormant preferences exist. Display off, Suspend,
Automatic Lock, and Caffeine remain functional; the clean-install defaults are
all `Never`, automatic lock `None`, and Caffeine off.

## Monitor control utilities

The implemented monitor panel directly requires `ddcutil` for DDC/CI brightness
operations. Pacman supplies `i2c-tools` transitively; Vanilla does not declare a
separate direct contract with it. Actual DDC availability,
I2C permissions, connector names, monitor modes, scale, color depth, and GPU
drivers are hardware-specific installation concerns.

The repository Hyprland entrypoint now loads managed core, managed bindings,
machine configuration, and user override layers. The managed files and public
machine seed contain no development-machine connector, mode, scale, color, or
keyboard choices. The seed's portable catch-all monitor rule uses preferred
mode, automatic position, and automatic scale; it is machine-owned but is not a
Monitor panel write target. The live ownership migration uses
`vanhyprarchMonitorScale` only in the development machine's explicit output
profile. Each Monitor panel maps its own `ShellScreen` through
`Hyprland.monitorFor(screen)` and consumes the backend's normalized read-only
inspection. The backend fails closed unless one unambiguous explicit connector
profile exists in the machine-owned file; it cannot edit the fallback rule or
managed Hyprland files. An undeployed repository follow-up allows the user to
opt in to advanced display management by cloning the supported fallback for one
connector while preserving `preferred`/`auto`/`auto` intent and verifying a
complete observational no-op. Neither bootstrap nor session startup performs
that operation automatically. No general multi-monitor schema is promised
during Alpha.

The managed `vanhyprarch-monitor` Python command and static, non-enabled
`vanhyprarch-monitor-safe-apply.service` use baseline Python, systemd,
Hyprland, and Bubblewrap. The service starts only for a transaction, is bounded
by `RuntimeMaxSec=90s`, and invokes an idempotent recovery entry point through
`ExecStopPost`; journal, lock, and socket material is private XDG runtime
state. The published schema-v5/protocol-v4/inspect-v3 engine gives Mode,
bitdepth, forced HDR, and global Automatic HDR an
explicit-confirmation window, makes Scale an immediate validated persistence
operation, and includes explicit opt-in profile materialization. Its real UI
and single-monitor runtime/persistence paths are live-accepted; real fallback
materialization and physical multi-monitor acceptance remain deferred.

## Screenshots

`grim`, `slurp`, and `wl-clipboard` are unpinned required packages from the
official Arch repositories. The project-owned Python helper uses Hyprland JSON
only to offer current visible window and monitor rectangles to `slurp`; JSON is
parsed with the standard library and does not require `jq`. Selection remains
unrestricted so dragging always captures a freeform region. If smart rectangle
discovery fails, the helper retains ordinary drag selection.

Print Screen saves a PNG under the XDG Pictures directory's `Screenshots`
subdirectory, or `$HOME/Pictures/Screenshots` when no valid XDG Pictures value
exists. It then supplies the exact saved bytes to `wl-copy` with MIME type
`image/png`, allowing normal Ctrl+V paste in applications that accept images.
Escape cancellation neither publishes a file nor changes the clipboard.

This first implementation intentionally has no screen freeze, screenshot
editor, notification, or Quickshell image-processing path. It also does not
change monitor scale, bit depth, color management, or cursor settings.

## Printing

Printing is a recommended component that is not installed by the default Alpha
policy. Its direct packages are:

- `cups`
- `cups-pk-helper`
- `system-config-printer`

`cups-filters` remains dependency-manager territory. Printing services are
activated only when the component is selected. `avahi` belongs to the separate
non-default `network-printing` extension so network discovery does not become
implicit local-printing or core membership.

## Deliberate exclusions

- `jq` is not installed and must not be introduced merely for occasional JSON
  inspection; Python's standard library is adequate for development checks.
- `less` is not installed and is intentionally outside the desired workflow;
  use non-paginated commands such as `git --no-pager`.
- Omarchy is a keybinding/UX reference, not a runtime or package dependency;
  no Omarchy code or assets are included.
- Caelestia is a visual-design reference only; no Caelestia code or assets are
  included.
