function clampMargin(preferredMargin, panelExtent, screenExtent) {
    const maximumMargin = Math.max(0,
        Math.round(screenExtent - panelExtent))
    return Math.max(0, Math.min(Math.round(preferredMargin), maximumMargin))
}

function horizontalMargin(anchorX, anchorWidth, anchorParentWidth, gap,
        panelWidth, screenWidth) {
    const centeredInset = Math.max(0,
        (anchorParentWidth - anchorWidth) / 2)
    const preferred = anchorX + anchorWidth + centeredInset + gap - 1
    return clampMargin(preferred, panelWidth, screenWidth)
}

function aboveMargin(anchorY, anchorHeight, parallelOffset, panelHeight,
        screenHeight) {
    const preferred = anchorY + anchorHeight - parallelOffset - panelHeight
    return clampMargin(preferred, panelHeight, screenHeight)
}

function alignedTopMargin(anchorY, topOffset, panelHeight, screenHeight) {
    return clampMargin(anchorY - topOffset, panelHeight, screenHeight)
}
