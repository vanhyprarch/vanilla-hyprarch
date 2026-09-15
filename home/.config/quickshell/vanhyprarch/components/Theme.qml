import QtQuick

QtObject {
    property bool darkMode: false

    readonly property color background: darkMode ? "#1C1714" : "#FFF8F5"
    readonly property color surface: darkMode ? "#2A211C" : "#FAEAE3"
    readonly property color hover: darkMode ? "#3A2D26" : "#F3D8CC"
    readonly property color accent: darkMode ? "#C07A52" : "#8D4C2B"
    readonly property color text: darkMode ? "#F3E7DF" : "#5A3525"
}
