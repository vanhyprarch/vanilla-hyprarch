<h1 align="center">
  <img src="docs/assets/readme-banner.svg" alt="Vanilla HyprArch — a focused desktop layer for Arch Linux" width="960">
</h1>

<p align="center">
  <strong>Stable v1.0.5</strong> · x86_64 · GPL-2.0-only
</p>

<p align="center">
  <a href="#install-stable">Install</a> ·
  <a href="https://github.com/vanhyprarch/vanilla-hyprarch/releases/tag/v1.0.5">Release notes</a> ·
  <a href="#documentation">Documentation</a>
</p>

Vanilla HyprArch is a **keyboard-first desktop layer for Arch Linux**.
Shortcuts offer the fastest, most efficient way to get things done. The desktop
is just as natural with a mouse: open Firefox from the dock, watch a video, or
browse your files. **Keyboard first, not keyboard only** — everyday use doesn't
require a power user's workflow.

It brings together upstream **Hyprland**, a **Quickshell** interface, and small
independent components. Arch and its upstream packages stay vanilla; the project
provides the configuration and integration that connect them.

## In pictures

<table>
  <tr>
    <th align="center">Dark appearance</th>
    <th align="center">Light appearance</th>
  </tr>
  <tr>
    <td width="50%"><a href="docs/assets/screenshots/desktop-dark.png"><img src="docs/assets/screenshots/desktop-dark.png" alt="Vanilla HyprArch dark desktop with the night wallpaper and vertical dock" width="100%"></a></td>
    <td width="50%"><a href="docs/assets/screenshots/desktop-light.png"><img src="docs/assets/screenshots/desktop-light.png" alt="Vanilla HyprArch light desktop with the daylight wallpaper and vertical dock" width="100%"></a></td>
  </tr>
</table>

<p align="center">
  <a href="docs/assets/screenshots/desktop-tiling.png"><img src="docs/assets/screenshots/desktop-tiling.png" alt="Hyprland tiling with Firefox on the left, an app catalog above a terminal on the right, and the Vanilla HyprArch dock" width="960"></a>
  <br>
  <sub>Firefox, an app catalog, and a terminal — tiled by Hyprland.</sub>
</p>

## Your desktop, at a glance

| Area | What you get |
| :--- | :--- |
| **Desktop** | A dock on each display, app launchers, workspaces, system tray, and clock. |
| **Everyday controls** | Audio, Wi-Fi, Bluetooth, monitor brightness, Caffeine, and Power & Idle. |
| **Appearance** | Coordinated light and dark themes, remembered wallpapers, and eight bundled 4K backgrounds. |
| **Apps & updates** | A keyboard-and-mouse app menu, package installation and removal, Flatpak with Flathub, and signed Vanilla updates. |
| **Shortcuts** | **Super+Space** for apps and actions; **Print Screen** for region, window, or monitor capture. |

Add optional components from **Additional system components**:

- **[Local Dictation](docs/dictation.md)** — hold **F9** to record, then release to
  transcribe locally. Choose your speech model, languages, and CPU or Vulkan GPU backend.
- **[Zig Screensaver](https://github.com/vanhyprarch/vanhyprarch-zig-player)** — an
  independent native player with Color Mix, Matrix, Doom, and Game of Life effects.

## Install stable

Start with a **fresh, minimal Arch Linux x86_64 installation**, working Internet,
and a regular user with `sudo` access. Configure the base system and graphics
drivers for your hardware first. Archinstall integration and a custom USB ISO
are deferred; use the existing installer after minimal Arch.

**v1.0.5 downloads:**
[Release archive](https://github.com/vanhyprarch/vanilla-hyprarch/releases/download/v1.0.5/vanhyprarch-v1.0.5.tar.gz) ·
[Release metadata](https://github.com/vanhyprarch/vanilla-hyprarch/releases/download/v1.0.5/release.json) ·
[GitHub release](https://github.com/vanhyprarch/vanilla-hyprarch/releases/tag/v1.0.5)

GitHub is the primary download source. The alternative vanhyprarch.it mirror
provides the same [archive](https://vanhyprarch.it/dist/v1/vanilla-hyprarch/releases/v1.0.5/assets/vanhyprarch-v1.0.5.tar.gz)
and [metadata](https://vanhyprarch.it/dist/v1/vanilla-hyprarch/releases/v1.0.5/assets/release.json).

**v1.0.5 Stable** preserves application tray colors and transparency, themes
explicitly named `-symbolic` icons, and corrects fractional-scale cropping.
Nextcloud's optional unnamed monochrome pixmaps may lack contrast in Light Mode;
see [compatibility](docs/compatibility.md#application-tray-icon-color-boundary).

<details>
<summary><strong>Verified installation commands</strong></summary>

Run as your regular user. Confirm the pinned SHA-256 values below against a
trusted publisher record before executing downloaded code.

```bash
(
  set -e
  sudo pacman -Syu --needed curl
  bundle_dir=$(mktemp -d "$HOME/vanhyprarch-v1.0.5.XXXXXXXX")
  cd "$bundle_dir"
  download_base='https://github.com/vanhyprarch/vanilla-hyprarch/releases/download/v1.0.5'

  curl -fL --proto '=https' --proto-redir '=https' --tlsv1.2 \
    -o release.json "$download_base/release.json"
  curl -fL --proto '=https' --proto-redir '=https' --tlsv1.2 \
    -o vanhyprarch-v1.0.5.tar.gz "$download_base/vanhyprarch-v1.0.5.tar.gz"

  sha256sum -c <<'SHA256'
3d2dbb86d9c5d33a0e71f2cbdcbbb3af783de068b9394c5bd1bfcda60cbc22a2  release.json
62fbfea0d2c95f73aa1b00966cb0024720ab1230fc6d26a8773bc40e803bb16d  vanhyprarch-v1.0.5.tar.gz
SHA256

  tar -xzf vanhyprarch-v1.0.5.tar.gz
  "$PWD/vanhyprarch-v1.0.5/install.sh" \
    --release-metadata "$PWD/release.json" \
    --release-artifact "$PWD/vanhyprarch-v1.0.5.tar.gz"
)
```

The installer verifies the bundle again, validates the installation, and records
its stable release identity. Reboot afterward to enter the SDDM login.
See the [installation strategy](docs/installation-strategy.md) for the full workflow.

</details>

## Already using Vanilla HyprArch?

Open **Update** from the dock or **Super+Space**. The updater authenticates signed
release metadata and checks the selected release before applying it.

> **Original v1.0.0 installations:** follow the
> [one-time updater preparation and upgrade guide](docs/upgrade-v1.0.0-to-v1.0.1.md)
> before your first update. Already prepared systems must not repeat the bridge.

## Documentation

| Topic | Read more |
| :--- | :--- |
| **Installation & customization** | [Installation strategy](docs/installation-strategy.md) · [File ownership](docs/deployment-ownership.md) |
| **Design & hardware coverage** | [Architecture decisions](docs/decisions.md) · [Compatibility](docs/compatibility.md) |
| **Optional components** | [Local Dictation](docs/dictation.md) · [Screensaver lifecycle](docs/screensaver-lifecycle.md) |
| **Development & releases** | [Contributor instructions](AGENTS.md) · [Release workflow](docs/release-workflow.md) · [Release contracts](docs/release-engineering.md) |

Development installs from `main` follow a separate
[source-install workflow](docs/installation-strategy.md#public-development-bootstrap)
and do not carry an installed stable release identity.

## License

Project-authored material is licensed under **[GPL-2.0-only](LICENSE)**.
Third-party material retains its own license and attribution notices.
