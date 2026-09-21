# Monitor Safe Apply backend

## Status and invariant

The deployed schema-v2 backend was validated through a temporary scale change
from 1.25 to 1.50 and verified automatic rollback. That deliberately low-risk
exercise validated the runtime transaction engine; it does not define the
final Scale UX. This repository-only policy realignment introduces schema v3
and is not deployed or connected to the Monitor panel.

The final policy has two transaction classes:

- **safe-confirmed:** resolution/refresh as one mode tuple, bit depth (8 or 10
  bpc), or both. These changes are temporary until explicit confirmation and
  automatically roll back after approximately ten seconds.
- **immediate-validated:** per-output scale. It is applied, authoritatively
  read back, prospectively verified, and persisted immediately. Any technical
  failure restores the previous durable bytes and runtime scale; there is no
  human confirmation window.

The invariant remains: **an unconfirmed safety-critical display configuration
is never persisted**. Position, output enablement, transform, mirroring, HDR,
wide-color intent, ICC, VRR, and reserved area are not editable. Brightness
remains the Monitor panel's separate DDC/CI path. Text Size remains the existing
global TextSizeController/preference architecture.

## Authority and lifecycle

`vanhyprarch-monitor` is the sole authority for both policies. Safe-confirmed
state progression is:

```text
preparing -> applying -> temporary-active -> committing -> committed
                                      \-> reverting -> reverted
```

Any state that may have attempted a runtime mutation remains recovery-armed
until rollback or commit is authoritatively verified. `rollback-failed` retains
recovery authority for another bounded recovery invocation.
`instance-vanished` is terminal only because the helper proves that the exact
bound compositor process is gone and never follows a replacement instance.

Immediate Scale skips `temporary-active`:

```text
preparing -> applying -> committing -> committed
                         \-> reverting -> reverted
```

The confirmation deadline is backend monotonic time and begins only after
fresh full-topology readback verifies the candidate. The default presentation
window is ten seconds and exists only for mode/bitdepth candidates. A later UI
may display the remaining time, but does not own it. Scale has no deadline or
Confirm operation.

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
same-connector override, and proves that every candidate-owned field is
replaceable in that profile. A catch-all-only, `desc:`-only, missing, or
duplicate profile cannot reach `eval`; the backend never relies on Hyprland's
new-rule defaults.

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
within one millionth. Effective bit depth is proved only by `currentFormat`:
`XRGB8888`/`XBGR8888` mean 8 bpc and
`XRGB2101010`/`XBGR2101010` mean 10 bpc for Hyprland 0.56.2's output-selection
path. A 10-bit request that falls back to an 8-bit format fails verification;
the requested-state `m_enabled10bit` flag is not used as authority.

Full-topology validation indexes outputs by connector and
physical identity rather than JSON order or numeric monitor ID. It rejects
physical-identity changes, added or removed outputs, protected-field drift,
changes to another output's owned fields, or a result with no usable output.
Generated calls contain only their owned fields: `output` plus `mode`,
`bitdepth`, both, or `scale`. They do not intentionally write position,
transform, mirror, color-management intent, ICC, VRR, enablement, reserved
area, or another monitor-rule field. Mode-only and Scale operations require
DRM format and effective color state to remain unchanged. For bitdepth changes,
all persisted color intent and numeric effective color properties remain
protected; only the dependent DRM format and, with `cm="auto"` and no ICC,
effective color preset may change. Eight-bit auto must resolve to `srgb`;
effective ten-bit auto may be `wide` when supported or `srgb` otherwise. Any
other transition fails closed. ICC intent is preserved byte-for-byte even
though the JSON response does not expose its path.

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
`rollback-failed` recovery-armed for one later bounded retry.

Primary rollback sends another connector-specific `hl.monitor()` containing
only the safety-critical fields the candidate changed, or the prior Scale for
an immediate operation, followed by full-topology readback. A normal
rollback does not reload the complete Hyprland configuration. If the bound
instance vanished, no command is sent to another instance. If the connector
now identifies a different display, no snapshot is applied to it. Bitdepth
rollback restores the exact prior requested 8/10 rule from the machine-profile
snapshot, then requires the prior effective format and color state. It does not
mistake an effective 8-bit fallback for the previous requested rule intent.

## Journal, lock, and supervision

The private `${XDG_RUNTIME_DIR}/vanhyprarch/monitor-safe-apply/` directory holds
one version-3 atomic `transaction.json`, one advisory `transaction.lock`, and
one version-2 `control.sock`. Directory and file ownership and permissions are
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

The small newline-delimited JSON socket protocol supports version-2 `begin`,
`scale`, `status`, `confirm`, and `revert` requests. `begin` carries an optional
mode tuple and optional bitdepth, with at least one required. `scale` carries
only connector and scale and completes its persistence transaction in one
request. Quickshell will eventually be only a client of this protocol.

## Persistence and machine-profile boundary

The persistence foundation locates exactly one existing explicit connector
profile, preserves unrelated bytes and comments, replaces only the fields
owned by that candidate (mode, bitdepth, or scale), rejects machine/override
hash races, and atomically replaces the machine file with preserved mode and
ownership.
Recovery restores exact original bytes only when the current hash is either
the original or the transaction's recorded candidate hash. A different hash
is an external edit and is never overwritten.

