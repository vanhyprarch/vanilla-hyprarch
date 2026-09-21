import QtQuick
import Quickshell
import "components"

ShellRoot {
    Component {
        Monitor {}
    }

    Component {
        MonitorPanel {}
    }

    Component {
        MonitorConfirmationPanel {}
    }

    Component.onCompleted: {
        Qt.callLater(function() {
            console.log("MONITOR_UI_TYPES_TEST_PASS")
            Qt.quit()
        })
    }
}
