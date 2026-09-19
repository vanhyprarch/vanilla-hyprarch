function previewWidth(panelWidth, horizontalPadding, maximumWidth,
        panelHeight, verticalChrome) {
    const horizontalLimit = panelWidth - horizontalPadding * 2
    const verticalLimit = Math.floor(Math.max(1,
        panelHeight - verticalChrome) * 16 / 9)
    return Math.max(1, Math.min(maximumWidth, horizontalLimit,
        verticalLimit))
}

function previewHeight(width) {
    return Math.max(1, Math.round(width * 9 / 16))
}

function sourceActive(index, currentIndex, count, radius) {
    if (index < 0 || index >= count || currentIndex < 0
            || currentIndex >= count)
        return false
    return Math.abs(index - currentIndex) <= radius
}

function cardStep(previewWidth, preferredStep, minimumStep) {
    return Math.min(preferredStep,
        Math.max(minimumStep, Math.round(previewWidth * 0.36)))
}
