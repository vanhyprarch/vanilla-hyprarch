#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the production tray using real SNI/DBusMenu items on a private bus.

Uses the installed Quickshell/Qt and existing python-dbus/PyGObject test tools.
No desktop application, preference, or live session bus is touched.
"""

from pathlib import Path
import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib


HERE = Path(__file__).resolve().parent
COMPONENTS = HERE.parent / "home/.config/quickshell/vanhyprarch/components"
SNI = "org.kde.StatusNotifierItem"
MENU = "com.canonical.dbusmenu"
CONTROL = "org.vanhyprarch.TrayFixture"
OPENGL = "--opengl" in sys.argv
DPR = 1.0
REPLAY_PIXMAPS = None
PHASES = ("light", "dark", "light-return", "pixmap-update", "symbolic-update",
          "dark-update", "path-symbolic", "overlay", "attention", "named-color", "symbolic-return")


def require(value, message):
    if not value:
        raise AssertionError(message)


def png(path, pixels):
    """Encode the exact straight-alpha RGBA bytes also sent as SNI ARGB."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))

    rows = b"".join(b"\0" + bytes(c for pixel in pixels[y:y + 22] for c in pixel)
                    for y in range(0, 22 * 22, 22))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", 22, 22, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def artwork(updated=False, overlay=False):
    pixels = []
    for y in range(22):
        for x in range(22):
            pixel = (0, 0, 0, 0)
            if overlay:
                if 14 <= x < 20 and 14 <= y < 20:
                    pixel = (40, 140, 240, 255)
            else:
                # Rounded tile, contrasting glyph, colored badge and a half-alpha edge.
                if 2 <= x < 20 and 2 <= y < 20 and not (
                        (x < 4 or x >= 18) and (y < 4 or y >= 18)):
                    pixel = (20, 60, 90, 255)
                if (6 <= x < 9 and 6 <= y < 16) or (6 <= x < 16 and 6 <= y < 9):
                    pixel = (240, 232, 210, 255)
                if 13 <= x < 18 and 13 <= y < 18:
                    pixel = (30, 200, 110, 255) if updated else (230, 70, 45, 255)
                if y == 20 and 7 <= x < 15:
                    pixel = (80, 160, 220, 128)
            pixels.append(pixel)
    return pixels


def verify_legacy_pixels(output, log, item_count):
    # Reuse the existing stdlib PNG decoder; no image library is added.
    spec = importlib.util.spec_from_file_location("system_icons", HERE / "system-icons.py")
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    rw, rh, reference = decoder.png_pixels(output / "reference.png")
    require((rw, rh) == (176, 22), "reference dimensions")
    refs = [[reference[y * rw + x + index * 22] for y in range(22) for x in range(22)]
            for index in range(8)]
    old_light, old_dark = refs[6:8]
    background, glyph = 4 * 22 + 11, 8 * 22 + 7
    if OPENGL:
        require(old_light[glyph][3] == 255, "old MultiEffect rendered with the installed scene graph")
        require(max(old_light[glyph][:3]) < 65 and max(old_light[background][:3]) < 25,
                "old Light tint compresses both glyph and background into dark pixels")
        require(max(old_dark[glyph][:3]) > 180, "old Dark tint retains the brighter glyph")
        require(refs[0][glyph][0] - refs[0][background][0] > 150, "original application contrast")
        print(f"PASS old MultiEffect reproduction: Light background/glyph "
              f"{old_light[background][:3]}/{old_light[glyph][:3]}")
    else:
        print("SKIP old shader control on software backend (run --opengl with an existing DISPLAY)")
    metadata = [json.loads(line.split("TRAY_METADATA ", 1)[1])
                for line in log.splitlines() if "TRAY_METADATA " in line]
    require([row["phase"] for row in metadata] == list(PHASES), "all render phases completed")
    previous_pixmap_source = None
    for index, row in enumerate(metadata):
        width, height, pixels = decoder.png_pixels(output / (row["phase"] + ".png"))
        require((width, height) == (56, 150 + (item_count - 4) * 34), "tray render dimensions")
        for item in row["icons"]:
            if item["id"] == "replay":
                continue
            region = [pixels[(item["y"] + y) * width + item["x"] + x]
                      for y in range(22) for x in range(22)]
            identity = item["id"]
            symbolic = identity == "symbolic" and index not in (7, 9)
            require(item["symbolic"] == symbolic, f"{row['phase']}: classification of {identity}")
            expected = refs[{"color": 0, "gray": 1, "symbolic": 2,
                             "pixmap": 4 if index >= 3 else 3}[identity]]
            if identity == "symbolic" and index == 9:
                expected = refs[0]
            if symbolic:
                foreground = (244, 244, 243) if index in (1, 5) else (58, 58, 58)
                # IconImage applies an exact mask tint, including to black SVG pixels.
                expected = [(*foreground, p[3]) if p[3] else (0, 0, 0, 0) for p in expected]
            if identity == "symbolic" and index == 7:
                # Quickshell flattens symbolic base + colored overlay into one opaque handle.
                expected = [overlay if overlay[3] else base
                            for base, overlay in zip(expected, refs[5])]
                require(item["source"].startswith("image://qspixmap/"), "composite provider")
            for actual, wanted in zip(region, expected):
                # Compare premultiplied channels: PNG unpremultiplication loses
                # precision at antialiased edges with only a few alpha levels.
                require(abs(actual[3] - wanted[3]) <= 1 and all(
                            abs(a * actual[3] - b * wanted[3]) <= 2 * 255
                            for a, b in zip(actual[:3], wanted[:3])),
                        f"{row['phase']}/{identity}: {actual} != {wanted}")
            if identity == "pixmap":
                require(item["source"].startswith("image://qspixmap/"), "real pixmap provider")
                if index == 2:
                    previous_pixmap_source = item["source"]
                if index == 3:
                    require(item["source"] != previous_pixmap_source, "NewIcon invalidates provider URL")
        print(f"PASS {row['phase']}: colors, symbolic foreground, alpha, geometry")


