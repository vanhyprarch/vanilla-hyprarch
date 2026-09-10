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
an interrupted operation. The default after login is off.

The deployed version-2 state is Screen saver `never`, Display `never`, Suspend
`never`, Lock `none`, effect `colormix`, and Caffeine off. This produces zero
listeners. Version-1 migration preserves existing timeout and lock selections
while defaulting the new effect field to `colormix`.

## Command interface

```text
vanhyprarch-idle status
vanhyprarch-idle apply
vanhyprarch-idle configure <screensaver> <display> <suspend> <lock>
vanhyprarch-idle set <screensaver|display|suspend|lock|effect> <value>
vanhyprarch-idle caffeine <on|off>
vanhyprarch-idle screensaver-effect
```

`status` emits stable `key=value` lines for later QML parsing. `configure`
updates all durable fields as one validated transaction; `set` changes one
field and rejects the result if it breaks ordering or lock ownership. `apply`
regenerates runtime configuration without changing preferences. Effect-only
updates persist without applying or restarting hypridle; the controller reads
the selection through `screensaver-effect` when starting. The `validate` and
`render` commands are development aids.

## Generated configuration

The static `home/.config/hypr/hypridle.conf` sources the managed
`vanhyprarch-idle.conf`. The backend writes the fragment atomically from the
stored preferences. When Caffeine is active, the fragment contains no
listeners and therefore performs no automatic screensaver, display-off, lock,
or suspend action.

An enabled screensaver generates one inhibitor-aware listener. Its timeout
starts `vanhyprarch-screensaver`; genuine-input resume stops it. If Screen saver
owns locking, resume requests `loginctl lock-session` instead and the general
unlock command stops the saver. The listener never ignores legitimate
inhibitors.

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

During development, `~/.local/bin/vanhyprarch-idle` is a symlink to the tracked
backend. The controller and separately installed `vanhyprarch-zig-player` must
both be in hypridle's PATH; the pinned player installer defaults to
`$HOME/.local/bin`. A future shared bootstrap must deploy the static main
configuration and initial generated fragment and create the default preference
file without depending on a Git checkout.

On normal Hyprland startup, hypridle is launched through
`sh -lc 'export PATH="$HOME/.local/bin:$PATH"; exec hypridle -v'`. The shell is
replaced by `exec`, leaving `/usr/bin/hypridle` directly parented by Hyprland
while exposing the user-local Vanilla HyprArch executables in its `PATH`.

A real reboot validated this cold-start contract, followed by a successful
Power & Idle apply and a complete 2-minute screensaver / 5-minute display-off /
10-minute suspend sequence with normal resume.

The backend validates the candidate fragment with a disconnected verbose
hypridle parse before deployment. It requires exactly one existing hypridle
whose executable and parent identify it as the direct Hyprland-owned daemon,
and requires the packaged user service to remain disabled and inactive.

It saves the previous fragment, replaces the file atomically, stops only that
validated daemon, and launches one replacement through Hyprland's Lua
`hl.exec_cmd` API with the existing daemon PATH. The replacement log must show
the exact expected listener count. Any failure restores the prior fragment and
attempts to launch and validate one daemon against the previous count.
Preference and Caffeine updates are also rolled back if the effective
configuration cannot be applied.

## Quickshell panel

The dock order is:

1. Power
2. Clock/calendar
3. Theme
4. Power & Idle
5. Display
6. Audio
7. Network
8. Bluetooth
9. System tray

This list follows the lower control area from bottom to top.

The panel begins with **Caffeine / Keep computer awake**, followed by a compact
screensaver-effect choice and the Screen saver, Turn off display, and Suspend
timeout controls. Effect choice persists even when Screen saver is `Never`.
Each stage can be
`Never` and can be selected as the one automatic lock point. A single global
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
