# Installation strategy

This document is the canonical plan for making Vanilla HyprArch reproducible.
The pinned Zig Screensaver component manager is implemented; the historical
`install-zig-player` command is only a compatibility wrapper. DF2 has separate
managed-file, create-once, accepted system-integration, and SDDM stages. The
repository-root `install.sh` now provides their thin shared post-install orchestration;
the optional archinstall entry point does not exist yet.

The current repository remains an Alpha development and testing source. Its
Hyprland files express portable managed, create-once machine, and user-override
ownership. The public wrapper does not duplicate those lifecycles: each
existing stage retains its own manifests, provenance, conflict handling, and
validation. Privileged BlueZ replacement remains limited to the system stage's
package-pristine adoption and exact rollback contract.

The initial Alpha support target is deliberately narrow: Arch Linux x86_64 on
a documented fresh-install or archinstall-derived base. It does not promise
adoption of arbitrary existing Arch desktops or other Hyprland distributions.
The public acquisition path uses curl to resolve the requested GitHub ref to
an exact commit and extracts that commit's source archive in a private
temporary directory. Git is therefore not required merely to obtain Vanilla,
although the system stage keeps `git` in the permanent build/bootstrap package
baseline for its approved yay build. Installed runtime files are regular
copies with no dependency on the temporary source. `install/bootstrap` still
uses only the Arch base shell to provision and verify Python when absent, then
stops before the Python-backed system stage. Python is not a manual
prerequisite.

## One bootstrap, two entry points

Vanilla HyprArch has one reusable post-install bootstrap implementation. Two
callers remain the architectural target:

1. **Archinstall-time:** an optional Vanilla HyprArch configuration helps the
   user install base Arch, then invokes the shared bootstrap inside the target
   system before the first reboot.
2. **Post-install:** the implemented `install.sh` runs independently on a fresh
   minimal Arch installation with working Internet access.

Archinstall is an integration layer, not the implementation of Vanilla
HyprArch. It may collect and pass installation context, but it must not contain
a second copy of package, deployment, service, or validation logic. A future
archinstall schema change should require adapting only this thin layer.

The intended Arch ISO flow is:

```text
Official Arch ISO
  -> connect to the network
  -> start archinstall
  -> optionally load the Vanilla HyprArch recommended configuration
  -> review and supply machine-specific and sensitive values
  -> install base Arch
  -> invoke the shared Vanilla HyprArch bootstrap in the target system
  -> run post-install validation
  -> first reboot into a working Vanilla HyprArch session
```

The archinstall-time first-reboot integration is not implemented yet.

## Public development bootstrap

Run the Alpha development path as the normal target user, never root:

```bash
sudo pacman -Syu --needed curl && bash <(curl -fsSL https://raw.githubusercontent.com/vanhyprarch/vanilla-hyprarch/main/install.sh)
```

The wrapper defaults to repository `vanhyprarch/vanilla-hyprarch` and ref
`main`. `VANHYPRARCH_REF=<tag-or-commit>` overrides the simple ref. It displays
the requested ref, resolved commit SHA, and downloaded archive SHA-256. Release
instructions must fetch `install.sh` from a pinned tag and set that same tag as
`VANHYPRARCH_REF`; moving `main` is development-only.

The exact orchestrated sequence is:

```text
host/user/sudo validation
  -> resolve ref and acquire exact-commit archive
  -> install/bootstrap plan (only when Python is absent)
  -> one user confirmation
  -> sudo install/bootstrap bootstrap-python (only when absent)
  -> sudo install/bootstrap plan
  -> sudo install/bootstrap apply
  -> managed_deploy.py plan reconcile
  -> managed_deploy.py reconcile
  -> create_once.py plan
  -> create_once.py initialize
  -> managed_deploy.py validate
  -> create_once.py validate
  -> sudo install/bootstrap validate
```

