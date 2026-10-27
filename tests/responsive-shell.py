#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
SHELL_ROOT = REPOSITORY / "home/.config/quickshell/vanhyprarch"
COMPONENTS = SHELL_ROOT / "components"
HYPRLAND_CORE = REPOSITORY / "home/.config/hypr/vanhyprarch/core.lua"


class ResponsiveShellStaticTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (SHELL_ROOT / relative).read_text(encoding="utf-8")

    def test_screen_metrics_follow_logical_screen_without_writing_text_size(self) -> None:
        shell = self.read("shell.qml")
        metrics = self.read("components/VisualMetrics.qml")
        self.assertIn("viewportWidth: screenScope.modelData.width", shell)
        self.assertIn("viewportHeight: screenScope.modelData.height", shell)
        self.assertIn("physicalPixelDensity: screenScope.modelData.physicalPixelDensity", shell)
        self.assertIn("readonly property real shellFitFactor", metrics)
        self.assertIn("readonly property real physicalShellScale", metrics)
        self.assertNotIn("requestSize(", metrics)
        self.assertNotIn("requestSize(", shell)

    def test_dock_width_and_exclusive_zone_share_metric(self) -> None:
        shell = self.read("shell.qml")
        self.assertIn("implicitWidth: screenMetrics.dockWidth", shell)
        self.assertIn("exclusiveZone: screenMetrics.dockWidth", shell)

    def test_dock_has_disjoint_top_middle_bottom_regions(self) -> None:
        shell = self.read("shell.qml")
        self.assertIn("id: dockTopRegion", shell)
        self.assertIn("id: dockLauncherRegion", shell)
        self.assertIn("id: dockSystemRegion", shell)
        self.assertIn("y: dockTopRegion.height", shell)
        self.assertIn("height: screenMetrics.dockLauncherRegionHeight(", shell)
        self.assertIn("height: screenMetrics.dockSystemRegionHeight(", shell)
        self.assertNotIn("anchors.verticalCenter: parent.verticalCenter", shell)

    def test_bottom_height_uses_complete_real_stack(self) -> None:
        shell = self.read("shell.qml")
        metrics = self.read("components/VisualMetrics.qml")
        bottom = shell.split("id: dockBottomContent", 1)[1]
        bottom = bottom.split("VerticalScrollIndicator {", 1)[0]
        for control in (
            "dockSystemTray.implicitHeight",
            "dockBluetooth.implicitHeight",
            "dockNetwork.implicitHeight",
            "dockAudio.implicitHeight",
            "dockMonitor.implicitHeight",
            "dockPowerIdle.implicitHeight",
            "dockThemeToggle.implicitHeight",
            "dockShortcutsButton.implicitHeight",
            "dockClock.implicitHeight",
            "powerMenu.implicitHeight",
        ):
            self.assertIn(control, bottom)
        self.assertIn("bottom: parent.bottom", bottom)
        self.assertIn("bottom: powerMenu.top", bottom)
        self.assertIn("bottom: dockClock.top", bottom)
        self.assertIn("bottom: dockShortcutsButton.top", bottom)
        self.assertIn("bottom: dockThemeToggle.top", bottom)
        self.assertIn("bottom: dockPowerIdle.top", bottom)
        self.assertIn("bottom: dockMonitor.top", bottom)
        self.assertIn("bottom: dockAudio.top", bottom)
        self.assertIn("bottom: dockNetwork.top", bottom)
        self.assertIn("bottom: dockBluetooth.top", bottom)
        self.assertIn("contentHeight: dockBottomContent.height", shell)
        self.assertNotIn("dockPowerButtonTarget * 2", metrics)

    def test_launcher_and_bottom_regions_use_bounded_flickables(self) -> None:
        shell = self.read("shell.qml")
        launchers = self.read("components/Launchers.qml")
        self.assertIn("id: launcherViewport", launchers)
        self.assertIn("contentHeight: Math.max(height, content.implicitHeight)", launchers)
        self.assertIn("clip: true", launchers)
        self.assertIn("Flickable {\n            id: dockSystemRegion", shell)
        self.assertIn("boundsBehavior: Flickable.StopAtBounds", shell)

    def test_launchers_center_in_their_content_item_without_screen_preference(self) -> None:
        shell = self.read("shell.qml")
        launchers = self.read("components/Launchers.qml")
        self.assertNotIn("preferredContentCenterY", shell + launchers)
        content = launchers.split("id: content", 1)[1].split("Repeater {", 1)[0]
        self.assertIn("anchors.verticalCenter: parent.verticalCenter", content)
        self.assertNotRegex(content, r"(?m)^\s+y:")
        self.assertIn("contentHeight: Math.max(height, content.implicitHeight)", launchers)

    def test_launcher_popup_anchors_project_reactive_flickable_geometry(self) -> None:
        launchers = self.read("components/Launchers.qml")
        self.assertIn(
            "y: root.y + launcherViewport.y + content.y + addButton.y\n"
            "            - launcherViewport.contentY",
            launchers,
        )
        self.assertIn(
            "? root.y + launcherViewport.y + content.y\n"
            "                + root.contextMenuSourceAnchor.y"
            " - launcherViewport.contentY",
            launchers,
        )
        self.assertNotIn("mapToItem(parent, 0, 0).y", launchers)

    def test_app_picker_uses_context_menu_top_alignment(self) -> None:
        app_picker = self.read("components/AppPicker.qml")
        context_menu = self.read("components/LauncherContextMenu.qml")
        for source in (app_picker, context_menu):
            self.assertIn("property int popupVerticalOffset: 4", source)
            self.assertIn("alignToAnchorTop: true", source)
            self.assertIn("anchorTopOffset: root.popupVerticalOffset", source)

    def test_all_tall_system_panels_share_scrollable_surface(self) -> None:
        for name in (
            "AudioPanel.qml",
            "NetworkPanel.qml",
            "BluetoothPanel.qml",
            "MonitorPanel.qml",
            "PowerIdlePanel.qml",
            "MonthCalendar.qml",
        ):
            source = self.read(f"components/{name}")
            self.assertIn("ScrollablePanelSurface {", source, name)
        monitor = self.read("components/MonitorPanel.qml")
        self.assertIn(
            "requestedPanelHeight: content.implicitHeight"
            " + root.metrics.panelPadding * 2",
            monitor,
        )

    def test_scrollable_panel_has_no_overflow_geometry_cycle(self) -> None:
        surface = self.read("components/ScrollablePanelSurface.qml")
        self.assertIn("contentHeight: scrollContent.childrenRect.height", surface)
        self.assertIn("width: viewport.width", surface)
        self.assertNotIn("width: viewport.width - (root.contentScrollable", surface)
        self.assertNotIn("height: childrenRect.height", surface)

    def test_dock_popup_has_hard_viewport_bounds(self) -> None:
        popup = self.read("components/DockPopup.qml")
        self.assertIn("root.metrics.dockPanelMaximumWidth", popup)
        self.assertIn("root.metrics.dockPanelMaximumHeight", popup)
        self.assertIn("implicitWidth: Math.min(root.panelWidth", popup)
        self.assertIn("property int requestedPanelHeight: 0", popup)
        self.assertIn(
            "implicitHeight: Math.min(root.requestedPanelHeight,\n"
            "        root.viewportMaximumHeight)",
            popup,
        )
        self.assertIn("root.viewportMaximumWidth", popup)
        self.assertIn("root.viewportMaximumHeight", popup)
        self.assertIn("root.metrics.panelViewportMargin", popup)
        self.assertNotRegex(popup, r"(?m)^\s+(?:width|height):")
        self.assertIn("root.width, root.targetScreen.width", popup)
        self.assertIn("root.height, root.targetScreen.height", popup)

    def test_every_dock_popup_supplies_its_original_requested_height(self) -> None:
        expected = {
            "AppPicker.qml": "Math.min(root.maximumPanelHeight,",
            "LauncherContextMenu.qml": "actionsColumn.implicitHeight",
            "LauncherStateDiagnostic.qml": "content.implicitHeight",
            "MonthCalendar.qml": "content.implicitHeight + root.metrics.panelPadding * 2",
            "AudioPanel.qml": "content.implicitHeight + root.metrics.panelPadding * 2",
            "BluetoothPanel.qml": "content.implicitHeight + root.metrics.panelPadding * 2",
            "MonitorPanel.qml": "content.implicitHeight + root.metrics.panelPadding * 2",
            "NetworkPanel.qml": "content.implicitHeight + root.metrics.panelPadding * 2",
            "PowerIdlePanel.qml": "content.implicitHeight + root.metrics.panelPadding * 2",
            "PowerMenu.qml": '(root.pendingAction === ""',
        }
        consumers = {
            path.name for path in COMPONENTS.glob("*.qml")
            if "DockPopup {" in path.read_text(encoding="utf-8")
        }
        self.assertEqual(consumers, set(expected))
        for name, expression in expected.items():
            source = self.read(f"components/{name}")
            self.assertIn(f"requestedPanelHeight: {expression}", source, name)
            if name != "PowerMenu.qml":
                self.assertNotRegex(source, r"(?m)^    implicitHeight:")

        app_picker = self.read("components/AppPicker.qml")
        self.assertIn(
            "applicationsView.contentHeight + root.metrics.panelPadding * 2)",
            app_picker,
        )
        context_menu = self.read("components/LauncherContextMenu.qml")
        self.assertIn("+ root.metrics.compactMenuPadding * 2", context_menu)
        self.assertIn("alignToAnchorTop: true", context_menu)
        self.assertIn("anchorTopOffset: root.popupVerticalOffset", context_menu)
        self.assertIn("implicitHeight: buttonSize", self.read("components/PowerMenu.qml"))

    def test_dock_popup_animation_rule_is_namespace_scoped(self) -> None:
        popup = self.read("components/DockPopup.qml")
        shell = self.read("shell.qml")
        core = HYPRLAND_CORE.read_text(encoding="utf-8")
        namespace = "vanhyprarch-dock-popup"
        self.assertIn("import Quickshell.Wayland", popup)
        self.assertIn(f'WlrLayershell.namespace: "{namespace}"', popup)
        self.assertIn('name = "vanhyprarch-dock-popup-no-animation"', core)
        self.assertIn(f'namespace = "^{namespace}$"', core)
        self.assertIn("no_anim = true", core)
        self.assertEqual(core.count("no_anim = true"), 1)
        self.assertNotIn('namespace = "^quickshell$"', core)
        self.assertNotIn("WlrLayershell.namespace", shell)
        self.assertNotIn(namespace, shell)

    def test_dock_popup_has_no_obsolete_presentation_workaround(self) -> None:
        popup = self.read("components/DockPopup.qml")
        presentation = COMPONENTS / "PopupPresentationState.qml"
        self.assertFalse(presentation.exists())
        self.assertNotIn("PopupPresentationState", popup)
        self.assertNotIn("contentItem.opacity", popup)
        self.assertNotIn("frameSwapped", popup)
        self.assertIn("visible: DockGeometry.surfaceVisible(", popup)
        self.assertNotIn("Timer {", popup)
        self.assertNotIn("Behavior on", popup)
        self.assertNotIn("FrameAnimation {", popup)
        self.assertNotIn("NumberAnimation {", popup)

    def test_responsive_regions_restore_empty_space_dismissal(self) -> None:
        shell = self.read("shell.qml")
        launchers = self.read("components/Launchers.qml")
        self.assertIn("signal emptySpacePressed()", launchers)
        self.assertIn("z: -1", launchers)
        self.assertIn("onPressed: root.emptySpacePressed()", launchers)
        self.assertIn("onEmptySpacePressed:", shell)
        self.assertGreaterEqual(
            shell.count("overlayFocusCoordinator.dockBackgroundInteracted()"),
            3,
        )
        bottom = shell.split("id: dockBottomContent", 1)[1]
        bottom = bottom.split("SystemTray {", 1)[0]
        self.assertIn("MouseArea {", bottom)
        self.assertIn("z: -1", bottom)
        self.assertIn("dockBackgroundInteracted()", bottom)

    def test_controls_retain_click_areas_and_system_icons(self) -> None:
        for name in (
            "ThemeToggle.qml",
            "Audio.qml",
            "Network.qml",
            "PowerIdle.qml",
            "Bluetooth.qml",
            "Monitor.qml",
            "ShortcutsButton.qml",
            "SystemTray.qml",
        ):
            source = self.read(f"components/{name}")
            self.assertIn("MouseArea {", source, name)
            self.assertIn("anchors.fill: parent", source, name)
        bluetooth = self.read("components/Bluetooth.qml")
        self.assertIn("visible: root.hardwareAvailable", bluetooth)
        self.assertIn("implicitHeight: visible ? buttonSize : 0", bluetooth)


if __name__ == "__main__":
    unittest.main(verbosity=2)
