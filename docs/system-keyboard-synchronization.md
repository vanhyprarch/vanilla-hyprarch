# System keyboard synchronization

Vanilla HyprArch projects the system graphical keyboard configuration into the
running Hyprland session. The projection is intentionally one-way:

| Layer | Authority |
| --- | --- |
| Graphical XKB preference | `systemd-localed`, through `org.freedesktop.locale1` |
| Runtime projection | `vanhyprarch-keyboard-sync` |
| Effective global compositor state | Hyprland `input:kb_*` runtime properties |
| Active layout/group | Hyprland and user interaction; never the synchronizer |
| Per-device rules | Machine/user Hyprland configuration; higher-precedence exceptions |
| Console keymap | `VConsoleKeymap`; independent when changed with `localectl --no-convert` |

The helper does not persist a second graphical keyboard preference. It reads
`X11Layout`, `X11Model`, `X11Variant`, and `X11Options` as one complete tuple
from `/org/freedesktop/locale1` on the system bus. Exact strings are preserved,
including empty model/variant/options fields, ordered options, comma-separated
layout lists, and positional empty variants.

## Reconciliation

The static `vanhyprarch-keyboard-sync.service` is restarted by the managed
`hyprland.start` callback. Restarting rather than enabling the unit keeps the
direct `Ly -> start-hyprland -> Hyprland` session as lifecycle owner and
refreshes the service's compositor environment after a same-login Hyprland
restart. The helper performs one startup reconciliation as soon as the exact
Hyprland command socket exists.

The helper uses a Gio D-Bus proxy to observe standard
`org.freedesktop.DBus.Properties.PropertiesChanged` notifications. Only
reports involving one of the four X11 properties request reconciliation.
Locale and vconsole-only reports are ignored. Every relevant report causes a
fresh complete `GetAll`; partial signal payloads are never assembled into a
candidate tuple. GLib idle dispatch serializes work and coalesces pending
requests without a timer or polling loop.

The helper also remembers the last observed and last successfully projected
X11 tuple. If systemd reports an X11 property during a console transaction but
the complete X11 tuple is unchanged, an ordinary event does not apply anything,
even if unrelated runtime drift exists. Startup, localed/IPC recovery, and the
explicit config-reload path are forced reconciliations: they still read current
Hyprland state because the compositor projection may have been recreated.

`systemd-localed` is D-Bus activated and may leave the bus when idle. The proxy
tracks its name owner. Disappearance preserves the current Hyprland state;
reappearance requests a fresh full reconciliation. An exact Gio file monitor
watches the Hyprland command-socket path or its nearest existing runtime
ancestor. Socket appearance requests one fresh reconciliation, disappearance
causes no fallback, and a later appearance reconciles the newest localed tuple.
There is no sleep or recurring IPC probe.

A full Hyprland config reload reparses the static files and can replace runtime
XKB values. The managed `config.reloaded` callback asks systemd to reload the
existing service. `ExecReload` sends `SIGHUP`; the helper then re-reads both
localed and Hyprland. It applies only when the current global tuple differs, so
the forced path does not disturb an already-correct active group. Runtime
`hl.config()` changes do not emit `config.reloaded`, preventing a feedback
loop.

## Validation and application

An empty `X11Layout` means localed has no graphical preference. The helper logs
that condition and leaves all current Hyprland XKB fields unchanged. It never
substitutes `us`.

Every non-empty candidate is preflighted with an exact argv invocation of:

```text
/usr/bin/xkbcli compile-keymap --test --rules evdev \
  --model <exact> --layout <exact> --variant <exact> --options <exact>
```

Failure preserves the running tuple and waits for a future event. No candidate
reaches Hyprland without passing this gate.

The helper reads the four global Hyprland values before applying. An exact
match suppresses the eval even if the helper's previous successful cache is
stale. A changed tuple is encoded as a byte-exact Lua string and passed without
a shell in one argv call:

```text
/usr/bin/hyprctl eval 'hl.config({ input = { ...four fields... } })'
```

`kb_rules` is not changed. After a successful eval the helper reads all four
global values again and requires an exact match. It records success only after
that verification.

Before applying, the helper retains the prior four-field runtime tuple. An
eval failure, readback failure, or mismatch causes one rollback attempt to the
preflighted prior tuple followed by exact readback. Rollback never loops and
never invents a fallback. Failures and requested/prior tuples are logged to the
user journal.

## Deliberate non-ownership

The helper never calls `switchxkblayout`, reads or stores active layout indexes
or keymap names, enumerates keyboard endpoints, or writes per-device rules.
User-selected groups therefore remain endpoint-local runtime state. A genuine
configured-tuple change may cause Hyprland to rebuild group state; an identical
tuple causes no eval.

Hyprland applies current global input configuration to keyboards connected
later, so this design has no keyboard-hotplug watcher. Explicit per-device
rules remain machine/user-owned and naturally override global values.

The helper needs no elevated privileges. Reading and subscribing to locale1 is
unprivileged, and same-user Hyprland IPC is unprivileged. Changing localed
state, including any PolicyKit decision for `localectl set-*`, is outside the
synchronizer.

systemd's service manager is the singleton authority. An additional advisory
runtime lock would add a second lifecycle mechanism and stale-lock recovery for
no current supported caller, so the prototype deliberately omits one. Manual
direct invocation is diagnostic and unsupported; normal startup always uses
the unit.

## Transitional safety net

The development machine's private machine configuration still contains its
explicit Italian `hl.config({ input = ... })` block. It is a temporary migration
safety net, not a public default, and this repository implementation does not
edit or remove it. Removal requires all of the following controlled live
checks while it remains available for recovery:

1. daemon startup and initial reconciliation;
2. real localed D-Bus change propagation;
3. config-reload reconciliation without a feedback loop;
4. service restart and IPC disappearance/reappearance behavior;
5. one cold logout/login with the expected Italian effective state.

Only after those checks pass may a separate migration remove the live block.
The create-once machine seed remains keyboard-neutral.
