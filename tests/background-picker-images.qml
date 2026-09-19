import QtQuick
import QtTest

TestCase {
    id: root

    name: "BackgroundPickerImages"
    when: windowShown
    visible: true
    width: 32
    height: 32
    property int transitionWidth: 552

    Image {
        id: transitionPreview

        visible: false
        width: root.transitionWidth
        height: Math.round(width * 9 / 16)
        source: Qt.resolvedUrl(
            "../assets/wallpapers/Light/Wolkenstein_1_light.png")
        sourceSize.width: 952
        sourceSize.height: 536
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
    }

    Component {
        id: previewComponent

        Image {
            visible: false
            asynchronous: true
            sourceSize.width: 320
            sourceSize.height: 180
        }
    }

    function test_missing_and_corrupt_previews_fail_safely() {
        const missingPreview = previewComponent.createObject(root, {
            source: "file:///__vanhyprarch_background_picker_test__/missing.png"
        })
        tryCompare(missingPreview, "status", Image.Error, 1000)
        missingPreview.destroy()

        const corruptPreview = previewComponent.createObject(root, {
            source: "data:image/png;base64,bm90IGEgcG5n"
        })
        tryCompare(corruptPreview, "status", Image.Error, 1000)
        corruptPreview.destroy()
    }

    function test_loaded_preview_survives_depth_resizing() {
        tryCompare(transitionPreview, "status", Image.Ready, 3000)
        const originalSource = transitionPreview.source

        for (const width of [724, 952, 724, 552]) {
            transitionWidth = width
            wait(0)
            compare(transitionPreview.source, originalSource)
            compare(transitionPreview.sourceSize.width, 952)
            compare(transitionPreview.sourceSize.height, 536)
            compare(transitionPreview.status, Image.Ready)
        }
    }
}
