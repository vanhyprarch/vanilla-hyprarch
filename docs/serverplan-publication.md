# Static publication and disposable hosting acceptance

Status: the static publisher and manual FileZilla FTPS workflow are implemented
and accepted. Production root 1 and Stable sequence 5 authenticate immutable
v1.0.0 through v1.0.4. HTTPS byte verification and the genuine v1.0.3 ->
v1.0.4 signed upgrade/reboot passed in release testing. GitHub Release publication
and asset verification passed; anonymous v1.0.4 page and asset access was verified
on 2026-10-27. v1.0.5 is in preparation, not published.

Use the [operator runbook](release-workflow.md) for the whole lifecycle and the
[signed protocol](signed-distribution.md) for trust rules. This document owns
local publication preparation, manual upload ordering and HTTPS verification.
Existing initial-root/earlier-sequence records below are historical evidence,
not commands to repeat or current channel pointers.

## Optional Zig Player archive

The component manager prefers GitHub and has a transport-only ServerPlan
fallback. The approved upload destination is:

```text
/dist/v1/vanhyprarch-zig-player/releases/v0.1.1/assets/vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz
```

This independent project directory is separate from
`/dist/v1/vanilla-hyprarch/`; player artifacts do not belong in the main project's
distribution tree or signed catalog. Publication remains a separately authorized
manual operation using the existing
FTPS procedure and operator-confirmed document-root mapping.

Publish the original v0.1.1 archive unchanged: filename
`vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz`, size **149,617 bytes**, SHA-256
`9bd759283aa823aba124c94d64b9696df670551a1d6418ca1a32194ea0b1a887`.
Do not repack or regenerate it. Both download sources must provide these exact
bytes. Trust remains in the existing manager constants and canonical component
metadata, not in a checksum fetched from the mirror. Archive/member or other
integrity failures terminate installation without another transport attempt.

Before publishing Vanilla HyprArch v1.0.3, download the uploaded archive via
HTTPS from
`https://vanhyprarch.it/dist/v1/vanhyprarch-zig-player/releases/v0.1.1/assets/vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz`
and verify its size and SHA-256 against the trusted values above. The operator
has confirmed publication and independent HTTPS verification: HTTP 200,
149,617 bytes, and the trusted archive SHA-256 above. This satisfies the player
archive publication prerequisite for v1.0.3. Isolated installer tests do not
require the endpoint to exist.

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

## Recreate operator upload materials

After `release.publication check` passes, set these operator-chosen variables in
Bash: `WORKSPACE` (the durable publisher), `VERSION`, `CHANNEL`, `SEQUENCE`,
`PREVIOUS_SEQUENCE` (the last published sequence), and new absolute `UPLOAD` and
`NOTES` directories outside Git/web roots. Keep the approved release and catalog
inputs unchanged. Run multi-command examples with `set -euo pipefail`; stop on
any failed check. New selections must not overwrite unexplained existing files.

The following reproduces the practical five-file selection without depending on
any earlier Downloads directory. Only `UPLOAD` is selected in FileZilla; never
upload `NOTES`, the workspace, receipts, keys or numbered staging-directory names.

```bash
set -euo pipefail
PUB="$WORKSPACE"
PUBLIC="$PUB/public/vanilla-hyprarch"
BASE=https://vanhyprarch.it/dist/v1/vanilla-hyprarch
python -B -m release.publication --workspace "$PUB" check
cmp "$PUBLIC/channels/$CHANNEL.json" "$PUB/receipts/catalogs/$CHANNEL/$SEQUENCE.json"
test ! -e "$UPLOAD"
test ! -e "$NOTES"
mkdir -m 0700 "$UPLOAD" "$NOTES"
mkdir -p "$UPLOAD/01-assets/releases/$VERSION/assets" \
  "$UPLOAD/02-metadata/releases/$VERSION" "$UPLOAD/03-channel/channels"
cp "$PUBLIC/releases/$VERSION/assets/release.json" "$UPLOAD/01-assets/releases/$VERSION/assets/"
cp "$PUBLIC/releases/$VERSION/assets/vanhyprarch-$VERSION.tar.gz" "$UPLOAD/01-assets/releases/$VERSION/assets/"
cp "$PUBLIC/releases/$VERSION/manifest.json" "$PUBLIC/releases/$VERSION/manifest.json.sig" "$UPLOAD/02-metadata/releases/$VERSION/"
cp "$PUB/receipts/catalogs/$CHANNEL/$SEQUENCE.json" "$UPLOAD/03-channel/channels/$CHANNEL.json.complete"
(cd "$UPLOAD" && sha256sum "01-assets/releases/$VERSION/assets/"* \
  "02-metadata/releases/$VERSION/"* "03-channel/channels/$CHANNEL.json.complete") > "$NOTES/UPLOAD-SHA256SUMS"
```

