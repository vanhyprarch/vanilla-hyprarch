# One-time v1.0.0 updater preparation

**For an original v1.0.0 installation, follow the [complete public upgrade
guide](upgrade-v1.0.0-to-v1.0.1.md)**. It provides the accepted downloadable kit,
all authoritative hashes, exact user commands and recovery guidance. Fresh
signed-release installations and already prepared systems must not repeat preparation.
This document retains the administrative design, historical build records and
advanced construction/recovery reference; its preliminary examples are not the
accepted download procedure.

The complete genuine v1.0.0 -> v1.0.1 upgrade and reboot acceptance passed on the
**existing snapshotted Proxmox VM**, including authenticated ServerPlan fallback,
Stable sequence 2, exact-target recovery after Arch mirror failure, migration
level 1 and preserved settings. Do not repeat preparation on that VM or run it
on an unreleased/development host.

**VM PREPARATION AND DISCOVERY ACCEPTED:** the definitive bundle from
`394422752564a832e2f15a004b6e3dc828e1b47b` was built reproducibly, transferred
and successfully applied. Updater hashes, ownership and schema-3 provenance
passed. The normal dock Update action reported v1.0.0 up to date with GitHub
HTTP 404 and authenticated ServerPlan fallback. The durable ledger recorded
root 1, Stable sequence 1 and the original v1.0.0 binding. Installed identity
and migration level 1 were unchanged. The accepted updater SHA-256 is
`4512e61395435c2e2e275d0481a4d9f1fe1de003c6e551b4cc6f0757889f0fc1`.
The v1.0.1 declaration changed no packaged updater source. Later releases may
replace the updater through the signed lifecycle without repeating this bridge.
Commit `76ba358` and its hashes below remain preliminary historical records,
never approved installation material. The remaining commands describe first-time
preparation elsewhere under separate authorization, not a repeat on this VM.

`admin/prepare-updater.py` replaces only the installed updater and its matching
bootstrap provenance. It does not execute an update, install packages, publish
a release identity, deploy desktop files, or advance migrations. It reuses
`BootstrapIntegration.plan(lifecycle="upgrade")`, `apply(...)`, and `validate()`.
The new payload carries provenance schema 3 with an uninitialized distribution
marker; the authentic original backup remains schema 2. Preparation still writes
only its original two components and preserves release identity/migration state.
The first signed updater invocation creates its separate rollback ledger before
discovery. After that operation begins (or ledger initialization is interrupted),
updater-only restoration is refused; use signed exact-target recovery instead.
If only acquisition was attempted, retry the prepared updater; an active journal
resumes its exact retained target. Snapshot restoration is a separate full-system
recovery decision, never an automatic alternative to authenticated resume.
The small in-memory payload adapter supplies bytes from the existing,
deterministic zipapp packager; it introduces no updater format or trust protocol.

## Trust and construction

The preliminary payload was built from
`76ba35807ae01197011017b119206316dff3796b`, which lacks ServerPlan fallback.
It must not become the definitive preparation payload. The tool takes an
explicit `--approved-commit`; it does not pin this preliminary commit.

The accepted definitive bundle uses the exact commit recorded above. For any
future separately authorized construction, use administrative tooling
from that same approved commit so its authoritative file list and packager stay
aligned with the payload. Existing protocol/schema requirements and byte-for-byte
packager comparison still apply; rerun the focused tests before VM authorization.
Do not transfer an unexplained dirty development checkout and execute it as root.

Use the existing trusted GitHub repository workflow (normal authenticated Git
transport, including its TLS/SSH host verification). The following is a future
construction template; replace `APPROVED_SOURCE_COMMIT` only after that approval:

```sh
prep_source_commit=APPROVED_SOURCE_COMMIT
git clone https://github.com/vanhyprarch/vanilla-hyprarch.git /tmp/vanhyprarch-preparation-source
git -C /tmp/vanhyprarch-preparation-source checkout --detach "$prep_source_commit"
mkdir /tmp/vanhyprarch-preparation-bundle
python3 -B admin/prepare-updater.py build \
  --source /tmp/vanhyprarch-preparation-source \
  --approved-commit "$prep_source_commit" \
  --output /tmp/vanhyprarch-preparation-bundle
```

