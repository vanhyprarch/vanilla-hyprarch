# Release engineering: offline contract and update primitives

Status: offline release declaration, deterministic artifact builder, verifier,
fresh-install identity publisher, upgrade-safe stages, migration runner, and
durable update journal implemented. No release is published and no updater
exists yet.

## Identity and authored declaration

`main` remains development, not an update channel. Release identities are the
canonical forms `vMAJOR.MINOR.PATCH` and `vMAJOR.MINOR.PATCH-rcN`, with no
leading zeroes, positive RC number, or other prerelease labels. The initial
channels are `stable` for the first form and `candidate` for the second.

[`release/release.toml`](../release/release.toml) is the authored source record.
It has exactly these fields:

| Field | Rule |
| --- | --- |
| `schema` | Integer `1` |
| `version` | Canonical Vanilla version |
| `channel` | `stable` or `candidate`, matching the version |
| `architecture` | `x86_64` |
| `update_protocol` | Integer `1` |
| `minimum_installed_version` | Optional canonical version; omitted for the first candidate |
| `minimum_migration_level` | Integer from 0 through 1,000,000 |
| `migration_level` | Integer from 0 through 1,000,000, at least the minimum |
| `summary` | One printable, trimmed line of 1–160 characters and at most 320 UTF-8 bytes |

The absent `minimum_installed_version` represents no prior supported release.
TOML has no null value; the generated JSON contains `null` for that field.
The minimum installed product version and minimum technical migration level
are separate policies. Level 0 is valid. Unknown fields or types fail closed.

## Artifact and metadata

`release/build.py` reads an exact 40-character Git commit and that commit's
tracked `release/release.toml`. It reads blobs from the committed tree, never
from working-tree files. A dirty tree cannot change the output. Tracked Git
symlinks, submodules, non-regular objects, unsafe names, or tracked release
outputs cause failure rather than being copied or silently omitted.

The builder produces `vanhyprarch-VERSION.tar.gz` and `release.json`. The
archive has exactly one `vanhyprarch-VERSION/` root. It contains the tracked
source tree, including installers, package/deployment/service manifests,
managed payload, and the declaration. It contains no `.git` directory,
untracked files, caches, or previous release outputs. The published JSON has
the declaration fields plus the full commit SHA and an `artifact` object with
the derived filename, compressed byte size, and lowercase SHA-256. It has no
download URL.

Builds normalize the USTAR member order to root, sorted directories, then
sorted files. Directories have mode `0755`; regular files have `0644` or
`0755` according to the Git executable bit. All members have uid/gid 0,
empty user/group names, and the commit timestamp. Gzip has timestamp 0 and no
original filename. JSON uses sorted keys, compact separators, ASCII escaping,
and one final newline. The same commit produces identical bytes in different
output directories, regardless of local clock, path, locale, timezone,
username, or umask. Reproducibility assumes the same Python gzip/zlib encoder;
the source/archive contract does not promise bitwise equality across different
compression implementations.

## Commands

Build a committed fixture or development commit without a tag:

```text
python release/build.py build --commit FULL_40_HEX_SHA --output-dir OUTPUT_DIR
```

Strict publication mode additionally requires the exact existing tag to name
the release version and resolve to that same commit:

```text
python release/build.py build --commit FULL_40_HEX_SHA --tag v1.0.0-rc1 --output-dir OUTPUT_DIR
```

`--repo PATH` is available for offline fixture repositories. The command never
creates a tag. A build requires a commit containing the declaration. Committing
this Phase 1 contract does not create the `v1.0.0-rc1` tag or publish a release.

Verify both published files without Git, network, extraction, or execution:

```text
python release/build.py verify OUTPUT_DIR/release.json OUTPUT_DIR/vanhyprarch-v1.0.0-rc1.tar.gz
```

Future update code should import and call the same strict metadata and archive
verifier before executing any release-supplied code.

## Verifier boundary and bounds

The verifier requires exact metadata fields and types, no duplicate JSON
keys, a canonical channel/version pair, supported schema/protocol/architecture,
the derived filename, exact compressed size, and exact SHA-256. It inspects
the tar stream without extraction. The root, ordering, parent directories,
paths, object types, uid/gid, names, modes, and timestamps must match the
contract. Links, devices, FIFOs, unknown special objects, traversal,
absolute paths, duplicate destinations, malformed names, extended tar
metadata, and extra top-level roots fail. The embedded declaration must agree
with every shared JSON field. Required installer/manifests must be present.

| Input | Maximum |
| --- | ---: |
| `release.json` | 4 KiB |
| `release/release.toml` | 4 KiB |
| Version string | 64 UTF-8 bytes |
| Compressed artifact | 512 MiB |
| Archive members | 2,048 |
| One file member | 128 MiB |
| Sum of regular-file bytes | 1 GiB |
| Entire decompressed tar stream, including headers/padding | 1 GiB + 2,048 KiB + 1 KiB |
| One archive path | 255 UTF-8 bytes |

These are comfortably above the currently tracked approximately 63 MiB tree
and 272 files while limiting hostile inputs. The stream cap also applies
before Python's tar parser can consume oversized extended records.

