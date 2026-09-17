# Local push-to-talk dictation

Vanilla HyprArch provides dictation as an optional component. It is not
installed by the baseline bootstrap and does not add anything to
`packages/official.txt` or `packages/aur.txt`.

## Default behavior

The managed default is local/offline, English-only transcription:

- hold F9 to run `voxtype record start`;
- release F9 to run `voxtype record stop`, transcribe, and type into the
  focused Wayland application;
- use Voxtype 1.0.1's official x86_64 AVX2 CPU binary;
- use local Whisper `small.en`, forced language `en`, without translation;
- use `wtype` as the only output driver;
- limit each recording to 120 seconds;
- use Voxtype's `default` audio-feedback theme at volume `1.0`, with
  notification and OSD output disabled.

There is no evdev hotkey, input-group membership, uinput, ydotool, clipboard
fallback, cloud API, custom recorder, custom Whisper wrapper, GPU setup, or
Quickshell indicator.

## Audited inputs and verification

`install/dictation/voxtype.conf` pins release 1.0.1, asset
`voxtype-1.0.1-linux-x86_64-avx2`, its release URL, and SHA-256
`cb3843a894ef47aca230b30bb1c45c2ef8e0d015adf2fa754d60e55123165fd0`.
The matching detached `.asc` file is downloaded separately. No production URL
uses GitHub's `latest` redirect.

`voxtype-ci-signing-key.asc` is an audited armored copy of the upstream CI
release-signing public key. It was retrieved by exact fingerprint from the
[Ubuntu keyserver](https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x9CCF7915B750CAE8B095ED1AA3FC9F33FD209279)
and cross-checked against the upstream-maintained
[AUR packaging key list](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=voxtype-bin).
Its full primary fingerprint is
`9CCF7915B750CAE8B095ED1AA3FC9F33FD209279`; its certification by the upstream
offline maintainer key is retained. The installer does not trust keyserver
lookup at installation time: it creates a dedicated temporary GPG home,
confirms that the vendored file contains exactly one primary key with that full
fingerprint, imports it, and requires a valid detached signature from that
primary key or one of its signing subkeys.

Only after independent SHA-256 and signature verification does the staged
binary become executable, solely for exact `--version` validation. A successful
candidate is atomically installed at `$HOME/.local/bin/voxtype` with mode
`0755`; it is never installed as root or under `/usr/local/bin`.

`install/dictation/models.toml` is the sole reviewed model security manifest.
It contains all ten selectable stable models with exact filenames, byte sizes,
SHA-256 digests, transport URLs, and provenance pinned to upstream revision
`5359861c739e955e79d9a303bcbc70fb988958b1`. Voxtype 1.0.1 maps `small.en` to
`ggml-small.en.bin` and downloads it from the `ggerganov/whisper.cpp` Hugging
Face repository. The tagged CLI invocation is:

```text
voxtype setup --download --model small.en --quiet --no-post-install
```

The normal final path is
`$HOME/.local/share/voxtype/models/ggml-small.en.bin` (or the corresponding
`$XDG_DATA_HOME` path). Vanilla requires exactly 487,614,201 bytes and SHA-256
`c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d`.
The metadata records both Voxtype's transport URL and a pinned upstream model
commit for provenance. A newly downloaded mismatch is deleted and the service
marker is never installed. Vanilla intentionally does not duplicate Voxtype's
atomic/resumable model downloader.

Stable 1.0.1 setup also creates its default `config.toml` when the normal XDG
config path is absent, even when a global `--config` argument is supplied.
Vanilla isolates the setup subprocess with a private temporary
`XDG_CONFIG_HOME`; the real `XDG_DATA_HOME` remains selected so the verified
model reaches its reviewed final path. The setup-generated `base.en` default
never reaches live user configuration.

The AVX2 release follows upstream's x86-64-v3 baseline. Before downloading,
the installer requires x86_64 plus `avx2`, `fma`, `bmi1`, `bmi2`, `f16c`, and
`movbe`. It performs no GPU discovery or activation.

