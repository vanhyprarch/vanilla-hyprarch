# Create-once initialization

DF2 Phase 3 implements the installer-internal create-once layer in
`install/create_once.py`. It complements, rather than extends the ownership of,
the Phase 2 managed-file engine:

- Phase 2 copies and updates only `VANILLA_MANAGED` artifacts;
- Phase 3 creates implemented `CREATE_ONCE_MACHINE` and `CREATE_ONCE_USER`
  files only when absent and invokes declared owners for backend/user state;
- package, service, privileged, optional-component, and live-session changes
  remain outside both engines.

The command consumes `deployment/ownership-v2.toml`; Python contains no second
seed or backend inventory. Its internal interface is `plan`, `initialize`, and
`validate`, with explicit source root and HOME/XDG target options. The later
release-stage `--lifecycle fresh|upgrade` option defaults to fresh. It is not a
public desktop command or the complete installer.

## Create-once rule

During fresh installation, absence authorizes creation. Existence removes
Vanilla's authority to replace.
A safe, user-owned regular file is reported as `preserve-existing` without
content comparison, merge, mode repair, or rewrite. Symlinks, wrong types,
unsafe owners, and symlinked parents fail closed.

An absent target is written to a private same-directory candidate with the
manifest mode, fsynced, and linked into place with no-clobber semantics. A
manifest artifact may declare generator arguments instead of copying its
source bytes; the initializer runs that executable source in the isolated
target environment only while the target is absent, then publishes its output
through the same no-clobber transaction. The target directory is then fsynced,
and final type, owner, mode, and bytes are
verified. Machine and override Lua files are mode `0600`; mpv and MIME seeds
are mode `0644`. The Foot file is also mode `0644`. All installed files are
regular copies independent of the source checkout.

A minimal mode-0700 transaction directory under XDG state exists only during
one create publish. Its fsynced intent names the artifact, destination,
candidate, expected digest, and mode. It does not retain user content or grant
future overwrite authority. On restart, `initialize` preserves any safe target,
discards only the precisely named engine candidate, and clears the intent.
`plan` is strictly read-only and reports `recovery-required`; `validate` fails
until recovery occurs. Abrupt termination before publish, after durable
publish, and after the published marker is deterministic and idempotent.

Fresh initialization also records every processed seed and owner-hook ID in
mode-0600 backend-owned XDG state. Upgrade mode requires this durable inventory:
an old ID remains processed even after user deletion, so its absent target is
preserved. A newly declared ID can be initialized once. Before acting on one
new ID, the backend records a pending intent. On interruption, a safe existing
target is preserved; an absent target is also conservatively marked processed
and left absent, since it may have been created and then deliberately deleted.
This record stores no user file bytes and grants no overwrite authority.
Create-once items are non-essential starter or user state. Anything required
for system correctness must use another ownership class.

## Application seeds

Foot is initialized at `$XDG_CONFIG_HOME/foot/foot.ini` only when absent. Its
create-once artifact runs the read-only `foot-seed` operation of the managed
text-size helper from the release source. The helper validates any existing
authoritative `text-size.conf` and emits `font=monospace:size=<points>` using
the same conversion as later Text Size changes. A missing preference yields the
Vanilla baseline of 12 points; an existing valid Text Size 14 yields 14 points
on the first create, including an update of a previously affected installation.
Malformed preference state fails before creating Foot. A pre-existing safe user
`foot.ini` is preserved without invoking the generator, comparing content, or
repairing its mode. Subsequent explicit Text Size changes use the helper's
existing conservative projection rules; already open Foot windows may need to
be reopened.

The provisional mpv seed is exactly:

```ini
vo=gpu-next
target-colorspace-hint=auto
target-colorspace-hint-mode=source
fullscreen=yes
```

It is created at `$XDG_CONFIG_HOME/mpv/mpv.conf` only when absent. Physical
validation on an SDR-only display remains required.

