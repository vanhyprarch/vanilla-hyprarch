# Signed distribution protocol 1 — offline foundation

Status: Phase 1 implementation, isolated tests only. No production trust anchor,
signing key, installed verifier, network fallback, hosted metadata, or installed
security-state changes. Existing release installation and updater behavior remain
as documented in [release engineering](release-engineering.md). Completion of
this foundation does **not** authorize the one-time updater preparation payload
or publication of v1.0.1.

`/dist/v1` names **distribution protocol 1**, independently of product versions
such as `v1.0.1` and the existing product `update_protocol = 1`.
`release/distribution.py` is an offline library and local publisher CLI. It is
outside the installed updater and package baseline in this phase.

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
interval. There is no default production key, trust-on-first-use, or live key
generation. SHA-256 alone establishes integrity, not publisher authentication.

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
| `issued_at`, `expires_at` | UTC timestamp strings; explicit root interval, separate from catalog policy |
| `channel_floors` | exact object `stable`, `candidate`, each a minimum sequence counter |

Root records use the envelope below, proposed path `roots/1.json`. Phase 1 can
validate the shape of a later root, but cannot adopt it or reset trust/state.

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
must authorize their use. Phase 1 verifies manifests against its one pinned root.

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
Duplicate signers fail. Initial root and current catalog verification require
exactly the pinned signer; the two-record envelope capacity reserves future
dual-signature root rotation, not current multi-key acceptance. Catalogs are
single self-contained objects at `channels/stable.json` and
`channels/candidate.json`; there is no detached channel signature/pointer race.
Envelope/signature bytes themselves may vary without changing the authenticated
payload; rollback/equivocation compares the canonical **payload** digest.

## Selection and durable rollback protection

`verify_catalog` requires an explicit prior serialized security state and
returns immutable authenticated payload bytes plus a proposed successor state.
It rejects rollback/equivocation before returning a selectable catalog. The
caller must durably commit the proposed state before using that selection in
Phase 2; Phase 1 has no installed-state store or default filesystem target.

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

State transitions are pure: interruption while validating cannot partially
modify prior state. The future privileged store must reuse the existing update
lock, root-private ownership/parent checks, bounded no-symlink reads, a temporary
file on the same filesystem, file fsync, atomic rename, and directory fsync.
It must reject missing/corrupt state after initialization, never auto-reset
floors, and commit authenticated observations before package/code mutation.
At a crash boundary the old or new complete state is recovered; exact-target
release-update resume must retain its authenticated target. The future store's
write/crash tests remain Phase 2 work; pure-state tests do not prove disk
durability. State deletion/rollback by a privileged attacker or disk snapshot
cannot be solved solely by local counters.

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

Root validity remains **a separate pending production decision**. The existing
schema requires an explicit finite root expiry and rejects expired roots; this
is an existing protocol assumption, not a selected root lifetime. There is no
default root lifetime or 365-day root ceiling. Decide root lifetime, custody, and
authenticated expiry recovery before pinning a production root. No production
root/key exists yet; longer test-root intervals are test fixtures only. Initial
trust pins and future rotation rules below are unchanged.

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

## Future root rotation rules

Rotation is a protocol requirement, not an implemented production workflow:

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
   Implement and test this policy before rotating or retiring production keys;
   Phase 1 deliberately rejects adoption of later roots.
5. Root expiry recovery must authenticate continuity, not skip signatures or
   reset state. Compromise of the sole root requires a separately authenticated
   administrative trust repair; self-signed replacement is insufficient.

Keep future production private keys encrypted, outside Git and hosting, with
offline recoverable backups and a separately recorded public fingerprint.
Never send private keys to ServerPlan or GitHub. Phase 1 tests generate only
temporary unencrypted **TEST-ONLY** keys, mode 0600 in a mode-0700 temporary
directory, and remove them afterward. No private fixtures are committed.

## Local publisher and isolated tests

Run from the repository root. The existing builder still builds an exact Git
commit, not dirty working-tree contents. All following commands are local;
outputs refuse existing destinations and should be built in a scratch directory:

```text
python -m release.distribution root --public-key PUBLIC_KEY --issued-at UTC_TIME --expires-at UTC_TIME --output ROOT_PAYLOAD
python -m release.distribution manifest --metadata RELEASE_JSON --archive ARCHIVE --root-version 1 --output MANIFEST
python -m release.distribution sign --input MANIFEST --secret-key PRIVATE_KEY_FILE --public-key PUBLIC_KEY --output MANIFEST_SIGNATURE
python -m release.distribution catalog --channel candidate --sequence SEQUENCE --root-version 1 --issued-at UTC_TIME --release MANIFEST MANIFEST_SIGNATURE --output CATALOG_PAYLOAD
python -m release.distribution sign --input CATALOG_PAYLOAD --secret-key PRIVATE_KEY_FILE --public-key PUBLIC_KEY --envelope --output SIGNED_CATALOG
```

Catalog publication defaults to 365 days after `--issued-at`; use an explicit
`--expires-at UTC_TIME` for a shorter interval. Root creation still requires an
explicit `--expires-at` under its separate policy.

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

## Phase 2 boundaries

Still required: transport acquisition/fallback, privileged durable trust/state
ownership, updater packaging and trust-anchor delivery, authenticated bootstrap
handoff/resume, official Minisign installation prerequisite, publisher artifact
freeze/reuse enforcement, static publication operations, and full Proxmox upgrade
acceptance from genuine v1.0.0. No phase-1 command deploys or updates anything.

Future GitHub and ServerPlan endpoints are untrusted replicas. HTTP 404/network
failure may permit another transport; authentication, equivocation, rollback,
identity, or digest failures must never trigger an unsigned/lower-trust bypass.
There is no GitHub branch or public-GitHub availability requirement in Phase 1.
Real ServerPlan acceptance must work without publicly accessible GitHub.

Static publication must upload immutable assets, verify them, publish immutable
manifest/signature files, verify them, then atomically replace the self-contained
signed channel catalog last. Hosting rename/replace semantics and interrupted
publication require separate validation; no FTPS, cPanel, upload, or production
publication code is included here. Official Arch packages remain official Arch
downloads; ServerPlan `packages/` remains reserved for future Vanilla components.
