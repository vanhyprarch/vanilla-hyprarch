# Authentic v1.0.0 preparation baseline

These two GPL-2.0-only project release assets are required by
`tests/updater-preparation.py`. No fixture updater is executed against the host.
Foot/PTY investigation assets are not required by the preparation tests.

Immutable source commit: `8b450e71ff6e2f698d7d4d2d1891fc64f19d03bb`.
The previously authenticated official `vanhyprarch-v1.0.0.tar.gz` was 65,148,187
bytes, SHA-256 `de57673385f961b233bdae95731ba9e7a3bfef32ce5f44851143dafff0bcb0c9`.

| Required fixture | SHA-256 |
| --- | --- |
| `vanhyprarch-update` | `13435389ce2e8d2e89d081ddab96b6f8287ccb58213d9a2c23b3b8fc6b9fb54d` |
| `release-metadata.json` | `6b02a0b286028a56d41217f42326c136f87dd7908ea86bf6cc22efdf32e4b75c` |

`release-metadata.json` retains the exact original published `release.json`
bytes under a fixture name, so it is not mistaken for a tracked release output.
Tests materialize those bytes as `usr/share/vanhyprarch/release.json` only inside
their isolated temporary installation roots. The release packaging safeguard
continues rejecting tracked `release.json` and release archive filenames.

The updater is the original deterministic ZIP_STORED zipapp reconstructed with
the published builder and byte-verified source inputs. Metadata is the canonical
430-byte published record, reproduced from the exact source declaration and
verified published artifact fields; it matches the independently recorded asset
checksum. SHA-256 records integrity; authenticated source/release verification
established the original baseline provenance.