The final privileged validation includes SDDM login payload validation. A
failure or ownership conflict stops immediately and success is printed only
after all three validation calls pass. `--yes` suppresses the one installer
confirmation without weakening preflight or validation. Reboot is never
automatic.

## Bootstrap responsibilities

The shared bootstrap and its delegated stages:

- consume `packages/manifest-v1.toml`, installing default official packages
  according to their explicit role and policy;
- build and install the explicit default `yay` exception as a non-root user,
  using the declared `base-devel` and `git` bootstrap prerequisites, without
  treating it as permission to add other AUR packages; the `yay` PKGBUILD,
  `makepkg`, and package dependency mechanism remain authoritative for yay's
  own `depends` and `makedepends`, which Vanilla does not mirror in its static
  package manifest;
- after installing the required unpinned `flatpak` package, invoke
  `install/configure-flatpak` to establish the required system Flathub remote;
- deploy managed home configuration without personal paths and initialize
  create-once machine and override seeds only when their targets are absent;
- deploy the main `vanhyprarch` named Quickshell configuration;
- atomically install regular executable files for public project commands,
  including `vanhyprarch-idle`, `vanhyprarch-screensaver`, and
  `vanhyprarch-screenshot`, under `$HOME/.local/bin` without depending on a Git
  checkout; install `vanhyprarch-appearance` and
  `vanhyprarch-keyboard-sync` through the same public-command contract;
- deploy the static `vanhyprarch-keyboard-sync.service` user unit without
  enabling it; Hyprland remains its startup and reload-reconciliation owner;
- deploy `vanhyprarch-monitor` and its static
  `vanhyprarch-monitor-safe-apply.service` without enabling the unit; the unit
  is activated only for one bounded Safe Apply transaction;
- deploy immutable Zig Screensaver manager resources, but leave the optional
  `vanhyprarch-zig-player` payload absent until explicitly installed;
- establish required installed files and enable or disable only the services
  declared by `deployment/service-policy-v1.toml`;
- deploy the minimal `system/etc/bluetooth/main.conf` before starting or
  enabling `bluetooth.service`, preserving exact rollback material if an
  existing administrator configuration would be replaced;
- preserve the documented startup owner for each session process;
- deploy the reviewed official wallpaper payload under XDG data, then invoke
  the Appearance one-shot asset bootstrap; only a user with no durable
  initialization evidence receives the current starter files and newly
  created XDG Pictures `Wallpapers/Light` and `Wallpapers/Dark` directories,
  while initialized directories and their contents remain untouched;
- preserve or initialize the Appearance preference through its backend and
  deploy the selection-free managed Hyprpaper configuration before the first
  graphical session;
- create safe initial preference state, including Power & Idle at all `Never`,
  automatic lock at `None`, `effect=colormix`, and Caffeine off; the backend
  must generate the effective idle fragment rather than receiving release-owned
  generated bytes;
- respect dependency ordering and migrations, remain idempotent where
  practical, fail closed on invalid state, and run post-install validation.

The narrow pre-Python portion remains implemented as `install/bootstrap`.
It performs only Arch/x86_64/current-database preflight and, when needed, the
single `python` package transaction before stopping. The public wrapper invokes
its preliminary plan when required, obtains one installation approval,
performs the Python transition, then calls each authoritative plan immediately
before its corresponding apply. This dependency order is required because
create-once owner hooks resolve commands installed by the managed stage.

For every integrated feature, its package source, files, commands, services,
deployment, startup ownership, defaults, dependencies, migration behavior, and
validation must be recoverable from the canonical repository. Development-
machine behavior alone is not complete integration.

The bootstrap installs only the create-once portable monitor fallback. A display
working through that rule is already correctly configured; installation,
session start, and hotplug must not convert it into a connector-specific
profile. Opening Display remains read-only. A normal user display mutation may
invoke the Monitor backend, which automatically clones the supported fallback
and changes only its selector before continuing through the established apply
path. DF2 must not implement another monitor parser, persister, or
materialization policy.

