# Screensaver lifecycle

This document describes the provisional lifecycle contract for the Vanilla
HyprArch colormix screensaver. Phase 1 provides the controller only. It does not
add hypridle listeners, Quickshell controls, or production timeouts.

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
Repeated starts are idempotent.

`stop` first sends SIGTERM only to the validated, dedicated screensaver process
group. Foot owns the renderer terminal, so closing Foot also closes the
renderer; the renderer handles termination and hangup cleanup. If the group
does not exit within three seconds, the controller revalidates ownership before
using SIGKILL. Repeated stops are harmless. It never searches for or signals
Foot by process name.

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

## Intended hypridle semantics

These are design notes for the next phase, not active listeners.

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

The existing `before_sleep_cmd = loginctl lock-session` remains the safety
mechanism before actual sleep.
