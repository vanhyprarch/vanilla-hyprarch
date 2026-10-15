# Static publication and disposable hosting acceptance

Status: Phase 3A tooling and user-confirmed disposable hosting acceptance are
complete for the current single-user deployment model. The user signed root 1,
the authentic v1.0.0 manifest and Stable sequence-1 catalog interactively, then
published the initial signed production baseline on ServerPlan. Native Minisign
and independent HTTPS byte verification passed for the complete public tree.
The public trust anchor is integrated in source. Preparation and normal dock
discovery passed on the existing v1.0.0 VM, preserving identity and migration
level 1 and recording root 1 / Stable sequence 1 in the ledger. The genuine
v1.0.1 target preflight and upgrade remain pending; further publication and
installed-system changes require separate authorization. Follow the
[signed protocol](signed-distribution.md) and existing
[release artifact workflow](release-engineering.md); this adds no identity source.

## Offline publisher

`release/publication.py` assembles `WORKSPACE/public/vanilla-hyprarch/` with only
`roots/`, `channels/`, and `releases/`. Uploading its contents under
`/dist/v1/vanilla-hyprarch/` requires explicit authorization for each publication.
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

## Initial production root — verified

The user generated one encrypted production key pair. The agent reads only
`~/.local/share/vanhyprarch-signing/publisher.pub`; it never opens, inspects or
copies `publisher.key`. Only the user runs operations requiring that key in Foot.
Official `/usr/bin/minisign` handles its normal interactive passphrase prompt;
no passphrase belongs in arguments, environment variables, scripts or logs.
The user signed root 1; `TrustedRoot.initial` verified its native signature,
exact payload digest, key, identity, sequence floors and current validity.

The canonical unsigned input is [`release/initial-root.json`](../release/initial-root.json).
It contains the protocol's existing root schema, not a second trust format:

| Public value | Initial production root |
| --- | --- |
| Project / distribution protocol | `vanilla-hyprarch` / `1` |
| Root version / predecessor | `1` / `null` |
| Stable / candidate sequence floors | `1` / `1` |
| Issued at | `2026-10-15T07:35:10Z` |
| Expires at | `2031-10-15T07:35:10Z` |
| Native Minisign key ID (display only) | `BCE599B5D2226B7E` |
| Protocol key ID / full public-packet SHA-256 | `66e3d461f7f1ccca2614da2005126cc0edaf821b0033beb73a70688e82e639a0` |
| Canonical root **payload** SHA-256 | `58e8bc7a3094d4ea9ad2b58b80af1184feab3c530157556eeb950c78980f0f72` |

The public verification key is
`RWR+ayLStZnlvFmvSohkDaHCDoR1lgtFYXElF3aN3YOhOZLaJQa+XR59`.
The full fingerprint is the existing `public_key_id()` result, not the short ID
from an unsigned comment. Reproduce the payload into a new scratch file with:

```text
python -B -m release.distribution root --public-key RWR+ayLStZnlvFmvSohkDaHCDoR1lgtFYXElF3aN3YOhOZLaJQa+XR59 --issued-at 2026-10-15T07:35:10Z --output NEW_ROOT_PAYLOAD
sha256sum NEW_ROOT_PAYLOAD
```

The five-calendar-year rule is independent of the unchanged catalog default and
maximum of 365 days (31,536,000 seconds). Do not change these frozen root bytes
when signing. The updater still requires a complete signed envelope in its
canonical `release/trust.json`: schema 1, this public key, this payload digest,
and the base64-encoded signed root envelope. The existing `publication init`
produced that exact public trust record after verifying the signature, and it
was integrated into `release/trust.json`. The signed envelope SHA-256 is
`c7cfe586811a366df01a4d666bf511c5c7594bc703f4045080082968c325752c`;
this is distinct from the pinned payload digest above. This is source-only
configuration; the installed updater and security state are untouched.

