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

Codex can perform already-authorized local preparation, read-only verification
and report analysis without asking again for routine commands. The operator
controls VM transfers/execution, signing keys, manual FileZilla uploads and
Stable activation. A new scope still needs explicit authorization: commit/push,
tag publication, signing, each remote publication stage, genuine upgrade or
production deployment. Stop at the relevant boundary with concrete reviewed
inputs; do not combine signing, upload and activation into one operation.

Use the reusable acceptance helper below, not release-specific diagnostic scripts.
Its focused gate is `python3 -B tests/release-acceptance.py`; its fixtures use
temporary releases and disposable TEST-ONLY keys. It does not change the updater
zipapp, installed authorities, trust roots or distribution protocol.
Rerun this focused gate after helper, authority CLI, ownership/service manifest
or relevant Qt changes; a new helper still needs an authorized real VM rehearsal.

Reuse successful evidence by identity and state, rather than repeating every
previous gate after an unrelated diagnostic warning:

| Evidence | Reuse and repetition rule |
| --- | --- |
| Reviewed source and focused readiness tests | Reuse for unchanged source; rerun affected tests after code changes. |
| Two reproducible builds and approved hashes | Preserve both outputs; section 5 still requires its one strict tagged comparison. Do not rebuild to debug a VM report. |
| Input verification | Recheck hashes at transfer/execution boundaries before using target code; this does not require rebuilding or re-signing. |
| PLAN and ownership decisions | Repeat after material target-system/package/provider changes; retain successful independent checks if a wrapper failed before PLAN. |
| Frozen signatures and HTTPS publication results | Reuse immutable receipts; verify each new upload batch and final active pointer. Never re-sign historical bytes. |
| Post-upgrade technical report | One complete run after the real upgrade/reboot. A warning alone does not invalidate successful validators; resolve only concrete remaining required checks. |
| Visual and normal-dock already-current acceptance | Operator records each separately; neither can be inferred from a technical report. |

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
# Review actions, conflicts and ownership; proceed within the authorized scope.
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

Use the existing designated release-test VM and its suitable recovery backup;
do not recreate it or repeat updater preparation. Original unprepared v1.0.0
alone needs the [legacy bridge](updater-preparation.md). An ordinary preflight
is offline bundle/compatibility planning, not signed discovery or an upgrade.

Use the reusable **operator-side** `release/acceptance.py`. It is not installed
as a new updater, service or package. Codex prepares inputs and reviews reports;
the operator alone performs authenticated SCP transfers and executes VM commands
in graphical Foot. Do not establish agent SSH access or fabricate graphical
context. Set `VM_HOST` and `VM_ENDPOINT` from the operator's verified target;
public examples intentionally contain no private host inventory.
The source installation must already have validated schema-3 updater provenance
and initialized signed-distribution state; diagnostics never initialize that state.

Codex may group local input preparation into one invocation. Set `OUT_A`,
`COMMIT`, `METADATA_SHA` and `ARCHIVE_SHA` from section 3's independently approved
record. `INSTALLED_METADATA` and `INSTALLED_UPDATER_SHA` name the **previous
release's** approved metadata file and packaged-updater hash, not values inferred
from the VM itself. `PREFLIGHT` must be a new directory outside Git. This works
before the target is signed or published:

```bash
python3 -B release/acceptance.py prepare --bundle "$OUT_A" --output "$PREFLIGHT" \
  --commit "$COMMIT" --metadata-sha256 "$METADATA_SHA" \
  --archive-sha256 "$ARCHIVE_SHA" --installed-metadata "$INSTALLED_METADATA" \
  --installed-updater-sha256 "$INSTALLED_UPDATER_SHA" --vm-host "$VM_HOST"
```

Preparation verifies the real archive contract, preserves the approved input
bytes and checksum file, computes the target updater with the existing packager,
and copies the one reusable Python helper and an approval record. Keep the
printed approval-record hash independently. The prepared directory is private;
it must travel through the operator's authenticated transfer, never an unsigned
public download treated as its own trust authority.

For example, when the chosen directory basename is `vanilla-preflight`, the
operator uses exactly these three manual operations. Transfer/retrieval are in
development Foot; execution is in the VM's graphical Foot:

```bash
scp -r "$PREFLIGHT" "$VM_ENDPOINT:Downloads/"
python3 -I -B ~/Downloads/vanilla-preflight/acceptance.py preflight ~/Downloads/vanilla-preflight
scp "$VM_ENDPOINT:Downloads/preflight-vanilla-preflight.txt" "$EVIDENCE/"
```

Substitute the actual prepared basename. One consolidated report is displayed and
saved with mode 0600; it refuses an existing path, including symlinks. An explicit
`--report NEW_PATH` records a justified retry without destroying previous evidence.
Keep other updates and deliberate preference edits idle during this comparison.
No terminal `tee`, root shell, global umask change or extra VM script is needed.
Python and the existing Vanilla baseline tools are required; missing tools fail
clearly rather than being installed by diagnostics. Host identity uses native
`uname` information, without requiring the optional `hostname` executable.

The helper independently checks the pinned inputs and installed updater before
importing its existing verifier. It captures provider/XDG context as the user
**before sudo**, then uses the authenticated updater's canonical `BundleStore`
for private root-owned preview material. The target driver's exact `plan`
command remains the compatibility/migration/three-authority authority. Its full
stdout and stderr are retained; source/target/digest, all three plan sections and
expected migration IDs must agree. No APPLY, maintenance or recovery is invoked.
The staged identity must still match approval, and PLAN consumes those root-owned
copies rather than rereading mutable user inputs after their verification.
Read-only package queries made by the canonical authorities are part of the
operator-authorized diagnostic, not an additional package-maintenance approval.

