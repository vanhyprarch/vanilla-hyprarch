# Static publication and disposable hosting acceptance

Status: Phase 3A tooling and user-confirmed disposable hosting acceptance are
complete for the current single-user deployment model. Production keys, metadata,
updater preparation and VM acceptance remain pending and require separate
authorization. The installed trust record remains unconfigured. Follow the
[signed protocol](signed-distribution.md) and existing
[release artifact workflow](release-engineering.md); this adds no identity source.

## Offline publisher

`release/publication.py` assembles `WORKSPACE/public/vanilla-hyprarch/` with only
`roots/`, `channels/`, and `releases/`. Uploading its contents under
`/dist/v1/vanilla-hyprarch/` is a later, separately authorized operation.
`dist/v1` is distribution protocol 1, not a product version. Unsigned indexes
are not selection authority; `packages/` is untouched and remains reserved for
future Vanilla components. Arch packages continue using official repositories.

The workspace is private, mode 0700, outside Git and outside any web document
root. **Never place private keys inside it.** Its local `trust.json` contains
only explicitly supplied public pins and the signed initial root. It does not
change the repository or installed trust record. Initial publication supports
root 1; production rotation tooling is deferred, while the existing protocol
and updater already validate sequential dual-signed rotations.

Command templates, not production execution authorization:

```text
python -m release.publication --workspace WORKSPACE init --root-envelope SIGNED_ROOT --public-key VERIFIED_PUBLIC_KEY --root-sha256 VERIFIED_ROOT_PAYLOAD_SHA256
python -m release.publication --workspace WORKSPACE release --metadata RELEASE_JSON --archive RELEASE_ARCHIVE --approved-commit APPROVED_40_HEX_COMMIT --secret-key OFFLINE_KEY
python -m release.publication --workspace WORKSPACE catalog --channel candidate --sequence 1 --version RELEASE_VERSION --issued-at UTC_TIME --secret-key OFFLINE_KEY
python -m release.publication --workspace WORKSPACE check
python -m release.publication --workspace WORKSPACE resume-channel --channel candidate
```

`--minisign /absolute/verified/minisign` is an optional global argument for a
separately verified official executable; normal installations use `/usr/bin/minisign`.
Minisign opens encrypted keys and handles its own password prompt. Python never
reads key contents or passwords. The approved commit must match the generated
release identity. That equality and SHA-256 integrity do **not** authenticate the
publisher or Git commit: independently approve source/artifact provenance first.
Use the existing exact-commit artifact builder, not a dirty checkout export.

Each release is copied and fully reverified before public publication. Its
canonical manifest and native signature are frozen once in an append-only local
receipt directory. Retrying identical inputs reuses the exact signature and
existing public objects; assigning another identity or bytes to the same version
fails. Missing receipts are not permission to adopt an existing public directory.
An interrupted receipt-first release can be completed by repeating the exact
approved inputs without the key. Unknown, corrupt, or incomplete public release
objects block catalog publication. There is no force/overwrite option.

Catalog receipt files reserve contiguous sequences before public pointer
replacement. The first sequence is its pinned root floor; later publications
use the next sequence. Reusing the latest sequence is permitted only for the
identical canonical payload and exact frozen envelope. Renewal, changed membership,
or expiration changes require a higher sequence. Historical signatures and all
immutable bindings are checked, including pruned releases and both channels.
Stable catalogs cannot contain candidates. The 365-day ceiling/default remains;
`--expires-at UTC_TIME` supports shorter periods without changing the schema.

The workspace lock serializes writers. Receipts, files and directories are
fsynced before the public rename; the channel pointer is replaced last by a
complete same-filesystem file, then its parent is fsynced. No temporary channel
file is exported. These filesystem guarantees describe the local workspace.
`check` changes no publication data and reports reserved but unpublished channels;
`resume-channel` completes only the latest verified,
unexpired reservation. Expired reservations need a higher-sequence renewal.
An unexplained pointer is never overwritten automatically. Incomplete receipt
temps, changed files, missing history, or unknown state require inspection and
restoration from a verified workspace backup; there is no speculative repair.

