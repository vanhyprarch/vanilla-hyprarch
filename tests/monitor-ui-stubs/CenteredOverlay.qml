import QtQuick

Item {
    required property var focusCoordinator
    required property var targetScreen
    required property string screenName
    required property int screenWidth
    required property int screenHeight
    property int persistentLeftInset: 0
    property color color: "transparent"

    signal dismissed
}
