#!/usr/bin/env python3

from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
COMPONENTS = REPOSITORY / "home/.config/quickshell/vanhyprarch/components"
PANEL = COMPONENTS / "MonitorPanel.qml"
CONTROLLER = COMPONENTS / "MonitorController.qml"
CONFIRMATION = COMPONENTS / "MonitorConfirmationPanel.qml"
SHELL = REPOSITORY / "home/.config/quickshell/vanhyprarch/shell.qml"


class MonitorPanelPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel = PANEL.read_text(encoding="utf-8")
        cls.controller = CONTROLLER.read_text(encoding="utf-8")
        cls.confirmation = CONFIRMATION.read_text(encoding="utf-8")
        cls.shell = SHELL.read_text(encoding="utf-8")

    def test_panel_maps_its_shell_screen_not_focus(self) -> None:
        self.assertIn("Hyprland.monitorFor(root.targetScreen)", self.panel)
        self.assertNotIn("Hyprland.focusedMonitor", self.panel)
        self.assertNotIn("lastIpcObject", self.panel)

    def test_scale_has_exactly_one_backend_persistence_authority(self) -> None:
        for legacy in (
            "scaleEditScript",
            "quickshell-scale-edit",
            "machine/hyprland.lua",
            'command = ["sh", "-c"',
        ):
            self.assertNotIn(legacy, self.panel)
        self.assertIn(
            'return root.startAction([root.backendCommand, "scale", "--connector",',
            self.controller,
        )
        self.assertIn('connector, "--scale", scaleText]', self.controller)

    def test_final_policy_boundaries_are_explicit(self) -> None:
        self.assertIn('"safe-apply"', self.controller)
        self.assertIn('"immediate-scale"', self.controller)
        self.assertNotIn('command.push("--scale"', self.controller)
        self.assertIn("textSizeController.requestSize(requested)", self.panel)
        self.assertIn('["ddcutil", "setvcp", "10"', self.panel)

    def test_pending_safe_fields_form_one_combined_request(self) -> None:
        self.assertIn("function requestSafeApply(connector: string)", self.controller)
        self.assertIn('command.push("--width"', self.controller)
        self.assertIn('command.push("--bitdepth"', self.controller)
        self.assertIn("function hasSafeChanges(connector: string)", self.controller)
        self.assertIn('? "Applying…" : "Apply display changes"', self.panel)

    def test_confirmation_is_backend_authoritative_and_cannot_just_close(self) -> None:
        self.assertIn("remaining_seconds", self.controller)
        self.assertIn("running: root.transactionInFlight && root.checksEnabled", self.controller)
        self.assertIn("onDismissed: controller.requestRevert()", self.confirmation)
        self.assertIn("event.key === Qt.Key_Escape", self.confirmation)
        self.assertIn("root.controller.requestRevert()", self.confirmation)
        self.assertIn("root.controller.requestConfirm()", self.confirmation)

    def test_global_controller_and_per_screen_surfaces(self) -> None:
        self.assertEqual(self.shell.count("    MonitorController {"), 1)
        variants = self.shell.index("    Variants {")
        confirmation = self.shell.index("    MonitorConfirmationPanel {")
        self.assertGreater(confirmation, variants)
        self.assertIn("controller: monitorController", self.shell)


if __name__ == "__main__":
    unittest.main()
