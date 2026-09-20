import QtQuick
import Quickshell
import Quickshell.Io
import "components"

ShellRoot {
    id: root

    IdleController {
        id: idleController

        onReadyChanged: {
            if (ready)
                console.log("VANHYPRARCH_IDLE_IPC_READY caffeine="
                    + (caffeine ? "on" : "off"))
        }
    }

    IpcHandler {
        target: "vanhyprarch.idle"

        function refresh(): void {
            idleController.refreshStatus(true)
        }
    }

    Timer {
        interval: 60000
        repeat: true
        running: true
    }
}
