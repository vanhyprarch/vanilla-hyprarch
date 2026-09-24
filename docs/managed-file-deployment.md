# Managed-file deployment

DF2 Phase 2 implements the installed-mode deployment core for user-space
artifacts classified as `VANILLA_MANAGED` in
`deployment/ownership-v2.toml`. It is the managed-file authority used by the
public bootstrap, not the complete installer.

## Boundary

`install/managed_deploy.py` is an internal source/release command and Python
library. It is intentionally not installed as a public session command. It
does not invoke pacman, yay, sudo, systemctl, a user manager, a package
service, or a live desktop process.

Its complete Phase 2 command surface is
`plan/install/update/reconcile/validate`.

The engine actively refuses an explicitly requested artifact outside
`VANILLA_MANAGED`. It never deploys create-once, user-owned, backend-owned,
generated, runtime, package-owned, adopted privileged, or optional-component
payload artifacts. In particular, Phase 2 does not create machine or override
configuration, mpv or MIME configuration, wallpaper starter copies, durable
preferences, or `/etc/bluetooth/main.conf`.

The ownership manifest remains the inventory and path authority. The Phase 2
addition to that contract is deliberately small:

- every managed tree has explicit directory and ordinary-file modes;
- executable members of a tree are named explicitly with an executable mode;
- optional lightweight validators are named on their artifact;
- one `BACKEND_OWNED` artifact declares the deployment provenance path.

No source file is discovered through Git. A checkout and an extracted release
tree are equivalent inputs.

## Current managed inventory

The current manifest supplies exactly 23 Phase 2 artifacts:

- Hyprland configuration: `hyprland-loader`, `hyprland-managed-core`,
  `hypridle-config`, `hyprpaper-config`, and `hyprlock-config`;
- shell configuration: `quickshell-config`;
- notification configuration: `dunst-config`;
- public commands: `appearance-command`, `default-apps-command`,
  `dictation-command`, `idle-command`,
  `keyboard-command`, `monitor-command`, `polkit-command`,
  `screensaver-command`, and `screenshot-command`;
- user systemd files: `keyboard-unit`, `monitor-transaction-unit`, and
  `polkit-drop-in`;
- project data/resources: `wallpaper-assets`, `zig-screensaver-manager`,
  `zig-screensaver-metadata`, and `dictation-resources`.

This inventory is descriptive; the executor still selects it from the
manifest rather than from a Python list.

## Invocation

The CLI requires an explicit absolute release root. Target paths may be taken
from the target user's environment or supplied explicitly:

```text
python install/managed_deploy.py \
  --source-root /absolute/path/to/vanilla-release \
  [--release-id IDENTIFIER] \
  [--home HOME] \
  [--xdg-config-home PATH] \
  [--xdg-data-home PATH] \
  [--xdg-state-home PATH] \
  plan install|update|reconcile

python install/managed_deploy.py [same options] install
python install/managed_deploy.py [same options] update
python install/managed_deploy.py [same options] reconcile
python install/managed_deploy.py [same options] validate
```

`plan` shares source validation, target resolution, provenance, conflict, and
action classification with real deployment but performs no writes. Its
tab-separated records are deterministic:

```text
ACTION<TAB>ARTIFACT_ID<TAB>DECLARATIVE_TARGET<TAB>REASON
```

Actions are `create`, `replace`, `remove`, `preserve`, `conflict`, or
`recovery-required`. The last action is read-only evidence that a prior
deployment stopped at a durable transaction milestone. `plan` never performs
that recovery. `validate` likewise reports the incomplete transaction without
mutating it; `install` and `update` recover it before planning any new work.

`install` expects absent managed targets. An existing destination without
valid Vanilla provenance is a conflict even when its bytes happen to match.
Repeating the same completed install is a no-op. A partial install created by
an interrupted Phase 2 operation may resume only against the same release
digest.

`update` requires valid prior provenance. It replaces changed managed
artifacts, leaves byte-and-mode-identical artifacts untouched, adds new
managed artifacts, and removes an artifact absent from the new manifest only
when its previous target and exact content are still proven by provenance.
Missing or modified managed content fails closed instead of adopting or
overwriting it.

`reconcile` is the public bootstrap's provenance-aware operation selector. No
provenance selects `install`; complete valid provenance selects `update`; and
partial provenance selects only its recorded `install` or `update` operation
so recovery cannot change operation or release. Malformed, unsafe, unsupported,
or conflicting provenance fails through the same authoritative loader before
selection. `plan reconcile` performs the same read-only selection and then
uses the selected operation's ordinary planner.

`validate` verifies the provenance schema and mode, complete artifact
inventory, regular-file/directory types, current-user ownership, exact modes,
hashes, lightweight artifact validators, and equality with the supplied
release.

## Target and source safety

Target context resolves HOME plus XDG config, data, and state roots. Standard
fallbacks are `$HOME/.config`, `$HOME/.local/share`, and
`$HOME/.local/state`. Values must be absolute. Declarative target expressions
are parsed as data rather than shell-expanded, and only the supported
HOME/XDG forms are accepted.

Source paths must be normalized relative paths beneath the explicit release
root. Deployable target paths must stay beneath their selected target root.
Duplicate or overlapping destinations and source/destination overlap are
rejected. NUL, traversal, patterns in deployable suffixes, missing sources,
special files, and unexpected source symlinks fail closed.

Existing destination symlinks and symlinked parent components are never
followed. An existing unknown file, tree, or type mismatch is a conflict.
Phase 2 deliberately has no development-symlink adoption flag, so running it
against the current repository-backed live development layout fails closed.

The engine runs as the receiving user, creates no arbitrary ownership, and
does not call `chown`. HOME and managed installed content must belong to the
current UID/GID. Newly needed parent directories use mode `0755`; existing
user directories are not remoded.

