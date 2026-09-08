# Compatibility and upstream workarounds

This is the canonical register for tested component versions, upstream quirks,
and local compatibility workarounds. Package selection belongs in
[the system baseline](system-baseline.md); implementation status belongs in
[current state](current-state.md); durable choices belong in
[architecture decisions](decisions.md).

## Validated baseline

The following versions were installed and inspected on 2026-09-08. This is a
tested rolling-release snapshot, not a claim that other versions are
incompatible.

| Component | Validated version | Role / important dependency | Status |
| --- | --- | --- | --- |
| Arch Linux | Rolling snapshot, 2026-09-08 | Standard minimal base, packaging, and systemd | Validated development baseline; no fixed distribution release |
| Hyprland | 0.56.2 (`hyprland 0.56.2-2`) | Compositor, Lua configuration, input, bindings, and session ownership | Validated; version-specific idle behavior is registered below |
| hypridle | 0.1.8 (`hypridle 0.1.8-2`) | Idle notifications and pre-sleep hooks; directly owned by Hyprland | Parser, generated configuration, ownership, and layer-shell timing mitigation validated |
| hyprlock | 0.9.6 (`hyprlock 0.9.6-3`) | Session lock surface | Manual locking available; generated automatic lock paths still need integrated validation |
| Quickshell | 0.3.1 (`quickshell 0.3.1-1`) | Main desktop shell plus separate layer-shell screensaver | Main-shell and screensaver screen lifecycles validated |
| Qt | 6.11.2 (`qt6-base 6.11.2-3`) | Quickshell runtime and QML foundation | Validated with the current Quickshell shell |
| hyprpaper | 0.8.4 (`hyprpaper 0.8.4-8`) | Wallpaper process launched by Hyprland | Runtime use validated; portable tracked configuration is still open work |
| Foot | 1.28.0 (`foot 1.28.0-1`) | Default terminal and former screensaver PoC presentation layer | Normal terminal use validated; xdg-toplevel mapping is unsuitable for the production screensaver on this baseline |
| Papirus | `papirus-icon-theme 20260801-1` | Project icon theme | Current dock and panel icon names validated |

## Hyprland 0.56.2 — inhibitor-aware idle clocks rearm when the screensaver Foot window maps

**Mitigation status:** Implemented and regression-validated

### Environment

- Hyprland 0.56.2
- hypridle 0.1.8
- fullscreen Foot running the Vanilla HyprArch colormix renderer

The diagnostic used normal inhibitor-aware notifications for a 10-second
screensaver action, a harmless 20-second display marker, and a harmless
30-second suspend marker. The display and suspend listeners performed no DPMS,
locking, or suspend action.

Expected absolute marker times were 10, 20, and 30 seconds after input. The
completed manual cycle recorded:

```text
screensaver-due  1788880167.021
display-due      1788880187.107
suspend-due      1788880197.106
```

Measured deltas were:

- screensaver to display: 20.086 seconds;
- screensaver to suspend: 30.085 seconds;
- display to suspend: 9.999 seconds.

A second screensaver marker occurred 10.085 seconds after the first. An earlier
independent completed cycle measured 20.082, 30.084, and 10.002 seconds for the
same three deltas.

The verbose hypridle trace correlated the first marker and Foot startup with a
false `Resumed` event for the already-idled screensaver notification. That
notification then idled and executed again. The 20- and 30-second notifications
were not yet idled, so they emitted no resume callback, but their marker times
show that their pending inhibitor-aware clocks restarted at the same mapping
event. The intended total 10/20/30-second timeline therefore became
approximately 10/30/40 seconds.

The input-only dismissal notification described below did not resume until
genuine input.

### Layer-shell proof of concept

A temporary, genuine Quickshell layer-shell overlay replaced the Foot mapping
in the same harmless 9/10/20/30-second test. The validated stack was Hyprland
0.56.2, hypridle 0.1.8, and Quickshell 0.3.1. Two clean cycles retained the
intended absolute timeline:

