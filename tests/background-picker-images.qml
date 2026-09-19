import QtQuick
import QtTest

TestCase {
    id: root

    name: "BackgroundPickerImages"
    when: windowShown
    visible: true
    width: 32
    height: 32

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
}
