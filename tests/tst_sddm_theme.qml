// SPDX-License-Identifier: GPL-2.0-only

import QtQuick
import QtTest
import "../system/usr/share/sddm/themes/vanhyprarch" as Theme

Item {
    id: harness

    width: 1920
    height: 1080

    ListModel {
        id: sessions
    }

    QtObject {
        id: configMock

        property string targetUserValue: "tester"
        property string targetSessionFileValue:
            "/usr/share/wayland-sessions/vanhyprarch.desktop"

        function stringValue(key) {
            if (key === "targetUser")
                return targetUserValue
            if (key === "targetSessionFile")
                return targetSessionFileValue
            return ""
        }
    }

    QtObject {
        id: sddmMock

        property bool canPowerOff: true
        property bool canReboot: true
        property int loginCalls: 0
        property int shutdownCalls: 0
        property int rebootCalls: 0
        property string loginUser: ""
        property string loginPassword: ""
        property int loginSessionIndex: -1

        signal loginFailed()
        signal loginSucceeded()

        function login(user, password, sessionIndex) {
            loginCalls += 1
            loginUser = user
            loginPassword = password
            loginSessionIndex = sessionIndex
        }

        function powerOff() {
            shutdownCalls += 1
        }

        function reboot() {
            rebootCalls += 1
        }

        function reset() {
            loginCalls = 0
            shutdownCalls = 0
            rebootCalls = 0
            loginUser = ""
            loginPassword = ""
            loginSessionIndex = -1
        }
    }

    Component {
        id: mainComponent

        Theme.Main {
        }
    }

    TestCase {
        id: testCase

        name: "SddmThemeContract"
        when: windowShown

        function init() {
            sessions.clear()
            configMock.targetUserValue = "tester"
            configMock.targetSessionFileValue =
                "/usr/share/wayland-sessions/vanhyprarch.desktop"
            sddmMock.reset()
        }

        function createMain(primary = true) {
            return createTemporaryObject(mainComponent, harness, {
                "width": harness.width,
                "height": harness.height,
                "sddmApi": sddmMock,
                "sessionSource": sessions,
                "themeConfiguration": configMock,
                "primaryScreenActive": primary
            })
        }

        function addVanillaSession() {
            sessions.append({
                "file": "/usr/share/wayland-sessions/vanhyprarch.desktop"
            })
        }

        function test_normal_scene_and_initial_focus() {
            addVanillaSession()
            const main = createMain()
            verify(main !== null)
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            compare(main.sessionResolver.matchCount, 1)
            verify(main.bindingValid)
            compare(main.color.toString(), "#000000")
            verify(main.loginScene.visible)
            compare(main.loginScene.shutdownLabel.text, "F1 Shutdown")
            compare(main.loginScene.rebootLabel.text, "F2 Reboot")
            compare(main.loginScene.passwordInput.echoMode, TextInput.Password)
            compare(main.loginScene.passwordInput.text, "")
            tryVerify(() => main.loginScene.passwordInput.activeFocus)
            verify(main.loginScene.passwordInput.cursorVisible)
            compare(main.loginScene.displayedError, "")
        }

        function test_enter_login_and_duplicate_submission_guard() {
            sessions.append({"file": "/usr/share/wayland-sessions/other.desktop"})
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 1)
            tryVerify(() => main.loginScene.passwordInput.activeFocus)
            main.loginScene.passwordInput.text = "not-recorded-by-production"
            keyClick(Qt.Key_Return)
            compare(sddmMock.loginCalls, 1)
            compare(sddmMock.loginUser, "tester")
            compare(sddmMock.loginPassword, "not-recorded-by-production")
            compare(sddmMock.loginSessionIndex, 1)
            main.loginScene.submit()
            compare(sddmMock.loginCalls, 1)
        }

        function test_login_failure_clears_refocuses_and_stays_generic() {
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            main.loginScene.passwordInput.text = "wrong"
            main.loginScene.submit()
            compare(sddmMock.loginCalls, 1)
            sddmMock.loginFailed()
            tryCompare(main.loginScene.passwordInput, "text", "")
            compare(main.submitting, false)
            compare(main.loginScene.submissionLocked, false)
            compare(main.loginScene.displayedError, "Authentication failed")
            tryVerify(() => main.loginScene.passwordInput.activeFocus)
            keyClick(Qt.Key_X)
            compare(main.loginScene.displayedError, "")
        }

        function test_login_success_clears_the_transient_password() {
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            main.loginScene.passwordInput.text = "temporary"
            main.loginScene.submit()
            sddmMock.loginSucceeded()
            compare(main.loginScene.passwordInput.text, "")
            compare(main.submitting, false)
            compare(main.loginScene.submissionLocked, false)
        }

        function test_empty_user_fails_closed() {
            configMock.targetUserValue = ""
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            verify(!main.bindingValid)
            main.loginScene.submit()
            compare(sddmMock.loginCalls, 0)
            compare(main.loginScene.displayedError, "Configuration unavailable")
        }

        function test_empty_session_path_fails_closed() {
            configMock.targetSessionFileValue = ""
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "matchCount", 0)
            verify(!main.bindingValid)
            main.loginScene.submit()
            compare(sddmMock.loginCalls, 0)
        }

        function test_zero_and_multiple_session_matches_fail_closed() {
            sessions.append({"file": "/usr/share/wayland-sessions/other.desktop"})
            let main = createMain()
            tryCompare(main.sessionResolver, "matchCount", 0)
            main.loginScene.submit()
            compare(sddmMock.loginCalls, 0)
            main.destroy()

            sessions.clear()
            addVanillaSession()
            addVanillaSession()
            main = createMain()
            tryCompare(main.sessionResolver, "matchCount", 2)
            compare(main.sessionResolver.sessionIndex, -1)
            main.loginScene.submit()
            compare(sddmMock.loginCalls, 0)
        }

        function test_session_reordering_resolves_by_file() {
            addVanillaSession()
            sessions.append({"file": "/usr/share/wayland-sessions/other.desktop"})
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            sessions.move(0, 1, 1)
            tryCompare(main.sessionResolver, "sessionIndex", 1)
            main.loginScene.passwordInput.text = "secret"
            main.loginScene.submit()
            compare(sddmMock.loginSessionIndex, 1)
        }

        function test_power_keys_and_clicks_use_only_the_matching_api() {
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            tryVerify(() => main.loginScene.passwordInput.activeFocus)
            keyClick(Qt.Key_F1)
            compare(sddmMock.shutdownCalls, 1)
            compare(sddmMock.rebootCalls, 0)
            keyClick(Qt.Key_F2)
            compare(sddmMock.shutdownCalls, 1)
            compare(sddmMock.rebootCalls, 1)
            mouseClick(main.loginScene.shutdownLabel)
            compare(sddmMock.shutdownCalls, 2)
            mouseClick(main.loginScene.rebootLabel)
            compare(sddmMock.rebootCalls, 2)
        }

        function test_secondary_screen_is_black_and_noninteractive() {
            addVanillaSession()
            const main = createMain(false)
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            compare(main.color.toString(), "#000000")
            verify(!main.loginScene.visible)
            verify(!main.loginScene.passwordInput.activeFocus)
        }

        function test_scaled_logo_and_password_block_uses_offset_center() {
            addVanillaSession()
            const main = createMain()
            const scene = main.loginScene
            const logo = scene.logo
            const frame = scene.passwordInput.parent
            const input = scene.passwordInput
            let errorLabel = null
            for (const child of scene.children) {
                if (child.objectName === "errorLabel")
                    errorLabel = child
            }
            verify(errorLabel !== null)
            compare(scene.compositionFactor, 0.6)

            for (const size of [[1920, 1080], [1024, 768]]) {
                main.width = size[0]
                main.height = size[1]
                const scale = scene.scaleFactor
                const designLogo = Math.min(Math.round(180 * scale),
                    Math.round(scene.width * 0.25))
                const designFrame = Math.min(Math.round(420 * scale),
                    Math.round(scene.width * 0.72))
                compare(logo.width, Math.round(designLogo * 0.6))
                compare(logo.height, Math.round(designLogo * 0.6))
                compare(frame.width, Math.round(designFrame * 0.6))
                compare(frame.height, Math.round(Math.round(46 * scale) * 0.6))
                compare(input.font.pixelSize,
                    Math.round(Math.round(17 * scale) * 0.6))
                compare(input.anchors.leftMargin,
                    Math.round(Math.round(12 * scale) * 0.6))
                compare(input.anchors.rightMargin,
                    Math.round(Math.round(12 * scale) * 0.6))
                compare(frame.border.width,
                    Math.max(1, Math.round(scale * 0.6)))
                const logoTop = logo.mapToItem(scene, 0, 0)
                const frameTop = frame.mapToItem(scene, 0, 0)
                verify(Math.abs(logoTop.x + logo.width / 2 - scene.width / 2) < 0.01)
                verify(Math.abs(frameTop.x + frame.width / 2 - scene.width / 2) < 0.01,
                    `frame center ${frameTop.x + frame.width / 2}, expected ${scene.width / 2}`)
                compare(frameTop.y - logoTop.y - logo.height,
                    Math.round(Math.round(48 * scale) * 0.6))
                const blockCenter = (logoTop.y + frameTop.y + frame.height) / 2
                const expectedCenter = scene.height / 2 - Math.round(24 * scale)
                verify(Math.abs(blockCenter - expectedCenter) < 0.01,
                    `block center ${blockCenter}, expected ${expectedCenter}`)

                scene.authenticationError = "Authentication failed"
                compare(errorLabel.visible, true)
                compare(logo.mapToItem(scene, 0, 0).y, logoTop.y)
                compare(frame.mapToItem(scene, 0, 0).y, frameTop.y)
                scene.authenticationError = ""
            }
        }

        function test_layout_scales_with_bounds() {
            addVanillaSession()
            const main = createMain()
            tryCompare(main.sessionResolver, "sessionIndex", 0)
            main.width = 1024
            main.height = 768
            compare(main.loginScene.scaleFactor, 0.72)
            verify(main.loginScene.passwordInput.parent.width <= main.width * 0.72 + 1)
            main.width = 3840
            main.height = 2160
            compare(main.loginScene.scaleFactor, 2.0)
            verify(main.loginScene.passwordInput.parent.width <= main.width * 0.72 + 1)
        }
    }
}
