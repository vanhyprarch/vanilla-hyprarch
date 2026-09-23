#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path
import argparse
import re
import struct
import xml.etree.ElementTree as ET
import zlib


REPOSITORY = Path(__file__).resolve().parents[1]
SHELL = REPOSITORY / "home/.config/quickshell/vanhyprarch"
COMPONENTS = SHELL / "components"
ASSETS = SHELL / "assets/system-icons"

CONTROL_FILES = (
    "ThemeToggle.qml",
    "Audio.qml",
    "Network.qml",
    "PowerIdle.qml",
    "Bluetooth.qml",
    "Monitor.qml",
    "ShortcutsButton.qml",
)

AUDIO_STATES = {
    "audio-volume-muted",
    "audio-volume-low",
    "audio-volume-medium",
    "audio-volume-high",
}

NETWORK_STATES = {
    "network-disconnected",
    "network-limited",
    "network-wired",
    "network-wireless-offline",
    "network-wireless-signal-none",
    "network-wireless-signal-low",
    "network-wireless-signal-ok",
    "network-wireless-signal-good",
    "network-wireless-signal-excellent",
}

STATIC_STATES = {
    "theme-light",
    "theme-dark",
    "power-idle",
    "power-caffeine",
    "bluetooth",
    "display",
    "information",
}

EXPECTED_ASSETS = AUDIO_STATES | NETWORK_STATES | STATIC_STATES


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def quoted_states(text: str, prefix: str) -> set[str]:
    return set(re.findall(rf'"({re.escape(prefix)}[a-z-]+)"', text))


def png_pixels(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), f"{path.name} is not PNG")
    offset = 8
    compressed = bytearray()
    width = height = 0
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + length]
        offset += length + 12
        if chunk_type == b"IHDR":
            width, height, depth, color_type, compression, filtering, interlace = \
                struct.unpack(">IIBBBBB", chunk_data)
            require((depth, color_type, compression, filtering, interlace)
                    == (8, 6, 0, 0, 0),
                    f"{path.name} has unsupported PNG encoding")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    raw = zlib.decompress(bytes(compressed))
    stride = width * 4
    previous = bytearray(stride)
    pixels: list[tuple[int, int, int, int]] = []
    position = 0
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        scanline = bytearray(raw[position:position + stride])
        position += stride
        require(filter_type in range(5), f"{path.name} has invalid PNG filter")
        for index in range(stride):
            left = scanline[index - 4] if index >= 4 else 0
            above = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                estimate = left + above - upper_left
                distances = (abs(estimate - left), abs(estimate - above),
                             abs(estimate - upper_left))
                predictor = (left, above, upper_left)[distances.index(min(distances))]
            else:
                predictor = 0
            scanline[index] = (scanline[index] + predictor) & 0xFF
        pixels.extend(tuple(scanline[index:index + 4])
                      for index in range(0, stride, 4))
        previous = scanline
    return width, height, pixels