Public-only preparation material is retained outside Git at
`~/Downloads/vanhyprarch-production-public/`: the unsigned root, verification
key, pins/checksums, signed root, unsigned release manifest and exact downloaded
v1.0.0 assets. The initialized `publisher/` workspace contains the verified root
and complete public trust record, frozen v1.0.0 manifest/signature receipts and
the signed Stable sequence-1 receipt and public catalog.
No private key is placed there. The original metadata is 430 bytes, SHA-256
`6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c`.
The original `vanhyprarch-v1.0.0.tar.gz` is 65,148,187 bytes, SHA-256
`de57673385f961b233bdae95731ba9e7a3bfef32ce5f44851143dafff0bcb0c9`.
Both were checked against the previously authenticated baseline and the archive
contract without extraction or execution. The source commit remains
`8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb`; no rebuild or identity edit occurs.

The following root signing command was completed by the user and is retained
for the ceremony record. **Do not rerun it or replace the frozen signed root.**

```bash
cd "$HOME/Projects/vanilla-hyprarch"
python -B -m release.distribution --minisign /usr/bin/minisign sign \
  --input release/initial-root.json \
  --secret-key "$HOME/.local/share/vanhyprarch-signing/publisher.key" \
  --public-key RWR+ayLStZnlvFmvSohkDaHCDoR1lgtFYXElF3aN3YOhOZLaJQa+XR59 \
  --envelope \
  --output "$HOME/Downloads/vanhyprarch-production-public/root-1.signed.json"
```

The public-only initialization below was also completed and its trust record
validated before integration. It is shown for reproducibility; do not rerun it
over the existing workspace.

```bash
PUBLICATION_DIR="$HOME/Downloads/vanhyprarch-production-public"
python -B -m release.publication --workspace "$PUBLICATION_DIR/publisher" init \
  --root-envelope "$PUBLICATION_DIR/root-1.signed.json" \
  --public-key RWR+ayLStZnlvFmvSohkDaHCDoR1lgtFYXElF3aN3YOhOZLaJQa+XR59 \
  --root-sha256 58e8bc7a3094d4ea9ad2b58b80af1184feab3c530157556eeb950c78980f0f72
```

The user completed the following manifest signing command in Foot. It recomputed
the manifest from the unchanged original assets and froze its exact signature.
This is a ceremony record, not an instruction to sign the release again.

```bash
cd "$HOME/Projects/vanilla-hyprarch"
PUBLICATION_DIR="$HOME/Downloads/vanhyprarch-production-public"
python -B -m release.publication --workspace "$PUBLICATION_DIR/publisher" release \
  --metadata "$PUBLICATION_DIR/assets/release.json" \
  --archive "$PUBLICATION_DIR/assets/vanhyprarch-v1.0.0.tar.gz" \
  --approved-commit 8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb \
  --secret-key "$HOME/.local/share/vanhyprarch-signing/publisher.key"
```

The user then signed the following catalog, binding the frozen manifest and
signature. These exact times are retained for reproducibility. Do not regenerate
sequence 1 with a new issuance or expiry; every renewal requires a higher sequence.

```bash
python -B -m release.publication --workspace "$PUBLICATION_DIR/publisher" catalog \
  --channel stable --sequence 1 --version v1.0.0 \
  --issued-at 2026-10-15T07:59:16Z --expires-at 2027-10-15T07:59:16Z \
  --secret-key "$HOME/.local/share/vanhyprarch-signing/publisher.key"
python -B -m release.publication --workspace "$PUBLICATION_DIR/publisher" check
```

## Initial production publication — complete

The authenticated export is
`~/Downloads/vanhyprarch-production-public/publisher/public/vanilla-hyprarch/`.
The user published its six public files under `/dist/v1/vanilla-hyprarch/`,
preserving the already uploaded authentic release assets. The catalog was uploaded
under a temporary filename, verified, then activated last through the tested FTPS
rename. Independent HTTPS downloads from
`https://vanhyprarch.it/dist/v1/vanilla-hyprarch/` matched every local byte, length
and SHA-256. The existing protocol verifier authenticated root, catalog and native
manifest signature, then verified the original release metadata and archive
contract without extraction or execution.

