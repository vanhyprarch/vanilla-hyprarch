# Installation strategy

This document is the canonical plan for making Vanilla HyprArch reproducible.
The pinned external-player installer is implemented; no shared project
bootstrap or archinstall preset exists yet.

The current repository is therefore a development and testing source tree, not
a copy-and-run installation payload. In particular, its tracked Hyprland
display/input profile and complete BlueZ `main.conf` replacement must be
reviewed rather than copied blindly onto another system.

## One bootstrap, two entry points

Vanilla HyprArch will have one reusable bootstrap implementation with two
supported callers:

1. **Archinstall-time:** an optional Vanilla HyprArch configuration helps the
   user install base Arch, then invokes the shared bootstrap inside the target
   system before the first reboot.
2. **Post-install:** the same bootstrap runs independently on a fresh minimal
   Arch installation with working Internet access.

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

This first-reboot experience is not implemented yet.

## Bootstrap responsibilities

The shared bootstrap will eventually:

- install `packages/official.txt` from official Arch repositories;
- install the explicit `yay` exception declared by `packages/aur.txt`, without
  treating it as permission to add other AUR dependencies;
- after installing the required unpinned `flatpak` package, invoke
  `install/configure-flatpak` to establish the required system Flathub remote;
- deploy tracked home and system configuration without personal paths;
- deploy the main `vanhyprarch` named Quickshell configuration;
- atomically install regular executable files for public project commands,
  including `vanhyprarch-idle`, `vanhyprarch-screensaver`, and
  `vanhyprarch-screenshot`, under `$HOME/.local/bin` without depending on a Git
  checkout;
- invoke the pinned external-player installer so
  `vanhyprarch-zig-player` is installed in that same directory;
- establish required symlinks and enable or disable documented services;
- deploy the minimal `system/etc/bluetooth/main.conf` before starting or
  enabling `bluetooth.service`, preserving exact rollback material if an
  existing administrator configuration would be replaced;
- preserve the documented startup owner for each session process;
- create safe initial state, including Power & Idle at all `Never`, automatic
  lock at `None`, `effect=colormix`, and Caffeine off;
- respect dependency ordering and migrations, remain idempotent where
  practical, fail closed on invalid state, and run post-install validation.

For every integrated feature, its package source, files, commands, services,
deployment, startup ownership, defaults, dependencies, migration behavior, and
validation must be recoverable from the canonical repository. Development-
machine behavior alone is not complete integration.

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

## External player installation

`install/install-zig-player` is a reusable bootstrap component, not a copy of
the external project. Its tracked metadata pins release `v0.1.1`, Linux
`x86_64`, the exact asset name and SHA-256, and canonical release and source-tag
URLs. It never follows GitHub's `latest` redirect.

The normal per-user destination is
`$HOME/.local/bin/vanhyprarch-zig-player`. The installer downloads into a
private temporary directory, verifies the hard-coded digest before extraction,
requires an exact archive layout, and atomically installs the executable with
mode `0755`. The upstream LICENSE and `THIRD_PARTY_NOTICES.md` are installed
under the user's XDG-style data tree together with the README and pinned source
metadata. `DESTDIR` and an install-home override support packaging and isolated
tests without touching a live home.

Release v0.1.1 provides only x86_64. Other architectures fail closed until a
reviewed release adds an explicit asset and digest. Runtime requires glibc and
the Wayland client library, not Zig. Updating the player is a deliberate
metadata and validation change, never an unattended download of a newer tag.

## Flatpak and Flathub configuration

`flatpak` is an ordinary required entry in `packages/official.txt`, without a
version constraint. The shared bootstrap must install the currently available
official Arch package before it invokes `install/configure-flatpak`.

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
`install/dictation/install`. Missing `gnupg` or `wtype` package deltas from
`packages/optional-dictation-official.txt` are offered through a visible
interactive pacman transaction. The component refuses root,
unsupported architectures, CPUs without the x86-64-v3 features required by
the chosen AVX2 artifact, missing dependencies, symlink destinations, invalid
signatures, unexpected fingerprints, checksum mismatches, and version
mismatches.

The installer uses private temporary state and a dedicated GPG home. It stages
the fixed Voxtype 1.0.1 AVX2 binary and signature, verifies the pinned SHA-256,
signature, full primary fingerprint, and exact `voxtype 1.0.1` version output,
then atomically deploys mode `0755` to `$HOME/.local/bin/voxtype`. It installs
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

The manager and its immutable `voxtype.conf`, signing key, default template,
unit, and model manifest are production deployment artifacts. They must be
installed under `$HOME/.local/bin` and the project XDG data directory rather
than referring to a source checkout. Its versioned JSON status and catalog are
the authority consumed by SuperSpace. The ten reviewed models are downloaded
only through the tagged Voxtype workflow and then independently checked by
filename, size, and SHA-256 before selection.

An apply transaction prepares and verifies a model and candidate config while
the existing daemon remains available. It validates stable Voxtype schema and
resolved values, stops the service only when a daemon-read setting changes,
atomically publishes the config, and requires both the service and Voxtype
status to become healthy. Failure restores the exact config and prior service
state. Allowed recording limits are 30, 60, 120, and 300 seconds; 120 is the
public default. Vulkan is not implemented or selectable yet.

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
Generic packages such as `gnupg` and `wtype` are not automatically removed.
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
| Additional base packages | `packages` | Include only prerequisites useful before the bootstrap; `packages/official.txt` remains authoritative. |
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

The existing `install/` tree contains the pinned external-player component and
the idempotent system-Flathub configuration component. Future work may add the
shared bootstrap, a small archinstall integration and recommended configuration
or template, and post-install validation. Exact filenames for those remaining
pieces are intentionally not selected until the bootstrap interface and current
archinstall schema are designed.

Unresolved installation choices are the recommended bootloader, filesystem,
layout policy, kernel policy, any project-wide timezone or locale defaults,
hardware-selection rules, and the exact safe delivery mechanism for invoking
the bootstrap from archinstall.