The bootstrap must create `$HOME/.local/bin` as a user-owned directory when
needed, preserve rollback material before replacing a managed command, and
verify executable ownership, mode, and content after publication. Repository
development may use symlinks into `bin/`; production deployment uses regular
files. Quickshell-private helpers stay inside the deployed named configuration
at `Quickshell.shellDir/helpers` and are not copied into the session command
directory.

Post-install validation must verify that `/usr/bin/flatpak` is executable,
that an enabled system remote named `flathub` exists, and that its URL is
`https://dl.flathub.org/repo/`. These checks validate the installed result;
they do not pin a Flatpak version, modify remotes, or install applications.

The Bluetooth bootstrap must not seed a power preference. With BlueZ
`AutoEnable=false`, the shell treats a missing preference as an in-memory
first-run default of ON. Only an explicit On or Off selection creates the
versioned XDG configuration file; subsequent sessions restore that saved
global choice across all adapters.

Appearance first-run reconciliation may migrate a valid legacy shell mode and
may adopt a uniform active wallpaper already contained in a required mode
directory. A clean installation with no such active selection uses the
explicit Wolkenstein pair-1 Light and Dark defaults; it never chooses an
arbitrary directory entry. Existing Appearance selections remain unchanged.

Wallpaper bootstrap records a durable completion marker under XDG state. It is
local, hash-verified, non-destructive, and requires no network access. Once
complete, the Light and Dark directories and all their contents are user-owned:
later releases do not add new starters, restore deleted starters, or update old
ones. Changing the managed starter set changes only true fresh installations.
Existing version-1 seed receipts migrate to completed without touching user
content.

The version-2 ownership manifest declares deployability plus install/update
semantics. DF2 Phase 2 implements those semantics only for
`VANILLA_MANAGED` user artifacts through the reusable managed-file core. Its
per-artifact staging, provenance, atomic exchange, and rollback are not the
full bootstrap, a global transaction, create-once migration, optional-component
uninstall, or privileged integration. Version 1 remains historical.

## Create-once application state

Phase 3 initializes Foot, the accepted provisional mpv seed, and a minimal MIME
seed. Their targets are `$XDG_CONFIG_HOME/foot/foot.ini`,
`$XDG_CONFIG_HOME/mpv/mpv.conf`, and `$XDG_CONFIG_HOME/mimeapps.list`, all mode
`0644`. Foot's initial font size is generated from the authoritative Vanilla
Text Size: 12 points when no preference exists, or the existing valid explicit
size. Each file is created only when absent, becomes user-owned immediately,
and is never overwritten or merged automatically. Existing standards-defined
user MIME configuration also suppresses the MIME seed.

The same internal initializer publishes the machine and override seeds with
no-clobber semantics, invokes `xdg-user-dirs-update` only when its configuration
is absent, and delegates Appearance and Power & Idle defaults to their owning
backends. It remains separate from package/service integration and the full
bootstrap. See [Create-once initialization](create-once-initialization.md).

The future graphical-login authority is the Vanilla-owned SDDM theme and
`vanhyprarch.desktop` session. System integration deploys and validates that
payload before enabling normal `sddm.service`; it does not start or restart a
display manager during installation. SDDM is the only supported baseline;
fresh systems have no tty2-specific display-manager policy. System integration
rejects unsupported pre-existing display-manager configuration.

## Vanilla update boundary

A future Vanilla update replaces only validated Vanilla-managed content and
preflights newly required packages. It never silently runs `pacman -Syu`, never
performs an unsupported partial Arch upgrade, and never assumes ownership of
the administrator's full system upgrade. If the current Arch state cannot
safely satisfy a new package requirement, update must stop and ask the
administrator to update Arch first.

## External player installation

`install/install-zig-player` is now a compatibility entry point that delegates
to `vanhyprarch-screensaver install`; it is not a baseline bootstrap step. The
tracked immutable manager metadata pins release `v0.1.1`, Linux
`x86_64`, the exact asset name and SHA-256, and canonical release and source-tag
URLs. It never follows GitHub's `latest` redirect.

