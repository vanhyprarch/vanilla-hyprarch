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
direct `Ly -> start-hyprland -> Hyprland` session as lifecycle owner. The
callback invokes `vanhyprarch-keyboard-sync session-start` in the new
compositor environment. That one-shot first uses an exact argument vector to
import only `HYPRLAND_INSTANCE_SIGNATURE`, `WAYLAND_DISPLAY`, and `DISPLAY`
into the systemd user manager, waits for success, and only then restarts the
unit. `XDG_RUNTIME_DIR` remains the stable user-manager value. A failed import
does not restart the service with a stale compositor identity. The restarted
helper therefore derives the exact command-socket path from its fresh process
environment and performs one startup reconciliation when that socket exists.

Hyprland 0.56.2 also schedules a broader systemd activation-environment import
immediately before emitting its ready event. That upstream process is
asynchronous, so its presence explains why the current manager environment is
correct but does not order completion before Vanilla's `hyprland.start`
callback. The explicit narrow import above closes that same-login restart race
without introducing UWSM or importing the full child environment.

The helper uses one long-lived Gio connection to the system bus for all
localed transport. It subscribes directly to
`org.freedesktop.DBus.Properties.PropertiesChanged`, filtered by locale1's
object path and interface payload, without binding the subscription to one
transient unique owner. A connection-scoped name watcher maintains the current
unique owner. The callback accepts a signal only when its actual D-Bus sender
equals that owner, so a late signal from a retired owner cannot trigger work.

Only reports involving one of the four X11 properties request reconciliation.
Locale and vconsole-only reports are ignored. Every accepted relevant report
causes an explicit complete `Properties.GetAll` on the same connection;
partial signal payloads and proxy caches are never assembled into a candidate
tuple. The read is bracketed by owner checks. If activation or an idle-exit
race changes the owner, that result is discarded and one reconciliation is
queued for the newest owner. GLib idle dispatch serializes work and coalesces
pending requests without a timer or polling loop. Every relevant report
fetches the complete localed tuple and reads the actual global Hyprland tuple.
Equality suppresses eval; a difference is validated and reconciled even when
the localed tuple equals the helper's last successful tuple. The cache is
observability only and cannot mask compositor runtime drift. A console-only
report schedules no localed fetch, Hyprland read, validation, or apply.

Startup, localed/IPC recovery, and the explicit config-reload path request the
same authority-versus-runtime reconciliation. The forced marker coalesces with
other pending work but never substitutes a cache comparison for the live
Hyprland read.

`systemd-localed` is D-Bus activated and may leave the bus when idle. Name
disappearance is an informational lifecycle transition: it clears the owner,
preserves Hyprland state, and schedules no retry. Every new owner appearance
requests a fresh full reconciliation, including after repeated idle exits.
An exact Gio file monitor watches the Hyprland command-socket path or its
nearest existing runtime ancestor. Socket appearance requests one fresh
reconciliation, disappearance causes no fallback, and a later appearance
reconciles the newest localed tuple. There is no sleep or recurring IPC probe.

A full Hyprland config reload reparses the static files and can replace runtime
XKB values. The managed `config.reloaded` callback asks systemd to reload the
existing service. `ExecReload` sends `SIGHUP`; the helper registers that signal
with `GLibUnix.signal_add()` and then re-reads both localed and Hyprland. It
applies only when the current global tuple differs, so the forced path does not
disturb an already-correct active group. Runtime `hl.config()` changes do not
emit `config.reloaded`, preventing a feedback loop.

## Validation and application

An empty `X11Layout` means localed has no graphical preference. The helper logs
that condition and leaves all current Hyprland XKB fields unchanged. It never
substitutes `us`.

Every non-empty candidate that differs from current Hyprland state is
preflighted with an exact argv invocation of:

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
