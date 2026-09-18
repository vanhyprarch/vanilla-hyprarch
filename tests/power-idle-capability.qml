import QtQuick
import Quickshell
import "../home/.config/quickshell/vanhyprarch/components"

ShellRoot {
    id: root

    function check(condition, message) {
        if (!condition)
            throw new Error(message)
    }

    QtObject {
        id: controller
        property bool screensaverAvailable: false
        property bool ready: true
        property bool busy: false
        property bool visualCaffeine: false
        property bool caffeine: false
        property string effect: "matrix"
        property string lockPoint: "display"
        property string errorMessage: ""
        function canSetLock(value) { return value !== "screensaver" || screensaverAvailable }
        function canSetStage(stage, value) { return stage !== "screensaver" || screensaverAvailable }
        function stageValue(stage) { return "never" }
        function requestStage(stage, value) {}
        function requestLock(value) {}
        function requestCaffeine(value) {}
        function requestEffect(value) {}
    }

    IdleController {
        id: idleParser
        checksEnabled: false
    }

    VisualMetrics { id: metrics }
    Theme { id: theme; metrics: metrics }
    Item { id: anchor }
    PowerIdlePanel {
        id: panel
        controller: controller
        metrics: metrics
        theme: theme
        popupAnchorItem: anchor
    }

    Timer {
        interval: 0
        running: true
        onTriggered: {
            const stored = "screensaver=120\ndisplay=300\nsuspend=600\nlock=screensaver\n"
                + "effect=matrix\ncaffeine=off\neffective_listeners=2\n"
            const absentState = idleParser.parseStatus("version=3\n" + stored
                + "effective_screensaver=never\neffective_lock=display\n"
                + "screensaver_capability=absent\n")
            root.check(absentState.screensaverCapability === "absent"
                    && absentState.effectiveScreensaver === "never"
                    && absentState.lockPoint === "display"
                    && absentState.storedLockPoint === "screensaver",
                "backend absence projection was not consumed exactly")
            const firstReconciledStatus = "version=3\nscreensaver=120\n"
                + "display=300\nsuspend=600\nlock=screensaver\n"
                + "effective_screensaver=120\neffective_lock=screensaver\n"
                + "effect=matrix\nscreensaver_capability=installed\n"
                + "caffeine=off\neffective_listeners=3\n"
            const installedState = idleParser.parseStatus(firstReconciledStatus)
            root.check(installedState.screensaverCapability === "installed"
                    && installedState.lockPoint === "screensaver",
                "first reconciled status was not consumed strictly")
            root.check(!panel.screensaverControlsVisible,
                "absent component retained screensaver controls")
            root.check(panel.automaticLockChoiceCount === 3,
                "absent component did not expose exactly three lock choices")
            root.check(panel.visibleSectionLabels.join(",")
                    === "Caffeine,Turn Off Display,Suspend,Automatic Lock",
                "absent component section order is not exact")
            root.check(panel.visibleLockChoiceLabels.join(",")
                    === "None,Display Off,Suspend",
                "absent component lock choices are not exact")
            root.check(panel.optionalLayoutContribution === 0,
                "absent optional sections reserved layout contribution")
            idleParser.screensaverCapability = "installed"
            idleParser.screensaver = "120"
            idleParser.display = "300"
            idleParser.suspend = "600"
            idleParser.lockPoint = "screensaver"
            idleParser.failClosedScreensaverCapability()
            root.check(!idleParser.screensaverAvailable
                    && idleParser.effectiveScreensaver === "never"
                    && idleParser.lockPoint === "display",
                "failed refresh retained stale installed capability")
            controller.screensaverAvailable = true
            Qt.callLater(function() {
                root.check(panel.screensaverControlsVisible,
                    "installed component did not restore screensaver controls")
                root.check(panel.automaticLockChoiceCount === 4,
                    "installed component did not restore Screensaver lock choice")
                root.check(panel.visibleSectionLabels.join(",")
                        === "Caffeine,Screen Saver Effect,Screensaver,Turn Off Display,Suspend,Automatic Lock",
                    "installed component section order is not exact")
                root.check(panel.visibleLockChoiceLabels.join(",")
                        === "None,Screensaver,Display Off,Suspend",
                    "installed component lock choices are not exact")
                root.check(panel.optionalLayoutContribution > 0,
                    "installed optional sections did not enter layout")
                idleParser.ready = true
                idleParser.screensaverCapability = "installed"
                idleParser.screensaver = "never"
                idleParser.display = "300"
                idleParser.suspend = "600"
                root.check(!idleParser.canSetLock("screensaver"),
                    "Screensaver lock remained selectable while Screensaver was Never")
                console.log("vanhyprarch Power & Idle capability self-check passed")
                Qt.quit()
            })
        }
    }
}
