# Vanilla HyprArch system baseline

This document defines the reusable Vanilla HyprArch base system. It describes
project requirements, not a complete snapshot of every package installed on the
development machine. Package facts were verified locally on 2026-09-10.

The starting point is a working minimal Arch Linux installation with systemd,
network access, a suitable kernel, firmware, and GPU drivers. Kernel, firmware,
Vulkan driver, monitor, and input-device choices are hardware-specific and are
therefore outside the generic package manifest.

## Package policy

`packages/official.txt` is the machine-readable list of explicitly supported
baseline packages from official Arch repositories. Pacman resolves their
transitive dependencies; the manifest is not a lockfile or an export of the
entire installed system.

`packages/aur.txt` lists foreign/AUR packages deliberately required by the
project or its bootstrap. Official Arch packages remain the default, and an AUR
package must not be introduced for convenience when a reasonable official
alternative exists. Every AUR entry requires an explicit requirement and
maintenance rationale.

`yay` is the sole current exception. It is intentionally required in the final
Vanilla HyprArch system and bootstrap, even though it is not a desktop runtime
dependency. Its inclusion does not authorize the installer or future agents to
select other AUR packages freely.

All packages in the current official manifest were verified as installed and
available from Arch's official repositories by 2026-09-17.

`wayland` is explicit because the external player directly links
`libwayland-client`. `curl` is explicit because the pinned installer invokes
its command-line client; neither dependency is left implicit merely because it
is also present transitively on the development system. Zig is not a runtime
or baseline package.

`flatpak` is a required, unpinned official Arch package. Clean installations
install the version currently available from the enabled official repositories,
and normal `yay -Syu` system upgrades keep it current. Flatpak is not sourced
from the AUR and its locally validated version is not an installation pin.

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
| Graphical authorization | `hyprpolkitagent` | Hyprland starts its packaged systemd user service for the direct graphical session. |
| Session logout | `hyprshutdown` | The Power Menu uses Hyprland's graceful shutdown utility to end the direct session cleanly. |
| Screensaver renderer | `wayland`, external `vanhyprarch-zig-player` v0.1.1 | The independently released native client owns layer-shell output coverage, input absorption, and animation. |
| Wallpaper | `hyprpaper` | Started by Hyprland. Its current configuration is live-only and still needs to be represented in the repository. |
| Generic graphics runtime | `mesa` | Hardware-neutral Mesa userspace. The installer must select any hardware-specific Vulkan package separately. |

The project uses upstream Hyprland and Quickshell rather than a downstream
desktop distribution layer.

The future shared bootstrap will deploy the `vanhyprarch` named Quickshell
configuration for the main shell. It will install `vanhyprarch-screensaver`
from `bin/` and invoke the existing pinned player installer so the separately
released `vanhyprarch-zig-player` is available in the same inherited PATH.
Production screensaver presentation does not use Quickshell or Foot.

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

## Deliberate default applications

| Role | Package |
| --- | --- |
| Browser | `firefox` |
| Terminal | `foot` |
| File manager | `thunar` |
| Graphical audio control | `pavucontrol` |

Thunar integration uses `gvfs` for virtual filesystems and `tumbler` for
thumbnails. `file-roller` is deliberately excluded from the core baseline: it
is not installed and is a desktop convenience rather than a shell/runtime
requirement. It may later be considered for an optional or recommended package
set.

## Audio

The audio baseline is PipeWire with WirePlumber:

- `pipewire`
- `pipewire-audio`
- `pipewire-alsa`
- `pipewire-pulse`
- `wireplumber`
- `pavucontrol`

The shell uses Quickshell's native PipeWire service. Hyprland media-key bindings
call WirePlumber's `wpctl`. Although `pipewire-jack` is installed on the
development machine, no project requirement for JACK compatibility has been
established, so it is not in the baseline manifest.

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
privileged authorization. Hyprland starts its packaged user service from the
existing `hyprland.start` callback with:

```text
systemctl --user start hyprpolkitagent
```

The project does not enable the unit separately; the direct Hyprland session
remains its startup owner.

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

Hyprland currently starts hypridle directly. The packaged `hypridle.service`
user unit is disabled and inactive. The static configuration has a
`pidof hyprlock || hyprlock` lock command, delegates conditional pre-sleep
locking to `vanhyprarch-idle`, and sources the project-generated listener
fragment. The migration defaults produce zero listeners: Screen saver, display
off, and suspend are `Never`, automatic lock is `None`, and Caffeine is off.

## Monitor control utilities

The implemented monitor panel directly requires `ddcutil` for DDC/CI brightness
operations. `i2c-tools` is included with that support. Actual DDC availability,
I2C permissions, connector names, monitor modes, scale, color depth, and GPU
drivers are hardware-specific installation concerns.

The tracked alpha `hyprland.lua` still carries the development machine's
`DP-1` mode, scale, color, and keyboard choices, and the scale writer is tied to
that connector. It is not a portable baseline file and must be reviewed before
manual deployment. General overrides belong to the planned customization layer.

## Printing

The verified printing baseline is:

- `cups`
- `cups-filters`
- `cups-pk-helper`
- `system-config-printer`

`cups.service` is enabled and active. `avahi` is installed transitively on the
development machine, but `avahi-daemon.service` is disabled and inactive, so it
is not declared as a project requirement pending a decision on network-printer
discovery.

## Deliberate exclusions

- `jq` is not installed and must not be introduced merely for occasional JSON
  inspection; Python's standard library is adequate for development checks.
- `less` is not installed and is intentionally outside the desired workflow;
  use non-paginated commands such as `git --no-pager`.
- Omarchy is a keybinding/UX reference, not a runtime or package dependency;
  no Omarchy code or assets are included.
- Caelestia is a visual-design reference only; no Caelestia code or assets are
  included.
