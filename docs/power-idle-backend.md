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
version=1
screensaver=never
display=never
suspend=never
lock=none
```

Timeout values are integer seconds. Enabled stages must be strictly ordered:
Screen saver < Turn off display < Suspend. Stages set to `never` are ignored in
that comparison. A lock point cannot name a disabled stage, and invalid changes
are rejected without rewriting another setting.

Caffeine is runtime-only. An atomic file containing `on` at
`${XDG_RUNTIME_DIR}/vanhyprarch/caffeine` means enabled; absence means off. It
never changes the durable preference file. Reapplying `caffeine on` or
`caffeine off` is idempotent and reconciles the generated configuration after
an interrupted operation. The default after login is off.

The migration defaults are Screen saver `never`, Display `never`, Suspend
`never`, Lock `none`, and Caffeine off. This produces zero listeners.

## Command interface

```text
vanhyprarch-idle status
vanhyprarch-idle apply
vanhyprarch-idle configure <screensaver> <display> <suspend> <lock>
vanhyprarch-idle set <screensaver|display|suspend|lock> <value>
vanhyprarch-idle caffeine <on|off>
```

`status` emits stable `key=value` lines for later QML parsing. `configure`
updates all durable fields as one validated transaction; `set` changes one
field and rejects the result if it breaks ordering or lock ownership. `apply`
regenerates runtime configuration without changing preferences. The
`validate` and `render` commands are development aids.

## Generated configuration

The static `home/.config/hypr/hypridle.conf` sources the managed
`vanhyprarch-idle.conf`. The backend writes the fragment atomically from the
stored preferences. When Caffeine is active, the fragment contains no
listeners and therefore performs no automatic screensaver, display-off, lock,
or suspend action.

An enabled screensaver generates the validated two-listener workaround for
Hyprland 0.56.2:

- At the selected timeout, an inhibitor-aware listener starts
  `vanhyprarch-screensaver` and has no resume action.
- One second earlier, an input-only listener arms with
  `ignore_inhibit = true`, runs only `/usr/bin/true` on timeout, and dismisses
  the saver on genuine input. If Screen saver owns locking, that resume command
  requests `loginctl lock-session` instead; the general unlock command then
  stops the saver.

The one-second lead is independent of the chosen timeout and guarantees the
dismiss notification is already idle before Foot maps. Consequently the
screensaver timeout must be at least two seconds. The action listener never
ignores legitimate inhibitors.

On the validated Hyprland 0.56.2 and hypridle 0.1.8 baseline, Foot mapping also
rearms later pending inhibitor-aware clocks. The resulting absolute-stage
timing limitation is confirmed but not yet corrected; consult the
[compatibility register](compatibility.md) before changing listener generation.

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
backend. A future installer should place the executable in the user's PATH,
deploy the static main configuration and initial generated fragment, and create
the default preference file without depending on a Git checkout.

The backend validates the candidate fragment with a disconnected verbose
hypridle parse before deployment. It requires exactly one existing hypridle
whose executable and parent identify it as the direct Hyprland-owned daemon,
and requires the packaged user service to remain disabled and inactive.

It saves the previous fragment, replaces the file atomically, stops only that
validated daemon, and launches one replacement through Hyprland's Lua
`hl.exec_cmd` API with the existing daemon PATH. The replacement log must show
the exact expected listener and `ignore_inhibit` counts. Any failure restores
the prior fragment and attempts to launch and validate one daemon against the
previous counts. Preference and Caffeine updates are also rolled back if the
effective configuration cannot be applied.

## Quickshell panel

The dock order is:

1. System Tray
2. Network
3. Audio
4. Monitor
5. Power & Idle
6. Theme
7. Clock
8. Power

The panel begins with **Caffeine / Keep computer awake**, followed by Screen
saver, Turn off display, and Suspend timeout controls. Each stage can be
`Never` and can be selected as the one automatic lock point. A single global
controller owns backend processes and parsed state; screen-bound buttons and
popups follow the existing `Quickshell.screens` delegate lifecycle.

Installed Papirus provides exact icons named `preferences-system-power` and
`caffeine`. Use the former normally and the latter while Caffeine is active.
The panel and passive synchronization behavior have passed manual visual
review; integrated idle actions remain pending.
