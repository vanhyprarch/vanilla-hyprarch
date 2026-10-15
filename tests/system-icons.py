#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path
import argparse
import hashlib
import importlib.util
import re
import shutil
import struct
import sys
import tarfile
import tempfile
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

EXPECTED_ASSETS = set("""bluetooth bluetooth-searching bluetooth-off bluetooth-connected
ethernet-port wifi wifi-high wifi-low globe-off volume-2 volume-1 volume volume-off
monitor-cog zap sun moon info""".split())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_packaging() -> None:
    deploy = module_from(REPOSITORY / "install/managed_deploy.py", "icons_managed_deploy")
    fixture = module_from(REPOSITORY / "tests/release-artifact.py", "icons_release_fixture")
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-icons-packaging-") as temporary:
        root = Path(temporary)
        home = root / "home"
        home.mkdir()
        engine = deploy.ManagedDeployment(source_root=REPOSITORY,
            target=deploy.TargetContext.build(home=home))
        snapshot = engine._source_snapshot(engine.require_phase2_artifact("quickshell-config"))
        installed = {entry["path"] for entry in snapshot.entries}
        for path in ASSETS.iterdir():
            require("assets/system-icons/" + path.name in installed,
                    f"managed install omits {path.name}")

        # A real release build in a disposable Git fixture, never the main repo.
        repo = root / "source"
        repo.mkdir()
        fixture.write_fixture(repo)
        relative = ASSETS.relative_to(REPOSITORY)
        shutil.copytree(ASSETS, repo / relative)
        fixture.git(repo, "add", ".")
        fixture.git(repo, "commit", "-qm", "local icon packaging fixture")
        output = root / "output"
        output.mkdir()
        metadata, archive = fixture.RELEASE.build(repo, fixture.git(repo, "rev-parse", "HEAD"), output)
        identity = fixture.RELEASE.verify(metadata, archive)
        with tarfile.open(archive) as bundle:
            prefix = fixture.RELEASE.archive_root(identity["version"]) + "/" + str(relative) + "/"
            for path in ASSETS.iterdir():
                require(bundle.extractfile(prefix + path.name).read() == path.read_bytes(),
                        f"release archive alters or omits {path.name}")


def write_state_fixture(output: Path) -> None:
    # Execute actual production property bindings/functions against observable
    # mock objects; omit only native singleton access and popup/interaction UI.
    fragments = {}
    for name, marker in (("Bluetooth", "    readonly property var adapter:"),
                         ("Network", "    readonly property bool backendAvailable:"),
                         ("Audio", "    readonly property var sink:")):
        text = (COMPONENTS / (name + ".qml")).read_text()
        fragment = text[text.index(marker):text.index("    implicitWidth:")]
        if name == "Bluetooth":
            fragment = fragment[:fragment.index("    visible:")]
            fragment = fragment.replace("readonly property var adapter: Bluetooth.defaultAdapter", "property var adapter: null")
        elif name == "Audio":
            fragment = fragment.replace("readonly property var sink: Pipewire.defaultAudioSink", "property var sink: null")
        else:
            fragment = fragment.replace("readonly property bool backendAvailable:\n        Networking.backend === NetworkBackendType.NetworkManager", "property bool backendAvailable: true")
            fragment = fragment.replace("readonly property var devices: root.backendAvailable && Networking.devices\n        ? Networking.devices.values : []", "property var devices: []")
        fragments[name] = fragment
    template = (REPOSITORY / "tests/system-icon-state.qml").read_text()
    for name, fragment in fragments.items():
        template = template.replace("@" + name.upper() + "_STATE@", fragment)
    output.write_text(template)


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
    require((width, height) == (52, 28 * len(EXPECTED_ASSETS)),
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
    for row in range(len(EXPECTED_ASSETS)):
        for mode, expected_rgb, x_offset in expectations:
            region = [pixels[y * width + x]
                      for y in range(row * 28 + 4, row * 28 + 24)
                      for x in range(x_offset, x_offset + 20)]
            require(len(region) == 400,
                    f"{mode} icon does not use the canonical logical size")
            opaque = [pixel for pixel in region if pixel[3] >= 240]
            require(sum(pixel[3] > 0 for pixel in region) >= 20 and len(opaque) >= 4,
                    f"{mode} icon {row} has no visible artwork")
            # PNG unpremultiplication can round antialiased channels by one.
            exact = sum(all(abs(actual - expected) <= 1
                            for actual, expected in zip(pixel[:3], expected_rgb))
                        for pixel in opaque)
            require(exact >= len(opaque) * 0.9,
                    f"{mode} icon {row} does not render the dock Power foreground")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--state-fixture", type=Path)
    arguments = parser.parse_args()
    if arguments.state_fixture is not None:
        write_state_fixture(arguments.state_fixture)
        return
    if arguments.render_dir is not None:
        verify_render(arguments.render_dir)
        print("vanhyprarch system icon pixel self-check passed")
        return

    controls = {name: (COMPONENTS / name).read_text() for name in CONTROL_FILES}
    for name, text in controls.items():
        require("Quickshell.iconPath(" not in text,
                f"{name} still theme-resolves structural dock artwork")
        require("SystemIcon {" in text,
                f"{name} does not use the canonical system icon renderer")

    for state in EXPECTED_ASSETS:
        require(any(f'"{state}"' in text for text in controls.values()),
                f"approved icon {state} is not referenced")

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
        require(root.attrib.get("width") == root.attrib.get("height") == "24"
                and root.attrib.get("stroke-width") == "2"
                and root.attrib.get("stroke-linecap") == "round"
                and root.attrib.get("stroke-linejoin") == "round",
                f"{path.name} changes upstream dimensions or stroke")
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            require(tag not in forbidden_elements,
                    f"{path.name} contains forbidden decorative element {tag}")
            for attribute in ("fill", "stroke"):
                value = element.attrib.get(attribute)
                require(value is None or value in {"none", "currentColor"},
                        f"{path.name} is not monochrome")
            require(not any(key.rsplit("}", 1)[-1] in {"href", "style"}
                            for key in element.attrib), f"{path.name} references external content")

    checksums = dict(line.split("  ", 1)[::-1]
                     for line in (ASSETS / "SHA256SUMS").read_text().splitlines())
    require(set(checksums) == {state + ".svg" for state in EXPECTED_ASSETS} | {"LICENSE"},
            "upstream byte inventory is incomplete")
    for name, expected in checksums.items():
        require(hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == expected,
                f"upstream bytes were changed: {name}")
    license_text = (ASSETS / "LICENSE").read_text()
    require("ISC License" in license_text and "Lucide Icons and Contributors" in license_text
            and "The MIT License (MIT)" in license_text and "Cole Bemis" in license_text,
            "Lucide/Feather notices are missing")

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

    require("Networking.connectivity" not in controls["Network.qml"],
            "Internet reachability is incorrectly masking an active link")
    require('iconName: "zap"' in controls["PowerIdle.qml"], "Power & Idle must use zap")
    manifest = (REPOSITORY / "packages/manifest-v1.toml").read_text().lower()
    require("lucide" not in manifest and "nodejs" not in manifest and "npm" not in manifest,
            "static icon integration added an unnecessary runtime dependency")
    verify_packaging()

    print("vanhyprarch canonical system icon self-check passed")


if __name__ == "__main__":
    main()