## Install and activate

The public `vanhyprarch-dictation` manager must be deployed independently of
the optional component. Review the component first, then run its compatibility
installer as the desktop user:

```sh
./install/dictation/install
```

For development, the normal public-command convention is a symlink from
`$HOME/.local/bin/vanhyprarch-dictation` to the checked-out `bin/` command. The
resolved development symlink deliberately permits the manager to find the
adjacent checked-out resources. A production regular-file deployment instead
places those resources under
`${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/dictation/`; it never depends
on a checkout path.

If `gnupg` or `wtype` is absent, installation offers the exact official package
transaction visibly and lets pacman handle authentication. After every payload
and the user unit are verified and installed, the manager reloads the systemd
user-unit catalog, starts `vanhyprarch-voxtype.service`, and requires bounded
healthy extended status before publishing the component marker or reporting
success. It never enables the unit. A manual CLI install needs only a Hyprland
configuration reload to register the marker-controlled F9 bindings:

```sh
hyprctl reload
```

SuperSpace performs that Hyprland reload automatically after the successful
Foot operation exits. A private runtime result records the manager child's exit
status before the terminal's final Enter prompt, while a supervisor remains
alive for the real Foot lifetime. The reload decision therefore cannot mistake
Foot window-close status for manager success or failure. Failed installs do not
reload Hyprland. Apply operations change no bindings and therefore never reload
it.

On the next logout/login, Hyprland reads the component marker, registers F9,
and starts the service itself. Hyprland remains the cold-session startup owner
and the service remains disabled. Validate `systemctl --user status
vanhyprarch-voxtype.service`, hold/release F9 in a disposable text field, and
confirm audio cues, English transcription, focused-field typing, and acceptable
CPU latency. Installation downloads the real release binary and approximately
465 MiB model; repository tests never do.

The development machine passed that complete validation with Voxtype 1.0.1 and
the pinned `small.en` model. Short and longer English dictation typed correctly
through `wtype`; short transcription took approximately 1–2 seconds on the CPU
backend. The `default` feedback theme at volume `1.0` was clear during
concurrent desktop audio. After a full logout/login, Hyprland registered both
F9 bindings and automatically started exactly one service-owned daemon without
a manual service start.

Cancellation uses Voxtype's own status/cancel APIs when manually required.
This milestone deliberately adds no global Escape binding. A failed start,
capture, transcription, or `wtype` output is left to Voxtype's exit status,
logs, and audio behavior; Vanilla does not synthesize alternate text or expose
clipboard content.

## SuperSpace and management API

SuperSpace contains `Additional system components -> Local Dictation`. The
not-installed page describes the Vanilla default and launches installation in
Foot. Once installed, it reports live state and provides nested model,
language, and maximum-recording selectors. Apply, uninstall, and model download
work remains in the visible terminal operation; QML never handles package,
download, signature, config, or service mutations.

The stable public command supports:

```text
vanhyprarch-dictation status --json
vanhyprarch-dictation catalog --json
vanhyprarch-dictation install
vanhyprarch-dictation apply --model MODEL --language-mode MODE --language CODE ... --acceleration cpu --max-duration SECONDS
vanhyprarch-dictation remove-model MODEL
vanhyprarch-dictation uninstall
```

Status and catalog use schema version 1 and work with no installed component.
JSON goes only to stdout; mutations give human-readable progress and errors.
Every selection is allowlisted. Acceleration accepts only `cpu` in this
milestone: Vulkan remains a planned explicit opt-in, not a displayed or working
selection.

## Configuration and customization boundary

