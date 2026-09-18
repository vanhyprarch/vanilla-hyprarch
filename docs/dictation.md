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
fallback, cloud API, custom recorder, custom Whisper wrapper, automatic GPU
selection, upstream GPU setup, or Quickshell indicator.

## Audited inputs and verification

`install/dictation/binaries.toml` is the immutable binary security manifest.
It pins release 1.0.1 and exactly two x86_64 artifacts:

- public-default CPU: `voxtype-1.0.1-linux-x86_64-avx2`, 18,245,408 bytes,
  SHA-256 `cb3843a894ef47aca230b30bb1c45c2ef8e0d015adf2fa754d60e55123165fd0`;
- explicit opt-in Vulkan: `voxtype-1.0.1-linux-x86_64-vulkan`, 64,913,912
  bytes, SHA-256
  `c569d038057464aa60290296794bcbd79b928ee0efd038e33062a4c015558ed8`.

Each record contains its exact release URL, detached `.asc` URL, version,
architecture, and CPU feature requirements. No production URL uses GitHub's
`latest` redirect.

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

Only after independent size, SHA-256, and signature verification does a newly
downloaded candidate become executable, solely for exact `--version`
validation. It is then cached under
`$XDG_DATA_HOME/voxtype/binaries/1.0.1/` by its exact asset name. CPU and Vulkan
may coexist there. Every cached candidate is checked again for regular-file
type, current-user ownership, size, digest, and version before activation. The
active `$HOME/.local/bin/voxtype` is atomically replaced with mode `0755` and
always remains a regular file, never a symlink; nothing is installed as root or
under `/usr/local/bin`.

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

Both reviewed releases follow upstream's x86-64-v3 baseline. Before
downloading, the manager requires x86_64 plus `avx2`, `fma`, `bmi1`, `bmi2`,
`f16c`, and `movbe`. Fresh installation always activates CPU and performs no
GPU discovery or activation.

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
Foot. Once installed, it reports live state and provides model, unified
Languages, and maximum-recording selectors. Languages places true Automatic
detection and the reviewed language catalog on one page. Manual selection
supports one to three languages, has no Done step, and remains an in-memory
draft when Back or Esc leaves the page. Apply Changes commits the complete
Local Dictation draft; Refresh discards all unapplied choices and reconstructs
the draft from authoritative status. Apply, uninstall, and model download work
remains in the visible terminal operation; QML never handles package, download,
signature, config, or service mutations.

The stable public command supports:

```text
vanhyprarch-dictation status --json
vanhyprarch-dictation catalog --json
vanhyprarch-dictation install
vanhyprarch-dictation apply --model MODEL --language-mode MODE --language CODE ... --acceleration cpu|vulkan --max-duration SECONDS
vanhyprarch-dictation remove-model MODEL
vanhyprarch-dictation uninstall
```

Status and catalog use schema version 2 and work with no installed component.
JSON goes only to stdout; mutations give human-readable progress and errors.
Every selection is allowlisted. The CLI and SuperSpace accept exactly `cpu`
and `vulkan`; SuperSpace labels them `CPU` and `Vulkan GPU`. CPU is the public
default, there is no automatic acceleration mode, and selecting a row changes
only proposed state until Apply runs the complete transaction in the visible
terminal.

Acceleration identity is the exact active executable digest. Voxtype's
`backend` text, tooltip, filenames, and logs do not determine it. An unknown
digest makes the component state explicit error/incomplete.

Schema 2's `vulkan` status object has the exact hardware fields `state`,
`vendor`, `vendor_id`, `driver`, `render_node`, `render_node_accessible`,
`loader_present`, `icd_manifest_present`, `required_packages`, and
`missing_packages`. Its nested `runtime_evidence` object reports `collected`,
`pid`, `executable_matches`, `vulkan_loader_mapped`, `vendor_icd_mapped`,
`render_node_open`, `device_runtime_evidence_valid`, and
`device_runtime_evidence_rule`. Missing or inaccessible evidence remains false
or null; the manager does not guess.

Vendor discovery reads `/sys/class/drm/renderD*`, the numeric PCI vendor, and
the kernel driver symlink, then validates the matching `/dev/dri/renderD*`
character device and current-user access. Supported vendor IDs are AMD
`0x1002`, Intel `0x8086`, and NVIDIA `0x10de`. The allowlisted official package
mapping is `vulkan-icd-loader` plus respectively `vulkan-radeon`,
`vulkan-intel`, or `nvidia-utils`. Zero usable devices, unsupported hardware,
or multiple usable supported devices fail before the daemon is stopped. A
missing package is offered through the existing visible terminal and direct
`sudo pacman` argv; QML never installs packages. CUDA, ROCm, ONNX, AUR packages,
and unrelated vendor ICDs are outside this architecture.