The manager downloads into a private temporary directory, verifies canonical
metadata, the exact archive digest and layout, each member digest, x86_64 ELF,
runtime libraries, destinations, ownership, and modes, then publishes the
complete XDG-aware payload. After prospective idle configuration parses, the
mode-0644 marker is published before the installed-capability fragment, so a
generated listener never precedes authoritative capability.
Install, adoption, repair, reinstall rollback, and uninstall are tested with
isolated home/data/runtime roots; production does not require a Git checkout.

Release v0.1.1 provides only x86_64. Other architectures fail closed until a
reviewed release adds an explicit asset and digest. Runtime requires glibc and
the Wayland client library, not Zig. Updating the player is a deliberate
metadata and validation change, never an unattended download of a newer tag.

## Flatpak and Flathub configuration

`flatpak` is an ordinary required official entry in
`packages/manifest-v1.toml`, without a version constraint. The shared bootstrap
must install the currently available official Arch package before it invokes
`install/configure-flatpak`.

The component uses the fixed system-scoped operation equivalent to:

```text
/usr/bin/flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

It first inspects enabled system remotes. An existing `flathub` pointing to
`https://dl.flathub.org/repo/` is accepted without a write. An existing
same-named remote with another URL fails closed and is not modified. After an
add, the component verifies the resulting name and URL. It never deletes or
rewrites user remotes, resets Flatpak state, or installs Flatpak applications.

## Optional dictation installation

Dictation is not a responsibility of the normal baseline bootstrap. An
explicit opt-in runs the independently deployed `vanhyprarch-dictation`
manager, also reached through the compatibility entry point
`install/dictation/install`. Missing `gnupg` or `wtype` package deltas from the
non-default `dictation` component in `packages/manifest-v1.toml` are offered
through an explicit terminal `[y/N]` confirmation for the exact package list.
After consent, the manager runs `sudo pacman -S --needed --noconfirm --` with
inherited terminal output, so package progress and errors remain visible
without a second pacman confirmation. The component refuses root,
unsupported architectures, CPUs without the x86-64-v3 features required by
the chosen AVX2 artifact, missing dependencies, symlink destinations, invalid
signatures, unexpected fingerprints, checksum mismatches, and version
mismatches.

The installer uses private temporary state and a dedicated GPG home. One
immutable `binaries.toml` manifest pins both stable Voxtype 1.0.1 artifacts:
the public-default AVX2 CPU build and the explicit opt-in Vulkan build. A new
candidate's SHA-256, detached signature, full primary fingerprint, size, and
exact `voxtype 1.0.1` version output are verified before it enters the
component-owned `$XDG_DATA_HOME/voxtype/binaries/1.0.1` cache. Every cached
candidate is rechecked before activation, then atomically deployed mode `0755`
as the regular file `$HOME/.local/bin/voxtype`. It installs
the default config only if the user has no Voxtype config; a differing config
before the first managed install requires explicit review, while later updates
preserve customization. Stable 1.0.1 setup writes a default config as a side
effect, so model acquisition runs with a private temporary `XDG_CONFIG_HOME`
and the intended final `XDG_DATA_HOME`; an explicit `--config` path alone is
not sufficient in this version. The installed binary runs the stable upstream
model workflow for `small.en`; Vanilla then verifies
the fixed filename, byte size, and SHA-256 before publishing the binary,
configuration, and service. Installation reloads the user-unit catalog, starts
the non-enabled service, requires active/healthy extended status for the exact
model and managed CPU digest, and publishes the component marker only after
health succeeds. Fresh-install failure safely removes complete transaction-
created config and data trees, plus a new runtime tree only after the service
is stopped and no live lock PID remains. Failure restores the previous payload
and service state.
Hyprland remains the cold-session startup owner at later logins.