Run the last command from the separately reviewed administrative source. Use new,
empty paths. The builder rejects the administrative working tree as payload
source, dirty checkouts, wrong commits, unexpected origins, and nonempty output.
It fetches `origin/main` and checks that the approved commit belongs to that
authenticated history. It uses `release/build.py` to produce the ordinary
`release.json` and its version-derived archive, then compares the canonical
updater built from the clean checkout with the updater built from that archive.

Save the printed JSON record independently of the transfer: exact source commit,
archive SHA-256, metadata SHA-256, updater SHA-256, and provenance SHA-256. Also
record the administrative source commit and its independently verified transfer
checksums. SHA-256 detects changed bytes; it **does not independently authenticate
the publisher**. Repository authentication and explicit source approval provide
that trust. Never substitute hashes supplied only with an untrusted download.

The historical authenticated isolated build of the **preliminary** source produced:

| Object | SHA-256 |
| --- | --- |
| Bundle | `adc7be628b2d3454a9fd9ff85d10759aeebb58ff61300a1747466d828ff2e3b4` |
| Bundle metadata | `d115c688c942d76f4418c2b2c3525fd9b5f1de5d83f8bead2e65cafea12a0504` |
| Prepared updater | `4adcff509dcd55ab97373b595252c96bc13e08be1326807610624fdac91e5369` |
| Prepared provenance | `13a33b1b684cbe9ac2066bf44282ef6e0bb8297f61eb8ee5053675936929436c` |

These are historical reproducibility records, not signatures or installation
approval. They must be superseded by the later approved source's newly verified
records; never use these preliminary hashes to authorize real preparation.

## VM prerequisites

Before any administrator command below:

- Signed ServerPlan distribution, updater fallback, definitive bundle construction
  and preparation/discovery on the existing VM are accepted. First-time preparation
  on another installation still requires explicit approval and verified input;
  this reference checklist does not authorize it.
- Require the official Arch `minisign` package before preparation. The tool performs
  read-only package/executable and packaged-root signature/expiry checks; it never
  installs a verifier or obtains trust keys from ServerPlan. Complete a normal
  administrator-owned Arch upgrade first if necessary; then `sudo pacman -S --needed minisign`
  is the ordinary official-package installation path. Do not run it as part of
  development tooling tests. Use the accepted public guide for an original
  installation, rather than executing these historical construction templates.
- Retain the existing genuine v1.0.0 VM and its available snapshot, including its
  system and user disks; no new VM or additional snapshot is required. Retain
  its original updater, provenance and release metadata as backup material.
- Verify the immutable v1.0.0 release source/asset through the trusted release
  workflow. The tool pins the original updater SHA-256
  `13435389ce2e8d2e89d081ddab96b6f8287ccb58213d9a2c23b3b8fc6b9fb54d`
  and release metadata SHA-256
  `6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c`.
  Stable v1.0.0, migration level 1, canonical schema-2 bootstrap provenance,
  root ownership, and the expected modes must all match.
- Transfer the two bundle files and compare all recorded hashes. Place them in
  `/opt/vanhyprarch-preparation-bundle`, root-owned with no group/other write
  permission. Do not replace the VM's installed `release.json` with this bundle's
  metadata.
- Independently verify and place the approved administrative source checkout at
  `/opt/vanhyprarch-updater-preparation`, root-owned and not writable by other
  accounts. Verify its exact approved Git commit and clean tracked content.
  Its Python sources and all their parents must be real, protected root-owned
  files/directories. The CLI checks this before importing project libraries.
- Close update windows and ensure no update is running. Existing journals,
  incomplete system-integration transactions, retained release staging, updater
  preview staging, and a busy update lock must be resolved through their normal
  recovery procedure, not deleted to make preparation pass.
- Log into the target user's normal graphical session. Use its existing Foot
  terminal; do not use a root shell or `sudo -E`. Have ordinary sudo access.
