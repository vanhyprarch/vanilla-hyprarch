# Screensaver lifecycle

Vanilla HyprArch delegates rendering to the independent
[`vanhyprarch-zig-player`](https://github.com/vanhyprarch/vanhyprarch-zig-player)
and controls it as a separate executable. The player owns Wayland,
`wlr-layer-shell`, output coverage, scaling, rendering, and animation. This
repository does not contain or vendor the player's Zig implementation.

The pinned integration is release `v0.1.1`. Its supported effects are
`colormix`, `matrix`, `doom`, and `gameoflife`.

## Controller API

`bin/vanhyprarch-screensaver` preserves one stable interface:

```text
vanhyprarch-screensaver start
vanhyprarch-screensaver stop
vanhyprarch-screensaver status
```

`start` asks `vanhyprarch-idle` for the validated selected effect, resolves
`vanhyprarch-zig-player` from PATH, records the exact current cursor visibility,
hides the cursor, and launches the native player in a detached session. A
repeated start is idempotent and never overwrites the original cursor value.

`stop` signals only a process matching the controller's complete ownership
record. It requests graceful SIGTERM, restores the cursor immediately, and
waits for a bounded interval. SIGKILL is used only after the same process is
revalidated. Repeated stops are harmless. Dead, stale, malformed, reused-PID,
executable-mismatch, and argument-mismatch states never authorize a signal.

`status` succeeds only for the exact owned process and reports its PID and
effect. It is observational; `stop` performs stale state and cursor cleanup.

## Runtime ownership

Session-only files live under `${XDG_RUNTIME_DIR}/vanhyprarch/`. The process
record contains:

- PID;
- Linux process start time;
- exact resolved executable path;
- exact effect argument.

The runtime directory, state file, and cursor record must belong to the current
user. An advisory lock serializes lifecycle operations. A separate cursor
record allows exact restoration even if the player exits unexpectedly. Failed
startup removes incomplete ownership state and restores the saved cursor.

The controller never searches for or signals a process by name. It has no
Quickshell registry, named-config, shell-ID, instance-ID, or layer-count logic,
and cannot target the main desktop shell.

## hypridle lifecycle

The static `home/.config/hypr/hypridle.conf` sources the generated
`vanhyprarch-idle.conf`. An enabled screensaver uses one inhibitor-aware
listener:

```text
listener {
    timeout = S
    on-timeout = vanhyprarch-screensaver start
    on-resume = vanhyprarch-screensaver stop
}
```

When Screen saver owns automatic locking, `on-resume` requests
`loginctl lock-session` instead. The static `on_unlock_cmd` then stops the
player after authentication. Display-off, suspend, pre-sleep, and Caffeine
semantics are unchanged.

The complete production chain was tested with a 10-second controller start and
a 20-second harmless marker. ColorMix started through
`vanhyprarch-screensaver` at +10.034 seconds and the marker fired at +20.036
seconds, 10.002 seconds later. Player mapping did not reset hypridle's clock.
Genuine keyboard input emitted resume at +23.291 seconds and stopped the owned
player. The first `x` did not reach Foot underneath, and cleanup restored the
cursor, layer set, single Hyprland-owned hypridle, and normal zero-listener
configuration. The former S-1 input-only helper is therefore obsolete.

## Input routing

Release v0.1.1 uses native layer-shell input routing. Manual tests with Foot
underneath confirmed that the first keyboard character, pointer click, and
scroll were absorbed while real input still caused hypridle to resume and stop
the player. Input absorption remains the player's responsibility; Vanilla
HyprArch adds no grab, injection, or input workaround.

The timing and input-routing validation described above deliberately excluded
DPMS, locking, and suspend. Subsequent controlled lifecycle tests validated
real display-off, suspend/resume, manual lock and password unlock, automatic
lock at the Screen saver and Display stages, dismissal before a later Display
lock without a password, cursor restoration, and cleanup without residual
lock, player, or layer state. No double-lock was observed. Remaining
lock-at-suspend/Caffeine combinations are tracked separately in
[current state](current-state.md).

Physical two-monitor validation also remains pending upstream.

## Installation

The controller and player must both be available in the PATH inherited by
hypridle. The normal per-user destination is `$HOME/.local/bin`. The pinned
installer in `install/` verifies the release archive before installing the
player plus its independent license and third-party notices. Zig is not an
end-user dependency.
