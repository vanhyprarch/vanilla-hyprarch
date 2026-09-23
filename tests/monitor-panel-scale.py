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

    def test_fallback_outputs_have_no_advanced_settings_gate(self) -> None:
        self.assertNotIn("Enable advanced display settings", self.panel)
        self.assertNotIn("requestMaterialize", self.controller)
        self.assertIn(
            "(root.inspectedOutput.editable || root.inspectedOutput.materializable)",
            self.panel,
        )

    def test_pending_safe_fields_form_one_combined_request(self) -> None:
        self.assertIn("function requestSafeApply(connector: string)", self.controller)
        self.assertIn('command.push("--width"', self.controller)
        self.assertIn('command.push("--bitdepth"', self.controller)
        self.assertIn("function hasSafeChanges(connector: string)", self.controller)
        self.assertIn('? "Applying…" : "Apply display changes"', self.panel)

    def test_display_fields_have_only_editable_rows(self) -> None:
        self.assertNotIn("id: displayReadouts", self.panel)
        self.assertNotIn("function resolutionText()", self.panel)
        self.assertNotIn("function refreshText()", self.panel)
        for label in ("Resolution", "Refresh rate", "Color depth"):
            self.assertEqual(self.panel.count(f'label: "{label}"'), 1)
        self.assertIn("value: root.pendingResolutionText()", self.panel)
        self.assertIn("value: root.pendingRefreshText()", self.panel)
        self.assertIn("value: root.pendingBitdepthText()", self.panel)

    def test_hdr_policy_is_explicitly_per_monitor_and_global(self) -> None:
        resolution = self.panel.index('label: "Resolution"')
        refresh = self.panel.index('label: "Refresh rate"')
        color = self.panel.index('label: "Color depth"')
        hdr = self.panel.index('label: "Forced HDR"')
        automatic = self.panel.index('label: "Automatic HDR"')
        all_displays = self.panel.index('detailLabel: "All displays"', automatic)
        apply = self.panel.index('text: root.monitorControllerReady', automatic)
        self.assertLess(resolution, refresh)
        self.assertLess(refresh, color)
        self.assertLess(color, hdr)
        self.assertLess(hdr, automatic)
        self.assertLess(automatic, all_displays)
        self.assertLess(automatic, apply)
        self.assertIn("property string detailLabel:", self.panel)
        self.assertIn("font.pixelSize: root.metrics.captionFontSize", self.panel)
        self.assertIn(
            'return root.pendingState.hdr_mode === "always-on" ? "On" : "Off"',
            self.panel,
        )
        self.assertIn('const labels = ["Off", "On", "On (EDID)"]', self.panel)
        self.assertIn('command.push("--hdr", pending.hdr_mode)', self.controller)
        self.assertIn(
            'command.push("--automatic-hdr", String(root.pendingAutomaticHdr))',
            self.controller,
        )
        self.assertIn("function validationMessage(connector: string)", self.controller)
        self.assertIn("Forced HDR On requires selecting 10-bit Color Depth", self.controller)
        self.assertIn("root.inspectedOutput.hdr.unavailable_reason", self.panel)
        self.assertIn("root.monitorController.automaticHdrUnavailableReason", self.panel)
        self.assertNotIn("effective_hdr", self.controller)

    def test_automatic_hdr_pending_value_is_one_global_controller_state(self) -> None:
        self.assertEqual(self.controller.count("property int pendingAutomaticHdr:"), 1)
        self.assertNotIn("pending_automatic_hdr", self.panel)
        self.assertIn("root.monitorController.pendingAutomaticHdr", self.panel)
        self.assertIn("Automatic HDR (all displays): ", self.controller)
        self.assertIn('parts.push("Forced HDR: "', self.controller)
        self.assertIn('const labels = ["Off", "On", "On (EDID)"]', self.controller)
        self.assertNotIn('"Always On"', self.panel)
        self.assertNotIn('["Off", "HDR", "HDR (EDID)"]', self.panel)

    def test_confirmation_is_backend_authoritative_and_cannot_just_close(self) -> None:
        self.assertIn("remaining_seconds", self.controller)
        self.assertIn("running: root.transactionInFlight && root.checksEnabled", self.controller)
        self.assertIn("onDismissed: controller.requestRevert()", self.confirmation)
        self.assertIn("event.key === Qt.Key_Escape", self.confirmation)
        self.assertIn("root.controller.requestRevert()", self.confirmation)
        self.assertIn("root.controller.requestConfirm()", self.confirmation)

    def test_confirmation_height_follows_wrapped_content(self) -> None:
        self.assertNotIn("implicitHeight: 248", self.confirmation)
        self.assertIn(
            "implicitHeight: contentColumn.implicitHeight + contentPadding * 2",
            self.confirmation,
        )
        self.assertIn("readonly property int contentPadding:", self.confirmation)
        self.assertIn("topMargin: root.contentPadding", self.confirmation)
        self.assertNotIn("fill: parent\n                    margins: 24", self.confirmation)
        self.assertIn("wrapMode: Text.WordWrap", self.confirmation)

    def test_confirmation_buttons_are_equal_compact_and_centered(self) -> None:
        self.assertIn(
            "Math.ceil(Math.max(\n        revertLabel.implicitWidth, "
            "keepLabel.implicitWidth))",
            self.confirmation,
        )
        self.assertIn("+ root.metrics.rowSidePadding * 2", self.confirmation)
        self.assertIn("anchors.horizontalCenter: parent.horizontalCenter", self.confirmation)
        self.assertIn("width: root.actionButtonWidth * 2 + spacing", self.confirmation)
        self.assertEqual(self.confirmation.count("width: root.actionButtonWidth\n"), 2)
        self.assertNotIn("width: (parent.width - parent.spacing) / 2", self.confirmation)
        self.assertIn('text: "Revert · Esc"', self.confirmation)
        self.assertIn('text: "Keep · Enter"', self.confirmation)

    def test_confirmation_width_follows_content_with_project_bounds(self) -> None:
        self.assertNotIn("Math.max(360, Math.min(520", self.confirmation)
        self.assertIn(
            "Math.ceil(naturalContentWidth)\n        + contentPadding * 2",
            self.confirmation,
        )
        self.assertIn("root.metrics.compactActionSurfaceWidth", self.confirmation)
        self.assertIn("root.metrics.standardPanelWidth", self.confirmation)
        self.assertIn("Math.min(maximumPanelWidth, idealPanelWidth)", self.confirmation)
        self.assertIn("titleMeasure.implicitWidth", self.confirmation)
        self.assertIn("descriptionMeasure.implicitWidth", self.confirmation)
        self.assertIn("countdownMeasure.implicitWidth", self.confirmation)

    def test_confirmation_does_not_reserve_hypothetical_error_space(self) -> None:
        self.assertNotIn("errorMessage", self.confirmation)
        self.assertIn("root.monitorController.errorMessage", self.panel)

    def test_global_controller_and_per_screen_surfaces(self) -> None:
        self.assertEqual(self.shell.count("    MonitorController {"), 1)
        self.assertIn("globalMonitorController: monitorController", self.shell)
        self.assertIn(
            "monitorController: root.globalMonitorController", self.shell
        )
        variants = self.shell.index("    Variants {")
        confirmation = self.shell.index("    MonitorConfirmationPanel {")
        self.assertGreater(confirmation, variants)
        self.assertIn("controller: monitorController", self.shell)

    def test_soft_reload_guards_controller_and_selector_colors(self) -> None:
        self.assertIn("monitorControllerReady", self.panel)
        self.assertIn("? root.monitorController.outputFor", self.panel)
        self.assertIn("? root.monitorController.pendingFor", self.panel)
        self.assertNotIn("? root.monitorController.ensurePending", self.panel)
        self.assertIn("const pending = root.pendingFor(connector)", self.controller)
        self.assertNotIn("color: root.text }", self.panel)
        self.assertEqual(self.panel.count("color: root.textColor }"), 2)


if __name__ == "__main__":
    unittest.main()
