# DF2 Phase 5 SDDM login

Status: **SLICES 1–3 IMPLEMENTED IN REPOSITORY; NOT DEPLOYED OR VM-ACCEPTED**

Decision date: 2026-09-22

DF2 Phase 5 supersedes Ly as the future Vanilla HyprArch display-manager
architecture. The earlier Ly investigation established that Ly 1.4.1 cannot
remove its visible username and session rows or display the canonical vector
logo without maintaining a patched custom package. The accepted replacement
is SDDM with a Vanilla-owned Qt Quick theme. This is a product decision, not an
adoption of another project's theme or branding.

The target chain is:

```text
SDDM X11 greeter
  -> Vanilla password-only Qt 6 theme
  -> /usr/bin/start-hyprland
  -> Hyprland Wayland session
  -> installed Vanilla HyprArch runtime
```

UWSM remains unsupported. The greeter stays on SDDM's normal X11 path; using a
Wayland desktop session does not require enabling SDDM's experimental Wayland
greeter.

## Slice 1 boundary

Slice 1 adds repository source contracts only:

- `system/usr/share/sddm/themes/vanhyprarch/` contains the generic Qt 6 theme;
- `system/usr/share/wayland-sessions/vanhyprarch.desktop` describes the one
  supported direct Wayland session;
- the theme's `logo.svg` is an exact distribution copy of the canonical
  Quickshell asset, with deterministic equality testing;
- deterministic Python and mocked Qt tests validate presentation,
  authentication plumbing, session resolution, and power actions.

Slice 1 itself installs nothing. It does not touch PAM, install SDDM, or
change a running display manager.

## Slice 2 privileged deployment

`install/sddm_login_integration.py` is the root-only internal
`plan`/`apply`/`validate` owner for the Slice 1 payload. `plan` and `apply`
require an explicit absolute `--source-root`; `validate` checks installed state
from root-private provenance without the source tree. Every operation requires
the explicit `--target-user` and resolves its canonical non-root account through
NSS. The first successful deployment records that account. A later request for
a different account fails closed; Slice 2 has no rebinding operation.

The ownership manifest classifies the immutable theme and session as
`VANILLA_MANAGED_SYSTEM`: root-owned regular Vanilla copies with directory mode
`0755`, file mode `0644`, provenance-backed updates, and no adoption of unknown
pre-existing content. The generated `theme.conf.user` remains `GENERATED` and
contains exactly the canonical username and fixed Vanilla session path. Its
owning backend is the only generator. No password, UID, home, or source path is
stored.

Root-private state lives under mode-0700
`/var/lib/vanhyprarch/sddm-login/`. Mode-0600 provenance records the target
binding, release digest/identity, complete artifact inventory, hashes, modes,
and owners. A separate mode-0600 durable transaction intent records staging,
publication, verification, commit, and cleanup. Staging containers are private
siblings of their destinations so Linux `renameat2(RENAME_EXCHANGE)` can swap
complete file/directory generations atomically on the target filesystem.

The fixed publication order is session entry first, then the complete theme
generation containing its generated binding, then the SDDM drop-in. Intent is
durable before any namespace changes. Before the provenance commit point,
recovery restores the old proven generation; after it, recovery retains the
verified candidate and finishes cleanup. Unknown content, symlinks, unsafe
parents, wrong types, ownership/mode drift, a session shadow at
`/usr/local/share/wayland-sessions/vanhyprarch.desktop`, or administrator edits
to managed payloads are conflicts rather than overwrite authority.

Typical internal invocation is:

```text
python install/sddm_login_integration.py plan \
  --source-root /absolute/release --target-user USER
python install/sddm_login_integration.py apply \
  --source-root /absolute/release --target-user USER
python install/sddm_login_integration.py validate --target-user USER
```

Slice 2 itself did not install SDDM, alter package or service policy, modify
PAM, or start/reload a display manager. Slice 3 extends the same
publisher and provenance boundary to the Vanilla SDDM drop-in.