def verify_pixels(output, log):
    spec = importlib.util.spec_from_file_location("system_icons", HERE / "system-icons.py")
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    metadata = [json.loads(line.split("TRAY_METADATA ", 1)[1])
                for line in log.splitlines() if "TRAY_METADATA " in line]
    require([row["phase"] for row in metadata] == list(PHASES), "all render phases completed")
    count = len(metadata[0]["icons"])
    if DPR == 1:
        # Keep the original artwork/tint/alpha and old-shader regression checks.
        verify_legacy_pixels(output, log, count)

    def bounds(width, pixels):
        coordinates = [(i % width, i // width) for i, pixel in enumerate(pixels) if pixel[3]]
        require(coordinates, "visible artwork")
        return [min(x for x, y in coordinates), min(y for x, y in coordinates),
                max(x for x, y in coordinates), max(y for x, y in coordinates)]

    measurements = []
    previous_pixmap_source = None
    for index, row in enumerate(metadata):
        require(row["dpr"] == DPR, "installed Qt uses the requested window DPR")
        width, height, actual = decoder.png_pixels(output / (row["phase"] + ".png"))
        fw, fh, fitted = decoder.png_pixels(output / (row["phase"] + "-fit.png"))
        tw, th, tinted = decoder.png_pixels(output / (row["phase"] + "-symbolic.png"))
        native = lambda logical: math.floor(logical * DPR + 0.5)
        require((width, height) == (native(56), native(150 + (count - 4) * 34)),
                "native-pixel render dimensions")
        require((fw, fh) == (tw, th) == (width, height), "reference render dimensions")
        for item in row["icons"]:
            symbolic = item["id"] == "symbolic" and index not in (7, 9)
            require(item["symbolic"] == symbolic, "source-name classification follows updates")
            if not symbolic:
                require(item["fillMode"] == 1 and item["painted"] == [22, 22],
                        "application artwork stays aspect-fit at fractional DPR")
            reference = tinted if symbolic else fitted
            x1, y1 = math.floor(item["buttonX"] * DPR), math.floor(item["buttonY"] * DPR)
            x2, y2 = math.ceil((item["buttonX"] + 32) * DPR), math.ceil((item["buttonY"] + 32) * DPR)
            region = [actual[y * width + x] for y in range(y1, y2) for x in range(x1, x2)]
            expected = [reference[y * width + x] for y in range(y1, y2) for x in range(x1, x2)]
            require(region == expected,
                    f"DPR {DPR} {row['phase']}/{item['id']}: exact reference RGBA pixels")
            box = bounds(x2 - x1, region)
            require(box == bounds(x2 - x1, expected), "complete uncropped pixel boundaries")
            require(any(p[3] == 0 for p in region), "transparent margins preserved")
            if symbolic:
                foreground = (244, 244, 243) if index in (1, 5) else (58, 58, 58)
                # Software filtering can round nearly opaque edge RGB by two
                # levels. Exact reference RGBA above covers those edges too.
                opaque = [p for p in region if p[3] == 255]
                require(len(opaque) >= 4 and all(
                    all(abs(a - b) <= 1 for a, b in zip(p[:3], foreground)) for p in opaque),
                    "symbolic theme foreground is unchanged")
            if item["id"] == "pixmap":
                require(item["source"].startswith("image://qspixmap/"), "native SNI pixmap source")
                if index == 2:
                    previous_pixmap_source = item["source"]
                if index == 3:
                    require(item["source"] != previous_pixmap_source, "NewIcon updates the source")
            if item["id"] in ("color", "gray"):
                require(item["source"].startswith("image://icon/"), "native named icon source")
            if item["id"] == "replay":
                require(item["source"].startswith("image://qspixmap/"), "captured SNI pixmap replay")
            measurements.append(dict(phase=row["phase"], id=item["id"], bounds=box, dpr=DPR))
        print(f"PASS DPR {DPR:g} {row['phase']}: exact RGBA/reference boundaries and symbolic foreground")
    (output / "boundaries.json").write_text(json.dumps(measurements, indent=2) + "\n")


def replay_pixmaps(dbus):
    result = []
    for path in sorted(REPLAY_PIXMAPS.glob("icon-*x*.argb")):
        match = re.fullmatch(r"icon-([0-9]+)x([0-9]+)\.argb", path.name)
        require(match is not None, "captured pixmap filename")
        width, height = map(int, match.groups())
        raw = path.read_bytes()
        require(0 < width <= 256 and 0 < height <= 256 and len(raw) == width * height * 4,
                "captured ARGB dimensions")
        result.append((width, height, dbus.ByteArray(raw)))
    require(result, "at least one captured SNI pixmap")
    return dbus.Array(result, signature="(iiay)")


def session():
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    name = dbus.service.BusName(CONTROL, bus)
    calls = []

    class Properties(dbus.service.Object):
        @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
        def Get(self, interface, prop):
            return self.props[prop]

        @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            return self.props

        @dbus.service.signal(dbus.PROPERTIES_IFACE, signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass

    class Item(Properties):
        def __init__(self, identity, icon, pixmaps=None):
            self.path = "/" + identity
            super().__init__(name, self.path)
            self.props = dict(Id=identity, Title=identity, Category="ApplicationStatus", Status="Active",
                              IconName=icon, IconPixmap=pixmaps or dbus.Array([], signature="(iiay)"),
                              IconThemePath=str(fixtures), OverlayIconName="", AttentionIconName="",
                              OverlayIconPixmap=dbus.Array([], signature="(iiay)"),
                              AttentionIconPixmap=dbus.Array([], signature="(iiay)"),
                              ItemIsMenu=False, Menu=dbus.ObjectPath("/Menu"))

        @dbus.service.signal(SNI)
        def NewIcon(self):
            pass

        @dbus.service.signal(SNI)
        def NewOverlayIcon(self):
            pass

        @dbus.service.signal(SNI)
        def NewAttentionIcon(self):
            pass

        @dbus.service.signal(SNI, signature="s")
        def NewStatus(self, status):
            pass

        @dbus.service.method(SNI, in_signature="ii")
        def Activate(self, x, y):
            calls.append("activate")

        @dbus.service.method(SNI, in_signature="ii")
        def SecondaryActivate(self, x, y):
            calls.append("secondary")

    class Menu(Properties):
        def __init__(self):
            super().__init__(name, "/Menu")
            self.props = dict(Version=dbus.UInt32(4), TextDirection="ltr", Status="normal",
                              IconThemePath=dbus.Array([], signature="s"))

        @dbus.service.method(MENU, in_signature="iias", out_signature="u(ia{sv}av)")
        def GetLayout(self, parent, depth, properties):
            calls.append("layout")
            props = dbus.Dictionary({"label": "Fixture action", "enabled": True, "visible": True},
                                    signature="sv")
            child = dbus.Struct((dbus.Int32(1), props, dbus.Array([], signature="v")),
                                signature="ia{sv}av", variant_level=1)
            return dbus.UInt32(1), dbus.Struct((dbus.Int32(0), dbus.Dictionary({}, signature="sv"),
                                               dbus.Array([child], signature="v")), signature="ia{sv}av")

        @dbus.service.method(MENU, in_signature="i", out_signature="b")
        def AboutToShow(self, identity):
            calls.append("about-to-show")
            return False

        @dbus.service.method(MENU, in_signature="isvu")
        def Event(self, identity, event, data, timestamp):
            calls.append(str(event))

    with tempfile.TemporaryDirectory(prefix="vanhyprarch-tray-",
                                     delete=not os.environ.get("TRAY_TEST_KEEP")) as tmp:
        root = Path(tmp)
        if os.environ.get("TRAY_TEST_KEEP"):
            print(f"Retained DPR {DPR:g} fixture: {root}", flush=True)
        config, output, fixtures = (root / part for part in ("config", "output", "fixtures"))
        for path in (config, output, fixtures, root / "runtime"):
            path.mkdir(mode=0o700)
        (config / "components").symlink_to(COMPONENTS)
        (config / "shell.qml").symlink_to(HERE / "system-tray.qml")
        for path in (HERE / "fixtures/system-tray").iterdir():
            shutil.copyfile(path, fixtures / path.name)
        for index in range(2):
            png(fixtures / f"pixmap{index}.png", artwork(bool(index)))
        png(fixtures / "overlay.png", artwork(overlay=True))
        # The offscreen platform has no theme search paths. Qt still resolves
        # real named icons through its standard standalone fallback directory.
        icons = root / "data/pixmaps"
        icons.mkdir(parents=True)
        for source, target in (("application.svg", "fixture-color.svg"),
                               ("grayscale.svg", "fixture-gray.svg"),
                               ("cloud-symbolic.svg", "fixture-symbolic.svg")):
            shutil.copyfile(fixtures / source, icons / target)
        shutil.copyfile(fixtures / "cloud-symbolic.svg", fixtures / "fallback-symbolic.svg")

        def pixmap(pixels):
            argb = bytes(channel for r, g, b, a in pixels for channel in (a, r, g, b))
            return dbus.Array([(22, 22, dbus.ByteArray(argb))], signature="(iiay)")

        items = [Item("color", "fixture-color"), Item("symbolic", "fixture-symbolic"),
                 Item("gray", "fixture-gray"), Item("pixmap", "", pixmap(artwork()))]
        if REPLAY_PIXMAPS:
            items.append(Item("replay", "", replay_pixmaps(dbus)))
        application_menu = Menu()

        class Control(dbus.service.Object):
            @dbus.service.method(CONTROL, in_signature="i")
            def Step(self, phase):
                symbolic = items[1]
                if phase == 3:
                    items[3].props["IconPixmap"] = pixmap(artwork(True))
                    items[3].NewIcon()
                elif phase == 4:
                    symbolic.props["IconName"] = str(fixtures / "cloud-symbolic.svg")
                    symbolic.NewIcon()
                elif phase == 6:
                    symbolic.props.update(IconName="fallback-symbolic.svg", IconThemePath=str(fixtures))
                    symbolic.PropertiesChanged(SNI, {key: symbolic.props[key]
                                                     for key in ("IconName", "IconThemePath")}, [])
                elif phase == 7:
                    symbolic.props.update(IconName="fixture-symbolic",
                                          OverlayIconName=str(fixtures / "overlay.png"))
                    symbolic.PropertiesChanged(SNI, {key: symbolic.props[key]
                                                     for key in ("IconName", "OverlayIconName")}, [])
                elif phase == 8:
                    symbolic.props.update(Status="NeedsAttention", AttentionIconName="fixture-symbolic")
                    symbolic.NewAttentionIcon()
                    symbolic.NewStatus("NeedsAttention")
                elif phase == 9:
                    symbolic.props.update(Status="Active", IconName="fixture-color",
                                          IconThemePath="", OverlayIconName="")
                    symbolic.PropertiesChanged(SNI, {key: symbolic.props[key] for key in (
                        "Status", "IconName", "IconThemePath", "OverlayIconName")}, [])
                elif phase == 10:
                    symbolic.props["IconName"] = "fixture-symbolic"
                    symbolic.NewIcon()
                elif phase == len(PHASES):
                    items[0].props["ItemIsMenu"] = True
                    items[0].PropertiesChanged(SNI, {"ItemIsMenu": True}, [])

        control = Control(name, "/Fixture")
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=str(root),
                           XDG_DATA_HOME=str(root / "data"), XDG_CONFIG_HOME=str(config),
                           XDG_DATA_DIRS=str(root / "data") + ":/usr/local/share:/usr/share",
                           XDG_RUNTIME_DIR=str(root / "runtime"), TRAY_TEST_OUTPUT=str(output),
                           TRAY_TEST_FIXTURES=str(fixtures), TRAY_TEST_COUNT=str(len(items)),
                           QS_NO_RELOAD_POPUP="1",
                           QT_QPA_PLATFORMTHEME="", QT_QUICK_BACKEND="rhi" if OPENGL else "software",
                           QSG_RHI_BACKEND="opengl", QT_SCALE_FACTOR=str(DPR))
        # Offscreen OpenGL can use an existing X server solely for its hidden
        # GLX context; no test window is mapped on the active desktop.
        if not OPENGL:
            environment.pop("DISPLAY", None)
        for key in ("WAYLAND_DISPLAY", "QS_CONFIG_PATH", "QS_CONFIG_NAME"):
            environment.pop(key, None)
        loop = GLib.MainLoop()
        with (root / "quickshell.log").open("w+") as log:
            process = subprocess.Popen(["qs", "--no-color", "-p", str(config)],
                                       env=environment, stdout=log, stderr=subprocess.STDOUT)
            registered = False

            def poll():
                nonlocal registered
                if process.poll() is not None:
                    loop.quit()
                    return False
                if not registered and bus.name_has_owner("org.kde.StatusNotifierWatcher"):
                    watcher = dbus.Interface(bus.get_object("org.kde.StatusNotifierWatcher",
                                                           "/StatusNotifierWatcher"),
                                             "org.kde.StatusNotifierWatcher")
                    for item in items:
                        watcher.RegisterStatusNotifierItem(item.path)
                    registered = True
                return True

            GLib.timeout_add(25, poll)
            def deadline():
                if process.poll() is None:
                    process.terminate()
                loop.quit()
                return False
            GLib.timeout_add_seconds(18, deadline)
            try:
                loop.run()
                process.wait(timeout=3)
                log.seek(0)
                text = log.read()
                require(process.returncode == 0, f"Quickshell exited {process.returncode}")
                require("vanhyprarch system tray self-check passed" in text, "QML completion")
                require(not any(marker in text for marker in ("ERROR", "Error:", "Could not load icon")),
                        "no QML errors")
                verify_pixels(output, text)
                require(calls.count("activate") == 1 and calls.count("secondary") == 1,
                        f"click delivery/menu-only policy: {calls}")
                require("about-to-show" in calls and "layout" in calls, f"real DBusMenu: {calls}")
                require(calls.count("clicked") == 1, f"application menu action delivery: {calls}")
                print("PASS hover, left/middle click, application menu/action, menu-only left click")
            except BaseException:
                log.seek(0)
                print(log.read(), file=sys.stderr)
                if os.environ.get("TRAY_TEST_KEEP"):
                    print(f"Retained fixture: {root}", file=sys.stderr)
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opengl", action="store_true", help="use a hidden offscreen GLX context")
    parser.add_argument("--dpr", type=float, action="append", choices=(1, 1.25, 1.5, 2))
    parser.add_argument("--replay-pixmaps", type=Path, help="directory of captured icon-WxH.argb files")
    parser.add_argument("--session", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    OPENGL = arguments.opengl
    REPLAY_PIXMAPS = arguments.replay_pixmaps
    if arguments.session:
        require(arguments.dpr and len(arguments.dpr) == 1, "one DPR per isolated session")
        DPR = arguments.dpr[0]
        session()
    else:
        for ratio in arguments.dpr or (1, 1.25, 1.5, 2):
            command = ["dbus-run-session", "--", sys.executable, "-B", str(Path(__file__).resolve()),
                       "--session", "--dpr", str(ratio), *(["--opengl"] if OPENGL else [])]
            if REPLAY_PIXMAPS:
                command.extend(["--replay-pixmaps", str(REPLAY_PIXMAPS.resolve())])
            subprocess.run(command, check=True)
        print("Vanilla system tray tests: PASS")
