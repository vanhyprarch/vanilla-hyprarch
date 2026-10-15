# Signed distribution protocol 1

Status: Phase 1 foundation and Phase 2 updater integration implemented in source
and isolated tests; the existing v1.0.0 Proxmox VM's prepared signed updater has
passed the real v1.0.0 -> v1.0.1 normal-dock upgrade and reboot acceptance.
Production root 1, both release manifests and Stable sequence 2 are signed,
verified and published on ServerPlan. The VM ledger records root 1, Stable 2 and
both immutable release bindings; installed v1.0.1 retains migration level 1.
Further publication and changes to other installations require separate
authorization. See [release engineering](release-engineering.md) for historical
behavior and the [original-v1.0.0 user guide](upgrade-v1.0.0-to-v1.0.1.md) for the
required one-time bridge. Fresh v1.0.1 and already prepared systems skip it.

`/dist/v1` names **distribution protocol 1**, independently of product versions
such as `v1.0.1` and the existing product `update_protocol = 1`.
`release/distribution.py` is the shared verifier and offline publisher library.
The updater zipapp includes it, the public `release/trust.json` record, and
`install/signed_distribution.py`. Official Arch `minisign` is now required in
the package baseline. This implementation phase installed no packages.

## Encoding, signatures, and trust

Every JSON object uses sorted keys, compact separators, ASCII JSON escapes,
and exactly one final LF, as produced by the existing `metadata_bytes` encoder.
The decoder requires byte-for-byte equality with this encoding. Duplicate keys,
BOMs, extra whitespace, non-finite numbers, unknown or missing fields, wrong
types, and unsupported schemas/protocols fail closed. Booleans are not integers.
All specified fields are required; there are no implicit optional fields.

