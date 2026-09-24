# Release engineering: Phase 1 contract

Status: offline release declaration, deterministic artifact builder, and
verifier implemented. No release is published, installed release identity or
updater exists yet.

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
metadata publisher. GitHub immutable publication, discovery, installed
identity, migrations, update execution, signatures, and VM acceptance belong
to later phases. An offline verifier cannot establish that a supplied commit
SHA is trusted; it can establish that the artifact matches the supplied
strict metadata and embedded declaration.
