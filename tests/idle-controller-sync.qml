import QtQuick
import Quickshell
import Quickshell.Io
import "components"

ShellRoot {
    id: root

    readonly property string testRoot: Quickshell.env("IDLE_SYNC_ROOT")
    readonly property string initialState: Quickshell.env("IDLE_SYNC_INITIAL")
    readonly property string targetState: Quickshell.env("IDLE_SYNC_TARGET")
    readonly property string origin: Quickshell.env("IDLE_SYNC_ORIGIN")
    readonly property string outcome: Quickshell.env("IDLE_SYNC_OUTCOME")
    readonly property string backend: Quickshell.env("IDLE_SYNC_BACKEND")
    property bool initialized: false
    property bool started: false
    property bool publishedSeen: false
    property bool released: false
    property int caffeineChanges: 0
    property int statusStarts: 0
    property bool sawStatusError: false
    property bool recoveryRequested: false

    function fail(message) {
        console.error("VANHYPRARCH_IDLE_CONTROLLER_FAIL: " + message)
        Qt.exit(1)
    }

    function lineCount(text) {
        return String(text || "").split("\n")
            .filter(line => String(line).trim() !== "").length
    }

    function releaseTransaction() {
        if (root.released || releaseProcess.running)
            return
        root.released = true
        releaseProcess.command = ["/usr/bin/touch", root.testRoot + "/gate"]
        releaseProcess.running = true
    }

    function startScenario() {
        root.started = true
        if (root.origin === "controller") {
            idleController.requestCaffeine(root.targetState === "on")
        } else if (root.origin === "external") {
            externalProcess.command = [root.backend, "test-external",
                root.targetState, root.outcome]
            externalProcess.running = true
        } else if (root.origin === "burst") {
            externalProcess.command = [root.backend, "test-burst"]
            externalProcess.running = true
        } else if (root.origin === "rapid") {
            externalProcess.command = [root.backend, "test-rapid"]
            externalProcess.running = true
        } else if (root.origin === "status-recovery") {
            externalProcess.command = [root.backend, "test-status-failure"]
            externalProcess.running = true
        } else {
            root.fail("unknown test origin")
        }
    }

    function maybeFinish() {
        if (!root.started || idleController.refreshing || idleController.busy
                || idleController.refreshNeeded)
            return

        if (root.origin === "status-recovery") {
            if (!root.sawStatusError || root.statusStarts < 3
                    || idleController.errorMessage !== ""
                    || idleController.errorFromStatus)
                return
            if (root.caffeineChanges !== 0)
                root.fail("status recovery changed confirmed Caffeine state")
            if (root.statusStarts > 3)
                root.fail("status recovery started too many reads")
            console.log("VANHYPRARCH_IDLE_CONTROLLER_PASS origin="
                + root.origin + " outcome=recovered status=" + root.statusStarts)
            Qt.quit()
            return
        }

        const expected = root.outcome === "rollback"
            ? root.initialState : root.targetState
        if ((idleController.caffeine ? "on" : "off") !== expected)
            return
        if (root.outcome === "rollback"
                && idleController.errorMessage.indexOf("rolled back") < 0)
            return
        if (root.outcome !== "rollback" && idleController.errorFromStatus)
            root.fail("successful scenario retained a status error")
        const expectedChanges = expected === root.initialState ? 0 : 1
        if (root.caffeineChanges !== expectedChanges)
            root.fail("confirmed state changed an unexpected number of times: "
                + root.caffeineChanges)
        const expectedStatusStarts = root.origin === "burst"
                || root.origin === "rapid" ? 3 : 2
        if (root.statusStarts < expectedStatusStarts)
            return
        if (root.statusStarts !== expectedStatusStarts)
            root.fail("refresh coalescing started an unexpected number of reads: "
                + root.statusStarts)
        console.log("VANHYPRARCH_IDLE_CONTROLLER_PASS origin=" + root.origin
            + " outcome=" + root.outcome + " status=" + root.statusStarts)
        Qt.quit()
    }

    IdleController {
        id: idleController

        onReadyChanged: {
            if (!ready || root.initialized)
                return
            const confirmed = caffeine ? "on" : "off"
            if (confirmed !== root.initialState)
                root.fail("initial authoritative state mismatch")
            root.initialized = true
            Qt.callLater(root.startScenario)
        }
        onCaffeineChanged: {
            if (root.started)
                root.caffeineChanges += 1
            Qt.callLater(root.maybeFinish)
        }
        onBusyChanged: Qt.callLater(root.maybeFinish)
        onRefreshingChanged: Qt.callLater(root.maybeFinish)
        onRefreshNeededChanged: Qt.callLater(root.maybeFinish)
        onErrorMessageChanged: Qt.callLater(root.maybeFinish)
        onErrorFromStatusChanged: {
            if (!root.started || !errorFromStatus)
                return
            root.sawStatusError = true
            if (root.origin === "status-recovery" && !root.recoveryRequested) {
                root.recoveryRequested = true
                Qt.callLater(function() { idleController.refreshStatus(true) })
            }
        }
    }

    FileView {
        id: publishedView

        path: root.testRoot + "/published"
        watchChanges: true
        printErrors: false
        onFileChanged: publishedView.reload()
        onLoaded: {
            if (!root.started)
                return
            const value = String(publishedView.text()).trim()
            if (value !== root.targetState || root.publishedSeen)
                return
            root.publishedSeen = true
            if ((idleController.caffeine ? "on" : "off") !== root.initialState)
                root.fail("Caffeine presentation changed before confirmation")
            const invalidations = root.origin === "burst"
                    || root.origin === "rapid" ? 3 : 1
            for (let index = 0; index < invalidations; ++index)
                idleController.refreshStatus(true)
            if (root.origin === "controller")
                root.releaseTransaction()
            else if ((root.origin === "external" || root.origin === "burst")
                    && root.statusStarts >= 2)
                root.releaseTransaction()
        }
    }

    FileView {
        id: statusView

        path: root.testRoot + "/status.log"
        watchChanges: true
        printErrors: false
        onFileChanged: statusView.reload()
        onLoaded: {
            root.statusStarts = root.lineCount(statusView.text())
            if ((root.origin === "external" || root.origin === "burst")
                    && root.publishedSeen
                    && root.statusStarts >= 2)
                root.releaseTransaction()
            Qt.callLater(root.maybeFinish)
        }
    }

    Process {
        id: externalProcess

        onExited: function(exitCode, exitStatus) {
            if (root.outcome === "rollback" && exitCode === 0)
                root.fail("rollback transaction unexpectedly succeeded")
            if (root.outcome !== "rollback" && exitCode !== 0)
                root.fail("external transaction failed")
            Qt.callLater(root.maybeFinish)
        }
    }

    Process {
        id: releaseProcess

        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0)
                root.fail("could not release fixture transaction")
        }
    }

    Timer {
        interval: 10
        repeat: true
        running: true
        onTriggered: root.maybeFinish()
    }

    Timer {
        interval: 8000
        running: true
        onTriggered: root.fail("scenario timed out")
    }
}