- Require default state/cache locations (`$HOME/.local/state`, `$HOME/.cache`),
  the standard user runtime directory/bus, and protected account home. Custom
  `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_DATA_DIRS`, and the existing provider
  discovery context are supported. Do not unset genuine overrides to bypass a
  rejection. A user whose login/session sets custom state/cache locations needs
  a separately reviewed forwarding change before this procedure can proceed.
  Keep those state/cache restrictions through the subsequent real release update;
  the prepared updater does not forward state/cache overrides itself.

After the separate source approval, the VM administrator can create that input
layout with ordinary Git and `install` commands (replace `APPROVED_SOURCE_COMMIT`
with the later approved tool/payload commit, `APPROVED_ARTIFACT_NAME` with the
archive filename in its verified metadata, and use the verified transfer directory):

```sh
sudo git clone --no-checkout https://github.com/vanhyprarch/vanilla-hyprarch.git /opt/vanhyprarch-updater-preparation
sudo git -C /opt/vanhyprarch-updater-preparation checkout --detach APPROVED_SOURCE_COMMIT
sudo git -C /opt/vanhyprarch-updater-preparation rev-parse HEAD
sudo git -C /opt/vanhyprarch-updater-preparation status --porcelain
sudo install -d -o root -g root -m 0755 /opt/vanhyprarch-preparation-bundle
sudo install -o root -g root -m 0644 /tmp/vanhyprarch-preparation-bundle/release.json /opt/vanhyprarch-preparation-bundle/release.json
sudo install -o root -g root -m 0644 /tmp/vanhyprarch-preparation-bundle/APPROVED_ARTIFACT_NAME /opt/vanhyprarch-preparation-bundle/APPROVED_ARTIFACT_NAME
```

Require the exact approved admin commit and empty status output. Independently
compare both transferred file hashes with the construction record. The CLI
also rejects user-writable parents, symlinks, hardlinks, or non-root bundle files.

## Check and explicit apply

The following commands are for future, separately authorized VM execution only.
Replace the placeholders with the later approved commit, archive filename, and
independently recorded rebuilt archive digest. Do not use the preliminary payload.
From the **target user's graphical terminal**, set these shell variables:

```sh
prep_tool=/opt/vanhyprarch-updater-preparation/admin/prepare-updater.py
prep_metadata=/opt/vanhyprarch-preparation-bundle/release.json
prep_artifact=/opt/vanhyprarch-preparation-bundle/APPROVED_ARTIFACT_NAME
prep_commit=APPROVED_SOURCE_COMMIT
prep_digest=APPROVED_BUNDLE_SHA256
```

Read-only preflight (the tool performs the ordinary sudo handoff itself):

```sh
python3 -B "$prep_tool" check --metadata "$prep_metadata" --artifact "$prep_artifact" \
  --approved-commit "$prep_commit" --bundle-sha256 "$prep_digest"
```

Expect JSON `status: "replace"`, `release_identity: "unchanged v1.0.0"`, the
two component paths, and all expected hashes. Compare them with the independent
construction record. This check creates no lock, backup, staging, or installed
files. If a lock already exists, it tests that same lock without creating one.
The observation is not a reservation: apply acquires the normal update lock and
rechecks all guards. Sudo may perform its ordinary authentication/audit writes.

Only after successful review and explicit VM authorization:

```sh
python3 -B "$prep_tool" apply --authorize --metadata "$prep_metadata" --artifact "$prep_artifact" \
  --approved-commit "$prep_commit" --bundle-sha256 "$prep_digest"
```

`--authorize` is mandatory. Context is captured before sudo, validated against
the actual target account, and never reconstructed from root's environment.
Unsupported state/cache overrides fail before sudo. No password is captured by
the tool. The prepared updater independently captures and forwards config/data
context each time the normal graphical update action is subsequently used.

Apply holds the existing update lock, creates a mode-0700 root-private verified
backup at `/root/vanhyprarch-updater-preparation`, then publishes the two files
using the existing per-file fsync/rename mechanism. Backup files are mode 0600.
The durable receipt records original and new hashes, original ownership/modes,
source commit, bundle hash, and recovery direction. Do not edit this receipt.

