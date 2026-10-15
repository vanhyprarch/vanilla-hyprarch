# Upgrade original v1.0.0 to v1.0.1

**Original v1.0.0 needs one manual updater preparation before normal Update can
install v1.0.1. Do not install the preparation archive as a desktop release.**
Fresh v1.0.1 installations and systems already prepared for signed updates must
skip preparation. The accepted Proxmox VM has completed this entire procedure;
do not repeat it there. Development installations have no release identity and
are outside this procedure.

The immutable v1.0.1 tag remains at
`83bfeaa627392817c21b29ce73557a32f5ad563e`. This guide is maintained on `main`
and distributed separately; it is not inside that already published archive.

## Why the bridge is needed

The original v1.0.0 updater predates independently signed discovery, ServerPlan
fallback, and explicit target-user XDG context forwarding. Its immutable release
cannot supply those features itself. The accepted administrative tool from
`394422752564a832e2f15a004b6e3dc828e1b47b` prepares only:

- `/usr/local/bin/vanhyprarch-update`
- `/var/lib/vanhyprarch/update-bootstrap-v1.json`

It uses the existing bootstrap authority and updater lock, creates verified
root-private backups, and preserves installed v1.0.0 identity, migration level 1,
desktop files and user preferences. It does not run the release installer,
perform a release update, or modify PAM, keyrings or Secret Service providers.
The subsequent normal signed update installs genuine v1.0.1 with zero migrations.

## Downloads, authenticity and prerequisites

