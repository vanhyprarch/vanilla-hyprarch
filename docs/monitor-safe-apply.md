# Monitor Safe Apply backend

## Status and invariant

The runtime backend has been deployed and validated through a temporary scale
change from 1.25 to 1.50 and verified automatic rollback. Phase B3A adds the
repository-only persistence and reconciliation foundation. It is not connected
to the Monitor panel, and production persistence remains deliberately disabled
until a separate controlled live acceptance.

The invariant is: **an unconfirmed display configuration is never persisted**.
The v1 editable fields are one advertised resolution/refresh mode tuple and
per-output scale. Position, output enablement, transform, mirroring, bit depth,
HDR, wide color, ICC, VRR, and brightness are not editable. Those observable
monitor properties are protected during a transaction. Brightness remains a
separate DDC operation, and Text Size remains one unrelated global preference.

## Authority and lifecycle

`vanhyprarch-monitor` is the sole transaction authority. Its state progression
is:

```text
preparing -> applying -> temporary-active -> committing -> committed
                                      \-> reverting -> reverted
```

Any state that may have attempted a runtime mutation remains recovery-armed
until rollback or commit is authoritatively verified. `rollback-failed` retains
recovery authority for another bounded recovery invocation.
`instance-vanished` is terminal only because the helper proves that the exact
bound compositor process is gone and never follows a replacement instance.

The confirmation deadline is backend monotonic time and begins only after
fresh full-topology readback verifies the candidate. The default presentation
window is ten seconds. A later UI may display the remaining time, but does not
own it.

## Runtime transaction

The helper binds the transaction to the exact Hyprland instance signature,
PID, process start time, executable device/inode, connector, available physical
make/model/serial/description identity, and transaction UUID. It reads
authoritative state with:

```text
hyprctl --instance <signature> -j monitors all
```

It applies the candidate through connector-specific Lua evaluation:

```text
hyprctl --instance <signature> eval 'hl.monitor({...})'
```

Hyprland 0.56.2 overlays these fields on an existing rule only when its output
name exactly equals the requested connector. Before any journaled mutation, the
backend therefore requires one unambiguous exact connector profile in the
machine file, rejects every description-addressed machine profile, rejects a
same-connector override, and proves that the selected profile's mode and scale
are replaceable. A catch-all-only, `desc:`-only, missing, or duplicate profile
cannot reach `eval`; the backend never relies on Hyprland's new-rule defaults.

An `ok` response is only command acceptance. Resolution and refresh must match
the selected advertised tuple, with refresh normalized to integer millihertz
and a 5-millihertz readback tolerance. The requested value must also be the
unique nearest two-decimal advertised refresh; a boundary tie fails closed, so
an adjacent 10-millihertz catalogue entry cannot be accepted accidentally.
Duplicate public mode strings are one selectable entry because Hyprland exposes
no identity that distinguishes them. Catalogue comparison uses a sorted set of
resolution/two-decimal-refresh tuples, making list order and duplicate count
irrelevant while preserving genuine catalogue changes. Scale must pass the
bounded 0.5 through 4.0 and 1/120-increment preflight, then match readback
within one millionth. Full-topology validation indexes outputs by connector and
physical identity rather than JSON order or numeric monitor ID. It rejects
physical-identity changes, added or removed outputs, protected-field drift,
changes to another output's owned fields, or a result with no usable output.
The generated candidate and rollback calls contain exactly `output`, `mode`,
and `scale`; they do not intentionally write position, transform, mirror,
bit depth, color-management intent, VRR, enablement, reserved area, or any
other rule field. Values exposed by the authoritative monitor JSON remain
protected readback state; ICC profile state is not exposed by that Hyprland
0.56.2 response and is therefore not claimed as directly observable.

The Hyprland 0.56.2 JSON boundary follows `CHyprCtl::getMonitorData()` exactly:
physical serial is read from `serial`, while the direct protected color fields
are `colorManagementPreset`, `sdrBrightness`, `sdrSaturation`,
`sdrMinLuminance`, and `sdrMaxLuminance`. Required consumed keys and their
types fail closed. Unrelated additional upstream keys are ignored so a new
informational field does not break readback; the project-owned transaction
journal retains its separate exact-key, unknown-key-rejecting schema.

All production subprocesses have an explicit five-second timeout, including
`hyprctl eval`, `hyprctl -j monitors all`, ordinary `hyprctl reload`,
`hyprctl configerrors`, the client-side `systemctl --user start`, and the
prospective verifier. Five seconds is conservative for local IPC and for the
installed verifier, which completes in about 0.05 seconds, while remaining
bounded beneath the service stop limit. Reload-event waits are separately
bounded to 1.5 seconds before and after an ordinary reload fallback.
Timeout during apply enters rollback; timeout during rollback leaves
`rollback-failed` recovery-armed for one later bounded retry. There is no
production config-validation subprocess in B1; a future verifier must use the
same explicit-bound rule.

