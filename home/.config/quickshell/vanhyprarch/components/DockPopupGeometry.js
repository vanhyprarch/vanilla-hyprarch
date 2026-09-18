function clampMargin(preferredMargin, panelExtent, screenExtent) {
    const maximumMargin = Math.max(0,
        Math.round(screenExtent - panelExtent))
    return Math.max(0, Math.min(Math.round(preferredMargin), maximumMargin))
}

function anchorReady(anchorItem, anchorWindow, targetScreen) {
    return Boolean(anchorItem && anchorWindow && targetScreen
        && anchorWindow.screen === targetScreen)
}

function mapAnchorRect(anchorItem, anchorWindow, targetScreen, mapper) {
    if (!anchorReady(anchorItem, anchorWindow, targetScreen))
        return null

    return mapper(anchorItem)
}

function surfaceVisible(requestedVisible, placementReady) {
    return Boolean(requestedVisible && placementReady)
}

function horizontalMargin(gap, panelWidth, screenWidth, persistentLeftInset) {
    const leftInset = Math.max(0,
        Math.min(persistentLeftInset, screenWidth))
    // The compositor has already moved the PanelWindow origin past the dock.
    return clampMargin(gap, panelWidth, screenWidth - leftInset)
}

function aboveMargin(anchorY, anchorHeight, parallelOffset, panelHeight,
        screenHeight) {
    const preferred = anchorY + anchorHeight - parallelOffset - panelHeight
    return clampMargin(preferred, panelHeight, screenHeight)
}

function alignedTopMargin(anchorY, topOffset, panelHeight, screenHeight) {
    return clampMargin(anchorY - topOffset, panelHeight, screenHeight)
}
