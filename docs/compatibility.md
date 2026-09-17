# Compatibility and upstream workarounds

This is the canonical register for tested component versions, upstream quirks,
and removable local mitigations. Package selection belongs in
[the system baseline](system-baseline.md); implementation status belongs in
[current state](current-state.md).

## Validated baseline

| Component | Validated version | Role / status |
| --- | --- | --- |
| Arch Linux | Rolling snapshot, 2026-09-10 | Standard minimal base, packaging, and systemd |
| Hyprland | 0.56.2 (`hyprland 0.56.2-2`) | Compositor, Lua configuration, input, and session ownership |
| hypridle | 0.1.8 (`hypridle 0.1.8-2`) | Idle notifications and pre-sleep hooks |
| hyprlock | 0.9.6 (`hyprlock 0.9.6-3`) | Manual/password unlock and Screen saver/Display automatic-lock paths validated; portable theming remains pending |
| Quickshell | 0.3.1 (`quickshell 0.3.1-1`) | Main desktop shell; no longer part of screensaver rendering |
| Qt | 6.11.2 (`qt6-base 6.11.2-3`) | Main Quickshell runtime |
| `vanhyprarch-zig-player` | v0.1.1 | Native layer-shell screensaver renderer; idle continuity and input routing validated, physical two-monitor testing pending |
| Foot | 1.28.0 (`foot 1.28.0-2`) | Default terminal for interactive Install/Remove/Update operations; a shared helper retains final output until Enter without `--hold` |
| pacman | 7.1.0 (`pacman 7.1.0.r9.g54d9411-2`) | Local installed-package catalog and authoritative removal transaction semantics |
| yay | 13.0.1 (`yay 13.0.1-1`) | Interactive repository/AUR installation, removal, and full-system update wrapper |
| Flatpak | 1.18.2 (`flatpak 1:1.18.2-1`) | Locally validated official package for interactive app/runtime updates; required but not version-pinned |
| hyprpaper | 0.8.4 (`hyprpaper 0.8.4-8`) | Wallpaper process launched by Hyprland; portable tracked configuration remains open work |
| Papirus | `papirus-icon-theme 20260801-1` | Project icon theme |

This is a tested rolling-release snapshot, not a dependency lock or a claim
that other versions are incompatible. External release artifacts are pinned
separately when required.

## Quickshell Bluetooth pairing-agent boundary

**Affected component:** Quickshell 0.3.1 with BlueZ 5.87

Quickshell 0.3.1 exposes native Bluetooth adapters, discovery, devices,
pairing, connection, removal, and trust, but not the full BlueZ
`org.bluez.Agent1` callback surface required for PIN entry, displayed
passkeys, numeric confirmation, and authorization. Vanilla HyprArch supplies
one narrowly scoped Python agent using dbus-python and PyGObject. It is a
Quickshell-supervised child, registers with capability `KeyboardDisplay`, and
becomes the default agent because pairing is initiated by Quickshell's separate
D-Bus client.

The helper subscribes to BlueZ owner changes before registration and rechecks
the unique owner before reporting readiness. Display callbacks use delayed
replies until a panel acknowledges visibility; missing UI, bounded timeouts,
IPC failure, and shell or BlueZ teardown all terminate outstanding work rather
than accepting it. Automatic trust/connect is scoped to one user pairing
transaction and one helper-session generation.

The mitigation contains no adapter or device model and does not parse
`bluetoothctl`. Retest after a Quickshell Bluetooth API upgrade. It can be
removed when the installed native module provides equivalent complete pairing
callbacks and explicit user-response methods without losing the current
fail-closed lifecycle.

Manual testing confirmed panel-owned discovery start/stop, Android-phone
discovery, and successful outgoing pairing through the shell. Persistent device
profiles, Forget/re-pair, incoming requests, the complete PIN/passkey and
service-authorization matrix, multi-monitor routing, and reload during active
pairing remain pending real-device validation.

## BlueZ controller power persistence

**Affected component:** BlueZ 5.87

BlueZ `Adapter1.Powered` is runtime-only. Its packaged `main.conf` documents
`[Policy] AutoEnable=true` as the default, which enables controllers when they
are discovered at boot or later. Quickshell 0.3.1 writes that runtime property
correctly but does not turn it into a durable user choice; rfkill persistence
is a separate mechanism.

Vanilla HyprArch supplies a minimal BlueZ `main.conf` with `AutoEnable=false`
and restores Bluetooth through native Quickshell adapters. A missing user
preference means the in-memory first-run default ON; only explicit panel actions
write the versioned preference. BlueZ 5.87 reads one `main.conf`, not a
configuration drop-in directory, so the future bootstrap must deploy the
tracked complete minimal file and preserve an existing administrator file for
rollback. On the development machine, manual reboot tests confirmed saved OFF
restores OFF and saved ON restores ON, with discovery inactive in both cases.
Retest the file-loading and `AutoEnable` behavior after a BlueZ upgrade.

Until that bootstrap exists, users must not copy the tracked file blindly over
an existing customized BlueZ configuration.

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

### Integrated power and lock lifecycle

Controlled single-output testing validated real display-off, suspend, resume,
automatic lock at the Screen saver stage, automatic lock at the Display stage,
and dismissal of the saver before its later Display lock without a password.
Manual Power Menu lock and `hyprlock` password unlock also passed. Cleanup left
no residual `hyprlock`, player process, or layer; cursor state was restored and
no double-lock was observed. Cold-start hypridle ownership and behavior were
also revalidated.

These results do not claim physical two-monitor acceptance or every
lock-at-suspend/Caffeine combination.

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

On the validated stack, explicit `yay -Syu` updates installed official and AUR
packages while preserving yay and pacman configuration and prompts. Explicit
`flatpak update` updates installed Flatpak applications and runtimes with its
normal interactive behavior. Super+Space passes both as fixed direct argument
vectors through the shared terminal helper; it supplies no noninteractive,
forced-refresh, downgrade, dependency-bypass, or ordering flags. No real update
transaction was run as part of this validation.

Flatpak's recorded version is compatibility evidence, not an installation pin.
Clean installations consume the current official Arch package, and the normal
system update keeps it current. The system Flathub remote was validated at
`https://dl.flathub.org/repo/`.

Vanilla HyprArch must not blindly update its configuration or external player.
A player update requires an explicit version, architecture, asset-name,
checksum, release URL, and source-tag update followed by controller, timing,
output, input, and license-notice validation. Project self-update remains
unavailable until the required MANAGED / USER OVERRIDE / STATE deployment
architecture can preserve user changes and roll back a validated deployment.

Before changing this baseline:

1. identify the installed component versions;
2. inspect relevant upstream changes;
3. run targeted regressions for applicable quirks;
4. remove obsolete mitigation rather than retaining it indefinitely;
5. update this register with the new evidence.

The optional archinstall entry point remains version-sensitive. Any released
preset must record its validated archinstall baseline here.
