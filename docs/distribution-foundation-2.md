# Distribution Foundation 2

## Phase 1 through Phase 4 status

Phase 1 normalizes package, component, service, and deployment ownership policy.
Phase 2 adds the reusable user-space deployment core for `VANILLA_MANAGED`
artifacts only. It provides deterministic plan/install/update/validate
operations, regular installed copies, minimal hash/mode provenance, atomic
file/tree generation exchange, safe stale-artifact removal, and local rollback.
Phase 3 adds manifest-driven create-once/backend initialization with
no-clobber publication, isolated XDG targets, owner-specific offline hooks, and
crash recovery. It does not provide the full installer, a package transaction,
privileged adoption, service mutation, first-login action,
optional-component lifecycle, or doctor command. See
[Managed-file deployment](managed-file-deployment.md) and
[Create-once initialization](create-once-initialization.md).

Phase 4 implements the separate installer-internal system-integration stage. It
derives official packages and system enablement from the
published manifests, builds the sole yay exception as an explicit non-root
user, adopts BlueZ only after package-pristine proof and exact backup, reuses
the system-Flathub helper, and keeps local crash recovery for BlueZ and service
transactions. A narrow shell bootstrap installs only `python` when a fresh
Arch base lacks the interpreter, verifies it, and stops. A later plan invocation
delegates to the Python stage for human review before a separately approved
full apply; the shell does not duplicate the manifest package transaction.
Deterministic acceptance remained isolated from the development host. A fresh
Arch Minimal GNOME Boxes VM passed no-Python bootstrap, partial-state resume,
full and preserve-only repeat applies, reboot, and integrated Phase 2/3/4
validation. See [DF2 system integration](system-integration.md).

The machine-readable authorities introduced by this phase are:

- `packages/manifest-v1.toml` for package roles, sources, component membership,
  and default-install policy;
- `deployment/ownership-v2.toml` for artifact ownership and the operations a
  future executor may perform;
- `deployment/service-policy-v1.toml` for intended activation ownership.

Pacman remains the package dependency authority. These manifests contain no
package versions and do not attempt dependency solving.

## Supported initial base

The initial target is Arch Linux x86_64 installed through a documented
fresh-install or archinstall-derived path. Vanilla HyprArch is installed on top
of that known base. It does not promise adoption of arbitrary existing Arch
desktops, migration from other Hyprland distributions, NVIDIA provisioning, or
support for every hardware combination.

The public executor acquires an exact-commit GitHub source archive with curl,
so `git` is not an acquisition prerequisite. Once the source exists,
Vanilla bootstraps `python` itself when needed and the Python system stage keeps
both `python` and `git` in the permanent build/bootstrap package baseline.
These roles do not conflict: the narrow shell boundary makes the
manifest-driven implementation executable, while system integration needs Git
for the approved non-root yay build. Installed runtime files are regular copies
and do not depend on Git, the extracted source, a worktree, or its absolute
source path. The same separation supports both the development `main` archive
and future pinned tag archives without changing runtime layout.

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
automatically; NVIDIA provisioning remains outside the initial scope. Zig Screensaver
follows the same manager/payload split and never requires a Zig compiler on an
installed system.

## MPV decision

`mpv` is required and installed by default. `pipewire-jack` is deliberately
direct because Vanilla chooses PipeWire as the provider satisfying mpv's JACK
requirement.

Phase 3 supplies a create-once `$XDG_CONFIG_HOME/mpv/mpv.conf` seed with mode
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
monitor**. Phase 3 acceptance uses disposable targets and creates no live
configuration.

## Default applications and MIME ownership

The deliberate packages are Firefox for web content, Thunar for directories,
imv for images, and mpv for media. GNOME Text Editor and Bazaar are additional
direct official baseline applications; neither changes this create-once MIME
seed. GNOME Text Editor is not assigned as the default text editor. Inspection
of installed package metadata and the current official imv file list identifies
the primary desktop IDs as
`firefox.desktop`, `thunar.desktop`, `imv.desktop`, and `mpv.desktop`.

Phase 3 defines a deliberately small MIME coverage set and revalidates those
IDs against current package/upstream desktop metadata. It adds a create-once
`$XDG_CONFIG_HOME/mimeapps.list` seed only when no user MIME configuration
exists. The file becomes user-owned immediately; installation and update never
overwrite or automatically merge an existing file. The seed does not claim an
exhaustive MIME database. Existing user configuration in the
other standards-defined XDG locations also prevents seeding.

## Display manager and services

Official `sddm` is required. Phase 5 system integration deploys and validates
the Vanilla password-only theme, direct Wayland session entry, generated target
binding, and X11-greeter drop-in before enabling normal `sddm.service`
display-manager semantics. SDDM is the sole supported display manager; fresh
systems have no tty2/getty-specific display-manager policy.

NetworkManager and Bluetooth are required enabled system services. Printing
activation occurs only with the printing component. PipeWire/WirePlumber use
package activation, and portals and dunst use package/D-Bus activation.
`hypridle.service`, `hyprpolkitagent.service`, the static keyboard helper, and
the Monitor transaction unit are never independently enabled. Hyprland remains
the owner of one direct hypridle process.

The service manifest is the Phase 4 system-stage authority. Phase 4 changes
enablement only after packages and adopted configuration are ready; it neither
starts services nor manipulates user units. Persistent enablement and reboot
behavior passed disposable-VM acceptance.

## Monitor installation boundary

The create-once machine seed contains the portable fallback rule. Installation,
session startup, hotplug, inspection, or panel opening never materializes a
connector profile. Only the existing Monitor backend may perform automatic
first-change materialization. Connector profiles, Forced HDR base-CM
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

The Phase 4 system stage provisions a fresh/current supported base but does not
turn Vanilla update into a distribution updater. It blocks on pending upgrades,
never refreshes pacman databases independently, and never runs a full upgrade.
The Phase 2 executor still updates only proven `VANILLA_MANAGED` user files.