Record approved source, lengths, hashes and local signature verification in the
operator's publication record. The native signature and catalog envelope are
copied as already signed, never regenerated. An identical historical remote file
is verified and skipped; different bytes or an unknown directory require stopping.

Generate the established GET-only byte-comparison helper from this tracked text:

```bash
cat > "$NOTES/HTTPS-CHECKS.sh" <<'CHECKS'
https_check() (
  local remote="$1" expected="${2:-$1}" tmp status limit
  limit=$(wc -c < "$PUB/$expected") || return
  tmp=$(mktemp) || return
  trap 'rm -f -- "$tmp"' EXIT
  status=$(curl --fail --silent --show-error --proto '=https' --noproxy '*' \
    --connect-timeout 10 --max-time 120 --max-filesize "$limit" \
    -H 'Cache-Control: no-cache' -H 'Accept-Encoding: identity' \
    --output "$tmp" --write-out '%{http_code}' "$BASE/$remote") || return
  if [[ "$status" != 200 ]]; then
    printf 'FAIL: HTTP %s for %s\n' "$status" "$remote" >&2
    return 1
  fi
  cmp "$PUB/$expected" "$tmp" || return
  printf 'PASS %s\n' "$remote"
)
CHECKS
bash -n "$NOTES/HTTPS-CHECKS.sh"
source "$NOTES/HTTPS-CHECKS.sh"
https_check "channels/$CHANNEL.json" "receipts/catalogs/$CHANNEL/$PREVIOUS_SEQUENCE.json"
```

That last check authenticates the currently active pointer by exact comparison
with a previously verified frozen receipt, not the workspace's newer catalog.
For a separately authorized first channel publication, require no channel receipt
history and confirm the remote pointer is absent instead; its first sequence is
the pinned floor. A 404 for an established channel is a failure, never up-to-date.

Generate `UPLOAD.txt` with concrete local-to-remote mappings and checks:

```bash
cat > "$NOTES/UPLOAD.txt" <<UPLOAD_NOTES
Manual FileZilla FTPS publication: $VERSION / $CHANNEL sequence $SEQUENCE
Upload ONLY files under $UPLOAD. Numbered directories are local labels.
Remote base: /dist/v1/vanilla-hyprarch/
Keep release updates on hold until the final check passes. STOP on any mismatch.
Never overwrite different immutable bytes, delete the active pointer first, or
change roots, earlier releases, upgrade kits or packages as an incidental upload.

HTTPS setup in the same Bash terminal:
PUB="$PUB"
BASE="$BASE"
source "$NOTES/HTTPS-CHECKS.sh"
https_check channels/$CHANNEL.json receipts/catalogs/$CHANNEL/$PREVIOUS_SEQUENCE.json

1. Upload local 01-assets/releases/$VERSION/assets/release.json and
   vanhyprarch-$VERSION.tar.gz into remote releases/$VERSION/assets/.
   After both complete:
https_check releases/$VERSION/assets/release.json public/vanilla-hyprarch/releases/$VERSION/assets/release.json
https_check releases/$VERSION/assets/vanhyprarch-$VERSION.tar.gz public/vanilla-hyprarch/releases/$VERSION/assets/vanhyprarch-$VERSION.tar.gz

2. Upload local 02-metadata/releases/$VERSION/manifest.json and manifest.json.sig
   into remote releases/$VERSION/. After both complete:
https_check releases/$VERSION/manifest.json public/vanilla-hyprarch/releases/$VERSION/manifest.json
https_check releases/$VERSION/manifest.json.sig public/vanilla-hyprarch/releases/$VERSION/manifest.json.sig

3. Upload local 03-channel/channels/$CHANNEL.json.complete into remote channels/.
   Require BOTH checks before promotion:
https_check channels/$CHANNEL.json.complete receipts/catalogs/$CHANNEL/$SEQUENCE.json
https_check channels/$CHANNEL.json receipts/catalogs/$CHANNEL/$PREVIOUS_SEQUENCE.json

4. ONLY after every check passes, manually rename-overwrite in FileZilla FTPS:
   channels/$CHANNEL.json.complete -> channels/$CHANNEL.json
   Then require:
https_check channels/$CHANNEL.json receipts/catalogs/$CHANNEL/$SEQUENCE.json

No FTPS action is performed by these verification commands. Do not run all
stages together before their respective manual uploads have completed.
UPLOAD_NOTES
```