Native [Minisign](https://jedisct1.github.io/minisign/) signatures authenticate
the **exact canonical payload bytes**, including the LF. Verification is:

```text
/usr/bin/minisign -V -H -q -P PINNED_NATIVE_PUBLIC_KEY -m MESSAGE -x SIGNATURE
```

`-H` requires upstream's current prehashed signature format. No signature
algorithm, prehash implementation, private-key parser, or credential handling
is implemented here. Minisign handles all signing and cryptographic verification.
Neither untrusted comments nor trusted comments carry protocol authority: all
policy is in the signed JSON. Verifier output is suppressed, so attacker-supplied
comments cannot become diagnostics. A missing/failing/timed-out verifier blocks
authentication. The executable path is locally trusted, never metadata-selected.
The official [Arch Extra package](https://archlinux.org/packages/extra/x86_64/minisign/)
is the intended implementation. Tests exercised 0.12-2; retest the native CLI
and signature fixtures when changing that dependency.

Public keys are native canonical base64 Minisign public packets: exactly 42
decoded bytes (`Ed`, 8-byte key identifier, 32-byte public key). `key_id` below
is lowercase SHA-256 of that **entire decoded public packet**, not the native
short identifier. This is encoding validation and fingerprinting, not custom
cryptography. A public key fetched alongside metadata is never a trust anchor.

The initial anchor must be delivered by the separately authenticated updater
preparation/source trust workflow: the full public key **and** SHA-256 of the
exact initial root payload. `TrustedRoot.initial` requires both explicit pins,
checks the root's self-signature using that pinned key, and validates its clock
interval. There is no implicit key selection, trust-on-first-use, or live key
generation. SHA-256 alone establishes integrity, not publisher authentication.

The packaged canonical `release/trust.json` has exactly `schema: 1`,
`public_key`, `root_sha256`, and `root` (base64 of the initial signed root
envelope). The source now contains the approved production key, exact payload
digest and verified signed root envelope. An entirely null development
placeholder remains explicitly rejected by acquisition and real preparation.
No client obtains an initial key from a transport. Private signing material is never
packaged. An initialized updater's initial anchor is immutable across normal
replacement; use the authenticated rotation chain for later keys.

## Exact wire schemas

The common header has exactly four fields, all mandatory:

| Field | Type and value |
| --- | --- |
| `schema` | integer `1` |
| `distribution_protocol` | integer `1` |
| `project` | string `vanilla-hyprarch` |
| `kind` | string `root`, `release`, or `catalog` |

Counters are integers from 1 through 2^63−1. Timestamps are real UTC dates in
`YYYY-MM-DDTHH:MM:SSZ`, at or after the Unix epoch; no alternate offsets or
fractional seconds. `issued_at < expires_at`. SHA-256 fields are exactly 64
lowercase hex characters. A descriptor has exactly `path` (string), `length`
(positive integer byte length), and `sha256`. Paths must equal the derived
literal paths below; arbitrary URLs, traversal, queries, and alternate spellings
cannot be represented.

**Initial root payload**, maximum 16 KiB: common header with `kind = root`, plus:

| Field | Type and rule |
| --- | --- |
| `root_version` | counter; initial trust loading accepts only `1` |
| `previous_root_sha256` | `null` for version 1; predecessor payload digest for later versions |
| `public_key` | one native public key as specified above |
| `issued_at`, `expires_at` | UTC timestamps exactly five calendar years apart, separate from catalog policy |
| `channel_floors` | exact object `stable`, `candidate`, each a minimum sequence counter |

Root records use the envelope below, path `roots/NUMBER.json`. Initial trust
loading accepts only root 1. Later roots require the sequential, dual-signed
rotation validation below; a self-signed replacement cannot reset trust/state.

**Immutable release manifest**, maximum 16 KiB: common header with
`kind = release`, plus:

| Field | Type and rule |
| --- | --- |
| `root_version` | signing root counter |
| `release` | the complete generated product `release.json` object |
| `release_json` | descriptor with path exactly `assets/release.json`, maximum 4 KiB |
| `archive` | descriptor with path exactly `assets/vanhyprarch-VERSION.tar.gz`, maximum 512 MiB |

The existing strict release contract is authoritative for every nested `release`
field, architecture (`x86_64`), product version/channel, full source commit,
update protocol, minimum version, migration range, summary, and artifact record.
There is no second authored identity. The builder first runs the existing
archive verifier, then derives this object from its generated metadata. Archive
length/hash must also equal the artifact fields inside `release`.

The client checks catalog bindings, the manifest's native signature, exact
`release.json` bytes/length/hash, and equality of that parsed identity with
`release`. `verify_artifact` reuses the existing bounded digest and archive
verifier before any extraction/execution. The immutable files are
`releases/VERSION/manifest.json` and detached `manifest.json.sig`, with assets
below the same release directory. Manifests do not expire: a fresh signed catalog
must authorize their use. Retained authenticated historical roots may verify
old immutable manifests only when the current signed catalog binds their bytes.

**Channel catalog payload**, maximum 256 KiB: common header with
`kind = catalog`, plus:

| Field | Type and rule |
| --- | --- |
| `root_version` | counter matching the trusted root |
| `channel` | `stable` or `candidate` |
| `sequence` | monotonically increasing counter within this channel |
| `issued_at`, `expires_at` | UTC timestamp strings, with an interval of 1–31,536,000 seconds |
| `releases` | array of at most 500 unique entries, ascending by product version |

Each entry has exactly `version`, `manifest`, and `signature`. `version` uses the
existing canonical product grammar. `manifest` is a descriptor with path
`releases/VERSION/manifest.json`, maximum 16 KiB; `signature` is a descriptor with
path `releases/VERSION/manifest.json.sig`, maximum 4 KiB. Thus the catalog binds
both immutable files, including their exact byte lengths and SHA-256 values.
An empty catalog is permitted. Stable catalogs accept final releases only;
candidate catalogs can contain candidates and final promotions.

**Signed envelope**, maximum 384 KiB, has exactly:

| Field | Type and rule |
| --- | --- |
| `schema` | integer `1` |
| `payload` | canonical standard base64 of exact canonical root/catalog payload bytes |
| `signatures` | array of 1–2 records, each exactly `key_id` and `minisign` |

`minisign` is the native ASCII signature file as a JSON string, maximum 4 KiB.
Duplicate signers fail. The initial root and current catalog require exactly
their pinned/current signer. A rotated root requires both the previous and new
key signatures over the same payload. Catalogs are
single self-contained objects at `channels/stable.json` and
`channels/candidate.json`; there is no detached channel signature/pointer race.
Envelope/signature bytes themselves may vary without changing the authenticated
payload; rollback/equivocation compares the canonical **payload** digest.

## Selection and durable rollback protection

`verify_catalog` requires an explicit prior serialized security state and
returns immutable authenticated payload bytes plus a proposed successor state.
It rejects rollback/equivocation before returning a selectable catalog. The
updater durably commits the proposed state before using that selection or
running target code. The library's pure state functions perform no live writes.

`select_release` chooses the highest strictly newer catalog version consistent
with the installed identity. Stable installations cannot opt into candidates.
Candidate upgrades remain in their product version, including promotion to its
final release. After manifest/artifact authentication, `compatible_release`
checks minimum installed version, architecture/update protocol, and migration
range. These checks supplement rather than replace existing target-driver
provenance, migration execution, resume, and identity-last rules. No eligible
target returns `None`; a bad selected target must not silently select an older
release or unsigned transport alternative.

The canonical security-state schema (maximum 8 MiB) has the same common header
with `kind = security-state`, plus exactly:

- `root_version` and `root_sha256`: accepted counter and root payload digest.
- `clock_high_water`: integer Unix seconds from 0 through 2^63−1.
- `channels`: object with optional `stable`/`candidate` records, each exactly
  `sequence` (counter) and `sha256` (accepted canonical catalog payload digest).
- `bindings`: object keyed by canonical product version, at most 10,000 entries,
  each the exact catalog release entry with matching `version`.

Lower sequences fail. Equal sequence/equal payload is idempotent; equal
sequence/different payload is equivocation. Previously observed version bindings
cannot change, even at higher sequences, after pruning, or across channels.
Root-pinned channel floors protect initial fetch; persistent observations protect
later fetches. Unobserved historical equivocation cannot be detected without an
independent transparency mechanism, outside this scope.

State transitions are pure. The privileged store publishes one root-private,
mode-0600 `/var/lib/vanhyprarch/distribution-security-v1.json` under the existing
update lock, with bounded no-symlink/single-link reads, ownership checks,
same-filesystem temporary files, file fsync, atomic publication, and directory
fsync. The canonical outer ledger has exactly `schema: 1`, `roots` (at most 16
base64 dual-signed rotations), `state` (the schema above), and `authorization`
(`null` or the proof below), bounded at 12 MiB. Root chain and counters change
together in this one file. Missing/corrupt initialized state never resets.

Updater provenance schema 3 retains `schema`, `sha256`, `update_protocol` and
adds `distribution_anchor_sha256` and boolean `distribution_initialized`.
The existing bootstrap authority converts its proven schema-2 record during
updater replacement; the release migration level/registry do not change.
The preparation tool still publishes only its original two components.
On first signed invocation, the updater verifies the packaged anchor and writes
an empty ledger durably, then marks initialization in provenance, before any
network request. If interrupted between those writes, only the exact empty
seed is recognized; unexplained contents fail closed. Once marked initialized,
an absent ledger requires explicit administrative recovery. Normal updater
replacement preserves the marker and rejects initial-anchor changes in preflight.

Before running any target code, the ledger retains `authorization` with exactly
`catalog`, `manifest`, `signature`, `metadata` (base64 exact signed/verified bytes),
`authenticated_at` (integer UTC seconds no later than the clock high-water), and
`updater` (the complete validated original schema-3 provenance record, without a
publication intent). The latter independently records the original updater hash,
initial root pin, and initialization marker before target code can replace them.
This root-private acceptance receipt is checked against immutable bindings and
the exact journal/retained artifact identity. New plan/apply requests recheck
current expiry. An existing transaction can resume offline using its recorded
valid authorization time even after catalog/root expiry; it cannot select another
target or use this exception for a new update. Missing/tampered authorization
blocks resume before target code. Uncommitted staging without a journal blocks
discovery and requires explicit exact-target recovery. Identity-last commit,
terminal cleanup, and target-user journal binding remain the existing driver's
authority. State deletion/rollback by a privileged attacker or disk snapshot
cannot be solved solely by local counters.

### Interrupted updater/provenance publication

Executable and provenance publication are atomic per file, not as a pair. An
initialized signed updater replacement now writes a durable intent **before**
replacing the executable. The existing provenance file temporarily retains its
original five schema-3 fields plus exactly `publication`, with `journal` (the
complete validated transaction snapshot) and `replacement_sha256`. This bounded
record is at most 20 KiB. The snapshot must describe the active target user's
`applying` / `system-integration` stage, with all migrations completed. The
existing target driver holds the update lock across its authority subprocess;
the authority requires that held lock and verifies the exact retained source.
Normal completed provenance still has only its original five fields.

Supported states are intent plus original executable, intent plus replacement
executable, and completed replacement plus matching final provenance. A mismatch
without intent is never inferred to be an interrupted update. On restart, before
discovery or target-driver execution, the bootstrap holds the same update lock,
requires the exact unchanged journal/source identity/user, verifies retained
archive/tree and canonical metadata bytes, and reauthenticates the recorded
signed authorization. It compares the original provenance against the independent
ledger receipt, reconstructs the replacement zipapp without importing target
modules, and requires its full hash and public trust record to match the intent
and preserved anchor. Only then may `BootstrapIntegration.apply(upgrade)` finish
the pair. Final provenance and executable are revalidated, then strict security
startup and the existing exact-target resume continue. Repeated interruption is
safe; missing or substituted evidence fails closed. Recovery changes no ledger
floors, bindings, clock state, release identity, or user-owned state itself.

The execution boundary remains the trusted OS and root-owned publisher: the
previous updater authenticates replacement code **before publishing or executing
it**. Restart checks use independently retained root-private evidence, not the
new executable's claim about its own hash. This is not a secure-boot mechanism
and cannot defend against a privileged attacker replacing executable code and
disabling its checks. No downloaded verifier, unsigned rescue mode, or alternate
root is introduced. An unexplained historical mismatch still needs separately
authenticated administrative recovery.

`tests/updater-publication.py` exercises real signed zipapps in temporary roots,
SIGKILL before/between/after component writes, interrupted recovery, expiry,
corruption, and concurrent invocation, including the authority's direct-script
subprocess import context. No installed system or live updater is used.

## Expiration and clocks — approved 365-day catalog policy

The initial publication default and protocol-v1 maximum catalog lifetime are
**365 days**, for both stable and candidate. One day means exactly **86,400
elapsed POSIX seconds**; 365 days is exactly **31,536,000 seconds**. Integer UTC
timestamp arithmetic defines `expires_at = issued_at + 31,536,000` by default.
This is not a calendar-year anniversary or local-time calculation; leap days
and daylight-saving transitions do not change the interval. Leap-second labels
are not supported by the timestamp format.

The signed interval must satisfy `0 < expires_at - issued_at <= 31,536,000`.
Exactly the maximum is accepted; exceeding it by even one second is rejected
by the schema, publisher, and client. Publishers can explicitly choose shorter
intervals, including 180, 90, or 30 days, with the same schema. `Clock` defaults
to the v1 maximum and permits a stricter local maximum, never a higher one.
Shortening the publisher default later needs no protocol-format change.

Renewal, including a refresh with no new release, requires a newly signed catalog
with a **higher channel sequence**. Changing expiration at the same sequence is
equivocation. Clients that have observed the higher sequence reject older
catalogs. Shortening validity does **not** retroactively revoke an older signed
catalog for clients that have not observed that higher sequence: they may still
accept it until its original expiry. Longer validity deliberately accepts a
longer withholding/replay window in exchange for less signing maintenance.

Expiry is exclusive (`now >= expires_at` fails). Future issuance, excessive
lifetime, and clock rollback below the recorded high-water fail. Optional
caller-controlled skew is bounded at five minutes and defaults to zero; expiry
uses the greater of current time and the saved high-water, so skew cannot extend
an expired catalog. Expiry/clock checks run again at use.

Root validity is **five UTC calendar years**, independently of catalog lifetime.
Preserve month, day, and time on the fifth anniversary, clamping February 29 to
February 28 when the target year is not leap. The interval can therefore span
different numbers of seconds; it is never `5 * 365 days`. The root builder
defaults to that exact expiry and rejects a different signed interval. New
acquisition rejects an expired root at the exact expiry second. Rotation must be
accepted while the current root is still valid. After expiry, new acquisition
requires separately authenticated administrative recovery; there is no automatic
trust reset. Existing exact-target transaction recovery is the bounded exception
described above. The verified initial production root follows this rule.

| Catalog lifetime option | Security and operation |
| --- | --- |
| 30 days | Shortest replay/freeze window; requires frequent signed refreshes and available signing custody even without a release. Long-offline systems need a fresh catalog before updating. |
| 90 days | Longer freeze exposure; quarterly maintenance still needs advance scheduling and margin. More forgiving of operator absence. |
| 180 days | More stale/replay exposure than 30/90 days; less signing maintenance and better tolerance of extended absence. |
| **365 days — approved default and maximum** | Longest accepted stale/replay exposure; avoids monthly signing maintenance for a single maintainer. Refresh before expiry even when no new product release exists. |

An offline/expired client may keep its installed desktop but cannot authenticate
a new update until valid metadata and a sane clock are available. The first
acquisition still relies on trusted anchor floors
and expiry; a network attacker can withhold new metadata until expiry but cannot
create authenticated updates. A bad local clock fails closed; do not silently
set it using untrusted transport headers.

## Root rotation validation

Phase 2 implements chain validation/acquisition, not production signing or
publication workflows:

1. Accept exactly current root version + 1, with the exact previous canonical
   root payload SHA-256, project, and distribution protocol.
2. Verify the exact new root payload with both the current trusted key and the
   proposed new key, proving continuity and possession. Comments/key IDs alone
   cannot authorize a key. Bound and validate the entire chain sequentially.
3. Preserve stored channel sequence/hash history, immutable release bindings,
   and clock high-water. New root channel floors cannot decrease. Persist root
   and security-state changes as one crash-recoverable trust transition.
4. New catalogs use the current key/root. Historical immutable manifests require
   a retained authenticated historical-root chain and an exact binding in a
   current-key-authenticated catalog. Historical keys cannot sign new catalogs.
   The integration tests cover current-key catalogs binding old-key manifests.
5. Root expiry recovery must authenticate continuity, not skip signatures or
   reset state. Compromise of the sole root requires a separately authenticated
   administrative trust repair; self-signed replacement is insufficient.

Keep production private keys encrypted, outside Git and hosting, with
offline recoverable backups and a separately recorded public fingerprint.
Never send private keys to ServerPlan or GitHub. Phase 1 tests generate only
temporary unencrypted **TEST-ONLY** keys, mode 0600 in a mode-0700 temporary
directory, and remove them afterward. No private fixtures are committed.

## Local publisher and isolated tests

Phase 3A's [static publication tooling and hosting runbook](serverplan-publication.md)
builds on these primitives, retaining frozen signatures and catalog receipts.
It adds no installed updater or network-transport changes; real hosting acceptance
has passed for the current single-user manual publication workflow. The initial
production trust anchor and signed ServerPlan baseline are also verified. The
existing v1.0.0 VM has passed preparation, signed discovery, actual v1.0.1 upgrade,
exact-target recovery and reboot acceptance. No production SSD preparation has
occurred.

Run from the repository root. The existing builder still builds an exact Git
commit, not dirty working-tree contents. All following commands are local;
outputs refuse existing destinations and should be built in a scratch directory:

```text
python -m release.distribution root --public-key PUBLIC_KEY --issued-at UTC_TIME --output ROOT_PAYLOAD
python -m release.distribution manifest --metadata RELEASE_JSON --archive ARCHIVE --root-version 1 --output MANIFEST
python -m release.distribution sign --input MANIFEST --secret-key PRIVATE_KEY_FILE --public-key PUBLIC_KEY --output MANIFEST_SIGNATURE
python -m release.distribution catalog --channel candidate --sequence SEQUENCE --root-version 1 --issued-at UTC_TIME --release MANIFEST MANIFEST_SIGNATURE --output CATALOG_PAYLOAD
python -m release.distribution sign --input CATALOG_PAYLOAD --secret-key PRIVATE_KEY_FILE --public-key PUBLIC_KEY --envelope --output SIGNED_CATALOG
```

Catalog publication defaults to 365 days after `--issued-at`; use an explicit
`--expires-at UTC_TIME` for a shorter interval. Root creation defaults to its
five-calendar-year expiry; an explicit root expiry must match that policy.

Sign a root payload with `sign --envelope` as well. These are command templates,
not authorization to generate or publish production metadata. Minisign opens
the explicit private key and handles any encrypted-key prompt directly; Python
does not read key contents or passwords. Metadata bytes are deterministic;
upstream signatures need not be. Generate a release signature once, freeze it
with its manifest, and bind those exact bytes in catalogs. Do not re-sign an
existing immutable release as a routine publication action.

Run the real-cryptography tests with an installed official Minisign, or a
separately verified official executable extracted into a temporary directory:

```text
MINISIGN=/absolute/verified/minisign PYTHONDONTWRITEBYTECODE=1 python tests/signed-distribution.py
```

The executable override is local test configuration, never remotely supplied.
Missing Minisign fails the suite rather than skipping signature coverage.

## Fixed transports and Phase 3 publication gate

The primary is GitHub, with automatic ServerPlan fallback. Channel/root/manifest
replica paths are fixed under
`https://raw.githubusercontent.com/vanhyprarch/vanilla-hyprarch/distribution-v1/vanilla-hyprarch/`;
GitHub artifacts use the fixed repository's version-derived release asset URLs.
ServerPlan uses `https://vanhyprarch.it/dist/v1/vanilla-hyprarch/` for all protocol
files. No metadata branch is created or published by Phase 2. Unsigned indexes,
remote URLs, and GitHub listing/immutability assertions are not discovery authority.
Official package downloads remain pacman's responsibility.

HTTP 401/403/404/408/429/5xx, connection failure, timeout, TLS unavailability, and
interrupted/truncated transfers permit the other endpoint. Invalid URLs,
redirects, excessive sizes, signatures, canonical JSON, protocol/identity/hash
mismatches, expiry, equivocation, and rollback block rather than trying another
catalog. A missing artifact can be retried only with the same authenticated
descriptors. Both transports unavailable is an error, never “up to date”.
Only an authenticated fresh catalog with no eligible target reports that status.

Requests retain HTTPS validation, a 20-second timeout, no inherited proxies,
bounded downloads, and at most three GitHub-asset redirects to the existing
CDN allowlist without credentials/cookies. Static ServerPlan/raw-metadata
redirects are refused. Disposable ServerPlan delivery and FTPS replacement have
passed user-confirmed hosting acceptance; these observations do not establish a
formal atomicity guarantee. Tests exercise real transport code with GitHub
HTTP 404 and complete signed ServerPlan fixtures; public GitHub is not needed.

The user generated the production key pair and signed the canonical
[initial root payload](../release/initial-root.json) interactively. Native
verification passed against the approved public key and exact root digest;
`release/trust.json` now contains the complete public anchor. The user also signed
the original v1.0.0 manifest and Stable sequence-1 catalog with the existing tools.
All six [published production files](serverplan-publication.md#initial-production-publication--complete)
match the authenticated local bytes over HTTPS, and the full trust chain verifies.
No Candidate catalog or partial trust schema is introduced.

Public trust-pin delivery, definitive preparation from commit
`394422752564a832e2f15a004b6e3dc828e1b47b` and authenticated discovery on the
existing snapshotted v1.0.0 VM are accepted. Genuine v1.0.1 target preflight,
signed Stable sequence 2 publication, actual upgrade and reboot acceptance also
passed, including exact-target resumption after Arch mirror failure and a full
Arch upgrade. No repeated preparation is needed. Production
preparation checks official Minisign and the packaged root signature before
changing its two files; it never installs the package or keys itself.

Static publication must upload immutable assets, verify them, publish immutable
manifest/signature files, verify them, then stage and verify the complete
self-contained signed channel catalog before replacing the active catalog last
with the tested FTPS rename operation. The sole developer must finish publication
and verify the active catalog before initiating Update. Temporary update-check
unavailability is acceptable during publication; invalid or inconsistent content
still fails closed. A formal provider-confirmed atomicity guarantee is not a
publication prerequisite. No FTPS, cPanel or upload client is included here.
Official Arch packages remain official Arch downloads; ServerPlan `packages/`
remains reserved for future Vanilla components.
