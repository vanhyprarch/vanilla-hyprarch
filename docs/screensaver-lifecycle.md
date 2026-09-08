# Screensaver lifecycle

This document describes the lifecycle contract for the Vanilla HyprArch
colormix screensaver. The controller, separate layer-shell presentation,
multi-screen structure, and two-listener hypridle lifecycle are implemented.
Generated locking, DPMS, and suspend paths still require integrated validation,
so the overall screensaver remains Provisional.

The [compatibility register](compatibility.md) is the canonical record of
version-specific upstream behavior, including the confirmed rearming of later
idle clocks.

## Controller

`bin/vanhyprarch-screensaver` exposes a stable command interface:

```text
vanhyprarch-screensaver start
vanhyprarch-screensaver stop
vanhyprarch-screensaver status
```

`start` launches the separate named Quickshell configuration
`vanhyprarch-screensaver` with `qs -n -c vanhyprarch-screensaver`. A dedicated
session and process group detach it from the caller, allowing the hypridle
timeout command to return promptly. Before launch, the controller records the
current Hyprland
`cursor:invisible` value and hides the cursor through Hyprland's native Lua
runtime API. Repeated starts are idempotent and do not overwrite that original
cursor value.

`stop` first sends SIGTERM only to the validated, dedicated screensaver process
group. If the group does not exit within three seconds, the controller
revalidates procfs identity before using SIGKILL. Repeated stops are harmless.
It never searches for or signals Quickshell by process name and cannot target
the main `vanhyprarch` shell. Immediately after SIGTERM, it restores the exact
cursor visibility value saved by `start`, before waiting for shutdown. It also
restores that value when ownership state remains after the saver has crashed.

`status` succeeds only while both the owned process and its exact Quickshell
registration remain valid. It is observational: stale state is reported with
an instruction to run `stop`, which performs cursor and ownership cleanup.

## Runtime ownership

Ownership state is ephemeral beneath:

```text
${XDG_RUNTIME_DIR}/vanhyprarch/
```

The state record contains the Quickshell PID, Linux process start time, process
group, session ID, Quickshell instance ID, and shell ID. Before signalling, the
controller requires the recorded PID/start-time/PGID/SID tuple, executable
`quickshell`, and exact `-n`, `-c`, and `vanhyprarch-screensaver` arguments. It
also requires the live Quickshell registry to map that PID, instance ID, and
shell ID to the expected named-config path. A reused PID, another Quickshell
instance, or malformed state cannot authorize a signal.

Startup additionally verifies one `vanhyprarch-screensaver` layer namespace
for every current Hyprland output and rejects a pre-existing unowned instance
of the same named config. Layer presence supplements procfs and Quickshell
registration checks; it is not the sole ownership mechanism.

A separate atomic `screensaver.cursor` record stores only the previous boolean
value of `cursor:invisible`. Keeping it separate leaves process-identity
validation unchanged and lets `stop` restore the cursor even if the Quickshell
process has already exited. The record is written before the cursor is hidden,
is not overwritten by an idempotent start, and is removed only after successful
restoration. Failed or interrupted starts terminate any launched process group,
restore the saved value, and remove their ownership records. No persistent
cursor state survives beyond the XDG runtime directory.

An advisory lock serializes concurrent lifecycle calls. A runtime log captures
Quickshell startup errors and is overwritten on each start; clean stop removes
it.
All controller files remain under the session-scoped XDG runtime directory.

## Development and installation layout

The controller remains in `bin/`, the source location for an executable
intended for PATH. The dedicated config is tracked at
`home/.config/quickshell/vanhyprarch-screensaver/`, separate from the main
desktop shell. Development uses a repository-backed symlink at
`~/.config/quickshell/vanhyprarch-screensaver`.

A future installer must deploy both named Quickshell configs and install the
controller in PATH. No compiled renderer is required by production. Controller
runtime requirements remain a POSIX shell, Linux procfs, normal base command
line tools, and util-linux's `flock` and `setsid`; it does not require jq.

## Manual lifecycle test

Run these commands from the repository root. The first and last status commands
are expected to return status 1. Resolve the main shell PID dynamically and
require exactly one instance at the expected named-config path before starting.

```sh
main_shell_pid=<validated PID from qs list --all --json>
controller=$PWD/bin/vanhyprarch-screensaver

(sleep 10; "$controller" stop) &
failsafe_pid=$!
trap '"$controller" stop >/dev/null 2>&1 || true' EXIT HUP INT TERM

"$controller" status
"$controller" start
"$controller" status
"$controller" start
"$controller" stop
"$controller" stop
"$controller" status

kill "$failsafe_pid" 2>/dev/null || true
wait "$failsafe_pid" 2>/dev/null || true
trap - EXIT HUP INT TERM

kill -0 "$main_shell_pid" && echo "main shell is still running"
```

The independent controller-stop failsafe must be armed before `start`. The
second `start` must report the existing owned PID, and the second `stop` must be
harmless. `kill -0` sends no signal; it only verifies that the main shell was
not terminated.

