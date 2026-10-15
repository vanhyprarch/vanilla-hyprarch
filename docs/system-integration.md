# DF2 system integration

DF2 Phase 4 adds the installer-internal `install/bootstrap` entry point and
`install/system_integration.py` stage. The shell entry point exists only to
cross a fresh Arch system from no Python to a verified `python` package. A
separate invocation then executes the Python stage. The Python stage consumes
the package, service-policy, and ownership-v2 manifests and exposes `plan`,
`apply`, and `validate`. Neither layer is the final installer or a public session command.
The feature passed full, idempotence, reboot, and integrated Phase 2/3/4
acceptance in a user-managed disposable Arch x86_64 VM. It must never be
applied to the development host.

The v1.0.2 release updater reuses Update System's interactive `yay -Syu`
as the unprivileged desktop user in the release updater, **before** this authority
plans or applies a new Vanilla target. It does not add `-Syu` to system integration
or change its package/recovery boundaries. See [updater maintenance and reboot
policy](release-engineering.md#next-release-development-arch-maintenance-before-a-new-update).
The immutable v1.0.1 updater retains its manual Arch maintenance prerequisite.

## Pre-Python bootstrap boundary

A fresh Arch Minimal installation does not necessarily contain Python, even
though `python` is a required/default Vanilla package. `install/bootstrap`
closes that bootstrapping cycle without becoming a second installer. It uses
only the supported Arch base shell and fixed base-system command paths, accepts
an explicit non-root target user, and owns exactly one possible mutation:

```text
pacman -S --needed --noconfirm -- python
```

Before that transaction it verifies `ID=arch` from `/usr/lib/os-release`,
x86_64, pacman availability,
the target account, an empty `pacman -Qu` result against the existing sync
database, and read-only resolution of `python`. It never refreshes databases,
runs `pacman -Sy`, or runs `pacman -Syu`. If upgrades are pending, the
administrator must complete a normal full Arch upgrade first. If Python is
already installed, this layer makes no package change.

The first-install sequence deliberately contains two separately approved
mutation boundaries:

```text
source acquired
  -> ./install/bootstrap plan --target-user USER
     (preliminary; non-root allowed while Python is absent)
  -> sudo ./install/bootstrap bootstrap-python --target-user USER
  -> capture context as USER with install/secret_service_preflight.py context
  -> sudo ./install/bootstrap plan --target-user USER --target-context-json CONTEXT_JSON
     (complete authoritative Phase 4 plan; read-only)
  -> human review
  -> sudo ./install/bootstrap apply --target-user USER --target-context-json CONTEXT_JSON
  -> sudo ./install/bootstrap validate --target-user USER --target-context-json CONTEXT_JSON
```

With Python absent, `bootstrap-python` requires root, installs and verifies only
the interpreter, prints the required next planning step, and exits successfully
without entering Python system integration. A no-Python `apply` refuses with a
Python-bootstrap-required error. Once Python is present, the complete `plan`,
`apply`, and `validate` operations require root, verify the interpreter, and
execute `system_integration.py` with the same operation, source root, and target
user. A system that already has Python therefore starts with
the context capture followed by `sudo ./install/bootstrap plan --target-user USER
--target-context-json CONTEXT_JSON`. For a normal-user Bash invocation after
Python is available, the read-only stage plan is:

```bash
target_user=$(id -un)
target_context=$(python -B install/secret_service_preflight.py context)
sudo ./install/bootstrap plan --target-user "$target_user" \
  --target-context-json "$target_context"
```

Keep the captured context for the separately authorized apply/validate stages;
never reconstruct it from root's environment. Repeating `bootstrap-python`
preserves the verified interpreter without another package transaction and
still does not delegate.

An absent-Python `plan` reports only the interpreter bootstrap action because
the manifest-driven planner cannot execute yet; it performs no writes.
`validate` never installs the interpreter. The production `bootstrap-python`
mutation and later Python `apply` path require root, while all yay build work
remains exclusively in the Python stage as the explicit non-root target user.
The shell layer contains no package manifest, service, BlueZ, Flatpak,
managed-file, or create-once logic.

## Privilege boundary

Production `plan`, `apply`, and `validate` run as root and require an explicit
existing non-root target username. Plan and validate remain strictly read-only,
but root is required to interpret the private adoption provenance, backups, and
recovery state under `/var/lib/vanhyprarch` authoritatively. A non-root full
plan or validation fails before emitting partial semantic results; private
state is not made world-readable or mirrored into HOME. Root also owns pacman
transactions, adopted system configuration, the system Flatpak remote, and
system-unit enablement. The fixed AUR clone and every Git/makepkg
inspection/build command cross one narrow boundary through `runuser` and
execute as the target user. The target cannot be root, its HOME must be a real
owned non-group/world-writable directory, and the private build directory is
created unpredictably beneath safe root-owned `/var/tmp`. No manifest or user
string is evaluated by a shell.

The production CLI has no alternate-system-root switch. Tests inject a command
runner, account resolver, and disposable filesystem root; their fake boundary
rejects every command it does not explicitly model.

## Release-upgrade stage mode

Secret Service provisioning runs an installer-only read-only `preflight`
from `install/secret_service_preflight.py` as the target user before official package
mutation, including fresh and upgrade paths. Plan and validate also expose
conflicts. The probe inspects KeePassXC's `FdoSecrets/Enabled`, standard/XDG and
configured D-Bus service directories, activation availability, and current bus
ownership without activating a provider or reading keyring contents. Package
`Provides` metadata is not a provider decision. Competing or ambiguous state
blocks provisioning; no existing provider registration, password manager,
keyring, or PAM file is rewritten. Missing SDDM PAM hooks or unsupported hook
ordering also block instead of acquiring PAM ownership. A fresh installation
without SDDM can install its official defaults first; validation then checks
the hooks. The probe is never invoked during graphical startup. See
[Secret Service](secret-service.md) for the session boundary and physical acceptance.

Provider discovery requires explicit `--target-context-json` invocation data
captured as the target user before sudo. The context contains only UID, account
HOME, XDG config/data homes and data search paths, and an optional provider
configuration path. Identity, required keys, and absolute paths are validated
before the probe; the same payload crosses `runuser`. Root/sudo environment
variables are ignored. Fresh installation and the user-launched updater forward
this context through existing stage arguments; there is no new persistent
context record. A root-only invocation with unknown target context fails closed.
This explicit input is an administrator-reviewed context declaration, not an
authentication token. Capture it in the actual target-user session rather than
manufacturing default paths from a root shell.

The Python authority now accepts `--lifecycle upgrade` for `plan`, `apply`,
and `validate`. The default `fresh` mode and pre-Python shell bootstrap retain
their installation behavior. Upgrade requires prior root-private system state
with the official-package and system-artifact inventory recorded by a completed
fresh apply. It also requires the separate SDDM provenance. These records
distinguish an old managed file that went missing from a target addition; the
former is drift, while the latter can be created when no foreign target exists.
An interrupted new-file publication has a local pending intent and can rerun.

New official packages and their new dependencies may be installed only when
the current Arch sync state has no pending upgrades. The read-only package
preview must contain no already installed package. The installer-only
`package_relationships.py` checks the complete name/version/repository preview
against the databases selected by `pacman-conf`, using read-only libalpm APIs.
Installed names and versioned virtual providers are matched by upstream code;
conflicts in either direction, conflicts or replacements between proposed
packages, actual installed-package replacements, unresolved dependencies, and
ambiguous metadata fail closed. A package's own virtual provision is not a
conflict with itself. No libalpm transaction is initialized or committed, and
pacman's existing signature and installation path are unchanged. A
missing package required by the old inventory is drift. Dropped
manifest packages remain installed. Upgrade preserves `yay` without an AUR
build or upgrade, and does not restore a missing formerly required Flathub
remote as a fresh adoption. Service changes apply only to target-declared
units after comparison with prior service-policy provenance. A changed BlueZ
candidate remains a conflict until an explicit provenance-safe replacement
path is designed. The stage does not advance the installed release identity
or implement the release transaction.

After the official `xdg-terminal-exec` package is verified, apply ensures the
mode-0644 root-owned Foot fallback at
`/usr/local/share/xdg-terminal-exec/hyprland-xdg-terminals.list`. Plan is
read-only, validate requires the exact file, and an already-correct file is
preserved. Symlinks, unsafe parents, or conflicting content fail closed.

## Arch and package preflight

The supported base is Arch Linux x86_64. The stage reads the package-owned
`/usr/lib/os-release` identity, queries `uname -m`, verifies that pacman's
installed-package database is usable, verifies that the existing sync databases
resolve pacman itself, and runs `pacman -Qu` against those already-present
databases. Any pending upgrade blocks provisioning with an instruction for the
administrator to perform a normal full `pacman -Syu` first.

This authority never runs `pacman -Sy`, never refreshes databases independently, and
never silently runs `pacman -Syu`. Missing default official packages are
derived only from `packages/manifest-v1.toml`, checked with read-only
`pacman -Sp`, and installed in one `pacman -S --needed --noconfirm`
transaction. A resolution or transaction failure stops with the successfully
installed package state left to pacman; Vanilla implements no package rollback.

`default_install=true`, not package role, selects the transaction. This keeps
recommended `pavucontrol` and `bluez-utils` in the default install while
excluding printing, network printing, dictation deltas, hardware-specific
Vulkan choices, and every other non-default component.

## yay bootstrap and AUR trust

`yay` remains the sole default AUR exception. If an installed foreign package
named `yay` owns an executable `/usr/bin/yay`, it is preserved. Otherwise the
stage clones exactly `https://aur.archlinux.org/yay.git` into a new private
target-user-owned directory and records the exact Git commit.

`makepkg --printsrcinfo` supplies the current `depends`, `makedepends`, and
`checkdepends`. Vanilla verifies each dependency is satisfiable by the current
official repositories, installs missing official dependencies through pacman,
and refuses any dependency that would require another AUR package. `go` is not
mirrored in the static Vanilla manifest. `makepkg` builds as the target user;
the stage requires exactly one primary package output and verifies every
predicted archive through its `.PKGINFO` before privileged installation. The
primary must identify `pkgname=yay`, `pkgbase=yay`, `pkgtype=pkg`, and a
compatible architecture. One additional `yay-debug` archive is accepted only
when its metadata identifies the same pkgbase, `pkgtype=debug`, and a compatible
architecture. This accommodates Arch's standard `strip` plus `debug` makepkg
behavior without changing system or user makepkg configuration. Only the
primary `yay` archive is passed to `pacman -U`; the auxiliary debug archive is
not installed or added to the AUR manifest. Unexpected, duplicate, ambiguous,
unsafe, or malformed outputs fail closed. The exact private build directory,
including an unused debug archive, is removed afterward.

The `.SRCINFO` reader keeps repeatable fields as lists and evaluates the
selected `yay` pkgname section separately from the shared pkgbase section.
Multiple unique pkgbase architectures are valid; the selected package is
eligible when its effective list contains `x86_64`, or contains only
`any`. Missing architecture metadata, duplicates, `any` mixed with another
architecture, and architecture lists that exclude x86_64 fail closed.
Architecture-qualified dependencies for other targets are not installed on
x86_64. This source compatibility check is distinct from the later `.PKGINFO`
check of the package archive actually produced by makepkg.

AUR PKGBUILDs are community code executed as the non-root build user. The
approved exception is not equivalent to an official package trust boundary and
does not authorize recursive AUR dependency resolution.

## BlueZ privileged adoption

Ownership v2 supplies the sole `ADOPTED_PRIVILEGED` mapping from
`system/etc/bluetooth/main.conf` to `/etc/bluetooth/main.conf`. A first adoption
requires a root-owned mode-0644 regular target and pacman-native proof that the
installed `bluez` package owns it and reports the backup file as unmodified via
`pacman -Qii` under the C locale. Timestamps and package presence alone are not
evidence. Any customized, missing, symlinked, wrong-type, wrong-mode,
wrong-owner, or otherwise ambiguous target fails closed.

Before publication, the exact original bytes are placed without clobber under
the private root-owned `/var/lib/vanhyprarch/bluez/` directory. Provenance
records the original hash, mode, uid/gid, target, backup path, and BlueZ package
version plus the deployed hash and metadata. The candidate is fsynced and
atomically replaced in `/etc/bluetooth`, whose directory is then fsynced. The
service is not restarted.

A durable local transaction distinguishes interrupted adoption from manual
drift. Before provenance commit, recovery restores the exact package file and
removes only backup material proved to belong to that transaction. After the
main state commits, recovery retains the verified Vanilla candidate and its
permanent original backup. An unrelated pre-existing backup is never removed
or overwritten.

## Flatpak and service policy

The existing `install/configure-flatpak` component remains the mutation owner
for the system Flathub remote. Planning and validation inspect system remotes.
An absent stable `flathub` is added from the canonical descriptor, an exact
`https://dl.flathub.org/repo/` remote is preserved, and duplicate or conflicting
same-named configuration fails closed. No user remote, beta remote, or Flatpak
application is changed.

After the official `flatpak` package and system Flathub are available, the
root stage ensures `/var/lib/flatpak/exports/share/applications` exists as
root-owned mode-0755 directory scaffolding. Plan only reports its state;
validation requires it. Existing safe directories are preserved without mode,
owner, timestamp, or content changes. Symlinked, non-directory, inaccessible,
or unexpectedly owned path components fail closed. Flatpak owns exported
desktop files and all other content; this stage does not inspect descendants.

Phase 5 Slice 3 defines the supported default-system policy as:

- enable `NetworkManager.service`;
- enable `bluetooth.service`;
- enable normal `sddm.service` display-manager semantics.

Fresh systems receive no special tty2/getty display-manager policy. An
unsupported pre-existing display-manager alias is a blocker. Integration
changes enablement only; it does not start, stop, restart, or reload
display-manager units.
Package/D-Bus-activated user services and every static Vanilla user unit are
observed only through the manifest and never passed to systemctl.

The service transaction durably records every exact prior and desired state
before the first mutation. An ordinary failure rolls back changes from that
local transaction. After an abrupt exit, a mutating invocation restores prior
states before commit or keeps verified desired states after commit. States
outside the supported persistent `enabled`/`disabled` pair fail closed rather
than being approximated.

## State, ordering, and failure semantics

Private root state is stored as mode-0600 JSON beneath the root-owned mode-0700
`/var/lib/vanhyprarch/` directory:

- `system-integration-v1.json` contains BlueZ adoption provenance, committed
  service-policy identity, the SDDM baseline marker, and diagnostics for a yay
  build performed by Vanilla;
- `system-integration-transaction-v1.json` exists only for an incomplete BlueZ
  or service-policy local transaction;
- `system-integration.lock` serializes mutating invocations without storing
  preferences or operation results;
- `bluez/main.conf.pre-vanilla` is the permanent exact pre-adoption backup.

It does not contain preferences, a copy of pacman's inventory, user state, or
Flatpak internals. JSON publication uses a private temporary file, exact mode,
file fsync, atomic replacement, and parent-directory fsync.

Mutating invocations recover a known incomplete local transaction before new
work. Normal order is Arch preflight, official packages, yay, BlueZ adoption,
Flathub, Flatpak export scaffolding, service policy, and final validation.
Pacman and Flatpak retain their own transaction semantics; there is
deliberately no global rollback. A later failure leaves earlier successful
stages in known state, and a rerun queries
reality and converges.

`plan` performs no writes and reports recovery as required rather than acting.
`validate` is read-only and requires every default official package, valid yay,
known BlueZ adoption, exact system Flathub, safe Flatpak export scaffolding,
and declared system enablement. A second successful `apply` performs no package
transaction, yay rebuild, BlueZ rewrite, Flathub mutation, service mutation,
or provenance rewrite.

## Acceptance boundary

Deterministic tests use fake pacman, systemctl, Flatpak, Git, makepkg, and
archive inspection plus disposable roots and abrupt child-process exits. The
user-managed Arch Minimal GNOME Boxes VM additionally passed no-Python
bootstrap, partial-state resume, package/yay/BlueZ/Flatpak/service integration,
preserve-only repeat apply, reboot, and integrated Phase 2/3/4 validation.
Phase 4 is never applied to the development host.

The supported chain is `SDDM X11 greeter -> Vanilla theme ->
/usr/bin/start-hyprland -> Hyprland Wayland`; UWSM remains absent and
unsupported. Fresh-install acceptance from the saved VM snapshot passed,
including bootstrap, direct SDDM installation, authentication, logout/login,
and reboot persistence.
