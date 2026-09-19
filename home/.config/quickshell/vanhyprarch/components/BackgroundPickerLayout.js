function previewWidth(surfaceWidth, horizontalPadding, maximumWidth,
        surfaceHeight, verticalPadding, distanceTwoScale,
        distanceTwoOffsetScale) {
    const compositionScale = distanceTwoOffsetScale * 2
        + distanceTwoScale
    const horizontalLimit = Math.floor(Math.max(1,
        surfaceWidth - horizontalPadding * 2) / compositionScale)
    const verticalLimit = Math.floor(Math.max(1,
        surfaceHeight - verticalPadding * 2) * 16 / 9)
    return Math.max(1, Math.min(maximumWidth, horizontalLimit,
        verticalLimit))
}

function previewHeight(width) {
    return Math.max(1, Math.round(width * 9 / 16))
}

function visualDistance(index, currentIndex, count) {
    if (index < 0 || index >= count || currentIndex < 0
            || currentIndex >= count)
        return -1
    return Math.abs(index - currentIndex)
}

function visible(index, currentIndex, count) {
    const distance = visualDistance(index, currentIndex, count)
    return distance >= 0 && distance <= 2
}

function sourceActive(index, currentIndex, count) {
    return visible(index, currentIndex, count)
}

function cardStep(previewWidth, preferredStep, minimumStep) {
    return Math.min(preferredStep,
        Math.max(minimumStep, Math.round(previewWidth * 0.38)))
}

function cardWidth(previewWidth, distance, distanceOneScale,
        distanceTwoScale) {
    if (distance === 0)
        return previewWidth
    if (distance === 1)
        return Math.max(1, Math.round(previewWidth * distanceOneScale))
    if (distance === 2)
        return Math.max(1, Math.round(previewWidth * distanceTwoScale))
    return 1
}

function cardCenterOffset(index, currentIndex, count, previewWidth,
        distanceOneOffsetScale, distanceTwoOffsetScale) {
    const distance = visualDistance(index, currentIndex, count)
    if (distance <= 0 || distance > 2)
        return 0
    const direction = index < currentIndex ? -1 : 1
    const scale = distance === 1
        ? distanceOneOffsetScale : distanceTwoOffsetScale
    return direction * Math.round(previewWidth * scale)
}

function cardTranslation(index, currentIndex, count, cardStep, previewWidth,
        distanceOneOffsetScale, distanceTwoOffsetScale) {
    const distance = visualDistance(index, currentIndex, count)
    if (distance < 0 || distance > 2)
        return 0
    return cardCenterOffset(index, currentIndex, count, previewWidth,
        distanceOneOffsetScale, distanceTwoOffsetScale)
        - (index - currentIndex) * cardStep
}

function cardZ(distance) {
    if (distance === 0)
        return 30
    if (distance === 1)
        return 20
    if (distance === 2)
        return 10
    return 0
}

function cardRect(index, currentIndex, count, surfaceWidth, surfaceHeight,
        previewWidth, distanceOneScale, distanceTwoScale,
        distanceOneOffsetScale, distanceTwoOffsetScale) {
    const distance = visualDistance(index, currentIndex, count)
    if (distance < 0 || distance > 2) {
        return { visible: false, index: index, distance: distance,
            x: 0, y: 0, width: 0, height: 0, z: 0 }
    }

    const width = cardWidth(previewWidth, distance, distanceOneScale,
        distanceTwoScale)
    const height = previewHeight(width)
    const centerOffset = cardCenterOffset(index, currentIndex, count,
        previewWidth, distanceOneOffsetScale, distanceTwoOffsetScale)
    return {
        visible: true,
        index: index,
        distance: distance,
        x: Math.round(surfaceWidth / 2 + centerOffset - width / 2),
        y: Math.round((surfaceHeight - height) / 2),
        width: width,
        height: height,
        z: cardZ(distance)
    }
}

function containsPoint(rect, x, y) {
    return rect.visible && x >= rect.x && x < rect.x + rect.width
        && y >= rect.y && y < rect.y + rect.height
}

function topmostCardAt(x, y, currentIndex, count, surfaceWidth,
        surfaceHeight, previewWidth, distanceOneScale, distanceTwoScale,
        distanceOneOffsetScale, distanceTwoOffsetScale) {
    let match = -1
    let matchZ = -1
    const first = Math.max(0, currentIndex - 2)
    const last = Math.min(count - 1, currentIndex + 2)
    for (let index = first; index <= last; ++index) {
        const rect = cardRect(index, currentIndex, count, surfaceWidth,
            surfaceHeight, previewWidth, distanceOneScale, distanceTwoScale,
            distanceOneOffsetScale, distanceTwoOffsetScale)
        if (containsPoint(rect, x, y) && rect.z > matchZ) {
            match = index
            matchZ = rect.z
        }
    }
    return match
}

function compositionWidth(previewWidth, distanceTwoWidth,
        distanceTwoOffset) {
    return Math.max(previewWidth,
        distanceTwoOffset * 2 + distanceTwoWidth)
}

function edgeSpacer(surfaceWidth, cardStep) {
    return Math.max(0, (surfaceWidth - cardStep) / 2)
}