For a running Vulkan artifact, health resolves the service `MainPID`, confirms
`/proc/PID/exe` against the managed command, and requires mappings for the
Vulkan loader and reviewed vendor ICD. AMD and Intel additionally require the
selected accessible DRM render node to remain open. NVIDIA accepts either its
reviewed GLX or EGL Vulkan ICD mapping but does not treat a DRM-render-node fd
as universal; `device_runtime_evidence_rule = "not-established"` records that
a reliable NVIDIA-specific device invariant remains future work. The common
evidence is still mandatory. All checks participate in the bounded startup
retry and a failed requirement rolls the transaction back.
Human journal messages remain useful diagnostics but are not part of this
health API or its permanent proof contract.

An acceleration change verifies the model, packages, target cached artifact,
and any config candidate while the old daemon remains running. It then retains
same-filesystem executable/config rollback material, stops the service,
atomically publishes changed files, starts the daemon, and requires bounded
health with the requested model and exact artifact digest. Failure restores
the old executable, config, and prior active/inactive service state. An
acceleration-only change leaves model, language, and duration untouched; no-op
Apply does not restart anything and acceleration changes never reload Hyprland.

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
`large-v3`, and `large-v3-turbo`. A `.en` selection forces English. For a
multilingual model, Automatic detection remains Voxtype's real unconstrained
mode; it is not simulated by selecting every reviewed language. The unified
Languages page maps one manual selection to Voxtype's scalar form and two or
three distinct selections to its constrained array form. The reviewed catalog
is English, French, German, Italian, Spanish, Portuguese, Dutch, Polish,
Chinese, Japanese, Korean, Russian, and Arabic. The manager rejects invalid
combinations rather than guessing. Maximum recording is one of 30, 60, 120,
or 300 seconds.

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

## Vulkan validation and explicit selection

The development Radeon 680M passed repeated CPU-to-Vulkan and Vulkan-to-CPU
transactions, verified-cache reuse, real F9 inference, and persistence of all
four AMD runtime signals before and after inference. SuperSpace therefore
offers Vulkan GPU as an explicit selection while CPU remains the public
default. The equivalent CLI validation path is:

```sh
vanhyprarch-dictation status --json
vanhyprarch-dictation apply --model small.en --language-mode specific --language en --acceleration vulkan --max-duration 120
vanhyprarch-dictation status --json
systemctl --user status vanhyprarch-voxtype.service
```

Inspect the resulting `acceleration`, `binary_sha256`, `service_state`, and full
`vulkan.runtime_evidence` object. On AMD, executable, loader, vendor ICD, render
node, and derived device evidence must all be true. Then test F9 in a
disposable text field. Return through the same verified transaction with:

```sh
vanhyprarch-dictation apply --model small.en --language-mode specific --language en --acceleration cpu --max-duration 120
vanhyprarch-dictation status --json
systemctl --user status vanhyprarch-voxtype.service
```

One live `small.en` F9 test on the Ryzen 7 7735HS/Radeon 680M observed correct
transcription with approximately 0.3 seconds perceived post-release latency,
compared with an earlier approximate 1–2 seconds on CPU. This is one
development-machine observation, not a general performance guarantee or a
broad GPU recommendation.

The same machine also passed real Italian and English F9 dictation with one
unchanged `small` multilingual profile constrained to `en` and `it`. A later
SuperSpace transaction activated `large-v3-turbo` with the same languages,
Vulkan, and 120-second maximum; both languages transcribed with excellent
observed accuracy, correct punctuation, competitive latency, and a responsive
desktop. The runtime reported approximately 1623.92 MB for that model. These
are development-machine observations and a personal profile choice, not
changes to the tracked `small.en`/English/CPU/120-second default or universal
performance promises.

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
the active model, every unused model, verified cached CPU and Vulkan binaries,
and Voxtype-owned metadata such as `CACHEDIR.TAG`. Recursive removal fails
closed on unexpected paths, symlinks, foreign ownership, or unsupported
filesystem entries.

Stable Voxtype 1.0.1 documents those config and data roots as its persistent
user locations. With the tracked `state_file = "auto"`, transient daemon state
uses `$XDG_RUNTIME_DIR/voxtype`; it is session runtime rather than persistent
user data. The stable CPU workflow documents no additional XDG cache or state
root. The independently deployed `vanhyprarch-dictation` manager and its
immutable Vanilla resources remain available, and generic system packages such
as `gnupg`, `wtype`, `vulkan-icd-loader`, and vendor ICDs are not removed. A
later Install therefore starts fresh: it recreates the tracked `small.en`,
English, CPU, 120-second configuration and
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
