# Distribution Foundation 2

## Phase 1 and Phase 2 status

Phase 1 normalizes package, component, service, and deployment ownership policy.
Phase 2 adds the reusable user-space deployment core for `VANILLA_MANAGED`
artifacts only. It provides deterministic plan/install/update/validate
operations, regular installed copies, minimal hash/mode provenance, atomic
file/tree generation exchange, safe stale-artifact removal, and local rollback.
It does not provide the full installer, a package transaction, create-once
initialization, privileged adoption, service mutation, first-login action,
optional-component lifecycle, or doctor command. See
[Managed-file deployment](managed-file-deployment.md).

The machine-readable authorities introduced by this phase are:

- `packages/manifest-v1.toml` for package roles, sources, component membership,
  and default-install policy;
- `deployment/ownership-v2.toml` for artifact ownership and the operations a
  future executor may perform;
- `deployment/service-policy-v1.toml` for intended activation ownership.

Pacman remains the package dependency authority. These manifests contain no
package versions and do not attempt dependency solving.

## Supported Alpha base

The initial Alpha target is Arch Linux x86_64 installed through a documented
fresh-install or archinstall-derived path. Vanilla HyprArch is installed on top
of that known base. Alpha does not promise adoption of arbitrary existing Arch
desktops, migration from other Hyprland distributions, NVIDIA provisioning, or
support for every hardware combination.

The executor may initially be run from a local Vanilla source tree obtained by
Git clone. That acquisition path necessarily starts with `git` already
available as a pre-bootstrap acquisition prerequisite. Once Vanilla can run,
`git` is also part of its permanent build/bootstrap package baseline. These
roles do not conflict: one obtains the initial source, while the other keeps
the declared Alpha build environment complete. Installed runtime files must be
regular copies and must not depend on Git, the checkout, its `.git` directory,
a worktree, or its absolute source path. The same separation must permit a
future tagged release archive that does not require Git merely to acquire the
source, without changing runtime layout.

## Package and component decisions

Package role and default installation are separate properties. Required
packages and the `build` prerequisites needed for the approved `yay` bootstrap
install by default. `pavucontrol` and `bluez-utils` are recommended and also
install by default. Printing is a recommended component but does not install by
default.

`yay` is the sole approved default AUR package. It must be built as an unprivileged
user using the official `base-devel` and `git` prerequisites. Its presence does
not authorize another AUR package. Vanilla owns that generic AUR bootstrap
contract; the `yay` PKGBUILD remains authoritative for its own `depends` and
`makedepends`, resolved through `makepkg` and the package dependency mechanism.
Vanilla does not duplicate that graph or declare `go` directly merely because
the current PKGBUILD needs it. A later PKGBUILD dependency change therefore
does not require Vanilla to mirror it in the static package manifest.

The printing component contains `cups`, `cups-pk-helper`, and
`system-config-printer`. Network discovery is the separate `network-printing`
extension containing `avahi`; it is not implied by local printing.
`cups-filters` remains dependency-manager territory.

The baseline archive stack is `thunar`, `thunar-archive-plugin`, `xarchiver`,
`7zip`, `zip`, `unzip`, `zstd`, `gvfs`, and `tumbler`. It promises practical
ZIP, 7z, tar, gzip, bzip2, xz, and zstd handling. Arch base supplies tar, gzip,
bzip2, and xz. `p7zip` is forbidden. RAR, `thunar-volman`, `gvfs-mtp`, and
video thumbnails remain later decisions.

Dictation is optional. Its baseline manager is managed content, while `gnupg`
and `wtype` are component-only official packages and Voxtype is a pinned
external payload. The separate non-default `dictation-vulkan` variant records
the loader plus AMD/Intel ICD candidates without selecting hardware
automatically; NVIDIA provisioning remains out of Alpha scope. Zig Screensaver
follows the same manager/payload split and never requires a Zig compiler on an
installed system.

## MPV decision

`mpv` is required and installed by default. `pipewire-jack` is deliberately
direct because Vanilla chooses PipeWire as the provider satisfying mpv's JACK
requirement.

Phase 3 will supply a create-once `$XDG_CONFIG_HOME/mpv/mpv.conf` seed with mode
`0644`. The installer must create it only when absent, after which it is
user-owned. Updates never replace or merge it. The accepted provisional content
is:

```ini
vo=gpu-next
target-colorspace-hint=auto
target-colorspace-hint-mode=source
fullscreen=yes
```

Physical acceptance remains explicit: **test this MPV baseline on an SDR-only
monitor**. No seed file or live configuration is created in Phase 1.

## Default applications and MIME ownership

The deliberate packages are Firefox for web content, Thunar for directories,
imv for images, and mpv for media. Inspection of installed package metadata and
the current official imv file list identifies the primary desktop IDs as
`firefox.desktop`, `thunar.desktop`, `imv.desktop`, and `mpv.desktop`.

Phase 3 will define a deliberately small MIME coverage set and revalidate those
IDs against the packages being provisioned. It will add a create-once
`$XDG_CONFIG_HOME/mimeapps.list` seed only when no user MIME configuration
exists. The file becomes user-owned immediately; installation and update never
overwrite or automatically merge an existing file. Phase 1 intentionally does
not create the seed or claim an exhaustive MIME database.

## Display manager and services

`ly` is required. Future system integration enables `ly@tty2.service` and
disables conflicting `getty@tty2.service`. The package-owned Hyprland session
entry remains authoritative, and selecting Hyprland once on the first Ly login
is acceptable Alpha behavior. Vanilla does not own a Ly configuration merely
to preselect it.

NetworkManager and Bluetooth are required enabled system services. Printing
activation occurs only with the printing component. PipeWire/WirePlumber use
package activation, and portals and dunst use package/D-Bus activation.
`hypridle.service`, `hyprpolkitagent.service`, the static keyboard helper, and
the Monitor transaction unit are never independently enabled. Hyprland remains
the owner of one direct hypridle process.

The service manifest records future policy only. Phase 1 changes no systemd
state.

## Monitor installation boundary

The create-once machine seed contains the portable fallback rule. Installation,
session startup, hotplug, inspection, or panel opening never materializes a
connector profile. Only the existing Monitor backend may perform explicit
advanced-settings materialization. Connector profiles, Forced HDR base-CM
metadata, and Automatic HDR policy remain machine-owned. Safe Apply remains a
static transaction unit. No distribution manifest or future executor may grow
a second Monitor parser.

## Vanilla update policy

A future Vanilla update replaces validated Vanilla-managed content and may
preflight newly required packages. It never silently performs `pacman -Syu`,
never takes ownership of the user's full Arch upgrade, and never performs an
unsupported partial upgrade. When the Arch state is unsuitable for a required
package change, update must fail clearly and ask the administrator to update
Arch first.

Exact full-installer package/update behavior remains deferred. The Phase 2
executor updates only proven `VANILLA_MANAGED` user files and never performs a
package transaction.
