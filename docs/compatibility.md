# Compatibility and upstream workarounds

This is the canonical register for tested component versions, upstream quirks,
and removable local mitigations. Package selection belongs in
[the system baseline](system-baseline.md); implementation status belongs in
[current state](current-state.md).

## Validated baseline

| Component | Validated version | Role / status |
| --- | --- | --- |
| Arch Linux | Rolling snapshot, 2026-09-10 | Standard minimal base, packaging, and systemd |
| Hyprland | 0.56.2 (`hyprland 0.56.2-3`) | Compositor, Lua configuration, input, and session ownership |
| Aquamarine | 0.15.1 (`aquamarine 0.15.1-1`) | Hyprland DRM backend; teardown-only SIGSEGV tracked upstream |
| hyprpolkitagent | 0.1.3 (`hyprpolkitagent 0.1.3-10`) | Package-owned graphical authorization service with a managed direct-session lifecycle adaptation |
| hypridle | 0.1.8 (`hypridle 0.1.8-2`) | Idle notifications and pre-sleep hooks |
| hyprlock | 0.9.6 (`hyprlock 0.9.6-3`) | Manual/password unlock and Screen saver/Display automatic-lock paths validated; portable repository baseline added but not live-migrated |
| Quickshell | 0.3.1 (`quickshell 0.3.1-1`) | Main desktop shell; no longer part of screensaver rendering |
| Qt | 6.11.2 (`qt6-base 6.11.2-3`) | Main Quickshell runtime |
| `vanhyprarch-zig-player` | optional v0.1.1, Linux x86_64 | Native layer-shell renderer; canonical member hashes and required Wayland/glibc libraries are validated before capability publication. Idle continuity and input routing validated; physical two-monitor testing pending. |
| Foot | 1.28.0 (`foot 1.28.0-2`) | Default terminal for interactive Install/Remove/Update operations; a shared helper retains final output until Enter without `--hold` |
| pacman | 7.1.0 (`pacman 7.1.0.r9.g54d9411-2`) | Local installed-package catalog and authoritative removal transaction semantics |
| yay | 13.0.1 (`yay 13.0.1-1`) | Interactive repository/AUR installation, removal, and full-system update wrapper |
| Flatpak | 1.18.2 (`flatpak 1:1.18.2-1`) | Locally validated official package for interactive app/runtime updates; required but not version-pinned |
| hyprpaper | 0.8.4 (`hyprpaper 0.8.4-8`) | Required Appearance renderer; new Hyprwire `wallpaper`/`listactive` contract validated |
| hyprgraphics | 0.5.1 (`hyprgraphics 0.5.1-4`) | Hyprpaper image decoding; PNG, JPEG, BMP, WebP, SVG, and JXL linked, without HEIF/AVIF |
| xdg-desktop-portal | 1.22.1 (`xdg-desktop-portal 1.22.1-2`) | Brokers the standard Settings read interface |
| xdg-desktop-portal-gtk | 1.15.3 (`xdg-desktop-portal-gtk 1.15.3-1`) | Active Settings provider mapping GNOME interface color scheme to the standard portal value |
| xdg-desktop-portal-hyprland | 1.4.1 (`xdg-desktop-portal-hyprland 1.4.1-2`) | Hyprland portal interfaces; does not provide Settings on this version |
| Papirus | `papirus-icon-theme 20260801-1` | Project icon theme |
| grim | 1.5.0 (`grim 1.5.0-2`) | Installed screenshot encoder; deterministic tests and the real 10-bit workflow pass |
| slurp | 1.5.0 (`slurp 1.5.0-2`) | Installed unrestricted region picker with predefined smart rectangles; real pointer selection passes |
| wl-clipboard | 2.3.0 (`wl-clipboard 1:2.3.0-1`) | Installed clipboard publisher; deterministic MIME/byte-stream tests and real paste acceptance pass |
| Voxtype | 1.0.1 upstream AVX2 and Vulkan binaries | Optional local dictation; CPU remains the public default. Explicit Vulkan selection, signed-artifact switching, and vendor-aware runtime proof are implemented. Radeon 680M inference has been validated; its observed latency is not a general performance guarantee. |

This is a tested rolling-release snapshot, not a dependency lock or a claim
that other versions are incompatible. External release artifacts are pinned
separately when required.

## Quickshell IPC handler reload boundary

**Affected component:** Quickshell 0.3.1

Power & Idle uses Quickshell's native `IpcHandler` only as a state-free
invalidation transport. The `vanhyprarch.idle` handler is a direct `ShellRoot`
child and calls the already-eager global `IdleController`; it is not placed in a
lazy popup, singleton, or screen delegate. A native named-config fixture requires
`qs ipc show` to expose `refresh()` before any Power & Idle interaction, invokes
it, and repeats both checks after a same-process reload.

Quickshell 0.3.1 registers handlers through its post-reload hook. Headless
offscreen reload tests must set the installed `QS_NO_RELOAD_POPUP` switch because
there is no `PanelWindow` backend for Quickshell's internal reload popup;
otherwise the test instance remains at `Not ready to accept queries yet` even
though the new handler registry was created. This switch is test-only and is not
used by the live shell.

Retest eager target registration, invocation, and same-process reload after a
Quickshell upgrade or any material `IpcHandler` lifecycle change. The backend's
notification remains bounded and nonfatal, and startup plus the 30-second
authoritative refresh remain recovery paths if IPC is unavailable.

## Hyprland Lua import boundary

**Affected component:** Hyprland 0.56.2

Hyprland's official Lua configuration documentation supports modules by
absolute path. The 0.56.2 loader intentionally recognizes leading `/` paths,
accepts an explicit `.lua` suffix, registers successfully resolved required
files in its tracked configuration paths, and clears user `package.loaded`
entries while rebuilding that tracking on reload. The same implementation is
present in the 0.56.0 and 0.56.1 tags.

The repository entrypoint therefore uses four explicit ordered absolute
`require()` calls. It does not use `dofile()`: standard `dofile()` executes an
absolute file but bypasses Hyprland's require searcher and its configuration
path tracking. Both mechanisms execute separate Lua chunks with chunk-local
locals and a shared global environment, so managed files avoid publishing
project globals. `Hyprland --verify-config` follows the same imports; missing
files or configuration errors make verification fail.

Retest the absolute-path resolver, required-file tracking, error behavior, and
`--verify-config` after a Hyprland Lua-loader upgrade before changing the
import mechanism.