Primary rollback sends another connector-specific `hl.monitor()` containing
only the snapshot mode and scale, followed by full-topology readback. A normal
rollback does not reload the complete Hyprland configuration. If the bound
instance vanished, no command is sent to another instance. If the connector
now identifies a different display, no snapshot is applied to it.

## Journal, lock, and supervision

The private `${XDG_RUNTIME_DIR}/vanhyprarch/monitor-safe-apply/` directory holds
one version-2 atomic `transaction.json`, one advisory `transaction.lock`, and
one version-1 `control.sock`. Directory and file ownership and permissions are
validated; the journal and lock are mode `0600`, the directory is mode `0700`,
and malformed or unknown journal schemas fail closed. Every journal publication
writes and `fsync`s a same-directory temporary file, atomically replaces the
journal, then `fsync`s its parent directory. A crash therefore leaves the prior
complete state or the next complete state; a truncated or semantically
inconsistent record authorizes no recovery command. Exact machine and user
override bytes, hashes, stat identity, ownership and modes are recovery material,
not a second monitor preference.

The static, non-enabled
`vanhyprarch-monitor-safe-apply.service` runs only for a requested transaction.
It has a 90-second `RuntimeMaxSec` hard bound and invokes `recover` through
`ExecStopPost` after normal or abnormal service termination. Recovery is
idempotent: verified `committed`, `reverted`, or proven `instance-vanished`
transactions need no action; every other readable state takes one bounded
rollback path. The service is independent of Quickshell lifetime.

The small newline-delimited JSON socket protocol supports version-1 `begin`,
`status`, `confirm`, and `revert` requests. Candidate requests have exactly the
connector, width, height, refresh, and scale fields. Quickshell will eventually
be only a client of this protocol.

## Persistence and machine-profile boundary

The persistence foundation locates exactly one existing explicit connector
profile, preserves unrelated bytes and comments, replaces only its mode and
scale representation, rejects machine/override hash races,
and atomically replace a fixture file with preserved mode and ownership.
Recovery restores exact original bytes only when the current hash is either
the original or the transaction's recorded candidate hash. A different hash
is an external edit and is never overwritten.

Prospective validation stages the managed Hyprland entrypoint and its complete
managed Lua subtree with the transaction's exact override bytes and candidate
machine bytes. The installed `Hyprland --verify-config` runs with a five-second
bound inside Bubblewrap with a private mount, PID, IPC, network, and runtime
namespace. The staged tree is read-only to the verifier and the live user bus
is absent. Exit status zero is the authority; human-oriented stdout is retained
only as a diagnostic. This containment is required because Hyprland 0.56.2
executes Lua callbacks while verifying, including the project's
`config.reloaded` keyboard reconciliation hook.

After an explicit confirmation, the durable sequence is:

```text
temporary-active
-> committing / candidate-planned
-> candidate-installed
-> candidate-reloaded
-> candidate-verified
-> committed
```

The watcher event socket is armed before replacement. Atomic replacement uses
a same-directory temporary file, restrictive permissions, complete write,
file `fsync`, `os.replace`, and parent-directory `fsync`. A watched
`configreloaded` event is accepted; if it does not arrive within 1.5 seconds,
the backend issues one ordinary, instance-bound `hyprctl reload` and requires
the event. It never uses `reload full-reset`. Clean `configerrors` and fresh
full-topology readback must then prove the persisted candidate effective. The
previous temporary runtime rule is not reapplied to make reconciliation pass.
Recovery remains armed through `candidate-verified` and is disarmed only by the
atomic terminal `committed` publication.

If verification, replacement, reload, configuration-error, or post-reload
readback fails, the backend restores original machine bytes only while it can
prove that the file is transaction-owned, reconciles the restoration, and then
uses the normal targeted runtime mode/scale rollback. Durable milestones make
recovery deterministic if the process exits immediately before or after any
replacement or reload step. Every nonterminal commit milestone, including
`candidate-verified`, restores the original durable bytes and runtime state;
only the terminal `committed` publication is retained. Unrelated bytes remain
untouched and recovery-armed.

The production authority still intentionally substitutes a disabled persister
and disabled reload coordinator. A production `confirm` therefore cannot write
the live machine file and takes the normal rollback path. The B3A machinery is
exercised only with fixture paths and isolated verifier trees; enabling it is a
separate live acceptance decision.

The public machine seed still contains only a catch-all rule. Safe Apply
requires an existing, unambiguous, explicit machine-owned output profile; it
does not edit the catch-all and never creates or infers a profile. Safe initial
materialization of explicit profiles is an unresolved fresh-install product
requirement that must be completed before Alpha release. The backend parser
permits multiple unique explicit connector profiles so that later
materialization does not require replacing the transaction architecture.

## Deferred live and UI work

A controlled phase must enable and exercise durable confirmation on the live
machine, including watcher reload, post-reload readback, and protected
subsystem checks. Quickshell controller and confirmation-overlay integration
remain unimplemented. External reload invalidation during the temporary window
and safe fresh-install profile materialization also remain later work. The
existing Monitor panel is unchanged, and brightness remains out of scope.
