# Power & Idle backend

`bin/vanhyprarch-idle` is the non-graphical configuration owner for Power &
Idle. The Quickshell panel calls this command rather than editing hypridle files
independently.

## State model

Durable user preferences live at:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/power-idle.conf
```

The strict, versioned format is deterministic and deliberately parseable
without jq:

```text
version=2
screensaver=never
display=never
suspend=never
lock=none
effect=colormix
```

Timeout values are integer seconds. Enabled stages must be strictly ordered:
Screen saver < Turn off display < Suspend. Stages set to `never` are ignored in
that comparison. A lock point cannot name a disabled stage, and invalid changes
are rejected without rewriting another setting.

`effect` is one of `colormix`, `matrix`, `doom`, or `gameoflife`. Existing
version-1 files remain valid and read as `effect=colormix`; the next preference
write migrates them to version 2 without changing their existing settings.

Caffeine is runtime-only. An atomic file containing `on` at
`${XDG_RUNTIME_DIR}/vanhyprarch/caffeine` means enabled; absence means off. It
never changes the durable preference file. Reapplying `caffeine on` or
`caffeine off` is idempotent and reconciles the generated configuration after
an interrupted operation. Every fresh Hyprland session runs the backend's
`session-start` path before hypridle parses its configuration. That path removes
any marker, regenerates the fragment from durable preferences with Caffeine
off, and only then replaces itself with the packaged hypridle executable.

The deployed version-2 state is Screen saver `never`, Display `never`, Suspend
`never`, Lock `none`, effect `colormix`, and Caffeine off. This produces zero
listeners. Version-1 migration preserves existing timeout and lock selections
while defaulting the new effect field to `colormix`.

Zig Screensaver capability is not a preference. The backend asks the baseline
`vanhyprarch-screensaver` manager and publishes
`screensaver_capability=installed|absent|incomplete` in status version 3,
together with stored and effective screensaver/lock values. Only a valid marker
plus fully validated pinned payload is installed. When capability is absent or
incomplete, effective Screensaver is `never`, no player listener is rendered,
and stored `lock=screensaver` projects temporarily to Display, else Suspend,
else None. Stored screensaver, effect, and lock values are not rewritten for
unexpected damage, so Repair can restore the exact configuration.
Periodic backend status observes the capability annotation in the deployed
fragment. A transition from installed to incomplete/absent (or back) triggers
an exact-owned player stop and the normal validated transactional fragment
deployment before status returns. Cursor restoration failure remains visible
after process termination and safe configuration publication;
unrelated fragment incoherence still fails closed instead of being overwritten.

## Command interface

```text
vanhyprarch-idle status
vanhyprarch-idle session-start
vanhyprarch-idle apply
vanhyprarch-idle configure <screensaver> <display> <suspend> <lock>
vanhyprarch-idle set <screensaver|display|suspend|lock|effect> <value>
vanhyprarch-idle caffeine <on|off>
vanhyprarch-idle screensaver-effect
vanhyprarch-idle reconcile-screensaver <installed|absent>
vanhyprarch-idle screensaver-uninstall-plan
vanhyprarch-idle remove-screensaver
```

`status` emits stable `key=value` lines for later QML parsing. Before reporting
them, it compares the deployed fragment with the expected fragment for current
preferences and runtime Caffeine state; the non-operational effect annotation
is ignored because effect-only changes deliberately do not apply the fragment.
An incoherent fragment produces an error instead of a misleading logical
listener count. `configure`
updates all durable fields as one validated transaction; `set` changes one
field and rejects the result if it breaks ordering or lock ownership. `apply`
regenerates runtime configuration without changing preferences. Effect-only
updates persist without applying or restarting hypridle; the controller reads
the selection through `screensaver-effect` when starting. The `validate` and
`render` commands are development aids.

## Generated configuration

The static `home/.config/hypr/hypridle.conf` sources
`vanhyprarch-idle.conf`. The fragment is a generated live projection, not a
tracked release artifact. The backend writes it atomically from stored
preferences. When Caffeine is active, the fragment contains no listeners and
therefore performs no automatic screensaver, display-off, lock, or suspend
action.

An enabled and authoritatively available screensaver generates one
inhibitor-aware listener. Its timeout starts `vanhyprarch-screensaver start
--idle`; genuine-input resume stops it. If Screensaver owns locking, resume
calls the controller's `resume-lock`, which requests
`loginctl lock-session` and disarms duplicate exit locking only after that
request succeeds; the general unlock command then stops the saver. The listener
never ignores legitimate inhibitors.

The final production chain started ColorMix through the controller at +10.034
seconds and fired a harmless later listener at +20.036 seconds, 10.002 seconds
afterward. Startup did not reset hypridle. Genuine keyboard input emitted
resume at +23.291 seconds, stopped the owned player, and did not leak the first
key to Foot underneath. The former S-1 helper listener is intentionally absent.
See the [compatibility register](compatibility.md).

An enabled display stage uses Hyprland's native 0.56 Lua dispatcher:

```text
hyprctl dispatch 'hl.dsp.dpms({ action = "disable" })'
hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'
```

If Screen saver or Turn off display owns locking, the display timeout requests
the lock before disabling DPMS. Otherwise it only disables DPMS. Activity
always requests DPMS enable.

An enabled suspend stage runs `systemctl suspend`. The static
`before_sleep_cmd` delegates to `vanhyprarch-idle before-sleep`, which requests
`loginctl lock-session` when any automatic lock point is selected. With Lock
`none` or Caffeine active it does nothing. This preserves manual lock while
making Lock `none` and Caffeine meaningful even for pre-sleep handling.

## Deployment and rollback

During development, `~/.local/bin/vanhyprarch-idle` may be a symlink to the
tracked backend. The baseline controller must be in hypridle's inherited PATH.
The player is required only when its validated optional capability is
installed; production
installs regular executables in `$HOME/.local/bin` without depending on a Git
checkout. A future shared bootstrap must deploy the static main configuration
and initialize the default preference file. It must not deploy generated
fragment bytes: the first `session-start` creates a missing fragment from the
preserved preference before hypridle starts.

An earlier real reboot showed that bare hypridle did not inherit that directory,
so startup temporarily used a shell to prepend it. The unified Hyprland session
PATH subsequently passed a full logout/login test in Foot, Quickshell,
hypridle, and the screenshot workflow, and per-process PATH compensation was
removed. That policy continues to expose `$HOME/.local/bin` to normal launched
session applications.

The first controlled Caffeine reboot validation established a narrower startup
fact: the Hyprland process's own inherited `/proc` environment did not contain
`$HOME/.local/bin`, even though the interactive shell did. Hyprland therefore
invokes the backend through
`"exec " .. sessionHome .. "/.local/bin/vanhyprarch-idle session-start"`. This is the
deterministic installed public-command path, not a hardcoded user's home, a
system-PATH relocation, or a per-process PATH override. Current `hl.exec_cmd`
behavior runs command strings through a transient `/bin/sh -c`; the leading
shell builtin `exec` replaces that shell in place with the backend. The backend
therefore sees Hyprland as its direct parent. Because `hyprland.start` can run
before Hyprland publishes its runtime instance lock, `session-start` does not
call `hyprctl instances`. It reads its actual PPID from `/proc`, requires that
process to be the current user's exact `/usr/bin/Hyprland`, and verifies the
parent start time before and after the executable and UID checks to reject PID
reuse. Normal manual apply and Caffeine transactions retain global instance
discovery because their replacement launch uses `hyprctl -i` after startup.
The command rejects root, acquires the normal backend lock, validates durable
preferences, forces the new session's Caffeine state off,
validates and atomically publishes the resulting fragment, and verifies that no
hypridle is already running while `hypridle.service` remains disabled and
inactive. It explicitly unlocks and closes the backend lock descriptor, then
uses direct `exec /usr/bin/hypridle -v`. No wrapper or additional process
remains: the resulting daemon retains Hyprland as its direct parent and inherits
the session environment and PATH unchanged. Failure returns nonzero without
starting hypridle against the prior fragment. A startup failure also atomically
overwrites one mode-0600 diagnostic line at
`${XDG_RUNTIME_DIR}/vanhyprarch/session-start-error.log`; successful
reconciliation removes a stale record before publication. The record is
runtime-only, bounded, and leaves no open descriptor across the final exec.

This startup reconciliation closes a security-relevant lifecycle gap: a
successful prior-session Caffeine ON transaction had persisted its zero-listener
projection after the runtime marker disappeared at reboot. The UI could report
OFF while screensaver, display, suspend, and their selected automatic-lock path
were absent from the newly started daemon. Durable timeout, lock, and effect
preferences remain unchanged.

The final controlled acceptance test enabled Caffeine, confirmed its
zero-listener projection, and rebooted without disabling it. Before any Power &
Idle interaction after login, the runtime marker and startup-error record were
absent, the fragment had a new login-time modification time and contained the
configured 120-second screensaver, 300-second display/lock, and 600-second
suspend listeners, and status reported Caffeine off with three effective
listeners. One `/usr/bin/hypridle -v` remained the direct child of
`/usr/bin/Hyprland`, with the packaged service disabled and inactive. The
screensaver fired after 120 seconds without a manual Caffeine or timeout
transaction, directly validating the original failure scenario.

The backend validates the candidate fragment with a disconnected verbose
hypridle parse before deployment. It requires exactly one existing hypridle
whose executable, exact supported argument vector, and parent identify it as
the direct Hyprland-owned daemon, and requires the packaged user service to
remain disabled and inactive.

It reads PATH from that exact validated daemon, verifies the required commands
against that PATH, saves the previous fragment, replaces the file atomically,
stops only that daemon, and launches one replacement through Hyprland's Lua
`hl.exec_cmd` API with the captured daemon PATH. The replacement log must show
the exact expected listener count. Any failure restores the prior fragment and
attempts to launch and validate one daemon against the previous count using the
same captured PATH.
Preference and Caffeine updates are also rolled back if the effective
configuration cannot be applied.

## Quickshell panel

The dock order is:

1. Power
2. Clock/calendar
3. Info/Shortcuts
4. Theme
5. Power & Idle
6. Display
7. Audio
8. Network
9. Bluetooth
10. System tray

This list follows the lower control area from bottom to top.

The panel always shows Caffeine, Turn Off Display, Suspend, and Automatic Lock
with None, Display Off, and Suspend. When Zig Screensaver is installed, Screen
Saver Effect and Screensaver appear between Caffeine and Turn Off Display, and
Screensaver is selectable as the Automatic Lock choice only while that stage is
enabled.
Absent and incomplete components leave no disabled row or empty placeholder.

Automatic Lock is not a separate timeout. It selects which configured stage
locks the session: for example, Screensaver at 120 seconds and Display at 300
seconds with `lock=display` starts the saver at 120 without locking and locks
when Display begins at 300. Deliberate uninstall atomically persists
`screensaver=never`, `effect=colormix`, and maps `lock=screensaver` to Display,
else Suspend, else None; other lock choices and Display/Suspend preferences are
preserved. The confirmation UI discloses that destination before removal.

`lock=screensaver` intentionally keeps the native saver visible while idle.
Normal activity asks the session to lock before the desktop can reappear, so
authentication protects leaving that stage without placing hyprlock over the
saver at timeout. The idle controller records this protection on the owned
process; an unexpected player exit requests the same session lock before it
restores the cursor. The bounded manual `test` command never arms this policy.
Display and Suspend retain their established stage behavior.

While the optional component is damaged, baseline Display and Suspend edits
remain subject to the stored ordering invariant. The backend does not rewrite
the dormant Screensaver timeout to make a newly requested value fit; the user
may repair or deliberately uninstall the component if that conservative rule
blocks a desired ordering change.

A single global
controller owns backend processes and parsed state; screen-bound buttons and
popups follow the existing `Quickshell.screens` delegate lifecycle.

Installed Papirus provides exact icons named `preferences-system-power` and
`caffeine`. Use the former normally and the latter while Caffeine is active.
The panel and passive synchronization behavior have passed manual visual
review, including effect persistence. The complete production screensaver
chain is validated. Controlled manual tests also passed for real DPMS,
suspend/resume, manual lock and password unlock, automatic lock at the Screen
saver and Display stages, dismissal before a later Display lock without a
password, cursor restoration, and cleanup without a residual lock or player.
No double-lock was observed. Physical multi-monitor acceptance and remaining
lock-at-suspend/Caffeine combinations are not implied by those results; see
[current state](current-state.md).