| Cycle | Screen saver | Display | Suspend | Screen saver to display | Screen saver to suspend | Display to suspend |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1788886469.791 | 1788886479.789 | 1788886489.790 | 9.998 s | 19.999 s | 10.001 s |
| 2 | 1788886508.596 | 1788886518.595 | 1788886528.595 | 9.999 s | 19.999 s | 10.000 s |

No false `Resumed` event occurred when either layer surface mapped. The pending
20- and 30-second inhibitor-aware notifications were not rearmed, and each
action executed once. Compared with Foot's approximately 10/30/40 behavior,
the layer-shell surface produced approximately 10/20/30 twice.

Vanilla HyprArch therefore removes its deterministic trigger by presenting the
production screensaver as a separate minimal Quickshell layer-shell process,
not as a Foot xdg-toplevel. Normal Hyprland and hypridle inhibitor handling
continues to own permission for inhibitor-aware actions. This is a targeted
mitigation for the project-created Foot mapping trigger; it is not a claim that
every upstream inhibitor reevaluation path is fixed or that layer-shell mapping
has a protocol-level timing guarantee.

The production controller path subsequently repeated the same harmless test
twice. From each diagnostic daemon's recorded origin, cycle 1 fired at 9.945,
19.944, and 29.945 seconds; cycle 2 fired at 9.949, 19.948, and 29.948 seconds.
Neither cycle logged a resume before the 30-second marker, and each action
executed exactly once. This validates the implemented presentation, not only
the temporary proof of concept.

### Removal and retest condition

After upgrading Hyprland, hypridle, and/or Quickshell, rerun the harmless
short-marker absolute-idle diagnostic with the production layer-shell saver.
Also retest the former xdg-toplevel trigger where useful to determine whether
upstream behavior changed. Keep the layer-shell architecture for its other
ownership and multi-output benefits, but remove version-specific workaround
claims or logic that are no longer necessary rather than carrying obsolete
compatibility code indefinitely.

## Hyprland 0.56.2 — false resume dismissed the former single-listener screensaver

**Workaround status:** Implemented and manually validated

Mapping the former Foot xdg-toplevel caused Hyprland 0.56.2 to recheck idle
inhibitors. Although Foot requested no inhibitor, an already-idled
inhibitor-aware notification received a false resume. A single listener with
both screensaver start and stop therefore started Foot and immediately
dismissed it.

Vanilla HyprArch uses two listeners:

- an inhibitor-aware listener starts the screensaver and has no resume action;
- an input-only listener arms one second earlier with `ignore_inhibit = true`,
  performs only `/usr/bin/true` on timeout, and owns genuine-input dismissal or
  the selected lock transition.

Legitimate inhibitors still prevent the action listener from starting the
screensaver. Ignoring inhibitors is safe only on the dismissal listener because
its timeout action is harmless. The production layer-shell mapping no longer
reproduces the false resume, but this validated arrangement remains in place
pending a separate simplification test. The detailed lifecycle contract is in
[screensaver-lifecycle.md](screensaver-lifecycle.md).

After a Hyprland or hypridle upgrade, rerun the short false-resume regression
test. If mapping no longer resumes the action notification, simplify the
workaround rather than retaining compatibility code indefinitely, but only
after legitimate inhibitor and genuine-input behavior are revalidated.

## Updateability principle

Arch and system packages are updated normally. Vanilla HyprArch itself should
not blindly auto-update configuration or mutate the system. Before changing
this validated baseline:

1. compare critical installed component versions with this register;
2. read upstream changes relevant to the affected integrations;
3. run targeted regressions for every applicable registered quirk;
4. remove obsolete workarounds when upstream behavior makes them unnecessary;
5. update this register together with the newly validated baseline.

A future `docs/update-guide.md`, `vanhyprarch check`, or `vanhyprarch doctor`
may automate inspection and compatibility checks. It must not become a blind
system-mutation or unattended project-update mechanism. None of those tools is
implemented yet.

The optional archinstall entry point has its own rolling, version-sensitive
configuration surface. Its validation and update rules are defined in the
[installation strategy](installation-strategy.md); any released preset must
record its newly validated archinstall baseline here.
