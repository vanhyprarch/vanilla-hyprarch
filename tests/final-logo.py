#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[1]
LOGO = REPOSITORY / "home/.config/quickshell/vanhyprarch/assets/logo.svg"
SHELL = REPOSITORY / "home/.config/quickshell/vanhyprarch/shell.qml"
SVG = "{http://www.w3.org/2000/svg}"


class FinalLogoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = LOGO.read_text(encoding="utf-8")
        self.root = ET.fromstring(self.raw)

    def test_svg_is_self_contained_and_script_free(self) -> None:
        self.assertEqual(self.root.tag, SVG + "svg")
        self.assertEqual(self.root.attrib.get("viewBox"), "0 0 1000 1000")
        self.assertEqual(
            self.root.attrib.get("preserveAspectRatio"), "xMidYMid meet"
        )
        self.assertNotIn("width", self.root.attrib)
        self.assertNotIn("height", self.root.attrib)
        self.assertEqual(self.root.findall(".//" + SVG + "script"), [])
        self.assertEqual(self.root.findall(".//" + SVG + "image"), [])
        self.assertNotRegex(self.raw, r"(?:href|src)\s*=")
        self.assertNotIn("file:", self.raw)
        self.assertNotIn("/home/", self.raw)
        self.assertNotRegex(self.raw, r"font-family|<text\b")

    def test_four_circles_share_the_documented_tangent_point(self) -> None:
        circles = self.root.findall(".//" + SVG + "circle")
        self.assertEqual(len(circles), 4)
        tangent = Decimal("853.553390593274")
        tolerance = Decimal("0.000000000002")
        sqrt_two = Decimal(2).sqrt()
        for circle in circles:
            cx = Decimal(circle.attrib["cx"])
            cy = Decimal(circle.attrib["cy"])
            radius = Decimal(circle.attrib["r"])
            self.assertLessEqual(abs(cx + radius / sqrt_two - tangent), tolerance)
            self.assertLessEqual(abs(cy + radius / sqrt_two - tangent), tolerance)
            self.assertRegex(circle.attrib["fill"], r"^#[0-9A-F]{6}$")

    def test_shell_uses_one_canonical_aspect_preserving_asset(self) -> None:
        shell = SHELL.read_text(encoding="utf-8")
        self.assertEqual(shell.count('Qt.resolvedUrl("assets/logo.svg")'), 1)
        self.assertIn("import QtQuick.VectorImage", shell)
        self.assertIn("VectorImage {\n                id: dockLogo", shell)
        self.assertNotRegex(
            shell, r"(?m)^\s*Image \{\n\s*id: dockLogo$"
        )
        self.assertIn("source: logoSource", shell)
        self.assertIn("width: screenMetrics.dockLogoSize", shell)
        self.assertIn("height: screenMetrics.dockLogoSize", shell)
        metrics = (SHELL.parent / "components/VisualMetrics.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "readonly property int dockLogoSize: fitted(40, 30)", metrics
        )
        self.assertIn("fillMode: VectorImage.PreserveAspectFit", shell)
        self.assertIn(
            "preferredRendererType: VectorImage.CurveRenderer", shell
        )
        logo_block = shell.split("VectorImage {\n                id: dockLogo", 1)[1]
        logo_block = logo_block.split("\n            Workspaces {", 1)[0]
        self.assertNotIn("sourceSize", logo_block)
        self.assertNotIn("mipmap", logo_block)
        self.assertNotIn("smooth", logo_block)
        self.assertIn("anchors.fill: parent", logo_block)
        self.assertIn("onClicked: superSpace.toggle()", logo_block)
        assets = list(LOGO.parent.glob("*logo*.svg"))
        self.assertEqual(assets, [LOGO])


if __name__ == "__main__":
    unittest.main(verbosity=2)
