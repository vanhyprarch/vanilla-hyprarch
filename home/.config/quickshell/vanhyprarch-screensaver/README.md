# Quickshell screensaver configuration

This dedicated named Quickshell configuration presents the Vanilla HyprArch
screensaver independently of the main desktop shell. It creates one full-output
overlay layer-shell surface for every screen in `Quickshell.screens`.

The visual is a lightweight Qt Quick port of Ly's `ColorMix` algorithm. The
algorithm source is Ly's
[`src/animations/ColorMix.zig`](https://github.com/fairyglade/ly/blob/863162b5f79850c08fda13a3fbde7e19aac544ba/src/animations/ColorMix.zig)
at commit `863162b5f79850c08fda13a3fbde7e19aac544ba`. Ly is distributed under the
[Do What The Fuck You Want To Public License, Version 2
(WTFPL)](https://github.com/fairyglade/ly/blob/863162b5f79850c08fda13a3fbde7e19aac544ba/license.md).
Vanilla HyprArch does not claim authorship of Ly's algorithm.

The port keeps the transform and palette-index mathematics, random pattern
offsets, and Ly-equivalent animation speed. For lower rendering cost it draws
the 12 foreground/background density combinations as blended low-resolution
cells rather than terminal Unicode glyphs. The 33-millisecond render cadence is
normalized to Ly's 5-millisecond reference.

The sample grid follows the approximately 9.6-by-22.6-logical-pixel cell pitch
measured from the retained Foot+C reference. Adjacent same-color samples are
batched into horizontal Canvas runs without reducing pattern density.

The overlay takes exclusive layer-shell keyboard focus so a dismissal key is
not delivered to the previously focused application. Input-driven dismissal is
still owned by the generated hypridle listener; direct manual starts require a
separately armed bounded controller stop.

`bin/vanhyprarch-screensaver` is the only supported lifecycle interface. A
future bootstrap must deploy this directory as the named Quickshell config
`vanhyprarch-screensaver` and install the controller in the user's PATH.