The MIME seed contains only `[Default Applications]`. It deliberately maps
Firefox to HTTP, HTTPS, and HTML; GNOME Text Editor to `text/plain`; Thunar to
directories; imv to JPEG, PNG, WebP, GIF, and SVG; and mpv to MP4, Matroska,
WebM, MP3/MPEG audio, FLAC, Ogg, and Opus. Desktop IDs are `firefox.desktop`,
`org.gnome.TextEditor.desktop`, `thunar.desktop`, `imv.desktop`, and
`mpv.desktop`. The selected types are advertised by current package or upstream
desktop metadata. The seed does not add associations or claim every format
those applications can open.

The [MIME Applications specification](https://specifications.freedesktop.org/mime-apps/latest-single/)
also recognizes user files at `$XDG_DATA_HOME/applications` and desktop-specific
`*-mimeapps.list` files. Any safe existing user file in those locations prevents
seeding; an unsafe one is a conflict. Create-once never creates a competing
default file or merges associations. Later explicit Default Apps choices use
the separate narrow user-owned preference backend.

## XDG directories and owner hooks

The target-user stage also ensures
`${XDG_DATA_HOME:-$HOME/.local/share}/flatpak/exports/share/applications`
exists before first login. It creates only missing user-owned mode-0755
directory components, preserves safe existing directories exactly, and rejects
unsafe path components. This repeatable scaffold has no create-once content
receipt: Flatpak owns the exports, including any symlinked desktop files, and
the initializer never inspects or changes their contents. Plan is read-only;
validate requires the directory. An explicit `XDG_DATA_HOME` selects that
location without creating the default path.

When `user-dirs.dirs` is absent, the initializer invokes the package-owned
`xdg-user-dirs-update` in the isolated target environment. If the file exists,
it does not invoke the tool: localized/custom paths remain unchanged. This
follows [xdg-user-dirs upstream behavior](https://www.freedesktop.org/wiki/Software/xdg-user-dirs/)
instead of hardcoding `Pictures` as an installation contract. A missing command
is reported as an unmet external hook; package provisioning will guarantee it
in the later installer phase. The package owner may also create
`user-dirs.locale`; ownership v2 records it as user-owned and Vanilla does not
write it directly.

Appearance and Power & Idle expose narrow offline `initialize-defaults` and
read-only `initialize-status` interfaces. The initializer invokes the installed
Phase 2 commands named by the ownership manifest and never writes their formats.

Appearance remains authoritative for `appearance.json`, the XDG Pictures path,
starter assets, and `appearance-assets.json`. A true fresh user receives the
reviewed Light/Dark starter set and deterministic pair-1 preference. The
version-2 receipt marks starter population complete. Later deletion,
modification, or addition is user-owned and is never undone. Existing valid
preferences are preserved; malformed owner state fails closed. Offline
initialization does not query Hyprland, Hyprpaper, or host color preference.

Power & Idle remains authoritative for `power-idle.conf` and the generated
`hypr/vanhyprarch-idle.conf`. It creates the established disabled-by-default
durable preference only when absent, renders and validates its generated
projection offline, and never contacts or restarts the live hypridle process.
Existing valid preferences are preserved. Both owner hooks use the validated
session Caffeine marker when comparing or generating the fragment, so a
same-session update preserves Caffeine ON without changing durable preferences.
Malformed runtime state or genuine fragment drift fails closed during the
read-only status check.

Text Size, Bluetooth power preference, and launcher state already have safe
lazy defaults and are intentionally not initialized. Phase 3 never changes a
Bluetooth service or device.

## Boundaries and assumptions

All target roots are explicit and XDG defaults apply when variables are absent.
Initialization runs as the target non-root user. Owner hooks require an explicit
safe `XDG_RUNTIME_DIR`; tests use disposable HOME/XDG/runtime roots. Seed
sources and target parents may not traverse symlinks.

Crash durability assumes successful regular-file and directory `fsync` plus
same-filesystem hard-link publication. The initializer does not claim a global
machine transaction. Backend owners retain their own local markers and
atomicity. No package operation, service mutation, `/etc` adoption, first-login
session mutation, optional-component lifecycle, or full-system doctor is
implemented here.