Prospective validation stages the managed Hyprland entrypoint and its complete
managed Lua subtree with the transaction's exact override bytes and candidate
machine bytes. The installed `Hyprland --verify-config` runs with a five-second
bound inside Bubblewrap with a private mount, PID, IPC, network, and runtime
namespace. The staged tree is read-only to the verifier and the live user bus
is absent. Bubblewrap clears the inherited environment and supplies only a
synthetic home, staged XDG config/data paths, a private runtime path, `/usr/bin`
PATH, and a fixed locale. It exposes `/usr` and `/etc` read-only, creates
private `/run`, `/runtime`, `/home`, `/data`, and `/tmp`, and does not expose
`/run/user/<uid>`, the live Hyprland sockets, or the user D-Bus socket. Exit
status zero is the authority; human-oriented stdout is retained only as a
diagnostic. This containment is required because Hyprland 0.56.2 executes Lua
callbacks while verifying, including the project's `config.reloaded` keyboard
reconciliation hook. A real containment regression proves that staged Lua
cannot reach the user bus or Hyprland IPC, alter a host marker, or write the
read-only staged tree.

After an explicit safe-confirmed confirmation, the durable sequence is:

```text
temporary-active
-> committing / candidate-planned
-> candidate-installed
-> candidate-reloaded
-> candidate-verified
-> committed
```

Immediate Scale enters the same `committing` persistence milestones directly
after runtime readback. It neither enters `temporary-active` nor waits for a
client command. This shares prospective verification, atomic replacement,
reload reconciliation, post-reload readback, and durable rollback rather than
creating a weaker second persistence engine.

Atomic replacement uses a same-directory temporary file, restrictive
permissions, complete write, file `fsync`, `os.replace`, and parent-directory
`fsync`. The persistence reload watcher is armed only after the candidate file
is installed, the `candidate-installed` milestone is durable, and the current
file hash proves transaction ownership. A watched `configreloaded` event is
then accepted; if it does not arrive within 1.5 seconds, the backend issues one
ordinary, instance-bound `hyprctl reload` and requires the event. It never uses
`reload full-reset`. Clean `configerrors` and fresh full-topology readback must
then prove the persisted candidate effective. The previous temporary runtime
rule is not reapplied to make reconciliation pass. Recovery remains armed
through `candidate-verified` and is disarmed only by the atomic terminal
`committed` publication.

An exact-instance socket2 watcher is also armed before the temporary runtime
apply. Any `configreloaded` observed while applying, while temporary-active, or
after Confirm begins but before candidate replacement invalidates the
transaction. The backend stops the confirmation path and performs the normal
verified rollback even when current-state owned-field readback happens to look
identical. It never silently reapplies the temporary candidate. Reloads can be
treated as persistence-owned only after the durable `candidate-installed`
phase and candidate-file hash agree; timing alone is not evidence of ownership.
After every accepted reload, `configerrors` and authoritative monitor readback
remain mandatory. `monitor.layout_changed` is not required.

If verification, replacement, reload, configuration-error, or post-reload
readback fails, the backend restores original machine bytes only while it can
prove that the file is transaction-owned, reconciles the restoration, and then
uses the normal targeted owned-field runtime rollback. Durable milestones make
recovery deterministic if the process exits immediately before or after any
replacement or reload step. Every nonterminal commit milestone, including
`candidate-verified`, restores the original durable bytes and runtime state;
only the terminal `committed` publication is retained. Unrelated bytes remain
untouched and recovery-armed.

The production authority now wires the tested machine-file persister,
Bubblewrap prospective verifier, and exact-instance reload coordinator. This
makes the durable Confirm path available for the next controlled live
acceptance; it does not itself begin a transaction or write configuration.
Fixture and isolated verifier coverage remains the prerequisite, and durable
Confirm is not considered accepted until that separate live test passes.

The policy-aligned journal is strict schema version 3. It intentionally does
not interpret schema-v2 recovery material because the old candidate encoded
mode plus scale with different semantics. A backend upgrade must never cross a
nonterminal or recovery-required transaction from an older schema. The old
deployed helper must first prove that its journal is terminal and
recovery-disarmed, its lock is
unheld, and no control listener exists. Only then may controlled deployment
remove that old terminal runtime journal and install the new helper into clean
runtime state. Future schema changes require the same explicit upgrade protocol
or a separately reviewed migration; they must not guess compatibility.

The public machine seed still contains only a catch-all rule. Safe Apply
requires an existing, unambiguous, explicit machine-owned output profile; it
does not edit the catch-all and never creates or infers a profile. Safe initial
materialization of explicit profiles is an unresolved fresh-install product
requirement that must be completed before Alpha release. The backend parser
permits multiple unique explicit connector profiles so that later
materialization does not require replacing the transaction architecture.

## Deferred live and UI work

A controlled phase must first deploy schema v3 only after schema v2 is proven
idle with no recovery-required journal. Later phases separately exercise live
safe-confirmed Mode, live safe-confirmed bitdepth, immediate Scale, and durable
persistence, including watcher reload, post-reload readback, and protected
subsystem checks.
Quickshell controller and confirmation-overlay integration remain unimplemented.
Safe fresh-install profile materialization also remains later work. The
existing Monitor panel is unchanged. Its current direct Scale writer is not the
final backend integration, while its DDC/CI Brightness and global Text Size
ownership remain deliberately separate.