| Public object | Bytes | SHA-256 |
| --- | ---: | --- |
| `roots/1.json` | 864 | `c7cfe586811a366df01a4d666bf511c5c7594bc703f4045080082968c325752c` |
| `channels/stable.json` | 1,148 | `1eab39c97e20b55fb2de7ad48d24cb107fbe845e49045622adb8c85351d4a937` |
| `releases/v1.0.0/manifest.json` | 825 | `2ffef6db6f6e54fb78f6d6de0f23b393f683f795cbec4c030bdd6ec2ccf32a0e` |
| `releases/v1.0.0/manifest.json.sig` | 307 | `2e5577e7756af24eed890130b10b09b59f778981b80c6a973262108bba9db4ae` |
| `releases/v1.0.0/assets/release.json` | 430 | `6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c` |
| `releases/v1.0.0/assets/vanhyprarch-v1.0.0.tar.gz` | 65,148,187 | `de57673385f961b233bdae95731ba9e7a3bfef32ce5f44851143dafff0bcb0c9` |

Stable sequence 1 uses root 1 and contains only the original stable v1.0.0
identity at `8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb`, migration level 1.
Its validity is exactly 365 days (31,536,000 seconds), ending at
`2027-10-15T07:59:16Z`. No Candidate catalog was created or uploaded. The local
publisher check reports v1.0.0 and no pending channel publication. Retain the
frozen receipts, public export and verification checksums for subsequent renewal.
Never upload the workspace, input directory, receipts or keys. No installed
updater, release identity, rollback state or VM was changed during publication.

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

## Production checklist — INITIAL PUBLICATION AND VM DISCOVERY COMPLETE

- The user has generated the encrypted production key pair and arranged backups.
  Keep private-key and passphrase custody outside Git, publication workspaces and
  web roots. Do not generate another key for this initial root. Only the user
  accesses the private key interactively; no agent inspection or backup copying.
- Independently verify the complete public-packet SHA-256 fingerprint on two
  trusted devices/channels, not merely Minisign's short ID or HTTPS download.
  Record the signed initial root payload digest separately. Approve its exact
  UTC issuance, five-calendar-year expiry and initial stable/candidate floors.
  Plan dual-signed rotation and reminders well before expiry; no automatic reset.
- Deliver approved public pins through a reviewed exact source commit. Keep
  production and test roots separate. Rebuild deterministic release artifacts
  from independently approved commits with the existing release builder.
- The authentic v1.0.0 assets, root, signed manifest and Stable sequence-1 catalog
  have been published and independently reverified as recorded above. Preserve
  those immutable bytes; stop on any later discrepancy or unexplained change.
- Freeze signed manifests/signatures once. Build the initial stable catalog
  from genuine stable releases only; never relabel current candidate/main as a
  stable product. Use higher sequences for every subsequent renewal/change.
  Default/maximum catalog validity is 365 days, independent of root validity.
- Follow the accepted single-user publication sequence above, keeping Update on
  hold until final HTTPS verification succeeds. Disposable hosting acceptance is
  complete; no formal atomicity guarantee is required. Initial production-path
  byte and signature checks passed. Do not edit/re-sign existing immutable
  objects. Back up publisher receipts and publication evidence.
- The definitive preparation from commit `394422752564a832e2f15a004b6e3dc828e1b47b`
  passed on the existing snapshotted v1.0.0 VM, including normal dock discovery
  with GitHub HTTP 404 and authenticated ServerPlan Stable sequence 1. Do not
  repeat preparation; retain the genuine identity, migration state and user data.
- Obtain separate authorization for the genuine v1.0.1 target preflight and
  normal upgrade on that same VM. Existing regression coverage includes XDG/provider
  conflicts, interrupted update/recovery, identity-last and zero unexpected
  migrations. Block public GitHub entirely and accept signed ServerPlan acquisition
  and post-reboot desktop/application behavior. No production SSD work precedes
  VM acceptance. No package/release/key installation occurred in Phase 3A.

Run isolated tests with a verified official Minisign executable:

```text
MINISIGN=/absolute/verified/minisign PYTHONDONTWRITEBYTECODE=1 python tests/static-publication.py
```
