# Release engineering: contract and installed manual updater

Status: offline release declaration, deterministic artifact builder, verifier,
fresh-install identity publisher, upgrade-safe stages, migration runner,
durable journal, local exact-target driver, and installed manual updater
implemented. Super+Space exposes the manual updater. `v1.0.0` stable is
published, immutable, and accepted for fresh installation and direct rc1/rc3
upgrades. `main` targets unpublished `v1.0.1-rc1`; rc1, rc2, and rc3 remain
historical candidates.

The [signed distribution protocol](signed-distribution.md) adds source-level
Minisign-authenticated acquisition, GitHub/ServerPlan fallback, durable rollback
state, and signed recovery using this existing generated release identity.
It remains undeployed and production trust is deliberately unconfigured. Public
key custody, static signed publication, definitive preparation, and Proxmox
acceptance remain release gates.

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
python release/build.py build --commit FULL_40_HEX_SHA --tag v1.0.0 --output-dir OUTPUT_DIR
```

`--repo PATH` is available for offline fixture repositories. The command never
creates a tag. A build requires a commit containing the declaration. The
published `v1.0.0` tag remains bound to
`8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb`; subsequent `main` commits
use the next repository target declaration.

Verify both published files without Git, network, extraction, or execution:

```text
python release/build.py verify OUTPUT_DIR/release.json OUTPUT_DIR/vanhyprarch-v1.0.0.tar.gz
```

The installed updater calls the same strict metadata and archive verifier
before executing release-supplied code.

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
update execution, and VM acceptance are separate implemented layers. An
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
`/usr/share/vanhyprarch/release.json` identity. The target driver supplies a
verified release tree and invokes the stages in order.

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
any already installed package. Read-only libalpm validation rejects matching
conflicts/replacements and unresolved dependencies across the complete proposed
transaction and installed packages; inert relationship metadata is allowed.
This conservatively refuses package removal and unsupported
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

The supported released upgrade history starts with `v1.0.0-rc1`, whose real
fresh installation passed and created both lifecycle inventories. No
retrospective adoption of pre-rc1 development installations is implemented.

`managed_deploy.py update` already has the needed release-upgrade behavior:
provenance-gated replacement, safe stale removal, foreign-content conflicts,
local recovery, and read-only validation. The SDDM authority similarly uses
its root-private provenance and local transaction for source updates. Neither
needs a synthetic lifecycle flag. Release discovery and the installed update UI
are implemented. A real rc1-to-rc3 update and post-reboot VM acceptance passed.
The migration and journal primitives are described below.

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
local target driver verifies the complete target artifact before giving its
root-controlled extracted tree and metadata to the runner. Registry entries
never contain shell commands. The published `v1.0.0` release and current
unpublished `v1.0.1-rc1` repository target both have minimum level 0 and target
level 1; the production registry contains migration `0001`, which upgrades rc1
updater provenance from schema 1 to schema 2. Real rc1-to-rc3 and
rc1-to-stable updates physically validated it. Fresh installations establish
level 1 and schema 2 directly without replaying the migration. Rc3-to-stable
needs no migration; rc1-to-stable runs `0001` directly. The current repository
target adds no new migration.

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
`completed_migrations`, nullable `pending_migration`, and `target_user`. The
driver records the explicit validated username; the low-level journal fixture
API also permits null. It stores no URLs.
The source and target fields are derived from strict Phase 1 metadata; journal
initialization also compares the proposed source to the Phase 2 installed
identity. A different target, source, or target user cannot replace an active
journal.

Phases are `applying`, `validating`, and `ready-for-final-commit`. Fixed
checkpoint labels cover preflight completion, system integration, migrations,
managed deployment, create-once, and final validation. They report the active
stage; the local driver fixes the stage order below. Migration IDs, rather than checkpoint
labels, are the authority for completed migration progress. The journal does not
claim a committed release. During an incomplete update, the installed
`/usr/share/vanhyprarch/release.json` still names the **old** release and
migration level; the journal alone records intermediate progress. Clearing is
permitted only after the journal is ready and the installed identity validates
as the exact target. If interruption happens after that commit but before
clearing, the target driver inspects the ready journal and clears it after
verifying the target identity. Phase 4 never performs the identity commit.

The root-owned runtime lock is `/run/vanhyprarch/update.lock`, mode 0600 in a
mode-0700 directory. A nonblocking `flock` allows one transaction at a time.
The inode is retained; process death releases the lock while the durable
journal remains for exact-target resume. Malformed or unsafe state fails
closed and is never discarded automatically.

## Local exact-target update driver (release Phase 5)

`install/release_update.py` has `plan`, `apply`, and `resume` commands. Plan and
apply require absolute `--release-metadata` and `--release-artifact` paths plus
an explicit `--target-user`; resume uses only the exact retained target named
by the journal. Optional explicit XDG directory overrides support installations
whose target user did not use the standard home-relative XDG paths. All three
commands require root. No command contacts the network, discovers a release,
chooses latest, or asks for final user confirmation.

Plan validates the installed release identity, the complete target bundle via
the Phase 1 verifier, upgrade compatibility, the migration chain, and all
target authority plans. It uses temporary root-owned staging under `/run` for
inspection and removes that preview; it does not change installed release
state or create an update journal. Candidate upgrades stay within the same base version:
`rc1 → rc3 → stable` or directly `rc1 → stable`; intermediate candidates are not
required. Rc2 is an immutable historical candidate whose pre-migration upgrade
planning failed on rc1 provenance. Rc3 fixes that planning path. Stable
installations accept only newer stable releases.
The target must be newer, have the same supported architecture and protocol,
and admit the source version and migration level. Development installations,
same-version transitions, downgrades, and stable-to-candidate transitions fail.
The release artifact contract now requires the migration registry, driver,
journal primitive, and SDDM authority as tracked target-release files.

Apply copies the locally supplied bundle into
`/var/lib/vanhyprarch-update/staging/<artifact-sha256>/`, a root-owned mode-0755
tree. The user may read the staged source for user-owned deployment, but cannot
write it. This durable user-readable tree is separate from the mode-0700
private journal directory. The archive and metadata are verified again after
copying. Extraction occurs only after verification and creates regular files and directories with
the archive's validated modes. Every resume re-verifies the retained archive,
metadata, extracted bytes, modes, and ownership before running target code.
The retained target is bounded by the Phase 1 artifact and expansion limits;
it does not depend on the caller's original path after the journal begins.

The driver holds the root runtime lock while mutating. It journals each stage
before mutation and uses this order: migrations, system integration (including
SDDM and service policy), managed deployment update, create-once upgrade, then
complete target validation. Each authority is invoked from the verified target
tree with its existing interface. System integration runs as root with the
explicit target username; managed deployment and create-once run as that
resolved non-root user with a fixed environment and explicit home/XDG paths.
On resume, completed migration IDs remain skipped; an authority stage is
validated before any repeat apply. The old installed release identity remains
until every target authority validates.

After full validation, the journal becomes `ready-for-final-commit`.
`release_identity.py` then compares the exact expected source record and
atomically replaces it with the exact verified target `release.json` bytes,
fsyncs, and validates the result. Only then can the journal be durably cleared.
If interruption occurs after identity replacement, resume recognizes the
ready journal plus exact target identity, clears the journal, and removes
staging without rerunning authorities. Ordinary success removes staging after
journal clearing. If interrupted between clearing and staging removal, resume
can remove only the staged bundle matching the already committed installed
identity. Failures retain the journal and exact target material for diagnosis
or explicit resume; there is no global rollback.

The installed discovery/download bootstrap follows below. Published `v1.0.0`
passed real fresh installation, direct rc1/rc3 updates, and post-reboot smoke
acceptance.

## Installed manual updater (release Phase 6)

The acquisition details in this section describe the immutable published
v1.0.0 updater and its historical acceptance. The current source replaces its
GitHub-listing discovery with the independently authenticated protocol described
in [signed distribution](signed-distribution.md). That candidate has not been
installed or exercised against a real release on the development host.

The system-integration authority installs `/usr/local/bin/vanhyprarch-update`
as a root-owned mode-0755 regular executable Python archive. It contains the
fixed acquisition envelope and the existing release verifier, identity, journal,
and staging primitives. Root-private mode-0600 provenance at
`/var/lib/vanhyprarch/update-bootstrap-v1.json` guards replacement in later
releases. Fresh release installs include the command. Development installs may
also include it, but it refuses automatic release updates while installed
`release.json` is absent. The command does not use a source checkout.

The distribution authority is fixed in the bootstrap as
`vanhyprarch/vanilla-hyprarch`. The command queries GitHub's published Releases
API pages, never `/releases/latest`, and orders validated Vanilla versions
locally. A stable installation considers newer stable versions only. A candidate
considers later candidates and the final stable of the same base version. It
requires GitHub's release `immutable` flag to be true, a matching prerelease
flag, and exactly one `release.json` plus one version-derived artifact asset.
Publishing rc1 must enable GitHub immutable releases; a mutable release is not
an automatic update source. The flag is GitHub's assertion, not an independent
cryptographic signature or proof about an external mirror.

HTTPS acquisition uses fixed-repository asset URLs from the release object,
at most three redirects from a fixed GitHub asset URL to
`release-assets.githubusercontent.com`, no API-listing redirects, a 20-second
timeout, private `/run` downloads,
and the Phase 1 limits: 4 KiB metadata and 512 MiB compressed artifact.
On 2026-09-24, a public `cli/cli` release checksum asset returned one HTTPS
302 from `github.com` to `release-assets.githubusercontent.com`, then HTTP 200.
If GitHub changes that delivery host, the allowlist requires a reviewed change.
The GitHub listing is limited to 8 MiB per page, five 100-release pages, and
500 inspected releases. Pagination URLs are constructed for the fixed API;
remote `Link` URLs are never followed.
The artifact streams to disk and is checked for exact size, SHA-256, safe archive
members, and embedded declaration agreement before target code executes.
The authenticated target is extracted into a temporary root-owned, non-user-
writable `/run` preview. The command runs that tree's `release_update.py plan`,
then shows the installed/available versions, validated short summary, locally
derived release-notes URL, concise plan, and default-No confirmation. On Yes it
invokes that same verified target driver's `apply`; Phase 5 independently
reverifies the bundle and retains its own durable staging before mutation.

The command checks the durable journal before any network call. An active
transaction binds it to the retained digest and the original explicit target
username. It verifies the retained bundle, creates a fresh safe `/run`
execution copy, and invokes the target driver's
`resume`. This also handles identity-committed journal cleanup. After a journal
was cleared but exact committed staging remains, it invokes Phase 5's orphan
cleanup path. A malformed journal or retained bundle fails closed. The manual
command crosses sudo once, passing a resolved explicit target username; root
invocation requires `--target-user` and never infers it from HOME or cwd.

Super+Space → Update → Vanilla HyprArch launches the installed command through
the existing supervised terminal helper, with a fixed direct argument vector
and no QML-side sudo or release logic. The same action appears on development
installations; the updater refuses automatic release updates without an
installed release identity. Real rc1-to-rc3 public-updater acceptance and
published `v1.0.0` fresh-install and direct rc1/rc3 upgrade acceptance passed,
including migration `0001` where required and post-reboot smoke testing.
Background update checks remain future work.

### One-time administrative updater preparation

The standalone [preparation tool and runbook](updater-preparation.md) reuse the
bootstrap authority to replace only the updater and matching provenance, with
verified private backups, explicit authorization, and guarded recovery. Installed
v1.0.0 identity and migration state remain unchanged. Execution is blocked until
signed ServerPlan distribution and updater fallback are complete and a definitive
payload is rebuilt from a later approved exact commit. The preliminary `76ba358`
payload is not approved for VM or production use. Snapshotted Proxmox acceptance
must precede any production preparation; no preparation has been executed.
