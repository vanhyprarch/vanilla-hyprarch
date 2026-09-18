# Screensaver lifecycle

Vanilla HyprArch delegates rendering to the independent
[`vanhyprarch-zig-player`](https://github.com/vanhyprarch/vanhyprarch-zig-player)
and controls it as a separate executable. The player owns Wayland,
`wlr-layer-shell`, output coverage, scaling, rendering, and animation. This
repository does not contain or vendor the player's Zig implementation.

The renderer is an optional Additional system component named **Zig
Screensaver** (`zig-screensaver`). The baseline controller remains installed
and its `stop` operation remains safe when the optional payload is absent. The
pinned integration is release `v0.1.1`. Its supported effects are
`colormix`, `matrix`, `doom`, and `gameoflife`.

## Controller API

`bin/vanhyprarch-screensaver` is the single runtime and component-lifecycle
authority:

```text
vanhyprarch-screensaver start --idle
vanhyprarch-screensaver resume-lock
vanhyprarch-screensaver test
vanhyprarch-screensaver stop
vanhyprarch-screensaver status
vanhyprarch-screensaver component-status --json
vanhyprarch-screensaver component-capability
vanhyprarch-screensaver install|adopt|reinstall|repair|clean-up
vanhyprarch-screensaver uninstall --plan-token TOKEN
vanhyprarch-screensaver uninstall-plan --json
```

`start --idle` asks `vanhyprarch-idle` for the validated selected effect and
whether leaving this idle-owned invocation is authentication-protected, first
requires authoritative installed capability, resolves
`vanhyprarch-zig-player` from PATH, records the exact current cursor visibility,
hides the cursor, and launches the native player in a detached session. A
repeated start is idempotent and never overwrites the original cursor value.
A plain `start` is rejected. `test` starts the same owned process without
arming Automatic Lock and stops it automatically after five seconds; the
timeout is controller-owned and does not depend on player or terminal input
delivery.

For `lock=screensaver`, hypridle calls `resume-lock` on activity. The controller
requests the session lock while the native saver still covers the desktop, then
records that authentication has been armed so the post-authentication `stop`
does not request a second lock. A direct `stop` of a still-protected idle saver
requests that same lock before terminating it. Missing, stale, or invalid
runtime ownership on the automatic resume path also requests lock first and
fails closed.

`stop` signals only a process matching the controller's complete ownership
record. It requests graceful SIGTERM and waits for a bounded interval. SIGKILL
is used only after the same process is revalidated. Process termination and
cursor restoration are separate obligations: process state is cleared after
termination even when restoration fails, while the cursor record is retained
and the command returns nonzero until a later idempotent `stop` verifies
restoration. An identity-bound watcher performs the same recovery after an
unexpected player exit and cannot stop a newer player. When the idle-owned
Screensaver stage is authentication-protected, that watcher requests session
lock before cursor restoration; normal resume continues to lock before the
desktop can reappear while leaving the saver visible during idle. Repeated stops are
harmless. Dead, stale, malformed, reused-PID,
executable-mismatch, and argument-mismatch states never authorize a signal.

`status` succeeds only for the exact owned process and reports its PID and
effect. It is observational; `stop` performs stale state and cursor cleanup.

## Runtime ownership

Session-only files live under `${XDG_RUNTIME_DIR}/vanhyprarch/`. The process
record contains:

- PID;
- Linux process start time;
- exact resolved executable path;
- exact effect argument;
- idle resume-authentication protection (`on` or `off`);
- current-user UID ownership, revalidated from `/proc` rather than trusted from
  a writable record.

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
    on-timeout = vanhyprarch-screensaver start --idle
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

## Optional component state and installation

Installed state means the exact mode-0644 marker
`${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/components/zig-screensaver`
contains `vanhyprarch-zig-screensaver-v1\n` and every expected payload member
passes type, current-user ownership, mode, canonical hash, x86_64 ELF, and
runtime-library validation. The dedicated license and documentation
directories must have exact canonical membership. Marker, payload, or
membership damage reports `incomplete` (or `error` for unsafe material), never
installed. The manager is the marker's only writer.

Immutable v0.1.1 metadata and the private manager implementation live at
`${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/zig-screensaver/` so
installation does not require a Git checkout. Optional payload uses
`$HOME/.local/bin/vanhyprarch-zig-player`, XDG data directories under
`licenses/vanhyprarch-zig-player/` and `doc/vanhyprarch-zig-player/`, and the
marker above. `adopt` verifies an existing complete payload byte-for-byte
against a newly verified pinned archive before publishing the marker and does
not replace valid player/archive-member bytes; it may refresh the installed
release record to the current canonical metadata schema. Install/reinstall
stage privately and parse the prospective installed idle configuration without
publishing it. They publish and validate payload, publish the marker, and only
then reconcile the installed-capability fragment. Reinstall restores a prior valid payload
when replacement fails safely.
Uninstall reconciles Power & Idle and publishes a no-player idle fragment
before withdrawing the marker and deleting only proven component-owned files.
Shared packages and the baseline controller are never removed. Zig is not an
end-user dependency.

Clean up is more conservative than installed validation. A valid marker proves
prior component provenance. A mode-0600 runtime-only receipt can prove exact
canonical files published by an interrupted fresh install; it is created
exclusively before publication and removed on success or handled rollback.
Without one of those proofs, expected path, name, type, and UID never authorize
deletion. Losing the receipt across reboot makes ambiguous partial material
manual-review-only.

Uninstall validates every intended removal target before stopping a process or
changing preferences. Its confirmation token binds the exact preference bytes,
resulting lock, and component file identity; changed state requires a new plan.
With custom `XDG_DATA_HOME`, adoption can copy a fully verified legacy
ancillary layout from `$HOME/.local/share` into the canonical root. It refuses
canonical-root conflicts, preserves the player inode, and retains the verified
legacy copy rather than risking ambiguous deletion.