Phase 1 establishes commit/tag identity at build time and SHA-256 consistency
at verification time. It does not authenticate a release independently of its
metadata publisher. GitHub immutable publication, discovery, migrations,
update execution, signatures, and VM acceptance belong to later phases. An
offline verifier cannot establish that a supplied commit
SHA is trusted; it can establish that the artifact matches the supplied
strict metadata and embedded declaration.

## Installed identity and fresh-install handoff

`/usr/share/vanhyprarch/release.json` is the only supported installed Vanilla
release identity. It is a root:root mode-0644 regular file in a root-owned,
non-user-writable directory. Its bytes are copied exactly from the verified
published `release.json`; the installer does not reconstruct its fields. The
record contains the complete published schema above, including the artifact
name, size, and SHA-256. Manual editing invalidates the record. It is
`BACKEND_OWNED` by the privileged release-identity publisher, outside ordinary
managed user-file deployment.

`install/release_identity.py validate` checks the file, parents, ownership,
mode, and complete Phase 1 schema offline. `validate --allow-absent` reports
`unreleased/development` when no record exists. This is the intentional state
of a `main` or arbitrary-ref development installation, not a guessed version.
The validator needs neither Git nor network access; its code is carried by a
release source tree, while the installed record remains source-independent.

The existing `install.sh` default remains the development bootstrap. Fresh
release mode requires both `--release-metadata /absolute/release.json` and
`--release-artifact /absolute/vanhyprarch-VERSION.tar.gz`, with `install.sh`
invoked as a regular file from an already verified, extracted release tree.
That earlier verification is the acquisition handoff; Phase 2 does not
download or discover a published release. If the target lacks Python, the
existing narrow Python bootstrap runs from that verified tree. The installer
then re-verifies private copies with the Phase 1 verifier **before extracting
or executing the supplied archive**, and uses the newly extracted tree for
the authoritative install stages. The verified installer and verifier bytes
must match the extracted copies.

Release mode performs a read-only privileged identity preflight before the
system stage. After system integration, managed deployment, create-once
initialization, and all three final validations succeed, it alone calls the
privileged identity commit and validates the installed record. The publisher
checks the artifact and metadata again, validates the extracted declaration,
stages exact metadata bytes with fsync, creates the installed file atomically
without clobbering an existing path, fsyncs the containing directory, and
checks the published bytes and schema. A failure never prints installation
success. There is no global rollback.

Fresh release installation refuses **any** existing release identity, even
if its bytes match. This avoids silently defining reinstall or upgrade
semantics in Phase 2; recovery or reinstall of a previously committed release
remains a future lifecycle decision. An incomplete install before the marker
may rerun through the existing stage recovery paths. Ordinary development
bootstrap still creates no installed identity and does not infer one from
the selected Git ref. Development bootstrap also refuses a host that already
has a release identity, so it cannot silently leave a stale release claim.

## Upgrade-safe authority modes (release Phase 3)

The system and create-once stages now accept `--lifecycle fresh|upgrade`;
`fresh` remains the default used by `install.sh`. These are individual stage
semantics, not a release updater. They never advance the installed
`/usr/share/vanhyprarch/release.json` identity. A future transaction driver
must supply a verified target source tree and invoke the stages in order.

`system_integration.py --lifecycle upgrade plan|apply|validate` requires the
prior root-private system state and SDDM provenance. Fresh apply records its
official-package and system-owned-file inventory in the existing
`/var/lib/vanhyprarch/system-integration-v1.json`. The prior inventory makes a
missing old terminal fallback a drift conflict, while a target-only addition
can be created. A local pending artifact intent lets apply resume an interrupted
new-file publication; foreign pre-existing files, symlinks, wrong modes, and
owners remain conflicts. Other future system-owned files need explicit
authority code and inventory entries; ownership-v2 alone is not a generic root
deployer. BlueZ's existing adoption provenance and the separate SDDM
provenance remain authoritative. A changed BlueZ candidate still fails closed
until an explicit update or migration path is reviewed.

Upgrade may install newly required **official** packages with the existing
`pacman -S --needed` path, including newly required dependency packages. It
blocks pending Arch updates and rejects a package preview that would change
any already installed package or whose new packages declare conflicts or
replacements. This conservatively refuses package removal and unsupported
replacement transactions. It neither
refreshes sync databases, runs `-Syu`, upgrades the AUR `yay` package, nor
removes packages omitted from the new manifest. Previously required packages
that disappeared locally are drift. Service changes use only target-declared
system units and compare their prior recorded policy; unrelated units are not
touched. A missing formerly required Flathub remote or SDDM provenance is a
conflict.

`create_once.py --lifecycle upgrade plan|initialize|validate` requires
`${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/create-once-lifecycle-v1.json`.
Fresh initialization writes this user-owned mode-0600 `BACKEND_OWNED` record
after processing all declared seeds and owner hooks. It contains sorted IDs,
not user file bytes. Upgrade preserves an old processed item even if the user
deleted it; only a target ID absent from the record is eligible for first
initialization. Pre-existing safe user files remain untouched. A durable
one-item pending intent precedes each new initialization. After interruption,
an absent pending target is conservatively recorded as processed and left
absent, because publication followed by user deletion cannot be distinguished
from interruption before publication. This avoids recreating user-deleted
state. Malformed or unsafe lifecycle state fails closed. Create-once items are
non-essential starter or user state; required system-correctness artifacts must
use another ownership class.

