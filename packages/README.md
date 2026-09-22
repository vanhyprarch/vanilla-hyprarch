# Package manifest

`manifest-v1.toml` is the sole Vanilla HyprArch package declaration. It is a
human-readable intent manifest, not a lockfile or dependency solver. Pacman
remains authoritative for dependency resolution and package versions.

Every package record declares its source, role, default-install policy, direct
Vanilla owner, and reason. `default_install` is independent of `role`: for
example, `pavucontrol` and `bluez-utils` are recommended but installed by the
normal Alpha baseline, while the recommended `printing` component is not.
Here `default_install` means the future executor selects that record directly;
pacman may still install a non-default record transitively for another package.

Supported roles are `required`, `recommended`, `optional`, `build`, and
`development`. Every listed package is an intentional direct declaration even
when it happens to be pulled transitively on a particular Arch snapshot.
Transitive-only packages do not belong in this manifest.

Component records classify additive package or external-payload features.
Component membership never implies default installation; both the component
and each package carry an explicit policy. The Zig Screensaver manager is
baseline managed content, while its native player is an external optional
payload and never requires Zig on the installed system.

The manifest intentionally contains no versions. Pinned external release
artifacts keep their versions and checksums in their component-specific
metadata.

Static schema and policy validation is network-independent:

```text
python tests/df2-manifests.py
```

An optional environment check reads the existing local Arch sync databases
directly without invoking pacman or changing package state:

```text
python tests/df2-manifests.py --check-repositories
```

That optional check proves only that the current local database recognizes all
official names; it does not synchronize repositories or validate a future
snapshot.