## Staging and replacement

Before staging begins, the ledger durably records a per-artifact `staging`
intent with a random 128-bit operation ID, declarative target, operation kind,
old and candidate snapshots, and the exact private mode-0700 container name.
This makes even an interrupted partial staging tree attributable without
cleaning name-prefix lookalikes. Copying uses regular-file descriptors without
following source symlinks. The manifest supplies final modes; checkout modes
and the caller's umask are not copied into installed content. Files and
directory generations, the staging directory, and its parent are fsynced
before the intent advances to `prepared`.

New artifacts publish through same-directory `os.replace`. Updates use
Linux `renameat2(RENAME_EXCHANGE)` to exchange the complete staged generation
and the old generation atomically on the target filesystem. This applies to
standalone files and complete directory trees, so Quickshell never observes a
partially copied tree. A filesystem without atomic exchange support fails
closed.

The exchanged old generation remains private rollback material until final
byte, type, mode, owner, validator, and provenance verification succeeds.
Because publication moves names between the private container and destination
parent, both containing directories are fsynced. Provenance then advances to
`committed`. A durable `cleaning` milestone precedes recursive rollback-tree
deletion, so a crash partway through cleanup can resume without treating the
partially removed private generation as drift.

## Provenance

The mode-0600 record at
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/managed-deployment-v1.json`
is `BACKEND_OWNED` by `vanhyprarch-managed-deploy`. It contains only:

- its schema and ownership-manifest schema;
- complete or resumable-partial deployment status;
- optional caller-supplied release identity and deterministic release digest;
- managed artifact IDs, `VANILLA_MANAGED` class, and declarative targets;
- artifact kinds, exact modes, deterministic entry lists, and SHA-256 hashes;
- at most one active managed-file transaction with its operation ID, phase,
  old/candidate records, and exact private rollback-container identity.

It contains no preferences, machine choices, Monitor state, Appearance state,
Power & Idle state, runtime state, or package state. Declarative targets, not
resolved machine-specific absolute paths, are stored. Each ledger transition
uses a private mode-0600 temporary file, complete write, file fsync, atomic
replacement, provenance-directory fsync, mode verification, and byte-for-byte
readback. A malformed or truncated ledger fails closed; the engine never
reconstructs ambiguous provenance from installed bytes.

This ledger is the minimum evidence needed to distinguish an installed
Vanilla artifact from unknown pre-existing user content and to remove stale
managed artifacts safely. Hashes are not the only boundary: class, path,
type, mode, UID/GID, and symlink checks are also required.

## Rollback, crash recovery, and durability order

Rollback is local to one artifact plus the provenance transition describing
that artifact. The durable order is:

1. record `staging` intent;
2. write and fsync candidate bytes and staging namespaces;
3. record `prepared` intent;
4. atomically publish/exchange/remove and fsync both containing directories;
5. verify the installed candidate or removal;
6. atomically commit new artifact provenance as `committed`;
7. record `cleaning`, delete only the recorded rollback container, fsync its
   parent, then clear the transaction record.

`staging` and `prepared` are pre-provenance states: recovery restores or keeps
the prior generation and clears the intent. `committed` and `cleaning` are
post-provenance states: recovery retains and revalidates the candidate, then
finishes cleanup. Create and stale-removal operations use the same rule. A
prepared file or complete-tree exchange is accepted only when destination and
rollback paths exactly match the recorded old/candidate pair. Any other state
is manual drift and remains a conflict.

Exception rollback uses the same recovery path, but the repository suite also
kills subprocesses with `os._exit` at namespace, verification, provenance, and
cleanup boundaries so Python exception handlers and `finally` blocks cannot
mask crash defects. Recovery is idempotent: a second invocation produces no
filesystem or ledger change.

Automatic cleanup is restricted to the exact random container named by the
active ledger transaction. Unrecorded staging-like directories and ledger-temp
lookalikes are never removed by prefix scanning. A recorded container with an
unsafe type, owner, mode, symlink, special file, unexpected top-level member,
or inconsistent pre-cleanup snapshot fails closed.

Earlier unrelated artifacts that completed successfully remain committed and
are described by a `partial` ledger. Repeating the same operation and release
resumes from that evidence. Phase 2 intentionally does not implement a global
machine transaction.

These guarantees assume a local Linux filesystem that correctly implements
`renameat2(RENAME_EXCHANGE)`, atomic rename, and successful file/directory
`fsync`. Unsupported exchange semantics and reported fsync failures fail
closed. The application cannot guarantee durability against storage hardware
that falsely reports completed barriers.

## Validation split

Deployment-time validation is intentionally lightweight and bounded:

- source, staged, and installed structural/hash/mode validation always runs;
- Python artifacts named by the manifest are compiled in memory;
- shell artifacts named by the manifest pass `/bin/sh -n`;
- the Quickshell tree must contain `shell.qml`, all QML/JS/SVG text must decode
  as UTF-8, and its Python helpers compile in memory.

Repository tests retain deeper subsystem responsibility. They exercise
Hyprland config verification, Quickshell offscreen harnesses, helper behavior,
and systemd unit verification without turning deployment into a full CI run.
Phase 2 only writes user unit and drop-in files; it never enables, starts,
stops, or reloads a user service manager.

## Development and installed modes

Development mode may continue to use intentional repository symlinks. Phase 2
does not change or migrate them. Installed mode always creates regular
files/directories containing complete bytes. Removing the source checkout or
release extraction after deployment does not break the installed tree.

The future full installer may call this engine after package provisioning and
before later lifecycle phases. Package transactions, create-once
initialization, privileged adoption, service integration, optional component
add/remove, and whole-system doctor behavior remain outside this core.
