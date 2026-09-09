# Compatibility and upstream workarounds

This is the canonical register for tested component versions, upstream quirks,
and removable local mitigations. Package selection belongs in
[the system baseline](system-baseline.md); implementation status belongs in
[current state](current-state.md).

## Validated baseline

| Component | Validated version | Role / status |
| --- | --- | --- |
| Arch Linux | Rolling snapshot, 2026-09-08 | Standard minimal base, packaging, and systemd |
| Hyprland | 0.56.2 (`hyprland 0.56.2-2`) | Compositor, Lua configuration, input, and session ownership |
| hypridle | 0.1.8 (`hypridle 0.1.8-2`) | Idle notifications and pre-sleep hooks |
| hyprlock | 0.9.6 (`hyprlock 0.9.6-3`) | Manual lock works; integrated automatic-lock testing remains pending |
| Quickshell | 0.3.1 (`quickshell 0.3.1-1`) | Main desktop shell; no longer part of screensaver rendering |
| Qt | 6.11.2 (`qt6-base 6.11.2-3`) | Main Quickshell runtime |
| `vanhyprarch-zig-player` | v0.1.1 | Native layer-shell screensaver renderer; idle continuity and input routing validated, physical two-monitor testing pending |
| Foot | 1.28.0 (`foot 1.28.0-1`) | Default terminal only |
| hyprpaper | 0.8.4 (`hyprpaper 0.8.4-8`) | Wallpaper process launched by Hyprland; portable tracked configuration remains open work |
| Papirus | `papirus-icon-theme 20260801-1` | Project icon theme |

This is a tested rolling-release snapshot, not a claim that other versions are
incompatible.

## Current screensaver validation

**Status:** validated with `vanhyprarch-zig-player` v0.1.1

### Production idle continuity

The final production test exercised the complete
`hypridle -> vanhyprarch-screensaver -> vanhyprarch-zig-player v0.1.1` chain.
ColorMix started through the controller after 10 seconds, a harmless second
listener recorded the 20-second deadline, and genuine input invoked the
listener's resume action:

```text
player start    +10.034 s
second timeout  +20.036 s
separation       10.002 s
genuine resume  +23.291 s
```

Native player startup neither reset pending hypridle clocks nor created a false
resume on the validated stack. Each event occurred exactly once. Genuine
keyboard activity emitted `on-resume`, which terminated the controller-owned
player and restored the normal zero-listener configuration. Production uses
one inhibitor-aware screensaver listener with both timeout and resume actions.
No S-1 or `ignore_inhibit` dismissal helper remains.

### Input routing

With Foot focused underneath the fullscreen player, manual tests—including the
final production-chain test—confirmed:

- the first keyboard character was absorbed;
- a pointer click was absorbed;
- scrolling was absorbed;
- real input still caused hypridle to emit `on-resume` and dismiss the player.

Release v0.1.0 exposed first-input leakage. Release v0.1.1 fixed it using
native layer-shell input routing. Input absorption belongs to the player;
Vanilla HyprArch carries no keyboard, pointer, injection, or compositor
workaround.

Retest after a Hyprland, hypridle, Wayland, or player update. Use harmless
timestamp actions first; do not trigger DPMS, locking, suspend, or fullscreen
UI as an incidental compatibility probe.

## Historical terminal behavior

The abandoned Foot/xdg-toplevel renderer caused Hyprland 0.56.2 to re-evaluate
idle inhibitors when its fullscreen window mapped. That produced a false resume
and changed an intended 10/20/30 timeline to approximately 10/30/40. It is
retained here only to explain why a native layer-shell renderer is an explicit
architecture boundary. Git history contains the detailed measurements and
temporary workarounds.

No compatibility code for that abandoned renderer remains active.

## Current player integration limit

The v0.1.1 player creates all-edge overlay surfaces using direct
`wlr-layer-shell`, handles integer and fractional output scaling, and contains
multi-output lifecycle logic. Physical two-monitor behavior has not yet been
validated upstream.

## Updateability principle

Arch packages update normally. Vanilla HyprArch must not blindly update its
configuration or external player. A player update requires an explicit version,
architecture, asset-name, checksum, release URL, and source-tag update followed
by controller, timing, output, input, and license-notice validation.

Before changing this baseline:

1. identify the installed component versions;
2. inspect relevant upstream changes;
3. run targeted regressions for applicable quirks;
4. remove obsolete mitigation rather than retaining it indefinitely;
5. update this register with the new evidence.

The optional archinstall entry point remains version-sensitive. Any released
preset must record its validated archinstall baseline here.
