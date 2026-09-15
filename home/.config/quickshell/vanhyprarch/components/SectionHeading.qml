import QtQuick

Text {
    id: root

    required property var metrics
    required property var theme

    textFormat: Text.PlainText
    color: root.theme.textMuted
    font.pixelSize: root.metrics.sectionHeadingFontSize
    font.weight: root.metrics.sectionHeadingFontWeight
}
