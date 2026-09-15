import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    function luminance(color): real {
        return color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722
    }

    function childNamed(parent, name): var {
        for (const child of parent.children) {
            if (child.objectName === name)
                return child
        }
        return null
    }

    TextSizeController {
        id: controller
        persistenceAutostart: false
    }

    VisualMetrics {
        id: metrics
        fontBaseSize: controller.baseSize
    }

    Theme {
        id: theme
        metrics: metrics
    }

    ToggleSwitch {
        id: toggle
        metrics: metrics
        theme: theme
        interactive: false
    }

    PanelSurface {
        id: panelSurface
        width: 100
        height: 100
        metrics: metrics
        theme: theme
    }

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: {
            root.check(controller.baseSize === 12, "default text size is not 12")
            root.check(controller.minimumSize === 9
                && controller.maximumSize === 20
                && controller.stepSize === 1,
                "text-size range changed")
            root.check(controller.values.join(",")
                === "9,10,11,12,13,14,15,16,17,18,19,20",
                "text-size values are not every integer from 9 through 20")
            for (let size = 9; size <= 20; size++)
                root.check(controller.validSize(size), "valid text size rejected: " + size)
            root.check(!controller.validSize(8) && !controller.validSize(21)
                && !controller.validSize(12.5),
                "invalid text size accepted")
            const status = controller.parseStatus(
                "version=1\nsize=14\nexplicit=yes\ngtk=updated\n"
                + "foot=updated\nfoot_restart=required\n")
            root.check(status.size === 14 && status.explicitPreference,
                "valid controller status was not parsed")
            root.check(status.footRestartRequired,
                "Foot restart state was not parsed")

            let invalidAccepted = false
            try {
                controller.parseStatus(
                    "version=1\nsize=21\nexplicit=yes\ngtk=updated\n"
                    + "foot=updated\nfoot_restart=required\n")
                invalidAccepted = true
            } catch (error) {
            }
            root.check(!invalidAccepted, "out-of-range controller status was accepted")

            root.check(metrics.bodyFontSize === 12, "base body size changed")
            root.check(metrics.captionFontSize === 10, "base caption size changed")
            root.check(metrics.detailFontSize === 11, "base detail size changed")
            root.check(metrics.panelTitleFontSize === 14, "base title size changed")
            root.check(metrics.overlayFontSize === 16, "base overlay size changed")
            root.check(metrics.informationLabelFontSize === metrics.bodyFontSize
                && metrics.informationValueFontSize === metrics.bodyFontSize,
                "ordinary information typography diverged from body text")
            root.check(metrics.standardPanelWidth === 380, "base panel width changed")
            root.check(metrics.actionSurfaceWidth === 300
                && metrics.compactActionSurfaceWidth === 200,
                "base action-surface size classes changed")
            root.check(metrics.compactMenuPadding === 10
                && metrics.compactActionRowHeight === 40,
                "base compact-menu geometry changed")
            root.check(metrics.toggleTrackWidth === 42
                && metrics.toggleTrackHeight === 22
                && metrics.toggleKnobSize === 16
                && metrics.toggleKnobInset === 3,
                "base toggle geometry changed")
            root.check(toggle.knobOffX === 3 && toggle.knobOnX === 23
                && toggle.knobY === 3,
                "toggle knob does not have symmetric three-pixel insets")
            root.check(theme.accent === theme.control,
                "ordinary accent callers are not neutral")
            root.check(String(theme.text).toLowerCase() === "#3a3a3a",
                "Light primary foreground changed")
            root.check(Math.abs(theme.textMuted.a - 0.60) < 0.001
                && Math.abs(theme.secondaryControl.a - 0.90) < 0.001,
                "Light neutral hierarchy changed")
            root.check(theme.toggleKnob === theme.secondaryControl
                && toggle.knobColor === theme.secondaryControl,
                "Light toggle knob is not using the secondary-control role")
            root.check(toggle.trackColor === theme.normalFill,
                "OFF toggle track is not using the normal neutral fill")
            toggle.checked = true
            root.check(toggle.trackColor === theme.activeFill,
                "ON toggle track is not using the active neutral fill")
            root.check(Math.abs(theme.hoverFill.a - metrics.hoverStrength) < 0.001,
                "hover strength was not derived centrally")
            root.check(Math.abs(theme.activeFill.a - metrics.activeStrength) < 0.001,
                "active strength was not derived centrally")
            root.check(Math.abs(theme.normalFill.a
                    - metrics.normalFillStrength) < 0.001
                && Math.abs(theme.pressedFill.a
                    - metrics.pressedStrength) < 0.001
                && Math.abs(theme.textMuted.a
                    - metrics.informationalMutedOpacity) < 0.001,
                "neutral state strengths were not derived centrally")
            root.check(theme.activeFill.r === theme.text.r
                && theme.activeFill.g === theme.text.g
                && theme.activeFill.b === theme.text.b,
                "active state is not derived from neutral foreground")
            root.check(theme.panelOutline.a === 1.0
                && panelSurface.outlineColor.a === 1.0,
                "Light panel outline is not opaque")
            root.check(String(theme.panelOutline).toLowerCase() === "#939292",
                "Light panel outline did not use its stronger neutral mix")
            root.check(root.luminance(theme.text)
                    < root.luminance(theme.panelOutline)
                && root.luminance(theme.panelOutline)
                    < root.luminance(theme.surface),
                "Light panel outline is outside the foreground/surface hierarchy")
            root.check(panelSurface.outlineThickness === 3
                && panelSurface.verticalEdgeTopInset === 3
                && panelSurface.verticalEdgeBottomInset === 3,
                "panel outline geometry can overlap at corners")
            const topOutline = root.childNamed(panelSurface, "panelOutlineTop")
            const rightOutline = root.childNamed(panelSurface, "panelOutlineRight")
            const bottomOutline = root.childNamed(panelSurface, "panelOutlineBottom")
            const leftOutline = root.childNamed(panelSurface, "panelOutlineLeft")
            root.check(topOutline !== null && rightOutline !== null
                    && bottomOutline !== null && leftOutline !== null
                    && topOutline.visible && rightOutline.visible
                    && bottomOutline.visible && leftOutline.visible,
                "panel does not render all four outline edges")
            root.check(leftOutline.y === 3 && rightOutline.y === 3
                    && leftOutline.height === 94 && rightOutline.height === 94
                    && topOutline.height === 3 && bottomOutline.height === 3,
                "vertical panel outlines overlap horizontal corner ownership")
            theme.darkMode = true
            root.check(theme.accent === theme.control
                && theme.control === theme.text,
                "dark normal controls are not neutral")
            root.check(Math.abs(theme.secondaryControl.a - 0.80) < 0.001,
                "dark secondary-control strength changed")
            root.check(theme.toggleKnob === theme.secondaryControl
                && toggle.knobColor === theme.secondaryControl,
                "dark toggle knob is not using the secondary-control role")
            root.check(theme.panelOutline.a === 1.0
                && String(theme.panelOutline).toLowerCase() === "#535251"
                && root.luminance(theme.surface)
                    < root.luminance(theme.panelOutline)
                && root.luminance(theme.panelOutline)
                    < root.luminance(theme.text),
                "Dark panel outline is not opaque or outside its hierarchy")
            theme.darkMode = false
            toggle.checked = false

            controller.baseSize = 16
            root.check(metrics.bodyFontSize === 16, "body size did not scale")
            root.check(metrics.captionFontSize === 13, "caption size did not scale")
            root.check(metrics.detailFontSize === 15, "detail size did not scale")
            root.check(metrics.panelTitleFontSize === 19, "title size did not scale")
            root.check(metrics.overlayFontSize === 21, "overlay size did not scale")
            root.check(metrics.standardPanelWidth === 507, "panel width did not scale")
            root.check(metrics.compactActionSurfaceWidth === 267
                && metrics.compactMenuPadding === 13
                && metrics.compactActionRowHeight === 53,
                "compact-menu geometry did not scale")
            root.check(metrics.dockWidth === 56
                && metrics.dockLauncherTarget === 40
                && metrics.dockSystemControlTarget === 36
                && metrics.dockPowerButtonTarget === 40
                && metrics.dockSystemIconSize === 20
                && metrics.applicationLauncherIconSize === 28,
                "fixed dock geometry scaled with text")
            root.check(metrics.dockGroupGap === 8
                && metrics.dockSystemControlGap === 0,
                "dock group and system-control gaps are not independent")
            root.check(metrics.dockSystemControlTarget
                    + metrics.dockSystemControlGap === 36,
                "system-control targets overlap or have unexpected center spacing")
            root.check(metrics.dockPopupGap === 9, "dock popup gap changed")
            root.check(metrics.panelOutlineThickness === 3,
                "panel exterior outline changed")
            root.check(metrics.controlOutlineThickness === 1
                && metrics.separatorThickness === 1,
                "internal physical-pixel geometry changed")
            controller.baseSize = 14
            root.check(metrics.toggleTrackHeight
                === metrics.toggleKnobSize + metrics.toggleKnobInset * 2,
                "scaled toggle lost its symmetric vertical inset")

            console.log("vanhyprarch text-size controller self-check passed")
            Qt.quit()
        }
    }
}
