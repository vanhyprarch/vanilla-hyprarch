# Monitor Safe Apply backend

## Status and invariant

Phase B1 implements and deterministically tests the repository-only backend
foundation. It is not connected to the Monitor panel, has not been deployed,
and has not performed a live mode or scale change. Production persistence is
deliberately disabled until the controlled Phase B2 integration.

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

An `ok` response is only command acceptance. Resolution and refresh must match
the selected advertised tuple, with refresh normalized to integer millihertz
and a 10-millihertz readback tolerance. Scale must pass the bounded 0.5 through
4.0 and 1/120-increment preflight, then match readback within one millionth.
Full-topology validation rejects physical-identity changes, added or removed
outputs, protected-field drift, changes to another output's owned fields, or a
result with no usable output.

Primary rollback sends another connector-specific `hl.monitor()` containing
only the snapshot mode and scale, followed by full-topology readback. A normal
rollback does not reload the complete Hyprland configuration. If the bound
instance vanished, no command is sent to another instance. If the connector
now identifies a different display, no snapshot is applied to it.

## Journal, lock, and supervision

The private `${XDG_RUNTIME_DIR}/vanhyprarch/monitor-safe-apply/` directory holds
one version-1 atomic `transaction.json`, one advisory `transaction.lock`, and
one version-1 `control.sock`. Directory and file ownership and permissions are
validated; the journal and lock are mode `0600`, the directory is mode `0700`,
and malformed or unknown journal schemas fail closed. Exact machine and user
override bytes, hashes, stat identity, ownership and modes are recovery
material, not a second monitor preference.

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

Phase B1 includes fixture-tested helpers that locate exactly one existing
explicit connector profile, preserve unrelated bytes and comments, replace
only its mode and scale representation, reject machine/override hash races,
run an injected prospective verifier, and atomically replace a fixture file
with preserved mode and ownership. Recovery can restore exact original bytes
only when the current hash is either the original or the transaction's recorded
candidate hash.

The production authority intentionally substitutes a disabled persister, so a
Phase B1 `confirm` cannot write the live machine file and instead takes the
normal rollback path. Phase B2 must add complete isolated Hyprland config
verification, durable write/reload/reconciliation, post-reload readback, and
only then enable production commit.

The public machine seed still contains only a catch-all rule. Safe Apply
requires an existing, unambiguous, explicit machine-owned output profile; it
does not edit the catch-all and never creates or infers a profile. Safe initial
materialization of explicit profiles is an unresolved fresh-install product
requirement that must be completed before Alpha release. The backend parser
permits multiple unique explicit connector profiles so that later
materialization does not require replacing the transaction architecture.

## Deferred Phase B2 work

Phase B2 owns Quickshell controller and confirmation-overlay integration,
Hyprland event/reload invalidation, production persistence enablement,
controlled deployment, and guarded live mode/scale validation. The existing
Monitor panel is unchanged in Phase B1.
