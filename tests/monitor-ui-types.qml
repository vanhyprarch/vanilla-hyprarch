import QtQuick
import Quickshell
import "components"

ShellRoot {
    id: root

    function require(value: bool, message: string): void {
        if (!value) {
            console.error("MONITOR_CONFIRMATION_LAYOUT_FAIL: " + message)
            Qt.exit(1)
        }
    }

    function namedChild(item: var, name: string): var {
        if (item === null || item === undefined)
            return null
        if (item.objectName === name)
            return item
        const children = item.children || []
        for (const child of children) {
            const match = namedChild(child, name)
            if (match !== null)
                return match
        }
        return null
    }

    MonitorController {
        id: monitorController
        checksEnabled: false
        executionEnabled: false
        transactionId: "layout-test"
        transactionState: "temporary-active"
        transactionConnector: "DP-1"
        transactionCandidate: ({
            connector: "DP-1",
            mode: {
                width: 2560,
                height: 1440,
                refresh_millihz: 59950
            },
            bitdepth: null,
            scale_millionths: null,
            hdr_mode: null,
            automatic_hdr: null
        })
        presentationRemainingSeconds: 8
    }

    VisualMetrics {
        id: visualMetrics
        fontBaseSize: 12
    }

    QtObject {
        id: shellTheme
        readonly property color background: "#202020"
        readonly property color panelOutline: "#404040"
        readonly property color text: "#ffffff"
        readonly property color textMuted: "#bbbbbb"
        readonly property color pressedFill: "#505050"
        readonly property color hoverFill: "#404040"
        readonly property color normalFill: "#303030"
        readonly property color activeFill: "#606060"
    }

    QtObject {
        id: focusCoordinator
    }

    QtObject {
        id: textSizeController
        property var values: [10, 11, 12, 13, 14]
        property int baseSize: 12
        property bool busy: false
        function requestSize(value: int): bool { return true }
    }

    MonitorConfirmationPanel {
        id: confirmationPanel
        controller: monitorController
        metrics: visualMetrics
        theme: shellTheme
        focusCoordinator: focusCoordinator
        targetScreen: null
        screenName: "layout-test-screen"
        screenWidth: 1000
        screenHeight: 800
        dockWidth: 0
        width: implicitWidth
        height: implicitHeight
    }

    MonitorPanel {
        id: scaleTestPanel
        theme: shellTheme
        metrics: visualMetrics
        targetScreen: null
        focusCoordinator: focusCoordinator
        textSizeController: textSizeController
        monitorController: monitorController
        visible: false
    }

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
            const content = namedChild(confirmationPanel, "confirmationContent")
            const description = namedChild(confirmationPanel,
                "confirmationDescription")
            const actions = namedChild(confirmationPanel, "confirmationActions")
            const revertButton = namedChild(confirmationPanel,
                "confirmationRevertButton")
            const keepButton = namedChild(confirmationPanel,
                "confirmationKeepButton")
            const revertLabel = namedChild(confirmationPanel,
                "confirmationRevertLabel")
            const keepLabel = namedChild(confirmationPanel,
                "confirmationKeepLabel")
            require(content !== null && description !== null && actions !== null,
                "layout objects were not constructed")
            require(revertButton !== null && keepButton !== null
                    && revertLabel !== null && keepLabel !== null,
                "button objects were not constructed")
            require(Math.abs(confirmationPanel.implicitHeight
                    - content.implicitHeight - visualMetrics.overlayPadding * 2) < 0.5,
                "overlay height does not follow content")
            require(Math.abs(content.y - visualMetrics.overlayPadding) < 0.5,
                "top padding is not the shared overlay padding")
            require(Math.abs(confirmationPanel.implicitHeight
                    - content.y - content.implicitHeight
                    - visualMetrics.overlayPadding) < 0.5,
                "bottom padding is not symmetric")
            require(Math.abs(content.x - visualMetrics.overlayPadding) < 0.5,
                "left padding is not the shared overlay padding")
            require(Math.abs(confirmationPanel.implicitWidth - content.x
                    - content.width - visualMetrics.overlayPadding) < 0.5,
                "right padding is not symmetric")
            require(confirmationPanel.implicitWidth
                    === Math.max(confirmationPanel.minimumPanelWidth,
                        Math.min(confirmationPanel.maximumPanelWidth,
                            confirmationPanel.idealPanelWidth)),
                "normal panel width does not follow its bounded content width")
            require(confirmationPanel.implicitWidth
                    < confirmationPanel.maximumPanelWidth,
                "normal content still receives the full maximum width")
            require(confirmationPanel.implicitWidth
                    - confirmationPanel.naturalContentWidth
                    <= visualMetrics.overlayPadding * 2 + 1,
                "normal content retains excessive horizontal whitespace")
            require(Math.abs(actions.x - (content.width - actions.width) / 2) <= 0.5,
                "action row is not centered")
            require(Math.abs(revertButton.width - keepButton.width) < 0.5,
                "action buttons are not equal width")
            require(actions.width < content.width,
                "action buttons still fill the content width")
            require(revertButton.width + 0.5 >= Math.max(revertLabel.implicitWidth,
                    keepLabel.implicitWidth) + visualMetrics.rowSidePadding * 2,
                "button labels do not have deliberate horizontal padding")
            const automaticArbitrary = {
                scale_millionths: 1333333, scale_automatic: true
            }
            require(scaleTestPanel.scaleTextFor(automaticArbitrary) === "1.333333×",
                "automatic Scale did not display its effective numeric value")
            for (const preset of [1, 1.25, 1.5, 2])
                require(!scaleTestPanel.scaleMatchesOutput(
                    automaticArbitrary, preset),
                    "automatic arbitrary Scale selected a Vanilla preset")
            const automaticPreset = {
                scale_millionths: 1250000, scale_automatic: true
            }
            require(scaleTestPanel.scaleTextFor(automaticPreset) === "1.25×",
                "automatic preset-valued Scale did not display its effective value")
            for (const preset of [1, 1.25, 1.5, 2])
                require(!scaleTestPanel.scaleMatchesOutput(automaticPreset, preset),
                    "automatic preset-valued Scale selected a Vanilla preset")
            const explicitPreset = {
                scale_millionths: 1250000, scale_automatic: false
            }
            require(scaleTestPanel.scaleMatchesOutput(explicitPreset, 1.25)
                    && !scaleTestPanel.scaleMatchesOutput(explicitPreset, 1.5),
                "explicit Scale did not select exactly its matching preset")
            monitorController.transactionCandidate = ({
                connector: "DP-1",
                mode: {
                    width: 15360,
                    height: 8640,
                    refresh_millihz: 240000
                },
                bitdepth: 10,
                scale_millionths: null,
                hdr_mode: "always-on",
                automatic_hdr: 0
            })
            visualMetrics.fontBaseSize = 20
            confirmationPanel.screenWidth = 420
            Qt.callLater(function() {
                require(confirmationPanel.implicitWidth
                        <= confirmationPanel.maximumPanelWidth,
                    "long content exceeds the maximum readable width")
                require(description.lineCount > 1,
                    "long constrained description did not wrap")
                require(description.paintedWidth <= description.width + 0.5,
                    "long confirmation description overflows horizontally")
                require(description.implicitHeight + 0.5
                        >= description.contentHeight,
                    "long confirmation description clips vertically")
                console.log("MONITOR_UI_TYPES_TEST_PASS")
                Qt.quit()
            })
        })
    }
}
