# Vanilla HyprArch

Vanilla HyprArch is a small, incremental desktop configuration layer for a
standard Arch Linux installation using upstream Hyprland. It is not a separate
distribution and does not patch upstream packages.

The project favors understandable configuration, official Arch packages, and
small components with clear ownership. Quickshell provides the desktop UI.
Hyprland owns the session, while hypridle and the `vanhyprarch-idle` controller
provide persistent Power & Idle behavior.

Screensaver rendering is delegated to the independent
[Vanilla HyprArch Zig Player](https://github.com/vanhyprarch/vanhyprarch-zig-player).
Vanilla HyprArch installs and controls its separately released executable; it
does not vendor or duplicate the player's source. The player owns native
layer-shell presentation and input absorption. The pinned integration uses
release `v0.1.1` and offers ColorMix, Matrix, Doom, and Game of Life.

Architecture, installation policy, current implementation state, and known
compatibility constraints are documented under [`docs/`](docs/).

Project-authored Vanilla HyprArch material in this repository, including
historical project-authored revisions, is licensed under GPL-2.0-only. Files or
material explicitly carrying separate third-party licensing or attribution
remain under those terms. The external player is an independent GPL-2.0-only
project with its own license and third-party notices.
