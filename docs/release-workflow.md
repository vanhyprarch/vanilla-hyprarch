# Development and signed release operator runbook

Start here for the operational sequence. [Current state](current-state.md)
records published versions and deferred acceptance; [release engineering](release-engineering.md)
defines the artifact, authority and recovery contracts;
[ServerPlan publication](serverplan-publication.md) owns upload-material generation
and the manual FTPS procedure; [signed distribution](signed-distribution.md)
defines signatures, trust, expiry and rollback rules. These tracked documents,
not previous chats, terminal history or a particular Downloads directory, are
the instructions for a new session.

Command blocks are operator templates, not permission to execute every phase.
Set the named variables to reviewed values on the machine running that block.
Use a dedicated Bash session with `set -euo pipefail` for multi-command operations;
stop on every nonzero result. Never continue to a push, signature, upload or
apply after a failed prerequisite.

## 1. Establish context and develop within ownership boundaries

From the checkout, inspect before changing anything:

```bash
git status --short --branch
git rev-parse HEAD origin/main
git log -5 --oneline
git tag --list
cat release/release.toml
```

Use authenticated Git access to verify remote refs when needed. Do not discard
an unexpected dirty tree or assume the checkout's declaration is an installed
identity. `main` is development; `/usr/share/vanhyprarch/release.json` is the
release installation identity. Its absence means unreleased/development, where
automatic release updates correctly refuse. Never forge it for testing.

The repository map is: `home/` and `assets/` managed payload, `seeds/` create-once
inputs, `bin/` public user commands, `packages/` baseline, `deployment/` ownership
and service policy, `install/` authoritative lifecycle implementations, `release/`
artifact/signature contracts, `admin/` exceptional administrative tools, and
`tests/` standalone regression scripts. Read [decisions](decisions.md) and the
relevant [compatibility entry](compatibility.md) before changing known boundaries.

- System integration owns packages, privileged files, services and the installed
  updater/provenance. See [system integration](system-integration.md).
- Managed deployment owns only `VANILLA_MANAGED` user artifacts. Create-once and
  `USER_OWNED` state must not be replaced to make a deployment pass. See
  [ownership](deployment-ownership.md), [managed deployment](managed-file-deployment.md)
  and [create-once initialization](create-once-initialization.md).
- A release number alone never authorizes a state migration. Appearance,
  keyrings, providers and user preferences retain their existing authorities.

For an explicitly authorized development installation, as its normal user:

```bash
python -B install/managed_deploy.py --source-root "$PWD" plan update
# Review every action/conflict and ownership before authorizing the next command.
python -B install/managed_deploy.py --source-root "$PWD" update
python -B install/managed_deploy.py --source-root "$PWD" validate
```

Do not use this engine to replace backend-owned updaters or bypass another owner.
Preserve rollback material; check native Quickshell reload/log health for QML
changes. Do not run the full installer/updater merely to deploy a UI edit.
Use focused `python -B tests/NAME.py` and `sh tests/NAME.sh` suites from the
relevant document; there is no assumed pytest command. Inspect tests before live
or input-sensitive execution. Only commit/push, deploy, sign, publish, upgrade
or perform destructive recovery with explicit operator authorization.

## 2. Declare and approve an exact release source

Edit only the necessary declaration/assertions/docs after feature acceptance.
`release/release.toml` is the single authored identity: Stable is `vMAJOR.MINOR.PATCH`
with `channel = "stable"`; Candidate is `vMAJOR.MINOR.PATCH-rcN` with
`channel = "candidate"`. Architecture is x86_64 and update protocol is 1.
Preserve compatibility minimums unless a reviewed change requires otherwise.

Review `release/migrations/registry.toml` and the installed source level. Required
IDs are the range after the installed level through the target level; at level
1, v1.0.1 -> v1.0.2 has an empty plan. Add a migration only for a real supported
state transition, with preservation/conflict behavior and isolated tests.
Stable cannot upgrade to Candidate; Candidate upgrades stay within their product
version, including final Stable promotion. Use a genuine compatible installation
for acceptance, not a forged Stable identity. A Candidate is optional, not a
mandatory extra publication for every patch.

Update current-declaration assertions in `tests/release-artifact.py`,
`tests/release-update-primitives.py` and `tests/release-update-bootstrap.py`;
do not globally replace historical fixture versions. Run the affected suites.
For updater/release changes, relevant coverage includes:

