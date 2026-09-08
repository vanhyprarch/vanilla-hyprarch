# Vanilla HyprArch system baseline

This document defines the reusable Vanilla HyprArch base system. It describes
project requirements, not a complete snapshot of every package installed on the
development machine. Package facts were verified locally on 2026-09-08.

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
available from Arch's `extra` repository on 2026-09-08.

## Installation reproducibility

One future bootstrap will consume this baseline, the package manifests, and
tracked configuration. It must support both an archinstall-time entry point and
independent execution after a fresh minimal Arch installation. The installer
does not exist yet. Its responsibilities, public-preset boundaries, and
unresolved choices are maintained in the canonical
[installation strategy](installation-strategy.md).

## Graphical and shell stack

| Role | Packages | Ownership |
| --- | --- | --- |
| Compositor and window manager | `hyprland` | Hyprland owns composition, windows, input, bindings, and session autostart. |
| Project shell | `quickshell`, `qt6-svg` | Quickshell owns the dock, frame, popups, launchers, system controls, and shell IPC. |
| Wallpaper | `hyprpaper` | Started by Hyprland. Its current configuration is live-only and still needs to be represented in the repository. |
| Generic graphics runtime | `mesa` | Hardware-neutral Mesa userspace. The installer must select any hardware-specific Vulkan package separately. |

The project uses upstream Hyprland and Quickshell rather than a downstream
desktop distribution layer.

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

The verified Bluetooth baseline is:

- `bluez`
- `bluez-utils`

`bluetooth.service` is enabled and active. No Quickshell Bluetooth panel exists.
`blueman` is not installed and is deliberately excluded from the core baseline.
Future Bluetooth UX remains an open decision and must not presume that blueman
is the selected interface.

## Desktop portals and authorization

The Wayland portal stack is:

- `xdg-desktop-portal`
- `xdg-desktop-portal-hyprland`
- `xdg-desktop-portal-gtk`

The installed authentication-agent package is `polkit-kde-agent`. It provides
`/usr/lib/polkit-kde-authentication-agent-1`, a static
`plasma-polkit-agent.service` user unit, and an XDG autostart entry restricted
to KDE. The current session is plain `start-hyprland`, not uwsm-managed; its
desktop identity is Hyprland, no user override or generic autostart launcher was
found, and the repository has no agent start command. At verification time the
unit was inactive, no authentication-agent process or user-bus name existed,
and only the system `polkitd` authorization backend was running.

This does not by itself establish that PolicyKit as a whole is broken. It means
authentication-agent startup ownership is currently undefined for the Hyprland
session and must be resolved and validated before the baseline installer is
considered complete.

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

The current Ly configuration uses its `colormix` login animation. This is
separate from the provisional user-session screensaver proof of concept.

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
- Omarchy is a design reference, not a runtime or package dependency.
