# Monitor Safe Apply backend

## Status and invariant

The published schema-v5/protocol-v4/inspect-v3 backend and Monitor UI have completed single-monitor
live acceptance. Mode-only and bitdepth-only changes passed automatic timeout
rollback and durable Keep, Mode passed explicit Revert, and immediate Scale
passed a 1.25→1.50→1.25 durable persistence round trip. Escape and outside
dismissal both perform Revert. A same-process Quickshell reload during
`temporary-active` preserved the transaction ID and original backend deadline,
reconstructed the overlay, and still rolled back at that deadline. The earlier
temporary Scale exercise validated the rollback engine at lower risk; it does
not define the final Scale UX.

The repository's schema-v6/protocol-v5 follow-up adds one safe-confirmed
combination: an explicit Resolution change also owns configured Scale `auto`.
This lets Hyprland choose the new effective numeric Scale while preserving one
atomic apply/confirm/rollback boundary. This generation is fixture-tested and
has not yet replaced the published schema-v5/protocol-v4 deployment.

The published HDR extension advances the journal to schema 5, control protocol
4, and inspection schema 3. The final policy has two transaction classes:

- **safe-confirmed:** resolution/refresh as one mode tuple, configured Scale
  `auto` paired with an explicit Resolution change, bit depth (8 or 10 bpc),
  forced per-monitor HDR, global Automatic HDR policy, or any valid combination.
  These changes are temporary until explicit confirmation and automatically
  roll back after approximately ten seconds.
- **immediate-validated:** per-output scale. It is applied, authoritatively
  read back, prospectively verified, and persisted immediately. Any technical
  failure restores the previous durable bytes and runtime scale; there is no
  human confirmation window.

The invariant remains: **an unconfirmed safety-critical display configuration
is never persisted**. Position, output enablement, transform, mirroring,
wide-color capability overrides, ICC, and VRR are not editable. Reserved area
is also not editable, but is layer-shell-derived observability rather than
monitor-owned protected state. Brightness remains the Monitor panel's separate
DDC/CI path. Text Size remains the existing global
TextSizeController/preference architecture.

The per-monitor **HDR** policy has two states: **Off** restores the exact durable
non-HDR CM intent, while **Always On** forces `cm = "hdr"`. It does not report
whether an HDR signal is active: Hyprland 0.56.2 does not expose its internal
generic `inHDR()` result through monitor JSON. **Automatic HDR · All displays**
is a separate global policy whose Off/HDR/HDR (EDID) values map to
`render:cm_auto_hdr` 0/1/2. Every panel presents the same shared pending and
confirmed value. Forced HDR requires an effective 10-bit path; the backend
rejects 8-bit plus Always On instead of changing bit depth implicitly.

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
window is ten seconds and exists only for safe-confirmed candidates. The UI
displays the backend's remaining time but does not own it. Scale has no deadline
or Confirm operation.

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
name exactly equals the requested connector. It does not copy a catch-all rule
when a runtime call creates a new connector rule. Before any journaled runtime
mutation, the backend therefore requires one unambiguous exact connector
profile in the machine file, rejects every description-addressed machine
profile, rejects a same-connector override, and proves that every
candidate-owned field is replaceable in that profile. A fallback-only,
`desc:`-only, missing, or duplicate profile cannot reach `eval`; the backend
never relies on Hyprland's new-rule defaults.

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
Generated monitor calls contain only their owned fields: `output` plus `mode`,
`bitdepth`, `cm`, a valid combination, or `scale`. A Resolution change from an
explicit numeric Scale owns `mode` and `scale = 1` in that one call; a
configured Scale `auto` leaves `scale` absent. Global Automatic HDR uses a
separate `hl.config({ render = { cm_auto_hdr = ... } })` runtime mutation in
the same transaction authority. Neither path writes position, transform,
mirror, ICC, VRR, enablement, reserved area, or another monitor-rule field.
Mode-only and Scale operations require
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
The required `reserved` array remains parsed and exposed for observability, but
is not a protected monitor-state field: it is compositor output derived from
active layer-shell exclusive zones, not state owned or restorable by the
monitor backend.

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
only the safety-critical fields the candidate changed, including the prior
Mode and Scale together for the new combined candidate, or the prior Scale for
an immediate operation, followed by full-topology readback. A normal
rollback does not reload the complete Hyprland configuration. If the bound
instance vanished, no command is sent to another instance. If the connector
now identifies a different display, no snapshot is applied to it. Bitdepth
rollback restores the exact prior requested 8/10 rule from the machine-profile
snapshot, then requires the prior effective format and color state. It does not
mistake an effective 8-bit fallback for the previous requested rule intent.
Forced-HDR rollback restores the prior base CM runtime semantics and the exact
prior Mode/bitdepth values owned by a combined request. Global rollback restores
the exact previous effective renderer value; an omitted default remains omitted
in durable configuration unless the user confirms a deliberate global change.