Back up the complete private workspace and frozen public bytes before publication.
Do not reconstruct counters by trusting the mirror or deleting receipts. A local
privileged deletion/snapshot rollback cannot be prevented by local counters
alone; retain independent records of published sequences/digests. Do not build a
later publication from an older workspace backup without reconciling those records.

## Accepted single-user manual publication policy

Vanilla HyprArch currently has one user, its developer. Publication and release
updates are manually coordinated: **do not initiate Update while publishing**.
Temporary update-check unavailability is acceptable during that window. A formal
provider-confirmed atomic-rename guarantee is not required. Cryptographic
authentication, provenance, rollback protection and fail-closed behavior remain
mandatory throughout; an unavailable or inconsistent publication is never evidence
that the installation is up to date.

For each separately authorized production publication:

1. Build approved exact-commit release artifacts locally, verify them, and freeze
   their signed manifest and the next signed channel catalog in the workspace.
2. Upload immutable release assets first. Never overwrite an existing version's
   objects; an identical retry must reuse verified bytes and frozen signatures.
3. Verify the complete remote asset bytes, lengths and hashes against local data.
4. Upload immutable signed release metadata and any approved initial root record;
   verify their bytes and signatures using the independently retained local pins.
5. Upload the complete new signed catalog to a temporary filename in the active
   channel's directory, keeping the current catalog in place.
6. Verify the staged catalog's exact bytes, signature, channel, sequence, expiry
   and immutable release bindings against the frozen local catalog.
7. Replace the active catalog **last**, using the tested FTPS same-directory
   rename operation. Do not delete the active catalog first or upload over it.
8. Fetch the active catalog over HTTPS and verify the new sequence, exact bytes
   and signature. Retain publication evidence and back up publisher receipts.
9. Only after all verification succeeds may the developer initiate Update.

If interrupted or inconsistent, keep Update on hold, inspect the failure and
complete publication from the verified frozen material. Never reset counters,
reuse a sequence for different bytes, overwrite immutable objects, bypass a
signature failure or substitute unsigned metadata. Local `resume-channel` repairs
only local receipt-first publication; remote completion remains an operator task.
No extra catalog protocol, server service or multi-user coordination is needed.

## Isolated hosting fixture and authorization boundary

`admin/hosting-acceptance.py` generates only **TEST-ONLY** keys in a private
temporary directory and destroys them before returning. Surviving files contain
public data only. Its two empty candidate catalogs expire after 86,400 seconds;
the disposable root follows the separate five-calendar-year schema. No fake
product release or stable identity is generated. The root is never installed.

Prepare locally in a new empty destination:

```text
python admin/hosting-acceptance.py prepare --directory LOCAL_FIXTURE
```

The result prints one exact proposed location:

```text
https://vanhyprarch.it/dist/v1/_acceptance/vanilla-hyprarch/TEST_ID/
```

`TEST_ID` is a fresh 32-character random hexadecimal identifier. The runtime
updater cannot discover this subtree: its paths and production trust pins are
fixed elsewhere. The observer also refuses production paths and other hosts.
Keep `fixture.json` local as the independent public trust/byte receipt; never
fetch verification keys from hosting. If the fixture expires, make a new one
with a new ID; do not renew or reuse its destroyed key or lower its sequence.

**STOP before connecting for writes.** Obtain explicit approval naming that exact
URL and its corresponding cPanel document-root directory. Approval must cover:
creating only this new directory, the uploads below, same-directory replacement
of its disposable pointer, canceled/incomplete temporary uploads, duplicate-upload
refusal, and eventual removal of only this test directory. Confirm the actual
document-root mapping in cPanel; do not guess `public_html` or account paths.
Do not create or change real `stable.json`, `candidate.json`, releases, or trust.

## Manual FTPS/cPanel acceptance

Use the user's existing FTPS client or cPanel session. Validate the TLS certificate
and use encrypted control **and data** connections. Authenticate normally; never
paste passwords into commands, send them to this agent, enable credential logging,
or share complete FTP transcripts. Record only the test ID, operation order,
sanitized RNFR/RNTO reply codes, public digests, and HTTPS probe results.

1. Verify the approved test directory does not exist. Create it and upload only
   the **contents of `LOCAL_FIXTURE/upload/`**, preserving `immutable/probe.bin`.
   Do not upload `fixture.json`, `switch/`, the publisher workspace, or any keys.
   Files must be publicly readable over HTTPS; directory listings are unnecessary.
