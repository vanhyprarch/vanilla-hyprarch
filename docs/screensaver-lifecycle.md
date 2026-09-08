# Screensaver lifecycle

This document describes the provisional lifecycle contract for the Vanilla
HyprArch colormix screensaver. The controller and two-listener hypridle
lifecycle have passed manual testing. Production timeout generation now exists,
but locking, multi-output behavior, and the future Quickshell controls still
require integrated validation.

## Controller

`bin/vanhyprarch-screensaver` exposes a stable command interface:

```text
vanhyprarch-screensaver start
vanhyprarch-screensaver stop
vanhyprarch-screensaver status
```

`start` launches one standalone, fullscreen Foot process with app ID
`vanhyprarch-screensaver`. Foot runs the existing colormix renderer at its
33-millisecond default cadence. A dedicated session and process group detach it
from the caller, allowing a future hypridle timeout command to return promptly.
Before launching Foot, the controller records the current Hyprland
`cursor:invisible` value and hides the cursor through Hyprland's native Lua
runtime API. Repeated starts are idempotent and do not overwrite that original
cursor value.

`stop` first sends SIGTERM only to the validated, dedicated screensaver process
group. Foot owns the renderer terminal, so closing Foot also closes the
renderer; the renderer handles termination and hangup cleanup. If the group
does not exit within three seconds, the controller revalidates ownership before
using SIGKILL. Repeated stops are harmless. It never searches for or signals
Foot by process name. Immediately after sending SIGTERM, the controller restores
the exact cursor visibility value saved by `start`, before waiting for the
process group to exit. It also restores that value when valid ownership state
remains after Foot has already exited.

`status` succeeds only while the owned screensaver Foot process is still valid.
It prints a concise PID/process-group result and returns nonzero while stopped.

## Runtime ownership

Ownership state is ephemeral beneath:

```text
${XDG_RUNTIME_DIR}/vanhyprarch/
```

The state record contains the Foot PID, Linux process start time, process group,
and session ID. Before reporting or signalling the process, the controller
checks all four values, verifies that the executable is Foot, and requires the
exact `--app-id=vanhyprarch-screensaver` and `--fullscreen` arguments. A reused
PID or malformed state therefore cannot authorize a signal. Invalid or stale
ownership state is removed automatically.

A separate atomic `screensaver.cursor` record stores only the previous boolean
value of `cursor:invisible`. Keeping it separate leaves process-identity
validation unchanged and lets `stop` restore the cursor even if Foot or the
renderer has already exited. The record is written before the cursor is hidden,
is not overwritten by an idempotent start, and is removed only after successful
restoration. Failed or interrupted starts terminate any launched process group,
restore the saved value, and remove their ownership records. No persistent
cursor state survives beyond the XDG runtime directory.

An advisory lock serializes concurrent lifecycle calls. A runtime log captures
Foot startup errors and is overwritten on each start; clean stop removes it.
All controller files remain under the session-scoped XDG runtime directory.

## Development and installation layout

The repository has no prior production-script convention, so the controller is
kept in `bin/`, the conventional source location for an executable intended for
the user's PATH. During development it finds the existing built renderer at
`experiments/colormix/colormix`; no renderer source is duplicated.

A future installer should build the renderer and install it as
`vanhyprarch-colormix`, alongside the controller or elsewhere in PATH. The
controller then runs without the Git checkout or a user-specific absolute path.
Its runtime requirements are a POSIX shell, Linux procfs, normal base command
line tools, and util-linux's `flock` and `setsid`; it does not require jq.

## Manual lifecycle test

Run these commands from the repository root in an ordinary Foot terminal. The
first and last status commands are expected to return status 1.

```sh
ordinary_foot_pid=$PPID

./bin/vanhyprarch-screensaver status
./bin/vanhyprarch-screensaver start
./bin/vanhyprarch-screensaver status
./bin/vanhyprarch-screensaver start
./bin/vanhyprarch-screensaver stop
./bin/vanhyprarch-screensaver stop
./bin/vanhyprarch-screensaver status

kill -0 "$ordinary_foot_pid" && echo "ordinary Foot is still running"
```

The second `start` must report the existing owned PID. The second `stop` must
be harmless. `kill -0` sends no signal; it only verifies that the ordinary Foot
process hosting the test shell was not terminated.

## Multi-output limitation

Phase 1 launches one fullscreen Foot window and has been designed for the
current single-monitor development system. Fullscreen coverage and lifecycle
ownership across multiple outputs remain production requirements. The stable
`start`/`stop`/`status` API can later manage multiple validated processes
without changing callers.

## Two-listener hypridle architecture

The canonical main configuration is `home/.config/hypr/hypridle.conf`. It uses
hypridle's supported relative include:

```text
source = ./vanhyprarch-idle.conf
```

Hyprland v0.56.2 performs an idle-inhibitor recheck whenever a window maps. Even
when no inhibitor exists, that recheck updates inhibitor-aware idle
notifications. If such a notification is already idled, Hyprland sends a false
resume event. The original single listener therefore started Foot and then
immediately stopped it when the new fullscreen window mapped. Foot itself did
not request an idle inhibitor, and the lifecycle controller behaved correctly.

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

The false resume delivered to the start listener when Foot maps is harmless
because that listener has no resume command. The input-only dismiss listener is
not updated by inhibitor rechecks and should remain idled until real input.

Two complete manual cycles confirmed that the screensaver starts, remains
visible without genuine input, and is dismissed immediately by mouse input.
No hyprlock appeared, and exactly one Hyprland-owned hypridle remained running.
Cursor hiding and exact restoration were subsequently validated manually.

Nine and ten seconds were deliberately short manual-test values and are not
Vanilla HyprArch defaults. The production backend preserves the same relation
at arbitrary configured timeouts: the input-only listener arms exactly one
second before the inhibitor-aware start listener. The migration state remains
Screen saver `Never`, Turn off display `Never`, and Suspend `Never` until the
future UI records user choices.

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
