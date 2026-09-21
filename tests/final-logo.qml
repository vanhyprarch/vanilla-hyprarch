import QtQuick
import QtQuick.VectorImage
import Quickshell

ShellRoot {
    id: root

    function fail(message: string): void {
        console.error("FINAL_LOGO_TEST_FAILURE: " + message)
        Qt.quit()
        throw new Error(message)
    }

    VectorImage {
        id: logo

        source: Qt.resolvedUrl("assets/logo.svg")
        width: 40
        height: 40
        fillMode: VectorImage.PreserveAspectFit
        preferredRendererType: VectorImage.CurveRenderer
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            if (logo.width !== 40 || logo.height !== 40)
                root.fail("logical dock bounds changed")
            if (logo.fillMode !== VectorImage.PreserveAspectFit)
                root.fail("square viewBox is not aspect-fit")
            if (logo.preferredRendererType !== VectorImage.CurveRenderer)
                root.fail("CurveRenderer is not selected")
            if (!logo.source.toString().endsWith("/assets/logo.svg"))
                root.fail("canonical SVG source is not loaded")
            console.log("FINAL_LOGO_TEST_PASS")
            Qt.quit()
        }
    }
}