## Journal, lock, and supervision

The published materialization generation uses journal schema 4, control
protocol 3, and inspection schema 2. The HDR candidate deliberately advances
these to schema 5, protocol 4, and inspection schema 3 because it adds CM base
intent, global renderer intent, new runtime mutations, and recovery data. Old
journals are never reinterpreted.
The Display gate removal leaves all three schemas unchanged: the obsolete
public `materialize` request is gone, while `begin` and `scale` invoke the same
internal transaction automatically when needed.

The private
`${XDG_RUNTIME_DIR}/vanhyprarch/monitor-safe-apply/` directory holds one atomic
`transaction.json`, one advisory `transaction.lock`, and one `control.sock`.
Directory and file ownership and permissions are validated; the journal and
lock are mode `0600`, the directory is mode `0700`, and malformed or unknown
journal schemas fail closed. Every journal publication
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

The small newline-delimited JSON socket protocol supports `begin`, `scale`,
`status`, `confirm`, and `revert` requests. `begin` carries an
optional mode tuple, its optional paired configured Scale `auto`, bitdepth,
forced-HDR policy, and global Automatic HDR value, with at least one required. Safe Apply
rejects Scale without Mode and any safe-confirmed Scale other than `auto`. `scale`
carries only connector and scale and completes its
persistence transaction in one request. When either mutation encounters a
supported fallback-only output, the authority first performs its internal
persistence-only materialization transaction. Quickshell is only a short-lived client of this protocol. Its
processes do not own or cancel the independently supervised transaction.

The separate `inspect` command is a versioned, read-only UI projection. It
uses the same Hyprland parser, canonical Mode catalogue, effective-bitdepth
rules, and explicit-profile/override checks as transaction preflight. It does
not start the service, create a journal, acquire mutation authority, invoke
`hl.monitor()`, or write configuration. It exposes normalized current state,
available Modes, Scale, effective bitdepth choices, physical identity, and
normalized explicit/fallback/materializable/conflict state, strict EDID-derived
HDR eligibility, exact base CM intent, and the global Automatic HDR policy;
QML does not parse raw `monitors all` JSON or decide materialization eligibility.
For Automatic HDR, inspection may project the effective candidate during an
unexpired `temporary-active` Safe Apply only after read-only validation of the
current compositor identity, owned authority lock, journal candidate, and
unchanged original machine and override snapshots. This is the expected interval
between runtime apply and durable Keep. Outside that exact transaction state,
the persistent/effective Automatic HDR mismatch remains unavailable and visible.

## HDR capability and durable intent

