// SPDX-License-Identifier: GPL-2.0-only

import QtQuick

Rectangle {
    id: root

    // SDDM provides these as QML context properties. Explicit properties keep
    // the contract injectable for deterministic tests without changing the
    // production context lookup.
    // qmllint disable unqualified
    property var sddmApi: typeof sddm === "undefined" ? null : sddm
    property var sessionSource: typeof sessionModel === "undefined"
        ? null : sessionModel
    property var themeConfiguration: typeof config === "undefined"
        ? null : config
    property bool primaryScreenActive: typeof primaryScreen === "undefined"
        ? true : primaryScreen
    // qmllint enable unqualified
    readonly property string targetUser: configString("targetUser")
    readonly property string targetSessionFile: configString("targetSessionFile")
    readonly property bool targetUserValid: validUser(targetUser)
    readonly property bool bindingValid: targetUserValid
        && targetSessionFile !== "" && targetSessionFile.startsWith("/")
        && targetSessionFile.endsWith(".desktop") && sessionResolver.valid
    readonly property alias loginScene: loginScene
    readonly property alias sessionResolver: sessionResolver
    property bool submitting: false

    color: "#000000"
    width: 1920
    height: 1080

    function configString(key: string): string {
        if (root.themeConfiguration === null
                || root.themeConfiguration === undefined
                || typeof root.themeConfiguration.stringValue !== "function")
            return ""
        return String(root.themeConfiguration.stringValue(key))
    }

    function validUser(candidate: string): bool {
        return candidate !== "" && candidate === candidate.trim()
            && !/[\u0000-\u001f\u007f\/:]/.test(candidate)
    }

    function requestLogin(password: string): void {
        if (root.submitting || !root.bindingValid || root.sddmApi === null
                || typeof root.sddmApi.login !== "function")
            return

        root.submitting = true
        root.sddmApi.login(root.targetUser, password,
            sessionResolver.sessionIndex)
    }

    function requestShutdown(): void {
        if (root.sddmApi !== null && root.sddmApi.canPowerOff !== false
                && typeof root.sddmApi.powerOff === "function")
            root.sddmApi.powerOff()
    }

    function requestReboot(): void {
        if (root.sddmApi !== null && root.sddmApi.canReboot !== false
                && typeof root.sddmApi.reboot === "function")
            root.sddmApi.reboot()
    }

    SessionResolver {
        id: sessionResolver

        sessionSource: root.sessionSource
        targetFile: root.targetSessionFile
    }

    LoginScene {
        id: loginScene

        objectName: "loginScene"
        anchors.fill: parent
        interactive: root.primaryScreenActive
        canSubmit: root.bindingValid && !root.submitting
        submitting: root.submitting
        configurationError: root.bindingValid ? "" : "Configuration unavailable"

        onLoginRequested: password => root.requestLogin(password)
        onShutdownRequested: root.requestShutdown()
        onRebootRequested: root.requestReboot()
    }

    Connections {
        target: root.sddmApi
        enabled: root.sddmApi !== null
        ignoreUnknownSignals: false

        function onLoginFailed(): void {
            root.submitting = false
            loginScene.authenticationFailed()
        }

        function onLoginSucceeded(): void {
            root.submitting = false
            loginScene.authenticationSucceeded()
        }
    }
}