def verify_render(render_dir: Path) -> None:
    filename = "icons.png"
    width, height, pixels = png_pixels(render_dir / filename)
    require((width, height) == (52, 28),
            f"{filename} does not use the expected render fixture size")
    theme = (COMPONENTS / "Theme.qml").read_text()
    match = re.search(
        r'readonly property color text: darkMode \? "(#[0-9A-Fa-f]{6})"'
        r' : "(#[0-9A-Fa-f]{6})"', theme)
    require(match is not None, "could not resolve authoritative theme foregrounds")

    def rgb(value: str) -> tuple[int, int, int]:
        return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))

    dark_rgb = rgb(match.group(1))
    light_rgb = rgb(match.group(2))
    require(sum(dark_rgb) / 3 > 0xCC and sum(light_rgb) / 3 < 0x66,
            "authoritative Dark/Light foreground contrast changed")
    expectations = (("dark", dark_rgb, 4), ("light", light_rgb, 28))
    for mode, expected_rgb, x_offset in expectations:
        region = [pixels[y * width + x]
                  for y in range(4, 24)
                  for x in range(x_offset, x_offset + 20)]
        require(len(region) == 400,
                f"{mode} icon does not use the canonical logical size")
        opaque = [pixel for pixel in region if pixel[3] >= 240]
        require(len(opaque) >= 20, f"{mode} icon has no visible artwork")
        exact = sum(pixel[:3] == expected_rgb for pixel in opaque)
        require(exact >= len(opaque) * 0.9,
                f"{mode} icon does not render the dock Power foreground")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-dir", type=Path)
    arguments = parser.parse_args()

    controls = {name: (COMPONENTS / name).read_text() for name in CONTROL_FILES}
    for name, text in controls.items():
        require("Quickshell.iconPath(" not in text,
                f"{name} still theme-resolves structural dock artwork")
        require("SystemIcon {" in text,
                f"{name} does not use the canonical system icon renderer")

    require(quoted_states(controls["Audio.qml"], "audio-volume-") == AUDIO_STATES,
            "Audio dynamic icon states changed or are incomplete")
    require(quoted_states(controls["Network.qml"], "network-") == NETWORK_STATES,
            "Network dynamic icon states changed or are incomplete")

    for state in STATIC_STATES:
        require(any(f'"{state}"' in text for text in controls.values()),
                f"structural state {state} is not referenced")

    asset_names = {path.stem for path in ASSETS.glob("*.svg")}
    require(asset_names == EXPECTED_ASSETS,
            "canonical system asset set does not exactly match semantic states")

    forbidden_elements = {"linearGradient", "radialGradient", "filter", "image"}
    for asset_name in sorted(EXPECTED_ASSETS):
        path = ASSETS / f"{asset_name}.svg"
        require(path.is_file(), f"missing system icon asset: {path.name}")
        root = ET.parse(path).getroot()
        require(root.attrib.get("viewBox") == "0 0 24 24",
                f"{path.name} does not use the canonical 24x24 coordinate system")
        require("width" not in root.attrib and "height" not in root.attrib,
                f"{path.name} embeds a scale-specific size")
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            require(tag not in forbidden_elements,
                    f"{path.name} contains forbidden decorative element {tag}")
            for attribute in ("fill", "stroke"):
                value = element.attrib.get(attribute)
                require(value is None or value in {"none", "#000000"},
                        f"{path.name} is not monochrome")

    renderer = (COMPONENTS / "SystemIcon.qml").read_text()
    require('../assets/system-icons/" + root.iconName + ".svg"' in renderer,
            "system icon renderer does not resolve Vanilla-owned assets")
    require("root.metrics.dockSystemIconSize" in renderer,
            "system icon renderer does not retain canonical dock icon size")
    require("width: implicitWidth" in renderer and "height: implicitHeight" in renderer,
            "system icon renderer does not apply its canonical logical size")
    power_menu = (COMPONENTS / "PowerMenu.qml").read_text()
    require("property color iconColor: root.theme.accent" in power_menu
            and "color: root.iconColor" in power_menu,
            "dock Power/menu foreground authority changed")
    require("import QtQuick.Controls.impl as ControlsImpl" in renderer
            and "ControlsImpl.IconImage {" in renderer,
            "system icons do not use the exact semantic-color renderer")
    require("color: root.theme.accent" in renderer,
            "system icons do not reuse the dock Power/menu foreground token")
    require("MultiEffect" not in renderer and "colorization" not in renderer,
            "system icon renderer still uses luminance-preserving tinting")
    for scale_input in ("devicePixelRatio", "Screen.", "effectiveDevicePixelRatio"):
        require(scale_input not in renderer,
                f"system icon renderer selects artwork from {scale_input}")

    launcher = (COMPONENTS / "LauncherButton.qml").read_text()
    picker = (COMPONENTS / "AppPicker.qml").read_text()
    require("Quickshell.iconPath(" in launcher and "Quickshell.iconPath(" in picker,
            "application icons no longer use normal icon-theme resolution")
    require("//@ pragma IconTheme Papirus" in (SHELL / "shell.qml").read_text(),
            "Papirus application icon baseline was removed")

    bluetooth = controls["Bluetooth.qml"]
    require("visible: root.hardwareAvailable" in bluetooth,
            "Bluetooth is no longer hidden without hardware")
    require("implicitWidth: visible ? buttonSize : 0" in bluetooth
            and "implicitHeight: visible ? buttonSize : 0" in bluetooth,
            "hidden Bluetooth control still reserves dock space")

    power_icon = ET.parse(ASSETS / "power-idle.svg").getroot()
    require(power_icon.find("{http://www.w3.org/2000/svg}title").text
            == "Lightning bolt",
            "Power/Idle normal state is not the canonical lightning bolt")
    require(not list(power_icon.iter("{http://www.w3.org/2000/svg}circle"))
            and len(list(power_icon.iter("{http://www.w3.org/2000/svg}path"))) == 1,
            "Power/Idle normal state still resembles a power button")

    wired_icon = ET.parse(ASSETS / "network-wired.svg").getroot()
    require(wired_icon.find("{http://www.w3.org/2000/svg}title").text
            == "Ethernet port",
            "wired Network state is not identified as an Ethernet port")
    wired_paths = list(wired_icon.iter("{http://www.w3.org/2000/svg}path"))
    require(len(wired_paths) == 3
            and "M9 6.5V10M11 6.5V10M13 6.5V10M15 6.5V10"
            in {path.attrib.get("d", "") for path in wired_paths},
            "wired Network asset lacks recognizable RJ45 contact geometry")

    if arguments.render_dir is not None:
        verify_render(arguments.render_dir)

    print("vanhyprarch canonical system icon self-check passed")


if __name__ == "__main__":
    main()
