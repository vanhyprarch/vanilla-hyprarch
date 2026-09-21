import QtQuick
import Quickshell

ShellRoot {
    id: root

    function fail(message: string): void {
        console.error("FINAL_LOGO_TEST_FAILURE: " + message)
        Qt.quit()
        throw new Error(message)
    }

    Image {
        id: logo

        source: Qt.resolvedUrl("assets/logo.svg")
        width: 40
        height: 40
        fillMode: Image.PreserveAspectFit
        smooth: true

    }

    Timer {
        property int attempts: 0

        interval: 20
        running: true
        repeat: true
        onTriggered: {
            attempts++
            if (logo.status === Image.Error)
                root.fail("SVG resource failed to load")
            if (logo.status === Image.Ready) {
                if (Math.abs(logo.paintedWidth - 40) > 0.01
                        || Math.abs(logo.paintedHeight - 40) > 0.01)
                    root.fail("square viewBox was distorted at dock size")
                console.log("FINAL_LOGO_TEST_PASS")
                Qt.quit()
            } else if (attempts >= 150) {
                root.fail("SVG resource did not become ready")
            }
        }
    }
}
