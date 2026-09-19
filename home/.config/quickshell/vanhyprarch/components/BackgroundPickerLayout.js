function previewWidth(surfaceWidth, horizontalPadding, maximumWidth,
        surfaceHeight, verticalPadding, horizontalShare) {
    const horizontalLimit = Math.floor(Math.max(1,
        surfaceWidth - horizontalPadding * 2) * horizontalShare)
    const verticalLimit = Math.floor(Math.max(1,
        surfaceHeight - verticalPadding * 2) * 16 / 9)
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
        Math.max(minimumStep, Math.round(previewWidth * 0.38)))
}

function adjacentWidth(previewWidth, maximumWidth) {
    return Math.max(1, Math.min(maximumWidth,
        Math.round(previewWidth * 0.58)))
}

function compositionWidth(previewWidth, adjacentWidth, cardStep) {
    return Math.max(previewWidth,
        2 * cardStep + adjacentWidth)
}

function edgeSpacer(surfaceWidth, cardStep) {
    return Math.max(0, (surfaceWidth - cardStep) / 2)
}
