# DF2 system integration

DF2 Phase 4 adds the installer-internal `install/bootstrap` entry point and
`install/system_integration.py` stage. The shell entry point exists only to
cross a fresh Arch system from no Python to a verified `python` package. A
separate invocation then executes the Python stage. The Python stage consumes
the package, service-policy, and ownership-v2 manifests and exposes `plan`,
`apply`, and `validate`. Neither layer is the final installer or a public session command.
The feature remains pending destructive acceptance in a user-managed
disposable Arch x86_64 VM; it must never be applied to the development host.

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
  -> bootstrap plan
  -> bootstrap-python
  -> bootstrap plan (complete Phase 4 plan)
  -> human review
  -> bootstrap apply
```

With Python absent, `bootstrap-python` requires root, installs and verifies only
the interpreter, prints the required next planning step, and exits successfully
without entering Python system integration. A no-Python `apply` refuses with a
Python-bootstrap-required error. Once Python is present, `plan`, `apply`, and
`validate` verify the interpreter and execute `system_integration.py` with the
same operation, source root, and target user. Repeating `bootstrap-python`
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

Production `apply` runs as root and requires an explicit existing non-root
target username. Root owns pacman transactions, adopted system configuration,
the system Flatpak remote, root provenance, and system-unit enablement. The
fixed AUR clone and every Git/makepkg inspection/build command cross one narrow
boundary through `runuser` and execute as the target user. The target cannot be
root, its HOME must be a real owned non-group/world-writable directory, and the
private build directory is created unpredictably beneath safe root-owned
`/var/tmp`. No manifest or user string is evaluated by a shell.

The production CLI has no alternate-system-root switch. Tests inject a command
runner, account resolver, and disposable filesystem root; their fake boundary
rejects every command it does not explicitly model.

## Arch and package preflight

The supported base is Arch Linux x86_64. The stage reads the package-owned
`/usr/lib/os-release` identity, queries `uname -m`, verifies that pacman's
installed-package database is usable, verifies that the existing sync databases
resolve pacman itself, and runs `pacman -Qu` against those already-present
databases. Any pending upgrade blocks provisioning with an instruction for the
administrator to perform a normal full `pacman -Syu` first.

Vanilla never runs `pacman -Sy`, never refreshes databases independently, and
never silently runs `pacman -Syu`. Missing default official packages are
derived only from `packages/manifest-v1.toml`, checked with read-only
`pacman -Sp`, and installed in one `pacman -S --needed --noconfirm`
transaction. A resolution or transaction failure stops with the successfully
installed package state left to pacman; Vanilla implements no package rollback.

`default_install=true`, not package role, selects the transaction. This keeps
recommended `pavucontrol` and `bluez-utils` in the normal Alpha install while
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
the stage requires exactly one package output and verifies its `.PKGINFO`
pkgname, pkgbase, and architecture before privileged `pacman -U` installation.
The exact private build directory is removed afterward.

The `.SRCINFO` reader keeps repeatable fields as lists and evaluates the
selected `yay` pkgname section separately from the shared pkgbase section.
Multiple unique pkgbase architectures are valid; the selected package is
eligible on Alpha when its effective list contains `x86_64`, or contains only
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

Only default system entries with `enabled` or `disabled` policy in
`deployment/service-policy-v1.toml` are mutated:

- enable `NetworkManager.service`;
- enable `bluetooth.service`;
- enable `ly@tty2.service`;
- disable `getty@tty2.service`.

Phase 4 changes enablement only; it does not start, stop, or restart units.
Package/D-Bus-activated user services and every static Vanilla user unit are
observed only through the manifest and never passed to systemctl. Ly retains
the package-owned Hyprland session and no Vanilla Ly configuration is created.

The service transaction durably records every exact prior and desired state
before the first mutation. An ordinary failure rolls back changes from that
local transaction. After an abrupt exit, a mutating invocation restores prior
states before commit or keeps verified desired states after commit. States
outside the supported persistent `enabled`/`disabled` pair fail closed rather
than being approximated.

## State, ordering, and failure semantics

Private root state is stored as mode-0600 JSON beneath the root-owned mode-0700
`/var/lib/vanhyprarch/` directory:

- `system-integration-v1.json` contains only BlueZ adoption provenance,
  committed service-policy identity, and diagnostics for a yay build performed
  by Vanilla;
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
Flathub, service policy, and final validation. Pacman and Flatpak retain their
own transaction semantics; there is deliberately no global rollback. A later
failure leaves earlier successful stages in known state, and a rerun queries
reality and converges.

`plan` performs no writes and reports recovery as required rather than acting.
`validate` is read-only and requires every default official package, valid yay,
known BlueZ adoption, exact system Flathub, and declared system enablement. A
second successful `apply` performs no package transaction, yay rebuild, BlueZ
rewrite, Flathub mutation, service mutation, or provenance rewrite.

## Acceptance boundary

Deterministic tests use fake pacman, systemctl, Flatpak, Git, makepkg, and
archive inspection plus disposable roots and abrupt child-process exits. They
are not a substitute for real system integration. Publication remains blocked
until the user prepares and snapshots a disposable current Arch x86_64 VM in
GNOME Boxes and completes guided package, reboot, service, BlueZ, Flatpak, and
integrated Phase 2/3/4 acceptance. Phase 4 is never applied to the development
host. The manual VM must exercise `install/bootstrap` while Python is absent;
manually installing Python would bypass the bootstrap acceptance under test.
