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

Voxtype 1.0.1 maps `small.en` to `ggml-small.en.bin` and downloads it from the
`ggerganov/whisper.cpp` Hugging Face repository. The tagged CLI invocation is:

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

The AVX2 release follows upstream's x86-64-v3 baseline. Before downloading,
the installer requires x86_64 plus `avx2`, `fma`, `bmi1`, `bmi2`, `f16c`, and
`movbe`. It performs no GPU discovery or activation.

## Install and activate

Review the component first, then install its two official-repository package
deltas and run the installer as the desktop user:

```sh
sudo pacman -S --needed gnupg wtype
./install/dictation/install
```

The installer does not start or enable anything. In an existing graphical
session, make systemd notice the new unit, reload Hyprland so the conditional F9
bindings are registered, and start the service:

```sh
systemctl --user daemon-reload
hyprctl reload
systemctl --user start vanhyprarch-voxtype.service
```

On the next logout/login, Hyprland reads the component marker, registers F9,
and starts the service itself. The service remains disabled; the active direct
graphical session is its only startup owner. Validate `systemctl --user status
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

## Configuration and customization boundary

On first install only, Vanilla places `install/dictation/config.toml` at
`$XDG_CONFIG_HOME/voxtype/config.toml`. A pre-existing file is never
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
`large-v3`, and `large-v3-turbo`. A `.en` model must use English and cannot be
configured for Italian, automatic detection, or multiple candidates. A future
manual customization can select a multilingual model with one explicit
language such as `"it"`, `"auto"`, or constrained detection such as
`["it", "en"]`, after separately downloading and verifying that model. No
settings or model-switching UI exists today. GPU/Vulkan acceleration is also a
future explicit opt-in, never an automatic default.

## Update and uninstall

There are no automatic updates. An update is a reviewed repository change with
an explicit stable version, pinned asset URL, reviewed signing fingerprint, new
expected digest, staged signature/hash/version verification, atomic binary
replacement, and a service restart only after validation. Configuration and
models remain in place, and rollback material is retained until the new daemon
is healthy. Floating URLs are forbidden.

Normal removal is conservative:

```sh
./install/dictation/uninstall
hyprctl reload
```

The uninstaller removes only exact managed binary, unit, and marker content. It
requires the user manager to stop the service first and removes nothing if that
stop fails. It preserves Voxtype config, runtime state, and model data. A future
explicit purge may remove those user assets; ordinary uninstall never destroys
the model or customization.