2. Run the read-only delivery/validator check below. It requires byte-exact root,
   immutable probe and a signed sequence-1 pointer. Record headers and digests.
3. Upload `switch/incomplete.json.part` under a temporary name, and also cancel
   an ordinary temporary-file upload partway through. Never rename these files
   onto `pointer.json`. Re-run inspection: the live pointer must remain complete
   at sequence 1. Remove only those disposable incomplete temporary files.
4. Upload the complete `switch/pointer-v2.json.part` as **`pointer.json.complete`**
   in the same remote directory as `pointer.json`. Wait for transfer completion.
   Run inspection with `--staged`; the complete remote bytes must match the
   independently retained sequence-2 signature/envelope before rename.
5. Start observers in two Foot terminals, one normal and one revalidating.
   While both run, perform exactly one same-directory rename replacing the
   existing pointer. With FTPS, record that RNFR targets `pointer.json.complete`
   and RNTO targets `pointer.json`. **No DELE, remove-then-rename, direct overwrite
   upload, or rename of an incomplete file is acceptable.** A 550 overwrite
   refusal is a blocked acceptance, not permission to delete the destination.
6. Both observers must see complete valid envelopes, observe sequence 2 by the
   end, and never see sequence 1 after 2. Any missing response, truncation,
   substitution, reused ETag for changed bytes, or stale rollback is a failure.
   Finish with `inspect`; immutable bytes must be unchanged and pointer sequence 2.
7. Test duplicate immutable publication **refusal**, not overwrite: inspection
   identifies `immutable/probe.bin` as already present and prints `REFUSE` for a
   second upload. Confirm the existing remote file in the client, cancel any
   overwrite prompt before transfer, and retain its digest. The offline publisher
   also rejects conflicting immutable directories automatically. Shared-host FTP
   write access is not WORM storage; do not claim the server itself enforces this.
8. Retain local public evidence and remove only the authorized `TEST_ID` subtree
   when cleanup is approved. Repeat trials use new fixtures/IDs, never a 2-to-1
   pointer reset at an accepted URL.

Read-only probe commands (use the same global verifier override if necessary):

```text
python admin/hosting-acceptance.py inspect --directory LOCAL_FIXTURE
python admin/hosting-acceptance.py inspect --directory LOCAL_FIXTURE --staged
python admin/hosting-acceptance.py watch --directory LOCAL_FIXTURE --samples 600 --interval 0.05 --cache-mode normal
python admin/hosting-acceptance.py watch --directory LOCAL_FIXTURE --samples 600 --interval 0.05 --cache-mode revalidate
```

These commands issue bounded HTTPS GETs, refuse redirects/proxies and unexpected
encodings, check exact lengths/bytes and native signatures, and enforce monotonic
observations. Samples include network latency; scheduling sleeps total at most
60 seconds per invocation. A completed run is **observational evidence only**.
The helper always reports `atomicity_guaranteed: false`; no sampling rate can
prove the absence of a shorter gap. No GitHub access is needed for this test.

## Accepted hosting observations and their limits

The user confirmed the following live disposable ServerPlan results:

- HTTPS delivery and artifact hashes verified; test catalogs passed native
  Minisign authentication against the retained local test root.
- An incomplete temporary upload left the active catalog unaffected.
- FTPS successfully replaced an existing file. All 240/240 HTTPS observations
  returned complete OLD or NEW content during that disposable replacement.
- All 240/240 observations during the signed-catalog replacement returned
  complete sequence-1 or sequence-2 catalogs, with zero observed HTTP errors,
  missing files or partial content.
- The final signed sequence-2 catalog verified and immutable test objects stayed
  unchanged.

These observations satisfy the current single-user operational requirements.
They do not prove filesystem atomicity, power-loss durability or universal cache
behavior. No formal provider guarantee is claimed or required before publication.