The manager and its immutable `binaries.toml`, signing key, default template,
unit, and model manifest are production deployment artifacts. They must be
installed under `$HOME/.local/bin` and the project XDG data directory rather
than referring to a source checkout. Its versioned JSON status and catalog are
the authority consumed by SuperSpace. The ten reviewed models are downloaded
only through the tagged Voxtype workflow and then independently checked by
filename, size, and SHA-256 before selection.

An apply transaction prepares and verifies the target model, binary artifact,
runtime prerequisites, and candidate config while the existing daemon remains
available. It stops the service only after those checks, atomically publishes
only changed files, and requires both the service and Voxtype status to become
healthy with the requested model and exact artifact digest. Failure restores
the exact executable, config, and prior service state. Allowed recording limits
are 30, 60, 120, and 300 seconds; 120 is the public default. SuperSpace offers
CPU and Vulkan GPU without an Auto mode. Vulkan Apply verifies supported
hardware, official runtime packages, the exact signed artifact, and
vendor-aware process evidence before committing the transaction.

Updates are reviewed repository changes: select an explicit stable version and
asset, review the signing fingerprint, update the expected binary digest, run
the same staged signature/hash/version checks, replace atomically, then restart
the project service only after validation. Configuration and models stay in
place, and rollback material is retained until the replacement daemon is
healthy. No automatic or `latest` update path exists.

`vanhyprarch-dictation uninstall` (and its compatibility entry point) requires
the project service to stop successfully, then removes the exact managed
marker, service file, pinned binary, complete `$XDG_CONFIG_HOME/voxtype`
configuration root, and complete `$XDG_DATA_HOME/voxtype` data root. This is
the component's only uninstall mode; there is no separate purge. Recursive
deletion requires exact XDG-child paths, current-user ownership, ordinary
directories/files, and a symlink-safe platform implementation. A failed stop
or unsafe tree removes nothing. The independently deployed manager and its
immutable project resources remain so SuperSpace can offer Install again.
Generic packages such as `gnupg`, `wtype`, `vulkan-icd-loader`, and a vendor
ICD are not automatically removed.
For SuperSpace Install and Uninstall, the terminal helper publishes the manager
child's exit status inside a private runtime directory and a supervisor waits
for the real Foot process to finish. A successful result then triggers one
direct `hyprctl reload` before status refresh so F9 bindings match the marker in
the current session. Failure and settings Apply refresh status without reload;
Foot's window-close status alone is never treated as the transaction result.

## Verified archinstall 4.4 capabilities

`archinstall` is not installed on the current development system. The local
Arch sync database offered `archinstall 4.4-1` on 2026-09-08, so the matching
upstream 4.4 release source was inspected without running an installation.

The 4.4 argument and configuration implementation confirms:

- `--config` reads an ordinary local JSON configuration;
- `--config-url` retrieves an ordinary JSON configuration by URL;
- `--creds` and `--creds-url` load credentials separately, with optional
  credential-file encryption support;
- `--dry-run` generates and saves configuration, then exits before filesystem
  operations or installation;
- `bootloader_config`, `disk_config`, `network_config`, `kernels`, `packages`,
  `profile_config`, `app_config`, `timezone`, and `locale_config` represent the
  corresponding guided-installer choices;
- `network_config` supports NetworkManager through type `nm`;
- a Minimal profile exists, and `app_config.audio_config` supports PipeWire;
- `custom_commands` remains the current post-install command list.

In the 4.4 guided flow, `custom_commands` runs after base installation and the
selected users, applications, profile, packages, timezone, and services have
been processed. Each command is written temporarily beneath the target and run
with `arch-chroot`. The intended Vanilla HyprArch use is a small, auditable
command that obtains or locates the shared bootstrap and invokes it in the
installed system. It must not embed the bootstrap implementation in JSON.