The preparation kit, published guide and checksums are publicly available on
ServerPlan. They are also preserved in the
[v1.0.1 GitHub Release](https://github.com/vanhyprarch/vanilla-hyprarch/releases/tag/v1.0.1),
whose anonymous access currently returns HTTP 404. The two different archives
have deliberately different purposes:

| Download | Purpose |
| --- | --- |
| [vanhyprarch-v1.0.0-updater-preparation-3944227.tar.gz](https://vanhyprarch.it/dist/v1/vanilla-hyprarch/upgrade-kits/v1.0.0-to-v1.0.1/vanhyprarch-v1.0.0-updater-preparation-3944227.tar.gz) | Complete one-time administrative kit; use this guide |
| `vanhyprarch-v1.0.1.tar.gz` and `release.json` | Genuine Stable release artifacts; normal Update acquires and authenticates these |
| [UPGRADE-FROM-v1.0.0.md](https://vanhyprarch.it/dist/v1/vanilla-hyprarch/upgrade-kits/v1.0.0-to-v1.0.1/UPGRADE-FROM-v1.0.0.md) | Published guide snapshot; this document on main may contain later clarifications |
| [SHA256SUMS](https://vanhyprarch.it/dist/v1/vanilla-hyprarch/upgrade-kits/v1.0.0-to-v1.0.1/SHA256SUMS) | Transfer checksums for the release downloads |

The preparation kit is **65,331,156 bytes**, SHA-256
`53865902c29c1e0a5098ec09c585afabb21435c174ac765d3a13627a322ed175`.
It wraps the following six original files without changing any of their bytes,
under `vanhyprarch-preparation-3944227/`:

| Original file | Bytes | SHA-256 |
| --- | ---: | --- |
| `vanhyprarch-v1.0.1-rc1.tar.gz` | 65,305,515 | `519a60b8cb792c4f9933082ffc54ff435dfee5a408a7afcbab01c58943880136` |
| `release.json` | 458 | `8e7826a0702913a39ee1d0372eebd6c95675b16211e6b998d6f2d52bf0ba63d4` |
| `VM-INSTRUCTIONS.txt` | 10,655 | `282dd393f8018010106a9534db78643759d89599223e013eed573e335683b6df` |
| `VERIFICATION.json` | 951 | `4731409bbd3bde69bb32b3b0384cf9bcef1fbedb8cf4a73db440d550c0fbfc0d` |
| `BUILD-RECORD.json` | 520 | `84b8b44fc94658a197fd99535b79f4c11dbe7f5f4d17c080b0a89b4273bc2d65` |
| `SHA256SUMS` | 429 | `f826a8743092e988742a8f2f956a261662e169adf329cc50593a4216d7ec38bd` |

The inner `rc1` name is historical **administrative input**, not a published RC
to install. Keep its filename and companion metadata unchanged. Never run its
`install.sh` or `release_update.py apply`. `VM-INSTRUCTIONS.txt` preserves the
original sequence-1 acceptance record; its old "up to date on v1.0.0" expectation
is historical. Follow this guide for the now-published Stable sequence 2.

SHA-256 establishes byte integrity, not independent publisher authentication.
Authenticate the approved source commit and these expected hashes using an
already trusted publisher record or the trusted repository workflow before
executing downloaded code as root. A checksum, guide, key or verification record
obtained only from the same compromised download source cannot authenticate that
source. This administrative kit has no separate production Minisign signature;
the signed root embedded inside it does not authenticate the kit itself.
Once prepared, the updater uses its pinned production root to authenticate
catalogs, manifests, metadata and archives independently of either transport.

Before starting, retain a usable full-system backup or VM snapshot, including
user data. An existing suitable Proxmox snapshot is sufficient; do not recreate
the VM, reinstall v1.0.0 or make redundant snapshots. Close all Update windows
and other package managers. Run the commands in Foot as the installed desktop
user, not a root shell, `sudo -E` or another user's login. Stop at any failed
check; the command blocks use subshells so errors do not close Foot.

The tool captures supported custom `XDG_CONFIG_HOME`, `XDG_DATA_HOME` and provider
discovery context before sudo. `XDG_STATE_HOME` and `XDG_CACHE_HOME` must be unset
or exactly `$HOME/.local/state` and `$HOME/.cache`. Do not unset a real custom
override to evade a refusal. Configured competing credential providers, ambiguous
context, unexpected files, active update state and mismatched provenance require
review; do not overwrite them to make preparation pass.

## 1. Confirm an original, unprepared v1.0.0

These commands only read installed state:

```bash
(
  set -eu
  printf '%s  %s\n' \
    6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c /usr/share/vanhyprarch/release.json \
    13435389ce2e8d2e89d081ddab96b6f8287ccb58213d9a2c23b3b8fc6b9fb54d /usr/local/bin/vanhyprarch-update | sha256sum --check -
  sudo python3 -B - <<'PY'
import json
from pathlib import Path
identity = json.loads(Path('/usr/share/vanhyprarch/release.json').read_bytes())
assert identity['version'] == 'v1.0.0' and identity['channel'] == 'stable'
assert identity['commit'] == '8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb'
assert identity['migration_level'] == 1
provenance = json.loads(Path('/var/lib/vanhyprarch/update-bootstrap-v1.json').read_bytes())
assert provenance == {'schema': 2, 'sha256': '13435389ce2e8d2e89d081ddab96b6f8287ccb58213d9a2c23b3b8fc6b9fb54d', 'update_protocol': 1}
assert not Path('/var/lib/vanhyprarch/update/journal.json').exists()
assert not Path('/var/lib/vanhyprarch/distribution-security-v1.json').exists()
print('PASS: original v1.0.0, migration 1, original updater/provenance')
PY
  sudo stat -c '%U:%G %a %n' /usr/local/bin/vanhyprarch-update \
    /var/lib/vanhyprarch/update-bootstrap-v1.json /usr/share/vanhyprarch/release.json
)
```

Expect both hashes `OK`, the `PASS` message, and root:root ownership with modes
755, 600 and 644 respectively. A different updater or a security ledger means
this original-baseline procedure does not apply: identify the existing state
instead of replacing it. Already prepared systems use normal Update directly.

## 2. Complete Arch maintenance and ensure official Minisign

Review any applicable [Arch upgrade notices](https://archlinux.org/news/), then:

```bash
(
  set -eu
  if pacman -Q minisign >/dev/null 2>&1; then
    sudo pacman -Syu
  else
    sudo pacman -Syu --needed minisign
  fi
  pacman -Q minisign
  /usr/bin/minisign -v
)
```

This completes a full Arch upgrade and installs official Minisign only when
absent. Original v1.0.0 already supplies Python and curl. Do not proceed after a
failed pacman transaction. See the recovery section if mirrors return HTTP 404.

## 3. Obtain and verify the complete kit

After authenticating the expected hash above, download into a new directory:

```bash
(
  set -eu
  download_dir="$HOME/Downloads/vanhyprarch-v1.0.0-bridge"
  test ! -e "$download_dir"
  test ! -L "$download_dir"
  mkdir -p "$HOME/Downloads"
  mkdir -m 0700 "$download_dir"
  cd "$download_dir"
  curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
    --output vanhyprarch-v1.0.0-updater-preparation-3944227.tar.gz \
    https://vanhyprarch.it/dist/v1/vanilla-hyprarch/upgrade-kits/v1.0.0-to-v1.0.1/vanhyprarch-v1.0.0-updater-preparation-3944227.tar.gz
  printf '%s  %s\n' \
    53865902c29c1e0a5098ec09c585afabb21435c174ac765d3a13627a322ed175 \
    vanhyprarch-v1.0.0-updater-preparation-3944227.tar.gz | sha256sum --check -
  tar -xzf vanhyprarch-v1.0.0-updater-preparation-3944227.tar.gz
  cd vanhyprarch-preparation-3944227
  sha256sum --check SHA256SUMS
)
```

Expect the outer kit and all five original checksum entries `OK`. The original
checksum file's own hash and size are recorded above. Its original five entries
cover every other original file. A browser download or existing trusted transfer
method is equally usable; preserve the exact filenames and run the same checks.

The ServerPlan kit is published and byte-identical to the approved GitHub asset;
the command above does not require GitHub access. A failed download is not a
usable kit. All hashes, approval requirements and subsequent steps remain
identical. The signed Stable assets on ServerPlan are separate and unchanged.

## 4. Stage protected administrative inputs and run read-only check

Use new `/opt` paths. If either already exists, stop and inspect it; do not
overwrite or remove unexplained state. The protected copies are hash-checked
before root extracts or executes any administrative source.

```bash
(
  set -eu
  prep_input="$HOME/Downloads/vanhyprarch-v1.0.0-bridge/vanhyprarch-preparation-3944227"
  prep_bundle=/opt/vanhyprarch-preparation-bundle
  prep_source=/opt/vanhyprarch-updater-preparation
  test ! -e "$prep_bundle"
  test ! -L "$prep_bundle"
  test ! -e "$prep_source"
  test ! -L "$prep_source"
  sudo install -d -o root -g root -m 0755 "$prep_bundle"
  sudo install -o root -g root -m 0644 "$prep_input/release.json" "$prep_bundle/release.json"
  sudo install -o root -g root -m 0644 "$prep_input/vanhyprarch-v1.0.1-rc1.tar.gz" "$prep_bundle/vanhyprarch-v1.0.1-rc1.tar.gz"
  printf '%s  %s\n' \
    8e7826a0702913a39ee1d0372eebd6c95675b16211e6b998d6f2d52bf0ba63d4 "$prep_bundle/release.json" \
    519a60b8cb792c4f9933082ffc54ff435dfee5a408a7afcbab01c58943880136 "$prep_bundle/vanhyprarch-v1.0.1-rc1.tar.gz" | sha256sum --check -
  sudo install -d -o root -g root -m 0755 "$prep_source"
  sudo tar --extract --gzip --file="$prep_bundle/vanhyprarch-v1.0.1-rc1.tar.gz" \
    --directory="$prep_source" --strip-components=1 --no-same-owner --same-permissions
  python3 -B "$prep_source/admin/prepare-updater.py" check \
    --metadata "$prep_bundle/release.json" \
    --artifact "$prep_bundle/vanhyprarch-v1.0.1-rc1.tar.gz" \
    --approved-commit 394422752564a832e2f15a004b6e3dc828e1b47b \
    --bundle-sha256 519a60b8cb792c4f9933082ffc54ff435dfee5a408a7afcbab01c58943880136
)
```

The staging commands create administrative input files, but `check` itself is
read-only. Invoke the Python tool without sudo; it captures the desktop user's
context and performs its own sudo handoff. Expected JSON: `status: "replace"`,
`release_identity: "unchanged v1.0.0"`, and exactly the two component paths listed
at the beginning of this guide. It verifies the authentic original pair,
packaged source, root signature, official verifier, lock/transaction state,
and supported XDG context. Refusal is not permission to bypass those checks.

## 5. Authorize preparation and validate it immediately

Only after a successful check, in the same user's Foot:

```bash
(
  set -eu
  python3 -B /opt/vanhyprarch-updater-preparation/admin/prepare-updater.py apply --authorize \
    --metadata /opt/vanhyprarch-preparation-bundle/release.json \
    --artifact /opt/vanhyprarch-preparation-bundle/vanhyprarch-v1.0.1-rc1.tar.gz \
    --approved-commit 394422752564a832e2f15a004b6e3dc828e1b47b \
    --bundle-sha256 519a60b8cb792c4f9933082ffc54ff435dfee5a408a7afcbab01c58943880136
  python3 -B /opt/vanhyprarch-updater-preparation/admin/prepare-updater.py check \
    --metadata /opt/vanhyprarch-preparation-bundle/release.json \
    --artifact /opt/vanhyprarch-preparation-bundle/vanhyprarch-v1.0.1-rc1.tar.gz \
    --approved-commit 394422752564a832e2f15a004b6e3dc828e1b47b \
    --bundle-sha256 519a60b8cb792c4f9933082ffc54ff435dfee5a408a7afcbab01c58943880136
  printf '%s  %s\n' \
    4512e61395435c2e2e275d0481a4d9f1fe1de003c6e551b4cc6f0757889f0fc1 /usr/local/bin/vanhyprarch-update \
    3805bb19df243d3f319d3df17466242d1f2f4360f91bc863f05b29426856888a /var/lib/vanhyprarch/update-bootstrap-v1.json \
    6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c /usr/share/vanhyprarch/release.json | sudo sha256sum --check -
  sudo stat -c '%U:%G %a %n' /usr/local/bin/vanhyprarch-update \
    /var/lib/vanhyprarch/update-bootstrap-v1.json /usr/share/vanhyprarch/release.json
)
```

Expect `prepared` from apply and repeated check, three hashes `OK`, and root:root
modes 755, 600 and 644. The verified original executable, provenance, identity
and receipt remain under `/root/vanhyprarch-updater-preparation/`, private to root.
The tool preserves v1.0.0 identity and migration level 1 throughout preparation.

**These preparation/provenance checks apply only before the first signed Update
invocation.** That invocation initializes durable rollback state and changes the
provenance initialization marker. Afterwards, preparation check/apply/restore
deliberately refuse. Do not repeat the bridge, delete its backups or substitute
the initial provenance hash for the initialized record.

## 6. Run the normal signed Vanilla update

The full Arch update in step 2 must have completed successfully. If package
databases have changed or significant time has elapsed, complete `sudo pacman
-Syu` again before proceeding. Open Vanilla's normal dock **Update** action
(Super+Space -> Update), or run this as the same normal graphical user:

```bash
/usr/local/bin/vanhyprarch-update
```

Do not prepend sudo or add a `resume` flag. The program handles sudo and the
target-user context. Review the displayed v1.0.1 summary and zero-migration plan,
then enter `y` to authorize. GitHub HTTP 404 permits authenticated ServerPlan
fallback; unavailable discovery, invalid signatures, inconsistent metadata and
rollback attempts remain errors, never "up to date".

Expected completion: `Vanilla HyprArch update complete: v1.0.1`. Installed
identity changes only after system integration, managed deployment, create-once
handling and complete validation succeed. Preserve your backup until reboot
acceptance is complete.

## 7. Confirm identity, ledger and reboot acceptance

These checks read public updater metadata only, never application secret values:

```bash
sudo python3 -B - <<'PY'
import hashlib
import json
import stat
from pathlib import Path
identity_path = Path('/usr/share/vanhyprarch/release.json')
identity_bytes = identity_path.read_bytes()
assert hashlib.sha256(identity_bytes).hexdigest() == 'c5ddeeb07dfe6ceb40144a26a490df39a344940d9e9e60b18acbf8ad3885b7d1'
identity = json.loads(identity_bytes)
assert identity['version'] == 'v1.0.1' and identity['channel'] == 'stable'
assert identity['commit'] == '83bfeaa627392817c21b29ce73557a32f5ad563e'
assert identity['migration_level'] == 1 and identity['update_protocol'] == 1
updater_path = Path('/usr/local/bin/vanhyprarch-update')
updater_sha = hashlib.sha256(updater_path.read_bytes()).hexdigest()
assert updater_sha == '4512e61395435c2e2e275d0481a4d9f1fe1de003c6e551b4cc6f0757889f0fc1'
provenance_path = Path('/var/lib/vanhyprarch/update-bootstrap-v1.json')
provenance = json.loads(provenance_path.read_bytes())
assert provenance['schema'] == 3 and provenance['sha256'] == updater_sha
assert provenance['distribution_initialized'] is True
root_sha = '58e8bc7a3094d4ea9ad2b58b80af1184feab3c530157556eeb950c78980f0f72'
assert provenance['distribution_anchor_sha256'] == root_sha
ledger = json.loads(Path('/var/lib/vanhyprarch/distribution-security-v1.json').read_bytes())
assert ledger['schema'] == 1
state = ledger['state']
assert state['root_version'] == 1 and state['root_sha256'] == root_sha
assert state['channels']['stable'] == {'sequence': 2, 'sha256': '8919821bd5abc1c5b1e4e677e2778713943a4ddd64eeeeda62bac10c389347a9'}
assert {'v1.0.0', 'v1.0.1'} <= set(state['bindings'])
assert not Path('/var/lib/vanhyprarch/update/journal.json').exists()
for path, mode in ((updater_path, 0o755), (provenance_path, 0o600), (identity_path, 0o644)):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
    assert stat.S_IMODE(info.st_mode) == mode
print('PASS: v1.0.1, migration 1, correct updater, initialized root 1 / Stable 2, no journal')
PY
```

This records acceptance against the currently published sequence 2. A later
legitimate signed catalog may have a higher sequence; do not edit the ledger to
satisfy this historical assertion. Ask for an updated verification procedure.
The ledger may retain signed authorization after a completed update until the
next successful discovery check. That is not an active transaction; the journal
and installed identity determine completion. Never clear that proof manually.

Reboot through the normal desktop power menu, log in through SDDM, and confirm
wallpaper, dock, theme and saved preferences. Run normal dock Update again:
expect `Installed: v1.0.1` and "up to date" after successful signed discovery.
The genuine v1.0.0 -> v1.0.1 VM acceptance passed all of these checks, including
recovery after mirror download failure and subsequent reboot.

## Recovery and when to stop

- **Mirror HTTP 404 / failed package downloads:** cached Arch databases may name
  versions removed from mirrors, or a mirror may be out of sync. Close the failed
  update window, retain all Vanilla state, then complete `sudo pacman -Syu`.
  If retrieval errors persist, use `sudo pacman -Syyu` to force database refresh
  together with the full upgrade. If needed, back up and edit
  `/etc/pacman.d/mirrorlist` to prefer a synchronized official mirror from
  [Arch mirror status](https://archlinux.org/mirrors/status/), then repeat
  `sudo pacman -Syyu`. Do not use `pacman -Sy` followed by selected installs:
  [Arch does not support partial upgrades](https://wiki.archlinux.org/title/System_maintenance#Partial_upgrades_are_unsupported).
  Do not resume Vanilla until the Arch upgrade finishes successfully.
- **Retained release journal:** `/var/lib/vanhyprarch/update/journal.json` means
  an authorized transaction is incomplete, not that rollback occurred. Read it
  with `sudo python3 -m json.tool /var/lib/vanhyprarch/update/journal.json` and
  inspect `sudo tail -n 60 /var/log/pacman.log`. Source, target and checkpoint
  identify the saved operation. After correcting the external package problem,
  start the normal updater again as the same user. It authenticates the saved
  authorization, re-verifies the exact staged target and resumes before new
  discovery. The message is `Resuming the exact incomplete Vanilla HyprArch
  update.` This also works after reboot; start normal Update again in the new
  graphical session. Do not run the staged target driver directly as a bypass.
- **Interrupted preparation before any signed Update:** keep the protected inputs
  and `/root/vanhyprarch-updater-preparation/`. The tool recognizes supported
  partial executable/provenance publication states. Rerun the same `check` and,
  only if recognized, the same `apply --authorize`; do not reconstruct either file
  manually. A half-written or corrupt backup requires assistance. Guarded
  updater-only restoration is an advanced operator procedure documented in
  [the preparation runbook](updater-preparation.md#interruption-and-recovery);
  it is refused after signed initialization or an actual release update begins.
- **Stop and seek assistance** for signature, hash, ownership, root-trust,
  provider/context, missing staging, corrupted journal/backup, target/source
  mismatch, unexpected migration, held lock, or unresolved pacman errors. Never
  delete journals, staging, provenance, security ledgers or receipts; never reset
  sequence floors, forge identity, disable signature checks or rerun preparation
  after signed initialization. Do not restore a snapshot casually after an
  update has begun; retain the evidence and coordinate full-system recovery.

## Optional advanced verification and preservation

The guide's hash, context, preparation-plan and immediate validation steps above
are required. Independently inspecting the original build records, comparing
archived administrative source with the trusted approved Git commit, or auditing
the signed root/catalog with the protocol tools are additional checks; they do
not replace the required checks or establish trust from an untrusted checksum.

The prepared updater embeds production root payload SHA-256
`58e8bc7a3094d4ea9ad2b58b80af1184feab3c530157556eeb950c78980f0f72`.
Root 1 is valid from `2026-10-15T07:35:10Z` to `2031-10-15T07:35:10Z`.
Stable sequence 2 expires `2027-10-15T09:35:27Z`; expired metadata cannot authorize
a new update. Do not change the clock or security state to evade expiry.
Keep the downloaded kit, protected inputs, original backup and approval hashes
as recovery material. Do not rebuild the accepted preparation payload or retag
the stable release to obtain newer documentation.

For comparison, genuine Stable downloads are 65,306,700 bytes / SHA-256
`8c349c35f1e01e57cce98d7247915742cf6c5e33dff395b7842963304b908aa5`
for `vanhyprarch-v1.0.1.tar.gz`, and 443 bytes / SHA-256
`c5ddeeb07dfe6ceb40144a26a490df39a344940d9e9e60b18acbf8ad3885b7d1`
for its `release.json`. These are not the inner preparation archive/metadata.