```bash
python -B tests/release-artifact.py
python -B tests/release-identity.py
python -B tests/release-update-primitives.py
python -B tests/release-update-driver.py
python -B tests/release-update-bootstrap.py
python -B tests/signed-distribution.py
python -B tests/signed-updater.py
python -B tests/updater-publication.py
python -B tests/static-publication.py
git diff --check
```

Add manifest, ownership, managed-deploy and relevant QML/asset suites when affected.
Minisign tests use disposable TEST-ONLY keys and clean them up; they never use
production keys. Review the complete diff, then stage only approved files,
commit and push normally. Independently verify `origin/main`; record the full
approved source SHA. Do not build a publication from uncommitted source.

## 3. Build twice and record immutable artifact identity

The following are templates. Set `REPO` to the trusted checkout, `VERSION` and
`COMMIT` to the approved declaration/full SHA, and `OUT_A`/`OUT_B` to new, empty
absolute output directories outside Git. Variables must be set in each terminal
where used. Do not use a private-key directory as an output directory.

```bash
cd "$REPO"
mkdir "$OUT_A" "$OUT_B"
python -B release/build.py build --commit "$COMMIT" --output-dir "$OUT_A"
build_scratch=$(mktemp -d)
git clone --no-hardlinks --no-checkout "$REPO" "$build_scratch/source"
git -C "$build_scratch/source" checkout --detach "$COMMIT"
python -B "$build_scratch/source/release/build.py" build \
  --repo "$build_scratch/source" --commit "$COMMIT" --output-dir "$OUT_B"
cmp "$OUT_A/release.json" "$OUT_B/release.json"
cmp "$OUT_A/vanhyprarch-$VERSION.tar.gz" "$OUT_B/vanhyprarch-$VERSION.tar.gz"
python -B release/build.py verify "$OUT_A/release.json" "$OUT_A/vanhyprarch-$VERSION.tar.gz"
(cd "$OUT_A" && sha256sum release.json "vanhyprarch-$VERSION.tar.gz") > "$OUT_A/SHA256SUMS"
wc -c "$OUT_A/release.json" "$OUT_A/vanhyprarch-$VERSION.tar.gz"
```

Record commit, sizes, hashes, identity, migration/compatibility fields, test
results and reproducibility. Compute the eventual installed updater hash using
the existing packager from the same approved extracted source/clean checkout:

```bash
python -B -c 'import hashlib,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from install.update_bootstrap_integration import BootstrapIntegration; print(hashlib.sha256(BootstrapIntegration(Path(sys.argv[1])).build()).hexdigest())' "$build_scratch/source"
```

The archive contains tracked files only, including all vendored SVGs, licenses
and manifests. Keep the builder's rejection of tracked release outputs, symlinks,
unsafe paths and oversized content. SHA-256 is integrity evidence, not independent
publisher authentication; source approval and the pinned signed chain supply trust.

## 4. Read-only preflight on a genuine compatible installation

Use the designated release-test installation and its suitable existing recovery
backup/snapshot. Transfer the approved archive, metadata and checksum record by
an established trusted method. Authenticate the expected hashes independently,
then check them before extracting/executing target code. Do not recreate an
existing test installation or repeat updater preparation. Original unprepared
v1.0.0 is the exceptional [legacy bridge](updater-preparation.md); genuine signed
v1.0.1 and later need no bridge.

In the target user's graphical Foot terminal, set `BUNDLE` to the absolute input
directory and `VERSION` to the approved target. Verify `SHA256SUMS` against the
approved record, not merely a checksum downloaded from the same untrusted host.
The installed updater/provenance must already be validated for that source release.