The supported released upgrade history starts with a future fresh
`v1.0.0-rc1` installation, which creates both lifecycle inventories. No
retrospective adoption of pre-rc1 development installations is implemented.

`managed_deploy.py update` already has the needed release-upgrade behavior:
provenance-gated replacement, safe stale removal, foreign-content conflicts,
local recovery, and read-only validation. The SDDM authority similarly uses
its root-private provenance and local transaction for source updates. Neither
needs a synthetic lifecycle flag. Release discovery, full transaction
orchestration, version advancement, UI action, and VM acceptance remain
unimplemented. The migration and journal primitives are described below.

## Migration registry and durable journal (release Phase 4)

Semantic versions identify releases; ascending integer IDs identify state
transitions. `release/migrations/registry.toml` has `schema = 1` and ordered
`[[migration]]` entries. Each entry requires integer `id`, short `name`, exact
`release/migrations/NNNN-name.py` path, concise `scope`, and Boolean
`touches_user_state`. An entry touching `USER_OWNED` or create-once state also
requires explicit `user_state_preservation` and `user_state_conflict` text.
These declarations make authority reviewable; they do not sandbox trusted
release code. Migration code must follow the existing ownership rules.

The registry contains exactly the chain from `minimum_migration_level + 1`
through `migration_level`, with no duplicates, gaps, reordered entries, or
unregistered files. An empty registry is valid only when both levels are 0.
The target declaration and optional verified metadata
must agree. The runner accepts only regular mode-0644 implementation files
under a safe target source tree, with bounded sizes and no symlinks. The
future driver must verify the complete target artifact before giving its
private extracted tree and metadata to the runner. Registry entries never
contain shell commands. `release/release.toml` remains at level 0 with minimum
0; the production registry is empty. Fresh installs establish the target
state directly and do not replay migrations. Production migration `0001` is
reserved for a later rc2 change, not a no-op in rc1.

Each migration Python file exposes `plan(context) -> list[str]`,
`apply(context) -> None`, and `validate(context) -> bool`. `plan` and
`validate` must be read-only. The context supplies the system root, verified
release root, source and target identities, numeric ID, and declared scope.
The runner plans immediately before applying
each migration, requires its ID to be journaled as pending first, then calls
apply and validate. Only a true validation result permits completion. On
resume, a pending migration is validated first; if already valid it is marked
complete without reapplying. Otherwise its read-only plan and idempotent or
recovery-aware apply run before validation. Foreign or ambiguous state must
raise and leave the pending record intact. Ordinary managed replacement and
stale cleanup remain with the existing deployment authority.

`install/update_journal.py` provides Python APIs for inspection, initialization,
exact-match resume, applying checkpoints, migration progress, phase changes,
and final clearing. The journal is
`/var/lib/vanhyprarch/update/journal.json`, a root:root mode-0600 regular file
inside a root:root mode-0700 directory. It is bounded to 16 KiB, uses strict
JSON with duplicate-key rejection, safe path/owner/mode checks, atomic
publication, file and directory fsync. Its exact schema is `schema = 1`,
`source` (`version`, `commit`, `artifact_sha256`, `migration_level`), `target`
(`version`, `commit`, `artifact_sha256`, `update_protocol`,
`minimum_migration_level`, `migration_level`), `phase`, `checkpoint`, ordered
`completed_migrations`, and nullable `pending_migration`. It stores no URLs.
The source and target fields are derived from strict Phase 1 metadata; journal
initialization also compares the proposed source to the Phase 2 installed
identity. A different target or source cannot replace an active journal.

Phases are `applying`, `validating`, and `ready-for-final-commit`. Fixed
checkpoint labels cover preflight completion, system integration, migrations,
managed deployment, create-once, and final validation. They report the active
stage; Phase 5 will decide stage order. Migration IDs, rather than checkpoint
labels, are the authority for completed migration progress. The journal does not
claim a committed release. During an incomplete update, the installed
`/usr/share/vanhyprarch/release.json` still names the **old** release and
migration level; the journal alone records intermediate progress. Clearing is
permitted only after the journal is ready and the installed identity validates
as the exact target. If interruption happens after that commit but before
clearing, the future driver can inspect the ready journal and clear it after
verifying the target identity. Phase 4 never performs the identity commit.

The root-owned runtime lock is `/run/vanhyprarch/update.lock`, mode 0600 in a
mode-0700 directory. A nonblocking `flock` allows one transaction at a time.
The inode is retained; process death releases the lock while the durable
journal remains for exact-target resume. Malformed or unsafe state fails
closed and is never discarded automatically. The future Phase 5 driver owns
release discovery, confirmation, stage orchestration, final validation, and
the installed-identity commit.