Hyprland 0.56.2 `--verify-config` evaluates the Lua configuration rather than
only parsing it. A read-only baseline verification on the development machine
therefore invoked the registered `config.reloaded` callback and requested a
keyboard-sync service reload, even though it did not mutate configuration or
monitor state. Monitor Safe Apply prospective verification consequently stages
the complete import tree and runs the installed verifier inside an unshared
Bubblewrap environment with no live user bus and no writable live config. Exit
status is authoritative and the subprocess is bounded to five seconds. Retest
both successful validation and callback containment after a Hyprland verifier
or Bubblewrap upgrade.

## Hyprland monitor runtime transaction boundary

**Affected components:** Hyprland 0.56.2 (`hyprland 0.56.2-3`) and Python's
standard JSON/decimal implementation

Hyprland's current Lua runtime configuration interface accepts
`hl.monitor({...})` through `hyprctl --instance <signature> eval`. Source for
0.56.2 shows that it copies an existing rule on an exact connector-name match,
overlays supplied fields, and schedules monitor rule application. The B1
backend therefore addresses one exact connector and supplies only the owned
mode and scale fields. It does not use legacy `keyword monitor` syntax or the
runtime `desc:` selector; [upstream issue 15961](https://github.com/hyprwm/Hyprland/issues/15961)
records that description-addressed runtime rules can report success without
applying on this version.

If no exact `rule.m_name == output` rule exists, 0.56.2 begins from monitor-rule
defaults before applying supplied fields. B1 consequently rejects missing,
catch-all-only, description-addressed, duplicate, or override-superseded
machine profiles before it writes a journal state that permits `eval`. Sending
every protected field is intentionally not used as a substitute for this
invariant.

The eval command's `ok` response proves parser/command acceptance only. Mode
selection may choose a nearby/fallback mode, scale is normalized by compositor
rules, 10-bit requests may fall back, output commits may fail, and multiple
outputs are refreshed sequentially rather than as one atomic DRM transaction.
The mitigation is fresh `hyprctl --instance <signature> -j monitors all`
readback after every candidate and rollback operation. B1 compares the chosen
advertised resolution/refresh tuple, scale, physical identity, full output set,
and protected position/transform/enablement/DPMS/mirror/format/observable
color-management/VRR/reserved-area state. Hyprland 0.56.2 reports the physical
serial as `serial` (not `serialNumber`) and exposes color state directly as
`colorManagementPreset` plus four SDR numeric fields; the backend consumes
those exact `CHyprCtl::getMonitorData()` keys. ICC profile state is not present
in this response and is not claimed as directly validated. Required consumed
fields are type-checked while unrelated new upstream keys are ignored. It
stores refresh as integer millihertz and permits a
5-millihertz active readback tolerance only when the requested two-decimal mode
is uniquely nearest; ties between adjacent advertised entries fail closed.
Catalogue comparison deduplicates and sorts complete resolution/refresh tuples,
because upstream JSON list order and duplicate multiplicity carry no selectable
identity. Scale preflight requires the 1/120 grid and readback within one
millionth.

A full configuration reload discards runtime monitor-rule projection and
reapplies parsed persistent configuration. It is intentionally not normal B1
rollback. Primary rollback issues one connector-specific `hl.monitor()` for
the snapshotted mode and scale and then verifies the complete topology. An
external reload therefore invalidates the candidate instead of authorizing it
to be re-applied. The helper never follows a replaced compositor process or a
connector that now has different available physical identity data.

This milestone verified command construction and behavior only with injected
fixtures; it made no live monitor mutation. Before Phase B2 production
enablement, repeat the controlled runtime experiments against the installed
Hyprland version. After every Hyprland upgrade, retest Lua monitor eval,
connector matching, advertised and active refresh representation, scale
normalization, inactive output JSON, color/readback fields, config reload,
hotplug, partial multi-output failure, and issue 15961. Remove the exact-name
restriction only when upstream behavior and a controlled test justify it.

## System keyboard synchronization boundary

**Affected components:** Hyprland 0.56.2, systemd/systemd-localed 261.3,
libxkbcommon 1.13.2, and xkeyboard-config 2.48

Hyprland's legacy `hyprctl keyword input:kb_*` path rejects the non-legacy Lua
parser. The supported projection is one shell-free `hyprctl eval` call whose
Lua source invokes `hl.config()` with layout, model, variant, and options.
Controlled Runtime Experiment 1 proved that this operation is runtime-only,
preserves the positional empty variant in `it,us` / `,`, and leaves a non-zero
endpoint active-layout index unchanged when the identical tuple is submitted.
The helper still suppresses identical evals to avoid unnecessary refreshes and
protect behavior across future versions.

A full configuration reload replaces runtime `hl.config()` values with parsed
file state, so the managed `config.reloaded` hook requests one forced
reconciliation. Runtime `hl.config()` property refresh does not itself emit
`config.reloaded`. Hyprland can fall back to US after an invalid XKB tuple;
every requested and rollback tuple is therefore checked first with
`xkbcli compile-keymap --test --rules evdev`.

systemd-localed 261.3 exposes the graphical tuple as `X11Layout`, `X11Model`,
`X11Variant`, and `X11Options` on `org.freedesktop.locale1` and emits standard
`PropertiesChanged` notifications. Its console keymap is separate when
`localectl --no-convert set-keymap` is used. Default `set-keymap` and
`set-x11-keymap` conversion semantics can update the other domain; explicit
`--no-convert` prevents that conversion. The helper ignores locale/vconsole
signals and always re-reads the complete X11 tuple for a relevant report.

A controlled live prototype exposed that a `GDBusProxy` created for the
well-known locale1 name could observe owner changes yet miss a later
`PropertiesChanged` after systemd-localed repeatedly exited idle and returned
under new unique owners. The proxy is therefore not the event authority. One
long-lived system-bus `GDBusConnection` now owns a direct signal subscription,
the name watcher, and explicit `Properties.GetAll` calls. Signals are accepted
only from the currently watched unique owner. Owner transitions around a read
discard that tuple and coalesce a fresh reconciliation for the newest owner;
idle disappearance alone leaves Hyprland unchanged and schedules no retry.

PyGObject 3.56.3 warns that `GLib.unix_signal_add()` is deprecated. The SIGHUP
reload path uses the supported `GLibUnix.signal_add()` API provided by GLib
2.88.3 instead; this changes registration only, not forced-reconcile behavior.

Hyprland 0.56.2's `CCompositor::startCompositor()` schedules
`systemctl --user import-environment` and D-Bus activation-environment
publication before it emits the ready event, but the executor spawn is
asynchronous. The user manager happened to contain the current compositor
signature in the audited session; that does not guarantee completion before a
`hyprland.start` callback starts a user service. Vanilla's startup callback
therefore runs the managed helper's `session-start` action. It imports only
`HYPRLAND_INSTANCE_SIGNATURE`, `WAYLAND_DISPLAY`, and `DISPLAY`, waits for that
exact-argv systemctl call, and restarts the keyboard service only on success.
The daemon then constructs its one-instance socket path from its own fresh
`XDG_RUNTIME_DIR` and signature environment. Config reload neither republishes
the environment nor restarts the daemon.

systemd 261.3 documents client-side named-variable import through `systemctl
--user import-environment`. It also explicitly supports environment expansion
in `ExecReload` and supplies `$MAINPID` for the service main process; the
shell-free `/usr/bin/kill -HUP $MAINPID` form remains the smallest exact signal
delivery for this service.

Final live validation removed the private machine fallback. A fresh Ly login
exposed Hyprland's built-in `us` tuple, then one preflighted transaction
projected localed's `it / pc105 / "" / terminate:ctrl_alt_bksp` state and
verified exact readback. Completion was observed approximately 123 ms after the
new IPC socket became available, with immediate human Italian input passing;
this is compatibility evidence, not a timing guarantee.

Retest the Lua eval API, reload event, identical-tuple active-index behavior,
global hotplug inheritance, activation-environment ordering, invalid-keymap
behavior, and command-socket layout after a Hyprland upgrade. Retest locale1
properties, direct signal sender identity, repeated owner reincarnation, D-Bus
activation, named environment import, `ExecReload`/`$MAINPID`, and
`--no-convert` semantics after a systemd major upgrade. Retest Unix-signal
registration after a PyGObject/GLib major upgrade and command-line validation
after libxkbcommon or xkeyboard-config changes.

## Hyprpolkitagent direct-session lifecycle boundary

**Affected components:** hyprpolkitagent 0.1.3-10 and systemd 261.3

The official package owns
`/usr/lib/systemd/user/hyprpolkitagent.service`. Its content matches the
upstream
[service template](https://github.com/hyprwm/hyprpolkitagent/blob/main/assets/hyprpolkitagent-service.in):
`PartOf=` and `After=` reference
`graphical-session.target`, `ConditionEnvironment=WAYLAND_DISPLAY`, and the
service uses `Restart=on-failure`. Vanilla neither edits nor copies that unit.
The upstream target integration was
[added for sessions that start Hyprland as a systemd service](https://github.com/hyprwm/hyprpolkitagent/pull/3);
Vanilla instead uses direct
`Ly -> start-hyprland -> Hyprland`, where `graphical-session.target` remains
inactive.

During the 2026-09-20 cold logout, the old agent first lost Wayland and exited
255. The package restart then repeatedly reached Qt without a display, aborted
with SIGABRT, and reached `start-limit-hit` after six scheduled restarts. The
new session's direct start was rejected by that retained failure state. This
closely matches upstream
[hyprpolkitagent issue #16](https://github.com/hyprwm/hyprpolkitagent/issues/16),
which records logout coredumps, six restart attempts, start-limit failure, and
failure to return on the next login. That report confirms the symptom, while
Vanilla's journal and inactive-target audit establish the local lifecycle
cause.

The local adaptation is deliberately smaller than a replacement unit.
`vanhyprarch-polkit-session` owns ordered direct-session start and graceful
stop. A managed package drop-in adds only a compositor-socket `ExecCondition`
and a one-second restart interval. Active-session failures retain the package's
`Restart=on-failure`; compositor-absent restart attempts become cleanly skipped,
and each fresh session clears old rate-limit state before one restart.

The first logout after that adaptation proved that the old agent stopped before
Wayland teardown and did not restart, but the following login exposed a second,
narrow systemd 261.3 boundary. A named `systemctl --user reset-failed
hyprpolkitagent.service` returns “Unit ... not loaded” after the inactive unit
has been garbage-collected, even though there is no failure state to clear. The
short-lived helper treated that as fatal and never requested the restart. A
same-session execution reproduced the failure after both compositor sockets
were already valid; `systemctl --user is-failed --quiet` returned the documented
non-failed status for the unloaded installed unit. Startup now resets only an
actually failed unit, then requests and verifies one restart.

Hyprland 0.56.2 does not make socket micro-timing part of Vanilla's product
contract. In the failed login, the Wayland socket was created at
13:19:12.919142, the command socket at 13:19:12.924143, the keyboard startup
service at 13:19:13.319, and `hyprland.lock` only at 13:19:13.433735. Thus the
observed failure was not a socket-readiness race, while the later lock confirms
that not every instance artifact exists when startup children can run. The
PolicyKit helper uses inotify on only the inherited session's runtime,
`hypr/$HYPRLAND_INSTANCE_SIGNATURE`, and exact socket paths. Missing sockets
therefore cause event-driven bounded waiting, not a fixed delay or scan for
another instance. Directory device/inode identity and socket ownership/type are
rechecked before environment import and service restart. A ten-second timer is
only a fail-safe bound.

The direct helper remains the lifecycle owner instead of a user-manager
oneshot. It inherits the new compositor identity directly; a oneshot would
start from the possibly stale user-manager environment that this operation is
responsible for replacing. Startup imports only `HYPRLAND_INSTANCE_SIGNATURE`,
`WAYLAND_DISPLAY`, and `DISPLAY`, then conditionally resets failure state and
restarts the official service. Each stage writes a concise
`vanhyprarch-polkit-session` journal record through the installed system logger,
so a later login failure can be assigned to readiness, import, failure reset,
restart, or final service verification without a wrapper unit.

Repeated controlled cold logins validated the final path: the old agent
stopped before Wayland loss, no conditioned restart loop occurred, an inactive
non-failed unit skipped `reset-failed`, and exactly one official agent started
with the new compositor environment. Graphical authorization then completed
successfully.

Retest named reset behavior and unit garbage collection after a systemd major
update. Retest startup-event/socket ordering after a Hyprland upgrade. Retest
after a hyprpolkitagent package or service-template update, and remove or
reduce the drop-in if upstream makes compositor-loss restart safe. Reconsider
the direct ownership helper if Vanilla adopts an active graphical session
target; do not carry both lifecycle owners.

## Aquamarine DRM teardown SIGSEGV

**Affected components:** Hyprland 0.56.2-3 with Aquamarine 0.15.0 and 0.15.1-1

Repeated local Hyprland coredumps from 2026-09-09 through 2026-09-20 occurred only
while Ly sessions were closing. Every dump has SIGSEGV at
`CDRMBackend::flushAsyncCommitEvents()`, followed by `cancelAsyncOutput()`,
`SDRMConnector::disconnect()`, and the DRM backend destructor. The logout still
completed, and no active-session occurrence has been observed.

The stack and timing match open upstream
[Aquamarine issue #383](https://github.com/hyprwm/aquamarine/issues/383), which
reports the same teardown stack on Hyprland exit beginning with Aquamarine
0.15.0. Related [issue #386](https://github.com/hyprwm/aquamarine/issues/386)
tracks a different connector-disconnect failure introduced by the same async
commit change and explicitly identifies #383 as the related exit-crash path.

Vanilla carries no workaround and does not alter logout to hide the coredump.
Treat this as an upstream teardown-only compatibility defect unless a future
observation shows active-session impact or failed logout. Retest the controlled
logout after the next relevant Aquamarine or Hyprland upgrade and retire this
record when the upstream path no longer crashes.

## Hyprlock portable baseline validation boundary

**Affected component:** hyprlock 0.9.6

The portable baseline uses only `general.hide_cursor`, a monitor-neutral solid
background, and one monitor-neutral input field. Every selected category and
value is registered by the exact 0.9.6
[configuration schema](https://github.com/hyprwm/hyprlock/blob/v0.9.6/src/config/ConfigManager.cpp).
Colors and layout values use forms also present in the installed package
example. Static tests reject connector names, home paths, image paths, commands,
and keyboard-layout presentation.

Hyprlock 0.9.6 has no verification-only command. An invalid-display invocation
exits at its compositor connection assertion before parsing configuration, so
it cannot provide a safe parser test. The repository-only milestone therefore
does not launch hyprlock against the live compositor. Validate the managed file
with a non-visible isolated compositor or an upstream parser-only facility
before live deployment, and retest the schema after a hyprlock upgrade.

## Appearance host-preference boundary

**Affected components:** xdg-desktop-portal 1.22.1,
xdg-desktop-portal-gtk 1.15.3, GLib 2.88.3, Firefox 156.0, GTK 3.24.52,
GTK 4.22.5, and Qt 6.11.2

The direct Hyprland session selects `hyprland;gtk` portal backends. The
Hyprland backend's declared interfaces do not include Settings, so the active
GTK backend owns `org.freedesktop.impl.portal.Settings`. Its exact 1.15.3
source reads the writable `org.gnome.desktop.interface color-scheme` enum,
maps it directly to `org.freedesktop.appearance/color-scheme`, subscribes to
GSettings changes, and emits the standardized `SettingChanged` signal without
a portal restart. Live read-only inspection returned `prefer-dark` and portal
value 1. A real opposite-value write was deliberately not performed during the
isolated milestone.

Firefox 156 contains both the standardized appearance namespace and its XDG
Settings preference path; no current profile override was found by the narrow
audit. Normal System theme and web `prefers-color-scheme` behavior can consume
the portal change, while explicit Firefox themes or site choices remain
authoritative. A read-only GTK 4 probe reported interface color scheme 2
(Dark), matching the live portal, while retaining the `Adwaita-dark` theme.
A GTK 3 probe instead reported application-prefer-dark false and the explicit
`Adwaita-dark` theme; such legacy applications may not change with the standard
preference because Appearance deliberately does not replace `gtk-theme`. Qt
6.11.2 provides the XDG desktop portal platform-theme plugin with the standard
appearance namespace and `QStyleHints::colorScheme`. However, a read-only
ordinary Wayland Qt 6.11.2 probe with no `QT_QPA_PLATFORMTHEME` override
reported `Qt::ColorScheme::Unknown` (0), so automatic consumption by ordinary
Qt applications is not proven on this session. Vanilla does not force-load a
platform theme or set a Qt style override; sandboxed applications or
applications that select the portal theme may behave differently.

Retest provider selection, writable schema, portal readback and signal,
Firefox System-theme behavior, representative GTK 4 and Qt applications, and
the documented GTK 3 limitation after portal, GLib, Firefox, GTK, or Qt
upgrades. Do not compensate with per-application configuration.

## Hyprpaper 0.8.4 IPC and image boundary

**Affected components:** hyprpaper 0.8.4, Hyprland/hyprctl 0.56.2, and
hyprgraphics 0.5.1

Installed `hyprctl hyprpaper --help` exposes only `wallpaper`; Hyprland 0.56.2
source proves that monitor, path, and optional fit mode are one comma-delimited
argument. `listactive` works; `listloaded` is invalid on this new protocol.
Tagged Hyprpaper 0.8.4 source proves that explicit monitor settings are matched
before an empty or `*` wildcard and that updating a wildcard removes only the
prior wildcard, not explicit targets. Current upstream documentation likewise
defines the empty monitor as a fallback only for outputs that have never had a
specific target.

A controlled live test adopted the existing renderer process, whose legacy
config had assigned DP-1 explicitly. The deployed attempt supplied separate
argv fields, which this `hyprctl` joins with spaces and cannot parse as the
required comma form. Independently, a correctly encoded empty-monitor request
would remain a fallback and could not replace that explicit target. One exact
request using `DP-1,<canonical-path>,cover` immediately changed `listactive`
without a renderer restart. Appearance therefore reads
active output names from `hyprctl -j monitors`, sends the fallback plus an
explicit comma-delimited request for every current output, checks for
monitor-set races, and verifies every output through `listactive`. It never
uses the older preload/reload workflow or a connector literal.
Because the installed IPC has no escaping for its comma delimiter, Appearance
rejects a selected path containing a comma instead of misaddressing the
renderer. Spaces, Unicode, and shell metacharacters remain literal argv data.

Hyprpaper 0.8.4 replaces an explicit output target by rebuilding that target's
layer surface. During a real Light/Dark switch, this briefly exposed
Hyprland 0.56.2's native `wall2.png` background: the packaged anime scene was
visible before the new Hyprpaper surface. A controlled runtime test setting
only `misc.disable_hyprland_logo = true` removed that foreign frame across four
alternating switches, with no black or blank frame and no renderer restart.
The managed Hyprland core therefore disables the native logo/default
background. `force_default_wallpaper` remains unchanged, splash-text policy is
unrelated, and Appearance does not add preload, fade, overlay, or request-order
workarounds. This is a compositor-background ownership boundary, not a general
claim that Hyprpaper transitions are defective.

The installed binary links hyprgraphics plus libmagic, PNG, JPEG, WebP, SVG,
and JPEG XL libraries. Tagged hyprgraphics source additionally provides BMP.
HEIF is not linked, so AVIF is not accepted even though generic upstream source
can compile that optional decoder. Appearance mirrors this content-based
contract and treats actual renderer failure as authoritative.

Retest request names, argument form, wildcard semantics, readback, native
background suppression, and compiled decoder libraries after Hyprpaper,
Hyprland, or hyprgraphics upgrades. Remove or update the local MIME capability
table in the same reviewed change.

## Voxtype 1.0.1 integration boundary

**Affected components:** Voxtype 1.0.1, Hyprland 0.56.2, systemd user services,
PipeWire, and `wtype`

Tagged Voxtype 1.0.1 supports `record start`, `record stop`, `-q daemon`, the
`small.en` model name, and `setup --download --model small.en --quiet
--no-post-install`. Its `run_setup()` always creates the XDG Voxtype directories
and writes `Config::default_path()` when absent; a global `--config` path does
not redirect that write. Vanilla therefore runs every model setup/download with
a private temporary `XDG_CONFIG_HOME` while retaining the intended
`XDG_DATA_HOME`. Any upstream-generated default config is discarded with that
staging directory, and only Vanilla's tracked template is published afterward
on a fresh install. The separate systemd setup action is never invoked. Retest
this isolation after a Voxtype upgrade and remove it only if setup gains a
documented side-effect-free download path or honors an explicit config target
for every write.

The upstream service assumes graphical-session enablement and may include an
optional ydotool dependency. That does not match the direct
`Ly -> start-hyprland -> Hyprland` session, so Vanilla owns a smaller unit with
only PipeWire ordering, a fixed `%h/.local/bin/voxtype -q daemon` command, and
restart-on-failure. It has no `[Install]` section. Hyprland conditionally starts
it from the exact component marker.

The built-in hotkey remains disabled. This avoids Voxtype's evdev/input-group
boundary, including reported failures when group membership changes; F9 press
and release are compositor bindings. Output disables modifier-key polling and
clipboard fallback and selects only `wtype`, so no evdev, uinput, or ydotool
access is required. Retest the tagged schema, CLI, service assumptions, model
mapping/hash, and press/release Lua API before a Voxtype or Hyprland upgrade.
Live testing confirmed short and longer microphone capture, approximately 1–2
second short-transcription latency, focused-application `wtype` injection,
audible `default` feedback at volume `1.0`, automatic F9 registration and
service startup after logout/login, and exactly one running daemon.

Stable 1.0.1 also accepts a string language code, `"auto"`, or a constrained
array of language codes. Vanilla exposes only 13 reviewed language codes and
ten manifest-pinned models. Its candidate-config path uses `voxtype config set`
for supported scalar fields and a narrow editor only for the language array,
then requires TOML parsing, upstream schema validation, resolved-value
readback, service activation, and daemon status before committing. Retest that
complete editing and status contract on any Voxtype upgrade.

The manager identifies CPU and Vulkan only by exact reviewed binary digest. It
can transactionally switch the signed artifacts through the CLI or SuperSpace,
validate official loader/vendor prerequisites from sysfs facts, and restore
the prior binary, config, and service state on failure. CPU remains the default
and there is no automatic acceleration selection.

Stable Voxtype 1.0.1 can report `backend = "unknown"` in extended status even
while its managed AVX2 build is running successfully with `use gpu = 0`.
Vanilla therefore does not infer acceleration identity from `backend` or
tooltip text. Apply health requires the user service to become active, valid
extended status with the requested model and a non-error runtime state, and an
unchanged pinned managed-binary digest. Retest this status behavior on a
Voxtype upgrade; Vulkan identity likewise comes from its verified artifact,
not this advisory field.

Stable 1.0.1 exposes no machine-readable backend proof, so Vulkan health
resolves systemd's `MainPID` and requires the managed executable, Vulkan
loader, and reviewed vendor ICD to remain mapped. Live Radeon 680M validation
also established the selected DRM render node as a stable required invariant
for AMD; Intel uses the same Mesa/DRM rule. The
[NVIDIA Linux driver component documentation](https://download.nvidia.com/XFree86/Linux-x86_64/580.126.09/README/installedcomponents.html)
identifies `libGLX_nvidia.so.0` or `libEGL_nvidia.so.0` as its
Vulkan ICD and `/dev/nvidia*` device handling, so absence of a DRM-render-node
fd alone does not reject NVIDIA until a reliable NVIDIA-specific device proof
is reviewed. Retest this contract on Voxtype, Vulkan loader, or driver upgrades.

## Foot completion boundary for component transactions

**Affected components:** Foot 1.28.0 and Quickshell 0.3.1

A live Local Dictation install completed successfully and published a valid
marker, but the current-session F9 bindings remained absent until a manual
`hyprctl reload`. The original deterministic test called the controller's
completion helper directly and counted a reload-intent signal without running
either real `Process`. The live path also used Foot's process exit as if it were
the manager child's transaction result; closing a completed terminal window is
not that contract.

Local Dictation operations now use the shared terminal helper's supervised
mode. The in-terminal helper records the manager child's normalized status in a
private runtime directory before its final Enter prompt, while the supervisor
waits for the real Foot process. Only that result can trigger the tracked
`/usr/bin/hyprctl reload`; reload completion precedes status refresh, and a
missing result fails closed. Other SuperSpace package operations retain their
existing terminal behavior. Retest this boundary after a Foot or Quickshell
process-lifecycle upgrade, or before replacing the shared terminal helper.

## Screenshot capture validation boundary

**Affected components:** Hyprland 0.56.2, grim 1.5.0, slurp 1.5.0, and
wl-clipboard 2.3.0

The screenshot helper has deterministic coverage for Hyprland JSON parsing,
logical monitor geometry at scale 1.25, rotated and flipped transforms, visible
client filtering, duplicate removal, unrestricted `slurp` input, PNG capture
arguments, collision-safe publication, runtime locking, cancellation, and the
exact `wl-copy --type image/png` clipboard operation. These tests use mocks and
an isolated forked clipboard-provider stand-in; they do not invoke a real
graphical picker.

A real capture with wl-clipboard 2.3.0 showed that its default `wl-copy`
launcher forks a background provider. When the helper captured launcher stderr
with `subprocess.PIPE`, that provider inherited the pipe and delayed EOF, so
Python waited and retained the screenshot lock for the clipboard selection's
lifetime. Clipboard publication now uses an anonymous temporary file as the
stderr sink: immediate nonzero launcher errors remain readable, while the
helper can return without changing `wl-copy`'s normal repeated-paste daemon
behavior. The regression test requires the helper lock to become reusable
while the isolated provider is still alive. Retest this boundary after a
wl-clipboard upgrade; remove the mitigation only if the launcher no longer
daemonizes or guarantees that descendants close captured descriptors.

The development output currently uses `3840x2160` at scale 1.25 with the
10-bit `XRGB2101010` format and the `wide` color-management preset.
All three screenshot packages are installed, and the manifest also represents
them as clean-install requirements. The real name-based workflow passed after a
full logout/login, including smart selection, saved PNG color and resolution,
`image/png` clipboard publication, and application paste acceptance. Physical
multi-output behavior remains pending. Apart from the bounded `wl-copy`
descriptor mitigation above, the helper does not freeze the screen or change
cursor, scale, bit depth, or color-management settings. Retest these paths after
Hyprland, grim, slurp, or wl-clipboard upgrades.

The user-local session PATH passed a full logout/login validation: new Foot and
Quickshell processes saw `$HOME/.local/bin` first, the name-based screenshot
command resolved, the complete screenshot workflow passed, and hypridle
continued to resolve its project commands. The former hypridle startup wrapper
and Quickshell-local PATH compensation are therefore removed. Retest direct
hypridle ownership, one-daemon state, and a Power & Idle apply after deploying
this cleanup; the backend's captured-daemon-PATH transaction is not part of the
removed workaround.

## Hyprland idle-start ownership boundary

**Affected component:** Hyprland 0.56.2

Current `hl.exec_cmd` execution ultimately passes command strings through
`/bin/sh -c`. Most autostart commands do not require special handling, but the
Power & Idle session initializer deliberately requires its immediate parent to
be Hyprland before publishing a reconciled fragment and becoming hypridle. Its
startup string therefore uses
`exec $HOME/.local/bin/vanhyprarch-idle session-start`: the absolute
`sessionHome`-derived path avoids dependence on Hyprland's inherited PATH, and
the shell builtin replaces the transient executor shell before backend
validation. The backend then directly execs `/usr/bin/hypridle -v`, leaving no
shell or wrapper alive and preserving direct Hyprland ownership.

On this version, the `hyprland.start` callback can also precede publication of
`$XDG_RUNTIME_DIR/hypr/.../hyprland.lock`; `hyprctl instances` can consequently
report no usable instance even though the callback's real Hyprland parent is
already valid. The initializer therefore proves startup ownership directly
from `/proc`: immediate PPID, exact `/usr/bin/Hyprland` executable, matching
user UID, and unchanged process start time around those checks. This exception
is confined to `session-start`; later manual transactions retain instance
discovery for targeted `hyprctl -i` replacement. No readiness sleep or retry is
used.

Live acceptance on Hyprland 0.56.2 rebooted with Caffeine enabled and a
zero-listener persistent fragment. Before any panel interaction, startup
republished the configured Caffeine-off listeners, left one direct
Hyprland-owned `/usr/bin/hypridle -v`, and the 120-second screensaver fired.
The runtime error record remained absent. This validates the mitigation for the
observed command-executor and instance-lock timing behavior.

The 2026-09-20 cold logout/login began with Caffeine ON and initialized the new
session with Caffeine OFF. This is PASS: Caffeine is intentionally
session-ephemeral, and resetting it prevents a forgotten override from
silently disabling idle, lock, or suspend protection in a later session. It
must not be persisted across logout, reboot, or shutdown/startup.

Retest both command execution and instance-lock timing after a Hyprland upgrade.
The leading `exec` can be reconsidered if a future Lua API provides direct
argument-vector execution with the same parent contract. The `/proc` ownership
proof can be reconsidered only if the startup lifecycle guarantees registry
readiness before callbacks. Public commands remain deployed under
`$HOME/.local/bin`; this mitigation does not move them into a system PATH and
is not generalized to unrelated autostart commands.

## Quickshell popup-stack centering boundary

**Affected components:** Quickshell 0.3.1, Qt 6.11.2, and Hyprland 0.56.2 on
Wayland

When a focus-grabbing dock popup was already open, opening the Super+Space or
Keyboard Shortcuts `PopupWindow` displaced the central surface down and right.
Both surfaces used a full-monitor anchor item, but Quickshell 0.3.1 implements
`grabFocus: true` with the native `Qt::Popup` role and an `xdg_popup` positioner.
Wayland popups form a nested popup stack, so a second focus-grabbing popup is
not an independent monitor-owned surface even when its QML anchor item belongs
to a full-monitor window. Tagged 0.3.1 source confirms that `PopupWindow` sets
the transient parent and `Qt::Popup` flag before passing the anchor rectangle
to the Wayland xdg positioner.

Super+Space and Keyboard Shortcuts therefore share a small per-screen
`PanelWindow` primitive instead of using `PopupWindow`. It assigns the exact
`Variants` delegate screen and uses `ExclusionMode.Ignore`. Vertical placement
uses the monitor's logical height; horizontal placement uses the monitor-local
region to the right of the persistent dock's `VisualMetrics.dockWidth`
exclusive region. Open dock popup size, position, and parent coordinates never
participate.

Live coexistence testing then exposed a related focus boundary: replacing only
the central surface caused the first shortcut press to close an existing dock
popup without showing the requested central surface. Hyprland 0.56.2 owns one
seat grab. Replacing the dock's grabbing `xdg_popup` with a layer-shell focus
grab sends that popup `popup_done`; its later teardown clears the newly
installed grab as well. Quickshell reports the clear to the central surface,
which correctly interprets it as outside-focus dismissal. This is native grab
replacement and teardown ordering, not application-level shortcut arbitration.

Dock-owned popup presentations now also use monitor-bound, non-exclusive
`PanelWindow` surfaces while preserving their prior monitor-local placement
and sliding an out-of-bounds edge placement back inside the logical screen.
The pre-migration popup expanded its anchor rectangle by the centered dock
inset plus `VisualMetrics.dockPopupGap`. Live `hyprctl layers -j` measurement
with the validated versions showed that a left-anchored `PanelWindow` margin is
applied from the compositor-provided usable origin after the persistent dock's
exclusive region. The layer-surface projection therefore uses
`VisualMetrics.dockPopupGap` as its relative margin and centers central surfaces
within the remaining logical width; adding `dockWidth` to either margin counts
the exclusive region twice. One shell-level focus coordinator owns the
Hyprland grab and whitelists the visible
central and dock surfaces together, plus the dock host while one of its panels
is visible. A newly opened central surface is prioritized for the opening
event-loop turn and then shares the whitelist with the still-visible dock
surface and host. A cleared grab dismisses only the foremost central surface
and rearms for a remaining dock on the next turn. Hidden surfaces leave the
whitelist, reserve no exclusive zone, and are not visible input targets.

Quickshell 0.3.1 reports a critical error if `QsWindow.itemRect()` is called
before its item belongs to a Quickshell window, and that mapping call is not
itself reactive. Dock surfaces are instantiated before their dock anchors have
necessarily joined a window, so `DockPopup` keeps requested-open state separate
from native visibility. It maps and shows only after the anchor has an owning
window on the target screen, and reads the owning window's `windowTransform` as
the documented geometry invalidation source. An early open request remains
pending until placement becomes valid; an invalidated placement immediately
leaves both native visibility and the focus whitelist without a timer or
polling.

Retest first-press coexistence, focus transfer, dismissal, and central
positioning with no popup and with Display, Audio, and Network open, plus a
fresh-process startup and monitor/delegate recreation, after a Quickshell, Qt
Wayland, Hyprland focus-grab, or layer-shell upgrade. The dedicated layer
surfaces and shared coordinator may be reconsidered only if a future popup
implementation can prove both an independent monitor coordinate space and
compatible nested focus ownership.

The compositor focus whitelist is intentionally broader than each overlay's
product-level dismissal boundary. Dock-host and dock-panel pointer taps are
observed with Qt's passive `TapHandler.DragThreshold` policy, so the original
target remains responsible for the click. A dock-panel tap dismisses only the
central surface. The persistent dock's background `MouseArea` sits below its
real controls and dismisses both transient roles only when no actionable child
accepted the press. Owning controls call the coordinator's explicit toggle;
they do not reuse background dismissal. A true compositor `cleared` event now
dismisses both visible transient roles. Keep the shared grab and all three
surface classes in its whitelist; removing dock surfaces to synthesize these
semantics would restore the grab-replacement failure above.

## Hyprland layer-surface pointer-refocus boundary

**Affected components:** Hyprland 0.56.2, Quickshell 0.3.1, and Qt 6.11.2 on
Wayland

On Hyprland 0.56.2, opening Display while the pointer remains stationary over
its owning dock icon can leave native pointer focus on the newly mapped panel
surface. A bounded QML and `WAYLAND_DEBUG=client` trace proved that the first
click reached the icon normally, after which Hyprland sent pointer leave to the
dock and pointer enter to the Display surface at coordinates outside its
content. The cursor consequently changed from the pointer to the default
arrow.

The next stationary button press and release went to that stale native surface;
no Vanilla icon, dock-host, dock-popup, or panel QML handler received them.
Hyprland retargeted the dock only after those button events. In the control
case, physical pointer movement forced the retarget before the next button, so
the same-icon click reached QML and closed Display normally. Hyprland issues
#4281 and #4882 and discussion #13116 describe related stale layer-surface
pointer-focus behavior.

This proves that no Vanilla toggle, dismissal, or coordinator state transition
runs for the swallowed second click. No pointer warp, synthetic input, replay,
delay, debounce, or focus hack is carried here. Retain the no-motion same-icon
case as a Hyprland 0.56.2 limitation unless a supported surface arrangement is
separately proven to avoid it without regressing the shared-grab architecture.

Retest after any Hyprland change to `InputManager::processMouseDownNormal`,
`mouseMoveUnified`, `CSeatManager` pointer focus, `CFocusGrab`, or layer-shell
hit testing, and after any Quickshell or Qt Wayland change to focus-grab or
cursor handling.

## Quickshell Bluetooth pairing-agent boundary

**Affected component:** Quickshell 0.3.1 with BlueZ 5.87

Quickshell 0.3.1 exposes native Bluetooth adapters, discovery, devices,
pairing, connection, removal, and trust, but not the full BlueZ
`org.bluez.Agent1` callback surface required for PIN entry, displayed
passkeys, numeric confirmation, and authorization. Vanilla HyprArch supplies
one narrowly scoped Python agent using dbus-python and PyGObject. It is a
Quickshell-supervised child, registers with capability `KeyboardDisplay`, and
becomes the default agent because pairing is initiated by Quickshell's separate
D-Bus client.

The helper subscribes to BlueZ owner changes before registration and rechecks
the unique owner before reporting readiness. Display callbacks use delayed
replies until a panel acknowledges visibility; missing UI, bounded timeouts,
IPC failure, and shell or BlueZ teardown all terminate outstanding work rather
than accepting it. Automatic trust/connect is scoped to one user pairing
transaction and one helper-session generation.

The mitigation contains no adapter or device model and does not parse
`bluetoothctl`. Retest after a Quickshell Bluetooth API upgrade. It can be
removed when the installed native module provides equivalent complete pairing
callbacks and explicit user-response methods without losing the current
fail-closed lifecycle.

Manual testing confirmed panel-owned discovery start/stop, Android-phone
discovery, and successful outgoing pairing through the shell. Persistent device
profiles, Forget/re-pair, incoming requests, the complete PIN/passkey and
service-authorization matrix, multi-monitor routing, and reload during active
pairing remain pending real-device validation.

## BlueZ controller power persistence

**Affected component:** BlueZ 5.87

BlueZ `Adapter1.Powered` is runtime-only. Its packaged `main.conf` documents
`[Policy] AutoEnable=true` as the default, which enables controllers when they
are discovered at boot or later. Quickshell 0.3.1 writes that runtime property
correctly but does not turn it into a durable user choice; rfkill persistence
is a separate mechanism.

Vanilla HyprArch supplies a minimal BlueZ `main.conf` with `AutoEnable=false`
and restores Bluetooth through native Quickshell adapters. A missing user
preference means the in-memory first-run default ON; only explicit panel actions
write the versioned preference. BlueZ 5.87 reads one `main.conf`, not a
configuration drop-in directory, so the future bootstrap must deploy the
tracked complete minimal file and preserve an existing administrator file for
rollback. On the development machine, manual reboot tests confirmed saved OFF
restores OFF and saved ON restores ON, with discovery inactive in both cases.
Retest the file-loading and `AutoEnable` behavior after a BlueZ upgrade.

Until that bootstrap exists, users must not copy the tracked file blindly over
an existing customized BlueZ configuration.

## Shortcut description metadata transport

Validated on 2026-09-20 with Hyprland 0.56.2, Lua 5.5.1, Quickshell 0.3.1,
Qt 6.11.2, and Python's standard JSON implementation. Hyprland descriptions
have no separate project-metadata field, while Super+K must continue to derive
rows from actual active described bindings rather than a second catalog.

The local transport appends a framed version-1 ASCII payload encoded as Unicode
tag characters after the normal `Category | Action` text. A deterministic
repository experiment passed the description through Lua UTF-8 generation,
JSON serialization and parsing, QML decoding, and Qt text measurement. Bytes
survived without truncation or escaping ambiguity, tagged and legacy text had
identical rendered width, normal text cannot collide with the non-BMP framing,
and malformed or unknown payloads failed closed. Bindings without availability
metadata remain byte-for-byte legacy descriptions.

This is an internal transport, not a public interface. Retest the Lua-to-runtime
description and `hyprctl -j binds` JSON path after a Hyprland config-provider or
JSON-output change, and retest default-ignorable rendering after a Qt upgrade.
Remove or replace the encoding if Hyprland gains a structured binding-metadata
field that survives runtime inspection.

## Current screensaver validation

**Status:** validated with `vanhyprarch-zig-player` v0.1.1

The player is now optional for the Arch Linux x86_64 Alpha target. Absence is
not a compatibility failure: the backend suppresses all player actions while
Display, Suspend, Automatic Lock, and Caffeine remain available. Marker or
payload corruption is reported as incomplete and uses the same safe effective
projection. The repository lifecycle tests are complete; this milestone has
not yet performed controlled adoption or a fullscreen physical live test.

### Production idle continuity

The final production test exercised the complete
`hypridle -> vanhyprarch-screensaver -> vanhyprarch-zig-player v0.1.1` chain.
ColorMix started through the controller after 10 seconds, a harmless second
listener recorded the 20-second deadline, and genuine input invoked the
listener's resume action:

```text
player start    +10.034 s
second timeout  +20.036 s
separation       10.002 s
genuine resume  +23.291 s
```

Native player startup neither reset pending hypridle clocks nor created a false
resume on the validated stack. Each event occurred exactly once. Genuine
keyboard activity emitted `on-resume`, which terminated the controller-owned
player and restored the normal zero-listener configuration. Production uses
one inhibitor-aware screensaver listener with both timeout and resume actions.
No S-1 or `ignore_inhibit` dismissal helper remains.

### Input routing

With Foot focused underneath the fullscreen player, manual tests—including the
final production-chain test—confirmed:

- the first keyboard character was absorbed;
- a pointer click was absorbed;
- scrolling was absorbed;
- real input still caused hypridle to emit `on-resume` and dismiss the player.

Release v0.1.0 exposed first-input leakage. Release v0.1.1 fixed it using
native layer-shell input routing. Input absorption belongs to the player;
Vanilla HyprArch carries no keyboard, pointer, injection, or compositor
workaround.

### Integrated power and lock lifecycle

Controlled single-output testing validated real display-off, suspend, resume,
automatic lock at the Screen saver stage, automatic lock at the Display stage,
and dismissal of the saver before its later Display lock without a password.
Manual Power Menu lock and `hyprlock` password unlock also passed. Cleanup left
no residual `hyprlock`, player process, or layer; cursor state was restored and
no double-lock was observed. Cold-start hypridle ownership and behavior were
also revalidated.

These results do not claim physical two-monitor acceptance or every
lock-at-suspend/Caffeine combination.

Retest after a Hyprland, hypridle, Wayland, or player update. Use harmless
timestamp actions first; do not trigger DPMS, locking, suspend, or fullscreen
UI as an incidental compatibility probe.

## Historical terminal behavior

The abandoned Foot/xdg-toplevel renderer caused Hyprland 0.56.2 to re-evaluate
idle inhibitors when its fullscreen window mapped. That produced a false resume
and changed an intended 10/20/30 timeline to approximately 10/30/40. It is
retained here only to explain why a native layer-shell renderer is an explicit
architecture boundary. Git history contains the detailed measurements and
temporary workarounds.

No compatibility code for that abandoned renderer remains active.

## Current player integration limit

The v0.1.1 player creates all-edge overlay surfaces using direct
`wlr-layer-shell`, handles integer and fractional output scaling, and contains
multi-output lifecycle logic. Physical two-monitor behavior has not yet been
validated upstream.

## Updateability principle

On the validated stack, explicit `yay -Syu` updates installed official and AUR
packages while preserving yay and pacman configuration and prompts. Explicit
`flatpak update` updates installed Flatpak applications and runtimes with its
normal interactive behavior. Super+Space passes both as fixed direct argument
vectors through the shared terminal helper; it supplies no noninteractive,
forced-refresh, downgrade, dependency-bypass, or ordering flags. No real update
transaction was run as part of this validation.

Flatpak's recorded version is compatibility evidence, not an installation pin.
Clean installations consume the current official Arch package, and the normal
system update keeps it current. The system Flathub remote was validated at
`https://dl.flathub.org/repo/`.

Vanilla HyprArch must not blindly update its configuration or external player.
A player update requires an explicit version, architecture, asset-name,
checksum, release URL, and source-tag update followed by controller, timing,
output, input, and license-notice validation. Project self-update remains
unavailable. The first ownership contract now distinguishes managed, machine,
override, preference, generated, runtime, optional, and system-adopted
artifacts, but no deployment ledger, release staging, updater transaction, or
rollback engine exists yet.

Before changing this baseline:

1. identify the installed component versions;
2. inspect relevant upstream changes;
3. run targeted regressions for applicable quirks;
4. remove obsolete mitigation rather than retaining it indefinitely;
5. update this register with the new evidence.

The optional archinstall entry point remains version-sensitive. Any released
preset must record its validated archinstall baseline here.