```bash
cd "$BUNDLE"
sha256sum --check SHA256SUMS
python3 -I -B -c 'import sys; from pathlib import Path; sys.path.insert(0,"/usr/local/bin/vanhyprarch-update"); from release.build import verify; print(verify(Path(sys.argv[1]),Path(sys.argv[2]))["version"])' "$BUNDLE/release.json" "$BUNDLE/vanhyprarch-$VERSION.tar.gz"
test ! -e "$BUNDLE/vanhyprarch-$VERSION"
test ! -L "$BUNDLE/vanhyprarch-$VERSION"
tar -xzf "$BUNDLE/vanhyprarch-$VERSION.tar.gz" -C "$BUNDLE"
SOURCE="$BUNDLE/vanhyprarch-$VERSION"
target_user=$(id -un)
target_context=$(python3 -B "$SOURCE/install/secret_service_preflight.py" context)
sudo python3 -B "$SOURCE/install/release_update.py" plan \
  --target-user "$target_user" --target-context-json "$target_context" \
  --xdg-config-home "${XDG_CONFIG_HOME:-$HOME/.config}" \
  --xdg-data-home "${XDG_DATA_HOME:-$HOME/.local/share}" \
  --xdg-state-home "${XDG_STATE_HOME:-$HOME/.local/state}" \
  --xdg-cache-home "${XDG_CACHE_HOME:-$HOME/.cache}" \
  --release-metadata "$BUNDLE/release.json" \
  --release-artifact "$BUNDLE/vanhyprarch-$VERSION.tar.gz"
```

Capture context **before sudo**; do not use a root shell, `sudo -E`, guessed XDG
defaults or process-environment scraping. Require correct source/target, exact
target digest, expected migrations and all three authority plans. Review provider,
package and managed ownership conflicts and user-state preservation. Plan uses
temporary preview files under `/run`, cleans them, and applies no authority.
Compare read-only before/after hashes of installed identity, updater/provenance
and distribution ledger; require no new journal. If a journal already exists,
stop and use the recovery section instead. Do not run offline apply here.

This proves bundle/compatibility planning; it does not substitute for signed
discovery or a genuine normal-dock upgrade. Recheck a plan after material system
changes. Complete needed Arch maintenance using standalone Update System
(`yay -Syu`) and follow reboot guidance before the later real upgrade.

## 5. Annotated tag and strict rebuild

After exact source/artifact and preflight approval, inspect local and remote refs.
If the tag exists, require an annotated tag with the exact approved target; stop
on any mismatch. Only when absent, create it:

```bash
git tag -a "$VERSION" "$COMMIT" -m "Vanilla HyprArch $VERSION"
git cat-file -t "refs/tags/$VERSION"
git rev-parse "$VERSION^{}"
tag_output=$(mktemp -d)
python -B release/build.py build --commit "$COMMIT" --tag "$VERSION" --output-dir "$tag_output"
python -B release/build.py verify "$tag_output/release.json" "$tag_output/vanhyprarch-$VERSION.tar.gz"
cmp "$OUT_A/release.json" "$tag_output/release.json"
cmp "$OUT_A/vanhyprarch-$VERSION.tar.gz" "$tag_output/vanhyprarch-$VERSION.tar.gz"
git push --no-follow-tags origin "refs/tags/$VERSION:refs/tags/$VERSION"
git ls-remote --exit-code origin "refs/tags/$VERSION" "refs/tags/$VERSION^{}"
```

Require remote peeled commit equality. Never silently move, delete or force-push
a release tag. Fixing a published payload requires a new version, not a rebuild
under an old identity.

## 6. Interactive signing and local verification

`WORKSPACE` is the established private publisher directory, with frozen receipts;
it is not an upload directory. Restore a verified workspace backup if necessary.
Do not rerun `init` over it, recreate sequence history from an untrusted active
pointer, or re-sign old releases. The first-use initialization and existing public
root pins are documented in [ServerPlan publication](serverplan-publication.md).

The operator sets `SIGNING_KEY` to their encrypted offline Minisign key in their
own terminal. An assistant supplies commands only: it must not read/copy/invoke
that key or handle a passphrase. Only the operator runs signing interactively
in Foot, without sudo; official Minisign owns its passphrase prompt. Never use
an unencrypted test key or the test-only `-W` option for production.

```bash
python -B -m release.publication --workspace "$WORKSPACE" check
python -B -m release.publication --workspace "$WORKSPACE" release \
  --metadata "$OUT_A/release.json" --archive "$OUT_A/vanhyprarch-$VERSION.tar.gz" \
  --approved-commit "$COMMIT" --secret-key "$SIGNING_KEY"
```

Set `CHANNEL` to the approved channel, `SEQUENCE` to its next contiguous receipt
number, and `ISSUED_AT` once to an approved UTC timestamp. Retain that timestamp
for retries. Derive a `--version` argument for **every** intended catalog member
from verified history; retain prior immutable bindings. Example only: substitute
the actual versions and channel, not these historical members blindly:

```bash
python -B -m release.publication --workspace "$WORKSPACE" catalog \
  --channel "$CHANNEL" --sequence "$SEQUENCE" \
  --version v1.0.0 --version v1.0.1 --version v1.0.2 \
  --issued-at "$ISSUED_AT" --secret-key "$SIGNING_KEY"
python -B -m release.publication --workspace "$WORKSPACE" check
```

Stable contains only final releases. Candidate uses its independent sequence
history and may contain compatible candidates/final promotions. Catalog default
and maximum validity are 365 days = 31,536,000 POSIX seconds; optional
`--expires-at UTC_TIME` can shorten it. Renewal with unchanged releases still
requires a higher sequence. Root lifetime is separately five UTC calendar years.
Require no pending channels and the complete intended inventory from `check`;
it verifies root, signatures, historical bindings and full artifacts.

On cancellation/failure, stop and inspect `check` and receipts. Repeating the
identical release input reuses frozen signatures. Never retry the same catalog
sequence with a different issuance, expiry or membership. `resume-channel
--channel CHANNEL` only completes the latest valid reserved local catalog;
missing/corrupt receipts or unknown files require review, not force/overwrite.

## 7. Manual ServerPlan publication

Follow [the canonical upload-material and HTTPS procedure](serverplan-publication.md#recreate-operator-upload-materials).
It regenerates the five-file selection, `UPLOAD.txt` mappings and `HTTPS-CHECKS.sh`
from tracked instructions and the verified workspace. No previous Downloads
file is needed. Keep Update on hold through this manually coordinated window.

The order is immutable assets -> HTTPS byte verification -> immutable manifest
and native signature -> HTTPS verification -> complete temporary catalog ->
verify staged bytes and unchanged old active catalog -> FileZilla FTPS
same-directory rename-overwrite **last** -> verify the new active catalog.
Do not delete the active pointer first. An existing identical immutable object
is verified and skipped; different bytes require stopping. No root, historical
release, public upgrade kit or package directory is an incidental upload target.

## 8. Genuine upgrade, reboot acceptance and recovery

After publication is fully verified, invoke normal dock Update or
`/usr/local/bin/vanhyprarch-update` as the normal graphical user, without sudo
or a fabricated `resume` flag. Review the discovered authenticated target and
final apply confirmation. Development identity refuses release updates.

v1.0.2's updater offers the existing unprivileged `yay -Syu` maintenance flow
only for a new authenticated target. Decline/failure stops Vanilla deployment;
any package/version change requests a manual reboot. A later invocation repeats
the check, usually finding no changes. No-new-release and exact-target recovery
skip maintenance. No automatic reboot or persistent reboot marker exists.
An older installed updater controls the transition installing this feature:
v1.0.1 -> v1.0.2 did not test it live. Live yay acceptance is deferred to genuine
v1.0.2 -> v1.0.3; the accepted automated coverage is not a v1.0.2 release blocker.

After apply, use read-only checks against the approved target records:

- Installed `/usr/share/vanhyprarch/release.json` must exactly match approved
  metadata bytes, version/channel/commit and migration level.
- `/usr/local/bin/vanhyprarch-update` must match the recorded packager SHA-256.
  Provenance `/var/lib/vanhyprarch/update-bootstrap-v1.json` must have schema 3,
  the same executable hash, expected initial anchor and initialized marker.
  Ownership/modes are root:root 0755 (updater), 0600 (provenance), 0644 (identity).
- The root-private distribution ledger must retain the authenticated root,
  channel sequence and immutable target binding. Its catalog digest is SHA-256
  of the canonical **payload**, not of the signed envelope file. Compare with
  the approved signed catalog; do not reset state to match a historical example.
- Require no remaining `/var/lib/vanhyprarch/update/journal.json`. A non-null
  ledger `authorization` alone is normal retained signed evidence, not a pending
  transaction. It is replaced/cleared during later authenticated discovery;
  completion does not require it to be null.
- Reboot manually, log in, verify shell/wallpaper/theme/icons and preserved
  preferences, then normal Update must report the installed release current
  only after authenticated discovery. Record exactly which acceptance passed.

For example, set `EXPECTED_UPDATER_SHA`, `CHANNEL`, `SEQUENCE`,
`CATALOG_PAYLOAD_SHA`, `ROOT_VERSION` and `ROOT_PAYLOAD_SHA` from the approved
build and signed publication records, and use this read-only immediate check.
`BUNDLE`/`SOURCE` still name the previously verified target inputs on this machine:

```bash
sudo python3 -B - "$BUNDLE/release.json" "$SOURCE/release/trust.json" \
  "$EXPECTED_UPDATER_SHA" "$CHANNEL" "$SEQUENCE" "$CATALOG_PAYLOAD_SHA" \
  "$ROOT_VERSION" "$ROOT_PAYLOAD_SHA" <<'PY_ACCEPT'
import hashlib, json, stat, sys
from pathlib import Path
expected = Path(sys.argv[1]).read_bytes()
identity = json.loads(expected)
assert Path('/usr/share/vanhyprarch/release.json').read_bytes() == expected
updater = Path('/usr/local/bin/vanhyprarch-update')
digest = hashlib.sha256(updater.read_bytes()).hexdigest()
assert digest == sys.argv[3]
provenance_path = Path('/var/lib/vanhyprarch/update-bootstrap-v1.json')
provenance = json.loads(provenance_path.read_bytes())
assert provenance['schema'] == 3 and provenance['sha256'] == digest
assert provenance['update_protocol'] == identity['update_protocol']
assert provenance['distribution_initialized'] is True
assert provenance['distribution_anchor_sha256'] == json.loads(Path(sys.argv[2]).read_bytes())['root_sha256']
ledger = json.loads(Path('/var/lib/vanhyprarch/distribution-security-v1.json').read_bytes())
assert ledger['schema'] == 1
state = ledger['state']
assert state['channels'][sys.argv[4]] == {'sequence': int(sys.argv[5]), 'sha256': sys.argv[6]}
assert state['root_version'] == int(sys.argv[7]) and state['root_sha256'] == sys.argv[8]
assert identity['version'] in state['bindings']
assert not Path('/var/lib/vanhyprarch/update/journal.json').exists()
for path, mode in ((updater, 0o755), (provenance_path, 0o600),
                   (Path('/usr/share/vanhyprarch/release.json'), 0o644)):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
    assert stat.S_IMODE(info.st_mode) == mode
print('PASS: exact identity/updater/provenance, authenticated channel/root, no journal')
PY_ACCEPT
```

A later legitimate catalog/root can supersede these expected values. Review its
authenticated records rather than changing/deleting security state to satisfy an
old acceptance example. This diagnostic reads no application secrets and does
not require `authorization` to be null.

Before deployment beyond the release-test installation, require its acceptance
and a current recoverable system/user-state backup. Do not change another
installation merely because its configuration resembles the test system.

For failures, read (do not edit) the journal and relevant package log:

```bash
sudo python3 -m json.tool /var/lib/vanhyprarch/update/journal.json
sudo tail -n 60 /var/log/pacman.log
```

A retained journal means incomplete work, not rollback. Repair an external Arch
mirror/database problem through full Update System (`yay -Syu`); official
`sudo pacman -Syu` is also a supported administrator repair. Never use
`pacman -Sy` followed by selected installs. If a selected mirror remains out of
sync, review the official mirror list/status before a full refresh/upgrade.
Then invoke normal Update as the same user, including after reboot: it verifies
the exact retained signed target before resuming, ahead of discovery/maintenance.
It cannot choose a new target. Expired metadata cannot authorize a new update;
previously authenticated exact-target recovery has the bounded exception in
[the protocol](signed-distribution.md#interrupted-updaterprovenance-publication).
Never delete journals, staging, provenance, authorization or ledger floors to
make progress. Missing/corrupt proof, foreign ownership, provider conflicts,
wrong identity, unexpected migrations or an unexplained updater pair require
stopping for diagnosis. Do not perform updater-only downgrade or snapshot
restoration during an active transaction without separately reviewed recovery.

## 9. GitHub Release and independent download verification

For a normal patch, attach only the approved archive, `release.json` and generated
`SHA256SUMS`. Historical v1.0.1 also carries its original-v1.0.0 bridge; do not
turn that kit into a requirement for newer installed releases. Signed protocol
objects stay on the verified static distribution unless separately approved.

Write reviewed concise release notes outside Git, covering changes, compatibility,
acceptance and any explicitly deferred test. Inspect the authenticated exact-tag
endpoint first; bulk release listings and anonymous 404s are not reliable evidence
that a known release is absent:

```bash
gh api "repos/vanhyprarch/vanilla-hyprarch/releases/tags/$VERSION"
```

If absent after an authenticated check and the remote tag is verified:

```bash
gh release create "$VERSION" --repo vanhyprarch/vanilla-hyprarch --verify-tag \
  --target "$COMMIT" --title "Vanilla HyprArch $VERSION" \
  --notes-file "$RELEASE_NOTES" --latest \
  "$OUT_A/vanhyprarch-$VERSION.tar.gz" "$OUT_A/release.json" "$OUT_A/SHA256SUMS"
```

For a Candidate add `--prerelease` and use `--latest=false` instead of `--latest`.
For an existing Release inspect notes, draft/prerelease status, tag and every
asset first. Download/compare existing assets; do not duplicate, delete or use
`--clobber` on a mismatch. Only separately approved missing uploads or note
corrections may be applied (`gh release upload`, `gh release edit --notes-file`).
Publishing a reviewed draft uses `gh release edit VERSION --draft=false`.

Use a new empty `VERIFY_DIR` to download **all** actual assets independently:

```bash
mkdir "$VERIFY_DIR"
gh api "repos/vanhyprarch/vanilla-hyprarch/releases/tags/$VERSION" > "$VERIFY_DIR/release-api.json"
mkdir "$VERIFY_DIR/assets"
gh release download "$VERSION" --repo vanhyprarch/vanilla-hyprarch --dir "$VERIFY_DIR/assets"
(cd "$VERIFY_DIR/assets" && sha256sum --check SHA256SUMS)
cmp "$OUT_A/release.json" "$VERIFY_DIR/assets/release.json"
cmp "$OUT_A/vanhyprarch-$VERSION.tar.gz" "$VERIFY_DIR/assets/vanhyprarch-$VERSION.tar.gz"
cmp "$OUT_A/SHA256SUMS" "$VERIFY_DIR/assets/SHA256SUMS"
wc -c "$VERIFY_DIR/assets/"*
sha256sum "$VERIFY_DIR/assets/"*
python -B release/build.py verify "$VERIFY_DIR/assets/release.json" "$VERIFY_DIR/assets/vanhyprarch-$VERSION.tar.gz"
```

Compare every name/length/digest with the approved local originals and API asset
records, including the checksum file itself. Require published, non-draft status
and the correct prerelease flag. Independently check the public page and each
`browser_download_url` without gh authentication or credentials, for example:

```bash
curl --silent --show-error --location --proto '=https' --proto-redir '=https' \
  --range 0-0 --output /dev/null --write-out '%{http_code}\n' \
  "https://github.com/vanhyprarch/vanilla-hyprarch/releases/tag/$VERSION"
```

Repeat for each asset URL. Record anonymous HTTP 404 accurately: it is a known
account-access limitation, not failure of an authenticated, verified publication.
ServerPlan signed distribution remains independently usable. Never claim an
anonymous download succeeded merely because gh uploaded/downloaded successfully.

## 10. Preserve continuity and schedule metadata maintenance

Record public release/tag/commit, approved artifact and updater hashes, channel
sequence, signed payload/envelope digests, publication and acceptance results in
current-state/release records. Documentation may advance on main without changing
the immutable tag/archive. Preserve old releases, signed receipts and original
recovery materials. Back up Git refs **and** downloadable Release assets/metadata;
a mirror containing tags does not preserve uploaded binaries. Use verified
additive backup increments, without overwriting historical copies. Locations and
private custody arrangements belong in operator records, never public docs.

Temporary selections, notes and verification downloads can be regenerated.
The encrypted offline key and complete frozen publisher workspace are durable
operator-held inputs, not disposable build outputs. If receipts are missing,
restore/reconcile an authenticated backup; this tooling has no general import
from a current mirror or safe sequence-reset command.

Renew catalogs before expiry using the next channel sequence even without a
product release. Shortening future validity does not revoke older catalogs for
clients that have not observed the new sequence. Root 1 expires
2031-10-15T07:35:10Z. Protocol/updater dual-signed sequential rotation validation
exists; the current publisher supports root 1 only. A production rotation ceremony
and publication workflow require separate work and review well before expiry.
Never silently edit the pinned initial root, install an untrusted new key, reset
rollback state or bypass expiration. See [root rotation](signed-distribution.md#root-rotation-validation).