## Presentation and multi-output lifecycle

The separate process uses one shared 33-millisecond animation clock and
`Variants { model: Quickshell.screens }`. Each delegate is a per-screen `Scope`
containing one four-edge-anchored `PanelWindow` bound to `modelData`. Every
surface is an overlay layer-shell surface with exclusion mode `Ignore`,
exclusive keyboard focus, and namespace `vanhyprarch-screensaver`. Exclusive
focus prevents the first dismissal key from reaching the previously focused
application; it does not turn the screensaver into a secure lock surface.
Hypridle still observes genuine input and owns dismissal. Hotplug and output
recreation are handled by the live screen model rather than a startup-time
screen snapshot.

`Colormix.qml` ports Ly's three-iteration transform and 12-entry palette
mapping using Qt Quick Canvas only. A small grid-sized image is scaled with
nearest-neighbor rendering; palette foreground/background densities are
represented as blended red, blue, and true-black cells rather than terminal
Unicode glyph rasterization. This avoids Foot, ANSI parsing, shaders, and new
dependencies while keeping the visual motion and color structure.

The controller does not observe input itself. Directly starting the screensaver
while its generated hypridle dismissal listener is absent therefore has no
input-driven stop path. Manual presentation tests must arm an independent,
bounded call to `vanhyprarch-screensaver stop` before starting it; standalone
test-mode behavior is a separate future UX decision.

## Two-listener hypridle architecture

The canonical main configuration is `home/.config/hypr/hypridle.conf`. It uses
hypridle's supported relative include:

```text
source = ./vanhyprarch-idle.conf
```

On the validated stack, mapping the former Foot xdg-toplevel performed an idle
inhibitor recheck and sent a false resume to the already-idled action
notification. The layer-shell production presentation removes this
deterministic trigger and preserves later absolute deadlines. Canonical
evidence is in the compatibility register.

Phase 2B separated the inhibitor-aware action from genuine-input dismissal.
Its successful manual test used exactly these listeners:

```text
listener {
    timeout = 10
    on-timeout = vanhyprarch-screensaver start
}

listener {
    timeout = 9
    ignore_inhibit = true
    on-timeout = /usr/bin/true
    on-resume = vanhyprarch-screensaver stop
}
```

The 10-second start listener remains inhibitor-aware and has no resume action.
Legitimate inhibitors can therefore prevent the screensaver from starting.
The 9-second dismiss listener uses an input-only notification, becomes idled
first, and performs only `/usr/bin/true` at timeout. Its resume action stops the
owned screensaver on subsequent genuine input. `ignore_inhibit` is intentional
only on this harmless input/dismiss listener; it must not be copied to the
screensaver action listener.

The input-only dismiss listener is not updated by inhibitor rechecks and
remains idled until real input. Although production layer mapping did not emit
a false resume in two marker cycles, the S-1 two-listener arrangement remains
implemented for now. Removing it requires a separate lifecycle and inhibitor
regression.

Two complete manual cycles confirmed that the screensaver starts, remains
visible without genuine input, and is dismissed immediately by mouse input.
No hyprlock appeared, and exactly one Hyprland-owned hypridle remained running.
Cursor hiding and exact restoration were subsequently validated manually.

Nine and ten seconds were deliberately short manual-test values and are not
Vanilla HyprArch defaults. The production backend preserves the same relation
at arbitrary configured timeouts: the input-only listener arms exactly one
second before the inhibitor-aware start listener. The migration state remains
Screen saver `Never`, Turn off display `Never`, and Suspend `Never` until the
user records other choices through the Power & Idle UI.

Hyprland remains the daemon owner; the packaged systemd user service stays
disabled. The development session exposes project commands through executable
symlinks in `~/.local/bin`, and hypridle receives that directory in PATH. A
future installer will deploy the executables independently of the Git checkout.

The generated production semantics, stored state, and transactional restart
procedure are documented in `power-idle-backend.md`.

## Intended hypridle semantics

These are the backend's generated semantics. All stages currently default to
`Never`, so they remain inactive until the user stores valid timeouts.

### Lock stage: Screen saver

- Screensaver timeout: `vanhyprarch-screensaver start`
- Screensaver resume: `loginctl lock-session`
- General unlock: `vanhyprarch-screensaver stop`

The screensaver remains alive behind hyprlock so the desktop is not exposed
between the screensaver and the lock surface.

### Lock stage: not Screen saver

- Screensaver timeout: `vanhyprarch-screensaver start`
- Screensaver resume: `vanhyprarch-screensaver stop`

### Lock stage: Turn off display

At the display-off timeout, request session lock before turning DPMS off. On
activity, turn DPMS on; hyprlock should already own the locked session.

### Lock stage: Suspend

`before_sleep_cmd = vanhyprarch-idle before-sleep` conditionally requests
`loginctl lock-session` immediately before sleep. It locks when an automatic
lock point is selected, but not with Lock `None` or Caffeine active.