The inspected 4.4 source is available in the upstream
[argument/configuration model](https://github.com/archlinux/archinstall/blob/4.4/archinstall/lib/args.py),
[guided installation flow](https://github.com/archlinux/archinstall/blob/4.4/archinstall/scripts/guided.py),
and [custom-command runner](https://github.com/archlinux/archinstall/blob/4.4/archinstall/lib/installer.py).

## Optional recommended archinstall configuration

The public project should eventually offer an optional recommended
configuration that a user can load locally with `--config` or remotely with
`--config-url`, then review in the guided installer before installation.

| Choice | archinstall 4.4 support | Vanilla HyprArch position |
| --- | --- | --- |
| Bootloader | `bootloader_config` | Recommended choice to be finalized; do not invent one from the development machine. |
| Filesystem and layout policy | `disk_config` | Recommended filesystem and layout to be finalized; the target device always remains user-selected. |
| Network | `network_config` | Preselect NetworkManager, the accepted baseline owner. |
| Installation profile | `profile_config` | Use the Minimal profile so the shared bootstrap owns the desktop baseline. |
| Kernel | `kernels` | Recommended choice or selection policy to be finalized, including hardware implications. |
| Audio | `app_config.audio_config` | PipeWire is accepted; decide later whether the preset or bootstrap installs it, without duplicating ownership. |
| Additional base packages | `packages` | Include only prerequisites useful before the bootstrap; `packages/manifest-v1.toml` remains authoritative. |
| Timezone and locale | `timezone`, `locale_config` | No project-wide values are accepted; leave them for review unless defaults are decided later. |
| Bootstrap hook | `custom_commands` | Invoke the shared bootstrap after base installation. |

The recommended configuration must remain optional. Loading it does not remove
the user's responsibility to inspect the installation summary and confirm all
destructive or machine-specific choices.

## Public and sensitive configuration

The public recommended configuration must not contain:

- a target disk path or a destructive choice tied to one machine;
- a username, password or password hash, encryption passphrase, token, or
  other secret;
- a personal hostname, home path, or machine-specific graphics choice.

Credentials belong in a separately supplied, untracked credentials file or in
interactive prompts using archinstall's `--creds` separation where applicable.
Ordinary but machine-specific values, including the target disk and hostname,
must also be supplied or explicitly confirmed by the user. Hardware-dependent
graphics configuration must be selected dynamically or during review.

## Version-sensitive integration

Archinstall follows Arch's rolling release. Before publishing or updating a
recommended configuration:

1. identify the archinstall version on the current official Arch ISO;
2. generate or save a configuration with that version and exercise
   `--dry-run` where appropriate;
3. validate the exact parser keys and guided review flow in a disposable test
   environment before any real disk operation;
4. keep credentials separate and confirm that generated ordinary
   configuration contains no secrets or machine identity;
5. test the thin bootstrap invocation and first-reboot result;
6. update `docs/compatibility.md` with the newly validated baseline.

Do not assume old JSON keys remain valid. In particular, the inspected 4.4
tag's bundled `schema.json` still describes some legacy top-level names while
the 4.4 parser and serializer use structured keys such as
`bootloader_config`, `profile_config`, and `app_config`. Configuration generated
and parsed by the exact target version is stronger evidence than a copied
example or stale schema.

The shared bootstrap should expose a stable input contract and remain less
sensitive to archinstall schema changes.

## Future installation work

The existing `install/` tree contains the pinned external-player component,
the idempotent system-Flathub configuration component, the managed-file and
create-once cores, the narrow pre-Python bootstrap, and the internal Phase 4
system-integration stage. Phase 4 passed guided destructive/reboot and
integrated Phase 2/3/4 acceptance in the user's disposable GNOME Boxes VM.
The shared top-level post-install orchestration is `install.sh`. Future work
may add a small archinstall integration and recommended configuration or
template. Exact filenames for that remaining integration are intentionally not
selected until the current archinstall schema is designed.

Unresolved installation choices are the recommended bootloader, filesystem,
layout policy, kernel policy, any project-wide timezone or locale defaults,
hardware-selection rules, and the exact safe delivery mechanism for invoking
the bootstrap from archinstall.
