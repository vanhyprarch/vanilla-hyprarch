.pragma library

function coordinate(origin, extent, surfaceExtent) {
    return origin + Math.floor((extent - surfaceExtent) / 2)
}

function margin(extent, surfaceExtent) {
    return coordinate(0, extent, surfaceExtent)
}

function usableCoordinate(origin, extent, persistentLeftInset, surfaceExtent) {
    const leftInset = Math.max(0, Math.min(persistentLeftInset, extent))
    return coordinate(origin + leftInset, extent - leftInset, surfaceExtent)
}

function usableMargin(extent, persistentLeftInset, surfaceExtent) {
    const leftInset = Math.max(0, Math.min(persistentLeftInset, extent))
    // PanelWindow margins are relative to the compositor's usable origin.
    return margin(extent - leftInset, surfaceExtent)
}

function usableCenter(origin, extent, persistentLeftInset, surfaceExtent) {
    return usableCoordinate(origin, extent, persistentLeftInset,
        surfaceExtent) + surfaceExtent / 2
}

function center(origin, extent, surfaceExtent) {
    return coordinate(origin, extent, surfaceExtent) + surfaceExtent / 2
}
