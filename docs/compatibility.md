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
