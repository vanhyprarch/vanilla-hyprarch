pragma ComponentBehavior: Bound

import QtQuick
import Quickshell

CenteredOverlay {
    id: root

    required property SuperSpace controller
    required property var metrics
    required property var theme
    required property string screenName
    required property int dockWidth

    readonly property bool activeForScreen:
        controller.activeScreenName === screenName
    readonly property bool confirming:
        controller.pendingPowerAction !== ""
    property string selectedEntryIdentity: ""
    readonly property int selectedEntryIndex: entriesView.currentIndex
    readonly property int panelWidth: Math.max(metrics.scaled(320),
        Math.min(metrics.wideOverlayMaximum,
            screenWidth - dockWidth - metrics.scaled(48)))
    readonly property int panelHeight: Math.max(metrics.scaled(320),
        Math.min(metrics.scaled(620), screenHeight - metrics.scaled(64)))

    function syncVisibility(): void {
        const shouldShow = controller.isOpen && activeForScreen
        if (visible !== shouldShow)
            visible = shouldShow
    }

    function resetSelection(): void {
        selectedEntryIdentity = ""
        for (let index = 0; index < controller.visibleEntries.length; ++index) {
            if (entrySelectable(index)) {
                selectEntryAt(index)
                entriesView.positionViewAtBeginning()
                break
            }
        }
        if (selectedEntryIdentity === "")
            entriesView.currentIndex = -1
    }

    function entrySelectable(index: int): bool {
        return index >= 0 && index < controller.visibleEntries.length
            && controller.visibleEntries[index].selectable !== false
            && controller.visibleEntries[index].enabled !== false
    }

    function selectEntryAt(index: int): bool {
        if (!entrySelectable(index))
            return false
        entriesView.currentIndex = index
        selectedEntryIdentity = controller.entryIdentity(
            controller.visibleEntries[index])
        return true
    }

    function preserveSelection(): void {
        const identity = selectedEntryIdentity
        if (identity !== "") {
            for (let index = 0; index < controller.visibleEntries.length; ++index) {
                if (entrySelectable(index)
                        && controller.entryIdentity(controller.visibleEntries[index])
                            === identity) {
                    entriesView.currentIndex = index
                    entriesView.positionViewAtIndex(index, ListView.Contain)
                    return
                }
            }
        }
        resetSelection()
    }

    function focusPrimaryControl(): void {
        Qt.callLater(function() {
            if (root.confirming || root.controller.currentComponentId !== "")
                panelSurface.forceActiveFocus()
            else
                searchInput.forceActiveFocus()
        })
    }

    function moveSelection(offset: int): void {
        if (entriesNavigation.move(offset))
            selectedEntryIdentity = controller.entryIdentity(
                controller.visibleEntries[entriesView.currentIndex])
    }

    function activateSelection(): void {
        if (entriesView.currentIndex < 0
                || entriesView.currentIndex >= entriesView.count)
            return
        controller.activate(controller.visibleEntries[entriesView.currentIndex])
    }

    function handleKey(event): void {
        if (event.key === Qt.Key_Escape) {
            controller.goBack()
            event.accepted = true
        } else if (event.key === Qt.Key_Up) {
            moveSelection(-1)
            event.accepted = true
        } else if (event.key === Qt.Key_Down) {
            moveSelection(1)
            event.accepted = true
        } else if (event.key === Qt.Key_Return
                || event.key === Qt.Key_Enter) {
            activateSelection()
            event.accepted = true
        }
    }

    implicitWidth: panelWidth
    implicitHeight: panelHeight
    color: "transparent"
    visible: false

    onDismissed: controller.close()

    Component.onCompleted: syncVisibility()

    onVisibleChanged: {
        if (visible) {
            resetSelection()
            focusPrimaryControl()
        } else if (controller.isOpen && activeForScreen) {
            controller.close()
        }
    }

    Connections {
        target: root.controller

        function onIsOpenChanged(): void {
            root.syncVisibility()
        }

        function onActiveScreenNameChanged(): void {
            root.syncVisibility()
        }

        function onCurrentSectionChanged(): void {
            root.resetSelection()
            root.focusPrimaryControl()
        }

        function onCurrentComponentIdChanged(): void {
            root.resetSelection()
            root.focusPrimaryControl()
        }

        function onComponentSubviewChanged(): void {
            root.resetSelection()
            root.focusPrimaryControl()
        }

        function onVisibleEntriesChanged(): void {
            root.preserveSelection()
        }

        function onSearchTextChanged(): void {
            root.resetSelection()
        }

        function onPendingPowerActionChanged(): void {
            root.resetSelection()
            root.focusPrimaryControl()
        }
    }

    PanelSurface {
        id: panelSurface

        anchors.fill: parent
        metrics: root.metrics
        theme: root.theme
        padding: root.metrics.overlayPadding
        focus: root.confirming

        Keys.onPressed: event => root.handleKey(event)

        Text {
            id: titleText

            anchors {
                top: parent.top
                left: parent.left
                right: navigationAction.left
                rightMargin: root.metrics.contentGap
            }
            height: root.metrics.scaled(34)
            text: root.confirming ? "Confirm power action"
                : root.controller.currentComponentId === "local-dictation"
                    ? "Local Dictation"
                : root.controller.currentComponentId === "zig-screensaver"
                    ? "Zig Screensaver" : "Super + Space"
            textFormat: Text.PlainText
            color: root.theme.text
            font.pixelSize: root.metrics.prominentValueFontSize
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Rectangle {
            id: navigationAction

            anchors {
                top: titleText.top
                right: parent.right
            }
            width: navigationLabel.implicitWidth
                + root.metrics.rowSidePadding * 2
            height: titleText.height
            color: navigationMouse.pressed ? root.theme.pressedFill
                : navigationMouse.containsMouse ? root.theme.hoverFill
                    : "transparent"

            Text {
                id: navigationLabel

                anchors.centerIn: parent
                text: root.controller.currentSection === "root"
                        && !root.confirming ? "Close · Esc" : "Back · Esc"
                textFormat: Text.PlainText
                color: navigationMouse.containsMouse
                    ? root.theme.text : root.theme.textMuted
                font.pixelSize: root.metrics.detailFontSize
            }

            MouseArea {
                id: navigationMouse

                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.controller.goBack()
            }
        }

        Rectangle {
            id: searchBox

            anchors {
                top: titleText.bottom
                left: parent.left
                right: parent.right
                topMargin: root.metrics.contentGap
            }
            height: root.metrics.scaled(44)
            visible: !root.confirming && root.controller.currentComponentId === ""
            color: root.theme.surface
            border.width: searchInput.activeFocus
                ? root.metrics.controlOutlineThickness : 0
            border.color: root.theme.focus

            Text {
                anchors {
                    left: parent.left
                    leftMargin: root.metrics.rowSidePadding
                    verticalCenter: parent.verticalCenter
                }
                visible: searchInput.text.length === 0
                text: root.controller.currentSection === "apps"
                    ? "Search applications"
                    : root.controller.currentSection === "install"
                        ? "Enter package or search terms"
                    : root.controller.currentSection === "remove"
                        ? "Search installed packages"
                    : root.controller.currentSection === "update"
                        ? "Search update actions"
                    : root.controller.currentSection === "components"
                        ? "Search optional components"
                    : root.controller.currentSection === "power"
                        ? "Search power actions" : "Search apps and actions"
                textFormat: Text.PlainText
                color: root.theme.textMuted
                font.pixelSize: root.metrics.overlayFontSize
            }

            TextInput {
                id: searchInput

                anchors {
                    fill: parent
                    leftMargin: root.metrics.rowSidePadding
                    rightMargin: root.metrics.rowSidePadding
                }
                text: root.controller.searchText
                color: root.theme.text
                selectionColor: root.theme.focus
                selectedTextColor: root.theme.background
                font.pixelSize: root.metrics.overlayFontSize
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                Keys.priority: Keys.BeforeItem

                onTextEdited: {
                    if (root.controller.searchText !== text)
                        root.controller.searchText = text
                }

                Keys.onPressed: event => root.handleKey(event)
            }
        }

        SectionHeading {
            id: sectionHeading

            anchors {
                top: root.confirming || !searchBox.visible
                    ? titleText.bottom : searchBox.bottom
                left: parent.left
                right: parent.right
                topMargin: root.metrics.sectionGap
            }
            height: root.metrics.captionLineHeight
            metrics: root.metrics
            theme: root.theme
            text: root.confirming ? "Choose an action"
                : root.controller.currentSection === "apps" ? "Apps"
                    : root.controller.currentSection === "install"
                        ? "Install packages"
                    : root.controller.currentSection === "remove"
                        ? "Remove packages"
                    : root.controller.currentSection === "update" ? "Update"
                    : root.controller.currentSection === "components"
                        ? root.controller.componentSubview === "model" ? "Choose a model"
                        : root.controller.componentSubview === "languages" ? "Languages"
                        : root.controller.componentSubview === "duration" ? "Maximum recording"
                        : root.controller.componentSubview === "acceleration" ? "Choose acceleration"
                        : root.controller.componentSubview === "uninstall"
                            ? root.controller.currentComponentId === "zig-screensaver"
                                ? "Uninstall Zig Screensaver?" : "Uninstall Local Dictation?"
                        : root.controller.currentComponentId === "local-dictation" ? "Local Dictation"
                        : root.controller.currentComponentId === "zig-screensaver" ? "Zig Screensaver"
                        : "Additional system components"
                    : root.controller.currentSection === "power" ? "Power"
                        : root.controller.searchText.trim() === ""
                            ? "Choose a section" : "Results"
            verticalAlignment: Text.AlignVCenter
        }

        ListView {
            id: entriesView

            anchors {
                top: sectionHeading.bottom
                bottom: footerText.top
                left: parent.left
                right: parent.right
                topMargin: root.metrics.contentGap
                bottomMargin: root.metrics.contentGap
            }

            clip: true
            boundsBehavior: Flickable.StopAtBounds
            spacing: root.metrics.rowSpacing
            model: root.controller.visibleEntries

            WrappedListNavigation {
                id: entriesNavigation

                view: entriesView
                isSelectable: function(index) {
                    return root.entrySelectable(index)
                }
            }

            VerticalScrollIndicator {
                view: entriesView
                metrics: root.metrics
                theme: root.theme
            }

            onCountChanged: {
                if (count === 0)
                    currentIndex = -1
                else
                    root.preserveSelection()
            }

            delegate: Item {
                id: entryDelegate

                required property var modelData
                required property int index
                readonly property bool separator:
                    modelData.kind === "componentSeparator"

                width: entriesView.width - root.metrics.scrollIndicatorGutter
                height: separator ? root.metrics.sectionGap
                    : entryRow.implicitHeight

                PanelSeparator {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: entryDelegate.separator
                    metrics: root.metrics
                    theme: root.theme
                }

                PanelActionRow {
                    id: entryRow

                    width: parent.width
                    visible: !entryDelegate.separator
                    metrics: root.metrics
                    theme: root.theme
                    primaryText: entryDelegate.modelData.label || ""
                    secondaryText: entryDelegate.modelData.detail || ""
                    keyboardSelected: entryDelegate.index === entriesView.currentIndex
                    navigationFill: root.theme.navigationFill
                    selectionFill: root.theme.selectionFill
                    danger: entryDelegate.modelData.danger === true
                    enabled: entryDelegate.modelData.enabled !== false
                    interactive: root.entrySelectable(entryDelegate.index)
                    informational: entryDelegate.modelData.informational === true
                    active: entryDelegate.modelData.active === true
                    leading: entryIcon
                    activeFocusOnTab: false
                    onActivated: {
                        if (root.selectEntryAt(entryDelegate.index))
                            root.controller.activate(entryDelegate.modelData)
                    }
                }

                Component {
                    id: entryIcon

                    Image {
                        id: iconImage

                        property bool failed: false
                        readonly property string iconName:
                            entryDelegate.modelData.icon || "application-x-executable"

                        width: root.metrics.heroIconSize
                        height: root.metrics.heroIconSize
                        source: Quickshell.iconPath(!failed ? iconName
                            : "application-x-executable",
                            "application-x-executable")
                        sourceSize: Qt.size(width, height)
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                        onIconNameChanged: failed = false
                        onStatusChanged: {
                            if (status === Image.Error && !failed)
                                failed = true
                        }
                    }
                }
            }
        }

        Text {
            anchors.fill: entriesView
            visible: root.controller.visibleEntries.length === 0
            text: root.controller.currentSection === "install"
                ? "Enter package terms to search with yay"
                : root.controller.currentSection === "remove"
                    ? root.controller.removeActions.loading
                        ? "Loading installed packages…"
                        : root.controller.removeActions.errorMessage !== ""
                            ? root.controller.removeActions.errorMessage
                            : "No matching installed packages"
                : root.controller.currentSection === "update"
                    ? "No matching update actions"
                : root.controller.currentSection === "components"
                    ? root.controller.systemComponentsActions.errorMessage !== ""
                        ? root.controller.systemComponentsActions.errorMessage
                        : "No matching optional components"
                : "No matching apps or actions"
            textFormat: Text.PlainText
            color: root.controller.currentSection === "remove"
                    && root.controller.removeActions.errorMessage !== ""
                    || root.controller.currentSection === "components"
                    && root.controller.systemComponentsActions.errorMessage !== ""
                ? root.theme.danger : root.theme.textMuted
            font.pixelSize: root.metrics.overlayFontSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            id: footerText

            anchors {
                bottom: parent.bottom
                left: parent.left
                right: parent.right
            }
            height: root.metrics.captionLineHeight
            text: root.controller.currentSection === "install"
                ? root.controller.searchText.trim() === ""
                    ? "Type package terms, then press Enter"
                    : "Enter or click to open yay in Foot"
                : root.controller.currentSection === "remove"
                    ? root.controller.removeActions.loading
                        ? "Reading pacman's local package database"
                        : root.controller.removeActions.errorMessage !== ""
                            ? "Back, then reopen Remove to retry"
                            : root.controller.visibleEntries.length === 1
                                ? "1 installed package"
                                : root.controller.visibleEntries.length
                                    + " installed packages"
                : root.controller.currentSection === "components"
                    ? root.controller.systemComponentsActions.operationRunning
                            || root.controller.zigScreensaverActions.operationRunning
                        ? "Operation running in Foot"
                        : root.controller.currentComponentId !== ""
                            ? "Enter or click to choose" : "Optional components"
                : root.controller.visibleEntries.length === 1
                    ? "1 result"
                    : root.controller.visibleEntries.length + " results"
            textFormat: Text.PlainText
            color: root.theme.textMuted
            font.pixelSize: root.metrics.captionFontSize
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter
        }
    }
}
