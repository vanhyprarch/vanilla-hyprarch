# DF2 Phase 5 SDDM login

Status: **SLICE 1 SOURCE CONTRACT IMPLEMENTED; NOT DEPLOYED**

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

Nothing in this slice installs or deploys those files. Ly remains the
published Phase 4 baseline until later work deliberately changes the package
manifest, privileged deployment, and systemd service policy. Slice 1 does not
create `theme.conf.user`, touch PAM, alter `/etc` or `/usr/share`, install SDDM,
or change a running display manager.

## Machine binding contract

The immutable `theme.conf` disables the full user model and leaves
`targetUser` and `targetSessionFile` empty. A later privileged integration
slice must generate SDDM's supported adjacent `theme.conf.user` override from
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

## Follow-on work

Later slices must separately add privileged system-file ownership and
deployment, install-specific `theme.conf.user` generation, SDDM package and
service policy, safe Ly migration and retirement, and VM acceptance. Those
changes must preserve the source contract established here rather than adding
session or user selection to the visible theme.