For first-channel publication omit only the old-pointer comparison after proving
absence as described above; never invent an old receipt. Archive `UPLOAD.txt`,
checksums, frozen signed bytes and observed HTTPS results with release evidence.
The helper bounds size, requires HTTP 200, refuses redirects and requests identity
encoding/cache revalidation. `cmp` checks every byte; a network failure, partial
transfer, signature/hash/identity mismatch or old-pointer change means stop.
Do not initiate Update until the new active catalog and its immutable references
have all passed verification. This is the accepted manual workflow, not a new
publication service or FTPS automation.

## Initial production root — verified

The existing root was signed interactively with an operator-held encrypted
Minisign key. Only PUBLIC pins, the root payload and its verified signed envelope
belong in project records. Private-key paths, custody arrangements and backups
are operator inputs; an agent must not inspect or invoke the key. Official
Minisign handles the passphrase prompt directly in the operator's terminal.

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
this is distinct from the pinned payload digest above. The complete anchor is
embedded in the reviewed updater source and retained across normal replacements.
Do not change it to rotate a key or rerun the completed root ceremony.

For a genuinely new, separately authorized publisher workspace only, obtain the
signed initial root from the tracked public trust record rather than an untrusted
transport. The following extracts PUBLIC material without accessing a key:

```bash
python -B - "$ROOT_ENVELOPE" <<'PY_ROOT'
import base64, json, sys
from pathlib import Path
trust = json.loads(Path('release/trust.json').read_bytes())
with Path(sys.argv[1]).open('xb') as output:
    output.write(base64.b64decode(trust['root'], validate=True))
PY_ROOT
python -B -m release.publication --workspace "$NEW_WORKSPACE" init \
  --root-envelope "$ROOT_ENVELOPE" \
  --public-key RWR+ayLStZnlvFmvSohkDaHCDoR1lgtFYXElF3aN3YOhOZLaJQa+XR59 \
  --root-sha256 58e8bc7a3094d4ea9ad2b58b80af1184feab3c530157556eeb950c78980f0f72
```