## Slice 3 baseline

The manifest requires official `sddm` directly and does not list `ly`; Qt and
Xorg dependencies remain pacman-owned transitive dependencies.
The service manifest enables only normal `sddm.service` display-manager
semantics. It contains no continuing `ly@tty2.service` or
`getty@tty2.service` policy.

The managed `/etc/sddm.conf.d/10-vanhyprarch.conf` explicitly keeps the
greeter on X11, selects `vanhyprarch`, disables avatar lookup, and disables
remembered user/session and session reuse. It configures neither autologin nor
PAM and is published with the theme, session, and generated binding before any
display-manager enablement.

Fresh integration installs SDDM, validates the complete Phase 5 payload, and
then enables `sddm.service`, which owns the standard
`display-manager.service` alias. It requires the effective default target to
already be `graphical.target`; a deliberate non-graphical administrator choice
is a blocker, not a mutation.

SDDM is the only supported baseline. Ly was superseded before Alpha, and no
released Vanilla version used it, so there is no production Ly migration,
rollback, or retirement operation. An unsupported pre-existing
display-manager alias fails closed rather than being migrated.

## Machine binding contract

The immutable `theme.conf` disables the full user model and leaves
`targetUser` and `targetSessionFile` empty. The Slice 2 privileged integration
backend generates SDDM's supported adjacent `theme.conf.user` override from
the installer-resolved target account. The generic theme contains no actual
username, UID assumption, remembered-user dependency, or password.

The theme fails closed until both configuration values are usable. It never
consults `userModel.lastUser`, a UID, or user order. The first implementation
is intentionally single-user: the username exists only as an authentication
input and is never rendered.

SDDM 0.21.0's session model publishes named `directory`, `file`, `type`,
`name`, `exec`, and `comment` roles. Its `file` role is the absolute path of
the parsed desktop entry. The theme therefore enumerates that named role and
requires exactly one match for the configured
`/usr/share/wayland-sessions/vanhyprarch.desktop`; zero or multiple matches
disable login. It never uses `lastIndex`, a display name, package order, or a
hardcoded runtime index. See the exact-version upstream
[`SessionModel`](https://github.com/sddm/sddm/blob/v0.21.0/src/greeter/SessionModel.cpp)
and [theming API](https://github.com/sddm/sddm/wiki/Theming).

The Vanilla session entry executes only package-owned
`/usr/bin/start-hyprland`, with the same absolute path in `TryExec`, and
declares `DesktopNames=Hyprland`. Package-owned Hyprland and UWSM entries are
not modified. No chooser is rendered, so the theme can submit only the exact
Vanilla session resolved above.

## Presentation and behavior

Every SDDM screen receives an exact black root. SDDM 0.21.0 creates one QML
view per screen and exposes a `primaryScreen` context property; only that view
instantiates an interactive scene. The normal primary scene contains exactly
the canonical logo, one square password input, `F1 Shutdown`, and `F2 Reboot`.
The two labels are also mouse-clickable.

The password input starts empty and focused, uses concealed echo, retains the
normal blinking text cursor, and blocks duplicate submission. A failed login
clears the password, unlocks submission, shows only `Authentication failed`,
and restores focus. Typing clears the error. A missing binding instead shows
the generic `Configuration unavailable` state and never calls `sddm.login()`.

Layout dimensions derive from the shorter logical screen dimension and clamp
the scale to `0.72` through `2.0`. Input and logo widths also have proportional
screen bounds. Physical VM, HiDPI, 4K, and multi-monitor acceptance remains a
later deployed-candidate requirement.

## Acceptance gate

A full fresh installation from the saved VM snapshot is the release gate. It
must prove direct SDDM installation, the Vanilla greeter and session, login and
logout, reboot persistence, idempotence, and source-checkout independence.
There is no Slice 4 Ly-retirement operation.
