// SPDX-License-Identifier: GPL-2.0-only

import QtQuick

FocusScope {
    id: root

    required property bool interactive
    required property bool canSubmit
    required property bool submitting
    required property string configurationError
    readonly property real scaleFactor: Math.max(0.72, Math.min(2.0,
        Math.min(width, height) / 1080.0))
    readonly property real compositionFactor: 0.6
    readonly property alias passwordInput: passwordInput
    readonly property alias shutdownLabel: shutdownLabel
    readonly property alias rebootLabel: rebootLabel
    readonly property alias logo: vanillaLogo
    readonly property string displayedError: errorLabel.text
    property bool submissionLocked: false
    property string authenticationError: ""

    signal loginRequested(string password)
    signal shutdownRequested()
    signal rebootRequested()

    visible: interactive
    focus: interactive

    function focusPassword(): void {
        if (root.interactive && root.configurationError === ""
                && !root.submissionLocked)
            passwordInput.forceActiveFocus()
    }

    function submit(): void {
        if (!root.canSubmit || root.submissionLocked)
            return

        root.submissionLocked = true
        root.authenticationError = ""
        root.loginRequested(passwordInput.text)
    }

    function authenticationFailed(): void {
        passwordInput.text = ""
        root.submissionLocked = false
        root.authenticationError = "Authentication failed"
        Qt.callLater(root.focusPassword)
    }

    function authenticationSucceeded(): void {
        passwordInput.text = ""
        root.submissionLocked = false
        root.authenticationError = ""
    }

    function handleKey(event): void {
        if (event.key === Qt.Key_F1) {
            root.shutdownRequested()
            event.accepted = true
        } else if (event.key === Qt.Key_F2) {
            root.rebootRequested()
            event.accepted = true
        }
    }

    onInteractiveChanged: {
        if (interactive)
            Qt.callLater(root.focusPassword)
    }
    Component.onCompleted: Qt.callLater(root.focusPassword)

    Row {
        id: powerControls

        objectName: "powerControls"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.topMargin: Math.round(24 * root.scaleFactor)
        anchors.leftMargin: Math.round(28 * root.scaleFactor)
        spacing: Math.round(24 * root.scaleFactor)

        Text {
            id: shutdownLabel

            objectName: "shutdownLabel"
            text: "F1 Shutdown"
            color: "#D8D8D8"
            font.pixelSize: Math.round(14 * root.scaleFactor)

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.shutdownRequested()
            }
        }

        Text {
            id: rebootLabel

            objectName: "rebootLabel"
            text: "F2 Reboot"
            color: "#D8D8D8"
            font.pixelSize: Math.round(14 * root.scaleFactor)

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.rebootRequested()
            }
        }
    }

    Item {
        id: loginBlock

        x: (parent.width - width) / 2
        y: (parent.height - height) / 2 - Math.round(24 * root.scaleFactor)
        width: Math.round(Math.min(Math.round(420 * root.scaleFactor),
            Math.round(parent.width * 0.72)) * root.compositionFactor)
        height: passwordFrame.y + passwordFrame.height

        Image {
            id: vanillaLogo

            objectName: "vanillaLogo"
            anchors.top: parent.top
            x: (parent.width - width) / 2
            width: Math.round(Math.min(Math.round(180 * root.scaleFactor),
                Math.round(root.width * 0.25)) * root.compositionFactor)
            height: width
            source: Qt.resolvedUrl("logo.svg")
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }

        Rectangle {
            id: passwordFrame

            objectName: "passwordFrame"
            anchors.top: vanillaLogo.bottom
            anchors.topMargin: Math.round(Math.round(48 * root.scaleFactor)
                * root.compositionFactor)
            x: (parent.width - width) / 2
            width: parent.width
            height: Math.round(Math.round(46 * root.scaleFactor)
                * root.compositionFactor)
            radius: 0
            color: "#000000"
            border.width: Math.max(1, Math.round(root.scaleFactor
                * root.compositionFactor))
            border.color: root.authenticationError !== "" ? "#BE5015"
                : passwordInput.activeFocus ? "#FCDA02" : "#595959"

            TextInput {
                id: passwordInput

                objectName: "passwordInput"
                anchors.fill: parent
                anchors.leftMargin: Math.round(Math.round(12 * root.scaleFactor)
                    * root.compositionFactor)
                anchors.rightMargin: Math.round(Math.round(12 * root.scaleFactor)
                    * root.compositionFactor)
                color: "#F2F2F2"
                selectionColor: "#6D3523"
                selectedTextColor: "#FFFFFF"
                font.pixelSize: Math.round(Math.round(17 * root.scaleFactor)
                    * root.compositionFactor)
                verticalAlignment: TextInput.AlignVCenter
                echoMode: TextInput.Password
                inputMethodHints: Qt.ImhHiddenText | Qt.ImhSensitiveData
                    | Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
                enabled: root.interactive && root.configurationError === ""
                    && !root.submissionLocked
                focus: root.interactive
                activeFocusOnTab: true
                cursorVisible: activeFocus
                clip: true

                onTextChanged: {
                    if (root.authenticationError !== "")
                        root.authenticationError = ""
                }
                Keys.priority: Keys.BeforeItem
                Keys.onReturnPressed: event => {
                    root.submit()
                    event.accepted = true
                }
                Keys.onEnterPressed: event => {
                    root.submit()
                    event.accepted = true
                }
                Keys.onPressed: event => root.handleKey(event)
            }
        }
    }

    Text {
        id: errorLabel

        objectName: "errorLabel"
        anchors.top: loginBlock.bottom
        anchors.topMargin: Math.round(10 * root.scaleFactor)
        anchors.horizontalCenter: parent.horizontalCenter
        text: root.configurationError !== ""
            ? root.configurationError : root.authenticationError
        visible: text !== ""
        color: "#BE5015"
        font.pixelSize: Math.round(13 * root.scaleFactor)
    }
}