Set new absolute output paths before use. This initializes empty history; it
cannot reconstruct an established publisher. For continuing publication restore
its verified workspace/receipts, reconcile published counters, then run `check`.
Do not use `init` to evade missing history. Interactive release/catalog commands
are in the [operator runbook](release-workflow.md#6-interactive-signing-and-local-verification).

## Initial production publication — complete

The authenticated export is `WORKSPACE/public/vanilla-hyprarch/`; its absolute
workspace location is supplied by the operator.
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

## v1.0.1 Stable sequence 2 — complete

The sole developer published the approved v1.0.1 assets, manifest and native
signature, verified their HTTPS bytes, then staged, verified and activated
signed Stable sequence 2 last. It binds unchanged v1.0.0 and v1.0.1 at
`83bfeaa627392817c21b29ce73557a32f5ad563e`, expires
`2027-10-15T09:35:27Z`, and retains root 1. Both original v1.0.0 objects and the
production root remain unchanged. No Candidate catalog was introduced.

Real VM acceptance passed signed ServerPlan discovery with GitHub HTTP 404,
zero migrations, normal dock authorization, journal retention after stale Arch
mirror failures, full Arch upgrade and exact-target resume, identity-last
completion, Stable 2 ledger, cleared journal and successful reboot/desktop checks.
The public original-v1.0.0 administrative kit is a separate download, not an
update-protocol object. It remains available through the historical user guide
and does not change signed channel membership.

## v1.0.2 Stable sequence 3 — complete

The immutable annotated tag targets `39ee15155e49be0af3d044a0b11b6c89108fddf7`.
The signed catalog retains root 1 and the unchanged v1.0.0/v1.0.1 bindings, adding
v1.0.2. Issuance is `2026-10-15T15:04:41Z`; expiry is `2027-10-15T15:04:41Z`.

| Public object | Bytes | SHA-256 |
| --- | ---: | --- |
| `releases/v1.0.2/assets/release.json` | 527 | `6292c27007151fbf859e92f2a0e066f3e0766dee3c075d798c1c9d76ca7bcb2c` |
| `releases/v1.0.2/assets/vanhyprarch-v1.0.2.tar.gz` | 65,330,818 | `91a521734dd9ea2cbfc6a239ca3969b70913ead28991c90594e1711a57f73bf7` |
| `releases/v1.0.2/manifest.json` | 922 | `8da04f8f2fa418abd352e9908dc8441256d29143b61380de5beabd94b837dc74` |
| `releases/v1.0.2/manifest.json.sig` | 307 | `438286a32f8f6f39c3e9a22d977a03d5ccb0bb725e3c70c24a9df4054cb44bf6` |
| `channels/stable.json` (sequence-3 envelope) | 1,968 | `5a4b4146d9ca1ef57f4c743e3012faaf29d8ee71cd016a7433a0fb355b40e0ec` |

The catalog **payload** digest, used by the anti-rollback ledger, is
`a234251a982276296b9a876e189e3bd599943bfaf3d51ac113aba29a465956dc`.
The deterministic installed updater hash is
`4c4c5c5c44dbf9cb2eb42cf5736aa5e23fc11c56f035b673543ef666e7e5c220`.
Normal signed upgrade from genuine v1.0.1, zero migrations, provenance/ledger,
journal cleanup, reboot and subsequent up-to-date discovery passed in release
testing. GitHub's three authenticated downloads also match the approved bytes.
At that release, live Yay maintenance acceptance was deferred; the genuine
v1.0.2 -> v1.0.3 run subsequently passed.

## v1.0.3 Stable sequence 4 — complete

The immutable annotated `v1.0.3` tag names source commit
`53bd30c402352684befb41bef9f827e19de254d9`. Both source builds and the strict tag
build produced the same archive. ServerPlan assets, manifest/signature, complete
candidate and final active catalog passed independent HTTPS/public-key checks.
Sequence 4 preserves v1.0.0, v1.0.1 and v1.0.2 bindings and adds v1.0.3. It was
issued `2026-10-16T11:56:13Z`, expires `2027-10-16T11:56:13Z`, and uses root 1.

| Object | Bytes | SHA-256 |
| --- | ---: | --- |
| `vanhyprarch-v1.0.3.tar.gz` | 65363742 | `614a360941c5fa05175cf7da0815ff1fc30ccc6a3a50c8ba17dc87c6f05622b7` |
| `release.json` | 538 | `8d8f154d0bc6dbb6e375edfc6160e289f3135b953c7e84a4ef2047939d3db1f4` |
| `manifest.json` | 933 | `1cf105f1e12872c6be5824508511c16461b410c5c205bec3efd79da9b7cb8d78` |
| `manifest.json.sig` | 307 | `57239fbb406919545e258f702e3a12ebfcb4fd1b06e47c46277b13622dac9072` |
| Signed Stable catalog envelope | 2380 | `494bfa60270e0897232c4bfe11236a31df9b753f0133248f663ff0d0b89a3548` |

Stable catalog **payload** SHA-256 is
`b75f632c59b6d0cc09ab0928c75911dc4c113afaaafb00d7155d3aa2e83340b2`;
the installed updater hash is
`4c4c5c5c44dbf9cb2eb42cf5736aa5e23fc11c56f035b673543ef666e7e5c220`.
These historical identities are evidence, not values to reuse for another release.
The genuine dock upgrade, Yay/reboot continuation, post-upgrade validators,
operator visual/preferences acceptance and authenticated already-current check
passed. The immutable GitHub Release and all three attached assets were verified
through authenticated downloads; anonymous GitHub page/assets returned HTTP 404.
See [the operator runbook](release-workflow.md) for the next release's steps.

## Accepted single-user manual publication policy

Publication and release updates use a manually coordinated maintenance window:
**do not initiate Update while publishing**.
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

- Keep private-key and passphrase custody outside Git, publication workspaces
  and web roots, with recoverable offline backups held by the operator. Do not
  generate another key for this initial root. Only the user
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
- Genuine v1.0.1 target preflight, normal upgrade, exact-target recovery and
  reboot acceptance on that same VM are complete, including GitHub HTTP 404 and
  authenticated ServerPlan acquisition. Keep the accepted originals and recovery
  records; do not repeat preparation. Other installed-system changes still need
  authorization. No package/release/key installation occurred in Phase 3A itself.

Run isolated tests with a verified official Minisign executable:

```text
MINISIGN=/absolute/verified/minisign PYTHONDONTWRITEBYTECODE=1 python tests/static-publication.py
```
