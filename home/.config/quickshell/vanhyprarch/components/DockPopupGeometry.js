function clampMargin(preferredMargin, panelExtent, screenExtent, safeInset) {
    const inset = Math.max(0, Math.round(safeInset || 0))
    const maximumMargin = Math.max(inset,
        Math.round(screenExtent - panelExtent - inset))
    return Math.max(inset,
        Math.min(Math.round(preferredMargin), maximumMargin))
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
        screenHeight, safeInset) {
    const preferred = anchorY + anchorHeight - parallelOffset - panelHeight
    return clampMargin(preferred, panelHeight, screenHeight, safeInset)
}

function alignedTopMargin(anchorY, topOffset, panelHeight, screenHeight,
        safeInset) {
    return clampMargin(anchorY - topOffset, panelHeight, screenHeight,
        safeInset)
}