On first install only, after the binary and model are verified, Vanilla places
`install/dictation/config.toml` at `$XDG_CONFIG_HOME/voxtype/config.toml`. A
pre-existing file is never
overwritten. Before the first managed installation, a differing existing file
causes a fail-closed review instead of letting Vanilla publish a service marker
for an unknown model. Once the exact component marker exists, later component
updates preserve user customization. The template uses only stable 1.0.1 keys.
Vanilla owns the template, service, marker, bindings, verification metadata,
installer, and uninstall policy; Voxtype owns recording, transcription,
runtime state, model download, daemon behavior, cancellation, and `wtype`
orchestration.

English-only model families are `tiny.en`, `base.en`, `small.en`, and
`medium.en`. Multilingual families are `tiny`, `base`, `small`, `medium`,
`large-v3`, and `large-v3-turbo`. A `.en` selection forces English. A
multilingual selection permits one curated explicit language, `"auto"`, or
constrained detection among two or three distinct curated languages. The UI
catalog is English, French, German, Italian, Spanish, Portuguese, Dutch,
Polish, Chinese, Japanese, Korean, Russian, and Arabic. The manager rejects
invalid combinations rather than guessing. Maximum recording is one of 30,
60, 120, or 300 seconds.

Settings changes preserve comments and unrelated configuration. Scalar fields
use Voxtype's stable config command against a private same-filesystem candidate;
only constrained language arrays use a narrow text editor, which refuses
ambiguous layouts. The candidate is parsed independently, validated through
Voxtype, and read back before publication. The required model is downloaded
and verified while the old daemon still runs. A failed health check restores
the exact old config and previous service state. Valid unused models remain
cached; explicit removal refuses the active model.

Manual edits remain supported. Symlink, non-regular, foreign-owned, malformed,
or ambiguous config targets fail closed instead of being rewritten. Changing
current settings never changes the tracked Vanilla default template.

## Update and uninstall

There are no automatic updates. An update is a reviewed repository change with
an explicit stable version, pinned asset URL, reviewed signing fingerprint, new
expected digest, staged signature/hash/version verification, atomic binary
replacement, and a service restart only after validation. Configuration and
models remain in place, and rollback material is retained until the new daemon
is healthy. Floating URLs are forbidden.

Local Dictation uses one clean-uninstall action; there is no separate purge:

```sh
./install/dictation/uninstall
hyprctl reload
```

The reload is needed only for manual CLI uninstall. SuperSpace requests it
automatically after a successful terminal operation and never after failure.

The uninstaller requires the user manager to stop the service first and removes
nothing if that stop fails. It then removes the exact managed binary, unit, and
marker plus the complete `$XDG_CONFIG_HOME/voxtype` configuration directory and
`$XDG_DATA_HOME/voxtype` persistent-data directory. That data deletion includes
the active model, every unused model, and Voxtype-owned metadata such as
`CACHEDIR.TAG`. Recursive removal fails closed on unexpected paths, symlinks,
foreign ownership, or unsupported filesystem entries.

Stable Voxtype 1.0.1 documents those config and data roots as its persistent
user locations. With the tracked `state_file = "auto"`, transient daemon state
uses `$XDG_RUNTIME_DIR/voxtype`; it is session runtime rather than persistent
user data. The stable CPU workflow documents no additional XDG cache or state
root. The independently deployed `vanhyprarch-dictation` manager and its
immutable Vanilla resources remain available, and generic system packages such
as `gnupg` and `wtype` are not removed. A later Install therefore starts fresh:
it recreates the tracked `small.en`, English, CPU, 120-second configuration and
downloads the verified default model again. While the component remains
installed, `remove-model` still removes individual unused models and refuses
the active model.

Failed fresh-install rollback compares config, data, and runtime-directory
existence with the state captured before any setup command. A newly created
config or data tree is removed in full only after the same exact-path,
ownership, regular-entry, and no-symlink validation used by clean uninstall.
A transaction-created `$XDG_RUNTIME_DIR/voxtype` tree is removed only after the
service is stopped and its lock does not identify a live process. Pre-existing
trees are never recursively removed by this rollback path.