The backend enables forced HDR only when the bound connector's sysfs EDID is
unambiguous, structurally and checksum valid, matches the monitor's model, and
matches its serial when both sides publish one. It must also advertise both
BT.2020 colorimetry and PQ/ST2084. Two known non-empty serials that differ are a
hard mismatch. When either side has no serial, the output remains bound through
the existing connector/topology identity but EDID HDR capability is neutral
`unknown` and forced HDR remains unavailable. Explicit
`supports_hdr = -1` or `supports_wide_color = -1`, an ICC-owned output,
disabled color management, a malformed/unknown monitor rule, or an unavailable
10-bit path fails closed. Current wide color, current bit depth, or connector
name alone is never treated as HDR capability evidence.

When Vanilla confirms **Always On**, the machine profile contains `cm = "hdr"`
and one adjacent strict marker:

```lua
-- vanhyprarch-monitor-forced-hdr-base-v1: present:auto
cm = "hdr",
```

The marker records either `absent` or one recognized exact non-HDR literal. It
is config-local, human-readable, and the only durable restoration metadata.
Returning to Off restores that exact literal or removes the CM field when it
was originally absent, then removes the marker. External `hdr`/`hdredid`, a
malformed marker, dynamic CM expressions, and ICC ownership are left unmanaged.
No preference database duplicates this intent.

A confirmed Automatic HDR selection is stored in one narrowly owned machine
configuration block. If the setting was initially Hyprland's implicit default,
temporary rollback restores both runtime value 1 and durable omission exactly.
Because runtime `hl.config()` permanently marks that live option as set until a
reload, inspection derives durable explicitness from the owned block rather
than misclassifying its own targeted rollback as external persistence.
The user override is never used as Vanilla-owned storage; an external machine
or override owner for `cm_auto_hdr` makes mutation unavailable.

## Automatic first-change profile materialization

A fallback-managed display is already a valid Hyprland configuration. Vanilla
does not create a connector profile during installation, session start,
hotplug, inspection, or panel open. Read-only inspection projects its live Mode,
Scale, effective bit depth, HDR policy, and validated capabilities immediately.
Ordinary controls are available without a preliminary opt-in. The first actual
Mode, refresh, Scale, bitdepth, forced-HDR, or Automatic HDR mutation request
materializes the connector profile before continuing through the existing
Safe Apply or immediate Scale path.

Materialization is a dedicated persistence-only transaction. It binds the
exact compositor, connector and meaningful physical identity, snapshots the
complete topology and both configuration files, validates one supported
fallback and the absence of exact/description/override conflicts, clones the
fallback block, and changes only `output = ""` to the connector. For the public
seed the result is therefore `preferred` Mode, automatic position, automatic
Scale, and no bitdepth or color field. The fallback remains byte-for-byte
unchanged.

The candidate passes the same Bubblewrap prospective verification, atomic
replacement, reload observation, `configerrors`, exact-instance and crash
recovery machinery as other persistence operations. It never calls
`hl.monitor()`, enters `temporary-active`, or owns a deadline. Complete
pre/post topology equality is mandatory, including every connected output,
identity, active Mode, Scale, position, transform, DPMS, mirror, VRR, DRM/color
state, and advertised catalogue. Layer-shell `reserved` geometry may be
recomputed across the reload and is deliberately excluded. A mismatch restores
the exact original machine bytes, reconciles the reload, and verifies the
original topology; no runtime correction hides a mismatch.

Normal eligibility requires meaningful make/model and a unique non-empty
serial. A serial-less output is eligible only when meaningful
make/model/description form a unique identity in the current topology. Weak or ambiguous identity,
inactive output, unsupported fallback syntax, a description-addressed rule, an
override conflict, hotplug, compositor replacement, or an external file edit
fails closed. One output is materialized per transaction while the complete
topology remains protected.

## Persistence and machine-profile boundary

The persistence foundation locates exactly one existing explicit connector
profile, preserves unrelated bytes and comments, replaces only the fields
owned by that candidate (mode, bitdepth, or scale), rejects machine/override
hash races, and atomically replaces the machine file with preserved mode and
ownership. A materialized `mode = "preferred"` and either the public Scale 1
or an existing supported `scale = "auto"` are valid replaceable sources: the
first actual user edit specializes only its owned value. Omitted bitdepth is the
known Hyprland default requested intent of 8;
the first bitdepth edit inserts exactly one simple field after Scale. A combined
Mode-plus-bitdepth edit replaces Mode and inserts bitdepth in one atomic
candidate. Materialization itself does none of those specializations.
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

