# Ly colormix proof of concept

This directory contains a provisional experiment, not an accepted Vanilla
HyprArch screensaver. It translates Ly's `ColorMix` animation into a small
standalone C renderer and presents it through Foot:

```text
standalone renderer -> Foot -> Wayland/Hyprland
```

There is no hypridle integration, Quickshell integration, automatic launch, or
production lifecycle handling yet.

## Provenance and fidelity

The algorithm is derived from Ly's
[`src/animations/ColorMix.zig`](https://github.com/fairyglade/ly/blob/863162b5f79850c08fda13a3fbde7e19aac544ba/src/animations/ColorMix.zig),
inspected at commit `863162b5f79850c08fda13a3fbde7e19aac544ba`.
Ly is distributed under the [Do What The Fuck You Want To Public License,
Version 2 (WTFPL)](https://github.com/fairyglade/ly/blob/863162b5f79850c08fda13a3fbde7e19aac544ba/license.md).
Vanilla HyprArch does not claim authorship of Ly's algorithm. No unrelated Ly
display-manager code is copied here.

At the 5-millisecond reference/fidelity render delay, the renderer preserves
Ly's current:

- `time_scale = 0.01` and one-frame-per-render time progression;
- two randomized initial pattern offsets in `[0, 2*pi)`;
- coordinate normalization, three transform iterations, trigonometric
  expressions, and `length(uv) * 5.0` mapping modulo 12;
- 12-cell palette ordering and Unicode block characters;
- red (`0x00ff0000`), blue (`0x000000ff`), and true-black
  (`0x20000000`) configuration used by this project.

Ly's [pinned termbox2
backend](https://github.com/AnErrupTion/termbox2/blob/c7f241e8888ce243e1748b05c26a42fcfaaad936/termbox2.h)
treats `TB_HI_BLACK` (`0x20000000` in its 32-bit attribute layout) as explicit
black rather than terminal-default color. In true-color output it emits RGB
zero while deliberately suppressing the default-color path. This renderer
therefore uses `38;2;0;0;0` and `48;2;0;0;0` ANSI colors wherever that palette
entry is foreground or background. It does not use SGR 39/49 for that entry.

The presentation differs from Ly in a few contained ways: this program writes
buffered ANSI frames instead of filling a termbox2 back buffer; it traverses
the independent cells row-first for terminal output; libc supplies the random
starting offsets; and Foot presents the terminal on Wayland instead of Ly
rendering directly on its login TTY. The mathematical cell result and palette
semantics are otherwise retained.

## Build and run

Build with the already-installed C compiler:

```sh
make -C experiments/colormix
```

From `experiments/colormix`, open a safe windowed test at the selected default
of 33 milliseconds, approximately 30 fps:

```sh
./run.sh
```

Request Foot's native fullscreen mode at the same default cadence explicitly:

```sh
./run.sh --fullscreen
```

Use 16 milliseconds for an optional approximately 60 fps mode, or 5
milliseconds for Ly render-cadence fidelity and debugging:

```sh
./run.sh --fullscreen --delay-ms 16
./run.sh --fullscreen --delay-ms 5
```

`--delay-ms` controls render cadence. Animation motion is normalized to the
current Ly configuration's 5-millisecond reference delay. Before each render,
the double-precision Ly-equivalent frame accumulator advances by:

```text
animation step = render delay / 5.0
```

The 5-millisecond fidelity/debug mode advances by exactly `1.0` frame per
render. The 16-millisecond mode advances by `3.2`, and the default
33-millisecond mode advances by `6.6`. All three retain approximately the same
Ly-equivalent movement speed. The selected 33-millisecond default is a PoC
choice based on current testing, not an immutable architectural requirement.

This normalization uses the configured render delay rather than elapsed wall
time. Rendering cost and scheduler delays are not compensated. A real-time
mode may be worth evaluating later, but is intentionally not part of this PoC.
The calculated step can be checked without rendering:

```sh
./colormix --delay-ms 16 --print-animation-step
```

## Manual performance observations

Fullscreen manual testing on the development system produced these process
CPU readings, expressed as percentages of one logical CPU:

| Render delay | Approximate rate | Foot | Renderer | Combined |
| --- | ---: | ---: | ---: | ---: |
| 16 ms | 60 fps | 20.8% | 21.6% | 42.4% |
| 33 ms | 30 fps | 11.6% | 12.3% | 23.9% |

Combined resident memory was approximately 55 MB in both modes. The native
renderer itself used approximately 2.7 MB, so Foot is a significant part of
both the CPU and total resident-memory cost. On this system the 30 fps mode
used substantially less CPU—roughly half the combined cost of the 60 fps
mode—without slowing the animation's movement.

These are development-machine observations, not universal performance claims.
CPU and memory must be remeasured on other systems and after any production
lifecycle or presentation changes.

Press Ctrl+C to exit. SIGINT, SIGTERM, and SIGHUP request a clean shutdown; the
renderer restores SGR state, cursor visibility, and the original screen after
leaving its alternate screen. It does not alter the terminal's line-wrapping
mode. Terminal resize events rebuild and clear the buffered frame at the new
row/column dimensions.

## Acceptance criteria

The PoC is successful as an isolated experiment: manual testing validated its
normalized movement speed and supports 33 milliseconds as the current default
candidate. This does not accept a production screensaver architecture. Before
promotion, testing must cover or revisit:

1. visual fidelity to Ly colormix;
2. fullscreen appearance;
3. smoothness;
4. CPU usage;
5. memory usage;
6. resize behavior;
7. clean exit and terminal restoration;
8. whether Foot remains an appropriate presentation layer.