Repeat `check` after apply: expect `status: "prepared"`. Independently verify the
two installed hashes, root ownership, updater mode 0755, provenance mode 0600,
and unchanged original release metadata hash. Retain the input bundle, backup,
receipt, construction record, and snapshot until the real upgrade is accepted.

## Interruption and recovery

There is no atomic two-file publication. Recovery accepts only the verified
receipt's exact old/new hashes, with unchanged original identity and no release
transaction or incompatible staging:

| Direction | Updater / provenance | Action |
| --- | --- | --- |
| Prepare | old / old | Repeat authorized apply |
| Prepare | new / old | Repeat authorized apply to finish provenance |
| Prepare | new / new | Already prepared; repeating apply is safe |
| Restore | new / new or old / new | Repeat authorized restore |
| Restore | old / old | Original pair restored |
| Either | Any unexplained hash, unsafe metadata, or corrupt receipt/backup | Stop; investigate or revert VM snapshot |

An interruption while creating the backup, before its receipt is complete,
fails closed. No updater publication has begun. Preserve the incomplete backup
for inspection and revert the VM snapshot; do not silently reconstruct it.
Unexplained temporary files are not automatically removed.

Before a real release update has begun, restore only the verified original pair:

```sh
python3 -B "$prep_tool" restore --authorize --metadata "$prep_metadata" --artifact "$prep_artifact" \
  --approved-commit "$prep_commit" --bundle-sha256 "$prep_digest"
```

For a recognized interrupted forward pair, restoration first completes its
provenance, records reverse intent durably, then restores through the same
bootstrap authority. It never rolls back packages or the desktop payload. Once
a release journal exists, release staging remains, or release identity changes,
updater-only restoration is forbidden. Use the normal **exact-target** release
resume procedure or the complete VM snapshot. Do not clear a journal or forge
identity/migration state. After restoration the receipt remains recoverable;
another preparation requires explicit administrative review, not receipt deletion.

## Validation matrix — reference

Preparation, authenticated discovery and the actual v1.0.1 upgrade/reboot are
accepted on the existing VM. The
following lifecycle and fault cases remain reference coverage for isolated
regressions; they are not instructions to repeat the completed phase or restore
the VM. Use the public user guide for a different original v1.0.0 installation.

1. Check genuine baseline and read-only plan; cancel without `--authorize` and
   verify zero changes. Apply, repeat check/apply, and compare the two component
   hashes, provenance, original identity, migration level, and unrelated state.
2. In separate snapshot branches, interrupt before executable publication,
   between the two publications, and after both publications. Check/resume,
   test allowed restore and interrupted restore, and reject corrupt backups or
   unexpected pairs. Also test an occupied lock and incompatible staging.
3. In a fresh user's actual graphical context, test custom config/data paths;
   verify the normal prepared updater forwards them. Test custom state/cache
   overrides and require a refusal before mutation. Do not infer paths from
   process environments or shell-profile execution.
4. After successful target preflight and separately authorized signing/publication,
   run the genuine v1.0.0 to v1.0.1 Stable upgrade through the normal dock action
   on the existing VM. Preserve channel rules, installed identity until final
   validation, and zero required migrations; no fixture identity is substituted.
5. Test a configured competing Secret Service provider under custom XDG paths:
   the normal target preflight must block provisioning before package mutation.
   Preserve providers and user settings. Standalone KeePassXC is not a conflict.
6. Interrupt that release update, reject updater-only restore, resume the same
   exact target, verify provenance throughout, identity publication last, no
   unexpected migration beyond level 1, and preserved user-owned state. Reboot
   and verify the updated desktop, dex, persistent keyring/Nextcloud behavior,
   and subsequent normal update discovery.

The legacy preparation, genuine v1.0.1 upgrade and reboot acceptance are complete.
These are historical regression cases, not remaining release gates. Use the
[current release workflow](release-workflow.md) for subsequent signed upgrades;
do not repeat this bridge or rebuild its accepted administrative payload.