The production authority wires the tested machine-file persister, Bubblewrap
prospective verifier, and exact-instance reload coordinator. Durable Confirm
has been live-accepted through the real UI for both Mode and bitdepth, including
exact restoration round trips. Immediate Scale persistence has also been
live-accepted. Fixture and isolated verifier coverage remain prerequisites for
future changes to these paths.

Journal schemas are strict and never reinterpret older recovery material. The
schema-5 HDR generation intentionally rejects schema 4, just as each prior
generation rejected its predecessor. Schema 6 likewise rejects schema 5
because safe-confirmed candidates may now own paired Mode and Scale rollback
material. A backend upgrade must never
cross a nonterminal or recovery-required transaction from an older schema. The
old deployed helper must first prove that its journal is terminal and
recovery-disarmed, its lock is unheld, and no control listener exists. Only then
may controlled deployment
remove that old terminal runtime journal and install the new helper into clean
runtime state. Future schema changes require the same explicit upgrade protocol
or a separately reviewed migration; they must not guess compatibility.

The public machine seed remains exactly one portable fallback with
`preferred`/`auto`/`1`. It is valid indefinitely and is never a settings write
target. A real user mutation automatically runs the materialization transaction,
and subsequent edits target only the cloned connector rule. Existing explicit
profiles are an idempotent no-op and are never normalized or rewritten by
materialization. Existing supported `scale = "auto"` profiles remain readable
and replaceable.

## Deployed UI integration and acceptance boundary

One global `MonitorController` coalesces read-only inspection, sends Safe Apply
or immediate Scale requests, reconciles status, and refreshes Quickshell's
monitor projection after terminal operations. Mode/refresh and bitdepth are
pending input state until one Apply action; they never masquerade as confirmed
state. Manual Scale selection invokes the immediate backend path and opens no
confirmation. A Resolution change changes the draft Scale to configured `auto`,
locks Scale controls, and carries Mode plus `auto` in that same safe-confirmed
request. Cancelling the Resolution draft restores the applied Scale ownership;
confirmation keeps `auto`, unlocks Scale, and shows Hyprland's effective numeric
readback with no preset selected.

The confirmation surface is instantiated per screen within the existing
`Variants { model: Quickshell.screens }` structure and uses `CenteredOverlay`
plus `OverlayFocusCoordinator`. Only the preferred target-screen instance is
visible, with fallback to another registered screen if necessary. Keep and
Revert carry the exact transaction ID; Escape and outside dismissal mean
Revert. A one-second status poll exists only while a backend transaction is
nonterminal. The displayed countdown is interpolated locally between status
samples, but only backend `remaining_seconds` and its monotonic deadline have
authority. A restarted Quickshell queries status and reconstructs the overlay
without changing or extending that deadline.

Controlled single-monitor deployment and live UI acceptance are complete.
Accepted real-session paths include Mode timeout, Revert, and Keep; bitdepth
timeout and Keep; immediate Scale persistence; Escape and outside dismissal as
Revert; and same-process Quickshell reload during confirmation without deadline
or transaction replacement. Combined Mode+bitdepth remains deterministically
covered by the same candidate and persistence machinery.

Physical multi-monitor acceptance is deferred until appropriate hardware is
available. The architecture and deterministic suite cover multiple outputs,
per-screen connector mapping, output-order independence, identity changes, and
protected-topology failures; no physical multi-monitor success is claimed.
Automatic first-change materialization is repository-implemented and
deterministically covered, but physical fallback-managed acceptance remains
later work. DDC/CI Brightness and global Text Size remain deliberately separate.