[FTP RNFR/RNTO](https://www.rfc-editor.org/rfc/rfc959#section-4.1.3) specifies a
rename operation, but does not establish a guarantee about simultaneous HTTP
readers, overwrite implementation, durability, or cache visibility. Similarly,
[cPanel File Manager](https://docs.cpanel.net/cpanel/files/file-manager/) documents
rename/move controls, not such a guarantee. Use the already tested FTPS operation
and the manual publication window above. A refused rename, incomplete upload,
incorrect response or failed verification must be resolved before Update is
initiated; never delete the active catalog first to make a replacement succeed.
No provider attestation, alternate hosting stack or additional publication
infrastructure is needed for this accepted operational model.

Inspect actual `Cache-Control`, `ETag`, `Last-Modified`, `Age`, `Date`, `Vary`,
content length and conditional responses. A validator is not authentication or
an atomicity proof. Both ordinary and revalidating requests must converge on the
new catalog without post-observation rollback. ETags must distinguish changed
bytes; second-resolution Last-Modified alone can miss rapid changes.

For mutable catalog URLs, prefer **`Cache-Control: no-store`** or reliable
revalidation (`no-cache, max-age=0, must-revalidate`) with correct validators and
no stale-on-error serving where hosting configuration permits. These directives
have different meanings in [HTTP caching](https://www.rfc-editor.org/rfc/rfc9111#section-5.2.2):
`no-cache` permits storage but requires validation; `no-store` prohibits storage.
Purge pre-existing shared/negative cache entries when activating the policy.
Catalog responses must not be transformed. Immutable manifests, signatures,
root records and assets may use long-lived immutable caching once frozen.
Never cache missing future files as a publication mechanism. Header configuration
and cache changes require separately approved scope; none is deployed here.
The updater's existing unconditional bounded downloads and cryptographic checks
remain unchanged. Test-subtree headers do not establish production-path policy.

## Production checklist — NOT EXECUTED

- Separately approve the offline signing workstation, operators, recovery owner,
  encryption/passphrase custody and at least two independent encrypted backups.
  Generate the real Minisign key **encrypted**, outside Git, workspaces and web
  roots; do not use the disposable `-W` test-key option. Test backup recovery
  offline. Never upload or transmit the private key or passphrase.
- Independently verify the complete public-packet SHA-256 fingerprint on two
  trusted devices/channels, not merely Minisign's short ID or HTTPS download.
  Record the signed initial root payload digest separately. Approve its exact
  UTC issuance, five-calendar-year expiry and initial stable/candidate floors.
  Plan dual-signed rotation and reminders well before expiry; no automatic reset.
- Deliver approved public pins through a reviewed exact source commit. Keep
  production and test roots separate. Rebuild deterministic release artifacts
  from independently approved commits with the existing release builder.
- For the existing authentic v1.0.0 mirror, independently reverify every asset
  against the published originals. Explicitly approve first-time missing signed
  sidecars during protocol activation; never replace existing asset bytes. Stop
  on any discrepancy or unexplained pre-existing manifest/signature.
- Freeze signed manifests/signatures once. Build the initial stable catalog
  from genuine stable releases only; never relabel current candidate/main as a
  stable product. Use higher sequences for every subsequent renewal/change.
  Default/maximum catalog validity is 365 days, independent of root validity.
- Follow the accepted single-user publication sequence above, keeping Update on
  hold until final HTTPS verification succeeds. Disposable hosting acceptance is
  complete; no formal atomicity guarantee is required. Production paths still
  need their own byte/signature and cache observations. Do not edit/re-sign
  existing immutable objects. Back up publisher receipts and publication evidence.
- Rebuild the one-time updater preparation bundle from a later approved exact
  commit containing the final public pins, completed fallback and accepted tools.
  Follow the [preparation runbook](updater-preparation.md); initial v1.0.0 identity,
  migration state and user-owned data must remain genuine and unchanged.
- Obtain separate snapshotted Proxmox authorization. Start from genuine v1.0.0;
  exercise preparation, normal upgrade, custom supported XDG context/provider
  conflicts, interrupted update/recovery, identity-last and zero unexpected
  migrations. Block public GitHub entirely and accept signed ServerPlan acquisition
  and post-reboot desktop/application behavior. No production SSD work precedes
  VM acceptance. No package/release/key installation occurred in Phase 3A.

Run isolated tests with a verified official Minisign executable:

```text
MINISIGN=/absolute/verified/minisign PYTHONDONTWRITEBYTECODE=1 python tests/static-publication.py
```