Only the privileged worker scopes its process umask to 0022, recording inherited
and effective values and restoring the original afterward. This lets the native
stager create its required exact 0755 directory; security validation is unchanged.
The v1.0.3 restrictive-umask failure was introduced by its manual wrapper; the
normal dock/Foot/sudo chain was separately measured at 0022. No installed updater
change or global sudo/umask policy is made here.

Identity, updater/provenance, security ledger, authority records and selected
manifest-derived user files are compared before/after, including handled failure.
Pending journals, authority intents, foreign previews or retained update staging
stop the check; unrelated temporary material is never deleted. Only this run's
native preview is cleaned. Hard termination/power loss cannot guarantee cleanup;
retain the failure report and inspect remaining state, without automatic repair.

PASS means all required checks succeeded. WARNING also exits 0, but records an
environmental issue or an unestablished property. FAIL exits nonzero (preserving
subprocess codes) and blocks progression. Required service failures come from the
release's actual default service policy; optional/unrelated failures, including
TPM measurement units, are warnings with unit details and available baseline
history. They are not silently ignored or automatically attributed to Vanilla.
Review warnings for relevance before closing the gate. A script defect does not
turn a genuine failure into PASS, nor invalidate other successful evidence.

Recheck PLAN after material package, provider, ownership or compatibility changes.
A passed preflight does not replace the real updater's own later PLAN. Arch
maintenance and reboot belong to the normal update workflow, never this helper.

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
for retries. Codex derives the reviewed Bash array `CATALOG_VERSIONS` from the
authenticated previous receipt's membership plus the approved new release;
the operator reviews that complete list and sequence before signing. Do not copy
a hard-coded historical version list or silently omit the current Stable.
The following signing block consumes the reviewed array:

```bash
catalog_args=()
for catalog_version in "${CATALOG_VERSIONS[@]}"; do
  catalog_args+=(--version "$catalog_version")
done
python -B -m release.publication --workspace "$WORKSPACE" catalog \
  --channel "$CHANNEL" --sequence "$SEQUENCE" \
  "${catalog_args[@]}" \
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
Codex groups mechanical preparation and verification for each completed batch
into one evidence summary; the operator need not transfer separate diagnostics
for each file. Keep the approval boundaries between signing, manual upload
batches, final activation and genuine upgrade intact.
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
v1.0.1 -> v1.0.2 did not test it live. Genuine v1.0.2 -> v1.0.3 acceptance closed
that gate, including Yay package changes, the manual-reboot stop, successful
continuation and final authenticated already-current discovery. Do not reopen
that completed gate unless relevant code changes require new acceptance.

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

Use the same reusable helper for the technical checks, with a fresh preparation
that includes the **public signed** publication evidence. Run the section-4
preparation command with `--publisher "$WORKSPACE" --output "$POSTUPGRADE"`
instead of its preflight output. All other independently approved inputs remain
the same. This reads only `public/vanilla-hyprarch/` catalog/manifest/signature
files, verifies native Minisign bindings, and never opens a private key. Do not
rebuild artifacts, sign again, or invent catalog sequences for diagnostics.

For a chosen output basename `vanilla-post-upgrade`, the operator again performs
one upload, one graphical command, and one report retrieval:

```bash
scp -r "$POSTUPGRADE" "$VM_ENDPOINT:Downloads/"
python3 -I -B ~/Downloads/vanilla-post-upgrade/acceptance.py post-upgrade ~/Downloads/vanilla-post-upgrade --baseline ~/Downloads/preflight-vanilla-preflight.txt
scp "$VM_ENDPOINT:Downloads/post-upgrade-vanilla-post-upgrade.txt" "$EVIDENCE/"
```

The original preflight report remains on the VM. `--baseline` accepts only a
successful report for the same target, approved source, host and user/XDG context.
It enables comparison with the actual pre-upgrade user-file hashes and service
failures. Without it, omit the option: the report explicitly warns that
cross-upgrade byte preservation is unestablished. Differences since preflight
require review for intervening user changes; never rewrite preferences to make
an assertion pass. Both phases still require unchanged user-file identities,
hashes, ownership and modes **during** their own diagnostic interval. Keyrings,
wallpaper contents and other unselected user data are not read or proven.

Post-upgrade verifies the exact target identity and packaged updater, root-owned
schema-3 provenance, signed catalog/manifest and ledger bindings, complete
transaction state and absence of retained staging. It runs the three existing
upgrade validators, preserving their graphical/user contexts. The system
authority verifies required official packages (including additions such as
`qt5-wayland`); managed deployment verifies all files in every target-managed
tree, so no second release-specific list can misplace an attribution notice or
miss a new component. Create-once remains the authority for user-state lifecycle.

Hyprland errors, a failed IPC command, an unexpected response, actual Quickshell
configuration/runtime errors and required service failures are FAIL. Quickshell
uses a locale selected from installed UTF-8 locales and verified with `locale
charmap`; stdout and stderr are always separate. A warning on stderr is not the
IPC value. Successful `pong` plus exit 0 remains necessary. Optional/environmental
warnings are recorded without converting a healthy Vanilla installation into a
failed release. No locale or unit configuration is changed.

The report finishes technical validation only. The operator separately confirms
shell/wallpaper/theme/icons and preferences visually, then uses the ordinary dock
Update action to authenticate discovery and report the installed release current.
Do not substitute a direct target-driver APPLY, command simulation or a technical
report for those two manual acceptance steps. Record their results once.

A later legitimate catalog can supersede the prepared publication evidence.
Prepare fresh authenticated public evidence in that case. Preparation currently
supports the signing root pinned in the target payload; a signing-root rotation
requires reviewed public-chain input support before using this helper. Never
reset the ledger or weaken an assertion. A retained non-null authorization is
normal and is verified as signed evidence, never mistaken for an active transaction.

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
