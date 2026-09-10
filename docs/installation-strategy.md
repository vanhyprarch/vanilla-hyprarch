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
- deploy tracked home and system configuration without personal paths;
- deploy the main `vanhyprarch` named Quickshell configuration;
- install project commands, including the screensaver lifecycle controller, in
  an appropriate user or system PATH;
- invoke the pinned external-player installer so
  `vanhyprarch-zig-player` is available in that same PATH;
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

The existing `install/` tree contains only the pinned external-player
component and its metadata. Future work may add the shared bootstrap, a small
archinstall integration and recommended configuration or template, and
post-install validation. Exact filenames are intentionally not selected until
the bootstrap interface and current archinstall schema are designed.

Unresolved installation choices are the recommended bootloader, filesystem,
layout policy, kernel policy, any project-wide timezone or locale defaults,
hardware-selection rules, and the exact safe delivery mechanism for invoking
the bootstrap from archinstall.
